# project/schemas/knowledge_schemas.py
"""
简化的知识库相关Schema定义
移除了复杂的软链接逻辑，提供更简洁的数据模型
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Literal, Any
from datetime import datetime

# ===== 知识库基础Schema =====

class KnowledgeBaseSimpleBase(BaseModel):
    """简化的知识库基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: Optional[str] = Field(None, max_length=500, description="知识库描述")
    access_type: Optional[str] = Field("private", description="访问类型")

class KnowledgeBaseSimpleCreate(KnowledgeBaseSimpleBase):
    """创建知识库的模型"""
    pass

class KnowledgeBaseSimpleResponse(KnowledgeBaseSimpleBase):
    """知识库响应模型"""
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt is not None else None
        }

# ===== 文件夹Schema（简化版） =====

class KnowledgeBaseFolderSimpleBase(BaseModel):
    """简化的知识库文件夹基础模型"""
    name: str = Field(..., min_length=1, max_length=100, description="文件夹名称")
    description: Optional[str] = Field(None, max_length=500, description="文件夹描述")
    parent_id: Optional[int] = Field(None, description="父文件夹ID")
    order: Optional[int] = Field(0, description="排序")

class KnowledgeBaseFolderSimpleCreate(KnowledgeBaseFolderSimpleBase):
    """创建文件夹的模型"""
    pass

class KnowledgeBaseFolderSimpleResponse(KnowledgeBaseFolderSimpleBase):
    """文件夹响应模型"""
    id: int
    kb_id: int
    owner_id: int
    item_count: Optional[int] = Field(None, description="文件夹内容数量")
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt is not None else None
        }

# ===== 文章Schema（简化版） =====

# ===== 文档Schema（简化版） =====

class KnowledgeDocumentSimpleBase(BaseModel):
    """简化的知识库文档基础模型"""
    file_name: str = Field(..., description="文件名")
    file_type: Optional[str] = Field(None, description="文件类型")
    content_type: str = Field("file", description="内容类型: file, image, video, url, website")
    url: Optional[str] = Field(None, description="网址URL（用于url和website类型）")
    website_title: Optional[str] = Field(None, description="网站标题")
    website_description: Optional[str] = Field(None, description="网站描述")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    mime_type: Optional[str] = Field(None, description="MIME类型")
    thumbnail_path: Optional[str] = Field(None, description="缩略图路径")
    status: Optional[str] = Field("processing", description="处理状态")
    processing_message: Optional[str] = Field(None, description="处理消息")
    total_chunks: Optional[int] = Field(0, description="文档块数量")
    kb_folder_id: Optional[int] = Field(None, description="所属文件夹ID")

class KnowledgeDocumentSimpleCreate(BaseModel):
    """创建文档的模型"""
    file_name: str
    content_type: str = Field("file", description="内容类型: file, image, video, url, website")
    url: Optional[str] = Field(None, description="网址URL（用于url和website类型）")
    website_title: Optional[str] = Field(None, description="网站标题")
    website_description: Optional[str] = Field(None, description="网站描述")
    kb_folder_id: Optional[int] = None

class KnowledgeDocumentUrlCreate(BaseModel):
    """创建网址/网站类型文档的模型"""
    url: str = Field(..., description="网址URL")
    title: Optional[str] = Field(None, description="自定义标题")
    description: Optional[str] = Field(None, description="描述")
    content_type: str = Field("url", description="内容类型: url 或 website")
    kb_folder_id: Optional[int] = None

class KnowledgeDocumentSimpleResponse(KnowledgeDocumentSimpleBase):
    """文档响应模型"""
    id: int
    kb_id: int
    owner_id: int
    file_path: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt is not None else None
        }

# ===== 搜索相关Schema =====

class KnowledgeSearchResult(BaseModel):
    """搜索结果项"""
    type: Literal["document"] = Field(..., description="结果类型")
    id: int = Field(..., description="项目ID")
    title: str = Field(..., description="标题")
    content: Optional[str] = Field(None, description="内容预览")
    file_type: Optional[str] = Field(None, description="文件类型")
    status: Optional[str] = Field(None, description="状态")
    content_type: Optional[str] = Field(None, description="内容类型")
    url: Optional[str] = Field(None, description="URL地址")
    thumbnail_path: Optional[str] = Field(None, description="缩略图路径")
    file_size: Optional[int] = Field(None, description="文件大小")
    created_at: datetime
    updated_at: Optional[datetime] = None

class KnowledgeSearchResponse(BaseModel):
    """搜索响应"""
    query: str = Field(..., description="搜索查询")
    total: int = Field(..., description="结果总数")
    results: List[KnowledgeSearchResult] = Field(..., description="搜索结果列表")
    page: Optional[int] = Field(1, description="当前页码")
    size: Optional[int] = Field(20, description="每页数量")
    search_mode: Optional[str] = Field("basic", description="搜索模式")
    content_type_filter: Optional[str] = Field(None, description="内容类型筛选")
    status_filter: Optional[str] = Field(None, description="状态筛选")

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt is not None else None
        }

# ===== 统计Schema =====

class KnowledgeBaseStats(BaseModel):
    """知识库统计信息"""
    total_document_chunks: int = Field(0, description="文档块总数")
    total_documents: int = Field(0, description="文档总数")
    total_folders: int = Field(0, description="文件夹总数")
    recent_updates: List[Any] = Field([], description="最近更新")

    class Config:
        from_attributes = True
