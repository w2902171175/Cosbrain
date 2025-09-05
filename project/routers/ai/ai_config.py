"""
企业级AI路由配置 - 简化版本
提供必要的配置项，去除冗余代码
"""

from typing import List

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


# 全局配置实例
ai_router_config = EnterpriseAIRouterConfig()


def is_production() -> bool:
    """检查是否为生产环境"""
    return ai_router_config.environment.lower() == "production"


def is_debug_enabled() -> bool:
    """检查是否启用调试模式"""
    return ai_router_config.debug_mode


def get_max_file_size_mb() -> float:
    """获取最大文件大小(MB)"""
    return ai_router_config.max_upload_size / (1024 * 1024)


def validate_file_type(filename: str) -> bool:
    """验证文件类型是否被支持"""
    import os
    file_ext = os.path.splitext(filename)[1].lower()
    return file_ext in ai_router_config.supported_file_types
