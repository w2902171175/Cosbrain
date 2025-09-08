# project/schemas/projects.py
"""
项目相关Schema模块
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from .common import SkillWithProficiency, TimestampMixin, UserOwnerMixin, LikeableMixin


# --- Project Schemas ---
class ProjectBase(BaseModel):
    """项目基础信息模型，用于创建或更新时接收数据"""
    title: str
    description: Optional[str] = None
    required_skills: Optional[List[SkillWithProficiency]] = Field(None, description="项目所需技能列表及熟练度")
    required_roles: Optional[List[str]] = Field(None, description="项目所需角色列表")
    keywords: Optional[str] = None
    project_type: Optional[str] = None
    expected_deliverables: Optional[str] = None
    contact_person_info: Optional[str] = None
    learning_outcomes: Optional[str] = None
    team_size_preference: Optional[str] = None
    project_status: Optional[str] = None
    start_date: Optional[datetime] = Field(None, description="项目开始日期")
    end_date: Optional[datetime] = Field(None, description="项目结束日期")
    estimated_weekly_hours: Optional[int] = Field(None, description="项目估计每周所需投入小时数")
    location: Optional[str] = Field(None, description="项目所在地理位置，例如：广州大学城，珠海横琴新区，琶洲")
    # --- 新增项目封面图片相关字段 ---
    cover_image_url: Optional[str] = Field(None, description="项目封面图片的OSS URL")
    cover_image_original_filename: Optional[str] = Field(None, description="原始上传的封面图片文件名")
    cover_image_type: Optional[str] = Field(None, description="封面图片MIME类型，例如 'image/jpeg'")
    cover_image_size_bytes: Optional[int] = Field(None, description="封面图片文件大小（字节）")


class ProjectCreate(ProjectBase):
    """创建项目时的数据模型"""
    pass


class ProjectResponse(ProjectBase, TimestampMixin, LikeableMixin):
    """返回项目信息时的模型"""
    id: int
    combined_text: Optional[str] = None
    # --- 新增项目文件列表 ---
    project_files: Optional[List['ProjectFileResponse']] = Field(None, description="项目关联的文件列表")

    @property
    def creator_name(self) -> Optional[str]:
        # ORM 对象上通过 `_creator_name` 赋值，@property 来读取它
        return getattr(self, '_creator_name', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


class ProjectUpdate(BaseModel):
    """项目更新时的数据模型，所有字段均为可选"""
    title: Optional[str] = None
    description: Optional[str] = None
    required_skills: Optional[List[SkillWithProficiency]] = Field(None, description="项目所需技能列表及熟练度")
    required_roles: Optional[List[str]] = Field(None, description="项目所需角色列表")
    keywords: Optional[str] = None
    project_type: Optional[str] = None
    expected_deliverables: Optional[str] = None
    contact_person_info: Optional[str] = None
    learning_outcomes: Optional[str] = None
    team_size_preference: Optional[str] = None
    project_status: Optional[str] = None
    start_date: Optional[datetime] = Field(None, description="项目开始日期")
    end_date: Optional[datetime] = Field(None, description="项目结束日期")
    estimated_weekly_hours: Optional[int] = Field(None, description="项目估计每周所需投入小时数")
    location: Optional[str] = Field(None, description="项目所在地理位置，例如：广州大学城，珠海横琴新区，琶洲")
    # --- 新增项目封面图片相关字段 ---
    cover_image_url: Optional[str] = Field(None, description="项目封面图片的OSS URL")
    cover_image_original_filename: Optional[str] = Field(None, description="原始上传的封面图片文件名")
    cover_image_type: Optional[str] = Field(None, description="封面图片MIME类型，例如 'image/jpeg'")
    cover_image_size_bytes: Optional[int] = Field(None, description="封面图片文件大小（字节）")


# --- Project File Update/Delete helper Schemas ---
class ProjectFileUpdateData(BaseModel):
    """项目文件更新数据模型"""
    id: int = Field(..., description="要更新的项目文件ID")
    file_name: Optional[str] = Field(None, description="更新后的文件名（可选，如果仅更新描述或权限）")
    description: Optional[str] = Field(None, description="更新后的文件描述")
    access_type: Optional[Literal["public", "member_only"]] = Field(None, description="更新后的文件访问权限")


class ProjectFileDeletionRequest(BaseModel):
    """项目文件删除请求模型"""
    file_ids: List[int] = Field(..., description="要删除的项目文件ID列表")


class ProjectUpdateWithFiles(BaseModel):
    """项目及文件更新组合请求模型"""
    project_data: ProjectUpdate = Field(..., description="要更新的项目主体数据")
    files_to_upload: Optional[List[Dict[str, Any]]] = Field(None, description="新上传文件的数据")
    files_to_delete_ids: Optional[List[int]] = Field(None, description="要删除的文件ID列表")
    files_to_update_metadata: Optional[List[ProjectFileUpdateData]] = Field(None, description="要更新元数据的文件列表")


# --- Project Application Schemas ---
class ProjectApplicationBase(BaseModel):
    """项目申请基础模型"""
    message: Optional[str] = Field(None, description="申请留言，例如为什么想加入")


class ProjectApplicationCreate(ProjectApplicationBase):
    """创建项目申请模型"""
    pass


class ProjectApplicationResponse(ProjectApplicationBase, TimestampMixin):
    """项目申请响应模型"""
    id: int
    project_id: int
    student_id: int
    status: Literal["pending", "approved", "rejected"]
    applied_at: datetime
    processed_at: Optional[datetime] = None
    processed_by_id: Optional[int] = None
    applicant_name: Optional[str] = Field(None, description="申请者姓名")
    applicant_email: Optional[EmailStr] = Field(None, description="申请者邮箱")
    processor_name: Optional[str] = Field(None, description="审批者姓名")


class ProjectApplicationProcess(BaseModel):
    """项目申请处理模型"""
    status: Literal["approved", "rejected"] = Field(..., description="处理结果: approved (批准) 或 rejected (拒绝)")
    process_message: Optional[str] = Field(None, description="审批附言，例如拒绝原因")


# --- Project Member Schemas ---
class ProjectMemberBase(BaseModel):
    """项目成员基础模型"""
    role: Literal["admin", "member"] = Field("member", description="项目成员角色: admin (管理员) 或 member (普通成员)")


class ProjectMemberResponse(ProjectMemberBase, TimestampMixin):
    """项目成员响应模型"""
    id: int
    project_id: int
    student_id: int
    joined_at: datetime
    member_name: Optional[str] = Field(None, description="成员姓名")
    member_email: Optional[EmailStr] = Field(None, description="成员邮箱")


# --- Project File Schemas ---
class ProjectFileBase(BaseModel):
    """项目文件基础模型"""
    file_name: str = Field(..., description="原始文件名")
    description: Optional[str] = Field(None, description="文件描述")
    access_type: Literal["public", "member_only"] = Field("member_only", description="文件访问权限")


class ProjectFileCreate(ProjectFileBase):
    """创建项目文件模型"""
    pass


class ProjectFileResponse(ProjectFileBase, TimestampMixin):
    """项目文件响应模型"""
    id: int
    project_id: int
    upload_by_id: int
    oss_object_name: str = Field(..., description="文件在OSS中的对象名称")
    file_path: str = Field(..., description="文件在OSS上的完整URL")
    file_type: Optional[str] = Field(None, description="文件的MIME类型")
    size_bytes: Optional[int] = Field(None, description="文件大小（字节）")

    @property
    def uploader_name(self) -> Optional[str]:
        return getattr(self, '_uploader_name', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


# --- Project Like Schemas ---
class ProjectLikeResponse(TimestampMixin, BaseModel):
    """项目点赞响应模型"""
    id: int
    owner_id: int
    project_id: int


# --- Matched Project for Recommendations ---
class MatchedProject(BaseModel):
    """推荐匹配项目模型"""
    project_id: int
    title: str
    description: str
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")


class MatchedStudent(BaseModel):
    """推荐匹配学生模型"""
    student_id: int
    name: str
    major: str
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="学生的技能列表及熟练度详情")
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")


class ProjectStatsResponse(BaseModel):
    """项目统计响应模型"""
    total_projects: int = Field(0, description="项目总数")
    my_projects: int = Field(0, description="我的项目数")
    joined_projects: int = Field(0, description="参与的项目数")
    pending_applications: int = Field(0, description="待处理申请数")
    approved_applications: int = Field(0, description="已通过申请数")
    rejected_applications: int = Field(0, description="已拒绝申请数")
    
    class Config:
        from_attributes = True
