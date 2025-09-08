# project/routers/auth/auth.py
"""
认证模块优化版本 - 应用统一优化模式
基于courses和forum模块的成功优化经验
"""
import asyncio
from fastapi import APIRouter, Form, Depends, HTTPException, status, BackgroundTasks
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
        
        # 后台任务：发送欢迎邮件和生成推荐内容
        # 目前暂时注释掉，避免阻塞注册流程
        # TODO: 实现后台任务处理系统
        # await submit_background_task(...)
    
    
    AuthUtils.log_auth_event("registration_success", result["user"].id, {
        "username": result["user"].username
    })
    
    logger.info(f"用户注册成功: {result['user'].username} (ID: {result['user'].id})")
    return AuthUtils.format_user_response(result["user"])

# ===== 用户登录 =====

@router.post("/token", response_model=schemas.Token, summary="用户登录")
@optimized_route("用户登录")
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
async def update_current_user(
    user_update: schemas.StudentUpdate,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新当前登录用户详情 - 优化版本"""
    
    # 过滤掉None值 - 兼容新旧版本Pydantic
    if hasattr(user_update, 'model_dump'):
        update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}
    else:
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
    
    # 使用直接数据库更新，避免会话问题
    try:
        # 验证更新数据
        from project.utils.auth.auth_utils import validate_update_data
        validate_update_data(update_data, current_user_id, db)
        
        # 直接更新数据库
        from sqlalchemy import update
        from datetime import datetime
        
        # 构建更新语句
        stmt = update(User).where(User.id == current_user_id).values(
            **update_data,
            updated_at=datetime.utcnow()
        )
        
        db.execute(stmt)
        db.commit()
        
        # 重新查询用户信息
        updated_user = db.query(User).filter(User.id == current_user_id).first()
        user_response_data = AuthUtils.format_user_response(updated_user, include_sensitive=True)
        
        logger.info(f"用户 {current_user_id} 更新资料成功，后台任务已忽略")
        
    except Exception as e:
        db.rollback()
        logger.error(f"更新用户信息失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新用户信息失败: {str(e)}")
    
    AuthUtils.log_auth_event("profile_update", current_user_id, {
        "updated_fields": list(update_data.keys())
    })
    
    logger.info(f"用户 {current_user_id} 更新个人信息成功")
    return user_response_data

# ===== 密码管理 =====

@router.post("/change-password", summary="修改密码")
@optimized_route("修改密码")
async def change_password(
    background_tasks: BackgroundTasks,
    current_password: str = Form(...),
    new_password: str = Form(...),
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
    
    # 直接从数据库获取用户，确保在当前会话中
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 验证当前密码
    from project.utils import pwd_context
    if not pwd_context.verify(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码不正确"
        )
    
    # 更新密码
    try:
        new_password_hash = pwd_context.hash(new_password)
        logger.info(f"密码修改 - 生成新密码哈希: {new_password_hash}")
        
        user.password_hash = new_password_hash
        user.updated_at = datetime.utcnow()
        
        # 显式提交事务并刷新
        db.commit()
        db.refresh(user)
        
        logger.info(f"密码修改 - 用户ID: {current_user_id}, 新密码哈希已设置并提交")
        logger.info(f"密码修改 - 提交后用户密码哈希: {user.password_hash}")
        
        # 清除用户相关缓存 - 修正：使用同步调用
        try:
            cache_manager.delete_pattern(f"user:{current_user_id}:*")
            cache_manager.delete_pattern(f"auth:credential:*")
            logger.info(f"密码修改 - 已清除用户缓存")
        except Exception as e:
            logger.warning(f"清除缓存失败: {str(e)}")
        
        # 异步发送密码修改通知 - 简化处理，避免协程错误
        # submit_background_task(
        #     background_tasks,
        #     "send_password_change_notification",
        #     {"user_id": current_user_id, "email": user.email},
        #     priority=TaskPriority.HIGH
        # )
        logger.info(f"用户 {current_user_id} 密码修改成功，后台任务已忽略")
            
    except Exception as e:
        db.rollback()
        logger.error(f"修改密码失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"修改密码失败: {str(e)}")
    
    AuthUtils.log_auth_event("password_change", current_user_id, {})
    
    logger.info(f"用户 {current_user_id} 修改密码成功")
    
    # 立即验证新密码是否正确设置
    test_verify = pwd_context.verify(new_password, user.password_hash)
    logger.info(f"密码修改后立即验证结果: {test_verify}")
    
    # 额外验证：重新从数据库查询用户并验证密码
    fresh_user = db.query(User).filter(User.id == current_user_id).first()
    fresh_verify = pwd_context.verify(new_password, fresh_user.password_hash)
    logger.info(f"密码修改后重新查询验证结果: {fresh_verify}")
    logger.info(f"重新查询的密码哈希: {fresh_user.password_hash}")
    
    return {"message": "密码修改成功"}

# ===== 账户管理 =====

@router.post("/deactivate", summary="停用账户")
@optimized_route("停用账户")
async def deactivate_account(
    background_tasks: BackgroundTasks,
    password: str = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """停用用户账户 - 优化版本"""
    
    # 强制清除缓存，确保获取最新用户信息
    try:
        cache_manager.delete_pattern(f"user:{current_user_id}:*")
    except Exception as e:
        logger.warning(f"清除用户缓存失败: {str(e)}")
    
    # 直接从数据库查询最新用户信息，跳过缓存
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 再次强制刷新数据
    db.refresh(user)
    
    # 验证密码
    from project.utils import pwd_context
    logger.info(f"停用账户 - 用户ID: {current_user_id}, 用户名: {user.username}")
    logger.info(f"停用账户 - 接收到的密码: '{password}'")
    logger.info(f"停用账户 - 接收到的密码长度: {len(password)}")
    logger.info(f"停用账户 - 数据库中密码哈希: {user.password_hash}")
    
    # 简化验证过程
    try:
        password_valid = pwd_context.verify(password, user.password_hash)
        logger.info(f"停用账户 - 密码验证结果: {password_valid}")
        
        if not password_valid:
            logger.warning(f"用户 {current_user_id} 停用账户时密码验证失败")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="密码不正确"
            )
    except Exception as e:
        logger.error(f"停用账户密码验证异常: {e}")
        logger.error(f"异常类型: {type(e)}")
        import traceback
        logger.error(f"异常堆栈: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"验证密码时发生错误: {str(e)}"
        )
    
    # 停用账户 - 由于User模型没有is_active和deactivated_at字段，使用其他方式
    with database_transaction(db):
        # 使用用户名后缀标记停用状态
        original_username = user.username
        user.username = f"{user.username}_deactivated_{int(datetime.utcnow().timestamp())}"
        user.updated_at = datetime.utcnow()
        db.flush()
        
        # 清除所有相关缓存 - 修正：使用同步调用
        try:
            cache_manager.delete_pattern(f"user:{current_user_id}:*")
            cache_manager.delete_pattern(f"auth:credential:*")
        except Exception as e:
            logger.warning(f"清除缓存失败: {str(e)}")
        
        # 异步处理账户停用后续操作 - 简化处理，避免协程错误
        # submit_background_task(
        #     background_tasks,
        #     "process_account_deactivation",
        #     {"user_id": current_user_id},
        #     priority=TaskPriority.HIGH
        # )
        logger.info(f"用户 {current_user_id} 账户停用成功，后台任务已忽略")
    
    AuthUtils.log_auth_event("account_deactivation", current_user_id, {})
    
    logger.info(f"用户 {current_user_id} 停用账户成功")
    return {"message": "账户已停用"}

# ===== 用户统计 =====

@router.get("/users/me/stats", summary="获取用户统计信息")
@optimized_route("用户统计信息")
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
            ForumTopic.owner_id == current_user_id  # 修正：使用owner_id而不是author_id
            # ForumTopic没有status字段，去掉状态过滤
        ).scalar() or 0,
        
        "comments_count": db.query(func.count(ForumComment.id)).filter(
            ForumComment.owner_id == current_user_id  # 修正：使用owner_id而不是author_id
            # ForumComment没有status字段，去掉状态过滤
        ).scalar() or 0,
        
        "projects_count": db.query(func.count(Project.id)).filter(
            Project.creator_id == current_user_id  # 修正：Project使用creator_id而不是owner_id
            # Project模型可能有status字段，保留此过滤（如果有的话）
        ).scalar() or 0,
        
        "total_points": db.query(User.total_points).filter(User.id == current_user_id).scalar() or 0,
        "login_count": db.query(User.login_count).filter(User.id == current_user_id).scalar() or 0  # 修正：使用login_count
    }
    
    # 缓存统计结果
    cache_manager.set(cache_key, stats, expire=300)  # 5分钟缓存，修正参数名
    
    return stats

# 使用路由优化器应用批量优化
# # router_optimizer.apply_batch_optimizations(router, {
# #     "cache_ttl": 600,
# #     "enable_compression": True,
# #     "rate_limit": "50/minute",
# #     "monitoring": True
# # })

logger.info("🔐 Auth Module - 身份认证模块已加载")
