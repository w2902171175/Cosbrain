"""
AI监控路由
提供AI监控相关的API端点，调用监控服务
"""

import asyncio
from typing import Dict, Any, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

# 项目依赖
from project.database import get_db
from project.utils import get_current_user_id
from project.models import User

# 监控服务
from project.services.ai_monitoring_service import (
    ai_monitoring_service,
    RealTimeMetrics,
    ProviderPerformance,
    SystemAlert
)

# 权限验证
from project.routers.ai.ai_admin import verify_admin_permission

# 企业级日志
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    logger = get_ai_logger("ai_monitoring")
except ImportError:
    import logging
    logger = logging.getLogger("ai_monitoring")


router = APIRouter(
    prefix="/ai/monitoring",
    tags=["AI监控"],
    dependencies=[Depends(verify_admin_permission)]
)


@router.get("/metrics/realtime", response_model=RealTimeMetrics, summary="获取实时指标")
async def get_realtime_metrics():
    """获取实时系统指标"""
    try:
        metrics = await ai_monitoring_service.get_real_time_metrics()
        return metrics
    except Exception as e:
        logger.error(f"Failed to get realtime metrics: {e}")
        raise HTTPException(status_code=500, detail="获取实时指标失败")


@router.get("/providers/performance", response_model=List[ProviderPerformance], summary="获取AI提供者性能指标")
async def get_provider_performance(db: Session = Depends(get_db)):
    """获取AI提供者性能指标"""
    try:
        performances = await ai_monitoring_service.get_provider_performance(db)
        return performances
    except Exception as e:
        logger.error(f"Failed to get provider performance: {e}")
        raise HTTPException(status_code=500, detail="获取提供者性能指标失败")


@router.get("/system/health", summary="获取系统健康状态")
async def get_system_health() -> Dict[str, Any]:
    """获取系统健康状态"""
    try:
        health = await ai_monitoring_service.get_system_health()
        return health
    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        raise HTTPException(status_code=500, detail="获取系统健康状态失败")


@router.get("/alerts/active", response_model=List[SystemAlert], summary="获取活跃告警")
async def get_active_alerts():
    """获取当前活跃的告警"""
    try:
        alerts = list(ai_monitoring_service.active_alerts.values())
        return alerts
    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(status_code=500, detail="获取活跃告警失败")


@router.get("/metrics/history", summary="获取历史指标")
async def get_metrics_history(
    hours: int = Query(default=24, description="历史数据小时数", ge=1, le=168)
):
    """获取历史指标数据"""
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        history = [
            metric for metric in ai_monitoring_service.metrics_history
            if metric.timestamp > cutoff_time
        ]
        return {
            "metrics": history,
            "total_count": len(history),
            "time_range_hours": hours
        }
    except Exception as e:
        logger.error(f"Failed to get metrics history: {e}")
        raise HTTPException(status_code=500, detail="获取历史指标失败")


@router.websocket("/realtime")
async def websocket_realtime_monitoring(
    websocket: WebSocket,
    user_id: int = Depends(get_current_user_id)
):
    """实时监控WebSocket连接"""
    await ai_monitoring_service.connection_manager.connect(websocket, user_id)
    
    try:
        while True:
            # 获取实时指标
            metrics = await ai_monitoring_service.get_real_time_metrics()
            
            # 检查告警规则
            await ai_monitoring_service.check_alert_rules(metrics)
            
            # 发送指标数据
            await ai_monitoring_service.connection_manager.send_personal_message(
                metrics.json(), websocket
            )
            
            # 等待5秒后发送下一次数据
            await asyncio.sleep(5)
            
    except WebSocketDisconnect:
        ai_monitoring_service.connection_manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        ai_monitoring_service.connection_manager.disconnect(websocket, user_id)


@router.post("/alerts/rules", summary="创建告警规则")
async def create_alert_rule(rule_data: Dict[str, Any]):
    """创建新的告警规则"""
    try:
        # 这里应该有更完整的验证和存储逻辑
        rule_id = f"rule_{int(datetime.utcnow().timestamp())}"
        
        from project.services.ai_monitoring_service import AlertRule
        rule = AlertRule(
            id=rule_id,
            name=rule_data.get("name", ""),
            metric=rule_data.get("metric", ""),
            operator=rule_data.get("operator", "gt"),
            threshold=float(rule_data.get("threshold", 0)),
            duration_minutes=int(rule_data.get("duration_minutes", 5)),
            enabled=rule_data.get("enabled", True)
        )
        
        ai_monitoring_service.alert_rules[rule_id] = rule
        
        return {
            "success": True,
            "rule_id": rule_id,
            "message": "告警规则创建成功"
        }
    except Exception as e:
        logger.error(f"Failed to create alert rule: {e}")
        raise HTTPException(status_code=500, detail="创建告警规则失败")


@router.get("/stats/errors", summary="获取错误统计")
async def get_error_stats():
    """获取错误统计信息"""
    try:
        from project.utils.ai.ai_exceptions import exception_handler
        stats = exception_handler.get_error_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get error stats: {e}")
        raise HTTPException(status_code=500, detail="获取错误统计失败")


@router.post("/metrics/record", summary="记录请求指标")
async def record_request_metrics(
    response_time: float,
    success: bool = True
):
    """记录请求指标（供内部调用）"""
    try:
        ai_monitoring_service.record_request(response_time, success)
        return {"success": True, "message": "指标记录成功"}
    except Exception as e:
        logger.error(f"Failed to record metrics: {e}")
        raise HTTPException(status_code=500, detail="记录指标失败")
