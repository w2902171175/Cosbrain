# project/config/mcp_config.py
"""
MCP 模块配置文件
"""
from typing import List, Dict, Any
from pydantic import BaseModel


class McpConnectivityConfig(BaseModel):
    """MCP 连接检查配置"""
    # 健康检查端点配置
    health_check_endpoints: List[str] = ["/health", "/status", "/ping", ""]
    
    # 超时配置（秒）
    request_timeout: int = 5
    
    # 缓存配置
    cache_ttl: int = 300  # 5分钟缓存
    cache_enabled: bool = True
    
    # 性能监控配置
    performance_monitoring_enabled: bool = True
    slow_request_threshold: float = 2.0  # 超过2秒视为慢请求
    
    # 特定服务商配置
    provider_specific_headers: Dict[str, Dict[str, str]] = {
        "modelscope": {
            "User-Agent": "MCP-Client/1.0",
            "Accept": "application/json"
        }
    }
    
    # 重试配置
    max_retries: int = 2
    retry_delay: float = 1.0


# 默认配置实例
mcp_config = McpConnectivityConfig()


def get_provider_headers(base_url: str, api_key: str = None) -> Dict[str, str]:
    """根据服务提供商获取特定的请求头"""
    headers = {"Accept": "application/json"}
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
        # ModelScope 特殊处理
        if "modelscope" in base_url.lower():
            headers["X-DashScope-Apikey"] = api_key
            headers.update(mcp_config.provider_specific_headers.get("modelscope", {}))
    
    return headers
