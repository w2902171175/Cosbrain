# project/models/tts.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from project.base import Base
from .mixins import UserServiceConfigMixin


class UserTTSConfig(Base, UserServiceConfigMixin):
    __tablename__ = "user_tts_configs"

    id = Column(Integer, primary_key=True, index=True)
    
    # 使用混入类继承的字段：
    # - owner_id (from OwnerMixin)
    # - name, description, is_active (from UserConfigMixin)
    # - created_at, updated_at (from TimestampMixin)
    # - api_key_encrypted, api_endpoint, api_version, etc. (from ApiConfigMixin)
    # - service_type (必填), model_id, custom_headers, etc. (from ApiConfigMixin enhanced)
    # - priority, fallback_config_id, health_check_url, etc. (from ServiceConfigMixin)
    
    # TTS特有字段
    voice_name = Column(String, nullable=True, comment="语音名称或ID，如：'alloy', 'f_cn_zh_anqi_a_f'")
    
    # 重写service_type的注释以提供TTS特定说明
    service_type = Column(String, nullable=False, comment="语音提供商类型，如：'openai', 'gemini', 'aliyun'")
    
    # 重写is_active的默认值（TTS配置特殊需求：默认不激活）
    is_active = Column(Boolean, default=False, nullable=False, comment="是否当前激活的TTS配置")

    owner = relationship("User", back_populates="tts_configs")

    __table_args__ = (
        UniqueConstraint('owner_id', 'name', name='_user_tts_configs_owner_name_uc'),
        # 同一个用户下配置名称唯一
        # 注意：为了确保每个用户只有一个激活的TTS配置，需要在应用层面处理
        # UniqueConstraint('owner_id', 'is_active', name='_owner_id_active_tts_config_uc'),
    )
