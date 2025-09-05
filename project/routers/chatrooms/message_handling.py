# project/routers/chatrooms/message_handling.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from project.database import get_db
from project.utils import get_current_user_id
from project.models import ChatRoom, ChatRoomMember, ChatMessage, User
import project.schemas as schemas
from project.services.message_service import MessageService
from project.utils.security.permissions import check_room_access
from project.utils.async_cache.cache import cache
from project.utils import _award_points, _check_and_award_achievements
from project.services.chatroom_base_service import ChatRoomBaseService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/chatrooms/{room_id}/messages/", response_model=schemas.ChatMessageResponse, summary="发送文本消息")
@ChatRoomBaseService.handle_chatroom_operation(require_room_access=True, award_points=1, points_reason="发送消息", invalidate_cache=True)
async def create_message(
    room_id: int,
    message: schemas.ChatMessageCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    room=None,  # 由装饰器注入
    member=None  # 由装饰器注入
):
    """发送文本消息"""
    # 验证回复消息（如果存在）
    if message.reply_to_id:
        reply_to = db.query(ChatMessage).filter(
            ChatMessage.id == message.reply_to_id,
            ChatMessage.room_id == room_id
        ).first()
        
        if not reply_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="回复的消息不存在"
            )
    
    # 创建消息
    db_message = await ChatRoomBaseService.create_message_with_cache(
        db=db,
        room_id=room_id,
        sender_id=current_user_id,
        content=message.content,
        message_type="text",
        reply_to_id=message.reply_to_id
    )
    
    return db_message

@router.get("/chatrooms/{room_id}/messages/", response_model=dict, summary="获取聊天室消息")
@ChatRoomBaseService.handle_chatroom_operation(require_room_access=True, invalidate_cache=False)
async def get_chat_messages(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(50, ge=1, le=100, description="每页数量"),
    message_type: Optional[str] = Query(None, description="消息类型过滤"),
    user_id: Optional[int] = Query(None, description="用户过滤"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    room=None,  # 由装饰器注入
    member=None  # 由装饰器注入
):
    """获取聊天室消息"""
    # 尝试从缓存获取最近消息（仅第一页且无过滤条件时）
    if page == 1 and not any([message_type, user_id, start_date, end_date]):
        cached_messages = await cache.get_recent_messages(room_id, size)
        if cached_messages:
            return {
                "messages": cached_messages,
                "pagination": {
                    "total": len(cached_messages),
                    "page": 1,
                    "size": size,
                    "total_pages": 1,
                    "has_next": False,
                    "has_prev": False
                }
            }
    
    # 使用统一分页处理
    async def query_messages(offset: int, limit: int, **kwargs):
        result = await MessageService.get_messages_with_pagination(
            db=db,
            room_id=room_id,
            page=(offset // limit) + 1,
            size=limit,
            message_type=message_type,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        return result["messages"], result["total"]
    
    return await ChatRoomBaseService.handle_pagination(
        query_func=query_messages,
        page=page,
        size=size
    )

@router.put("/chatrooms/{room_id}/messages/{message_id}/recall", summary="撤回消息")
@ChatRoomBaseService.handle_chatroom_operation(require_room_access=True, invalidate_cache=True)
async def recall_message(
    room_id: int,
    message_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    room=None,  # 由装饰器注入
    member=None  # 由装饰器注入
):
    """撤回消息"""
    # 撤回消息
    recalled_message = await MessageService.recall_message(db, message_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 撤回了消息 {message_id}")
    
    return {
        "message": "消息已撤回",
        "message_id": message_id,
        "recalled_at": recalled_message.recalled_at
    }

@router.put("/chatrooms/{room_id}/messages/{message_id}/pin", summary="置顶消息")
@ChatRoomBaseService.handle_chatroom_operation(require_room_access=True, invalidate_cache=True)
async def pin_message(
    room_id: int,
    message_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    room=None,  # 由装饰器注入
    member=None  # 由装饰器注入
):
    """置顶消息"""
    # 置顶消息（权限检查在服务层进行）
    pinned_message = await MessageService.pin_message(db, room_id, message_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 置顶了消息 {message_id}")
    
    return {
        "message": "消息已置顶",
        "message_id": message_id,
        "pinned_at": pinned_message.pinned_at
    }

@router.post("/chatrooms/{room_id}/messages/{message_id}/forward", summary="转发消息")
async def forward_message(
    room_id: int,
    message_id: int,
    forward_data: schemas.ForwardMessageRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """转发消息到其他聊天室"""
    try:
        # 检查原聊天室访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 转发消息
        forwarded_message = await MessageService.forward_message(
            db=db,
            message_id=message_id,
            from_room_id=room_id,
            to_room_id=forward_data.to_room_id,
            user_id=current_user_id,
            additional_message=forward_data.message
        )
        
        # 清除相关缓存
        await cache.invalidate_room_cache(forward_data.to_room_id)
        
        logger.info(f"用户 {current_user_id} 将消息 {message_id} 从聊天室 {room_id} 转发到 {forward_data.to_room_id}")
        
        return {
            "message": "消息已转发",
            "original_message_id": message_id,
            "forwarded_message_id": forwarded_message.id,
            "to_room_id": forward_data.to_room_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"转发消息失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="转发消息失败"
        )


@router.post("/chatrooms/{room_id}/messages/batch-forward", response_model=schemas.ForwardOperationResponse, summary="批量转发消息")
async def batch_forward_messages(
    room_id: int,
    forward_data: schemas.BatchForwardMessageRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """批量转发选中的消息到多个聊天室"""
    try:
        # 检查原聊天室访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 执行批量转发
        result = await MessageService.batch_forward_messages(
            db=db,
            message_ids=forward_data.message_ids,
            from_room_id=room_id,
            to_room_ids=forward_data.to_room_ids,
            user_id=current_user_id,
            additional_message=forward_data.message
        )
        
        # 清除相关缓存
        for to_room_id in forward_data.to_room_ids:
            await cache.invalidate_room_cache(to_room_id)
        
        logger.info(f"用户 {current_user_id} 批量转发了 {len(forward_data.message_ids)} 条消息到 {len(forward_data.to_room_ids)} 个聊天室")
        
        return schemas.ForwardOperationResponse(
            success=result["success"],
            message="批量转发完成",
            total_messages=result["total_messages"],
            total_rooms=result["total_rooms"],
            successful_forwards=result["successful_forwards"],
            failed_forwards=result["failed_forwards"],
            results=result["results"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量转发消息失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="批量转发消息失败"
        )


@router.post("/chatrooms/{room_id}/files/forward", response_model=schemas.ForwardOperationResponse, summary="转发文件到多个聊天室")
async def forward_file_to_rooms(
    room_id: int,
    forward_data: schemas.ForwardFileRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """转发文件到多个聊天室"""
    try:
        # 检查原聊天室访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 执行文件转发
        result = await MessageService.forward_file_to_rooms(
            db=db,
            file_message_id=forward_data.file_message_id,
            from_room_id=room_id,
            to_room_ids=forward_data.to_room_ids,
            user_id=current_user_id,
            additional_message=forward_data.message
        )
        
        # 清除相关缓存
        for to_room_id in forward_data.to_room_ids:
            await cache.invalidate_room_cache(to_room_id)
        
        logger.info(f"用户 {current_user_id} 转发文件 {forward_data.file_message_id} 到 {len(forward_data.to_room_ids)} 个聊天室")
        
        return schemas.ForwardOperationResponse(
            success=result["success"],
            message=f"文件 {result.get('file_name', '未知文件')} 转发完成",
            total_rooms=result["total_rooms"],
            successful_forwards=result["successful_forwards"],
            failed_forwards=result["failed_forwards"],
            results=result["results"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"转发文件失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="转发文件失败"
        )


@router.get("/chatrooms/{room_id}/messages/selectable", response_model=List[schemas.ChatMessageResponse], summary="获取可选择转发的消息")
async def get_selectable_messages(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    start_message_id: Optional[int] = Query(None, description="起始消息ID"),
    end_message_id: Optional[int] = Query(None, description="结束消息ID"),
    include_media: bool = Query(True, description="是否包含媒体文件"),
    max_messages: int = Query(50, ge=1, le=100, description="最大消息数量")
):
    """获取可选择转发的消息列表"""
    try:
        # 获取可选择的消息
        messages = await MessageService.get_selectable_messages(
            db=db,
            room_id=room_id,
            user_id=current_user_id,
            start_message_id=start_message_id,
            end_message_id=end_message_id,
            include_media=include_media,
            max_messages=max_messages
        )
        
        # 转换为响应模型
        response_messages = []
        for message in messages:
            # 获取发送者信息
            sender = db.query(User).filter(User.id == message.sender_id).first()
            sender_name = sender.username if sender else f"用户{message.sender_id}"
            
            # 构建响应
            message_response = schemas.ChatMessageResponse(
                id=message.id,
                room_id=message.room_id,
                sender_id=message.sender_id,
                content_text=message.content_text,
                message_type=message.message_type,
                media_url=message.media_url,
                original_filename=message.original_filename,
                file_size=message.file_size_bytes,
                audio_duration=message.audio_duration,
                reply_to_message_id=message.reply_to_message_id,
                is_pinned=message.is_pinned,
                sent_at=message.sent_at or message.created_at,
                created_at=message.created_at,
                updated_at=message.updated_at,
                sender_name=sender_name
            )
            response_messages.append(message_response)
        
        return response_messages
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取可选择消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取可选择消息失败"
        )

@router.get("/chatrooms/{room_id}/media", response_model=List[schemas.ChatMessageResponse], summary="获取聊天室媒体文件")
async def get_chat_room_media(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    media_type: str = Query("all", description="媒体类型 (all/image/video/audio/document)"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """获取聊天室媒体文件"""
    try:
        # 检查访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 获取媒体消息
        result = await MessageService.get_media_messages(
            db=db,
            room_id=room_id,
            media_type=media_type,
            page=page,
            size=size
        )
        
        return {
            "media_messages": result["messages"],
            "pagination": {
                "total": result["total"],
                "page": result["page"],
                "size": result["size"],
                "total_pages": result["total_pages"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取媒体文件失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取媒体文件失败"
        )

@router.delete("/chatrooms/{room_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除消息")
async def delete_message(
    room_id: int,
    message_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除消息"""
    try:
        # 检查访问权限
        room, member = check_room_access(db, room_id, current_user_id)
        
        # 检查是否是管理员
        is_admin = member.role in ['creator', 'admin']
        
        # 删除消息
        await MessageService.delete_message(db, message_id, current_user_id, is_admin)
        
        # 清除相关缓存
        await cache.invalidate_room_cache(room_id)
        
        logger.info(f"用户 {current_user_id} 删除了消息 {message_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除消息失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除消息失败"
        )

@router.get("/chatrooms/{room_id}/messages/search", summary="搜索聊天室消息")
async def search_messages(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    query: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """搜索聊天室消息"""
    try:
        # 检查访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 搜索消息
        from sqlalchemy import func
        
        search_results = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.content.contains(query),
            ChatMessage.is_deleted != True
        ).order_by(
            ChatMessage.created_at.desc()
        ).offset((page - 1) * size).limit(size).all()
        
        # 获取总数
        total = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.content.contains(query),
            ChatMessage.is_deleted != True
        ).count()
        
        return {
            "messages": search_results,
            "query": query,
            "pagination": {
                "total": total,
                "page": page,
                "size": size,
                "total_pages": (total + size - 1) // size
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="搜索消息失败"
        )
