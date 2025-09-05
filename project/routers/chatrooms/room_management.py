# project/routers/chatrooms/room_management.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from project.database import get_db
from project.utils import get_current_user_id
from project.models import ChatRoom, ChatRoomMember, User
import project.schemas as schemas
from project.services.chatroom_service import ChatRoomService
from project.utils.security.permissions import check_room_access, check_admin_role
from project.utils.async_cache.cache import cache
from project.utils import _award_points, _check_and_award_achievements

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/chat-rooms/", response_model=schemas.ChatRoomResponse, summary="创建新的聊天室")
async def create_chat_room(
    room: schemas.ChatRoomCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建新的聊天室"""
    try:
        # 检查是否存在重复名称的聊天室
        if await ChatRoomService.check_duplicate_room(db, room.name, current_user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经创建了同名的聊天室"
            )
        
        # 创建聊天室
        db_room = ChatRoom(
            name=room.name,
            description=room.description,
            creator_id=current_user_id,
            is_public=room.is_public,
            max_members=room.max_members,
            created_at=datetime.now()
        )
        
        db.add(db_room)
        db.commit()
        db.refresh(db_room)
        
        # 将创建者添加为聊天室管理员
        db_member = ChatRoomMember(
            room_id=db_room.id,
            user_id=current_user_id,
            role="creator",
            status="active",
            joined_at=datetime.now()
        )
        
        db.add(db_member)
        db.commit()
        
        # 奖励积分和成就
        await _award_points(db, current_user_id, 10, "创建聊天室")
        await _check_and_award_achievements(db, current_user_id)
        
        # 清除相关缓存
        await cache.invalidate_user_cache(current_user_id)
        
        # 获取完整的聊天室信息
        room_with_stats = await ChatRoomService.get_room_with_stats(db, db_room.id)
        
        logger.info(f"用户 {current_user_id} 创建了聊天室 {db_room.id}")
        
        return room_with_stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建聊天室失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建聊天室失败"
        )

@router.get("/chatrooms/", response_model=List[schemas.ChatRoomResponse], summary="获取当前用户所属的所有聊天室")
async def get_all_chat_rooms(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """获取当前用户所属的所有聊天室"""
    try:
        # 尝试从缓存获取
        cached_rooms = await cache.get_user_rooms(current_user_id)
        if cached_rooms and page == 1:
            # 只有第一页才使用缓存
            rooms = []
            for room_id in cached_rooms[:size]:
                room_info = await cache.get_room_info(room_id)
                if room_info:
                    rooms.append(room_info)
            
            if rooms:
                return rooms
        
        # 从数据库获取
        all_rooms = await ChatRoomService.get_user_rooms_with_stats(db, current_user_id)
        
        # 分页处理
        start_idx = (page - 1) * size
        end_idx = start_idx + size
        paginated_rooms = all_rooms[start_idx:end_idx]
        
        # 缓存第一页数据
        if page == 1:
            room_ids = [room.id for room in all_rooms]
            await cache.set_user_rooms(current_user_id, room_ids)
            
            # 缓存每个房间信息
            for room in paginated_rooms:
                await cache.set_room_info(room.id, room.__dict__)
        
        return paginated_rooms
        
    except Exception as e:
        logger.error(f"获取用户聊天室列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取聊天室列表失败"
        )

@router.get("/chatrooms/{room_id}", response_model=schemas.ChatRoomResponse, summary="获取指定聊天室详情")
async def get_chat_room_by_id_enhanced(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取指定聊天室详情（增强版）"""
    try:
        # 检查访问权限
        room, member = check_room_access(db, room_id, current_user_id)
        
        # 尝试从缓存获取
        cached_room = await cache.get_room_info(room_id)
        if cached_room:
            return cached_room
        
        # 从数据库获取完整信息
        room_with_stats = await ChatRoomService.get_room_with_stats(db, room_id)
        if not room_with_stats:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聊天室不存在"
            )
        
        # 缓存房间信息
        await cache.set_room_info(room_id, room_with_stats.__dict__)
        
        return room_with_stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取聊天室详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取聊天室详情失败"
        )

@router.put("/chatrooms/{room_id}/", response_model=schemas.ChatRoomResponse, summary="更新指定聊天室")
async def update_chat_room_enhanced(
    room_id: int,
    room_update: schemas.ChatRoomUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新指定聊天室（增强版）"""
    try:
        # 检查权限（只有创建者和管理员可以更新）
        room, member = check_room_access(db, room_id, current_user_id)
        
        if member.role not in ['creator', 'admin']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有创建者和管理员可以更新聊天室"
            )
        
        # 更新聊天室信息
        update_data = room_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(room, field, value)
        
        room.updated_at = datetime.now()
        db.commit()
        db.refresh(room)
        
        # 清除缓存
        await cache.invalidate_room_cache(room_id)
        
        # 获取更新后的完整信息
        room_with_stats = await ChatRoomService.get_room_with_stats(db, room_id)
        
        logger.info(f"用户 {current_user_id} 更新了聊天室 {room_id}")
        
        return room_with_stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新聊天室失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新聊天室失败"
        )

@router.delete("/chatrooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定聊天室")
async def delete_chat_room(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除指定聊天室"""
    try:
        # 检查权限（只有创建者可以删除）
        room, member = check_room_access(db, room_id, current_user_id)
        
        if member.role != 'creator':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有创建者可以删除聊天室"
            )
        
        # 软删除：标记为已删除而不是真正删除
        room.is_deleted = True
        room.deleted_at = datetime.now()
        room.deleted_by = current_user_id
        
        # 将所有成员状态设为 inactive
        db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id
        ).update({"status": "inactive"})
        
        db.commit()
        
        # 清除所有相关缓存
        await cache.invalidate_room_cache(room_id)
        
        # 清除所有成员的用户缓存
        members = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id
        ).all()
        
        for member in members:
            await cache.invalidate_user_cache(member.user_id)
        
        logger.info(f"用户 {current_user_id} 删除了聊天室 {room_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除聊天室失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除聊天室失败"
        )

@router.get("/chatrooms/{room_id}/stats", summary="获取聊天室统计信息")
async def get_chat_room_stats(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=365, description="统计天数")
):
    """获取聊天室统计信息"""
    try:
        # 检查访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 获取统计信息
        from project.services.message_service import MessageService
        stats = await MessageService.get_message_statistics(db, room_id, days)
        
        return {
            "room_id": room_id,
            "statistics": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取聊天室统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取统计信息失败"
        )
