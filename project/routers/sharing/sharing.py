# project/routers/sharing/sharing.py
"""
分享功能路由模块
提供平台内容的转发分享功能
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

# FastAPI核心依赖
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session

# 项目核心依赖
from project.database import get_db
from project.models import SharedContent, User
from project.utils import get_current_user_id
import project.schemas as schemas

# 业务服务层
from project.services.sharing_service import SharingService, SharingUtils

# 优化工具导入
from project.utils.core.error_decorators import handle_database_errors
from project.utils.optimization.router_optimization import optimized_route

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sharing", tags=["分享功能"])

# ===== 分享内容管理路由 =====

@router.post("/create", response_model=schemas.ShareContentResponse, summary="创建分享")
@optimized_route("创建分享")
@handle_database_errors
async def create_share(
    share_request: schemas.ShareContentRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建分享"""
    result = await SharingService.create_share(db, share_request, current_user_id)
    
    # 异步处理分享统计更新
    # background_tasks.add_task(update_share_analytics, result.id)
    
    logger.info(f"用户 {current_user_id} 创建分享 {result.id}")
    return result


@router.post("/forum", response_model=schemas.ShareToForumResponse, summary="分享到论坛")
@optimized_route("分享到论坛")
@handle_database_errors
async def share_to_forum(
    share_request: schemas.ShareToForumRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """分享到论坛"""
    result = await SharingService.share_to_forum(db, share_request, current_user_id)
    
    logger.info(f"用户 {current_user_id} 分享内容到论坛，话题ID: {result.topic_id}")
    return result


@router.post("/chatroom", response_model=schemas.ShareToChatroomResponse, summary="分享到聊天室")
@optimized_route("分享到聊天室")
@handle_database_errors
async def share_to_chatroom(
    share_request: schemas.ShareToChatroomRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """分享到聊天室"""
    result = await SharingService.share_to_chatroom(db, share_request, current_user_id)
    
    logger.info(f"用户 {current_user_id} 分享内容到 {len(share_request.chatroom_ids)} 个聊天室")
    return result


@router.post("/link", response_model=schemas.ShareLinkResponse, summary="生成分享链接")
@optimized_route("生成分享链接")
@handle_database_errors
async def generate_share_link(
    content_type: str = Query(..., description="内容类型"),
    content_id: int = Query(..., description="内容ID"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """生成分享链接（支持微信、QQ等平台）"""
    result = await SharingService.generate_share_link(db, content_type, content_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 生成分享链接，分享ID: {result.share_id}")
    return result


@router.post("/quick", response_model=schemas.QuickShareResponse, summary="快速分享到多个平台")
@optimized_route("快速分享")
@handle_database_errors
async def quick_share(
    quick_share_request: schemas.QuickShareRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """快速分享到多个平台"""
    result = await SharingService.quick_share(db, quick_share_request, current_user_id)
    
    logger.info(f"用户 {current_user_id} 快速分享到 {len(quick_share_request.platforms)} 个平台")
    return result


# ===== 分享记录查询路由 =====

@router.get("/my-shares", response_model=List[schemas.ShareContentResponse], summary="获取我的分享列表")
@optimized_route("获取我的分享列表")
@handle_database_errors
async def get_my_shares(
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    content_type: Optional[str] = Query(None, description="内容类型筛选"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取当前用户的分享列表"""
    shares, total = await SharingService.get_user_shares(
        db, current_user_id, skip, limit, content_type
    )
    
    return shares


@router.get("/stats", response_model=schemas.ShareStatsResponse, summary="获取分享统计")
@optimized_route("获取分享统计")
@handle_database_errors
async def get_share_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取当前用户的分享统计"""
    stats = await SharingService.get_share_stats(db, current_user_id)
    return stats


@router.get("/{share_id}", response_model=schemas.ShareContentResponse, summary="获取分享详情")
@optimized_route("获取分享详情")
@handle_database_errors
async def get_share_detail(
    share_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取分享详情"""
    shared_content = db.query(SharedContent).filter(SharedContent.id == share_id).first()
    
    if not shared_content:
        raise HTTPException(status_code=404, detail="分享不存在")
    
    # 检查权限
    if not shared_content.is_public and shared_content.owner_id != current_user_id:
        raise HTTPException(status_code=403, detail="没有权限查看此分享")
    
    # 增加查看次数
    shared_content.view_count += 1
    db.commit()
    
    # 记录查看日志
    await SharingService._log_share_action(
        db, share_id, current_user_id, "view"
    )
    
    result = await SharingService._format_share_response(db, shared_content)
    return result


# ===== 分享内容预览路由 =====

@router.get("/preview/{content_type}/{content_id}", response_model=schemas.ShareableContentPreview, summary="获取内容分享预览")
@optimized_route("获取内容分享预览")
@handle_database_errors
async def get_share_preview(
    content_type: str,
    content_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取内容的分享预览信息"""
    try:
        content_info = await SharingService._validate_shareable_content(
            db, content_type, content_id, current_user_id
        )
        
        preview = SharingUtils.format_share_preview({
            "id": content_id,
            "type": content_type,
            **content_info
        })
        
        return preview
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分享预览失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取分享预览失败"
        )


# ===== 分享操作路由 =====

@router.post("/{share_id}/click", summary="记录分享点击")
@optimized_route("记录分享点击")
@handle_database_errors
async def record_share_click(
    share_id: int,
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """记录分享链接点击"""
    shared_content = db.query(SharedContent).filter(SharedContent.id == share_id).first()
    
    if not shared_content:
        raise HTTPException(status_code=404, detail="分享不存在")
    
    # 检查分享是否过期
    if shared_content.expires_at and shared_content.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="分享已过期")
    
    # 更新点击次数
    shared_content.click_count += 1
    db.commit()
    
    # 记录点击日志
    await SharingService._log_share_action(
        db, share_id, current_user_id, "click"
    )
    
    return {"message": "点击记录成功", "redirect_url": f"/{shared_content.content_type}/{shared_content.content_id}"}


@router.delete("/{share_id}", summary="删除分享")
@optimized_route("删除分享")
@handle_database_errors
async def delete_share(
    share_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除分享"""
    shared_content = db.query(SharedContent).filter(SharedContent.id == share_id).first()
    
    if not shared_content:
        raise HTTPException(status_code=404, detail="分享不存在")
    
    # 检查权限
    if shared_content.owner_id != current_user_id:
        raise HTTPException(status_code=403, detail="没有权限删除此分享")
    
    # 软删除
    shared_content.status = "deleted"
    db.commit()
    
    logger.info(f"用户 {current_user_id} 删除分享 {share_id}")
    return {"message": "分享删除成功"}


# ===== 管理员路由 =====

@router.get("/admin/all", response_model=List[schemas.ShareContentResponse], summary="管理员获取所有分享", dependencies=[])
@optimized_route("管理员获取所有分享")
@handle_database_errors
async def admin_get_all_shares(
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    status_filter: Optional[str] = Query(None, description="状态筛选"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """管理员获取所有分享（需要管理员权限）"""
    # 检查管理员权限
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    query = db.query(SharedContent)
    
    if status_filter:
        query = query.filter(SharedContent.status == status_filter)
    
    total = query.count()
    shares = query.order_by(SharedContent.created_at.desc()).offset(skip).limit(limit).all()
    
    share_responses = []
    for share in shares:
        share_response = await SharingService._format_share_response(db, share)
        share_responses.append(share_response)
    
    return share_responses


@router.put("/admin/{share_id}/status", summary="管理员更新分享状态")
@optimized_route("管理员更新分享状态")
@handle_database_errors
async def admin_update_share_status(
    share_id: int,
    status: str = Query(..., regex="^(active|expired|deleted)$", description="新状态"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """管理员更新分享状态"""
    # 检查管理员权限
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    shared_content = db.query(SharedContent).filter(SharedContent.id == share_id).first()
    if not shared_content:
        raise HTTPException(status_code=404, detail="分享不存在")
    
    shared_content.status = status
    db.commit()
    
    logger.info(f"管理员 {current_user_id} 更新分享 {share_id} 状态为 {status}")
    return {"message": f"分享状态已更新为 {status}"}


# ===== 新增：论坛话题转发路由 =====

@router.post("/forum-topic/repost", response_model=schemas.ForumTopicRepostResponse, summary="论坛话题转发")
@optimized_route("论坛话题转发")
@handle_database_errors
async def repost_forum_topic(
    repost_request: schemas.ForumTopicRepostRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """转发论坛话题到论坛或聊天室"""
    result = await SharingService.repost_forum_topic(db, repost_request, current_user_id)
    
    logger.info(f"用户 {current_user_id} 转发话题 {repost_request.topic_id} 到 {repost_request.share_type}")
    return result


# ===== 新增：社交平台分享路由 =====

@router.post("/social", response_model=schemas.SocialShareResponse, summary="社交平台分享")
@optimized_route("社交平台分享")
@handle_database_errors
async def create_social_share(
    social_request: schemas.SocialShareRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建微信/QQ分享"""
    result = await SharingService.create_social_share(db, social_request, current_user_id)
    
    logger.info(f"用户 {current_user_id} 创建 {social_request.platform} 分享，内容: {social_request.content_type}:{social_request.content_id}")
    return result


# ===== 新增：复制链接分享路由 =====

@router.post("/copy-link", response_model=schemas.CopyLinkResponse, summary="复制链接分享")
@optimized_route("复制链接分享")
@handle_database_errors
async def create_copy_link_share(
    copy_request: schemas.CopyLinkRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """生成复制链接分享"""
    result = await SharingService.create_copy_link(db, copy_request, current_user_id)
    
    logger.info(f"用户 {current_user_id} 生成复制链接，内容: {copy_request.content_type}:{copy_request.content_id}")
    return result
