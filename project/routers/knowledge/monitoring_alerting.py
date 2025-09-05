# project/routers/knowledge/monitoring_alerting.py
"""
监控告警模块 - 完善的系统监控、告警和自动化运维
提供实时监控、智能告警、自动故障恢复等功能
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
    SUMMARY = "summary"     # 摘要

@dataclass
class Alert:
    """告警信息"""
    alert_id: str
    title: str
    description: str
    level: AlertLevel
    status: AlertStatus
    source: str
    metric_name: str
    current_value: float
    threshold: float
    timestamp: datetime
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    auto_resolve: bool = False
    tags: Dict[str, str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'alert_id': self.alert_id,
            'title': self.title,
            'description': self.description,
            'level': self.level,
            'status': self.status,
            'source': self.source,
            'metric_name': self.metric_name,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'timestamp': self.timestamp.isoformat(),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'acknowledged_by': self.acknowledged_by,
            'auto_resolve': self.auto_resolve,
            'tags': self.tags or {}
        }

@dataclass
class MetricThreshold:
    """指标阈值"""
    metric_name: str
    warning_threshold: Optional[float] = None
    error_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    comparison: str = "gt"  # gt, lt, eq, ge, le
    duration: int = 60  # 持续时间（秒）
    enabled: bool = True

class SystemMonitor:
    """系统监控器"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.metrics = defaultdict(deque)
        self.is_running = False
        self.monitor_thread = None
        self.collect_interval = 30  # 采集间隔（秒）
        
    def start_monitoring(self):
        """启动监控"""
        if self.is_running:
            return
            
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("系统监控已启动")
        
    def stop_monitoring(self):
        """停止监控"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("系统监控已停止")
        
    def _monitor_loop(self):
        """监控主循环"""
        while self.is_running:
            try:
                self._collect_system_metrics()
                self._collect_application_metrics()
                time.sleep(self.collect_interval)
            except Exception as e:
                logger.error(f"监控采集失败: {e}")
                time.sleep(5)
                
    def _collect_system_metrics(self):
        """采集系统指标"""
        timestamp = time.time()
        
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=1)
        self._store_metric("system.cpu.usage", cpu_percent, timestamp)
        
        # 内存使用情况
        memory = psutil.virtual_memory()
        self._store_metric("system.memory.usage", memory.percent, timestamp)
        self._store_metric("system.memory.available", memory.available / (1024**3), timestamp)  # GB
        
        # 磁盘使用情况
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        self._store_metric("system.disk.usage", disk_percent, timestamp)
        self._store_metric("system.disk.free", disk.free / (1024**3), timestamp)  # GB
        
        # 网络I/O
        network = psutil.net_io_counters()
        self._store_metric("system.network.bytes_sent", network.bytes_sent, timestamp)
        self._store_metric("system.network.bytes_recv", network.bytes_recv, timestamp)
        
        # 进程数
        process_count = len(psutil.pids())
        self._store_metric("system.process.count", process_count, timestamp)
        
        # 负载平均值（Unix系统）
        try:
            load_avg = os.getloadavg()
            self._store_metric("system.load.1min", load_avg[0], timestamp)
            self._store_metric("system.load.5min", load_avg[1], timestamp)
            self._store_metric("system.load.15min", load_avg[2], timestamp)
        except (AttributeError, OSError):
            pass  # Windows系统不支持
            
    def _collect_application_metrics(self):
        """采集应用指标"""
        timestamp = time.time()
        
        try:
            # Redis连接数
            redis_info = self.redis_client.info()
            self._store_metric("app.redis.connected_clients", redis_info.get('connected_clients', 0), timestamp)
            self._store_metric("app.redis.used_memory", redis_info.get('used_memory', 0) / (1024**2), timestamp)  # MB
            
            # 任务队列长度
            queue_length = self.redis_client.llen("pending_tasks") or 0
            self._store_metric("app.queue.pending_tasks", queue_length, timestamp)
            
            # 缓存命中率
            cache_hits = int(self.redis_client.get("cache:hits") or 0)
            cache_misses = int(self.redis_client.get("cache:misses") or 0)
            if cache_hits + cache_misses > 0:
                hit_rate = cache_hits / (cache_hits + cache_misses) * 100
                self._store_metric("app.cache.hit_rate", hit_rate, timestamp)
                
        except Exception as e:
            logger.error(f"应用指标采集失败: {e}")
            
    def _store_metric(self, metric_name: str, value: float, timestamp: float):
        """存储指标数据"""
        metric_data = {
            'value': value,
            'timestamp': timestamp
        }
        
        # 本地存储（用于实时监控）
        self.metrics[metric_name].append(metric_data)
        if len(self.metrics[metric_name]) > 1000:  # 限制内存使用
            self.metrics[metric_name].popleft()
            
        # Redis存储（用于持久化和告警）
        self.redis_client.lpush(
            f"metrics:{metric_name}",
            json.dumps(metric_data)
        )
        self.redis_client.ltrim(f"metrics:{metric_name}", 0, 2879)  # 保留48小时数据（每分钟一个点）
        
    async def get_metric_data(self, metric_name: str, duration: int = 3600) -> List[Dict[str, Any]]:
        """获取指标数据"""
        end_time = time.time()
        start_time = end_time - duration
        
        # 从Redis获取数据
        data = self.redis_client.lrange(f"metrics:{metric_name}", 0, -1)
        
        metrics = []
        for item in data:
            try:
                metric = json.loads(item)
                if metric['timestamp'] >= start_time:
                    metrics.append(metric)
            except json.JSONDecodeError:
                continue
                
        return sorted(metrics, key=lambda x: x['timestamp'])
        
    async def get_current_metrics(self) -> Dict[str, float]:
        """获取当前指标值"""
        current_metrics = {}
        
        for metric_name, metric_queue in self.metrics.items():
            if metric_queue:
                current_metrics[metric_name] = metric_queue[-1]['value']
                
        return current_metrics

class AlertManager:
    """告警管理器"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.thresholds = {}
        self.notification_channels = []
        self.alert_rules = []
        self.active_alerts = {}
        self.suppression_rules = []
        
    def add_threshold(self, threshold: MetricThreshold):
        """添加告警阈值"""
        self.thresholds[threshold.metric_name] = threshold
        
    def add_notification_channel(self, channel: 'NotificationChannel'):
        """添加通知渠道"""
        self.notification_channels.append(channel)
        
    async def check_alerts(self, metrics: Dict[str, float]):
        """检查告警"""
        current_time = datetime.now()
        
        for metric_name, current_value in metrics.items():
            threshold = self.thresholds.get(metric_name)
            if not threshold or not threshold.enabled:
                continue
                
            # 检查各级别阈值
            alert_level = self._evaluate_threshold(current_value, threshold)
            
            if alert_level:
                alert_id = f"{metric_name}_{alert_level}"
                
                # 检查是否已有活跃告警
                if alert_id in self.active_alerts:
                    # 更新现有告警
                    alert = self.active_alerts[alert_id]
                    alert.current_value = current_value
                else:
                    # 创建新告警
                    alert = Alert(
                        alert_id=alert_id,
                        title=f"{metric_name} {alert_level.upper()} 告警",
                        description=self._generate_alert_description(metric_name, current_value, threshold, alert_level),
                        level=alert_level,
                        status=AlertStatus.ACTIVE,
                        source="system_monitor",
                        metric_name=metric_name,
                        current_value=current_value,
                        threshold=self._get_threshold_value(threshold, alert_level),
                        timestamp=current_time,
                        auto_resolve=True
                    )
                    
                    self.active_alerts[alert_id] = alert
                    
                    # 发送通知
                    await self._send_notification(alert)
                    
                    # 存储到Redis
                    await self._store_alert(alert)
                    
            else:
                # 检查是否需要自动解决告警
                await self._auto_resolve_alerts(metric_name, current_value)
                
    def _evaluate_threshold(self, value: float, threshold: MetricThreshold) -> Optional[AlertLevel]:
        """评估阈值"""
        thresholds = [
            (threshold.critical_threshold, AlertLevel.CRITICAL),
            (threshold.error_threshold, AlertLevel.ERROR),
            (threshold.warning_threshold, AlertLevel.WARNING)
        ]
        
        for threshold_value, level in thresholds:
            if threshold_value is None:
                continue
                
            if self._compare_value(value, threshold_value, threshold.comparison):
                return level
                
        return None
        
    def _compare_value(self, value: float, threshold: float, comparison: str) -> bool:
        """比较值"""
        if comparison == "gt":
            return value > threshold
        elif comparison == "lt":
            return value < threshold
        elif comparison == "ge":
            return value >= threshold
        elif comparison == "le":
            return value <= threshold
        elif comparison == "eq":
            return value == threshold
        return False
        
    def _get_threshold_value(self, threshold: MetricThreshold, level: AlertLevel) -> float:
        """获取对应级别的阈值"""
        if level == AlertLevel.CRITICAL:
            return threshold.critical_threshold
        elif level == AlertLevel.ERROR:
            return threshold.error_threshold
        elif level == AlertLevel.WARNING:
            return threshold.warning_threshold
        return 0.0
        
    def _generate_alert_description(self, metric_name: str, current_value: float, 
                                  threshold: MetricThreshold, level: AlertLevel) -> str:
        """生成告警描述"""
        threshold_value = self._get_threshold_value(threshold, level)
        
        return (f"指标 {metric_name} 当前值 {current_value:.2f} "
                f"{'超过' if threshold.comparison.startswith('g') else '低于'} "
                f"{level.upper()} 阈值 {threshold_value}")
        
    async def _auto_resolve_alerts(self, metric_name: str, current_value: float):
        """自动解决告警"""
        alerts_to_resolve = []
        
        for alert_id, alert in self.active_alerts.items():
            if alert.metric_name == metric_name and alert.auto_resolve:
                threshold = self.thresholds.get(metric_name)
                if threshold:
                    # 检查是否回到正常范围
                    if not self._evaluate_threshold(current_value, threshold):
                        alert.status = AlertStatus.RESOLVED
                        alert.resolved_at = datetime.now()
                        alerts_to_resolve.append(alert_id)
                        
                        # 发送解决通知
                        await self._send_resolution_notification(alert)
                        
        # 移除已解决的告警
        for alert_id in alerts_to_resolve:
            del self.active_alerts[alert_id]
            
    async def _send_notification(self, alert: Alert):
        """发送告警通知"""
        for channel in self.notification_channels:
            try:
                await channel.send_alert(alert)
            except Exception as e:
                logger.error(f"发送告警通知失败 ({channel.__class__.__name__}): {e}")
                
    async def _send_resolution_notification(self, alert: Alert):
        """发送解决通知"""
        for channel in self.notification_channels:
            try:
                await channel.send_resolution(alert)
            except Exception as e:
                logger.error(f"发送解决通知失败 ({channel.__class__.__name__}): {e}")
                
    async def _store_alert(self, alert: Alert):
        """存储告警"""
        await self.redis_client.hset(
            f"alert:{alert.alert_id}",
            mapping=alert.to_dict()
        )
        
        # 添加到活跃告警列表
        await self.redis_client.sadd("active_alerts", alert.alert_id)
        
    async def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        alert_ids = await self.redis_client.smembers("active_alerts")
        alerts = []
        
        for alert_id in alert_ids:
            alert_data = await self.redis_client.hgetall(f"alert:{alert_id}")
            if alert_data:
                alert_data['timestamp'] = datetime.fromisoformat(alert_data['timestamp'])
                if alert_data.get('resolved_at'):
                    alert_data['resolved_at'] = datetime.fromisoformat(alert_data['resolved_at'])
                    
                alert = Alert(**alert_data)
                alerts.append(alert)
                
        return alerts
        
    async def acknowledge_alert(self, alert_id: str, user: str):
        """确认告警"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].status = AlertStatus.ACKNOWLEDGED
            self.active_alerts[alert_id].acknowledged_by = user
            
            # 更新Redis
            await self.redis_client.hset(
                f"alert:{alert_id}",
                mapping={
                    'status': AlertStatus.ACKNOWLEDGED,
                    'acknowledged_by': user
                }
            )

class NotificationChannel:
    """通知渠道基类"""
    
    async def send_alert(self, alert: Alert):
        """发送告警通知"""
        raise NotImplementedError
        
    async def send_resolution(self, alert: Alert):
        """发送解决通知"""
        raise NotImplementedError

class EmailNotificationChannel(NotificationChannel):
    """邮件通知渠道"""
    
    def __init__(self, smtp_server: str, smtp_port: int, username: str, 
                 password: str, recipients: List[str]):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.recipients = recipients
        
    async def send_alert(self, alert: Alert):
        """发送告警邮件"""
        subject = f"[{alert.level.upper()}] {alert.title}"
        
        body = f"""
告警详情:
- 告警ID: {alert.alert_id}
- 告警级别: {alert.level.upper()}
- 指标名称: {alert.metric_name}
- 当前值: {alert.current_value:.2f}
- 阈值: {alert.threshold:.2f}
- 时间: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- 描述: {alert.description}

请及时处理！
        """
        
        await self._send_email(subject, body)
        
    async def send_resolution(self, alert: Alert):
        """发送解决邮件"""
        subject = f"[RESOLVED] {alert.title}"
        
        body = f"""
告警已解决:
- 告警ID: {alert.alert_id}
- 指标名称: {alert.metric_name}
- 解决时间: {alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if alert.resolved_at else 'Unknown'}

告警已自动解决。
        """
        
        await self._send_email(subject, body)
        
    async def _send_email(self, subject: str, body: str):
        """发送邮件"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.username
            msg['To'] = ', '.join(self.recipients)
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
                
        except Exception as e:
            logger.error(f"发送邮件失败: {e}")

class WebhookNotificationChannel(NotificationChannel):
    """Webhook通知渠道"""
    
    def __init__(self, webhook_url: str, headers: Dict[str, str] = None):
        self.webhook_url = webhook_url
        self.headers = headers or {}
        
    async def send_alert(self, alert: Alert):
        """发送告警到Webhook"""
        payload = {
            'type': 'alert',
            'data': alert.to_dict()
        }
        
        await self._send_webhook(payload)
        
    async def send_resolution(self, alert: Alert):
        """发送解决通知到Webhook"""
        payload = {
            'type': 'resolution',
            'data': alert.to_dict()
        }
        
        await self._send_webhook(payload)
        
    async def _send_webhook(self, payload: Dict[str, Any]):
        """发送Webhook"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers=self.headers,
                    timeout=10.0
                )
                
                if response.status_code not in [200, 201, 202]:
                    logger.error(f"Webhook发送失败: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Webhook发送异常: {e}")

class AutoHealer:
    """自动修复器"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.healing_rules = []
        
    def add_healing_rule(self, metric_pattern: str, action: Callable):
        """添加自动修复规则"""
        self.healing_rules.append({
            'pattern': metric_pattern,
            'action': action
        })
        
    async def heal_system(self, alert: Alert):
        """自动修复系统"""
        for rule in self.healing_rules:
            if self._match_pattern(alert.metric_name, rule['pattern']):
                try:
                    await rule['action'](alert)
                    logger.info(f"自动修复已执行: {alert.metric_name}")
                except Exception as e:
                    logger.error(f"自动修复失败: {e}")
                    
    def _match_pattern(self, metric_name: str, pattern: str) -> bool:
        """匹配模式"""
        import fnmatch
        return fnmatch.fnmatch(metric_name, pattern)

# 预定义的自动修复动作
class HealingActions:
    """自动修复动作"""
    
    @staticmethod
    async def restart_service(service_name: str):
        """重启服务"""
        try:
            subprocess.run(['systemctl', 'restart', service_name], check=True)
            logger.info(f"服务 {service_name} 已重启")
        except subprocess.CalledProcessError as e:
            logger.error(f"重启服务 {service_name} 失败: {e}")
            
    @staticmethod
    async def clear_cache(redis_client):
        """清理缓存"""
        try:
            # 清理过期的缓存键
            keys = redis_client.keys("cache:*")
            if keys:
                redis_client.delete(*keys)
            logger.info("缓存已清理")
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
            
    @staticmethod
    async def cleanup_temp_files():
        """清理临时文件"""
        try:
            temp_dirs = ['/tmp', '/var/tmp']
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    # 删除7天前的临时文件
                    subprocess.run([
                        'find', temp_dir, '-type', 'f', '-mtime', '+7', '-delete'
                    ], check=True)
            logger.info("临时文件已清理")
        except subprocess.CalledProcessError as e:
            logger.error(f"清理临时文件失败: {e}")
            
    @staticmethod
    async def free_memory():
        """释放内存"""
        try:
            # 清理页面缓存
            subprocess.run(['sync'], check=True)
            with open('/proc/sys/vm/drop_caches', 'w') as f:
                f.write('3')
            logger.info("内存已释放")
        except Exception as e:
            logger.error(f"释放内存失败: {e}")

class HealthChecker:
    """健康检查器"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.health_checks = []
        
    def add_health_check(self, name: str, check_func: Callable, interval: int = 60):
        """添加健康检查"""
        self.health_checks.append({
            'name': name,
            'func': check_func,
            'interval': interval,
            'last_check': 0
        })
        
    async def run_health_checks(self) -> Dict[str, Any]:
        """运行健康检查"""
        results = {}
        current_time = time.time()
        
        for check in self.health_checks:
            if current_time - check['last_check'] >= check['interval']:
                try:
                    result = await check['func']()
                    results[check['name']] = {
                        'status': 'healthy' if result else 'unhealthy',
                        'timestamp': current_time,
                        'details': result if isinstance(result, dict) else {}
                    }
                    check['last_check'] = current_time
                except Exception as e:
                    results[check['name']] = {
                        'status': 'error',
                        'timestamp': current_time,
                        'error': str(e)
                    }
                    
        # 存储健康检查结果
        await self.redis_client.set(
            "health_check_results",
            json.dumps(results),
            ex=300  # 5分钟过期
        )
        
        return results

# 预定义的健康检查
class HealthChecks:
    """健康检查集合"""
    
    @staticmethod
    async def check_database_connection(db_url: str) -> bool:
        """检查数据库连接"""
        try:
            # 这里需要实际的数据库连接检查
            return True
        except Exception:
            return False
            
    @staticmethod
    async def check_redis_connection(redis_client) -> bool:
        """检查Redis连接"""
        try:
            redis_client.ping()
            return True
        except Exception:
            return False
            
    @staticmethod
    async def check_disk_space() -> Dict[str, Any]:
        """检查磁盘空间"""
        disk = psutil.disk_usage('/')
        free_percent = (disk.free / disk.total) * 100
        
        return {
            'healthy': free_percent > 10,  # 10%以上认为健康
            'free_percent': free_percent,
            'free_gb': disk.free / (1024**3)
        }
        
    @staticmethod
    async def check_memory_usage() -> Dict[str, Any]:
        """检查内存使用"""
        memory = psutil.virtual_memory()
        
        return {
            'healthy': memory.percent < 90,  # 90%以下认为健康
            'usage_percent': memory.percent,
            'available_gb': memory.available / (1024**3)
        }

class MonitoringSystem:
    """监控系统主类"""
    
    def __init__(self, redis_client, config_path: str = None):
        self.redis_client = redis_client
        self.system_monitor = SystemMonitor(redis_client)
        self.alert_manager = AlertManager(redis_client)
        self.auto_healer = AutoHealer(redis_client)
        self.health_checker = HealthChecker(redis_client)
        self.is_running = False
        self.main_loop_task = None
        
        if config_path:
            self.load_config(config_path)
        else:
            self._setup_default_config()
            
    def load_config(self, config_path: str):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            self._setup_thresholds(config.get('thresholds', {}))
            self._setup_notifications(config.get('notifications', {}))
            self._setup_healing_rules(config.get('healing', {}))
            self._setup_health_checks(config.get('health_checks', {}))
            
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self._setup_default_config()
            
    def _setup_default_config(self):
        """设置默认配置"""
        # 默认阈值
        thresholds = [
            MetricThreshold("system.cpu.usage", 70, 85, 95),
            MetricThreshold("system.memory.usage", 80, 90, 95),
            MetricThreshold("system.disk.usage", 80, 90, 95),
            MetricThreshold("app.redis.connected_clients", None, None, 100),
            MetricThreshold("app.queue.pending_tasks", 50, 100, 200),
        ]
        
        for threshold in thresholds:
            self.alert_manager.add_threshold(threshold)
            
        # 默认自动修复规则
        self.auto_healer.add_healing_rule("system.memory.usage", 
                                        lambda alert: HealingActions.free_memory())
        self.auto_healer.add_healing_rule("app.cache.*", 
                                        lambda alert: HealingActions.clear_cache(self.redis_client))
        
        # 默认健康检查
        self.health_checker.add_health_check("redis", 
                                           lambda: HealthChecks.check_redis_connection(self.redis_client))
        self.health_checker.add_health_check("disk", HealthChecks.check_disk_space)
        self.health_checker.add_health_check("memory", HealthChecks.check_memory_usage)
        
    def _setup_thresholds(self, thresholds_config: Dict[str, Any]):
        """设置阈值配置"""
        for metric_name, config in thresholds_config.items():
            threshold = MetricThreshold(
                metric_name=metric_name,
                warning_threshold=config.get('warning'),
                error_threshold=config.get('error'),
                critical_threshold=config.get('critical'),
                comparison=config.get('comparison', 'gt'),
                duration=config.get('duration', 60),
                enabled=config.get('enabled', True)
            )
            self.alert_manager.add_threshold(threshold)
            
    def _setup_notifications(self, notifications_config: Dict[str, Any]):
        """设置通知配置"""
        for channel_name, config in notifications_config.items():
            if channel_name == 'email':
                channel = EmailNotificationChannel(
                    smtp_server=config['smtp_server'],
                    smtp_port=config['smtp_port'],
                    username=config['username'],
                    password=config['password'],
                    recipients=config['recipients']
                )
                self.alert_manager.add_notification_channel(channel)
                
            elif channel_name == 'webhook':
                channel = WebhookNotificationChannel(
                    webhook_url=config['url'],
                    headers=config.get('headers', {})
                )
                self.alert_manager.add_notification_channel(channel)
                
    def _setup_healing_rules(self, healing_config: Dict[str, Any]):
        """设置自动修复规则"""
        for pattern, action_name in healing_config.items():
            if hasattr(HealingActions, action_name):
                action = getattr(HealingActions, action_name)
                self.auto_healer.add_healing_rule(pattern, action)
                
    def _setup_health_checks(self, health_checks_config: Dict[str, Any]):
        """设置健康检查"""
        for check_name, config in health_checks_config.items():
            if hasattr(HealthChecks, config['function']):
                check_func = getattr(HealthChecks, config['function'])
                interval = config.get('interval', 60)
                self.health_checker.add_health_check(check_name, check_func, interval)
                
    async def start(self):
        """启动监控系统"""
        if self.is_running:
            return
            
        self.is_running = True
        self.system_monitor.start_monitoring()
        self.main_loop_task = asyncio.create_task(self._main_loop())
        
        logger.info("监控系统已启动")
        
    async def stop(self):
        """停止监控系统"""
        self.is_running = False
        self.system_monitor.stop_monitoring()
        
        if self.main_loop_task:
            self.main_loop_task.cancel()
            
        logger.info("监控系统已停止")
        
    async def _main_loop(self):
        """主循环"""
        while self.is_running:
            try:
                # 获取当前指标
                current_metrics = await self.system_monitor.get_current_metrics()
                
                # 检查告警
                await self.alert_manager.check_alerts(current_metrics)
                
                # 运行健康检查
                await self.health_checker.run_health_checks()
                
                # 检查是否需要自动修复
                active_alerts = await self.alert_manager.get_active_alerts()
                for alert in active_alerts:
                    if alert.level in [AlertLevel.CRITICAL, AlertLevel.ERROR]:
                        await self.auto_healer.heal_system(alert)
                        
                await asyncio.sleep(30)  # 30秒检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控主循环错误: {e}")
                await asyncio.sleep(10)

# 全局监控系统实例
monitoring_system = None

def init_monitoring_system(redis_client, config_path: str = None) -> MonitoringSystem:
    """初始化监控系统"""
    global monitoring_system
    
    monitoring_system = MonitoringSystem(redis_client, config_path)
    
    logger.info("📡 Monitoring System - 监控告警系统已初始化")
    return monitoring_system

def get_monitoring_system() -> Optional[MonitoringSystem]:
    """获取监控系统实例"""
    return monitoring_system
