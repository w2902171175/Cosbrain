# project/schemas/forum.py
"""
论坛相关Schema模块
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from .common import TimestampMixin, UserOwnerMixin, LikeableMixin, MediaMixin, validate_media_fields


# --- Forum Topic Schemas ---
class ForumTopicBase(BaseModel):
    """论坛话题基础模型"""
    title: Optional[str] = None
    content: str
    shared_item_type: Optional[Literal[
        "note", "course", "project", "chat_message", "knowledge_base", "collected_content"]] = Field(
        None, description="如果分享平台内部内容，记录其类型")
    shared_item_id: Optional[int] = Field(None, description="如果分享平台内部内容，记录其ID")
    tags: Optional[str] = None
    media_url: Optional[str] = Field(None, description="图片、视频或文件的OSS URL")
    media_type: Optional[Literal["image", "video", "file", "audio"]] = Field(None, description="媒体类型")
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    media_size_bytes: Optional[int] = Field(None, description="媒体文件大小（字节）")
    # 新增字段
    attachments: Optional[List[Dict[str, Any]]] = Field(None, description="附件信息列表")
    mentioned_users_info: Optional[List[Dict[str, Any]]] = Field(None, description="被@用户信息列表")

    @model_validator(mode='after')
    def validate_media_and_shared_item(self) -> 'ForumTopicBase':
        # 使用通用验证函数
        validate_media_fields(self.media_url, self.media_type, "media")
        
        # 检查共享内容和直接上传媒体文件的互斥性
        if (self.shared_item_type and self.shared_item_id is not None) and self.media_url:
            raise ValueError("不能同时指定共享平台内容 (shared_item_type/id) 和直接上传媒体文件 (media_url)。请选择一种方式。")
        
        # 检查共享内容字段的完整性
        if (self.shared_item_type and self.shared_item_id is None) or \
                (self.shared_item_id is not None and not self.shared_item_type):
            raise ValueError("shared_item_type 和 shared_item_id 必须同时提供，或同时为空。")
        return self


class ForumTopicCreate(ForumTopicBase):
    """创建论坛话题模型"""
    pass


class ForumTopicResponse(ForumTopicBase, TimestampMixin, UserOwnerMixin, LikeableMixin):
    """论坛话题响应模型"""
    id: int
    owner_name: Optional[str] = None
    comments_count: Optional[int] = None
    views_count: Optional[int] = None
    is_collected_by_current_user: Optional[bool] = False
    combined_text: Optional[str] = None


# --- Forum Comment Schemas ---
class ForumCommentBase(BaseModel):
    """论坛评论基础模型"""
    content: str
    parent_comment_id: Optional[int] = None
    media_url: Optional[str] = Field(None, description="图片、视频或文件的OSS URL")
    media_type: Optional[Literal["image", "video", "file", "audio"]] = Field(None, description="媒体类型")
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    media_size_bytes: Optional[int] = Field(None, description="媒体文件大小（字节）")
    # 新增字段
    attachments: Optional[List[Dict[str, Any]]] = Field(None, description="附件信息列表")
    emoji_info: Optional[Dict[str, Any]] = Field(None, description="表情包信息")
    mentioned_users_info: Optional[List[Dict[str, Any]]] = Field(None, description="被@用户信息列表")
    reply_count: Optional[int] = Field(None, description="回复数量")

    @model_validator(mode='after')
    def validate_media_in_comment(self) -> 'ForumCommentBase':
        # 使用通用验证函数
        validate_media_fields(self.media_url, self.media_type, "media")
        return self


class ForumCommentCreate(ForumCommentBase):
    """创建论坛评论模型"""
    pass


class ForumCommentResponse(ForumCommentBase, TimestampMixin, UserOwnerMixin, LikeableMixin):
    """论坛评论响应模型"""
    id: int
    topic_id: int

    @property
    def owner_name(self) -> str:
        return getattr(self, '_owner_name', "未知用户")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


# --- Forum Like Schemas ---
class ForumLikeResponse(TimestampMixin, BaseModel):
    """论坛点赞响应模型"""
    id: int
    owner_id: int
    topic_id: Optional[int] = None
    comment_id: Optional[int] = None


# --- 抖音式论坛功能新增 Schemas ---
class EmojiBase(BaseModel):
    """表情包基础模型"""
    name: str = Field(..., description="表情包名称")
    category: str = Field(default="custom", description="表情包分类")
    url: str = Field(..., description="表情包URL")


class EmojiResponse(EmojiBase, TimestampMixin):
    """表情包响应模型"""
    id: int
    uploader_id: Optional[int] = None
    is_system: bool = False
    is_active: bool = True


class MentionedUserInfo(BaseModel):
    """被提及用户信息模型"""
    id: int
    username: str
    name: str
    avatar_url: Optional[str] = None


class AttachmentInfo(BaseModel):
    """附件信息模型"""
    url: str = Field(..., description="附件URL")
    type: str = Field(..., description="附件类型: image, video, audio, file")
    filename: str = Field(..., description="原始文件名")
    size: int = Field(..., description="文件大小（字节）")
    content_type: str = Field(..., description="MIME类型")


class ForumMentionResponse(TimestampMixin, BaseModel):
    """论坛提及响应模型"""
    id: int
    mentioner_id: int
    mentioned_id: int
    topic_id: Optional[int] = None
    comment_id: Optional[int] = None
    is_read: bool = False
    
    # 关联信息
    mentioner_name: Optional[str] = None
    topic_title: Optional[str] = None
    comment_content: Optional[str] = None


class TrendingTopicResponse(BaseModel):
    """热门话题响应模型"""
    topic: 'ForumTopicResponse'
    hot_score: float
    rank: int
    
    class Config:
        from_attributes = True


class UserSearchResult(BaseModel):
    """用户搜索结果模型"""
    id: int
    username: str
    name: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None


# --- 收藏相关模型 ---
class ForumTopicCollectionRequest(BaseModel):
    """论坛话题收藏请求模型"""
    folder_id: Optional[int] = Field(None, description="目标文件夹ID")
    title: Optional[str] = Field(None, max_length=200, description="自定义标题")
    notes: Optional[str] = Field(None, max_length=1000, description="收藏备注")
    collect_attachment_only: Optional[bool] = Field(False, description="是否只收藏附件")


class ForumCommentCollectionRequest(BaseModel):
    """论坛回复收藏请求模型"""
    folder_id: Optional[int] = Field(None, description="目标文件夹ID")
    title: Optional[str] = Field(None, max_length=200, description="自定义标题")
    notes: Optional[str] = Field(None, max_length=1000, description="收藏备注")


class CollectibleTopicResponse(TimestampMixin, BaseModel):
    """可收藏的论坛话题响应模型"""
    id: int
    title: Optional[str]
    content: str
    author_name: str
    has_attachment: bool
    media_type: Optional[str]
    media_filename: Optional[str]
    media_size: Optional[int]
    likes_count: int
    comments_count: int
    views_count: int
