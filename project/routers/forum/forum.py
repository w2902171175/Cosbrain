# project/routers/forum/forum.py
"""
论坛模块优化版本 - 应用统一优化模式
基于courses模块的成功优化经验
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

# 核心依赖
from project.database import get_db
from project.models import User, ForumTopic, ForumLike, ForumComment, UserFollow
from project.utils import get_current_user_id
import project.schemas as schemas

# 优化工具导入
from project.services.forum_service import (
    ForumService, ForumCommentService, ForumLikeService, ForumUtils
)
from project.utils.core.error_decorators import database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/forum", tags=["forum"])

# ===== 话题管理路由 =====

@router.post("/topics", status_code=status.HTTP_201_CREATED, summary="发布话题")
@optimized_route("发布话题")
async def create_topic(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    content: str = Form(...),
    category: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """发布新话题 - 优化版本"""
    
    # 验证输入数据
    topic_data = ForumUtils.validate_topic_data({
        "title": title,
        "content": content,
        "category": category
    })
    
    # 使用事务创建话题
    with database_transaction(db):
        topic = ForumService.create_topic_optimized(db, topic_data, current_user_id)
        
        # 处理文件上传（异步）
        if files and files[0].filename:
            submit_background_task(
                background_tasks,
                "process_topic_files",
                {"topic_id": topic.id, "files": files},
                priority=TaskPriority.MEDIUM
            )
        
        # 生成AI嵌入向量（异步）
        submit_background_task(
            background_tasks,
            "generate_topic_embeddings",
            {"topic_id": topic.id, "content": content},
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 发布话题 {topic.id} 成功")
    return ForumUtils.format_topic_response(topic)

@router.get("/topics", summary="获取话题列表")
@optimized_route("获取话题列表")
async def get_topics(
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    category: Optional[str] = Query(None, description="分类筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    sort_by: str = Query("latest", regex="^(latest|hot|comments)$", description="排序方式"),
    db: Session = Depends(get_db)
):
    """获取话题列表 - 优化版本"""
    
    topics, total = ForumService.get_topics_list_optimized(
        db, skip, limit, category, search, sort_by
    )
    
    return {
        "items": [ForumUtils.format_topic_response(topic, include_content=False) for topic in topics],
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/topics/{topic_id}", summary="获取话题详情")
@optimized_route("获取话题详情")
async def get_topic_detail(
    topic_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取话题详情 - 优化版本"""
    
    topic = ForumService.get_topic_by_id_optimized(db, topic_id, current_user_id)
    
    # 异步更新浏览量
    submit_background_task(
        background_tasks,
        "update_topic_views",
        {"topic_id": topic_id, "user_id": current_user_id},
        priority=TaskPriority.LOW
    )
    
    return ForumUtils.format_topic_response(topic)

@router.put("/topics/{topic_id}", summary="更新话题")
@optimized_route("更新话题")
async def update_topic(
    topic_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新话题 - 优化版本"""
    
    # 准备更新数据
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if content is not None:
        update_data["content"] = content
    if category is not None:
        update_data["category"] = category
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个要更新的字段"
        )
    
    # 验证数据
    if "title" in update_data or "content" in update_data:
        ForumUtils.validate_topic_data(update_data)
    
    # 使用事务更新
    with database_transaction(db):
        topic = ForumService.update_topic_optimized(db, topic_id, update_data, current_user_id)
    
    logger.info(f"用户 {current_user_id} 更新话题 {topic_id} 成功")
    return ForumUtils.format_topic_response(topic)

@router.delete("/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除话题")
@optimized_route("删除话题")
async def delete_topic(
    topic_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除话题 - 优化版本（软删除）"""
    
    with database_transaction(db):
        ForumService.delete_topic_optimized(db, topic_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 删除话题 {topic_id} 成功")

# ===== 评论管理路由 =====

@router.get("/topics/{topic_id}/comments", summary="获取话题评论")
@optimized_route("获取评论列表")
async def get_comments(
    topic_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取话题评论 - 优化版本"""
    
    comments, total = ForumCommentService.get_comments_optimized(db, topic_id, skip, limit)
    
    return {
        "items": [ForumUtils.format_comment_response(comment) for comment in comments],
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.post("/topics/{topic_id}/comments", status_code=status.HTTP_201_CREATED, summary="发布评论")
@optimized_route("发布评论")
async def create_comment(
    topic_id: int,
    background_tasks: BackgroundTasks,
    content: str = Form(...),
    parent_id: Optional[int] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """发布评论 - 优化版本"""
    
    # 验证数据
    comment_data = ForumUtils.validate_comment_data({
        "content": content,
        "topic_id": topic_id,
        "parent_id": parent_id
    })
    
    # 验证话题存在
    ForumService.get_topic_by_id_optimized(db, topic_id)
    
    # 使用事务创建评论
    with database_transaction(db):
        comment = ForumCommentService.create_comment_optimized(db, comment_data, current_user_id)
        
        # 异步处理通知
        submit_background_task(
            background_tasks,
            "send_comment_notification",
            {"comment_id": comment.id, "topic_id": topic_id},
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"用户 {current_user_id} 在话题 {topic_id} 发布评论 {comment.id}")
    return ForumUtils.format_comment_response(comment)

@router.put("/comments/{comment_id}", summary="更新评论")
@optimized_route("更新评论")
async def update_comment(
    comment_id: int,
    content: str = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新评论 - 优化版本"""
    
    # 验证数据
    ForumUtils.validate_comment_data({"content": content})
    
    # 获取评论
    comment = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="评论不存在"
        )
    
    # 权限检查
    if comment.author_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限修改此评论"
        )
    
    # 更新评论
    with database_transaction(db):
        comment.content = content
        comment.updated_at = datetime.utcnow()
        db.flush()
        db.refresh(comment)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{comment.topic_id}:comments:*"))
    
    logger.info(f"用户 {current_user_id} 更新评论 {comment_id} 成功")
    return ForumUtils.format_comment_response(comment)

@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除评论")
@optimized_route("删除评论")
async def delete_comment(
    comment_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除评论 - 优化版本"""
    
    # 获取评论
    comment = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="评论不存在"
        )
    
    # 权限检查
    if comment.author_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限删除此评论"
        )
    
    # 软删除评论
    with database_transaction(db):
        comment.is_deleted = True
        comment.deleted_at = datetime.utcnow()
        db.flush()
        
        # 更新话题评论数
        topic = db.query(ForumTopic).filter(ForumTopic.id == comment.topic_id).first()
        if topic:
            topic.comments_count = max(0, topic.comments_count - 1)
            db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{comment.topic_id}:comments:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{comment.topic_id}:detail"))
    
    logger.info(f"用户 {current_user_id} 删除评论 {comment_id} 成功")

# ===== 互动功能路由 =====

@router.post("/like", summary="点赞/取消点赞")
@optimized_route("点赞操作")
async def toggle_like(
    target_type: str = Form(..., regex="^(topic|comment)$"),
    target_id: int = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """点赞/取消点赞 - 优化版本"""
    
    with database_transaction(db):
        result = ForumLikeService.toggle_like_optimized(
            db, target_type, target_id, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} {result['action']} {target_type} {target_id}")
    return result

@router.post("/follow", summary="关注/取消关注用户")
@optimized_route("关注操作")
async def toggle_follow(
    target_user_id: int = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """关注/取消关注用户 - 优化版本"""
    
    if target_user_id == current_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能关注自己"
        )
    
    # 检查目标用户是否存在
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 检查是否已关注
    existing_follow = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user_id,
        UserFollow.followed_id == target_user_id
    ).first()
    
    with database_transaction(db):
        if existing_follow:
            # 取消关注
            db.delete(existing_follow)
            action = "unfollowed"
        else:
            # 添加关注
            new_follow = UserFollow(
                follower_id=current_user_id,
                followed_id=target_user_id,
                created_at=datetime.utcnow()
            )
            db.add(new_follow)
            action = "followed"
        
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"user:{current_user_id}:follows:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"user:{target_user_id}:followers:*"))
    
    logger.info(f"用户 {current_user_id} {action} 用户 {target_user_id}")
    return {"action": action, "target_user_id": target_user_id}

# ===== 搜索和推荐路由 =====

@router.get("/search", summary="智能搜索")
@optimized_route("论坛搜索")
async def search_topics(
    q: str = Query(..., min_length=2, description="搜索关键词"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    category: Optional[str] = Query(None),
    sort_by: str = Query("relevance", regex="^(relevance|latest|hot)$"),
    db: Session = Depends(get_db)
):
    """智能搜索话题 - 优化版本"""
    
    cache_key = f"search:{q}:{skip}:{limit}:{category}:{sort_by}"
    cached_result = cache_manager.get(cache_key)
    if cached_result:
        return cached_result
    
    # 使用优化的搜索服务
    topics, total = ForumService.get_topics_list_optimized(
        db, skip, limit, category, q, sort_by
    )
    
    result = {
        "items": [ForumUtils.format_topic_response(topic, include_content=False) for topic in topics],
        "total": total,
        "skip": skip,
        "limit": limit,
        "query": q
    }
    
    cache_manager.set(cache_key, result, expire_time=300)
    return result

@router.get("/trending", summary="获取趋势话题")
@optimized_route("趋势话题")
async def get_trending_topics(
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(7, ge=1, le=30, description="时间范围（天）"),
    db: Session = Depends(get_db)
):
    """获取趋势话题 - 优化版本"""
    
    cache_key = f"trending:topics:{limit}:{days}"
    cached_result = cache_manager.get(cache_key)
    if cached_result:
        return cached_result
    
    # 计算趋势话题（基于点赞数、评论数、时间等权重）
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    topics = db.query(ForumTopic).filter(
        ForumTopic.created_at >= cutoff_date,
        ForumTopic.is_deleted == False
    ).order_by(
        desc(ForumTopic.likes_count + ForumTopic.comments_count * 2)
    ).limit(limit).all()
    
    result = {
        "items": [ForumUtils.format_topic_response(topic, include_content=False) for topic in topics],
        "days": days,
        "limit": limit
    }
    
    cache_manager.set(cache_key, result, expire_time=600)  # 10分钟缓存
    return result

# ===== 文件上传路由 =====

@router.post("/upload/single", summary="单文件上传")
@optimized_route("单文件上传")
async def upload_single_file(
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)
):
    """单文件上传 - 优化版本"""
    
    # 验证文件
    from project.utils.optimization.production_utils import validate_file_upload
    validate_file_upload(file)
    
    # 异步上传文件
    try:
        from project.utils.uploads import upload_single_file as upload_file
        file_url = await upload_file(file, f"forum/{current_user_id}")
        
        logger.info(f"用户 {current_user_id} 上传文件成功: {file_url}")
        return {"file_url": file_url, "filename": file.filename}
        
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文件上传失败"
        )

# 使用路由优化器应用批量优化
# router_optimizer.apply_batch_optimizations(router, {
#     "cache_ttl": 300,
#     "enable_compression": True,
#     "rate_limit": "100/minute",
#     "monitoring": True
# })

logger.info("💬 Forum Module - 论坛模块已加载")
