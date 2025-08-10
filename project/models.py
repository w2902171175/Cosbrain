# project/models.py

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, remote
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.schema import UniqueConstraint
from base import Base
import json


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    username = Column(String, unique=True, index=True, nullable=False, default="新用户")
    phone_number = Column(String, unique=True, index=True, nullable=True)
    school = Column(String, nullable=True)

    name = Column(String, index=True)
    major = Column(String, nullable=True)
    skills = Column(JSONB, nullable=False, server_default='[]')  # 存储技能列表，每个技能包含名称和熟练度
    interests = Column(Text, nullable=True)
    bio = Column(Text, default="欢迎使用本平台！")
    awards_competitions = Column(Text, nullable=True)
    academic_achievements = Column(Text, nullable=True)
    soft_skills = Column(Text, nullable=True)
    portfolio_link = Column(String, nullable=True)
    preferred_role = Column(String, nullable=True)
    availability = Column(String, nullable=True)
    # **<<<<< 新增：学生所在地理位置字段 >>>>>**
    location = Column(String, nullable=True, comment="学生所在地理位置")
    # **<<<<< 新增字段结束 >>>>>**

    combined_text = Column(Text, nullable=True)
    embedding = Column(Vector(1024), nullable=True)

    llm_api_type = Column(String, nullable=True)
    llm_api_key_encrypted = Column(Text, nullable=True)
    llm_api_base_url = Column(String, nullable=True)
    llm_model_id = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    is_admin = Column(Boolean, default=False, nullable=False)

    # Relationships
    created_chat_rooms = relationship("ChatRoom", back_populates="creator")
    chat_room_memberships = relationship("ChatRoomMember", back_populates="member")
    sent_join_requests = relationship("ChatRoomJoinRequest", foreign_keys="[ChatRoomJoinRequest.requester_id]",
                                      back_populates="requester")
    processed_join_requests = relationship("ChatRoomJoinRequest", foreign_keys="[ChatRoomJoinRequest.processed_by_id]",
                                           back_populates="processor")

    notes = relationship("Note", back_populates="owner")
    knowledge_bases = relationship("KnowledgeBase", back_populates="owner")
    knowledge_articles = relationship("KnowledgeArticle", back_populates="author")
    user_courses = relationship("UserCourse", back_populates="student")
    collection_items = relationship("CollectionItem", back_populates="user")
    daily_records = relationship("DailyRecord", back_populates="owner")
    folders = relationship("Folder", back_populates="owner")
    collected_contents = relationship("CollectedContent", back_populates="owner")
    sent_messages = relationship("ChatMessage", back_populates="sender")

    forum_topics = relationship("ForumTopic", back_populates="owner", cascade="all, delete-orphan")
    forum_comments = relationship("ForumComment", back_populates="owner", cascade="all, delete-orphan")
    forum_likes = relationship("ForumLike", back_populates="owner", cascade="all, delete-orphan")
    following = relationship("UserFollow", foreign_keys="UserFollow.follower_id", back_populates="follower",
                             cascade="all, delete-orphan")
    followers = relationship("UserFollow", foreign_keys="UserFollow.followed_id", back_populates="followed",
                             cascade="all, delete-orphan")

    mcp_configs = relationship("UserMcpConfig", back_populates="owner", cascade="all, delete-orphan")
    search_engine_configs = relationship("UserSearchEngineConfig", back_populates="owner", cascade="all, delete-orphan")
    uploaded_documents = relationship("KnowledgeDocument", back_populates="owner",
                                      cascade="all, delete-orphan")

    projects_created = relationship("Project", back_populates="creator")

    def __repr__(self):
        return f"<Student(id={self.id}, email='{self.email}', username='{self.username}')>"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    required_skills = Column(JSONB, nullable=False, server_default='[]')  # 存储所需技能列表，每个技能包含名称和熟练度
    required_roles = Column(JSONB, nullable=False, server_default='[]') # 存储项目所需角色列表，例如 ["后端开发", "UI/UX 设计"]
    keywords = Column(String)
    project_type = Column(String)
    expected_deliverables = Column(Text)
    contact_person_info = Column(String)
    learning_outcomes = Column(Text)
    team_size_preference = Column(String)
    project_status = Column(String)

    start_date = Column(DateTime, nullable=True, comment="项目开始日期")
    end_date = Column(DateTime, nullable=True, comment="项目结束日期")
    estimated_weekly_hours = Column(Integer, nullable=True, comment="项目估计每周所需投入小时数")
    # **<<<<< 新增：项目所在地理位置字段 >>>>>**
    location = Column(String, nullable=True, comment="项目所在地理位置")
    # **<<<<< 新增字段结束 >>>>>**

    creator_id = Column(Integer, ForeignKey("students.id"), nullable=False)  # 外键关联到 Student 表

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    chat_room = relationship("ChatRoom", back_populates="project", uselist=False, cascade="all, delete-orphan")
    creator = relationship("Student", back_populates="projects_created")

    def __repr__(self):
        return f"<Project(id={self.id}, title='{self.title}')>"


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"))
    title = Column(String)
    content = Column(Text)
    note_type = Column(String)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    tags = Column(String)

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="notes")
    course = relationship("Course", back_populates="notes_made")


class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"))

    content = Column(Text, nullable=False)
    mood = Column(String, nullable=True)
    tags = Column(String, nullable=True)

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="daily_records")


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"))

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)
    order = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    children = relationship(
        "Folder",
        primaryjoin="Folder.parent_id == remote(Folder.id)",
        back_populates="parent",
        cascade="all, delete-orphan",
        single_parent=True
    )
    parent = relationship(
        "Folder",
        primaryjoin="Folder.id == remote(Folder.parent_id)",
        back_populates="children"
    )

    collected_contents = relationship("CollectedContent", back_populates="folder", cascade="all, delete-orphan")

    owner = relationship("Student", back_populates="folders")


class CollectedContent(Base):
    __tablename__ = "collected_contents"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"))
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)

    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    url = Column(String, nullable=True)
    content = Column(Text, nullable=True)
    tags = Column(String, nullable=True)
    priority = Column(Integer, default=3)
    notes = Column(Text, nullable=True)
    access_count = Column(Integer, default=0)
    is_starred = Column(Boolean, default=False)
    thumbnail = Column(String, nullable=True)
    author = Column(String, nullable=True)
    duration = Column(String, nullable=True)
    file_size = Column(String, nullable=True)
    status = Column(String, default="active")

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="collected_contents")
    folder = relationship("Folder", back_populates="collected_contents")


class ChatRoom(Base):
    __tablename__ = "chat_rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    type = Column(String, nullable=False, default="general")

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, unique=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, unique=True)

    creator_id = Column(Integer, ForeignKey("students.id"), nullable=False)  # 群主字段

    color = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    messages = relationship("ChatMessage", back_populates="room", cascade="all, delete-orphan")
    project = relationship("Project", back_populates="chat_room")
    course = relationship("Course", back_populates="chat_room")
    creator = relationship("Student", back_populates="created_chat_rooms")
    memberships = relationship("ChatRoomMember", back_populates="room", cascade="all, delete-orphan")
    join_requests = relationship("ChatRoomJoinRequest", back_populates="room", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    content_text = Column(Text, nullable=False)
    message_type = Column(String, default="text")

    media_url = Column(String, nullable=True)

    sent_at = Column(DateTime, server_default=func.now())

    room = relationship("ChatRoom", back_populates="messages")
    sender = relationship("Student", back_populates="sent_messages")


# --- 聊天室成员模型 ---
class ChatRoomMember(Base):
    __tablename__ = "chat_room_members"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)

    # 角色类型： 'admin' (管理员), 'member' (普通成员)
    # 'creator' 角色将通过 ChatRoom.creator_id 直接关联。
    role = Column(String, default="member", nullable=False)

    # 成员状态： 'active' (活跃), 'banned' (被踢出/禁用), 'left' (已离开)
    status = Column(String, default="active", nullable=False)

    joined_at = Column(DateTime, default=func.now(), nullable=False)
    # last_read_at = Column(DateTime, nullable=True) # 可选：用于跟踪未读消息，如果需要可以添加

    # Relationships
    room = relationship("ChatRoom", back_populates="memberships")
    member = relationship("Student", back_populates="chat_room_memberships")

    __table_args__ = (
        # 确保一个用户在一个聊天室中只有一条成员记录
        UniqueConstraint('room_id', 'member_id', name='_room_member_uc'),
    )


# --- 聊天室加入请求模型 ---
class ChatRoomJoinRequest(Base):
    __tablename__ = "chat_room_join_requests"
    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("chat_rooms.id"), nullable=False, index=True)
    requester_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    reason = Column(String, nullable=True)  # 用户申请的理由

    # 状态：'pending' (待处理), 'approved' (已批准), 'rejected' (已拒绝)
    status = Column(String, default="pending", nullable=False)

    requested_at = Column(DateTime, default=func.now(), nullable=False)
    processed_by_id = Column(Integer, ForeignKey("students.id"), nullable=True)  # 谁处理的这个请求
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    room = relationship("ChatRoom", back_populates="join_requests")  # 新增 back_populates
    requester = relationship("Student", foreign_keys=[requester_id], back_populates="sent_join_requests")
    processor = relationship("Student", foreign_keys=[processed_by_id], back_populates="processed_join_requests")

    __table_args__ = (
        # 确保一个用户在一个聊天室中最多只有一个 'pending' 状态的申请
        # 这是 PostgreSQL 特性，对于 SQLite 可能需要弱化此约束或手动管理
        Index('_room_requester_pending_uc', 'room_id', 'requester_id', unique=True,
              postgresql_where=text("status = 'pending'")),
    )


class ForumTopic(Base):
    __tablename__ = "forum_topics"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)

    shared_item_type = Column(String, nullable=True)
    shared_item_id = Column(Integer, nullable=True)

    tags = Column(String, nullable=True)

    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    views_count = Column(Integer, default=0)

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="forum_topics")
    comments = relationship("ForumComment", back_populates="topic", cascade="all, delete-orphan")
    likes = relationship("ForumLike", back_populates="topic", cascade="all, delete-orphan")


class ForumComment(Base):
    __tablename__ = "forum_comments"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("forum_topics.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    content = Column(Text, nullable=False)

    parent_comment_id = Column(Integer, ForeignKey("forum_comments.id"), nullable=True)

    likes_count = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    topic = relationship("ForumTopic", back_populates="comments")
    owner = relationship("Student", back_populates="forum_comments")

    parent = relationship(
        "ForumComment",
        remote_side=[id],  # 确保这里的 id 指向的是本类的 id 列
        primaryjoin="ForumComment.parent_comment_id == remote(ForumComment.id)",
        back_populates="children",
        cascade="all, delete-orphan",
        single_parent=True
    )
    children = relationship(
        "ForumComment",
        primaryjoin="ForumComment.id == remote(ForumComment.parent_comment_id)",
        back_populates="parent"
    )

    likes = relationship("ForumLike", back_populates="comment", cascade="all, delete-orphan")


class ForumLike(Base):
    __tablename__ = "forum_likes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    topic_id = Column(Integer, ForeignKey("forum_topics.id"), nullable=True)
    comment_id = Column(Integer, ForeignKey("forum_comments.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("Student", back_populates="forum_likes")
    topic = relationship("ForumTopic", back_populates="likes")
    comment = relationship("ForumComment", back_populates="likes")


class UserFollow(Base):
    __tablename__ = "user_follows"

    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    followed_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    follower = relationship("Student", foreign_keys=[follower_id], back_populates="following")
    followed = relationship("Student", foreign_keys=[followed_id], back_populates="followers")


class UserMcpConfig(Base):
    __tablename__ = "user_mcp_configs"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    name = Column(String, nullable=False)
    mcp_type = Column(String, nullable=True)
    base_url = Column(String, nullable=False)
    protocol_type = Column(String, nullable=True)
    api_key_encrypted = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="mcp_configs")


class UserSearchEngineConfig(Base):
    __tablename__ = "user_search_engine_configs"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    name = Column(String, nullable=False)
    engine_type = Column(String, nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="search_engine_configs")


# --- 知识库相关模型 ---
class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"))
    name = Column(String, index=True, nullable=False)
    description = Column(Text)
    access_type = Column(String)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="knowledge_bases")
    articles = relationship("KnowledgeArticle", back_populates="knowledge_base", cascade="all, delete-orphan")
    documents = relationship("KnowledgeDocument", back_populates="knowledge_base",
                             cascade="all, delete-orphan")


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"))
    author_id = Column(Integer, ForeignKey("students.id"))
    title = Column(String, index=True)
    content = Column(Text)
    version = Column(String)
    tags = Column(String)

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    knowledge_base = relationship("KnowledgeBase", back_populates="articles")
    author = relationship("Student", back_populates="knowledge_articles")


# --- KnowledgeDocument (for uploaded files) ---
class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)

    status = Column(String, default="processing")
    processing_message = Column(Text, nullable=True)
    total_chunks = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    owner = relationship("Student", back_populates="uploaded_documents")
    chunks = relationship("KnowledgeDocumentChunk", back_populates="document", cascade="all, delete-orphan")


# --- KnowledgeDocumentChunk (for RAG) ---
class KnowledgeDocumentChunk(Base):
    __tablename__ = "knowledge_document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)

    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())

    document = relationship("KnowledgeDocument", back_populates="chunks")


# --- 课程相关模型 ---
class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    instructor = Column(String)
    category = Column(String)
    total_lessons = Column(Integer)
    avg_rating = Column(Float)

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    notes_made = relationship("Note", back_populates="course")
    user_courses = relationship("UserCourse", back_populates="course")
    chat_room = relationship("ChatRoom", back_populates="course", uselist=False, cascade="all, delete-orphan")


class UserCourse(Base):
    __tablename__ = "user_courses"

    student_id = Column(Integer, ForeignKey("students.id"), primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), primary_key=True)
    progress = Column(Float, default=0.0)
    status = Column(String, default="in_progress")
    last_accessed = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    student = relationship("Student", back_populates="user_courses")
    course = relationship("Course", back_populates="user_courses")


# --- 旧的 CollectionItem (可以考虑未来删除或重构到 CollectedContent) ---
class CollectionItem(Base):
    __tablename__ = "collection_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("students.id"))
    item_type = Column(String)
    item_id = Column(Integer)

    created_at = Column(DateTime, server_default=func.now())

    user = relationship("Student", back_populates="collection_items")
