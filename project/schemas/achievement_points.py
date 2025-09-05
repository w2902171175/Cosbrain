# project/schemas/achievement_points.py
"""
成就积分系统相关Schema模块
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from .common import TimestampMixin


# --- Achievement Schemas ---
class AchievementBase(BaseModel):
    """成就基础模型"""
    name: str = Field(..., description="成就名称")
    description: str = Field(..., description="成就描述")
    criteria_type: Literal[
        "PROJECT_COMPLETED_COUNT", "COURSE_COMPLETED_COUNT", "FORUM_LIKES_RECEIVED",
        "DAILY_LOGIN_STREAK", "FORUM_POSTS_COUNT", "CHAT_MESSAGES_SENT_COUNT",
        "LOGIN_COUNT"
    ] = Field(..., description="达成成就的条件类型")
    criteria_value: float = Field(..., description="达成成就所需的数值门槛")
    badge_url: Optional[str] = Field(None, description="勋章图片或图标URL")
    reward_points: int = Field(0, description="达成此成就额外奖励的积分")
    is_active: bool = Field(True, description="该成就是否启用")


class AchievementCreate(AchievementBase):
    """创建成就模型"""
    pass


class AchievementUpdate(AchievementBase):
    """更新成就模型"""
    name: Optional[str] = None
    description: Optional[str] = None
    criteria_type: Optional[Literal[
        "PROJECT_COMPLETED_COUNT", "COURSE_COMPLETED_COUNT", "FORUM_LIKES_RECEIVED",
        "DAILY_LOGIN_STREAK", "FORUM_POSTS_COUNT", "CHAT_MESSAGES_SENT_COUNT",
        "LOGIN_COUNT"
    ]] = None
    criteria_value: Optional[float] = None
    badge_url: Optional[str] = None
    reward_points: Optional[int] = None
    is_active: Optional[bool] = None


class AchievementResponse(AchievementBase, TimestampMixin):
    """成就响应模型"""
    id: int


# --- UserAchievement Schemas ---
class UserAchievementResponse(TimestampMixin, BaseModel):
    """用户成就响应模型"""
    id: int
    user_id: int
    achievement_id: int
    earned_at: datetime
    is_notified: bool
    achievement_name: Optional[str] = Field(None, description="成就名称")
    achievement_description: Optional[str] = Field(None, description="成就描述")
    badge_url: Optional[str] = Field(None, description="勋章图片URL")
    reward_points: Optional[int] = Field(None, description="获得此成就奖励的积分")


# --- PointsRewardRequest Schema ---
class PointsRewardRequest(BaseModel):
    """积分奖励请求模型"""
    user_id: int = Field(..., description="目标用户ID")
    amount: int = Field(..., description="积分变动数量，正数代表增加，负数代表减少")
    reason: Optional[str] = Field(None, description="积分变动理由")
    transaction_type: Literal["EARN", "CONSUME", "ADMIN_ADJUST"] = Field("ADMIN_ADJUST", description="交易类型")
    related_entity_type: Optional[str] = Field(None, description="关联的实体类型（如 project, course, forum_topic）")
    related_entity_id: Optional[int] = Field(None, description="关联实体ID")


# --- PointTransaction Schemas ---
class PointTransactionResponse(TimestampMixin, BaseModel):
    """积分交易响应模型"""
    id: int
    user_id: int
    amount: int
    reason: Optional[str] = Field(None, description="积分变动理由描述")
    transaction_type: str = Field(..., description="积分交易类型")
    related_entity_type: Optional[str] = Field(None, description="关联的实体类型")
    related_entity_id: Optional[int] = Field(None, description="关联实体的ID")
