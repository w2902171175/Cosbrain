# project/routers/knowledge/advanced_knowledge.py
"""
增强的API端点 - 集成分布式处理、安全扫描和监控告警
重构后只包含API端点定义，业务逻辑已移至服务层
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import os

# 导入重构后的服务和工具
from project.services.distributed_service import (
    distributed_service, TaskPriority, NodeRole,
    submit_distributed_task, get_distributed_task_status, cancel_distributed_task,
    get_distributed_system_stats
)
from project.services.security_service import (
    ScanType, scan_content_security, scan_url_security
)
from project.services.enhanced_monitoring_service import (
    enhanced_monitoring_service, MetricType,
    record_system_metric, add_monitoring_threshold
)
from project.utils.recommendation import (
    UserAction, UserBehavior, record_user_behavior, get_user_profile,
    extract_tags_from_content, suggest_document_tags, find_similar_documents,
    add_document_to_index, calculate_similarity
)

router = APIRouter(prefix="/enhanced", tags=["增强功能"])

# ===== 分布式处理API =====

@router.post("/distributed/init", summary="初始化分布式系统")
async def initialize_distributed_system(
    redis_url: Optional[str] = None,
    node_role: NodeRole = NodeRole.HYBRID,
    host: str = "localhost",
    port: int = 8000,
    capabilities: Optional[List[str]] = None
):
    """初始化分布式系统"""
    try:
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        node_id = await distributed_service.initialize(node_role, host, port, capabilities)
        
        return {
            "success": True,
            "message": "分布式系统初始化成功",
            "node_id": node_id,
            "role": node_role,
            "capabilities": capabilities or ["general"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化失败: {str(e)}")

@router.post("/distributed/tasks", summary="提交分布式任务")
async def submit_task(
    task_type: str,
    priority: TaskPriority = TaskPriority.NORMAL,
    data: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    timeout: int = 3600,
    dependencies: Optional[List[str]] = None
):
    """提交分布式任务"""
    try:
        if not distributed_service.is_initialized:
            raise HTTPException(status_code=400, detail="分布式系统未初始化")
        
        task_id = await submit_distributed_task(
            task_type=task_type,
            data=data or {},
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
            dependencies=dependencies
        )
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "任务提交成功"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"任务提交失败: {str(e)}")

@router.get("/distributed/tasks/{task_id}", summary="获取任务状态")
async def get_task_status(task_id: str):
    """获取任务状态"""
    try:
        if not distributed_service.is_initialized:
            raise HTTPException(status_code=400, detail="分布式系统未初始化")
        
        status = await get_distributed_task_status(task_id)
        
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return {
            "success": True,
            "task_id": task_id,
            "status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取状态失败: {str(e)}")

@router.delete("/distributed/tasks/{task_id}", summary="取消任务")
async def cancel_task(task_id: str):
    """取消任务"""
    try:
        if not distributed_service.is_initialized:
            raise HTTPException(status_code=400, detail="分布式系统未初始化")
        
        success = await cancel_distributed_task(task_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="任务不存在或无法取消")
        
        return {
            "success": True,
            "message": "任务取消成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")

@router.get("/distributed/stats", summary="获取分布式系统统计")
async def get_system_stats():
    """获取分布式系统统计信息"""
    try:
        stats = await get_distributed_system_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")

# ===== 安全扫描API =====

@router.post("/security/scan/file", summary="扫描文件")
async def scan_file(
    file: UploadFile = File(...),
    scan_types: Optional[List[ScanType]] = Query(default=None)
):
    """扫描上传的文件"""
    try:
        content = await file.read()
        
        result = await scan_content_security(
            content=content,
            filename=file.filename or "unknown",
            scan_types=scan_types
        )
        
        return {
            "success": True,
            "scan_result": {
                "filename": result.file_path,
                "threat_level": result.threat_level,
                "is_safe": result.is_safe,
                "threats_count": len(result.threats),
                "threats": [
                    {
                        "type": threat.threat_type,
                        "level": threat.threat_level,
                        "description": threat.description,
                        "confidence": threat.confidence,
                        "recommendation": threat.recommendation
                    }
                    for threat in result.threats
                ],
                "scan_duration": result.scan_duration,
                "file_size": result.file_size,
                "scanned_at": result.scanned_at.isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件扫描失败: {str(e)}")

@router.post("/security/scan/url", summary="扫描URL")
async def scan_url(url: str):
    """扫描URL安全性"""
    try:
        result = await scan_url_security(url)
        
        return {
            "success": True,
            "scan_result": {
                "url": url,
                "threat_level": result.threat_level,
                "is_safe": result.is_safe,
                "threats_count": len(result.threats),
                "threats": [
                    {
                        "type": threat.threat_type,
                        "level": threat.threat_level,
                        "description": threat.description,
                        "confidence": threat.confidence
                    }
                    for threat in result.threats
                ],
                "scan_duration": result.scan_duration,
                "scanned_at": result.scanned_at.isoformat()
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"URL扫描失败: {str(e)}")

# ===== 监控告警API =====

@router.post("/monitoring/init", summary="初始化监控系统")
async def initialize_monitoring(
    redis_url: Optional[str] = None,
    config_file: Optional[str] = None
):
    """初始化监控系统"""
    try:
        if redis_url:
            enhanced_monitoring_service.redis_url = redis_url
        
        await enhanced_monitoring_service.initialize()
        
        return {
            "success": True,
            "message": "监控系统初始化成功"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"监控系统初始化失败: {str(e)}")

@router.get("/monitoring/metrics/{metric_name}/history", summary="获取指标历史")
async def get_metric_history(
    metric_name: str,
    hours: int = Query(default=1, ge=1, le=168, description="时间范围(小时)")
):
    """获取指标历史数据"""
    try:
        time_range = timedelta(hours=hours)
        history = await enhanced_monitoring_service.get_metric_history(metric_name, time_range)
        
        return {
            "success": True,
            "metric_name": metric_name,
            "time_range_hours": hours,
            "data_points": len(history),
            "history": history
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取指标历史失败: {str(e)}")

@router.get("/monitoring/alerts", summary="获取活跃告警")
async def get_active_alerts():
    """获取当前活跃告警"""
    try:
        alerts = await enhanced_monitoring_service.get_active_alerts()
        
        return {
            "success": True,
            "active_alerts": len(alerts),
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "name": alert.name,
                    "level": alert.level,
                    "message": alert.message,
                    "metric_name": alert.metric_name,
                    "current_value": alert.current_value,
                    "threshold_value": alert.threshold_value,
                    "triggered_at": alert.triggered_at.isoformat()
                }
                for alert in alerts
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取告警失败: {str(e)}")

@router.post("/monitoring/alerts/{alert_id}/acknowledge", summary="确认告警")
async def acknowledge_alert(alert_id: str, acknowledged_by: str):
    """确认告警"""
    try:
        await enhanced_monitoring_service.acknowledge_alert(alert_id, acknowledged_by)
        
        return {
            "success": True,
            "message": "告警已确认"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"确认告警失败: {str(e)}")

@router.post("/monitoring/alerts/{alert_id}/resolve", summary="解决告警")
async def resolve_alert(alert_id: str):
    """解决告警"""
    try:
        await enhanced_monitoring_service.resolve_alert(alert_id)
        
        return {
            "success": True,
            "message": "告警已解决"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解决告警失败: {str(e)}")

@router.post("/monitoring/thresholds", summary="添加监控阈值")
async def add_threshold(
    metric_name: str,
    warning_threshold: float,
    error_threshold: float,
    critical_threshold: float,
    comparison_type: str = "greater"
):
    """添加监控阈值"""
    try:
        await add_monitoring_threshold(
            metric_name, warning_threshold, error_threshold, critical_threshold
        )
        
        return {
            "success": True,
            "message": "阈值添加成功"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加阈值失败: {str(e)}")

@router.post("/monitoring/metrics", summary="记录自定义指标")
async def record_metric(
    name: str,
    value: float,
    metric_type: MetricType = MetricType.GAUGE,
    tags: Optional[Dict[str, str]] = None
):
    """记录自定义指标"""
    try:
        await record_system_metric(name, value, metric_type, tags)
        
        return {
            "success": True,
            "message": "指标记录成功"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"记录指标失败: {str(e)}")

# ===== 智能推荐API =====

@router.post("/recommendations/behavior", summary="记录用户行为")
async def record_behavior(
    user_id: int,
    action: UserAction,
    document_id: int,
    kb_id: int,
    metadata: Optional[Dict[str, Any]] = None
):
    """记录用户行为用于推荐分析"""
    try:
        import uuid
        
        behavior = UserBehavior(
            user_id=user_id,
            action=action,
            document_id=document_id,
            kb_id=kb_id,
            timestamp=datetime.now(),
            session_id=str(uuid.uuid4()),
            metadata=metadata
        )
        
        await record_user_behavior(behavior)
        
        return {
            "success": True,
            "message": "用户行为记录成功"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"记录用户行为失败: {str(e)}")

@router.get("/recommendations/profile/{user_id}", summary="获取用户画像")
async def get_user_profile_api(user_id: int):
    """获取用户画像"""
    try:
        profile = await get_user_profile(user_id)
        
        return {
            "success": True,
            "user_profile": profile.to_dict()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户画像失败: {str(e)}")

@router.post("/recommendations/tags/extract", summary="提取内容标签")
async def extract_content_tags(
    content: str,
    max_tags: int = Query(default=10, ge=1, le=20)
):
    """从内容中提取标签"""
    try:
        tags = extract_tags_from_content(content, max_tags)
        
        return {
            "success": True,
            "tags": tags
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标签提取失败: {str(e)}")

@router.post("/recommendations/tags/suggest", summary="建议文档标签")
async def suggest_tags(
    title: str,
    content: str,
    existing_tags: Optional[List[str]] = None
):
    """为文档建议标签"""
    try:
        suggested_tags = suggest_document_tags(title, content, existing_tags)
        
        return {
            "success": True,
            "suggested_tags": suggested_tags
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标签建议失败: {str(e)}")

@router.post("/recommendations/documents/add", summary="添加文档到推荐索引")
async def add_document_to_recommendation_index(
    document_id: int,
    content: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """添加文档到推荐索引"""
    try:
        add_document_to_index(document_id, content, metadata)
        
        return {
            "success": True,
            "message": "文档已添加到推荐索引"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加文档到索引失败: {str(e)}")

@router.get("/recommendations/documents/{document_id}/similar", summary="获取相似文档")
async def get_similar_documents(
    document_id: int,
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
    limit: int = Query(default=10, ge=1, le=50)
):
    """获取相似文档推荐"""
    try:
        similar_docs = find_similar_documents(document_id, threshold, limit)
        
        return {
            "success": True,
            "document_id": document_id,
            "similar_documents": [
                {
                    "document_id": doc_id,
                    "similarity_score": similarity
                }
                for doc_id, similarity in similar_docs
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取相似文档失败: {str(e)}")

@router.post("/recommendations/similarity/calculate", summary="计算文本相似度")
async def calculate_text_similarity(
    text1: str,
    text2: str
):
    """计算两个文本的相似度"""
    try:
        similarity = calculate_similarity(text1, text2)
        
        return {
            "success": True,
            "similarity_score": similarity,
            "similarity_level": "high" if similarity > 0.7 else "medium" if similarity > 0.4 else "low"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"计算相似度失败: {str(e)}")

# ===== 健康检查API =====

@router.get("/health", summary="系统健康检查")
async def health_check():
    """系统健康检查"""
    try:
        status = {
            "distributed_system": distributed_service.is_initialized,
            "monitoring_system": enhanced_monitoring_service.is_monitoring,
            "security_service": True,  # 安全服务无状态，始终可用
            "timestamp": datetime.now().isoformat()
        }
        
        overall_healthy = all(
            status[key] if isinstance(status[key], bool) else True 
            for key in status if key != "timestamp"
        )
        
        return {
            "success": True,
            "healthy": overall_healthy,
            "services": status
        }
        
    except Exception as e:
        return JSONResponse(
            content={
                "success": False,
                "healthy": False,
                "error": str(e)
            },
            status_code=500
        )
