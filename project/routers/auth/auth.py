# project/routers/auth/auth.py
"""
认证模块优化版本 - 应用统一优化模式
基于courses和forum模块的成功优化经验
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

# 核心依赖
from project.database import get_db
from project.models import User
from project.utils import get_current_user_id
import project.schemas as schemas

# 优化工具导入
from project.services.auth_service import AuthService, AuthUtils
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["认证管理"])

# ===== 健康检查 =====

@router.get("/health", summary="健康检查")
@optimized_route("健康检查")
def health_check():
    """检查API服务是否正常运行 - 优化版本"""
    return {
        "status": "ok", 
        "message": "鸿庆书云创新协作平台后端API运行正常！",
        "timestamp": datetime.utcnow().isoformat()
    }

# ===== 用户注册 =====

@router.post("/register", response_model=schemas.StudentResponse, summary="用户注册")
@optimized_route("用户注册")
@handle_database_errors
async def register_user(
    user_data: schemas.StudentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """用户注册 - 优化版本"""
    
    AuthUtils.log_auth_event("registration_attempt", None, {
        "email": user_data.email,
        "phone": getattr(user_data, 'phone_number', None)
    })
    
    # 验证密码强度
    password_errors = AuthUtils.validate_password_strength(user_data.password)
    if password_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": password_errors}
        )
    
    # 验证邮箱格式
    if not AuthUtils.validate_email_format(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱格式不正确"
        )
    
    # 验证手机号格式（如果提供）
    if hasattr(user_data, 'phone_number') and user_data.phone_number:
        if not AuthUtils.validate_phone_format(user_data.phone_number):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号格式不正确"
            )
    
    # 使用事务注册用户
    with database_transaction(db):
        result = AuthService.register_user_optimized(db, user_data.dict())
        
        # 异步发送欢迎邮件
        submit_background_task(
            background_tasks,
            "send_welcome_email",
            {"user_id": result["user"].id, "email": result["user"].email},
            priority=TaskPriority.MEDIUM
        )
        
        # 异步生成用户推荐内容
        submit_background_task(
            background_tasks,
            "generate_user_recommendations",
            {"user_id": result["user"].id},
            priority=TaskPriority.LOW
        )
    
    AuthUtils.log_auth_event("registration_success", result["user"].id, {
        "username": result["user"].username
    })
    
    logger.info(f"用户注册成功: {result['user'].username} (ID: {result['user'].id})")
    return AuthUtils.format_user_response(result["user"])

# ===== 用户登录 =====

@router.post("/token", response_model=schemas.Token, summary="用户登录")
@optimized_route("用户登录")
@handle_database_errors
async def login_user(
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """用户登录并获取JWT令牌 - 优化版本"""
    
    AuthUtils.log_auth_event("login_attempt", None, {
        "credential": form_data.username
    })
    
    # 使用事务处理登录
    with database_transaction(db):
        result = AuthService.login_user_optimized(
            db, 
            form_data.username, 
            form_data.password
        )
        
        # 异步记录登录日志
        submit_background_task(
            background_tasks,
            "log_user_activity",
            {
                "user_id": result["user"].id,
                "action": "login",
                "ip_address": None,  # 可以从request中获取
                "user_agent": None   # 可以从request中获取
            },
            priority=TaskPriority.LOW
        )
        
        # 异步更新用户活跃度统计
        submit_background_task(
            background_tasks,
            "update_user_activity_stats",
            {"user_id": result["user"].id},
            priority=TaskPriority.LOW
        )
    
    AuthUtils.log_auth_event("login_success", result["user"].id, {
        "username": result["user"].username
    })
    
    logger.info(f"用户登录成功: {result['user'].username} (ID: {result['user'].id})")
    return {
        "access_token": result["access_token"],
        "token_type": result["token_type"]
    }

# ===== 获取当前用户信息 =====

@router.get("/users/me", response_model=schemas.StudentResponse, summary="获取当前用户信息")
@optimized_route("获取用户信息")
@handle_database_errors
async def get_current_user(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取当前登录用户详情 - 优化版本"""
    
    user = AuthService.get_user_by_id_optimized(db, current_user_id)
    
    logger.debug(f"用户 {current_user_id} 获取个人信息")
    return AuthUtils.format_user_response(user, include_sensitive=True)

# ===== 更新用户信息 =====

@router.put("/users/me", response_model=schemas.StudentResponse, summary="更新当前用户信息")
@optimized_route("更新用户信息")
@handle_database_errors
async def update_current_user(
    user_update: schemas.StudentUpdate,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新当前登录用户详情 - 优化版本"""
    
    # 过滤掉None值
    update_data = {k: v for k, v in user_update.dict().items() if v is not None}
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个要更新的字段"
        )
    
    # 验证邮箱格式（如果更新邮箱）
    if "email" in update_data:
        if not AuthUtils.validate_email_format(update_data["email"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱格式不正确"
            )
    
    # 验证手机号格式（如果更新手机号）
    if "phone_number" in update_data:
        if not AuthUtils.validate_phone_format(update_data["phone_number"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号格式不正确"
            )
    
    # 使用事务更新用户信息
    with database_transaction(db):
        user = AuthService.update_user_profile_optimized(db, current_user_id, update_data)
        
        # 异步更新搜索索引
        submit_background_task(
            background_tasks,
            "update_user_search_index",
            {"user_id": current_user_id},
            priority=TaskPriority.MEDIUM
        )
        
        # 异步同步用户数据到其他系统
        submit_background_task(
            background_tasks,
            "sync_user_data",
            {"user_id": current_user_id, "changes": list(update_data.keys())},
            priority=TaskPriority.LOW
        )
    
    AuthUtils.log_auth_event("profile_update", current_user_id, {
        "updated_fields": list(update_data.keys())
    })
    
    logger.info(f"用户 {current_user_id} 更新个人信息成功")
    return AuthUtils.format_user_response(user, include_sensitive=True)

# ===== 密码管理 =====

@router.post("/change-password", summary="修改密码")
@optimized_route("修改密码")
@handle_database_errors
async def change_password(
    current_password: str,
    new_password: str,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """修改用户密码 - 优化版本"""
    
    # 验证新密码强度
    password_errors = AuthUtils.validate_password_strength(new_password)
    if password_errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": password_errors}
        )
    
    user = AuthService.get_user_by_id_optimized(db, current_user_id)
    
    # 验证当前密码
    from project.utils import pwd_context
    if not pwd_context.verify(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码不正确"
        )
    
    # 更新密码
    with database_transaction(db):
        user.password_hash = pwd_context.hash(new_password)
        user.updated_at = datetime.utcnow()
        db.flush()
        
        # 清除用户相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"user:{current_user_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"auth:credential:*"))
        
        # 异步发送密码修改通知
        submit_background_task(
            background_tasks,
            "send_password_change_notification",
            {"user_id": current_user_id, "email": user.email},
            priority=TaskPriority.HIGH
        )
    
    AuthUtils.log_auth_event("password_change", current_user_id, {})
    
    logger.info(f"用户 {current_user_id} 修改密码成功")
    return {"message": "密码修改成功"}

# ===== 账户管理 =====

@router.post("/deactivate", summary="停用账户")
@optimized_route("停用账户")
@handle_database_errors
async def deactivate_account(
    password: str,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """停用用户账户 - 优化版本"""
    
    user = AuthService.get_user_by_id_optimized(db, current_user_id)
    
    # 验证密码
    from project.utils import pwd_context
    if not pwd_context.verify(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码不正确"
        )
    
    # 停用账户
    with database_transaction(db):
        user.is_active = False
        user.deactivated_at = datetime.utcnow()
        db.flush()
        
        # 清除所有相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"user:{current_user_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"auth:credential:*"))
        
        # 异步处理账户停用后续操作
        submit_background_task(
            background_tasks,
            "process_account_deactivation",
            {"user_id": current_user_id},
            priority=TaskPriority.HIGH
        )
    
    AuthUtils.log_auth_event("account_deactivation", current_user_id, {})
    
    logger.info(f"用户 {current_user_id} 停用账户成功")
    return {"message": "账户已停用"}

# ===== 用户统计 =====

@router.get("/users/me/stats", summary="获取用户统计信息")
@optimized_route("用户统计信息")
@handle_database_errors
async def get_user_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户统计信息 - 优化版本"""
    
    cache_key = f"user:{current_user_id}:stats"
    cached_stats = cache_manager.get(cache_key)
    if cached_stats:
        return cached_stats
    
    # 查询用户统计数据
    from sqlalchemy import func
    from project.models import ForumTopic, ForumComment, Project
    
    stats = {
        "topics_count": db.query(func.count(ForumTopic.id)).filter(
            ForumTopic.author_id == current_user_id,
            ForumTopic.is_deleted == False
        ).scalar() or 0,
        
        "comments_count": db.query(func.count(ForumComment.id)).filter(
            ForumComment.author_id == current_user_id,
            ForumComment.is_deleted == False
        ).scalar() or 0,
        
        "projects_count": db.query(func.count(Project.id)).filter(
            Project.author_id == current_user_id,
            Project.is_deleted == False
        ).scalar() or 0,
        
        "total_points": db.query(User.total_points).filter(User.id == current_user_id).scalar() or 0,
        "current_level": db.query(User.level).filter(User.id == current_user_id).scalar() or 1
    }
    
    # 缓存统计结果
    cache_manager.set(cache_key, stats, expire_time=300)  # 5分钟缓存
    
    return stats

# 使用路由优化器应用批量优化
# # router_optimizer.apply_batch_optimizations(router, {
# #     "cache_ttl": 600,
# #     "enable_compression": True,
# #     "rate_limit": "50/minute",
# #     "monitoring": True
# # })

logger.info("🔐 Auth Module - 身份认证模块已加载")
