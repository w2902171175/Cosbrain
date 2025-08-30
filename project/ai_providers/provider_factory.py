"""
AI提供者工厂
统一创建和管理各种AI提供者实例
"""

from typing import Dict, Any, Optional, Type, List
from .llm_provider import OpenAIProvider, CustomOpenAIProvider, HttpxLLMProvider
from .embedding_provider import EnterpriseEmbeddingProvider
from .rerank_provider import EnterpriseRerankProvider
from .ai_config import get_enterprise_config
from .ai_base import LLMProvider

class AIProviderFactory:
    """AI提供者工厂类"""
    
    def __init__(self):
        self.config = get_enterprise_config()
        
        # 注册LLM提供者
        self._llm_providers = {
            "openai": OpenAIProvider,
            "deepseek": CustomOpenAIProvider,
            "siliconflow": CustomOpenAIProvider,
            "zhipu": CustomOpenAIProvider,
            "kimi": CustomOpenAIProvider
        }
        
        # 注册嵌入提供者
        self._embedding_providers = {
            "openai": EnterpriseEmbeddingProvider,
            "zhipu": EnterpriseEmbeddingProvider
        }
        
        # 注册重排序提供者
        self._rerank_providers = {
            "cohere": EnterpriseRerankProvider
        }
    
    def create_llm_provider(self, provider_name: str, **kwargs) -> LLMProvider:
        """创建LLM提供者实例"""
        if provider_name not in self._llm_providers:
            raise ValueError(f"Unsupported LLM provider: {provider_name}")
        
        provider_class = self._llm_providers[provider_name]
        
        if provider_name == "openai":
            return provider_class(**kwargs)
        else:
            return provider_class(provider_name, **kwargs)
    
    def create_embedding_provider(self, provider_name: str, **kwargs) -> EnterpriseEmbeddingProvider:
        """创建嵌入提供者实例"""
        if provider_name not in self._embedding_providers:
            raise ValueError(f"Unsupported embedding provider: {provider_name}")
        
        provider_class = self._embedding_providers[provider_name]
        return provider_class(provider_name, **kwargs)
    
    def create_rerank_provider(self, provider_name: str, **kwargs) -> EnterpriseRerankProvider:
        """创建重排序提供者实例"""
        if provider_name not in self._rerank_providers:
            raise ValueError(f"Unsupported rerank provider: {provider_name}")
        
        provider_class = self._rerank_providers[provider_name]
        return provider_class(provider_name, **kwargs)
    
    def get_available_llm_providers(self) -> List[str]:
        """获取可用的LLM提供者列表"""
        return self.config.get_available_providers()
    
    def get_available_embedding_providers(self) -> List[str]:
        """获取可用的嵌入提供者列表"""
        return [name for name in self._embedding_providers.keys() 
                if self.config.get_embedding_config(name) and 
                self.config.get_embedding_config(name).api_key]
    
    def get_available_rerank_providers(self) -> List[str]:
        """获取可用的重排序提供者列表"""
        return [name for name in self._rerank_providers.keys() 
                if self.config.get_rerank_config(name) and 
                self.config.get_rerank_config(name).api_key]
    
    def register_llm_provider(self, name: str, provider_class: Type[LLMProvider]):
        """注册新的LLM提供者"""
        self._llm_providers[name] = provider_class
    
    def register_embedding_provider(self, name: str, provider_class: Type[EnterpriseEmbeddingProvider]):
        """注册新的嵌入提供者"""
        self._embedding_providers[name] = provider_class
    
    def register_rerank_provider(self, name: str, provider_class: Type[EnterpriseRerankProvider]):
        """注册新的重排序提供者"""
        self._rerank_providers[name] = provider_class

# 全局工厂实例
_factory = None

def get_ai_provider_factory() -> AIProviderFactory:
    """获取全局AI提供者工厂实例"""
    global _factory
    if _factory is None:
        _factory = AIProviderFactory()
    return _factory
