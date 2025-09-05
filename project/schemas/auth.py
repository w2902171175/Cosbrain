# project/schemas/auth.py
"""
用户认证相关Schema模块
"""

from pydantic import BaseModel, EmailStr, Field, model_validator, field_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
import json
from .common import SkillWithProficiency, TimestampMixin, UserOwnerMixin


# --- Student/User Schemas ---
class StudentBase(BaseModel):
    """学生基础信息模型，用于创建或更新时接收数据"""
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="用户在平台内唯一的用户名/昵称")
    phone_number: Optional[str] = Field(None, min_length=11, max_length=11,
                                        description="用户手机号，用于登录和重置密码")  # 假设手机号是11位
    school: Optional[str] = Field(None, max_length=100, description="用户所属学校名称")

    name: Optional[str] = Field(None, description="用户真实姓名")
    major: Optional[str] = None
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="用户技能列表及熟练度")
    interests: Optional[str] = None
    bio: Optional[str] = None
    awards_competitions: Optional[str] = None
    academic_achievements: Optional[str] = None
    soft_skills: Optional[str] = None
    portfolio_link: Optional[str] = None
    preferred_role: Optional[str] = None
    availability: Optional[str] = None
    location: Optional[str] = Field(None, description="学生所在地理位置，例如：广州大学城，珠海横琴")


class StudentCreate(StudentBase):
    """创建学生时的数据模型 (包含邮箱或手机号，以及密码)"""
    email: Optional[EmailStr] = Field(None, description="用户邮箱，如果提供则用于注册和登录")
    password: str = Field(..., min_length=6, description="用户密码，至少6位")

    @model_validator(mode='after')  # 在所有字段验证之后运行
    def check_email_or_phone_number_provided(self) -> 'StudentCreate':
        if not self.email and not self.phone_number:
            raise ValueError('邮箱或手机号至少需要提供一个用于注册。')
        return self


class StudentResponse(StudentBase, TimestampMixin):
    """返回学生信息时的模型 (不包含密码哈希)"""
    id: int
    email: Optional[EmailStr] = None

    combined_text: Optional[str] = None
    embedding: Optional[List[float]] = None
    llm_api_type: Optional[Literal[
        "openai", "zhipu", "siliconflow", "huoshanengine", "kimi", "deepseek", "custom_openai"
    ]] = None
    llm_api_base_url: Optional[str] = None
    llm_model_id: Optional[str] = None
    llm_model_ids: Optional[Dict[str, List[str]]] = None
    llm_api_key_encrypted: Optional[str] = None

    is_admin: bool
    total_points: int
    last_login_at: Optional[datetime] = None
    login_count: int

    completed_projects_count: Optional[int] = Field(None, description="用户创建并已完成的项目总数")
    completed_courses_count: Optional[int] = Field(None, description="用户完成的课程总数")

    model_config = {
        'protected_namespaces': ()
    }

    # 3. 添加下面的验证器函数
    @field_validator('llm_model_ids', mode='before')
    @classmethod
    def parse_llm_model_ids(cls, value):
        """
        在验证之前，尝试将字符串类型的 llm_model_ids 解析为字典。
        """
        # 如果值是字符串类型，就尝试用 json.loads 解析它
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # 如果字符串不是有效的JSON，返回None，符合字段的Optional属性
                return None
        # 如果值不是字符串（比如已经是dict或None），直接返回原值
        return value


class StudentUpdate(BaseModel):
    """更新学生信息时的模型，所有字段均为可选"""
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="用户在平台内唯一的用户名/昵称")
    phone_number: Optional[str] = Field(None, min_length=11, max_length=11, description="用户手机号")
    school: Optional[str] = Field(None, max_length=100, description="用户所属学校名称")
    name: Optional[str] = Field(None, description="用户真实姓名")
    major: Optional[str] = None
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="用户技能列表及熟练度")
    interests: Optional[str] = None
    bio: Optional[str] = None
    awards_competitions: Optional[str] = None
    academic_achievements: Optional[str] = None
    soft_skills: Optional[str] = None
    portfolio_link: Optional[str] = None
    preferred_role: Optional[str] = None
    availability: Optional[str] = None
    location: Optional[str] = Field(None, description="学生所在地理位置，例如：广州大学城，珠海横琴")


# --- User Login Model ---
class UserLogin(BaseModel):
    """用户登录模型"""
    email: EmailStr
    password: str


# --- JWT Token Response Model ---
class Token(BaseModel):
    """JWT令牌响应模型"""
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int = 0


# --- 用户管理员状态更新 ---
class UserAdminStatusUpdate(BaseModel):
    """用户管理员状态更新模型"""
    is_admin: bool = Field(..., description="是否设置为系统管理员 (True) 或取消管理员权限 (False)")


# --- 用户关注相关 ---
class UserFollowResponse(TimestampMixin, BaseModel):
    """用户关注响应模型"""
    id: int
    follower_id: int
    followed_id: int
