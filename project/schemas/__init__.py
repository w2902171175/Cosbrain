# project/schemas/__init__.py
"""
模式包：包含所有 Pydantic 模型定义（请求和响应模式）
"""

# 导入所有模式类 - 明确列出以避免通配符导入
from .schemas import (
    # 公共模式
    SkillWithProficiency,
    
    # 学生相关
    StudentBase, StudentCreate, StudentResponse, StudentUpdate,
    
    # 项目相关
    ProjectBase, ProjectCreate, ProjectResponse, ProjectUpdate,
    ProjectFileUpdateData, ProjectFileDeletionRequest, ProjectUpdateWithFiles,
    
    # 项目申请相关
    ProjectApplicationBase, ProjectApplicationCreate, ProjectApplicationResponse,
    ProjectApplicationProcess,
    
    # 项目成员相关
    ProjectMemberBase, ProjectMemberResponse,
    
    # 项目文件相关
    ProjectFileBase, ProjectFileCreate, ProjectFileResponse,
    
    # 笔记相关
    NoteBase, NoteCreate, NoteResponse,
    
    # 日记相关
    DailyRecordBase, DailyRecordCreate, DailyRecordResponse,
    
    # 聊天室相关
    ChatRoomBase, ChatRoomCreate, ChatRoomUpdate, ChatRoomResponse,
    
    # 聊天室成员相关
    ChatRoomMemberBase, ChatRoomMemberCreate, ChatRoomMemberResponse,
    ChatRoomMemberRoleUpdate,
    
    # 聊天室加入请求相关
    ChatRoomJoinRequestCreate, ChatRoomJoinRequestProcess, ChatRoomJoinRequestResponse,
    
    # 用户管理员状态更新
    UserAdminStatusUpdate,
    
    # 聊天消息相关
    ChatMessageBase, ChatMessageCreate, ChatMessageResponse,
    
    # 论坛话题相关
    ForumTopicBase, ForumTopicCreate, ForumTopicResponse,
    
    # 论坛评论相关
    ForumCommentBase, ForumCommentCreate, ForumCommentResponse,
    
    # 点赞相关
    ForumLikeResponse, ProjectLikeResponse, CourseLikeResponse,
    
    # 用户关注相关
    UserFollowResponse,
    
    # MCP 配置相关
    UserMcpConfigBase, UserMcpConfigCreate, UserMcpConfigResponse,
    McpStatusResponse, McpToolDefinition,
    
    # 搜索引擎配置相关
    UserSearchEngineConfigBase, UserSearchEngineConfigCreate,
    UserSearchEngineConfigResponse, SearchEngineStatusResponse,
    
    # TTS 配置相关
    UserTTSConfigBase, UserTTSConfigCreate, UserTTSConfigUpdate,
    UserTTSConfigResponse, TTSTextRequest,
    
    # 搜索相关
    WebSearchResult, WebSearchResponse, WebSearchRequest,
    
    # 课程相关
    CourseBase, CourseCreate, CourseResponse, CourseUpdate,
    
    # 用户课程关系相关
    UserCourseBase, UserCourseCreate, UserCourseResponse,
    
    # 课程材料相关
    CourseMaterialBase, CourseMaterialCreate, CourseMaterialUpdate,
    CourseMaterialResponse,
    
    # 收藏项目相关 (Legacy - 已标记为废弃)
    CollectionItemBase, CollectionItemCreate, CollectionItemResponse,
    
    # 推荐匹配相关
    MatchedProject, MatchedCourse, MatchedStudent, CountResponse,
    
    # 文件夹相关（新版本）
    FolderBaseNew, FolderCreateNew, FolderResponseNew, FolderUpdateNew,
    
    # 收藏内容相关（新版本）
    CollectedContentBaseNew, CollectedContentCreateNew,
    CollectedContentResponseNew, CollectedContentUpdateNew,
    
    # AI 相关
    AIConversationMessageBase, AIConversationMessageCreate, AIConversationMessageResponse,
    AIQARequest, AIQAResponse,
    AIConversationBase, AIConversationCreate, AIConversationResponse,
    AIConversationRegenerateTitleRequest,
    
    # 成就积分相关
    AchievementBase, AchievementCreate, AchievementUpdate, AchievementResponse,
    UserAchievementResponse, PointsRewardRequest, PointTransactionResponse,
    
    # 其他缺失的模式类
    EmojiBase, EmojiResponse, MentionedUserInfo, AttachmentInfo,
    ForumMentionResponse, TrendingTopicResponse, UserSearchResult,
    UserLogin, Token, UserLLMConfigUpdate,
    SemanticSearchRequest, SemanticSearchResult,
    DashboardSummaryResponse, DashboardProjectCard, DashboardCourseCard,
    FolderStatsResponse,
    QuickCollectRequest, SearchRequest, SearchResponse,
    BatchOperationRequest, BatchOperationResponse,
    CollectionStatsRequest, CollectionStatsResponse,
    ImportRequest, ExportRequest, ShareRequest, ShareResponse,
    ChatMessageCollectionRequest, ForumTopicCollectionRequest, ForumCommentCollectionRequest,
    CollectibleMessageResponse, CollectibleTopicResponse,
)

# 明确指定可导出的模式类
__all__ = [
    # 公共模式
    "SkillWithProficiency",
    
    # 学生相关
    "StudentBase",
    "StudentCreate",
    "StudentResponse", 
    "StudentUpdate",
    
    # 项目相关
    "ProjectBase",
    "ProjectCreate",
    "ProjectResponse",
    "ProjectUpdate",
    "ProjectFileUpdateData",
    "ProjectFileDeletionRequest",
    "ProjectUpdateWithFiles",
    
    # 项目申请相关
    "ProjectApplicationBase",
    "ProjectApplicationCreate",
    "ProjectApplicationResponse",
    "ProjectApplicationProcess",
    
    # 项目成员相关
    "ProjectMemberBase",
    "ProjectMemberResponse",
    
    # 项目文件相关
    "ProjectFileBase",
    "ProjectFileCreate",
    "ProjectFileResponse",
    
    # 笔记相关
    "NoteBase",
    "NoteCreate", 
    "NoteResponse",
    
    # 日记相关
    "DailyRecordBase",
    "DailyRecordCreate",
    "DailyRecordResponse",
    
    # 聊天室相关
    "ChatRoomBase",
    "ChatRoomCreate",
    "ChatRoomUpdate",
    "ChatRoomResponse",
    
    # 聊天室成员相关
    "ChatRoomMemberBase",
    "ChatRoomMemberCreate",
    "ChatRoomMemberResponse",
    "ChatRoomMemberRoleUpdate",
    
    # 聊天室加入请求相关
    "ChatRoomJoinRequestCreate",
    "ChatRoomJoinRequestProcess",
    "ChatRoomJoinRequestResponse",
    
    # 用户管理员状态更新
    "UserAdminStatusUpdate",
    
    # 聊天消息相关
    "ChatMessageBase",
    "ChatMessageCreate",
    "ChatMessageResponse",
    
    # 论坛话题相关
    "ForumTopicBase",
    "ForumTopicCreate", 
    "ForumTopicResponse",
    
    # 论坛评论相关
    "ForumCommentBase",
    "ForumCommentCreate",
    "ForumCommentResponse",
    
    # 点赞相关
    "ForumLikeResponse",
    "ProjectLikeResponse",
    "CourseLikeResponse",
    
    # 用户关注相关
    "UserFollowResponse",
    
    # MCP 配置相关
    "UserMcpConfigBase",
    "UserMcpConfigCreate",
    "UserMcpConfigResponse",
    "McpStatusResponse",
    "McpToolDefinition",
    
    # 搜索引擎配置相关
    "UserSearchEngineConfigBase",
    "UserSearchEngineConfigCreate",
    "UserSearchEngineConfigResponse",
    "SearchEngineStatusResponse",
    
    # TTS 配置相关
    "UserTTSConfigBase",
    "UserTTSConfigCreate",
    "UserTTSConfigUpdate",
    "UserTTSConfigResponse",
    "TTSTextRequest",
    
    # 搜索相关
    "WebSearchResult",
    "WebSearchResponse",
    "WebSearchRequest",
    
    # 注意：知识库相关的Schemas已经移动到独立的knowledge_schemas.py文件
    # 如需使用，请直接从 schemas.knowledge_schemas 导入
    # 例如：from schemas.knowledge_schemas import KnowledgeBaseSimpleResponse
    
    # 课程相关
    "CourseBase",
    "CourseCreate",
    "CourseResponse",
    "CourseUpdate",
    
    # 用户课程关系相关
    "UserCourseBase",
    "UserCourseCreate",
    "UserCourseResponse",
    
    # 课程材料相关
    "CourseMaterialBase",
    "CourseMaterialCreate",
    "CourseMaterialUpdate",
    "CourseMaterialResponse",
    
    # 收藏项目相关
    "CollectionItemBase",
    "CollectionItemCreate",
    "CollectionItemResponse",
    
    # 推荐匹配相关
    "MatchedProject",
    "MatchedCourse",
    "MatchedStudent",
    "CountResponse",
    
    # 文件夹相关（新版本）
    "FolderBaseNew",
    "FolderCreateNew",
    "FolderResponseNew",
    "FolderUpdateNew",
    
    # 收藏内容相关（新版本）
    "CollectedContentBaseNew",
    "CollectedContentCreateNew",
    "CollectedContentResponseNew",
    "CollectedContentUpdateNew",
    
    # AI 相关
    "AIConversationMessageBase",
    "AIConversationMessageCreate",
    "AIConversationMessageResponse",
    "AIQARequest",
    "AIQAResponse",
    "AIConversationBase",
    "AIConversationCreate",
    "AIConversationResponse",
    "AIConversationRegenerateTitleRequest",
    
    # 成就积分相关
    "AchievementBase",
    "AchievementCreate",
    "AchievementUpdate",
    "AchievementResponse",
    "UserAchievementResponse",
    "PointsRewardRequest",
    "PointTransactionResponse",
    
    # 其他缺失的模式类
    "EmojiBase",
    "EmojiResponse", 
    "MentionedUserInfo",
    "AttachmentInfo",
    "ForumMentionResponse",
    "TrendingTopicResponse",
    "UserSearchResult",
    "UserLogin",
    "Token",
    "UserLLMConfigUpdate",
    "SemanticSearchRequest",
    "SemanticSearchResult",
    "DashboardSummaryResponse",
    "DashboardProjectCard",
    "DashboardCourseCard",
    "FolderStatsResponse",
    "QuickCollectRequest",
    "SearchRequest",
    "SearchResponse",
    "BatchOperationRequest",
    "BatchOperationResponse",
    "CollectionStatsRequest",
    "CollectionStatsResponse",
    "ImportRequest",
    "ExportRequest",
    "ShareRequest",
    "ShareResponse",
    "ChatMessageCollectionRequest",
    "ForumTopicCollectionRequest",
    "ForumCommentCollectionRequest",
    "CollectibleMessageResponse",
    "CollectibleTopicResponse",
]
