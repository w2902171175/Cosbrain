# project/routers/mcp/cache_manager.py
"""
MCP 连接检查缓存管理器
"""
import time
import hashlib
from typing import Optional, Dict, Any
from dataclasses import dataclass
import threading
import project.schemas as schemas


@dataclass
class CacheEntry:
    """缓存条目"""
    value: schemas.McpStatusResponse
    timestamp: float
    ttl: int


class McpCacheManager:
    """MCP 连接检查缓存管理器"""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
    
    def _generate_cache_key(self, base_url: str, headers: Dict[str, str]) -> str:
        """生成缓存键"""
        # 排除敏感信息，只使用 URL 和非敏感头信息
        cache_data = {
            "base_url": base_url,
            "has_auth": "Authorization" in headers,
            "user_agent": headers.get("User-Agent", "")
        }
        cache_str = str(sorted(cache_data.items()))
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def get(self, base_url: str, headers: Dict[str, str], ttl: int = 300) -> Optional[schemas.McpStatusResponse]:
        """从缓存获取连接检查结果"""
        cache_key = self._generate_cache_key(base_url, headers)
        
        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            
            # 检查是否过期
            if time.time() - entry.timestamp > entry.ttl:
                del self._cache[cache_key]
                return None
            
            return entry.value
    
    def set(self, base_url: str, headers: Dict[str, str], result: schemas.McpStatusResponse, ttl: int = 300):
        """将连接检查结果存入缓存"""
        cache_key = self._generate_cache_key(base_url, headers)
        
        with self._lock:
            self._cache[cache_key] = CacheEntry(
                value=result,
                timestamp=time.time(),
                ttl=ttl
            )
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self):
        """清理过期的缓存条目"""
        current_time = time.time()
        expired_keys = []
        
        with self._lock:
            for key, entry in self._cache.items():
                if current_time - entry.timestamp > entry.ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_entries = len(self._cache)
            current_time = time.time()
            expired_count = sum(
                1 for entry in self._cache.values()
                if current_time - entry.timestamp > entry.ttl
            )
            
            return {
                "total_entries": total_entries,
                "active_entries": total_entries - expired_count,
                "expired_entries": expired_count
            }


# 全局缓存管理器实例
cache_manager = McpCacheManager()
