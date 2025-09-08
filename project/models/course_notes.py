# project/models/course_notes.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from project.base import Base
from .mixins import TimestampMixin, OwnerMixin, EmbeddingMixin, MediaMixin


class Note(Base, TimestampMixin, OwnerMixin, EmbeddingMixin, MediaMixin):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at, updated_at (from TimestampMixin)
    # - combined_text, embedding (from EmbeddingMixin)
    # - media_url, media_type, original_filename, file_size_bytes (from MediaMixin)
    
    # Note特有字段
    title = Column(String, comment="笔记标题")
    content = Column(Text, comment="笔记内容")
    note_type = Column(String, comment="笔记类型")
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, comment="关联课程ID")
    tags = Column(String, comment="标签")

    # 章节信息字段
    chapter = Column(String, nullable=True, comment="课程章节信息，例如：第一章 - AI概述")

    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True, comment="用户自定义文件夹ID")

    owner = relationship("User", back_populates="notes")
    course = relationship("Course", back_populates="notes_made")
    folder = relationship("Folder", back_populates="notes")


class Folder(Base, TimestampMixin, OwnerMixin):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at (from TimestampMixin)
    # - updated_at (from TimestampMixin)
    
    # Folder特有字段
    name = Column(String, nullable=False, comment="文件夹名称")
    description = Column(Text, nullable=True, comment="文件夹描述")
    color = Column(String, nullable=True, comment="文件夹颜色")
    icon = Column(String, nullable=True, comment="文件夹图标")
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True, comment="父文件夹ID")
    order = Column(Integer, default=0, comment="排序")
    is_public = Column(Boolean, default=False, nullable=False, comment="是否公开: True(公开到全平台), False(私密)")

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

    owner = relationship("User", back_populates="folders")
