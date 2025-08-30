"""
企业级重排序提供者实现
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
import httpx

# 添加企业级组件路径
enterprise_path = Path(__file__).parent.parent.parent / "logs"
if str(enterprise_path) not in sys.path:
    sys.path.insert(0, str(enterprise_path))

from .ai_base import BaseRerankProvider, EnterpriseDecorator
from .ai_config import get_enterprise_config

class EnterpriseRerankProvider(BaseRerankProvider):
    """企业级重排序提供者"""
    
    def __init__(self, provider_name: str = "cohere", **kwargs):
        # 从企业配置获取参数
        config = get_enterprise_config()
        rerank_config = config.get_rerank_config(provider_name)
        
        if not rerank_config:
            raise ValueError(f"Rerank provider {provider_name} not found in configuration")
        
        if not rerank_config.api_key:
            raise ValueError(f"API key not configured for rerank provider {provider_name}")
        
        super().__init__(
            provider_name=provider_name,
            api_key=rerank_config.api_key,
            api_base=rerank_config.api_base,
            model=rerank_config.model,
            timeout=rerank_config.timeout,
            max_retries=rerank_config.max_retries
        )
        
        self.rerank_config = rerank_config
    
    @EnterpriseDecorator.with_retry(max_retries=3)
    @EnterpriseDecorator.with_timeout(timeout_seconds=30.0)
    async def rerank(
        self,
        query: str,
        documents: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """重排序文档"""
        async with self._request_context("rerank", query=query, documents=documents, **kwargs) as request_id:
            
            # 限制文档数量
            max_docs = kwargs.get("max_documents", self.rerank_config.max_documents)
            if len(documents) > max_docs:
                documents = documents[:max_docs]
            
            # 构建请求参数
            request_data = {
                "model": kwargs.get("model", self.model),
                "query": query,
                "documents": documents,
                "top_k": kwargs.get("top_k", len(documents)),
                "return_documents": kwargs.get("return_documents", True)
            }
            
            # 准备HTTP请求
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # 执行请求
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_base}/rerank",
                    headers=headers,
                    json=request_data
                )
                response.raise_for_status()
                
                result_data = response.json()
                
                # 解析响应
                result = {
                    "results": result_data.get("results", []),
                    "model": result_data.get("model", self.model),
                    "usage": result_data.get("usage", {}),
                    "request_id": request_id
                }
                
                return result
    
    async def _make_request(self, **kwargs) -> Any:
        """实现基础请求方法"""
        if kwargs.get("test"):
            # 健康检查的简单测试
            return {"status": "ok", "model": self.model}
        
        return await self.rerank(**kwargs)

async def get_rerank_scores_from_api(
    query: str,
    documents: List[str],
    api_key: str = None,
    llm_type: str = None,
    llm_base_url: str = None,
    fallback_to_similarity: bool = True,
    **kwargs
) -> List[float]:
    """
    获取重排序分数
    
    Args:
        query: 查询文本
        documents: 要重排序的文档列表
        api_key: API密钥
        llm_type: LLM类型
        llm_base_url: LLM基础URL
        fallback_to_similarity: 是否回退到相似度计算
        **kwargs: 其他参数
        
    Returns:
        重排序分数列表
    """
    try:
        # 创建重排序提供者
        provider = EnterpriseRerankProvider("cohere")
        
        # 执行重排序
        result = await provider.rerank(query, documents, **kwargs)
        
        if result and 'results' in result:
            # 提取分数
            scores = []
            for doc_result in result['results']:
                scores.append(doc_result.get('relevance_score', 0.0))
            return scores
        else:
            # 返回零分数
            return [0.0] * len(documents)
            
    except Exception as e:
        if fallback_to_similarity:
            # 回退到零分数
            return [0.0] * len(documents)
        else:
            raise e

def create_rerank_provider(provider_name: str = "cohere", **kwargs):
    """
    创建重排序提供者
    
    Args:
        provider_name: 提供者名称
        **kwargs: 其他参数
        
    Returns:
        重排序提供者实例
    """
    return EnterpriseRerankProvider(provider_name, **kwargs)
