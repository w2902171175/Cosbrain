# project/utils/optimization/__init__.py
"""
性能优化工具模块
包含路由优化、生产环境配置、性能监控等功能
"""

from .router_optimization import *
from .config_router_base import *
from .production_utils import *

# 创建全局 cache_manager 实例
from .production_utils import get_cache_manager
cache_manager = get_cache_manager()

__all__ = [
    # 路由优化
    "OptimizedRouter",
    "RouterOptimizer",
    
    # 生产环境工具
    "ProductionConfig",
    "get_config",
    "get_cache_manager",
    "cache_manager",  # 全局实例
    "cache_set",
    "cache_get", 
    "cache_delete",
    "cache_delete_pattern",
    
    # 路由基础配置
    "BaseRouter",
    "RouterConfig",
]
