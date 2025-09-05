# project/models/recommendation.py
"""
推荐系统相关模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

from project.models.mixins import TimestampMixin
from project.database import Base


class UserBehavior(Base, TimestampMixin):
    """用户行为记录模型"""
    __tablename__ = "user_behaviors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)  # 行为类型
    resource_type = Column(String(50), nullable=False)  # 资源类型
    resource_id = Column(Integer, nullable=False)  # 资源ID
    session_id = Column(String(128))  # 会话ID
    ip_address = Column(String(45))  # IP地址
    user_agent = Column(Text)  # 用户代理
    duration = Column(Integer)  # 持续时间（秒）
    score = Column(Float, default=0.0)  # 行为权重分数
    extra_data = Column(Text)  # 额外元数据（JSON格式）

    # 关系
    user = relationship("User", back_populates="behaviors")

    def __repr__(self):
        return f"<UserBehavior(user_id={self.user_id}, action={self.action_type}, resource={self.resource_type}:{self.resource_id})>"


class RecommendationLog(Base, TimestampMixin):
    """推荐日志模型"""
    __tablename__ = "recommendation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recommendation_type = Column(String(50), nullable=False)  # 推荐类型
    algorithm = Column(String(50), nullable=False)  # 使用的算法
    resource_type = Column(String(50), nullable=False)  # 推荐的资源类型
    resource_id = Column(Integer, nullable=False)  # 推荐的资源ID
    confidence_score = Column(Float, default=0.0)  # 推荐置信度
    position = Column(Integer, default=0)  # 推荐位置
    clicked = Column(Boolean, default=False)  # 是否被点击
    session_id = Column(String(128))  # 会话ID
    extra_data = Column(Text)  # 推荐元数据（JSON格式）

    # 关系
    user = relationship("User", back_populates="recommendation_logs")

    def __repr__(self):
        return f"<RecommendationLog(user_id={self.user_id}, type={self.recommendation_type}, resource={self.resource_type}:{self.resource_id})>"


class KnowledgeItem(Base, TimestampMixin):
    """知识项目模型（用于推荐系统兼容性）"""
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    summary = Column(Text)
    category = Column(String(100))
    tags = Column(Text)  # JSON格式的标签
    difficulty_level = Column(Integer, default=1)  # 难度级别 1-5
    estimated_time = Column(Integer, default=0)  # 预估学习时间（分钟）
    is_published = Column(Boolean, default=True)
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    author_id = Column(Integer, ForeignKey("users.id"))
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"))

    # 关系
    author = relationship("User")
    knowledge_base = relationship("KnowledgeBase")

    def __repr__(self):
        return f"<KnowledgeItem(id={self.id}, title='{self.title}')>"


class ForumPost(Base, TimestampMixin):
    """论坛帖子模型（用于推荐系统兼容性）"""
    __tablename__ = "forum_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    category = Column(String(100))
    tags = Column(Text)  # JSON格式的标签
    is_published = Column(Boolean, default=True)
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    author_id = Column(Integer, ForeignKey("users.id"))
    topic_id = Column(Integer, ForeignKey("forum_topics.id"))

    # 关系
    author = relationship("User")
    topic = relationship("ForumTopic")

    def __repr__(self):
        return f"<ForumPost(id={self.id}, title='{self.title}')>"
