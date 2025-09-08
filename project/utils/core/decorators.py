# project/utils/core/decorators.py
"""
装饰器模块：包含项目中使用的各种装饰器
"""

import functools
import inspect
import logging
from typing import List, Optional, Callable, Any
from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from project.database import get_db
from ..auth import get_current_user_id
from project.models import User, Project, ProjectMember
from .common_utils import get_user_by_id_or_404, get_resource_or_404

logger = logging.getLogger(__name__)


def require_project_permission(
    required_permissions: List[str],
    error_message: str = "无权访问此项目",
    project_id_param: str = "project_id"
):
    """
    项目权限检查装饰器
    
    Args:
        required_permissions: 所需权限列表 ["creator", "admin", "project_admin", "member"]
        error_message: 权限不足时的错误信息
        project_id_param: 项目ID参数名（默认为"project_id"）
    
    Usage:
        @require_project_permission(["creator", "admin"])
        async def some_project_function(project_id: int, current_user_id: int, db: Session):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 提取参数
            project_id = bound.arguments.get(project_id_param)
            current_user_id = bound.arguments.get("current_user_id")
            db = bound.arguments.get("db")
            
            if not all([project_id, current_user_id, db]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="缺少必要的参数：project_id, current_user_id, db"
                )
            
            # 获取项目和用户信息
            project = get_resource_or_404(db, Project, project_id, "项目未找到")
            current_user = get_user_by_id_or_404(db, current_user_id, "用户未找到")
            
            # 检查权限
            permissions = set(required_permissions)
            user_has_permission = False
            
            # 检查是否为项目创建者
            if "creator" in permissions and project.creator_id == current_user_id:
                user_has_permission = True
            
            # 检查是否为系统管理员
            if "admin" in permissions and current_user.is_admin:
                user_has_permission = True
            
            # 检查是否为项目管理员或成员
            if ("project_admin" in permissions or "member" in permissions):
                membership = db.query(ProjectMember).filter(
                    ProjectMember.project_id == project_id,
                    ProjectMember.student_id == current_user_id,
                    ProjectMember.status == 'active'
                ).first()
                
                if membership:
                    if "project_admin" in permissions and membership.role == 'admin':
                        user_has_permission = True
                    elif "member" in permissions:
                        user_has_permission = True
            
            if not user_has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_message
                )
            
            # 执行原函数
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_admin():
    """
    系统管理员权限检查装饰器
    
    Usage:
        @require_admin()
        async def admin_only_function(current_user_id: int, db: Session):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 提取参数
            current_user_id = bound.arguments.get("current_user_id")
            db = bound.arguments.get("db")
            
            if not all([current_user_id, db]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="缺少必要的参数：current_user_id, db"
                )
            
            # 检查管理员权限
            current_user = get_user_by_id_or_404(db, current_user_id, "用户未找到")
            if not current_user.is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="需要系统管理员权限"
                )
            
            # 执行原函数
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def db_transaction(
    rollback_on_error: bool = True,
    commit_on_success: bool = True,
    refresh_result: bool = False,
    cleanup_on_error: Optional[Callable] = None
):
    """
    数据库事务处理装饰器
    
    Args:
        rollback_on_error: 出错时是否回滚
        commit_on_success: 成功时是否提交
        refresh_result: 是否刷新返回结果
        cleanup_on_error: 出错时的清理函数
    
    Usage:
        @db_transaction(rollback_on_error=True, commit_on_success=True)
        async def create_something(data, db: Session):
            # 数据库操作
            return result
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 提取数据库会话
            db = bound.arguments.get("db")
            if not db:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="缺少数据库会话参数：db"
                )
            
            try:
                # 执行原函数
                result = await func(*args, **kwargs)
                
                # 成功时提交
                if commit_on_success:
                    db.commit()
                    
                    # 刷新结果对象
                    if refresh_result and hasattr(result, '__table__'):
                        db.refresh(result)
                
                return result
                
            except HTTPException:
                # HTTP异常直接重新抛出
                if rollback_on_error:
                    db.rollback()
                if cleanup_on_error:
                    await cleanup_on_error()
                raise
                
            except IntegrityError as e:
                # 数据库完整性错误
                if rollback_on_error:
                    db.rollback()
                if cleanup_on_error:
                    await cleanup_on_error()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="数据冲突或唯一性约束错误"
                )
                
            except Exception as e:
                # 其他异常
                if rollback_on_error:
                    db.rollback()
                if cleanup_on_error:
                    await cleanup_on_error()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"操作失败: {str(e)}"
                )
        
        return wrapper
    return decorator


def with_oss_cleanup(oss_objects_param: str = "oss_objects_for_cleanup"):
    """
    OSS文件清理装饰器
    
    Args:
        oss_objects_param: OSS对象列表参数名
    
    Usage:
        @with_oss_cleanup("newly_uploaded_files")
        @db_transaction()
        async def upload_files(files, newly_uploaded_files: List[str], db: Session):
            # 文件上传和数据库操作
            return result
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 提取OSS对象列表
            oss_objects = bound.arguments.get(oss_objects_param, [])
            
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # 出错时清理OSS文件
                if oss_objects:
                    from project import oss_utils
                    import asyncio
                    for obj_name in oss_objects:
                        asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                raise e
        
        return wrapper
    return decorator


def validate_request_data(schema_class):
    """
    请求数据验证装饰器
    
    Args:
        schema_class: Pydantic模式类
    
    Usage:
        @validate_request_data(ProjectCreateSchema)
        async def create_project(project_data_json: str, **kwargs):
            # 在这里，project_data_json会被自动解析和验证
            return result
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            
            # 查找JSON数据参数
            json_param = None
            for param_name, param_value in bound.arguments.items():
                if isinstance(param_value, str) and param_name.endswith('_json'):
                    json_param = param_name
                    break
            
            if json_param:
                try:
                    # 验证和解析JSON数据
                    validated_data = schema_class.model_validate_json(bound.arguments[json_param])
                    # 将验证后的数据替换原始JSON字符串
                    param_name_without_json = json_param.replace('_json', '_data')
                    bound.arguments[param_name_without_json] = validated_data
                    # 移除原始JSON参数
                    del bound.arguments[json_param]
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"数据验证失败: {str(e)}"
                    )
            
            # 使用新的参数调用原函数
            return await func(**bound.arguments)
        
        return wrapper
    return decorator


# ================== 收藏系统装饰器 ==================

def handle_database_errors(operation_name: str):
    """
    统一的数据库错误处理装饰器
    
    Args:
        operation_name: 操作名称，用于错误消息
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # HTTPException 直接重新抛出
                raise
            except Exception as e:
                # 获取数据库会话并回滚
                db = kwargs.get('db')
                if db and isinstance(db, Session):
                    try:
                        db.rollback()
                    except Exception as rollback_error:
                        logger.error(f"数据库回滚失败: {rollback_error}")
                
                logger.error(f"{operation_name}失败: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"{operation_name}失败: {str(e)}"
                )
        return wrapper
    return decorator


def validate_folder_access(func: Callable) -> Callable:
    """
    验证文件夹访问权限的装饰器
    
    要求被装饰的函数必须有 folder_id, current_user_id, db 参数
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        folder_id = kwargs.get('folder_id')
        current_user_id = kwargs.get('current_user_id')
        db = kwargs.get('db')
        
        if not all([folder_id, current_user_id, db]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少必要的参数用于权限验证"
            )
        
        # 使用基础权限验证函数
        from ..core.collections_utils import check_folder_access
        check_folder_access(db, folder_id, current_user_id)
        
        # 获取文件夹对象添加到kwargs中供函数使用
        from project.models import Folder
        folder = db.query(Folder).filter(
            Folder.id == folder_id,
            Folder.owner_id == current_user_id
        ).first()
        kwargs['folder'] = folder
        
        return await func(*args, **kwargs)
    return wrapper


def validate_content_access(func: Callable) -> Callable:
    """
    验证收藏内容访问权限的装饰器
    
    要求被装饰的函数必须有 content_id, current_user_id, db 参数
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        content_id = kwargs.get('content_id')
        current_user_id = kwargs.get('current_user_id')
        db = kwargs.get('db')
        
        if not all([content_id, current_user_id, db]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少必要的参数用于权限验证"
            )
        
        # 使用基础权限验证函数
        from ..core.collections_utils import check_content_access
        check_content_access(db, content_id, current_user_id)
        
        # 获取内容对象添加到kwargs中供函数使用
        from project.models import CollectedContent
        content = db.query(CollectedContent).filter(
            CollectedContent.id == content_id,
            CollectedContent.owner_id == current_user_id
        ).first()
        kwargs['content'] = content
        
        return await func(*args, **kwargs)
    return wrapper


def log_operation(operation_name: str):
    """
    操作日志装饰器
    
    Args:
        operation_name: 操作名称
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            current_user_id = kwargs.get('current_user_id')
            logger.info(f"用户 {current_user_id} 开始执行操作: {operation_name}")
            
            try:
                result = await func(*args, **kwargs)
                logger.info(f"用户 {current_user_id} 成功完成操作: {operation_name}")
                return result
            except Exception as e:
                logger.error(f"用户 {current_user_id} 执行操作失败: {operation_name}, 错误: {str(e)}")
                raise
        return wrapper
    return decorator


# ================== 组合装饰器 ==================

def project_operation(
    required_permissions: List[str],
    commit_transaction: bool = True,
    error_message: str = "无权执行此操作"
):
    """
    项目操作组合装饰器（权限检查 + 事务处理）
    
    Usage:
        @project_operation(["creator", "admin"], commit_transaction=True)
        async def update_project(project_id: int, data, current_user_id: int, db: Session):
            # 项目更新逻辑
            return result
    """
    def decorator(func: Callable) -> Callable:
        # 应用装饰器链
        decorated_func = require_project_permission(
            required_permissions, error_message
        )(func)
        decorated_func = db_transaction(
            commit_on_success=commit_transaction
        )(decorated_func)
        return decorated_func
    
    return decorator


def collections_operation(
    operation_name: str,
    check_folder: bool = False,
    check_content: bool = False,
    commit_transaction: bool = True
):
    """
    收藏系统操作组合装饰器（权限检查 + 错误处理 + 事务处理）
    
    Usage:
        @collections_operation("创建收藏", check_folder=True, commit_transaction=True)
        async def create_collection(folder_id: int, current_user_id: int, db: Session):
            # 收藏创建逻辑
            return result
    """
    def decorator(func: Callable) -> Callable:
        # 应用装饰器链
        decorated_func = handle_database_errors(operation_name)(func)
        
        if check_folder:
            decorated_func = validate_folder_access(decorated_func)
        
        if check_content:
            decorated_func = validate_content_access(decorated_func)
        
        if commit_transaction:
            decorated_func = db_transaction(commit_on_success=True)(decorated_func)
        
        decorated_func = log_operation(operation_name)(decorated_func)
        
        return decorated_func
    
    return decorator


# ================== 论坛系统装饰器 ==================

def rate_limit_check(max_requests: int = 10, window_seconds: int = 60):
    """速率限制装饰器 - 基础实现版本"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 基础实现：记录调用但不限制
            # 生产环境建议使用Redis或内存缓存实现真正的速率限制
            logger.debug(f"API调用: {func.__name__}, 限制: {max_requests}/{window_seconds}s")
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def admin_required_forum(func: Callable) -> Callable:
    """论坛管理员权限检查装饰器 - 基础实现版本"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 基础实现：从kwargs中获取current_user_id进行检查
        # 生产环境建议实现真正的角色权限系统
        current_user_id = kwargs.get('current_user_id')
        if current_user_id:
            logger.debug(f"管理员权限检查: user_id={current_user_id}")
            # 这里可以添加实际的管理员检查逻辑
            # 暂时允许所有用户，实际使用时需要实现权限验证
        return await func(*args, **kwargs)
    return wrapper


def validate_topic_access(func: Callable) -> Callable:
    """话题访问权限验证装饰器"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"话题访问验证失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问此话题"
            )
    return wrapper


def handle_forum_exceptions(operation_name: str):
    """论坛异常处理装饰器"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"{operation_name}失败: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"{operation_name}失败: {str(e)}"
                )
        return wrapper
    return decorator
