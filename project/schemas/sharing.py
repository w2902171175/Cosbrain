# project/schemas/sharing.py
"""
分享功能相关Schema模块
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from .common import TimestampMixin, UserOwnerMixin


# ===== 分享内容基础Schema =====

class ShareContentRequest(BaseModel):
    """分享内容请求模型"""
    content_type: Literal["project", "course", "knowledge_base", "note_folder", "forum_topic"] = Field(
        ..., description="分享内容类型"
    )
    content_id: int = Field(..., description="分享内容ID")
    share_type: Literal["forum_topic", "chatroom", "link", "wechat", "qq"] = Field(
        ..., description="分享类型"
    )
    target_id: Optional[int] = Field(None, description="分享目标ID（聊天室ID等）")
    
    # 分享配置
    title: Optional[str] = Field(None, max_length=200, description="自定义标题")
    description: Optional[str] = Field(None, max_length=1000, description="分享描述")
    is_public: Optional[bool] = Field(True, description="是否公开分享")
    allow_comments: Optional[bool] = Field(True, description="是否允许评论")
    expires_at: Optional[datetime] = Field(None, description="分享过期时间")
    
    @model_validator(mode='after')
    def validate_share_request(self) -> 'ShareContentRequest':
        """验证分享请求"""
        # 聊天室分享必须提供target_id
        if self.share_type == "chatroom" and not self.target_id:
            raise ValueError("聊天室分享必须提供target_id")
        
        # 论坛分享不需要target_id
        if self.share_type == "forum_topic" and self.target_id:
            raise ValueError("论坛分享不需要target_id")
        
        return self


class ShareContentResponse(BaseModel):
    """分享内容响应模型"""
    id: int
    content_type: str
    content_id: int
    content_title: Optional[str]
    content_description: Optional[str]
    share_type: str
    target_id: Optional[int]
    
    # 分享配置
    is_public: bool
    allow_comments: bool
    expires_at: Optional[datetime]
    
    # 统计信息
    view_count: int
    click_count: int
    share_count: int
    
    # 基础信息
    owner_id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime]
    
    # 关联信息
    owner_name: Optional[str] = None
    target_name: Optional[str] = None  # 聊天室名称等
    share_url: Optional[str] = None  # 分享链接
    
    class Config:
        from_attributes = True


class ShareLinkResponse(BaseModel):
    """分享链接响应模型"""
    share_id: int
    share_url: str
    share_text: str
    qr_code_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    
    # 平台特定的分享信息
    wechat_share: Optional[Dict[str, Any]] = None
    qq_share: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


# ===== 快速分享Schema =====

class QuickShareRequest(BaseModel):
    """快速分享请求模型"""
    content_type: Literal["project", "course", "knowledge_base", "note_folder", "forum_topic"]
    content_id: int
    platforms: List[Literal["forum", "chatroom", "wechat", "qq", "link"]] = Field(
        ..., description="分享平台列表"
    )
    custom_message: Optional[str] = Field(None, max_length=500, description="自定义分享消息")


class QuickShareResponse(BaseModel):
    """快速分享响应模型"""
    share_results: List[Dict[str, Any]] = Field(..., description="各平台分享结果")
    success_count: int = Field(..., description="成功分享数量")
    failed_count: int = Field(..., description="失败分享数量")


# ===== 分享到论坛Schema =====

class ShareToForumRequest(BaseModel):
    """分享到论坛请求模型"""
    content_type: Literal["project", "course", "knowledge_base", "note_folder", "forum_topic"]
    content_id: int
    title: Optional[str] = Field(None, max_length=200, description="自定义话题标题")
    additional_content: Optional[str] = Field(None, max_length=2000, description="附加说明内容")
    tags: Optional[str] = Field(None, max_length=200, description="话题标签")


class ShareToForumResponse(BaseModel):
    """分享到论坛响应模型"""
    topic_id: int = Field(..., description="创建的论坛话题ID")
    share_id: int = Field(..., description="分享记录ID")
    topic_url: str = Field(..., description="话题链接")


# ===== 分享到聊天室Schema =====

class ShareToChatroomRequest(BaseModel):
    """分享到聊天室请求模型"""
    content_type: Literal["project", "course", "knowledge_base", "note_folder", "forum_topic"]
    content_id: int
    chatroom_ids: List[int] = Field(..., description="目标聊天室ID列表")
    message: Optional[str] = Field(None, max_length=500, description="分享消息")


class ShareToChatroomResponse(BaseModel):
    """分享到聊天室响应模型"""
    share_results: List[Dict[str, Any]] = Field(..., description="各聊天室分享结果")
    success_count: int
    failed_count: int


# ===== 新增：论坛话题转发Schema =====

class ForumTopicRepostRequest(BaseModel):
    """论坛话题转发请求模型"""
    topic_id: int = Field(..., description="要转发的话题ID")
    additional_content: Optional[str] = Field(None, max_length=2000, description="转发时的附加说明")
    share_type: Literal["forum", "chatroom"] = Field(..., description="转发类型")
    chatroom_ids: Optional[List[int]] = Field(None, description="转发到聊天室时的聊天室ID列表")
    
    @model_validator(mode='after')
    def validate_repost_request(self) -> 'ForumTopicRepostRequest':
        """验证转发请求"""
        if self.share_type == "chatroom" and not self.chatroom_ids:
            raise ValueError("转发到聊天室时必须提供chatroom_ids")
        return self


class ForumTopicRepostResponse(BaseModel):
    """论坛话题转发响应模型"""
    share_type: str
    success: bool
    message: str
    # 转发到论坛时的结果
    new_topic_id: Optional[int] = None
    topic_url: Optional[str] = None
    # 转发到聊天室时的结果
    chatroom_results: Optional[List[Dict[str, Any]]] = None
    success_count: Optional[int] = None
    failed_count: Optional[int] = None


# ===== 新增：微信/QQ分享Schema =====

class SocialShareRequest(BaseModel):
    """社交平台分享请求模型"""
    content_type: Literal["project", "course", "knowledge_base", "note_folder", "forum_topic"]
    content_id: int
    platform: Literal["wechat", "qq"] = Field(..., description="分享平台")
    custom_message: Optional[str] = Field(None, max_length=500, description="自定义分享消息")


class SocialShareResponse(BaseModel):
    """社交平台分享响应模型"""
    share_id: int
    platform: str
    share_url: str
    share_text: str
    qr_code_url: Optional[str] = None
    
    # 平台特定信息
    wechat_config: Optional[Dict[str, Any]] = None
    qq_config: Optional[Dict[str, Any]] = None
    
    # 分享指导信息
    share_instructions: str = Field(..., description="分享操作指导")


# ===== 新增：链接复制分享Schema =====

class CopyLinkRequest(BaseModel):
    """复制链接请求模型"""
    content_type: Literal["project", "course", "knowledge_base", "note_folder", "forum_topic"]
    content_id: int
    include_qr: Optional[bool] = Field(True, description="是否包含二维码")


class CopyLinkResponse(BaseModel):
    """复制链接响应模型"""
    share_id: int
    share_url: str
    share_text: str
    qr_code_url: Optional[str] = None
    copy_success_message: str = Field(..., description="复制成功提示信息")
    sharing_tips: List[str] = Field(..., description="分享使用提示")


# ===== 分享统计Schema =====

class ShareStatsResponse(BaseModel):
    """分享统计响应模型"""
    total_shares: int = Field(..., description="总分享数")
    shares_by_type: Dict[str, int] = Field(..., description="按类型统计")
    shares_by_platform: Dict[str, int] = Field(..., description="按平台统计")
    recent_shares: List[ShareContentResponse] = Field(..., description="最近分享")
    top_shared_content: List[Dict[str, Any]] = Field(..., description="热门分享内容")


# ===== 分享日志Schema =====

class ShareLogResponse(BaseModel):
    """分享日志响应模型"""
    id: int
    action_type: str
    user_id: Optional[int]
    user_name: Optional[str]
    created_at: datetime
    extra_data: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True


# ===== 分享模板Schema =====

class ShareTemplateBase(BaseModel):
    """分享模板基础模型"""
    name: str = Field(..., max_length=100, description="模板名称")
    description: Optional[str] = Field(None, max_length=500, description="模板描述")
    content_types: List[str] = Field(..., description="支持的内容类型")
    share_platforms: List[str] = Field(..., description="支持的分享平台")
    default_settings: Optional[Dict[str, Any]] = Field(None, description="默认设置")
    template_style: Optional[Dict[str, Any]] = Field(None, description="样式配置")
    custom_text: Optional[str] = Field(None, description="自定义文案模板")


class ShareTemplateCreate(ShareTemplateBase):
    """创建分享模板请求模型"""
    pass


class ShareTemplateResponse(ShareTemplateBase, TimestampMixin, UserOwnerMixin):
    """分享模板响应模型"""
    id: int
    is_system: bool
    is_active: bool
    
    class Config:
        from_attributes = True


class ShareTemplateUpdate(BaseModel):
    """更新分享模板请求模型"""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    content_types: Optional[List[str]] = None
    share_platforms: Optional[List[str]] = None
    default_settings: Optional[Dict[str, Any]] = None
    template_style: Optional[Dict[str, Any]] = None
    custom_text: Optional[str] = None
    is_active: Optional[bool] = None


# ===== 内容预览Schema =====

class ShareableContentPreview(BaseModel):
    """可分享内容预览模型"""
    id: int
    type: str
    title: str
    description: Optional[str]
    author: str
    created_at: datetime
    is_public: bool
    thumbnail: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True
