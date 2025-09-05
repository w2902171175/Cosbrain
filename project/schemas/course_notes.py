# project/schemas/course_notes.py
"""
课程笔记相关Schema模块(course_notes)
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Literal
from datetime import datetime
from .common import TimestampMixin, UserOwnerMixin, MediaMixin


# --- Note Schemas ---
class NoteBase(BaseModel):
    """笔记基础模型"""
    title: Optional[str] = None
    content: Optional[str] = None
    note_type: Optional[str] = "general"
    course_id: Optional[int] = Field(None, description="关联的课程ID")
    tags: Optional[str] = None
    chapter: Optional[str] = Field(None, description="课程章节信息，例如：第一章 - AI概述")
    media_url: Optional[str] = Field(None, description="笔记中嵌入的图片、视频或文件的OSS URL")
    media_type: Optional[Literal["image", "video", "file"]] = Field(None, description="媒体类型")
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    media_size_bytes: Optional[int] = Field(None, description="媒体文件大小（字节）")
    folder_id: Optional[int] = Field(None, description="关联的用户自定义文件夹ID")

    @model_validator(mode='after')
    def validate_media_and_content(self) -> 'NoteBase':
        # 媒体字段验证
        if self.media_url and not self.media_type:
            raise ValueError("media_url 存在时，media_type 不能为空，且必须为 'image', 'video' 或 'file'。")
        
        # 文件夹ID处理
        if self.folder_id == 0:
            self.folder_id = None
        
        # 关联关系验证
        is_course_note = (self.course_id is not None) or (self.chapter is not None and self.chapter.strip() != "")
        is_folder_note = (self.folder_id is not None)
        if is_course_note and is_folder_note:
            raise ValueError("笔记不能同时关联到课程/章节和自定义文件夹。请选择一种组织方式。")
        if (self.chapter is not None and self.chapter.strip() != "") and (self.course_id is None):
            raise ValueError("为了关联章节信息，课程ID (course_id) 不能为空。")
        
        return self


class NoteCreate(NoteBase):
    """创建笔记模型"""
    title: str = Field(..., description="笔记标题，创建时必需")
    
    @model_validator(mode='after')
    def validate_title_not_empty(self) -> 'NoteCreate':
        if not self.title or not self.title.strip():
            raise ValueError("笔记标题不能为空。")
        return self


class NoteUpdate(NoteBase):
    """更新笔记模型"""
    pass


class NoteResponse(NoteBase, TimestampMixin, UserOwnerMixin):
    """笔记响应模型"""
    id: int
    combined_text: Optional[str] = None

    @property
    def folder_name(self) -> Optional[str]:
        return getattr(self, '_folder_name_for_response', None)

    @property
    def course_title(self) -> Optional[str]:
        return getattr(self, '_course_title_for_response', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True
