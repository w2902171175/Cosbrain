# project/utils/dependencies/__init__.py
"""
依赖注入工具模块
包含 FastAPI 依赖注入相关的函数和配置，按功能分组
"""

# 数据库相关
from .database import get_db

# 密码相关
from .password import (
    verify_password,
    get_password_hash,
    pwd_context,
)

# JWT 认证相关
from .jwt_auth import (
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    oauth2_scheme,
    bearer_scheme,
)

# 用户认证相关
from .user_auth import (
    get_current_user_id,
    get_current_user,
    get_current_user_id_optional,
    is_admin_user,
    require_admin_user,
)

# 认证工具函数
from .auth_utils import (
    generate_unique_username,
    check_field_uniqueness,
    build_combined_text,
    normalize_skills_data,
    find_user_by_credential,
    prepare_user_data_for_registration,
    validate_registration_data,
    validate_update_data,
)

# 分页相关
from .pagination import get_pagination_params

# 资源相关
from .resources import (
    get_resource_dependency,
    get_user_resource_dependency,
    require_resource_owner,
    require_resource_owner_or_admin,
)

__all__ = [
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
    
    # 认证工具函数
    "generate_unique_username",
    "check_field_uniqueness", 
    "build_combined_text",
    "normalize_skills_data",
    "find_user_by_credential",
    "prepare_user_data_for_registration",
    "validate_registration_data",
    "validate_update_data",
    
    # 分页
    "get_pagination_params",
    
    # 资源依赖
    "get_resource_dependency",
    "get_user_resource_dependency",
    "require_resource_owner",
    "require_resource_owner_or_admin",
]
