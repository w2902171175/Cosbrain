# project/services/chatroom_service.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func
from sqlalchemy import desc, and_
from typing import List, Optional, Dict
from project.models import ChatRoom, ChatRoomMember, ChatMessage, User
import project.schemas as schemas
from datetime import datetime

class ChatRoomService:
    @staticmethod
    async def populate_room_stats(rooms: List[ChatRoom], db: Session) -> List[ChatRoom]:
        """批量填充聊天室统计信息"""
        if not rooms:
            return rooms
            
        room_ids = [room.id for room in rooms]
        
        # 批量查询成员数量
        member_counts = db.query(
            ChatRoomMember.room_id,
            func.count(ChatRoomMember.id).label('count')
        ).filter(
            ChatRoomMember.room_id.in_(room_ids),
            ChatRoomMember.status == "active"
        ).group_by(ChatRoomMember.room_id).all()
        
        member_counts_dict = {row.room_id: row.count for row in member_counts}
        
        # 批量查询最新消息
        latest_messages = db.query(
            ChatMessage.room_id,
            func.max(ChatMessage.created_at).label('latest_time')
        ).filter(
            ChatMessage.room_id.in_(room_ids)
        ).group_by(ChatMessage.room_id).all()
        
        latest_times_dict = {row.room_id: row.latest_time for row in latest_messages}
        
        # 批量查询消息数量
        message_counts = db.query(
            ChatMessage.room_id,
            func.count(ChatMessage.id).label('count')
        ).filter(
            ChatMessage.room_id.in_(room_ids)
        ).group_by(ChatMessage.room_id).all()
        
        message_counts_dict = {row.room_id: row.count for row in message_counts}
        
        # 填充数据
        for room in rooms:
            room.members_count = member_counts_dict.get(room.id, 0)
            room.latest_message_time = latest_times_dict.get(room.id)
            room.messages_count = message_counts_dict.get(room.id, 0)
            
        return rooms

    @staticmethod
    async def get_room_with_stats(db: Session, room_id: int) -> Optional[ChatRoom]:
        """获取包含统计信息的聊天室"""
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return None
            
        # 获取成员数量
        members_count = db.query(func.count(ChatRoomMember.id)).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.status == "active"
        ).scalar()
        
        # 获取消息数量
        messages_count = db.query(func.count(ChatMessage.id)).filter(
            ChatMessage.room_id == room_id
        ).scalar()
        
        # 获取最新消息时间
        latest_message = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id
        ).order_by(desc(ChatMessage.created_at)).first()
        
        room.members_count = members_count
        room.messages_count = messages_count
        room.latest_message_time = latest_message.created_at if latest_message else None
        
        return room

    @staticmethod
    async def get_user_rooms_with_stats(db: Session, user_id: int) -> List[ChatRoom]:
        """获取用户所有聊天室及其统计信息"""
        # 获取用户所属的聊天室
        rooms = db.query(ChatRoom).join(
            ChatRoomMember, ChatRoom.id == ChatRoomMember.room_id
        ).filter(
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.status == "active"
        ).options(
            joinedload(ChatRoom.creator)
        ).all()
        
        # 批量填充统计信息
        return await ChatRoomService.populate_room_stats(rooms, db)

    @staticmethod
    async def get_room_members_with_user_info(db: Session, room_id: int) -> List[Dict]:
        """获取聊天室成员及其用户信息"""
        members = db.query(ChatRoomMember).options(
            joinedload(ChatRoomMember.user)
        ).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.status == "active"
        ).all()
        
        result = []
        for member in members:
            user_info = {
                "id": member.id,
                "user_id": member.user_id,
                "role": member.role,
                "joined_at": member.joined_at,
                "user_name": member.user.name if member.user else "未知用户",
                "user_avatar": getattr(member.user, 'avatar_url', None) if member.user else None
            }
            result.append(user_info)
            
        return result

    @staticmethod
    async def check_duplicate_room(db: Session, name: str, creator_id: int) -> bool:
        """检查是否存在重复的聊天室名称"""
        existing_room = db.query(ChatRoom).filter(
            ChatRoom.name == name,
            ChatRoom.creator_id == creator_id
        ).first()
        return existing_room is not None

    @staticmethod
    async def get_room_messages_with_pagination(
        db: Session, 
        room_id: int, 
        page: int = 1, 
        size: int = 50,
        message_type: Optional[str] = None
    ) -> Dict:
        """分页获取聊天室消息"""
        query = db.query(ChatMessage).filter(ChatMessage.room_id == room_id)
        
        if message_type:
            query = query.filter(ChatMessage.message_type == message_type)
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        messages = query.options(
            joinedload(ChatMessage.sender),
            joinedload(ChatMessage.reply_to)
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
