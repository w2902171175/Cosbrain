# project/routers/collections/__init__.py
"""
新一代收藏系统路由模块

采用文件夹为核心的架构设计，提供统一的收藏管理体验。

核心特性：
1. 文件夹是收藏系统的核心实体，所有收藏内容都围绕文件夹展开
2. 支持多级文件夹嵌套，提供类似文件系统的体验
3. 统一的收藏接口，无论是内部资源还是外部链接
4. 智能的默认分类和自动标签
5. 高效的搜索和过滤功能
6. 支持聊天室内容收藏：文件、图片、视频、语音
7. 支持论坛内容收藏：附件、论坛话题

使用方式：
    from project.routers.collections import router
"""

from .collections import router

__all__ = [
    "router"
]
