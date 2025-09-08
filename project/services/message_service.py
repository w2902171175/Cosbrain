# project/services/message_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func
from sqlalchemy import desc, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from project.models import ChatMessage, ChatRoom, ChatRoomMember, User
import project.schemas as schemas
from fastapi import HTTPException, status

class MessageService:
    @staticmethod
    async def create_message_async(
        db: Session,
        room_id: int,
        sender_id: int,
        content: str,
        message_type: str = "text",
        media_url: Optional[str] = None,
        reply_to_id: Optional[int] = None,
        file_info: Optional[Dict] = None
    ) -> ChatMessage:
        """异步创建消息"""
        message_data = {
            "room_id": room_id,
            "sender_id": sender_id,
            "content": content,
            "message_type": message_type,
            "media_url": media_url,
            "reply_to_id": reply_to_id,
            "created_at": datetime.now()
        }
        
        # 如果有文件信息，添加到内容中
        if file_info:
            message_data["file_size"] = file_info.get("file_size")
            message_data["file_name"] = file_info.get("original_filename")
        
        db_message = ChatMessage(**message_data)
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        return db_message

    @staticmethod
    async def get_messages_with_pagination(
        db: Session,
        room_id: int,
        page: int = 1,
        size: int = 50,
        message_type: Optional[str] = None,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """分页获取消息"""
        query = db.query(ChatMessage).filter(ChatMessage.room_id == room_id)
        
        # 应用过滤条件
        if message_type:
            query = query.filter(ChatMessage.message_type == message_type)
        
        if user_id:
            query = query.filter(ChatMessage.sender_id == user_id)
        
        if start_date:
            query = query.filter(ChatMessage.created_at >= start_date)
        
        if end_date:
            query = query.filter(ChatMessage.created_at <= end_date)
        
        # 获取总数
        total = query.count()
        
        # 分页查询，预加载相关数据
        messages = query.options(
            joinedload(ChatMessage.sender),
            joinedload(ChatMessage.reply_to).joinedload(ChatMessage.sender)
        ).order_by(
            desc(ChatMessage.created_at)
        ).offset((page - 1) * size).limit(size).all()
        
        return {
            "messages": messages,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size
        }

    @staticmethod
    async def recall_message(db: Session, message_id: int, user_id: int) -> ChatMessage:
        """撤回消息"""
        message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="消息不存在"
            )
        
        # 检查是否是消息发送者
        if message.sender_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能撤回自己的消息"
            )
        
        # 检查撤回时间限制（例如：只能撤回2分钟内的消息）
        time_limit = datetime.now() - timedelta(minutes=2)
        if message.created_at < time_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="消息发送超过2分钟，无法撤回"
            )
        
        # 标记为已撤回
        message.is_recalled = True
        message.recalled_at = datetime.now()
        message.content = "[此消息已被撤回]"
        
        db.commit()
        db.refresh(message)
        
        return message

    @staticmethod
    async def pin_message(db: Session, room_id: int, message_id: int, user_id: int) -> ChatMessage:
        """置顶消息"""
        # 检查用户权限（需要是管理员或创建者）
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.status == "active"
        ).first()
        
        if not member or member.role not in ['admin', 'creator']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有管理员或创建者可以置顶消息"
            )
        
        message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room_id
        ).first()
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="消息不存在"
            )
        
        # 取消其他置顶消息
        db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.is_pinned == True
        ).update({"is_pinned": False})
        
        # 置顶当前消息
        message.is_pinned = True
        message.pinned_at = datetime.now()
        message.pinned_by = user_id
        
        db.commit()
        db.refresh(message)
        
        return message

    @staticmethod
    async def forward_message(
        db: Session,
        message_id: int,
        from_room_id: int,
        to_room_id: int,
        user_id: int,
        additional_message: Optional[str] = None
    ) -> ChatMessage:
        """转发单个消息"""
        # 检查原消息
        original_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == from_room_id
        ).first()
        
        if not original_message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="原消息不存在"
            )
        
        # 检查用户是否是目标聊天室成员
        target_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == to_room_id,
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.status == "active"
        ).first()
        
        if not target_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您不是目标聊天室的成员"
            )
        
        # 构建转发内容
        forward_content = f"[转发消息]"
        if additional_message:
            forward_content = f"{additional_message}\n\n{forward_content}"
        
        if original_message.content_text:
            forward_content += f"\n{original_message.content_text}"
        
        # 创建转发消息
        forwarded_message = ChatMessage(
            room_id=to_room_id,
            sender_id=user_id,
            content_text=forward_content,
            message_type=original_message.message_type,
            media_url=original_message.media_url,
            original_filename=original_message.original_filename,
            file_size_bytes=original_message.file_size_bytes,
            audio_duration=original_message.audio_duration,
            reply_to_message_id=None  # 转发消息不保持回复关系
        )
        
        db.add(forwarded_message)
        db.commit()
        db.refresh(forwarded_message)
        
        return forwarded_message

    @staticmethod
    async def batch_forward_messages(
        db: Session,
        message_ids: List[int],
        from_room_id: int,
        to_room_ids: List[int],
        user_id: int,
        additional_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """批量转发消息到多个聊天室"""
        results = []
        successful_forwards = 0
        failed_forwards = 0
        
        # 验证原消息存在
        original_messages = db.query(ChatMessage).filter(
            ChatMessage.id.in_(message_ids),
            ChatMessage.room_id == from_room_id,
            ChatMessage.deleted_at.is_(None)
        ).all()
        
        if not original_messages:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到有效的原消息"
            )
        
        # 验证用户对所有目标聊天室的访问权限
        accessible_rooms = db.query(ChatRoomMember.room_id).filter(
            ChatRoomMember.room_id.in_(to_room_ids),
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.status == "active"
        ).all()
        
        accessible_room_ids = [room.room_id for room in accessible_rooms]
        
        for to_room_id in to_room_ids:
            if to_room_id not in accessible_room_ids:
                results.append({
                    "room_id": to_room_id,
                    "success": False,
                    "error": "无权限访问此聊天室"
                })
                failed_forwards += 1
                continue
            
            try:
                # 为每个聊天室创建合并的转发消息
                forward_content_parts = []
                
                if additional_message:
                    forward_content_parts.append(additional_message)
                
                forward_content_parts.append(f"[转发了 {len(original_messages)} 条消息]")
                
                # 合并原消息内容
                for i, msg in enumerate(original_messages[:10]):  # 限制显示前10条
                    sender_name = f"用户{msg.sender_id}"  # 简化处理，实际可以查询用户名
                    content_preview = msg.content_text[:100] if msg.content_text else "[媒体文件]"
                    forward_content_parts.append(f"{i+1}. {sender_name}: {content_preview}")
                
                if len(original_messages) > 10:
                    forward_content_parts.append(f"... 及其他 {len(original_messages) - 10} 条消息")
                
                forward_content = "\n".join(forward_content_parts)
                
                # 创建转发消息
                forwarded_message = ChatMessage(
                    room_id=to_room_id,
                    sender_id=user_id,
                    content_text=forward_content,
                    message_type="text"  # 批量转发统一为文本类型
                )
                
                db.add(forwarded_message)
                db.flush()  # 获取消息ID但不提交
                
                results.append({
                    "room_id": to_room_id,
                    "success": True,
                    "message_id": forwarded_message.id,
                    "forwarded_count": len(original_messages)
                })
                successful_forwards += 1
                
            except Exception as e:
                results.append({
                    "room_id": to_room_id,
                    "success": False,
                    "error": str(e)
                })
                failed_forwards += 1
        
        if successful_forwards > 0:
            db.commit()
        else:
            db.rollback()
        
        return {
            "success": successful_forwards > 0,
            "total_messages": len(original_messages),
            "total_rooms": len(to_room_ids),
            "successful_forwards": successful_forwards,
            "failed_forwards": failed_forwards,
            "results": results
        }

    @staticmethod
    async def forward_file_to_rooms(
        db: Session,
        file_message_id: int,
        from_room_id: int,
        to_room_ids: List[int],
        user_id: int,
        additional_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """转发文件到多个聊天室"""
        # 检查原文件消息
        original_message = db.query(ChatMessage).filter(
            ChatMessage.id == file_message_id,
            ChatMessage.room_id == from_room_id,
            ChatMessage.media_url.isnot(None)
        ).first()
        
        if not original_message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="原文件消息不存在"
            )
        
        results = []
        successful_forwards = 0
        failed_forwards = 0
        
        # 验证用户对所有目标聊天室的访问权限
        accessible_rooms = db.query(ChatRoomMember.room_id).filter(
            ChatRoomMember.room_id.in_(to_room_ids),
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.status == "active"
        ).all()
        
        accessible_room_ids = [room.room_id for room in accessible_rooms]
        
        for to_room_id in to_room_ids:
            if to_room_id not in accessible_room_ids:
                results.append({
                    "room_id": to_room_id,
                    "success": False,
                    "error": "无权限访问此聊天室"
                })
                failed_forwards += 1
                continue
            
            try:
                # 构建转发内容
                forward_content = f"[转发文件] {original_message.original_filename or '文件'}"
                if additional_message:
                    forward_content = f"{additional_message}\n\n{forward_content}"
                
                # 创建转发消息，复制文件信息
                forwarded_message = ChatMessage(
                    room_id=to_room_id,
                    sender_id=user_id,
                    content_text=forward_content,
                    message_type=original_message.message_type,
                    media_url=original_message.media_url,  # 复用同一个文件URL
                    original_filename=original_message.original_filename,
                    file_size_bytes=original_message.file_size_bytes,
                    audio_duration=original_message.audio_duration
                )
                
                db.add(forwarded_message)
                db.flush()
                
                results.append({
                    "room_id": to_room_id,
                    "success": True,
                    "message_id": forwarded_message.id,
                    "file_name": original_message.original_filename
                })
                successful_forwards += 1
                
            except Exception as e:
                results.append({
                    "room_id": to_room_id,
                    "success": False,
                    "error": str(e)
                })
                failed_forwards += 1
        
        if successful_forwards > 0:
            db.commit()
        else:
            db.rollback()
        
        return {
            "success": successful_forwards > 0,
            "file_name": original_message.original_filename,
            "total_rooms": len(to_room_ids),
            "successful_forwards": successful_forwards,
            "failed_forwards": failed_forwards,
            "results": results
        }

    @staticmethod
    async def get_selectable_messages(
        db: Session,
        room_id: int,
        user_id: int,
        start_message_id: Optional[int] = None,
        end_message_id: Optional[int] = None,
        message_ids: Optional[List[int]] = None,
        include_media: bool = True,
        max_messages: int = 50
    ) -> List[ChatMessage]:
        """获取可选择转发的消息列表"""
        # 检查用户权限
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.status == "active"
        ).first()
        
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您不是此聊天室的成员"
            )
        
        query = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)
        )
        
        # 根据不同的选择方式构建查询
        if message_ids:
            # 指定消息ID列表
            query = query.filter(ChatMessage.id.in_(message_ids))
        elif start_message_id and end_message_id:
            # 消息ID范围
            query = query.filter(
                ChatMessage.id >= start_message_id,
                ChatMessage.id <= end_message_id
            )
        elif start_message_id:
            # 从指定消息开始
            query = query.filter(ChatMessage.id >= start_message_id)
        
        # 是否包含媒体文件
        if not include_media:
            query = query.filter(ChatMessage.message_type == "text")
        
        # 排序和限制数量
        messages = query.order_by(ChatMessage.id.asc()).limit(max_messages).all()
        
        return messages

    @staticmethod
    async def get_media_messages(
        db: Session,
        room_id: int,
        media_type: str = "all",
        page: int = 1,
        size: int = 20
    ) -> Dict:
        """获取聊天室媒体消息"""
        query = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.media_url.isnot(None)
        )
        
        # 根据媒体类型过滤
        if media_type != "all":
            if media_type == "image":
                query = query.filter(ChatMessage.message_type.in_(["image", "gallery"]))
            elif media_type == "video":
                query = query.filter(ChatMessage.message_type == "video")
            elif media_type == "audio":
                query = query.filter(ChatMessage.message_type == "audio")
            elif media_type == "document":
                query = query.filter(ChatMessage.message_type == "document")
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        messages = query.options(
            joinedload(ChatMessage.sender)
        ).order_by(
            desc(ChatMessage.created_at)
        ).offset((page - 1) * size).limit(size).all()
        
        return {
            "messages": messages,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size
        }

    @staticmethod
    async def delete_message(db: Session, message_id: int, user_id: int, is_admin: bool = False) -> bool:
        """删除消息"""
        message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="消息不存在"
            )
        
        # 检查删除权限
        if not is_admin and message.sender_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只能删除自己的消息"
            )
        
        # 软删除：标记为已删除而不是真正删除
        message.is_deleted = True
        message.deleted_at = datetime.now()
        message.deleted_by = user_id
        
        db.commit()
        return True

    @staticmethod
    async def get_message_statistics(db: Session, room_id: int, days: int = 7) -> Dict:
        """获取消息统计信息"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 总消息数
        total_messages = db.query(func.count(ChatMessage.id)).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.created_at >= start_date,
            ChatMessage.is_deleted != True
        ).scalar()
        
        # 按类型统计
        type_stats = db.query(
            ChatMessage.message_type,
            func.count(ChatMessage.id).label('count')
        ).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.created_at >= start_date,
            ChatMessage.is_deleted != True
        ).group_by(ChatMessage.message_type).all()
        
        # 活跃用户统计
        active_users = db.query(
            ChatMessage.sender_id,
            func.count(ChatMessage.id).label('message_count')
        ).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.created_at >= start_date,
            ChatMessage.is_deleted != True
        ).group_by(ChatMessage.sender_id).order_by(
            desc('message_count')
        ).limit(10).all()
        
        return {
            "total_messages": total_messages,
            "type_statistics": {row.message_type: row.count for row in type_stats},
            "active_users": [
                {"user_id": row.sender_id, "message_count": row.message_count}
                for row in active_users
            ],
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
                "days": days
            }
        }
