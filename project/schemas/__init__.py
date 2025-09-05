# project/schemas/__init__.py
"""
模式包：按照routers结构组织的模块化 Pydantic 模型定义
"""

# ===== 导入所有模块 =====

# ===== 公共模块导入 =====
from .common import (
    SkillWithProficiency, TimestampMixin, MediaMixin, UserOwnerMixin, LikeableMixin,
    Response, PaginatedResponse, CountResponse, MessageResponse, validate_media_fields
)

# ===== 知识库模块导入 =====
from .knowledge import (
    KnowledgeBaseSimpleBase, KnowledgeBaseSimpleCreate, KnowledgeBaseSimpleResponse,
    KnowledgeBaseFolderSimpleBase, KnowledgeBaseFolderSimpleCreate, KnowledgeBaseFolderSimpleResponse,
    KnowledgeBaseVisibilityUpdate, KnowledgeBaseFolderVisibilityUpdate,
    KnowledgeDocumentSimpleBase, KnowledgeDocumentSimpleCreate, KnowledgeDocumentUrlCreate,
    KnowledgeSearchResult, KnowledgeSearchResponse, KnowledgeBaseStats
)

# ===== 认证模块导入 =====
from .auth import (
    StudentBase, StudentCreate, StudentResponse, StudentUpdate,
    UserLogin, Token, UserAdminStatusUpdate, UserFollowResponse
)

# ===== 项目模块导入 =====
from .projects import (
    ProjectBase, ProjectCreate, ProjectResponse, ProjectUpdate,
    ProjectFileUpdateData, ProjectFileDeletionRequest, ProjectUpdateWithFiles,
    ProjectApplicationBase, ProjectApplicationCreate, ProjectApplicationResponse, ProjectApplicationProcess,
    ProjectMemberBase, ProjectMemberResponse,
    ProjectFileBase, ProjectFileCreate, ProjectFileResponse,
    ProjectLikeResponse, MatchedProject, MatchedStudent, ProjectStatsResponse
)

# ===== 论坛模块导入 =====
from .forum import (
    ForumTopicBase, ForumTopicCreate, ForumTopicResponse,
    ForumCommentBase, ForumCommentCreate, ForumCommentResponse,
    ForumLikeResponse, EmojiBase, EmojiResponse, MentionedUserInfo, AttachmentInfo,
    ForumMentionResponse, TrendingTopicResponse, UserSearchResult,
    ForumTopicCollectionRequest, ForumCommentCollectionRequest, CollectibleTopicResponse
)

# ===== 聊天室模块导入 =====
from .chatrooms import (
    ChatRoomBase, ChatRoomCreate, ChatRoomUpdate, ChatRoomResponse,
    ChatRoomMemberBase, ChatRoomMemberCreate, ChatRoomMemberResponse, ChatRoomMemberRoleUpdate,
    ChatRoomJoinRequestCreate, ChatRoomJoinRequestProcess, ChatRoomJoinRequestResponse,
    ChatMessageBase, ChatMessageCreate, ChatMessageResponse,
    ChatRoomSettingsUpdate, BatchCleanupOptions, ProcessJoinRequestAction, ForwardMessageRequest,
    ChatMessageCollectionRequest, CollectibleMessageResponse
)

# ===== 课程模块导入 =====
from .courses import (
    CourseBase, CourseCreate, CourseResponse, CourseUpdate,
    UserCourseBase, UserCourseCreate, UserCourseResponse,
    CourseMaterialBase, CourseMaterialCreate, CourseMaterialUpdate, CourseMaterialResponse,
    CourseLikeResponse, MatchedCourse
)

# ===== 课程笔记模块导入 =====
from .course_notes import (
    NoteBase, NoteCreate, NoteUpdate, NoteResponse
)

# ===== 随手记录模块导入 =====
from .quick_notes import (
    DailyRecordBase, DailyRecordCreate, DailyRecordResponse
)

# ===== 收藏系统模块导入 =====
from .collections import (
    FolderBase, FolderCreate, FolderResponse, FolderUpdate, FolderVisibilityUpdate, FolderStatsResponse,
    CollectedContentBase, CollectedContentCreate, CollectedContentResponse, CollectedContentUpdate,
    QuickCollectRequest, SearchRequest, SearchResponse,
    BatchOperationRequest, BatchOperationResponse,
    CollectionStatsRequest, CollectionStatsResponse,
    ImportRequest, ExportRequest, ShareRequest, ShareResponse,
    CollectionSummaryResponse
)

# ===== AI模块导入 =====
from .ai import (
    SemanticSearchRequest, SemanticSearchResult
)

# ===== LLM模块导入 =====
from .llm import (
    UserLLMConfigUpdate, LLMModelConfigBase,
    AIConversationMessageBase, AIConversationMessageCreate, AIConversationMessageResponse,
    AIConversationBase, AIConversationCreate, AIConversationResponse,
    AIConversationRegenerateTitleRequest,
    AIQARequest, AIQAResponse,
    LLMUsageStatsBase, LLMUsageStatsResponse
)

# ===== 成就积分模块导入 =====
from .achievement_points import (
    AchievementBase, AchievementCreate, AchievementUpdate, AchievementResponse,
    UserAchievementResponse, PointsRewardRequest, PointTransactionResponse
)

# ===== 仪表板模块导入 =====
from .dashboard import (
    DashboardSummaryResponse, DashboardProjectCard, DashboardCourseCard
)

# ===== MCP模块导入 =====
from .mcp import (
    UserMcpConfigBase, UserMcpConfigCreate, UserMcpConfigResponse,
    McpStatusResponse, McpToolDefinition
)

# ===== 搜索引擎模块导入 =====
from .search_engine import (
    UserSearchEngineConfigBase, UserSearchEngineConfigCreate, UserSearchEngineConfigResponse,
    SearchEngineStatusResponse, WebSearchResult, WebSearchResponse, WebSearchRequest
)

# ===== TTS模块导入 =====
from .tts import (
    UserTTSConfigBase, UserTTSConfigCreate, UserTTSConfigUpdate, UserTTSConfigResponse,
    TTSTextRequest
)

# ===== 推荐系统模块导入 =====
from .recommend import (
    MatchedProject as RecommendMatchedProject,
    MatchedCourse as RecommendMatchedCourse,
    MatchedStudent as RecommendMatchedStudent
)

# ===== 管理员模块导入 =====
from .admin import (
    AdminOperationRequest, AdminOperationResponse
)

# ===== 知识库模块导入 =====
from .knowledge import (
    KnowledgeBaseSimpleBase, KnowledgeBaseSimpleCreate, KnowledgeBaseSimpleResponse,
    KnowledgeBaseFolderSimpleBase, KnowledgeBaseFolderSimpleCreate, KnowledgeBaseFolderSimpleResponse,
    KnowledgeDocumentSimpleBase, KnowledgeDocumentSimpleCreate, KnowledgeDocumentUrlCreate, KnowledgeDocumentSimpleResponse,
    KnowledgeSearchResult, KnowledgeSearchResponse, KnowledgeBaseStats
)

# ===== 明确指定可导出的模式类 =====
__all__ = [
    # 公共模块
    "SkillWithProficiency", "TimestampMixin", "MediaMixin", "UserOwnerMixin", "LikeableMixin",
    "CountResponse", "MessageResponse", "validate_media_fields",
    
    # 认证模块
    "StudentBase", "StudentCreate", "StudentResponse", "StudentUpdate",
    "UserLogin", "Token", "UserAdminStatusUpdate", "UserFollowResponse",
    
    # 项目模块
    "ProjectBase", "ProjectCreate", "ProjectResponse", "ProjectUpdate",
    "ProjectFileUpdateData", "ProjectFileDeletionRequest", "ProjectUpdateWithFiles",
    "ProjectApplicationBase", "ProjectApplicationCreate", "ProjectApplicationResponse", "ProjectApplicationProcess",
    "ProjectMemberBase", "ProjectMemberResponse",
    "ProjectFileBase", "ProjectFileCreate", "ProjectFileResponse",
    "ProjectLikeResponse", "MatchedProject", "MatchedStudent",
    
    # 论坛模块
    "ForumTopicBase", "ForumTopicCreate", "ForumTopicResponse",
    "ForumCommentBase", "ForumCommentCreate", "ForumCommentResponse",
    "ForumLikeResponse", "EmojiBase", "EmojiResponse", "MentionedUserInfo", "AttachmentInfo",
    "ForumMentionResponse", "TrendingTopicResponse", "UserSearchResult",
    "ForumTopicCollectionRequest", "ForumCommentCollectionRequest", "CollectibleTopicResponse",
    
    # 聊天室模块
    "ChatRoomBase", "ChatRoomCreate", "ChatRoomUpdate", "ChatRoomResponse",
    "ChatRoomMemberBase", "ChatRoomMemberCreate", "ChatRoomMemberResponse", "ChatRoomMemberRoleUpdate",
    "ChatRoomJoinRequestCreate", "ChatRoomJoinRequestProcess", "ChatRoomJoinRequestResponse",
    "ChatMessageBase", "ChatMessageCreate", "ChatMessageResponse",
    "ChatRoomSettingsUpdate", "BatchCleanupOptions", "ProcessJoinRequestAction", "ForwardMessageRequest",
    "ChatMessageCollectionRequest", "CollectibleMessageResponse",
    
    # 课程模块
    "CourseBase", "CourseCreate", "CourseResponse", "CourseUpdate",
    "UserCourseBase", "UserCourseCreate", "UserCourseResponse",
    "CourseMaterialBase", "CourseMaterialCreate", "CourseMaterialUpdate", "CourseMaterialResponse",
    "CourseLikeResponse", "MatchedCourse",
    
    # 课程笔记模块
    "NoteBase", "NoteCreate", "NoteResponse",
    
    # 随手记录模块
    "DailyRecordBase", "DailyRecordCreate", "DailyRecordResponse",
    
    # 收藏系统模块
    "FolderBase", "FolderCreate", "FolderResponse", "FolderUpdate", "FolderVisibilityUpdate", "FolderStatsResponse",
    "CollectedContentBase", "CollectedContentCreate", "CollectedContentResponse", "CollectedContentUpdate",
    "QuickCollectRequest", "SearchRequest", "SearchResponse",
    "BatchOperationRequest", "BatchOperationResponse",
    "CollectionStatsRequest", "CollectionStatsResponse",
    "ImportRequest", "ExportRequest", "ShareRequest", "ShareResponse",
    "CollectionSummaryResponse",
    
    # AI模块
    "SemanticSearchRequest", "SemanticSearchResult",
    
    # LLM模块
    "UserLLMConfigUpdate", "LLMModelConfigBase",
    "AIConversationMessageBase", "AIConversationMessageCreate", "AIConversationMessageResponse",
    "AIConversationBase", "AIConversationCreate", "AIConversationResponse",
    "AIConversationRegenerateTitleRequest",
    "AIQARequest", "AIQAResponse",
    "LLMUsageStatsBase", "LLMUsageStatsResponse",
    
    # 成就积分模块
    "AchievementBase", "AchievementCreate", "AchievementUpdate", "AchievementResponse",
    "UserAchievementResponse", "PointsRewardRequest", "PointTransactionResponse",
    
    # 仪表板模块
    "DashboardSummaryResponse", "DashboardProjectCard", "DashboardCourseCard",
    
    # MCP模块
    "UserMcpConfigBase", "UserMcpConfigCreate", "UserMcpConfigResponse",
    "McpStatusResponse", "McpToolDefinition",
    
    # 搜索引擎模块
    "UserSearchEngineConfigBase", "UserSearchEngineConfigCreate", "UserSearchEngineConfigResponse",
    "SearchEngineStatusResponse", "WebSearchResult", "WebSearchResponse", "WebSearchRequest",
    
    # TTS模块
    "UserTTSConfigBase", "UserTTSConfigCreate", "UserTTSConfigUpdate", "UserTTSConfigResponse",
    "TTSTextRequest",
    
    # 推荐系统模块
    "RecommendMatchedProject", "RecommendMatchedCourse", "RecommendMatchedStudent",
    
    # 管理员模块
    "AdminOperationRequest", "AdminOperationResponse",
    
    # 知识库模块
    "KnowledgeBaseSimpleBase", "KnowledgeBaseSimpleCreate", "KnowledgeBaseSimpleResponse",
    "KnowledgeBaseFolderSimpleBase", "KnowledgeBaseFolderSimpleCreate", "KnowledgeBaseFolderSimpleResponse",
    "KnowledgeBaseVisibilityUpdate", "KnowledgeBaseFolderVisibilityUpdate",
    "KnowledgeDocumentSimpleBase", "KnowledgeDocumentSimpleCreate", "KnowledgeDocumentUrlCreate", "KnowledgeDocumentSimpleResponse",
    "KnowledgeSearchResult", "KnowledgeSearchResponse", "KnowledgeBaseStats",
]

# ===== 向后兼容性别名 =====
# 为了避免破坏现有代码，提供一些别名
FolderBaseNew = FolderBase
FolderCreateNew = FolderCreate
FolderResponseNew = FolderResponse
FolderUpdateNew = FolderUpdate

CollectedContentBaseNew = CollectedContentBase
CollectedContentCreateNew = CollectedContentCreate
CollectedContentResponseNew = CollectedContentResponse
CollectedContentUpdateNew = CollectedContentUpdate
