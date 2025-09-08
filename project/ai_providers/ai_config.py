# ai_providers/config.py
"""
AI服务配置模块 - 企业级版本
包含所有AI服务的默认配置、API端点、模型列表等常量，支持多环境和热更新
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
import os

# --- 全局常量 ---
INITIAL_CANDIDATES_K = 50
FINAL_TOP_K = 3

# --- 占位符密钥，用于测试或未配置API时 ---
DUMMY_API_KEY = "dummy_key"

# 全局模型初始化占位符（用于确保返回零向量时不报错）
GLOBAL_PLACEHOLDER_ZERO_VECTOR = [0.0] * 1024  # 匹配数据库Vector(1024)维度

# --- 企业级配置类 ---
@dataclass
class ProviderConfig:
    """AI提供者配置"""
    name: str
    api_key: str
    api_base: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 30.0
    max_retries: int = 3
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 90000
    supports_streaming: bool = True
    supports_functions: bool = True
    supports_vision: bool = False
    cost_per_1k_tokens: float = 0.002
    priority: int = 1  # 1=高优先级, 10=低优先级

@dataclass  
class EmbeddingConfig:
    """嵌入模型配置"""
    name: str
    api_key: str
    api_base: str
    model: str
    dimensions: int = 1536
    timeout: float = 30.0
    max_retries: int = 3
    rate_limit_rpm: int = 3000
    cost_per_1k_tokens: float = 0.0001

@dataclass
class RerankConfig:
    """重排序模型配置"""
    name: str
    api_key: str
    api_base: str
    model: str
    max_documents: int = 100
    timeout: float = 30.0
    max_retries: int = 3
    rate_limit_rpm: int = 1000

# --- 通用大模型 API 配置示例 ---
DEFAULT_LLM_API_CONFIG = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "gpt-4o",
        "available_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-5-2025-08-07","gpt-5-mini-2025-08-07","gpt-5-nano-2025-08-07"]
    },
     "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-chat",
        "available_models": ["deepseek-chat", "deepseek-reasoner"]
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "deepseek-ai/DeepSeek-V3",
        "available_models": ["deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-V3","BAAI/bge-m3","BAAI/bge-reranker-v2-m3"]
    },
    "huoshanengine": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_path": "/chat/completions",
        "default_model": "doubao-1-5-thinking-pro-250415",
        "available_models": ["doubao-1-5-thinking-pro-250415", "doubao-1-5-thinking-vision-pro-250428", "kimi-k2-250711"]
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "chat_path": "/chat/completions",
        "default_model": "kimi-k2-0711-preview",
        "available_models": ["kimi-k2-0711-preview", "moonshot-v1-auto"]
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "chat_path": "/chat/completions",
        "default_model": "glm-4.5v",
        "available_models": ["glm-4.5v", "glm-4.5", "glm-4.5-x", "glm-4.5-air", "glm-4-flash"]
    },
    "custom_openai": { # 作为自定义OpenAI兼容服务的模板
            "base_url": None, # 用户必须提供，此处为None表示无默认值
            "chat_path": "/chat/completions", # OpenAI兼容API的标准路径
            "default_model": None, # 用户必须提供，此处为None表示无默认值
            "available_models": ["any_openai_compatible_model"] # 占位符，用户可使用任意模型ID
    }
}

# --- TTS 服务配置常量 ---
DEFAULT_TTS_CONFIGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "tts_path": "/audio/speech",
        "default_model": "gpt-4o-mini-tts",
        "available_models": ["gpt-4o-mini-tts"],
        "default_voice": "alloy",
        "available_voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    },
    "gemini": {
        "notes": "Gemini TTS direct API integration not yet implemented. Requires Google Cloud/Vertex AI TTS API setup."
    },
    "aliyun": {
        "notes": "Aliyun TTS direct API integration not yet implemented. Requires Aliyun SDK/API setup."
    },
    "siliconflow": {
        "notes": "SiliconFlow TTS direct API integration not yet implemented. (假设SiliconFlow有独立的TTS服务而非仅LLM)."
    },
    "default_gtts": {
        "notes": "Default gTTS fallback, no API key needed."
    }
}

# --- 搜索引擎配置 ---
DEFAULT_SEARCH_CONFIGS = {
    "bing": {
        "base_url": "https://api.bing.microsoft.com/v7.0/search",
        "subscription_key_header": "Ocp-Apim-Subscription-Key"
    },
    "tavily": {
        "base_url": "https://api.tavily.com/search",
        "api_key_header": "Api-Key"
    }
}

# --- 嵌入和重排服务配置 ---
DEFAULT_EMBEDDING_CONFIGS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "embeddings_path": "/embeddings",
        "default_model": "BAAI/bge-m3",
        "available_models": ["BAAI/bge-m3", "text-embedding-3-small", "text-embedding-3-large"]
    }
}

DEFAULT_RERANK_CONFIGS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "rerank_path": "/rerank", 
        "default_model": "BAAI/bge-reranker-v2-m3",
        "available_models": ["BAAI/bge-reranker-v2-m3"]
    }
}

def get_available_llm_configs() -> Dict[str, Dict[str, Any]]:
    """获取可用的LLM配置信息"""
    configs = {}
    for llm_type, data in DEFAULT_LLM_API_CONFIG.items():
        configs[llm_type] = {
            "default_model": data["default_model"],
            "available_models": data["available_models"],
            "notes": f"请访问 {data['base_url']} 对应的服务商官网获取API密钥。"
        }
        if llm_type == "custom_openai":
            configs[llm_type]["notes"] = "自定义OpenAI兼容服务：需要提供完整的API基础URL、API密钥和模型ID。"
            configs[llm_type]["default_model"] = None
            configs[llm_type]["available_models"] = ["任意兼容OpenAI API的自定义模型"]
    return configs


# --- 多模型ID处理辅助函数 ---
def parse_llm_model_ids(llm_model_ids_json: Optional[str]) -> Dict[str, List[str]]:
    """
    解析存储在数据库中的 JSON 格式的模型ID配置
    返回: {"服务商类型": ["模型ID1", "模型ID2"]}
    """
    if not llm_model_ids_json:
        return {}
    
    try:
        import json
        parsed = json.loads(llm_model_ids_json)
        if isinstance(parsed, dict):
            # 确保值都是列表格式
            result = {}
            for provider, models in parsed.items():
                if isinstance(models, str):
                    result[provider] = [models]
                elif isinstance(models, list):
                    result[provider] = models
                else:
                    result[provider] = []
            return result
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


def get_user_model_for_provider(llm_model_ids_json: Optional[str], provider: str, fallback_model_id: Optional[str] = None) -> Optional[str]:
    """
    从用户的多模型配置中获取指定服务商的首选模型
    如果没有配置，则使用fallback_model_id或配置中的默认模型
    """
    model_ids_dict = parse_llm_model_ids(llm_model_ids_json)
    
    # 从多模型配置中获取
    provider_models = model_ids_dict.get(provider, [])
    if provider_models:
        return provider_models[0]  # 使用第一个作为默认
    
    # 如果没有配置，尝试使用fallback
    if fallback_model_id:
        return fallback_model_id
        
    # 最后使用系统默认配置
    config = DEFAULT_LLM_API_CONFIG.get(provider)
    if config:
        return config.get("default_model")
    
    return None


def serialize_llm_model_ids(model_ids_dict: Dict[str, List[str]]) -> str:
    """
    将模型ID字典序列化为JSON字符串以存储到数据库
    """
    try:
        import json
        return json.dumps(model_ids_dict, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


# --- 企业级配置管理器 ---
@dataclass
class SecurityConfig:
    """安全配置"""
    encryption_enabled: bool = True
    api_key_encryption: bool = True
    request_signing: bool = False
    allowed_domains: List[str] = field(default_factory=lambda: ["*.openai.com", "*.anthropic.com"])
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    rate_limit_enabled: bool = True
    audit_logging: bool = True

@dataclass
class PerformanceConfig:
    """性能配置"""
    connection_pool_size: int = 100
    connection_pool_maxsize: int = 200
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    cache_enabled: bool = True
    cache_ttl: int = 3600
    cache_max_size: int = 1000
    redis_enabled: bool = False
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    metrics_enabled: bool = True
    health_check_interval: int = 60

@dataclass
class MonitoringConfig:
    """监控配置"""
    prometheus_enabled: bool = True
    prometheus_port: int = 8090
    log_level: str = "INFO"
    structured_logging: bool = True
    performance_tracking: bool = True
    error_tracking: bool = True
    slow_query_threshold: float = 5.0
    alert_on_failures: bool = True
    alert_failure_threshold: int = 5

class EnterpriseConfig:
    """企业级AI提供者配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.providers: Dict[str, ProviderConfig] = {}
        self.embeddings: Dict[str, EmbeddingConfig] = {}
        self.reranks: Dict[str, RerankConfig] = {}
        self.security = SecurityConfig()
        self.performance = PerformanceConfig()
        self.monitoring = MonitoringConfig()
        
        self._load_default_configs()
        self._load_environment_configs()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        return str(Path(__file__).parent.parent.parent / "logs" / "ai_providers" / "config.yaml")
    
    def _load_default_configs(self):
        """加载默认配置"""
        # OpenAI 配置
        self.providers["openai"] = ProviderConfig(
            name="openai",
            api_key=os.getenv("OPENAI_API_KEY", ""),
            api_base="https://api.openai.com/v1",
            model="gpt-4o",
            max_tokens=4096,
            temperature=0.7,
            cost_per_1k_tokens=0.03,
            supports_vision=True,
            priority=1
        )
        
        # DeepSeek 配置
        self.providers["deepseek"] = ProviderConfig(
            name="deepseek",
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            api_base="https://api.deepseek.com",
            model="deepseek-chat",
            max_tokens=4096,
            cost_per_1k_tokens=0.0014,
            priority=2
        )
        
        # SiliconFlow 配置
        self.providers["siliconflow"] = ProviderConfig(
            name="siliconflow",
            api_key=os.getenv("SILICONFLOW_API_KEY", ""),
            api_base="https://api.siliconflow.cn/v1",
            model="Qwen/Qwen2.5-7B-Instruct",
            max_tokens=4096,
            cost_per_1k_tokens=0.0007,
            priority=3
        )
        
        # 嵌入模型配置
        self.embeddings["openai"] = EmbeddingConfig(
            name="openai",
            api_key=os.getenv("OPENAI_API_KEY", ""),
            api_base="https://api.openai.com/v1",
            model="text-embedding-3-large",
            dimensions=3072
        )
    
    def _load_environment_configs(self):
        """从环境变量加载配置"""
        # 性能配置
        if pool_size := os.getenv("AI_PROVIDERS_POOL_SIZE"):
            self.performance.connection_pool_size = int(pool_size)
        
        if timeout := os.getenv("AI_PROVIDERS_TIMEOUT"):
            self.performance.read_timeout = float(timeout)
    
    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        """获取AI提供者配置"""
        return self.providers.get(name)

# 全局配置实例
_enterprise_config = None

def get_enterprise_config() -> EnterpriseConfig:
    """获取全局企业级配置实例"""
    global _enterprise_config
    if _enterprise_config is None:
        _enterprise_config = EnterpriseConfig()
    return _enterprise_config

# 向后兼容函数
def get_provider_config(name: str):
    """获取提供者配置 - 兼容旧版本"""
    return get_enterprise_config().get_provider_config(name)

def is_production() -> bool:
    """检查是否为生产环境"""
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


# === 企业级AI路由配置 ===
try:
    from pydantic_settings import BaseSettings
    from pydantic import Field
except ImportError:
    # 兼容旧版本
    from pydantic import BaseSettings, Field


class EnterpriseAIRouterConfig(BaseSettings):
    """企业级AI路由配置"""
    
    # === 基础配置 ===
    version: str = "2.0.0"
    environment: str = Field(default="production", env="AI_ENVIRONMENT")
    debug_mode: bool = Field(default=False, env="AI_DEBUG_MODE")
    
    # === 性能配置 ===
    max_message_length: int = 32000
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    default_conversation_limit: int = 50
    max_concurrent_requests: int = 100
    request_timeout_seconds: int = 300
    
    # === 速率限制配置 ===
    rate_limit_requests: int = Field(default=100, env="AI_RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=3600, env="AI_RATE_LIMIT_WINDOW")
    rate_limit_burst_size: int = Field(default=10, env="AI_RATE_LIMIT_BURST")
    
    # === 文件处理配置 ===
    supported_file_types: List[str] = ['.pdf', '.docx', '.txt', '.md', '.json', '.xlsx', '.pptx']
    max_file_processing_time: int = 600  # 10分钟
    file_processing_queue_size: int = 100
    
    # === 缓存配置 ===
    enable_response_cache: bool = Field(default=True, env="AI_ENABLE_CACHE")
    cache_ttl_seconds: int = Field(default=3600, env="AI_CACHE_TTL")
    max_cache_size_mb: int = Field(default=1024, env="AI_MAX_CACHE_SIZE")
    
    # === 监控配置 ===
    enable_monitoring: bool = Field(default=True, env="AI_ENABLE_MONITORING")
    metrics_collection_interval: int = 5  # 秒
    metrics_retention_hours: int = 168  # 7天
    max_websocket_connections: int = 100
    
    # === 安全配置 ===
    enable_rate_limiting: bool = True
    enable_request_validation: bool = True
    max_tokens_per_request: int = 8192
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 忽略额外的环境变量，避免与全局配置冲突
        extra = "ignore"


# 全局路由配置实例
ai_router_config = EnterpriseAIRouterConfig()


def is_router_debug_enabled() -> bool:
    """检查是否启用路由调试模式"""
    return ai_router_config.debug_mode


def get_max_file_size_mb() -> float:
    """获取最大文件大小(MB)"""
    return ai_router_config.max_upload_size / (1024 * 1024)


def validate_file_type(filename: str) -> bool:
    """验证文件类型是否被支持"""
    import os
    file_ext = os.path.splitext(filename)[1].lower()
    return file_ext in ai_router_config.supported_file_types
