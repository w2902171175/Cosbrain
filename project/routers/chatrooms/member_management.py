# project/routers/chatrooms/member_management.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from project.database import get_db
from project.utils import get_current_user_id
from project.models import ChatRoom, ChatRoomMember, ChatRoomJoinRequest, User
import project.schemas as schemas
from project.services.chatroom_service import ChatRoomService
from project.utils.security.permissions import check_room_access, check_admin_role
from project.utils.async_cache.cache import cache
from project.utils import _award_points, _check_and_award_achievements

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/chatrooms/{room_id}/members", response_model=List[schemas.ChatRoomMemberResponse], summary="获取聊天室成员列表")
async def get_chat_room_members(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(50, ge=1, le=100, description="每页数量")
):
    """获取聊天室成员列表"""
    try:
        # 检查访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 获取成员列表
        members_info = await ChatRoomService.get_room_members_with_user_info(db, room_id)
        
        # 分页处理
        start_idx = (page - 1) * size
        end_idx = start_idx + size
        paginated_members = members_info[start_idx:end_idx]
        
        return paginated_members
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取聊天室成员列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取成员列表失败"
        )

@router.put("/chat-rooms/{room_id}/members/{member_id}/set-role", response_model=schemas.ChatRoomMemberResponse, summary="设置聊天室成员角色")
async def set_chat_room_member_role(
    room_id: int,
    member_id: int,
    role_update: schemas.ChatRoomMemberRoleUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """设置聊天室成员角色"""
    try:
        # 检查当前用户权限
        room, current_member = check_room_access(db, room_id, current_user_id)
        
        if current_member.role not in ['creator', 'admin']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有创建者和管理员可以设置成员角色"
            )
        
        # 获取目标成员
        target_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.id == member_id,
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.status == "active"
        ).first()
        
        if not target_member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="成员不存在"
            )
        
        # 检查角色权限规则
        if current_member.role == 'admin' and target_member.role == 'creator':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="管理员不能修改创建者的角色"
            )
        
        if role_update.role == 'creator' and current_member.role != 'creator':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有创建者可以转让创建者权限"
            )
        
        # 如果是转让创建者权限，需要将当前创建者降级为管理员
        if role_update.role == 'creator':
            current_member.role = 'admin'
        
        # 更新目标成员角色
        target_member.role = role_update.role
        target_member.updated_at = datetime.now()
        
        db.commit()
        db.refresh(target_member)
        
        # 清除缓存
        await cache.invalidate_room_cache(room_id)
        
        logger.info(f"用户 {current_user_id} 将成员 {member_id} 的角色设置为 {role_update.role}")
        
        return target_member
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置成员角色失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="设置成员角色失败"
        )

@router.delete("/chat-rooms/{room_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT, summary="移除聊天室成员")
async def remove_chat_room_member(
    room_id: int,
    member_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """移除聊天室成员"""
    try:
        # 检查当前用户权限
        room, current_member = check_room_access(db, room_id, current_user_id)
        
        # 获取目标成员
        target_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.id == member_id,
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.status == "active"
        ).first()
        
        if not target_member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="成员不存在"
            )
        
        # 权限检查
        is_self_leave = target_member.user_id == current_user_id
        is_admin_action = current_member.role in ['creator', 'admin'] and target_member.role not in ['creator']
        
        if not (is_self_leave or is_admin_action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="没有权限移除此成员"
            )
        
        # 创建者不能被移除（除非是自己退出）
        if target_member.role == 'creator' and not is_self_leave:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="不能移除创建者"
            )
        
        # 移除成员
        target_member.status = "inactive"
        target_member.left_at = datetime.now()
        
        db.commit()
        
        # 清除缓存
        await cache.invalidate_room_cache(room_id)
        await cache.invalidate_user_cache(target_member.user_id)
        
        action = "退出" if is_self_leave else "移除"
        logger.info(f"用户 {current_user_id} {action}了成员 {target_member.user_id} 从聊天室 {room_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移除聊天室成员失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="移除成员失败"
        )

@router.post("/chat-rooms/{room_id}/join-request", response_model=schemas.ChatRoomJoinRequestResponse, summary="申请加入聊天室")
async def create_join_request(
    room_id: int,
    request_data: schemas.ChatRoomJoinRequestCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """申请加入聊天室"""
    try:
        # 检查聊天室是否存在
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聊天室不存在"
            )
        
        # 检查用户是否已经是成员
        existing_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.user_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first()
        
        if existing_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经是该聊天室的成员"
            )
        
        # 检查是否已有待处理的申请
        existing_request = db.query(ChatRoomJoinRequest).filter(
            ChatRoomJoinRequest.room_id == room_id,
            ChatRoomJoinRequest.user_id == current_user_id,
            ChatRoomJoinRequest.status == "pending"
        ).first()
        
        if existing_request:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经有一个待处理的加入申请"
            )
        
        # 如果是公开聊天室，直接加入
        if room.is_public:
            # 检查人数限制
            current_members_count = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == room_id,
                ChatRoomMember.status == "active"
            ).count()
            
            if room.max_members and current_members_count >= room.max_members:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="聊天室已满"
                )
            
            # 直接添加为成员
            new_member = ChatRoomMember(
                room_id=room_id,
                user_id=current_user_id,
                role="member",
                status="active",
                joined_at=datetime.now()
            )
            
            db.add(new_member)
            db.commit()
            
            # 清除缓存
            await cache.invalidate_room_cache(room_id)
            await cache.invalidate_user_cache(current_user_id)
            
            # 创建自动批准的申请记录
            auto_approved_request = ChatRoomJoinRequest(
                room_id=room_id,
                user_id=current_user_id,
                message=request_data.message,
                status="approved",
                created_at=datetime.now(),
                processed_at=datetime.now(),
                processed_by=current_user_id  # 自动批准
            )
            
            db.add(auto_approved_request)
            db.commit()
            db.refresh(auto_approved_request)
            
            logger.info(f"用户 {current_user_id} 自动加入公开聊天室 {room_id}")
            
            return auto_approved_request
        
        # 私人聊天室需要申请
        join_request = ChatRoomJoinRequest(
            room_id=room_id,
            user_id=current_user_id,
            message=request_data.message,
            status="pending",
            created_at=datetime.now()
        )
        
        db.add(join_request)
        db.commit()
        db.refresh(join_request)
        
        logger.info(f"用户 {current_user_id} 申请加入私人聊天室 {room_id}")
        
        return join_request
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"申请加入聊天室失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="申请加入失败"
        )

@router.get("/chat-rooms/{room_id}/join-requests", response_model=List[schemas.ChatRoomJoinRequestResponse], summary="获取聊天室加入申请列表")
async def get_join_requests(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None, description="状态过滤 (pending/approved/rejected)"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """获取聊天室加入申请列表"""
    try:
        # 检查权限（只有创建者和管理员可以查看）
        room, member = check_room_access(db, room_id, current_user_id)
        
        if member.role not in ['creator', 'admin']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有创建者和管理员可以查看加入申请"
            )
        
        # 构建查询
        query = db.query(ChatRoomJoinRequest).filter(
            ChatRoomJoinRequest.room_id == room_id
        )
        
        if status_filter:
            query = query.filter(ChatRoomJoinRequest.status == status_filter)
        
        # 分页查询
        join_requests = query.order_by(
            ChatRoomJoinRequest.created_at.desc()
        ).offset((page - 1) * size).limit(size).all()
        
        return join_requests
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取加入申请列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取申请列表失败"
        )

@router.post("/chat-rooms/join-requests/{request_id}/process", response_model=schemas.ChatRoomJoinRequestResponse, summary="处理加入申请")
async def process_join_request(
    request_id: int,
    action: schemas.ProcessJoinRequestAction,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """处理加入申请"""
    try:
        # 获取申请记录
        join_request = db.query(ChatRoomJoinRequest).filter(
            ChatRoomJoinRequest.id == request_id
        ).first()
        
        if not join_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="加入申请不存在"
            )
        
        # 检查权限
        room, member = check_room_access(db, join_request.room_id, current_user_id)
        
        if member.role not in ['creator', 'admin']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有创建者和管理员可以处理加入申请"
            )
        
        # 检查申请状态
        if join_request.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该申请已经被处理过了"
            )
        
        # 处理申请
        join_request.status = action.action
        join_request.processed_at = datetime.now()
        join_request.processed_by = current_user_id
        join_request.admin_message = action.message
        
        # 如果批准申请，添加用户为成员
        if action.action == "approved":
            # 检查人数限制
            current_members_count = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == join_request.room_id,
                ChatRoomMember.status == "active"
            ).count()
            
            if room.max_members and current_members_count >= room.max_members:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="聊天室已满，无法批准申请"
                )
            
            # 添加为成员
            new_member = ChatRoomMember(
                room_id=join_request.room_id,
                user_id=join_request.user_id,
                role="member",
                status="active",
                joined_at=datetime.now()
            )
            
            db.add(new_member)
            
            # 清除缓存
            await cache.invalidate_room_cache(join_request.room_id)
            await cache.invalidate_user_cache(join_request.user_id)
        
        db.commit()
        db.refresh(join_request)
        
        action_text = "批准" if action.action == "approved" else "拒绝"
        logger.info(f"用户 {current_user_id} {action_text}了用户 {join_request.user_id} 的加入申请")
        
        return join_request
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理加入申请失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="处理申请失败"
        )
