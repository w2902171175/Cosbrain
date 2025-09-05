"""
AI异常处理
从路由层移动过来的企业级AI异常处理，提供统一的错误处理、日志记录和恢复机制
"""

import traceback
import time
import uuid
from typing import Dict, Any, Optional, Type
from datetime import datetime
from enum import Enum

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError

# 企业级日志
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    logger = get_ai_logger("ai_exceptions")
except ImportError:
    import logging
    logger = logging.getLogger("ai_exceptions")


class ErrorCode(Enum):
    """错误代码枚举"""
    
    # 通用错误 (1000-1999)
    UNKNOWN_ERROR = 1000
    INTERNAL_SERVER_ERROR = 1001
    SERVICE_UNAVAILABLE = 1002
    TIMEOUT_ERROR = 1003
    CONFIGURATION_ERROR = 1004
    
    # 请求错误 (2000-2999)  
    INVALID_REQUEST = 2000
    MISSING_PARAMETER = 2001
    INVALID_PARAMETER = 2002
    REQUEST_TOO_LARGE = 2003
    UNSUPPORTED_FORMAT = 2004
    MALFORMED_REQUEST = 2005
    
    # 认证/授权错误 (3000-3999)
    AUTHENTICATION_FAILED = 3000
    AUTHORIZATION_FAILED = 3001
    INVALID_API_KEY = 3002
    EXPIRED_TOKEN = 3003
    INSUFFICIENT_PERMISSIONS = 3004
    
    # 速率限制错误 (4000-4999)
    RATE_LIMIT_EXCEEDED = 4000
    QUOTA_EXCEEDED = 4001
    CONCURRENT_LIMIT_EXCEEDED = 4002
    
    # AI提供者错误 (5000-5999)
    PROVIDER_UNAVAILABLE = 5000
    PROVIDER_ERROR = 5001
    MODEL_NOT_FOUND = 5002
    INSUFFICIENT_QUOTA = 5003
    PROVIDER_TIMEOUT = 5004
    CONTEXT_LENGTH_EXCEEDED = 5005
    
    # 文件处理错误 (6000-6999)
    FILE_TOO_LARGE = 6000
    UNSUPPORTED_FILE_TYPE = 6001
    FILE_PROCESSING_FAILED = 6002
    FILE_CORRUPTION = 6003
    FILE_NOT_FOUND = 6004
    
    # 数据库错误 (7000-7999)
    DATABASE_ERROR = 7000
    CONNECTION_ERROR = 7001
    QUERY_TIMEOUT = 7002
    CONSTRAINT_VIOLATION = 7003
    
    # 缓存错误 (8000-8999)
    CACHE_ERROR = 8000
    CACHE_MISS = 8001
    CACHE_CORRUPTION = 8002


class AIRouterException(Exception):
    """AI路由基础异常类"""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        user_message: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause
        self.user_message = user_message or self._get_user_friendly_message()
        self.error_id = str(uuid.uuid4())
        self.timestamp = datetime.utcnow()
    
    def _get_user_friendly_message(self) -> str:
        """获取用户友好的错误消息"""
        error_messages = {
            ErrorCode.UNKNOWN_ERROR: "发生了未知错误，请稍后重试",
            ErrorCode.INTERNAL_SERVER_ERROR: "服务器内部错误，请稍后重试",
            ErrorCode.SERVICE_UNAVAILABLE: "服务暂时不可用，请稍后重试",
            ErrorCode.TIMEOUT_ERROR: "请求超时，请稍后重试",
            ErrorCode.CONFIGURATION_ERROR: "服务配置错误，请联系管理员",
            
            ErrorCode.INVALID_REQUEST: "请求格式不正确",
            ErrorCode.MISSING_PARAMETER: "缺少必要参数",
            ErrorCode.INVALID_PARAMETER: "参数值不正确",
            ErrorCode.REQUEST_TOO_LARGE: "请求内容过大",
            ErrorCode.UNSUPPORTED_FORMAT: "不支持的格式",
            ErrorCode.MALFORMED_REQUEST: "请求格式错误",
            
            ErrorCode.AUTHENTICATION_FAILED: "身份验证失败",
            ErrorCode.AUTHORIZATION_FAILED: "没有访问权限",
            ErrorCode.INVALID_API_KEY: "API密钥无效",
            ErrorCode.EXPIRED_TOKEN: "访问令牌已过期",
            ErrorCode.INSUFFICIENT_PERMISSIONS: "权限不足",
            
            ErrorCode.RATE_LIMIT_EXCEEDED: "请求过于频繁，请稍后重试",
            ErrorCode.QUOTA_EXCEEDED: "已超出使用配额",
            ErrorCode.CONCURRENT_LIMIT_EXCEEDED: "并发请求数超限",
            
            ErrorCode.PROVIDER_UNAVAILABLE: "AI服务暂时不可用",
            ErrorCode.PROVIDER_ERROR: "AI服务发生错误",
            ErrorCode.MODEL_NOT_FOUND: "指定的模型不存在",
            ErrorCode.INSUFFICIENT_QUOTA: "AI服务配额不足",
            ErrorCode.PROVIDER_TIMEOUT: "AI服务响应超时",
            ErrorCode.CONTEXT_LENGTH_EXCEEDED: "输入内容过长",
            
            ErrorCode.FILE_TOO_LARGE: "文件过大",
            ErrorCode.UNSUPPORTED_FILE_TYPE: "不支持的文件类型",
            ErrorCode.FILE_PROCESSING_FAILED: "文件处理失败",
            ErrorCode.FILE_CORRUPTION: "文件已损坏",
            ErrorCode.FILE_NOT_FOUND: "文件不存在",
            
            ErrorCode.DATABASE_ERROR: "数据库操作失败",
            ErrorCode.CONNECTION_ERROR: "数据库连接失败",
            ErrorCode.QUERY_TIMEOUT: "数据库查询超时",
            ErrorCode.CONSTRAINT_VIOLATION: "数据约束冲突",
            
            ErrorCode.CACHE_ERROR: "缓存操作失败",
            ErrorCode.CACHE_MISS: "缓存未命中",
            ErrorCode.CACHE_CORRUPTION: "缓存数据损坏"
        }
        
        return error_messages.get(self.error_code, "发生了未知错误")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_id": self.error_id,
            "error_code": self.error_code.value,
            "error_name": self.error_code.name,
            "message": self.message,
            "user_message": self.user_message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "cause": str(self.cause) if self.cause else None
        }


class ProviderException(AIRouterException):
    """AI提供者异常"""
    
    def __init__(self, provider_name: str, message: str, cause: Exception = None):
        super().__init__(
            message=f"Provider {provider_name}: {message}",
            error_code=ErrorCode.PROVIDER_ERROR,
            details={"provider": provider_name},
            cause=cause
        )


class RateLimitException(AIRouterException):
    """速率限制异常"""
    
    def __init__(self, limit: int, window: int, current_count: int):
        super().__init__(
            message=f"Rate limit exceeded: {current_count}/{limit} requests in {window}s",
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            details={
                "limit": limit,
                "window_seconds": window,
                "current_count": current_count
            }
        )


class FileProcessingException(AIRouterException):
    """文件处理异常"""
    
    def __init__(self, filename: str, message: str, error_code: ErrorCode = ErrorCode.FILE_PROCESSING_FAILED):
        super().__init__(
            message=f"File processing error for {filename}: {message}",
            error_code=error_code,
            details={"filename": filename}
        )


class ValidationException(AIRouterException):
    """验证异常"""
    
    def __init__(self, field: str, value: Any, reason: str):
        super().__init__(
            message=f"Validation failed for field '{field}': {reason}",
            error_code=ErrorCode.INVALID_PARAMETER,
            details={
                "field": field,
                "value": str(value),
                "reason": reason
            }
        )


class ExceptionHandler:
    """统一异常处理器"""
    
    def __init__(self):
        self.error_stats = {}
        self.recovery_strategies = {}
        self._register_recovery_strategies()
    
    def _register_recovery_strategies(self):
        """注册恢复策略"""
        self.recovery_strategies = {
            ErrorCode.PROVIDER_TIMEOUT: self._retry_with_backoff,
            ErrorCode.PROVIDER_UNAVAILABLE: self._switch_provider,
            ErrorCode.DATABASE_ERROR: self._retry_database_operation,
            ErrorCode.CACHE_ERROR: self._bypass_cache,
            ErrorCode.RATE_LIMIT_EXCEEDED: self._queue_request
        }
    
    async def handle_exception(
        self,
        request: Request,
        exc: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """处理异常并返回适当的响应"""
        
        # 生成错误ID用于追踪
        error_id = str(uuid.uuid4())
        
        # 记录请求上下文
        request_context = {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "error_id": error_id
        }
        
        if context:
            request_context.update(context)
        
        # 处理不同类型的异常
        if isinstance(exc, AIRouterException):
            ai_exception = exc
        elif isinstance(exc, HTTPException):
            ai_exception = self._convert_http_exception(exc)
        elif isinstance(exc, ValidationError):
            ai_exception = self._convert_validation_error(exc)
        elif isinstance(exc, SQLAlchemyError):
            ai_exception = self._convert_database_error(exc)
        elif isinstance(exc, TimeoutError):
            ai_exception = AIRouterException(
                message="Operation timeout",
                error_code=ErrorCode.TIMEOUT_ERROR,
                cause=exc
            )
        else:
            ai_exception = AIRouterException(
                message="Unexpected error occurred",
                error_code=ErrorCode.UNKNOWN_ERROR,
                cause=exc
            )
        
        # 设置错误ID
        ai_exception.error_id = error_id
        
        # 记录异常
        await self._log_exception(ai_exception, request_context)
        
        # 更新错误统计
        self._update_error_stats(ai_exception.error_code)
        
        # 尝试恢复
        recovery_result = await self._attempt_recovery(ai_exception, request_context)
        if recovery_result:
            return recovery_result
        
        # 确定HTTP状态码
        http_status = self._get_http_status(ai_exception.error_code)
        
        # 构建响应
        response_data = {
            "success": False,
            "error": ai_exception.to_dict(),
            "request_id": error_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return JSONResponse(
            status_code=http_status,
            content=response_data
        )
    
    def _convert_http_exception(self, exc: HTTPException) -> AIRouterException:
        """转换HTTPException"""
        error_code_map = {
            400: ErrorCode.INVALID_REQUEST,
            401: ErrorCode.AUTHENTICATION_FAILED,
            403: ErrorCode.AUTHORIZATION_FAILED,
            404: ErrorCode.FILE_NOT_FOUND,
            413: ErrorCode.REQUEST_TOO_LARGE,
            422: ErrorCode.INVALID_PARAMETER,
            429: ErrorCode.RATE_LIMIT_EXCEEDED,
            500: ErrorCode.INTERNAL_SERVER_ERROR,
            502: ErrorCode.PROVIDER_UNAVAILABLE,
            503: ErrorCode.SERVICE_UNAVAILABLE,
            504: ErrorCode.TIMEOUT_ERROR
        }
        
        error_code = error_code_map.get(exc.status_code, ErrorCode.UNKNOWN_ERROR)
        
        return AIRouterException(
            message=exc.detail,
            error_code=error_code,
            cause=exc
        )
    
    def _convert_validation_error(self, exc: ValidationError) -> AIRouterException:
        """转换Pydantic验证错误"""
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            errors.append(f"{field}: {error['msg']}")
        
        return AIRouterException(
            message="Validation failed: " + "; ".join(errors),
            error_code=ErrorCode.INVALID_PARAMETER,
            details={"validation_errors": exc.errors()},
            cause=exc
        )
    
    def _convert_database_error(self, exc: SQLAlchemyError) -> AIRouterException:
        """转换数据库错误"""
        return AIRouterException(
            message=f"Database operation failed: {str(exc)}",
            error_code=ErrorCode.DATABASE_ERROR,
            cause=exc
        )
    
    async def _log_exception(self, exc: AIRouterException, context: Dict[str, Any]):
        """记录异常"""
        log_data = {
            "error_id": exc.error_id,
            "error_code": exc.error_code.name,
            "message": exc.message,
            "user_message": exc.user_message,
            "details": exc.details,
            "context": context,
            "stack_trace": traceback.format_exc() if exc.cause else None
        }
        
        if exc.error_code.value >= 5000:  # 严重错误
            logger.error(f"AI Router Exception: {exc.message}", extra=log_data)
        elif exc.error_code.value >= 4000:  # 客户端错误
            logger.warning(f"AI Router Warning: {exc.message}", extra=log_data)
        else:
            logger.info(f"AI Router Info: {exc.message}", extra=log_data)
    
    def _update_error_stats(self, error_code: ErrorCode):
        """更新错误统计"""
        code_name = error_code.name
        if code_name not in self.error_stats:
            self.error_stats[code_name] = {
                "count": 0,
                "first_seen": datetime.utcnow(),
                "last_seen": None
            }
        
        self.error_stats[code_name]["count"] += 1
        self.error_stats[code_name]["last_seen"] = datetime.utcnow()
    
    async def _attempt_recovery(
        self, 
        exc: AIRouterException, 
        context: Dict[str, Any]
    ) -> Optional[JSONResponse]:
        """尝试错误恢复"""
        recovery_func = self.recovery_strategies.get(exc.error_code)
        if recovery_func:
            try:
                return await recovery_func(exc, context)
            except Exception as recovery_error:
                logger.error(f"Recovery failed for {exc.error_code.name}: {recovery_error}")
        
        return None
    
    async def _retry_with_backoff(self, exc: AIRouterException, context: Dict[str, Any]) -> Optional[JSONResponse]:
        """重试策略"""
        # 实现退避重试逻辑
        return None
    
    async def _switch_provider(self, exc: AIRouterException, context: Dict[str, Any]) -> Optional[JSONResponse]:
        """切换提供者策略"""
        # 实现提供者切换逻辑
        return None
    
    async def _retry_database_operation(self, exc: AIRouterException, context: Dict[str, Any]) -> Optional[JSONResponse]:
        """数据库重试策略"""
        # 实现数据库重试逻辑
        return None
    
    async def _bypass_cache(self, exc: AIRouterException, context: Dict[str, Any]) -> Optional[JSONResponse]:
        """绕过缓存策略"""
        # 实现缓存绕过逻辑
        return None
    
    async def _queue_request(self, exc: AIRouterException, context: Dict[str, Any]) -> Optional[JSONResponse]:
        """请求排队策略"""
        # 实现请求排队逻辑
        return None
    
    def _get_http_status(self, error_code: ErrorCode) -> int:
        """获取HTTP状态码"""
        status_map = {
            # 1000-1999: 服务器错误
            ErrorCode.UNKNOWN_ERROR: 500,
            ErrorCode.INTERNAL_SERVER_ERROR: 500,
            ErrorCode.SERVICE_UNAVAILABLE: 503,
            ErrorCode.TIMEOUT_ERROR: 504,
            ErrorCode.CONFIGURATION_ERROR: 500,
            
            # 2000-2999: 客户端错误
            ErrorCode.INVALID_REQUEST: 400,
            ErrorCode.MISSING_PARAMETER: 400,
            ErrorCode.INVALID_PARAMETER: 422,
            ErrorCode.REQUEST_TOO_LARGE: 413,
            ErrorCode.UNSUPPORTED_FORMAT: 415,
            ErrorCode.MALFORMED_REQUEST: 400,
            
            # 3000-3999: 认证/授权错误
            ErrorCode.AUTHENTICATION_FAILED: 401,
            ErrorCode.AUTHORIZATION_FAILED: 403,
            ErrorCode.INVALID_API_KEY: 401,
            ErrorCode.EXPIRED_TOKEN: 401,
            ErrorCode.INSUFFICIENT_PERMISSIONS: 403,
            
            # 4000-4999: 速率限制错误
            ErrorCode.RATE_LIMIT_EXCEEDED: 429,
            ErrorCode.QUOTA_EXCEEDED: 429,
            ErrorCode.CONCURRENT_LIMIT_EXCEEDED: 429,
            
            # 5000-5999: AI提供者错误
            ErrorCode.PROVIDER_UNAVAILABLE: 502,
            ErrorCode.PROVIDER_ERROR: 502,
            ErrorCode.MODEL_NOT_FOUND: 404,
            ErrorCode.INSUFFICIENT_QUOTA: 402,
            ErrorCode.PROVIDER_TIMEOUT: 504,
            ErrorCode.CONTEXT_LENGTH_EXCEEDED: 413,
            
            # 6000-6999: 文件处理错误
            ErrorCode.FILE_TOO_LARGE: 413,
            ErrorCode.UNSUPPORTED_FILE_TYPE: 415,
            ErrorCode.FILE_PROCESSING_FAILED: 422,
            ErrorCode.FILE_CORRUPTION: 422,
            ErrorCode.FILE_NOT_FOUND: 404,
            
            # 7000-7999: 数据库错误
            ErrorCode.DATABASE_ERROR: 500,
            ErrorCode.CONNECTION_ERROR: 500,
            ErrorCode.QUERY_TIMEOUT: 504,
            ErrorCode.CONSTRAINT_VIOLATION: 409,
            
            # 8000-8999: 缓存错误
            ErrorCode.CACHE_ERROR: 500,
            ErrorCode.CACHE_MISS: 404,
            ErrorCode.CACHE_CORRUPTION: 500
        }
        
        return status_map.get(error_code, 500)
    
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计"""
        return {
            "total_errors": sum(stat["count"] for stat in self.error_stats.values()),
            "error_types": len(self.error_stats),
            "by_type": self.error_stats,
            "generated_at": datetime.utcnow().isoformat()
        }


# === 全局异常处理器实例 ===
exception_handler = ExceptionHandler()


# === 便捷函数 ===

def raise_ai_exception(
    message: str,
    error_code: ErrorCode,
    details: Optional[Dict[str, Any]] = None,
    cause: Optional[Exception] = None
):
    """抛出AI路由异常"""
    raise AIRouterException(
        message=message,
        error_code=error_code,
        details=details,
        cause=cause
    )


def raise_provider_exception(provider_name: str, message: str, cause: Exception = None):
    """抛出提供者异常"""
    raise ProviderException(provider_name, message, cause)


def raise_rate_limit_exception(limit: int, window: int, current_count: int):
    """抛出速率限制异常"""
    raise RateLimitException(limit, window, current_count)


def raise_file_exception(filename: str, message: str, error_code: ErrorCode = ErrorCode.FILE_PROCESSING_FAILED):
    """抛出文件处理异常"""
    raise FileProcessingException(filename, message, error_code)


def raise_validation_exception(field: str, value: Any, reason: str):
    """抛出验证异常"""
    raise ValidationException(field, value, reason)
