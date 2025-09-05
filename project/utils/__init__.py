# project/utils/__init__.py
"""
工具包：包含项目中使用的各种工具函数和装饰器
重构后按功能模块组织，提供更清晰的结构和更好的可维护性
"""

# 核心功能模块
from .core import (
    # 核心工具函数
    _get_text_part,
    _award_points,
    _check_and_award_achievements,
    validate_ownership,
    check_admin_permission, 
    check_resource_permission,
    check_project_permission,
    validate_file_type,
    check_unique_field,
    paginate_query,
    generate_embedding_safe,
    update_embedding_safe,
    populate_user_name,
    populate_like_status,
    get_user_by_id_or_404,
    get_resource_or_404,
    get_user_resource_or_404,
    commit_or_rollback,
    create_and_add_resource,
    get_resources_with_details,
    get_projects_with_details,
    get_courses_with_details,
    get_forum_topics_with_details,
    process_skills_field,
    build_user_combined_text,
    update_fields_from_dict,
    debug_log,
    debug_operation,
    
    # 通用操作
    QueryBuilder,
    DbOps,
    Validator,
    UserOps,
    ProjectOps,
    build_query,
    get_or_404,
    required,
    fill_user_names,
    create_query_builder,
    validate_required,
    DatabaseOperations,
    ValidationUtils,
    UserOperations,
    ProjectOperations,
    
    # 装饰器
    require_project_permission,
    require_admin,
    db_transaction,
    with_oss_cleanup,
    validate_request_data,
    project_operation,
    
    # 错误处理
    error_handler,
    handle_errors,
    safe_operation,
    ProjectError,
    DatabaseError,
    PermissionError,
    ValidationError,
    BusinessLogicError,
    ExternalServiceError,
    not_found,
    permission_denied,
    validation_failed,
    business_error,
    raise_not_found,
    raise_permission_denied,
    raise_validation_error,
    raise_business_error
)

# 依赖注入模块（认证相关）
from .auth import (
    # 数据库
    get_db,
    
    # 密码处理
    verify_password,
    get_password_hash,
    pwd_context,
    
    # JWT 认证
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    oauth2_scheme,
    bearer_scheme,
    
    # 用户认证
    get_current_user_id,
    get_current_user,
    get_current_user_id_optional,
    is_admin_user,
    require_admin_user,
    
    # 分页
    get_pagination_params,
    
    # 资源依赖
    get_resource_dependency,
    get_user_resource_dependency,
    require_resource_owner,
    require_resource_owner_or_admin,
)

# 数据库相关模块  
# from .database import *

# 安全相关模块
# from .security import (
#     EnhancedFileSecurityValidator,
#     validate_file_security,
#     EnhancedInputSecurityValidator,
#     validate_forum_input,
#     require_room_access,
# )

# 文件处理模块
from .uploads import (
    ChunkedUploadManager,
    DirectUploadManager, 
    ImageOptimizer,
    upload_single_file,
)

# 缓存和异步处理模块
# from .async_cache import (
#     ChatRoomCache,
#     TaskManager,
#     TaskStatus,
#     TaskPriority,
#     Task,
#     AsyncTaskExecutor,
# )

# 性能优化模块
# from .optimization import (
#     OptimizedRouter,
#     RouterOptimizer,
#     ProductionConfig,
#     PerformanceMonitor,
#     BaseRouter,
#     RouterConfig,
# )

# 暂时启用优化模块以支持 cache_manager
from .optimization import cache_manager

# 日志处理模块
# from .logging import (
#     StartupFormatter,
#     StartupLogger,
#     setup_startup_logging,
#     log_errors,
#     track_performance,
#     log_function_calls,
# )

__all__ = [
    # 核心工具函数
    "_get_text_part",
    "_award_points",
    "_check_and_award_achievements",
    "validate_ownership",
    "check_admin_permission", 
    "check_resource_permission",
    "check_project_permission",
    "validate_file_type",
    "check_unique_field",
    "paginate_query",
    "generate_embedding_safe",
    "update_embedding_safe",
    "populate_user_name",
    "populate_like_status",
    "get_user_by_id_or_404",
    "get_resource_or_404",
    "get_user_resource_or_404",
    "commit_or_rollback",
    "create_and_add_resource",
    "get_resources_with_details",
    "get_projects_with_details",
    "get_courses_with_details", 
    "get_forum_topics_with_details",
    "process_skills_field",
    "build_user_combined_text",
    "update_fields_from_dict",
    "debug_log",
    "debug_operation",
    
    # 通用操作
    "QueryBuilder",
    "DbOps",
    "Validator",
    "UserOps", 
    "ProjectOps",
    "build_query",
    "get_or_404",
    "required",
    "fill_user_names",
    "create_query_builder",
    "validate_required",
    "DatabaseOperations",
    "ValidationUtils",
    "UserOperations", 
    "ProjectOperations",
    
    # 装饰器
    "require_project_permission",
    "require_admin",
    "db_transaction",
    "with_oss_cleanup",
    "validate_request_data",
    "project_operation",
    
    # 错误处理
    "error_handler",
    "handle_errors",
    "safe_operation",
    "ProjectError",
    "DatabaseError",
    "PermissionError", 
    "ValidationError",
    "BusinessLogicError",
    "ExternalServiceError",
    "not_found",
    "permission_denied",
    "validation_failed",
    "business_error",
    "raise_not_found",
    "raise_permission_denied", 
    "raise_validation_error",
    "raise_business_error",
    
    # 依赖注入
    # 数据库
    "get_db",
    
    # 密码处理
    "verify_password",
    "get_password_hash",
    "pwd_context",
    
    # JWT 认证
    "create_access_token",
    "SECRET_KEY",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "oauth2_scheme",
    "bearer_scheme",
    
    # 用户认证
    "get_current_user_id",
    "get_current_user",
    "get_current_user_id_optional",
    "is_admin_user",
    "require_admin_user",
    
    # 分页
    "get_pagination_params",
    
    # 资源依赖
    "get_resource_dependency",
    "get_user_resource_dependency",
    "require_resource_owner",
    "require_resource_owner_or_admin",
    
    # 缓存管理
    "cache_manager",
    
    # 安全相关
    # "EnhancedFileSecurityValidator",
    # "validate_file_security",
    # "EnhancedInputSecurityValidator",
    # "validate_forum_input",
    # "require_room_access",
    
    # 文件处理
    "ChunkedUploadManager",
    "DirectUploadManager", 
    "ImageOptimizer",
    "upload_single_file",
    
    # 缓存和异步
    # "ChatRoomCache",
    # "TaskManager",
    # "TaskStatus",
    # "TaskPriority",
    # "Task",
    # "AsyncTaskExecutor",
    
    # 性能优化
    # "OptimizedRouter",
    # "RouterOptimizer",
    # "ProductionConfig",
    # "PerformanceMonitor",
    # "BaseRouter",
    # "RouterConfig",
    
    # 日志处理
    # "StartupFormatter",
    # "StartupLogger",
    # "setup_startup_logging",
    # "log_errors",
    # "track_performance",
    # "log_function_calls",
]
