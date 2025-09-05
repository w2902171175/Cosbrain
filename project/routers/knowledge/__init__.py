# project/routers/knowledge/__init__.py
"""
现代化知识库路由包 - 支持多媒体内容管理和增强功能
提供分布式处理、安全扫描、智能推荐、监控告警等高级功能
所有配置统一在主.env文件中管理
"""

import os
import logging

logger = logging.getLogger(__name__)

from .knowledge import router

# 尝试导入增强功能模块（可选）
_enhanced_modules = {}

try:
    from .distributed_processing import DistributedTaskProcessor
    _enhanced_modules['distributed_processing'] = DistributedTaskProcessor
except ImportError as e:
    logger.debug(f"分布式处理模块未启用: {e}")

try:
    from .security_scanner import ComprehensiveSecurityScanner
    _enhanced_modules['security_scanner'] = ComprehensiveSecurityScanner
except ImportError as e:
    logger.debug(f"安全扫描模块未启用: {e}")

try:
    from .intelligent_recommendation import RecommendationEngine
    _enhanced_modules['intelligent_recommendation'] = RecommendationEngine
except ImportError as e:
    logger.debug(f"智能推荐模块未启用: {e}")

try:
    from .monitoring_alerting import SystemMonitor, AlertManager, HealthChecker
    _enhanced_modules['monitoring_alerting'] = {
        'SystemMonitor': SystemMonitor,
        'AlertManager': AlertManager,
        'HealthChecker': HealthChecker
    }
except ImportError as e:
    logger.debug(f"监控告警模块未启用: {e}")

# 记录启用的增强功能
enabled_features = list(_enhanced_modules.keys())
if enabled_features:
    logger.info(f"🔧 Knowledge Features - 增强功能已启用: {', '.join(enabled_features)}")
else:
    logger.info("📚 Knowledge Base - 基础功能已加载")

__all__ = ["router", "_enhanced_modules"]
