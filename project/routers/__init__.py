# project/routers/__init__.py
"""
路由模块总导入
这个文件负责从各个子包导入路由器，以便在main.py中统一导入
"""

# 从各个子包导入路由器
from .admin import router as admin
from .ai import router as ai
from .achievement_points import router as achievement_points
from .auth import router as auth
from .chatrooms import router as chatrooms
from .course_notes import router as course_notes
from .courses import router as courses
from .dashboard import router as dashboard
from .forum import router as forum
from .knowledge import router as knowledge
from .llm import router as llm
from .mcp import router as mcp
from .projects import router as projects
from .quick_notes import router as quick_notes
from .recommend import router as recommend
from .search_engine import router as search_engine
from .tts import router as tts

# 导出所有路由器
__all__ = [
    "admin", "ai", "achievement_points", "auth", "chatrooms", 
    "course_notes", "courses", "dashboard", "forum", "knowledge",
    "llm", "mcp", "projects", "quick_notes", "recommend", 
    "search_engine", "tts"
]
