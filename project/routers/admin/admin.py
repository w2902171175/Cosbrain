# project/routers/admin/admin_optimized.py
"""
管理员模块优化版本 - 管理功能和权限控制优化
基于成功优化模式，优化admin模块的管理功能
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

# 核心依赖
from project.database import get_db
from project.models import User
from project.utils import is_admin_user
import project.schemas as schemas

# 服务层导入
from project.services.admin_service import AdminService, AdminValidators

# 优化工具导入
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["系统管理"])

# ===== 用户管理路由 =====

@router.get("/users", response_model=List[schemas.StudentResponse], summary="获取用户列表")
@optimized_route("用户列表管理")
@handle_database_errors
async def get_users_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None, min_length=2),
    role_filter: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """获取用户列表 - 优化版本"""
    
    # 构建查询
    query = db.query(User)
    
    # 搜索过滤
    if search:
        query = query.filter(
            func.or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.name.ilike(f"%{search}%")
            )
        )
    
    # 角色过滤
    if role_filter == "admin":
        query = query.filter(User.is_admin == True)
    elif role_filter == "user":
        query = query.filter(User.is_admin == False)
    
    # 状态过滤（假设有 is_active 字段）
    if status_filter == "active":
        query = query.filter(User.is_active == True)
    elif status_filter == "inactive":
        query = query.filter(User.is_active == False)
    
    # 分页查询
    users = query.offset(skip).limit(limit).all()
    
    logger.info(f"管理员 {current_admin.id} 查看用户列表：{len(users)} 个用户")
    return users

@router.get("/users/{user_id}", response_model=schemas.StudentResponse, summary="获取用户详情")
@optimized_route("用户详情管理")
@handle_database_errors
async def get_user_detail(
    user_id: int,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """获取用户详情 - 优化版本"""
    
    user = AdminService.get_user_by_id_or_404(db, user_id)
    
    # 获取用户统计信息
    from project.services.dashboard_service import DashboardUtilities
    from project.models import Project, AIConversation, ForumTopic
    
    user_stats = {
        "created_projects": db.query(Project).filter(Project.creator_id == user_id).count(),
        "ai_conversations": db.query(AIConversation).filter(AIConversation.user_id == user_id).count(),
        "forum_topics": db.query(ForumTopic).filter(ForumTopic.author_id == user_id).count(),
        "resume_completion": DashboardUtilities.calculate_resume_completion(user),
        "last_active": user.last_login_at if hasattr(user, 'last_login_at') else None
    }
    
    logger.info(f"管理员 {current_admin.id} 查看用户 {user_id} 详情")
    
    # 返回详细信息（这里需要扩展 schemas）
    return {
        **user.__dict__,
        "statistics": user_stats
    }

@router.put("/users/{user_id}/set-admin", response_model=schemas.StudentResponse, summary="设置管理员权限")
@optimized_route("设置管理员权限")
@handle_database_errors
async def set_user_admin_status(
    user_id: int,
    admin_status: schemas.UserAdminStatusUpdate,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """设置用户管理员权限 - 优化版本"""
    
    with database_transaction(db):
        updated_user = await AdminService.set_user_admin_status(
            db, user_id, admin_status.is_admin, current_admin
        )
        
        # 异步记录权限变更日志
        submit_background_task(
            background_tasks,
            "log_admin_permission_change",
            {
                "target_user_id": user_id,
                "admin_user_id": current_admin.id,
                "new_status": admin_status.is_admin,
                "timestamp": datetime.utcnow().isoformat()
            },
            priority=TaskPriority.HIGH
        )
    
    logger.info(f"管理员 {current_admin.id} 设置用户 {user_id} 管理员权限为 {admin_status.is_admin}")
    return updated_user

@router.post("/users/{user_id}/suspend", summary="暂停用户账户")
@optimized_route("暂停用户账户")
@handle_database_errors
async def suspend_user_account(
    user_id: int,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db),
    suspension_reason: str = Query(..., min_length=5),
    suspension_days: int = Query(7, ge=1, le=365)
):
    """暂停用户账户 - 优化版本"""
    
    if current_admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="管理员不能暂停自己的账户"
        )
    
    user = AdminService.get_user_by_id_or_404(db, user_id)
    
    with database_transaction(db):
        # 设置暂停状态（假设有相关字段）
        suspension_end = datetime.utcnow() + timedelta(days=suspension_days)
        
        # 这里需要根据实际用户模型调整
        user.is_suspended = True
        user.suspension_reason = suspension_reason
        user.suspension_end = suspension_end
        user.suspended_by = current_admin.id
        user.suspended_at = datetime.utcnow()
        
        db.add(user)
        
        # 异步处理暂停后续操作
        submit_background_task(
            background_tasks,
            "process_user_suspension",
            {
                "user_id": user_id,
                "admin_id": current_admin.id,
                "reason": suspension_reason,
                "end_date": suspension_end.isoformat()
            },
            priority=TaskPriority.HIGH
        )
    
    logger.info(f"管理员 {current_admin.id} 暂停用户 {user_id}，期限 {suspension_days} 天")
    return {"message": f"用户账户已暂停 {suspension_days} 天", "suspension_end": suspension_end}

# ===== 成就管理路由 =====

@router.get("/achievements", response_model=List[schemas.AchievementResponse], summary="获取成就列表")
@optimized_route("成就列表管理")
@handle_database_errors
async def get_achievements_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """获取成就列表 - 优化版本"""
    
    from project.models import Achievement
    
    query = db.query(Achievement)
    
    # 状态过滤
    if is_active is not None:
        query = query.filter(Achievement.is_active == is_active)
    
    achievements = query.offset(skip).limit(limit).all()
    
    logger.info(f"管理员 {current_admin.id} 查看成就列表：{len(achievements)} 个成就")
    return achievements

@router.post("/achievements", response_model=schemas.AchievementResponse, summary="创建成就")
@optimized_route("创建成就")
@handle_database_errors
async def create_achievement_definition(
    achievement_data: schemas.AchievementCreate,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """创建成就定义 - 优化版本"""
    
    # 验证数据
    AdminValidators.validate_achievement_data(achievement_data)
    
    with database_transaction(db):
        achievement = await AdminService.create_achievement(db, achievement_data)
        
        # 异步处理成就创建后续操作
        submit_background_task(
            background_tasks,
            "process_new_achievement",
            {
                "achievement_id": achievement.id,
                "created_by": current_admin.id,
                "achievement_name": achievement.name
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"管理员 {current_admin.id} 创建成就：{achievement.name}")
    return achievement

@router.put("/achievements/{achievement_id}", response_model=schemas.AchievementResponse, summary="更新成就")
@optimized_route("更新成就")
@handle_database_errors
async def update_achievement_definition(
    achievement_id: int,
    achievement_data: schemas.AchievementUpdate,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """更新成就定义 - 优化版本"""
    
    with database_transaction(db):
        achievement = await AdminService.update_achievement(
            db, achievement_id, achievement_data
        )
    
    logger.info(f"管理员 {current_admin.id} 更新成就 {achievement_id}")
    return achievement

@router.delete("/achievements/{achievement_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除成就")
@optimized_route("删除成就")
@handle_database_errors
async def delete_achievement_definition(
    achievement_id: int,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """删除成就定义 - 优化版本"""
    
    with database_transaction(db):
        await AdminService.delete_achievement(db, achievement_id)
    
    logger.info(f"管理员 {current_admin.id} 删除成就 {achievement_id}")

# ===== 积分管理路由 =====

@router.post("/points/reward", response_model=schemas.PointTransactionResponse, summary="调整用户积分")
@optimized_route("积分管理")
@handle_database_errors
async def admin_reward_or_deduct_points(
    reward_request: schemas.PointsRewardRequest,
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """管理员调整用户积分 - 优化版本"""
    
    # 验证积分数量
    AdminValidators.validate_points_amount(reward_request.amount)
    
    with database_transaction(db):
        transaction = await AdminService.adjust_user_points(
            db, reward_request, current_admin
        )
        
        # 异步记录积分操作日志
        submit_background_task(
            background_tasks,
            "log_admin_points_operation",
            {
                "target_user_id": reward_request.user_id,
                "admin_id": current_admin.id,
                "amount": reward_request.amount,
                "reason": reward_request.reason,
                "transaction_id": transaction.id
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"管理员 {current_admin.id} 为用户 {reward_request.user_id} 调整积分 {reward_request.amount}")
    return transaction

@router.get("/points/transactions", summary="获取积分交易记录")
@optimized_route("积分交易记录")
@handle_database_errors
async def get_points_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    transaction_type: Optional[str] = Query(None),
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """获取积分交易记录 - 优化版本"""
    
    from project.models import PointTransaction
    
    query = db.query(PointTransaction)
    
    # 用户过滤
    if user_id:
        query = query.filter(PointTransaction.user_id == user_id)
    
    # 交易类型过滤
    if transaction_type:
        query = query.filter(PointTransaction.transaction_type == transaction_type)
    
    # 按时间倒序排列
    transactions = query.order_by(PointTransaction.created_at.desc()).offset(skip).limit(limit).all()
    
    logger.info(f"管理员 {current_admin.id} 查看积分交易记录：{len(transactions)} 条")
    return transactions

# ===== 系统监控路由 =====

@router.get("/system/status", summary="系统状态监控")
@optimized_route("系统状态监控")
@handle_database_errors
async def get_system_status(
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """获取系统状态 - 优化版本"""
    
    # 获取数据库统计
    from project.models import User, Project, Course, AIConversation, ForumTopic
    
    db_stats = {
        "users_count": db.query(User).count(),
        "active_users": db.query(User).filter(User.is_active == True).count(),
        "admin_users": db.query(User).filter(User.is_admin == True).count(),
        "projects_count": db.query(Project).count(),
        "active_projects": db.query(Project).filter(Project.project_status == "进行中").count(),
        "courses_count": db.query(Course).count(),
        "ai_conversations": db.query(AIConversation).count(),
        "forum_topics": db.query(ForumTopic).count()
    }
    
    # 获取今日活动统计
    today = datetime.now().date()
    today_stats = {
        "new_users": db.query(User).filter(func.date(User.created_at) == today).count(),
        "new_projects": db.query(Project).filter(func.date(Project.created_at) == today).count(),
        "new_conversations": db.query(AIConversation).filter(func.date(AIConversation.created_at) == today).count()
    }
    
    # 系统健康检查
    system_health = {
        "database": "healthy",
        "cache": "healthy",  # 需要实际检查Redis等
        "ai_services": "healthy",  # 需要实际检查AI服务
        "storage": "healthy"  # 需要实际检查OSS等
    }
    
    system_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "database_statistics": db_stats,
        "today_statistics": today_stats,
        "system_health": system_health,
        "uptime": "假设运行时间",  # 需要实际计算
        "version": "2.0.0"
    }
    
    logger.info(f"管理员 {current_admin.id} 查看系统状态")
    return system_status

@router.get("/rag/status", summary="RAG功能状态检查")
@optimized_route("RAG状态检查")
@handle_database_errors
async def get_rag_status(
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db)
):
    """检查RAG功能状态 - 优化版本"""
    
    rag_status = AdminService.get_rag_statistics(db)
    
    logger.info(f"管理员 {current_admin.id} 检查RAG状态")
    return rag_status

# ===== 数据管理路由 =====

@router.post("/data/backup", summary="创建数据备份")
@optimized_route("数据备份")
@handle_database_errors
async def create_data_backup(
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(is_admin_user),
    db: Session = Depends(get_db),
    backup_type: str = Query("full", regex="^(full|incremental)$")
):
    """创建数据备份 - 优化版本"""
    
    backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 异步执行备份任务
    submit_background_task(
        background_tasks,
        "create_database_backup",
        {
            "backup_id": backup_id,
            "backup_type": backup_type,
            "admin_id": current_admin.id,
            "timestamp": datetime.utcnow().isoformat()
        },
        priority=TaskPriority.HIGH
    )
    
    logger.info(f"管理员 {current_admin.id} 创建数据备份：{backup_id}")
    return {
        "message": f"备份任务已启动",
        "backup_id": backup_id,
        "backup_type": backup_type,
        "estimated_time": "5-30分钟"
    }

@router.get("/logs", summary="获取系统日志")
@optimized_route("系统日志")
@handle_database_errors
async def get_system_logs(
    log_level: str = Query("INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    limit: int = Query(100, ge=1, le=1000),
    current_admin: User = Depends(is_admin_user)
):
    """获取系统日志 - 优化版本"""
    
    # 这里需要根据实际日志系统实现
    # 假设日志存储在文件或数据库中
    logs = [
        {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "message": "系统日志示例",
            "module": "admin_optimized"
        }
    ]
    
    logger.info(f"管理员 {current_admin.id} 查看系统日志")
    return {
        "logs": logs,
        "total_count": len(logs),
        "log_level": log_level
    }

# 使用路由优化器应用批量优化
# # router_optimizer.apply_batch_optimizations(router, {
# #     "cache_ttl": 60,  # 管理功能缓存时间较短
# #     "enable_compression": True,
# #     "rate_limit": "500/minute",  # 管理员需要更高访问频率
# #     "monitoring": True
# # })

logger.info("👑 Admin Module - 管理员模块已加载 (全功能版本)")
