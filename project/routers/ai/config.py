"""
企业级AI路由配置
"""

from typing import Dict, Any, List
import os

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
    enable_api_key_auth: bool = Field(default=True, env="AI_ENABLE_API_KEY_AUTH")
    enable_request_signing: bool = Field(default=False, env="AI_ENABLE_REQUEST_SIGNING")
    max_request_size_mb: int = 50
    allowed_origins: List[str] = Field(default=["*"], env="AI_ALLOWED_ORIGINS")
    
    # === 告警配置 ===
    enable_alerts: bool = Field(default=True, env="AI_ENABLE_ALERTS")
    alert_email_recipients: List[str] = Field(default=[], env="AI_ALERT_EMAILS")
    alert_webhook_url: str = Field(default="", env="AI_ALERT_WEBHOOK")
    
    # === 日志配置 ===
    log_level: str = Field(default="INFO", env="AI_LOG_LEVEL")
    enable_request_logging: bool = Field(default=True, env="AI_ENABLE_REQUEST_LOGGING")
    enable_performance_logging: bool = Field(default=True, env="AI_ENABLE_PERF_LOGGING")
    log_retention_days: int = 30
    
    # === 数据库配置 ===
    enable_query_optimization: bool = True
    max_db_connections: int = 50
    db_connection_timeout: int = 30
    
    # === 特性开关 ===
    enable_streaming_responses: bool = Field(default=True, env="AI_ENABLE_STREAMING")
    enable_tool_calling: bool = Field(default=True, env="AI_ENABLE_TOOLS")
    enable_context_enhancement: bool = Field(default=True, env="AI_ENABLE_CONTEXT")
    enable_multi_model_routing: bool = Field(default=True, env="AI_ENABLE_MULTI_MODEL")
    enable_background_processing: bool = Field(default=True, env="AI_ENABLE_BACKGROUND")
    
    class Config:
        env_file = ".env"
        env_prefix = "AI_ROUTER_"
        extra = "allow"  # 允许额外字段


class SecurityConfig:
    """安全配置"""
    
    # 输入验证
    MAX_MESSAGE_LENGTH = 32000
    MAX_FILENAME_LENGTH = 255
    ALLOWED_MIME_TYPES = [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain',
        'text/markdown',
        'application/json',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    ]
    
    # 敏感信息过滤
    SENSITIVE_PATTERNS = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # 信用卡号
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',  # IP地址
    ]
    
    # API密钥脱敏
    @staticmethod
    def sanitize_api_key(api_key: str) -> str:
        """脱敏API密钥"""
        if not api_key or len(api_key) < 8:
            return "***"
        return f"{api_key[:4]}...{api_key[-4:]}"


class PerformanceConfig:
    """性能配置"""
    
    # 响应时间阈值（毫秒）
    RESPONSE_TIME_THRESHOLDS = {
        "fast": 1000,      # 1秒
        "normal": 3000,    # 3秒
        "slow": 10000,     # 10秒
        "timeout": 30000   # 30秒
    }
    
    # 并发限制
    MAX_CONCURRENT_REQUESTS_PER_USER = 5
    MAX_CONCURRENT_FILE_UPLOADS = 3
    MAX_CONCURRENT_MODEL_REQUESTS = 20
    
    # 资源限制
    MAX_MEMORY_USAGE_MB = 8192  # 8GB
    MAX_CPU_USAGE_PERCENT = 80
    MAX_DISK_USAGE_PERCENT = 85


class MonitoringConfig:
    """监控配置"""
    
    # 指标定义
    CORE_METRICS = [
        "requests_per_second",
        "average_response_time",
        "error_rate",
        "active_connections",
        "memory_usage_mb",
        "cpu_usage_percent",
        "cache_hit_rate"
    ]
    
    # 告警规则模板
    DEFAULT_ALERT_RULES = [
        {
            "name": "High Error Rate",
            "metric": "error_rate",
            "operator": "gt",
            "threshold": 0.05,  # 5%
            "duration_minutes": 5
        },
        {
            "name": "Slow Response Time",
            "metric": "average_response_time",
            "operator": "gt",
            "threshold": 5000,  # 5秒
            "duration_minutes": 10
        },
        {
            "name": "High Memory Usage",
            "metric": "memory_usage_mb",
            "operator": "gt",
            "threshold": 6144,  # 6GB
            "duration_minutes": 15
        }
    ]


# === 全局配置实例 ===
ai_router_config = EnterpriseAIRouterConfig()
security_config = SecurityConfig()
performance_config = PerformanceConfig()
monitoring_config = MonitoringConfig()


def get_config() -> EnterpriseAIRouterConfig:
    """获取配置实例"""
    return ai_router_config


def is_production() -> bool:
    """检查是否为生产环境"""
    return ai_router_config.environment.lower() == "production"


def is_debug_enabled() -> bool:
    """检查是否启用调试模式"""
    return ai_router_config.debug_mode


def get_feature_flags() -> Dict[str, bool]:
    """获取特性开关状态"""
    return {
        "streaming_responses": ai_router_config.enable_streaming_responses,
        "tool_calling": ai_router_config.enable_tool_calling,
        "context_enhancement": ai_router_config.enable_context_enhancement,
        "multi_model_routing": ai_router_config.enable_multi_model_routing,
        "background_processing": ai_router_config.enable_background_processing,
        "monitoring": ai_router_config.enable_monitoring,
        "alerts": ai_router_config.enable_alerts,
        "caching": ai_router_config.enable_response_cache
    }


def validate_environment():
    """验证环境配置"""
    errors = []
    
    # 检查必要配置
    if ai_router_config.max_message_length <= 0:
        errors.append("max_message_length must be positive")
    
    if ai_router_config.rate_limit_requests <= 0:
        errors.append("rate_limit_requests must be positive")
    
    if ai_router_config.max_upload_size <= 0:
        errors.append("max_upload_size must be positive")
    
    # 检查环境特定配置
    if is_production():
        if ai_router_config.debug_mode:
            errors.append("Debug mode should be disabled in production")
        
        if not ai_router_config.enable_monitoring:
            errors.append("Monitoring should be enabled in production")
    
    return errors


def get_runtime_info() -> Dict[str, Any]:
    """获取运行时信息"""
    import psutil
    import platform
    
    return {
        "version": ai_router_config.version,
        "environment": ai_router_config.environment,
        "debug_mode": ai_router_config.debug_mode,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": psutil.cpu_count(),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "feature_flags": get_feature_flags(),
        "config_validation_errors": validate_environment()
    }
