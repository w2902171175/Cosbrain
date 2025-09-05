# project/utils/production_utils.py
"""
生产环境工具集 - 整合版
将所有simple版本的功能整合到一个成熟的生产环境工具包中
"""

import os
import sys
import logging
from typing import Optional
from pathlib import Path

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

logger = logging.getLogger(__name__)

# 配置类
class ProductionConfig:
    """生产环境配置"""
    def __init__(self):
        # 缓存配置
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.enable_redis = os.getenv("ENABLE_REDIS", "true").lower() == "true"
        self.cache_default_expire = int(os.getenv("CACHE_DEFAULT_EXPIRE", "3600"))
        
        # 文件安全配置
        self.max_file_size = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))
        self.enable_virus_scan = os.getenv("ENABLE_VIRUS_SCAN", "false").lower() == "true"
        self.quarantine_path = os.getenv("QUARANTINE_PATH", "/tmp/quarantine")
        
        # 输入安全配置
        self.max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", "50000"))
        self.max_title_length = int(os.getenv("MAX_TITLE_LENGTH", "200"))
        self.enable_ai_detection = os.getenv("ENABLE_AI_DETECTION", "false").lower() == "true"
        
        # 应用配置
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

# 延迟导入和初始化
_cache_manager = None
_input_validator = None
_file_validator = None
_config = None

def _create_simple_cache_manager():
    """创建简单的内存缓存管理器作为降级方案"""
    class SimpleCacheManager:
        def __init__(self):
            self.cache = {}
            self.stats = {"hits": 0, "misses": 0}
        
        def set(self, key: str, value: any, expire: int = 3600) -> bool:
            try:
                self.cache[key] = value
                return True
            except Exception:
                return False
        
        def get(self, key: str) -> any:
            try:
                if key in self.cache:
                    self.stats["hits"] += 1
                    return self.cache[key]
                else:
                    self.stats["misses"] += 1
                    return None
            except Exception:
                return None
        
        def delete(self, key: str) -> bool:
            try:
                if key in self.cache:
                    del self.cache[key]
                    return True
                return False
            except Exception:
                return False
        
        def delete_pattern(self, pattern: str) -> int:
            try:
                import fnmatch
                keys_to_delete = [k for k in self.cache.keys() if fnmatch.fnmatch(k, pattern)]
                for key in keys_to_delete:
                    del self.cache[key]
                return len(keys_to_delete)
            except Exception:
                return 0
        
        def get_stats(self):
            total = self.stats["hits"] + self.stats["misses"]
            hit_rate = (self.stats["hits"] / total * 100) if total > 0 else 0
            return {
                "hits": self.stats["hits"],
                "misses": self.stats["misses"], 
                "hit_rate": f"{hit_rate:.2f}%",
                "backend": "Simple Memory"
            }
        
        def health_check(self):
            return {"status": "healthy", "backend": "Simple Memory Cache"}
    
    return SimpleCacheManager()

def _create_simple_input_validator():
    """创建简单的输入验证器作为降级方案"""
    class SimpleInputValidator:
        def sanitize_html(self, content: str) -> str:
            import html
            return html.escape(content)
        
        def detect_sql_injection(self, text: str) -> tuple:
            import re
            sql_patterns = [
                r'\b(union|select|insert|update|delete|drop)\b',
                r'[\'";]',
                r'--',
                r'/\*.*?\*/'
            ]
            detected = []
            for pattern in sql_patterns:
                if re.search(pattern, text.lower()):
                    detected.append(pattern)
            return len(detected) > 0, detected
    
    return SimpleInputValidator()

def _create_simple_file_validator():
    """创建简单的文件验证器作为降级方案"""
    def simple_file_validator(filename: str, file_content: bytes, content_type: str) -> tuple:
        # 基础文件验证
        if not filename:
            return False, "文件名不能为空", {}
        
        # 检查文件大小 (10MB限制)
        if len(file_content) > 10 * 1024 * 1024:
            return False, "文件过大", {}
        
        # 检查扩展名
        import os
        _, ext = os.path.splitext(filename.lower())
        dangerous_exts = {'.exe', '.bat', '.cmd', '.scr', '.vbs', '.php', '.asp'}
        if ext in dangerous_exts:
            return False, f"不允许的文件类型: {ext}", {}
        
        return True, "文件验证通过", {
            "file_info": {
                "original_filename": filename,
                "secure_filename": filename,
                "file_size": len(file_content),
                "content_type": content_type
            }
        }
    
    return simple_file_validator

def get_config() -> ProductionConfig:
    """获取配置实例"""
    global _config
    if _config is None:
        _config = ProductionConfig()
    return _config

def get_cache_manager():
    """获取缓存管理器"""
    global _cache_manager
    if _cache_manager is None:
        try:
            # 使用增强版缓存管理器
            from ..async_cache.cache_manager import cache_manager
            _cache_manager = cache_manager
            # 延迟记录日志，避免在startup_logger设置前记录
            # logger.info("💾 Cache Manager - 增强版缓存系统已启用")
        except ImportError as e:
            # 创建简单的内存缓存作为降级方案
            logger.warning(f"增强版缓存管理器不可用，使用基础内存缓存: {e}")
            _cache_manager = _create_simple_cache_manager()
    
    return _cache_manager

def get_input_validator():
    """获取输入验证器"""
    global _input_validator
    if _input_validator is None:
        try:
            # 使用增强版输入验证器
            from ..security.input_security import input_validator
            _input_validator = input_validator
            logger.info("使用增强版输入验证器")
        except ImportError as e:
            # 创建基础验证器作为降级方案
            logger.warning(f"增强版输入验证器不可用，使用基础验证器: {e}")
            _input_validator = _create_simple_input_validator()
    
    return _input_validator

def get_file_validator():
    """获取文件验证器"""
    global _file_validator
    if _file_validator is None:
        try:
            # 使用增强版文件验证器
            from ..security.file_security import validate_file_security
            _file_validator = validate_file_security
            logger.info("使用增强版文件验证器")
        except ImportError as e:
            # 创建基础验证器作为降级方案
            logger.warning(f"增强版文件验证器不可用，使用基础验证器: {e}")
            _file_validator = _create_simple_file_validator()
    
    return _file_validator

# 统一接口函数
def cache_set(key: str, value: any, expire: int = None) -> bool:
    """设置缓存"""
    cache_manager = get_cache_manager()
    if expire is None:
        expire = get_config().cache_default_expire
    return cache_manager.set(key, value, expire)

def cache_get(key: str) -> any:
    """获取缓存"""
    cache_manager = get_cache_manager()
    return cache_manager.get(key)

def cache_delete(key: str) -> bool:
    """删除缓存"""
    cache_manager = get_cache_manager()
    return cache_manager.delete(key)

def cache_delete_pattern(pattern: str) -> int:
    """按模式删除缓存"""
    cache_manager = get_cache_manager()
    return cache_manager.delete_pattern(pattern)

def validate_user_input(title: str, content: str, user_id: int) -> tuple:
    """验证用户输入"""
    try:
        # 尝试使用增强版验证
        from ..security.input_security import validate_forum_input
        return validate_forum_input(title, content, user_id, get_cache_manager())
    except ImportError:
        # 使用基础验证作为降级方案
        logger.warning("使用基础输入验证")
        
        # 基础验证逻辑
        if not title or not title.strip():
            return False, "标题不能为空", {}
        
        if not content or not content.strip():
            return False, "内容不能为空", {}
        
        if len(title) > 200:
            return False, "标题过长", {}
        
        if len(content) > 50000:
            return False, "内容过长", {}
        
        # 基础SQL注入检测
        validator = get_input_validator()
        has_injection, patterns = validator.detect_sql_injection(title + " " + content)
        if has_injection:
            return False, "输入包含非法字符", {}
        
        # 清理HTML
        cleaned_content = validator.sanitize_html(content)
        
        return True, "输入验证通过", {
            "cleaned_data": {
                "title": title.strip(),
                "content": cleaned_content
            }
        }

def validate_file_upload(filename: str, file_content: bytes, content_type: str) -> tuple:
    """验证文件上传"""
    file_validator = get_file_validator()
    return file_validator(filename, file_content, content_type)

def sanitize_html(content: str) -> str:
    """清理HTML内容"""
    input_validator = get_input_validator()
    if hasattr(input_validator, 'sanitize_html'):
        return input_validator.sanitize_html(content)
    else:
        # 基础HTML转义
        import html
        return html.escape(content)

def detect_sql_injection(text: str) -> tuple:
    """检测SQL注入"""
    input_validator = get_input_validator()
    if hasattr(input_validator, 'detect_sql_injection'):
        return input_validator.detect_sql_injection(text)
    else:
        # 基础SQL注入检测
        import re
        sql_patterns = [
            r'\b(union|select|insert|update|delete|drop)\b',
            r'[\'";]',
            r'--',
            r'/\*.*?\*/'
        ]
        
        detected = []
        for pattern in sql_patterns:
            if re.search(pattern, text.lower()):
                detected.append(pattern)
        
        return len(detected) > 0, detected

# 论坛特定的缓存功能
class ForumCacheUtils:
    """论坛缓存工具"""
    
    @staticmethod
    def get_hot_topics_key(limit: int = 10) -> str:
        return f"forum:hot_topics:{limit}"
    
    @staticmethod
    def get_user_info_key(user_id: int) -> str:
        return f"user:info:{user_id}"
    
    @staticmethod
    def get_topic_stats_key(topic_id: int) -> str:
        return f"forum:topic:stats:{topic_id}"
    
    @staticmethod
    def invalidate_topic_cache(topic_id: int):
        """删除话题相关缓存"""
        patterns = [
            f"forum:topic:stats:{topic_id}",
            "forum:hot_topics:*",
            f"forum:topic:{topic_id}:*"
        ]
        for pattern in patterns:
            cache_delete_pattern(pattern)
    
    @staticmethod
    def invalidate_user_cache(user_id: int):
        """删除用户相关缓存"""
        patterns = [
            f"user:info:{user_id}",
            f"user:{user_id}:*"
        ]
        for pattern in patterns:
            cache_delete_pattern(pattern)

# 系统监控和健康检查
def system_health_check() -> dict:
    """系统健康检查"""
    health = {
        "status": "healthy",
        "timestamp": time.time(),
        "components": {}
    }
    
    try:
        # 缓存系统检查
        cache_manager = get_cache_manager()
        if hasattr(cache_manager, 'health_check'):
            health["components"]["cache"] = cache_manager.health_check()
        else:
            # 基础缓存测试
            test_key = "health_check_test"
            cache_set(test_key, "test_value", 60)
            if cache_get(test_key) == "test_value":
                health["components"]["cache"] = {"status": "healthy"}
                cache_delete(test_key)
            else:
                health["components"]["cache"] = {"status": "unhealthy", "error": "缓存读写测试失败"}
    except Exception as e:
        health["components"]["cache"] = {"status": "unhealthy", "error": str(e)}
    
    try:
        # 输入验证器检查
        input_validator = get_input_validator()
        health["components"]["input_validator"] = {"status": "healthy", "type": type(input_validator).__name__}
    except Exception as e:
        health["components"]["input_validator"] = {"status": "unhealthy", "error": str(e)}
    
    try:
        # 文件验证器检查
        file_validator = get_file_validator()
        health["components"]["file_validator"] = {"status": "healthy", "type": file_validator.__name__}
    except Exception as e:
        health["components"]["file_validator"] = {"status": "unhealthy", "error": str(e)}
    
    # 判断整体健康状态
    unhealthy_components = [name for name, status in health["components"].items() 
                          if status.get("status") != "healthy"]
    
    if unhealthy_components:
        health["status"] = "degraded" if len(unhealthy_components) < len(health["components"]) else "unhealthy"
        health["unhealthy_components"] = unhealthy_components
    
    return health

def get_system_stats() -> dict:
    """获取系统统计信息"""
    stats = {
        "config": {
            "environment": get_config().environment,
            "debug": get_config().debug,
            "redis_enabled": get_config().enable_redis
        },
        "cache": {},
        "runtime": {
            "python_version": sys.version,
            "process_id": os.getpid()
        }
    }
    
    try:
        cache_manager = get_cache_manager()
        if hasattr(cache_manager, 'get_stats'):
            stats["cache"] = cache_manager.get_stats()
    except Exception as e:
        stats["cache"] = {"error": str(e)}
    
    return stats

# 装饰器
def cache_result(key_prefix: str = "", expire: int = None):
    """缓存结果装饰器"""
    def decorator(func):
        from functools import wraps
        import hashlib
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            args_str = str(args) + str(sorted(kwargs.items()))
            cache_key = f"{key_prefix}:{func.__name__}:{hashlib.md5(args_str.encode()).hexdigest()}"
            
            # 尝试从缓存获取
            cached_result = cache_get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_set(cache_key, result, expire)
            return result
        
        return wrapper
    return decorator

# 初始化日志
import time

def setup_logging():
    """设置日志"""
    config = get_config()
    
    # 确保日志目录存在
    log_dir = Path("logs/production")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 配置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 配置处理器
    handlers = [logging.StreamHandler()]
    
    if config.environment == 'production':
        # 生产环境使用文件日志，支持轮转
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_dir / 'production_utils.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

# 模块初始化
setup_logging()
# 延迟记录初始化日志，将在startup_logger设置后记录

def log_production_utils_initialization():
    """记录Production Utils初始化日志"""
    logger.info("🔧 Production Utils - 生产环境工具包初始化完成")
    # 如果缓存管理器已初始化，也记录其日志
    if _cache_manager is not None:
        logger.info("💾 Cache Manager - 增强版缓存系统已启用")

# 导出的API
__all__ = [
    'get_config',
    'get_cache_manager',
    'cache_manager',  # 添加直接导出
    'ForumCache',
    'get_input_validator', 
    'get_file_validator',
    'cache_set',
    'cache_get',
    'cache_delete',
    'cache_delete_pattern',
    'validate_user_input',
    'validate_file_upload',
    'sanitize_html',
    'detect_sql_injection',
    'ForumCacheUtils',
    'system_health_check',
    'get_system_stats',
    'cache_result'
]

# 创建cache_manager的延迟初始化引用，方便导入
def _get_cache_manager_lazy():
    """延迟获取缓存管理器"""
    return get_cache_manager()

# 延迟初始化的cache_manager
class CacheManagerProxy:
    """缓存管理器代理，实现延迟初始化"""
    def __init__(self):
        self._cache_manager = None
    
    def __getattr__(self, name):
        if self._cache_manager is None:
            self._cache_manager = get_cache_manager()
        return getattr(self._cache_manager, name)

cache_manager = CacheManagerProxy()

# 为向后兼容，创建ForumCache别名
ForumCache = ForumCacheUtils

# 兼容性函数
def get_cache_key(*args, prefix: str = "", **kwargs) -> str:
    """
    生成缓存键
    """
    import hashlib
    key_parts = [str(prefix)] if prefix else []
    key_parts.extend([str(arg) for arg in args])
    key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
    
    key_string = ":".join(key_parts)
    if len(key_string) > 200:  # 如果键太长，使用哈希
        return f"{prefix}:{hashlib.md5(key_string.encode()).hexdigest()}"
    return key_string

def monitor_performance(func_name: str = "", operation: str = ""):
    """
    性能监控装饰器/函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            import time
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(f"Performance: {func_name or func.__name__} took {duration:.3f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"Performance: {func_name or func.__name__} failed after {duration:.3f}s: {e}")
                raise
        return wrapper
    
    # 如果直接调用而不是作为装饰器
    if callable(func_name):
        func = func_name
        func_name = func.__name__
        return decorator(func)
    
    return decorator
