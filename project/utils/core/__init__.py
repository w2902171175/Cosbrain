# project/utils/core/__init__.py
"""
核心工具模块
包含项目的核心功能、通用操作、装饰器和错误处理
"""

from .common_utils import (
    # 私有工具函数（内部使用）
    _get_text_part,
    _award_points,
    _check_and_award_achievements,
    
    # 验证和权限相关
    validate_ownership,
    check_admin_permission, 
    check_resource_permission,
    check_project_permission,
    validate_file_type,
    check_unique_field,
    
    # 分页相关
    paginate_query,
    
    # 向量嵌入相关
    generate_embedding_safe,
    update_embedding_safe,
    
    # 数据填充相关
    populate_user_name,
    populate_like_status,
    
    # 用户和资源获取
    get_user_by_id_or_404,
    get_resource_or_404,
    get_user_resource_or_404,
    
    # 数据库操作相关
    commit_or_rollback,
    create_and_add_resource,
    
    # 资源详情获取
    get_resources_with_details,
    get_projects_with_details,
    get_courses_with_details,
    get_forum_topics_with_details,
    
    # 用户相关工具
    process_skills_field,
    build_user_combined_text,
    update_fields_from_dict,
    
    # 调试相关
    debug_log,
    debug_operation,
)

from .operations import (
    QueryBuilder,
    DbOps,
    Validator,
    UserOps,
    ProjectOps,
    build_query,
    get_or_404,
    required,
    fill_user_names,
    # 向后兼容
    create_query_builder,
    validate_required,
    DatabaseOperations,
    ValidationUtils,
    UserOperations,
    ProjectOperations
)

from .decorators import (
    require_project_permission,
    require_admin,
    db_transaction,
    with_oss_cleanup,
    validate_request_data,
    project_operation,
)

from .error_handler import (
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
    # 向后兼容
    raise_not_found,
    raise_permission_denied,
    raise_validation_error,
    raise_business_error
)

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
]
