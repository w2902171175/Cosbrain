# project/schemas/search_engine.py
"""
搜索引擎相关Schema模块
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from .common import TimestampMixin


# --- UsersSearchEngineConfig Schemas ---
class UserSearchEngineConfigBase(BaseModel):
    """用户搜索引擎配置基础模型"""
    name: Optional[str] = None
    engine_type: Optional[Literal["bing", "tavily", "baidu", "google_cse", "custom"]] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = True
    description: Optional[str] = None
    base_url: Optional[str] = Field(None, description="搜索引擎API的基础URL")


class UserSearchEngineConfigCreate(UserSearchEngineConfigBase):
    """创建用户搜索引擎配置模型"""
    name: str
    engine_type: Literal["bing", "tavily", "baidu", "google_cse", "custom"]


class UserSearchEngineConfigResponse(UserSearchEngineConfigBase, TimestampMixin):
    """用户搜索引擎配置响应模型"""
    id: int
    owner_id: int


# --- SearchEngineStatusResponse Schemas ---
class SearchEngineStatusResponse(BaseModel):
    """搜索引擎状态响应模型"""
    status: str
    message: str
    engine_name: Optional[str] = None
    config_id: Optional[int] = None
    timestamp: datetime

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat() if dt is not None else None}


# --- WebSearchResult Schemas ---
class WebSearchResult(BaseModel):
    """网络搜索结果模型"""
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    """网络搜索响应模型"""
    query: str
    engine_used: str
    results: List[WebSearchResult]
    total_results: Optional[int] = None
    search_time: Optional[float] = None
    message: Optional[str] = None

    class Config:
        from_attributes = True


# --- WebSearchRequest Schemas ---
class WebSearchRequest(BaseModel):
    """网络搜索请求模型"""
    query: str
    engine_config_id: int
    limit: int = 5
