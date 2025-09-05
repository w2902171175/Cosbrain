# project/utils/database/optimization.py
from sqlalchemy import Index, text, func, and_, or_
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from functools import wraps

from project.models import ForumTopic, ForumComment, ForumLike, User, UserFollow
from ..async_cache.cache_manager import EnhancedCacheManager

logger = logging.getLogger(__name__)

# 全局缓存管理器实例
_cache_manager = None

def get_cache_manager():
    """获取缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        try:
            _cache_manager = EnhancedCacheManager()
        except Exception as e:
            logger.warning(f"无法初始化增强缓存管理器: {e}")
            # 使用简单的内存缓存作为fallback
            _cache_manager = SimpleFallbackCache()
    return _cache_manager

class SimpleFallbackCache:
    """简单的fallback缓存"""
    def __init__(self):
        self.cache = {}
    
    def set(self, key: str, value: any, expire: int = 300) -> bool:
        self.cache[key] = value
        return True
    
    def get(self, key: str) -> any:
        return self.cache.get(key)
    
    def delete(self, key: str) -> bool:
        if key in self.cache:
            del self.cache[key]
            return True
        return False

def cache_result(key_prefix="", expire=300):
    """增强版缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            cache_mgr = get_cache_manager()
            
            # 尝试从缓存获取
            cached_result = cache_mgr.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_mgr.set(cache_key, result, expire)
            return result
        return wrapper
    return decorator

class ForumCache:
    """论坛缓存工具类"""
    
    @staticmethod
    def get_hot_topics_cache_key(time_range_hours: int = 24):
        return f"forum:hot_topics:{time_range_hours}h"
    
    @staticmethod
    def get_user_cache_key(user_id: int):
        return f"forum:user:{user_id}"
    
    @staticmethod
    def invalidate_user_cache(user_id: int):
        """清除用户相关缓存"""
        cache_mgr = get_cache_manager()
        cache_mgr.delete(ForumCache.get_user_cache_key(user_id))
    
    @staticmethod
    def invalidate_hot_topics_cache():
        """清除热门话题缓存"""
        cache_mgr = get_cache_manager()
        for hours in [1, 6, 24, 168]:  # 1小时, 6小时, 24小时, 1周
            cache_mgr.delete(ForumCache.get_hot_topics_cache_key(hours))

logger = logging.getLogger(__name__)

class DatabaseOptimizer:
    """数据库优化器"""
    
    @staticmethod
    def create_forum_indexes(engine):
        """创建论坛相关索引"""
        try:
            with engine.connect() as conn:
                # 论坛主题索引
                indexes = [
                    # 按创建时间排序的索引
                    "CREATE INDEX IF NOT EXISTS idx_forum_topic_created ON forum_topics(created_at DESC)",
                    
                    # 热门话题索引（按点赞数和评论数）
                    "CREATE INDEX IF NOT EXISTS idx_forum_topic_popularity ON forum_topics(likes_count DESC, comments_count DESC, created_at DESC)",
                    
                    # 用户主题索引
                    "CREATE INDEX IF NOT EXISTS idx_forum_topic_owner ON forum_topics(owner_id, created_at DESC)",
                    
                    # 论坛评论索引
                    "CREATE INDEX IF NOT EXISTS idx_forum_comment_topic ON forum_comments(topic_id, created_at ASC)",
                    "CREATE INDEX IF NOT EXISTS idx_forum_comment_owner ON forum_comments(owner_id, created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_forum_comment_parent ON forum_comments(parent_comment_id, created_at ASC)",
                    
                    # 点赞索引
                    "CREATE INDEX IF NOT EXISTS idx_forum_like_owner_topic ON forum_likes(owner_id, topic_id)",
                    "CREATE INDEX IF NOT EXISTS idx_forum_like_topic ON forum_likes(topic_id)",
                    
                    # 用户关注索引
                    "CREATE INDEX IF NOT EXISTS idx_user_follow_follower ON user_follows(follower_id)",
                    "CREATE INDEX IF NOT EXISTS idx_user_follow_followed ON user_follows(followed_id)",
                    
                    # 全文搜索索引（PostgreSQL）
                    "CREATE INDEX IF NOT EXISTS idx_forum_topic_search ON forum_topics USING gin(to_tsvector('simple', title || ' ' || content))",
                ]
                
                for index_sql in indexes:
                    try:
                        conn.execute(text(index_sql))
                        logger.info(f"索引创建成功: {index_sql[:50]}...")
                    except Exception as e:
                        logger.warning(f"索引创建失败: {e}")
                
                conn.commit()
                logger.info("论坛索引创建完成")
                
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
    
    @staticmethod
    def analyze_table_statistics(engine):
        """分析表统计信息"""
        try:
            with engine.connect() as conn:
                # 更新表统计信息
                tables = ['forum_topics', 'forum_comments', 'forum_likes', 'students', 'user_follows']
                for table in tables:
                    try:
                        conn.execute(text(f"ANALYZE {table}"))
                        logger.info(f"表统计信息更新完成: {table}")
                    except Exception as e:
                        logger.warning(f"更新表统计信息失败 {table}: {e}")
                
                conn.commit()
        except Exception as e:
            logger.error(f"分析表统计信息失败: {e}")

class ForumQueryOptimizer:
    """论坛查询优化器"""
    
    @staticmethod
    @cache_result(key_prefix="forum", expire=300)  # 缓存5分钟
    def get_hot_topics(db: Session, limit: int = 20, time_range_hours: int = 24) -> List[Dict[str, Any]]:
        """获取热门话题（优化版）"""
        try:
            # 计算时间范围
            time_threshold = datetime.now() - timedelta(hours=time_range_hours)
            
            # 优化的查询：使用子查询和索引
            hot_topics_query = db.query(
                ForumTopic.id,
                ForumTopic.title,
                ForumTopic.content,
                ForumTopic.owner_id,
                ForumTopic.created_at,
                ForumTopic.likes_count,
                ForumTopic.comments_count,
                ForumTopic.view_count,
                User.name.label('author_name'),
                User.avatar_url.label('author_avatar')
            ).join(
                User, ForumTopic.owner_id == User.id
            ).filter(
                ForumTopic.created_at >= time_threshold
            ).order_by(
                # 热度算法：点赞数 * 2 + 评论数 * 3 + 浏览数 * 0.1
                (ForumTopic.likes_count * 2 + 
                 ForumTopic.comments_count * 3 + 
                 ForumTopic.view_count * 0.1).desc(),
                ForumTopic.created_at.desc()
            ).limit(limit)
            
            topics = hot_topics_query.all()
            
            # 转换为字典格式
            result = []
            for topic in topics:
                result.append({
                    'id': topic.id,
                    'title': topic.title,
                    'content': topic.content[:200] + '...' if len(topic.content) > 200 else topic.content,
                    'author_id': topic.owner_id,
                    'author_name': topic.author_name,
                    'author_avatar': topic.author_avatar,
                    'created_at': topic.created_at.isoformat(),
                    'likes_count': topic.likes_count,
                    'comments_count': topic.comments_count,
                    'view_count': topic.view_count,
                    'heat_score': topic.likes_count * 2 + topic.comments_count * 3 + topic.view_count * 0.1
                })
            
            return result
            
        except Exception as e:
            logger.error(f"获取热门话题失败: {e}")
            return []
    
    @staticmethod
    @cache_result(key_prefix="forum_user", expire=600)  # 缓存10分钟
    def get_user_info_batch(db: Session, user_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """批量获取用户信息（优化版）"""
        try:
            if not user_ids:
                return {}
            
            # 使用in查询批量获取
            users = db.query(
                User.id,
                User.name,
                User.avatar_url,
                User.student_id,
                User.major
            ).filter(
                User.id.in_(user_ids)
            ).all()
            
            return {
                user.id: {
                    'id': user.id,
                    'name': user.name,
                    'avatar_url': user.avatar_url,
                    'student_id': user.student_id,
                    'major': user.major
                }
                for user in users
            }
            
        except Exception as e:
            logger.error(f"批量获取用户信息失败: {e}")
            return {}
    
    @staticmethod
    def get_topic_comments_paginated(db: Session, topic_id: int, page: int = 1, 
                                   page_size: int = 20) -> Dict[str, Any]:
        """分页获取话题评论（优化版）"""
        try:
            offset = (page - 1) * page_size
            
            # 获取评论总数（缓存）
            cache_key = f"topic_comment_count:{topic_id}"
            cache_mgr = get_cache_manager()
            total_count = cache_mgr.get(cache_key)
            if total_count is None:
                total_count = db.query(ForumComment).filter(
                    ForumComment.topic_id == topic_id
                ).count()
                cache_mgr.set(cache_key, total_count, 300)  # 缓存5分钟
            
            # 获取评论列表
            comments_query = db.query(
                ForumComment.id,
                ForumComment.content,
                ForumComment.owner_id,
                ForumComment.parent_comment_id,
                ForumComment.created_at,
                ForumComment.likes_count,
                User.name.label('author_name'),
                User.avatar_url.label('author_avatar')
            ).join(
                User, ForumComment.owner_id == User.id
            ).filter(
                ForumComment.topic_id == topic_id
            ).order_by(
                ForumComment.created_at.asc()
            ).offset(offset).limit(page_size)
            
            comments = comments_query.all()
            
            # 构建评论树形结构
            comment_dict = {}
            root_comments = []
            
            for comment in comments:
                comment_data = {
                    'id': comment.id,
                    'content': comment.content,
                    'author_id': comment.owner_id,
                    'author_name': comment.author_name,
                    'author_avatar': comment.author_avatar,
                    'created_at': comment.created_at.isoformat(),
                    'likes_count': comment.likes_count,
                    'parent_comment_id': comment.parent_comment_id,
                    'replies': []
                }
                
                comment_dict[comment.id] = comment_data
                
                if comment.parent_comment_id is None:
                    root_comments.append(comment_data)
                else:
                    # 添加到父评论的回复列表
                    parent = comment_dict.get(comment.parent_comment_id)
                    if parent:
                        parent['replies'].append(comment_data)
            
            return {
                'comments': root_comments,
                'total_count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size
            }
            
        except Exception as e:
            logger.error(f"获取话题评论失败: {e}")
            return {'comments': [], 'total_count': 0, 'page': page, 'page_size': page_size, 'total_pages': 0}
    
    @staticmethod
    @cache_result(key_prefix="forum_stats", expire=1800)  # 缓存30分钟
    def get_topic_statistics(db: Session, topic_id: int) -> Dict[str, Any]:
        """获取话题统计信息（缓存版）"""
        try:
            # 获取基本统计
            topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
            if not topic:
                return {}
            
            # 获取点赞用户列表（前10个）
            recent_likes = db.query(
                ForumLike.owner_id,
                User.name,
                User.avatar_url
            ).join(
                User, ForumLike.owner_id == User.id
            ).filter(
                ForumLike.topic_id == topic_id
            ).order_by(
                ForumLike.created_at.desc()
            ).limit(10).all()
            
            return {
                'topic_id': topic_id,
                'likes_count': topic.likes_count,
                'comments_count': topic.comments_count,
                'view_count': topic.view_count,
                'recent_likes': [
                    {
                        'user_id': like.owner_id,
                        'name': like.name,
                        'avatar_url': like.avatar_url
                    }
                    for like in recent_likes
                ]
            }
            
        except Exception as e:
            logger.error(f"获取话题统计失败: {e}")
            return {}
    
    @staticmethod
    def search_topics_optimized(db: Session, query: str, page: int = 1, 
                               page_size: int = 20) -> Dict[str, Any]:
        """优化的话题搜索"""
        try:
            if not query or len(query.strip()) < 2:
                return {'topics': [], 'total_count': 0, 'page': page, 'page_size': page_size}
            
            query = query.strip()
            offset = (page - 1) * page_size
            
            # 使用PostgreSQL全文搜索
            search_query = db.query(
                ForumTopic.id,
                ForumTopic.title,
                ForumTopic.content,
                ForumTopic.owner_id,
                ForumTopic.created_at,
                ForumTopic.likes_count,
                ForumTopic.comments_count,
                User.name.label('author_name'),
                # 添加相关性评分
                func.ts_rank(
                    func.to_tsvector('simple', ForumTopic.title + ' ' + ForumTopic.content),
                    func.plainto_tsquery('simple', query)
                ).label('rank')
            ).join(
                User, ForumTopic.owner_id == User.id
            ).filter(
                func.to_tsvector('simple', ForumTopic.title + ' ' + ForumTopic.content).match(
                    func.plainto_tsquery('simple', query)
                )
            ).order_by(
                text('rank DESC'),
                ForumTopic.created_at.desc()
            )
            
            # 获取总数
            total_count = search_query.count()
            
            # 获取分页结果
            topics = search_query.offset(offset).limit(page_size).all()
            
            result_topics = []
            for topic in topics:
                # 高亮搜索关键词
                highlighted_title = ForumQueryOptimizer._highlight_keywords(topic.title, query)
                highlighted_content = ForumQueryOptimizer._highlight_keywords(
                    topic.content[:200] + '...' if len(topic.content) > 200 else topic.content, 
                    query
                )
                
                result_topics.append({
                    'id': topic.id,
                    'title': highlighted_title,
                    'content': highlighted_content,
                    'author_id': topic.owner_id,
                    'author_name': topic.author_name,
                    'created_at': topic.created_at.isoformat(),
                    'likes_count': topic.likes_count,
                    'comments_count': topic.comments_count,
                    'relevance_score': float(topic.rank) if hasattr(topic, 'rank') else 0.0
                })
            
            return {
                'topics': result_topics,
                'total_count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': (total_count + page_size - 1) // page_size,
                'query': query
            }
            
        except Exception as e:
            logger.error(f"搜索话题失败: {e}")
            return {'topics': [], 'total_count': 0, 'page': page, 'page_size': page_size}
    
    @staticmethod
    def _highlight_keywords(text: str, keywords: str) -> str:
        """高亮搜索关键词"""
        if not text or not keywords:
            return text
        
        # 简单的关键词高亮
        import re
        for keyword in keywords.split():
            if len(keyword) >= 2:
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                text = pattern.sub(f'<mark>{keyword}</mark>', text)
        
        return text

class CacheRefreshScheduler:
    """缓存刷新调度器"""
    
    @staticmethod
    def refresh_hot_topics_cache(db: Session):
        """刷新热门话题缓存"""
        try:
            # 清除旧缓存
            ForumCache.invalidate_hot_topics_cache()
            
            # 重新计算热门话题
            ForumQueryOptimizer.get_hot_topics(db)
            
            logger.info("热门话题缓存刷新完成")
        except Exception as e:
            logger.error(f"刷新热门话题缓存失败: {e}")
    
    @staticmethod
    def refresh_user_redis_cache(db: Session, user_id: int):
        """刷新用户Redis缓存（原stats_cache已废弃，现使用Redis）"""
        try:
            # 清除用户相关缓存
            ForumCache.invalidate_user_cache(user_id)
            
            # 重新计算用户信息
            ForumQueryOptimizer.get_user_info_batch(db, [user_id])
            
            logger.info(f"用户{user_id}Redis缓存刷新完成")
        except Exception as e:
            logger.error(f"刷新用户Redis缓存失败: {e}")
    
    @staticmethod
    def batch_update_topic_counts(db: Session):
        """批量更新话题计数"""
        try:
            # 更新点赞数
            like_counts = db.query(
                ForumLike.topic_id,
                func.count(ForumLike.id).label('likes_count')
            ).group_by(ForumLike.topic_id).subquery()
            
            db.query(ForumTopic).join(
                like_counts, ForumTopic.id == like_counts.c.topic_id
            ).update(
                {ForumTopic.likes_count: like_counts.c.likes_count},
                synchronize_session=False
            )
            
            # 更新评论数
            comment_counts = db.query(
                ForumComment.topic_id,
                func.count(ForumComment.id).label('comments_count')
            ).group_by(ForumComment.topic_id).subquery()
            
            db.query(ForumTopic).join(
                comment_counts, ForumTopic.id == comment_counts.c.topic_id
            ).update(
                {ForumTopic.comments_count: comment_counts.c.comments_count},
                synchronize_session=False
            )
            
            db.commit()
            logger.info("批量更新话题计数完成")
            
        except Exception as e:
            logger.error(f"批量更新话题计数失败: {e}")
            db.rollback()

# 全局实例
db_optimizer = DatabaseOptimizer()
query_optimizer = ForumQueryOptimizer()
cache_scheduler = CacheRefreshScheduler()
