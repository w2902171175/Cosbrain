# project/routers/collections/collections_config.py
"""
收藏系统配置文件

统一管理收藏系统的配置常量和类型定义
"""

from project.models import (
    Project, Course, ProjectLike, CourseLike,
    KnowledgeBase, Folder  # 修正：知识库本身，而不是文件夹
)

# 收藏类型配置 - 统一管理不同类型的收藏配置
COLLECTION_CONFIGS = {
    "project": {
        "model": Project,
        "like_model": ProjectLike,
        "folder_name": "我的项目收藏",
        "color": "#FF6B6B",
        "icon": "project",
        "like_field": "project_id",
        "display_name": "项目"
    },
    "course": {
        "model": Course,
        "like_model": CourseLike,
        "folder_name": "我的课程收藏",
        "color": "#4ECDC4", 
        "icon": "course",
        "like_field": "course_id",
        "display_name": "课程"
    },
    "knowledge_base": {
        "model": KnowledgeBase,
        "like_model": None,  # 知识库暂时不支持点赞
        "folder_name": "我的知识库收藏",
        "color": "#9B59B6",
        "icon": "book",
        "like_field": None,
        "display_name": "知识库"
    },
    "note_folder": {
        "model": Folder,  # 课程笔记文件夹
        "like_model": None,  # 笔记文件夹暂时不支持点赞
        "folder_name": "我的笔记文件夹收藏",
        "color": "#F39C12",
        "icon": "edit-3",
        "like_field": None,
        "display_name": "笔记文件夹"
    }
}

# 文件夹颜色映射
FOLDER_COLOR_MAPPING = {
    "项目": "#FF6B6B",     # 红色
    "课程": "#4ECDC4",     # 青色
    "学习": "#45B7D1",     # 蓝色
    "工作": "#96CEB4",     # 绿色
    "个人": "#FFEAA7",     # 黄色
    "收藏": "#DDA0DD",     # 紫色
    "重要": "#FF7675",     # 亮红色
    "临时": "#A0A0A0",     # 灰色
    "归档": "#74B9FF",     # 浅蓝色
    "分享": "#00B894",     # 翠绿色
    "图片": "#6C5CE7",     # 紫色
    "视频": "#FD79A8",     # 粉色
    "音频": "#FDCB6E",     # 橙色
    "文档": "#81ECEC",     # 浅青色
    "链接": "#A29BFE",     # 淡紫色
    "聊天": "#00CEC9",     # 青绿色
    "论坛": "#E17055",     # 橙红色
}

# 文件夹图标映射
FOLDER_ICON_MAPPING = {
    "项目": "briefcase",
    "课程": "book-open",
    "学习": "graduation-cap",
    "工作": "briefcase",
    "个人": "user",
    "重要": "star",
    "临时": "clock",
    "归档": "archive",
    "分享": "share-2",
    "图片": "image",
    "视频": "video",
    "音频": "music",
    "文档": "file-text",
    "链接": "link",
    "收藏": "heart",
    "聊天": "message-circle",
    "论坛": "users",
    "文件": "file",
    "语音": "mic",
    "知识库": "book",
}

# 内容类型与文件夹的映射
CONTENT_TYPE_FOLDER_MAPPING = {
    "project": "项目收藏",
    "course": "课程收藏", 
    "forum_topic": "论坛收藏",
    "note": "笔记收藏",
    "chat_message": "聊天收藏",
    "knowledge_base": "知识库收藏",
    "note_folder": "笔记文件夹收藏"
}

# 标签关键词映射
TAG_KEYWORD_MAPPING = {
    "学习": ["学习", "教程", "课程", "教育"],
    "工作": ["工作", "项目", "任务", "业务"],
    "技术": ["技术", "编程", "开发", "代码"],
    "设计": ["设计", "UI", "UX", "界面"],
    "文档": ["文档", "说明", "手册", "指南"]
}

# 文件类型标签映射
FILE_TYPE_TAG_MAPPING = {
    "image": ["图片", "视觉"],
    "video": ["视频", "影像"],
    "audio": ["音频", "声音"],
    "file": ["文件", "资料"],
    "link": ["链接", "网页"],
    "forum_topic": ["论坛", "讨论"],
    "chat_message": ["聊天", "消息"],
    "project": ["项目"],
    "course": ["课程", "学习"],
    "note": ["笔记", "记录"],
    "knowledge_base": ["知识库", "知识"],
    "note_folder": ["笔记文件夹", "文件夹", "笔记"]
}

# 默认配置
DEFAULT_FOLDER_COLOR = "#74B9FF"
DEFAULT_FOLDER_ICON = "folder"
DEFAULT_FOLDER_NAME = "默认收藏"
MAX_AUTO_TAGS = 5
