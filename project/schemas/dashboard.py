# project/schemas/dashboard.py
"""
仪表板相关Schema模块
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from .common import TimestampMixin


# --- Dashboard Schemas ---
class DashboardSummaryResponse(BaseModel):
    """仪表板摘要响应模型"""
    active_projects_count: int
    completed_projects_count: int
    learning_courses_count: int
    completed_courses_count: int
    active_chats_count: int = 0
    unread_messages_count: int = 0
    resume_completion_percentage: float


class DashboardProjectCard(BaseModel):
    """仪表板项目卡片模型"""
    id: int
    title: str
    progress: float = 0.0

    class Config:
        from_attributes = True


class DashboardCourseCard(TimestampMixin, BaseModel):
    """仪表板课程卡片模型"""
    id: int
    title: str
    progress: float = 0.0
    last_accessed: Optional[datetime] = None
