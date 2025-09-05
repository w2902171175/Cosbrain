# project/utils/dependencies/password.py
"""
密码相关功能
"""

import warnings
# 抑制 passlib bcrypt 版本警告
warnings.filterwarnings("ignore", message=".*bcrypt version.*", category=UserWarning)

from passlib.context import CryptContext

# --- 密码哈希上下文 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- 密码处理函数 ---
def verify_password(plain_password, hashed_password):
    """验证明文密码与哈希密码是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """生成密码哈希值"""
    return pwd_context.hash(password)
