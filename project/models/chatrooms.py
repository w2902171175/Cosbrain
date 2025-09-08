# project/models/chatrooms.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, UniqueConstraint, Index, text, CheckConstraint, BigInteger
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from project.base import Base
from .mixins import TimestampMixin, OwnerMixin, MediaMixin
from typing import Optional, List
from enum import Enum


# 枚举定义
class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    SYSTEM_NOTIFICATION = "system_notification"


class MessageStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class ChatRoomType(str, Enum):
    GENERAL = "general"
    PROJECT = "project"
    COURSE = "course"
    PRIVATE = "private"


class MemberRole(str, Enum):
    CREATOR = "creator"
    ADMIN = "admin"
    MEMBER = "member"


class MemberStatus(str, Enum):
    ACTIVE = "active"
    BANNED = "banned"
    LEFT = "left"


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChatRoom(Base):
    __tablename__ = "chat_rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    type = Column(String, nullable=False, default=ChatRoomType.GENERAL.value)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, unique=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, unique=True)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # 群主字段

    color = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # 关系定义
    messages = relationship("ChatMessage", back_populates="room", cascade="all, delete-orphan", 
                          order_by="ChatMessage.sent_at.desc()")
    project = relationship("Project", back_populates="chat_room")
    course = relationship("Course", back_populates="chat_room")
    creator = relationship("User", back_populates="created_chat_rooms")
    memberships = relationship("ChatRoomMember", back_populates="room", cascade="all, delete-orphan")
    join_requests = relationship("ChatRoomJoinRequest", back_populates="room", cascade="all, delete-orphan")

    @validates('type')
    def validate_type(self, key, value):
        if value not in [t.value for t in ChatRoomType]:
            raise ValueError(f"Invalid chat room type: {value}")
        return value

    def get_active_members(self):
        """获取活跃成员"""
        return [m for m in self.memberships if m.status == MemberStatus.ACTIVE.value]

    def get_member_count(self):
        """获取成员数量"""
        return len(self.get_active_members())

    def is_member(self, user_id: int) -> bool:
        """检查用户是否为成员"""
        return any(m.member_id == user_id and m.status == MemberStatus.ACTIVE.value 
                  for m in self.memberships)

    def is_admin(self, user_id: int) -> bool:
        """检查用户是否为管理员"""
        if user_id == self.creator_id:
            return True
        return any(m.member_id == user_id and m.role == MemberRole.ADMIN.value 
                  and m.status == MemberStatus.ACTIVE.value for m in self.memberships)

    def get_unread_count(self, user_id: int) -> int:
        """获取用户的未读消息数量"""
        member = next((m for m in self.memberships if m.member_id == user_id), None)
        if not member or not member.last_read_at:
            return len([m for m in self.messages if m.deleted_at is None])
        
        return len([m for m in self.messages 
                   if m.deleted_at is None and m.sent_at > member.last_read_at])

    def get_pinned_messages(self):
        """获取置顶消息"""
        return [m for m in self.messages if m.is_pinned and m.deleted_at is None]


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)
    
    # ChatMessage特有字段
    room_id = Column(Integer, ForeignKey("chat_rooms.id"), nullable=False, comment="所属聊天室ID")
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="发送者ID")

    content_text = Column(Text, nullable=True, comment="消息文本内容")
    message_type = Column(String, default=MessageType.TEXT.value, comment="消息类型")

    # 媒体文件字段（统一字段命名）
    media_url = Column(String, nullable=True, comment="媒体文件OSS URL或外部链接")
    original_filename = Column(String(255), nullable=True, comment="原始文件名")
    file_size_bytes = Column(BigInteger, nullable=True, comment="文件大小（字节）")
    
    # 回复消息支持
    reply_to_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True, comment="回复的消息ID")
    
    # 音频消息支持
    audio_duration = Column(Float, nullable=True, comment="音频时长（秒）")
    
    # 消息状态和优先级
    message_status = Column(String(20), default=MessageStatus.SENT.value, comment="消息状态：sent/delivered/read")
    is_pinned = Column(Boolean, default=False, comment="是否置顶消息")
    
    # 重写时间戳字段以保持现有字段名
    sent_at = Column(DateTime, server_default=func.now(), comment="发送时间")
    deleted_at = Column(DateTime, nullable=True, comment="消息删除时间，为空表示未删除")
    edited_at = Column(DateTime, nullable=True, comment="消息编辑时间")

    # 关系定义
    room = relationship("ChatRoom", back_populates="messages")
    sender = relationship("User", back_populates="sent_messages")
    
    # 自引用关系：回复消息
    reply_to = relationship("ChatMessage", remote_side=[id], backref="replies")

    # 表级约束
    __table_args__ = (
        # 音频时长约束
        CheckConstraint(
            "(message_type != 'audio') OR "
            "(message_type = 'audio' AND audio_duration IS NOT NULL AND audio_duration > 0)",
            name='check_audio_duration'
        ),
        
        # 媒体URL约束
        CheckConstraint(
            "(message_type IN ('text', 'system_notification')) OR "
            "(message_type IN ('image', 'video', 'audio', 'file') AND media_url IS NOT NULL)",
            name='check_media_url'
        ),
        
        # 文本内容约束
        CheckConstraint(
            "(message_type != 'text') OR "
            "(message_type = 'text' AND content_text IS NOT NULL AND LENGTH(TRIM(content_text)) > 0)",
            name='check_text_content'
        ),
        
        # 索引管理已移至 performance_indexes.py 统一管理
        # 只保留约束条件，移除索引定义以避免重复
    )

    @validates('message_type')
    def validate_message_type(self, key, value):
        if value not in [t.value for t in MessageType]:
            raise ValueError(f"Invalid message type: {value}")
        return value

    @validates('message_status')
    def validate_message_status(self, key, value):
        if value not in [s.value for s in MessageStatus]:
            raise ValueError(f"Invalid message status: {value}")
        return value

    @validates('audio_duration')
    def validate_audio_duration(self, key, value):
        if self.message_type == MessageType.AUDIO.value and (value is None or value <= 0):
            raise ValueError("Audio messages must have a valid duration")
        return value

    def is_media_message(self) -> bool:
        """判断是否为媒体消息"""
        return self.message_type in [MessageType.IMAGE.value, MessageType.VIDEO.value, 
                                   MessageType.AUDIO.value, MessageType.FILE.value]

    def get_file_size_formatted(self) -> str:
        """获取格式化的文件大小（兼容MediaMixin接口）"""
        if not self.file_size_bytes:
            return "0 B"
        
        size = self.file_size_bytes
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    @property
    def file_size(self):
        """向后兼容属性，映射到file_size_bytes"""
        return self.file_size_bytes

    @file_size.setter
    def file_size(self, value):
        """向后兼容属性设置器"""
        self.file_size_bytes = value

    def is_editable(self) -> bool:
        """判断消息是否可编辑（仅文本消息且未被删除）"""
        return (self.message_type == MessageType.TEXT.value and 
                self.deleted_at is None and 
                not self.is_pinned)

    def soft_delete(self):
        """软删除消息"""
        self.deleted_at = func.now()

    def mark_as_read(self):
        """标记消息为已读"""
        self.message_status = MessageStatus.READ.value

    def get_reply_chain(self) -> List['ChatMessage']:
        """获取回复链"""
        chain = []
        current = self.reply_to
        while current and len(chain) < 10:  # 限制链长度防止无限循环
            chain.append(current)
            current = current.reply_to
        return chain

    def get_file_size_formatted(self) -> str:
        """格式化文件大小显示"""
        if not self.file_size_bytes:
            return "Unknown"
        
        size = self.file_size_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def get_audio_duration_formatted(self) -> str:
        """格式化音频时长显示"""
        if not self.audio_duration:
            return "00:00"
        
        minutes = int(self.audio_duration // 60)
        seconds = int(self.audio_duration % 60)
        return f"{minutes:02d}:{seconds:02d}"


class ChatRoomMember(Base):
    __tablename__ = "chat_room_members"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 角色类型： 'admin' (管理员), 'member' (普通成员)
    # 'creator' 角色将通过 ChatRoom.creator_id 直接关联。
    role = Column(String, default=MemberRole.MEMBER.value, nullable=False)

    # 成员状态： 'active' (活跃), 'banned' (被踢出/禁用), 'left' (已离开)
    status = Column(String, default=MemberStatus.ACTIVE.value, nullable=False)

    joined_at = Column(DateTime, default=func.now(), nullable=False)
    last_read_at = Column(DateTime, nullable=True, comment="最后阅读时间，用于计算未读消息")
    
    # 成员设置
    notification_enabled = Column(Boolean, default=True, comment="是否启用通知")
    muted_until = Column(DateTime, nullable=True, comment="静音到期时间")

    # 关系定义
    room = relationship("ChatRoom", back_populates="memberships")
    member = relationship("User", back_populates="chat_room_memberships")

    __table_args__ = (
        # 确保一个用户在一个聊天室中只有一条成员记录
        UniqueConstraint('room_id', 'member_id', name='_room_member_uc'),
        # 添加索引
        Index('idx_room_member_status', 'room_id', 'status'),
        Index('idx_member_rooms', 'member_id', 'status'),
    )

    @validates('role')
    def validate_role(self, key, value):
        if value not in [r.value for r in MemberRole]:
            raise ValueError(f"Invalid member role: {value}")
        return value

    @validates('status')
    def validate_status(self, key, value):
        if value not in [s.value for s in MemberStatus]:
            raise ValueError(f"Invalid member status: {value}")
        return value

    def is_active(self) -> bool:
        """检查成员是否活跃"""
        return self.status == MemberStatus.ACTIVE.value

    def is_admin(self) -> bool:
        """检查是否为管理员"""
        return self.role == MemberRole.ADMIN.value and self.is_active()

    def is_muted(self) -> bool:
        """检查是否被静音"""
        return self.muted_until is not None and self.muted_until > func.now()

    def mark_as_read(self):
        """标记为已读（更新最后阅读时间）"""
        self.last_read_at = func.now()

    def leave_room(self):
        """离开聊天室"""
        self.status = MemberStatus.LEFT.value

    def ban_member(self):
        """禁用成员"""
        self.status = MemberStatus.BANNED.value

    def promote_to_admin(self):
        """提升为管理员"""
        if self.is_active():
            self.role = MemberRole.ADMIN.value

    def demote_to_member(self):
        """降级为普通成员"""
        if self.is_active():
            self.role = MemberRole.MEMBER.value


class ChatRoomJoinRequest(Base):
    __tablename__ = "chat_room_join_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id"), nullable=False, index=True)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reason = Column(String, nullable=True, comment="申请理由")

    # 状态：'pending' (待处理), 'approved' (已批准), 'rejected' (已拒绝)
    status = Column(String, default=RequestStatus.PENDING.value, nullable=False)

    requested_at = Column(DateTime, default=func.now(), nullable=False)
    processed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 谁处理的这个请求
    processed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String, nullable=True, comment="拒绝理由")

    # 关系定义
    room = relationship("ChatRoom", back_populates="join_requests")
    requester = relationship("User", foreign_keys=[requester_id], back_populates="sent_join_requests")
    processor = relationship("User", foreign_keys=[processed_by_id], back_populates="processed_join_requests")

    __table_args__ = (
        # 确保一个用户在一个聊天室中最多只有一个 'pending' 状态的申请
        # 这是 PostgreSQL 特性，对于 SQLite 可能需要弱化此约束或手动管理
        Index('_room_requester_pending_uc', 'room_id', 'requester_id', unique=True,
              postgresql_where=text("status = 'pending'")),
        # 添加常用索引
        Index('idx_join_requests_status', 'room_id', 'status'),
        Index('idx_join_requests_requester', 'requester_id', 'status'),
    )

    @validates('status')
    def validate_status(self, key, value):
        if value not in [s.value for s in RequestStatus]:
            raise ValueError(f"Invalid request status: {value}")
        return value

    def is_pending(self) -> bool:
        """检查是否为待处理状态"""
        return self.status == RequestStatus.PENDING.value

    def approve(self, processor_id: int):
        """批准申请"""
        self.status = RequestStatus.APPROVED.value
        self.processed_by_id = processor_id
        self.processed_at = func.now()

    def reject(self, processor_id: int, reason: str = None):
        """拒绝申请"""
        self.status = RequestStatus.REJECTED.value
        self.processed_by_id = processor_id
        self.processed_at = func.now()
        if reason:
            self.rejection_reason = reason

    def can_be_processed(self) -> bool:
        """检查是否可以被处理"""
        return self.is_pending()


# 视图模型（用于复杂查询）
class ChatMessageWithReplies:
    """消息及其回复信息的视图模型"""
    def __init__(self, message: ChatMessage, reply_content: str = None, 
                 reply_sender_id: int = None, sender_name: str = None, 
                 reply_sender_name: str = None):
        self.message = message
        self.reply_content = reply_content
        self.reply_sender_id = reply_sender_id
        self.sender_name = sender_name
        self.reply_sender_name = reply_sender_name


# 辅助函数
class ChatRoomMediaStats:
    """聊天室媒体统计"""
    def __init__(self, message_type: str, count: int, total_size: int):
        self.message_type = message_type
        self.count = count
        self.total_size = total_size

    def get_total_size_formatted(self) -> str:
        """格式化总大小显示"""
        size = self.total_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
