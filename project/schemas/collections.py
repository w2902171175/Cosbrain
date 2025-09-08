# project/schemas/collections.py
"""
收藏系统相关Schema模块
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, date
from .common import TimestampMixin, UserOwnerMixin


# ================== 增强的文件夹模型（新收藏系统）==================

class FolderBase(BaseModel):
    """增强的文件夹基础信息模型"""
    name: str = Field(..., min_length=1, max_length=100, description="文件夹名称")
    description: Optional[str] = Field(None, max_length=500, description="文件夹描述")
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", description="文件夹颜色（十六进制）")
    icon: Optional[str] = Field(None, max_length=50, description="文件夹图标名称")
    parent_id: Optional[int] = Field(None, description="父文件夹ID")
    order: Optional[int] = Field(None, ge=0, description="排序顺序")
    is_public: Optional[bool] = Field(False, description="是否公开文件夹")
    tags: Optional[List[str]] = Field(None, description="文件夹标签")


class FolderCreate(FolderBase):
    """创建文件夹的请求模型"""
    auto_classify: Optional[bool] = Field(True, description="是否启用自动分类")
    template: Optional[str] = Field(None, description="使用的文件夹模板")


class FolderResponse(FolderBase, TimestampMixin, UserOwnerMixin):
    """返回文件夹信息的响应模型"""
    id: int
    item_count: Optional[int] = Field(0, description="包含的项目数量")
    content_count: Optional[int] = Field(0, description="直接收藏内容数量")
    subfolder_count: Optional[int] = Field(0, description="子文件夹数量")
    total_size: Optional[int] = Field(0, description="总文件大小（字节）")
    last_accessed: Optional[datetime] = Field(None, description="最后访问时间")
    
    # 层级路径信息
    path: Optional[List[Dict[str, Any]]] = Field(None, description="文件夹路径")
    depth: Optional[int] = Field(0, description="文件夹深度")
    
    # 统计信息
    stats: Optional[Dict[str, Any]] = Field(None, description="统计信息")
    
    # 子文件夹列表（可选）
    children: Optional[List["FolderResponse"]] = Field(None, description="子文件夹")


class FolderUpdate(BaseModel):
    """更新文件夹的请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[int] = None
    order: Optional[int] = Field(None, ge=0)
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class FolderVisibilityUpdate(BaseModel):
    """文件夹公开状态更新请求模型"""
    is_public: bool = Field(..., description="是否设为公开")


class FolderStatsResponse(BaseModel):
    """文件夹统计信息响应模型"""
    total_folders: int
    total_contents: int
    content_by_type: Dict[str, int]
    storage_used: int
    recent_activity: List[Dict[str, Any]]
    
    class Config:
        from_attributes = True


# ================== 增强的收藏内容模型（新收藏系统）==================

class CollectedContentBase(BaseModel):
    """增强的收藏内容基础模型"""
    title: Optional[str] = Field(None, max_length=200, description="标题")
    type: Optional[Literal[
        "document", "video", "audio", "note", "link", "file", "image",
        "forum_topic", "forum_comment", "forum_topic_attachment", "course", "project", "chat_message",
        "code", "bookmark", "contact", "location", "text"
    ]] = Field(None, description="内容类型")
    url: Optional[str] = Field(None, description="URL地址")
    content: Optional[str] = Field(None, description="内容描述")
    excerpt: Optional[str] = Field(None, max_length=500, description="内容摘要")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    folder_id: Optional[int] = Field(None, description="所属文件夹ID")
    
    # 元数据
    priority: Optional[int] = Field(None, ge=1, le=5, description="优先级（1-5）")
    notes: Optional[str] = Field(None, max_length=1000, description="个人备注")
    is_starred: Optional[bool] = Field(False, description="是否加星标")
    is_public: Optional[bool] = Field(False, description="是否公开")
    
    # 媒体属性
    thumbnail: Optional[str] = Field(None, description="缩略图URL")
    author: Optional[str] = Field(None, max_length=100, description="作者")
    duration: Optional[str] = Field(None, description="时长")
    file_size: Optional[int] = Field(None, ge=0, description="文件大小（字节）")
    
    # 状态和分类
    status: Optional[Literal["active", "archived", "deleted", "draft"]] = Field("active", description="状态")
    source: Optional[str] = Field(None, max_length=100, description="来源")
    category: Optional[str] = Field(None, max_length=50, description="分类")
    
    # 平台内部资源关联
    shared_item_type: Optional[str] = Field(None, description="关联的平台资源类型")
    shared_item_id: Optional[int] = Field(None, description="关联的平台资源ID")
    
    # 时间相关
    published_at: Optional[datetime] = Field(None, description="内容发布时间")
    scheduled_at: Optional[datetime] = Field(None, description="计划处理时间")
    
    @model_validator(mode='after')
    def validate_content_requirements(self) -> 'CollectedContentBase':
        """验证内容要求 - 简化版"""
        # 链接类型必须有URL
        if self.type == "link" and not self.url:
            raise ValueError("链接类型必须提供URL")
        
        # 文件类型必须有URL
        if self.type in ["file", "image", "video", "audio"] and not self.url:
            raise ValueError(f"{self.type}类型必须提供文件URL")
        
        # 至少需要提供一种内容标识
        required_fields = [self.title, self.content, self.url, self.shared_item_id]
        if not any(required_fields):
            raise ValueError("至少需要提供标题、内容、URL或关联资源ID中的一个")
        
        return self


class CollectedContentCreate(CollectedContentBase):
    """创建收藏内容的请求模型"""
    auto_extract: Optional[bool] = Field(True, description="是否自动提取内容信息")
    auto_classify: Optional[bool] = Field(True, description="是否自动分类")
    auto_tag: Optional[bool] = Field(True, description="是否自动生成标签")


class CollectedContentResponse(CollectedContentBase, TimestampMixin, UserOwnerMixin):
    """返回收藏内容的响应模型"""
    id: int
    
    # 访问统计
    access_count: Optional[int] = Field(0, description="访问次数")
    last_accessed: Optional[datetime] = Field(None, description="最后访问时间")
    
    # 关系信息
    folder_name: Optional[str] = Field(None, description="所属文件夹名称")
    folder_path: Optional[List[str]] = Field(None, description="文件夹路径")
    
    # 内容分析结果
    extracted_info: Optional[Dict[str, Any]] = Field(None, description="提取的内容信息")
    sentiment_score: Optional[float] = Field(None, description="情感分析得分")
    
    # 相关内容
    related_items: Optional[List[int]] = Field(None, description="相关内容ID列表")


class CollectedContentUpdate(BaseModel):
    """更新收藏内容的请求模型"""
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    excerpt: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    folder_id: Optional[int] = None
    priority: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=1000)
    is_starred: Optional[bool] = None
    is_public: Optional[bool] = None
    status: Optional[Literal["active", "archived", "deleted", "draft"]] = None
    category: Optional[str] = Field(None, max_length=50)
    scheduled_at: Optional[datetime] = None


# ================== 快速收藏模型（新收藏系统）==================

class QuickCollectRequest(BaseModel):
    """快速收藏请求模型"""
    url: Optional[str] = Field(None, description="要收藏的URL")
    title: Optional[str] = Field(None, max_length=200, description="自定义标题")
    folder_id: Optional[int] = Field(None, description="目标文件夹ID")
    folder_name: Optional[str] = Field(None, max_length=100, description="目标文件夹名称（如不存在则创建）")
    
    # 平台内部资源
    shared_item_type: Optional[str] = Field(None, description="内部资源类型")
    shared_item_id: Optional[int] = Field(None, description="内部资源ID")
    
    # 自动化选项
    auto_extract: Optional[bool] = Field(True, description="是否自动提取内容信息")
    auto_classify: Optional[bool] = Field(True, description="是否自动分类到合适文件夹")
    auto_tag: Optional[bool] = Field(True, description="是否自动生成标签")
    
    # 快速标记
    priority: Optional[int] = Field(None, ge=1, le=5, description="优先级")
    is_starred: Optional[bool] = Field(False, description="是否标星")
    notes: Optional[str] = Field(None, max_length=500, description="快速备注")


# ================== 搜索和过滤模型（新收藏系统）==================

class SearchRequest(BaseModel):
    """搜索请求模型"""
    query: str = Field(..., min_length=1, max_length=200, description="搜索关键词")
    
    # 范围限制
    folder_ids: Optional[List[int]] = Field(None, description="限制在指定文件夹中搜索")
    include_subfolders: Optional[bool] = Field(True, description="是否包含子文件夹")
    
    # 类型过滤
    content_types: Optional[List[str]] = Field(None, description="内容类型过滤")
    exclude_types: Optional[List[str]] = Field(None, description="排除的内容类型")
    
    # 时间范围
    date_from: Optional[date] = Field(None, description="开始日期")
    date_to: Optional[date] = Field(None, description="结束日期")
    
    # 属性过滤
    is_starred: Optional[bool] = Field(None, description="是否只搜索加星内容")
    priority_min: Optional[int] = Field(None, ge=1, le=5, description="最低优先级")
    priority_max: Optional[int] = Field(None, ge=1, le=5, description="最高优先级")
    
    # 标签过滤
    tags: Optional[List[str]] = Field(None, description="标签过滤")
    exclude_tags: Optional[List[str]] = Field(None, description="排除的标签")
    
    # 搜索选项
    search_mode: Optional[Literal["simple", "fuzzy", "semantic"]] = Field("simple", description="搜索模式")
    sort_by: Optional[str] = Field("relevance", description="排序字段")
    sort_order: Optional[Literal["asc", "desc"]] = Field("desc", description="排序方向")
    
    # 分页
    limit: Optional[int] = Field(20, ge=1, le=100, description="返回数量限制")
    offset: Optional[int] = Field(0, ge=0, description="偏移量")


class SearchResponse(BaseModel):
    """搜索响应模型"""
    total: int = Field(..., description="总结果数")
    items: List[CollectedContentResponse] = Field(..., description="搜索结果")
    facets: Optional[Dict[str, Any]] = Field(None, description="搜索聚合信息")
    suggestions: Optional[List[str]] = Field(None, description="搜索建议")
    
    class Config:
        from_attributes = True


# ================== 批量操作模型（新收藏系统）==================

class BatchOperationRequest(BaseModel):
    """批量操作请求模型"""
    item_ids: List[int] = Field(..., description="要操作的项目ID列表")
    operation: Literal[
        "move", "copy", "delete", "archive", "star", "unstar",
        "tag", "untag", "change_priority", "change_status"
    ] = Field(..., description="操作类型")
    
    # 操作参数
    target_folder_id: Optional[int] = Field(None, description="目标文件夹ID（用于移动/复制）")
    tags: Optional[List[str]] = Field(None, description="标签（用于打标签操作）")
    priority: Optional[int] = Field(None, ge=1, le=5, description="优先级（用于修改优先级）")
    status: Optional[str] = Field(None, description="状态（用于修改状态）")


class BatchOperationResponse(BaseModel):
    """批量操作响应模型"""
    success_count: int = Field(..., description="成功操作的数量")
    failed_count: int = Field(..., description="失败操作的数量")
    errors: Optional[List[Dict[str, Any]]] = Field(None, description="错误详情")
    
    class Config:
        from_attributes = True


# ================== 统计和分析模型（新收藏系统）==================

class CollectionStatsRequest(BaseModel):
    """收藏统计请求模型"""
    date_from: Optional[date] = Field(None, description="统计开始日期")
    date_to: Optional[date] = Field(None, description="统计结束日期")
    folder_id: Optional[int] = Field(None, description="特定文件夹ID")
    group_by: Optional[Literal["day", "week", "month", "type", "folder"]] = Field("day", description="分组方式")


class CollectionStatsResponse(BaseModel):
    """收藏统计响应模型"""
    total_items: int = Field(..., description="总收藏数")
    total_folders: int = Field(..., description="总文件夹数")
    
    # 按类型统计
    by_type: Dict[str, int] = Field(..., description="按类型统计")
    by_folder: Dict[str, int] = Field(..., description="按文件夹统计")
    by_date: List[Dict[str, Any]] = Field(..., description="按日期统计")
    
    # 存储统计
    total_storage: int = Field(..., description="总存储空间使用")
    storage_by_type: Dict[str, int] = Field(..., description="按类型的存储使用")
    
    # 活动统计
    recent_activity: List[Dict[str, Any]] = Field(..., description="最近活动")
    top_accessed: List[Dict[str, Any]] = Field(..., description="最常访问的内容")
    
    class Config:
        from_attributes = True


# ================== 导入导出模型（新收藏系统）==================

class ImportRequest(BaseModel):
    """导入请求模型"""
    source_type: Literal["browser", "json", "csv", "markdown"] = Field(..., description="导入源类型")
    target_folder_id: Optional[int] = Field(None, description="目标文件夹ID")
    merge_duplicates: Optional[bool] = Field(True, description="是否合并重复项")
    auto_classify: Optional[bool] = Field(True, description="是否自动分类")


class ExportRequest(BaseModel):
    """导出请求模型"""
    format: Literal["json", "csv", "html", "markdown"] = Field(..., description="导出格式")
    folder_ids: Optional[List[int]] = Field(None, description="要导出的文件夹ID")
    include_content: Optional[bool] = Field(True, description="是否包含内容详情")
    include_metadata: Optional[bool] = Field(True, description="是否包含元数据")


# ================== 共享和协作模型（新收藏系统）==================

class ShareRequest(BaseModel):
    """分享请求模型"""
    item_type: Literal["folder", "content"] = Field(..., description="分享类型")
    item_id: int = Field(..., description="分享项目ID")
    share_type: Literal["public", "private", "protected"] = Field(..., description="分享方式")
    password: Optional[str] = Field(None, description="访问密码（受保护分享）")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


class ShareResponse(BaseModel):
    """分享响应模型"""
    share_id: str = Field(..., description="分享ID")
    share_url: str = Field(..., description="分享链接")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    
    class Config:
        from_attributes = True


# ================== 收藏摘要响应模型 ==================

class CollectionSummaryResponse(BaseModel):
    """收藏摘要响应模型"""
    total_collections: int = Field(..., description="总收藏数")
    chatroom_collections: int = Field(..., description="聊天室收藏数")
    forum_collections: int = Field(..., description="论坛收藏数")
    recent_collections: List[CollectedContentResponse] = Field(..., description="最近收藏")
    popular_folders: List[Dict[str, Any]] = Field(..., description="热门文件夹")
    
    class Config:
        from_attributes = True
