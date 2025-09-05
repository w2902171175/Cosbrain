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
from project.routers.auth.auth_utils import (
    generate_unique_username, validate_registration_data, validate_update_data,
    find_user_by_credential, normalize_skills_data, build_combined_text
)
from project.routers.auth.embedding_manager import EmbeddingManager

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
            joinedload(User.user_achievements)
        ).filter(User.id == user_id).first()
        
        if not user:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, user, expire_time=600)  # 10分钟缓存
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
        user = find_user_by_credential(db, credential)
        if not user:
            return None
        
        # 验证密码
        if not pwd_context.verify(password, user.password_hash):
            return None
        
        # 短时间缓存认证信息（2分钟）
        cache_manager.set(cache_key, user, expire_time=120)
        return user
    
    @staticmethod
    def register_user_optimized(db: Session, user_data: dict) -> Dict[str, Any]:
        """优化的用户注册"""
        
        # 验证注册数据
        validate_registration_data(db, user_data)
        
        # 生成唯一用户名
        base_username = user_data.get("username", "user")
        unique_username = generate_unique_username(db, base_username)
        
        # 准备用户数据
        normalized_skills = normalize_skills_data(user_data.get("skills", []))
        
        # 创建用户
        user = User(
            username=unique_username,
            email=user_data["email"],
            phone_number=user_data.get("phone_number"),
            password_hash=pwd_context.hash(user_data["password"]),
            real_name=user_data.get("real_name"),
            student_id=user_data.get("student_id"),
            academic_year=user_data.get("academic_year"),
            major=user_data.get("major"),
            class_name=user_data.get("class_name"),
            skills=normalized_skills,
            self_introduction=user_data.get("self_introduction"),
            profile_image=user_data.get("profile_image"),
            created_at=datetime.utcnow()
        )
        
        db.add(user)
        db.flush()
        db.refresh(user)
        
        # 生成AI嵌入向量（异步）
        try:
            combined_text = build_combined_text(user)
            embedding_manager = EmbeddingManager()
            user.user_vector = embedding_manager.generate_embedding(combined_text)
            db.flush()
        except Exception as e:
            logger.warning(f"生成用户嵌入向量失败: {str(e)}")
            from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
            user.user_vector = GLOBAL_PLACEHOLDER_ZERO_VECTOR
            db.flush()
        
        # 奖励注册积分
        from project.utils import _award_points, _check_and_award_achievements
        _award_points(db, user.id, 100, "用户注册")
        _check_and_award_achievements(db, user.id)
        
        return {
            "user": user,
            "message": "注册成功"
        }
    
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
        user.last_login = datetime.utcnow()
        db.flush()
        
        # 生成访问令牌
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=access_token_expires
        )
        
        # 清除用户相关缓存（确保数据一致性）
        asyncio.create_task(cache_manager.delete_pattern(f"user:{user.id}:*"))
        
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
        
        # 验证更新数据
        validate_update_data(db, update_data, user_id)
        
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
        profile_fields = ["real_name", "major", "skills", "self_introduction"]
        if any(field in update_data for field in profile_fields):
            try:
                combined_text = build_combined_text(user)
                embedding_manager = EmbeddingManager()
                user.user_vector = embedding_manager.generate_embedding(combined_text)
                db.flush()
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
        
        if len(password) < 8:
            errors.append("密码长度至少需要8个字符")
        
        if not any(c.isupper() for c in password):
            errors.append("密码需要包含至少一个大写字母")
        
        if not any(c.islower() for c in password):
            errors.append("密码需要包含至少一个小写字母")
        
        if not any(c.isdigit() for c in password):
            errors.append("密码需要包含至少一个数字")
        
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
            "real_name": user.real_name,
            "student_id": user.student_id,
            "academic_year": user.academic_year,
            "major": user.major,
            "class_name": user.class_name,
            "skills": user.skills,
            "self_introduction": user.self_introduction,
            "profile_image": user.profile_image,
            "avatar": user.avatar,
            "points": user.points,
            "total_points": user.total_points,
            "level": user.level,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "last_login": user.last_login
        }
        
        if include_sensitive:
            result["phone_number"] = user.phone_number
            result["is_active"] = user.is_active
            result["is_superuser"] = user.is_superuser
        
        return result
    
    @staticmethod
    def check_user_permissions(user: User, required_permissions: List[str]) -> bool:
        """检查用户权限"""
        # 超级用户拥有所有权限
        if user.is_superuser:
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
