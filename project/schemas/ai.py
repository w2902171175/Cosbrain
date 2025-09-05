# project/schemas/ai.py
"""
AI相关Schema模块（保留语义搜索等非LLM核心功能）
"""

from pydantic import BaseModel
from typing import Optional, List


# --- Semantic Search Schemas ---
class SemanticSearchRequest(BaseModel):
    """语义搜索请求模型"""
    query: str
    item_types: Optional[List[str]] = None
    limit: int = 10


class SemanticSearchResult(BaseModel):
    """语义搜索结果模型"""
    id: int
    title: str
    type: str
    content_snippet: Optional[str] = None
    relevance_score: float
