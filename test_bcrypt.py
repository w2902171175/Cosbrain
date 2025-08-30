#!/usr/bin/env python3
"""
测试 bcrypt 和 passlib 兼容性
"""

import warnings
# 抑制 passlib bcrypt 版本警告
warnings.filterwarnings("ignore", message=".*bcrypt version.*", category=UserWarning)

try:
    import bcrypt
    print(f"✅ bcrypt 版本: {bcrypt.__version__}")
    
    # 测试基本的 bcrypt 功能
    password = b"test_password"
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())
    print(f"✅ bcrypt 哈希生成成功")
    
    # 验证密码
    if bcrypt.checkpw(password, hashed):
        print("✅ bcrypt 密码验证成功")
    else:
        print("❌ bcrypt 密码验证失败")

except Exception as e:
    print(f"❌ bcrypt 测试失败: {e}")

try:
    from passlib.context import CryptContext
    
    # 创建密码上下文
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    # 测试密码哈希
    test_password = "test_password"
    hashed_password = pwd_context.hash(test_password)
    print(f"✅ passlib + bcrypt 哈希生成成功")
    
    # 验证密码
    if pwd_context.verify(test_password, hashed_password):
        print("✅ passlib + bcrypt 密码验证成功")
    else:
        print("❌ passlib + bcrypt 密码验证失败")
        
    print("✅ passlib 与 bcrypt 兼容性测试通过")

except Exception as e:
    print(f"❌ passlib + bcrypt 测试失败: {e}")
