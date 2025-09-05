# project/routers/llm/prometheus_monitor.py
"""
LLM模块Prometheus监控集成
提供详细的性能指标收集和导出
"""
import time
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging
import json
import os
from functools import wraps

try:
    from prometheus_client import Counter, Histogram, Gauge, Summary, Info, start_http_server, CollectorRegistry, REGISTRY
    from prometheus_client.core import REGISTRY as DEFAULT_REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # 创建简单的模拟类
    class MockMetric:
        def __init__(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass
        def info(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
    
    Counter = Histogram = Gauge = Summary = Info = MockMetric

from .cache_service import get_llm_cache_service
from .distributed_cache import get_llm_cache

logger = logging.getLogger(__name__)

@dataclass
class PrometheusConfig:
    """Prometheus监控配置"""
    enabled: bool = True
    port: int = 9090  # Prometheus metrics端口（避免与主应用端口8001冲突）
    path: str = "/metrics"
    registry: Optional[Any] = None
    namespace: str = "llm"
    collect_interval: int = 30  # 指标收集间隔（秒）
    
    def __post_init__(self):
        if self.registry is None and PROMETHEUS_AVAILABLE:
            self.registry = REGISTRY

class LLMPrometheusMonitor:
    """LLM Prometheus监控器"""
    
    def __init__(self, config: Optional[PrometheusConfig] = None):
        self.config = config or PrometheusConfig()
        self.cache_service = get_llm_cache_service()
        self.cache = get_llm_cache()
        
        # 初始化Prometheus指标
        self._init_metrics()
        
        # 内部状态
        self._monitoring_active = False
        self._collection_thread = None
        self._metrics_data = defaultdict(list)
        
        # 性能基线数据
        self._baseline_data = {}
        self._load_baseline()
        
        logger.info(f"LLM Prometheus监控器初始化完成，Prometheus可用: {PROMETHEUS_AVAILABLE}")
    
    def _init_metrics(self):
        """初始化Prometheus指标"""
        namespace = self.config.namespace
        
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus客户端不可用，使用模拟指标")
        
        # === 缓存相关指标 ===
        self.cache_operations_total = Counter(
            f'{namespace}_cache_operations_total',
            'LLM缓存操作总数',
            ['operation', 'result'],
            registry=self.config.registry
        )
        
        self.cache_hit_ratio = Gauge(
            f'{namespace}_cache_hit_ratio',
            'LLM缓存命中率',
            registry=self.config.registry
        )
        
        self.cache_response_time = Histogram(
            f'{namespace}_cache_response_time_seconds',
            'LLM缓存响应时间',
            ['operation'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
            registry=self.config.registry
        )
        
        self.cache_memory_usage = Gauge(
            f'{namespace}_cache_memory_usage_bytes',
            'LLM缓存内存使用量',
            ['cache_type'],
            registry=self.config.registry
        )
        
        # === API相关指标 ===
        self.api_requests_total = Counter(
            f'{namespace}_api_requests_total',
            'LLM API请求总数',
            ['endpoint', 'method', 'status'],
            registry=self.config.registry
        )
        
        self.api_response_time = Histogram(
            f'{namespace}_api_response_time_seconds',
            'LLM API响应时间',
            ['endpoint'],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.config.registry
        )
        
        self.api_errors_total = Counter(
            f'{namespace}_api_errors_total',
            'LLM API错误总数',
            ['endpoint', 'error_type'],
            registry=self.config.registry
        )
        
        # === 配置相关指标 ===
        self.config_updates_total = Counter(
            f'{namespace}_config_updates_total',
            'LLM配置更新总数',
            ['config_type', 'user_id'],
            registry=self.config.registry
        )
        
        self.config_validation_errors = Counter(
            f'{namespace}_config_validation_errors_total',
            'LLM配置验证错误总数',
            ['error_type'],
            registry=self.config.registry
        )
        
        self.active_users = Gauge(
            f'{namespace}_active_users',
            '活跃用户数量',
            registry=self.config.registry
        )
        
        # === 系统健康指标 ===
        self.redis_availability = Gauge(
            f'{namespace}_redis_availability',
            'Redis可用性 (1=可用, 0=不可用)',
            registry=self.config.registry
        )
        
        self.system_health_score = Gauge(
            f'{namespace}_system_health_score',
            'LLM系统健康评分 (0-100)',
            registry=self.config.registry
        )
        
        # === 性能基线指标 ===
        self.baseline_deviation = Gauge(
            f'{namespace}_baseline_deviation_percent',
            '与性能基线的偏差百分比',
            ['metric'],
            registry=self.config.registry
        )
        
        # === 信息指标 ===
        self.build_info = Info(
            f'{namespace}_build_info',
            'LLM模块构建信息',
            registry=self.config.registry
        )
        
        # 设置构建信息
        self.build_info.info({
            'version': '2.0.0',
            'cache_backend': 'redis+memory',
            'monitoring_enabled': str(self.config.enabled)
        })
    
    def start_monitoring(self):
        """启动监控"""
        if not self.config.enabled:
            logger.info("Prometheus监控已禁用")
            return
        
        if self._monitoring_active:
            logger.warning("监控已在运行")
            return
        
        self._monitoring_active = True
        
        # 启动Prometheus HTTP服务器
        if PROMETHEUS_AVAILABLE:
            try:
                start_http_server(self.config.port, registry=self.config.registry)
                logger.info(f"Prometheus监控服务已启动，端口: {self.config.port}")
            except Exception as e:
                logger.error(f"启动Prometheus服务失败: {e}")
        
        # 启动指标收集线程
        self._collection_thread = threading.Thread(target=self._collect_metrics_loop, daemon=True)
        self._collection_thread.start()
        
        logger.info("LLM Prometheus监控已启动")
    
    def stop_monitoring(self):
        """停止监控"""
        self._monitoring_active = False
        if self._collection_thread:
            self._collection_thread.join(timeout=5)
        logger.info("LLM Prometheus监控已停止")
    
    def _collect_metrics_loop(self):
        """指标收集循环"""
        while self._monitoring_active:
            try:
                self._collect_cache_metrics()
                self._collect_system_metrics()
                self._update_baseline_comparison()
                
                time.sleep(self.config.collect_interval)
            except Exception as e:
                logger.error(f"指标收集失败: {e}")
                time.sleep(self.config.collect_interval)
    
    def _collect_cache_metrics(self):
        """收集缓存相关指标"""
        try:
            # 获取缓存统计
            stats = self.cache_service.get_cache_statistics()
            
            # 更新缓存命中率
            hit_rate = stats.get('hit_rate', 0) / 100.0  # 转换为0-1范围
            self.cache_hit_ratio.set(hit_rate)
            
            # 更新Redis可用性
            redis_healthy = 1 if stats.get('redis_healthy', False) else 0
            self.redis_availability.set(redis_healthy)
            
            # 更新内存使用情况
            memory_usage = stats.get('memory_fallback_size', 0) * 1024  # 假设每个条目1KB
            self.cache_memory_usage.labels(cache_type='memory_fallback').set(memory_usage)
            
            # 记录缓存操作
            total_ops = stats.get('hits', 0) + stats.get('misses', 0)
            if total_ops > 0:
                # 这里可以添加更详细的操作统计
                pass
                
        except Exception as e:
            logger.error(f"收集缓存指标失败: {e}")
    
    def _collect_system_metrics(self):
        """收集系统健康指标"""
        try:
            # 计算系统健康评分
            health_score = self._calculate_health_score()
            self.system_health_score.set(health_score)
            
        except Exception as e:
            logger.error(f"收集系统指标失败: {e}")
    
    def _calculate_health_score(self) -> float:
        """计算系统健康评分"""
        try:
            stats = self.cache_service.get_cache_statistics()
            
            # 基础评分
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
            error_rate = stats.get('errors', 0) / max(stats.get('total_requests', 1), 1)
            if error_rate > 0.15:
                score -= 20
            elif error_rate > 0.05:
                score -= 10
            
            # 响应时间影响 (10%)
            # 这里需要从其他地方获取响应时间数据
            
            return max(0, score)
            
        except Exception as e:
            logger.error(f"计算健康评分失败: {e}")
            return 50.0  # 默认评分
    
    def _load_baseline(self):
        """加载性能基线"""
        baseline_file = "llm_performance_baseline.json"
        try:
            if os.path.exists(baseline_file):
                with open(baseline_file, 'r', encoding='utf-8') as f:
                    self._baseline_data = json.load(f)
                logger.info("性能基线数据加载成功")
            else:
                # 设置默认基线
                self._baseline_data = {
                    'cache_hit_rate': 85.0,
                    'api_response_time_p95': 0.5,
                    'cache_response_time_p95': 0.01,
                    'error_rate': 0.02,
                    'system_health_score': 90.0
                }
                logger.info("使用默认性能基线")
        except Exception as e:
            logger.error(f"加载性能基线失败: {e}")
            self._baseline_data = {}
    
    def save_baseline(self):
        """保存当前性能作为基线"""
        try:
            current_stats = self.cache_service.get_cache_statistics()
            
            baseline = {
                'cache_hit_rate': current_stats.get('hit_rate', 85.0),
                'system_health_score': self._calculate_health_score(),
                'baseline_created': datetime.now().isoformat(),
                'note': '通过Prometheus监控系统创建的基线'
            }
            
            baseline_file = "llm_performance_baseline.json"
            with open(baseline_file, 'w', encoding='utf-8') as f:
                json.dump(baseline, f, ensure_ascii=False, indent=2)
            
            self._baseline_data = baseline
            logger.info(f"性能基线已保存到: {baseline_file}")
            
        except Exception as e:
            logger.error(f"保存性能基线失败: {e}")
    
    def _update_baseline_comparison(self):
        """更新与基线的对比"""
        try:
            if not self._baseline_data:
                return
            
            current_stats = self.cache_service.get_cache_statistics()
            
            # 缓存命中率偏差
            baseline_hit_rate = self._baseline_data.get('cache_hit_rate', 85.0)
            current_hit_rate = current_stats.get('hit_rate', 0)
            hit_rate_deviation = ((current_hit_rate - baseline_hit_rate) / baseline_hit_rate) * 100
            self.baseline_deviation.labels(metric='cache_hit_rate').set(hit_rate_deviation)
            
            # 系统健康评分偏差
            baseline_health = self._baseline_data.get('system_health_score', 90.0)
            current_health = self._calculate_health_score()
            health_deviation = ((current_health - baseline_health) / baseline_health) * 100
            self.baseline_deviation.labels(metric='system_health').set(health_deviation)
            
        except Exception as e:
            logger.error(f"更新基线对比失败: {e}")
    
    # === 指标记录方法 ===
    
    def record_cache_operation(self, operation: str, success: bool, duration: float):
        """记录缓存操作"""
        result = 'success' if success else 'failure'
        self.cache_operations_total.labels(operation=operation, result=result).inc()
        self.cache_response_time.labels(operation=operation).observe(duration)
    
    def record_api_request(self, endpoint: str, method: str, status: int, duration: float):
        """记录API请求"""
        self.api_requests_total.labels(endpoint=endpoint, method=method, status=str(status)).inc()
        self.api_response_time.labels(endpoint=endpoint).observe(duration)
    
    def record_api_error(self, endpoint: str, error_type: str):
        """记录API错误"""
        self.api_errors_total.labels(endpoint=endpoint, error_type=error_type).inc()
    
    def record_config_update(self, config_type: str, user_id: str):
        """记录配置更新"""
        self.config_updates_total.labels(config_type=config_type, user_id=user_id).inc()
    
    def record_validation_error(self, error_type: str):
        """记录验证错误"""
        self.config_validation_errors.labels(error_type=error_type).inc()
    
    def update_active_users(self, count: int):
        """更新活跃用户数"""
        self.active_users.set(count)
    
    # === 监控装饰器 ===
    
    def monitor_api_endpoint(self, endpoint: str, method: str = 'GET'):
        """API端点监控装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                error_occurred = False
                
                try:
                    result = func(*args, **kwargs)
                    status = 200  # 默认成功状态
                    return result
                except Exception as e:
                    error_occurred = True
                    status = 500
                    error_type = type(e).__name__
                    self.record_api_error(endpoint, error_type)
                    raise
                finally:
                    duration = time.time() - start_time
                    self.record_api_request(endpoint, method, status, duration)
            
            return wrapper
        return decorator
    
    def monitor_cache_operation(self, operation: str):
        """缓存操作监控装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    raise
                finally:
                    duration = time.time() - start_time
                    self.record_cache_operation(operation, success, duration)
            
            return wrapper
        return decorator
    
    # === 查询和导出方法 ===
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        try:
            cache_stats = self.cache_service.get_cache_statistics()
            
            summary = {
                'prometheus_enabled': PROMETHEUS_AVAILABLE,
                'monitoring_active': self._monitoring_active,
                'metrics_endpoint': f"http://localhost:{self.config.port}{self.config.path}",
                'current_metrics': {
                    'cache_hit_rate': cache_stats.get('hit_rate', 0),
                    'redis_healthy': cache_stats.get('redis_healthy', False),
                    'system_health_score': self._calculate_health_score(),
                },
                'baseline_data': self._baseline_data,
                'collection_interval': self.config.collect_interval
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"获取指标摘要失败: {e}")
            return {'error': str(e)}
    
    def export_metrics_config(self) -> str:
        """导出Prometheus配置"""
        config = f"""
# Prometheus配置示例 - LLM模块监控
global:
  scrape_interval: {self.config.collect_interval}s

scrape_configs:
  - job_name: 'llm-module'
    static_configs:
      - targets: ['localhost:{self.config.port}']
    scrape_interval: {self.config.collect_interval}s
    metrics_path: '{self.config.path}'
    
rule_files:
  - "llm_alerting_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
"""
        return config
    
    def export_alerting_rules(self) -> str:
        """导出告警规则"""
        rules = f"""
groups:
- name: llm_alerts
  rules:
  
  # 缓存命中率告警
  - alert: LLMCacheHitRateLow
    expr: {self.config.namespace}_cache_hit_ratio < 0.7
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "LLM缓存命中率过低"
      description: "LLM缓存命中率为 {{{{ $value }}}}，低于70%阈值"
  
  - alert: LLMCacheHitRateCritical
    expr: {self.config.namespace}_cache_hit_ratio < 0.5
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "LLM缓存命中率严重过低"
      description: "LLM缓存命中率为 {{{{ $value }}}}，低于50%阈值"
  
  # Redis可用性告警
  - alert: LLMRedisDown
    expr: {self.config.namespace}_redis_availability == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "LLM Redis缓存不可用"
      description: "Redis缓存服务不可用，已降级为内存缓存"
  
  # API响应时间告警
  - alert: LLMAPIResponseTimeSlow
    expr: histogram_quantile(0.95, rate({self.config.namespace}_api_response_time_seconds_bucket[5m])) > 2.0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "LLM API响应时间过长"
      description: "API响应时间95分位数为 {{{{ $value }}}}秒，超过2秒阈值"
  
  # 系统健康评分告警
  - alert: LLMSystemHealthLow
    expr: {self.config.namespace}_system_health_score < 70
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "LLM系统健康评分过低"
      description: "系统健康评分为 {{{{ $value }}}}，低于70分"
  
  # 错误率告警
  - alert: LLMErrorRateHigh
    expr: rate({self.config.namespace}_api_errors_total[5m]) / rate({self.config.namespace}_api_requests_total[5m]) > 0.1
    for: 3m
    labels:
      severity: warning
    annotations:
      summary: "LLM API错误率过高"
      description: "API错误率为 {{{{ $value }}}}，超过10%阈值"
  
  # 性能基线偏差告警
  - alert: LLMPerformanceDeviationHigh
    expr: abs({self.config.namespace}_baseline_deviation_percent) > 20
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "LLM性能偏离基线"
      description: "{{{{ $labels.metric }}}} 偏离基线 {{{{ $value }}}}%，超过20%阈值"
"""
        return rules


# 全局监控实例
_prometheus_monitor = None
_monitor_lock = threading.Lock()

def get_prometheus_monitor() -> LLMPrometheusMonitor:
    """获取Prometheus监控实例（单例模式）"""
    global _prometheus_monitor
    
    if _prometheus_monitor is None:
        with _monitor_lock:
            if _prometheus_monitor is None:
                config = PrometheusConfig(
                    enabled=os.getenv('LLM_PROMETHEUS_ENABLED', 'true').lower() == 'true',
                    port=int(os.getenv('LLM_PROMETHEUS_PORT', '9090')),
                    namespace=os.getenv('LLM_PROMETHEUS_NAMESPACE', 'llm'),
                    collect_interval=int(os.getenv('LLM_PROMETHEUS_INTERVAL', '30'))
                )
                _prometheus_monitor = LLMPrometheusMonitor(config)
    
    return _prometheus_monitor

def start_prometheus_monitoring():
    """启动Prometheus监控"""
    monitor = get_prometheus_monitor()
    monitor.start_monitoring()
    return monitor

def stop_prometheus_monitoring():
    """停止Prometheus监控"""
    global _prometheus_monitor
    if _prometheus_monitor:
        _prometheus_monitor.stop_monitoring()

# 便捷的装饰器导出
def monitor_llm_api(endpoint: str, method: str = 'GET'):
    """LLM API监控装饰器"""
    return get_prometheus_monitor().monitor_api_endpoint(endpoint, method)

def monitor_llm_cache(operation: str):
    """LLM缓存监控装饰器"""
    return get_prometheus_monitor().monitor_cache_operation(operation)

if __name__ == "__main__":
    """测试Prometheus监控"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Prometheus监控")
    parser.add_argument("--port", type=int, default=8001, help="Prometheus端口")
    parser.add_argument("--interval", type=int, default=30, help="收集间隔（秒）")
    parser.add_argument("--export-config", action="store_true", help="导出Prometheus配置")
    parser.add_argument("--export-rules", action="store_true", help="导出告警规则")
    parser.add_argument("--save-baseline", action="store_true", help="保存当前性能基线")
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    if args.export_config:
        monitor = LLMPrometheusMonitor(PrometheusConfig(port=args.port))
        config = monitor.export_metrics_config()
        with open("prometheus.yml", "w") as f:
            f.write(config)
        print("Prometheus配置已导出到 prometheus.yml")
    
    elif args.export_rules:
        monitor = LLMPrometheusMonitor(PrometheusConfig())
        rules = monitor.export_alerting_rules()
        with open("llm_alerting_rules.yml", "w") as f:
            f.write(rules)
        print("告警规则已导出到 llm_alerting_rules.yml")
    
    elif args.save_baseline:
        monitor = get_prometheus_monitor()
        monitor.save_baseline()
        print("性能基线已保存")
    
    else:
        # 启动监控
        config = PrometheusConfig(port=args.port, collect_interval=args.interval)
        monitor = LLMPrometheusMonitor(config)
        monitor.start_monitoring()
        
        try:
            print(f"Prometheus监控已启动:")
            print(f"- 指标端点: http://localhost:{args.port}/metrics")
            print(f"- 收集间隔: {args.interval}秒")
            print("按 Ctrl+C 停止监控")
            
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止监控...")
            monitor.stop_monitoring()
