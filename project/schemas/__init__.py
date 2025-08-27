# project/schemas/__init__.py
"""
模式包：包含所有 Pydantic 模型定义（请求和响应模式）
"""

# 导入所有模式类
from .schemas import *

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
    
    # 知识库相关
    "KnowledgeBaseBase",
    "KnowledgeBaseCreate",
    "KnowledgeBaseResponse",
    
    # 知识库文件夹相关
    "KnowledgeBaseFolderBase",
    "KnowledgeBaseFolderCreate",
    "KnowledgeBaseFolderResponse",
    "KnowledgeBaseFolderContentResponse",
    
    # 知识库文章相关
    "KnowledgeArticleBase",
    "KnowledgeArticleCreate",
    "KnowledgeArticleResponse",
    
    # 知识库文档相关
    "KnowledgeDocumentBase",
    "KnowledgeDocumentCreate",
    "KnowledgeDocumentResponse",
    "KnowledgeDocumentChunkResponse",
    
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
]
