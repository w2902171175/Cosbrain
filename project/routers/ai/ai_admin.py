"""
企业级AI管理路由
提供AI提供者管理、配置、监控等管理功能
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# 项目依赖
from project.database import get_db
from project.dependencies import get_current_user_id
from project.models import Student

# AI提供者集成
from project.ai_providers.provider_manager import AIProviderManager
from project.ai_providers.ai_config import get_enterprise_config
from project.ai_providers.management_api import SystemStatus, ProviderStats

# 企业级日志
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    from logs.ai_providers.config_manager import get_config_manager
    logger = get_ai_logger("ai_admin")
    ENTERPRISE_FEATURES = True
except ImportError:
    import logging
    logger = logging.getLogger("ai_admin")
    ENTERPRISE_FEATURES = False


# === 请求/响应模型 ===

class ProviderConfigUpdate(BaseModel):
    """提供者配置更新模型"""
    provider_name: str
    config_updates: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "provider_name": "openai",
                "config_updates": {
                    "max_retries": 5,
                    "timeout": 60,
                    "rate_limit": 50
                }
            }
        }


class ModelSwitchRequest(BaseModel):
    """模型切换请求"""
    provider_name: str
    new_model: str
    apply_to_users: List[int] = Field(default_factory=list)


class SystemMetrics(BaseModel):
    """系统指标响应"""
    timestamp: datetime
    uptime_seconds: float
    total_requests: int
    success_rate: float
    average_response_time: float
    error_count: int
    cache_hit_rate: float
    active_providers: int
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None


class ProviderInfo(BaseModel):
    """提供者信息"""
    name: str
    type: str  # llm, embedding, rerank
    status: str  # healthy, degraded, offline
    model: str
    last_health_check: datetime
    total_requests: int
    success_rate: float
    avg_response_time_ms: float
    rate_limit: float
    cache_enabled: bool


# === 权限验证 ===

async def verify_admin_permission(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> bool:
    """验证管理员权限"""
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户未找到"
        )
    
    # 检查是否为管理员（这里需要根据实际权限字段调整）
    if not getattr(user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    
    return True


# === 路由定义 ===

router = APIRouter(
    prefix="/ai/admin",
    tags=["AI系统管理"],
    dependencies=[Depends(verify_admin_permission)],
    responses={
        403: {"description": "禁止访问 - 需要管理员权限"},
        404: {"description": "资源未找到"}
    }
)


@router.get("/system/status", response_model=SystemStatus, summary="获取系统状态")
async def get_system_status():
    """获取系统整体状态"""
    try:
        if not ENTERPRISE_FEATURES:
            return SystemStatus(
                timestamp=datetime.now(),
                status="basic",
                enterprise_features=False,
                uptime_seconds=time.time()
            )
        
        # 获取系统状态
        config_manager = get_config_manager()
        system_stats = await config_manager.get_system_stats()
        
        return SystemStatus(
            timestamp=datetime.now(),
            status=system_stats.get("status", "unknown"),
            enterprise_features=True,
            uptime_seconds=system_stats.get("uptime_seconds", 0)
        )
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统状态失败: {str(e)}"
        )


@router.get("/system/metrics", response_model=SystemMetrics, summary="获取系统指标")
async def get_system_metrics():
    """获取详细系统指标"""
    try:
        if not ENTERPRISE_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="企业功能不可用"
            )
        
        # 获取详细指标
        config_manager = get_config_manager()
        metrics = await config_manager.get_detailed_metrics()
        
        return SystemMetrics(
            timestamp=datetime.now(),
            uptime_seconds=metrics.get("uptime_seconds", 0),
            total_requests=metrics.get("total_requests", 0),
            success_rate=metrics.get("success_rate", 0.0),
            average_response_time=metrics.get("avg_response_time", 0.0),
            error_count=metrics.get("error_count", 0),
            cache_hit_rate=metrics.get("cache_hit_rate", 0.0),
            active_providers=metrics.get("active_providers", 0),
            memory_usage_mb=metrics.get("memory_usage_mb"),
            cpu_usage_percent=metrics.get("cpu_usage_percent")
        )
        
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统指标失败: {str(e)}"
        )


@router.get("/providers", response_model=List[ProviderInfo], summary="获取AI提供者列表")
async def list_providers():
    """列出所有AI提供者及其状态"""
    try:
        provider_manager = AIProviderManager()
        await provider_manager.initialize()
        
        providers_info = []
        
        # 获取LLM提供者信息
        for provider_name in provider_manager.factory.get_available_llm_providers():
            try:
                provider = provider_manager.get_llm_provider(provider_name)
                health = await provider_manager.check_provider_health(provider_name)
                stats = await provider_manager.get_provider_stats(provider_name)
                
                providers_info.append(ProviderInfo(
                    name=provider_name,
                    type="llm",
                    status=health.get("status", "unknown"),
                    model=provider.model,
                    last_health_check=datetime.now(),
                    total_requests=stats.get("total_requests", 0),
                    success_rate=stats.get("success_rate", 0.0),
                    avg_response_time_ms=stats.get("avg_response_time", 0.0),
                    rate_limit=getattr(provider, 'rate_limit', 0.0),
                    cache_enabled=getattr(provider, 'enable_cache', False)
                ))
            except Exception as e:
                logger.warning(f"Failed to get info for provider {provider_name}: {e}")
        
        # 获取嵌入提供者信息
        for provider_name in provider_manager.factory.get_available_embedding_providers():
            try:
                provider = provider_manager.get_embedding_provider(provider_name)
                health = await provider_manager.check_provider_health(f"embedding_{provider_name}")
                stats = await provider_manager.get_provider_stats(f"embedding_{provider_name}")
                
                providers_info.append(ProviderInfo(
                    name=provider_name,
                    type="embedding",
                    status=health.get("status", "unknown"),
                    model=getattr(provider, 'model', 'default'),
                    last_health_check=datetime.now(),
                    total_requests=stats.get("total_requests", 0),
                    success_rate=stats.get("success_rate", 0.0),
                    avg_response_time_ms=stats.get("avg_response_time", 0.0),
                    rate_limit=getattr(provider, 'rate_limit', 0.0),
                    cache_enabled=getattr(provider, 'enable_cache', False)
                ))
            except Exception as e:
                logger.warning(f"Failed to get info for embedding provider {provider_name}: {e}")
        
        return providers_info
        
    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取AI提供者列表失败: {str(e)}"
        )


@router.post("/providers/{provider_name}/config", summary="更新提供者配置")
async def update_provider_config(
    provider_name: str,
    config_update: ProviderConfigUpdate
):
    """更新提供者配置"""
    try:
        if not ENTERPRISE_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="企业功能不可用"
            )
        
        config_manager = get_config_manager()
        
        # 验证提供者存在
        provider_manager = AIProviderManager()
        await provider_manager.initialize()
        
        if not provider_manager.has_provider(provider_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI提供者 {provider_name} 未找到"
            )
        
        # 更新配置
        result = await config_manager.update_provider_config(
            provider_name,
            config_update.config_updates
        )
        
        logger.info(f"Updated config for provider {provider_name}: {config_update.config_updates}")
        
        return {
            "message": f"AI提供者 {provider_name} 配置更新成功",
            "updated_fields": list(config_update.config_updates.keys()),
            "restart_required": result.get("restart_required", False)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update provider config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新AI提供者配置失败: {str(e)}"
        )


@router.post("/providers/{provider_name}/restart", summary="重启AI提供者")
async def restart_provider(provider_name: str):
    """重启指定提供者"""
    try:
        provider_manager = AIProviderManager()
        await provider_manager.initialize()
        
        if not provider_manager.has_provider(provider_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI提供者 {provider_name} 未找到"
            )
        
        # 重启提供者
        success = await provider_manager.restart_provider(provider_name)
        
        if success:
            logger.info(f"Successfully restarted provider {provider_name}")
            return {"message": f"AI提供者 {provider_name} 重启成功"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI提供者 {provider_name} 重启失败"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restart provider: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重启AI提供者失败: {str(e)}"
        )


@router.post("/models/switch", summary="切换AI模型")
async def switch_model(model_switch: ModelSwitchRequest):
    """切换模型"""
    try:
        provider_manager = AIProviderManager()
        await provider_manager.initialize()
        
        # 验证提供者和模型
        if not provider_manager.has_provider(model_switch.provider_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI提供者 {model_switch.provider_name} 未找到"
            )
        
        # 执行模型切换
        result = await provider_manager.switch_model(
            model_switch.provider_name,
            model_switch.new_model,
            model_switch.apply_to_users
        )
        
        logger.info(f"Switched model for provider {model_switch.provider_name} to {model_switch.new_model}")
        
        return {
            "message": f"模型切换成功",
            "provider": model_switch.provider_name,
            "new_model": model_switch.new_model,
            "affected_users": len(model_switch.apply_to_users) if model_switch.apply_to_users else "all",
            "rollback_available": result.get("rollback_available", False)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to switch model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"模型切换失败: {str(e)}"
        )


@router.get("/providers/{provider_name}/stats", response_model=ProviderStats, summary="获取提供者统计")
async def get_provider_stats(
    provider_name: str,
    hours: int = Query(default=24, ge=1, le=168)  # 1小时到1周
):
    """获取指定提供者的详细统计信息"""
    try:
        provider_manager = AIProviderManager()
        await provider_manager.initialize()
        
        if not provider_manager.has_provider(provider_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI提供者 {provider_name} 未找到"
            )
        
        # 获取指定时间范围的统计
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        stats = await provider_manager.get_provider_stats(
            provider_name, start_time, end_time
        )
        
        return ProviderStats(
            provider_name=provider_name,
            total_requests=stats.get("total_requests", 0),
            success_rate=stats.get("success_rate", 0.0),
            average_response_time=stats.get("avg_response_time", 0.0),
            error_count=stats.get("error_count", 0),
            cache_hit_rate=stats.get("cache_hit_rate")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get provider stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取AI提供者统计信息失败: {str(e)}"
        )


@router.delete("/cache", summary="清空缓存")
async def clear_cache(
    provider_name: Optional[str] = Query(None, description="仅清空指定提供者的缓存")
):
    """清空缓存"""
    try:
        if not ENTERPRISE_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="企业功能不可用"
            )
        
        provider_manager = AIProviderManager()
        await provider_manager.initialize()
        
        if provider_name:
            # 清空特定提供者的缓存
            if not provider_manager.has_provider(provider_name):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"AI提供者 {provider_name} 未找到"
                )
            
            cleared_count = await provider_manager.clear_provider_cache(provider_name)
            message = f"已清空AI提供者 {provider_name} 的 {cleared_count} 个缓存条目"
        else:
            # 清空所有缓存
            cleared_count = await provider_manager.clear_all_cache()
            message = f"已清空所有AI提供者的 {cleared_count} 个缓存条目"
        
        logger.info(message)
        return {"message": message, "cleared_entries": cleared_count}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空缓存失败: {str(e)}"
        )


@router.get("/logs", summary="获取系统日志")
async def get_system_logs(
    level: str = Query(default="INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=100, ge=1, le=1000)
):
    """获取系统日志"""
    try:
        if not ENTERPRISE_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="企业功能不可用"
            )
        
        # 获取日志
        from logs.ai_providers.ai_logger import get_recent_logs
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        logs = await get_recent_logs(
            start_time=start_time,
            end_time=end_time,
            level=level,
            limit=limit
        )
        
        return {
            "logs": logs,
            "total_count": len(logs),
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "level": level
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统日志失败: {str(e)}"
        )
