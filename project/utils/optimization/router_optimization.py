# project/utils/router_optimization.py
"""
路由优化工具包 - 为所有路由模块提供统一的优化模式
"""
from functools import wraps
from typing import Dict, Any, List, Optional, Callable
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging
import asyncio
from contextlib import contextmanager

from ..core.error_decorators import handle_database_errors, database_transaction
# 使用现有的缓存管理器
try:
    from ..async_cache.cache_manager import CacheManager
except ImportError:
    # 如果导入失败，创建一个简单的占位符
    class CacheManager:
        async def get(self, key): return None
        async def set(self, key, value, ttl=300): return True

logger = logging.getLogger(__name__)

class RouterOptimizer:
    """路由优化器 - 提供统一的优化模式"""
    
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
    
    @staticmethod
    def optimize_query(query, preload_relations: List[str] = None):
        """优化查询 - 添加预加载"""
        if preload_relations:
            from sqlalchemy.orm import joinedload
            for relation in preload_relations:
                query = query.options(joinedload(relation))
        return query
    
    @staticmethod
    def batch_process_likes(db: Session, items: List[Any], user_id: int, like_model, foreign_key: str):
        """批量处理点赞状态"""
        if not items or not user_id:
            for item in items:
                item.is_liked_by_current_user = False
            return
        
        item_ids = [getattr(item, 'id') for item in items]
        user_likes = set(
            getattr(like, foreign_key) for like in 
            db.query(getattr(like_model, foreign_key)).filter(
                like_model.owner_id == user_id,
                getattr(like_model, foreign_key).in_(item_ids)
            ).all()
        )
        
        for item in items:
            item.is_liked_by_current_user = item.id in user_likes
    
    def cache_query_result(self, cache_key: str, query_func: Callable, ttl: int = 300):
        """缓存查询结果"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 尝试从缓存获取
                cached_result = await self.cache_manager.get(cache_key)
                if cached_result:
                    logger.info(f"缓存命中: {cache_key}")
                    return cached_result
                
                # 执行查询
                result = await func(*args, **kwargs)
                
                # 缓存结果
                await self.cache_manager.set(cache_key, result, ttl)
                logger.info(f"缓存设置: {cache_key}")
                
                return result
            return wrapper
        return decorator

# 全局优化器实例
router_optimizer = RouterOptimizer()

def apply_standard_optimizations(router_class):
    """应用标准优化的类装饰器"""
    def decorator(cls):
        # 为类添加优化方法
        cls.optimizer = router_optimizer
        cls.handle_database_errors = handle_database_errors
        cls.database_transaction = database_transaction
        
        return cls
    return decorator

# 标准优化装饰器
def optimized_route(operation_name: str, cache_key: Optional[str] = None, cache_ttl: int = 300):
    """标准优化路由装饰器"""
    def decorator(func):
        # 应用错误处理
        func = handle_database_errors(operation_name)(func)
        
        # 如果指定了缓存，应用缓存
        if cache_key:
            func = router_optimizer.cache_query_result(cache_key, func, cache_ttl)(func)
        
        return func
    return decorator
