# project/routers/knowledge/__init__.py
"""
知识库路由包 - 提供知识库相关的API端点

重构后的架构：
- knowledge.py - 基础知识库API
- advanced_knowledge.py - 增强功能API（分布式、安全、监控、推荐）
- 业务逻辑已移至 project/services/ 层
"""

import logging

logger = logging.getLogger(__name__)

# 导入主要的知识库路由
from .knowledge import router

# 导入增强功能API（已重构为服务层架构）
try:
    from .advanced_knowledge import router as enhanced_router
    logger.info("📈 增强功能API已启用 - 支持分布式处理、安全扫描、监控和推荐功能")
except ImportError as e:
    logger.debug(f"增强功能API未启用: {e}")
    enhanced_router = None

logger.info("📚 知识库路由包已加载完成")

__all__ = ["router", "enhanced_router"]
