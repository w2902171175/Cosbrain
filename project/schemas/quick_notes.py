# project/schemas/quick_notes.py
"""
随手记录相关Schema模块（quick_notes）
"""

from pydantic import BaseModel
from typing import Optional
from .common import TimestampMixin, UserOwnerMixin


# --- DailyRecord Schemas ---
class DailyRecordBase(BaseModel):
    """随手记录基础信息模型"""
    content: str
    mood: Optional[str] = None
    tags: Optional[str] = None


class DailyRecordCreate(DailyRecordBase):
    """创建随手记录模型"""
    pass


class DailyRecordResponse(DailyRecordBase, TimestampMixin, UserOwnerMixin):
    """随手记录响应模型"""
    id: int
    combined_text: Optional[str] = None