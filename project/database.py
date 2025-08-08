# project/database.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

from fastapi import HTTPException, status
from base import Base
import models

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL 环境变量未设置。请在 .env 文件中提供PostgreSQL连接字符串。")

engine = create_engine(
    DATABASE_URL,
    echo=True,  # 调试时保留，会打印SQL语句
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    print("DEBUG_DB: 正在尝试初始化数据库结构...")
    # **警告：以下行将删除数据库中所有由 SQLAlchemy 管理的表及其数据！**
    # **仅在开发或测试环境使用，生产环境请通过 Alembic 或其他迁移工具进行版本化管理。**
    Base.metadata.drop_all(bind=engine)  # <-- **这一行已被添加**
    print("DEBUG_DB: 数据库中所有旧表已删除。")

    Base.metadata.create_all(bind=engine)
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

