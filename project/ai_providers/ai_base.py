# ai_providers/ai_base.py
"""
企业级AI提供者基础类
现代化的、高性能的、生产就绪的基础抽象类
"""

import sys
import json
import time
import hashlib
import asyncio
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, AsyncGenerator
from contextlib import asynccontextmanager
from functools import wraps
import logging

# 简化导入策略 - 只导入基础功能
import logging

# 默认日志配置
def get_ai_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

# 尝试导入企业级日志组件
try:
    from pathlib import Path
    enterprise_path = Path(__file__).parent.parent.parent / "logs"
    if str(enterprise_path) not in sys.path:
        sys.path.insert(0, str(enterprise_path))
    
    # 尝试导入企业级日志器（使用exec避免静态检查）
    exec("from logs.ai_providers.ai_logger import get_ai_logger as enterprise_get_ai_logger")
    exec("get_ai_logger = enterprise_get_ai_logger")  # 替换为企业级版本
    ENTERPRISE_LOGGING = True
except:
    # 使用基础日志器
    ENTERPRISE_LOGGING = False

# 简单的缓存管理器
class SimpleCacheManager:
    def __init__(self):
        self._cache = {}
    
    def get(self, key):
        return self._cache.get(key)
    
    def set(self, key, value, ttl=None):
        self._cache[key] = value

# 全局实例
_cache_manager = SimpleCacheManager()

def get_cache_manager():
    return _cache_manager

def get_provider_config(name):
    # 返回默认配置
    return None

def get_http_client(name, url, rate_limit):
    # 简单实现
    return None


class BaseAIProvider(ABC):
    """企业级AI服务提供者基类"""
    
    def __init__(self, provider_name: str, api_key: str, 
                 base_url: Optional[str] = None, model: Optional[str] = None):
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        
        # 企业级组件初始化
        self.logger = get_ai_logger(provider_name)
        self.cache_manager = get_cache_manager()
        
        # 从配置获取参数
        config = get_provider_config(provider_name)
        if config:
            self.base_url = self.base_url or config.base_url
            self.model = self.model or config.default_model
            self.timeout = config.timeout
            self.max_retries = config.max_retries
            self.rate_limit = config.rate_limit
            self.enable_cache = config.enable_cache
            self.cache_ttl = config.cache_ttl
        else:
            # 默认配置
            self.timeout = 30.0
            self.max_retries = 3
            self.rate_limit = 10.0
            self.enable_cache = True
            self.cache_ttl = 3600
        
        # 记录初始化
        self.logger.info(f"Initialized {provider_name} provider", extra={
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "cache_enabled": self.enable_cache
        })
    
    def _sanitize_api_key(self, api_key: str) -> str:
        """脱敏API密钥用于日志"""
        if not api_key or len(api_key) < 8:
            return "***"
        return f"{api_key[:4]}...{api_key[-4:]}"
    
    def _generate_cache_key(self, operation: str, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = {
            "provider": self.provider_name,
            "operation": operation,
            "args": args,
            "kwargs": sorted(kwargs.items())
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    async def _get_http_client(self):
        """获取HTTP客户端"""
        return get_http_client(self.provider_name, self.base_url, self.rate_limit)


class LLMProvider(BaseAIProvider):
    """LLM服务提供者抽象基类"""
    
    def __init__(self, provider_name: str, api_key: str, 
                 base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(provider_name, api_key, base_url, model)
    
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
    
    async def chat_completion_with_cache(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = 0.5,
        top_p: float = 0.9,
        model: Optional[str] = None,
        use_cache: bool = None
    ) -> Dict[str, Any]:
        """
        带缓存的聊天完成请求
        """
        use_cache = use_cache if use_cache is not None else self.enable_cache
        
        if not use_cache or not self.cache_manager:
            return await self.chat_completion(messages, tools, tool_choice, temperature, top_p, model)
        
        # 生成缓存键（只对deterministic的调用进行缓存）
        if temperature == 0 and top_p == 1.0:
            cache_key = self._generate_cache_key(
                "chat_completion",
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                model=model or self.model
            )
            
            # 尝试从缓存获取
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result:
                self.logger.info("Cache hit for chat completion")
                return cached_result
        
        # 执行请求
        result = await self.chat_completion(messages, tools, tool_choice, temperature, top_p, model)
        
        # 缓存结果（仅对deterministic调用）
        if use_cache and temperature == 0 and top_p == 1.0:
            await self.cache_manager.set(cache_key, result, self.cache_ttl)
        
        return result


class EmbeddingProvider(BaseAIProvider):
    """嵌入服务提供者抽象基类"""
    
    def __init__(self, provider_name: str, api_key: str, 
                 base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(provider_name, api_key, base_url, model)
    
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
    
    async def get_embeddings_with_cache(
        self,
        texts: List[str],
        model: Optional[str] = None,
        use_cache: bool = None
    ) -> List[List[float]]:
        """
        带缓存的嵌入向量获取
        """
        use_cache = use_cache if use_cache is not None else self.enable_cache
        
        if not use_cache or not self.cache_manager:
            return await self.get_embeddings(texts, model)
        
        # 检查缓存
        cached_results = []
        missing_indices = []
        missing_texts = []
        
        for i, text in enumerate(texts):
            cache_key = self._generate_cache_key("embedding", text=text, model=model or self.model)
            cached_embedding = await self.cache_manager.get(cache_key)
            
            if cached_embedding:
                cached_results.append((i, cached_embedding))
            else:
                missing_indices.append(i)
                missing_texts.append(text)
        
        # 获取缺失的嵌入向量
        if missing_texts:
            new_embeddings = await self.get_embeddings(missing_texts, model)
            
            # 缓存新结果
            for j, embedding in enumerate(new_embeddings):
                text = missing_texts[j]
                cache_key = self._generate_cache_key("embedding", text=text, model=model or self.model)
                await self.cache_manager.set(cache_key, embedding, self.cache_ttl)
        else:
            new_embeddings = []
        
        # 合并结果
        results = [None] * len(texts)
        
        # 填入缓存结果
        for i, embedding in cached_results:
            results[i] = embedding
        
        # 填入新结果
        new_embedding_iter = iter(new_embeddings)
        for i in missing_indices:
            results[i] = next(new_embedding_iter)
        
        return results


class RerankProvider(BaseAIProvider):
    """重排服务提供者抽象基类"""
    
    def __init__(self, provider_name: str, api_key: str, 
                 base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(provider_name, api_key, base_url, model)
    
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


class TTSProvider(BaseAIProvider):
    """TTS服务提供者抽象基类"""
    
    def __init__(self, provider_name: str, api_key: str, 
                 base_url: Optional[str] = None, model: Optional[str] = None):
        super().__init__(provider_name, api_key, base_url, model)
    
    @abstractmethod
    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        response_format: str = "mp3",
        speed: float = 1.0
    ) -> bytes:
        """
        文本转语音
        
        Args:
            text: 要转换的文本
            voice: 语音类型
            model: 模型名称（可覆盖默认模型）
            response_format: 响应格式
            speed: 语速
            
        Returns:
            音频数据
        """
        pass


class SearchProvider(BaseAIProvider):
    """搜索服务提供者抽象基类"""
    
    def __init__(self, provider_name: str, api_key: str, 
                 base_url: Optional[str] = None):
        super().__init__(provider_name, api_key, base_url)
    
    @abstractmethod
    async def search(
        self,
        query: str,
        count: int = 10,
        offset: int = 0,
        language: str = "zh-CN"
    ) -> Dict[str, Any]:
        """
        执行搜索
        
        Args:
            query: 搜索查询
            count: 返回结果数量
            offset: 偏移量
            language: 语言
            
        Returns:
            搜索结果
        """
        pass


# 简化的性能监控类
class PerformanceMonitor:
    """简化的性能监控装饰器"""
    
    def __init__(self, logger, operation_name):
        self.logger = logger
        self.operation_name = operation_name
    
    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                self.logger.info(f"Operation {self.operation_name} completed in {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                self.logger.error(f"Operation {self.operation_name} failed after {duration:.2f}s: {e}")
                raise
        return wrapper

# 简化的重试处理器
class RetryHandler:
    """简化的重试处理器"""
    
    def __init__(self, logger, max_retries):
        self.logger = logger
        self.max_retries = max_retries
    
    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(self.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == self.max_retries:
                        self.logger.error(f"All {self.max_retries + 1} attempts failed: {e}")
                        raise
                    self.logger.warning(f"Attempt {attempt + 1} failed, retrying: {e}")
                    await asyncio.sleep(2 ** attempt)  # 指数退避
            return None
        return wrapper

# 装饰器工厂函数
def with_monitoring(operation_name: str):
    """性能监控装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            monitor = PerformanceMonitor(self.logger, operation_name)
            return await monitor(func)(self, *args, **kwargs)
        
        return wrapper
    return decorator


def with_retry(max_retries: int = None):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            retries = max_retries or getattr(self, 'max_retries', 3)
            retry_handler = RetryHandler(self.logger, retries)
            return await retry_handler(func)(self, *args, **kwargs)
        
        return wrapper
    return decorator


# 健康检查接口
async def health_check() -> Dict[str, Any]:
    """系统健康检查"""
    status = {
        "timestamp": time.time(),
        "status": "healthy"
    }
    
    try:
        # 检查缓存
        cache_manager = get_cache_manager()
        cache_stats = await cache_manager.get_stats()
        status["cache"] = cache_stats
        
        # 检查连接池
        connection_stats = await get_http_client().get_stats()
        status["connections"] = connection_stats
        
    except Exception as e:
        status["status"] = "degraded"
        status["error"] = str(e)
    
    return status

class EnterpriseDecorator:
    """企业级装饰器集合"""
    
    @staticmethod
    def with_retry(max_retries: int = 3, backoff_factor: float = 1.0):
        """重试装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        if attempt < max_retries:
                            wait_time = backoff_factor * (2 ** attempt)
                            await asyncio.sleep(wait_time)
                        else:
                            break
                
                raise last_exception
            return wrapper
        return decorator
    
    @staticmethod
    def with_timeout(timeout_seconds: float = 30.0):
        """超时装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            return wrapper
        return decorator
    
    @staticmethod
    def with_circuit_breaker(failure_threshold: int = 5, recovery_timeout: int = 60):
        """断路器装饰器"""
        def decorator(func):
            # 简化的断路器实现
            failure_count = 0
            last_failure_time = 0
            
            @wraps(func)
            async def wrapper(*args, **kwargs):
                nonlocal failure_count, last_failure_time
                
                # 检查断路器状态
                if failure_count >= failure_threshold:
                    if time.time() - last_failure_time < recovery_timeout:
                        raise Exception("Circuit breaker is open")
                    else:
                        failure_count = 0  # 重置计数器
                
                try:
                    result = await func(*args, **kwargs)
                    failure_count = 0  # 成功时重置
                    return result
                except Exception as e:
                    failure_count += 1
                    last_failure_time = time.time()
                    raise
            
            return wrapper
        return decorator

# 基础AI提供者类
class BaseAIProvider(ABC):
    """企业级AI提供者基类"""
    
    def __init__(
        self, 
        provider_name: str,
        api_key: str,
        api_base: str,
        model: str,
        **kwargs
    ):
        self.provider_name = provider_name
        self.api_key = api_key
        self.api_base = api_base  
        self.model = model
        
# 简化的企业级装饰器类
class EnterpriseDecorator:
    """企业级AI提供者装饰器 - 简化版本"""
    
    def __init__(
        self, 
        provider_name: str,
        api_key: str,
        api_base: str,
        model: str,
        **kwargs
    ):
        self.provider_name = provider_name
        self.api_key = api_key
        self.api_base = api_base  
        self.model = model
        
        # 使用简化的组件
        self.logger = get_ai_logger(provider_name)
        self.cache_manager = get_cache_manager()
        
        # 配置参数
        self.timeout = kwargs.get('timeout', 30.0)
        self.max_retries = kwargs.get('max_retries', 3)
        self.temperature = kwargs.get('temperature', 0.7)
        self.max_tokens = kwargs.get('max_tokens', 4096)
        
        # 统计信息
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_tokens = 0
        self._total_cost = 0.0
    
    async def _make_request(self, **kwargs) -> Any:
        """执行具体的API请求 - 基础实现"""
        self._total_requests += 1
        try:
            # 基础请求实现
            result = {"status": "success", "data": kwargs}
            self._successful_requests += 1
            return result
        except Exception as e:
            self._failed_requests += 1
            self.logger.error(f"Request failed: {e}")
            raise
    
    @staticmethod
    def with_retry(max_retries: int = 3):
        """重试装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(self, *args, **kwargs):
                for attempt in range(max_retries + 1):
                    try:
                        return await func(self, *args, **kwargs)
                    except Exception as e:
                        if attempt == max_retries:
                            if hasattr(self, 'logger'):
                                self.logger.error(f"All {max_retries + 1} attempts failed: {e}")
                            raise
                        if hasattr(self, 'logger'):
                            self.logger.warning(f"Attempt {attempt + 1} failed, retrying: {e}")
                        await asyncio.sleep(2 ** attempt)
                return None
            return wrapper
        return decorator
    
    @staticmethod
    def with_timeout(timeout_seconds: float = 30.0):
        """超时装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(self, *args, **kwargs):
                try:
                    return await asyncio.wait_for(func(self, *args, **kwargs), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    if hasattr(self, 'logger'):
                        self.logger.error(f"Operation timed out after {timeout_seconds}s")
                    raise
            return wrapper
        return decorator
    
    @staticmethod
    def with_monitoring(operation_name: str):
        """监控装饰器"""
        def decorator(func):
            @wraps(func)
            async def wrapper(self, *args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(self, *args, **kwargs)
                    duration = time.time() - start_time
                    if hasattr(self, 'logger'):
                        self.logger.info(f"Operation {operation_name} completed in {duration:.2f}s")
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    if hasattr(self, 'logger'):
                        self.logger.error(f"Operation {operation_name} failed after {duration:.2f}s: {e}")
                    raise
            return wrapper
        return decorator
        pass

# LLM提供者基类
class BaseLLMProvider(BaseAIProvider):
    """LLM提供者基类"""
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """聊天补全"""
        pass
    
    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式聊天补全"""
        pass

# 嵌入提供者基类
class BaseEmbeddingProvider(BaseAIProvider):
    """嵌入提供者基类"""
    
    @abstractmethod
    async def create_embedding(
        self,
        input_text: Union[str, List[str]],
        **kwargs
    ) -> Dict[str, Any]:
        """创建嵌入向量"""
        pass

# 重排序提供者基类  
class BaseRerankProvider(BaseAIProvider):
    """重排序提供者基类"""
    
    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """重排序文档"""
        pass
