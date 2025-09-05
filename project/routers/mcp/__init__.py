# project/routers/mcp/__init__.py
"""
MCP 路由包

包含以下模块：
- mcp: 主路由定义
- config: 配置管理
- cache_manager: 缓存管理
- performance_monitor: 性能监控
"""

from .mcp import router
from .config import mcp_config, get_provider_headers
from .cache_manager import cache_manager
from .performance_monitor import performance_monitor

__all__ = [
    "router",
    "mcp_config", 
    "get_provider_headers",
    "cache_manager",
    "performance_monitor"
]
