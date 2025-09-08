# project/utils/monitoring/llm_alert_manager.py
"""
LLM模块告警管理系统
提供智能告警、基线对比和性能监控
"""
import time
import threading
import smtplib
import json
import os
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
from email.mime.text import MIMEText as MimeText
from email.mime.multipart import MIMEMultipart as MimeMultipart
import logging
from enum import Enum
import asyncio
import aiohttp

from project.utils.async_cache.llm_cache_service import get_llm_cache_service
from project.utils.async_cache.llm_distributed_cache import get_llm_cache

logger = logging.getLogger(__name__)

class AlertSeverity(Enum):
    """告警严重级别"""
    INFO = "info"
    WARNING = "warning" 
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class AlertStatus(Enum):
    """告警状态"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    SUPPRESSED = "suppressed"

@dataclass
class AlertRule:
    """告警规则定义"""
    name: str
    description: str
    metric: str
    condition: str  # 例如: "< 0.7", "> 2.0", "== 0"
    threshold: float
    severity: AlertSeverity
    duration: int = 300  # 持续时间（秒）
    enabled: bool = True
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.annotations:
            self.annotations = {
                'summary': f'{self.name} 告警',
                'description': self.description
            }

@dataclass
class Alert:
    """告警实例"""
    rule: AlertRule
    value: float
    timestamp: datetime
    status: AlertStatus = AlertStatus.ACTIVE
    fingerprint: str = ""
    
    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = f"{self.rule.name}_{self.rule.metric}_{int(self.timestamp.timestamp())}"

@dataclass
class AlertConfig:
    """告警配置"""
    enabled: bool = True
    check_interval: int = 30  # 检查间隔（秒）
    
    # 邮件配置
    email_enabled: bool = False
    smtp_server: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    from_email: str = ""
    to_emails: List[str] = field(default_factory=list)
    
    # Webhook配置
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_timeout: int = 10
    
    # 告警抑制配置
    suppress_duration: int = 900  # 告警抑制时间（秒）
    max_alerts_per_hour: int = 10  # 每小时最大告警数
    
    def __post_init__(self):
        # 从环境变量加载配置
        self.enabled = os.getenv('LLM_ALERT_ENABLED', str(self.enabled)).lower() == 'true'
        self.email_enabled = os.getenv('LLM_ALERT_EMAIL_ENABLED', str(self.email_enabled)).lower() == 'true'
        self.webhook_enabled = os.getenv('LLM_ALERT_WEBHOOK_ENABLED', str(self.webhook_enabled)).lower() == 'true'
        
        if self.email_enabled:
            self.smtp_server = os.getenv('LLM_ALERT_SMTP_SERVER', self.smtp_server)
            self.smtp_port = int(os.getenv('LLM_ALERT_SMTP_PORT', str(self.smtp_port)))
            self.smtp_username = os.getenv('LLM_ALERT_SMTP_USERNAME', self.smtp_username)
            self.smtp_password = os.getenv('LLM_ALERT_SMTP_PASSWORD', self.smtp_password)
            self.from_email = os.getenv('LLM_ALERT_FROM_EMAIL', self.from_email)
            to_emails_str = os.getenv('LLM_ALERT_TO_EMAILS', '')
            if to_emails_str:
                self.to_emails = [email.strip() for email in to_emails_str.split(',')]
        
        if self.webhook_enabled:
            self.webhook_url = os.getenv('LLM_ALERT_WEBHOOK_URL', self.webhook_url)

class LLMAlertManager:
    """LLM告警管理器"""
    
    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or AlertConfig()
        self.cache_service = get_llm_cache_service()
        self.cache = get_llm_cache()
        
        # 告警规则
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.suppressed_alerts: Dict[str, datetime] = {}
        self.alert_counts: defaultdict = defaultdict(int)
        
        # 性能基线
        self.baseline_data = {}
        self.baseline_file = "llm_performance_baseline.json"
        
        # 监控状态
        self._monitoring_active = False
        self._monitoring_thread = None
        self._alert_lock = threading.Lock()
        
        # 初始化默认规则
        self._init_default_rules()
        self._load_baseline()
        
        logger.info("🚨 LLM Alert - 告警管理器已初始化")
    
    def _init_default_rules(self):
        """初始化默认告警规则"""
        default_rules = [
            AlertRule(
                name="cache_hit_rate_low",
                description="缓存命中率过低",
                metric="cache_hit_rate",
                condition="<",
                threshold=70.0,
                severity=AlertSeverity.WARNING,
                duration=300,
                annotations={
                    'summary': '缓存命中率过低告警',
                    'description': '缓存命中率低于70%，可能影响系统性能'
                }
            ),
            AlertRule(
                name="cache_hit_rate_critical",
                description="缓存命中率严重过低",
                metric="cache_hit_rate", 
                condition="<",
                threshold=50.0,
                severity=AlertSeverity.CRITICAL,
                duration=120,
                annotations={
                    'summary': '缓存命中率严重过低',
                    'description': '缓存命中率低于50%，严重影响系统性能'
                }
            ),
            AlertRule(
                name="redis_unavailable",
                description="Redis缓存不可用",
                metric="redis_healthy",
                condition="==",
                threshold=0.0,
                severity=AlertSeverity.CRITICAL,
                duration=60,
                annotations={
                    'summary': 'Redis缓存服务不可用',
                    'description': 'Redis缓存服务连接失败，已降级为内存缓存'
                }
            ),
            AlertRule(
                name="system_health_low",
                description="系统健康评分过低",
                metric="system_health_score",
                condition="<",
                threshold=70.0,
                severity=AlertSeverity.WARNING,
                duration=300,
                annotations={
                    'summary': '系统健康评分过低',
                    'description': '系统整体健康评分低于70分，需要检查各项指标'
                }
            ),
            AlertRule(
                name="baseline_deviation_high",
                description="性能偏离基线",
                metric="baseline_deviation",
                condition=">",
                threshold=20.0,
                severity=AlertSeverity.WARNING,
                duration=600,
                annotations={
                    'summary': '性能偏离基线',
                    'description': '关键指标偏离性能基线超过20%'
                }
            ),
            AlertRule(
                name="error_rate_high",
                description="错误率过高",
                metric="error_rate",
                condition=">",
                threshold=5.0,
                severity=AlertSeverity.WARNING,
                duration=180,
                annotations={
                    'summary': 'API错误率过高',
                    'description': 'API错误率超过5%，需要检查系统状态'
                }
            )
        ]
        
        for rule in default_rules:
            self.add_rule(rule)
    
    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.rules[rule.name] = rule
        logger.info(f"添加告警规则: {rule.name}")
    
    def remove_rule(self, rule_name: str):
        """移除告警规则"""
        if rule_name in self.rules:
            del self.rules[rule_name]
            logger.info(f"移除告警规则: {rule_name}")
    
    def start_monitoring(self):
        """启动告警监控"""
        if not self.config.enabled:
            logger.info("告警监控已禁用")
            return
        
        if self._monitoring_active:
            logger.warning("告警监控已在运行")
            return
        
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        
        logger.info("LLM告警监控已启动")
    
    def stop_monitoring(self):
        """停止告警监控"""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
        logger.info("LLM告警监控已停止")
    
    def _monitoring_loop(self):
        """监控循环"""
        last_check_time = {}
        
        while self._monitoring_active:
            try:
                current_time = datetime.now()
                
                # 获取当前指标
                metrics = self._collect_metrics()
                
                # 检查每个规则
                for rule_name, rule in self.rules.items():
                    if not rule.enabled:
                        continue
                    
                    # 检查是否到了检查时间
                    last_check = last_check_time.get(rule_name, current_time - timedelta(seconds=rule.duration))
                    if (current_time - last_check).total_seconds() < self.config.check_interval:
                        continue
                    
                    # 评估规则
                    self._evaluate_rule(rule, metrics, current_time)
                    last_check_time[rule_name] = current_time
                
                # 清理过期的抑制状态
                self._cleanup_suppressions()
                
                time.sleep(self.config.check_interval)
                
            except Exception as e:
                logger.error(f"告警监控循环错误: {e}")
                time.sleep(self.config.check_interval)
    
    def _collect_metrics(self) -> Dict[str, float]:
        """收集当前指标"""
        try:
            # 获取缓存统计
            cache_stats = self.cache_service.get_cache_stats()
            
            # 基础指标
            metrics = {
                'cache_hit_rate': cache_stats.get('hit_rate', 0),
                'redis_healthy': 1.0 if cache_stats.get('redis_healthy', False) else 0.0,
                'system_health_score': self._calculate_health_score(cache_stats),
                'error_rate': self._calculate_error_rate(cache_stats),
                'total_requests': cache_stats.get('hits', 0) + cache_stats.get('misses', 0)
            }
            
            # 计算基线偏差
            if self.baseline_data:
                baseline_deviation = self._calculate_baseline_deviation(metrics)
                metrics['baseline_deviation'] = baseline_deviation
            
            return metrics
            
        except Exception as e:
            logger.error(f"收集指标失败: {e}")
            return {}
    
    def _calculate_health_score(self, stats: Dict) -> float:
        """计算系统健康评分"""
        try:
            score = 100.0
            
            # 缓存命中率影响 (40%)
            hit_rate = stats.get('hit_rate', 0)
            if hit_rate < 50:
                score -= 40
            elif hit_rate < 70:
                score -= 20
            elif hit_rate < 85:
                score -= 10
            
            # Redis可用性影响 (30%)
            if not stats.get('redis_healthy', False):
                score -= 30
            
            # 错误率影响 (20%)
            error_rate = self._calculate_error_rate(stats)
            if error_rate > 15:
                score -= 20
            elif error_rate > 5:
                score -= 10
            
            # 响应时间影响 (10%) - 这里简化处理
            # 实际应该从API响应时间统计中获取
            
            return max(0, score)
            
        except Exception as e:
            logger.error(f"计算健康评分失败: {e}")
            return 50.0
    
    def _calculate_error_rate(self, stats: Dict) -> float:
        """计算错误率"""
        try:
            errors = stats.get('errors', 0)
            total = stats.get('total_requests', 1)
            return (errors / max(total, 1)) * 100
        except:
            return 0.0
    
    def _calculate_baseline_deviation(self, current_metrics: Dict[str, float]) -> float:
        """计算与基线的偏差"""
        try:
            if not self.baseline_data:
                return 0.0
            
            deviations = []
            
            # 关键指标的偏差
            key_metrics = ['cache_hit_rate', 'system_health_score']
            
            for metric in key_metrics:
                if metric in current_metrics and metric in self.baseline_data:
                    baseline_value = self.baseline_data[metric]
                    current_value = current_metrics[metric]
                    
                    if baseline_value > 0:
                        deviation = abs((current_value - baseline_value) / baseline_value) * 100
                        deviations.append(deviation)
            
            return max(deviations) if deviations else 0.0
            
        except Exception as e:
            logger.error(f"计算基线偏差失败: {e}")
            return 0.0
    
    def _evaluate_rule(self, rule: AlertRule, metrics: Dict[str, float], current_time: datetime):
        """评估告警规则"""
        try:
            if rule.metric not in metrics:
                return
            
            value = metrics[rule.metric]
            triggered = self._check_condition(value, rule.condition, rule.threshold)
            
            alert_key = f"{rule.name}_{rule.metric}"
            
            if triggered:
                # 检查是否已有活跃告警
                if alert_key not in self.active_alerts:
                    # 检查是否被抑制
                    if self._is_suppressed(alert_key):
                        return
                    
                    # 检查告警频率限制
                    if not self._check_rate_limit(rule.name):
                        return
                    
                    # 创建新告警
                    alert = Alert(
                        rule=rule,
                        value=value,
                        timestamp=current_time,
                        status=AlertStatus.ACTIVE
                    )
                    
                    self.active_alerts[alert_key] = alert
                    self.alert_history.append(alert)
                    
                    # 发送告警
                    self._send_alert(alert)
                    
                    logger.warning(f"触发告警: {rule.name}, 值: {value}, 阈值: {rule.threshold}")
            
            else:
                # 解决已有告警
                if alert_key in self.active_alerts:
                    alert = self.active_alerts[alert_key]
                    alert.status = AlertStatus.RESOLVED
                    
                    # 发送解决通知
                    self._send_alert_resolved(alert)
                    
                    del self.active_alerts[alert_key]
                    logger.info(f"告警已解决: {rule.name}")
        
        except Exception as e:
            logger.error(f"评估告警规则失败 {rule.name}: {e}")
    
    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        """检查条件是否满足"""
        if condition == '<':
            return value < threshold
        elif condition == '>':
            return value > threshold
        elif condition == '<=':
            return value <= threshold
        elif condition == '>=':
            return value >= threshold
        elif condition == '==':
            return value == threshold
        elif condition == '!=':
            return value != threshold
        else:
            logger.warning(f"未知的条件操作符: {condition}")
            return False
    
    def _is_suppressed(self, alert_key: str) -> bool:
        """检查告警是否被抑制"""
        if alert_key in self.suppressed_alerts:
            suppress_until = self.suppressed_alerts[alert_key]
            if datetime.now() < suppress_until:
                return True
            else:
                del self.suppressed_alerts[alert_key]
        return False
    
    def _check_rate_limit(self, rule_name: str) -> bool:
        """检查告警频率限制"""
        current_hour = datetime.now().hour
        key = f"{rule_name}_{current_hour}"
        
        self.alert_counts[key] += 1
        
        if self.alert_counts[key] > self.config.max_alerts_per_hour:
            logger.warning(f"告警 {rule_name} 超过频率限制")
            return False
        
        return True
    
    def _cleanup_suppressions(self):
        """清理过期的抑制状态"""
        current_time = datetime.now()
        expired_keys = [
            key for key, until_time in self.suppressed_alerts.items()
            if current_time >= until_time
        ]
        
        for key in expired_keys:
            del self.suppressed_alerts[key]
        
        # 清理过期的频率计数
        current_hour = current_time.hour
        expired_count_keys = [
            key for key in self.alert_counts.keys()
            if not key.endswith(str(current_hour))
        ]
        
        for key in expired_count_keys:
            del self.alert_counts[key]
    
    def _send_alert(self, alert: Alert):
        """发送告警"""
        try:
            if self.config.email_enabled:
                self._send_email_alert(alert)
            
            if self.config.webhook_enabled:
                asyncio.run(self._send_webhook_alert(alert))
            
        except Exception as e:
            logger.error(f"发送告警失败: {e}")
    
    def _send_alert_resolved(self, alert: Alert):
        """发送告警解决通知"""
        try:
            if self.config.email_enabled:
                self._send_email_resolved(alert)
            
            if self.config.webhook_enabled:
                asyncio.run(self._send_webhook_resolved(alert))
            
        except Exception as e:
            logger.error(f"发送告警解决通知失败: {e}")
    
    def _send_email_alert(self, alert: Alert):
        """发送邮件告警"""
        try:
            if not self.config.to_emails:
                return
            
            msg = MimeMultipart()
            msg['From'] = self.config.from_email
            msg['To'] = ', '.join(self.config.to_emails)
            msg['Subject'] = f"[{alert.rule.severity.value.upper()}] {alert.rule.annotations.get('summary', alert.rule.name)}"
            
            body = f"""
LLM模块告警通知

告警名称: {alert.rule.name}
严重级别: {alert.rule.severity.value}
触发时间: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
当前值: {alert.value}
阈值: {alert.rule.threshold}
描述: {alert.rule.annotations.get('description', alert.rule.description)}

请及时检查系统状态。
            """
            
            msg.attach(MimeText(body, 'plain', 'utf-8'))
            
            server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
            server.starttls()
            server.login(self.config.smtp_username, self.config.smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"邮件告警已发送: {alert.rule.name}")
            
        except Exception as e:
            logger.error(f"发送邮件告警失败: {e}")
    
    def _send_email_resolved(self, alert: Alert):
        """发送邮件解决通知"""
        try:
            if not self.config.to_emails:
                return
            
            msg = MimeMultipart()
            msg['From'] = self.config.from_email
            msg['To'] = ', '.join(self.config.to_emails)
            msg['Subject'] = f"[RESOLVED] {alert.rule.annotations.get('summary', alert.rule.name)}"
            
            body = f"""
LLM模块告警解决通知

告警名称: {alert.rule.name}
解决时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
持续时间: {datetime.now() - alert.timestamp}

告警已自动解决。
            """
            
            msg.attach(MimeText(body, 'plain', 'utf-8'))
            
            server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
            server.starttls()
            server.login(self.config.smtp_username, self.config.smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"邮件解决通知已发送: {alert.rule.name}")
            
        except Exception as e:
            logger.error(f"发送邮件解决通知失败: {e}")
    
    async def _send_webhook_alert(self, alert: Alert):
        """发送Webhook告警"""
        try:
            payload = {
                'status': 'firing',
                'alert': {
                    'name': alert.rule.name,
                    'severity': alert.rule.severity.value,
                    'value': alert.value,
                    'threshold': alert.rule.threshold,
                    'timestamp': alert.timestamp.isoformat(),
                    'fingerprint': alert.fingerprint,
                    'labels': alert.rule.labels,
                    'annotations': alert.rule.annotations
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.config.webhook_timeout)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Webhook告警已发送: {alert.rule.name}")
                    else:
                        logger.error(f"Webhook告警发送失败: HTTP {response.status}")
        
        except Exception as e:
            logger.error(f"发送Webhook告警失败: {e}")
    
    async def _send_webhook_resolved(self, alert: Alert):
        """发送Webhook解决通知"""
        try:
            payload = {
                'status': 'resolved',
                'alert': {
                    'name': alert.rule.name,
                    'fingerprint': alert.fingerprint,
                    'resolved_at': datetime.now().isoformat()
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.config.webhook_timeout)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Webhook解决通知已发送: {alert.rule.name}")
                    else:
                        logger.error(f"Webhook解决通知发送失败: HTTP {response.status}")
        
        except Exception as e:
            logger.error(f"发送Webhook解决通知失败: {e}")
    
    def _load_baseline(self):
        """加载性能基线"""
        try:
            if os.path.exists(self.baseline_file):
                with open(self.baseline_file, 'r', encoding='utf-8') as f:
                    self.baseline_data = json.load(f)
                logger.info("性能基线数据加载成功")
            else:
                logger.info("未找到性能基线文件，将使用默认值")
        except Exception as e:
            logger.error(f"加载性能基线失败: {e}")
    
    def save_baseline(self):
        """保存当前性能作为基线"""
        try:
            metrics = self._collect_metrics()
            
            baseline = {
                'cache_hit_rate': metrics.get('cache_hit_rate', 85.0),
                'system_health_score': metrics.get('system_health_score', 90.0),
                'error_rate': metrics.get('error_rate', 2.0),
                'baseline_created': datetime.now().isoformat(),
                'note': '通过告警管理系统创建的基线'
            }
            
            with open(self.baseline_file, 'w', encoding='utf-8') as f:
                json.dump(baseline, f, ensure_ascii=False, indent=2)
            
            self.baseline_data = baseline
            logger.info(f"性能基线已保存到: {self.baseline_file}")
            
        except Exception as e:
            logger.error(f"保存性能基线失败: {e}")
    
    # === 管理接口 ===
    
    def suppress_alert(self, alert_key: str, duration_minutes: int = 15):
        """抑制告警"""
        suppress_until = datetime.now() + timedelta(minutes=duration_minutes)
        self.suppressed_alerts[alert_key] = suppress_until
        logger.info(f"告警已抑制 {duration_minutes} 分钟: {alert_key}")
    
    def acknowledge_alert(self, alert_key: str):
        """确认告警"""
        if alert_key in self.active_alerts:
            self.active_alerts[alert_key].status = AlertStatus.ACKNOWLEDGED
            logger.info(f"告警已确认: {alert_key}")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """获取活跃告警"""
        alerts = []
        for alert in self.active_alerts.values():
            alerts.append({
                'name': alert.rule.name,
                'severity': alert.rule.severity.value,
                'value': alert.value,
                'threshold': alert.rule.threshold,
                'timestamp': alert.timestamp.isoformat(),
                'status': alert.status.value,
                'fingerprint': alert.fingerprint,
                'description': alert.rule.annotations.get('description', ''),
                'summary': alert.rule.annotations.get('summary', '')
            })
        return alerts
    
    def get_alert_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取告警历史"""
        history = []
        recent_alerts = list(self.alert_history)[-limit:]
        
        for alert in recent_alerts:
            history.append({
                'name': alert.rule.name,
                'severity': alert.rule.severity.value,
                'value': alert.value,
                'timestamp': alert.timestamp.isoformat(),
                'status': alert.status.value,
                'fingerprint': alert.fingerprint
            })
        
        return history
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """获取告警统计"""
        stats = {
            'total_rules': len(self.rules),
            'enabled_rules': len([r for r in self.rules.values() if r.enabled]),
            'active_alerts': len(self.active_alerts),
            'suppressed_alerts': len(self.suppressed_alerts),
            'total_history': len(self.alert_history),
            'monitoring_active': self._monitoring_active,
            'config': {
                'email_enabled': self.config.email_enabled,
                'webhook_enabled': self.config.webhook_enabled,
                'check_interval': self.config.check_interval,
                'max_alerts_per_hour': self.config.max_alerts_per_hour
            },
            'baseline_available': bool(self.baseline_data)
        }
        
        # 按严重级别统计
        severity_counts = defaultdict(int)
        for alert in self.active_alerts.values():
            severity_counts[alert.rule.severity.value] += 1
        stats['alerts_by_severity'] = dict(severity_counts)
        
        return stats


# 全局告警管理器实例
_alert_manager = None
_alert_lock = threading.Lock()

def get_alert_manager() -> LLMAlertManager:
    """获取告警管理器实例（单例模式）"""
    global _alert_manager
    
    if _alert_manager is None:
        with _alert_lock:
            if _alert_manager is None:
                _alert_manager = LLMAlertManager()
    
    return _alert_manager

def start_alert_monitoring():
    """启动告警监控"""
    manager = get_alert_manager()
    manager.start_monitoring()
    return manager

def stop_alert_monitoring():
    """停止告警监控"""
    global _alert_manager
    if _alert_manager:
        _alert_manager.stop_monitoring()
