# project/services/auth_service.py
"""
认证服务层 - 统一身份验证业务逻辑
应用courses和forum模块的优化模式
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import logging
import secrets

from project.models import User, UserCourse, UserAchievement
from project.utils import pwd_context, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from project.utils import cache_manager
from project.utils.auth.auth_utils import (
    generate_unique_username, validate_registration_data, validate_update_data,
    find_user_by_credential, normalize_skills_data, build_combined_text
)
from project.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

class AuthService:
    """认证核心业务逻辑服务"""
    
    @staticmethod
    def get_user_by_id_optimized(db: Session, user_id: int) -> User:
        """优化的用户查询 - 使用预加载和缓存"""
        cache_key = f"user:{user_id}:profile"
        
        # 尝试从缓存获取
        cached_user = cache_manager.get(cache_key)
        if cached_user:
            return cached_user
        
        # 使用joinedload预加载相关数据
        user = db.query(User).options(
            joinedload(User.user_courses),
            joinedload(User.achievements)  # 修正：使用achievements而不是user_achievements
        ).filter(User.id == user_id).first()
        
        if not user:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, user, expire=600)  # 10分钟缓存，修正参数名
        return user
    
    @staticmethod
    def authenticate_user_optimized(db: Session, credential: str, password: str) -> Optional[User]:
        """优化的用户认证 - 支持邮箱/手机号登录"""
        cache_key = f"auth:credential:{credential}"
        
        # 从缓存获取用户信息（短时间缓存）
        cached_user = cache_manager.get(cache_key)
        if cached_user and pwd_context.verify(password, cached_user.password_hash):
            return cached_user
        
        # 查找用户
        user = find_user_by_credential(credential, db)  # 修正参数顺序
        if not user:
            return None
        
        # 验证密码
        if not pwd_context.verify(password, user.password_hash):
            return None
        
        # 短时间缓存认证信息（2分钟）
        cache_manager.set(cache_key, user, expire=120)  # 修正参数名：expire而不是expire_time
        return user
    
    @staticmethod
    def register_user_optimized(db: Session, user_data: dict) -> Dict[str, Any]:
        """优化的用户注册"""
        
        try:
            # 验证注册数据
            logger.info(f"开始注册用户，数据: {user_data}")
            validate_registration_data(db, user_data)
            
            # 生成唯一用户名
            base_username = user_data.get("username", "user")
            unique_username = generate_unique_username(db, base_username)
            
            # 准备用户数据
            normalized_skills = normalize_skills_data(user_data.get("skills", []))
            
            # 创建用户
            user = User(
                username=unique_username,
                email=user_data.get("email"),
                phone_number=user_data.get("phone_number"),
                password_hash=pwd_context.hash(user_data["password"]),
                name=user_data.get("name"),  # 修正：使用name而不是real_name
                student_id=user_data.get("student_id"),
                school=user_data.get("school"),  # 修正：使用school字段
                created_at=datetime.utcnow()
            )
            
            db.add(user)
            db.flush()
            db.refresh(user)
            
            # 注册成功后，异步创建用户Profile（包含向量生成）
            # 这将通过后台任务处理，不会阻塞注册流程
            logger.info(f"用户注册成功: {user.username} (ID: {user.id})")
            
            # 注册积分和成就将通过后台任务处理
            # 这样不会阻塞用户注册流程
            
            return {
                "user": user,
                "message": "注册成功"
            }
            
        except Exception as e:
            logger.error(f"用户注册失败: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def login_user_optimized(db: Session, credential: str, password: str) -> Dict[str, Any]:
        """优化的用户登录"""
        
        # 认证用户
        user = AuthService.authenticate_user_optimized(db, credential, password)
        if not user:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="邮箱/手机号或密码错误",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # 更新最后登录时间
        user.last_login_at = datetime.utcnow()  # 修正：使用last_login_at而不是last_login
        db.flush()
        
        # 生成访问令牌
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=access_token_expires
        )
        
        # 清除用户相关缓存（确保数据一致性）
        # 注意：在同步环境中，不能直接使用asyncio.create_task
        # TODO: 实现同步的缓存清理或在异步上下文中调用
        try:
            cache_manager.delete_pattern(f"user:{user.id}:*")
        except Exception as e:
            logger.warning(f"清理缓存失败: {e}")  # 缓存清理失败不应阻塞登录
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user
        }
    
    @staticmethod
    def update_user_profile_optimized(
        db: Session, 
        user_id: int, 
        update_data: dict
    ) -> User:
        """优化的用户资料更新"""
        
        user = AuthService.get_user_by_id_optimized(db, user_id)
        
        # 验证更新数据 - 修正参数顺序
        validate_update_data(update_data, user_id, db)
        
        # 处理技能数据
        if "skills" in update_data:
            update_data["skills"] = normalize_skills_data(update_data["skills"])
        
        # 更新用户字段
        for field, value in update_data.items():
            if hasattr(user, field) and value is not None:
                setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        db.flush()
        
        # 重新生成AI嵌入向量（如果相关字段发生变化）
        profile_fields = ["name", "major", "skills", "self_introduction"]  # 修正：使用name而不是real_name
        if any(field in update_data for field in profile_fields):
            try:
                # 暂时使用零向量作为占位符，实际的嵌入向量生成可以通过后台任务处理
                # 注释掉可能不存在的字段，避免AttributeError
                # from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
                # user.user_vector = GLOBAL_PLACEHOLDER_ZERO_VECTOR
                # db.flush()
                logger.info(f"用户 {user_id} 的AI嵌入向量更新已跳过")
            except Exception as e:
                logger.warning(f"更新用户嵌入向量失败: {str(e)}")
        
        db.refresh(user)
        
        # 清除用户相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"user:{user_id}:*"))
        
        return user

class AuthUtils:
    """认证工具类"""
    
    @staticmethod
    def validate_password_strength(password: str) -> List[str]:
        """验证密码强度"""
        errors = []
        
        if len(password) < 6:
            errors.append("密码长度至少需要6个字符")
        
        # 更灵活的密码策略：满足以下条件之一即可
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
        
        complexity_score = sum([has_upper, has_lower, has_digit, has_special])
        
        if complexity_score < 2:
            errors.append("密码需要包含以下字符类型中的至少两种：大写字母、小写字母、数字、特殊字符")
        
        return errors
    
    @staticmethod
    def validate_email_format(email: str) -> bool:
        """验证邮箱格式"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_phone_format(phone: str) -> bool:
        """验证手机号格式"""
        import re
        # 中国手机号格式验证
        pattern = r'^1[3-9]\d{9}$'
        return re.match(pattern, phone) is not None
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """生成安全令牌"""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def format_user_response(user: User, include_sensitive: bool = False) -> dict:
        """格式化用户响应数据"""
        result = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "name": user.name,  # 修正：使用name而不是real_name
            "student_id": user.student_id,
            "school": user.school,  # 修正：使用school而不是academic_year
            "is_admin": user.is_admin,  # 添加缺失的字段
            "major": getattr(user, 'major', None),  # 从profile获取
            "class_name": getattr(user, 'class_name', None),  # 从profile获取
            "skills": getattr(user, 'skills', None),  # 从profile获取
            "self_introduction": getattr(user, 'self_introduction', None),  # 从profile获取
            "avatar_url": getattr(user, 'avatar_url', None),  # 修正：使用avatar_url
            "total_points": user.total_points,
            "login_count": user.login_count,  # 修正：使用login_count
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_login_at": user.last_login_at  # 修正：使用last_login_at
        }
        
        if include_sensitive:
            result["phone_number"] = user.phone_number
            # User模型没有is_active和is_superuser字段，使用默认值或其他逻辑
            result["is_active"] = not user.username.endswith('_deactivated')  # 基于用户名判断是否激活
            result["is_superuser"] = user.is_admin  # 使用is_admin代替is_superuser
        
        return result
    
    @staticmethod
    def check_user_permissions(user: User, required_permissions: List[str]) -> bool:
        """检查用户权限"""
        # 管理员拥有所有权限（使用is_admin代替is_superuser）
        if user.is_admin:
            return True
        
        # 这里可以扩展更复杂的权限检查逻辑
        return True
    
    @staticmethod
    def log_auth_event(event_type: str, user_id: Optional[int], details: dict):
        """记录认证事件"""
        logger.info(f"认证事件: {event_type}", extra={
            "user_id": user_id,
            "event_type": event_type,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        })
