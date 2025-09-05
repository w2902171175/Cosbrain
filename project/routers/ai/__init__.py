# project/routers/ai/__init__.py
"""
企业级AI路由包 - 重构优化版本
模块化设计，提高代码复用性和维护性
"""

# 导入优化后的模块化路由
from .ai_core import router as ai_core_router              # 核心AI功能
# from .conversations import router as conversations_router   # 对话管理  
from .file_upload import router as file_upload_router      # 文件处理
from .ai_admin import router as ai_admin_router            # AI管理
from .ai_monitoring import router as ai_monitoring_router  # AI监控

# 企业级路由列表
enterprise_routers = [
    ai_core_router,         # 核心AI服务
    # conversations_router,   # 对话管理
    file_upload_router,     # 文件上传处理
    ai_admin_router,        # AI管理功能
    ai_monitoring_router    # AI监控功能
]

# 主要路由别名（向后兼容）
ai_router = ai_core_router  # 主要AI路由指向核心功能

# 导出所有路由器
__all__ = [
    "ai_core_router",           # 核心AI功能路由
    "conversations_router",     # 对话管理路由
    "file_upload_router",       # 文件处理路由
    "ai_admin_router",          # AI管理路由
    "ai_monitoring_router",     # AI监控路由
    "enterprise_routers",       # 企业级路由列表
    "ai_router"                 # 主要AI路由（向后兼容）
]

# 版本信息
__version__ = "2.0.0"
__description__ = "企业级AI路由包 - 重构优化版本"
