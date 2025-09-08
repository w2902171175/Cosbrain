# project/models/collections.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, UniqueConstraint, BigInteger, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from project.base import Base


class CollectedContent(Base):
    __tablename__ = "collected_contents"

    # 确保同一用户不能重复收藏同一个共享实体
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "shared_item_type", "shared_item_id",
            name="_owner_shared_item_uc"
        ),
        # 创建索引以提高查询性能 - 对应 SQL 中的 idx_collected_contents_shared_item
        Index("idx_collected_contents_shared_item", "owner_id", "shared_item_type", "shared_item_id"),
        # 创建索引以提高按类型查询的性能 - 对应 SQL 中的 idx_collected_contents_type
        Index("idx_collected_contents_type", "owner_id", "type", "status"),
        # 创建索引以提高按文件夹查询的性能 - 对应 SQL 中的 idx_collected_contents_folder
        Index("idx_collected_contents_folder", "folder_id", "status"),
        # 为 title + owner_id 添加唯一约束，如果要求收藏标题在用户维度唯一
        # UniqueConstraint("owner_id", "title", name="_owner_title_uc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)

    title = Column(String, nullable=False)
    type = Column(String, nullable=False)
    url = Column(String, nullable=True, comment="收藏内容的URL，可以是外部链接或OSS文件URL")
    content = Column(Text, nullable=True)
    tags = Column(String, nullable=True)
    priority = Column(Integer, default=3)
    notes = Column(Text, nullable=True)
    access_count = Column(Integer, default=0, nullable=False, comment="访问（查看）次数")
    is_starred = Column(Boolean, default=False)
    thumbnail = Column(String, nullable=True)
    author = Column(String, nullable=True)
    duration = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True, comment="文件大小（字节，适用于OSS文件）")
    status = Column(String, default="active")
    shared_item_type = Column(String(50), nullable=True,
                              comment="如果收藏平台内部内容，记录其类型（例如project, course, forum_topic, note, daily_record, knowledge_document, chat_message, forum_comment, forum_topic_attachment）")
    shared_item_id = Column(Integer, nullable=True, comment="如果收藏平台内部内容，记录其ID")

    combined_text = Column(Text, nullable=True, comment="用于AI模型嵌入的组合文本")
    embedding = Column(Vector(1024), nullable=True, comment="文本内容的嵌入向量")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("User", back_populates="collected_contents")
    folder = relationship("Folder", back_populates="collected_contents")

    @property
    def is_internal_content(self) -> bool:
        """判断是否为平台内部内容收藏"""
        return self.shared_item_type is not None and self.shared_item_id is not None

    @property
    def is_chatroom_content(self) -> bool:
        """判断是否为聊天室内容收藏"""
        return self.shared_item_type == "chat_message"

    @property
    def is_forum_content(self) -> bool:
        """判断是否为论坛内容收藏"""
        return self.shared_item_type in ("forum_topic", "forum_comment", "forum_topic_attachment")

    @property
    def file_size_formatted(self) -> str:
        """格式化文件大小显示"""
        if not self.file_size_bytes:
            return "未知大小"
        
        size = self.file_size_bytes
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"

    @property
    def file_size(self):
        """向后兼容属性，映射到file_size_bytes"""
        return self.file_size_bytes

    @file_size.setter
    def file_size(self, value):
        """向后兼容属性设置器"""
        self.file_size_bytes = value

    def increment_access_count(self):
        """增加访问次数"""
        self.access_count = (self.access_count or 0) + 1

    @classmethod
    def get_supported_internal_types(cls) -> list:
        """获取支持的内部内容类型列表"""
        return [
            "project", "course", "forum_topic", "note", "daily_record", 
            "knowledge_document", "chat_message", "forum_comment", "forum_topic_attachment"
        ]

    @classmethod
    def get_chatroom_collection_types(cls) -> list:
        """获取聊天室收藏类型"""
        return ["chat_message"]

    @classmethod
    def get_forum_collection_types(cls) -> list:
        """获取论坛收藏类型"""
        return ["forum_topic", "forum_comment", "forum_topic_attachment"]

    def __repr__(self):
        return f"<CollectedContent(id={self.id}, title='{self.title}', type='{self.type}', owner_id={self.owner_id})>"


class CollectionStats:
    """收藏统计类 - 对应 SQL 中的 get_user_collection_stats 函数功能"""
    
    def __init__(self, total_collections: int = 0, chatroom_collections: int = 0, 
                 forum_collections: int = 0, other_collections: int = 0, total_storage: int = 0):
        self.total_collections = total_collections
        self.chatroom_collections = chatroom_collections
        self.forum_collections = forum_collections
        self.other_collections = other_collections
        self.total_storage = total_storage

    @property
    def total_storage_formatted(self) -> str:
        """格式化总存储大小显示"""
        if not self.total_storage:
            return "0 B"
        
        size = self.total_storage
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "total_collections": self.total_collections,
            "chatroom_collections": self.chatroom_collections,
            "forum_collections": self.forum_collections,
            "other_collections": self.other_collections,
            "total_storage": self.total_storage,
            "total_storage_formatted": self.total_storage_formatted
        }


class CollectionSummary:
    """收藏汇总类 - 对应 SQL 中的 v_collection_summary 视图功能"""
    
    def __init__(self, owner_id: int, folder_id: int = None, folder_name: str = None,
                 shared_item_type: str = None, content_type: str = None, 
                 count: int = 0, total_size: int = 0):
        self.owner_id = owner_id
        self.folder_id = folder_id
        self.folder_name = folder_name
        self.shared_item_type = shared_item_type
        self.content_type = content_type
        self.count = count
        self.total_size = total_size

    @property
    def total_size_formatted(self) -> str:
        """格式化总大小显示"""
        if not self.total_size:
            return "0 B"
        
        size = self.total_size
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "owner_id": self.owner_id,
            "folder_id": self.folder_id,
            "folder_name": self.folder_name,
            "shared_item_type": self.shared_item_type,
            "content_type": self.content_type,
            "count": self.count,
            "total_size": self.total_size,
            "total_size_formatted": self.total_size_formatted
        }


# 收藏类型常量定义
class CollectionContentType:
    """收藏内容类型常量"""
    
    # 平台内部内容类型
    PROJECT = "project"
    COURSE = "course"
    FORUM_TOPIC = "forum_topic"
    NOTE = "note"
    DAILY_RECORD = "daily_record"
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    CHAT_MESSAGE = "chat_message"
    FORUM_COMMENT = "forum_comment"
    FORUM_TOPIC_ATTACHMENT = "forum_topic_attachment"
    
    # 外部内容类型
    EXTERNAL_LINK = "external_link"
    EXTERNAL_FILE = "external_file"
    
    # 内容分类
    CHATROOM_TYPES = [CHAT_MESSAGE]
    FORUM_TYPES = [FORUM_TOPIC, FORUM_COMMENT, FORUM_TOPIC_ATTACHMENT]
    INTERNAL_TYPES = [
        PROJECT, COURSE, FORUM_TOPIC, NOTE, DAILY_RECORD, 
        KNOWLEDGE_DOCUMENT, CHAT_MESSAGE, FORUM_COMMENT, FORUM_TOPIC_ATTACHMENT
    ]
    
    @classmethod
    def is_chatroom_type(cls, content_type: str) -> bool:
        """判断是否为聊天室类型"""
        return content_type in cls.CHATROOM_TYPES
    
    @classmethod
    def is_forum_type(cls, content_type: str) -> bool:
        """判断是否为论坛类型"""
        return content_type in cls.FORUM_TYPES
    
    @classmethod
    def is_internal_type(cls, content_type: str) -> bool:
        """判断是否为内部类型"""
        return content_type in cls.INTERNAL_TYPES
    
    @classmethod
    def get_all_types(cls) -> list:
        """获取所有支持的类型"""
        return cls.INTERNAL_TYPES + [cls.EXTERNAL_LINK, cls.EXTERNAL_FILE]


# 收藏状态常量
class CollectionStatus:
    """收藏状态常量"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    
    @classmethod
    def get_all_statuses(cls) -> list:
        """获取所有状态"""
        return [cls.ACTIVE, cls.ARCHIVED, cls.DELETED]


# 默认文件夹常量
class DefaultFolders:
    """默认文件夹常量"""
    CHATROOM_FOLDER = "聊天室收藏"
    FORUM_FOLDER = "论坛收藏"
    GENERAL_FOLDER = "我的收藏"
    
    @classmethod
    def get_default_folders(cls) -> list:
        """获取默认文件夹列表"""
        return [
            {
                "name": cls.CHATROOM_FOLDER,
                "description": "来自聊天室的收藏内容",
                "color": "#4A90E2",
                "icon": "chat"
            },
            {
                "name": cls.FORUM_FOLDER,
                "description": "来自论坛的收藏内容",
                "color": "#FF6B6B",
                "icon": "forum"
            },
            {
                "name": cls.GENERAL_FOLDER,
                "description": "通用收藏内容",
                "color": "#50C878",
                "icon": "folder"
            }
        ]
