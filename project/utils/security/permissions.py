# project/utils/permissions.py
from functools import wraps
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from project.models import ChatRoom, ChatRoomMember, User
from typing import List, Optional, Tuple

def require_room_access(roles: Optional[List[str]] = None):
    """聊天室访问权限装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从参数中提取必要的信息
            room_id = kwargs.get('room_id')
            current_user_id = kwargs.get('current_user_id')
            db = kwargs.get('db')
            
            if not all([room_id, current_user_id, db]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="缺少必要的参数"
                )
            
            # 检查聊天室是否存在
            room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
            if not room:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="聊天室不存在"
                )
            
            # 检查用户是否有访问权限
            member = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == room_id,
                ChatRoomMember.user_id == current_user_id,
                ChatRoomMember.status == "active"
            ).first()
            
            if not member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="您不是该聊天室的成员"
                )
            
            # 检查角色权限
            if roles and member.role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="您没有执行此操作的权限"
                )
            
            # 将权限信息添加到kwargs中
            kwargs['current_member'] = member
            kwargs['current_room'] = room
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_admin_access():
    """管理员权限装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user_id = kwargs.get('current_user_id')
            db = kwargs.get('db')
            
            if not all([current_user_id, db]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="缺少必要的参数"
                )
            
            # 检查用户是否为管理员
            user = db.query(User).filter(User.id == current_user_id).first()
            if not user or user.role != 'admin':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="需要管理员权限"
                )
            
            kwargs['current_admin'] = user
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def check_room_access(db: Session, room_id: int, user_id: int) -> Tuple[ChatRoom, ChatRoomMember]:
    """检查用户对聊天室的访问权限"""
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="聊天室不存在"
        )
    
    member = db.query(ChatRoomMember).filter(
        ChatRoomMember.room_id == room_id,
        ChatRoomMember.user_id == user_id,
        ChatRoomMember.status == "active"
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您不是该聊天室的成员"
        )
    
    return room, member

def check_admin_role(db: Session, user_id: int) -> User:
    """检查用户是否为管理员"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return user
