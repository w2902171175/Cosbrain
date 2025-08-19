# project/schemas.py (片段修改)
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
        from_attributes = True


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
    llm_model_ids: Optional[Dict[str, List[str]]] = None
    llm_api_key_encrypted: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    is_admin: bool
    total_points: int
    last_login_at: Optional[datetime] = None
    login_count: int

    completed_projects_count: Optional[int] = Field(None, description="用户创建并已完成的项目总数")
    completed_courses_count: Optional[int] = Field(None, description="用户完成的课程总数")

    # 3. 添加下面的验证器函数
    @field_validator('llm_model_ids', mode='before')
    @classmethod
    def parse_llm_model_ids(cls, value):
        """
        在验证之前，尝试将字符串类型的 llm_model_ids 解析为字典。
        """
        # 如果值是字符串类型，就尝试用 json.loads 解析它
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # 如果字符串不是有效的JSON，返回None，符合字段的Optional属性
                return None
        # 如果值不是字符串（比如已经是dict或None），直接返回原值
        return value

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

class StudentUpdate(BaseModel):
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
    # --- 新增项目封面图片相关字段 ---
    cover_image_url: Optional[str] = Field(None, description="项目封面图片的OSS URL")
    cover_image_original_filename: Optional[str] = Field(None, description="原始上传的封面图片文件名")
    cover_image_type: Optional[str] = Field(None, description="封面图片MIME类型，例如 'image/jpeg'")
    cover_image_size_bytes: Optional[int] = Field(None, description="封面图片文件大小（字节）")
    # --- 新增字段结束 ---


class ProjectCreate(ProjectBase):
    """创建项目时的数据模型"""
    pass


class ProjectResponse(ProjectBase):
    """返回项目信息时的模型"""
    id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    likes_count: Optional[int] = Field(None, description="点赞数量")
    is_liked_by_current_user: Optional[bool] = Field(False, description="当前用户是否已点赞")
    # --- 新增项目文件列表 ---
    project_files: Optional[List['ProjectFileResponse']] = Field(None, description="项目关联的文件列表")
    # --- 新增结束 ---

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
    # --- 新增字段结束 ---


# --- Project File Update/Delete helper Schemas ---
class ProjectFileUpdateData(BaseModel):
    id: int = Field(..., description="要更新的项目文件ID")
    file_name: Optional[str] = Field(None, description="更新后的文件名（可选，如果仅更新描述或权限）")
    description: Optional[str] = Field(None, description="更新后的文件描述")
    access_type: Optional[Literal["public", "member_only"]] = Field(None, description="更新后的文件访问权限")

    # 注意：file_path, file_type, size_bytes, oss_object_name 不应通过此接口更新。
    # 如果要替换文件，需要先删除旧文件，再上传新文件。

class ProjectFileDeletionRequest(BaseModel):
    file_ids: List[int] = Field(..., description="要删除的项目文件ID列表")

class ProjectUpdateWithFiles(BaseModel):
    """
    用于更新项目及其文件（包括新增、修改、删除）的组合请求体。
    项目的主体数据通过 project_data 提供，文件操作通过单独的字段提供。
    """
    project_data: ProjectUpdate = Field(..., description="要更新的项目主体数据")
    files_to_upload: Optional[List[Dict[str, Any]]] = Field(None, description="新上传文件的数据（文件名、描述、访问权限），文件本身通过 multipart form 另行传入。")
    files_to_delete_ids: Optional[List[int]] = Field(None, description="仅删除，这些id对应的文件将从OSS和数据库中删除。")
    files_to_update_metadata: Optional[List[ProjectFileUpdateData]] = Field(None, description="更新文件元数据（如描述、访问权限）。")



# --- Project Application Schemas ---
class ProjectApplicationBase(BaseModel):
    message: Optional[str] = Field(None, description="申请留言，例如为什么想加入")


class ProjectApplicationCreate(ProjectApplicationBase):
    pass


class ProjectApplicationResponse(ProjectApplicationBase):
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

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


class ProjectApplicationProcess(BaseModel):
    status: Literal["approved", "rejected"] = Field(..., description="处理结果: approved (批准) 或 rejected (拒绝)")
    process_message: Optional[str] = Field(None, description="审批附言，例如拒绝原因")


# --- Project Member Schemas ---
class ProjectMemberBase(BaseModel):
    role: Literal["admin", "member"] = Field("member", description="项目成员角色: admin (管理员) 或 member (普通成员)")


class ProjectMemberResponse(ProjectMemberBase):
    id: int
    project_id: int
    student_id: int
    joined_at: datetime
    member_name: Optional[str] = Field(None, description="成员姓名")
    member_email: Optional[EmailStr] = Field(None, description="成员邮箱")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- 新增 ProjectFile Schemas ---
class ProjectFileBase(BaseModel):
    file_name: str = Field(..., description="原始文件名")
    description: Optional[str] = Field(None, description="文件描述")
    access_type: Literal["public", "member_only"] = Field("member_only", description="文件访问权限: public (所有用户可见) 或 member_only (仅项目成员可见)")


class ProjectFileCreate(ProjectFileBase):
    pass


class ProjectFileResponse(ProjectFileBase):
    id: int
    project_id: int
    upload_by_id: int
    oss_object_name: str = Field(..., description="文件在OSS中的对象名称")
    file_path: str = Field(..., description="文件在OSS上的完整URL")
    file_type: Optional[str] = Field(None, description="文件的MIME类型")
    size_bytes: Optional[int] = Field(None, description="文件大小（字节）")
    created_at: datetime
    updated_at: Optional[datetime] = None

    @property # Pydantic v2 @property 支持
    def uploader_name(self) -> Optional[str]:
        # ORM 对象上通过 `_uploader_name` 赋值，@property 来读取它
        return getattr(self, '_uploader_name', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True # 确保 @property 名称被正确序列化

# --- ProjectResponse 预警解决 (Forward Reference) ---
ProjectResponse.model_rebuild()


# --- Note Schemas ---
class NoteBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    note_type: Optional[str] = "general"
    course_id: Optional[int] = Field(None, description="关联的课程ID")
    tags: Optional[str] = None
    chapter: Optional[str] = Field(None, description="课程章节信息，例如：第一章 - AI概述")
    media_url: Optional[str] = Field(None, description="笔记中嵌入的图片、视频或文件的OSS URL")
    media_type: Optional[Literal["image", "video", "file"]] = Field(None, description="媒体类型：'image', 'video', 'file'")
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    media_size_bytes: Optional[int] = Field(None, description="媒体文件大小（字节）")
    folder_id: Optional[int] = Field(None, description="关联的用户自定义文件夹ID。如果为None，则表示笔记未放入特定文件夹。")

    @model_validator(mode='after')
    def validate_media_and_content(self) -> 'NoteBase':
        if not self.content and not self.media_url:
            raise ValueError("笔记内容 (content) 和媒体文件 (media_url) 至少需要提供一个。")
        if self.media_type and not self.media_url:
            raise ValueError(f"当 media_type 为 '{self.media_type}' 时，media_url 不能为空。")
        if self.media_url and not self.media_type:
            raise ValueError("media_url 存在时，media_type 不能为空，且必须为 'image', 'video' 或 'file'。")
        is_course_note = (self.course_id is not None) or (self.chapter is not None and self.chapter.strip() != "")
        is_folder_note = (self.folder_id is not None)
        if is_course_note and is_folder_note:
            raise ValueError("笔记不能同时关联到课程/章节和自定义文件夹。请选择一种组织方式。")
        if (self.chapter is not None and self.chapter.strip() != "") and (self.course_id is None):
            raise ValueError("为了关联章节信息，课程ID (course_id) 不能为空。")
        if self.folder_id == 0:
            self.folder_id = None
        return self


class NoteCreate(NoteBase):
    pass


class NoteResponse(NoteBase):
    id: int
    owner_id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @property # Pydantic v2 @property 支持，这里将其暴露为不带下划线的公共属性
    def folder_name(self) -> Optional[str]:
        # ORM 对象上通过 `_folder_name_for_response` 赋值，@property 来读取它
        return getattr(self, '_folder_name_for_response', None)

    @property
    def course_title(self) -> Optional[str]:
        return getattr(self, '_course_title_for_response', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


# --- DailyRecord Schemas ---
class DailyRecordBase(BaseModel):
    """随手记录基础信息模型，用于创建或更新时接收数据"""
    content: str
    mood: Optional[str] = None
    tags: Optional[str] = None


class DailyRecordCreate(DailyRecordBase):
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
        "document", "video", "note", "link", "file", "image",
        "forum_topic", "course", "project", "knowledge_article",
        "daily_record"] = Field(..., description="内容类型：document, video, note, link, file, image, forum_topic, course, project, knowledge_article, daily_record")
    url: Optional[str] = Field(None, description="外部链接或OSS URL")
    content: Optional[str] = Field(None, description="文本内容或简要描述")
    tags: Optional[str] = None
    folder_id: Optional[int] = None
    priority: Optional[int] = None
    notes: Optional[str] = None
    is_starred: Optional[bool] = None
    thumbnail: Optional[str] = None
    author: Optional[str] = None
    duration: Optional[str] = None
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    status: Optional[Literal["active", "archived", "deleted"]] = None

    @model_validator(mode='after')
    def validate_content_or_url(self) -> 'CollectedContentBase':
        if self.type == "link":
            if not self.url:
                raise ValueError("类型为 'link' 时，'url' 字段为必填。")
        elif self.type in ["file", "image", "video"]:
            if not self.url:
                raise ValueError(f"类型为 '{self.type}' 时，'url' (文件/媒体URL) 为必填。")
        elif self.type not in ["file", "image", "video", "link"]:
            if not self.content and not self.url and not (
                getattr(self, 'shared_item_type', None) and getattr(self, 'shared_item_id', None)
            ):
                raise ValueError(f"类型为 '{self.type}' 时，'content' 和 'url' (如果适用) 至少需要提供一个。")
        return self


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
    is_starred: Optional[bool] = Field(False, description="是否立即为该收藏添加星标")
    title: Optional[str] = Field(None, description="收藏项的自定义标题。如果为空，后端将从共享项中提取。")



class CollectItemRequestBase(BaseModel):
    """
    收藏操作的基础请求体，用于接收可选的文件夹、备注、星标和自定义标题等信息。
    """
    folder_id: Optional[int] = Field(None, description="要收藏到的文件夹ID。传入0表示顶级文件夹（即folder_id为NULL）")
    notes: Optional[str] = Field(None, description="收藏时的个人备注")
    is_starred: Optional[bool] = Field(False, description="是否立即为该收藏添加星标")
    title: Optional[str] = Field(None, description="收藏项的自定义标题。如果为空，后端将从共享项中提取。")
    priority: Optional[int] = Field(None, description="收藏内容的优先级")

    @model_validator(mode='after')
    def convert_zero_to_none_folder(self) -> 'CollectItemRequestBase':
        if self.folder_id == 0:
            self.folder_id = None
        return self


class CollectedContentCreate(CollectedContentBase):
    pass


class CollectedContentResponse(CollectedContentBase):
    """返回具体收藏内容信息时的模型"""
    id: int
    owner_id: int
    access_count: Optional[int] = None
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @property
    def folder_name(self) -> Optional[str]:
        return getattr(self, '_folder_name_for_response', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


# --- ChatRoom Schemas ---
class ChatRoomBase(BaseModel):
    """聊天室基础信息模型，用于创建或更新时接收数据"""
    name: str = Field(..., max_length=100)
    type: Literal["project_group", "course_group", "private", "general"] = Field("general", description="聊天室类型")
    project_id: Optional[int] = Field(None, description="如果为项目群组，关联的项目ID")
    course_id: Optional[int] = Field(None, description="如果为课程群组，关联的课程ID")
    color: Optional[str] = Field(None, max_length=20)


class ChatRoomMemberBase(BaseModel):
    room_id: int
    member_id: int
    role: Literal["king", "admin", "member"] = Field("member", description="成员角色 (king: 群主, admin: 管理员, member: 普通成员)")
    status: Literal["active", "banned", "left"] = Field("active", description="成员状态 (active: 活跃, banned: 被踢出, left: 已离开)")
    last_read_at: Optional[datetime] = None


class ChatRoomMemberCreate(ChatRoomMemberBase):
    pass


class ChatRoomMemberResponse(ChatRoomMemberBase):
    id: int
    member_id: int
    joined_at: datetime
    member_name: Optional[str] = Field(None, description="成员的姓名")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


class ChatRoomMemberRoleUpdate(BaseModel):
    role: Literal["king", "admin", "member"] = Field(..., description="要设置的新角色：'admin' 或 'member'")


class ChatRoomJoinRequestCreate(BaseModel):
    room_id: int = Field(..., description="目标聊天室ID")
    reason: Optional[str] = Field(None, description="入群申请理由")


class ChatRoomJoinRequestProcess(BaseModel):
    status: Literal["approved", "rejected"] = Field(..., description="处理结果状态：'approved' 或 'rejected'")


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
    pass


class ChatRoomUpdate(ChatRoomBase):
    name: Optional[str] = None
    type: Optional[str] = None
    project_id: Optional[int] = None
    course_id: Optional[int] = None
    color: Optional[str] = None


class ChatRoomResponse(ChatRoomBase):
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
    content_text: Optional[str] = None
    message_type: Literal["text", "image", "file", "video", "system_notification"] = "text"
    media_url: Optional[str] = Field(None, description="媒体文件OSS URL或外部链接")

    @model_validator(mode='after')
    def check_content_or_media(self) -> 'ChatMessageBase':
        if self.message_type == "text":
            if not self.content_text:
                raise ValueError("当 message_type 为 'text' 时，content_text (消息内容) 不能为空。")
            if self.media_url:
                raise ValueError("当 message_type 为 'text' 时，media_url 不应被提供。")
        elif self.message_type in ["image", "file", "video"]:
            if not self.media_url:
                raise ValueError(f"当 message_type 为 '{self.message_type}' 时，media_url (媒体文件URL) 不能为空。")
        return self


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessageResponse(ChatMessageBase):
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
    title: str
    content: str
    shared_item_type: Optional[Literal[
        "note", "daily_record", "course", "project", "knowledge_article", "knowledge_base", "collected_content"]] = Field(
        None, description="如果分享平台内部内容，记录其类型")
    shared_item_id: Optional[int] = Field(None, description="如果分享平台内部内容，记录其ID")
    tags: Optional[str] = None
    media_url: Optional[str] = Field(None, description="图片、视频或文件的OSS URL")
    media_type: Optional[Literal["image", "video", "file"]] = Field(None, description="媒体类型：'image', 'video', 'file'")
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    media_size_bytes: Optional[int] = Field(None, description="媒体文件大小（字节）")

    @model_validator(mode='after')
    def validate_media_and_shared_item(self) -> 'ForumTopicBase':
        if self.media_type and not self.media_url:
            raise ValueError(f"当 media_type 为 '{self.media_type}' 时，media_url 不能为空。")
        if self.media_url and not self.media_type:
            raise ValueError("media_url 存在时，media_type 不能为空，且必须为 'image', 'video' 或 'file'。")
        if (self.shared_item_type and self.shared_item_id is not None) and self.media_url:
            raise ValueError("不能同时指定共享平台内容 (shared_item_type/id) 和直接上传媒体文件 (media_url)。请选择一种方式。")
        if (self.shared_item_type and self.shared_item_id is None) or \
                (self.shared_item_id is not None and not self.shared_item_type):
            raise ValueError("shared_item_type 和 shared_item_id 必须同时提供，或同时为空。")
        return self


class ForumTopicCreate(ForumTopicBase):
    pass


class ForumTopicResponse(ForumTopicBase):
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
    content: str
    parent_comment_id: Optional[int] = None
    media_url: Optional[str] = Field(None, description="图片、视频或文件的OSS URL")
    media_type: Optional[Literal["image", "video", "file"]] = Field(None, description="媒体类型：'image', 'video', 'file'")
    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    media_size_bytes: Optional[int] = Field(None, description="媒体文件大小（字节）")

    @model_validator(mode='after')
    def validate_media_in_comment(self) -> 'ForumCommentBase':
        if self.media_type and not self.media_url:
            raise ValueError(f"当 media_type 为 '{self.media_type}' 时，media_url 不能为空。")
        if self.media_url and not self.media_type:
            raise ValueError("media_url 存在时，media_type 不能为空，且必须为 'image', 'video' 或 'file'。")
        return self


class ForumCommentCreate(ForumCommentBase):
    pass


class ForumCommentResponse(ForumCommentBase):
    id: int
    topic_id: int
    owner_id: int
    # 移除直接声明的 _owner_name 字段
    likes_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_liked_by_current_user: Optional[bool] = False

    @property # 使用 @property 来暴露 'owner_name'
    def owner_name(self) -> str:
        # 安全地从 ORM 对象上访问动态设置的私有属性
        return getattr(self, '_owner_name', "未知用户")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True # 添加 populate_by_name 以确保 property 名称被正确序列化


# --- ForumLike Schemas ---
class ForumLikeResponse(BaseModel):
    id: int
    owner_id: int
    topic_id: Optional[int] = None
    comment_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- Project Like Schemas ---
class ProjectLikeResponse(BaseModel):
    id: int
    owner_id: int
    project_id: int
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}

# --- Course Like Schemas ---
class CourseLikeResponse(BaseModel):
    id: int
    owner_id: int
    course_id: int
    created_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}



# --- UserFollow Schemas ---
class UserFollowResponse(BaseModel):
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
    tool_id: str
    name: str
    description: str
    mcp_config_id: int
    mcp_config_name: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    class Config:
        from_attributes = True


# --- UsersSearchEngineConfig Schemas ---
class UserSearchEngineConfigBase(BaseModel):
    name: Optional[str] = None
    engine_type: Optional[Literal["bing", "tavily", "baidu", "google_cse", "custom"]] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = True
    description: Optional[str] = None
    base_url: Optional[str] = Field(None, description="搜索引擎API的基础URL。Tavily: https://api.tavily.com, Bing: https://api.bing.microsoft.com")


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
        "openai", "gemini", "aliyun", "siliconflow"
    ] = Field(..., description="语音提供商类型，如：'openai', 'gemini', 'aliyun', 'siliconflow'")
    api_key: Optional[str] = Field(None, description="API密钥（未加密）")
    base_url: Optional[str] = Field(None, description="API基础URL，如有自定义需求")
    model_id: Optional[str] = Field(None, description="语音模型ID，如：'tts-1', 'gemini-pro'")
    voice_name: Optional[str] = Field(None, description="语音名称或ID，如：'alloy', 'f_cn_zh_anqi_a_f'")
    is_active: Optional[bool] = Field(False, description="是否当前激活的TTS配置，每个用户只能有一个激活配置")

    model_config = {
        'protected_namespaces': ()
    }


class UserTTSConfigCreate(UserTTSConfigBase):
    name: str = Field(..., description="TTS配置名称")
    tts_type: Literal[
        "openai", "gemini", "aliyun", "siliconflow"
    ] = Field(..., description="语音提供商类型")
    api_key: str = Field(..., description="API密钥（未加密）")

    model_config = {
        'protected_namespaces': ()
    }


class UserTTSConfigUpdate(UserTTSConfigBase):
    name: Optional[str] = None
    tts_type: Optional[Literal["openai", "gemini", "aliyun", "siliconflow"]] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_id: Optional[str] = None
    voice_name: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = {
        'protected_namespaces': ()
    }


class UserTTSConfigResponse(UserTTSConfigBase):
    id: int
    owner_id: int
    api_key_encrypted: Optional[str] = Field(None, description="加密后的API密钥")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {
        'protected_namespaces': (),
        'from_attributes': True,
        'json_encoders': {datetime: lambda dt: dt.isoformat() if dt is not None else None}
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


# --- KnowledgeBaseFolder Schemas (已更新软链接字段，并修正命名) ---
class KnowledgeBaseFolderBase(BaseModel):
    name: str = Field(..., description="文件夹名称")
    description: Optional[str] = Field(None, description="文件夹描述")
    parent_id: Optional[int] = Field(None, description="父文件夹ID。传入0表示顶级文件夹（即parent_id为NULL）")
    order: Optional[int] = Field(None, description="排序")
    linked_folder_type: Optional[Literal["note_folder", "collected_content_folder"]] = Field(None, description="链接到的外部文件夹类型：'note_folder'（课程笔记文件夹）或'collected_content_folder'（收藏文件夹）")
    linked_folder_id: Optional[int] = Field(None, description="链接到的外部文件夹ID")

    @model_validator(mode='after')
    def convert_zero_to_none(self) -> 'KnowledgeBaseFolderBase':
        if self.parent_id == 0:
            self.parent_id = None
        return self

    @model_validator(mode='after')
    def validate_linked_folder(self) -> 'KnowledgeBaseFolderBase':
        if self.linked_folder_type and self.linked_folder_id is None:
            raise ValueError("linked_folder_type 存在时，linked_folder_id 不能为空。")
        if self.linked_folder_id is not None and not self.linked_folder_type:
            raise ValueError("linked_folder_id 存在时，linked_folder_type 不能为空，且必须为 'note_folder' 或 'collected_content_folder'。")
        if self.linked_folder_type and self.linked_folder_id is not None:
            if self.parent_id is not None:
                raise ValueError("软链接文件夹只能是顶级文件夹，不能指定父文件夹。")
        if not self.linked_folder_type and not self.name: # A regular folder (not a linked folder) must have a name
            raise ValueError("非软链接文件夹必须设置名称。")
        return self


class KnowledgeBaseFolderCreate(KnowledgeBaseFolderBase):
    pass


class KnowledgeBaseFolderResponse(KnowledgeBaseFolderBase):
    id: int
    kb_id: int
    owner_id: int
    item_count: Optional[int] = Field(None, description="文件夹下直属文章和文档的数量")

    @property # Pydantic v2 @property 支持，这里将其暴露为不带下划线的公共属性
    def parent_folder_name(self) -> Optional[str]:
        return getattr(self, '_parent_folder_name_for_response', None)

    @property
    def knowledge_base_name(self) -> Optional[str]:
        return getattr(self, '_kb_name_for_response', None)

    @property
    def linked_object_names(self) -> Optional[List[str]]:
        return getattr(self, '_linked_object_names_for_response', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


# --- KnowledgeBaseFolderContentResponse (用于软链接文件夹内容) ---
class KnowledgeBaseFolderContentResponse(BaseModel): # 注意这里是 BaseModel，因为它不完全继承 KnowledgeBaseFolderBase 的所有字段，而是包含其所需字段并添加新的
    # 显式声明所有字段，并确保其 @property 的正确性
    id: int
    kb_id: int
    owner_id: int
    name: str # 文件夹名称是必填的

    # 以下是可选字段，它们可能存在于数据库中
    description: Optional[str] = None
    parent_id: Optional[int] = None
    order: Optional[int] = None
    linked_folder_type: Optional[Literal["note_folder", "collected_content_folder"]] = None
    linked_folder_id: Optional[int] = None

    # 动态填充的字段 (通过 ORM 对象的私有属性设置，通过 @property 暴露)
    item_count: Optional[int] = Field(None, description="文件夹下直属文章和文档的数量")

    # 注意：这些 @property 定义要与 main.py 中 ORM 对象赋值的属性名保持一致 (带下划线)
    @property
    def parent_folder_name(self) -> Optional[str]:
        return getattr(self, '_parent_folder_name_for_response', None)

    @property
    def knowledge_base_name(self) -> Optional[str]:
        return getattr(self, '_kb_name_for_response', None)

    @property
    def linked_object_names(self) -> Optional[List[str]]:
        return getattr(self, '_linked_object_names_for_response', None)

    contents: Optional[List[Any]] = Field(None, description="软链接文件夹内实际包含的内容列表（例如笔记或收藏）")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


# --- KnowledgeArticle Schemas (重新添加) ---
class KnowledgeArticleBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    version: Optional[str] = "1.0"
    tags: Optional[str] = None
    kb_folder_id: Optional[int] = Field(None, description="所属知识库文件夹ID。传入0表示顶级文件夹（即folder_id为NULL）")

    @model_validator(mode='after')
    def convert_zero_to_none(self) -> 'KnowledgeArticleBase':
        if self.kb_folder_id == 0:
            self.kb_folder_id = None
        return self

class KnowledgeArticleCreate(KnowledgeArticleBase):
    kb_id: int # KB ID is essential for creation context

class KnowledgeArticleResponse(KnowledgeArticleBase):
    id: int
    kb_id: int
    author_id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @property # Pydantic v2 @property 支持，这里将其暴露为不带下划线的公共属性
    def kb_folder_name(self) -> Optional[str]:
        return getattr(self, '_kb_folder_name_for_response', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


# --- KnowledgeDocument (for uploaded files) Schemas (保留包含 kb_folder_id 的版本) ---
class KnowledgeDocumentBase(BaseModel):
    file_name: str
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    status: Optional[str] = "processing"
    processing_message: Optional[str] = None
    total_chunks: Optional[int] = 0
    kb_folder_id: Optional[int] = Field(None, description="所属知识库文件夹ID。传入0表示顶级文件夹（即folder_id为NULL）")

    @model_validator(mode='after')
    def convert_zero_to_none_kb_doc(self) -> 'KnowledgeDocumentBase':
        if self.kb_folder_id == 0:
            self.kb_folder_id = None
        return self


class KnowledgeDocumentCreate(BaseModel):
    kb_id: int
    file_name: str
    kb_folder_id: Optional[int] = Field(None, description="所属知识库文件夹ID。传入0表示顶级文件夹（即folder_id为NULL）")

    @model_validator(mode='after')
    def convert_zero_to_none_kb_doc_create(self) -> 'KnowledgeDocumentCreate':
        if self.kb_folder_id == 0:
            self.kb_folder_id = None
        return self


class KnowledgeDocumentResponse(KnowledgeDocumentBase):
    id: int
    kb_id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @property # Pydantic v2 @property 支持，这里将其暴露为不带下划线的公共属性
    def kb_folder_name(self) -> Optional[str]:
        return getattr(self, '_kb_folder_name_for_response', None)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}
        populate_by_name = True


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

class CourseResponse(CourseBase):
    id: int
    combined_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    likes_count: Optional[int] = Field(None, description="点赞数量")
    is_liked_by_current_user: Optional[bool] = Field(False, description="当前用户是否已点赞")

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


class CourseMaterialBase(BaseModel):
    title: str = Field(..., description="课程材料标题")
    type: Literal["file", "link", "text", "video", "image"] = Field(..., description="材料类型：'file', 'link', 'text', 'video', 'image'")

    url: Optional[str] = Field(None, description="当类型为'link'或媒体文件时，提供外部链接URL或OSS URL")
    content: Optional[str] = Field(None, description="当类型为'text'时，提供少量文本内容，或作为文件/链接/媒体的补充描述")

    original_filename: Optional[str] = Field(None, description="原始上传文件名")
    file_type: Optional[str] = Field(None, description="文件MIME类型")
    size_bytes: Optional[int] = Field(None, description="文件大小（字节）")

    @field_validator('url', 'content', 'original_filename', 'file_type', 'size_bytes', mode='before')
    def validate_material_fields(cls, v, info):
        if not info.data.get('type'):
            return v
        material_type = info.data['type']
        field_name = info.field_name
        if material_type == "link":
            if field_name == "url" and not v:
                raise ValueError("类型为 'link' 时，'url' 字段为必填。")
            if field_name in ['original_filename', 'file_type', 'size_bytes'] and v is not None:
                raise ValueError(f"类型为 'link' 时，'{field_name}' 字段不应提供。")
            if field_name == "content" and v is not None:  # Content for links is optional
                return v
        elif material_type == "text":
            if field_name == "content" and not v:
                raise ValueError("类型为 'text' 时，'content' 字段为必填。")
            if field_name in ['url', 'original_filename', 'file_type', 'size_bytes'] and v is not None:
                raise ValueError(f"类型为 'text' 时，'{field_name}' 字段不应提供。")
        elif material_type in ["file", "image", "video"]:
            if field_name == "url" and not v:
                raise ValueError(f"类型为 '{material_type}' 时，'url' 字段为必填。")
            # For file/image/video, content is optional supplemental description
            if field_name == "content" and v is not None:
                return v
        return v


class CourseMaterialCreate(CourseMaterialBase):
    title: str
    type: Literal["file", "link", "text", "video", "image"]


class CourseMaterialUpdate(CourseMaterialBase):
    title: Optional[str] = None
    type: Optional[Literal["file", "link", "text", "video", "image"]] = None


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
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")


class MatchedCourse(BaseModel):
    course_id: int
    title: str
    description: str
    instructor: Optional[str] = None
    category: Optional[str] = None
    cover_image_url: Optional[str] = None
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与课程匹配理由及建议")


class CountResponse(BaseModel):
    count: int = Field(..., description="统计数量")
    description: Optional[str] = Field(None, description="统计的描述信息")


class MatchedStudent(BaseModel):
    student_id: int
    name: str
    major: str
    skills: Optional[List[SkillWithProficiency]] = Field(None, description="学生的技能列表及熟练度详情")
    similarity_stage1: float
    relevance_score: float
    match_rationale: Optional[str] = Field(None, description="AI生成的用户与项目匹配理由及建议")


# --- User Login Model ---
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# --- JWT Token Response Model ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int = 0


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
    llm_model_id: Optional[str] = None  # 保留原字段以兼容性
    llm_model_ids: Optional[Dict[str, List[str]]] = None  # 新字段：为每个服务商配置的模型ID列表


# --- AI Conversation Message Schemas ---
class AIConversationMessageBase(BaseModel):
    role: Literal["user", "assistant", "tool_call", "tool_output"] = Field(..., description="消息角色: user, assistant, tool_call, tool_output")
    content: str = Field(..., description="消息内容（文本）")
    tool_calls_json: Optional[List[Dict[str, Any]]] = Field(None, description="如果角色是'tool_call'，存储原始工具调用的JSON数据")
    tool_output_json: Optional[Dict[str, Any]] = Field(None, description="如果角色是'tool_output'，存储原始工具输出的JSON数据")
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


# --- AI Q&A Schemas ---
class AIQARequest(BaseModel):
    query: str
    kb_ids: Optional[List[int]] = None
    note_ids: Optional[List[int]] = None
    use_tools: Optional[bool] = False
    preferred_tools: Optional[List[Literal["rag", "web_search", "mcp_tool"]]] = None
    llm_model_id: Optional[str] = None
    conversation_id: Optional[int] = Field(None, description="要继续的对话Session ID。如果为空，则开始新的对话。")


class AIQAResponse(BaseModel):
    answer: str
    answer_mode: str
    llm_type_used: Optional[str] = None
    llm_model_used: Optional[str] = None
    conversation_id: int = Field(..., description="当前问答所关联的对话Session ID。")
    turn_messages: List["AIConversationMessageResponse"] = Field(..., description="当前轮次（包括用户问题和AI回复）产生的完整消息序列。")
    source_articles: Optional[List[Dict[str, Any]]] = None
    search_results: Optional[List[Dict[str, Any]]] = None

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
    total_messages_count: Optional[int] = Field(None, description="对话中的总消息数量")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- 用于触发AI对话标题重新生成的请求体 ---
class AIConversationRegenerateTitleRequest(BaseModel):
    """
    用于触发AI对话标题（重新）生成的请求体。
    此请求体不包含任何标题字段，明确告知客户端不能手动提交标题。
    任何对此PUT接口的调用都被视为要AI自动生成或重生成标题。
    """
    pass # 留空表示请求体可以是空的 {}

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
    criteria_type: Literal[
        "PROJECT_COMPLETED_COUNT", "COURSE_COMPLETED_COUNT", "FORUM_LIKES_RECEIVED",
        "DAILY_LOGIN_STREAK", "FORUM_POSTS_COUNT", "CHAT_MESSAGES_SENT_COUNT",
        "LOGIN_COUNT"
    ] = Field(..., description="达成成就的条件类型")
    criteria_value: float = Field(..., description="达成成就所需的数值门槛")
    badge_url: Optional[str] = Field(None, description="勋章图片或图标URL")
    reward_points: int = Field(0, description="达成此成就额外奖励的积分")
    is_active: bool = Field(True, description="该成是否启用")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


class AchievementCreate(AchievementBase):
    pass


class AchievementUpdate(AchievementBase):
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
    achievement_name: Optional[str] = Field(None, description="成就名称")
    achievement_description: Optional[str] = Field(None, description="成就描述")
    badge_url: Optional[str] = Field(None, description="勋章图片URL")
    reward_points: Optional[int] = Field(None, description="获得此成就奖励的积分")

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- PointsRewardRequest Schema ---
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
