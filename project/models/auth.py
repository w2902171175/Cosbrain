# project/models/auth.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from project.base import Base
from .mixins import TimestampMixin, EmbeddingMixin


class User(Base, TimestampMixin):
    """用户基础模型 - 认证和基本信息"""
    __tablename__ = "users"
    __table_args__ = (
        Index('idx_user_email', 'email'),
        Index('idx_user_username', 'username'),
        Index('idx_user_student_id', 'student_id'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)
    
    # 认证相关字段
    email = Column(String, unique=True, index=True, nullable=True, comment="邮箱")
    username = Column(String, unique=True, index=True, nullable=False, default="新用户", comment="用户名")
    password_hash = Column(String, nullable=True, comment="密码哈希")
    phone_number = Column(String, unique=True, index=True, nullable=True, comment="手机号")
    
    # 基本信息
    student_id = Column(String, unique=True, index=True, nullable=True, comment="学号")
    name = Column(String, index=True, comment="真实姓名")
    avatar_url = Column(String(500), nullable=True, comment="用户头像URL")
    school = Column(String, nullable=True, comment="学校")
    
    # 系统字段
    is_admin = Column(Boolean, default=False, nullable=False, comment="是否管理员")
    total_points = Column(Integer, default=0, nullable=False, comment="用户当前总积分")
    last_login_at = Column(DateTime, nullable=True, comment="用户上次登录时间，用于每日打卡")
    login_count = Column(Integer, default=0, nullable=False, comment="用户总登录天数（完成每日打卡的次数）")

    # 关系
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    # 用户相关关系
    achievements = relationship("UserAchievement", back_populates="user", cascade="all, delete-orphan")
    point_transactions = relationship("PointTransaction", back_populates="user", cascade="all, delete-orphan")
    created_chat_rooms = relationship("ChatRoom", back_populates="creator")
    chat_room_memberships = relationship("ChatRoomMember", back_populates="member")
    sent_join_requests = relationship("ChatRoomJoinRequest", foreign_keys="[ChatRoomJoinRequest.requester_id]",
                                      back_populates="requester")
    processed_join_requests = relationship("ChatRoomJoinRequest", foreign_keys="[ChatRoomJoinRequest.processed_by_id]",
                                           back_populates="processor")

    notes = relationship("Note", back_populates="owner")
    knowledge_bases = relationship("KnowledgeBase", back_populates="owner")
    user_courses = relationship("UserCourse", back_populates="student")
    daily_records = relationship("DailyRecord", back_populates="owner")
    folders = relationship("Folder", back_populates="owner")
    collected_contents = relationship("CollectedContent", back_populates="owner")
    sent_messages = relationship("ChatMessage", back_populates="sender")

    forum_topics = relationship("ForumTopic", back_populates="owner", cascade="all, delete-orphan")
    forum_comments = relationship("ForumComment", back_populates="owner", cascade="all, delete-orphan")
    forum_likes = relationship("ForumLike", back_populates="owner", cascade="all, delete-orphan")
    uploaded_emojis = relationship("ForumEmoji", back_populates="uploader", cascade="all, delete-orphan")
    mentions_made = relationship("ForumMention", foreign_keys="ForumMention.mentioner_id", back_populates="mentioner", cascade="all, delete-orphan")
    mentions_received = relationship("ForumMention", foreign_keys="ForumMention.mentioned_id", back_populates="mentioned", cascade="all, delete-orphan")
    following = relationship("UserFollow", foreign_keys="UserFollow.follower_id", back_populates="follower",
                             cascade="all, delete-orphan")
    followers = relationship("UserFollow", foreign_keys="UserFollow.followed_id", back_populates="followed",
                             cascade="all, delete-orphan")

    mcp_configs = relationship("UserMcpConfig", back_populates="owner", cascade="all, delete-orphan")
    search_engine_configs = relationship("UserSearchEngineConfig", back_populates="owner", cascade="all, delete-orphan")
    llm_configs = relationship("UserLLMConfig", back_populates="owner", cascade="all, delete-orphan")
    uploaded_documents = relationship("KnowledgeDocument", back_populates="owner",
                                      cascade="all, delete-orphan")
    tts_configs = relationship("UserTTSConfig", back_populates="owner", cascade="all, delete-orphan")

    projects_created = relationship("Project", back_populates="creator")

    ai_conversations = relationship("AIConversation", back_populates="user_owner", cascade="all, delete-orphan")
    project_applications = relationship("ProjectApplication", foreign_keys="[ProjectApplication.student_id]",
                                        back_populates="applicant", cascade="all, delete-orphan")
    project_memberships = relationship("ProjectMember", back_populates="member", cascade="all, delete-orphan")
    project_likes = relationship("ProjectLike", back_populates="owner", cascade="all, delete-orphan")
    course_likes = relationship("CourseLike", back_populates="owner", cascade="all, delete-orphan")

    # 推荐系统相关关系
    behaviors = relationship("UserBehavior", back_populates="user", cascade="all, delete-orphan")
    recommendation_logs = relationship("RecommendationLog", back_populates="user", cascade="all, delete-orphan")

    # 分享系统相关关系
    shared_contents = relationship("SharedContent", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', username='{self.username}')>"


class UserProfile(Base, TimestampMixin, EmbeddingMixin):
    """用户详细资料模型 - 技能、兴趣、成就等"""
    __tablename__ = "user_profiles"
    __table_args__ = (
        Index('idx_user_profile_major', 'major'),
        Index('idx_user_profile_location', 'location'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, comment="用户ID")
    
    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)
    # - combined_text, embedding (from EmbeddingMixin)
    
    # 学术和专业信息
    major = Column(String, nullable=True, comment="专业")
    skills = Column(JSONB, nullable=False, server_default='[]', comment="技能列表")
    interests = Column(Text, nullable=True, comment="兴趣爱好")
    bio = Column(Text, default="欢迎使用本平台！", comment="个人简介")
    
    # 成就和经历
    awards_competitions = Column(Text, nullable=True, comment="奖项和竞赛")
    academic_achievements = Column(Text, nullable=True, comment="学术成就")
    soft_skills = Column(Text, nullable=True, comment="软技能")
    portfolio_link = Column(String, nullable=True, comment="作品集链接")
    
    # 工作偏好
    preferred_role = Column(String, nullable=True, comment="偏好角色")
    availability = Column(String, nullable=True, comment="可用性")
    location = Column(String, nullable=True, comment="所在地理位置")

    # 关系
    user = relationship("User", back_populates="profile")

    def __repr__(self):
        return f"<UserProfile(id={self.id}, user_id={self.user_id}, major='{self.major}')>"


class UserSettings(Base, TimestampMixin):
    """用户设置模型 - LLM配置等"""
    __tablename__ = "user_settings"
    __table_args__ = (
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, comment="用户ID")
    
    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)
    
    # LLM配置
    llm_api_type = Column(String, nullable=True, comment="LLM API类型")
    llm_api_key_encrypted = Column(Text, nullable=True, comment="加密的LLM API密钥")
    llm_api_base_url = Column(String, nullable=True, comment="LLM API基础URL")
    llm_model_ids = Column(Text, nullable=True, comment="JSON格式存储多个模型ID")

    # 关系
    user = relationship("User", back_populates="settings")

    def __repr__(self):
        return f"<UserSettings(id={self.id}, user_id={self.user_id}, llm_api_type='{self.llm_api_type}')>"
