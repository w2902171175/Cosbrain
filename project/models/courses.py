# project/models/courses.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, UniqueConstraint, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from project.base import Base
from .mixins import TimestampMixin, OwnerMixin, EmbeddingMixin, BaseContentMixin, LikeMixin


class Course(Base, TimestampMixin, EmbeddingMixin):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)
    # - combined_text, embedding (from EmbeddingMixin)
    
    # Course特有字段
    title = Column(String, index=True, comment="课程标题")
    description = Column(Text, comment="课程描述")
    instructor = Column(String, comment="讲师")
    category = Column(String, comment="课程分类")
    total_lessons = Column(Integer, comment="总课时")
    avg_rating = Column(Float, comment="平均评分")
    cover_image_url = Column(String, nullable=True, comment="课程封面图片URL")
    required_skills = Column(JSONB, nullable=False, server_default='[]',
                             comment="学习该课程所需基础技能列表及熟练度，或课程教授的技能")
    likes_count = Column(Integer, default=0, comment="点赞数量")

    notes_made = relationship("Note", back_populates="course")
    user_courses = relationship("UserCourse", back_populates="course")
    chat_room = relationship("ChatRoom", back_populates="course", uselist=False, cascade="all, delete-orphan")
    materials = relationship("CourseMaterial", back_populates="course", cascade="all, delete-orphan")
    likes = relationship("CourseLike", back_populates="course", cascade="all, delete-orphan")


class UserCourse(Base):
    __tablename__ = "user_courses"

    student_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), primary_key=True)
    progress = Column(Float, default=0.0)
    status = Column(String, default="in_progress")
    last_accessed = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    student = relationship("User", back_populates="user_courses")
    course = relationship("Course", back_populates="user_courses")


class CourseMaterial(Base, TimestampMixin):
    __tablename__ = "course_materials"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)

    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)

    title = Column(String, nullable=False, comment="材料标题，如：Lecture 1 Introduction to AI")
    # 材料类型: 'file' (OSS上传文件), 'link' (外部链接), 'text' (少量文本内容)
    type = Column(String, nullable=False, comment="材料类型：'file', 'link', 'text', 'video', 'image'")

    # 文件相关字段（统一字段命名）
    file_path = Column(String, nullable=True, comment="OSS文件URL")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    file_type = Column(String, nullable=True, comment="文件MIME类型")
    file_size_bytes = Column(BigInteger, nullable=True, comment="文件大小（字节）")

    # 如果是 'link' 类型，存储URL
    url = Column(String, nullable=True, comment="外部链接URL")

    # 如果是 'text' 类型，或作为其他类型的补充描述
    content = Column(Text, nullable=True, comment="材料的文本内容或简要描述")

    # 嵌入相关，用于未来搜索或匹配
    combined_text = Column(Text, nullable=True)
    embedding = Column(Vector(1024), nullable=True)

    @property
    def size_bytes(self):
        """向后兼容属性，映射到file_size_bytes"""
        return self.file_size_bytes

    @size_bytes.setter
    def size_bytes(self, value):
        """向后兼容属性设置器"""
        self.file_size_bytes = value

    course = relationship("Course", back_populates="materials")

    __table_args__ = (
        UniqueConstraint('course_id', 'title', name='_course_material_title_uc'),  # 确保同一课程下材料标题唯一
    )


class CourseLike(Base, LikeMixin):
    __tablename__ = "course_likes"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at (from TimestampMixin)
    
    # CourseLike特有字段
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, comment="被点赞课程ID")

    owner = relationship("User", back_populates="course_likes")
    course = relationship("Course", back_populates="likes")

    __table_args__ = (
        UniqueConstraint('owner_id', 'course_id', name='_course_like_uc'), # 确保一个用户不会重复点赞同一个课程
    )
