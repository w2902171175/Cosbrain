# project/utils/dependencies/jwt_auth.py
"""
JWT 认证相关功能
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, HTTPBearer

# --- JWT 认证配置 ---
SECRET_KEY = os.getenv("SECRET_KEY", "your-very-secret-key-that-should-be-in-env-production")  # 从环境变量获取，避免硬编码
ALGORITHM = "HS256"  # JWT签名算法
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 访问令牌过期时间（例如7天）

# 令牌认证方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")  # 指向登录接口的URL
bearer_scheme = HTTPBearer(auto_error=False)  # auto_error=False 避免在依赖注入层直接抛出401


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
