# project/utils/__init__.py
"""
工具包：包含项目中使用的各种工具函数
"""

from .utils import (
    # 私有工具函数（内部使用）
    _get_text_part,
    _award_points,
    _check_and_award_achievements,
    
    # 验证和权限相关
    validate_ownership,
    check_admin_permission,
    check_resource_permission,
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

__all__ = [
    # 文本处理
    "_get_text_part",
    
    # 积分和成就
    "_award_points",
    "_check_and_award_achievements",
    
    # 验证和权限
    "validate_ownership",
    "check_admin_permission", 
    "check_resource_permission",
    "check_unique_field",
    
    # 分页
    "paginate_query",
    
    # 向量嵌入
    "generate_embedding_safe",
    "update_embedding_safe",
    
    # 数据填充
    "populate_user_name",
    "populate_like_status",
    
    # 资源获取
    "get_user_by_id_or_404",
    "get_resource_or_404",
    "get_user_resource_or_404",
    
    # 数据库操作
    "commit_or_rollback",
    "create_and_add_resource",
    
    # 详情获取
    "get_resources_with_details",
    "get_projects_with_details",
    "get_courses_with_details", 
    "get_forum_topics_with_details",
    
    # 用户相关工具
    "process_skills_field",
    "build_user_combined_text",
    "update_fields_from_dict",
    
    # 调试
    "debug_log",
    "debug_operation",
]
