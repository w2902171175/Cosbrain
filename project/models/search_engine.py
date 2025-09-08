# project/models/search_engine.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from project.base import Base
from .mixins import UserServiceConfigMixin


class UserSearchEngineConfig(Base, UserServiceConfigMixin):
    __tablename__ = "user_search_engine_configs"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - name, description, is_active (from UserConfigMixin)
    # - created_at, updated_at (from TimestampMixin)
    # - api_key_encrypted, api_endpoint, api_version, etc. (from ApiConfigMixin)
    # - service_type (必填), model_id, custom_headers, etc. (from ApiConfigMixin enhanced)
    # - priority, fallback_config_id, health_check_url, etc. (from ServiceConfigMixin)
    
    # 重写service_type的注释以提供搜索引擎特定说明
    service_type = Column(String, nullable=False, comment="搜索引擎类型，如：google, bing, duckduckgo")

    owner = relationship("User", back_populates="search_engine_configs")

    __table_args__ = (
        UniqueConstraint('owner_id', 'name', name='_user_search_engine_configs_owner_name_uc'),
    )
