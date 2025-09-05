# project/models/mixins.py
"""
数据库模型混入类
提供通用的字段和功能，减少重复代码
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, BigInteger, UniqueConstraint
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector


class TimestampMixin:
    """时间戳混入类
    
    为模型添加创建时间和更新时间字段
    """
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, onupdate=func.now(), comment="更新时间")


class OwnerMixin:
    """用户所有者混入类
    
    为模型添加所有者关联
    """
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="所有者ID")


class EmbeddingMixin:
    """嵌入向量混入类
    
    为模型添加文本嵌入功能
    """
    combined_text = Column(Text, nullable=True, comment="组合文本内容")
    embedding = Column(Vector(1024), nullable=True, comment="文本嵌入向量")


class UserConfigMixin(TimestampMixin, OwnerMixin):
    """用户配置基类
    
    用于所有用户配置相关的模型
    包含：时间戳、所有者、基本配置字段
    """
    name = Column(String, nullable=False, comment="配置名称")
    description = Column(Text, nullable=True, comment="配置描述")
    is_active = Column(Boolean, default=True, comment="是否激活")


class LikeMixin(TimestampMixin, OwnerMixin):
    """点赞混入类
    
    为各种点赞功能提供统一的基础结构
    包含创建时间和所有者信息
    """
    pass


class PolymorphicLikeMixin(LikeMixin):
    """多态点赞混入类
    
    为可以点赞不同类型目标的点赞功能提供基础结构
    使用多态设计，可以支持不同类型的点赞目标
    """
    target_id = Column(Integer, nullable=False, comment="目标对象ID")
    target_type = Column(String, nullable=False, comment="目标对象类型")


class BaseContentMixin(TimestampMixin, OwnerMixin):
    """基础内容混入类
    
    为包含标题、内容的模型提供统一结构
    """
    title = Column(String, nullable=False, comment="标题")
    content = Column(Text, nullable=True, comment="内容")
    is_public = Column(Boolean, default=True, comment="是否公开")


class MetadataMixin:
    """元数据混入类
    
    为模型添加通用的元数据字段
    """
    tags = Column(Text, nullable=True, comment="标签，JSON格式")
    metadata = Column(Text, nullable=True, comment="扩展元数据，JSON格式")


class StatusMixin:
    """状态混入类
    
    为需要状态管理的模型提供通用状态字段
    """
    status = Column(String, default="active", comment="状态：active, inactive, deleted")
    is_deleted = Column(Boolean, default=False, comment="是否已删除")


class ApiConfigMixin(UserConfigMixin):
    """API配置混入类
    
    为各种API配置模型提供统一结构，包括常用的API配置字段
    """
    api_key_encrypted = Column(Text, nullable=True, comment="加密的API密钥")
    api_endpoint = Column(String, nullable=True, comment="API端点URL/基础URL")
    api_version = Column(String, nullable=True, comment="API版本")
    max_requests_per_minute = Column(Integer, default=60, comment="每分钟最大请求数")
    timeout_seconds = Column(Integer, default=30, comment="请求超时时间（秒）")
    
    # 新增通用配置字段
    service_type = Column(String, nullable=True, comment="服务类型标识")
    model_id = Column(String, nullable=True, comment="模型ID或引擎标识")
    custom_headers = Column(Text, nullable=True, comment="自定义请求头（JSON格式）")
    retry_attempts = Column(Integer, default=3, comment="重试次数")
    connection_pool_size = Column(Integer, default=10, comment="连接池大小")


class MediaMixin:
    """媒体文件混入类
    
    为需要存储媒体文件信息的模型提供统一的字段结构
    包含：媒体URL、类型、原始文件名、文件大小等
    """
    media_url = Column(String, nullable=True, comment="媒体文件OSS URL")
    media_type = Column(String, nullable=True, comment="媒体类型：image, video, audio, file")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    file_size_bytes = Column(BigInteger, nullable=True, comment="媒体文件大小（字节）")


class FileHandlingMixin(MediaMixin):
    """文件处理混入类
    
    为需要文件处理功能的模型提供统一的字段和方法
    继承MediaMixin的所有字段，并添加文件处理相关功能
    """
    
    def get_file_size_formatted(self) -> str:
        """获取格式化的文件大小"""
        if not hasattr(self, 'file_size_bytes') or not self.file_size_bytes:
            return "0 B"
        
        size = self.file_size_bytes
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    
    def is_image(self) -> bool:
        """判断是否为图片文件"""
        if not hasattr(self, 'media_type') or not self.media_type:
            return False
        return self.media_type.lower() in ['image', 'img'] or (
            hasattr(self, 'original_filename') and self.original_filename and
            self.original_filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'))
        )
    
    def is_video(self) -> bool:
        """判断是否为视频文件"""
        if not hasattr(self, 'media_type') or not self.media_type:
            return False
        return self.media_type.lower() in ['video', 'vid'] or (
            hasattr(self, 'original_filename') and self.original_filename and
            self.original_filename.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'))
        )


class ServiceConfigMixin(ApiConfigMixin):
    """服务配置混入类
    
    为特定服务配置提供更专业的基础结构
    继承ApiConfigMixin的所有字段，并添加服务相关配置
    """
    priority = Column(Integer, default=1, comment="配置优先级，数字越小优先级越高")
    fallback_config_id = Column(Integer, nullable=True, comment="备用配置ID")
    health_check_url = Column(String, nullable=True, comment="健康检查URL")
    last_health_check = Column(DateTime, nullable=True, comment="上次健康检查时间")
    is_healthy = Column(Boolean, default=True, comment="服务是否健康")


class UserServiceConfigMixin(ServiceConfigMixin):
    """用户服务配置混入类
    
    为用户特定的服务配置提供统一结构
    包含用户关系和通用约束模式
    """
    
    # 重写service_type为必填字段（所有用户配置都需要指定服务类型）
    service_type = Column(String, nullable=False, comment="服务类型标识")
    
    @classmethod
    def get_owner_relationship_name(cls):
        """获取owner关系的反向引用名称
        
        子类可以重写此方法来自定义关系名称
        """
        # 默认使用表名的复数形式
        table_name = cls.__tablename__
        if table_name.endswith('_configs'):
            return table_name[:-8] + '_configs'  # 移除'_configs'后再加回来
        return table_name + '_configs'
    
    @classmethod
    def get_unique_constraints(cls):
        """获取唯一约束
        
        子类可以重写此方法来添加额外的唯一约束
        默认提供 owner_id + name 的唯一约束
        """
        constraint_name = f"_{cls.__tablename__}_owner_name_uc"
        return [
            UniqueConstraint('owner_id', 'name', name=constraint_name),
        ]


class UserConfigModelTemplate:
    """用户配置模型模板类
    
    提供创建用户配置模型的标准模板和工厂方法
    减少样板代码，统一配置模型的创建模式
    """
    
    @staticmethod
    def create_user_config_class(table_name: str, service_comment: str, back_populates_name: str):
        """创建用户配置类的工厂方法
        
        Args:
            table_name: 数据库表名
            service_comment: 服务类型的注释
            back_populates_name: User模型中的反向关系名称
            
        Returns:
            配置类的字典，包含常用字段和方法
        """
        
        class_attrs = {
            '__tablename__': table_name,
            'id': Column(Integer, primary_key=True, index=True),
            'service_type': Column(String, nullable=False, comment=service_comment),
        }
        
        # 添加标准的owner关系
        def create_owner_relationship():
            from sqlalchemy.orm import relationship
            return relationship("User", back_populates=back_populates_name)
        
        class_attrs['owner'] = create_owner_relationship()
        
        # 添加标准约束
        constraint_name = f"_{table_name}_owner_name_uc"
        class_attrs['__table_args__'] = (
            UniqueConstraint('owner_id', 'name', name=constraint_name),
        )
        
        return class_attrs
