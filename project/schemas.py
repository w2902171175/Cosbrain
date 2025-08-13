# project/schemas.py
from pydantic import BaseModel, EmailStr, Field, model_validator, field_validator
from typing import Optional, List, Dict, Any, Literal, Union
from datetime import datetime
import json


# --- 自定义公共Schema ---
# 定义技能熟练度模型，包含古文优雅的描述
class SkillWithProficiency(BaseModel):
    name: str = Field(..., description="技能名称")
    # 熟练度等级，使用 Literal 限制可选值
    level: Literal[
        "初窥门径", "登堂入室", "融会贯通", "炉火纯青"
    ] = Field(..., description="熟练度等级：初窥门径, 登堂入室, 融会贯通, 炉火纯青")

    class Config:
        # 允许从ORM对象创建，但由于它通常是内嵌在其他模型中，其父模型有 from_attributes 即可
        # 也可以在此明确指定 from_attributes = True
        pass


# --- Student Schemas ---
class StudentBase(BaseModel):
    """学生基础信息模型，用于创建或更新时接收数据"""
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="用户在平台内唯一的用户名/昵称")
    phone_number: Optional[str] = Field(None, min_length=11, max_length=11,
                                        description="用户手机号，用于登录和重置密码")  # 假设手机号是11位
    school: Optional[str] = Field(None, max_length=100, description="用户所属学校名称")

    name: Optional[str] = Field(None, description="用户真实姓名")
    major: Optional[str] = None
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="用户技能列表及熟练度")
    interests: Optional[str] = None
    bio: Optional[str] = None
    awards_competitions: Optional[str] = None
    academic_achievements: Optional[str] = None
    soft_skills: Optional[str] = None
    portfolio_link: Optional[str] = None
    preferred_role: Optional[str] = None
    availability: Optional[str] = None
    location: Optional[str] = Field(None, description="学生所在地理位置，例如：广州大学城，珠海横琴")


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
    embedding: Optional[List[float]] = None
    llm_api_type: Optional[Literal[
        "openai", "zhipu", "siliconflow", "huoshanengine", "kimi", "deepseek", "custom_openai"
    ]] = None
    llm_api_base_url: Optional[str] = None
    llm_model_id: Optional[str] = None
    llm_api_key_encrypted: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    is_admin: bool
    total_points: int
    last_login_at: Optional[datetime] = None
    login_count: int

    completed_projects_count: Optional[int] = Field(None, description="用户创建并已完成的项目总数")
    completed_courses_count: Optional[int] = Field(None, description="用户完成的课程总数")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


class StudentUpdate(BaseModel): # StudentUpdate 一般直接继承 BaseModel
    """更新学生信息时的模型，所有字段均为可选"""
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="用户在平台内唯一的用户名/昵称")
    phone_number: Optional[str] = Field(None, min_length=11, max_length=11, description="用户手机号")
    school: Optional[str] = Field(None, max_length=100, description="用户所属学校名称")

    name: Optional[str] = Field(None, description="用户真实姓名")
    major: Optional[str] = None
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="用户技能列表及熟练度")
    interests: Optional[str] = None
    bio: Optional[str] = None
    awards_competitions: Optional[str] = None
    academic_achievements: Optional[str] = None
    soft_skills: Optional[str] = None
    portfolio_link: Optional[str] = None
    preferred_role: Optional[str] = None
    availability: Optional[str] = None
    location: Optional[str] = Field(None, description="学生所在地理位置，例如：广州大学城，珠海横琴")


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


class ProjectCreate(ProjectBase):
    """创建项目时的数据模型"""
    pass # ProjectCreate 继承 ProjectBase，自动拥有新字段


class ProjectResponse(ProjectBase):
    """返回项目信息时的模型"""
    id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # ProjectResponse 继承 ProjectBase，自动拥有新字段

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

class ProjectUpdate(BaseModel): # ProjectUpdate 一般直接继承 BaseModel
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
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- CollectedContent Schemas ---
class CollectedContentBase(BaseModel):
    """具体收藏内容基础信息模型，用于创建或更新时接收数据"""
    title: str
    type: Literal[
        "document", "video", "note", "link", "file", "forum_topic", "course", "project", "knowledge_article",
        "daily_record"]
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


class CollectedContentSharedItemAddRequest(BaseModel):
    """
    用于从平台内部快速收藏一个项目、课程、论坛话题等内容的请求体。
    后端会根据 shared_item_type 和 shared_item_id 自动填充大部分内容。
    """
    shared_item_type: Literal[
        "project",
        "course",
        "forum_topic",
        "note",
        "daily_record",
        "knowledge_article",
        "chat_message",
        "knowledge_document"
    ] = Field(..., description="要收藏的平台内部内容的类型")
    shared_item_id: int = Field(..., description="要收藏的平台内部内容的ID")

    folder_id: Optional[int] = Field(None, description="要收藏到的文件夹ID")
    notes: Optional[str] = Field(None, description="收藏时的个人备注")
    is_starred: Optional[bool] = Field(None, description="是否立即为该收藏添加星标")

    # 允许用户在快速收藏时给一个自定义标题，但如果后端能提取，优先提取
    # 这个字段在 CollectedContentBase 里面，这里不强制要求
    title: Optional[str] = Field(None, description="收藏项的自定义标题。如果为空，后端将从共享项中提取。")


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
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- ChatRoom Schemas ---
class ChatRoomBase(BaseModel):
    """聊天室基础信息模型，用于创建或更新时接收数据"""
    name: str = Field(..., max_length=100) # 明确名称为必填且最大长度
    type: Literal["project_group", "course_group", "private", "general"] = Field("general", description="聊天室类型")
    project_id: Optional[int] = Field(None, description="如果为项目群组，关联的项目ID")
    course_id: Optional[int] = Field(None, description="如果为课程群组，关联的课程ID")
    color: Optional[str] = Field(None, max_length=20) # 颜色字符串，例如 "#FFFFFF"


# 聊天室成员基础信息 (用于请求和响应)
class ChatRoomMemberBase(BaseModel):
    room_id: int
    member_id: int
    role: Literal["admin", "member"] = Field("member", description="成员角色：'admin'或'member'")
    status: Literal["active", "banned", "left"] = Field("active", description="成员状态：'active', 'banned', 'left'")
    last_read_at: Optional[datetime] = None


# 聊天室成员响应信息 (包含 ID 和时间戳)
class ChatRoomMemberResponse(ChatRoomMemberBase):
    id: int
    joined_at: datetime
    member_name: Optional[str] = Field(None, description="成员的姓名")

    class Config:
        from_attributes = True  # Pydantic V2
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}  # 保持一致


# 用于更新成员角色的请求体
class ChatRoomMemberRoleUpdate(BaseModel):
    role: Literal["admin", "member"] = Field(..., description="要设置的新角色：'admin' 或 'member'")


# 入群申请请求体
class ChatRoomJoinRequestCreate(BaseModel):
    room_id: int = Field(..., description="目标聊天室ID")
    reason: Optional[str] = Field(None, description="入群申请理由")


# 入群申请处理请求体 (用于管理员/群主批准或拒绝)
class ChatRoomJoinRequestProcess(BaseModel):
    status: Literal["approved", "rejected"] = Field(..., description="处理结果状态：'approved' 或 'rejected'")  # 只能是这两个字符串
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


# 聊天室更新请求体，所有字段均为可选
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
    base_url: Optional[str] = Field(None, description="搜索引擎API的基础URL，例如：https://api.tavily.com")


class UserSearchEngineConfigCreate(UserSearchEngineConfigBase):
    name: str
    engine_type: Literal["bing", "tavily", "baidu", "google_cse", "custom"]
    pass

class UserSearchEngineConfigResponse(UserSearchEngineConfigBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


class UserTTSConfigBase(BaseModel):
    name: str = Field(..., description="TTS配置名称，如：'我的OpenAI语音'")
    tts_type: Literal[
        "openai", # OpenAI的TTS服务类型
        "gemini", # Google Gemini的TTS服务类型
        "aliyun", # 阿里云的TTS服务类型
        "siliconflow" # 硅基流动的TTS服务类型，假设存在
    ] = Field(..., description="语音提供商类型，如：'openai', 'gemini', 'aliyun', 'siliconflow'")
    api_key: Optional[str] = Field(None, description="API密钥（未加密）") # 输入时接收的明文密钥
    base_url: Optional[str] = Field(None, description="API基础URL，如有自定义需求")
    model_id: Optional[str] = Field(None, description="语音模型ID，如：'tts-1', 'gemini-pro'")
    voice_name: Optional[str] = Field(None, description="语音名称或ID，如：'alloy', 'f_cn_zh_anqi_a_f'")
    is_active: Optional[bool] = Field(False, description="是否当前激活的TTS配置，每个用户只能有一个激活配置")

    # 解决 Pydantic 'model_' 命名空间冲突警告
    model_config = { # Pydantic V2 的配置方式是 model_config
        'protected_namespaces': () # 解除对 'model_' 命名空间的保护
    }


class UserTTSConfigCreate(UserTTSConfigBase):
    # 创建时 name 和 tts_type 必须提供，api_key 必须提供
    name: str = Field(..., description="TTS配置名称")
    tts_type: Literal[
        "openai", "gemini", "aliyun", "siliconflow"
    ] = Field(..., description="语音提供商类型")
    api_key: str = Field(..., description="API密钥（未加密）")

    #  解决 Pydantic 'model_' 命名空间冲突警告
    model_config = {
        'protected_namespaces': ()
    }


class UserTTSConfigUpdate(UserTTSConfigBase):
    # 更新时所有字段均为可选
    name: Optional[str] = None
    tts_type: Optional[Literal["openai", "gemini", "aliyun", "siliconflow"]] = None
    api_key: Optional[str] = None # 更新时如果提供，则更新密钥
    base_url: Optional[str] = None
    model_id: Optional[str] = None
    voice_name: Optional[str] = None
    is_active: Optional[bool] = None # 允许更新激活状态

    #  解决 Pydantic 'model_' 命名空间冲突警告
    model_config = {
        'protected_namespaces': ()
    }

class UserTTSConfigResponse(UserTTSConfigBase):
    id: int
    owner_id: int
    api_key_encrypted: Optional[str] = Field(None, description="加密后的API密钥") # 响应时返回的是加密后的密钥
    created_at: datetime
    updated_at: Optional[datetime] = None

    # 合并 Pydantic 配置，移除 class Config:
    model_config = {
        'protected_namespaces': (), # 解除对 'model_' 命名空间的保护
        'from_attributes': True,   # 从 ORM 模型创建实例
        'json_encoders': {datetime: lambda dt: dt.isoformat() if dt is not None else None} # 将 json_encoders 移到此处
    }

# --- TTSTextRequest Schemas ---
class TTSTextRequest(BaseModel):
    text: str
    lang: str = "zh-CN"


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
    cover_image_url: Optional[str] = Field(None, description="课程封面图片的URL链接")
    required_skills: Optional[List[SkillWithProficiency]] = Field(None, description="课程所需基础技能列表及熟练度，或学习该课程所需前置技能")

class CourseCreate(CourseBase):
    pass

class CourseResponse(CourseBase): # CourseResponse 继承 CourseBase，所以新增字段会自动包含
    id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

class CourseUpdate(BaseModel):
    """更新课程信息时的数据模型，所有字段均为可选"""
    title: Optional[str] = None
    description: Optional[str] = None
    instructor: Optional[str] = None
    category: Optional[str] = None
    total_lessons: Optional[int] = None
    avg_rating: Optional[float] = None
    cover_image_url: Optional[str] = Field(None, description="课程封面图片的URL链接")
    required_skills: Optional[List[SkillWithProficiency]] = Field(None, description="课程所需基础技能列表及熟练度，或学习该课程所需前置技能")


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
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- CourseMaterial Schemas ---
class CourseMaterialBase(BaseModel):
    title: str = Field(..., description="课程材料标题")
    type: Literal["file", "link", "text"] = Field(...,
                                                  description="材料类型：'file' (上传文件), 'link' (外部链接), 'text' (少量文本内容)")

    # 根据类型提供相应的数据
    url: Optional[str] = Field(None, description="当类型为'link'时，提供外部链接URL")
    content: Optional[str] = Field(None, description="当类型为'text'时，提供少量文本内容，或作为文件/链接的补充描述")

    # 仅在需要更新文件时（PUT操作中替换文件）使用，POST上传文件时不需要客户端提供这些
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    file_type: Optional[str] = Field(None, description="文件MIME类型")  # 例如：'application/pdf', 'video/mp4'
    size_bytes: Optional[int] = Field(None, description="文件大小（字节）")

    # 验证逻辑：根据 `type` 字段，强制要求 `url` 或 `content`
    @field_validator('url', 'content', 'original_filename', 'file_type', 'size_bytes', mode='before')
    def validate_material_fields(cls, v, info):
        # 仅在创建时（即没有实例）进行严格检查
        if not info.data.get('type'):  # 如果type字段都没有，则跳过更深层次的验证
            return v

        material_type = info.data['type']
        field_name = info.field_name

        if material_type == "link":
            if field_name == "url" and not v:
                raise ValueError("类型为 'link' 时，'url' 字段为必填。")
            if field_name in ['original_filename', 'file_type', 'size_bytes'] and v is not None:
                raise ValueError(f"类型为 'link' 时，'{field_name}' 字段不应提供。")
        elif material_type == "text":
            if field_name == "content" and not v:
                raise ValueError("类型为 'text' 时，'content' 字段为必填。")
            if field_name in ['url', 'original_filename', 'file_type', 'size_bytes'] and v is not None:
                raise ValueError(f"类型为 'text' 时，'{field_name}' 字段不应提供。")
        # 对于 "file" 类型，这些字段会在后端处理，客户端通常不必提供

        return v


class CourseMaterialCreate(CourseMaterialBase):
    # 创建时 title 和 type 必须提供
    title: str
    type: Literal["file", "link", "text"]


class CourseMaterialUpdate(CourseMaterialBase):
    # 更新时所有字段均为可选
    title: Optional[str] = None
    type: Optional[Literal["file", "link", "text"]] = None


class CourseMaterialResponse(CourseMaterialBase):
    id: int
    course_id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
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
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- API Response for Match Results ---
class MatchedProject(BaseModel):
    project_id: int
    title: str
    description: str
    similarity_stage1: float # 通常指第一阶段筛选得分或综合得分
    relevance_score: float   # 最终重排后的相关性得分
    # 匹配理由字段
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")


class MatchedCourse(BaseModel):
    course_id: int
    title: str
    description: str
    instructor: Optional[str] = None
    category: Optional[str] = None
    cover_image_url: Optional[str] = None
    similarity_stage1: float # 通常指第一阶段筛选得分或综合得分
    relevance_score: float   # 最终重排后的相关性得分
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与课程匹配理由及建议")


class CountResponse(BaseModel):
    """通用计数响应模型"""
    count: int = Field(..., description="统计数量")
    description: Optional[str] = Field(None, description="统计的描述信息")


class MatchedStudent(BaseModel):
    student_id: int
    name: str
    major: str
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="学生的技能列表及熟练度详情")
    similarity_stage1: float # 通常指第一阶段筛选得分或综合得分
    relevance_score: float   # 最终重排后的相关性得分
    # 匹配理由字段
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")


# --- 用户登录模型 ---
class UserLogin(BaseModel):
    """用户登录时的数据模型，只包含邮箱和密码"""
    email: EmailStr
    password: str


# --- JWT 令牌响应模型 ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # JWT 令牌类型，通常是 "bearer"
    # 可以添加过期时间等其他信息
    expires_in_minutes: int = 0  # 令牌过期时间，单位分钟 (可选)


# --- UserLLMConfigUpdate ---
class UserLLMConfigUpdate(BaseModel):
    llm_api_type: Optional[Literal[
        "openai",
        "zhipu",
        "siliconflow",
        "huoshanengine",
        "kimi",
        "deepseek",
        "custom_openai"
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
    conversation_id: Optional[int] = Field(None, description="要继续的对话Session ID。如果为空，则开始新的对话。")


class AIQAResponse(BaseModel):
    answer: str  # 统一返回最终答案

    # AIQA相关通用信息
    answer_mode: str  # "General_mode", "RAG_mode", "Tool_Use_mode"
    llm_type_used: Optional[str] = None
    llm_model_used: Optional[str] = None

    # 新增会话ID，用于客户端后续保持会话
    conversation_id: int = Field(..., description="当前问答所关联的对话Session ID。")
    # 当前轮次产生的所有消息，方便前端显示和区分角色
    # 例如：用户消息 -> LLM工具调用消息 -> 工具输出消息 -> LLM回复消息
    turn_messages: List["AIConversationMessageResponse"] = Field(..., description="当前轮次（包括用户问题和AI回复）产生的完整消息序列。")

    source_articles: Optional[List[Dict[str, Any]]] = None  # RAG模式下的来源文章
    search_results: Optional[List[Dict[str, Any]]] = None  # 网络搜索结果摘要，如果使用了网络搜索

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


class AIConversationBase(BaseModel):
    title: Optional[str] = Field(None, description="对话标题")


class AIConversationCreate(AIConversationBase):
    pass


class AIConversationResponse(AIConversationBase):
    id: int
    user_id: int
    created_at: datetime
    last_updated: datetime

    # 可以在这里包含最近的消息概要，或总消息数，如果需要
    total_messages_count: Optional[int] = Field(None, description="对话中的总消息数量")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- AI Conversation Message Schemas ---
class AIConversationMessageBase(BaseModel):
    role: Literal["user", "assistant", "tool_call", "tool_output"] = Field(...,
                                                                           description="消息角色: user, assistant, tool_call, tool_output")
    content: str = Field(..., description="消息内容（文本）")

    tool_calls_json: Optional[Dict[str, Any]] = Field(None,
                                                      description="如果角色是'tool_call'，存储原始工具调用的JSON数据")
    tool_output_json: Optional[Dict[str, Any]] = Field(None,
                                                       description="如果角色是'tool_output'，存储原始工具输出的JSON数据")

    llm_type_used: Optional[str] = Field(None, description="本次消息使用的LLM类型")
    llm_model_used: Optional[str] = Field(None, description="本次消息使用的LLM模型ID")


class AIConversationMessageCreate(AIConversationMessageBase):
    pass


class AIConversationMessageResponse(AIConversationMessageBase):
    id: int
    conversation_id: int
    sent_at: datetime

    class Config:
        from_attributes = True
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
        from_attributes = True


class DashboardCourseCard(BaseModel):
    id: int
    title: str
    progress: float = 0.0
    last_accessed: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- Achievement Schemas ---
class AchievementBase(BaseModel):
    name: str = Field(..., description="成就名称")
    description: str = Field(..., description="成就描述")
    # Literal 限制条件类型，例如：PROJECT_COMPLETED_COUNT, COURSE_COMPLETED_COUNT 等
    criteria_type: Literal[
        "PROJECT_COMPLETED_COUNT", "COURSE_COMPLETED_COUNT", "FORUM_LIKES_RECEIVED",
        "DAILY_LOGIN_STREAK", "FORUM_POSTS_COUNT", "CHAT_MESSAGES_SENT_COUNT",
        "LOGIN_COUNT" # 明确增加登录次数作为条件
    ] = Field(..., description="达成成就的条件类型")
    criteria_value: float = Field(..., description="达成成就所需的数值门槛") # 使用Float以支持小数，如平均分

    badge_url: Optional[str] = Field(None, description="勋章图片或图标URL")
    reward_points: int = Field(0, description="达成此成就额外奖励的积分")
    is_active: bool = Field(True, description="该成是否启用")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


class AchievementCreate(AchievementBase):
    # 创建成就时，所有基础字段都是必需的 (除非它们有默认值)
    pass


class AchievementUpdate(AchievementBase):
    # 更新成就时，所有字段都是可选的
    name: Optional[str] = None
    description: Optional[str] = None
    criteria_type: Optional[Literal[
        "PROJECT_COMPLETED_COUNT", "COURSE_COMPLETED_COUNT", "FORUM_LIKES_RECEIVED",
        "DAILY_LOGIN_STREAK", "FORUM_POSTS_COUNT", "CHAT_MESSAGES_SENT_COUNT",
        "LOGIN_COUNT"
    ]] = None
    criteria_value: Optional[float] = None
    badge_url: Optional[str] = None
    reward_points: Optional[int] = None
    is_active: Optional[bool] = None


class AchievementResponse(AchievementBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


# --- UserAchievement Schemas ---
class UserAchievementResponse(BaseModel):
    id: int
    user_id: int
    achievement_id: int
    earned_at: datetime
    is_notified: bool

    # 包含成就的实际名称和描述，方便前端展示，避免再次查询
    achievement_name: Optional[str] = Field(None, description="成就名称")
    achievement_description: Optional[str] = Field(None, description="成就描述")
    badge_url: Optional[str] = Field(None, description="勋章图片URL")
    reward_points: Optional[int] = Field(None, description="获得此成就奖励的积分")


    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- PointsRewardRequest Schema (用于手动发放/扣除积分) ---
class PointsRewardRequest(BaseModel):
    user_id: int = Field(..., description="目标用户ID")
    amount: int = Field(..., description="积分变动数量，正数代表增加，负数代表减少")
    reason: Optional[str] = Field(None, description="积分变动理由")
    transaction_type: Literal["EARN", "CONSUME", "ADMIN_ADJUST"] = Field("ADMIN_ADJUST", description="交易类型")
    related_entity_type: Optional[str] = Field(None, description="关联的实体类型（如 project, course, forum_topic）")
    related_entity_id: Optional[int] = Field(None, description="关联实体ID")

# --- PointTransaction Schemas ---
class PointTransactionResponse(BaseModel):
    id: int
    user_id: int
    amount: int
    reason: Optional[str] = Field(None, description="积分变动理由描述")
    transaction_type: str = Field(..., description="积分交易类型")
    related_entity_type: Optional[str] = Field(None, description="关联的实体类型")
    related_entity_id: Optional[int] = Field(None, description="关联实体的ID")
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

