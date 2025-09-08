# project/schemas/llm.py
"""
LLM (Large Language Model) 相关Schema模块
包含LLM配置、对话管理、问答系统等核心功能的数据模型
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
import json
from .common import TimestampMixin


# --- LLM Configuration Schemas ---
class UserLLMConfigUpdate(BaseModel):
    """用户LLM配置更新模型"""
    llm_api_type: Optional[Literal[
        "openai",
        "zhipu", 
        "siliconflow",
        "huoshanengine",
        "kimi",
        "deepseek",
        "custom_openai"
    ]] = None
    llm_api_key: Optional[str] = None
    llm_api_base_url: Optional[str] = None
    llm_model_id: Optional[str] = None  # 保留原字段以兼容性
    llm_model_ids: Optional[Dict[str, List[str]]] = None  # 新字段：为每个服务商配置的模型ID列表


class LLMModelConfigBase(BaseModel):
    """LLM模型配置基础模型"""
    api_type: Literal[
        "openai", "zhipu", "siliconflow", "huoshanengine", "kimi", "deepseek", "custom_openai"
    ] = Field(..., description="LLM服务提供商类型")
    api_base_url: Optional[str] = None
    model_id: Optional[str] = None
    model_ids: Optional[Dict[str, List[str]]] = None
    api_key_encrypted: Optional[str] = None

    model_config = {
        'protected_namespaces': ()
    }

    @field_validator('model_ids', mode='before')
    @classmethod
    def parse_model_ids(cls, value):
        """
        在验证之前，尝试将字符串类型的 model_ids 解析为字典。
        """
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return value


# --- AI Conversation Message Schemas ---
class AIConversationMessageBase(BaseModel):
    """AI对话消息基础模型"""
    role: Literal["user", "assistant", "tool_call", "tool_output"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容（文本）")
    tool_calls_json: Optional[List[Dict[str, Any]]] = Field(None, description="工具调用的JSON数据")
    tool_output_json: Optional[Dict[str, Any]] = Field(None, description="工具输出的JSON数据")
    llm_type_used: Optional[str] = Field(None, description="本次消息使用的LLM类型")
    llm_model_used: Optional[str] = Field(None, description="本次消息使用的LLM模型ID")


class AIConversationMessageCreate(AIConversationMessageBase):
    """创建AI对话消息模型"""
    pass


class AIConversationMessageResponse(AIConversationMessageBase, TimestampMixin):
    """AI对话消息响应模型"""
    id: int
    conversation_id: int
    sent_at: datetime


# --- AI Conversation Schemas ---
class AIConversationBase(BaseModel):
    """AI对话基础模型"""
    title: Optional[str] = Field(None, description="对话标题")


class AIConversationCreate(AIConversationBase):
    """创建AI对话模型"""
    pass


class AIConversationResponse(AIConversationBase, TimestampMixin):
    """AI对话响应模型"""
    id: int
    user_id: int
    last_updated: datetime
    total_messages_count: Optional[int] = Field(None, description="对话中的总消息数量")


class AIConversationRegenerateTitleRequest(BaseModel):
    """AI对话标题重新生成请求模型"""
    pass  # 留空表示请求体可以是空的 {}


# --- AI Q&A Schemas ---
class AIQARequest(BaseModel):
    """AI问答请求模型"""
    query: str
    kb_ids: Optional[List[int]] = None
    note_ids: Optional[List[int]] = None
    use_tools: Optional[bool] = False
    preferred_tools: Optional[List[Literal["rag", "web_search", "mcp_tool"]]] = None
    llm_model_id: Optional[str] = None
    conversation_id: Optional[int] = Field(None, description="要继续的对话Session ID")


class AIQAResponse(BaseModel):
    """AI问答响应模型"""
    answer: str
    answer_mode: str
    llm_type_used: Optional[str] = None
    llm_model_used: Optional[str] = None
    conversation_id: int = Field(..., description="当前问答所关联的对话Session ID")
    turn_messages: List["AIConversationMessageResponse"] = Field(..., description="当前轮次的完整消息序列")
    source_articles: Optional[List[Dict[str, Any]]] = Field(None, description="搜索到的源内容")
    search_results: Optional[List[Dict[str, Any]]] = None

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- LLM Usage Statistics Schemas ---
class LLMUsageStatsBase(BaseModel):
    """LLM使用统计基础模型"""
    model_type: str = Field(..., description="LLM模型类型")
    total_tokens: int = Field(0, description="总token使用量")
    input_tokens: int = Field(0, description="输入token数量")
    output_tokens: int = Field(0, description="输出token数量")

    model_config = {
        'protected_namespaces': ()
    }
    total_requests: int = Field(0, description="总请求次数")
    successful_requests: int = Field(0, description="成功请求次数")
    failed_requests: int = Field(0, description="失败请求次数")


class LLMUsageStatsResponse(LLMUsageStatsBase, TimestampMixin):
    """LLM使用统计响应模型"""
    id: int
    user_id: int
    date: datetime = Field(..., description="统计日期")

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}