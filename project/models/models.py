# project/models/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, text, Index, UniqueConstraint, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, remote
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from sqlalchemy.schema import UniqueConstraint
from base import Base
from sqlalchemy import event
import asyncio
from typing import Optional
import json
from datetime import datetime
import oss_utils


class ProjectApplication(Base):
    __tablename__ = "project_applications"
    __table_args__ = (
        # 确保同一学生对同一项目只有一条待处理或已批准的申请记录
        UniqueConstraint("project_id", "student_id", name="_project_student_application_uc"),
        {'extend_existing': True}  # 允许重新定义表结构，避免MetaData重复定义错误
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True, comment="申请项目ID")
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True, comment="申请学生ID")

    status = Column(String, default="pending", nullable=False, comment="申请状态: pending, approved, rejected")
    message = Column(Text, nullable=True, comment="申请留言")

    applied_at = Column(DateTime, server_default=func.now(), nullable=False, comment="申请提交时间")
    processed_at = Column(DateTime, nullable=True, comment="申请处理时间")
    processed_by_id = Column(Integer, ForeignKey("students.id"), nullable=True, comment="审批者ID")

    # Relationships
    project = relationship("Project", back_populates="applications")
    applicant = relationship("Student", foreign_keys=[student_id], back_populates="project_applications")
    processor = relationship("Student", foreign_keys=[processed_by_id])  # 审批者


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        # 确保同一学生在同一项目下只有一条成员记录
        UniqueConstraint("project_id", "student_id", name="_project_student_member_uc"),
        {'extend_existing': True}  # 允许重新定义表结构，避免MetaData重复定义错误
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True, comment="所属项目ID")
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True, comment="成员学生ID")

    role = Column(String, default="member", nullable=False, comment="成员角色: admin, member")  # 项目管理员或普通成员
    status = Column(String, default="active", nullable=False,
                    comment="成员状态: active (活跃), inactive (不活跃), removed (被移除)")
    joined_at = Column(DateTime, server_default=func.now(), nullable=False, comment="加入时间")

    # Relationships
    project = relationship("Project", back_populates="members")
    member = relationship("Student", back_populates="project_memberships")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = {'extend_existing': True}  # 允许重新定义表结构，避免MetaData重复定义错误

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    username = Column(String, unique=True, index=True, nullable=False, default="新用户")
    phone_number = Column(String, unique=True, index=True, nullable=True)
    school = Column(String, nullable=True)

    name = Column(String, index=True)
    major = Column(String, nullable=True)
    skills = Column(JSONB, nullable=False, server_default='[]')
    interests = Column(Text, nullable=True)
    bio = Column(Text, default="欢迎使用本平台！")
    awards_competitions = Column(Text, nullable=True)
    academic_achievements = Column(Text, nullable=True)
    soft_skills = Column(Text, nullable=True)
    portfolio_link = Column(String, nullable=True)
    preferred_role = Column(String, nullable=True)
    availability = Column(String, nullable=True)
    location = Column(String, nullable=True, comment="学生所在地理位置")

    combined_text = Column(Text, nullable=True)
    embedding = Column(Vector(1024), nullable=True)

    llm_api_type = Column(String, nullable=True)
    llm_api_key_encrypted = Column(Text, nullable=True)
    llm_api_base_url = Column(String, nullable=True)
    llm_model_id = Column(String, nullable=True)  # 保留原字段以兼容性
    llm_model_ids = Column(Text, nullable=True)  # 新字段：JSON格式存储多个模型ID

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    is_admin = Column(Boolean, default=False, nullable=False)

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
    tts_configs = relationship("UserTTSConfig", back_populates="owner", cascade="all, delete-orphan")

    projects_created = relationship("Project", back_populates="creator")

    total_points = Column(Integer, default=0, nullable=False, comment="用户当前总积分")
    last_login_at = Column(DateTime, nullable=True, comment="用户上次登录时间，用于每日打卡")
    login_count = Column(Integer, default=0, nullable=False,
                         comment="用户总登录天数（完成每日打卡的次数）")

    ai_conversations = relationship("AIConversation", back_populates="user_owner", cascade="all, delete-orphan")
    project_applications = relationship("ProjectApplication", foreign_keys=[ProjectApplication.student_id],
                                        back_populates="applicant", cascade="all, delete-orphan")
    project_memberships = relationship("ProjectMember", back_populates="member", cascade="all, delete-orphan")
    project_likes = relationship("ProjectLike", back_populates="owner", cascade="all, delete-orphan")
    course_likes = relationship("CourseLike", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Student(id={self.id}, email='{self.email}', username='{self.username}')>"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    required_skills = Column(JSONB, nullable=False, server_default='[]')  # 存储所需技能列表，每个技能包含名称和熟练度
    required_roles = Column(JSONB, nullable=False, server_default='[]') # 存储项目所需角色列表
    keywords = Column(String)
    project_type = Column(String)
    expected_deliverables = Column(Text)
    contact_person_info = Column(String)
    learning_outcomes = Column(Text)
    team_size_preference = Column(String)
    project_status = Column(String)
    likes_count = Column(Integer, default=0, comment="点赞数量")

    start_date = Column(DateTime, nullable=True, comment="项目开始日期")
    end_date = Column(DateTime, nullable=True, comment="项目结束日期")
    estimated_weekly_hours = Column(Integer, nullable=True, comment="项目估计每周所需投入小时数")
    location = Column(String, nullable=True, comment="项目所在地理位置")

    creator_id = Column(Integer, ForeignKey("students.id"), nullable=False)  # 外键关联到 Student 表

    cover_image_url = Column(String, nullable=True, comment="项目封面图片的OSS URL")
    cover_image_original_filename = Column(String, nullable=True, comment="原始上传的封面图片文件名")
    cover_image_type = Column(String, nullable=True, comment="封面图片MIME类型，例如 'image/jpeg'")
    cover_image_size_bytes = Column(BigInteger, nullable=True, comment="封面图片文件大小（字节）")

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    chat_room = relationship("ChatRoom", back_populates="project", uselist=False, cascade="all, delete-orphan")
    creator = relationship("Student", back_populates="projects_created")
    applications = relationship("ProjectApplication", back_populates="project", cascade="all, delete-orphan")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    likes = relationship("ProjectLike", back_populates="project", cascade="all, delete-orphan")
    # --- 新增关系：一个项目可以有多个项目文件 ---
    project_files = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    # --- 新增关系结束 ---

    def __repr__(self):
        return f"<Project(id={self.id}, title='{self.title}')>"


# --- 新增：项目文件模型 ---
class ProjectFile(Base):
    __tablename__ = "project_files"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True, comment="所属项目ID")
    upload_by_id = Column(Integer, ForeignKey("students.id"), nullable=False, comment="文件上传者ID")

    file_name = Column(String, nullable=False, comment="原始上传文件名")
    oss_object_name = Column(String, nullable=False, unique=True, comment="文件在OSS中的对象名称（唯一）")
    file_path = Column(String, nullable=False, comment="文件在OSS上的完整URL")
    file_type = Column(String, nullable=True, comment="文件的MIME类型，例如 'application/pdf', 'application/vnd.ms-excel'")
    size_bytes = Column(BigInteger, nullable=True, comment="文件大小（字节）")
    description = Column(Text, nullable=True, comment="文件描述")
    # 访问类型：'public' (所有用户可见), 'member_only' (仅项目成员可见)
    access_type = Column(String, default="member_only", nullable=False, comment="文件访问权限")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    project = relationship("Project", back_populates="project_files")
    uploader = relationship("Student", backref="uploaded_project_files")

    def __repr__(self):
        return f"<ProjectFile(id={self.id}, project_id={self.project_id}, file_name='{self.file_name}')>"

# --- 事件监听器：在 ProjectFile 记录删除时，从 OSS 删除对应的文件 ---
@event.listens_for(ProjectFile, 'before_delete')
def receive_before_delete_project_file(mapper, connection, target: ProjectFile):
    """
    在 ProjectFile 记录删除之前，从 OSS 删除对应的文件。
    """
    oss_object_name = target.oss_object_name
    if oss_object_name:
        print(f"DEBUG_OSS_DELETE_EVENT: 准备删除 OSS 项目文件: {oss_object_name} (关联 ProjectFile ID: {target.id})")
        # 异步删除文件，不阻塞数据库事务
        asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name))
    else:
        print(f"WARNING_OSS_DELETE_EVENT: ProjectFile ID: {target.id} 没有关联的 OSS 对象名称，跳过 OSS 文件删除。")
# --- 新增 ProjectFile 模型结束 ---


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"))
    title = Column(String)
    content = Column(Text)
    note_type = Column(String)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True)
    tags = Column(String)

    # 章节信息字段
    chapter = Column(String, nullable=True, comment="课程章节信息，例如：第一章 - AI概述")

    # 媒体文件相关字段
    media_url = Column(String, nullable=True, comment="笔记中嵌入的图片、视频或文件的OSS URL")
    media_type = Column(String, nullable=True, comment="媒体类型：'image', 'video', 'file'")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    media_size_bytes = Column(BigInteger, nullable=True, comment="媒体文件大小（字节）")
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True, comment="用户自定义文件夹ID")

    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="notes")
    course = relationship("Course", back_populates="notes_made")
    folder = relationship("Folder", back_populates="notes")


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

    # START MODIFICATION FOR Folder relationships
    children = relationship(
        "Folder",
        # Remove primaryjoin and rely on foreign key constraint and back_populates
        back_populates="parent",
        cascade="all, delete-orphan", # Correctly cascade deletion for children
        single_parent=True # Correctly mark children as exclusively tied to this parent
    )
    parent = relationship(
        "Folder",
        remote_side=[id],  # Explicitly state that 'id' of the remote Folder (parent) is the target
        back_populates="children"
    )
    # END MODIFICATION FOR Folder relationships

    collected_contents = relationship("CollectedContent", back_populates="folder", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="folder", cascade="all, delete-orphan")

    owner = relationship("Student", back_populates="folders")


class CollectedContent(Base):
    __tablename__ = "collected_contents"

    # 确保同一用户不能重复收藏同一个共享实体
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "shared_item_type", "shared_item_id",
            name="_owner_shared_item_uc"
        ),
        # 为 title + owner_id 添加唯一约束，如果要求收藏标题在用户维度唯一
        # UniqueConstraint("owner_id", "title", name="_owner_title_uc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"))
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)

    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    url = Column(String, nullable=True, comment="收藏内容的URL，可以是外部链接或OSS文件URL")
    content = Column(Text, nullable=True)
    tags = Column(String, nullable=True)
    priority = Column(Integer, default=3)
    notes = Column(Text, nullable=True)
    access_count = Column(Integer, default=0)
    is_starred = Column(Boolean, default=False)
    thumbnail = Column(String, nullable=True)
    author = Column(String, nullable=True)
    duration = Column(String, nullable=True)
    file_size = Column(BigInteger, nullable=True, comment="文件大小（字节，适用于OSS文件）")
    status = Column(String, default="active")

    access_count = Column(Integer, default=0, nullable=False, comment="访问（查看）次数")
    shared_item_type = Column(String, nullable=True,
                              comment="如果收藏平台内部内容，记录其类型（例如'project', 'course', 'forum_topic', 'note', 'daily_record', 'knowledge_article', 'chat_message'）")
    shared_item_id = Column(Integer, nullable=True, comment="如果收藏平台内部内容，记录其ID")

    combined_text = Column(Text, nullable=True, comment="用于AI模型嵌入的组合文本")
    embedding = Column(Vector(1024), nullable=True, comment="文本内容的嵌入向量")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
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

    media_url = Column(String, nullable=True, comment="媒体文件OSS URL或外部链接")

    sent_at = Column(DateTime, server_default=func.now())
    deleted_at = Column(DateTime, nullable=True, comment="消息删除时间，为空表示未删除")

    room = relationship("ChatRoom", back_populates="messages")
    sender = relationship("Student", back_populates="sent_messages")


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
    last_read_at = Column(DateTime, nullable=True)

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
    reason = Column(String, nullable=True)

    # 状态：'pending' (待处理), 'approved' (已批准), 'rejected' (已拒绝)
    status = Column(String, default="pending", nullable=False)

    requested_at = Column(DateTime, default=func.now(), nullable=False)
    processed_by_id = Column(Integer, ForeignKey("students.id"), nullable=True)  # 谁处理的这个请求
    processed_at = Column(DateTime, nullable=True)

    room = relationship("ChatRoom", back_populates="join_requests")
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

    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)

    shared_item_type = Column(String, nullable=True)
    shared_item_id = Column(Integer, nullable=True)

    tags = Column(String, nullable=True)

    media_url = Column(String, nullable=True, comment="图片、视频或文件的OSS URL")
    media_type = Column(String, nullable=True, comment="媒体类型：'image', 'video', 'file'")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    media_size_bytes = Column(BigInteger, nullable=True, comment="媒体文件大小（字节）")

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

    media_url = Column(String, nullable=True, comment="图片、视频或文件的OSS URL")
    media_type = Column(String, nullable=True, comment="媒体类型：'image', 'video', 'file'")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    media_size_bytes = Column(BigInteger, nullable=True, comment="媒体文件大小（字节）")

    likes_count = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    topic = relationship("ForumTopic", back_populates="comments")
    owner = relationship("Student", back_populates="forum_comments")

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



class ProjectLike(Base):
    __tablename__ = "project_likes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False, comment="点赞者ID")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, comment="被点赞项目ID")

    created_at = Column(DateTime, server_default=func.now(), comment="点赞时间")

    owner = relationship("Student", back_populates="project_likes")
    project = relationship("Project", back_populates="likes")

    __table_args__ = (
        UniqueConstraint('owner_id', 'project_id', name='_project_like_uc'), # 确保一个用户不会重复点赞同一个项目
    )

class CourseLike(Base):
    __tablename__ = "course_likes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False, comment="点赞者ID")
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, comment="被点赞课程ID")

    created_at = Column(DateTime, server_default=func.now(), comment="点赞时间")

    owner = relationship("Student", back_populates="course_likes")
    course = relationship("Course", back_populates="likes")

    __table_args__ = (
        UniqueConstraint('owner_id', 'course_id', name='_course_like_uc'), # 确保一个用户不会重复点赞同一个课程
    )


class AIConversationMessage(Base):
    __tablename__ = "ai_conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), nullable=False, index=True,
                             comment="所属对话ID")

    # 消息角色: "user" (用户输入), "assistant" (LLM回答), "tool_call" (LLM决定调用工具), "tool_output" (工具执行结果)
    role = Column(String, nullable=False, comment="消息角色")
    content = Column(Text, nullable=False, comment="消息内容（文本）")

    # 存储工具调用和工具输出的原始JSON数据，以便更详细的记录和回放
    tool_calls_json = Column(JSONB, nullable=True, comment="如果角色是'tool_call'，存储工具调用的JSON数据")
    tool_output_json = Column(JSONB, nullable=True, comment="如果角色是'tool_output'，存储工具输出的JSON数据")

    # 存储本次消息生成时使用的LLM信息（如果角色是 assistant）
    llm_type_used = Column(String, nullable=True, comment="本次消息使用的LLM类型")
    llm_model_used = Column(String, nullable=True, comment="本次消息使用的LLM模型ID")

    sent_at = Column(DateTime, server_default=func.now(), nullable=False, comment="消息发送时间")

    conversation = relationship("AIConversation", back_populates="messages")

    def to_dict(self):
        """将AIConversationMessage对象转换为字典，用于LLM调用"""
        data = {
            "role": self.role,
            "content": self.content
        }
        if self.tool_calls_json:
            data["tool_calls_json"] = self.tool_calls_json
        if self.tool_output_json:
            data["tool_output_json"] = self.tool_output_json
        return data

    def __repr__(self):
        return f"<AIConversationMessage(id={self.id}, role='{self.role}', conv_id={self.conversation_id}, sent_at='{self.sent_at}')>"



class AIConversationTemporaryFile(Base):
    __tablename__ = "ai_conversation_temporary_files"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), nullable=False, index=True,
                             comment="所属AI对话的ID")
    oss_object_name = Column(String, nullable=False, comment="文件在OSS中的对象名称")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    file_type = Column(String, nullable=False, comment="文件MIME类型")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


    extracted_text = Column(Text, nullable=True, comment="从文件中提取的文本内容，用于RAG")
    embedding = Column(Vector(1024), nullable=True, comment="提取文本的嵌入向量")
    status = Column(String, default="pending", nullable=False, comment="处理状态：'pending', 'processing', 'completed', 'failed'")
    processing_message = Column(Text, nullable=True, comment="处理状态消息")

    conversation = relationship("AIConversation", back_populates="temp_files")

    __table_args__ = (
        # 确保同一个对话中，OSS对象名称是唯一的，防止重复记录
        UniqueConstraint('conversation_id', 'oss_object_name', name='_conv_temp_file_uc'),
    )

    def __repr__(self):
        return f"<AIConversationTemporaryFile(id={self.id}, conv_id={self.conversation_id}, filename='{self.original_filename}', status='{self.status}')>"


@event.listens_for(AIConversationTemporaryFile, 'before_delete')
def receive_before_delete(mapper, connection, target: AIConversationTemporaryFile):
    """
    在 AIConversationTemporaryFile 记录删除之前，从 OSS 删除对应的文件。
    """
    oss_object_name = target.oss_object_name
    if oss_object_name:
        print(f"DEBUG_OSS_DELETE_EVENT: 准备删除 OSS 文件: {oss_object_name} (关联 AI 临时文件 ID: {target.id})")
        # 异步删除文件，不阻塞数据库事务
        # 注意：这里是同步事件监听器，调用异步函数需要用 asyncio.create_task()
        asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name))
    else:
        print(f"WARNING_OSS_DELETE_EVENT: AI 临时文件 ID: {target.id} 没有关联的 OSS 对象名称，跳过 OSS 文件删除。")


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True, comment="对话所属用户ID")
    title = Column(String, nullable=True, comment="对话标题（可由AI生成或用户自定义）")

    created_at = Column(DateTime, server_default=func.now(), nullable=False, comment="对话创建时间")
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
                          comment="对话最后更新时间")

    user_owner = relationship("Student", back_populates="ai_conversations")
    messages = relationship("AIConversationMessage", back_populates="conversation",
                            order_by="AIConversationMessage.sent_at", cascade="all, delete-orphan")
    temp_files = relationship("AIConversationTemporaryFile", back_populates="conversation",
                              cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AIConversation(id={self.id}, user_id={self.user_id}, title='{self.title[:20] if self.title else ''}')>"


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
    base_url = Column(String, nullable=True, comment="搜索引擎API的基础URL")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="search_engine_configs")


class UserTTSConfig(Base):
    __tablename__ = "user_tts_configs"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    name = Column(String, nullable=False, comment="TTS配置名称，如：'我的OpenAI语音'")
    tts_type = Column(String, nullable=False, comment="语音提供商类型，如：'openai', 'gemini', 'aliyun'")
    api_key_encrypted = Column(Text, nullable=True, comment="加密后的API密钥")
    base_url = Column(String, nullable=True, comment="API基础URL")
    model_id = Column(String, nullable=True, comment="语音模型ID，如：'tts-1', 'gemini-pro'")
    voice_name = Column(String, nullable=True, comment="语音名称或ID，如：'alloy', 'f_cn_zh_anqi_a_f'")
    is_active = Column(Boolean, default=False, nullable=False, comment="是否当前激活的TTS配置")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("Student", back_populates="tts_configs")

    __table_args__ = (
        UniqueConstraint('owner_id', 'name', name='_owner_id_tts_config_name_uc'),
        # 同一个用户下配置名称唯一
        # 注意：为了确保每个用户只有一个激活的TTS配置，需要在应用层面处理
        # UniqueConstraint('owner_id', 'is_active', name='_owner_id_active_tts_config_uc'),
    )


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
    kb_folders = relationship("KnowledgeBaseFolder", back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeBaseFolder(Base):
    __tablename__ = "knowledge_base_folders"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, index=True, comment="所属知识库ID")
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True,
                      comment="文件夹所有者ID (与知识库所有者相同)")

    name = Column(String, nullable=False, comment="文件夹名称")
    description = Column(Text, nullable=True, comment="文件夹描述")

    parent_id = Column(Integer, ForeignKey("knowledge_base_folders.id"), nullable=True, index=True,
                       comment="父文件夹ID")
    order = Column(Integer, default=0, comment="排序")

    linked_folder_type = Column(String, nullable=True,
                                comment="链接到的外部文件夹类型：'note_folder'（课程笔记文件夹）或'collected_content_folder'（收藏文件夹）")
    linked_folder_id = Column(BigInteger, nullable=True, comment="链接到的外部文件夹ID")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="kb_folders")
    owner = relationship("Student")

    # START MODIFICATION FOR KnowledgeBaseFolder relationships
    children = relationship(
        "KnowledgeBaseFolder",
        back_populates="parent",
        cascade="all, delete-orphan", # Correctly cascade deletion for children
        single_parent=True # Correctly mark children as exclusively tied to this parent
    )
    parent = relationship(
        "KnowledgeBaseFolder",
        remote_side=[id], # Explicitly state that 'id' of the remote KnowledgeBaseFolder (parent) is the target
        back_populates="children"
    )
    # END MODIFICATION FOR KnowledgeBaseFolder relationships

    articles = relationship("KnowledgeArticle", back_populates="kb_folder", cascade="all, delete-orphan")
    documents = relationship("KnowledgeDocument", back_populates="kb_folder", cascade="all, delete-orphan")

    __table_args__ = (
        Index('_kb_folder_name_unique_idx', 'kb_id', 'parent_id', 'name', unique=True,
              postgresql_where=text("parent_id IS NOT NULL AND linked_folder_type IS NULL")),
        Index('_kb_folder_root_name_unique_idx', 'kb_id', 'name', unique=True,
              postgresql_where=text("parent_id IS NULL AND linked_folder_type IS NULL")),
        Index('_kb_folder_linked_unique_idx', 'kb_id', 'linked_folder_type', 'linked_folder_id', unique=True,
              postgresql_where=text("linked_folder_type IS NOT NULL AND linked_folder_id IS NOT NULL")),
    )


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"))
    author_id = Column(Integer, ForeignKey("students.id"))
    title = Column(String, index=True)
    content = Column(Text)
    version = Column(String)
    tags = Column(String)

    kb_folder_id = Column(Integer, ForeignKey("knowledge_base_folders.id"), nullable=True, index=True,
                          comment="所属知识库文件夹ID")
    combined_text = Column(Text)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    knowledge_base = relationship("KnowledgeBase", back_populates="articles")
    author = relationship("Student", back_populates="knowledge_articles")
    kb_folder = relationship("KnowledgeBaseFolder", back_populates="articles")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)
    
    # 新增字段：内容类型分类
    content_type = Column(String, nullable=False, default="file", 
                         comment="内容类型: file, image, video, url, website")
    
    # 新增字段：用于网址和网站类型
    url = Column(Text, nullable=True, comment="网址URL（用于url和website类型）")
    website_title = Column(String, nullable=True, comment="网站标题")
    website_description = Column(Text, nullable=True, comment="网站描述")
    
    # 新增字段：文件大小和其他元数据
    file_size = Column(BigInteger, nullable=True, comment="文件大小（字节）")
    mime_type = Column(String, nullable=True, comment="MIME类型")
    
    # 新增字段：缩略图（用于图片和视频）
    thumbnail_path = Column(String, nullable=True, comment="缩略图路径")

    status = Column(String, default="processing")
    processing_message = Column(Text, nullable=True)
    total_chunks = Column(Integer, default=0)

    kb_folder_id = Column(Integer, ForeignKey("knowledge_base_folders.id"), nullable=True, index=True,
                          comment="所属知识库文件夹ID")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    owner = relationship("Student", back_populates="uploaded_documents")
    chunks = relationship("KnowledgeDocumentChunk", back_populates="document", cascade="all, delete-orphan")
    kb_folder = relationship("KnowledgeBaseFolder", back_populates="documents")


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


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    instructor = Column(String)
    category = Column(String)
    total_lessons = Column(Integer)
    avg_rating = Column(Float)
    cover_image_url = Column(String, nullable=True, comment="课程封面图片URL")
    required_skills = Column(JSONB, nullable=False, server_default='[]',
                             comment="学习该课程所需基础技能列表及熟练度，或课程教授的技能")

    combined_text = Column(Text)
    embedding = Column(Vector(1024))
    likes_count = Column(Integer, default=0, comment="点赞数量")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    notes_made = relationship("Note", back_populates="course")
    user_courses = relationship("UserCourse", back_populates="course")
    chat_room = relationship("ChatRoom", back_populates="course", uselist=False, cascade="all, delete-orphan")
    materials = relationship("CourseMaterial", back_populates="course", cascade="all, delete-orphan")
    likes = relationship("CourseLike", back_populates="course", cascade="all, delete-orphan")


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



class CourseMaterial(Base):
    __tablename__ = "course_materials"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)

    title = Column(String, nullable=False, comment="材料标题，如：Lecture 1 Introduction to AI")
    # 材料类型: 'file' (OSS上传文件), 'link' (外部链接), 'text' (少量文本内容)
    type = Column(String, nullable=False, comment="材料类型：'file', 'link', 'text', 'video', 'image'")

    # 如果是 'file' 类型，存储OSS URL和原始文件名、文件类型、大小
    file_path = Column(String, nullable=True, comment="OSS文件URL")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    file_type = Column(String, nullable=True, comment="文件MIME类型")
    size_bytes = Column(BigInteger, nullable=True, comment="文件大小（字节）") # 使用 BigInteger

    # 如果是 'link' 类型，存储URL
    url = Column(String, nullable=True, comment="外部链接URL")

    # 如果是 'text' 类型，或作为其他类型的补充描述
    content = Column(Text, nullable=True, comment="材料的文本内容或简要描述")

    # 嵌入相关，用于未来搜索或匹配
    combined_text = Column(Text, nullable=True)
    embedding = Column(Vector(1024), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    course = relationship("Course", back_populates="materials")

    __table_args__ = (
        UniqueConstraint('course_id', 'title', name='_course_material_title_uc'),  # 确保同一课程下材料标题唯一
    )


# --- 旧的 CollectionItem (可以考虑未来删除或重构到 CollectedContent) ---
class CollectionItem(Base):
    __tablename__ = "collection_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("students.id"))
    item_type = Column(String)
    item_id = Column(Integer)

    created_at = Column(DateTime, server_default=func.now())

    user = relationship("Student", back_populates="collection_items")


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, comment="成就名称")
    description = Column(Text, nullable=False, comment="成就描述")
    # 成就达成条件类型，例如：PROJECT_COMPLETED_COUNT, COURSE_COMPLETED_COUNT, FORUM_LIKES_RECEIVED, DAILY_LOGIN_STREAK
    criteria_type = Column(String, nullable=False, comment="达成成就的条件类型")
    criteria_value = Column(Float, nullable=False, comment="达成成就所需的数值门槛") # 使用Float以支持小数，如平均分
    badge_url = Column(String, nullable=True, comment="勋章图片或图标URL")
    reward_points = Column(Integer, default=0, nullable=False, comment="达成此成就额外奖励的积分")
    is_active = Column(Boolean, default=True, nullable=False, comment="该成是否启用")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    earned_by_users = relationship("UserAchievement", back_populates="achievement", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Achievement(id={self.id}, name='{self.name}', criteria_type='{self.criteria_type}')>"


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    earned_at = Column(DateTime, server_default=func.now(), nullable=False)
    is_notified = Column(Boolean, default=False, nullable=False)

    user = relationship("Student", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="earned_by_users")

    __table_args__ = (
        UniqueConstraint('user_id', 'achievement_id', name='_user_achievement_uc'), # 确保一个用户不会重复获得同一个成就
    )

    def __repr__(self):
        return f"<UserAchievement(user_id={self.user_id}, achievement_id={self.achievement_id})>"


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    amount = Column(Integer, nullable=False, comment="积分变动金额（正数获得，负数消耗）")
    reason = Column(String, nullable=True, comment="积分变动理由描述")
    # 交易类型：EARN, CONSUME, ADMIN_ADJUST 等
    transaction_type = Column(String, nullable=False, comment="积分交易类型")
    related_entity_type = Column(String, nullable=True, comment="关联的实体类型")
    related_entity_id = Column(Integer, nullable=True, comment="关联实体的ID")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("Student", back_populates="point_transactions")

    def __repr__(self):
        return f"<PointTransaction(user_id={self.user_id}, amount={self.amount}, type='{self.transaction_type}')>"

