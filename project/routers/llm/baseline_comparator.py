# project/routers/llm/baseline_comparator.py
"""
LLM模块性能基线对比系统
提供详细的性能基线管理和对比分析
"""
import json
import os
import time
import statistics
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging
import threading
from pathlib import Path

from .cache_service import get_llm_cache_service
from .distributed_cache import get_llm_cache

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    """性能指标数据"""
    name: str
    value: float
    timestamp: datetime
    unit: str = ""
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'unit': self.unit,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceMetric':
        return cls(
            name=data['name'],
            value=data['value'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            unit=data.get('unit', ''),
            description=data.get('description', '')
        )

@dataclass
class BaselineSnapshot:
    """性能基线快照"""
    name: str
    created_at: datetime
    metrics: Dict[str, PerformanceMetric]
    metadata: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'created_at': self.created_at.isoformat(),
            'metrics': {name: metric.to_dict() for name, metric in self.metrics.items()},
            'metadata': self.metadata,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaselineSnapshot':
        return cls(
            name=data['name'],
            created_at=datetime.fromisoformat(data['created_at']),
            metrics={
                name: PerformanceMetric.from_dict(metric_data)
                for name, metric_data in data['metrics'].items()
            },
            metadata=data.get('metadata', {}),
            description=data.get('description', '')
        )

@dataclass
class ComparisonResult:
    """对比结果"""
    metric_name: str
    baseline_value: float
    current_value: float
    deviation_percent: float
    deviation_absolute: float
    status: str  # 'improved', 'degraded', 'stable'
    significance: str  # 'low', 'medium', 'high', 'critical'
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'metric_name': self.metric_name,
            'baseline_value': self.baseline_value,
            'current_value': self.current_value,
            'deviation_percent': self.deviation_percent,
            'deviation_absolute': self.deviation_absolute,
            'status': self.status,
            'significance': self.significance
        }

class LLMBaselineComparator:
    """LLM性能基线对比器"""
    
    def __init__(self, data_dir: str = "performance_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self.cache_service = get_llm_cache_service()
        self.cache = get_llm_cache()
        
        # 基线存储
        self.baselines: Dict[str, BaselineSnapshot] = {}
        self.current_baseline: Optional[BaselineSnapshot] = None
        
        # 性能历史数据
        self.performance_history: deque = deque(maxlen=10000)
        self.metric_trends: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # 配置
        self.metric_definitions = self._init_metric_definitions()
        self.significance_thresholds = self._init_significance_thresholds()
        
        # 加载数据
        self._load_baselines()
        self._load_performance_history()
        
        logger.info("📊 LLM Baseline - 性能基线对比器已初始化")
    
    def _init_metric_definitions(self) -> Dict[str, Dict[str, Any]]:
        """初始化指标定义"""
        return {
            'cache_hit_rate': {
                'unit': '%',
                'description': '缓存命中率',
                'higher_is_better': True,
                'critical_threshold': 20,  # 偏差超过20%为关键
                'warning_threshold': 10    # 偏差超过10%为警告
            },
            'cache_response_time': {
                'unit': 'ms',
                'description': '缓存响应时间',
                'higher_is_better': False,
                'critical_threshold': 50,
                'warning_threshold': 25
            },
            'api_response_time': {
                'unit': 'ms',
                'description': 'API响应时间',
                'higher_is_better': False,
                'critical_threshold': 100,
                'warning_threshold': 50
            },
            'system_health_score': {
                'unit': '分',
                'description': '系统健康评分',
                'higher_is_better': True,
                'critical_threshold': 20,
                'warning_threshold': 10
            },
            'error_rate': {
                'unit': '%',
                'description': '错误率',
                'higher_is_better': False,
                'critical_threshold': 100,  # 错误率增加100%为关键
                'warning_threshold': 50     # 错误率增加50%为警告
            },
            'memory_usage': {
                'unit': 'MB',
                'description': '内存使用量',
                'higher_is_better': False,
                'critical_threshold': 50,
                'warning_threshold': 25
            },
            'concurrent_requests': {
                'unit': 'req/s',
                'description': '并发请求处理能力',
                'higher_is_better': True,
                'critical_threshold': 30,
                'warning_threshold': 15
            },
            'redis_availability': {
                'unit': '%',
                'description': 'Redis可用性',
                'higher_is_better': True,
                'critical_threshold': 10,
                'warning_threshold': 5
            }
        }
    
    def _init_significance_thresholds(self) -> Dict[str, Dict[str, float]]:
        """初始化显著性阈值"""
        return {
            'low': {'min': 0, 'max': 5},      # 0-5%偏差
            'medium': {'min': 5, 'max': 15},  # 5-15%偏差
            'high': {'min': 15, 'max': 30},   # 15-30%偏差
            'critical': {'min': 30, 'max': float('inf')}  # >30%偏差
        }
    
    def _load_baselines(self):
        """加载基线数据"""
        try:
            baseline_file = self.data_dir / "baselines.json"
            if baseline_file.exists():
                with open(baseline_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for name, baseline_data in data.items():
                    self.baselines[name] = BaselineSnapshot.from_dict(baseline_data)
                
                # 设置当前基线为最新的
                if self.baselines:
                    latest_baseline = max(
                        self.baselines.values(),
                        key=lambda b: b.created_at
                    )
                    self.current_baseline = latest_baseline
                
                logger.info(f"加载了 {len(self.baselines)} 个基线")
            
        except Exception as e:
            logger.error(f"加载基线数据失败: {e}")
    
    def _save_baselines(self):
        """保存基线数据"""
        try:
            baseline_file = self.data_dir / "baselines.json"
            data = {name: baseline.to_dict() for name, baseline in self.baselines.items()}
            
            with open(baseline_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("基线数据已保存")
            
        except Exception as e:
            logger.error(f"保存基线数据失败: {e}")
    
    def _load_performance_history(self):
        """加载性能历史数据"""
        try:
            history_file = self.data_dir / "performance_history.json"
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for record in data.get('history', []):
                    timestamp = datetime.fromisoformat(record['timestamp'])
                    metrics = record['metrics']
                    
                    self.performance_history.append({
                        'timestamp': timestamp,
                        'metrics': metrics
                    })
                    
                    # 更新趋势数据
                    for metric_name, value in metrics.items():
                        self.metric_trends[metric_name].append({
                            'timestamp': timestamp,
                            'value': value
                        })
                
                logger.info(f"加载了 {len(self.performance_history)} 条历史记录")
            
        except Exception as e:
            logger.error(f"加载性能历史数据失败: {e}")
    
    def _save_performance_history(self):
        """保存性能历史数据"""
        try:
            history_file = self.data_dir / "performance_history.json"
            
            # 转换为可序列化格式
            history_data = []
            for record in list(self.performance_history)[-1000:]:  # 只保存最近1000条
                history_data.append({
                    'timestamp': record['timestamp'].isoformat(),
                    'metrics': record['metrics']
                })
            
            data = {
                'history': history_data,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info("性能历史数据已保存")
            
        except Exception as e:
            logger.error(f"保存性能历史数据失败: {e}")
    
    def collect_current_metrics(self) -> Dict[str, PerformanceMetric]:
        """收集当前性能指标"""
        try:
            current_time = datetime.now()
            metrics = {}
            
            # 获取缓存统计
            cache_stats = self.cache_service.get_cache_statistics()
            
            # 基础性能指标
            metrics['cache_hit_rate'] = PerformanceMetric(
                name='cache_hit_rate',
                value=cache_stats.get('hit_rate', 0),
                timestamp=current_time,
                unit='%',
                description='缓存命中率'
            )
            
            metrics['redis_availability'] = PerformanceMetric(
                name='redis_availability',
                value=100.0 if cache_stats.get('redis_healthy', False) else 0.0,
                timestamp=current_time,
                unit='%',
                description='Redis可用性'
            )
            
            metrics['system_health_score'] = PerformanceMetric(
                name='system_health_score',
                value=self._calculate_health_score(cache_stats),
                timestamp=current_time,
                unit='分',
                description='系统健康评分'
            )
            
            metrics['error_rate'] = PerformanceMetric(
                name='error_rate',
                value=self._calculate_error_rate(cache_stats),
                timestamp=current_time,
                unit='%',
                description='错误率'
            )
            
            # 模拟一些其他指标（实际应该从真实数据源获取）
            metrics['cache_response_time'] = PerformanceMetric(
                name='cache_response_time',
                value=self._estimate_cache_response_time(),
                timestamp=current_time,
                unit='ms',
                description='缓存响应时间'
            )
            
            metrics['api_response_time'] = PerformanceMetric(
                name='api_response_time',
                value=self._estimate_api_response_time(),
                timestamp=current_time,
                unit='ms',
                description='API响应时间'
            )
            
            metrics['memory_usage'] = PerformanceMetric(
                name='memory_usage',
                value=self._estimate_memory_usage(cache_stats),
                timestamp=current_time,
                unit='MB',
                description='内存使用量'
            )
            
            # 更新历史记录
            metric_values = {name: metric.value for name, metric in metrics.items()}
            self.performance_history.append({
                'timestamp': current_time,
                'metrics': metric_values
            })
            
            # 更新趋势数据
            for name, metric in metrics.items():
                self.metric_trends[name].append({
                    'timestamp': current_time,
                    'value': metric.value
                })
            
            return metrics
            
        except Exception as e:
            logger.error(f"收集当前指标失败: {e}")
            return {}
    
    def _calculate_health_score(self, stats: Dict) -> float:
        """计算系统健康评分"""
        try:
            score = 100.0
            
            # 缓存命中率影响
            hit_rate = stats.get('hit_rate', 0)
            if hit_rate < 50:
                score -= 40
            elif hit_rate < 70:
                score -= 20
            elif hit_rate < 85:
                score -= 10
            
            # Redis可用性影响
            if not stats.get('redis_healthy', False):
                score -= 30
            
            # 错误率影响
            error_rate = self._calculate_error_rate(stats)
            if error_rate > 15:
                score -= 20
            elif error_rate > 5:
                score -= 10
            
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
    
    def _estimate_cache_response_time(self) -> float:
        """估算缓存响应时间"""
        # 实际应该从监控系统获取真实数据
        # 这里提供一个简单的估算
        try:
            cache_stats = self.cache_service.get_cache_statistics()
            hit_rate = cache_stats.get('hit_rate', 85)
            
            # 命中率越高，响应时间越低
            if hit_rate > 90:
                return 5.0  # 5ms
            elif hit_rate > 80:
                return 8.0  # 8ms
            elif hit_rate > 60:
                return 15.0  # 15ms
            else:
                return 25.0  # 25ms
        except:
            return 10.0
    
    def _estimate_api_response_time(self) -> float:
        """估算API响应时间"""
        # 实际应该从API监控获取真实数据
        try:
            cache_stats = self.cache_service.get_cache_statistics()
            hit_rate = cache_stats.get('hit_rate', 85)
            redis_healthy = cache_stats.get('redis_healthy', True)
            
            base_time = 100.0  # 基础响应时间100ms
            
            # 缓存命中率影响
            if hit_rate > 90:
                base_time *= 0.5
            elif hit_rate > 70:
                base_time *= 0.7
            elif hit_rate < 50:
                base_time *= 1.5
            
            # Redis可用性影响
            if not redis_healthy:
                base_time *= 1.3
            
            return base_time
        except:
            return 150.0
    
    def _estimate_memory_usage(self, stats: Dict) -> float:
        """估算内存使用量"""
        try:
            # 基于缓存统计估算内存使用
            fallback_size = stats.get('memory_fallback_size', 0)
            base_memory = 50.0  # 基础内存50MB
            
            # 每个缓存条目约1KB
            cache_memory = fallback_size * 0.001  # 转换为MB
            
            return base_memory + cache_memory
        except:
            return 50.0
    
    def create_baseline(self, name: str, description: str = "") -> BaselineSnapshot:
        """创建新的性能基线"""
        try:
            current_metrics = self.collect_current_metrics()
            
            baseline = BaselineSnapshot(
                name=name,
                created_at=datetime.now(),
                metrics=current_metrics,
                description=description,
                metadata={
                    'total_metrics': len(current_metrics),
                    'created_by': 'baseline_comparator',
                    'version': '2.0.0'
                }
            )
            
            self.baselines[name] = baseline
            self.current_baseline = baseline
            
            self._save_baselines()
            
            logger.info(f"创建新基线: {name}")
            return baseline
            
        except Exception as e:
            logger.error(f"创建基线失败: {e}")
            raise
    
    def set_current_baseline(self, name: str):
        """设置当前基线"""
        if name in self.baselines:
            self.current_baseline = self.baselines[name]
            logger.info(f"切换当前基线为: {name}")
        else:
            raise ValueError(f"基线不存在: {name}")
    
    def compare_with_baseline(self, baseline_name: Optional[str] = None) -> Dict[str, ComparisonResult]:
        """与基线对比"""
        try:
            # 确定要对比的基线
            if baseline_name:
                if baseline_name not in self.baselines:
                    raise ValueError(f"基线不存在: {baseline_name}")
                baseline = self.baselines[baseline_name]
            else:
                if not self.current_baseline:
                    raise ValueError("未设置当前基线")
                baseline = self.current_baseline
            
            # 收集当前指标
            current_metrics = self.collect_current_metrics()
            
            # 执行对比
            comparison_results = {}
            
            for metric_name, current_metric in current_metrics.items():
                if metric_name in baseline.metrics:
                    baseline_metric = baseline.metrics[metric_name]
                    result = self._compare_metric(baseline_metric, current_metric)
                    comparison_results[metric_name] = result
            
            return comparison_results
            
        except Exception as e:
            logger.error(f"基线对比失败: {e}")
            raise
    
    def _compare_metric(self, baseline_metric: PerformanceMetric, current_metric: PerformanceMetric) -> ComparisonResult:
        """对比单个指标"""
        baseline_value = baseline_metric.value
        current_value = current_metric.value
        
        # 计算偏差
        if baseline_value == 0:
            deviation_percent = 0 if current_value == 0 else float('inf')
        else:
            deviation_percent = ((current_value - baseline_value) / baseline_value) * 100
        
        deviation_absolute = current_value - baseline_value
        
        # 确定状态和显著性
        metric_def = self.metric_definitions.get(current_metric.name, {})
        higher_is_better = metric_def.get('higher_is_better', True)
        
        # 状态判断
        if abs(deviation_percent) < 5:
            status = 'stable'
        elif (higher_is_better and deviation_percent > 0) or (not higher_is_better and deviation_percent < 0):
            status = 'improved'
        else:
            status = 'degraded'
        
        # 显著性判断
        abs_deviation = abs(deviation_percent)
        if abs_deviation < 5:
            significance = 'low'
        elif abs_deviation < 15:
            significance = 'medium'
        elif abs_deviation < 30:
            significance = 'high'
        else:
            significance = 'critical'
        
        return ComparisonResult(
            metric_name=current_metric.name,
            baseline_value=baseline_value,
            current_value=current_value,
            deviation_percent=deviation_percent,
            deviation_absolute=deviation_absolute,
            status=status,
            significance=significance
        )
    
    def get_trend_analysis(self, metric_name: str, days: int = 7) -> Dict[str, Any]:
        """获取指标趋势分析"""
        try:
            if metric_name not in self.metric_trends:
                return {'error': f'指标不存在: {metric_name}'}
            
            trend_data = list(self.metric_trends[metric_name])
            
            # 过滤时间范围
            cutoff_time = datetime.now() - timedelta(days=days)
            recent_data = [
                point for point in trend_data
                if point['timestamp'] >= cutoff_time
            ]
            
            if len(recent_data) < 2:
                return {'error': '数据点不足，无法分析趋势'}
            
            # 计算统计信息
            values = [point['value'] for point in recent_data]
            
            analysis = {
                'metric_name': metric_name,
                'time_range_days': days,
                'data_points': len(recent_data),
                'statistics': {
                    'mean': statistics.mean(values),
                    'median': statistics.median(values),
                    'min': min(values),
                    'max': max(values),
                    'std_dev': statistics.stdev(values) if len(values) > 1 else 0
                },
                'trend': self._calculate_trend(recent_data),
                'volatility': self._calculate_volatility(values),
                'latest_value': values[-1],
                'change_from_start': values[-1] - values[0],
                'change_percent': ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"趋势分析失败 {metric_name}: {e}")
            return {'error': str(e)}
    
    def _calculate_trend(self, data_points: List[Dict]) -> str:
        """计算趋势方向"""
        if len(data_points) < 2:
            return 'insufficient_data'
        
        values = [point['value'] for point in data_points]
        
        # 简单线性趋势计算
        x = list(range(len(values)))
        n = len(values)
        
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        # 计算斜率
        if n * sum_x2 - sum_x ** 2 == 0:
            return 'stable'
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        
        if abs(slope) < 0.01:
            return 'stable'
        elif slope > 0:
            return 'increasing'
        else:
            return 'decreasing'
    
    def _calculate_volatility(self, values: List[float]) -> str:
        """计算波动性"""
        if len(values) < 2:
            return 'unknown'
        
        mean_val = statistics.mean(values)
        if mean_val == 0:
            return 'unknown'
        
        cv = statistics.stdev(values) / mean_val * 100  # 变异系数
        
        if cv < 5:
            return 'low'
        elif cv < 15:
            return 'medium'
        elif cv < 30:
            return 'high'
        else:
            return 'very_high'
    
    def generate_comparison_report(self, baseline_name: Optional[str] = None) -> Dict[str, Any]:
        """生成详细的对比报告"""
        try:
            # 执行对比
            comparison_results = self.compare_with_baseline(baseline_name)
            
            # 获取基线信息
            baseline = self.current_baseline if not baseline_name else self.baselines[baseline_name]
            
            # 汇总统计
            total_metrics = len(comparison_results)
            improved_count = len([r for r in comparison_results.values() if r.status == 'improved'])
            degraded_count = len([r for r in comparison_results.values() if r.status == 'degraded'])
            stable_count = len([r for r in comparison_results.values() if r.status == 'stable'])
            
            critical_issues = [r for r in comparison_results.values() if r.significance == 'critical']
            high_issues = [r for r in comparison_results.values() if r.significance == 'high']
            
            # 生成报告
            report = {
                'report_metadata': {
                    'generated_at': datetime.now().isoformat(),
                    'baseline_name': baseline.name,
                    'baseline_created_at': baseline.created_at.isoformat(),
                    'baseline_description': baseline.description
                },
                'summary': {
                    'total_metrics': total_metrics,
                    'improved_metrics': improved_count,
                    'degraded_metrics': degraded_count,
                    'stable_metrics': stable_count,
                    'critical_issues': len(critical_issues),
                    'high_priority_issues': len(high_issues)
                },
                'overall_score': self._calculate_overall_score(comparison_results),
                'detailed_comparisons': {
                    name: result.to_dict() for name, result in comparison_results.items()
                },
                'critical_alerts': [
                    {
                        'metric': r.metric_name,
                        'baseline_value': r.baseline_value,
                        'current_value': r.current_value,
                        'deviation_percent': r.deviation_percent,
                        'recommendation': self._get_recommendation(r)
                    }
                    for r in critical_issues
                ],
                'recommendations': self._generate_recommendations(comparison_results)
            }
            
            return report
            
        except Exception as e:
            logger.error(f"生成对比报告失败: {e}")
            raise
    
    def _calculate_overall_score(self, comparison_results: Dict[str, ComparisonResult]) -> float:
        """计算整体性能评分"""
        if not comparison_results:
            return 0.0
        
        total_score = 100.0
        penalty_weights = {
            'critical': 15,
            'high': 8,
            'medium': 3,
            'low': 1
        }
        
        for result in comparison_results.values():
            if result.status == 'degraded':
                penalty = penalty_weights.get(result.significance, 1)
                total_score -= penalty
        
        return max(0, total_score)
    
    def _get_recommendation(self, result: ComparisonResult) -> str:
        """获取改进建议"""
        metric_name = result.metric_name
        
        recommendations = {
            'cache_hit_rate': "检查缓存配置和数据访问模式，考虑优化缓存策略",
            'cache_response_time': "检查Redis连接状态，优化缓存查询逻辑",
            'api_response_time': "检查API性能瓶颈，考虑增加缓存或优化数据库查询",
            'system_health_score': "全面检查系统各项指标，重点关注错误率和可用性",
            'error_rate': "检查应用日志，修复错误根因，加强错误处理",
            'redis_availability': "检查Redis服务状态，确保网络连接稳定",
            'memory_usage': "优化内存使用，清理不必要的缓存数据"
        }
        
        return recommendations.get(metric_name, "检查该指标的相关配置和系统状态")
    
    def _generate_recommendations(self, comparison_results: Dict[str, ComparisonResult]) -> List[str]:
        """生成整体改进建议"""
        recommendations = []
        
        # 分析关键问题
        critical_issues = [r for r in comparison_results.values() if r.significance == 'critical']
        degraded_metrics = [r for r in comparison_results.values() if r.status == 'degraded']
        
        if critical_issues:
            recommendations.append("🚨 发现严重性能退化，需要立即处理关键问题")
        
        if len(degraded_metrics) > len(comparison_results) / 2:
            recommendations.append("⚠️ 多项指标出现退化，建议全面检查系统状态")
        
        # 具体建议
        cache_issues = [r for r in comparison_results.values() 
                       if 'cache' in r.metric_name and r.status == 'degraded']
        if cache_issues:
            recommendations.append("🔧 缓存性能下降，检查Redis配置和网络连接")
        
        api_issues = [r for r in comparison_results.values() 
                     if 'api' in r.metric_name and r.status == 'degraded']
        if api_issues:
            recommendations.append("🔧 API性能下降，检查应用服务器和数据库性能")
        
        error_issues = [r for r in comparison_results.values() 
                       if 'error' in r.metric_name and r.status == 'degraded']
        if error_issues:
            recommendations.append("🔧 错误率上升，检查应用日志和异常处理")
        
        if not recommendations:
            recommendations.append("✅ 系统性能稳定，继续保持当前配置")
        
        return recommendations
    
    def export_baseline(self, baseline_name: str, file_path: str):
        """导出基线数据"""
        try:
            if baseline_name not in self.baselines:
                raise ValueError(f"基线不存在: {baseline_name}")
            
            baseline = self.baselines[baseline_name]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(baseline.to_dict(), f, ensure_ascii=False, indent=2)
            
            logger.info(f"基线已导出到: {file_path}")
            
        except Exception as e:
            logger.error(f"导出基线失败: {e}")
            raise
    
    def import_baseline(self, file_path: str, baseline_name: Optional[str] = None):
        """导入基线数据"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            baseline = BaselineSnapshot.from_dict(data)
            
            if baseline_name:
                baseline.name = baseline_name
            
            self.baselines[baseline.name] = baseline
            self._save_baselines()
            
            logger.info(f"基线已导入: {baseline.name}")
            
        except Exception as e:
            logger.error(f"导入基线失败: {e}")
            raise
    
    def get_baseline_list(self) -> List[Dict[str, Any]]:
        """获取基线列表"""
        return [
            {
                'name': baseline.name,
                'created_at': baseline.created_at.isoformat(),
                'description': baseline.description,
                'metrics_count': len(baseline.metrics),
                'is_current': baseline == self.current_baseline
            }
            for baseline in self.baselines.values()
        ]
    
    def delete_baseline(self, baseline_name: str):
        """删除基线"""
        if baseline_name not in self.baselines:
            raise ValueError(f"基线不存在: {baseline_name}")
        
        if self.current_baseline and self.current_baseline.name == baseline_name:
            self.current_baseline = None
        
        del self.baselines[baseline_name]
        self._save_baselines()
        
        logger.info(f"基线已删除: {baseline_name}")
    
    def cleanup_old_data(self, days: int = 30):
        """清理过期数据"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            # 清理性能历史
            old_count = len(self.performance_history)
            self.performance_history = deque(
                [record for record in self.performance_history 
                 if record['timestamp'] >= cutoff_time],
                maxlen=10000
            )
            new_count = len(self.performance_history)
            
            # 清理趋势数据
            for metric_name in self.metric_trends:
                self.metric_trends[metric_name] = deque(
                    [point for point in self.metric_trends[metric_name]
                     if point['timestamp'] >= cutoff_time],
                    maxlen=1000
                )
            
            self._save_performance_history()
            
            logger.info(f"清理了 {old_count - new_count} 条过期记录")
            
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")


# 全局基线对比器实例
_baseline_comparator = None
_comparator_lock = threading.Lock()

def get_baseline_comparator() -> LLMBaselineComparator:
    """获取基线对比器实例（单例模式）"""
    global _baseline_comparator
    
    if _baseline_comparator is None:
        with _comparator_lock:
            if _baseline_comparator is None:
                _baseline_comparator = LLMBaselineComparator()
    
    return _baseline_comparator

if __name__ == "__main__":
    """测试基线对比器"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM性能基线对比")
    parser.add_argument("--create-baseline", type=str, help="创建新基线")
    parser.add_argument("--compare", type=str, help="与指定基线对比")
    parser.add_argument("--trend", type=str, help="查看指标趋势")
    parser.add_argument("--report", action="store_true", help="生成完整对比报告")
    parser.add_argument("--list", action="store_true", help="列出所有基线")
    parser.add_argument("--export", nargs=2, metavar=('baseline', 'file'), help="导出基线")
    parser.add_argument("--import", nargs=1, metavar='file', help="导入基线")
    parser.add_argument("--cleanup", type=int, default=30, help="清理指定天数前的数据")
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    comparator = get_baseline_comparator()
    
    if args.create_baseline:
        baseline = comparator.create_baseline(
            name=args.create_baseline,
            description=f"通过命令行创建的基线 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        print(f"基线已创建: {baseline.name}")
        print(f"包含指标: {len(baseline.metrics)} 个")
    
    elif args.compare:
        try:
            results = comparator.compare_with_baseline(args.compare)
            print(f"\n与基线 '{args.compare}' 的对比结果:")
            print("-" * 50)
            
            for metric_name, result in results.items():
                status_icon = "✅" if result.status == "improved" else "⚠️" if result.status == "stable" else "❌"
                print(f"{status_icon} {metric_name}: {result.deviation_percent:+.2f}% ({result.significance})")
        
        except Exception as e:
            print(f"对比失败: {e}")
    
    elif args.trend:
        analysis = comparator.get_trend_analysis(args.trend)
        if 'error' not in analysis:
            print(f"\n指标 '{args.trend}' 的趋势分析:")
            print("-" * 50)
            print(f"数据点数: {analysis['data_points']}")
            print(f"趋势方向: {analysis['trend']}")
            print(f"波动性: {analysis['volatility']}")
            print(f"最新值: {analysis['latest_value']:.2f}")
            print(f"变化幅度: {analysis['change_percent']:+.2f}%")
        else:
            print(f"分析失败: {analysis['error']}")
    
    elif args.report:
        try:
            report = comparator.generate_comparison_report()
            print("\n性能对比报告")
            print("=" * 50)
            print(f"基线: {report['report_metadata']['baseline_name']}")
            print(f"生成时间: {report['report_metadata']['generated_at']}")
            print(f"整体评分: {report['overall_score']:.1f}/100")
            print(f"\n指标汇总:")
            print(f"  改善: {report['summary']['improved_metrics']} 项")
            print(f"  稳定: {report['summary']['stable_metrics']} 项")
            print(f"  退化: {report['summary']['degraded_metrics']} 项")
            print(f"  关键问题: {report['summary']['critical_issues']} 项")
            
            if report['critical_alerts']:
                print(f"\n关键告警:")
                for alert in report['critical_alerts']:
                    print(f"  ❌ {alert['metric']}: {alert['deviation_percent']:+.2f}%")
            
            print(f"\n改进建议:")
            for rec in report['recommendations']:
                print(f"  • {rec}")
        
        except Exception as e:
            print(f"生成报告失败: {e}")
    
    elif getattr(args, 'list', False):
        baselines = comparator.get_baseline_list()
        print("\n可用基线:")
        print("-" * 50)
        for baseline in baselines:
            current_mark = " (当前)" if baseline['is_current'] else ""
            print(f"• {baseline['name']}{current_mark}")
            print(f"  创建时间: {baseline['created_at']}")
            print(f"  指标数量: {baseline['metrics_count']}")
            if baseline['description']:
                print(f"  描述: {baseline['description']}")
            print()
    
    elif args.export:
        baseline_name, file_path = args.export
        try:
            comparator.export_baseline(baseline_name, file_path)
            print(f"基线 '{baseline_name}' 已导出到 '{file_path}'")
        except Exception as e:
            print(f"导出失败: {e}")
    
    elif getattr(args, 'import', None):
        file_path = getattr(args, 'import')[0]
        try:
            comparator.import_baseline(file_path)
            print(f"基线已从 '{file_path}' 导入")
        except Exception as e:
            print(f"导入失败: {e}")
    
    elif args.cleanup:
        comparator.cleanup_old_data(args.cleanup)
        print(f"已清理 {args.cleanup} 天前的数据")
    
    else:
        print("请指定操作参数，使用 --help 查看帮助")
