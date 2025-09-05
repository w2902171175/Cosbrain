# project/utils/async_cache/__init__.py
"""
异步缓存模块
包含Redis缓存、LLM缓存等功能
"""

# 原有缓存服务
from .cache import ChatRoomCache
from .cache_manager import *
from .async_tasks import *

# LLM 缓存服务
from .llm_cache_service import (
    get_llm_cache_service,
    cache_llm_config,
    get_llm_config,
    cache_conversation,
    get_conversation,
    LLMConfigCacheService
)

# MCP 缓存服务
from .mcp_cache_manager import mcp_cache_manager, McpCacheManager

from .llm_distributed_cache import (
    get_llm_cache,
    llm_cache,
    LLMDistributedCache,
    LLMCacheConfig,
    DistributedLock
)

# 添加到 __all__ 列表
__all__ = [
    # 原有缓存
    'ChatRoomCache',
    
    # LLM 缓存服务
    'get_llm_cache_service',
    'cache_llm_config',
    'get_llm_config', 
    'cache_conversation',
    'get_conversation',
    'LLMConfigCacheService',
    
    # 分布式缓存
    'get_llm_cache',
    'llm_cache',
    'LLMDistributedCache',
    'LLMCacheConfig',
    'DistributedLock',
]

__all__ = [
    # 缓存相关
    "ChatRoomCache",
    
    # 异步任务
    "TaskManager",
    "TaskStatus", 
    "TaskPriority",
    "Task",
    "AsyncTaskExecutor",
    
    # MCP 缓存
    "mcp_cache_manager",
    "McpCacheManager",
]
