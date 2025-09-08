# project/schemas/courses.py
"""
课程相关Schema模块
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime
from .common import SkillWithProficiency, TimestampMixin, LikeableMixin


# --- Course Schemas ---
class CourseBase(BaseModel):
    """课程基础模型"""
    title: str = Field(..., min_length=1, max_length=200, description="课程标题")
    description: Optional[str] = Field(None, max_length=2000, description="课程描述")
    instructor: Optional[str] = Field(None, max_length=100, description="讲师姓名")
    category: Optional[str] = Field(None, max_length=50, description="课程分类")
    total_lessons: Optional[int] = Field(0, ge=0, le=1000, description="总课时数")
    avg_rating: Optional[float] = Field(0.0, ge=0.0, le=5.0, description="平均评分")
    cover_image_url: Optional[str] = Field(None, max_length=500, description="课程封面图片的URL链接")
    required_skills: Optional[List[SkillWithProficiency]] = Field(None, max_items=20, description="课程所需基础技能列表")


class CourseCreate(CourseBase):
    """创建课程模型"""
    pass


class CourseResponse(CourseBase, TimestampMixin, LikeableMixin):
    """课程响应模型"""
    id: int
    combined_text: Optional[str] = None


class CourseUpdate(BaseModel):
    """更新课程信息模型"""
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="课程标题")
    description: Optional[str] = Field(None, max_length=2000, description="课程描述")
    instructor: Optional[str] = Field(None, max_length=100, description="讲师姓名")
    category: Optional[str] = Field(None, max_length=50, description="课程分类")
    total_lessons: Optional[int] = Field(None, ge=0, le=1000, description="总课时数")
    avg_rating: Optional[float] = Field(None, ge=0.0, le=5.0, description="平均评分")
    cover_image_url: Optional[str] = Field(None, max_length=500, description="课程封面图片的URL链接")
    required_skills: Optional[List[SkillWithProficiency]] = Field(None, max_items=20, description="课程所需基础技能列表")


# --- UserCourse Schemas ---
class UserCourseBase(BaseModel):
    """用户课程关系基础模型"""
    student_id: int
    course_id: int
    progress: Optional[float] = 0.0
    status: Optional[str] = "in_progress"


class UserCourseCreate(UserCourseBase):
    """创建用户课程关系模型"""
    pass


class UserCourseResponse(UserCourseBase, TimestampMixin):
    """用户课程关系响应模型"""
    last_accessed: datetime


# --- Course Material Schemas ---
class CourseMaterialBase(BaseModel):
    """课程材料基础模型"""
    title: str = Field(..., min_length=1, max_length=200, description="课程材料标题")
    type: Literal["file", "link", "text", "video", "image"] = Field(..., description="材料类型")

    url: Optional[str] = Field(None, max_length=1000, description="外部链接URL或文件URL")
    content: Optional[str] = Field(None, max_length=10000, description="文本内容或补充描述")

    original_filename: Optional[str] = Field(None, max_length=255, description="原始上传文件名")
    file_type: Optional[str] = Field(None, max_length=100, description="文件MIME类型")
    size_bytes: Optional[int] = Field(None, ge=0, le=100*1024*1024, description="文件大小（字节）")

    @field_validator('url', 'content', 'original_filename', 'file_type', 'size_bytes', mode='before')
    def validate_material_fields(cls, v, info):
        if 'type' not in info.data:
            return v

        material_type = info.data['type']
        field_name = info.field_name

        # 链接类型验证
        if material_type == "link":
            if field_name == "url" and not v:
                raise ValueError("类型为 'link' 时，'url' 字段为必填。")
            if field_name in ['original_filename', 'file_type', 'size_bytes'] and v is not None:
                raise ValueError(f"类型为 'link' 时，客户端不应提供 '{field_name}' 字段。")

        # 文本类型验证
        elif material_type == "text":
            if field_name == "content" and not v:
                raise ValueError("类型为 'text' 时，'content' 字段为必填。")
            if field_name in ['url', 'original_filename', 'file_type', 'size_bytes'] and v is not None:
                raise ValueError(f"类型为 'text' 时，客户端不应提供 '{field_name}' 字段。")

        # 文件类型验证
        elif material_type in ["file", "image", "video"]:
            if field_name == "url" and v is not None:
                raise ValueError(f"类型为 '{material_type}' 时，客户端不应提供 'url' 字段，它将由服务器在文件上传后生成。")

        return v


class CourseMaterialCreate(CourseMaterialBase):
    """创建课程材料模型"""
    title: str
    type: Literal["file", "link", "text", "video", "image"]


class CourseMaterialUpdate(CourseMaterialBase):
    """更新课程材料模型"""
    title: Optional[str] = None
    type: Optional[Literal["file", "link", "text", "video", "image"]] = None


class CourseMaterialResponse(CourseMaterialBase, TimestampMixin):
    """课程材料响应模型"""
    id: int
    course_id: int
    combined_text: Optional[str] = None


# --- Course Like Schemas ---
class CourseLikeResponse(TimestampMixin, BaseModel):
    """课程点赞响应模型"""
    id: int
    owner_id: int
    course_id: int


# --- Matched Course for Recommendations ---
class MatchedCourse(BaseModel):
    """推荐匹配课程模型"""
    course_id: int
    title: str
    description: str
    instructor: Optional[str] = None
    category: Optional[str] = None
    cover_image_url: Optional[str] = None
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与课程匹配理由及建议")
