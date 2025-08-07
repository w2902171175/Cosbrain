# project/database.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

from fastapi import HTTPException, status

from base import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL 环境变量未设置。请在 .env 文件中提供PostgreSQL连接字符串。")

engine = create_engine(
    DATABASE_URL,
    echo=True,  # 调试时保留
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    print("正在尝试创建数据库表（如果不存在）...")
    Base.metadata.create_all(bind=engine)
    print("数据库表已创建或已存在。")


def get_db():
    db = None
    try:
        print("DEBUG_DB: 尝试从连接池获取数据库会话...")
        db = SessionLocal()
        print("DEBUG_DB: 成功获取数据库会话。")

        print("DEBUG_DB: 验证数据库连接活跃性...")
        db.execute(text("SELECT 1")).scalar()
        print("DEBUG_DB: 数据库连接活跃性验证通过。")

        yield db
    except Exception as e:
        if db is None:
            print(f"ERROR_DB: 无法从连接池获取数据库会话: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"数据库连接失败: {e}")
        else:
            print(f"ERROR_DB: 数据库会话使用过程中发生异常: {e}")
            raise
    finally:
        if db:
            print("DEBUG_DB: 关闭数据库会话。")
            db.close()


def test_db_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            if result.scalar() == 1:
                print("数据库连接成功！")
            else:
                print("数据库连接失败：意外结果。")
    except Exception as e:
        print(f"数据库连接失败：{e}")
        print("请检查 .env 文件中的 DATABASE_URL 是否正确，以及PostgreSQL服务是否运行。")


if __name__ == "__main__":
    print("正在测试数据库连接...")
    test_db_connection()

    # 在这里导入models，以便init_db能看到所有模型
    # from . import models # 如果这里也报错，可能需要调整 sys.path 或使用完整路径

    # 也可以直接调用 Base.metadata.create_all(bind=engine)
    # 但为了兼容性和明确性，建议在 init_db 中处理

    # Alembic 依赖于 env.py 导入 Base.metadata，这里只是本地测试数据库连接和创建
    # 所以直接调用 models 可能会导致循环导入，或者需要更复杂的 setup
    # 对于 Alembic 而言，env.py 的 sys.path 配置和 Base.metadata 赋值更为关键。

    # 为了让 init_db 看到所有模型，通常会确保所有模型都被导入到 main.py 或某个中心文件
    # 并且 Base.metadata 能够收集到它们。
    # 对于 Alembic，env.py 会正确处理这个。

    print(f"Base.metadata.tables after import: {list(Base.metadata.tables.keys())}")

    init_db()
    print("数据库初始化流程完成。")

