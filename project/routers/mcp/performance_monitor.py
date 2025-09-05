# project/routers/mcp/performance_monitor.py
"""
MCP 连接检查性能监控器
"""
import time
import logging
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import statistics
import threading


@dataclass
class PerformanceMetric:
    """性能指标"""
    base_url: str
    response_time: float
    status: str
    timestamp: datetime
    error_message: str = None


@dataclass
class PerformanceStats:
    """性能统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    slow_requests: int = 0
    response_times: List[float] = field(default_factory=list)


class McpPerformanceMonitor:
    """MCP 性能监控器"""
    
    def __init__(self, slow_threshold: float = 2.0, max_history: int = 1000):
        self.slow_threshold = slow_threshold
        self.max_history = max_history
        self._metrics: List[PerformanceMetric] = []
        self._stats_cache: Dict[str, PerformanceStats] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(f"{__name__}.McpPerformanceMonitor")
    
    def record_request(self, base_url: str, response_time: float, status: str, error_message: str = None):
        """记录请求性能指标"""
        metric = PerformanceMetric(
            base_url=base_url,
            response_time=response_time,
            status=status,
            timestamp=datetime.now(),
            error_message=error_message
        )
        
        with self._lock:
            self._metrics.append(metric)
            
            # 限制历史记录数量
            if len(self._metrics) > self.max_history:
                self._metrics = self._metrics[-self.max_history:]
            
            # 清除统计缓存，强制重新计算
            self._stats_cache.clear()
        
        # 记录慢请求
        if response_time > self.slow_threshold:
            self.logger.warning(
                f"慢请求检测: {base_url} 响应时间 {response_time:.2f}s 超过阈值 {self.slow_threshold}s"
            )
        
        # 记录失败请求
        if status != "success":
            self.logger.warning(
                f"请求失败: {base_url} 状态: {status} 错误: {error_message or 'N/A'}"
            )
    
    def get_stats(self, base_url: str = None, time_window: timedelta = None) -> PerformanceStats:
        """获取性能统计信息"""
        with self._lock:
            cache_key = f"{base_url}_{time_window}"
            
            if cache_key in self._stats_cache:
                return self._stats_cache[cache_key]
            
            # 过滤指标
            filtered_metrics = self._metrics
            
            if time_window:
                cutoff_time = datetime.now() - time_window
                filtered_metrics = [m for m in filtered_metrics if m.timestamp >= cutoff_time]
            
            if base_url:
                filtered_metrics = [m for m in filtered_metrics if m.base_url == base_url]
            
            if not filtered_metrics:
                return PerformanceStats()
            
            # 计算统计信息
            response_times = [m.response_time for m in filtered_metrics]
            successful_count = len([m for m in filtered_metrics if m.status == "success"])
            failed_count = len(filtered_metrics) - successful_count
            slow_count = len([m for m in filtered_metrics if m.response_time > self.slow_threshold])
            
            stats = PerformanceStats(
                total_requests=len(filtered_metrics),
                successful_requests=successful_count,
                failed_requests=failed_count,
                average_response_time=statistics.mean(response_times),
                min_response_time=min(response_times),
                max_response_time=max(response_times),
                slow_requests=slow_count,
                response_times=response_times
            )
            
            self._stats_cache[cache_key] = stats
            return stats
    
    def get_recent_failures(self, time_window: timedelta = timedelta(hours=1)) -> List[PerformanceMetric]:
        """获取最近的失败请求"""
        cutoff_time = datetime.now() - time_window
        
        with self._lock:
            return [
                m for m in self._metrics 
                if m.timestamp >= cutoff_time and m.status != "success"
            ]
    
    def clear_history(self):
        """清空历史记录"""
        with self._lock:
            self._metrics.clear()
            self._stats_cache.clear()
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        overall_stats = self.get_stats()
        recent_stats = self.get_stats(time_window=timedelta(hours=1))
        
        return {
            "overall": {
                "total_requests": overall_stats.total_requests,
                "success_rate": (overall_stats.successful_requests / max(overall_stats.total_requests, 1)) * 100,
                "average_response_time": overall_stats.average_response_time,
                "slow_request_rate": (overall_stats.slow_requests / max(overall_stats.total_requests, 1)) * 100,
            },
            "recent_1hour": {
                "total_requests": recent_stats.total_requests,
                "success_rate": (recent_stats.successful_requests / max(recent_stats.total_requests, 1)) * 100,
                "average_response_time": recent_stats.average_response_time,
                "slow_request_rate": (recent_stats.slow_requests / max(recent_stats.total_requests, 1)) * 100,
            },
            "recent_failures": len(self.get_recent_failures())
        }


# 全局性能监控器实例
performance_monitor = McpPerformanceMonitor()
