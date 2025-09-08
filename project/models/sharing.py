# project/models/sharing.py
"""
分享模型
提供平台内容的转发分享功能
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from project.base import Base
from .mixins import TimestampMixin, OwnerMixin


class SharedContent(Base, TimestampMixin, OwnerMixin):
    """分享的内容模型"""
    __tablename__ = "shared_contents"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin) - 分享者ID
    # - created_at, updated_at (from TimestampMixin)

    # 被分享的内容信息
    content_type = Column(String(50), nullable=False, comment="分享内容类型: project, course, knowledge_base, note_folder")
    content_id = Column(Integer, nullable=False, comment="分享内容ID")
    content_title = Column(String(500), nullable=True, comment="分享内容标题（冗余存储，提高查询性能）")
    content_description = Column(Text, nullable=True, comment="分享内容描述")
    content_metadata = Column(JSON, nullable=True, comment="分享内容的元数据信息")

    # 分享类型和目标
    share_type = Column(String(50), nullable=False, comment="分享类型: forum_topic, chatroom, link")
    target_id = Column(Integer, nullable=True, comment="分享目标ID（如聊天室ID，论坛分享时为null）")
    
    # 分享配置
    is_public = Column(Boolean, default=True, comment="是否公开分享")
    allow_comments = Column(Boolean, default=True, comment="是否允许评论")
    expires_at = Column(DateTime, nullable=True, comment="分享过期时间")
    
    # 分享统计
    view_count = Column(Integer, default=0, comment="查看次数")
    click_count = Column(Integer, default=0, comment="点击次数")
    share_count = Column(Integer, default=0, comment="被再次分享次数")

    # 分享状态
    status = Column(String(20), default='active', comment="分享状态: active, expired, deleted")

    # 关系
    owner = relationship("User", back_populates="shared_contents")
    share_logs = relationship("ShareLog", back_populates="shared_content", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SharedContent(id={self.id}, content_type='{self.content_type}', content_id={self.content_id}, share_type='{self.share_type}')>"


class ShareLog(Base, TimestampMixin):
    """分享操作日志"""
    __tablename__ = "share_logs"

    id = Column(Integer, primary_key=True, index=True)
    shared_content_id = Column(Integer, ForeignKey("shared_contents.id"), nullable=False, comment="分享内容ID")
    
    # 操作信息
    action_type = Column(String(50), nullable=False, comment="操作类型: view, click, share, copy_link")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="操作用户ID（匿名用户时为null）")
    user_agent = Column(String(500), nullable=True, comment="用户代理信息")
    ip_address = Column(String(45), nullable=True, comment="IP地址")
    
    # 额外信息
    extra_data = Column(JSON, nullable=True, comment="额外数据（如分享平台信息）")

    # 关系
    shared_content = relationship("SharedContent", back_populates="share_logs")
    user = relationship("User")

    def __repr__(self):
        return f"<ShareLog(id={self.id}, action_type='{self.action_type}', user_id={self.user_id})>"


class ShareTemplate(Base, TimestampMixin, OwnerMixin):
    """分享模板配置"""
    __tablename__ = "share_templates"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin) - 模板创建者ID
    # - created_at, updated_at (from TimestampMixin)

    name = Column(String(100), nullable=False, comment="模板名称")
    description = Column(Text, nullable=True, comment="模板描述")
    
    # 模板配置
    content_types = Column(JSON, nullable=False, comment="支持的内容类型列表")
    share_platforms = Column(JSON, nullable=False, comment="支持的分享平台列表")
    default_settings = Column(JSON, nullable=True, comment="默认分享设置")
    
    # 模板样式
    template_style = Column(JSON, nullable=True, comment="分享样式配置")
    custom_text = Column(Text, nullable=True, comment="自定义分享文案模板")
    
    # 模板状态
    is_system = Column(Boolean, default=False, comment="是否为系统模板")
    is_active = Column(Boolean, default=True, comment="是否启用")

    # 关系
    owner = relationship("User")

    def __repr__(self):
        return f"<ShareTemplate(id={self.id}, name='{self.name}', is_system={self.is_system})>"
