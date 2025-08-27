# ai_providers/rerank_provider.py
"""
重排服务提供者实现
"""
import httpx
from typing import List, Dict, Any, Optional
from .ai_base import RerankProvider
from .config import DEFAULT_RERANK_CONFIGS


class SiliconFlowRerankProvider(RerankProvider):
    """SiliconFlow重排服务提供者"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key, base_url, model)
        
        config = DEFAULT_RERANK_CONFIGS["siliconflow"]
        self.base_url = base_url or config["base_url"]
        self.model = model or config["default_model"]
        self.rerank_url = f"{self.base_url.rstrip('/')}{config['rerank_path']}"
    
    async def rerank(
        self,
        query: str,
        documents: List[str],
        model: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """对文档进行重排"""
        if not documents:
            return []
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model or self.model,
            "query": query,
            "documents": documents
        }
        
        if top_k is not None:
            data["top_k"] = top_k
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.rerank_url,
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                
                # 提取重排结果
                return result.get("results", [])
                
        except httpx.HTTPStatusError as e:
            print(f"ERROR_SILICONFLOW_RERANK: HTTP {e.response.status_code} 错误: {e.response.text}")
            # 返回原始顺序
            return [{"index": i, "relevance_score": 0.0, "document": doc} 
                   for i, doc in enumerate(documents)]
        except httpx.RequestError as e:
            print(f"ERROR_SILICONFLOW_RERANK: 请求错误: {e}")
            return [{"index": i, "relevance_score": 0.0, "document": doc} 
                   for i, doc in enumerate(documents)]
        except Exception as e:
            print(f"ERROR_SILICONFLOW_RERANK: 未知错误: {e}")
            return [{"index": i, "relevance_score": 0.0, "document": doc} 
                   for i, doc in enumerate(documents)]


def create_rerank_provider(
    provider_type: str,
    api_key: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None
) -> RerankProvider:
    """
    重排提供者工厂函数
    
    Args:
        provider_type: 提供者类型
        api_key: API密钥
        base_url: API基础URL（可选）
        model: 模型名称（可选）
        
    Returns:
        重排提供者实例
    """
    if provider_type == "siliconflow":
        return SiliconFlowRerankProvider(api_key, base_url, model)
    else:
        raise ValueError(f"不支持的重排提供者类型: {provider_type}")


# --- 兼容性包装函数 ---
async def get_rerank_scores_from_api(
    query: str,
    documents: List[str],
    api_key: str,
    api_type: str = "siliconflow",
    api_url: Optional[str] = None,
    rerank_model: Optional[str] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    向后兼容的重排序API调用函数
    保持与原ai_core.get_rerank_scores_from_api的接口兼容
    """
    try:
        provider = create_rerank_provider(
            provider_type=api_type,
            api_key=api_key,
            base_url=api_url,
            model=rerank_model
        )
        
        results = await provider.rerank(query, documents)
        return results
        
    except Exception as e:
        print(f"WARNING: 重排序失败: {e}, 返回原始顺序")
        return [{"index": i, "relevance_score": 0.0, "document": doc} 
               for i, doc in enumerate(documents)]
