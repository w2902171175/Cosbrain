# project/routers/collections/__init__.py
"""
收藏系统路由模块

这个包包含了完整的收藏管理系统，采用文件夹为中心的架构设计。

模块说明：
- collections.py: 核心收藏系统，提供文件夹管理和基础收藏功能
- collections_advanced.py: 高级功能，包括批量操作、统计分析、导入导出等

使用方式：
    from routers.collections import collections_router, collections_advanced_router
"""

from .collections import router as collections_router
from .collections_advanced import router as collections_advanced_router

# 导出路由器
__all__ = ['collections_router', 'collections_advanced_router']
