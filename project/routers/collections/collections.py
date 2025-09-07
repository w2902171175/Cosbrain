# project/routers/collections/collections_optimized.py
"""
收藏模块优化版本 - 应用统一优化模式
基于成功优化模式，优化collections模块
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

# 核心依赖
from project.database import get_db
from project.models import Folder, CollectedContent
from project.utils import get_current_user_id
import project.schemas as schemas

# 优化工具导入
from project.services.collections_service import (
    CollectionsFolderService, CollectedContentService, CollectionsUtils
)
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/collections", tags=["收藏管理"])

# ===== 文件夹管理路由 =====

@router.get("/folders", response_model=List[schemas.FolderResponseNew], summary="获取用户的文件夹树结构")
@optimized_route("获取文件夹树")
async def get_user_folders(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户的文件夹树结构 - 优化版本"""
    
    folders = CollectionsFolderService.get_user_folders_tree_optimized(db, current_user_id)
    return [CollectionsUtils.format_folder_response(folder) for folder in folders]

@router.post("/folders", response_model=schemas.FolderResponseNew, summary="创建新文件夹")
@optimized_route("创建文件夹")
async def create_folder(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    parent_id: Optional[int] = Form(None),
    icon: str = Form("📁"),
    color: str = Form("#3498db"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建新文件夹 - 优化版本"""
    
    # 验证输入数据
    folder_data = CollectionsUtils.validate_folder_data({
        "name": name,
        "description": description,
        "parent_id": parent_id,
        "icon": icon,
        "color": color
    })
    
    # 使用事务创建文件夹
    with database_transaction(db):
        folder = CollectionsFolderService.create_folder_optimized(db, folder_data, current_user_id)
        
        # 异步初始化文件夹
        submit_background_task(
            background_tasks,
            "initialize_collection_folder",
            {"folder_id": folder.id, "user_id": current_user_id},
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 创建文件夹 {folder.id} 成功")
    return CollectionsUtils.format_folder_response(folder)

@router.get("/folders/{folder_id}", response_model=schemas.FolderResponseNew, summary="获取文件夹详情")
@optimized_route("获取文件夹详情")
async def get_folder_detail(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取文件夹详情 - 优化版本"""
    
    folder = CollectionsFolderService.get_folder_optimized(db, folder_id, current_user_id)
    return CollectionsUtils.format_folder_response(folder)

@router.put("/folders/{folder_id}", response_model=schemas.FolderResponseNew, summary="更新文件夹信息")
@optimized_route("更新文件夹")
async def update_folder(
    folder_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    parent_id: Optional[int] = Form(None),
    icon: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新文件夹信息 - 优化版本"""
    
    # 准备更新数据
    update_data = {}
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if parent_id is not None:
        update_data["parent_id"] = parent_id
    if icon is not None:
        update_data["icon"] = icon
    if color is not None:
        update_data["color"] = color
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个要更新的字段"
        )
    
    # 验证数据
    CollectionsUtils.validate_folder_data(update_data)
    
    # 使用事务更新
    with database_transaction(db):
        folder = CollectionsFolderService.update_folder_optimized(db, folder_id, update_data, current_user_id)
    
    logger.info(f"用户 {current_user_id} 更新文件夹 {folder_id} 成功")
    return CollectionsUtils.format_folder_response(folder)

@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除文件夹")
@optimized_route("删除文件夹")
async def delete_folder(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除文件夹 - 优化版本"""
    
    with database_transaction(db):
        CollectionsFolderService.delete_folder_optimized(db, folder_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 删除文件夹 {folder_id} 成功")

@router.get("/folders/{folder_id}/contents", response_model=List[schemas.CollectedContentResponseNew], summary="获取文件夹内容")
@optimized_route("获取文件夹内容")
async def get_folder_contents(
    folder_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    content_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取文件夹内容 - 优化版本"""
    
    contents, total = CollectedContentService.get_folder_contents_optimized(
        db, folder_id, current_user_id, skip, limit, content_type, search
    )
    
    return [CollectionsUtils.format_content_response(content) for content in contents]

# ===== 收藏内容管理路由 =====

@router.post("/folders/{folder_id}/collect", response_model=schemas.CollectedContentResponseNew, summary="向文件夹添加收藏")
@optimized_route("添加收藏")
async def collect_to_folder(
    folder_id: int,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    content_type: str = Form(...),
    description: Optional[str] = Form(None),
    resource_type: Optional[str] = Form(None),
    resource_id: Optional[int] = Form(None),
    url: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """向文件夹添加收藏 - 优化版本"""
    
    # 处理标签
    tag_list = []
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    
    # 准备内容数据
    content_data = CollectionsUtils.validate_content_data({
        "title": title,
        "content_type": content_type,
        "description": description,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "url": url,
        "tags": tag_list
    })
    
    # 使用事务创建收藏内容
    with database_transaction(db):
        content = CollectedContentService.create_collected_content_optimized(
            db, folder_id, content_data, current_user_id
        )
        
        # 异步处理收藏内容
        submit_background_task(
            background_tasks,
            "process_collected_content",
            {
                "content_id": content.id,
                "content_type": content_type,
                "resource_type": resource_type,
                "resource_id": resource_id
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"用户 {current_user_id} 在文件夹 {folder_id} 添加收藏 {content.id}")
    return CollectionsUtils.format_content_response(content)

@router.post("/quick-collect", response_model=schemas.CollectedContentResponseNew, summary="快速收藏")
@optimized_route("快速收藏")
async def quick_collect(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    content_type: str = Form(...),
    description: Optional[str] = Form(None),
    resource_type: Optional[str] = Form(None),
    resource_id: Optional[int] = Form(None),
    url: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """快速收藏到默认文件夹 - 优化版本"""
    
    # 获取或创建默认文件夹
    with database_transaction(db):
        default_folder = CollectionsUtils.get_or_create_default_folder(db, current_user_id)
        
        # 准备内容数据
        content_data = CollectionsUtils.validate_content_data({
            "title": title,
            "content_type": content_type,
            "description": description,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "url": url
        })
        
        # 创建收藏内容
        content = CollectedContentService.create_collected_content_optimized(
            db, default_folder.id, content_data, current_user_id
        )
        
        # 异步处理收藏内容
        submit_background_task(
            background_tasks,
            "process_collected_content",
            {
                "content_id": content.id,
                "content_type": content_type,
                "resource_type": resource_type,
                "resource_id": resource_id
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"用户 {current_user_id} 快速收藏 {content.id}")
    return CollectionsUtils.format_content_response(content)

@router.get("/contents/{content_id}", response_model=schemas.CollectedContentResponseNew, summary="获取收藏内容详情")
@optimized_route("获取收藏详情")
async def get_collected_content(
    content_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取收藏内容详情 - 优化版本"""
    
    content = CollectedContentService.get_content_optimized(db, content_id, current_user_id)
    return CollectionsUtils.format_content_response(content)

@router.put("/contents/{content_id}", response_model=schemas.CollectedContentResponseNew, summary="更新收藏内容")
@optimized_route("更新收藏内容")
async def update_collected_content(
    content_id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新收藏内容 - 优化版本"""
    
    # 准备更新数据
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if description is not None:
        update_data["description"] = description
    if tags is not None:
        update_data["tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个要更新的字段"
        )
    
    # 使用事务更新
    with database_transaction(db):
        content = CollectedContentService.update_collected_content_optimized(
            db, content_id, update_data, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 更新收藏内容 {content_id} 成功")
    return CollectionsUtils.format_content_response(content)

@router.delete("/contents/{content_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除收藏内容")
@optimized_route("删除收藏内容")
async def delete_collected_content(
    content_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除收藏内容 - 优化版本"""
    
    with database_transaction(db):
        CollectedContentService.delete_collected_content_optimized(db, content_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 删除收藏内容 {content_id} 成功")

# ===== 搜索和统计路由 =====

@router.get("/search", response_model=List[schemas.CollectedContentResponseNew], summary="搜索收藏内容")
@optimized_route("搜索收藏")
async def search_collected_content(
    background_tasks: BackgroundTasks,
    q: str = Query(..., min_length=2, description="搜索关键词"),
    content_type: Optional[str] = Query(None),
    folder_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """搜索收藏内容 - 优化版本"""
    
    # 执行搜索
    contents, total = CollectedContentService.search_collected_content_optimized(
        db, current_user_id, q, content_type, folder_id, skip, limit
    )
    
    # 异步记录搜索日志
    submit_background_task(
        background_tasks,
        "log_collection_search",
        {
            "user_id": current_user_id,
            "query": q,
            "content_type": content_type,
            "folder_id": folder_id,
            "result_count": total
        },
        priority=TaskPriority.LOW
    )
    
    logger.info(f"用户 {current_user_id} 搜索收藏: {q}，找到 {total} 条结果")
    return [CollectionsUtils.format_content_response(content) for content in contents]

@router.get("/stats", response_model=schemas.FolderStatsResponse, summary="获取收藏统计信息")
@optimized_route("收藏统计")
async def get_collection_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取收藏统计信息 - 优化版本"""
    
    stats = CollectionsFolderService.get_folder_stats_optimized(db, current_user_id)
    return stats

# ===== 批量操作路由 =====

@router.post("/batch-move", summary="批量移动收藏内容")
@optimized_route("批量移动")
async def batch_move_contents(
    background_tasks: BackgroundTasks,
    content_ids: List[int] = Form(...),
    target_folder_id: int = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """批量移动收藏内容 - 优化版本"""
    
    if not content_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供要移动的收藏内容ID列表"
        )
    
    if len(content_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="一次最多只能移动100个收藏内容"
        )
    
    # 使用事务批量移动
    with database_transaction(db):
        moved_contents = CollectedContentService.batch_move_contents_optimized(
            db, content_ids, target_folder_id, current_user_id
        )
        
        # 异步记录批量操作日志
        submit_background_task(
            background_tasks,
            "log_batch_operation",
            {
                "user_id": current_user_id,
                "operation": "batch_move",
                "content_ids": content_ids,
                "target_folder_id": target_folder_id,
                "success_count": len(moved_contents)
            },
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 批量移动 {len(moved_contents)} 个收藏内容到文件夹 {target_folder_id}")
    return {
        "message": f"成功移动 {len(moved_contents)} 个收藏内容",
        "moved_count": len(moved_contents),
        "total_requested": len(content_ids)
    }

# ===== 特殊收藏类型路由 =====

@router.post("/collect-chat-message/{message_id}", response_model=schemas.CollectedContentResponseNew, summary="收藏聊天消息")
@optimized_route("收藏聊天消息")
async def collect_chat_message(
    message_id: int,
    background_tasks: BackgroundTasks,
    folder_id: Optional[int] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """收藏聊天消息 - 优化版本"""
    
    # 验证聊天消息是否存在且有权限访问
    from project.models import ChatMessage, ChatRoomMember
    
    message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="聊天消息不存在"
        )
    
    # 检查是否是聊天室成员
    membership = db.query(ChatRoomMember).filter(
        ChatRoomMember.room_id == message.room_id,
        ChatRoomMember.user_id == current_user_id
    ).first()
    
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限访问此聊天消息"
        )
    
    # 获取目标文件夹
    with database_transaction(db):
        if folder_id:
            target_folder = CollectionsFolderService.get_folder_optimized(db, folder_id, current_user_id)
        else:
            target_folder = CollectionsUtils.get_or_create_default_folder(db, current_user_id, "聊天消息")
        
        # 准备内容数据
        content_data = {
            "title": f"聊天消息 - {message.content[:50]}...",
            "content_type": "chat_message",
            "resource_type": "chat_message",
            "resource_id": message_id,
            "description": message.content,
            "metadata": {
                "room_id": message.room_id,
                "sender_id": message.sender_id,
                "message_type": message.message_type
            }
        }
        
        # 创建收藏
        content = CollectedContentService.create_collected_content_optimized(
            db, target_folder.id, content_data, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 收藏聊天消息 {message_id}")
    return CollectionsUtils.format_content_response(content)

@router.post("/collect-forum-topic/{topic_id}", response_model=schemas.CollectedContentResponseNew, summary="收藏论坛话题")
@optimized_route("收藏论坛话题")
async def collect_forum_topic(
    topic_id: int,
    background_tasks: BackgroundTasks,
    folder_id: Optional[int] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """收藏论坛话题 - 优化版本"""
    
    # 验证论坛话题是否存在
    from project.models import ForumTopic
    
    topic = db.query(ForumTopic).filter(
        ForumTopic.id == topic_id,
        ForumTopic.is_deleted == False
    ).first()
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="论坛话题不存在"
        )
    
    # 获取目标文件夹
    with database_transaction(db):
        if folder_id:
            target_folder = CollectionsFolderService.get_folder_optimized(db, folder_id, current_user_id)
        else:
            target_folder = CollectionsUtils.get_or_create_default_folder(db, current_user_id, "论坛话题")
        
        # 准备内容数据
        content_data = {
            "title": topic.title,
            "content_type": "forum_topic",
            "resource_type": "forum_topic",
            "resource_id": topic_id,
            "description": topic.content[:200] + "..." if len(topic.content) > 200 else topic.content,
            "metadata": {
                "author_id": topic.author_id,
                "category": topic.category,
                "likes_count": topic.likes_count,
                "comments_count": topic.comments_count
            }
        }
        
        # 创建收藏
        content = CollectedContentService.create_collected_content_optimized(
            db, target_folder.id, content_data, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 收藏论坛话题 {topic_id}")
    return CollectionsUtils.format_content_response(content)

# 使用路由优化器应用批量优化
# router_optimizer.apply_batch_optimizations(router, {
#     "cache_ttl": 300,
#     "enable_compression": True,
#     "rate_limit": "150/minute",
#     "monitoring": True
# })

logger.info("⭐ Collections Module - 收藏模块已加载")
