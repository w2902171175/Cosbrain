# project/scripts/forum_optimization_init.py
"""
论坛优化初始化脚本
用于设置数据库索引、初始化缓存等
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent  # 向上两级到达项目根目录
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from project.utils.database_optimization import db_optimizer
from project.utils.production_utils import cache_manager
from project.database import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database_optimizations():
    """初始化数据库优化"""
    try:
        engine = create_engine(DATABASE_URL)
        
        logger.info("开始创建数据库索引...")
        db_optimizer.create_forum_indexes(engine)
        
        logger.info("开始分析表统计信息...")
        db_optimizer.analyze_table_statistics(engine)
        
        logger.info("数据库优化初始化完成!")
        
    except Exception as e:
        logger.error(f"数据库优化初始化失败: {e}")
        raise

def run_migration_script():
    """运行数据库迁移脚本"""
    try:
        engine = create_engine(DATABASE_URL)
        
        # 读取迁移脚本
        migration_file = project_root / "project" / "migration" / "forum_optimization_migration.sql"
        
        if not migration_file.exists():
            logger.warning("迁移脚本文件不存在")
            return
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        logger.info("开始执行数据库迁移...")
        
        # 执行迁移脚本 - 使用事务块执行整个脚本
        with engine.connect() as conn:
            try:
                # 直接执行整个SQL脚本，让PostgreSQL处理语句分割
                conn.execute(text(migration_sql))
                conn.commit()
                logger.info("数据库迁移完成!")
            except Exception as e:
                logger.warning(f"数据库迁移执行中有警告: {e}")
                # 即使有警告也继续，因为可能是重复创建等非致命错误
                try:
                    conn.commit()
                except:
                    conn.rollback()
        
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}")
        # 不抛出异常，允许其他初始化步骤继续

def test_cache_connection():
    """测试缓存连接"""
    try:
        logger.info("测试缓存连接...")
        
        # 测试设置和获取缓存
        test_key = "forum_init_test"
        test_value = {"message": "Cache connection test", "timestamp": str(os.urandom(8).hex())}
        
        cache_manager.set(test_key, test_value, 60)
        retrieved_value = cache_manager.get(test_key)
        
        if retrieved_value == test_value:
            logger.info("缓存连接测试成功!")
            logger.info(f"缓存后端: {cache_manager.get_stats()['backend']}")
        else:
            logger.warning("缓存连接测试失败，但系统将使用内存缓存")
        
        # 清理测试数据
        cache_manager.delete(test_key)
        
    except Exception as e:
        logger.error(f"缓存连接测试失败: {e}")

def check_file_upload_requirements():
    """检查文件上传所需的依赖"""
    try:
        logger.info("检查文件上传依赖...")
        
        # 检查所需的Python包
        required_packages = {
            'PIL': 'PIL',
            'magic': 'python-magic',
            'boto3': 'boto3',
            'bleach': 'bleach'
        }
        
        missing_packages = []
        for package, package_name in required_packages.items():
            try:
                if package == 'magic':
                    # 特殊处理magic包，因为在Windows上可能有libmagic依赖问题
                    import magic
                    # 尝试实际使用magic
                    magic.Magic()
                else:
                    __import__(package)
                logger.info(f"✓ {package_name} 已安装")
            except ImportError:
                missing_packages.append(package_name)
                logger.warning(f"✗ {package_name} 未安装")
            except Exception as e:
                # magic包可能安装了但缺少libmagic
                if package == 'magic':
                    logger.warning(f"⚠️ {package_name} 已安装但可能缺少libmagic库: {e}")
                    logger.info("  在Windows上可以使用: pip install python-magic-bin")
                else:
                    missing_packages.append(package_name)
                    logger.warning(f"✗ {package_name} 安装有问题: {e}")
        
        if missing_packages:
            logger.warning(f"缺少或有问题的依赖包: {missing_packages}")
            logger.info("请运行: pip install -r requirements.txt")
            logger.info("注意: 缺少的依赖不会阻止核心功能运行")
            return False
        
        logger.info("所有文件上传依赖检查通过!")
        return True
        
    except Exception as e:
        logger.warning(f"依赖检查失败: {e}")
        return False

def verify_oss_configuration():
    """验证OSS配置"""
    try:
        logger.info("验证OSS配置...")
        
        required_env_vars = [
            'S3_ACCESS_KEY_ID',
            'S3_SECRET_ACCESS_KEY', 
            'S3_ENDPOINT_URL',
            'S3_BUCKET_NAME',
            'S3_BASE_URL'
        ]
        
        missing_vars = []
        for var in required_env_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            logger.warning(f"缺少OSS环境变量: {missing_vars}")
            logger.info("请在.env文件中配置OSS相关参数")
            return False
        
        logger.info("OSS配置验证通过!")
        return True
        
    except Exception as e:
        logger.error(f"OSS配置验证失败: {e}")
        return False

def create_upload_directories():
    """创建上传目录"""
    try:
        logger.info("创建本地上传目录...")
        
        upload_dirs = [
            project_root / "uploads" / "temp",
            project_root / "uploads" / "forum",
            project_root / "uploads" / "avatars",
            project_root / "logs"
        ]
        
        for dir_path in upload_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"✓ 目录创建: {dir_path}")
        
        logger.info("上传目录创建完成!")
        
    except Exception as e:
        logger.error(f"创建上传目录失败: {e}")

def init_logging():
    """初始化日志配置"""
    try:
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # 配置文件日志
        log_file = log_dir / "forum_optimization.log"
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        
        # 添加到根日志器
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        
        logger.info("日志配置初始化完成!")
        
    except Exception as e:
        logger.error(f"日志配置初始化失败: {e}")

def generate_config_template():
    """生成配置文件模板"""
    try:
        config_template = """# 论坛优化配置文件模板
# 请将此文件重命名为 .env 并填入实际配置

# 数据库配置
DATABASE_URL=postgresql://username:password@localhost:5432/database_name

# Redis缓存配置（可选，不配置将使用内存缓存）
REDIS_URL=redis://localhost:6379/0

# OSS/S3配置
S3_ACCESS_KEY_ID=your_access_key_id
S3_SECRET_ACCESS_KEY=your_secret_access_key
S3_ENDPOINT_URL=https://oss-cn-hangzhou.aliyuncs.com
S3_BUCKET_NAME=your_bucket_name
S3_BASE_URL=https://your_bucket_name.oss-cn-hangzhou.aliyuncs.com
S3_REGION=oss-cn-hangzhou

# JWT配置
SECRET_KEY=your_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# 其他配置
DEBUG=False
LOG_LEVEL=INFO

# 文件上传限制
MAX_FILE_SIZE=500MB
ALLOWED_FILE_TYPES=images,documents,videos,audio

# 安全配置
ENABLE_RATE_LIMITING=True
ENABLE_CONTENT_MODERATION=True
ENABLE_XSS_PROTECTION=True
"""
        
        env_example_file = project_root / ".env.example"
        with open(env_example_file, 'w', encoding='utf-8') as f:
            f.write(config_template)
        
        logger.info(f"配置文件模板已生成: {env_example_file}")
        
    except Exception as e:
        logger.error(f"生成配置文件模板失败: {e}")

def main():
    """主初始化函数"""
    logger.info("开始论坛优化初始化...")
    
    try:
        # 1. 初始化日志
        init_logging()
        
        # 2. 生成配置文件模板
        generate_config_template()
        
        # 3. 创建必要的目录
        create_upload_directories()
        
        # 4. 检查依赖
        deps_ok = check_file_upload_requirements()
        if not deps_ok:
            logger.warning("依赖检查未通过，但脚本将继续执行核心功能")
        
        # 5. 验证OSS配置
        verify_oss_configuration()
        
        # 6. 测试缓存连接
        test_cache_connection()
        
        # 7. 运行数据库迁移
        run_migration_script()
        
        # 8. 初始化数据库优化
        init_database_optimizations()
        
        logger.info("论坛优化初始化完成!")
        logger.info("请检查上述输出，确保所有组件都正确配置")
        
        # 输出下一步说明
        print("\n" + "="*50)
        print("初始化完成! 下一步操作:")
        print("1. 检查并配置 .env 文件")
        print("2. 确保 Redis 服务正在运行（可选）")
        print("3. 配置 OSS/S3 存储服务")
        print("4. 重启应用程序以加载新配置")
        print("5. 访问 /api/forum/admin/stats 查看系统状态")
        print("="*50)
        
    except Exception as e:
        logger.error(f"初始化过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
