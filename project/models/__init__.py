# project/models/__init__.py
"""
模型包：包含所有数据库模型定义
"""

from .models import (
    # 项目相关模型
    ProjectApplication,
    ProjectMember,
    Project,
    ProjectFile,
    ProjectLike,
    
    # 用户相关模型
    Student,
    UserFollow,
    UserMcpConfig,
    UserSearchEngineConfig,
    UserTTSConfig,
    
    # 笔记相关模型
    Note,
    DailyRecord,
    Folder,
    CollectedContent,
    CollectionItem,
    
    # 聊天相关模型
    ChatRoom,
    ChatMessage,
    ChatRoomMember,
    ChatRoomJoinRequest,
    
    # 论坛相关模型
    ForumTopic,
    ForumComment,
    ForumLike,
    
    # 课程相关模型
    Course,
    UserCourse,
    CourseMaterial,
    CourseLike,
    
    # 知识库相关模型
    KnowledgeBase,
    KnowledgeBaseFolder,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    
    # AI 对话相关模型
    AIConversationMessage,
    AIConversationTemporaryFile,
    AIConversation,
    
    # 积分和成就相关模型
    PointTransaction,
    Achievement,
    UserAchievement,
)

__all__ = [
    # 项目相关
    "ProjectApplication",
    "ProjectMember", 
    "Project",
    "ProjectFile",
    "ProjectLike",
    
    # 用户相关
    "Student",
    "UserFollow",
    "UserMcpConfig",
    "UserSearchEngineConfig", 
    "UserTTSConfig",
    
    # 笔记相关
    "Note",
    "DailyRecord", 
    "Folder",
    "CollectedContent",
    "CollectionItem",
    
    # 聊天相关
    "ChatRoom",
    "ChatMessage",
    "ChatRoomMember",
    "ChatRoomJoinRequest",
    
    # 论坛相关
    "ForumTopic",
    "ForumComment",
    "ForumLike",
    
    # 课程相关
    "Course",
    "UserCourse",
    "CourseMaterial",
    "CourseLike",
    
    # 知识库相关
    "KnowledgeBase",
    "KnowledgeBaseFolder",
    "KnowledgeDocument",
    "KnowledgeDocumentChunk",
    
    # AI 对话相关
    "AIConversationMessage",
    "AIConversationTemporaryFile",
    "AIConversation",
    
    # 积分和成就
    "PointTransaction",
    "Achievement", 
    "UserAchievement",
]
