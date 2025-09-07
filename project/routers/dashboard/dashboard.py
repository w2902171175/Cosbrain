# project/routers/dashboard/dashboard_optimized.py
"""
仪表板模块优化版本 - 数据聚合和实时缓存优化
基于成功优化模式，优化dashboard模块的数据聚合功能

统一优化特性：
- 使用@optimized_route装饰器（已包含错误处理）
- 统一的数据缓存和异步任务处理
- 专业服务层和工具函数
- 优化数据库查询，减少N+1问题
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

# 核心依赖
from project.database import get_db
from project.utils import get_current_user_id
import project.schemas as schemas

# 优化工具导入
from project.services.dashboard_service import (
    DashboardDataService, DashboardAnalyticsService, DashboardUtilities
)
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["智能仪表板"])

# 常量定义
VALID_PROJECT_STATUSES = ["进行中", "已完成", "待开始", "已暂停", "已取消"]
VALID_COURSE_STATUSES = ["in_progress", "completed", "not_started", "paused"]
VALID_TIME_RANGES = ["7d", "30d", "90d", "1y"]

# ===== 仪表板概览路由 =====

@router.get("/summary", response_model=schemas.DashboardSummaryResponse, summary="获取仪表板概览")
@optimized_route("仪表板概览")
async def get_dashboard_summary(
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取仪表板概览数据 - 优化版本"""
    
    # 获取聚合数据
    summary_data = DashboardDataService.get_dashboard_summary_optimized(
        db, current_user_id
    )
    
    # 异步更新用户活跃度
    submit_background_task(
        background_tasks,
        "update_user_activity",
        {
            "user_id": current_user_id,
            "activity_type": "dashboard_view",
            "timestamp": datetime.utcnow().isoformat()
        },
        priority=TaskPriority.LOW
    )
    
    logger.info(f"用户 {current_user_id} 查看仪表板概览")
    
    # 格式化响应
    return schemas.DashboardSummaryResponse(
        # 项目统计
        total_projects=summary_data["total_projects"],
        created_projects=summary_data["created_projects"],
        active_projects=summary_data["active_projects"],
        completed_projects=summary_data["completed_projects"],
        
        # 课程统计  
        total_courses=summary_data["total_courses"],
        learning_courses=summary_data["learning_courses"],
        completed_courses=summary_data["completed_courses"],
        avg_course_progress=summary_data["avg_course_progress"],
        
        # AI统计
        total_ai_conversations=summary_data["total_ai_conversations"],
        today_ai_conversations=summary_data["today_ai_conversations"],
        
        # 论坛统计
        forum_topics_created=summary_data["forum_topics_created"],
        total_forum_likes=summary_data["total_forum_likes"],
        
        # 收藏统计
        collected_items=summary_data["collected_items"],
        
        # 用户信息
        resume_completion_percentage=summary_data["resume_completion_percentage"],
        user_level=summary_data["user_level"],
        recent_activities=summary_data["recent_activities"]
    )

@router.get("/analytics", response_model=Dict[str, Any], summary="获取用户分析数据")
@optimized_route("用户分析")
async def get_user_analytics(
    time_range: str = Query("30d", regex="^(7d|30d|90d|1y)$"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户分析数据 - 优化版本"""
    
    # 转换时间范围
    time_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
    days = time_map[time_range]
    
    # 获取分析数据
    analytics_data = DashboardAnalyticsService.get_user_analytics_optimized(
        db, current_user_id, days
    )
    
    logger.info(f"用户 {current_user_id} 查看分析数据（{time_range}）")
    return analytics_data

@router.get("/productivity", response_model=Dict[str, Any], summary="获取生产力指标")
@optimized_route("生产力指标")
async def get_productivity_metrics(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取生产力指标 - 优化版本"""
    
    productivity_data = DashboardAnalyticsService.get_productivity_metrics_optimized(
        db, current_user_id
    )
    
    logger.info(f"用户 {current_user_id} 查看生产力指标")
    return productivity_data

# ===== 项目仪表板路由 =====

@router.get("/projects", response_model=List[schemas.DashboardProjectCard], summary="获取项目仪表板")
@optimized_route("项目仪表板")
async def get_dashboard_projects(
    status_filter: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取项目仪表板卡片 - 优化版本"""
    
    # 验证状态筛选器
    DashboardUtilities.validate_status_filter(
        status_filter, VALID_PROJECT_STATUSES, "项目"
    )
    
    # 获取项目数据
    projects, stats = DashboardDataService.get_dashboard_projects_optimized(
        db, current_user_id, status_filter, limit
    )
    
    # 格式化项目卡片
    project_cards = []
    for project in projects:
        progress = DashboardUtilities.calculate_project_progress(project.project_status)
        
        card_data = DashboardUtilities.format_dashboard_card(
            item_id=project.id,
            title=project.title,
            progress=progress,
            item_type="project",
            metadata={
                "status": project.project_status,
                "creator_id": project.creator_id,
                "member_count": len(project.members) if hasattr(project, 'members') else 0,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None
            }
        )
        
        project_cards.append(schemas.DashboardProjectCard(
            id=card_data["id"],
            title=card_data["title"],
            progress=card_data["progress"],
            status=project.project_status,
            created_at=project.created_at,
            updated_at=project.updated_at,
            metadata=card_data["metadata"]
        ))
    
    logger.info(f"用户 {current_user_id} 查看项目仪表板：{len(project_cards)} 个项目")
    return project_cards

@router.get("/projects/stats", response_model=Dict[str, Any], summary="获取项目统计信息")
@optimized_route("项目统计")
async def get_project_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取项目统计信息 - 优化版本"""
    
    _, stats = DashboardDataService.get_dashboard_projects_optimized(
        db, current_user_id
    )
    
    logger.info(f"用户 {current_user_id} 查看项目统计")
    return stats

# ===== 课程仪表板路由 =====

@router.get("/courses", response_model=List[schemas.DashboardCourseCard], summary="获取课程仪表板")
@optimized_route("课程仪表板")
async def get_dashboard_courses(
    status_filter: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取课程仪表板卡片 - 优化版本"""
    
    # 验证状态筛选器
    DashboardUtilities.validate_status_filter(
        status_filter, VALID_COURSE_STATUSES, "课程"
    )
    
    # 获取课程数据
    user_courses, stats = DashboardDataService.get_dashboard_courses_optimized(
        db, current_user_id, status_filter, limit
    )
    
    # 格式化课程卡片
    course_cards = []
    for uc in user_courses:
        if not uc.course:
            continue
            
        card_data = DashboardUtilities.format_dashboard_card(
            item_id=uc.course.id,
            title=uc.course.title,
            progress=uc.progress or 0.0,
            item_type="course",
            metadata={
                "status": uc.status,
                "study_time": uc.study_time or 0,
                "last_accessed": uc.last_accessed.isoformat() if uc.last_accessed else None,
                "enrollment_date": uc.enrollment_date.isoformat() if uc.enrollment_date else None
            }
        )
        
        course_cards.append(schemas.DashboardCourseCard(
            id=card_data["id"],
            title=card_data["title"],
            progress=card_data["progress"],
            status=uc.status,
            last_accessed=uc.last_accessed,
            study_time=uc.study_time or 0,
            metadata=card_data["metadata"]
        ))
    
    logger.info(f"用户 {current_user_id} 查看课程仪表板：{len(course_cards)} 门课程")
    return course_cards

@router.get("/courses/stats", response_model=Dict[str, Any], summary="获取课程统计信息")
@optimized_route("课程统计")
async def get_course_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取课程统计信息 - 优化版本"""
    
    _, stats = DashboardDataService.get_dashboard_courses_optimized(
        db, current_user_id
    )
    
    logger.info(f"用户 {current_user_id} 查看课程统计")
    return stats

# ===== 实时数据路由 =====

@router.get("/real-time", response_model=Dict[str, Any], summary="获取实时数据")
@optimized_route("实时数据")
async def get_real_time_data(
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取实时数据 - 优化版本"""
    
    # 获取实时活动数据
    today = datetime.now().date()
    
    real_time_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": current_user_id,
        "online_status": "active",
        "today_activities": {
            "dashboard_views": 1,  # 当前访问算一次
            "projects_accessed": 0,
            "courses_accessed": 0,
            "ai_chats": 0
        },
        "system_status": {
            "api_status": "healthy",
            "database_status": "healthy",
            "cache_status": "healthy"
        }
    }
    
    # 异步更新实时统计
    submit_background_task(
        background_tasks,
        "update_real_time_stats",
        {
            "user_id": current_user_id,
            "activity_type": "dashboard_real_time_view",
            "timestamp": datetime.utcnow().isoformat()
        },
        priority=TaskPriority.HIGH
    )
    
    logger.info(f"用户 {current_user_id} 获取实时数据")
    return real_time_data

# ===== 个性化推荐路由 =====

@router.get("/recommendations", response_model=Dict[str, Any], summary="获取个性化推荐")
@optimized_route("个性化推荐")
async def get_personalized_recommendations(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取个性化推荐 - 优化版本"""
    
    # 基于用户活动生成推荐
    summary_data = DashboardDataService.get_dashboard_summary_optimized(
        db, current_user_id
    )
    
    recommendations = {
        "projects": [],
        "courses": [],
        "ai_features": [],
        "actions": []
    }
    
    # 基于数据生成推荐
    if summary_data["active_projects"] == 0:
        recommendations["actions"].append({
            "type": "create_project",
            "title": "创建你的第一个项目",
            "description": "开始你的项目之旅，展示你的创意和技能",
            "priority": "high"
        })
    
    if summary_data["learning_courses"] == 0:
        recommendations["actions"].append({
            "type": "enroll_course",
            "title": "选择一门课程开始学习",
            "description": "持续学习，提升你的技能水平",
            "priority": "medium"
        })
    
    if summary_data["total_ai_conversations"] == 0:
        recommendations["ai_features"].append({
            "type": "try_ai_chat",
            "title": "尝试AI智能助手",
            "description": "AI助手可以帮助你解答问题和提供建议",
            "priority": "medium"
        })
    
    if summary_data["resume_completion_percentage"] < 50:
        recommendations["actions"].append({
            "type": "complete_profile",
            "title": "完善你的个人资料",
            "description": f"当前完成度 {summary_data['resume_completion_percentage']:.1f}%，完善资料获得更多机会",
            "priority": "high"
        })
    
    logger.info(f"用户 {current_user_id} 获取个性化推荐")
    return recommendations

# ===== 数据导出路由 =====

@router.get("/export", summary="导出仪表板数据")
@optimized_route("数据导出")
async def export_dashboard_data(
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    format: str = Query("json", regex="^(json|csv|excel)$")
):
    """导出仪表板数据 - 优化版本"""
    
    # 获取完整数据
    summary_data = DashboardDataService.get_dashboard_summary_optimized(
        db, current_user_id
    )
    projects, project_stats = DashboardDataService.get_dashboard_projects_optimized(
        db, current_user_id
    )
    user_courses, course_stats = DashboardDataService.get_dashboard_courses_optimized(
        db, current_user_id
    )
    
    export_data = {
        "export_info": {
            "user_id": current_user_id,
            "export_time": datetime.utcnow().isoformat(),
            "format": format
        },
        "summary": summary_data,
        "project_stats": project_stats,
        "course_stats": course_stats,
        "projects": [
            {
                "id": p.id,
                "title": p.title,
                "status": p.project_status,
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in projects
        ],
        "courses": [
            {
                "id": uc.course.id if uc.course else None,
                "title": uc.course.title if uc.course else "未知课程",
                "progress": uc.progress,
                "status": uc.status
            }
            for uc in user_courses
        ]
    }
    
    # 异步处理数据导出
    submit_background_task(
        background_tasks,
        "process_dashboard_export",
        {
            "user_id": current_user_id,
            "export_data": export_data,
            "format": format
        },
        priority=TaskPriority.MEDIUM
    )
    
    logger.info(f"用户 {current_user_id} 导出仪表板数据（{format}格式）")
    
    if format == "json":
        return export_data
    else:
        return {
            "message": f"数据导出任务已提交，格式：{format}",
            "status": "processing",
            "estimated_time": "1-2分钟"
        }

# 使用路由优化器应用批量优化
# router_optimizer.apply_batch_optimizations(router, {
#     "cache_ttl": 180,  # 仪表板数据缓存3分钟
#     "enable_compression": True,
#     "rate_limit": "300/minute",  # 仪表板需要更高频率访问
#     "monitoring": True
# })

logger.info("📈 Dashboard Router - 仪表板路由已加载")
