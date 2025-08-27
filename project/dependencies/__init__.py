# project/dependencies/__init__.py
"""
依赖包：包含 FastAPI 依赖注入相关的函数和配置
"""

from .dependencies import (
    # 密码相关
    verify_password,
    get_password_hash,
    
    # 数据库会话
    get_db,
    
    # JWT 令牌相关
    create_access_token,
    
    # 用户认证相关
    get_current_user_id,
    get_current_user,
    get_current_user_id_optional,
    
    # 管理员权限
    is_admin_user,
    require_admin_user,
    
    # 分页参数
    get_pagination_params,
    
    # 资源依赖
    get_resource_dependency,
    get_user_resource_dependency,
    require_resource_owner,
    require_resource_owner_or_admin,
    
    # 常量
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    oauth2_scheme,
    bearer_scheme,
    pwd_context,
)

__all__ = [
    # 密码处理
    "verify_password",
    "get_password_hash",
    
    # 数据库
    "get_db",
    
    # JWT 令牌
    "create_access_token",
    
    # 用户认证
    "get_current_user_id",
    "get_current_user",
    "get_current_user_id_optional",
    
    # 管理员权限
    "is_admin_user",
    "require_admin_user",
    
    # 分页
    "get_pagination_params",
    
    # 资源依赖
    "get_resource_dependency",
    "get_user_resource_dependency",
    "require_resource_owner",
    "require_resource_owner_or_admin",
    
    # 常量和配置
    "SECRET_KEY",
    "ALGORITHM", 
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "oauth2_scheme",
    "bearer_scheme",
    "pwd_context",
]
