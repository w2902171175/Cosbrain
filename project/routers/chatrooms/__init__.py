# project/routers/chatrooms/__init__.py
"""
聊天室路由包 - 重构后的模块化结构
"""

from fastapi import APIRouter
from . import room_management, member_management, message_handling, file_upload, chatrooms_admin
from project.services import websocket_service

# 创建新的主路由器
router = APIRouter()

# 包含新的模块化路由
router.include_router(room_management.router, tags=["聊天室管理"])
router.include_router(member_management.router, tags=["成员管理"])
router.include_router(message_handling.router, tags=["消息处理"])
router.include_router(file_upload.router, tags=["文件上传"])
router.include_router(websocket_service.router, tags=["WebSocket"])
router.include_router(chatrooms_admin.router, tags=["管理员操作"])

# 模块加载日志
import logging
logger = logging.getLogger(__name__)
logger.info("💬 Chatrooms Module - 聊天室模块已加载")

__all__ = ["router"]
