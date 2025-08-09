# project/schemas.py

from pydantic import BaseModel, EmailStr, Field, Field, model_validator
from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime


# --- Student Schemas ---
class StudentBase(BaseModel):
    """学生基础信息模型，用于创建或更新时接收数据"""
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="用户在平台内唯一的用户名/昵称")
    phone_number: Optional[str] = Field(None, min_length=11, max_length=11,
                                        description="用户手机号，用于登录和重置密码")  # 假设手机号是11位
    school: Optional[str] = Field(None, max_length=100, description="用户所属学校名称")

    name: Optional[str] = Field(None, description="用户真实姓名")
    major: Optional[str] = None
    skills: Optional[str] = None
    interests: Optional[str] = None
    bio: Optional[str] = None
    awards_competitions: Optional[str] = None
    academic_achievements: Optional[str] = None
    soft_skills: Optional[str] = None
    portfolio_link: Optional[str] = None
    preferred_role: Optional[str] = None
    availability: Optional[str] = None


class StudentCreate(StudentBase):
    """创建学生时的数据模型 (包含邮箱或手机号，以及密码)"""
    email: Optional[EmailStr] = Field(None, description="用户邮箱，如果提供则用于注册和登录")

    password: str = Field(..., min_length=6, description="用户密码，至少6位")

    @model_validator(mode='after')  # 在所有字段验证之后运行
    def check_email_or_phone_number_provided(self) -> 'StudentCreate':
        if not self.email and not self.phone_number:
            raise ValueError('邮箱或手机号至少需要提供一个用于注册。')
        return self


class StudentResponse(StudentBase):
    """返回学生信息时的模型 (不包含密码哈希)"""
    id: int
    email: Optional[EmailStr] = None

    combined_text: Optional[str] = None
    llm_api_type: Optional[str] = None
    llm_api_base_url: Optional[str] = None
    llm_model_id: Optional[str] = None
    llm_api_key_encrypted: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    is_admin: bool

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
    # --- Project Schemas ---


class ProjectBase(BaseModel):
    """项目基础信息模型，用于创建或更新时接收数据"""
    title: str
    description: Optional[str] = None
    required_skills: Optional[str] = None
    keywords: Optional[str] = None
    project_type: Optional[str] = None
    expected_deliverables: Optional[str] = None
    contact_person_info: Optional[str] = None
    learning_outcomes: Optional[str] = None
    team_size_preference: Optional[str] = None
    project_status: Optional[str] = None


class ProjectCreate(ProjectBase):
    """创建项目时的数据模型"""
    pass


class ProjectResponse(ProjectBase):
    """返回项目信息时的模型"""
    id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- Note Schemas ---


class NoteBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    note_type: Optional[str] = "general"
    course_id: Optional[int] = None
    tags: Optional[str] = None


class NoteCreate(NoteBase):
    owner_id: int


class NoteResponse(NoteBase):
    id: int
    owner_id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- DailyRecord Schemas ---


class DailyRecordBase(BaseModel):
    """随手记录基础信息模型，用于创建或更新时接收数据"""
    content: str
    mood: Optional[str] = None
    tags: Optional[str] = None


class DailyRecordCreate(DailyRecordBase):
    """创建随手记录时的数据模型"""
    pass


class DailyRecordResponse(DailyRecordBase):
    """返回随手记录信息时的模型"""
    id: int
    owner_id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- Folder Schemas ---


class FolderBase(BaseModel):
    """文件夹基础信息模型，用于创建或更新时接收数据"""
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    order: Optional[int] = None


class FolderCreate(FolderBase):
    """创建文件夹时的数据模型"""
    pass


class FolderResponse(FolderBase):
    """返回文件夹信息时的模型"""
    id: int
    owner_id: int
    item_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- CollectedContent Schemas ---


class CollectedContentBase(BaseModel):
    """具体收藏内容基础信息模型，用于创建或更新时接收数据"""
    title: str
    type: Literal[
        "document", "video", "note", "link", "file", "forum_topic", "course", "project", "knowledge_article", "daily_record"]
    url: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None
    folder_id: Optional[int] = None
    priority: Optional[int] = None
    notes: Optional[str] = None
    is_starred: Optional[bool] = None
    thumbnail: Optional[str] = None
    author: Optional[str] = None
    duration: Optional[str] = None
    file_size: Optional[str] = None
    status: Optional[Literal["active", "archived", "deleted"]] = None


class CollectedContentCreate(CollectedContentBase):
    """创建具体收藏内容时的数据模型"""
    pass


class CollectedContentResponse(CollectedContentBase):
    """返回具体收藏内容信息时的模型"""
    id: int
    owner_id: int
    access_count: Optional[int] = None
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- ChatRoom Schemas ---


class ChatRoomBase(BaseModel):
    """聊天室基础信息模型，用于创建或更新时接收数据"""
    name: str
    type: Literal["project_group", "course_group", "private", "general"] = "general"
    project_id: Optional[int] = None
    course_id: Optional[int] = None
    color: Optional[str] = None


# 聊天室成员基础信息 (用于请求和响应)
class ChatRoomMemberBase(BaseModel):
    room_id: int
    member_id: int
    role: str = Field("member", description="成员角色：'admin'或'member'")
    status: str = Field("active", description="成员状态：'active', 'banned', 'left'")
    # last_read_at: Optional[datetime] = None # 如果在 models.py 中添加了此字段

# 聊天室成员响应信息 (包含 ID 和时间戳)
class ChatRoomMemberResponse(ChatRoomMemberBase):
    id: int
    joined_at: datetime
    member_name: Optional[str] = Field(None, description="成员的姓名")
    class Config:
        from_attributes = True # Pydantic V2
        # orm_mode = True # Pydantic V1
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None} # 保持一致


# ** 用于更新成员角色的请求体**
class ChatRoomMemberRoleUpdate(BaseModel):
    role: str = Field(..., description="要设置的新角色：'admin' 或 'member'")


# 入群申请请求体
class ChatRoomJoinRequestCreate(BaseModel):
    room_id: int = Field(..., description="目标聊天室ID")
    reason: Optional[str] = Field(None, description="入群申请理由")

# 入群申请处理请求体 (用于管理员/群主批准或拒绝)
class ChatRoomJoinRequestProcess(BaseModel):
    status: str = Field(..., description="处理结果状态：'approved' 或 'rejected'") # 只能是这两个字符串
    # 备注：processed_by_id 和 processed_at 将由后端自动填充

# 入群申请响应信息 (包含所有详情)
class ChatRoomJoinRequestResponse(BaseModel):
    id: int
    room_id: int
    requester_id: int
    reason: Optional[str] = None
    status: str
    requested_at: datetime
    processed_by_id: Optional[int] = None
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

class UserAdminStatusUpdate(BaseModel):
    is_admin: bool = Field(..., description="是否设置为系统管理员 (True) 或取消管理员权限 (False)")

class ChatRoomCreate(ChatRoomBase):
    """创建聊天室时的数据模型"""
    pass

# ** 聊天室更新请求体，所有字段均为可选**
class ChatRoomUpdate(ChatRoomBase):
    name: Optional[str] = None
    type: Optional[str] = None
    project_id: Optional[int] = None
    course_id: Optional[int] = None
    color: Optional[str] = None


class ChatRoomResponse(ChatRoomBase):
    """返回聊天室信息时的模型"""
    id: int
    creator_id: int
    members_count: Optional[int] = None
    last_message: Optional[Dict[str, Any]] = None
    unread_messages_count: Optional[int] = 0
    online_members_count: Optional[int] = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- ChatMessage Schemas ---


class ChatMessageBase(BaseModel):
    """聊天消息基础信息模型，用于创建时接收数据"""
    content_text: str
    message_type: Literal["text", "image", "file", "system_notification"] = "text"
    media_url: Optional[str] = None


class ChatMessageCreate(ChatMessageBase):
    """创建聊天消息时的数据模型"""
    pass


class ChatMessageResponse(ChatMessageBase):
    """返回聊天消息信息时的模型"""
    id: int
    room_id: int
    sender_id: int
    sent_at: datetime
    sender_name: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- ForumTopic Schemas ---


class ForumTopicBase(BaseModel):
    """论坛话题基础信息模型，用于创建或更新时接收数据"""
    title: str
    content: str
    shared_item_type: Optional[Literal[
        "note", "daily_record", "course", "project", "knowledge_article", "knowledge_base", "collected_content"]] = None
    shared_item_id: Optional[int] = None
    tags: Optional[str] = None


class ForumTopicCreate(ForumTopicBase):
    """创建论坛话题时的数据模型"""
    pass


class ForumTopicResponse(ForumTopicBase):
    """返回论坛话题信息时的模型"""
    id: int
    owner_id: int
    owner_name: Optional[str] = None
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None
    views_count: Optional[int] = None
    is_liked_by_current_user: Optional[bool] = False
    is_collected_by_current_user: Optional[bool] = False
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- ForumComment Schemas ---


class ForumCommentBase(BaseModel):
    """论坛评论基础信息模型，用于创建或更新时接收数据"""
    content: str
    parent_comment_id: Optional[int] = None


class ForumCommentCreate(ForumCommentBase):
    """创建论坛评论时的数据模型"""
    pass


class ForumCommentResponse(ForumCommentBase):
    """返回论坛评论信息时的模型"""
    id: int
    topic_id: int
    owner_id: int
    _owner_name: Optional[str] = None
    likes_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_liked_by_current_user: Optional[bool] = False

    @property
    def owner_name(self) -> str:
        return self._owner_name if self._owner_name else "未知用户"

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- ForumLike Schemas ---


class ForumLikeResponse(BaseModel):
    """点赞操作的响应模型"""
    id: int
    owner_id: int
    topic_id: Optional[int] = None
    comment_id: Optional[int] = None
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- UserFollow Schemas ---


class UserFollowResponse(BaseModel):
    """用户关注操作的响应模型"""
    id: int
    follower_id: int
    followed_id: int
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- UserMcpConfig Schemas ---


class UserMcpConfigBase(BaseModel):
    name: Optional[str] = None
    mcp_type: Optional[Literal["modelscope_community", "custom_mcp"]] = None
    base_url: Optional[str] = None
    protocol_type: Optional[Literal["sse", "http_rest", "websocket"]] = "http_rest"
    api_key: Optional[str] = None
    is_active: Optional[bool] = True
    description: Optional[str] = None


class UserMcpConfigCreate(UserMcpConfigBase):
    name: str
    base_url: str
    pass


class UserMcpConfigResponse(UserMcpConfigBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- McpStatusResponse Schemas ---


class McpStatusResponse(BaseModel):
    status: str
    message: str
    service_name: Optional[str] = None
    config_id: Optional[int] = None
    timestamp: datetime

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- McpToolDefinition Schemas ---


class McpToolDefinition(BaseModel):
    """表示一个可供智库LLM调用的MCP工具定义"""
    tool_id: str  # 工具的唯一ID，可以用于LLM的function_call
    name: str  # 工具名称，用于显示给用户
    description: str  # 工具描述，告诉LLM工具的用途
    mcp_config_id: int  # 关联的MCP配置ID
    mcp_config_name: str  # 关联的MCP配置名称
    input_schema: Dict[str, Any]  # 符合OpenAPI Spec的输入JSON Schema
    output_schema: Dict[str, Any]  # 符合OpenAPI Spec的输出JSON Schema

    class Config:
        from_attributes = True

    # --- UsersSearchEngineConfig Schemas ---


class UserSearchEngineConfigBase(BaseModel):
    name: Optional[str] = None
    engine_type: Optional[Literal["bing", "tavily", "baidu", "google_cse", "custom"]] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = True
    description: Optional[str] = None


class UserSearchEngineConfigCreate(UserSearchEngineConfigBase):
    name: str
    engine_type: Literal["bing", "tavily", "baidu", "google_cse", "custom"]
    base_url: Optional[str] = None
    pass


class UserSearchEngineConfigResponse(UserSearchEngineConfigBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- SearchEngineStatusResponse Schemas ---


class SearchEngineStatusResponse(BaseModel):
    status: str
    message: str
    engine_name: Optional[str] = None
    config_id: Optional[int] = None
    timestamp: datetime

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- WebSearchResult Schemas ---


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    query: str
    engine_used: str
    results: List[WebSearchResult]
    total_results: Optional[int] = None
    search_time: Optional[float] = None
    message: Optional[str] = None

    class Config:
        from_attributes = True

    # --- WebSearchRequest Schemas ---


class WebSearchRequest(BaseModel):
    query: str
    engine_config_id: int
    limit: int = 5


# --- TTSTextRequest Schemas ---
class TTSTextRequest(BaseModel):
    text: str
    lang: str = "zh-CN"


# --- KnowledgeBase Schemas ---
class KnowledgeBaseBase(BaseModel):
    name: str
    description: Optional[str] = None
    access_type: Optional[str] = "private"


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseResponse(KnowledgeBaseBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt is not None else None
        }


# --- KnowledgeArticle Schemas ---
class KnowledgeArticleBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    version: Optional[str] = "1.0"
    tags: Optional[str] = None


class KnowledgeArticleCreate(KnowledgeArticleBase):
    kb_id: int


class KnowledgeArticleResponse(KnowledgeArticleBase):
    id: int
    kb_id: int
    author_id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- KnowledgeDocument (for uploaded files) Schemas ---


class KnowledgeDocumentBase(BaseModel):
    file_name: str
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    status: Optional[str] = "processing"
    processing_message: Optional[str] = None
    total_chunks: Optional[int] = 0


class KnowledgeDocumentCreate(BaseModel):
    kb_id: int
    file_name: str


class KnowledgeDocumentResponse(KnowledgeDocumentBase):
    id: int
    kb_id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- KnowledgeDocumentChunk (for RAG) Schemas ---


class KnowledgeDocumentChunkResponse(BaseModel):
    id: int
    document_id: int
    owner_id: int
    kb_id: int
    chunk_index: int
    content: str
    combined_text: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- Course Schemas ---


class CourseBase(BaseModel):
    title: str
    description: Optional[str] = None
    instructor: Optional[str] = None
    category: Optional[str] = None
    total_lessons: Optional[int] = 0
    avg_rating: Optional[float] = 0.0


class CourseCreate(CourseBase):
    pass


class CourseResponse(CourseBase):
    id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- UserCourse Schemas ---


class UserCourseBase(BaseModel):
    student_id: int
    course_id: int
    progress: Optional[float] = 0.0
    status: Optional[str] = "in_progress"


class UserCourseCreate(UserCourseBase):
    pass


class UserCourseResponse(UserCourseBase):
    last_accessed: datetime
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- CollectionItem Schemas (旧版，可以考虑重构或废弃) ---


class CollectionItemBase(BaseModel):
    user_id: int
    item_type: str
    item_id: int


class CollectionItemCreate(CollectionItemBase):
    pass


class CollectionItemResponse(BaseModel):
    id: int
    user_id: int
    item_type: str
    item_id: int
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- API Response for Match Results ---


class MatchedProject(BaseModel):
    project_id: int
    title: str
    description: str
    similarity_stage1: float
    relevance_score: float


class MatchedStudent(BaseModel):
    student_id: int
    name: str
    major: str
    skills: str
    similarity_stage1: float
    relevance_score: float


# --- 用户登录模型 ---
class UserLogin(BaseModel):
    """用户登录时的数据模型，只包含邮箱和密码"""
    email: EmailStr
    password: str

# --- JWT 令牌响应模型 ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer" # JWT 令牌类型，通常是 "bearer"
    # 可以添加过期时间等其他信息
    expires_in_minutes: int = 0 # 令牌过期时间，单位分钟 (可选)


# --- UserLLMConfigUpdate ---
class UserLLMConfigUpdate(BaseModel):
    llm_api_type: Optional[Literal[
        "openai",
        "zhipu",
        "siliconflow",
        "huoshanengine",
        "kimi",
        "deepseek"
    ]] = None
    llm_api_key: Optional[str] = None
    llm_api_base_url: Optional[str] = None
    llm_model_id: Optional[str] = None


# --- AI Q&A Schemas ---
class AIQARequest(BaseModel):
    query: str
    kb_ids: Optional[List[int]] = None  # 知识库ID列表，用于RAG
    note_ids: Optional[List[int]] = None  # 笔记ID列表，用于RAG

    # 新增字段，控制是否允许AI使用工具 (如网络搜索, MCP工具)
    use_tools: Optional[bool] = False
    # 新增字段，指定优先使用的工具类型，或允许AI自动选择
    preferred_tools: Optional[List[Literal["rag", "web_search", "mcp_tool"]]] = None

    llm_model_id: Optional[str] = None


# AIQAResponse 也要更新，以反映工具使用情况
class AIQAResponse(BaseModel):
    answer: str
    source_articles: Optional[List[Dict[str, Any]]] = None  # RAG模式下的来源文章
    search_results: Optional[List[Dict[str, Any]]] = None  # 网络搜索结果摘要，如果使用了网络搜索
    tool_calls: Optional[List[Dict[str, Any]]] = None  # 如果AI调用了工具，记录工具调用信息

    answer_mode: str  # "General_mode", "RAG_mode", "Tool_Use_mode"
    llm_type_used: Optional[str] = None
    llm_model_used: Optional[str] = None

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

    # --- Semantic Search Schemas ---


class SemanticSearchRequest(BaseModel):
    query: str
    item_types: Optional[List[str]] = None
    limit: int = 10


class SemanticSearchResult(BaseModel):
    id: int
    title: str
    type: str
    content_snippet: Optional[str] = None
    relevance_score: float


# --- Dashboard Schemas ---
class DashboardSummaryResponse(BaseModel):
    active_projects_count: int
    completed_projects_count: int
    learning_courses_count: int
    completed_courses_count: int
    active_chats_count: int = 0
    unread_messages_count: int = 0
    resume_completion_percentage: float


class DashboardProjectCard(BaseModel):
    id: int
    title: str
    progress: float = 0.0

    class Config:
        orm_mode = True
        from_attributes = True


class DashboardCourseCard(BaseModel):
    id: int
    title: str
    progress: float = 0.0
    last_accessed: Optional[datetime] = None

    class Config:
        orm_mode = True
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
