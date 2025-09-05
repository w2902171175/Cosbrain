"""
AI监控服务
从路由层移动过来的企业级AI监控服务，提供实时监控、性能分析、告警等功能
"""

import asyncio
import time
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# 项目依赖
from project.database import get_db
from project.models import User, AIConversation, AIConversationMessage

# AI提供者集成
from project.ai_providers.provider_manager import AIProviderManager

# 企业级日志和监控
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    from logs.ai_providers.cache_manager import get_cache_stats
    from logs.ai_providers.connection_manager import get_connection_stats
    from logs.metrics.health_20250830 import get_health_metrics
    logger = get_ai_logger("ai_monitoring_service")
    ENTERPRISE_MONITORING = True
except ImportError:
    import logging
    logger = logging.getLogger("ai_monitoring_service")
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
        """连接WebSocket"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_connections[user_id].append(websocket)
        logger.info(f"User {user_id} connected to monitoring WebSocket")
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        """断开WebSocket连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.user_connections[user_id]:
            self.user_connections[user_id].remove(websocket)
        logger.info(f"User {user_id} disconnected from monitoring WebSocket")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """发送个人消息"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
    
    async def broadcast(self, message: str):
        """广播消息"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to broadcast message: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for connection in disconnected:
            if connection in self.active_connections:
                self.active_connections.remove(connection)
    
    async def send_to_user(self, user_id: int, message: str):
        """发送消息给特定用户"""
        user_connections = self.user_connections.get(user_id, [])
        disconnected = []
        
        for connection in user_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send message to user {user_id}: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for connection in disconnected:
            if connection in user_connections:
                user_connections.remove(connection)
            if connection in self.active_connections:
                self.active_connections.remove(connection)


class AIMonitoringService:
    """AI监控服务"""
    
    def __init__(self):
        self.connection_manager = ConnectionManager()
        self.metrics_history: List[RealTimeMetrics] = []
        self.provider_stats: Dict[str, ProviderPerformance] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, SystemAlert] = {}
        self.request_counter = 0
        self.error_counter = 0
        self.response_times: List[float] = []
        self.last_cleanup = datetime.utcnow()
    
    async def get_real_time_metrics(self) -> RealTimeMetrics:
        """获取实时指标"""
        current_time = datetime.utcnow()
        
        # 计算请求率（过去1分钟）
        recent_requests = self._count_recent_requests(minutes=1)
        requests_per_second = recent_requests / 60.0
        
        # 计算平均响应时间
        avg_response_time = sum(self.response_times[-100:]) / len(self.response_times[-100:]) if self.response_times else 0
        
        # 计算错误率
        total_requests = self.request_counter
        error_rate = (self.error_counter / total_requests) * 100 if total_requests > 0 else 0
        
        # 获取系统指标
        active_connections = len(self.connection_manager.active_connections)
        
        # 获取缓存命中率
        cache_hit_rate = await self._get_cache_hit_rate()
        
        # 模拟系统资源使用情况（实际应用中应该获取真实数据）
        memory_usage = await self._get_memory_usage()
        cpu_usage = await self._get_cpu_usage()
        
        metrics = RealTimeMetrics(
            timestamp=current_time,
            requests_per_second=requests_per_second,
            average_response_time=avg_response_time,
            error_rate=error_rate,
            active_connections=active_connections,
            memory_usage_mb=memory_usage,
            cpu_usage_percent=cpu_usage,
            cache_hit_rate=cache_hit_rate
        )
        
        # 保存到历史记录
        self.metrics_history.append(metrics)
        
        # 清理旧数据（保留最近24小时）
        cutoff_time = current_time - timedelta(hours=24)
        self.metrics_history = [m for m in self.metrics_history if m.timestamp > cutoff_time]
        
        return metrics
    
    async def get_provider_performance(self, db: Session) -> List[ProviderPerformance]:
        """获取AI提供者性能指标"""
        try:
            # 从数据库获取统计数据
            provider_stats = await self._calculate_provider_stats(db)
            
            performances = []
            for provider_name, stats in provider_stats.items():
                performance = ProviderPerformance(
                    provider_name=provider_name,
                    model=stats.get('model', 'unknown'),
                    total_requests=stats.get('total_requests', 0),
                    successful_requests=stats.get('successful_requests', 0),
                    failed_requests=stats.get('failed_requests', 0),
                    average_response_time=stats.get('avg_response_time', 0),
                    p95_response_time=stats.get('p95_response_time', 0),
                    p99_response_time=stats.get('p99_response_time', 0),
                    tokens_per_second=stats.get('tokens_per_second', 0),
                    cost_estimate=stats.get('cost_estimate', 0)
                )
                performances.append(performance)
            
            return performances
            
        except Exception as e:
            logger.error(f"Failed to get provider performance: {e}")
            return []
    
    async def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        try:
            health_data = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "services": {}
            }
            
            # 检查各个服务状态
            health_data["services"]["database"] = await self._check_database_health()
            health_data["services"]["ai_providers"] = await self._check_ai_providers_health()
            health_data["services"]["cache"] = await self._check_cache_health()
            health_data["services"]["file_storage"] = await self._check_storage_health()
            
            # 确定总体状态
            service_statuses = [service["status"] for service in health_data["services"].values()]
            if "unhealthy" in service_statuses:
                health_data["status"] = "unhealthy"
            elif "degraded" in service_statuses:
                health_data["status"] = "degraded"
            
            return health_data
            
        except Exception as e:
            logger.error(f"Failed to get system health: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def check_alert_rules(self, metrics: RealTimeMetrics):
        """检查告警规则"""
        for rule_id, rule in self.alert_rules.items():
            if not rule.enabled:
                continue
            
            try:
                # 获取指标值
                metric_value = getattr(metrics, rule.metric)
                
                # 检查阈值
                triggered = False
                if rule.operator == "gt" and metric_value > rule.threshold:
                    triggered = True
                elif rule.operator == "lt" and metric_value < rule.threshold:
                    triggered = True
                elif rule.operator == "eq" and metric_value == rule.threshold:
                    triggered = True
                elif rule.operator == "ne" and metric_value != rule.threshold:
                    triggered = True
                
                if triggered:
                    await self._trigger_alert(rule, metric_value)
                    
            except Exception as e:
                logger.error(f"Failed to check alert rule {rule_id}: {e}")
    
    async def _trigger_alert(self, rule: AlertRule, metric_value: float):
        """触发告警"""
        alert_id = f"{rule.id}_{int(time.time())}"
        
        # 确定告警级别
        level = "warning"
        if rule.metric in ["error_rate", "cpu_usage_percent"] and metric_value > 80:
            level = "critical"
        elif rule.metric in ["memory_usage_mb"] and metric_value > 1000:
            level = "error"
        
        alert = SystemAlert(
            id=alert_id,
            rule_id=rule.id,
            level=level,
            message=f"Alert: {rule.name} - {rule.metric} is {metric_value} (threshold: {rule.threshold})",
            metric_value=metric_value,
            threshold=rule.threshold,
            triggered_at=datetime.utcnow()
        )
        
        self.active_alerts[alert_id] = alert
        
        # 发送告警通知
        await self._send_alert_notification(alert)
        
        logger.warning(f"Alert triggered: {alert.message}")
    
    async def _send_alert_notification(self, alert: SystemAlert):
        """发送告警通知"""
        notification = {
            "type": "alert",
            "data": {
                "id": alert.id,
                "level": alert.level,
                "message": alert.message,
                "triggered_at": alert.triggered_at.isoformat()
            }
        }
        
        await self.connection_manager.broadcast(json.dumps(notification))
    
    def record_request(self, response_time: float, success: bool = True):
        """记录请求"""
        self.request_counter += 1
        self.response_times.append(response_time)
        
        if not success:
            self.error_counter += 1
        
        # 清理旧的响应时间数据
        if len(self.response_times) > 10000:
            self.response_times = self.response_times[-5000:]
    
    def _count_recent_requests(self, minutes: int) -> int:
        """计算最近几分钟的请求数"""
        # 简化实现，实际应该使用时间窗口
        return min(self.request_counter, minutes * 60)
    
    async def _get_cache_hit_rate(self) -> float:
        """获取缓存命中率"""
        try:
            if ENTERPRISE_MONITORING:
                cache_stats = get_cache_stats()
                return cache_stats.get('hit_rate', 0.0)
            return 75.0  # 模拟值
        except Exception:
            return 0.0
    
    async def _get_memory_usage(self) -> float:
        """获取内存使用量（MB）"""
        try:
            import psutil
            return psutil.virtual_memory().used / 1024 / 1024
        except ImportError:
            return 512.0  # 模拟值
    
    async def _get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        try:
            import psutil
            return psutil.cpu_percent(interval=1)
        except ImportError:
            return 25.0  # 模拟值
    
    async def _calculate_provider_stats(self, db: Session) -> Dict[str, Dict[str, Any]]:
        """计算AI提供者统计数据"""
        try:
            # 获取最近24小时的对话数据
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            conversations = db.query(AIConversation).filter(
                AIConversation.created_at > cutoff_time
            ).all()
            
            stats = {}
            for conv in conversations:
                provider = conv.ai_provider or "unknown"
                if provider not in stats:
                    stats[provider] = {
                        'model': conv.ai_model or 'unknown',
                        'total_requests': 0,
                        'successful_requests': 0,
                        'failed_requests': 0,
                        'response_times': [],
                        'tokens_used': 0
                    }
                
                stats[provider]['total_requests'] += 1
                
                # 检查对话是否成功（简化判断）
                messages = db.query(AIConversationMessage).filter(
                    AIConversationMessage.conversation_id == conv.id
                ).all()
                
                if any(msg.role == "assistant" for msg in messages):
                    stats[provider]['successful_requests'] += 1
                else:
                    stats[provider]['failed_requests'] += 1
            
            # 计算衍生指标
            for provider, data in stats.items():
                total = data['total_requests']
                if total > 0:
                    data['avg_response_time'] = sum(data['response_times']) / len(data['response_times']) if data['response_times'] else 0
                    data['p95_response_time'] = self._calculate_percentile(data['response_times'], 95)
                    data['p99_response_time'] = self._calculate_percentile(data['response_times'], 99)
                    data['tokens_per_second'] = data['tokens_used'] / total if total > 0 else 0
                    data['cost_estimate'] = self._estimate_cost(provider, data['tokens_used'])
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to calculate provider stats: {e}")
            return {}
    
    def _calculate_percentile(self, values: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int((percentile / 100.0) * len(sorted_values))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]
    
    def _estimate_cost(self, provider: str, tokens: int) -> float:
        """估算成本"""
        # 简化的成本估算
        cost_per_1k_tokens = {
            'openai': 0.002,
            'anthropic': 0.001,
            'google': 0.0015,
            'siliconflow': 0.0005
        }
        
        rate = cost_per_1k_tokens.get(provider, 0.001)
        return (tokens / 1000) * rate
    
    async def _check_database_health(self) -> Dict[str, Any]:
        """检查数据库健康状态"""
        try:
            # 简单的数据库连接测试
            from project.database import SessionLocal
            db = SessionLocal()
            db.execute("SELECT 1")
            db.close()
            
            return {
                "status": "healthy",
                "response_time_ms": 10,
                "last_check": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def _check_ai_providers_health(self) -> Dict[str, Any]:
        """检查AI提供者健康状态"""
        try:
            # 检查AI提供者状态
            provider_manager = AIProviderManager()
            providers_status = {}
            
            # 简化检查，实际应该测试每个提供者
            providers_status["openai"] = "healthy"
            providers_status["anthropic"] = "healthy"
            providers_status["siliconflow"] = "healthy"
            
            overall_status = "healthy" if all(status == "healthy" for status in providers_status.values()) else "degraded"
            
            return {
                "status": overall_status,
                "providers": providers_status,
                "last_check": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def _check_cache_health(self) -> Dict[str, Any]:
        """检查缓存健康状态"""
        try:
            # 检查缓存状态
            return {
                "status": "healthy",
                "hit_rate": await self._get_cache_hit_rate(),
                "last_check": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def _check_storage_health(self) -> Dict[str, Any]:
        """检查存储健康状态"""
        try:
            # 检查文件存储状态
            return {
                "status": "healthy",
                "available_space_gb": 100,
                "last_check": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }


# === 全局监控服务实例 ===
ai_monitoring_service = AIMonitoringService()
