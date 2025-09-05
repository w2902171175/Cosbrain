# project/models/mcp.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from project.base import Base
from .mixins import UserServiceConfigMixin


class UserMcpConfig(Base, UserServiceConfigMixin):
    __tablename__ = "user_mcp_configs"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - name, description, is_active (from UserConfigMixin)
    # - created_at, updated_at (from TimestampMixin)
    # - api_key_encrypted, api_endpoint, api_version, etc. (from ApiConfigMixin)
    # - service_type (必填), model_id, custom_headers, etc. (from ApiConfigMixin enhanced)
    # - priority, fallback_config_id, health_check_url, etc. (from ServiceConfigMixin)
    
    # MCP特有字段
    protocol_type = Column(String, nullable=True, comment="协议类型，如：stdio, sse, websocket")
    
    # 重写service_type的注释以提供MCP特定说明
    service_type = Column(String, nullable=False, comment="MCP协议类型")

    owner = relationship("User", back_populates="mcp_configs")

    __table_args__ = (
        UniqueConstraint('owner_id', 'name', name='_user_mcp_configs_owner_name_uc'),
    )
