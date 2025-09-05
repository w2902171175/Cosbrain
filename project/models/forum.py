# project/models/forum.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger, Boolean, DECIMAL, Date, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from project.base import Base
from .mixins import TimestampMixin, OwnerMixin, EmbeddingMixin, BaseContentMixin, LikeMixin, MediaMixin


class ForumTopic(Base, TimestampMixin, OwnerMixin, EmbeddingMixin, MediaMixin):
    __tablename__ = "forum_topics"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at, updated_at (from TimestampMixin)
    # - combined_text, embedding (from EmbeddingMixin)
    # - media_url, media_type, original_filename, file_size_bytes (from MediaMixin)

    # ForumTopic特有字段
    title = Column(String, nullable=True, comment="话题标题")
    content = Column(Text, nullable=False, comment="话题内容")

    shared_item_type = Column(String, nullable=True, comment="分享内容类型")
    shared_item_id = Column(Integer, nullable=True, comment="分享内容ID")

    tags = Column(String, nullable=True, comment="话题标签")

    # 新增字段：附件信息JSON和被@用户
    attachments_json = Column(Text, nullable=True, comment="附件信息JSON（支持多个附件）")
    mentioned_users = Column(Text, nullable=True, comment="被@用户ID列表JSON")

    # 统计字段（保持一致性）
    like_count = Column(Integer, default=0, comment="点赞数")
    comment_count = Column(Integer, default=0, comment="评论数")
    view_count = Column(Integer, default=0, comment="浏览量")
    
    # 性能优化新增字段
    last_reply_at = Column(DateTime, nullable=True, comment="最后回复时间")
    status = Column(String(20), default='active', comment="话题状态：active, deleted, hidden")
    
    # 热度分数字段（基于监控脚本）
    heat_score = Column(DECIMAL(10, 2), nullable=True, comment="热度分数（自动计算）")

    owner = relationship("User", back_populates="forum_topics")
    comments = relationship("ForumComment", back_populates="topic", cascade="all, delete-orphan")
    likes = relationship("ForumLike", back_populates="topic", cascade="all, delete-orphan")
    topic_tags = relationship("ForumTopicTag", back_populates="topic", cascade="all, delete-orphan")
    mentions = relationship("ForumMention", back_populates="topic", cascade="all, delete-orphan")
    trending_cache = relationship("ForumTrendingCache", back_populates="topic", cascade="all, delete-orphan")
    
    # 索引管理已移至 performance_indexes.py 统一管理
    # 移除原有的 __table_args__ 中的索引定义以避免重复


class ForumComment(Base, TimestampMixin, MediaMixin):
    __tablename__ = "forum_comments"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("forum_topics.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="评论作者ID（统一使用owner_id）")

    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)
    # - media_url, media_type, original_filename, file_size_bytes (from MediaMixin)

    content = Column(Text, nullable=False)

    # 新增字段：附件信息JSON、表情包数据、被@用户
    attachments_json = Column(Text, nullable=True, comment="附件信息JSON（支持多个附件）")
    emoji_data = Column(Text, nullable=True, comment="表情包数据JSON")
    mentioned_users = Column(Text, nullable=True, comment="被@用户ID列表JSON")

    parent_comment_id = Column(Integer, ForeignKey("forum_comments.id"), nullable=True)

    # 统计字段
    like_count = Column(Integer, default=0, comment="点赞数")
    reply_count = Column(Integer, default=0, comment="回复数量（子评论数）")

    topic = relationship("ForumTopic", back_populates="comments")
    owner = relationship("User", back_populates="forum_comments")

    # START MODIFICATION FOR ForumComment relationships
    # Parent relationship (many-to-one from child to parent)
    parent = relationship(
        "ForumComment",
        remote_side=[id], # 'id' column of the remote side (the parent comment)
        back_populates="children"
        # Removed cascade and single_parent as they are not applicable here
    )
    # Children relationship (one-to-many from parent to child)
    children = relationship(
        "ForumComment",
        back_populates="parent",
        cascade="all, delete-orphan", # Correct place for cascade to delete orphans when parent is deleted
        single_parent=True # A child belongs exclusively to one parent through this relationship
    )
    # END MODIFICATION FOR ForumComment relationships

    likes = relationship("ForumLike", back_populates="comment", cascade="all, delete-orphan")
    mentions = relationship("ForumMention", back_populates="comment", cascade="all, delete-orphan")
    
    # 索引管理已移至 performance_indexes.py 统一管理
    # 移除原有的 __table_args__ 中的索引定义以避免重复


class ForumLike(Base, LikeMixin):
    __tablename__ = "forum_likes"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at (from TimestampMixin)
    
    # ForumLike特有字段 - 支持对话题和评论的点赞
    topic_id = Column(Integer, ForeignKey("forum_topics.id"), nullable=True, comment="点赞的话题ID")
    comment_id = Column(Integer, ForeignKey("forum_comments.id"), nullable=True, comment="点赞的评论ID")

    owner = relationship("User", back_populates="forum_likes")
    topic = relationship("ForumTopic", back_populates="likes")
    comment = relationship("ForumComment", back_populates="likes")
    
    # 索引管理已移至 performance_indexes.py 统一管理
    # 移除原有的 __table_args__ 中的索引定义以避免重复


class UserFollow(Base):
    __tablename__ = "user_follows"

    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    followed_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    followed = relationship("User", foreign_keys=[followed_id], back_populates="followers")
    
    # 性能优化索引（基于监控脚本优化）
    __table_args__ = (
        Index('idx_user_follow_follower', 'follower_id', 'created_at'),
        Index('idx_user_follow_followed', 'followed_id', 'created_at'),
        Index('idx_user_follow_unique', 'follower_id', 'followed_id', unique=True),
        # 关注关系查询优化
        Index('idx_user_follow_mutual', 'follower_id', 'followed_id'),
        # 活跃用户关注统计
        Index('idx_user_follow_activity', 'created_at'),
    )


class ForumEmoji(Base):
    __tablename__ = "forum_emojis"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="表情包名称")
    category = Column(String(50), default='custom', comment="表情包分类")
    url = Column(String(500), nullable=False, comment="表情包OSS URL")
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="上传者用户ID")
    is_system = Column(Boolean, default=False, comment="是否为系统表情包")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    uploader = relationship("User", back_populates="uploaded_emojis")

    # 性能优化索引
    __table_args__ = (
        Index('idx_forum_emoji_category', 'category', 'is_active'),
        Index('idx_forum_emoji_uploader', 'uploader_id', 'created_at'),
        Index('idx_forum_emoji_system', 'is_system', 'is_active'),
        Index('idx_forum_emoji_name', 'name'),
    )


class ForumTopicTag(Base):
    __tablename__ = "forum_topic_tags"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("forum_topics.id"), nullable=False, comment="话题ID")
    tag_name = Column(String(50), nullable=False, comment="标签名称")
    created_at = Column(DateTime, server_default=func.now())

    topic = relationship("ForumTopic", back_populates="topic_tags")

    # 性能优化索引
    __table_args__ = (
        UniqueConstraint('topic_id', 'tag_name', name='unique_topic_tag'),
        Index('idx_forum_topic_tag_name', 'tag_name'),
        Index('idx_forum_topic_tag_topic', 'topic_id'),
        Index('idx_forum_topic_tag_created', 'created_at'),
    )


class ForumMention(Base):
    __tablename__ = "forum_mentions"

    id = Column(Integer, primary_key=True, index=True)
    mentioner_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="提及者用户ID")
    mentioned_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="被提及者用户ID")
    topic_id = Column(Integer, ForeignKey("forum_topics.id"), nullable=True, comment="话题ID（如果在话题中提及）")
    comment_id = Column(Integer, ForeignKey("forum_comments.id"), nullable=True, comment="评论ID（如果在评论中提及）")
    is_read = Column(Boolean, default=False, comment="是否已读")
    created_at = Column(DateTime, server_default=func.now())

    mentioner = relationship("User", foreign_keys=[mentioner_id], back_populates="mentions_made")
    mentioned = relationship("User", foreign_keys=[mentioned_id], back_populates="mentions_received")
    topic = relationship("ForumTopic", back_populates="mentions")
    comment = relationship("ForumComment", back_populates="mentions")

    # 性能优化索引
    __table_args__ = (
        Index('idx_forum_mention_mentioned', 'mentioned_id', 'is_read', 'created_at'),
        Index('idx_forum_mention_mentioner', 'mentioner_id', 'created_at'),
        Index('idx_forum_mention_topic', 'topic_id', 'created_at'),
        Index('idx_forum_mention_comment', 'comment_id', 'created_at'),
        Index('idx_forum_mention_unread', 'mentioned_id', 'is_read'),
    )


class ForumTrendingCache(Base):
    __tablename__ = "forum_trending_cache"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("forum_topics.id"), nullable=False, comment="话题ID")
    hot_score = Column(DECIMAL(10, 2), nullable=False, comment="热度分数")
    time_range = Column(String(20), nullable=False, comment="时间范围: day, week, month, all")
    cache_date = Column(Date, nullable=False, comment="缓存日期")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    topic = relationship("ForumTopic", back_populates="trending_cache")

    # 性能优化索引
    __table_args__ = (
        UniqueConstraint('topic_id', 'time_range', 'cache_date', name='unique_topic_range_date'),
        Index('idx_trending_cache_range_score', 'time_range', 'hot_score', 'cache_date'),
        Index('idx_trending_cache_topic', 'topic_id', 'cache_date'),
        Index('idx_trending_cache_date', 'cache_date'),
        Index('idx_trending_cache_score', 'hot_score', 'cache_date'),
    )


class ForumHotTopicsCache(Base):
    """热门话题缓存表"""
    __tablename__ = "forum_hot_topics_cache"

    id = Column(Integer, primary_key=True, index=True)
    topic_data = Column(JSONB, nullable=False, comment="话题数据JSON")
    heat_score = Column(DECIMAL(10, 2), nullable=False, comment="热度分数")
    cached_at = Column(DateTime, server_default=func.now(), comment="缓存时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")

    # 性能优化索引（基于监控脚本优化）
    __table_args__ = (
        Index('idx_hot_topics_cache_score', 'heat_score', 'cached_at'),
        Index('idx_hot_topics_cache_expires', 'expires_at'),
        Index('idx_hot_topics_cache_valid', 'expires_at', 'heat_score'),
        Index('idx_hot_topics_cache_cleanup', 'expires_at'),
    )







