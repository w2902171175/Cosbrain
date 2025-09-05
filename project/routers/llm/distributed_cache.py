# project/routers/llm/distributed_cache.py
"""
LLM配置分布式缓存管理器
使用Redis替代本地LRU缓存，支持多实例共享缓存
"""
import json
import logging
import hashlib
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
import redis
from functools import wraps
import os
import time
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class LLMCacheConfig:
    """LLM缓存配置"""
    
    def __init__(self):
        # Redis连接配置
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_password = os.getenv("REDIS_PASSWORD")
        self.redis_db = int(os.getenv("LLM_CACHE_REDIS_DB", "1"))  # 使用独立的DB
        
        # 缓存过期策略
        self.default_expire = int(os.getenv("LLM_CACHE_DEFAULT_EXPIRE", "3600"))  # 1小时
        self.config_expire = int(os.getenv("LLM_CACHE_CONFIG_EXPIRE", "1800"))   # 30分钟
        self.provider_expire = int(os.getenv("LLM_CACHE_PROVIDER_EXPIRE", "7200"))  # 2小时
        self.model_list_expire = int(os.getenv("LLM_CACHE_MODEL_LIST_EXPIRE", "3600"))  # 1小时
        
        # 缓存键前缀
        self.key_prefix = os.getenv("LLM_CACHE_KEY_PREFIX", "llm:cache:")
        self.lock_prefix = os.getenv("LLM_CACHE_LOCK_PREFIX", "llm:lock:")
        
        # 性能配置
        self.enable_compression = os.getenv("LLM_CACHE_ENABLE_COMPRESSION", "true").lower() == "true"
        self.compression_threshold = int(os.getenv("LLM_CACHE_COMPRESSION_THRESHOLD", "1024"))
        self.max_memory_fallback_size = int(os.getenv("LLM_CACHE_MAX_MEMORY_SIZE", "100"))
        
        # 监控配置
        self.enable_metrics = os.getenv("LLM_CACHE_ENABLE_METRICS", "true").lower() == "true"
        self.health_check_interval = int(os.getenv("LLM_CACHE_HEALTH_CHECK_INTERVAL", "60"))


class LLMCacheMetrics:
    """LLM缓存监控指标"""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.errors = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
    
    def record_hit(self):
        with self.lock:
            self.hits += 1
    
    def record_miss(self):
        with self.lock:
            self.misses += 1
    
    def record_set(self):
        with self.lock:
            self.sets += 1
    
    def record_delete(self):
        with self.lock:
            self.deletes += 1
    
    def record_error(self):
        with self.lock:
            self.errors += 1
    
    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            uptime = time.time() - self.start_time
            
            return {
                "hits": self.hits,
                "misses": self.misses,
                "sets": self.sets,
                "deletes": self.deletes,
                "errors": self.errors,
                "hit_rate": round(hit_rate, 2),
                "total_requests": total_requests,
                "uptime_seconds": round(uptime, 2)
            }


class DistributedLock:
    """分布式锁实现"""
    
    def __init__(self, redis_client: redis.Redis, key: str, timeout: int = 10):
        self.redis_client = redis_client
        self.key = key
        self.timeout = timeout
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
            time.sleep(0.001)  # 1ms
        
        return False
    
    def release(self) -> bool:
        """释放锁"""
        if not self.identifier:
            return False
        
        # Lua脚本确保原子性
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = self.redis_client.eval(lua_script, 1, self.key, self.identifier)
            return bool(result)
        except Exception as e:
            logger.error(f"释放分布式锁失败: {e}")
            return False


class LLMDistributedCache:
    """LLM分布式缓存管理器"""
    
    def __init__(self, config: Optional[LLMCacheConfig] = None):
        self.config = config or LLMCacheConfig()
        self.redis_client = None
        self.memory_fallback = {}  # 内存后备缓存
        self.memory_lock = threading.RLock()
        self.metrics = LLMCacheMetrics()
        self.is_healthy = False
        
        self._init_redis()
        self._start_health_monitor()
    
    def _init_redis(self):
        """初始化Redis连接"""
        try:
            # 构建Redis URL，指定特定的数据库
            redis_url = self.config.redis_url
            if redis_url.count('/') >= 3:
                # 替换数据库编号
                base_url = '/'.join(redis_url.split('/')[:-1])
                redis_url = f"{base_url}/{self.config.redis_db}"
            else:
                redis_url = f"{redis_url}/{self.config.redis_db}"
            
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                password=self.config.redis_password,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            # 测试连接
            self.redis_client.ping()
            self.is_healthy = True
            logger.info(f"LLM Redis缓存连接成功 (DB: {self.config.redis_db})")
            
        except Exception as e:
            logger.warning(f"LLM Redis缓存连接失败，将使用内存后备缓存: {e}")
            self.redis_client = None
            self.is_healthy = False
    
    def _start_health_monitor(self):
        """启动健康监控"""
        def health_check_worker():
            while True:
                try:
                    time.sleep(self.config.health_check_interval)
                    if self.redis_client:
                        self.redis_client.ping()
                        self.is_healthy = True
                    else:
                        self._init_redis()
                except Exception as e:
                    self.is_healthy = False
                    logger.warning(f"LLM Redis健康检查失败: {e}")
        
        monitor_thread = threading.Thread(target=health_check_worker, daemon=True)
        monitor_thread.start()
    
    def _make_key(self, key: str) -> str:
        """生成缓存键"""
        return f"{self.config.key_prefix}{key}"
    
    def _compress_data(self, data: str) -> str:
        """压缩数据"""
        if not self.config.enable_compression:
            return data
        
        if len(data) < self.config.compression_threshold:
            return data
        
        try:
            import zlib
            compressed = zlib.compress(data.encode('utf-8'))
            return f"compressed:{compressed.hex()}"
        except Exception as e:
            logger.warning(f"数据压缩失败: {e}")
            return data
    
    def _decompress_data(self, data: str) -> str:
        """解压缩数据"""
        if not data.startswith("compressed:"):
            return data
        
        try:
            import zlib
            compressed_hex = data[11:]  # 移除"compressed:"前缀
            compressed_bytes = bytes.fromhex(compressed_hex)
            return zlib.decompress(compressed_bytes).decode('utf-8')
        except Exception as e:
            logger.warning(f"数据解压缩失败: {e}")
            return data
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """设置缓存"""
        if expire is None:
            expire = self.config.default_expire
        
        try:
            # 序列化数据
            serialized = json.dumps(value, default=str, ensure_ascii=False)
            compressed = self._compress_data(serialized)
            cache_key = self._make_key(key)
            
            success = False
            
            # 优先使用Redis
            if self.redis_client and self.is_healthy:
                try:
                    success = self.redis_client.setex(cache_key, expire, compressed)
                except Exception as e:
                    logger.warning(f"Redis设置缓存失败，使用内存后备: {e}")
                    self.is_healthy = False
            
            # 内存后备缓存
            if not success:
                with self.memory_lock:
                    # 限制内存缓存大小
                    if len(self.memory_fallback) >= self.config.max_memory_fallback_size:
                        # 删除最老的条目
                        oldest_key = min(self.memory_fallback.keys(), 
                                       key=lambda k: self.memory_fallback[k].get('created', 0))
                        del self.memory_fallback[oldest_key]
                    
                    self.memory_fallback[cache_key] = {
                        'value': compressed,
                        'expire_time': datetime.now() + timedelta(seconds=expire),
                        'created': time.time()
                    }
                success = True
            
            if self.config.enable_metrics:
                self.metrics.record_set()
            
            return success
            
        except Exception as e:
            logger.error(f"设置LLM缓存失败 {key}: {e}")
            if self.config.enable_metrics:
                self.metrics.record_error()
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            cache_key = self._make_key(key)
            value = None
            
            # 优先从Redis获取
            if self.redis_client and self.is_healthy:
                try:
                    value = self.redis_client.get(cache_key)
                except Exception as e:
                    logger.warning(f"Redis获取缓存失败，尝试内存后备: {e}")
                    self.is_healthy = False
            
            # 内存后备缓存
            if value is None:
                with self.memory_lock:
                    cache_item = self.memory_fallback.get(cache_key)
                    if cache_item:
                        # 检查是否过期
                        if cache_item['expire_time'] > datetime.now():
                            value = cache_item['value']
                        else:
                            # 清理过期数据
                            del self.memory_fallback[cache_key]
            
            if value is not None:
                # 解压缩并反序列化
                decompressed = self._decompress_data(value)
                result = json.loads(decompressed)
                
                if self.config.enable_metrics:
                    self.metrics.record_hit()
                
                return result
            else:
                if self.config.enable_metrics:
                    self.metrics.record_miss()
                
                return None
                
        except Exception as e:
            logger.error(f"获取LLM缓存失败 {key}: {e}")
            if self.config.enable_metrics:
                self.metrics.record_error()
            return None
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            cache_key = self._make_key(key)
            success = True
            
            # 从Redis删除
            if self.redis_client and self.is_healthy:
                try:
                    self.redis_client.delete(cache_key)
                except Exception as e:
                    logger.warning(f"Redis删除缓存失败: {e}")
                    success = False
            
            # 从内存后备删除
            with self.memory_lock:
                self.memory_fallback.pop(cache_key, None)
            
            if self.config.enable_metrics:
                self.metrics.record_delete()
            
            return success
            
        except Exception as e:
            logger.error(f"删除LLM缓存失败 {key}: {e}")
            if self.config.enable_metrics:
                self.metrics.record_error()
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """按模式删除缓存"""
        try:
            count = 0
            full_pattern = self._make_key(pattern)
            
            # Redis模式删除
            if self.redis_client and self.is_healthy:
                try:
                    keys = self.redis_client.keys(full_pattern)
                    if keys:
                        count = self.redis_client.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis模式删除失败: {e}")
            
            # 内存后备模式删除
            with self.memory_lock:
                import fnmatch
                keys_to_delete = [k for k in self.memory_fallback.keys() 
                                if fnmatch.fnmatch(k, full_pattern)]
                for key in keys_to_delete:
                    del self.memory_fallback[key]
                    count += 1
            
            return count
            
        except Exception as e:
            logger.error(f"模式删除LLM缓存失败 {pattern}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            cache_key = self._make_key(key)
            
            # 检查Redis
            if self.redis_client and self.is_healthy:
                try:
                    return bool(self.redis_client.exists(cache_key))
                except Exception as e:
                    logger.warning(f"Redis检查存在性失败: {e}")
            
            # 检查内存后备
            with self.memory_lock:
                cache_item = self.memory_fallback.get(cache_key)
                if cache_item:
                    if cache_item['expire_time'] > datetime.now():
                        return True
                    else:
                        # 清理过期数据
                        del self.memory_fallback[cache_key]
            
            return False
            
        except Exception as e:
            logger.error(f"检查LLM缓存存在性失败 {key}: {e}")
            return False
    
    def get_lock(self, key: str, timeout: int = 10) -> DistributedLock:
        """获取分布式锁"""
        lock_key = f"{self.config.lock_prefix}{key}"
        if self.redis_client and self.is_healthy:
            return DistributedLock(self.redis_client, lock_key, timeout)
        else:
            # 使用线程锁作为后备
            return threading.Lock()
    
    def clear_all(self) -> bool:
        """清空所有LLM缓存"""
        try:
            count = 0
            
            # 清空Redis中的LLM缓存
            if self.redis_client and self.is_healthy:
                try:
                    pattern = f"{self.config.key_prefix}*"
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        count = self.redis_client.delete(*keys)
                        logger.info(f"清空Redis中 {count} 个LLM缓存条目")
                except Exception as e:
                    logger.warning(f"清空Redis LLM缓存失败: {e}")
            
            # 清空内存后备缓存
            with self.memory_lock:
                memory_count = len(self.memory_fallback)
                self.memory_fallback.clear()
                logger.info(f"清空内存后备中 {memory_count} 个LLM缓存条目")
            
            return True
            
        except Exception as e:
            logger.error(f"清空LLM缓存失败: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = self.metrics.get_stats()
        
        # Redis信息
        redis_info = {}
        if self.redis_client and self.is_healthy:
            try:
                info = self.redis_client.info()
                redis_info = {
                    "version": info.get("redis_version"),
                    "used_memory": info.get("used_memory_human"),
                    "connected_clients": info.get("connected_clients"),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0)
                }
            except Exception as e:
                redis_info["error"] = str(e)
        
        stats.update({
            "backend": "Redis + Memory Fallback" if self.is_healthy else "Memory Fallback Only",
            "redis_healthy": self.is_healthy,
            "redis_info": redis_info,
            "memory_fallback_size": len(self.memory_fallback),
            "max_memory_fallback_size": self.config.max_memory_fallback_size,
            "config": {
                "default_expire": self.config.default_expire,
                "config_expire": self.config.config_expire,
                "provider_expire": self.config.provider_expire,
                "model_list_expire": self.config.model_list_expire,
                "compression_enabled": self.config.enable_compression,
                "compression_threshold": self.config.compression_threshold
            }
        })
        
        return stats
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health = {
            "redis_available": False,
            "memory_fallback_available": True,
            "overall_status": "degraded"
        }
        
        try:
            if self.redis_client:
                self.redis_client.ping()
                health["redis_available"] = True
                health["overall_status"] = "healthy"
        except Exception as e:
            health["redis_error"] = str(e)
        
        health.update({
            "cache_stats": self.get_stats(),
            "timestamp": datetime.now().isoformat()
        })
        
        return health


# 全局实例
_llm_cache = None
_cache_lock = threading.Lock()

def get_llm_cache() -> LLMDistributedCache:
    """获取LLM缓存实例（单例模式）"""
    global _llm_cache
    
    if _llm_cache is None:
        with _cache_lock:
            if _llm_cache is None:
                _llm_cache = LLMDistributedCache()
    
    return _llm_cache


# 缓存装饰器
def llm_cache(expire: Optional[int] = None, key_func: Optional[callable] = None):
    """LLM缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认键生成策略
                func_name = func.__name__
                args_str = str(args) + str(sorted(kwargs.items()))
                cache_key = f"func:{func_name}:{hashlib.md5(args_str.encode()).hexdigest()}"
            
            cache = get_llm_cache()
            
            # 尝试从缓存获取
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache.set(cache_key, result, expire)
            
            return result
        
        return wrapper
    return decorator
