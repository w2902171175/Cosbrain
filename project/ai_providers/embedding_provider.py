# ai_providers/embedding_provider.py
"""
嵌入服务提供者实现
"""
import httpx
from typing import List, Optional
from .ai_base import EmbeddingProvider
from .config import DEFAULT_EMBEDDING_CONFIGS, GLOBAL_PLACEHOLDER_ZERO_VECTOR


class SiliconFlowEmbeddingProvider(EmbeddingProvider):
    """SiliconFlow嵌入服务提供者"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(api_key, base_url, model)
        
        config = DEFAULT_EMBEDDING_CONFIGS["siliconflow"]
        self.base_url = base_url or config["base_url"]
        self.model = model or config["default_model"]
        self.embeddings_url = f"{self.base_url.rstrip('/')}{config['embeddings_path']}"
    
    async def get_embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None
    ) -> List[List[float]]:
        """获取文本嵌入向量"""
        if not texts:
            return []
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model or self.model,
            "input": texts
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.embeddings_url,
                    headers=headers,
                    json=data
                )
                response.raise_for_status()
                result = response.json()
                
                # 提取嵌入向量
                embeddings = []
                for item in result.get("data", []):
                    embeddings.append(item.get("embedding", GLOBAL_PLACEHOLDER_ZERO_VECTOR))
                
                return embeddings
                
        except httpx.HTTPStatusError as e:
            print(f"ERROR_SILICONFLOW_EMBEDDING: HTTP {e.response.status_code} 错误: {e.response.text}")
            # 返回占位符向量
            return [GLOBAL_PLACEHOLDER_ZERO_VECTOR] * len(texts)
        except httpx.RequestError as e:
            print(f"ERROR_SILICONFLOW_EMBEDDING: 请求错误: {e}")
            return [GLOBAL_PLACEHOLDER_ZERO_VECTOR] * len(texts)
        except Exception as e:
            print(f"ERROR_SILICONFLOW_EMBEDDING: 未知错误: {e}")
            return [GLOBAL_PLACEHOLDER_ZERO_VECTOR] * len(texts)


def create_embedding_provider(
    provider_type: str,
    api_key: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None
) -> EmbeddingProvider:
    """
    嵌入提供者工厂函数
    
    Args:
        provider_type: 提供者类型
        api_key: API密钥
        base_url: API基础URL（可选）
        model: 模型名称（可选）
        
    Returns:
        嵌入提供者实例
    """
    if provider_type == "siliconflow":
        return SiliconFlowEmbeddingProvider(api_key, base_url, model)
    else:
        raise ValueError(f"不支持的嵌入提供者类型: {provider_type}")


# --- 兼容性包装函数 ---
async def get_embeddings_from_api(
    texts: List[str],
    api_key: str,
    api_type: str = "siliconflow",
    api_url: Optional[str] = None,
    embedding_model: Optional[str] = None,
    **kwargs
) -> List[List[float]]:
    """
    向后兼容的嵌入API调用函数
    保持与原ai_core.get_embeddings_from_api的接口兼容
    """
    try:
        provider = create_embedding_provider(
            provider_type=api_type,
            api_key=api_key,
            base_url=api_url,
            model=embedding_model
        )
        
        # 如果API密钥是占位符，返回零向量
        if api_key == "dummy_key" or api_key == "dummy_key_for_testing_without_api":
            return [GLOBAL_PLACEHOLDER_ZERO_VECTOR] * len(texts)
        
        embeddings = await provider.get_embeddings(texts)
        return embeddings
        
    except Exception as e:
        print(f"WARNING: 嵌入生成失败: {e}, 返回零向量")
        return [GLOBAL_PLACEHOLDER_ZERO_VECTOR] * len(texts)
