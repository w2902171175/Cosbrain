# project/routers/ai/__init__.py
"""
企业级AI路由包
整合核心AI功能、管理和监控模块
"""

# 导入新的企业级路由模块
from .ai_router import router as ai_router
from .ai_admin import router as ai_admin_router  
from .ai_monitoring import router as ai_monitoring_router

# 废弃原有路由，仅保留兼容性
# from .ai import router as legacy_router

# 企业级路由列表
enterprise_routers = [ai_router, ai_admin_router, ai_monitoring_router]

# 导出所有路由器
__all__ = [
    "ai_router",           # 核心AI功能路由（新的主路由）
    "ai_admin_router",     # AI管理路由
    "ai_monitoring_router", # AI监控路由
    "enterprise_routers"   # 企业级路由列表
]
