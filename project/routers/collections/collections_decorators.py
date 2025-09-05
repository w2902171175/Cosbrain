# project/routers/collections/collections_decorators.py
"""
收藏系统公共装饰器

提供：
- 统一的错误处理装饰器
- 性能监控装饰器
- 权限验证装饰器
"""

import logging
import functools
from typing import Callable, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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
    复用 collections_utils 中的基础权限验证函数
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
        
        # 复用基础权限验证函数，避免重复代码
        from .collections_utils import check_folder_access
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
    复用 collections_utils 中的基础权限验证函数
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
        
        # 复用基础权限验证函数，避免重复代码
        from .collections_utils import check_content_access
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
