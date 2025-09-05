# project/schemas/chatrooms.py
"""
聊天室相关Schema模块
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from .common import TimestampMixin, UserOwnerMixin, validate_media_fields


# --- ChatRoom Schemas ---
class ChatRoomBase(BaseModel):
    """聊天室基础信息模型"""
    name: str = Field(..., max_length=100)
    type: Literal["project_group", "course_group", "private", "general"] = Field("general", description="聊天室类型")
    project_id: Optional[int] = Field(None, description="如果为项目群组，关联的项目ID")
    course_id: Optional[int] = Field(None, description="如果为课程群组，关联的课程ID")
    color: Optional[str] = Field(None, max_length=20)


class ChatRoomCreate(ChatRoomBase):
    """创建聊天室模型"""
    pass


class ChatRoomUpdate(ChatRoomBase):
    """更新聊天室模型"""
    name: Optional[str] = None
    type: Optional[str] = None
    project_id: Optional[int] = None
    course_id: Optional[int] = None
    color: Optional[str] = None


class ChatRoomResponse(ChatRoomBase, TimestampMixin):
    """聊天室响应模型"""
    id: int
    creator_id: int
    members_count: Optional[int] = None
    last_message: Optional[Dict[str, Any]] = None
    unread_messages_count: Optional[int] = 0
    online_members_count: Optional[int] = 0


# --- ChatRoom Member Schemas ---
class ChatRoomMemberBase(BaseModel):
    """聊天室成员基础模型"""
    room_id: int
    member_id: int
    role: Literal["king", "admin", "member"] = Field("member", description="成员角色")
    status: Literal["active", "banned", "left"] = Field("active", description="成员状态")
    last_read_at: Optional[datetime] = None


class ChatRoomMemberCreate(ChatRoomMemberBase):
    """创建聊天室成员模型"""
    pass


class ChatRoomMemberResponse(ChatRoomMemberBase, TimestampMixin):
    """聊天室成员响应模型"""
    id: int
    member_id: int
    joined_at: datetime
    member_name: Optional[str] = Field(None, description="成员的姓名")


class ChatRoomMemberRoleUpdate(BaseModel):
    """聊天室成员角色更新模型"""
    role: Literal["king", "admin", "member"] = Field(..., description="要设置的新角色")


# --- ChatRoom Join Request Schemas ---
class ChatRoomJoinRequestCreate(BaseModel):
    """聊天室加入请求创建模型"""
    message: Optional[str] = Field(None, description="入群申请理由")


class ChatRoomJoinRequestProcess(BaseModel):
    """聊天室加入请求处理模型"""
    status: Literal["approved", "rejected"] = Field(..., description="处理结果状态")


class ChatRoomJoinRequestResponse(TimestampMixin, BaseModel):
    """聊天室加入请求响应模型"""
    id: int
    room_id: int
    requester_id: int
    reason: Optional[str] = None
    status: str
    requested_at: datetime
    processed_by_id: Optional[int] = None
    processed_at: Optional[datetime] = None


# --- Chat Message Schemas ---
class ChatMessageBase(BaseModel):
    """聊天消息基础模型"""
    content_text: Optional[str] = None
    message_type: Literal["text", "image", "file", "video", "audio", "system_notification"] = "text"
    media_url: Optional[str] = Field(None, description="媒体文件OSS URL或外部链接")
    reply_to_message_id: Optional[int] = Field(None, description="回复的消息ID")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    original_filename: Optional[str] = Field(None, description="原始文件名")
    audio_duration: Optional[float] = Field(None, description="音频时长（秒）")
    is_pinned: Optional[bool] = Field(False, description="是否置顶消息")

    @model_validator(mode='after')
    def check_content_or_media(self) -> 'ChatMessageBase':
        if self.message_type == "text":
            if not self.content_text:
                raise ValueError("当 message_type 为 'text' 时，content_text (消息内容) 不能为空。")
        elif self.message_type in ["image", "file", "video", "audio"]:
            if not self.media_url:
                raise ValueError(f"当 message_type 为 '{self.message_type}' 时，media_url (媒体文件URL) 不能为空。")
        elif self.message_type == "system_notification":
            if not self.content_text:
                raise ValueError("系统通知消息必须有文本内容。")
        return self


class ChatMessageCreate(ChatMessageBase):
    """创建聊天消息模型"""
    pass


class ChatMessageResponse(ChatMessageBase, TimestampMixin):
    """聊天消息响应模型"""
    id: int
    room_id: int
    sender_id: int
    sent_at: datetime
    deleted_at: Optional[datetime] = None
    edited_at: Optional[datetime] = None
    message_status: Optional[str] = Field("sent", description="消息状态")
    sender_name: Optional[str] = None
    
    # 回复消息的详情
    reply_to_message: Optional['ChatMessageResponse'] = Field(None, description="被回复的消息详情")


# --- 聊天室设置更新 ---
class ChatRoomSettingsUpdate(BaseModel):
    """聊天室设置更新模型"""
    allow_member_invite: Optional[bool] = Field(None, description="允许成员邀请")
    message_retention_days: Optional[int] = Field(None, description="消息保留天数")
    file_upload_enabled: Optional[bool] = Field(None, description="是否允许文件上传")
    announcement: Optional[str] = Field(None, description="聊天室公告")


# --- 批量清理选项 ---
class BatchCleanupOptions(BaseModel):
    """批量清理选项模型"""
    cleanup_deleted_rooms: bool = Field(False, description="清理已删除的聊天室")
    cleanup_old_messages: bool = Field(False, description="清理过期消息")
    cleanup_invalid_members: bool = Field(False, description="清理无效成员")
    cleanup_expired_files: bool = Field(False, description="清理过期文件")
    days_threshold: int = Field(30, ge=1, le=365, description="清理天数阈值")


# --- 处理加入申请动作 ---
class ProcessJoinRequestAction(BaseModel):
    """处理加入申请的动作模型"""
    action: Literal["approved", "rejected"] = Field(..., description="处理动作：批准或拒绝")
    message: Optional[str] = Field(None, description="管理员留言")


# --- 转发消息请求 ---
class ForwardMessageRequest(BaseModel):
    """转发消息请求模型"""
    to_room_id: int = Field(..., description="目标聊天室ID")


# --- 收藏相关模型 ---
class ChatMessageCollectionRequest(BaseModel):
    """聊天室消息收藏请求模型"""
    folder_id: Optional[int] = Field(None, description="目标文件夹ID")
    title: Optional[str] = Field(None, max_length=200, description="自定义标题")
    notes: Optional[str] = Field(None, max_length=1000, description="收藏备注")


class CollectibleMessageResponse(TimestampMixin, BaseModel):
    """可收藏的聊天室消息响应模型"""
    id: int
    content_text: Optional[str]
    message_type: str
    media_url: Optional[str]
    original_filename: Optional[str]
    file_size: Optional[int]
    audio_duration: Optional[float]
    sender_name: str
    sent_at: datetime
    preview_title: str
