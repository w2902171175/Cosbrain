# project/utils/core/error_handler.py
"""统一错误处理模块"""

import functools
import uuid
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from pydantic import ValidationError

from .common_utils import debug_operation


class ErrorCategory(Enum):
    DATABASE = "database"
    PERMISSION = "permission"
    VALIDATION = "validation"
    BUSINESS = "business"
    EXTERNAL = "external"
    SYSTEM = "system"


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectError(Exception):
    """统一异常基类"""
    
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.SYSTEM,
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM, details: Dict[str, Any] = None,
                 user_message: str = None, operation: str = None, cause: Exception = None):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.user_message = user_message or message
        self.operation = operation
        self.cause = cause
        self.timestamp = datetime.utcnow()
        self.error_id = f"{category.value}-{uuid.uuid4().hex[:8]}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_id": self.error_id,
            "message": self.message,
            "user_message": self.user_message,
            "category": self.category.value,
            "severity": self.severity.value,
            "operation": self.operation,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


# 具体错误类型
class DatabaseError(ProjectError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.DATABASE, **kwargs)


class PermissionError(ProjectError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.PERMISSION, **kwargs)


class ValidationError(ProjectError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.VALIDATION, **kwargs)


class BusinessLogicError(ProjectError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.BUSINESS, **kwargs)


class ExternalServiceError(ProjectError):
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.EXTERNAL, **kwargs)


class ErrorHandler:
    """统一错误处理器"""
    
    def __init__(self):
        self.error_stats = {}
    
    async def handle_error(self, error: Exception, operation: str = "操作",
                          context: Dict[str, Any] = None, db: Session = None) -> ProjectError:
        context = context or {}
        
        project_error = self._convert_to_project_error(error, operation)
        
        if not project_error.operation:
            project_error.operation = operation
        
        self._rollback_if_needed(db, project_error)
        self._update_stats(project_error)
        self._log_error(project_error)
        
        return project_error
    
    def _convert_to_project_error(self, error: Exception, operation: str) -> ProjectError:
        if isinstance(error, ProjectError):
            return error
        if isinstance(error, HTTPException):
            return self._from_http_exception(error, operation)
        if isinstance(error, (IntegrityError, SQLAlchemyError)):
            return DatabaseError(f"数据库操作失败: {str(error)}", operation=operation, cause=error)
        if isinstance(error, ValidationError):
            return ValidationError(f"数据验证失败: {str(error)}", operation=operation, cause=error)
        
        return ProjectError(f"未知错误: {str(error)}", category=ErrorCategory.SYSTEM,
                          severity=ErrorSeverity.HIGH, operation=operation, cause=error)
    
    def _from_http_exception(self, error: HTTPException, operation: str) -> ProjectError:
        category_map = {400: ErrorCategory.VALIDATION, 401: ErrorCategory.PERMISSION,
                       403: ErrorCategory.PERMISSION, 404: ErrorCategory.BUSINESS,
                       409: ErrorCategory.BUSINESS, 422: ErrorCategory.VALIDATION,
                       500: ErrorCategory.SYSTEM}
        
        severity_map = {400: ErrorSeverity.LOW, 401: ErrorSeverity.MEDIUM,
                       403: ErrorSeverity.MEDIUM, 404: ErrorSeverity.LOW,
                       409: ErrorSeverity.MEDIUM, 422: ErrorSeverity.LOW,
                       500: ErrorSeverity.HIGH}
        
        category = category_map.get(error.status_code, ErrorCategory.SYSTEM)
        severity = severity_map.get(error.status_code, ErrorSeverity.MEDIUM)
        
        return ProjectError(error.detail, category=category, severity=severity,
                          operation=operation, cause=error)
    
    def _rollback_if_needed(self, db: Session, error: ProjectError):
        if db and error.category in [ErrorCategory.DATABASE, ErrorCategory.SYSTEM]:
            try:
                db.rollback()
            except Exception:
                pass
    
    def _update_stats(self, error: ProjectError):
        key = f"{error.category.value}_{error.severity.value}"
        if key not in self.error_stats:
            self.error_stats[key] = {"count": 0, "first_seen": error.timestamp, "last_seen": error.timestamp}
        else:
            self.error_stats[key]["count"] += 1
            self.error_stats[key]["last_seen"] = error.timestamp
    
    def _log_error(self, error: ProjectError):
        debug_operation(f"{error.severity.value}级错误", **error.to_dict())
    
    def to_http_exception(self, error: ProjectError) -> HTTPException:
        status_map = {
            ErrorCategory.VALIDATION: status.HTTP_400_BAD_REQUEST,
            ErrorCategory.PERMISSION: status.HTTP_403_FORBIDDEN,
            ErrorCategory.BUSINESS: status.HTTP_409_CONFLICT,
            ErrorCategory.DATABASE: status.HTTP_500_INTERNAL_SERVER_ERROR,
            ErrorCategory.EXTERNAL: status.HTTP_502_BAD_GATEWAY,
            ErrorCategory.SYSTEM: status.HTTP_500_INTERNAL_SERVER_ERROR
        }
        
        return HTTPException(
            status_code=status_map.get(error.category, status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=error.user_message,
            headers={"X-Error-ID": error.error_id}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_errors": sum(stat["count"] for stat in self.error_stats.values()),
            "by_category": self.error_stats,
            "generated_at": datetime.utcnow().isoformat()
        }


# 全局实例
error_handler = ErrorHandler()


def handle_errors(operation: str, category: ErrorCategory = None, rollback_db: bool = True):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            db = kwargs.get('db') if rollback_db else None
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                project_error = await error_handler.handle_error(e, operation, db=db)
                raise error_handler.to_http_exception(project_error)
        return wrapper
    return decorator


def safe_operation(operation: str):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                debug_operation(f"{operation}失败", error=str(e))
                raise HTTPException(status_code=500, detail=f"{operation}失败")
        return wrapper
    return decorator


# 便捷错误函数
def not_found(resource: str, resource_id: Any = None):
    message = f"{resource}未找到"
    if resource_id:
        message += f" (ID: {resource_id})"
    raise BusinessLogicError(message, severity=ErrorSeverity.LOW)


def permission_denied(operation: str, resource: str = "资源"):
    message = f"无权{operation}{resource}"
    raise PermissionError(message, severity=ErrorSeverity.MEDIUM)


def validation_failed(field: str, message: str):
    raise ValidationError(f"{field}: {message}", severity=ErrorSeverity.LOW,
                         details={"field": field, "message": message})


def business_error(message: str, user_message: str = None):
    raise BusinessLogicError(message, user_message=user_message or message,
                           severity=ErrorSeverity.MEDIUM)


# 向后兼容的别名
raise_not_found = not_found
raise_permission_denied = permission_denied
raise_validation_error = validation_failed
raise_business_error = business_error
