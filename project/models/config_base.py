# project/models/config_base.py
"""
用户配置模型基类和工厂函数
提供标准化的用户配置模型创建模式
"""

from typing import Type, Optional, List, Dict, Any
from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from project.base import Base
from .mixins import UserServiceConfigMixin


class BaseUserConfig(Base, UserServiceConfigMixin):
    """用户配置的抽象基类
    
    不要直接使用此类，而是使用create_user_config_model函数创建具体的配置模型
    """
    __abstract__ = True  # 标记为抽象类，不会创建数据库表
    
    id = Column(Integer, primary_key=True, index=True)


def create_user_config_model(
    class_name: str,
    table_name: str,
    service_type_comment: str,
    back_populates_name: str,
    additional_fields: Optional[Dict[str, Any]] = None,
    additional_constraints: Optional[List[Any]] = None,
    class_docstring: Optional[str] = None
) -> Type[BaseUserConfig]:
    """创建用户配置模型的工厂函数
    
    Args:
        class_name: 类名，如 'UserTTSConfig'
        table_name: 数据库表名，如 'user_tts_configs'
        service_type_comment: service_type字段的注释
        back_populates_name: User模型中的反向关系名称，如 'tts_configs'
        additional_fields: 额外的字段定义字典
        additional_constraints: 额外的表约束列表
        class_docstring: 类的文档字符串
        
    Returns:
        配置模型类
    """
    
    # 基础属性
    class_attrs = {
        '__tablename__': table_name,
        '__module__': 'project.models',
        'id': Column(Integer, primary_key=True, index=True),
        'service_type': Column(String, nullable=False, comment=service_type_comment),
    }
    
    # 添加owner关系
    class_attrs['owner'] = relationship("User", back_populates=back_populates_name)
    
    # 添加额外字段
    if additional_fields:
        class_attrs.update(additional_fields)
    
    # 设置表约束
    constraints = [
        UniqueConstraint('owner_id', 'name', name=f'_{table_name}_owner_name_uc'),
    ]
    if additional_constraints:
        constraints.extend(additional_constraints)
    
    class_attrs['__table_args__'] = tuple(constraints)
    
    # 设置文档字符串
    if class_docstring:
        class_attrs['__doc__'] = class_docstring
    
    # 动态创建类
    config_class = type(class_name, (BaseUserConfig,), class_attrs)
    
    return config_class


# 预定义的标准配置模型工厂函数

def create_mcp_config_model() -> Type[BaseUserConfig]:
    """创建MCP配置模型"""
    return create_user_config_model(
        class_name='UserMcpConfig',
        table_name='user_mcp_configs',
        service_type_comment='MCP协议类型',
        back_populates_name='mcp_configs',
        additional_fields={
            'protocol_type': Column(String, nullable=True, comment="协议类型，如：stdio, sse, websocket"),
        },
        class_docstring="用户MCP（Model Context Protocol）配置模型"
    )


def create_search_engine_config_model() -> Type[BaseUserConfig]:
    """创建搜索引擎配置模型"""
    return create_user_config_model(
        class_name='UserSearchEngineConfig',
        table_name='user_search_engine_configs',
        service_type_comment='搜索引擎类型，如：google, bing, duckduckgo',
        back_populates_name='search_engine_configs',
        class_docstring="用户搜索引擎配置模型"
    )


def create_tts_config_model() -> Type[BaseUserConfig]:
    """创建TTS配置模型"""
    return create_user_config_model(
        class_name='UserTTSConfig',
        table_name='user_tts_configs',
        service_type_comment='语音提供商类型，如：openai, gemini, aliyun',
        back_populates_name='tts_configs',
        additional_fields={
            'voice_name': Column(String, nullable=True, comment="语音名称或ID，如：'alloy', 'f_cn_zh_anqi_a_f'"),
            'is_active': Column(Boolean, default=False, nullable=False, comment="是否当前激活的TTS配置"),
        },
        class_docstring="用户文本转语音(TTS)配置模型"
    )


# 配置模型注册表
CONFIG_MODEL_REGISTRY = {
    'mcp': create_mcp_config_model,
    'search_engine': create_search_engine_config_model,
    'tts': create_tts_config_model,
}


def get_config_model(config_type: str) -> Type[BaseUserConfig]:
    """根据配置类型获取配置模型
    
    Args:
        config_type: 配置类型，如 'mcp', 'search_engine', 'tts'
        
    Returns:
        配置模型类
        
    Raises:
        ValueError: 如果配置类型不存在
    """
    if config_type not in CONFIG_MODEL_REGISTRY:
        available_types = ', '.join(CONFIG_MODEL_REGISTRY.keys())
        raise ValueError(f"未知的配置类型: {config_type}. 可用类型: {available_types}")
    
    return CONFIG_MODEL_REGISTRY[config_type]()


def register_config_model(config_type: str, factory_func):
    """注册新的配置模型工厂函数
    
    Args:
        config_type: 配置类型标识
        factory_func: 工厂函数，应该返回配置模型类
    """
    CONFIG_MODEL_REGISTRY[config_type] = factory_func
