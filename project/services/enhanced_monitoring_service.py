# project/services/enhanced_monitoring_service.py
"""
增强监控服务 - 整合系统监控、告警和自动化运维
从 routers/knowledge/monitoring_alerting.py 重构而来
与现有的 ai_monitoring_service.py 配合工作
"""

import asyncio
import json
import time
import logging
import psutil
import redis
from typing import Dict, List, Optional, Any, Callable, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
import threading
from collections import defaultdict, deque
import smtplib
import subprocess
import os
import aiofiles
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import yaml
import schedule
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

class AlertLevel(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AlertStatus(str, Enum):
    """告警状态"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"

class MetricType(str, Enum):
    """指标类型"""
    COUNTER = "counter"      # 计数器
    GAUGE = "gauge"         # 仪表盘
    HISTOGRAM = "histogram"  # 直方图
    SUMMARY = "summary"     # 汇总

@dataclass
class Alert:
    """告警信息"""
    alert_id: str
    name: str
    level: AlertLevel
    status: AlertStatus
    message: str
    metric_name: str
    current_value: float
    threshold_value: float
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    acknowledgment_by: Optional[str] = None
    metadata: Dict[str, Any] = None

@dataclass
class MetricThreshold:
    """指标阈值"""
    metric_name: str
    warning_threshold: float
    error_threshold: float
    critical_threshold: float
    comparison_type: str = "greater"  # greater, less, equal
    enabled: bool = True

@dataclass
class SystemMetric:
    """系统指标"""
    name: str
    value: float
    timestamp: datetime
    metric_type: MetricType
    tags: Dict[str, str] = None

class EnhancedMonitoringService:
    """增强监控服务"""
    
    def __init__(self, redis_url: str = None, config_file: str = None):
        self.redis_url = redis_url or "redis://localhost:6379/0"
        self.redis_client = None
        self.config = self._load_config(config_file)
        self.thresholds = {}
        self.active_alerts = {}
        self.metrics_history = deque(maxlen=10000)
        self.notification_handlers = []
        self.is_monitoring = False
        
    async def initialize(self):
        """初始化监控系统"""
        try:
            # 连接Redis
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            
            # 加载阈值配置
            await self._load_thresholds()
            
            # 注册默认通知处理器
            await self._setup_notification_handlers()
            
            # 启动监控
            await self.start_monitoring()
            
            logger.info("增强监控系统初始化完成")
            
        except Exception as e:
            logger.error(f"初始化增强监控系统失败: {e}")
            raise

    async def start_monitoring(self):
        """开始监控"""
        if self.is_monitoring:
            return
            
        self.is_monitoring = True
        
        # 启动监控任务
        asyncio.create_task(self._monitor_system_metrics())
        asyncio.create_task(self._check_alert_conditions())
        asyncio.create_task(self._cleanup_old_data())
        
        logger.info("系统监控已启动")

    async def stop_monitoring(self):
        """停止监控"""
        self.is_monitoring = False
        logger.info("系统监控已停止")

    async def add_metric_threshold(self, threshold: MetricThreshold):
        """添加指标阈值"""
        self.thresholds[threshold.metric_name] = threshold
        
        # 保存到Redis
        await self.redis_client.hset(
            "monitoring:thresholds",
            threshold.metric_name,
            json.dumps(asdict(threshold))
        )
        
        logger.info(f"添加指标阈值: {threshold.metric_name}")

    async def record_metric(self, metric: SystemMetric):
        """记录指标"""
        # 存储到Redis
        await self.redis_client.lpush(
            f"metrics:{metric.name}",
            json.dumps({
                "value": metric.value,
                "timestamp": metric.timestamp.isoformat(),
                "tags": metric.tags or {}
            })
        )
        
        # 保留最近1000条记录
        await self.redis_client.ltrim(f"metrics:{metric.name}", 0, 999)
        
        # 添加到内存历史
        self.metrics_history.append(metric)

    async def get_metric_history(self, metric_name: str, 
                                time_range: timedelta = None) -> List[Dict[str, Any]]:
        """获取指标历史"""
        if not time_range:
            time_range = timedelta(hours=1)
            
        cutoff_time = datetime.now() - time_range
        
        # 从Redis获取
        raw_data = await self.redis_client.lrange(f"metrics:{metric_name}", 0, -1)
        
        history = []
        for data in raw_data:
            try:
                metric_data = json.loads(data)
                timestamp = datetime.fromisoformat(metric_data["timestamp"])
                
                if timestamp >= cutoff_time:
                    history.append(metric_data)
                    
            except Exception as e:
                logger.error(f"解析指标数据失败: {e}")
                
        return sorted(history, key=lambda x: x["timestamp"], reverse=True)

    async def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        return [alert for alert in self.active_alerts.values() 
                if alert.status == AlertStatus.ACTIVE]

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str):
        """确认告警"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledgment_by = acknowledged_by
            
            # 更新Redis
            await self.redis_client.hset(
                "monitoring:alerts",
                alert_id,
                json.dumps(asdict(alert))
            )
            
            logger.info(f"告警 {alert_id} 已被 {acknowledged_by} 确认")

    async def resolve_alert(self, alert_id: str):
        """解决告警"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now()
            
            # 更新Redis
            await self.redis_client.hset(
                "monitoring:alerts",
                alert_id,
                json.dumps(asdict(alert))
            )
            
            logger.info(f"告警 {alert_id} 已解决")

    async def _monitor_system_metrics(self):
        """监控系统指标"""
        while self.is_monitoring:
            try:
                # CPU使用率
                cpu_usage = psutil.cpu_percent(interval=1)
                await self.record_metric(SystemMetric(
                    name="system.cpu.usage",
                    value=cpu_usage,
                    timestamp=datetime.now(),
                    metric_type=MetricType.GAUGE
                ))
                
                # 内存使用率
                memory = psutil.virtual_memory()
                await self.record_metric(SystemMetric(
                    name="system.memory.usage",
                    value=memory.percent,
                    timestamp=datetime.now(),
                    metric_type=MetricType.GAUGE
                ))
                
                # 磁盘使用率
                disk = psutil.disk_usage('/')
                await self.record_metric(SystemMetric(
                    name="system.disk.usage",
                    value=(disk.used / disk.total) * 100,
                    timestamp=datetime.now(),
                    metric_type=MetricType.GAUGE
                ))
                
                # 应用指标
                await self._collect_application_metrics()
                
                await asyncio.sleep(30)  # 每30秒采集一次
                
            except Exception as e:
                logger.error(f"采集系统指标失败: {e}")
                await asyncio.sleep(60)

    async def _collect_application_metrics(self):
        """采集应用指标"""
        try:
            # Redis连接数
            if self.redis_client:
                redis_info = self.redis_client.info()
                await self.record_metric(SystemMetric(
                    name="app.redis.connected_clients",
                    value=redis_info.get('connected_clients', 0),
                    timestamp=datetime.now(),
                    metric_type=MetricType.GAUGE
                ))
                
                await self.record_metric(SystemMetric(
                    name="app.redis.used_memory",
                    value=redis_info.get('used_memory', 0) / (1024**2),  # MB
                    timestamp=datetime.now(),
                    metric_type=MetricType.GAUGE
                ))
            
            # 任务队列长度
            queue_length = await self.redis_client.llen("pending_tasks") or 0
            await self.record_metric(SystemMetric(
                name="app.queue.pending_tasks",
                value=queue_length,
                timestamp=datetime.now(),
                metric_type=MetricType.GAUGE
            ))
            
            # 缓存命中率
            cache_hits = int(await self.redis_client.get("cache:hits") or 0)
            cache_misses = int(await self.redis_client.get("cache:misses") or 0)
            if cache_hits + cache_misses > 0:
                hit_rate = (cache_hits / (cache_hits + cache_misses)) * 100
                await self.record_metric(SystemMetric(
                    name="app.cache.hit_rate",
                    value=hit_rate,
                    timestamp=datetime.now(),
                    metric_type=MetricType.GAUGE
                ))
                
        except Exception as e:
            logger.error(f"采集应用指标失败: {e}")

    async def _check_alert_conditions(self):
        """检查告警条件"""
        while self.is_monitoring:
            try:
                for metric_name, threshold in self.thresholds.items():
                    if not threshold.enabled:
                        continue
                        
                    # 获取最新指标值
                    recent_metrics = await self.get_metric_history(
                        metric_name, timedelta(minutes=5)
                    )
                    
                    if not recent_metrics:
                        continue
                        
                    current_value = recent_metrics[0]["value"]
                    
                    # 检查是否超过阈值
                    alert_level = self._check_threshold(current_value, threshold)
                    
                    if alert_level:
                        await self._trigger_alert(
                            metric_name, current_value, threshold, alert_level
                        )
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"检查告警条件失败: {e}")
                await asyncio.sleep(300)

    def _check_threshold(self, value: float, threshold: MetricThreshold) -> Optional[AlertLevel]:
        """检查阈值"""
        if threshold.comparison_type == "greater":
            if value >= threshold.critical_threshold:
                return AlertLevel.CRITICAL
            elif value >= threshold.error_threshold:
                return AlertLevel.ERROR
            elif value >= threshold.warning_threshold:
                return AlertLevel.WARNING
        elif threshold.comparison_type == "less":
            if value <= threshold.critical_threshold:
                return AlertLevel.CRITICAL
            elif value <= threshold.error_threshold:
                return AlertLevel.ERROR
            elif value <= threshold.warning_threshold:
                return AlertLevel.WARNING
                
        return None

    async def _trigger_alert(self, metric_name: str, current_value: float,
                           threshold: MetricThreshold, alert_level: AlertLevel):
        """触发告警"""
        # 检查是否已存在相同告警
        alert_key = f"{metric_name}_{alert_level}"
        if alert_key in self.active_alerts:
            existing_alert = self.active_alerts[alert_key]
            if existing_alert.status == AlertStatus.ACTIVE:
                return  # 避免重复告警
        
        # 创建新告警
        alert = Alert(
            alert_id=alert_key,
            name=f"{metric_name} 超过 {alert_level} 阈值",
            level=alert_level,
            status=AlertStatus.ACTIVE,
            message=f"指标 {metric_name} 当前值 {current_value:.2f} 超过 {alert_level} 阈值",
            metric_name=metric_name,
            current_value=current_value,
            threshold_value=getattr(threshold, f"{alert_level.value}_threshold"),
            triggered_at=datetime.now()
        )
        
        self.active_alerts[alert_key] = alert
        
        # 保存到Redis
        await self.redis_client.hset(
            "monitoring:alerts",
            alert_key,
            json.dumps(asdict(alert))
        )
        
        # 发送通知
        await self._send_alert_notification(alert)
        
        logger.warning(f"触发告警: {alert.name}")

    async def _send_alert_notification(self, alert: Alert):
        """发送告警通知"""
        for handler in self.notification_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"发送告警通知失败: {e}")

    async def _cleanup_old_data(self):
        """清理旧数据"""
        while self.is_monitoring:
            try:
                # 清理旧的指标数据（保留7天）
                cutoff_time = datetime.now() - timedelta(days=7)
                
                # 清理解决的告警（保留30天）
                alert_cutoff = datetime.now() - timedelta(days=30)
                
                # 从Redis清理旧告警
                all_alerts = await self.redis_client.hgetall("monitoring:alerts")
                for alert_id, alert_data in all_alerts.items():
                    try:
                        alert_dict = json.loads(alert_data)
                        resolved_at = alert_dict.get("resolved_at")
                        if resolved_at:
                            resolved_time = datetime.fromisoformat(resolved_at)
                            if resolved_time < alert_cutoff:
                                await self.redis_client.hdel("monitoring:alerts", alert_id)
                    except Exception as e:
                        logger.error(f"清理告警数据失败: {e}")
                
                await asyncio.sleep(3600)  # 每小时清理一次
                
            except Exception as e:
                logger.error(f"清理旧数据失败: {e}")
                await asyncio.sleep(7200)

    def _load_config(self, config_file: str = None) -> Dict[str, Any]:
        """加载配置"""
        default_config = {
            "monitoring": {
                "enabled": True,
                "collection_interval": 30,
                "retention_days": 7
            },
            "alerts": {
                "enabled": True,
                "check_interval": 60,
                "email_notifications": True
            },
            "thresholds": {
                "system.cpu.usage": {
                    "warning": 70,
                    "error": 85,
                    "critical": 95
                },
                "system.memory.usage": {
                    "warning": 80,
                    "error": 90,
                    "critical": 95
                },
                "system.disk.usage": {
                    "warning": 80,
                    "error": 90,
                    "critical": 95
                }
            }
        }
        
        # 尝试加载项目级配置文件
        config_paths = [
            config_file,
            "project/config/enhanced_monitoring_config.yaml",
            "../config/enhanced_monitoring_config.yaml"
        ]
        
        for config_path in config_paths:
            if config_path and os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        custom_config = yaml.safe_load(f)
                        default_config.update(custom_config)
                        logger.info(f"已加载监控配置文件: {config_path}")
                        break
                except Exception as e:
                    logger.error(f"加载配置文件 {config_path} 失败: {e}")
        
        return default_config

    async def _load_thresholds(self):
        """加载阈值配置"""
        # 从配置文件加载默认阈值
        for metric_name, thresholds in self.config.get("thresholds", {}).items():
            threshold = MetricThreshold(
                metric_name=metric_name,
                warning_threshold=thresholds["warning"],
                error_threshold=thresholds["error"],
                critical_threshold=thresholds["critical"]
            )
            self.thresholds[metric_name] = threshold
        
        # 从Redis加载自定义阈值
        try:
            saved_thresholds = await self.redis_client.hgetall("monitoring:thresholds")
            for metric_name, threshold_data in saved_thresholds.items():
                threshold_dict = json.loads(threshold_data)
                threshold = MetricThreshold(**threshold_dict)
                self.thresholds[metric_name] = threshold
        except Exception as e:
            logger.error(f"加载Redis阈值配置失败: {e}")

    async def _setup_notification_handlers(self):
        """设置通知处理器"""
        # 添加日志通知处理器
        self.notification_handlers.append(self._log_alert_handler)
        
        # 如果配置了邮件通知，添加邮件处理器
        if self.config.get("alerts", {}).get("email_notifications"):
            self.notification_handlers.append(self._email_alert_handler)

    async def _log_alert_handler(self, alert: Alert):
        """日志告警处理器"""
        logger.warning(f"[ALERT] {alert.level.upper()}: {alert.message}")

    async def _email_alert_handler(self, alert: Alert):
        """邮件告警处理器"""
        # 这里应该实现邮件发送逻辑
        # 暂时只记录日志
        logger.info(f"应该发送邮件告警: {alert.name}")

# 创建全局实例
enhanced_monitoring_service = EnhancedMonitoringService()

# 便捷函数
async def init_enhanced_monitoring(redis_url: str = None, config_file: str = None):
    """初始化增强监控系统"""
    if redis_url:
        enhanced_monitoring_service.redis_url = redis_url
    await enhanced_monitoring_service.initialize()

async def record_system_metric(name: str, value: float, metric_type: MetricType = MetricType.GAUGE,
                              tags: Dict[str, str] = None):
    """记录系统指标"""
    metric = SystemMetric(
        name=name,
        value=value,
        timestamp=datetime.now(),
        metric_type=metric_type,
        tags=tags
    )
    await enhanced_monitoring_service.record_metric(metric)

async def add_monitoring_threshold(metric_name: str, warning: float, error: float, critical: float):
    """添加监控阈值"""
    threshold = MetricThreshold(
        metric_name=metric_name,
        warning_threshold=warning,
        error_threshold=error,
        critical_threshold=critical
    )
    await enhanced_monitoring_service.add_metric_threshold(threshold)
