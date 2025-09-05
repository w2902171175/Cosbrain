# project/routers/llm/__init__.py
"""
大语言模型路由包
包含路由处理、分布式缓存和高级监控系统
"""

from .llm import router

# 分布式缓存功能
from .distributed_cache import get_llm_cache, LLMDistributedCache, LLMCacheConfig
from .cache_service import get_llm_cache_service, LLMConfigCacheService

# 高级监控系统
from .prometheus_monitor import get_prometheus_monitor, start_prometheus_monitoring, stop_prometheus_monitoring
from .alert_manager import get_alert_manager, start_alert_monitoring, stop_alert_monitoring
from .baseline_comparator import get_baseline_comparator

# 缓存装饰器
from .cache_service import cache_llm_config, cache_provider_config, cache_model_list

# 可以通过以下方式导入：
# 
# 基础缓存功能:
# from project.routers.llm import get_llm_cache, get_llm_cache_service
#
# 高级监控功能:
# from project.routers.llm import get_prometheus_monitor, get_alert_manager, get_baseline_comparator
# from project.routers.llm import start_prometheus_monitoring, start_alert_monitoring
#
# 装饰器:
# from project.routers.llm import cache_llm_config, cache_provider_config

__all__ = [
    "router",
    # 缓存相关
    "get_llm_cache",
    "LLMDistributedCache", 
    "LLMCacheConfig",
    "get_llm_cache_service",
    "LLMConfigCacheService",
    # 高级监控相关
    "get_prometheus_monitor",
    "start_prometheus_monitoring",
    "stop_prometheus_monitoring",
    "get_alert_manager",
    "start_alert_monitoring", 
    "stop_alert_monitoring",
    "get_baseline_comparator",
    # 装饰器
    "cache_llm_config",
    "cache_provider_config", 
    "cache_model_list"
]
