# project/services/forum_service.py
"""
论坛服务层 - 统一业务逻辑处理
应用courses模块的成功优化模式到论坛模块
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func, text
import logging

from project.models import User, ForumTopic, ForumLike, ForumComment, UserFollow
from project.utils.optimization.production_utils import cache_manager
from project.utils.database.optimization import query_optimizer
import project.oss_utils as oss_utils

logger = logging.getLogger(__name__)

class ForumService:
    """论坛核心业务逻辑服务"""
    
    @staticmethod
    def get_topic_by_id_optimized(db: Session, topic_id: int, current_user_id: Optional[int] = None) -> ForumTopic:
        """优化的话题查询 - 使用预加载避免N+1查询"""
        cache_key = f"topic:{topic_id}:detail"
        
        # 尝试从缓存获取
        cached_topic = cache_manager.get(cache_key)
        if cached_topic:
            return cached_topic
            
        # 使用joinedload预加载相关数据
        topic = db.query(ForumTopic).options(
            joinedload(ForumTopic.author),
            joinedload(ForumTopic.comments).joinedload(ForumComment.author),
            joinedload(ForumTopic.likes).joinedload(ForumLike.user)
        ).filter(
            ForumTopic.id == topic_id,
            ForumTopic.is_deleted == False
        ).first()
        
        if not topic:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="话题不存在"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, topic, expire_time=300)  # 5分钟缓存
        return topic
    
    @staticmethod
    def get_topics_list_optimized(
        db: Session, 
        skip: int = 0, 
        limit: int = 20,
        category: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "latest"
    ) -> Tuple[List[ForumTopic], int]:
        """优化的话题列表查询"""
        
        cache_key = f"topics:list:{skip}:{limit}:{category}:{search}:{sort_by}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建基础查询
        query = db.query(ForumTopic).options(
            joinedload(ForumTopic.author),
            joinedload(ForumTopic.likes),
            joinedload(ForumTopic.comments)
        ).filter(ForumTopic.is_deleted == False)
        
        # 应用过滤条件
        if category:
            query = query.filter(ForumTopic.category == category)
            
        if search:
            query = query.filter(
                or_(
                    ForumTopic.title.contains(search),
                    ForumTopic.content.contains(search)
                )
            )
        
        # 应用排序
        if sort_by == "latest":
            query = query.order_by(desc(ForumTopic.created_at))
        elif sort_by == "hot":
            query = query.order_by(desc(ForumTopic.likes_count))
        elif sort_by == "comments":
            query = query.order_by(desc(ForumTopic.comments_count))
        
        # 获取总数和分页结果
        total = query.count()
        topics = query.offset(skip).limit(limit).all()
        
        result = (topics, total)
        cache_manager.set(cache_key, result, expire_time=180)  # 3分钟缓存
        return result
    
    @staticmethod
    def create_topic_optimized(db: Session, topic_data: dict, current_user_id: int) -> ForumTopic:
        """优化的话题创建"""
        
        # 创建话题
        topic = ForumTopic(
            title=topic_data["title"],
            content=topic_data["content"],
            category=topic_data.get("category"),
            author_id=current_user_id,
            created_at=datetime.utcnow()
        )
        
        db.add(topic)
        db.flush()
        db.refresh(topic)
        
        # 异步清除相关缓存
        asyncio.create_task(
            cache_manager.delete_pattern("topics:list:*")
        )
        
        return topic
    
    @staticmethod
    def update_topic_optimized(
        db: Session, 
        topic_id: int, 
        update_data: dict, 
        current_user_id: int
    ) -> ForumTopic:
        """优化的话题更新"""
        
        topic = ForumService.get_topic_by_id_optimized(db, topic_id)
        
        # 权限检查
        if topic.author_id != current_user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限修改此话题"
            )
        
        # 更新字段
        for field, value in update_data.items():
            if hasattr(topic, field) and value is not None:
                setattr(topic, field, value)
        
        topic.updated_at = datetime.utcnow()
        db.flush()
        db.refresh(topic)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{topic_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern("topics:list:*"))
        
        return topic
    
    @staticmethod
    def delete_topic_optimized(db: Session, topic_id: int, current_user_id: int) -> bool:
        """优化的话题删除（软删除）"""
        
        topic = ForumService.get_topic_by_id_optimized(db, topic_id)
        
        # 权限检查
        if topic.author_id != current_user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限删除此话题"
            )
        
        topic.is_deleted = True
        topic.deleted_at = datetime.utcnow()
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{topic_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern("topics:list:*"))
        
        return True

class ForumCommentService:
    """论坛评论服务"""
    
    @staticmethod
    def get_comments_optimized(
        db: Session, 
        topic_id: int, 
        skip: int = 0, 
        limit: int = 50
    ) -> Tuple[List[ForumComment], int]:
        """优化的评论查询"""
        
        cache_key = f"topic:{topic_id}:comments:{skip}:{limit}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        query = db.query(ForumComment).options(
            joinedload(ForumComment.author),
            joinedload(ForumComment.replies).joinedload(ForumComment.author)
        ).filter(
            ForumComment.topic_id == topic_id,
            ForumComment.is_deleted == False,
            ForumComment.parent_id.is_(None)  # 只获取顶级评论
        ).order_by(desc(ForumComment.created_at))
        
        total = query.count()
        comments = query.offset(skip).limit(limit).all()
        
        result = (comments, total)
        cache_manager.set(cache_key, result, expire_time=300)
        return result
    
    @staticmethod
    def create_comment_optimized(
        db: Session, 
        comment_data: dict, 
        current_user_id: int
    ) -> ForumComment:
        """优化的评论创建"""
        
        comment = ForumComment(
            content=comment_data["content"],
            topic_id=comment_data["topic_id"],
            parent_id=comment_data.get("parent_id"),
            author_id=current_user_id,
            created_at=datetime.utcnow()
        )
        
        db.add(comment)
        db.flush()
        db.refresh(comment)
        
        # 更新话题评论数
        topic = db.query(ForumTopic).filter(ForumTopic.id == comment.topic_id).first()
        if topic:
            topic.comments_count = topic.comments_count + 1
            db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{comment.topic_id}:comments:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{comment.topic_id}:detail"))
        
        return comment

class ForumLikeService:
    """论坛点赞服务"""
    
    @staticmethod
    def toggle_like_optimized(
        db: Session, 
        target_type: str, 
        target_id: int, 
        current_user_id: int
    ) -> Dict[str, Any]:
        """优化的点赞/取消点赞"""
        
        # 检查是否已点赞
        existing_like = db.query(ForumLike).filter(
            ForumLike.user_id == current_user_id,
            ForumLike.target_type == target_type,
            ForumLike.target_id == target_id
        ).first()
        
        if existing_like:
            # 取消点赞
            db.delete(existing_like)
            action = "unliked"
            
            # 更新计数
            if target_type == "topic":
                topic = db.query(ForumTopic).filter(ForumTopic.id == target_id).first()
                if topic:
                    topic.likes_count = max(0, topic.likes_count - 1)
            
        else:
            # 添加点赞
            new_like = ForumLike(
                user_id=current_user_id,
                target_type=target_type,
                target_id=target_id,
                created_at=datetime.utcnow()
            )
            db.add(new_like)
            action = "liked"
            
            # 更新计数
            if target_type == "topic":
                topic = db.query(ForumTopic).filter(ForumTopic.id == target_id).first()
                if topic:
                    topic.likes_count = topic.likes_count + 1
        
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"topic:{target_id}:*"))
        
        return {"action": action, "target_type": target_type, "target_id": target_id}

class ForumUtils:
    """论坛工具类"""
    
    @staticmethod
    def validate_topic_data(data: dict) -> dict:
        """验证话题数据"""
        errors = []
        
        if not data.get("title") or len(data["title"].strip()) < 5:
            errors.append("话题标题至少需要5个字符")
        
        if not data.get("content") or len(data["content"].strip()) < 10:
            errors.append("话题内容至少需要10个字符")
        
        if data.get("title") and len(data["title"]) > 200:
            errors.append("话题标题不能超过200个字符")
        
        if errors:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"errors": errors}
            )
        
        return data
    
    @staticmethod
    def validate_comment_data(data: dict) -> dict:
        """验证评论数据"""
        errors = []
        
        if not data.get("content") or len(data["content"].strip()) < 2:
            errors.append("评论内容至少需要2个字符")
        
        if data.get("content") and len(data["content"]) > 1000:
            errors.append("评论内容不能超过1000个字符")
        
        if errors:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"errors": errors}
            )
        
        return data
    
    @staticmethod
    def format_topic_response(topic: ForumTopic, include_content: bool = True) -> dict:
        """格式化话题响应数据"""
        result = {
            "id": topic.id,
            "title": topic.title,
            "category": topic.category,
            "author": {
                "id": topic.author.id,
                "username": topic.author.username,
                "avatar": topic.author.avatar
            } if topic.author else None,
            "likes_count": topic.likes_count,
            "comments_count": topic.comments_count,
            "views_count": getattr(topic, 'views_count', 0),
            "created_at": topic.created_at,
            "updated_at": topic.updated_at
        }
        
        if include_content:
            result["content"] = topic.content
        
        return result
    
    @staticmethod
    def format_comment_response(comment: ForumComment) -> dict:
        """格式化评论响应数据"""
        return {
            "id": comment.id,
            "content": comment.content,
            "author": {
                "id": comment.author.id,
                "username": comment.author.username,
                "avatar": comment.author.avatar
            } if comment.author else None,
            "parent_id": comment.parent_id,
            "replies_count": len(comment.replies) if comment.replies else 0,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at
        }
