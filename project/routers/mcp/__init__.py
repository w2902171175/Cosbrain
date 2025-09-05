# project/routers/mcp/__init__.py
"""
MCP 路由包

包含以下模块：
- mcp: 主路由定义

注意：配置、缓存管理和性能监控模块已移动到更合适的位置：
- 配置: project.config.mcp_config
- 缓存管理: project.utils.async_cache.mcp_cache_manager  
- 性能监控: project.utils.monitoring.mcp_performance_monitor
"""

from .mcp import router

# 为了向后兼容，从新位置导入并重新导出
from project.config.mcp_config import mcp_config, get_provider_headers
from project.utils.async_cache.mcp_cache_manager import mcp_cache_manager as cache_manager
from project.utils.monitoring.mcp_performance_monitor import mcp_performance_monitor as performance_monitor

__all__ = [
    "router",
    "mcp_config", 
    "get_provider_headers",
    "cache_manager",
    "performance_monitor"
]
