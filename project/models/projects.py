# project/models/projects.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, UniqueConstraint, BigInteger, event
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from project.base import Base
from project import oss_utils
from .mixins import TimestampMixin, OwnerMixin, EmbeddingMixin, LikeMixin
import threading
import asyncio


class ProjectApplication(Base):
    __tablename__ = "project_applications"
    __table_args__ = (
        # 确保同一学生对同一项目只有一条待处理或已批准的申请记录
        UniqueConstraint("project_id", "student_id", name="_project_student_application_uc"),
        {'extend_existing': True}  # 允许重新定义表结构，避免MetaData重复定义错误
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True, comment="申请项目ID")
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="申请学生ID")

    status = Column(String, default="pending", nullable=False, comment="申请状态: pending, approved, rejected")
    message = Column(Text, nullable=True, comment="申请留言")

    applied_at = Column(DateTime, server_default=func.now(), nullable=False, comment="申请提交时间")
    processed_at = Column(DateTime, nullable=True, comment="申请处理时间")
    processed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="审批者ID")

    # Relationships
    project = relationship("Project", back_populates="applications")
    applicant = relationship("User", foreign_keys=[student_id], back_populates="project_applications")
    processor = relationship("User", foreign_keys=[processed_by_id])  # 审批者


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        # 确保同一学生在同一项目下只有一条成员记录
        UniqueConstraint("project_id", "student_id", name="_project_student_member_uc"),
        {'extend_existing': True}  # 允许重新定义表结构，避免MetaData重复定义错误
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True, comment="所属项目ID")
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="成员学生ID")

    role = Column(String, default="member", nullable=False, comment="成员角色: admin, member")  # 项目管理员或普通成员
    status = Column(String, default="active", nullable=False,
                    comment="成员状态: active (活跃), inactive (不活跃), removed (被移除)")
    joined_at = Column(DateTime, server_default=func.now(), nullable=False, comment="加入时间")

    # Relationships
    project = relationship("Project", back_populates="members")
    member = relationship("User", back_populates="project_memberships")


class Project(Base, TimestampMixin, EmbeddingMixin):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - created_at, updated_at (from TimestampMixin)
    # - combined_text, embedding (from EmbeddingMixin)
    
    # Project特有字段
    title = Column(String, index=True, comment="项目标题")
    description = Column(Text, comment="项目描述")
    required_skills = Column(JSONB, nullable=False, server_default='[]', comment="存储所需技能列表，每个技能包含名称和熟练度")
    required_roles = Column(JSONB, nullable=False, server_default='[]', comment="存储项目所需角色列表")
    keywords = Column(String, comment="关键词")
    project_type = Column(String, comment="项目类型")
    expected_deliverables = Column(Text, comment="预期交付成果")
    contact_person_info = Column(String, comment="联系人信息")
    learning_outcomes = Column(Text, comment="学习成果")
    team_size_preference = Column(String, comment="团队规模偏好")
    project_status = Column(String, comment="项目状态")
    likes_count = Column(Integer, default=0, comment="点赞数量")

    start_date = Column(DateTime, nullable=True, comment="项目开始日期")
    end_date = Column(DateTime, nullable=True, comment="项目结束日期")
    estimated_weekly_hours = Column(Integer, nullable=True, comment="项目估计每周所需投入小时数")
    location = Column(String, nullable=True, comment="项目所在地理位置")

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="项目创建者ID")

    cover_image_url = Column(String, nullable=True, comment="项目封面图片的OSS URL")
    cover_image_original_filename = Column(String, nullable=True, comment="原始上传的封面图片文件名")
    cover_image_type = Column(String, nullable=True, comment="封面图片MIME类型，例如 'image/jpeg'")
    cover_image_size_bytes = Column(BigInteger, nullable=True, comment="封面图片文件大小（字节）")

    chat_room = relationship("ChatRoom", back_populates="project", uselist=False, cascade="all, delete-orphan")
    creator = relationship("User", back_populates="projects_created")
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
    upload_by_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="文件上传者ID")

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
    uploader = relationship("User", backref="uploaded_project_files")

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
        # 使用同步方式调度异步任务，避免在事务中创建不安全的异步任务
        try:
            def delete_oss_file():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(oss_utils.delete_file_from_oss(oss_object_name))
                finally:
                    loop.close()
            
            thread = threading.Thread(target=delete_oss_file, daemon=True)
            thread.start()
        except Exception as e:
            print(f"ERROR_OSS_DELETE_EVENT: 删除OSS文件失败: {e}")
    else:
        print(f"WARNING_OSS_DELETE_EVENT: ProjectFile ID: {target.id} 没有关联的 OSS 对象名称，跳过 OSS 文件删除。")
# --- 新增 ProjectFile 模型结束 ---


class ProjectLike(Base, LikeMixin):
    __tablename__ = "project_likes"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at (from TimestampMixin)
    
    # ProjectLike特有字段
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, comment="被点赞项目ID")

    owner = relationship("User", back_populates="project_likes")
    project = relationship("Project", back_populates="likes")

    __table_args__ = (
        UniqueConstraint('owner_id', 'project_id', name='_project_like_uc'), # 确保一个用户不会重复点赞同一个项目
    )
