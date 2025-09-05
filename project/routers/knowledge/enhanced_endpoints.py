# project/routers/knowledge/enhanced_endpoints.py
"""
增强的API端点 - 集成分布式处理、安全扫描、智能推荐和监控告警
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import json
import os

from project.database import get_db
from project.models import KnowledgeBase, KnowledgeDocument, User

# 导入新的模块
from .distributed_processing import (
    DistributedTask, TaskPriority, DistributedTaskStatus,
    distributed_queue, init_distributed_system, NodeRole
)
from .security_scanner import (
    get_security_scanner, ThreatLevel, AlertLevel
)
from .intelligent_recommendation import (
    get_recommendation_engine, get_tag_suggester, get_personalized_search,
    UserAction, UserBehavior, RecommendationType
)
from .monitoring_alerting import (
    get_monitoring_system, Alert, MetricThreshold
)

router = APIRouter()

# ===== 分布式处理API =====

@router.post("/distributed/init")
async def initialize_distributed_system(
    redis_url: str = None,
    node_role: NodeRole = NodeRole.HYBRID,
    host: str = "localhost",
    port: int = 8000,
    capabilities: List[str] = None
):
    """初始化分布式系统"""
    try:
        # 设置默认Redis URL
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            
        if capabilities is None:
            capabilities = [
                "document_processing",
                "batch_vectorization",
                "thumbnail_generation", 
                "format_conversion"
            ]
            
        queue = await init_distributed_system(redis_url, node_role, host, port, capabilities)
        
        return {
            "status": "success",
            "message": f"分布式系统已初始化 - 角色: {node_role}",
            "node_capabilities": capabilities
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分布式系统初始化失败: {str(e)}")

@router.post("/distributed/tasks/submit")
async def submit_distributed_task(
    task_type: str,
    priority: TaskPriority = TaskPriority.NORMAL,
    data: Dict[str, Any] = None,
    max_retries: int = 3,
    timeout: int = 3600,
    dependencies: List[str] = None
):
    """提交分布式任务"""
    try:
        if not distributed_queue:
            raise HTTPException(status_code=503, detail="分布式系统未初始化")
            
        task = DistributedTask(
            task_type=task_type,
            priority=priority,
            data=data or {},
            max_retries=max_retries,
            timeout=timeout,
            dependencies=dependencies or []
        )
        
        task_id = await distributed_queue.submit_task(task)
        
        return {
            "status": "success",
            "task_id": task_id,
            "message": "任务已提交到分布式队列"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务提交失败: {str(e)}")

@router.get("/distributed/tasks/{task_id}/status")
async def get_distributed_task_status(task_id: str):
    """获取分布式任务状态"""
    try:
        if not distributed_queue:
            raise HTTPException(status_code=503, detail="分布式系统未初始化")
            
        status = await distributed_queue.get_task_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
            
        return {
            "status": "success",
            "task_status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务状态失败: {str(e)}")

@router.post("/distributed/tasks/{task_id}/cancel")
async def cancel_distributed_task(task_id: str):
    """取消分布式任务"""
    try:
        if not distributed_queue:
            raise HTTPException(status_code=503, detail="分布式系统未初始化")
            
        success = await distributed_queue.cancel_task(task_id)
        
        return {
            "status": "success" if success else "failed",
            "message": "任务已取消" if success else "任务取消失败"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务取消失败: {str(e)}")

# ===== 安全扫描API =====

@router.post("/security/scan/file")
async def scan_file_security(
    file: UploadFile = File(...),
    scan_content: bool = True,
    scan_virus: bool = True,
    scan_image: bool = True
):
    """文件安全扫描"""
    try:
        scanner = get_security_scanner()
        
        # 保存临时文件
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
            
        try:
            # 执行综合扫描
            scan_result = await scanner.scan_file_comprehensive(tmp_file_path, content)
            
            return {
                "status": "success",
                "scan_result": scan_result
            }
            
        finally:
            # 清理临时文件
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件安全扫描失败: {str(e)}")

@router.get("/security/scan/{scan_id}/history")
async def get_scan_history(scan_id: str = None):
    """获取扫描历史"""
    try:
        scanner = get_security_scanner()
        history = await scanner.get_scan_history(scan_id)
        
        return {
            "status": "success",
            "scan_history": history
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取扫描历史失败: {str(e)}")

# ===== 智能推荐API =====

@router.post("/recommendation/behavior/record")
async def record_user_behavior(
    user_id: int,
    action: UserAction,
    document_id: int,
    kb_id: int,
    session_id: str,
    metadata: Dict[str, Any] = None
):
    """记录用户行为"""
    try:
        engine = get_recommendation_engine()
        if not engine:
            raise HTTPException(status_code=503, detail="推荐系统未初始化")
            
        behavior = UserBehavior(
            user_id=user_id,
            action=action,
            document_id=document_id,
            kb_id=kb_id,
            timestamp=datetime.now(),
            session_id=session_id,
            metadata=metadata
        )
        
        await engine.behavior_analyzer.record_behavior(behavior)
        
        return {
            "status": "success",
            "message": "用户行为已记录"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"记录用户行为失败: {str(e)}")

@router.get("/recommendation/user/{user_id}/recommendations")
async def get_user_recommendations(
    user_id: int,
    kb_id: int,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """获取用户推荐"""
    try:
        engine = get_recommendation_engine()
        if not engine:
            raise HTTPException(status_code=503, detail="推荐系统未初始化")
            
        recommendations = await engine.generate_recommendations(user_id, kb_id, db, limit)
        
        return {
            "status": "success",
            "recommendations": [
                {
                    "document_id": rec.document_id,
                    "score": rec.score,
                    "reason": rec.reason,
                    "type": rec.rec_type,
                    "metadata": rec.metadata
                }
                for rec in recommendations
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取推荐失败: {str(e)}")

@router.get("/recommendation/user/{user_id}/profile")
async def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db)
):
    """获取用户画像"""
    try:
        engine = get_recommendation_engine()
        if not engine:
            raise HTTPException(status_code=503, detail="推荐系统未初始化")
            
        profile = await engine.get_user_profile(user_id, db)
        
        return {
            "status": "success",
            "profile": profile.to_dict()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户画像失败: {str(e)}")

@router.post("/recommendation/tags/suggest")
async def suggest_tags(
    content: str,
    existing_tags: List[str] = None
):
    """智能标签建议"""
    try:
        suggester = get_tag_suggester()
        if not suggester:
            raise HTTPException(status_code=503, detail="标签建议器未初始化")
            
        suggestions = await suggester.analyze_document_for_tags(content, existing_tags)
        
        return {
            "status": "success",
            "tag_suggestions": suggestions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标签建议失败: {str(e)}")

@router.post("/recommendation/search/personalized")
async def personalized_search(
    user_id: int,
    query: str,
    kb_id: int,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """个性化搜索"""
    try:
        search_engine = get_personalized_search()
        if not search_engine:
            raise HTTPException(status_code=503, detail="个性化搜索未初始化")
            
        results = await search_engine.personalized_search(user_id, query, kb_id, db, limit)
        
        return {
            "status": "success",
            "search_results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"个性化搜索失败: {str(e)}")

# ===== 监控告警API =====

@router.get("/monitoring/metrics/current")
async def get_current_metrics():
    """获取当前系统指标"""
    try:
        monitoring = get_monitoring_system()
        if not monitoring:
            raise HTTPException(status_code=503, detail="监控系统未初始化")
            
        metrics = await monitoring.system_monitor.get_current_metrics()
        
        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统指标失败: {str(e)}")

@router.get("/monitoring/metrics/{metric_name}/history")
async def get_metric_history(
    metric_name: str,
    duration: int = 3600  # 默认1小时
):
    """获取指标历史数据"""
    try:
        monitoring = get_monitoring_system()
        if not monitoring:
            raise HTTPException(status_code=503, detail="监控系统未初始化")
            
        data = await monitoring.system_monitor.get_metric_data(metric_name, duration)
        
        return {
            "status": "success",
            "metric_name": metric_name,
            "duration": duration,
            "data": data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取指标历史失败: {str(e)}")

@router.get("/monitoring/alerts/active")
async def get_active_alerts():
    """获取活跃告警"""
    try:
        monitoring = get_monitoring_system()
        if not monitoring:
            raise HTTPException(status_code=503, detail="监控系统未初始化")
            
        alerts = await monitoring.alert_manager.get_active_alerts()
        
        return {
            "status": "success",
            "alerts": [alert.to_dict() for alert in alerts]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取活跃告警失败: {str(e)}")

@router.post("/monitoring/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    user: str = "system"
):
    """确认告警"""
    try:
        monitoring = get_monitoring_system()
        if not monitoring:
            raise HTTPException(status_code=503, detail="监控系统未初始化")
            
        await monitoring.alert_manager.acknowledge_alert(alert_id, user)
        
        return {
            "status": "success",
            "message": f"告警 {alert_id} 已确认"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"确认告警失败: {str(e)}")

@router.get("/monitoring/health")
async def get_system_health():
    """获取系统健康状态"""
    try:
        monitoring = get_monitoring_system()
        if not monitoring:
            raise HTTPException(status_code=503, detail="监控系统未初始化")
            
        health_results = await monitoring.health_checker.run_health_checks()
        
        # 计算整体健康状态
        all_healthy = all(
            result.get('status') == 'healthy' 
            for result in health_results.values()
        )
        
        return {
            "status": "success",
            "overall_health": "healthy" if all_healthy else "unhealthy",
            "health_checks": health_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统健康状态失败: {str(e)}")

@router.post("/monitoring/thresholds/add")
async def add_metric_threshold(
    metric_name: str,
    warning_threshold: Optional[float] = None,
    error_threshold: Optional[float] = None,
    critical_threshold: Optional[float] = None,
    comparison: str = "gt",
    duration: int = 60,
    enabled: bool = True
):
    """添加指标阈值"""
    try:
        monitoring = get_monitoring_system()
        if not monitoring:
            raise HTTPException(status_code=503, detail="监控系统未初始化")
            
        threshold = MetricThreshold(
            metric_name=metric_name,
            warning_threshold=warning_threshold,
            error_threshold=error_threshold,
            critical_threshold=critical_threshold,
            comparison=comparison,
            duration=duration,
            enabled=enabled
        )
        
        monitoring.alert_manager.add_threshold(threshold)
        
        return {
            "status": "success",
            "message": f"已添加指标 {metric_name} 的告警阈值"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加指标阈值失败: {str(e)}")

# ===== 综合管理API =====

@router.post("/system/initialize")
async def initialize_enhanced_system(
    redis_url: str = None,
    enable_distributed: bool = True,
    enable_monitoring: bool = True,
    enable_recommendations: bool = True,
    node_role: NodeRole = NodeRole.HYBRID,
    config_path: Optional[str] = None
):
    """初始化增强系统"""
    try:
        # 设置默认Redis URL
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            
        results = {}
        
        # 初始化分布式系统
        if enable_distributed:
            try:
                await init_distributed_system(redis_url, node_role)
                results["distributed"] = "success"
            except Exception as e:
                results["distributed"] = f"failed: {str(e)}"
                
        # 初始化推荐系统
        if enable_recommendations:
            try:
                import redis
                redis_client = redis.from_url(redis_url, decode_responses=True)
                from .intelligent_recommendation import init_recommendation_system
                init_recommendation_system(redis_client)
                results["recommendations"] = "success"
            except Exception as e:
                results["recommendations"] = f"failed: {str(e)}"
                
        # 初始化监控系统
        if enable_monitoring:
            try:
                import redis
                redis_client = redis.from_url(redis_url, decode_responses=True)
                from .monitoring_alerting import init_monitoring_system
                monitoring = init_monitoring_system(redis_client, config_path)
                await monitoring.start()
                results["monitoring"] = "success"
            except Exception as e:
                results["monitoring"] = f"failed: {str(e)}"
                
        return {
            "status": "success",
            "message": "增强系统初始化完成",
            "initialization_results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"系统初始化失败: {str(e)}")

@router.get("/system/status")
async def get_system_status():
    """获取系统状态"""
    try:
        status = {
            "distributed_processing": distributed_queue is not None,
            "security_scanner": get_security_scanner() is not None,
            "recommendation_engine": get_recommendation_engine() is not None,
            "tag_suggester": get_tag_suggester() is not None,
            "personalized_search": get_personalized_search() is not None,
            "monitoring_system": get_monitoring_system() is not None,
            "timestamp": datetime.now().isoformat()
        }
        
        return {
            "status": "success",
            "system_status": status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统状态失败: {str(e)}")

# ===== 高级分析API =====

@router.get("/analytics/user/{user_id}/behavior-analysis")
async def analyze_user_behavior(
    user_id: int,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """用户行为分析"""
    try:
        engine = get_recommendation_engine()
        if not engine:
            raise HTTPException(status_code=503, detail="推荐系统未初始化")
            
        # 获取用户行为
        behaviors = await engine.behavior_analyzer.get_user_behaviors(user_id, days)
        
        # 分析用户兴趣
        interests = await engine.behavior_analyzer.analyze_user_interests(user_id, db)
        
        # 获取用户画像
        profile = await engine.get_user_profile(user_id, db)
        
        return {
            "status": "success",
            "user_id": user_id,
            "analysis_period": f"{days} days",
            "behavior_count": len(behaviors),
            "interests": interests,
            "profile": profile.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"用户行为分析失败: {str(e)}")

@router.get("/analytics/system/performance-report")
async def get_performance_report(
    hours: int = 24
):
    """系统性能报告"""
    try:
        monitoring = get_monitoring_system()
        if not monitoring:
            raise HTTPException(status_code=503, detail="监控系统未初始化")
            
        # 获取指标数据
        duration = hours * 3600
        metrics_to_analyze = [
            "system.cpu.usage",
            "system.memory.usage", 
            "system.disk.usage",
            "app.redis.connected_clients",
            "app.queue.pending_tasks",
            "app.cache.hit_rate"
        ]
        
        report = {
            "report_period": f"{hours} hours",
            "metrics": {},
            "alerts_summary": {},
            "health_summary": {},
            "timestamp": datetime.now().isoformat()
        }
        
        # 收集指标数据
        for metric_name in metrics_to_analyze:
            try:
                data = await monitoring.system_monitor.get_metric_data(metric_name, duration)
                if data:
                    values = [d['value'] for d in data]
                    report["metrics"][metric_name] = {
                        "current": values[-1] if values else 0,
                        "average": sum(values) / len(values) if values else 0,
                        "max": max(values) if values else 0,
                        "min": min(values) if values else 0,
                        "data_points": len(values)
                    }
            except Exception as e:
                report["metrics"][metric_name] = {"error": str(e)}
                
        # 告警摘要
        active_alerts = await monitoring.alert_manager.get_active_alerts()
        alert_levels = {}
        for alert in active_alerts:
            alert_levels[alert.level] = alert_levels.get(alert.level, 0) + 1
            
        report["alerts_summary"] = {
            "total_active": len(active_alerts),
            "by_level": alert_levels
        }
        
        # 健康检查摘要
        health_results = await monitoring.health_checker.run_health_checks()
        healthy_count = sum(1 for r in health_results.values() if r.get('status') == 'healthy')
        
        report["health_summary"] = {
            "total_checks": len(health_results),
            "healthy": healthy_count,
            "unhealthy": len(health_results) - healthy_count,
            "overall_status": "healthy" if healthy_count == len(health_results) else "degraded"
        }
        
        return {
            "status": "success",
            "performance_report": report
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成性能报告失败: {str(e)}")

# 将路由器添加到主应用中
def setup_enhanced_routes(app):
    """设置增强路由"""
    app.include_router(router, prefix="/api/v1/enhanced", tags=["Enhanced Features"])
