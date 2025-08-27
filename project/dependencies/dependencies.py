# project/dependencies/dependencies.py

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import secrets
from database import SessionLocal  # 确保 base.py 存在且 SessionLocal 已从中定义
from models import Student  # 导入 Student 模型，用于用户认证
# --- JWT 认证配置 ---
SECRET_KEY = os.getenv("SECRET_KEY", "your-very-secret-key-that-should-be-in-env-production")  # 从环境变量获取，避免硬编码
ALGORITHM = "HS256"  # JWT签名算法
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 访问令牌过期时间（例如7天）

# 令牌认证方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")  # 指向登录接口的URL
bearer_scheme = HTTPBearer(auto_error=False)  # auto_error=False 避免在依赖注入层直接抛出401

# --- 密码哈希上下文 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- 密码处理函数 ---
def verify_password(plain_password, hashed_password):
    """验证明文密码与哈希密码是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """生成密码哈希值"""
    return pwd_context.hash(password)


# --- 数据库会话依赖 ---
def get_db():
    """
    依赖项：为每个请求提供一个独立的数据库会话。
    """
    db = SessionLocal()
    try:
        # 性能优化：数据库连接活跃性验证 (仅在DEBUG模式或高负载下开启)
        # if os.getenv("DEBUG_DB_CONN", "False").lower() == "true": # 可通过环境变量控制
        #     print("DEBUG_DB: 尝试从连接池获取数据库会话...")
        #     start_time = time.time()
        #     db.connection() # 强制从连接池获取连接并测试
        #     print(f"DEBUG_DB: 成功获取数据库会话。耗时: {time.time() - start_time:.4f}s")
        #     print("DEBUG_DB: 验证数据库连接活跃性...")
        #     start_time = time.time()
        #     db.execute(text("SELECT 1")) # 执行一个轻量级查询来验证连接是否活跃
        #     print(f"DEBUG_DB: 数据库连接活跃性验证通过。耗时: {time.time() - start_time:.4f}s")
        yield db
    except Exception as e:
        # print(f"ERROR_DB: 数据库会话使用过程中发生异常: {e}")
        # 移除，防止重复打印
        db.rollback()  # 发生异常时回滚
        raise  # 重新抛出异常
    finally:
        db.close()  # 确保会话关闭


# --- 辅助函数：创建 JWT 访问令牌 ---
def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None):
    """
    根据提供的用户信息创建 JWT 访问令牌。
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta  # 使用 UTC 时间，更严谨
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})  # 将过期时间添加到payload
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)  # 使用定义的秘密密钥和算法编码
    return encoded_jwt


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
        # user = db.query(Student).filter(Student.id == user_id).first()
        # if user is None:
        #     raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT 令牌指向的用户不存在")

        # 由于依赖注入的 get_current_user_id 会在每个受保护接口调用，频繁查询会加重数据库负担。
        # 这里的目的是验证 ID 合法性，通常在数据库层面，只需要确认 ID 存在即可
        # 避免全量加载 Student 对象。如果需要在路由函数中用到 Student 对象的其他属性，再通过 user_id 查询。
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


# --- 依赖项：验证用户是否为管理员 ---
async def is_admin_user(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    验证当前用户是否是系统管理员。如果不是，则抛出403 Forbidden异常。
    返回完整的 Student 对象，方便后续操作。
    """
    print(f"DEBUG_ADMIN_AUTH: 验证用户 {current_user_id} 是否为管理员。")
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作，此功能仅限系统管理员。")
    return user  # 返回整个用户对象，方便需要用户详情的接口


# --- 通用依赖项：分页参数 ---
def get_pagination_params(
    page: int = 1,
    page_size: int = 10,
    max_page_size: int = 100
):
    """
    通用分页参数依赖项
    
    Args:
        page: 页码（从1开始）
        page_size: 每页大小
        max_page_size: 最大每页大小
    
    Returns:
        dict: 包含分页参数的字典
    """
    page = max(1, page)  # 确保页码至少为1
    page_size = min(page_size, max_page_size)  # 限制每页大小
    offset = (page - 1) * page_size
    
    return {
        "page": page,
        "page_size": page_size,
        "offset": offset,
        "limit": page_size
    }


# --- 依赖项：获取当前用户对象 ---
async def get_current_user(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> Student:
    """
    获取当前登录用户的完整对象
    
    Args:
        current_user_id: 当前用户ID
        db: 数据库会话
    
    Returns:
        Student: 用户对象
        
    Raises:
        HTTPException: 如果用户不存在
    """
    user = db.query(Student).filter(Student.id == current_user_id).first()
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
        from utils import get_resource_or_404
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
        from utils import get_user_resource_or_404
        return get_user_resource_or_404(db, model_class, resource_id, current_user_id, user_field, error_message)
    return dependency


# --- 权限检查依赖项 ---

async def require_admin_user(current_user_id: int = Depends(get_current_user_id), 
                           db: Session = Depends(get_db)) -> Student:
    """
    要求管理员权限的依赖项
    
    Args:
        current_user_id: 当前用户ID
        db: 数据库会话
    
    Returns:
        Student: 管理员用户对象
        
    Raises:
        HTTPException: 如果用户不是管理员
    """
    from utils import check_admin_permission
    return check_admin_permission(db, current_user_id)


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
        from utils import get_resource_or_404, check_resource_permission
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
        from utils import get_resource_or_404, check_resource_permission, get_user_by_id_or_404
        resource = get_resource_or_404(db, model_class, resource_id)
        admin_user = get_user_by_id_or_404(db, current_user_id)
        check_resource_permission(resource, current_user_id, admin_user, owner_field)
        return resource
    return dependency
