# project/schemas/common.py
"""
公共Schema模块：包含通用的基础模型、工具函数和Mixin类
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


# --- 工具函数 ---
def validate_media_fields(media_url: Optional[str], media_type: Optional[str], field_name: str = "media") -> None:
    """
    通用媒体字段验证函数，减少重复代码
    
    Args:
        media_url: 媒体文件URL
        media_type: 媒体类型
        field_name: 字段名称前缀，用于错误消息
    """
    if media_url and not media_type:
        raise ValueError(f"{field_name}_url 存在时，{field_name}_type 不能为空，且必须为 'image', 'video', 'file' 或 'audio'。")


# --- 公共基础Schema ---
class SkillWithProficiency(BaseModel):
    """技能熟练度模型，包含古文优雅的描述"""
    name: str = Field(..., description="技能名称")
    # 熟练度等级，使用 Literal 限制可选值
    level: Literal[
        "初窥门径", "登堂入室", "融会贯通", "炉火纯青"
    ] = Field(..., description="熟练度等级：初窥门径, 登堂入室, 融会贯通, 炉火纯青")

    class Config:
        from_attributes = True


# --- 公共Mixin类 ---
class TimestampMixin(BaseModel):
    """时间戳Mixin"""
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {
        'protected_namespaces': ()
    }


class MediaMixin(BaseModel):
    """媒体内容Mixin"""
    media_url: Optional[str] = Field(None, description="媒体文件OSS URL")
    media_type: Optional[Literal["image", "video", "file", "audio"]] = Field(None, description="媒体类型")
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    media_size_bytes: Optional[int] = Field(None, description="媒体文件大小（字节）")

    model_config = {
        'protected_namespaces': ()
    }


class UserOwnerMixin(BaseModel):
    """用户所有者Mixin"""
    owner_id: int

    model_config = {
        'protected_namespaces': ()
    }


class LikeableMixin(BaseModel):
    """可点赞内容Mixin"""
    likes_count: Optional[int] = Field(default=None, description="点赞数量")
    is_liked_by_current_user: Optional[bool] = Field(default=False, description="当前用户是否已点赞")

    model_config = {
        'protected_namespaces': ()
    }


# --- 通用响应模型 ---
class Response(BaseModel):
    """通用API响应模型"""
    message: str = Field(..., description="响应消息")
    success: bool = Field(True, description="是否成功")
    data: Optional[dict] = Field(None, description="响应数据")


class PaginatedResponse(BaseModel):
    """分页响应模型"""
    items: List[dict] = Field(..., description="数据项列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(1, description="当前页数")
    size: int = Field(50, description="每页大小")
    pages: int = Field(..., description="总页数")


class CountResponse(BaseModel):
    """统计数量响应模型"""
    count: int = Field(..., description="统计数量")
    description: Optional[str] = Field(None, description="统计的描述信息")


class MessageResponse(BaseModel):
    """通用消息响应模型"""
    message: str = Field(..., description="响应消息")
    success: bool = Field(True, description="是否成功")
    data: Optional[dict] = Field(None, description="附加数据")
