# project/utils/auth/auth_utils.py
"""认证模块工具函数"""

import secrets
import logging
from typing import Optional, List, Dict, Any
from json import loads, JSONDecodeError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from project.models import User
from project.utils.core.common_utils import _get_text_part, check_unique_field

logger = logging.getLogger(__name__)


def generate_unique_username(db: Session, base_name: str = "新用户") -> str:
    """生成唯一用户名
    
    Args:
        db: 数据库会话
        base_name: 用户名前缀
        
    Returns:
        str: 唯一的用户名
        
    Raises:
        HTTPException: 无法生成唯一用户名时抛出
    """
    attempts = 0
    max_attempts = 10
    
    while attempts < max_attempts:
        random_suffix = secrets.token_hex(4)
        proposed_username = f"{base_name}_{random_suffix}"
        
        if not db.query(User).filter(User.username == proposed_username).first():
            logger.info("生成唯一用户名", extra={"username": proposed_username})
            return proposed_username
            
        attempts += 1
    
    logger.error("无法生成唯一用户名", extra={"attempts": attempts, "base_name": base_name})
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="无法生成唯一用户名，请稍后再试或提供一个自定义用户名。"
    )


def check_field_uniqueness(
    db: Session, 
    model_class, 
    field_name: str, 
    field_value: str, 
    exclude_id: Optional[int] = None
) -> None:
    """检查字段唯一性
    
    Args:
        db: 数据库会话
        model_class: 数据模型类
        field_name: 字段名
        field_value: 字段值
        exclude_id: 排除的ID（用于更新操作）
        
    Raises:
        HTTPException: 字段值已存在时抛出
    """
    # 使用原有的check_unique_field函数，但适配新的错误信息格式
    error_message = f"{field_name}已被使用"
    
    if exclude_id:
        # 对于更新操作，需要排除当前用户
        query = db.query(model_class).filter(
            getattr(model_class, field_name) == field_value,
            model_class.id != exclude_id
        )
        if query.first():
            logger.warning("字段唯一性检查失败", extra={
                "field_name": field_name, 
                "field_value": field_value,
                "exclude_id": exclude_id
            })
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=error_message
            )
    else:
        # 对于注册操作，直接检查唯一性
        query = db.query(model_class).filter(getattr(model_class, field_name) == field_value)
        if query.first():
            logger.warning("字段唯一性检查失败", extra={
                "field_name": field_name, 
                "field_value": field_value
            })
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=error_message
            )


def build_combined_text(user_data: Dict[str, Any]) -> str:
    """构建用户综合描述文本
    
    Args:
        user_data: 用户数据字典
        
    Returns:
        str: 组合后的描述文本
    """
    # 处理技能数据
    skills_text = ""
    if user_data.get('skills'):
        skills_list = normalize_skills_data(user_data['skills'])
        skills_text = ", ".join([
            s.get("name", "") for s in skills_list 
            if isinstance(s, dict) and s.get("name")
        ])
    
    # 组合所有文本部分
    text_parts = [
        _get_text_part(user_data.get('name')),
        _get_text_part(user_data.get('major')),
        _get_text_part(skills_text),
        _get_text_part(user_data.get('interests')),
        _get_text_part(user_data.get('bio')),
        _get_text_part(user_data.get('awards_competitions')),
        _get_text_part(user_data.get('academic_achievements')),
        _get_text_part(user_data.get('soft_skills')),
        _get_text_part(user_data.get('portfolio_link')),
        _get_text_part(user_data.get('preferred_role')),
        _get_text_part(user_data.get('availability')),
        _get_text_part(user_data.get('location'))
    ]
    
    combined_text = ". ".join(filter(None, text_parts)).strip()
    
    # 如果没有内容，使用默认描述
    if not combined_text:
        name = user_data.get('name') or user_data.get('username', '用户')
        combined_text = f"{name} 的简介。"
    
    logger.debug("构建用户综合文本", extra={
        "text_length": len(combined_text),
        "preview": combined_text[:100]
    })
    
    return combined_text


def normalize_skills_data(skills_data) -> List[Dict[str, Any]]:
    """标准化技能数据格式
    
    Args:
        skills_data: 技能数据（可能是字符串、列表或None）
        
    Returns:
        List[Dict[str, Any]]: 标准化后的技能列表
    """
    if isinstance(skills_data, str):
        try:
            return loads(skills_data)
        except JSONDecodeError:
            logger.warning("技能数据JSON解析失败", extra={"skills_data": skills_data})
            return []
    elif isinstance(skills_data, list):
        return skills_data
    elif skills_data is None:
        return []
    else:
        logger.warning("未知的技能数据类型", extra={"type": type(skills_data)})
        return []


def find_user_by_credential(credential: str, db: Session) -> Optional[User]:
    """根据邮箱或手机号查找用户
    
    Args:
        credential: 登录凭证（邮箱或手机号）
        db: 数据库会话
        
    Returns:
        Optional[User]: 找到的用户对象，未找到则返回None
    """
    if "@" in credential:
        logger.debug("通过邮箱查找用户", extra={"credential": credential})
        return db.query(User).filter(User.email == credential).first()
    elif credential.isdigit() and 7 <= len(credential) <= 15:
        logger.debug("通过手机号查找用户", extra={"credential": credential})
        return db.query(User).filter(User.phone_number == credential).first()
    else:
        logger.warning("无效的登录凭证格式", extra={"credential": credential})
        return None


def prepare_user_data_for_registration(user_data, final_username: str) -> Dict[str, Any]:
    """为用户注册准备数据字典
    
    Args:
        user_data: 用户注册数据
        final_username: 最终确定的用户名
        
    Returns:
        Dict[str, Any]: 准备好的用户数据字典
    """
    # 处理技能数据
    skills_list_for_db = []
    if user_data.skills:
        skills_list_for_db = [skill.model_dump() for skill in user_data.skills]
    
    # 构建用户数据字典
    user_dict = {
        'name': user_data.name if user_data.name else final_username,
        'username': final_username,
        'major': user_data.major if user_data.major else "未填写",
        'skills': skills_list_for_db,
        'interests': user_data.interests if user_data.interests else "未填写",
        'bio': user_data.bio if user_data.bio else "欢迎使用本平台！",
        'awards_competitions': user_data.awards_competitions,
        'academic_achievements': user_data.academic_achievements,
        'soft_skills': user_data.soft_skills,
        'portfolio_link': user_data.portfolio_link,
        'preferred_role': user_data.preferred_role,
        'availability': user_data.availability,
        'location': user_data.location
    }
    
    return user_dict


def validate_registration_data(db: Session, user_data) -> None:
    """验证用户注册数据
    
    Args:
        db: 数据库会话
        user_data: 用户注册数据（字典格式）
        
    Raises:
        HTTPException: 验证失败时抛出
    """
    # 检查邮箱唯一性
    if user_data.get("email"):
        check_field_uniqueness(db, User, "email", user_data["email"])
    
    # 检查手机号唯一性
    if user_data.get("phone_number"):
        check_field_uniqueness(db, User, "phone_number", user_data["phone_number"])
    
    # 检查用户名唯一性（如果提供了）
    if user_data.get("username"):
        check_field_uniqueness(db, User, "username", user_data["username"])


def validate_update_data(user_update_data, current_user_id: int, db: Session) -> None:
    """验证用户更新数据
    
    Args:
        user_update_data: 用户更新数据（dict或Pydantic模型）
        current_user_id: 当前用户ID
        db: 数据库会话
        
    Raises:
        HTTPException: 验证失败时抛出
    """
    # 兼容dict和Pydantic模型
    if hasattr(user_update_data, 'dict'):
        update_data = user_update_data.dict(exclude_unset=True)
    else:
        update_data = user_update_data if isinstance(user_update_data, dict) else {}
    
    # 检查用户名唯一性
    if "username" in update_data and update_data["username"] is not None:
        check_field_uniqueness(db, User, "username", update_data["username"], current_user_id)
    
    # 检查手机号唯一性
    if "phone_number" in update_data and update_data["phone_number"] is not None:
        check_field_uniqueness(db, User, "phone_number", update_data["phone_number"], current_user_id)
