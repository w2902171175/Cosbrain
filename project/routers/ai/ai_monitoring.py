"""
企业级AI监控路由
提供实时监控、性能分析、告警等功能
"""

import asyncio
import time
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# 项目依赖
from project.database import get_db
from project.dependencies import get_current_user_id
from project.models import Student, AIConversation, AIConversationMessage

# AI提供者集成
from project.ai_providers.provider_manager import AIProviderManager

# 企业级日志和监控
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    from logs.ai_providers.cache_manager import get_cache_stats
    from logs.ai_providers.connection_manager import get_connection_stats
    from logs.metrics.health_20250830 import get_health_metrics
    logger = get_ai_logger("ai_monitoring")
    ENTERPRISE_MONITORING = True
except ImportError:
    import logging
    logger = logging.getLogger("ai_monitoring")
    ENTERPRISE_MONITORING = False


# === 监控数据模型 ===

class RealTimeMetrics(BaseModel):
    """实时指标模型"""
    timestamp: datetime
    requests_per_second: float
    average_response_time: float
    error_rate: float
    active_connections: int
    memory_usage_mb: float
    cpu_usage_percent: float
    cache_hit_rate: float


class ProviderPerformance(BaseModel):
    """提供者性能指标"""
    provider_name: str
    model: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    p95_response_time: float
    p99_response_time: float
    tokens_per_second: float
    cost_estimate: float


class AlertRule(BaseModel):
    """告警规则"""
    id: str
    name: str
    metric: str
    operator: str  # gt, lt, eq, ne
    threshold: float
    duration_minutes: int
    enabled: bool
    last_triggered: Optional[datetime] = None


class SystemAlert(BaseModel):
    """系统告警"""
    id: str
    rule_id: str
    level: str  # info, warning, error, critical
    message: str
    metric_value: float
    threshold: float
    triggered_at: datetime
    resolved_at: Optional[datetime] = None


# === WebSocket连接管理 ===

class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[int, List[WebSocket]] = defaultdict(list)
    
    async def connect(self, websocket: WebSocket, user_id: int):
        """建立连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_connections[user_id].append(websocket)
        logger.info(f"WebSocket connected for user {user_id}")
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        """断开连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.user_connections[user_id]:
            self.user_connections[user_id].remove(websocket)
        logger.info(f"WebSocket disconnected for user {user_id}")
    
    async def send_personal_message(self, message: str, user_id: int):
        """发送个人消息"""
        for connection in self.user_connections[user_id]:
            try:
                await connection.send_text(message)
            except:
                # 连接已断开，移除
                self.disconnect(connection, user_id)
    
    async def broadcast(self, message: str):
        """广播消息"""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                dead_connections.append(connection)
        
        # 清理死连接
        for connection in dead_connections:
            if connection in self.active_connections:
                self.active_connections.remove(connection)


# === 全局实例 ===
connection_manager = ConnectionManager()


# === 监控数据收集 ===

class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.provider_manager = None
        self._metrics_history = []
        self._alert_rules = []
        self._active_alerts = []
    
    async def initialize(self):
        """初始化"""
        self.provider_manager = AIProviderManager()
        await self.provider_manager.initialize()
    
    async def collect_real_time_metrics(self) -> RealTimeMetrics:
        """收集实时指标"""
        try:
            current_time = datetime.now()
            
            # 基础指标
            if ENTERPRISE_MONITORING:
                health_data = get_health_metrics()
                connection_stats = get_connection_stats()
                cache_stats = get_cache_stats()
                
                metrics = RealTimeMetrics(
                    timestamp=current_time,
                    requests_per_second=health_data.get("requests_per_second", 0.0),
                    average_response_time=health_data.get("avg_response_time", 0.0),
                    error_rate=health_data.get("error_rate", 0.0),
                    active_connections=connection_stats.get("active_connections", 0),
                    memory_usage_mb=health_data.get("memory_usage_mb", 0.0),
                    cpu_usage_percent=health_data.get("cpu_usage_percent", 0.0),
                    cache_hit_rate=cache_stats.get("hit_rate", 0.0)
                )
            else:
                # 简化指标
                metrics = RealTimeMetrics(
                    timestamp=current_time,
                    requests_per_second=0.0,
                    average_response_time=0.0,
                    error_rate=0.0,
                    active_connections=len(connection_manager.active_connections),
                    memory_usage_mb=0.0,
                    cpu_usage_percent=0.0,
                    cache_hit_rate=0.0
                )
            
            # 保存历史记录
            self._metrics_history.append(metrics)
            if len(self._metrics_history) > 1000:  # 保留最近1000条记录
                self._metrics_history.pop(0)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            raise
    
    async def collect_provider_performance(self, hours: int = 1) -> List[ProviderPerformance]:
        """收集提供者性能数据"""
        try:
            if not self.provider_manager:
                await self.initialize()
            
            performance_data = []
            
            # 获取所有提供者的性能数据
            for provider_name in self.provider_manager.get_all_provider_names():
                try:
                    stats = await self.provider_manager.get_provider_stats(
                        provider_name, 
                        datetime.now() - timedelta(hours=hours),
                        datetime.now()
                    )
                    
                    provider = self.provider_manager.get_llm_provider(provider_name)
                    
                    performance = ProviderPerformance(
                        provider_name=provider_name,
                        model=getattr(provider, 'model', 'unknown'),
                        total_requests=stats.get("total_requests", 0),
                        successful_requests=stats.get("successful_requests", 0),
                        failed_requests=stats.get("failed_requests", 0),
                        average_response_time=stats.get("avg_response_time", 0.0),
                        p95_response_time=stats.get("p95_response_time", 0.0),
                        p99_response_time=stats.get("p99_response_time", 0.0),
                        tokens_per_second=stats.get("tokens_per_second", 0.0),
                        cost_estimate=stats.get("cost_estimate", 0.0)
                    )
                    
                    performance_data.append(performance)
                    
                except Exception as e:
                    logger.warning(f"Failed to get performance data for {provider_name}: {e}")
            
            return performance_data
            
        except Exception as e:
            logger.error(f"Failed to collect provider performance: {e}")
            return []
    
    async def check_alerts(self, current_metrics: RealTimeMetrics):
        """检查告警条件"""
        try:
            for rule in self._alert_rules:
                if not rule.enabled:
                    continue
                
                # 获取指标值
                metric_value = getattr(current_metrics, rule.metric, None)
                if metric_value is None:
                    continue
                
                # 检查阈值
                should_alert = False
                if rule.operator == "gt" and metric_value > rule.threshold:
                    should_alert = True
                elif rule.operator == "lt" and metric_value < rule.threshold:
                    should_alert = True
                elif rule.operator == "eq" and metric_value == rule.threshold:
                    should_alert = True
                elif rule.operator == "ne" and metric_value != rule.threshold:
                    should_alert = True
                
                if should_alert:
                    # 创建告警
                    alert = SystemAlert(
                        id=f"alert_{int(time.time())}_{rule.id}",
                        rule_id=rule.id,
                        level="warning" if metric_value > rule.threshold * 1.5 else "error",
                        message=f"{rule.name}: {rule.metric} = {metric_value} (threshold: {rule.threshold})",
                        metric_value=metric_value,
                        threshold=rule.threshold,
                        triggered_at=datetime.now()
                    )
                    
                    self._active_alerts.append(alert)
                    rule.last_triggered = datetime.now()
                    
                    # 发送告警通知
                    await self._send_alert_notification(alert)
            
        except Exception as e:
            logger.error(f"Failed to check alerts: {e}")
    
    async def _send_alert_notification(self, alert: SystemAlert):
        """发送告警通知"""
        alert_message = json.dumps({
            "type": "alert",
            "data": alert.dict()
        })
        
        await connection_manager.broadcast(alert_message)


# === 全局收集器实例 ===
metrics_collector = MetricsCollector()


# === 权限验证 ===

async def verify_monitoring_permission(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> bool:
    """验证监控权限"""
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户未找到"
        )
    
    # 检查是否有监控权限（这里需要根据实际权限字段调整）
    if not getattr(user, 'can_monitor', False) and not getattr(user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要监控权限"
        )
    
    return True


# === 路由定义 ===

router = APIRouter(
    prefix="/ai/monitoring",
    tags=["AI监控统计"],
    dependencies=[Depends(verify_monitoring_permission)],
    responses={
        403: {"description": "禁止访问 - 需要监控权限"},
        404: {"description": "资源未找到"}
    }
)


@router.get("/metrics/real-time", response_model=RealTimeMetrics, summary="获取实时指标")
async def get_real_time_metrics():
    """获取实时系统指标"""
    try:
        if metrics_collector.provider_manager is None:
            await metrics_collector.initialize()
        
        metrics = await metrics_collector.collect_real_time_metrics()
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to get real-time metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取实时指标失败: {str(e)}"
        )


@router.get("/metrics/history", summary="获取历史指标")
async def get_metrics_history(
    hours: int = Query(default=24, ge=1, le=168),
    resolution: str = Query(default="5m", regex="^(1m|5m|15m|1h)$")
):
    """获取历史指标数据"""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # 从历史记录中筛选数据
        filtered_metrics = [
            m for m in metrics_collector._metrics_history 
            if start_time <= m.timestamp <= end_time
        ]
        
        # 根据分辨率聚合数据
        if resolution == "1m":
            aggregated = filtered_metrics  # 不聚合
        else:
            # 简化聚合逻辑
            aggregated = filtered_metrics[::5] if resolution == "5m" else filtered_metrics[::15]
        
        return {
            "metrics": [m.dict() for m in aggregated],
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "resolution": resolution,
            "total_points": len(aggregated)
        }
        
    except Exception as e:
        logger.error(f"Failed to get metrics history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取指标历史失败: {str(e)}"
        )


@router.get("/providers/performance", response_model=List[ProviderPerformance], summary="获取提供者性能")
async def get_provider_performance(
    hours: int = Query(default=1, ge=1, le=168)
):
    """获取提供者性能数据"""
    try:
        performance_data = await metrics_collector.collect_provider_performance(hours)
        return performance_data
        
    except Exception as e:
        logger.error(f"Failed to get provider performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取AI提供者性能数据失败: {str(e)}"
        )


@router.get("/alerts/rules", response_model=List[AlertRule], summary="获取告警规则")
async def get_alert_rules():
    """获取告警规则列表"""
    return metrics_collector._alert_rules


@router.post("/alerts/rules", response_model=AlertRule, summary="创建告警规则")
async def create_alert_rule(rule: AlertRule):
    """创建告警规则"""
    try:
        # 验证指标名称
        valid_metrics = ["requests_per_second", "average_response_time", "error_rate", 
                        "memory_usage_mb", "cpu_usage_percent", "cache_hit_rate"]
        if rule.metric not in valid_metrics:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid metric. Valid metrics: {valid_metrics}"
            )
        
        # 添加规则
        metrics_collector._alert_rules.append(rule)
        
        logger.info(f"Created alert rule: {rule.name}")
        return rule
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create alert rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建告警规则失败: {str(e)}"
        )


@router.get("/alerts/active", response_model=List[SystemAlert], summary="获取活跃告警")
async def get_active_alerts():
    """获取活跃告警列表"""
    # 返回未解决的告警
    active_alerts = [alert for alert in metrics_collector._active_alerts if alert.resolved_at is None]
    return active_alerts


@router.post("/alerts/{alert_id}/resolve", summary="解决告警")
async def resolve_alert(alert_id: str):
    """解决告警"""
    try:
        for alert in metrics_collector._active_alerts:
            if alert.id == alert_id:
                alert.resolved_at = datetime.now()
                logger.info(f"Resolved alert: {alert_id}")
                return {"message": "告警解决成功"}
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警未找到"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解决告警失败: {str(e)}"
        )


@router.get("/dashboard/summary", summary="获取仪表板摘要")
async def get_dashboard_summary():
    """获取监控仪表板摘要数据"""
    try:
        # 获取最新指标
        current_metrics = await metrics_collector.collect_real_time_metrics()
        
        # 获取提供者性能
        provider_performance = await metrics_collector.collect_provider_performance(1)
        
        # 统计活跃告警
        active_alerts_count = len([
            alert for alert in metrics_collector._active_alerts 
            if alert.resolved_at is None
        ])
        
        # 计算总体健康分数
        health_score = 100.0
        if current_metrics.error_rate > 0.05:  # 错误率 > 5%
            health_score -= 20
        if current_metrics.average_response_time > 2000:  # 响应时间 > 2s
            health_score -= 15
        if current_metrics.cpu_usage_percent > 80:  # CPU > 80%
            health_score -= 10
        if current_metrics.memory_usage_mb > 8000:  # 内存 > 8GB
            health_score -= 10
        
        return {
            "timestamp": datetime.now().isoformat(),
            "health_score": max(0, health_score),
            "current_metrics": current_metrics.dict(),
            "provider_count": len(provider_performance),
            "active_alerts": active_alerts_count,
            "total_providers": len(provider_performance),
            "healthy_providers": len([p for p in provider_performance if p.failed_requests == 0]),
            "enterprise_features_enabled": ENTERPRISE_MONITORING
        }
        
    except Exception as e:
        logger.error(f"Failed to get dashboard summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取仪表板摘要失败: {str(e)}"
        )


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """WebSocket端点用于实时监控数据推送"""
    await connection_manager.connect(websocket, user_id)
    
    try:
        # 启动指标推送任务
        async def send_metrics():
            while True:
                try:
                    metrics = await metrics_collector.collect_real_time_metrics()
                    await metrics_collector.check_alerts(metrics)
                    
                    message = json.dumps({
                        "type": "metrics",
                        "data": metrics.dict()
                    })
                    
                    await connection_manager.send_personal_message(message, user_id)
                    await asyncio.sleep(5)  # 每5秒推送一次
                    
                except Exception as e:
                    logger.error(f"Error sending metrics: {e}")
                    break
        
        # 启动推送任务
        metrics_task = asyncio.create_task(send_metrics())
        
        # 保持连接
        while True:
            try:
                data = await websocket.receive_text()
                # 处理客户端消息（如订阅特定指标等）
                logger.info(f"Received WebSocket message from user {user_id}: {data}")
            except WebSocketDisconnect:
                break
            
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        connection_manager.disconnect(websocket, user_id)
        if 'metrics_task' in locals():
            metrics_task.cancel()


@router.get("/export/metrics", summary="导出监控指标")
async def export_metrics(
    format: str = Query(default="json", regex="^(json|csv)$"),
    hours: int = Query(default=24, ge=1, le=168)
):
    """导出监控指标数据"""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # 获取历史数据
        filtered_metrics = [
            m for m in metrics_collector._metrics_history 
            if start_time <= m.timestamp <= end_time
        ]
        
        if format == "json":
            return {
                "metrics": [m.dict() for m in filtered_metrics],
                "exported_at": datetime.now().isoformat(),
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                }
            }
        else:  # CSV
            # 生成CSV数据
            csv_lines = ["timestamp,requests_per_second,average_response_time,error_rate,active_connections,memory_usage_mb,cpu_usage_percent,cache_hit_rate"]
            
            for m in filtered_metrics:
                csv_lines.append(
                    f"{m.timestamp.isoformat()},{m.requests_per_second},{m.average_response_time},"
                    f"{m.error_rate},{m.active_connections},{m.memory_usage_mb},"
                    f"{m.cpu_usage_percent},{m.cache_hit_rate}"
                )
            
            csv_content = "\n".join(csv_lines)
            
            return StreamingResponse(
                iter([csv_content]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=ai_metrics_{int(time.time())}.csv"}
            )
        
    except Exception as e:
        logger.error(f"Failed to export metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出指标失败: {str(e)}"
        )
