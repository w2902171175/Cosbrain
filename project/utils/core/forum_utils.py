# project/utils/core/forum_utils.py
"""
论坛工具函数 - 用于减少重复代码
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

def parse_attachments_safely(attachments_json: Optional[str]) -> List[Dict[str, Any]]:
    """安全解析附件JSON"""
    if not attachments_json:
        return []
    
    try:
        return json.loads(attachments_json)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse attachments: {e}")
        return []

def set_topic_compatibility_fields(topic, uploaded_files: List[Dict[str, Any]], user_id: int):
    """设置话题兼容性字段"""
    topic.owner_id = user_id
    topic.attachments_json = json.dumps(uploaded_files) if uploaded_files else None
    
    if uploaded_files:
        first_file = uploaded_files[0]
        topic.media_url = first_file.get("url")
        topic.media_type = first_file.get("type")
        topic.original_filename = first_file.get("filename")
        topic.media_size_bytes = first_file.get("size")
    else:
        topic.media_url = None
        topic.media_type = None
        topic.original_filename = None
        topic.media_size_bytes = None

def format_topic_data(topic, user_info: Dict[int, Dict], current_user_id: Optional[int] = None, db=None) -> Dict[str, Any]:
    """格式化话题数据"""
    attachments = parse_attachments_safely(topic.attachments)
    
    # 检查用户点赞状态
    user_liked = False
    if current_user_id and db:
        from project.models import ForumLike
        from sqlalchemy import and_
        like_exists = db.query(ForumLike).filter(
            and_(
                ForumLike.topic_id == topic.id,
                ForumLike.user_id == current_user_id
            )
        ).first()
        user_liked = like_exists is not None
    
    return {
        "id": topic.id,
        "title": topic.title,
        "content": topic.content,
        "author": user_info.get(topic.user_id, {"id": topic.user_id, "name": "未知用户"}),
        "created_at": topic.created_at.isoformat(),
        "updated_at": getattr(topic, 'updated_at', topic.created_at).isoformat(),
        "tags": topic.tags.split(", ") if topic.tags else [],
        "attachments": attachments,
        "shared_item_type": topic.shared_item_type,
        "shared_item_id": topic.shared_item_id,
        "status": topic.status,
        "stats": {
            "views": topic.views_count or 0,
            "likes": topic.likes_count or 0,
            "comments": topic.comment_count or 0
        },
        "user_interaction": {
            "liked": user_liked
        }
    }

def create_standard_response(success: bool, message: str, data: Any = None) -> Dict[str, Any]:
    """创建标准响应格式"""
    response = {
        "success": success,
        "message": message
    }
    if data is not None:
        response["data"] = data
    return response

class CacheKeyManager:
    """缓存键管理器"""
    PREFIX = "forum"
    
    @classmethod
    def hot_topics(cls, sort_by: str, page: int, page_size: int, **filters) -> str:
        filter_str = "_".join(f"{k}:{v}" for k, v in filters.items() if v is not None)
        return f"{cls.PREFIX}:hot_topics:{sort_by}:{page}:{page_size}:{filter_str}"
    
    @classmethod
    def topic_detail(cls, topic_id: int, user_id: Optional[int] = None) -> str:
        return f"{cls.PREFIX}:topic_detail:{topic_id}:{user_id or 'anonymous'}"
    
    @classmethod
    def topic_stats(cls, topic_id: int) -> str:
        return f"{cls.PREFIX}:topic_stats:{topic_id}"
    
    @classmethod
    def comments(cls, topic_id: int, page: int, page_size: int, sort_by: str) -> str:
        return f"{cls.PREFIX}:comments:{topic_id}:{page}:{page_size}:{sort_by}"
    
    @classmethod
    def search_results(cls, query: str, **params) -> str:
        import hashlib
        param_str = "_".join(f"{k}:{v}" for k, v in sorted(params.items()) if v is not None)
        query_hash = hashlib.md5(f"{query}:{param_str}".encode()).hexdigest()[:8]
        return f"{cls.PREFIX}:search:{query_hash}"
    
    @classmethod
    def popular_searches(cls) -> str:
        """热门搜索缓存键"""
        return f"{cls.PREFIX}:popular_searches"
    
    @classmethod
    def search_suggestions(cls, query: str) -> str:
        """搜索建议缓存键"""
        return f"{cls.PREFIX}:search_suggestions:{query[:20]}"

def handle_forum_error(operation: str, error: Exception) -> None:
    """统一的错误处理"""
    logger.error(f"{operation}失败: {error}")
    from fastapi import HTTPException, status
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"{operation}失败: {str(error)}"
    )
