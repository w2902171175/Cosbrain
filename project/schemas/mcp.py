# project/schemas/mcp.py
"""
MCP (Model Context Protocol) 相关Schema模块
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from .common import TimestampMixin


# --- UserMcpConfig Schemas ---
class UserMcpConfigBase(BaseModel):
    """用户MCP配置基础模型"""
    name: Optional[str] = None
    mcp_type: Optional[Literal["modelscope_community", "custom_mcp"]] = None
    base_url: Optional[str] = None
    protocol_type: Optional[Literal["sse", "http_rest", "websocket"]] = "http_rest"
    api_key: Optional[str] = None
    is_active: Optional[bool] = True
    description: Optional[str] = None


class UserMcpConfigCreate(UserMcpConfigBase):
    """创建用户MCP配置模型"""
    name: str
    base_url: str


class UserMcpConfigResponse(UserMcpConfigBase, TimestampMixin):
    """用户MCP配置响应模型"""
    id: int
    owner_id: int


# --- McpStatusResponse Schemas ---
class McpStatusResponse(BaseModel):
    """MCP状态响应模型"""
    status: str
    message: str
    service_name: Optional[str] = None
    config_id: Optional[int] = None
    timestamp: datetime

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- McpToolDefinition Schemas ---
class McpToolDefinition(BaseModel):
    """MCP工具定义模型"""
    tool_id: str
    name: str
    description: str
    mcp_config_id: int
    mcp_config_name: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    class Config:
        from_attributes = True
