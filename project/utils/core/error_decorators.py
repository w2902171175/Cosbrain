# project/utils/error_decorators.py
"""
统一的错误处理装饰器和数据库事务管理
"""
from functools import wraps
from contextlib import contextmanager
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import logging

# 配置日志
logger = logging.getLogger(__name__)

def handle_database_errors(operation_name: str):
    """统一的数据库错误处理装饰器"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except IntegrityError as e:
                db = kwargs.get('db')
                if db:
                    db.rollback()
                logger.error(f"{operation_name}完整性错误: {e}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, 
                    detail=f"{operation_name}失败，可能存在数据冲突"
                )
            except HTTPException:
                raise
            except Exception as e:
                db = kwargs.get('db')
                if db:
                    db.rollback()
                logger.error(f"{operation_name}失败: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                    detail=f"{operation_name}失败"
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except IntegrityError as e:
                db = kwargs.get('db')
                if db:
                    db.rollback()
                logger.error(f"{operation_name}完整性错误: {e}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, 
                    detail=f"{operation_name}失败，可能存在数据冲突"
                )
            except HTTPException:
                raise
            except Exception as e:
                db = kwargs.get('db')
                if db:
                    db.rollback()
                logger.error(f"{operation_name}失败: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                    detail=f"{operation_name}失败"
                )
        
        # 检查函数是否是异步的
        if hasattr(func, '__code__') and func.__code__.co_flags & 0x80:
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

@contextmanager
def database_transaction(db: Session):
    """数据库事务上下文管理器"""
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise

def safe_db_operation(db: Session, operation_func, *args, **kwargs):
    """安全的数据库操作封装"""
    try:
        result = operation_func(*args, **kwargs)
        db.add(result) if hasattr(result, '__table__') else None
        db.commit()
        if hasattr(result, '__table__'):
            db.refresh(result)
        return result
    except Exception:
        db.rollback()
        raise
