# project/utils/dependencies/user_auth.py
"""
用户认证相关依赖注入
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from .database import get_db
from .jwt_auth import bearer_scheme, SECRET_KEY, ALGORITHM
from project.models import User


# --- 依赖项：获取当前登录用户ID ---
async def get_current_user_id(
        # 依赖于 bearer_scheme 来获取 Authorization: Bearer <token>
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        db: Session = Depends(get_db)
) -> int:
    """
    从 JWT 令牌中提取并验证用户ID。
    如果令牌无效或缺失，抛出 HTTPException。
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials  # 获取实际的 token 字符串

    try:
        # 使用 SECRET_KEY 和 ALGORITHM 解码 JWT 令牌
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")  # JWT payload 中的 'sub' (subject) 字段通常存放用户ID

        if user_id_str is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT 令牌中缺少用户ID信息")

        user_id = int(user_id_str)  # 转换为整数

        # 验证用户是否存在 (确保 token 对应的用户是有效的)
        # 这里优化：如果不要 user 对象的详细信息，仅验证存在性即可
        # user = db.query(User).filter(User.id == user_id).first()
        # if user is None:
        #     raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT 令牌指向的用户不存在")

        # 由于依赖注入的 get_current_user_id 会在每个受保护接口调用，频繁查询会加重数据库负担。
        # 这里的目的是验证 ID 合法性，通常在数据库层面，只需要确认 ID 存在即可
        # 避免全量加载 User 对象。如果需要在路由函数中用到 User 对象的其他属性，再通过 user_id 查询。
        # 为了简化，我们暂时不进行这个额外的 db 查询，信任 token 中的 user_id
        # 如果极端情况，用户在登录后被删除了，但其token未过期，依然可以访问，这是后续可以优化的点。
        # 目前为了性能和减少复杂性，假设 token 中的 user_id 是有效的。

        print(f"DEBUG_AUTH: 已认证用户 ID: {user_id}")
        return user_id

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的 JWT 令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        print(f"ERROR_AUTH: 认证过程中发生未知错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证过程中发生服务器错误"
        )


# --- 依赖项：获取当前用户对象 ---
async def get_current_user(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> User:
    """
    获取当前登录用户的完整对象
    
    Args:
        current_user_id: 当前用户ID
        db: 数据库会话
    
    Returns:
        User: 用户对象
        
    Raises:
        HTTPException: 如果用户不存在
    """
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


# --- 依赖项：可选的用户认证（用于允许匿名访问的接口） ---
async def get_current_user_id_optional(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> Optional[int]:
    """
    可选的用户认证，如果没有提供token或token无效，返回None而不是抛出异常
    用于那些允许匿名访问但为认证用户提供额外功能的接口
    
    Args:
        credentials: 认证凭据
        db: 数据库会话
    
    Returns:
        Optional[int]: 用户ID或None
    """
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        
        if user_id_str is None:
            return None
            
        user_id = int(user_id_str)
        return user_id
        
    except (JWTError, ValueError):
        return None


# --- 依赖项：验证用户是否为管理员 ---
async def is_admin_user(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    验证当前用户是否是系统管理员。如果不是，则抛出403 Forbidden异常。
    返回完整的 User 对象，方便后续操作。
    """
    print(f"DEBUG_ADMIN_AUTH: 验证用户 {current_user_id} 是否为管理员。")
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作，此功能仅限系统管理员。")
    return user  # 返回整个用户对象，方便需要用户详情的接口


async def require_admin_user(current_user_id: int = Depends(get_current_user_id), 
                           db: Session = Depends(get_db)) -> User:
    """
    要求管理员权限的依赖项
    
    Args:
        current_user_id: 当前用户ID
        db: 数据库会话
    
    Returns:
        User: 管理员用户对象
        
    Raises:
        HTTPException: 如果用户不是管理员
    """
    from ..core import check_admin_permission
    return check_admin_permission(db, current_user_id)
