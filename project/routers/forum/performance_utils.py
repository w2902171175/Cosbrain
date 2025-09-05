"""
Forum 性能优化工具模块
用于优化数据库查询和缓存策略
"""

from typing import Dict, List, Optional, Set, Union, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging
from datetime import datetime, timedelta
from project.models import User, ForumTopic, ForumComment, ForumLike
from project.utils import cache_manager

logger = logging.getLogger(__name__)


class CacheConfig:
    """统一的缓存配置"""
    
    # 缓存过期时间(秒)
    CACHE_TIMES = {
        'hot_topics': 300,        # 5分钟 - 热门话题
        'topic_detail': 600,      # 10分钟 - 话题详情
        'topic_stats': 300,       # 5分钟 - 话题统计
        'comments': 300,          # 5分钟 - 评论列表
        'search_results': 1800,   # 30分钟 - 搜索结果
        'trending_topics': 600,   # 10分钟 - 趋势话题
        'user_profile': 3600,     # 1小时 - 用户资料
        'view_count': 300,        # 5分钟 - 浏览计数防抖
        'popular_searches': 3600, # 1小时 - 热门搜索
        'search_suggestions': 600,# 10分钟 - 搜索建议
    }
    
    @classmethod
    def get_cache_time(cls, cache_type: str) -> int:
        """获取缓存时间，带默认值"""
        return cls.CACHE_TIMES.get(cache_type, 300)


class QueryOptimizer:
    """数据库查询优化器"""
    
    @staticmethod
    def get_topics_batch(db: Session, topic_ids: List[int]) -> Dict[int, ForumTopic]:
        """批量获取话题信息"""
        if not topic_ids:
            return {}
        
        topics = db.query(ForumTopic).filter(ForumTopic.id.in_(topic_ids)).all()
        return {topic.id: topic for topic in topics}
    
    @staticmethod
    def get_comments_batch(db: Session, comment_ids: List[int]) -> Dict[int, ForumComment]:
        """批量获取评论信息"""
        if not comment_ids:
            return {}
        
        comments = db.query(ForumComment).filter(ForumComment.id.in_(comment_ids)).all()
        return {comment.id: comment for comment in comments}
    
    @staticmethod
    def get_likes_batch(
        db: Session, 
        user_id: int, 
        target_type: str, 
        target_ids: List[int]
    ) -> Set[int]:
        """批量检查用户点赞状态"""
        if not target_ids:
            return set()
        
        likes = db.query(ForumLike).filter(
            and_(
                ForumLike.user_id == user_id,
                ForumLike.target_type == target_type,
                ForumLike.target_id.in_(target_ids)
            )
        ).all()
        
        return {like.target_id for like in likes}
    
    @staticmethod
    def get_comment_likes_batch(
        db: Session, 
        user_id: int, 
        comment_ids: List[int]
    ) -> Set[int]:
        """批量检查用户对评论的点赞状态"""
        if not comment_ids or not user_id:
            return set()
        
        likes = db.query(ForumLike).filter(
            and_(
                ForumLike.user_id == user_id,
                ForumLike.comment_id.in_(comment_ids),
                ForumLike.deleted_at.is_(None)
            )
        ).all()
        
        return {like.comment_id for like in likes}
    
    @staticmethod
    def get_topic_stats_batch(db: Session, topic_ids: List[int]) -> Dict[int, Dict[str, int]]:
        """批量获取话题统计信息"""
        if not topic_ids:
            return {}
        
        # 获取评论数
        comment_counts = {}
        comments_query = db.query(
            ForumComment.topic_id,
            db.func.count(ForumComment.id).label('count')
        ).filter(
            and_(
                ForumComment.topic_id.in_(topic_ids),
                ForumComment.deleted_at.is_(None)
            )
        ).group_by(ForumComment.topic_id).all()
        
        for topic_id, count in comments_query:
            comment_counts[topic_id] = count
        
        # 获取点赞数
        like_counts = {}
        likes_query = db.query(
            ForumLike.target_id,
            db.func.count(ForumLike.id).label('count')
        ).filter(
            and_(
                ForumLike.target_type == 'topic',
                ForumLike.target_id.in_(topic_ids),
                ForumLike.deleted_at.is_(None)
            )
        ).group_by(ForumLike.target_id).all()
        
        for target_id, count in likes_query:
            like_counts[target_id] = count
        
        # 组合结果
        result = {}
        for topic_id in topic_ids:
            result[topic_id] = {
                'comment_count': comment_counts.get(topic_id, 0),
                'like_count': like_counts.get(topic_id, 0)
            }
        
        return result

    @staticmethod
    def get_reply_counts_batch(db: Session, comment_ids: List[int]) -> Dict[int, int]:
        """批量获取评论的回复数量"""
        if not comment_ids:
            return {}
        
        reply_counts = {}
        query_result = db.query(
            ForumComment.parent_id,
            db.func.count(ForumComment.id).label('count')
        ).filter(
            and_(
                ForumComment.parent_id.in_(comment_ids),
                ForumComment.deleted_at.is_(None)
            )
        ).group_by(ForumComment.parent_id).all()
        
        for parent_id, count in query_result:
            reply_counts[parent_id] = count
        
        # 确保所有comment_id都有对应的值
        for comment_id in comment_ids:
            if comment_id not in reply_counts:
                reply_counts[comment_id] = 0
        
        return reply_counts


class CacheOptimizer:
    """缓存优化器"""
    
    @staticmethod
    def invalidate_topic_caches(topic_id: int, user_id: Optional[int] = None):
        """智能失效话题相关缓存"""
        patterns_to_delete = [
            f"topic_detail:{topic_id}:*",  # 话题详情缓存
            f"topic_stats:{topic_id}",     # 话题统计缓存
            "hot_topics:*",                # 热门话题缓存
            "trending_topics:*",           # 趋势话题缓存
        ]
        
        for pattern in patterns_to_delete:
            try:
                cache_manager.delete_pattern(pattern)
                logger.debug(f"删除缓存模式: {pattern}")
            except Exception as e:
                logger.warning(f"删除缓存失败 {pattern}: {e}")
    
    @staticmethod
    def invalidate_comment_caches(topic_id: int, comment_id: Optional[int] = None):
        """智能失效评论相关缓存"""
        patterns_to_delete = [
            f"comments:{topic_id}:*",      # 评论列表缓存
            f"topic_detail:{topic_id}:*",  # 话题详情缓存
            f"topic_stats:{topic_id}",     # 话题统计缓存
        ]
        
        if comment_id:
            patterns_to_delete.append(f"comment_detail:{comment_id}")
        
        for pattern in patterns_to_delete:
            try:
                cache_manager.delete_pattern(pattern)
                logger.debug(f"删除缓存模式: {pattern}")
            except Exception as e:
                logger.warning(f"删除缓存失败 {pattern}: {e}")
    
    @staticmethod
    def invalidate_user_caches(user_id: int):
        """智能失效用户相关缓存"""
        patterns_to_delete = [
            f"user_profile:{user_id}",     # 用户资料缓存
            f"user_topics:{user_id}:*",    # 用户话题缓存
            f"user_comments:{user_id}:*",  # 用户评论缓存
        ]
        
        for pattern in patterns_to_delete:
            try:
                cache_manager.delete_pattern(pattern)
                logger.debug(f"删除缓存模式: {pattern}")
            except Exception as e:
                logger.warning(f"删除缓存失败 {pattern}: {e}")


class PerformanceMonitor:
    """性能监控工具"""
    
    @staticmethod
    def log_slow_query(query_name: str, duration: float, threshold: float = 1.0):
        """记录慢查询"""
        if duration > threshold:
            logger.warning(f"慢查询检测: {query_name} 耗时 {duration:.2f}s")
    
    @staticmethod
    def log_cache_miss(cache_key: str, operation: str):
        """记录缓存未命中"""
        logger.info(f"缓存未命中: {operation} - {cache_key}")
    
    @staticmethod
    def log_cache_hit(cache_key: str, operation: str):
        """记录缓存命中"""
        logger.debug(f"缓存命中: {operation} - {cache_key}")


def get_topic_with_cache(db: Session, topic_id: int) -> Optional[ForumTopic]:
    """带缓存的话题获取"""
    cache_key = f"topic_basic:{topic_id}"
    
    # 尝试从缓存获取
    cached_topic = cache_manager.get(cache_key)
    if cached_topic:
        PerformanceMonitor.log_cache_hit(cache_key, "get_topic")
        return cached_topic
    
    # 从数据库查询
    topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if topic:
        # 缓存话题基本信息
        cache_manager.set(
            cache_key, 
            topic, 
            expire=CacheConfig.get_cache_time('topic_detail')
        )
        PerformanceMonitor.log_cache_miss(cache_key, "get_topic")
    
    return topic


def get_user_with_cache(db: Session, user_id: int) -> Optional[User]:
    """带缓存的用户获取"""
    cache_key = f"user_basic:{user_id}"
    
    # 尝试从缓存获取
    cached_user = cache_manager.get(cache_key)
    if cached_user:
        PerformanceMonitor.log_cache_hit(cache_key, "get_user")
        return cached_user
    
    # 从数据库查询
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # 缓存用户基本信息
        cache_manager.set(
            cache_key, 
            user, 
            expire=CacheConfig.get_cache_time('user_profile')
        )
        PerformanceMonitor.log_cache_miss(cache_key, "get_user")
    
    return user


    return result


class SearchCacheManager:
    """搜索缓存管理器"""
    
    @staticmethod
    def record_search_query(query: str):
        """记录搜索查询，用于生成热门搜索"""
        try:
            from .forum_utils import CacheKeyManager
            popular_key = CacheKeyManager.popular_searches()
            
            # 获取当前热门搜索统计
            search_stats = cache_manager.get(popular_key) or {}
            
            # 清理查询词
            clean_query = query.strip().lower()
            if len(clean_query) >= 2:  # 只记录长度>=2的查询
                search_stats[clean_query] = search_stats.get(clean_query, 0) + 1
                
                # 限制记录数量，保留top 100
                if len(search_stats) > 100:
                    sorted_items = sorted(search_stats.items(), key=lambda x: x[1], reverse=True)
                    search_stats = dict(sorted_items[:100])
                
                # 更新缓存
                cache_time = CacheConfig.get_cache_time('popular_searches')
                cache_manager.set(popular_key, search_stats, expire=cache_time)
                
        except Exception as e:
            logger.warning(f"记录搜索查询失败: {e}")
    
    @staticmethod
    def get_popular_searches(limit: int = 10) -> List[Dict[str, Any]]:
        """获取热门搜索"""
        try:
            from .forum_utils import CacheKeyManager
            popular_key = CacheKeyManager.popular_searches()
            
            search_stats = cache_manager.get(popular_key) or {}
            
            # 按搜索次数排序
            sorted_searches = sorted(search_stats.items(), key=lambda x: x[1], reverse=True)
            
            return [
                {"query": query, "count": count} 
                for query, count in sorted_searches[:limit]
            ]
            
        except Exception as e:
            logger.warning(f"获取热门搜索失败: {e}")
            return []
    
    @staticmethod
    def get_search_suggestions(query: str, db: Session, limit: int = 5) -> List[str]:
        """获取搜索建议"""
        try:
            from .forum_utils import CacheKeyManager
            cache_key = CacheKeyManager.search_suggestions(query)
            
            # 尝试从缓存获取
            cached_suggestions = cache_manager.get(cache_key)
            if cached_suggestions:
                return cached_suggestions
            
            # 生成搜索建议
            suggestions = []
            clean_query = query.strip().lower()
            
            if len(clean_query) >= 2:
                # 从话题标题中查找相似的词
                like_pattern = f"%{clean_query}%"
                similar_topics = db.query(ForumTopic.title).filter(
                    ForumTopic.title.ilike(like_pattern)
                ).limit(20).all()
                
                # 提取关键词
                for (title,) in similar_topics:
                    words = title.split()
                    for word in words:
                        if clean_query in word.lower() and word not in suggestions:
                            suggestions.append(word)
                            if len(suggestions) >= limit:
                                break
                    if len(suggestions) >= limit:
                        break
            
            # 缓存建议
            cache_time = CacheConfig.get_cache_time('search_suggestions')
            cache_manager.set(cache_key, suggestions, expire=cache_time)
            
            return suggestions
            
        except Exception as e:
            logger.warning(f"获取搜索建议失败: {e}")
            return []


def batch_get_topics_with_cache(db: Session, topic_ids: List[int]) -> Dict[int, ForumTopic]:
    """批量获取话题（带缓存）"""
    if not topic_ids:
        return {}
    
    result = {}
    missing_ids = []
    
    # 尝试从缓存获取
    for topic_id in topic_ids:
        cache_key = f"topic_basic:{topic_id}"
        cached_topic = cache_manager.get(cache_key)
        if cached_topic:
            result[topic_id] = cached_topic
            PerformanceMonitor.log_cache_hit(cache_key, "batch_get_topics")
        else:
            missing_ids.append(topic_id)
    
    # 批量查询缺失的话题
    if missing_ids:
        topics = db.query(ForumTopic).filter(ForumTopic.id.in_(missing_ids)).all()
        cache_time = CacheConfig.get_cache_time('topic_detail')
        
        for topic in topics:
            result[topic.id] = topic
            # 缓存单个话题
            cache_key = f"topic_basic:{topic.id}"
            cache_manager.set(cache_key, topic, expire=cache_time)
            PerformanceMonitor.log_cache_miss(cache_key, "batch_get_topics")
    
    return result
