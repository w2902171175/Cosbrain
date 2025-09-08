# project/schemas/tts.py
"""
TTS (Text-to-Speech) 相关Schema模块
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from .common import TimestampMixin


# --- UserTTSConfig Schemas ---
class UserTTSConfigBase(BaseModel):
    """用户TTS配置基础模型"""
    name: str = Field(..., description="TTS配置名称，如：'我的OpenAI语音'")
    tts_type: Literal[
        "openai", "gemini", "aliyun", "siliconflow"
    ] = Field(..., description="语音提供商类型")
    api_key: Optional[str] = Field(None, description="API密钥（未加密）")
    base_url: Optional[str] = Field(None, description="API基础URL，如有自定义需求")
    model_id: Optional[str] = Field(None, description="语音模型ID，如：'tts-1', 'gemini-pro'")
    voice_name: Optional[str] = Field(None, description="语音名称或ID，如：'alloy', 'f_cn_zh_anqi_a_f'")
    is_active: Optional[bool] = Field(False, description="是否当前激活的TTS配置")

    model_config = {
        'protected_namespaces': ()
    }


class UserTTSConfigCreate(UserTTSConfigBase):
    """创建用户TTS配置模型"""
    name: str = Field(..., description="TTS配置名称")
    tts_type: Literal[
        "openai", "gemini", "aliyun", "siliconflow"
    ] = Field(..., description="语音提供商类型")
    api_key: str = Field(..., description="API密钥（未加密）")

    model_config = {
        'protected_namespaces': ()
    }


class UserTTSConfigUpdate(UserTTSConfigBase):
    """更新用户TTS配置模型"""
    name: Optional[str] = None
    tts_type: Optional[Literal["openai", "gemini", "aliyun", "siliconflow"]] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_id: Optional[str] = None
    voice_name: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = {
        'protected_namespaces': ()
    }


class UserTTSConfigResponse(UserTTSConfigBase, TimestampMixin):
    """用户TTS配置响应模型"""
    id: int
    owner_id: int
    api_key_encrypted: Optional[str] = Field(None, description="加密后的API密钥")

    model_config = {
        'protected_namespaces': (),
        'from_attributes': True,
        'json_encoders': {datetime: lambda dt: dt.isoformat() if dt is not None else None}
    }


# --- TTSTextRequest Schemas ---
class TTSTextRequest(BaseModel):
    """TTS文本请求模型"""
    text: str
    lang: str = "zh-CN"
