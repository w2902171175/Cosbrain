# project/database.py
import os
<<<<<<< HEAD
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from base import Base
import models
=======
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from project.base import Base
import project.models  # 这个导入会加载 models/__init__.py，进而导入所有模型
from project.models.achievement_points import Achievement, DEFAULT_ACHIEVEMENTS
import logging

# 设置日志
logger = logging.getLogger(__name__)
>>>>>>> origin/Cosbrainplus

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


<<<<<<< HEAD
def init_db():
    print("DEBUG_DB: 正在尝试初始化数据库结构...")

    Base.metadata.drop_all(bind=engine)
    print("DEBUG_DB: 数据库中所有旧表已删除。")
=======
def initialize_default_achievements():
    """
    初始化默认成就到数据库中
    在数据库表创建后自动调用
    """
    print("DEBUG_DB: 开始初始化默认成就...")
    
    db = SessionLocal()
    try:
        inserted_count = 0
        for achievement_data in DEFAULT_ACHIEVEMENTS:
            # 检查成就是否已存在
            existing_achievement = db.query(Achievement).filter(
                Achievement.name == achievement_data["name"]
            ).first()
            
            if existing_achievement:
                print(f"DEBUG_DB: 成就 '{achievement_data['name']}' 已存在，跳过。")
                continue

            # 创建新成就
            new_achievement = Achievement(
                name=achievement_data["name"],
                description=achievement_data["description"],
                criteria_type=achievement_data["criteria_type"],
                criteria_value=achievement_data["criteria_value"],
                badge_url=achievement_data["badge_url"],
                reward_points=achievement_data["reward_points"],
                is_active=achievement_data["is_active"]
            )
            db.add(new_achievement)
            print(f"DEBUG_DB: 添加成就: {new_achievement.name}")
            inserted_count += 1

        db.commit()
        print(f"DEBUG_DB: 默认成就初始化完成，共插入 {inserted_count} 个新成就。")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 初始化默认成就失败: {e}")
        logger.error(f"初始化默认成就失败: {e}")
        # 不抛出异常，让数据库初始化继续
    finally:
        db.close()


def reset_achievements():
    """
    重置成就系统：删除所有现有成就和用户成就，然后重新初始化默认成就
    警告：这将删除所有用户的成就进度！
    """
    print("WARNING_DB: 开始重置成就系统...")
    
    from project.models.achievement_points import UserAchievement
    
    db = SessionLocal()
    try:
        # 删除所有用户成就记录
        user_achievements_count = db.query(UserAchievement).count()
        if user_achievements_count > 0:
            db.query(UserAchievement).delete()
            print(f"DEBUG_DB: 删除了 {user_achievements_count} 个用户成就记录")
        
        # 删除所有成就定义
        achievements_count = db.query(Achievement).count()
        if achievements_count > 0:
            db.query(Achievement).delete()
            print(f"DEBUG_DB: 删除了 {achievements_count} 个成就定义")
        
        db.commit()
        
        # 重新初始化默认成就
        print("DEBUG_DB: 重新初始化默认成就...")
        for achievement_data in DEFAULT_ACHIEVEMENTS:
            new_achievement = Achievement(
                name=achievement_data["name"],
                description=achievement_data["description"],
                criteria_type=achievement_data["criteria_type"],
                criteria_value=achievement_data["criteria_value"],
                badge_url=achievement_data["badge_url"],
                reward_points=achievement_data["reward_points"],
                is_active=achievement_data["is_active"]
            )
            db.add(new_achievement)
            print(f"DEBUG_DB: 重新添加成就: {new_achievement.name}")
        
        db.commit()
        print("DEBUG_DB: 成就系统重置完成！")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 重置成就系统失败: {e}")
        logger.error(f"重置成就系统失败: {e}")
        raise
    finally:
        db.close()


def init_db():
    print("DEBUG_DB: 正在尝试初始化数据库结构...")

    try:
        # 先尝试删除依赖的视图
        with engine.connect() as connection:
            try:
                connection.execute(text("DROP VIEW IF EXISTS user_forum_stats CASCADE"))
                print("DEBUG_DB: 已删除依赖的视图。")
            except Exception as e:
                print(f"DEBUG_DB: 删除视图时出现错误（可能不存在）：{e}")
            
            connection.commit()
        
        # 然后删除所有表
        Base.metadata.drop_all(bind=engine)
        print("DEBUG_DB: 数据库中所有旧表已删除。")

    except Exception as e:
        print(f"WARNING_DB: 删除表时出现错误：{e}")
        print("DEBUG_DB: 尝试使用 CASCADE 方式删除...")
        try:
            with engine.connect() as connection:
                connection.execute(text("DROP SCHEMA public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
                connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
                connection.commit()
                print("DEBUG_DB: 使用 CASCADE 方式重置数据库结构成功。")
        except Exception as cascade_error:
            print(f"ERROR_DB: CASCADE 删除也失败：{cascade_error}")
            raise
>>>>>>> origin/Cosbrainplus

    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()
        print("DEBUG_DB: pgvector 扩展已确保创建或已存在。")
<<<<<<< HEAD
    models.Base.metadata.create_all(bind=engine)
    print("DEBUG_DB: 数据库表已根据模型重新创建。")
=======
    
    Base.metadata.create_all(bind=engine)
    print("DEBUG_DB: 数据库表已根据模型重新创建。")
    
    # 初始化默认成就
    initialize_default_achievements()
>>>>>>> origin/Cosbrainplus


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
<<<<<<< HEAD
=======
    import sys
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "reset-achievements":
            print("DEBUG_DB: 执行成就系统重置...")
            reset_achievements()
            print("✅ 成就系统重置完成！")
            sys.exit(0)
        elif command == "init-achievements":
            print("DEBUG_DB: 仅初始化成就系统...")
            initialize_default_achievements()
            print("✅ 成就系统初始化完成！")
            sys.exit(0)
        elif command == "help":
            print("数据库管理工具用法:")
            print("  python database.py                 # 完整初始化数据库")
            print("  python database.py init-achievements  # 仅初始化成就")
            print("  python database.py reset-achievements # 重置成就系统")
            print("  python database.py help              # 显示帮助")
            sys.exit(0)
        else:
            print(f"未知命令: {command}")
            print("使用 'python database.py help' 查看可用命令")
            sys.exit(1)
    
    # 默认完整初始化
>>>>>>> origin/Cosbrainplus
    print("DEBUG_DB: 正在测试数据库连接...")
    test_db_connection()
    print("DEBUG_DB: 启动数据库初始化流程...")
    init_db()
    print("DEBUG_DB: 数据库初始化流程完成。")
<<<<<<< HEAD
=======
    print("💡 注意：默认成就已自动创建完成！")
>>>>>>> origin/Cosbrainplus
