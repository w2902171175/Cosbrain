"""
AI Providers 监控和管理API
提供系统状态监控、配置管理等功能
"""

import asyncio
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

try:
    from logs.ai_providers.ai_logger import get_all_stats
    from logs.ai_providers.config_manager import get_config_manager, get_config
    from logs.ai_providers.connection_manager import get_connection_stats
    from logs.ai_providers.cache_manager import get_cache_stats
    from project.ai_providers.ai_base import health_check
    ENTERPRISE_FEATURES = True
except ImportError:
    ENTERPRISE_FEATURES = False


router = APIRouter(prefix="/api/ai-providers", tags=["AI Providers Management"])


class SystemStatus(BaseModel):
    """系统状态响应模型"""
    timestamp: datetime
    status: str
    enterprise_features: bool
    uptime_seconds: float
    version: str = "2.0.0"


class ProviderStats(BaseModel):
    """提供者统计响应模型"""
    provider_name: str
    total_requests: int
    success_rate: float
    average_response_time: float
    error_count: int
    cache_hit_rate: Optional[float] = None


class ConfigUpdateRequest(BaseModel):
    """配置更新请求模型"""
    provider_name: str
    config_updates: Dict[str, Any]


# 系统启动时间
_start_time = time.time()


@router.get("/health", response_model=SystemStatus)
async def get_health_status():
    """获取系统健康状态"""
    if not ENTERPRISE_FEATURES:
        return SystemStatus(
            timestamp=datetime.now(),
            status="basic",
            enterprise_features=False,
            uptime_seconds=time.time() - _start_time
        )
    
    try:
        health_data = await health_check()
        
        return SystemStatus(
            timestamp=datetime.now(),
            status=health_data.get("status", "unknown"),
            enterprise_features=True,
            uptime_seconds=time.time() - _start_time
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/stats")
async def get_system_stats():
    """获取系统统计信息"""
    if not ENTERPRISE_FEATURES:
        return {"message": "Enterprise features not available"}
    
    try:
        stats = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": time.time() - _start_time,
            "enterprise_features": True
        }
        
        # AI提供者统计
        try:
            provider_stats = get_all_stats()
            stats["providers"] = provider_stats
        except Exception as e:
            stats["providers_error"] = str(e)
        
        # 连接池统计
        try:
            connection_stats = await get_connection_stats()
            stats["connections"] = connection_stats
        except Exception as e:
            stats["connections_error"] = str(e)
        
        # 缓存统计
        try:
            cache_stats = await get_cache_stats()
            stats["cache"] = cache_stats
        except Exception as e:
            stats["cache_error"] = str(e)
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/config")
async def get_current_config():
    """获取当前配置"""
    if not ENTERPRISE_FEATURES:
        return {"message": "Enterprise features not available"}
    
    try:
        config = get_config()
        
        # 脱敏处理，不返回敏感信息
        safe_config = {
            "environment": config.environment.value,
            "providers": {},
            "performance": {
                "connection_pool_size": config.performance.connection_pool_size,
                "keepalive_connections": config.performance.keepalive_connections,
                "request_timeout": config.performance.request_timeout,
                "retry_backoff_factor": config.performance.retry_backoff_factor
            },
            "logging": {
                "level": config.logging.level,
                "enable_performance_logs": config.logging.enable_performance_logs,
                "log_retention_days": config.logging.log_retention_days
            }
        }
        
        # 添加提供者配置（去除敏感信息）
        for name, provider in config.providers.items():
            safe_config["providers"][name] = {
                "name": provider.name,
                "base_url": provider.base_url,
                "default_model": provider.default_model,
                "available_models": provider.available_models,
                "timeout": provider.timeout,
                "max_retries": provider.max_retries,
                "rate_limit": provider.rate_limit,
                "enable_cache": provider.enable_cache
            }
        
        return safe_config
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")


@router.post("/config/reload")
async def reload_config():
    """重新加载配置"""
    if not ENTERPRISE_FEATURES:
        return {"message": "Enterprise features not available"}
    
    try:
        config_manager = get_config_manager()
        config_manager.reload_config()
        
        return {
            "message": "Configuration reloaded successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload config: {str(e)}")


@router.get("/providers")
async def list_providers():
    """列出所有AI提供者"""
    if not ENTERPRISE_FEATURES:
        return {"message": "Enterprise features not available"}
    
    try:
        config = get_config()
        providers = []
        
        for name, provider_config in config.providers.items():
            providers.append({
                "name": name,
                "type": "llm",  # 可以扩展支持其他类型
                "base_url": provider_config.base_url,
                "default_model": provider_config.default_model,
                "available_models": provider_config.available_models,
                "status": "active",
                "rate_limit": provider_config.rate_limit
            })
        
        return {
            "providers": providers,
            "total_count": len(providers)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list providers: {str(e)}")


@router.get("/providers/{provider_name}/stats")
async def get_provider_stats(provider_name: str):
    """获取特定提供者的统计信息"""
    if not ENTERPRISE_FEATURES:
        return {"message": "Enterprise features not available"}
    
    try:
        all_stats = get_all_stats()
        
        if provider_name not in all_stats:
            raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")
        
        provider_stats = all_stats[provider_name]
        
        return {
            "provider_name": provider_name,
            "stats": provider_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get provider stats: {str(e)}")


@router.post("/cache/clear")
async def clear_cache():
    """清空缓存"""
    if not ENTERPRISE_FEATURES:
        return {"message": "Enterprise features not available"}
    
    try:
        from logs.ai_providers.cache_manager import get_cache_manager
        
        cache_manager = get_cache_manager()
        await cache_manager.clear()
        
        return {
            "message": "Cache cleared successfully",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get("/metrics")
async def get_metrics():
    """获取Prometheus格式的指标"""
    if not ENTERPRISE_FEATURES:
        return {"message": "Enterprise features not available"}
    
    try:
        stats = get_all_stats()
        connection_stats = await get_connection_stats()
        cache_stats = await get_cache_stats()
        
        metrics = []
        
        # AI提供者指标
        for provider_name, provider_stats in stats.items():
            operations = provider_stats.get("operations", {})
            for op_name, op_stats in operations.items():
                metrics.append(f'ai_provider_requests_total{{provider="{provider_name}",operation="{op_name}"}} {op_stats["total_calls"]}')
                metrics.append(f'ai_provider_errors_total{{provider="{provider_name}",operation="{op_name}"}} {op_stats["total_errors"]}')
                metrics.append(f'ai_provider_duration_ms{{provider="{provider_name}",operation="{op_name}"}} {op_stats["average_duration_ms"]}')
                metrics.append(f'ai_provider_error_rate{{provider="{provider_name}",operation="{op_name}"}} {op_stats["error_rate"]}')
        
        # 连接池指标
        for pool_name, pool_stats in connection_stats.get("connection_pools", {}).items():
            metrics.append(f'connection_pool_active{{pool="{pool_name}"}} {pool_stats["active_connections"]}')
            metrics.append(f'connection_pool_requests_total{{pool="{pool_name}"}} {pool_stats["request_count"]}')
            metrics.append(f'connection_pool_errors_total{{pool="{pool_name}"}} {pool_stats["error_count"]}')
        
        # 缓存指标
        if "memory_cache" in cache_stats:
            memory_cache = cache_stats["memory_cache"]
            metrics.append(f'cache_hits_total{{type="memory"}} {memory_cache["hits"]}')
            metrics.append(f'cache_misses_total{{type="memory"}} {memory_cache["misses"]}')
            metrics.append(f'cache_hit_rate{{type="memory"}} {memory_cache["hit_rate"]}')
            metrics.append(f'cache_size{{type="memory"}} {memory_cache["size"]}')
        
        return "\n".join(metrics)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


# 后台任务：定期清理和监控
async def background_maintenance():
    """后台维护任务"""
    if not ENTERPRISE_FEATURES:
        return
    
    while True:
        try:
            # 每5分钟执行一次维护任务
            await asyncio.sleep(300)
            
            # 清理过期缓存
            from logs.ai_providers.cache_manager import get_cache_manager
            cache_manager = get_cache_manager()
            if hasattr(cache_manager.memory_cache, 'cleanup_expired'):
                expired_count = cache_manager.memory_cache.cleanup_expired()
                if expired_count > 0:
                    print(f"Cleaned up {expired_count} expired cache items")
            
            # 记录系统状态
            health_data = await health_check()
            print(f"System health check: {health_data.get('status', 'unknown')}")
            
        except Exception as e:
            print(f"Background maintenance error: {e}")


# 启动后台任务
@router.on_event("startup")
async def startup_event():
    """启动事件"""
    if ENTERPRISE_FEATURES:
        # 启动后台维护任务
        asyncio.create_task(background_maintenance())
        print("AI Providers enterprise features initialized")
    else:
        print("AI Providers running in basic mode")
