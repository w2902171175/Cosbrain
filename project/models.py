# project/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship, remote
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from base import Base


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)

    name = Column(String, index=True)
    major = Column(String)
    skills = Column(Text)
    interests = Column(Text)
    bio = Column(Text)
    awards_competitions = Column(Text)
    academic_achievements = Column(Text)
    soft_skills = Column(Text)
    portfolio_link = Column(String)
    preferred_role = Column(String)
    availability = Column(String)

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    llm_api_type = Column(String, nullable=True)
    llm_api_key_encrypted = Column(Text, nullable=True)
    llm_api_base_url = Column(String, nullable=True)
    llm_model_id = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    notes = relationship("Note", back_populates="owner")
    knowledge_bases = relationship("KnowledgeBase", back_populates="owner")
    knowledge_articles = relationship("KnowledgeArticle", back_populates="author")
    user_courses = relationship("UserCourse", back_populates="student")
    collection_items = relationship("CollectionItem", back_populates="user")
    daily_records = relationship("DailyRecord", back_populates="owner")
    folders = relationship("Folder", back_populates="owner")
    collected_contents = relationship("CollectedContent", back_populates="owner")

    created_chat_rooms = relationship("ChatRoom", back_populates="creator")
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
                                      cascade="all, delete-orphan")  # 用户上传的文档


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    required_skills = Column(Text)
    keywords = Column(String)
    project_type = Column(String)
    expected_deliverables = Column(Text)
    contact_person_info = Column(String)
    learning_outcomes = Column(Text)
    team_size_preference = Column(String)
    project_status = Column(String)

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    chat_room = relationship("ChatRoom", back_populates="project", uselist=False, cascade="all, delete-orphan")


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
    name = Column(String, nullable=False)

    type = Column(String, nullable=False, default="general")

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, unique=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, unique=True)

    creator_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    color = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    messages = relationship("ChatMessage", back_populates="room", cascade="all, delete-orphan")
    project = relationship("Project", back_populates="chat_room")
    course = relationship("Course", back_populates="chat_room")
    creator = relationship("Student", back_populates="created_chat_rooms")


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
        remote_side=[id],
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
    name = Column(String, index=True, nullable=False)  # <--- name 字段明确为非空
    description = Column(Text)
    access_type = Column(String)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="knowledge_bases")
    articles = relationship("KnowledgeArticle", back_populates="knowledge_base", cascade="all, delete-orphan")
    documents = relationship("KnowledgeDocument", back_populates="knowledge_base",
                             cascade="all, delete-orphan")  # 知识库下的文档


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
