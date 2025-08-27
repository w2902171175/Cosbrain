# ai_providers/ai_base.py
"""
AI服务提供者的抽象基类
定义了各种AI服务的统一接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class LLMProvider(ABC):
    """LLM服务提供者抽象基类"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行聊天完成请求
        
        Args:
            messages: 消息列表
            tools: 可用工具列表
            tool_choice: 工具选择策略
            temperature: 温度参数
            top_p: top_p参数
            model: 模型名称（可覆盖默认模型）
            
        Returns:
            聊天完成响应
        """
        pass


class EmbeddingProvider(ABC):
    """嵌入服务提供者抽象基类"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    @abstractmethod
    async def get_embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None
    ) -> List[List[float]]:
        """
        获取文本嵌入向量
        
        Args:
            texts: 文本列表
            model: 模型名称（可覆盖默认模型）
            
        Returns:
            嵌入向量列表
        """
        pass


class RerankProvider(ABC):
    """重排服务提供者抽象基类"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        model: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        对文档进行重排
        
        Args:
            query: 查询文本
            documents: 文档列表
            model: 模型名称（可覆盖默认模型）
            top_k: 返回的文档数量
            
        Returns:
            重排后的文档列表，包含分数信息
        """
        pass


class TTSProvider(ABC):
    """TTS服务提供者抽象基类"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
    
    @abstractmethod
    async def synthesize_speech(
        self,
        text: str,
        voice: str = "alloy",
        model: Optional[str] = None,
        language: str = "zh-CN"
    ) -> bytes:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            voice: 语音类型
            model: 模型名称
            language: 语言代码
            
        Returns:
            音频数据（字节）
        """
        pass


class SearchProvider(ABC):
    """搜索服务提供者抽象基类"""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
    
    @abstractmethod
    async def search(
        self,
        query: str,
        count: int = 10,
        offset: int = 0,
        language: str = "zh-CN"
    ) -> Dict[str, Any]:
        """
        执行网络搜索
        
        Args:
            query: 搜索查询
            count: 返回结果数量
            offset: 偏移量
            language: 语言
            
        Returns:
            搜索结果
        """
        pass


# ===== 工厂函数 =====

def create_llm_provider(provider_type: str, api_config: Dict[str, Any]) -> LLMProvider:
    """创建LLM提供者实例"""
    if provider_type.lower() == "openai":
        from .llm_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=api_config.get("api_key", "dummy"),
            base_url=api_config.get("base_url"),
            model=api_config.get("model")
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_type}")


def create_embedding_provider(provider_type: str, api_config: Dict[str, Any]) -> EmbeddingProvider:
    """创建嵌入提供者实例"""
    if provider_type.lower() == "openai":
        from .embedding_provider import SiliconFlowEmbeddingProvider
        return SiliconFlowEmbeddingProvider(
            api_key=api_config.get("api_key", "dummy"),
            base_url=api_config.get("base_url"),
            model=api_config.get("model")
        )
    else:
        raise ValueError(f"Unsupported embedding provider: {provider_type}")


def create_rerank_provider(provider_type: str, api_config: Dict[str, Any]) -> RerankProvider:
    """创建重排序提供者实例"""
    if provider_type.lower() == "openai":
        from .rerank_provider import SiliconFlowRerankProvider
        return SiliconFlowRerankProvider(
            api_key=api_config.get("api_key", "dummy"),
            base_url=api_config.get("base_url"),
            model=api_config.get("model")
        )
    else:
        raise ValueError(f"Unsupported rerank provider: {provider_type}")


def create_tts_provider(provider_type: str, api_config: Dict[str, Any]) -> TTSProvider:
    """创建TTS提供者实例"""
    if provider_type.lower() == "openai":
        from .tts_provider import OpenAITTSProvider
        return OpenAITTSProvider(
            api_key=api_config.get("api_key", "dummy"),
            base_url=api_config.get("base_url"),
            model=api_config.get("model")
        )
    else:
        raise ValueError(f"Unsupported TTS provider: {provider_type}")


def create_search_provider(provider_type: str, api_config: Dict[str, Any]) -> SearchProvider:
    """创建搜索提供者实例"""
    if provider_type.lower() == "google":
        from .search_provider import GoogleSearchProvider
        return GoogleSearchProvider(
            api_key=api_config.get("api_key", "dummy"),
            engine_id=api_config.get("engine_id", "dummy")
        )
    else:
        raise ValueError(f"Unsupported search provider: {provider_type}")
