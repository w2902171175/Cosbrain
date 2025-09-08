# project/models/performance_indexes.py
"""
性能优化索引定义
为常用查询模式添加复合索引以提升查询性能

统一管理所有模型的索引，避免重复定义
模型文件中应该移除 __table_args__ 中的索引定义，统一在此处管理
"""

from sqlalchemy import Index
from . import (
    User, UserProfile, UserSettings,
    Project, ForumTopic, ForumComment, ForumLike, 
    CourseLike, ProjectLike, Course, ChatMessage, ChatRoom,
    Note, DailyRecord, UserMcpConfig, UserTTSConfig, UserSearchEngineConfig,
    AIConversation, KnowledgeDocument
)

# 用户相关索引
user_performance_indexes = [
    # 用户登录相关
    Index('idx_user_email_active', User.email, User.is_admin),
    Index('idx_user_login_stats', User.last_login_at, User.login_count),
    
    # 用户档案搜索
    Index('idx_profile_skills_location', UserProfile.location, UserProfile.major),
    Index('idx_profile_embedding_search', UserProfile.embedding),
    
    # 用户设置查询
    Index('idx_settings_llm_config', UserSettings.llm_api_type, UserSettings.user_id),
]

# 项目相关索引
project_performance_indexes = [
    # 项目搜索和排序
    Index('idx_project_status_created', Project.project_status, Project.created_at),
    Index('idx_project_likes_created', Project.likes_count, Project.created_at),
    Index('idx_project_creator_status', Project.creator_id, Project.project_status),
    Index('idx_project_embedding_search', Project.embedding),
]

# 论坛相关索引 - 统一管理所有论坛索引
forum_performance_indexes = [
    # === ForumTopic 索引 ===
    # 基础查询索引
    Index('idx_forum_topic_created', ForumTopic.created_at),
    Index('idx_forum_topic_owner', ForumTopic.owner_id, ForumTopic.created_at),
    Index('idx_forum_topic_status', ForumTopic.status),
    Index('idx_forum_topic_last_reply', ForumTopic.last_reply_at),
    
    # 热度和排序索引
    Index('idx_forum_topic_popularity', ForumTopic.like_count, ForumTopic.comment_count, ForumTopic.created_at),
    Index('idx_forum_topic_heat_score', ForumTopic.like_count, ForumTopic.view_count, ForumTopic.comment_count),
    Index('idx_forum_topic_heat_ranking', ForumTopic.heat_score, ForumTopic.created_at),
    
    # 复合查询索引
    Index('idx_forum_topic_status_created', ForumTopic.status, ForumTopic.created_at),
    Index('idx_forum_topic_owner_status', ForumTopic.owner_id, ForumTopic.status, ForumTopic.created_at),
    Index('idx_forum_topic_shared', ForumTopic.shared_item_type, ForumTopic.shared_item_id),
    
    # 搜索优化索引
    Index('idx_topic_embedding_search', ForumTopic.embedding),
    
    # === ForumComment 索引 ===
    # 基础查询索引
    Index('idx_forum_comment_topic', ForumComment.topic_id, ForumComment.created_at),
    Index('idx_forum_comment_owner', ForumComment.owner_id, ForumComment.created_at),
    Index('idx_forum_comment_parent', ForumComment.parent_comment_id, ForumComment.created_at),
    
    # 层级结构索引
    Index('idx_forum_comment_tree', ForumComment.topic_id, ForumComment.parent_comment_id, ForumComment.created_at),
    Index('idx_forum_comment_topic_parent', ForumComment.topic_id, ForumComment.parent_comment_id),
    
    # 统计和排序索引
    Index('idx_forum_comment_likes', ForumComment.like_count, ForumComment.created_at),
    Index('idx_forum_comment_reply_count', ForumComment.reply_count, ForumComment.created_at),
    Index('idx_forum_comment_owner_topic', ForumComment.owner_id, ForumComment.topic_id, ForumComment.created_at),
    
    # === ForumLike 索引 ===
    # 点赞统计和查询索引
    Index('idx_forum_like_owner_topic', ForumLike.owner_id, ForumLike.topic_id, unique=True),
    Index('idx_forum_like_topic', ForumLike.topic_id, ForumLike.created_at),
    Index('idx_forum_like_owner_history', ForumLike.owner_id, ForumLike.created_at),
    Index('idx_forum_like_stats', ForumLike.topic_id, ForumLike.created_at),
    
    # 评论点赞索引（新增）
    Index('idx_forum_like_comment', ForumLike.comment_id, ForumLike.created_at),
    Index('idx_forum_like_owner_comment', ForumLike.owner_id, ForumLike.comment_id, unique=True),
    Index('idx_forum_like_global_activity', ForumLike.created_at),
]

# AI对话相关索引
ai_performance_indexes = [
    # AI对话查询优化
    Index('idx_conversation_user_time', AIConversation.user_id, AIConversation.created_at),
    Index('idx_conversation_title_search', AIConversation.title, AIConversation.user_id),
]

# 知识库相关索引
knowledge_performance_indexes = [
    # 知识库文档搜索
    Index('idx_doc_kb_type', KnowledgeDocument.kb_id, KnowledgeDocument.content_type),
    Index('idx_doc_owner_status', KnowledgeDocument.owner_id, KnowledgeDocument.status),
    Index('idx_doc_created_status', KnowledgeDocument.created_at, KnowledgeDocument.status),
]

# 课程相关索引
course_performance_indexes = [
    # 课程搜索和排序
    Index('idx_course_rating_category', Course.avg_rating, Course.category),
    Index('idx_course_likes_created', Course.likes_count, Course.created_at),
    Index('idx_course_embedding_search', Course.embedding),
]

# 点赞系统相关索引
like_performance_indexes = [
    # 课程点赞索引
    Index('idx_course_like_stats', CourseLike.course_id, CourseLike.created_at),
    Index('idx_course_like_owner_course', CourseLike.owner_id, CourseLike.course_id, unique=True),
    
    # 项目点赞索引  
    Index('idx_project_like_stats', ProjectLike.project_id, ProjectLike.created_at),
    Index('idx_project_like_owner_project', ProjectLike.owner_id, ProjectLike.project_id, unique=True),
]

# 聊天相关索引 - 统一管理所有聊天室索引
chat_performance_indexes = [
    # === ChatMessage 索引 ===
    # 基础查询索引
    Index('idx_message_room_time', ChatMessage.room_id, ChatMessage.sent_at),
    Index('idx_message_sender_time', ChatMessage.sender_id, ChatMessage.sent_at),
    Index('idx_message_type_room', ChatMessage.message_type, ChatMessage.room_id),
    Index('idx_message_reply_to', ChatMessage.reply_to_message_id),
    Index('idx_message_room_pinned', ChatMessage.room_id, ChatMessage.is_pinned),
    Index('idx_message_room_status', ChatMessage.room_id, ChatMessage.message_status),
    Index('idx_message_sent_at_desc', ChatMessage.room_id, ChatMessage.sent_at),
    
    # 注意：ChatRoomMember 和 ChatRoomJoinRequest 的索引需要在对应模型中处理
    # 或者在此处添加字符串形式的索引定义
]

# 笔记相关索引
note_performance_indexes = [
    # 笔记搜索优化
    Index('idx_note_owner_created', Note.owner_id, Note.created_at),
    Index('idx_note_course_created', Note.course_id, Note.created_at),
    Index('idx_note_folder_created', Note.folder_id, Note.created_at),
    Index('idx_note_embedding_search', Note.embedding),
    
    # 日记查询优化
    Index('idx_daily_record_owner_created', DailyRecord.owner_id, DailyRecord.created_at),
    Index('idx_daily_record_embedding_search', DailyRecord.embedding),
]

# 配置模型相关索引
config_performance_indexes = [
    # 用户配置查询优化
    Index('idx_mcp_config_owner_active', UserMcpConfig.owner_id, UserMcpConfig.is_active),
    Index('idx_mcp_config_service_priority', UserMcpConfig.service_type, UserMcpConfig.priority),
    Index('idx_mcp_config_health', UserMcpConfig.is_healthy, UserMcpConfig.last_health_check),
    
    Index('idx_tts_config_owner_active', UserTTSConfig.owner_id, UserTTSConfig.is_active),
    Index('idx_tts_config_service_priority', UserTTSConfig.service_type, UserTTSConfig.priority),
    Index('idx_tts_config_health', UserTTSConfig.is_healthy, UserTTSConfig.last_health_check),
    
    Index('idx_search_config_owner_active', UserSearchEngineConfig.owner_id, UserSearchEngineConfig.is_active),
    Index('idx_search_config_service_priority', UserSearchEngineConfig.service_type, UserSearchEngineConfig.priority),
    Index('idx_search_config_health', UserSearchEngineConfig.is_healthy, UserSearchEngineConfig.last_health_check),
]

# 所有性能索引集合
ALL_PERFORMANCE_INDEXES = (
    user_performance_indexes +
    project_performance_indexes +
    forum_performance_indexes +
    like_performance_indexes +  # 新增点赞索引
    ai_performance_indexes +
    knowledge_performance_indexes +
    course_performance_indexes +
    chat_performance_indexes +
    note_performance_indexes +
    config_performance_indexes
)

def create_performance_indexes(engine):
    """
    创建所有性能优化索引
    
    Args:
        engine: SQLAlchemy 引擎实例
    """
    from sqlalchemy import MetaData
    
    metadata = MetaData()
    
    for index in ALL_PERFORMANCE_INDEXES:
        try:
            index.create(engine, checkfirst=True)
            print(f"✅ 创建索引: {index.name}")
        except Exception as e:
            print(f"❌ 创建索引失败 {index.name}: {e}")
    
    print(f"🎉 性能索引创建完成，共处理 {len(ALL_PERFORMANCE_INDEXES)} 个索引")

def analyze_query_performance():
    """
    分析查询性能的建议
    
    Returns:
        dict: 性能优化建议
    """
    return {
        "high_frequency_queries": [
            "用户登录查询 (email + password)",
            "项目列表查询 (status + created_at)",
            "论坛热门话题 (heat_score + created_at)",
            "AI对话历史 (user_id + created_at)",
            "知识库文档搜索 (kb_id + content_type)",
            "配置管理查询 (owner_id + is_active + service_type)"
        ],
        "embedding_queries": [
            "项目相似度搜索 (Project.embedding)",
            "论坛话题搜索 (ForumTopic.embedding)",
            "课程推荐 (Course.embedding)",
            "笔记内容搜索 (Note.embedding)",
            "用户技能匹配 (UserProfile.embedding)"
        ],
        "config_optimization": [
            "配置服务健康检查 (is_healthy + last_health_check)",
            "配置优先级排序 (service_type + priority)",
            "用户激活配置查询 (owner_id + is_active)"
        ],
        "optimization_tips": [
            "对于嵌入向量查询，考虑使用 HNSW 或 IVF 索引",
            "定期运行 ANALYZE 更新表统计信息",
            "监控慢查询日志，识别需要优化的查询",
            "考虑为经常使用的 JSON 字段创建 GIN 索引",
            "配置模型查询频繁，建议设置适当的缓存策略"
        ]
    }
