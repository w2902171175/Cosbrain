# project/utils/dependencies/resources.py
"""
资源相关依赖注入
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from .database import get_db
from .user_auth import get_current_user_id


# --- 通用资源依赖项 ---

def get_resource_dependency(model_class, error_message: str = None):
    """
    创建资源获取依赖项的工厂函数
    
    Args:
        model_class: 模型类
        error_message: 自定义错误信息
    
    Returns:
        依赖项函数
    """
    def dependency(resource_id: int, db: Session = Depends(get_db)):
        from ..core import get_resource_or_404
        return get_resource_or_404(db, model_class, resource_id, error_message)
    return dependency


def get_user_resource_dependency(model_class, user_field: str = "owner_id", error_message: str = None):
    """
    创建用户资源获取依赖项的工厂函数
    
    Args:
        model_class: 模型类
        user_field: 用户字段名
        error_message: 自定义错误信息
    
    Returns:
        依赖项函数
    """
    def dependency(resource_id: int, 
                   current_user_id: int = Depends(get_current_user_id),
                   db: Session = Depends(get_db)):
        from ..core import get_user_resource_or_404
        return get_user_resource_or_404(db, model_class, resource_id, current_user_id, user_field, error_message)
    return dependency


# --- 权限检查依赖项 ---

def require_resource_owner(model_class, owner_field: str = "owner_id"):
    """
    创建需要资源所有者权限的依赖项工厂函数
    
    Args:
        model_class: 模型类
        owner_field: 所有者字段名
    
    Returns:
        依赖项函数
    """
    def dependency(resource_id: int,
                   current_user_id: int = Depends(get_current_user_id),
                   db: Session = Depends(get_db)):
        from ..core import get_resource_or_404, check_resource_permission
        resource = get_resource_or_404(db, model_class, resource_id)
        check_resource_permission(resource, current_user_id, None, owner_field)
        return resource
    return dependency


def require_resource_owner_or_admin(model_class, owner_field: str = "owner_id"):
    """
    创建需要资源所有者或管理员权限的依赖项工厂函数
    
    Args:
        model_class: 模型类
        owner_field: 所有者字段名
    
    Returns:
        依赖项函数
    """
    def dependency(resource_id: int,
                   current_user_id: int = Depends(get_current_user_id),
                   db: Session = Depends(get_db)):
        from ..core import get_resource_or_404, check_resource_permission, get_user_by_id_or_404
        resource = get_resource_or_404(db, model_class, resource_id)
        admin_user = get_user_by_id_or_404(db, current_user_id)
        check_resource_permission(resource, current_user_id, admin_user, owner_field)
        return resource
    return dependency
