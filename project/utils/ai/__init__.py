"""
AI工具模块
包含AI相关的工具函数和异常处理
"""

from .ai_utils import (
    clean_optional_json_string_input,
    process_ai_temp_file_in_background,
    format_response_time,
    validate_file_type,
    sanitize_filename,
    get_file_size_mb
)

from .ai_exceptions import (
    ErrorCode,
    AIRouterException,
    ProviderException,
    RateLimitException,
    FileProcessingException,
    ValidationException,
    ExceptionHandler,
    exception_handler,
    raise_ai_exception,
    raise_provider_exception,
    raise_rate_limit_exception,
    raise_file_exception,
    raise_validation_exception
)

__all__ = [
    # 工具函数
    "clean_optional_json_string_input",
    "process_ai_temp_file_in_background", 
    "format_response_time",
    "validate_file_type",
    "sanitize_filename",
    "get_file_size_mb",
    
    # 异常处理
    "ErrorCode",
    "AIRouterException",
    "ProviderException",
    "RateLimitException",
    "FileProcessingException",
    "ValidationException",
    "ExceptionHandler",
    "exception_handler",
    "raise_ai_exception",
    "raise_provider_exception",
    "raise_rate_limit_exception",
    "raise_file_exception",
    "raise_validation_exception"
]
