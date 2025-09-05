# project/models/__init__.py
"""
模型包：按照功能模块组织的 SQLAlchemy 模型定义
"""

# ===== 导入所有模块 =====

# ===== 用户认证相关模型 =====
from .auth import User, UserProfile, UserSettings

# ===== 项目相关模型 =====
from .projects import (
    Project, ProjectApplication, ProjectMember, 
    ProjectFile, ProjectLike
)

# ===== 论坛相关模型 =====
from .forum import (
    ForumTopic, ForumComment, ForumLike, UserFollow
)

# ===== 聊天室相关模型 =====
from .chatrooms import (
    ChatRoom, ChatMessage, ChatRoomMember, 
    ChatRoomJoinRequest
)

# ===== 课程相关模型 =====
from .courses import (
    Course, UserCourse, CourseMaterial, CourseLike
)

# ===== 笔记和日记相关模型 =====
from .course_notes import (
    Note, Folder
)

# ===== 快速笔记相关模型 =====
from .quick_notes import (
    DailyRecord
)

# ===== 收藏相关模型 =====
from .collections import CollectedContent

# ===== LLM和AI对话相关模型 =====
from .llm import (
    LLMProvider, UserLLMConfig, LLMConversation, LLMMessage,
    AIConversation, AIConversationMessage, 
    AIConversationTemporaryFile
)

# ===== 成就和积分相关模型 =====
from .achievement_points import (
    Achievement, UserAchievement, PointTransaction
)

# ===== MCP配置相关模型 =====
from .mcp import UserMcpConfig

# ===== 搜索引擎配置相关模型 =====
from .search_engine import UserSearchEngineConfig

# ===== TTS配置相关模型 =====
from .tts import UserTTSConfig

# ===== 知识库相关模型 =====
from .knowledge import (
    KnowledgeBase, KnowledgeBaseFolder, 
    KnowledgeDocument, KnowledgeDocumentChunk
)

# ===== 推荐系统相关模型 =====
from .recommendation import (
    UserBehavior, RecommendationLog, KnowledgeItem, ForumPost
)

# ===== 导出所有模型 =====
__all__ = [
    # 用户认证
    'User', 'UserProfile', 'UserSettings',
    
    # 项目
    'Project', 'ProjectApplication', 'ProjectMember', 
    'ProjectFile', 'ProjectLike',
    
    # 论坛
    'ForumTopic', 'ForumComment', 'ForumLike', 'UserFollow',
    
    # 聊天室
    'ChatRoom', 'ChatMessage', 'ChatRoomMember', 
    'ChatRoomJoinRequest',
    
    # 课程
    'Course', 'UserCourse', 'CourseMaterial', 'CourseLike',
    
    # 笔记和日记
    'Note', 'DailyRecord', 'Folder',
    
    # 收藏
    'CollectedContent',
    
    # LLM和AI对话
    'LLMProvider', 'UserLLMConfig', 'LLMConversation', 'LLMMessage',
    'AIConversation', 'AIConversationMessage', 
    'AIConversationTemporaryFile',
    
    # 成就和积分
    'Achievement', 'UserAchievement', 'PointTransaction',
    
    # 配置
    'UserMcpConfig', 'UserSearchEngineConfig', 'UserTTSConfig',
    
    # 知识库
    'KnowledgeBase', 'KnowledgeBaseFolder', 
    'KnowledgeDocument', 'KnowledgeDocumentChunk',
    
    # 推荐系统
    'UserBehavior', 'RecommendationLog', 'KnowledgeItem', 'ForumPost',
]
