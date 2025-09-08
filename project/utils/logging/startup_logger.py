# project/utils/startup_logger.py
"""
启动日志格式化器
用于优化应用启动时的日志输出，使其更加整齐有条理
"""

import logging
import sys
from typing import Dict, Any
from datetime import datetime


class StartupFormatter(logging.Formatter):
    """自定义启动日志格式化器"""
    
    # 颜色代码
    COLORS = {
        'RESET': '\033[0m',
        'RED': '\033[31m',
        'GREEN': '\033[32m',
        'YELLOW': '\033[33m',
        'BLUE': '\033[34m',
        'MAGENTA': '\033[35m',
        'CYAN': '\033[36m',
        'WHITE': '\033[37m',
        'BRIGHT_RED': '\033[91m',
        'BRIGHT_GREEN': '\033[92m',
        'BRIGHT_YELLOW': '\033[93m',
        'BRIGHT_BLUE': '\033[94m',
        'BRIGHT_MAGENTA': '\033[95m',
        'BRIGHT_CYAN': '\033[96m'
    }
    
    # 日志级别对应的emoji和颜色
    LEVEL_STYLES = {
        'DEBUG': ('🔍', 'CYAN'),
        'INFO': ('ℹ️', 'GREEN'),
        'WARNING': ('⚠️', 'YELLOW'),
        'ERROR': ('❌', 'RED'),
        'CRITICAL': ('🚨', 'BRIGHT_RED')
    }
    
    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 修复record.name中的拼写错误
        if hasattr(record, 'name'):
            record.name = record.name.replace('production_utills', 'production_utils')
            record.name = record.name.replace('coourse_notes', 'course_notes')  
            record.name = record.name.replace('quicck_notes', 'quick_notes')
            record.name = record.name.replace('program__collections', 'program_collections')
            record.name = record.name.replace('security_scaanner', 'security_scanner')
        
        # 获取级别样式
        emoji, color = self.LEVEL_STYLES.get(record.levelname, ('📝', 'WHITE'))
        
        # 格式化时间
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # 简化模块名
        module_name = self._simplify_module_name(record.name)
        
        # 构建消息
        if self.use_colors:
            color_code = self.COLORS.get(color, '')
            reset_code = self.COLORS['RESET']
            formatted_msg = f"   {emoji} {color_code}{record.getMessage()}{reset_code}"
        else:
            formatted_msg = f"   {emoji} {record.getMessage()}"
        
        # 添加模块信息（如果不是根级别日志）
        if module_name and module_name != 'root':
            formatted_msg += f" [{module_name}]"
        
        return formatted_msg
    
    def _simplify_module_name(self, name: str) -> str:
        """简化模块名称"""
        # 修复常见的拼写错误
        name = name.replace('production_utills', 'production_utils')
        name = name.replace('coourse_notes', 'course_notes')  
        name = name.replace('quicck_notes', 'quick_notes')
        name = name.replace('program__collections', 'program_collections')
        name = name.replace('security_scaanner', 'security_scanner')
        
        # 移除常见的前缀
        prefixes_to_remove = [
            'project.routers.',
            'project.utils.',
            'project.services.',
            'project.',
            'uvicorn.',
            'fastapi.'
        ]
        
        simplified = name
        for prefix in prefixes_to_remove:
            if simplified.startswith(prefix):
                simplified = simplified[len(prefix):]
                break
        
        # 进一步简化
        parts = simplified.split('.')
        if len(parts) > 2:
            simplified = f"{parts[0]}...{parts[-1]}"
        
        return simplified


class StartupLoggerManager:
    """启动日志管理器"""
    
    def __init__(self):
        self.original_formatters = {}
        self.startup_formatter = StartupFormatter()
        self.is_setup = False
    
    def setup_startup_logging(self):
        """设置启动时的日志格式"""
        if self.is_setup:
            return
        
        # 获取根日志器
        root_logger = logging.getLogger()
        
        # 保存原始格式化器并应用新的
        for handler in root_logger.handlers:
            if hasattr(handler, 'formatter'):
                self.original_formatters[handler] = handler.formatter
                handler.setFormatter(self.startup_formatter)
        
        # 设置特定logger的级别
        startup_loggers = [
            'project.routers.llm.distributed_cache',
            'project.routers.llm.prometheus_monitor',
            'project.routers.knowledge.knowledge',
            'project.utils.production_utils',
            'project.utils.file_security',
            'project.ai_providers',
            'project.utils.optimization.production_utils'
        ]
        
        for logger_name in startup_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
        
        self.is_setup = True
    
    def restore_original_logging(self):
        """恢复原始日志格式"""
        if not self.is_setup:
            return
        
        # 恢复原始格式化器
        for handler, original_formatter in self.original_formatters.items():
            handler.setFormatter(original_formatter)
        
        self.original_formatters.clear()
        self.is_setup = False
    
    def print_startup_summary(self):
        """打印启动总结"""
        pass


# 全局实例
startup_logger_manager = StartupLoggerManager()


def setup_startup_logging():
    """设置启动日志"""
    startup_logger_manager.setup_startup_logging()


def restore_logging():
    """恢复正常日志"""
    startup_logger_manager.restore_original_logging()


def print_startup_summary():
    """打印启动总结"""
    startup_logger_manager.print_startup_summary()
