# project/routers/llm/cache_service.py
"""
LLM配置缓存服务
专门处理LLM配置相关的缓存操作
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib

from .distributed_cache import get_llm_cache, llm_cache, LLMCacheConfig

logger = logging.getLogger(__name__)

class LLMConfigCacheService:
    """LLM配置缓存服务"""
    
    def __init__(self):
        self.cache = get_llm_cache()
        self.config = LLMCacheConfig()
    
    # ===== LLM配置相关缓存 =====
    
    def get_llm_configs(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """获取缓存的LLM配置信息"""
        return self.cache.get("llm_configs")
    
    def set_llm_configs(self, configs: Dict[str, Dict[str, Any]]) -> bool:
        """缓存LLM配置信息"""
        return self.cache.set("llm_configs", configs, self.config.config_expire)
    
    def get_provider_config(self, provider: str) -> Optional[Dict[str, Any]]:
        """获取特定服务商的配置"""
        cache_key = f"provider_config:{provider}"
        return self.cache.get(cache_key)
    
    def set_provider_config(self, provider: str, config: Dict[str, Any]) -> bool:
        """缓存特定服务商的配置"""
        cache_key = f"provider_config:{provider}"
        return self.cache.set(cache_key, config, self.config.provider_expire)
    
    def get_model_list(self, provider: str) -> Optional[List[str]]:
        """获取服务商的模型列表"""
        cache_key = f"model_list:{provider}"
        return self.cache.get(cache_key)
    
    def set_model_list(self, provider: str, models: List[str]) -> bool:
        """缓存服务商的模型列表"""
        cache_key = f"model_list:{provider}"
        return self.cache.set(cache_key, models, self.config.model_list_expire)
    
    # ===== 用户配置相关缓存 =====
    
    def get_user_llm_config(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户的LLM配置缓存"""
        cache_key = f"user_config:{user_id}"
        return self.cache.get(cache_key)
    
    def set_user_llm_config(self, user_id: int, config: Dict[str, Any]) -> bool:
        """缓存用户的LLM配置"""
        cache_key = f"user_config:{user_id}"
        return self.cache.set(cache_key, config, self.config.default_expire)
    
    def delete_user_llm_config(self, user_id: int) -> bool:
        """删除用户的LLM配置缓存"""
        cache_key = f"user_config:{user_id}"
        return self.cache.delete(cache_key)
    
    # ===== 推荐配置相关缓存 =====
    
    def get_recommended_config(self, provider: str, user_type: str = "default") -> Optional[Dict[str, Any]]:
        """获取推荐配置缓存"""
        cache_key = f"recommended_config:{provider}:{user_type}"
        return self.cache.get(cache_key)
    
    def set_recommended_config(self, provider: str, config: Dict[str, Any], user_type: str = "default") -> bool:
        """缓存推荐配置"""
        cache_key = f"recommended_config:{provider}:{user_type}"
        return self.cache.set(cache_key, config, self.config.default_expire)
    
    # ===== 性能统计相关缓存 =====
    
    def get_provider_stats(self, provider: str) -> Optional[Dict[str, Any]]:
        """获取服务商性能统计缓存"""
        cache_key = f"provider_stats:{provider}"
        return self.cache.get(cache_key)
    
    def set_provider_stats(self, provider: str, stats: Dict[str, Any]) -> bool:
        """缓存服务商性能统计"""
        cache_key = f"provider_stats:{provider}"
        return self.cache.set(cache_key, stats, 600)  # 10分钟缓存
    
    def get_model_performance(self, provider: str, model: str) -> Optional[Dict[str, Any]]:
        """获取模型性能数据缓存"""
        cache_key = f"model_performance:{provider}:{model}"
        return self.cache.get(cache_key)
    
    def set_model_performance(self, provider: str, model: str, performance: Dict[str, Any]) -> bool:
        """缓存模型性能数据"""
        cache_key = f"model_performance:{provider}:{model}"
        return self.cache.set(cache_key, performance, 900)  # 15分钟缓存
    
    # ===== 批量操作 =====
    
    def clear_provider_cache(self, provider: str) -> int:
        """清除特定服务商的所有缓存"""
        patterns = [
            f"provider_config:{provider}",
            f"model_list:{provider}",
            f"recommended_config:{provider}:*",
            f"provider_stats:{provider}",
            f"model_performance:{provider}:*"
        ]
        
        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.cache.delete_pattern(pattern)
        
        logger.info(f"清除服务商 {provider} 的缓存，共删除 {total_deleted} 个条目")
        return total_deleted
    
    def clear_user_cache(self, user_id: int) -> bool:
        """清除特定用户的缓存"""
        cache_key = f"user_config:{user_id}"
        return self.cache.delete(cache_key)
    
    def clear_all_llm_cache(self) -> bool:
        """清除所有LLM相关缓存"""
        return self.cache.clear_all()
    
    # ===== 缓存预热 =====
    
    def warm_up_cache(self, providers: List[str]) -> Dict[str, bool]:
        """缓存预热"""
        results = {}
        
        for provider in providers:
            try:
                # 这里可以添加预热逻辑，比如提前加载常用配置
                logger.info(f"预热服务商 {provider} 的缓存")
                results[provider] = True
            except Exception as e:
                logger.error(f"预热服务商 {provider} 缓存失败: {e}")
                results[provider] = False
        
        return results
    
    # ===== 缓存验证和修复 =====
    
    def validate_cache_integrity(self) -> Dict[str, Any]:
        """验证缓存完整性"""
        validation_results = {
            "cache_health": self.cache.health_check(),
            "integrity_checks": [],
            "recommendations": []
        }
        
        # 检查核心缓存是否存在
        if not self.cache.exists("llm_configs"):
            validation_results["integrity_checks"].append({
                "check": "llm_configs_exists",
                "status": "warning",
                "message": "核心LLM配置缓存不存在"
            })
            validation_results["recommendations"].append("考虑重新加载LLM配置")
        
        return validation_results
    
    # ===== 统计和监控 =====
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        base_stats = self.cache.get_stats()
        
        # 添加LLM特有的统计信息
        llm_stats = {
            "cache_keys": {
                "llm_configs": self.cache.exists("llm_configs"),
                "total_provider_configs": len([k for k in self._get_all_keys() if k.startswith("provider_config:")]),
                "total_user_configs": len([k for k in self._get_all_keys() if k.startswith("user_config:")]),
                "total_model_lists": len([k for k in self._get_all_keys() if k.startswith("model_list:")])
            }
        }
        
        base_stats.update(llm_stats)
        return base_stats
    
    def _get_all_keys(self) -> List[str]:
        """获取所有缓存键（用于统计）"""
        try:
            if self.cache.redis_client and self.cache.is_healthy:
                pattern = f"{self.cache.config.key_prefix}*"
                return self.cache.redis_client.keys(pattern)
            else:
                # 从内存后备获取
                return list(self.cache.memory_fallback.keys())
        except Exception as e:
            logger.error(f"获取缓存键列表失败: {e}")
            return []
    
    # ===== 缓存优化建议 =====
    
    def get_optimization_suggestions(self) -> List[Dict[str, str]]:
        """获取缓存优化建议"""
        suggestions = []
        stats = self.get_cache_statistics()
        
        # 基于统计数据提供优化建议
        if stats.get("hit_rate", 0) < 70:
            suggestions.append({
                "type": "performance",
                "suggestion": "缓存命中率较低，考虑调整缓存策略或增加缓存时间",
                "priority": "medium"
            })
        
        if not stats.get("redis_healthy", False):
            suggestions.append({
                "type": "infrastructure",
                "suggestion": "Redis连接不健康，检查Redis服务状态",
                "priority": "high"
            })
        
        if stats.get("memory_fallback_size", 0) > self.config.max_memory_fallback_size * 0.8:
            suggestions.append({
                "type": "capacity",
                "suggestion": "内存后备缓存使用率过高，考虑清理或增加容量",
                "priority": "medium"
            })
        
        return suggestions


# 全局缓存服务实例
_cache_service = None

def get_llm_cache_service() -> LLMConfigCacheService:
    """获取LLM缓存服务实例（单例模式）"""
    global _cache_service
    
    if _cache_service is None:
        _cache_service = LLMConfigCacheService()
    
    return _cache_service


# 便捷的装饰器函数
def cache_llm_config(expire: Optional[int] = None):
    """LLM配置缓存装饰器"""
    if expire is None:
        expire = LLMCacheConfig().config_expire
    
    def key_generator(*args, **kwargs):
        # 为LLM配置生成专用的缓存键
        func_name = "llm_config"
        params_hash = hashlib.md5(str(sorted(kwargs.items())).encode()).hexdigest()
        return f"llm_config:{func_name}:{params_hash}"
    
    return llm_cache(expire=expire, key_func=key_generator)


def cache_provider_config(provider: str, expire: Optional[int] = None):
    """服务商配置缓存装饰器"""
    if expire is None:
        expire = LLMCacheConfig().provider_expire
    
    def decorator(func):
        def key_generator(*args, **kwargs):
            return f"provider_config:{provider}"
        
        return llm_cache(expire=expire, key_func=key_generator)(func)
    
    return decorator


def cache_model_list(provider: str, expire: Optional[int] = None):
    """模型列表缓存装饰器"""
    if expire is None:
        expire = LLMCacheConfig().model_list_expire
    
    def decorator(func):
        def key_generator(*args, **kwargs):
            return f"model_list:{provider}"
        
        return llm_cache(expire=expire, key_func=key_generator)(func)
    
    return decorator
