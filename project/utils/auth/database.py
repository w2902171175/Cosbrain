# project/utils/dependencies/database.py
"""
数据库相关依赖注入
"""

import os
from sqlalchemy.orm import Session
from project.database import SessionLocal


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
