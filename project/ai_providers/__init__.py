"""
AI Providers - 企业级AI服务提供者模块
统一的、高性能的、生产就绪的AI服务接口
"""

import sys
import os
from pathlib import Path

# 添加企业级组件路径
enterprise_path = Path(__file__).parent.parent.parent / "logs"
if str(enterprise_path) not in sys.path:
    sys.path.insert(0, str(enterprise_path))

# 简化的企业级功能检查
ENTERPRISE_FEATURES = False
try:
    # 尝试导入企业级组件
    import sys
    from pathlib import Path
    
    enterprise_path = Path(__file__).parent.parent.parent / "logs"
    if str(enterprise_path) not in sys.path:
        sys.path.insert(0, str(enterprise_path))
    
    # 尝试导入企业级日志器（静默失败）
    exec("from logs.ai_providers.ai_logger import get_ai_logger")
    ENTERPRISE_FEATURES = True
    print("Enterprise logging features available")
except:
    # 静默失败，使用基础功能
    print("Using basic features (enterprise components not available)")
    ENTERPRISE_FEATURES = False

# 基础组件
try:
    from .ai_base import BaseAIProvider, EnterpriseDecorator
    print("Base AI provider components loaded successfully")
except ImportError as e:
    print(f"Warning: Cannot import base AI provider: {e}")
    BaseAIProvider = None
    EnterpriseDecorator = None

# 配置组件
try:
    from .ai_config import EnterpriseConfig, get_enterprise_config
except ImportError as e:
    print(f"Info: AI config not available (this is optional): {e}")
    EnterpriseConfig = None
    get_enterprise_config = None

# LLM提供者
try:
    from .llm_provider import (
        OpenAIProvider,
        CustomOpenAIProvider,
        HttpxLLMProvider
    )
    print("LLM providers loaded successfully")
except ImportError as e:
    print(f"Info: LLM providers not fully available (this is optional): {e}")

# 嵌入和重排序提供者
try:
    from .embedding_provider import EnterpriseEmbeddingProvider
    from .rerank_provider import EnterpriseRerankProvider
except ImportError as e:
    print(f"Info: Embedding/Rerank providers not available (this is optional): {e}")

# 工厂和管理器
try:
    from .provider_factory import AIProviderFactory
    from .provider_manager import AIProviderManager
    print("Factory and manager components loaded successfully")
except ImportError as e:
    print(f"Info: Factory/Manager not available (this is optional): {e}")

# 导出主要组件
__all__ = [
    'BaseAIProvider', 
    'EnterpriseDecorator',
    'ENTERPRISE_FEATURES'
]

# 条件导出
if BaseAIProvider is not None:
    __all__.extend(['BaseAIProvider', 'EnterpriseDecorator'])

print(f"AI Providers module loaded. Enterprise features: {ENTERPRISE_FEATURES}")
print(f"Available components: {[name for name in __all__ if globals().get(name) is not None]}")

# 监控和健康检查
try:
    from logs.ai_providers.ai_logger import get_performance_stats, get_health_status
except ImportError:
    def get_performance_stats():
        return {}
    def get_health_status():
        return {"status": "unknown"}

__version__ = "2.0.0"

# 全局单例管理器
_provider_manager = None

def get_provider_manager() -> AIProviderManager:
    """获取全局AI提供者管理器"""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = AIProviderManager()
    return _provider_manager

def get_llm_provider(provider_name: str = "openai", **kwargs):
    """获取LLM提供者实例"""
    return get_provider_manager().get_llm_provider(provider_name, **kwargs)

def get_embedding_provider(provider_name: str = "openai", **kwargs):
    """获取嵌入提供者实例"""
    return get_provider_manager().get_embedding_provider(provider_name, **kwargs)

def get_rerank_provider(provider_name: str = "cohere", **kwargs):
    """获取重排序提供者实例"""
    return get_provider_manager().get_rerank_provider(provider_name, **kwargs)

# 快速启动函数
def initialize_enterprise_ai(config_path: str = None):
    """初始化企业级AI系统"""
    manager = get_provider_manager()
    return manager.initialize(config_path)

__all__ = [
    # 版本信息
    '__version__',
    
    # 核心组件
    'BaseAIProvider',
    'EnterpriseDecorator', 
    'EnterpriseConfig',
    
    # LLM提供者
    'OpenAIProvider',
    'CustomOpenAIProvider',
    'HttpxLLMProvider',
    
    # 其他提供者
    'EnterpriseEmbeddingProvider',
    'EnterpriseRerankProvider',
    
    # 管理组件
    'AIProviderFactory',
    'AIProviderManager',
    
    # 便捷函数
    'get_provider_manager',
    'get_llm_provider',
    'get_embedding_provider', 
    'get_rerank_provider',
    'initialize_enterprise_ai',
    
    # 监控函数
    'get_performance_stats',
    'get_health_status'
]
