# ai_providers/security_utils.py
"""
安全工具模块
包含加密解密功能和API密钥管理
"""
import os
from cryptography.fernet import Fernet
from typing import Optional

# 从环境变量获取加密密钥，如果没有则生成一个临时密钥用于测试
_ENCRYPTION_KEY_STR = os.getenv("ENCRYPTION_KEY")

if not _ENCRYPTION_KEY_STR:
    # 生成一个临时密钥用于测试环境
    _ENCRYPTION_KEY_STR = Fernet.generate_key().decode('utf-8')
    print("WARNING: 使用临时加密密钥。在生产环境中请设置 ENCRYPTION_KEY 环境变量。")

try:
    FERNET_KEY = Fernet(_ENCRYPTION_KEY_STR.encode('utf-8'))
except Exception as e:
    # 如果解析失败，生成新密钥
    _ENCRYPTION_KEY_STR = Fernet.generate_key().decode('utf-8')
    FERNET_KEY = Fernet(_ENCRYPTION_KEY_STR.encode('utf-8'))
    print("WARNING: 加密密钥格式无效，使用新生成的临时密钥。")


def encrypt_key(key: str) -> str:
    """加密API密钥"""
    return FERNET_KEY.encrypt(key.encode()).decode()


def decrypt_key(encrypted_key: str) -> str:
    """解密API密钥"""
    return FERNET_KEY.decrypt(encrypted_key.encode()).decode()


def get_decrypted_api_key(encrypted_key: Optional[str], service_name: str = "未知服务") -> Optional[str]:
    """
    安全地获取解密后的API密钥
    
    Args:
        encrypted_key: 加密的API密钥
        service_name: 服务名称，用于日志记录
        
    Returns:
        解密后的API密钥，如果失败返回None
    """
    if not encrypted_key:
        print(f"WARNING: {service_name} 的API密钥为空")
        return None
        
    try:
        return decrypt_key(encrypted_key)
    except Exception as e:
        print(f"ERROR: 解密 {service_name} API密钥失败: {e}")
        return None
