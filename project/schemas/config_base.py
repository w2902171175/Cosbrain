# project/schemas/config_base.py
"""
配置Schema基类 - 消除配置相关Schema中的重复代码
提供标准化的配置Schema模式
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
from datetime import datetime
from .common import TimestampMixin


class BaseConfigSchema(BaseModel):
    """配置Schema基类"""
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    description: Optional[str] = Field(None, max_length=500, description="配置描述")
    is_active: Optional[bool] = Field(True, description="是否激活")


class BaseConfigCreateSchema(BaseConfigSchema):
    """创建配置的基础Schema"""
    service_type: str = Field(..., description="服务类型")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_endpoint: Optional[str] = Field(None, description="API端点")
    api_version: Optional[str] = Field(None, description="API版本")
    model_id: Optional[str] = Field(None, description="模型ID")
    custom_headers: Optional[Dict[str, str]] = Field(None, description="自定义请求头")
    priority: Optional[int] = Field(1, ge=1, le=10, description="优先级（1-10）")
    health_check_url: Optional[str] = Field(None, description="健康检查URL")


class BaseConfigResponseSchema(BaseConfigCreateSchema, TimestampMixin):
    """配置响应基础Schema"""
    id: int
    owner_id: int
    api_key_encrypted: Optional[str] = Field(None, description="加密的API密钥（不返回明文）")
    
    # 不包含明文api_key字段，确保安全
    model_config = {
        'from_attributes': True,
        'exclude': {'api_key'}  # 确保不包含明文密钥
    }


class BaseConfigUpdateSchema(BaseModel):
    """更新配置的基础Schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="配置名称")
    description: Optional[str] = Field(None, max_length=500, description="配置描述")
    is_active: Optional[bool] = Field(None, description="是否激活")
    service_type: Optional[str] = Field(None, description="服务类型")
    api_key: Optional[str] = Field(None, description="API密钥")
    api_endpoint: Optional[str] = Field(None, description="API端点")
    api_version: Optional[str] = Field(None, description="API版本")
    model_id: Optional[str] = Field(None, description="模型ID")
    custom_headers: Optional[Dict[str, str]] = Field(None, description="自定义请求头")
    priority: Optional[int] = Field(None, ge=1, le=10, description="优先级（1-10）")
    health_check_url: Optional[str] = Field(None, description="健康检查URL")


# 工厂函数：为特定服务类型创建配置Schema
def create_config_schemas(
    service_name: str,
    service_types: list,
    additional_create_fields: Optional[Dict[str, Any]] = None,
    additional_response_fields: Optional[Dict[str, Any]] = None
):
    """
    为特定服务创建配置Schema的工厂函数
    
    Args:
        service_name: 服务名称（如 "TTS", "MCP", "SearchEngine"）
        service_types: 服务类型列表（如 ["openai", "google", "bing"]）
        additional_create_fields: 创建Schema的额外字段
        additional_response_fields: 响应Schema的额外字段
    
    Returns:
        tuple: (CreateSchema, ResponseSchema, UpdateSchema)
    """
    
    # 创建基础属性
    base_create_attrs = {
        'service_type': Field(..., description=f"{service_name}服务类型", 
                             examples=service_types[:3] if len(service_types) > 3 else service_types)
    }
    
    base_response_attrs = {}
    
    # 添加额外字段
    if additional_create_fields:
        base_create_attrs.update(additional_create_fields)
    if additional_response_fields:
        base_response_attrs.update(additional_response_fields)
    
    # 动态创建CreateSchema
    CreateSchema = type(
        f"{service_name}ConfigCreate",
        (BaseConfigCreateSchema,),
        {
            **base_create_attrs,
            '__annotations__': {
                **BaseConfigCreateSchema.__annotations__,
                **{k: type(v.default) if hasattr(v, 'default') else str 
                   for k, v in base_create_attrs.items()}
            }
        }
    )
    
    # 动态创建ResponseSchema  
    ResponseSchema = type(
        f"{service_name}ConfigResponse",
        (BaseConfigResponseSchema,),
        {
            **base_response_attrs,
            '__annotations__': {
                **BaseConfigResponseSchema.__annotations__,
                **{k: type(v.default) if hasattr(v, 'default') else str 
                   for k, v in base_response_attrs.items()}
            }
        }
    )
    
    # UpdateSchema继承CreateSchema但所有字段都是Optional
    update_attrs = {}
    for field_name, field_info in CreateSchema.__annotations__.items():
        if not field_name.startswith('_'):
            update_attrs[field_name] = Optional[field_info]
    
    UpdateSchema = type(
        f"{service_name}ConfigUpdate", 
        (BaseConfigUpdateSchema,),
        {
            '__annotations__': {
                **BaseConfigUpdateSchema.__annotations__,
                **update_attrs
            }
        }
    )
    
    return CreateSchema, ResponseSchema, UpdateSchema
