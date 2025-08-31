"""
企业级嵌入提供者
现代化、高性能的向量嵌入服务
"""

import asyncio
import time
import openai
from typing import List, Dict, Any, Union, Optional
from dataclasses import dataclass
import numpy as np

from .ai_base import BaseEmbeddingProvider, EnterpriseDecorator
from .ai_config import get_enterprise_config

@dataclass
class EmbeddingResult:
    """嵌入结果"""
    embeddings: List[List[float]]
    usage: Dict[str, int]
    model: str
    response_time: float

class EnterpriseEmbeddingProvider(BaseEmbeddingProvider):
    """企业级嵌入提供者"""
    
    def __init__(
        self,
        provider_name: str = "openai",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: str = "text-embedding-3-small",
        **kwargs
    ):
        # 获取配置
        config = get_enterprise_config()
        provider_config = config.providers.get(provider_name)
        
        if provider_config:
            api_key = api_key or provider_config.api_key
            api_base = api_base or provider_config.api_base
            model = model or provider_config.embedding_model or model
        
        super().__init__(
            provider_name=provider_name,
            api_key=api_key,
            api_base=api_base or "https://api.openai.com/v1",
            model=model,
            **kwargs
        )
        
        # 初始化OpenAI客户端
        self.openai_client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )
    
    @EnterpriseDecorator.with_retry(max_retries=3)
    @EnterpriseDecorator.with_timeout(timeout_seconds=30.0)
    async def create_embedding(
        self,
        input_text: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> EmbeddingResult:
        """创建嵌入向量"""
        
        start_time = time.time()
        model = model or self.model
        
        try:
            # 标准化输入
            if isinstance(input_text, str):
                texts = [input_text]
            else:
                texts = input_text
            
            # 日志记录
            await self.logger.log_request(
                operation="create_embedding",
                request_data={
                    "model": model,
                    "input_count": len(texts),
                    "input_length": sum(len(text) for text in texts)
                },
                response_time=0,
                success=True
            )
            
            # 限流
            await self.rate_limiter.acquire(tokens=sum(len(text) for text in texts))
            
            # 检查缓存
            cache_key = self.cache_manager.generate_key(
                "embedding",
                model=model,
                input_text=input_text
            )
            
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                return EmbeddingResult(**cached_result)
            
            # 调用API
            response = await self.openai_client.embeddings.create(
                model=model,
                input=texts,
                **kwargs
            )
            
            # 处理响应
            embeddings = [data.embedding for data in response.data]
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            response_time = time.time() - start_time
            
            result = EmbeddingResult(
                embeddings=embeddings,
                usage=usage,
                model=model,
                response_time=response_time
            )
            
            # 缓存结果
            await self.cache_manager.set(
                cache_key,
                result.__dict__,
                ttl=3600  # 1小时
            )
            
            # 更新统计
            self._total_requests += 1
            self._successful_requests += 1
            self._total_tokens += usage["total_tokens"]
            
            # 性能监控
            await self.performance_monitor.record_latency(
                operation="embedding",
                latency=response_time
            )
            
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            self._failed_requests += 1
            
            # 错误日志
            await self.logger.log_request(
                operation="create_embedding",
                request_data={
                    "model": model,
                    "input_count": len(texts) if 'texts' in locals() else 0
                },
                response_time=response_time,
                success=False,
                error=str(e)
            )
            
            raise
    
    async def batch_create_embedding(
        self,
        input_texts: List[str],
        model: Optional[str] = None,
        batch_size: int = 100,
        **kwargs
    ) -> List[EmbeddingResult]:
        """批量创建嵌入向量"""
        
        results = []
        
        # 分批处理
        for i in range(0, len(input_texts), batch_size):
            batch = input_texts[i:i + batch_size]
            result = await self.create_embedding(
                input_text=batch,
                model=model,
                **kwargs
            )
            results.append(result)
        
        return results
    
    async def _make_request(self, **kwargs) -> Any:
        """实现基类抽象方法"""
        return await self.create_embedding(**kwargs)
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 测试简单的嵌入请求
            test_result = await self.create_embedding("test")
            return {
                "status": "healthy",
                "model": self.model,
                "embedding_dim": len(test_result.embeddings[0]) if test_result.embeddings else 0,
                "response_time": test_result.response_time
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "provider_name": self.provider_name,
            "model": self.model,
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "total_tokens": self._total_tokens,
            "success_rate": (
                self._successful_requests / self._total_requests
                if self._total_requests > 0 else 0
            )
        }

# 工厂函数
def create_enterprise_embedding_provider(
    provider_name: str = "openai",
    **kwargs
) -> EnterpriseEmbeddingProvider:
    """创建企业级嵌入提供者"""
    return EnterpriseEmbeddingProvider(
        provider_name=provider_name,
        **kwargs
    )

# 预定义的提供者配置
EMBEDDING_PROVIDERS = {
    "openai": {
        "class": EnterpriseEmbeddingProvider,
        "default_model": "text-embedding-3-small"
    },
    "openai-large": {
        "class": EnterpriseEmbeddingProvider,
        "default_model": "text-embedding-3-large"
    }
}

async def get_embeddings_from_api(
    texts: List[str],
    user_id: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs
) -> List[List[float]]:
    """
    获取文本的嵌入向量
    
    Args:
        texts: 要嵌入的文本列表
        user_id: 用户ID（可选）
        provider: 提供者名称（可选）
        api_key: API密钥（可选）
        **kwargs: 其他参数
        
    Returns:
        嵌入向量列表
    """
    try:
        # 创建嵌入提供者
        embedding_provider = create_enterprise_embedding_provider(
            provider_name=provider or "openai",
            api_key=api_key
        )
        
        # 获取嵌入
        result = await embedding_provider.get_embeddings(texts)
        
        if result and hasattr(result, 'embeddings'):
            return result.embeddings
        else:
            # 返回零向量
            from .ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
            return [GLOBAL_PLACEHOLDER_ZERO_VECTOR] * len(texts)
            
    except Exception as e:
        # 出错时返回零向量
        from .ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
        return [GLOBAL_PLACEHOLDER_ZERO_VECTOR] * len(texts)

# 向后兼容的别名
create_embedding_provider = create_enterprise_embedding_provider

__all__ = [
    "EnterpriseEmbeddingProvider",
    "EmbeddingResult", 
    "create_enterprise_embedding_provider",
    "create_embedding_provider",
    "EMBEDDING_PROVIDERS",
    "get_embeddings_from_api"
]
