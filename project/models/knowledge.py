# project/models/knowledge.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, BigInteger, text, CheckConstraint, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from project.base import Base
from .mixins import TimestampMixin, OwnerMixin, EmbeddingMixin, BaseContentMixin


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True, nullable=False)
    description = Column(Text)
    access_type = Column(String)
    is_public = Column(Boolean, default=False, nullable=False, comment="是否公开: True(公开到全平台), False(私密)")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    owner = relationship("User", back_populates="knowledge_bases")
    documents = relationship("KnowledgeDocument", back_populates="knowledge_base",
                             cascade="all, delete-orphan")
    kb_folders = relationship("KnowledgeBaseFolder", back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeBaseFolder(Base):
    __tablename__ = "knowledge_base_folders"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, index=True, comment="所属知识库ID")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True,
                      comment="文件夹所有者ID (与知识库所有者相同)")

    name = Column(String, nullable=False, comment="文件夹名称")
    description = Column(Text, nullable=True, comment="文件夹描述")
    is_public = Column(Boolean, default=False, nullable=False, comment="是否公开: True(公开到全平台), False(私密)")

    parent_id = Column(Integer, ForeignKey("knowledge_base_folders.id"), nullable=True, index=True,
                       comment="父文件夹ID")
    order = Column(Integer, default=0, comment="排序")

    linked_folder_type = Column(String, nullable=True,
                                comment="链接到的外部文件夹类型：'note_folder'（课程笔记文件夹）或'collected_content_folder'（收藏文件夹）")
    linked_folder_id = Column(BigInteger, nullable=True, comment="链接到的外部文件夹ID")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    knowledge_base = relationship("KnowledgeBase", back_populates="kb_folders")
    owner = relationship("User")

    # START MODIFICATION FOR KnowledgeBaseFolder relationships
    children = relationship(
        "KnowledgeBaseFolder",
        back_populates="parent",
        cascade="all, delete-orphan", # Correctly cascade deletion for children
        single_parent=True # Correctly mark children as exclusively tied to this parent
    )
    parent = relationship(
        "KnowledgeBaseFolder",
        remote_side=[id], # Explicitly state that 'id' of the remote KnowledgeBaseFolder (parent) is the target
        back_populates="children"
    )
    # END MODIFICATION FOR KnowledgeBaseFolder relationships

    documents = relationship("KnowledgeDocument", back_populates="kb_folder", cascade="all, delete-orphan")

    __table_args__ = (
        Index('_kb_folder_name_unique_idx', 'kb_id', 'parent_id', 'name', unique=True,
              postgresql_where=text("parent_id IS NOT NULL AND linked_folder_type IS NULL")),
        Index('_kb_folder_root_name_unique_idx', 'kb_id', 'name', unique=True,
              postgresql_where=text("parent_id IS NULL AND linked_folder_type IS NULL")),
        Index('_kb_folder_linked_unique_idx', 'kb_id', 'linked_folder_type', 'linked_folder_id', unique=True,
              postgresql_where=text("linked_folder_type IS NOT NULL AND linked_folder_id IS NOT NULL")),
    )


class KnowledgeDocument(Base, TimestampMixin, OwnerMixin):
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - created_at, updated_at (from TimestampMixin)
    
    # KnowledgeDocument特有字段
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, comment="所属知识库ID")

    file_name = Column(String, nullable=False, comment="文件名称")
    file_path = Column(String, nullable=False, comment="文件路径")
    file_type = Column(String, nullable=True, comment="文件类型")
    
    # 内容类型分类字段
    content_type = Column(String, nullable=False, default="file", 
                         comment="内容类型分类：file-文档文件, image-图片, video-视频, url-网址链接, website-网站")
    
    # 网址和网站类型相关字段
    url = Column(Text, nullable=True, comment="网址URL，用于url和website类型的文档")
    website_title = Column(String, nullable=True, comment="网站标题，从网页自动提取或用户自定义")
    website_description = Column(Text, nullable=True, comment="网站描述，从网页自动提取或用户自定义")
    
    # 文件元数据字段（统一字段命名）
    file_size_bytes = Column(BigInteger, nullable=True, comment="文件大小，单位字节")
    mime_type = Column(String, nullable=True, comment="MIME类型，用于更精确的文件类型识别")
    
    # 缩略图字段
    thumbnail_path = Column(String, nullable=True, comment="缩略图路径，用于图片和视频的预览")

    status = Column(String, default="processing", comment="处理状态")
    processing_message = Column(Text, nullable=True, comment="处理消息")
    total_chunks = Column(Integer, default=0, comment="总分块数")

    kb_folder_id = Column(Integer, ForeignKey("knowledge_base_folders.id"), nullable=True, index=True,
                          comment="所属知识库文件夹ID")

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    owner = relationship("User", back_populates="uploaded_documents")
    chunks = relationship("KnowledgeDocumentChunk", back_populates="document", cascade="all, delete-orphan")
    kb_folder = relationship("KnowledgeBaseFolder", back_populates="documents")

    @property
    def file_size(self):
        """向后兼容属性，映射到file_size_bytes"""
        return self.file_size_bytes

    @file_size.setter
    def file_size(self, value):
        """向后兼容属性设置器"""
        self.file_size_bytes = value

    # 表级约束和索引
    __table_args__ = (
        # 内容类型字段索引，提高查询性能
        Index('idx_knowledge_documents_content_type', 'content_type'),
        
        # 检查约束确保内容类型值的有效性
        CheckConstraint(
            "content_type IN ('file', 'image', 'video', 'url', 'website')",
            name='chk_content_type'
        ),
        
        # 网址类型的记录必须有url字段
        CheckConstraint(
            "((content_type IN ('url', 'website') AND url IS NOT NULL AND url != '') OR "
            "(content_type NOT IN ('url', 'website')))",
            name='chk_url_required'
        ),
    )


class KnowledgeDocumentChunk(Base):
    __tablename__ = "knowledge_document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)

    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024))

    created_at = Column(DateTime, server_default=func.now())

    document = relationship("KnowledgeDocument", back_populates="chunks")
