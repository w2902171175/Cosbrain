# project/database.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from base import Base
import models

load_dotenv()
# PostgreSQL 数据库连接字符串（优先读取环境变量，未提供则回退到原默认值）
DATABASE_URL = os.getenv(
    "DATABASE_URL"
)

if not DATABASE_URL:
    raise ValueError("DATABASE_URL 环境变量未设置。")

engine = create_engine(
    DATABASE_URL,
    echo=(os.getenv("SQL_ECHO", "false").lower() == "true"),  # 生产默认关闭，可通过环境变量开启
    pool_size=int(os.getenv("SQL_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("SQL_MAX_OVERFLOW", "20")),
    pool_timeout=int(os.getenv("SQL_POOL_TIMEOUT", "30")),
    pool_recycle=int(os.getenv("SQL_POOL_RECYCLE", "3600")),
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    print("DEBUG_DB: 正在尝试初始化数据库结构...")

    Base.metadata.drop_all(bind=engine)
    print("DEBUG_DB: 数据库中所有旧表已删除。")

    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()
        print("DEBUG_DB: pgvector 扩展已确保创建或已存在。")
    models.Base.metadata.create_all(bind=engine)
    print("DEBUG_DB: 数据库表已根据模型重新创建。")


def get_db():
    db = SessionLocal()
    try:
        print("DEBUG_DB: 尝试从连接池获取数据库会话...")
        print("DEBUG_DB: 成功获取数据库会话。")

        print("DEBUG_DB: 验证数据库连接活跃性...")
        db.execute(text("SELECT 1")).scalar()
        print("DEBUG_DB: 数据库连接活跃性验证通过。")

        yield db
    finally:
        if db:
            print("DEBUG_DB: 关闭数据库会话。")
            db.close()


def test_db_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            if result.scalar() == 1:
                print("DEBUG_DB: 数据库连接成功！")
            else:
                print("WARNING_DB: 数据库连接失败：意外结果。")
    except Exception as e:
        print(f"ERROR_DB: 数据库连接失败：{e}")
        print("请检查 .env 文件中的 DATABASE_URL 是否正确，以及PostgreSQL服务是否运行。")


if __name__ == "__main__":
    print("DEBUG_DB: 正在测试数据库连接...")
    test_db_connection()
    print("DEBUG_DB: 启动数据库初始化流程...")
    init_db()
    print("DEBUG_DB: 数据库初始化流程完成。")
