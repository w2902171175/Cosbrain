"""
AI提供者管理器
统一管理所有AI提供者实例，提供负载均衡、故障转移等功能
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
from .provider_factory import get_ai_provider_factory, AIProviderFactory
from .llm_provider import OpenAIProvider
from .embedding_provider import EnterpriseEmbeddingProvider
from .rerank_provider import EnterpriseRerankProvider
from .ai_config import get_enterprise_config
from .ai_base import LLMProvider

class AIProviderManager:
    """AI提供者管理器"""
    
    def __init__(self):
        self.factory = get_ai_provider_factory()
        self.config = get_enterprise_config()
        
        # 提供者实例缓存
        self._llm_providers: Dict[str, LLMProvider] = {}
        self._embedding_providers: Dict[str, EnterpriseEmbeddingProvider] = {}
        self._rerank_providers: Dict[str, EnterpriseRerankProvider] = {}
        
        # 健康状态跟踪
        self._provider_health: Dict[str, Dict[str, Any]] = {}
        
        # 负载均衡轮询索引
        self._llm_round_robin_index = 0
        
        # 初始化标志
        self._initialized = False
    
    async def initialize(self, config_path: Optional[str] = None) -> bool:
        """初始化管理器"""
        if self._initialized:
            return True
        
        try:
            # 初始化可用的提供者
            await self._initialize_providers()
            
            # 启动健康检查
            asyncio.create_task(self._health_check_loop())
            
            self._initialized = True
            return True
            
        except Exception as e:
            print(f"Failed to initialize AI Provider Manager: {e}")
            return False
    
    async def _initialize_providers(self):
        """初始化所有可用的提供者"""
        # 初始化LLM提供者
        for provider_name in self.factory.get_available_llm_providers():
            try:
                provider = self.factory.create_llm_provider(provider_name)
                self._llm_providers[provider_name] = provider
                self._provider_health[provider_name] = {"status": "unknown", "last_check": 0}
            except Exception as e:
                print(f"Failed to initialize LLM provider {provider_name}: {e}")
        
        # 初始化嵌入提供者
        for provider_name in self.factory.get_available_embedding_providers():
            try:
                provider = self.factory.create_embedding_provider(provider_name)
                self._embedding_providers[provider_name] = provider
                self._provider_health[f"embedding_{provider_name}"] = {"status": "unknown", "last_check": 0}
            except Exception as e:
                print(f"Failed to initialize embedding provider {provider_name}: {e}")
        
        # 初始化重排序提供者
        for provider_name in self.factory.get_available_rerank_providers():
            try:
                provider = self.factory.create_rerank_provider(provider_name)
                self._rerank_providers[provider_name] = provider
                self._provider_health[f"rerank_{provider_name}"] = {"status": "unknown", "last_check": 0}
            except Exception as e:
                print(f"Failed to initialize rerank provider {provider_name}: {e}")
    
    def get_llm_provider(self, provider_name: Optional[str] = None, **kwargs) -> LLMProvider:
        """获取LLM提供者实例"""
        if not self._initialized:
            raise RuntimeError("Provider manager not initialized")
        
        if provider_name:
            # 返回指定的提供者
            if provider_name not in self._llm_providers:
                raise ValueError(f"LLM provider {provider_name} not available")
            return self._llm_providers[provider_name]
        else:
            # 负载均衡选择提供者
            return self._get_best_llm_provider()
    
    def get_embedding_provider(self, provider_name: Optional[str] = None, **kwargs) -> EnterpriseEmbeddingProvider:
        """获取嵌入提供者实例"""
        if not self._initialized:
            raise RuntimeError("Provider manager not initialized")
        
        provider_name = provider_name or "openai"  # 默认使用OpenAI
        
        if provider_name not in self._embedding_providers:
            raise ValueError(f"Embedding provider {provider_name} not available")
        
        return self._embedding_providers[provider_name]
    
    def get_rerank_provider(self, provider_name: Optional[str] = None, **kwargs) -> EnterpriseRerankProvider:
        """获取重排序提供者实例"""
        if not self._initialized:
            raise RuntimeError("Provider manager not initialized")
        
        provider_name = provider_name or "cohere"  # 默认使用Cohere
        
        if provider_name not in self._rerank_providers:
            raise ValueError(f"Rerank provider {provider_name} not available")
        
        return self._rerank_providers[provider_name]
    
    def _get_best_llm_provider(self) -> LLMProvider:
        """选择最佳的LLM提供者（负载均衡 + 健康检查）"""
        healthy_providers = []
        
        # 筛选健康的提供者
        for name, provider in self._llm_providers.items():
            health = self._provider_health.get(name, {})
            if health.get("status") == "healthy":
                healthy_providers.append((name, provider))
        
        if not healthy_providers:
            # 如果没有健康的提供者，返回按优先级排序的第一个
            available_providers = list(self._llm_providers.items())
            if not available_providers:
                raise RuntimeError("No LLM providers available")
            return available_providers[0][1]
        
        # 轮询选择
        self._llm_round_robin_index = (self._llm_round_robin_index + 1) % len(healthy_providers)
        return healthy_providers[self._llm_round_robin_index][1]
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await self._check_all_providers_health()
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                print(f"Health check error: {e}")
                await asyncio.sleep(30)  # 出错时30秒后重试
    
    async def _check_all_providers_health(self):
        """检查所有提供者的健康状态"""
        tasks = []
        
        # 检查LLM提供者
        for name, provider in self._llm_providers.items():
            task = self._check_provider_health(name, provider)
            tasks.append(task)
        
        # 检查嵌入提供者
        for name, provider in self._embedding_providers.items():
            task = self._check_provider_health(f"embedding_{name}", provider)
            tasks.append(task)
        
        # 检查重排序提供者
        for name, provider in self._rerank_providers.items():
            task = self._check_provider_health(f"rerank_{name}", provider)
            tasks.append(task)
        
        # 并发执行健康检查
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _check_provider_health(self, provider_key: str, provider):
        """检查单个提供者的健康状态"""
        try:
            health_result = await provider.health_check()
            self._provider_health[provider_key] = {
                "status": health_result.get("status", "unknown"),
                "last_check": time.time(),
                "response_time": health_result.get("response_time", 0),
                "error": health_result.get("error")
            }
        except Exception as e:
            self._provider_health[provider_key] = {
                "status": "unhealthy",
                "last_check": time.time(),
                "error": str(e)
            }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取所有提供者的健康状态"""
        return {
            "initialized": self._initialized,
            "providers": dict(self._provider_health),
            "last_update": time.time()
        }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        stats = {
            "llm_providers": {},
            "embedding_providers": {},
            "rerank_providers": {}
        }
        
        # LLM提供者统计
        for name, provider in self._llm_providers.items():
            stats["llm_providers"][name] = provider.get_stats()
        
        # 嵌入提供者统计
        for name, provider in self._embedding_providers.items():
            stats["embedding_providers"][name] = provider.get_stats()
        
        # 重排序提供者统计
        for name, provider in self._rerank_providers.items():
            stats["rerank_providers"][name] = provider.get_stats()
        
        return stats
    
    async def batch_chat_completion(
        self,
        batch_requests: List[Dict[str, Any]],
        provider_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """批量聊天补全"""
        provider = self.get_llm_provider(provider_name)
        
        # 如果提供者支持批量处理
        if hasattr(provider, 'batch_chat_completion'):
            messages_list = [req["messages"] for req in batch_requests]
            return await provider.batch_chat_completion(messages_list)
        else:
            # 并发处理
            tasks = []
            for request in batch_requests:
                task = provider.chat_completion(**request)
                tasks.append(task)
            
            return await asyncio.gather(*tasks, return_exceptions=True)

# 全局管理器实例
_manager = None

def get_ai_provider_manager() -> AIProviderManager:
    """获取全局AI提供者管理器实例"""
    global _manager
    if _manager is None:
        _manager = AIProviderManager()
    return _manager
