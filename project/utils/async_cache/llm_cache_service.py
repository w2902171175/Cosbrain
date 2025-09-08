# project/utils/async_cache/llm_cache_service.py
"""
LLM配置缓存服务
专门处理LLM配置相关的缓存操作
"""
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib

from .llm_distributed_cache import get_llm_cache, llm_cache, LLMCacheConfig

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
    
    def get_model_info(self, provider: str, model: str) -> Optional[Dict[str, Any]]:
        """获取模型详细信息"""
        cache_key = f"model_info:{provider}:{model}"
        return self.cache.get(cache_key)
    
    def set_model_info(self, provider: str, model: str, info: Dict[str, Any]) -> bool:
        """缓存模型详细信息"""
        cache_key = f"model_info:{provider}:{model}"
        return self.cache.set(cache_key, info, self.config.model_list_expire)
    
    # ===== 对话历史缓存 =====
    
    def get_conversation_history(self, user_id: str, conversation_id: str) -> Optional[List[Dict[str, Any]]]:
        """获取对话历史"""
        cache_key = f"conversation:{user_id}:{conversation_id}"
        return self.cache.get(cache_key)
    
    def set_conversation_history(self, user_id: str, conversation_id: str, 
                               history: List[Dict[str, Any]]) -> bool:
        """缓存对话历史"""
        cache_key = f"conversation:{user_id}:{conversation_id}"
        return self.cache.set(cache_key, history, self.config.default_expire)
    
    def append_conversation_message(self, user_id: str, conversation_id: str, 
                                  message: Dict[str, Any]) -> bool:
        """向对话历史追加消息"""
        cache_key = f"conversation:{user_id}:{conversation_id}"
        history = self.cache.get(cache_key) or []
        history.append(message)
        return self.cache.set(cache_key, history, self.config.default_expire)
    
    # ===== 请求结果缓存 =====
    
    def _generate_request_hash(self, provider: str, model: str, messages: List[Dict[str, Any]], 
                              **kwargs) -> str:
        """生成请求的哈希值用作缓存键"""
        request_data = {
            'provider': provider,
            'model': model,
            'messages': messages,
            **kwargs
        }
        request_str = json.dumps(request_data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(request_str.encode()).hexdigest()
    
    def get_llm_response(self, provider: str, model: str, messages: List[Dict[str, Any]], 
                        **kwargs) -> Optional[Dict[str, Any]]:
        """获取LLM响应缓存"""
        request_hash = self._generate_request_hash(provider, model, messages, **kwargs)
        cache_key = f"llm_response:{request_hash}"
        return self.cache.get(cache_key)
    
    def set_llm_response(self, provider: str, model: str, messages: List[Dict[str, Any]], 
                        response: Dict[str, Any], **kwargs) -> bool:
        """缓存LLM响应"""
        request_hash = self._generate_request_hash(provider, model, messages, **kwargs)
        cache_key = f"llm_response:{request_hash}"
        return self.cache.set(cache_key, response, self.config.default_expire)
    
    # ===== 性能统计缓存 =====
    
    def get_performance_stats(self, provider: str, model: str, 
                            period: str = "hour") -> Optional[Dict[str, Any]]:
        """获取性能统计"""
        cache_key = f"performance:{provider}:{model}:{period}"
        return self.cache.get(cache_key)
    
    def set_performance_stats(self, provider: str, model: str, period: str,
                            stats: Dict[str, Any]) -> bool:
        """缓存性能统计"""
        cache_key = f"performance:{provider}:{model}:{period}"
        return self.cache.set(cache_key, stats, 300)  # 5分钟过期
    
    def increment_usage_counter(self, provider: str, model: str) -> int:
        """增加使用计数器"""
        cache_key = f"usage_counter:{provider}:{model}"
        current_count = self.cache.get(cache_key) or 0
        new_count = current_count + 1
        self.cache.set(cache_key, new_count, 86400)  # 24小时过期
        return new_count
    
    # ===== 错误追踪缓存 =====
    
    def record_error(self, provider: str, model: str, error_type: str, 
                    error_msg: str) -> bool:
        """记录错误到缓存"""
        cache_key = f"errors:{provider}:{model}"
        errors = self.cache.get(cache_key) or []
        error_record = {
            'type': error_type,
            'message': error_msg,
            'timestamp': datetime.now().isoformat()
        }
        errors.append(error_record)
        # 只保留最近50条错误记录
        errors = errors[-50:]
        return self.cache.set(cache_key, errors, 3600)  # 1小时过期
    
    def get_recent_errors(self, provider: str = None, model: str = None) -> List[Dict[str, Any]]:
        """获取最近的错误记录"""
        if provider and model:
            cache_key = f"errors:{provider}:{model}"
            return self.cache.get(cache_key) or []
        else:
            # 获取所有错误记录（这个操作比较昂贵，谨慎使用）
            all_errors = []
            # 由于Redis的键扫描成本较高，这里简化实现
            return all_errors
    
    # ===== 工具方法 =====
    
    def clear_user_cache(self, user_id: str) -> bool:
        """清除特定用户的缓存"""
        try:
            # 获取所有相关的键
            patterns = [
                f"conversation:{user_id}:*",
                f"user_preferences:{user_id}",
                f"user_stats:{user_id}"
            ]
            
            for pattern in patterns:
                keys = self.cache.scan_keys(pattern)
                for key in keys:
                    self.cache.delete(key)
            
            return True
        except Exception as e:
            logger.error(f"清除用户缓存失败: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            return self.cache.get_stats()
        except Exception as e:
            logger.error(f"获取缓存统计失败: {e}")
            return {}
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            test_key = "health_check"
            test_value = "ok"
            self.cache.set(test_key, test_value, 10)
            result = self.cache.get(test_key)
            self.cache.delete(test_key)
            return result == test_value
        except Exception as e:
            logger.error(f"缓存健康检查失败: {e}")
            return False


# 全局缓存服务实例
_llm_cache_service = None

def get_llm_cache_service() -> LLMConfigCacheService:
    """获取LLM缓存服务实例"""
    global _llm_cache_service
    if _llm_cache_service is None:
        _llm_cache_service = LLMConfigCacheService()
    return _llm_cache_service

# 便捷的模块级函数
def cache_llm_config(provider: str, config: Dict[str, Any]) -> bool:
    """便捷函数：缓存LLM配置"""
    return get_llm_cache_service().set_provider_config(provider, config)

def get_llm_config(provider: str) -> Optional[Dict[str, Any]]:
    """便捷函数：获取LLM配置"""
    return get_llm_cache_service().get_provider_config(provider)

def cache_conversation(user_id: str, conversation_id: str, 
                      history: List[Dict[str, Any]]) -> bool:
    """便捷函数：缓存对话历史"""
    return get_llm_cache_service().set_conversation_history(user_id, conversation_id, history)

def get_conversation(user_id: str, conversation_id: str) -> Optional[List[Dict[str, Any]]]:
    """便捷函数：获取对话历史"""
    return get_llm_cache_service().get_conversation_history(user_id, conversation_id)

def cache_provider_config(provider: str, config: Dict[str, Any]) -> bool:
    """便捷函数：缓存提供商配置（与cache_llm_config相同）"""
    return get_llm_cache_service().set_provider_config(provider, config)

def cache_model_list(provider: str, models: List[str]) -> bool:
    """便捷函数：缓存模型列表"""
    cache_key = f"llm:models:{provider}"
    return get_llm_cache_service().cache.set(cache_key, models, expire=3600)
