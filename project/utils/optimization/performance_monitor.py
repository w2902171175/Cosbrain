# project/utils/optimization/performance_monitor.py
"""
聊天室性能监控工具
"""
import time
import logging
from functools import wraps
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """性能监控类"""
    
    def __init__(self):
        # 操作计时器
        self.operation_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        # 错误统计
        self.error_counts: Dict[str, int] = defaultdict(int)
        # 成功统计
        self.success_counts: Dict[str, int] = defaultdict(int)
        # 活跃连接统计
        self.active_connections: Dict[int, int] = defaultdict(int)
    
    def time_operation(self, operation_name: str):
        """操作计时装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    self.success_counts[operation_name] += 1
                    return result
                except Exception as e:
                    self.error_counts[operation_name] += 1
                    raise
                finally:
                    end_time = time.time()
                    duration = end_time - start_time
                    self.operation_times[operation_name].append(duration)
            return wrapper
        return decorator
    
    def get_operation_stats(self, operation_name: str) -> Dict:
        """获取操作统计信息"""
        times = list(self.operation_times[operation_name])
        if not times:
            return {
                "operation": operation_name,
                "count": 0,
                "avg_time": 0,
                "max_time": 0,
                "min_time": 0,
                "success_count": self.success_counts[operation_name],
                "error_count": self.error_counts[operation_name]
            }
        
        return {
            "operation": operation_name,
            "count": len(times),
            "avg_time": sum(times) / len(times),
            "max_time": max(times),
            "min_time": min(times),
            "success_count": self.success_counts[operation_name],
            "error_count": self.error_counts[operation_name],
            "success_rate": self.success_counts[operation_name] / (
                self.success_counts[operation_name] + self.error_counts[operation_name]
            ) if (self.success_counts[operation_name] + self.error_counts[operation_name]) > 0 else 0
        }
    
    def get_all_stats(self) -> List[Dict]:
        """获取所有操作的统计信息"""
        all_operations = set(list(self.operation_times.keys()) + 
                           list(self.success_counts.keys()) + 
                           list(self.error_counts.keys()))
        
        return [self.get_operation_stats(op) for op in all_operations]
    
    def update_connection_count(self, room_id: int, count: int):
        """更新房间连接数"""
        self.active_connections[room_id] = count
    
    def get_connection_stats(self) -> Dict:
        """获取连接统计"""
        total_connections = sum(self.active_connections.values())
        active_rooms = len([count for count in self.active_connections.values() if count > 0])
        
        return {
            "total_connections": total_connections,
            "active_rooms": active_rooms,
            "avg_connections_per_room": total_connections / active_rooms if active_rooms > 0 else 0,
            "room_details": dict(self.active_connections)
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.operation_times.clear()
        self.error_counts.clear()
        self.success_counts.clear()
        self.active_connections.clear()

# 全局性能监控实例
performance_monitor = PerformanceMonitor()

# 性能监控装饰器
def monitor_performance(operation_name: str):
    """性能监控装饰器"""
    return performance_monitor.time_operation(operation_name)

class DatabaseQueryOptimizer:
    """数据库查询优化器"""
    
    @staticmethod
    def add_query_hints(query, index_hints: Optional[List[str]] = None):
        """添加查询提示"""
        if index_hints:
            # 这里可以添加具体的索引提示逻辑
            pass
        return query
    
    @staticmethod
    def optimize_pagination(query, page: int, size: int):
        """优化分页查询"""
        offset = (page - 1) * size
        return query.offset(offset).limit(size)
    
    @staticmethod
    def batch_load_relationships(objects, relationship_name: str):
        """批量加载关联对象"""
        # 实现批量加载逻辑以避免N+1查询
        pass

class CacheOptimizer:
    """缓存优化器"""
    
    @staticmethod
    async def warm_up_cache(room_ids: List[int]):
        """预热缓存"""
        from project.utils.async_cache.cache import cache
        
        # 批量预热房间信息缓存
        for room_id in room_ids:
            # 预热逻辑
            pass
    
    @staticmethod
    async def invalidate_related_caches(room_id: int, user_id: Optional[int] = None):
        """智能缓存失效"""
        from project.utils.async_cache.cache import cache
        
        # 失效房间相关缓存
        await cache.invalidate_room_cache(room_id)
        
        # 失效用户相关缓存
        if user_id:
            await cache.invalidate_user_cache(user_id)
    
    @staticmethod
    def get_cache_key(prefix: str, **kwargs) -> str:
        """生成统一的缓存键"""
        key_parts = [prefix]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return ":".join(key_parts)
