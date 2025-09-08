# project/utils/cache_manager.py
"""
增强版缓存管理器 - 生产环境版本
支持Redis集群、内存缓存、分布式锁、缓存预热、监控等高级功能
"""
import redis
import redis.sentinel
import json
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union, Callable
import os
from functools import wraps
import logging
import threading
from contextlib import contextmanager
import pickle
import hashlib
import zlib

logger = logging.getLogger(__name__)

class CacheConfig:
    """缓存配置类"""
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_cluster_nodes = os.getenv("REDIS_CLUSTER_NODES", "").split(",")
        self.redis_sentinel_hosts = os.getenv("REDIS_SENTINEL_HOSTS", "").split(",")
        self.redis_sentinel_service = os.getenv("REDIS_SENTINEL_SERVICE", "mymaster")
        self.redis_password = os.getenv("REDIS_PASSWORD")
        self.enable_compression = os.getenv("CACHE_ENABLE_COMPRESSION", "true").lower() == "true"
        self.compression_threshold = int(os.getenv("CACHE_COMPRESSION_THRESHOLD", "1024"))
        self.default_expire = int(os.getenv("CACHE_DEFAULT_EXPIRE", "3600"))
        self.max_memory_cache_size = int(os.getenv("CACHE_MAX_MEMORY_SIZE", "1000"))
        self.enable_metrics = os.getenv("CACHE_ENABLE_METRICS", "true").lower() == "true"

class CacheMetrics:
    """缓存监控指标"""
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.errors = 0
        self.total_memory_usage = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
    
    def record_hit(self):
        with self._lock:
            self.hits += 1
    
    def record_miss(self):
        with self._lock:
            self.misses += 1
    
    def record_set(self):
        with self._lock:
            self.sets += 1
    
    def record_delete(self):
        with self._lock:
            self.deletes += 1
    
    def record_error(self):
        with self._lock:
            self.errors += 1
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            uptime = time.time() - self.start_time
            
            return {
                "hits": self.hits,
                "misses": self.misses,
                "sets": self.sets,
                "deletes": self.deletes,
                "errors": self.errors,
                "hit_rate": f"{hit_rate:.2f}%",
                "uptime_seconds": uptime,
                "requests_per_second": total_requests / uptime if uptime > 0 else 0,
                "memory_usage": self.total_memory_usage
            }

class DistributedLock:
    """分布式锁实现"""
    def __init__(self, redis_client, key: str, timeout: int = 10, retry_delay: float = 0.1):
        self.redis_client = redis_client
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.identifier = None
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
    
    def acquire(self) -> bool:
        """获取锁"""
        import uuid
        self.identifier = str(uuid.uuid4())
        end_time = time.time() + self.timeout
        
        while time.time() < end_time:
            if self.redis_client.set(self.key, self.identifier, nx=True, ex=self.timeout):
                return True
            time.sleep(self.retry_delay)
        
        raise TimeoutError(f"Failed to acquire lock for {self.key}")
    
    def release(self) -> bool:
        """释放锁"""
        if not self.identifier:
            return False
        
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = self.redis_client.eval(lua_script, 1, self.key, self.identifier)
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to release lock {self.key}: {e}")
            return False

class EnhancedCacheManager:
    """增强版缓存管理器"""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.redis_client = None
        self.memory_cache = {}
        self.memory_cache_access_time = {}
        self.metrics = CacheMetrics()
        self._memory_lock = threading.RLock()
        self._init_redis()
        
        # 启动清理线程
        if not hasattr(self, '_cleanup_thread_started'):
            self._cleanup_thread_started = True
            cleanup_thread = threading.Thread(target=self._memory_cleanup_worker, daemon=True)
            cleanup_thread.start()
    
    def _init_redis(self):
        """初始化Redis连接"""
        try:
            # 尝试Redis集群
            if self.config.redis_cluster_nodes and self.config.redis_cluster_nodes[0]:
                try:
                    from redis.cluster import RedisCluster
                    startup_nodes = [{"host": node.split(":")[0], "port": int(node.split(":")[1])} 
                                   for node in self.config.redis_cluster_nodes if node]
                    self.redis_client = RedisCluster(startup_nodes=startup_nodes, 
                                                   decode_responses=True,
                                                   password=self.config.redis_password)
                    self.redis_client.ping()
                    logger.info("Redis集群连接成功")
                    return
                except ImportError:
                    logger.warning("redis-py集群模块未找到，跳过集群模式")
                except Exception as e:
                    logger.warning(f"Redis集群连接失败: {e}")
            
            # 尝试Redis哨兵
            if self.config.redis_sentinel_hosts and self.config.redis_sentinel_hosts[0]:
                try:
                    sentinel_list = [(host.split(":")[0], int(host.split(":")[1])) 
                                   for host in self.config.redis_sentinel_hosts if host]
                    sentinel = redis.sentinel.Sentinel(sentinel_list)
                    self.redis_client = sentinel.master_for(self.config.redis_sentinel_service, 
                                                          decode_responses=True,
                                                          password=self.config.redis_password)
                    self.redis_client.ping()
                    logger.info("Redis哨兵连接成功")
                    return
                except Exception as e:
                    logger.warning(f"Redis哨兵连接失败: {e}")
            
            # 单实例Redis
            self.redis_client = redis.from_url(self.config.redis_url, 
                                             decode_responses=True,
                                             password=self.config.redis_password)
            self.redis_client.ping()
            logger.info("Redis单实例连接成功")
            
        except Exception as e:
            logger.warning(f"Redis连接失败，使用内存缓存: {e}")
            self.redis_client = None
    
    def _serialize(self, value: Any) -> bytes:
        """序列化数据"""
        try:
            # 优先使用JSON序列化
            if isinstance(value, (dict, list, str, int, float, bool, type(None))):
                serialized = json.dumps(value, default=str, ensure_ascii=False).encode('utf-8')
            else:
                # 复杂对象使用pickle
                serialized = pickle.dumps(value)
            
            # 压缩大数据
            if self.config.enable_compression and len(serialized) > self.config.compression_threshold:
                compressed = zlib.compress(serialized)
                return b'compressed:' + compressed
            
            return serialized
        except Exception as e:
            logger.error(f"序列化失败: {e}")
            return pickle.dumps(value)
    
    def _deserialize(self, value: Union[bytes, str]) -> Any:
        """反序列化数据"""
        try:
            if isinstance(value, str):
                value = value.encode('utf-8')
            
            # 检查是否压缩
            if value.startswith(b'compressed:'):
                value = zlib.decompress(value[11:])
            
            # 尝试JSON反序列化
            try:
                return json.loads(value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # 使用pickle反序列化
                return pickle.loads(value)
                
        except Exception as e:
            logger.error(f"反序列化失败: {e}")
            return value
    
    def _memory_cleanup_worker(self):
        """内存缓存清理工作线程"""
        while True:
            try:
                time.sleep(60)  # 每分钟清理一次
                self._cleanup_memory_cache()
            except Exception as e:
                logger.error(f"内存缓存清理失败: {e}")
    
    def _cleanup_memory_cache(self):
        """清理过期的内存缓存"""
        with self._memory_lock:
            current_time = datetime.now()
            expired_keys = []
            
            for key, cache_item in self.memory_cache.items():
                if cache_item.get("expire_time") and cache_item["expire_time"] < current_time:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.memory_cache[key]
                if key in self.memory_cache_access_time:
                    del self.memory_cache_access_time[key]
            
            # LRU清理：如果缓存数量超过限制，删除最久未访问的
            if len(self.memory_cache) > self.config.max_memory_cache_size:
                # 按访问时间排序
                sorted_keys = sorted(self.memory_cache_access_time.items(), key=lambda x: x[1])
                keys_to_remove = sorted_keys[:len(self.memory_cache) - self.config.max_memory_cache_size]
                
                for key, _ in keys_to_remove:
                    if key in self.memory_cache:
                        del self.memory_cache[key]
                    if key in self.memory_cache_access_time:
                        del self.memory_cache_access_time[key]
            
            if expired_keys:
                logger.debug(f"清理了 {len(expired_keys)} 个过期缓存项")
    
    def set(self, key: str, value: Any, expire: int = None) -> bool:
        """设置缓存"""
        if expire is None:
            expire = self.config.default_expire
        
        try:
            serialized_value = self._serialize(value)
            
            if self.redis_client:
                # Redis缓存
                success = self.redis_client.setex(key, expire, serialized_value)
            else:
                success = True
            
            # 内存缓存（作为备份）
            with self._memory_lock:
                self.memory_cache[key] = {
                    "value": serialized_value,
                    "expire_time": datetime.now() + timedelta(seconds=expire) if expire > 0 else None
                }
                self.memory_cache_access_time[key] = time.time()
            
            if self.config.enable_metrics:
                self.metrics.record_set()
            
            return success
            
        except Exception as e:
            logger.error(f"设置缓存失败 {key}: {e}")
            if self.config.enable_metrics:
                self.metrics.record_error()
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            value = None
            
            # 优先从Redis获取
            if self.redis_client:
                try:
                    value = self.redis_client.get(key)
                except Exception as e:
                    logger.warning(f"Redis获取失败，尝试内存缓存: {e}")
            
            # 如果Redis失败，从内存缓存获取
            if value is None:
                with self._memory_lock:
                    cache_item = self.memory_cache.get(key)
                    if cache_item:
                        # 检查是否过期
                        if cache_item.get("expire_time") is None or cache_item["expire_time"] > datetime.now():
                            value = cache_item["value"]
                            self.memory_cache_access_time[key] = time.time()
                        else:
                            # 过期删除
                            del self.memory_cache[key]
                            if key in self.memory_cache_access_time:
                                del self.memory_cache_access_time[key]
            
            if value is not None:
                if self.config.enable_metrics:
                    self.metrics.record_hit()
                return self._deserialize(value)
            
            if self.config.enable_metrics:
                self.metrics.record_miss()
            return None
            
        except Exception as e:
            logger.error(f"获取缓存失败 {key}: {e}")
            if self.config.enable_metrics:
                self.metrics.record_error()
            return None
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            success = True
            
            # 从Redis删除
            if self.redis_client:
                try:
                    success = bool(self.redis_client.delete(key))
                except Exception as e:
                    logger.warning(f"Redis删除失败: {e}")
                    success = False
            
            # 从内存缓存删除
            with self._memory_lock:
                if key in self.memory_cache:
                    del self.memory_cache[key]
                if key in self.memory_cache_access_time:
                    del self.memory_cache_access_time[key]
            
            if self.config.enable_metrics:
                self.metrics.record_delete()
            
            return success
            
        except Exception as e:
            logger.error(f"删除缓存失败 {key}: {e}")
            if self.config.enable_metrics:
                self.metrics.record_error()
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """根据模式删除缓存"""
        try:
            deleted_count = 0
            
            # Redis模式删除
            if self.redis_client:
                try:
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        deleted_count = self.redis_client.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis模式删除失败: {e}")
            
            # 内存缓存模式删除
            import fnmatch
            with self._memory_lock:
                keys_to_delete = [k for k in self.memory_cache.keys() 
                                if fnmatch.fnmatch(k, pattern)]
                for key in keys_to_delete:
                    del self.memory_cache[key]
                    if key in self.memory_cache_access_time:
                        del self.memory_cache_access_time[key]
                
                deleted_count += len(keys_to_delete)
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"按模式删除缓存失败 {pattern}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            if self.redis_client:
                return bool(self.redis_client.exists(key))
            
            with self._memory_lock:
                cache_item = self.memory_cache.get(key)
                if cache_item:
                    if cache_item.get("expire_time") is None or cache_item["expire_time"] > datetime.now():
                        return True
                    else:
                        # 过期删除
                        del self.memory_cache[key]
                        if key in self.memory_cache_access_time:
                            del self.memory_cache_access_time[key]
            
            return False
            
        except Exception as e:
            logger.error(f"检查缓存存在性失败 {key}: {e}")
            return False
    
    def expire(self, key: str, seconds: int) -> bool:
        """设置缓存过期时间"""
        try:
            success = True
            
            if self.redis_client:
                success = bool(self.redis_client.expire(key, seconds))
            
            # 更新内存缓存过期时间
            with self._memory_lock:
                if key in self.memory_cache:
                    self.memory_cache[key]["expire_time"] = datetime.now() + timedelta(seconds=seconds)
            
            return success
            
        except Exception as e:
            logger.error(f"设置缓存过期时间失败 {key}: {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """获取缓存剩余过期时间"""
        try:
            if self.redis_client:
                return self.redis_client.ttl(key)
            
            with self._memory_lock:
                cache_item = self.memory_cache.get(key)
                if cache_item and cache_item.get("expire_time"):
                    remaining = cache_item["expire_time"] - datetime.now()
                    return max(0, int(remaining.total_seconds()))
            
            return -1
            
        except Exception as e:
            logger.error(f"获取缓存TTL失败 {key}: {e}")
            return -1
    
    def get_lock(self, key: str, timeout: int = 10) -> DistributedLock:
        """获取分布式锁"""
        if self.redis_client:
            return DistributedLock(self.redis_client, key, timeout)
        else:
            # 内存锁（单机环境）
            return threading.Lock()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        stats = self.metrics.get_stats() if self.config.enable_metrics else {}
        
        stats.update({
            "backend": "Redis" if self.redis_client else "Memory",
            "memory_cache_size": len(self.memory_cache),
            "memory_cache_max_size": self.config.max_memory_cache_size,
            "compression_enabled": self.config.enable_compression,
            "config": {
                "default_expire": self.config.default_expire,
                "compression_threshold": self.config.compression_threshold,
                "max_memory_size": self.config.max_memory_cache_size
            }
        })
        
        return stats
    
    def warm_up(self, warm_up_data: Dict[str, Any], expire: int = None):
        """缓存预热"""
        logger.info(f"开始缓存预热，数据量: {len(warm_up_data)}")
        
        for key, value in warm_up_data.items():
            try:
                self.set(key, value, expire)
            except Exception as e:
                logger.error(f"预热缓存失败 {key}: {e}")
        
        logger.info("缓存预热完成")
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health = {
            "redis_available": False,
            "memory_cache_available": True,
            "total_memory_items": len(self.memory_cache),
            "errors": self.metrics.errors if self.config.enable_metrics else 0
        }
        
        try:
            if self.redis_client:
                self.redis_client.ping()
                health["redis_available"] = True
                
                # Redis信息
                redis_info = self.redis_client.info()
                health["redis_info"] = {
                    "version": redis_info.get("redis_version"),
                    "used_memory": redis_info.get("used_memory_human"),
                    "connected_clients": redis_info.get("connected_clients"),
                    "uptime": redis_info.get("uptime_in_seconds")
                }
                
        except Exception as e:
            health["redis_error"] = str(e)
        
        return health

# 装饰器函数
def cache_result(key_prefix: str = "", expire: int = None, cache_manager=None):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if cache_manager is None:
                from . import cache_manager as cm
                manager = cm.cache_manager
            else:
                manager = cache_manager
            
            # 生成缓存key
            args_str = str(args) + str(sorted(kwargs.items()))
            cache_key = f"{key_prefix}:{func.__name__}:{hashlib.md5(args_str.encode()).hexdigest()}"
            
            # 尝试从缓存获取
            cached_result = manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            manager.set(cache_key, result, expire)
            return result
        
        return wrapper
    return decorator

def async_cache_result(key_prefix: str = "", expire: int = None, cache_manager=None):
    """异步缓存装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if cache_manager is None:
                from . import cache_manager as cm
                manager = cm.cache_manager
            else:
                manager = cache_manager
            
            # 生成缓存key
            args_str = str(args) + str(sorted(kwargs.items()))
            cache_key = f"{key_prefix}:{func.__name__}:{hashlib.md5(args_str.encode()).hexdigest()}"
            
            # 尝试从缓存获取
            cached_result = manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            manager.set(cache_key, result, expire)
            return result
        
        return wrapper
    return decorator

# 论坛特定的缓存管理
class ForumCacheManager:
    """论坛专用缓存管理器"""
    
    def __init__(self, cache_manager: EnhancedCacheManager):
        self.cache = cache_manager
    
    # 缓存键生成
    def get_hot_topics_key(self, limit: int = 10) -> str:
        return f"forum:hot_topics:{limit}"
    
    def get_user_info_key(self, user_id: int) -> str:
        return f"user:info:{user_id}"
    
    def get_topic_stats_key(self, topic_id: int) -> str:
        return f"forum:topic:stats:{topic_id}"
    
    def get_user_posts_key(self, user_id: int, page: int = 1) -> str:
        return f"user:posts:{user_id}:page:{page}"
    
    def get_category_topics_key(self, category_id: int, page: int = 1) -> str:
        return f"forum:category:{category_id}:topics:page:{page}"
    
    def get_search_results_key(self, query: str, page: int = 1) -> str:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        return f"search:results:{query_hash}:page:{page}"
    
    # 缓存失效策略
    def invalidate_topic_cache(self, topic_id: int, user_id: int = None):
        """删除话题相关缓存"""
        patterns = [
            f"forum:topic:stats:{topic_id}",
            "forum:hot_topics:*",
            f"forum:topic:{topic_id}:*",
            "search:results:*"  # 搜索结果也需要失效
        ]
        
        if user_id:
            patterns.append(f"user:posts:{user_id}:*")
        
        for pattern in patterns:
            self.cache.delete_pattern(pattern)
    
    def invalidate_user_cache(self, user_id: int):
        """删除用户相关缓存"""
        patterns = [
            f"user:info:{user_id}",
            f"user:posts:{user_id}:*",
            f"user:{user_id}:*"
        ]
        
        for pattern in patterns:
            self.cache.delete_pattern(pattern)
    
    def invalidate_category_cache(self, category_id: int):
        """删除分类相关缓存"""
        patterns = [
            f"forum:category:{category_id}:*",
            "forum:hot_topics:*"
        ]
        
        for pattern in patterns:
            self.cache.delete_pattern(pattern)
    
    # 批量缓存操作
    def warm_up_hot_data(self, db_session):
        """预热热门数据"""
        try:
            # 这里应该根据实际的数据库查询来获取热门数据
            # 示例代码，需要根据实际情况调整
            warm_up_data = {}
            
            # 预热热门话题
            # hot_topics = get_hot_topics_from_db(db_session)
            # warm_up_data[self.get_hot_topics_key()] = hot_topics
            
            # 预热活跃用户信息
            # active_users = get_active_users_from_db(db_session)
            # for user in active_users:
            #     warm_up_data[self.get_user_info_key(user.id)] = user_to_dict(user)
            
            self.cache.warm_up(warm_up_data, expire=1800)  # 30分钟过期
            
        except Exception as e:
            logger.error(f"缓存预热失败: {e}")

# 全局缓存实例 - 延迟初始化
_cache_manager_instance = None
_forum_cache_instance = None

def get_cache_manager_instance() -> EnhancedCacheManager:
    """获取缓存管理器实例（延迟初始化）"""
    global _cache_manager_instance
    if _cache_manager_instance is None:
        _cache_manager_instance = EnhancedCacheManager()
    return _cache_manager_instance

def get_forum_cache_instance() -> ForumCacheManager:
    """获取论坛缓存管理器实例（延迟初始化）"""
    global _forum_cache_instance
    if _forum_cache_instance is None:
        _forum_cache_instance = ForumCacheManager(get_cache_manager_instance())
    return _forum_cache_instance

# 兼容性属性访问
class CacheManagerProxy:
    """缓存管理器代理类"""
    def __getattr__(self, name):
        return getattr(get_cache_manager_instance(), name)
    
    def __getitem__(self, key):
        return get_cache_manager_instance()[key]
    
    def __setitem__(self, key, value):
        get_cache_manager_instance()[key] = value

class ForumCacheProxy:
    """论坛缓存管理器代理类"""
    def __getattr__(self, name):
        return getattr(get_forum_cache_instance(), name)

# 向后兼容的全局实例
cache_manager = CacheManagerProxy()
forum_cache = ForumCacheProxy()

# 向后兼容的函数
def invalidate_cache_pattern(pattern: str, cache_manager=None):
    """
    根据模式失效缓存
    这是一个兼容性函数，实际上调用缓存管理器的删除功能
    """
    try:
        cm = cache_manager or get_cache_manager_instance()
        # 简单实现：如果是具体的key就直接删除
        if '*' not in pattern and '?' not in pattern:
            return cm.delete(pattern)
        else:
            # 对于模式匹配，暂时返回 True
            # 实际生产环境中应该实现真正的模式匹配删除
            logger.warning(f"Pattern cache invalidation not fully implemented for: {pattern}")
            return True
    except Exception as e:
        logger.error(f"Cache pattern invalidation failed: {e}")
        return False
