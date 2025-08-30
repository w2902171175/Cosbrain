#!/usr/bin/env python3
"""
生产环境YARA配置管理器
用于解决部署到网站或app时的路径问题
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv


class ProductionYaraConfig:
    """生产环境YARA配置管理器"""
    
    def __init__(self):
        """初始化配置管理器"""
        self.is_production = self._detect_production_environment()
        self.base_path = self._get_base_path()
        self._setup_environment()
    
    def _detect_production_environment(self) -> bool:
        """检测是否为生产环境"""
        # 检测常见的生产环境标识
        production_indicators = [
            os.getenv('PRODUCTION', 'false').lower() == 'true',
            os.getenv('ENVIRONMENT', '').lower() == 'production',
            os.getenv('NODE_ENV', '').lower() == 'production',
            'heroku' in os.getenv('HOME', '').lower(),
            os.getenv('VERCEL', '').lower() in ['1', 'true'],  # 修复VERCEL检测
            '/app' in os.getcwd(),  # Docker容器常见路径
            '/var/www' in os.getcwd(),  # 常见的web服务器路径
        ]
        return any(production_indicators)
    
    def _get_base_path(self) -> Path:
        """获取项目基础路径"""
        if self.is_production:
            # 生产环境：从当前执行文件开始查找项目根目录
            current_path = Path(__file__).resolve()
            
            # 向上查找包含特定文件的目录（如requirements.txt, main.py等）
            for parent in current_path.parents:
                if any([
                    (parent / 'requirements.txt').exists(),
                    (parent / 'main.py').exists(),
                    (parent / 'run_server.py').exists(),
                    (parent / 'project').exists(),
                ]):
                    return parent
            
            # 如果找不到，使用当前工作目录
            return Path.cwd()
        else:
            # 开发环境：智能检测项目根目录
            # 首先尝试从当前文件位置向上查找
            current_path = Path(__file__).resolve()
            for parent in current_path.parents:
                if any([
                    (parent / 'requirements.txt').exists(),
                    (parent / 'run_server.py').exists(),
                    (parent / 'project').exists(),
                ]):
                    return parent
            
            # 然后尝试从当前工作目录向上查找
            current_dir = Path.cwd()
            for parent in [current_dir] + list(current_dir.parents):
                if any([
                    (parent / 'requirements.txt').exists(),
                    (parent / 'run_server.py').exists(),
                    (parent / 'project').exists(),
                ]):
                    return parent
            
            # 最后使用环境变量或当前目录
            return Path(os.getenv('PROJECT_ROOT', Path.cwd()))
    
    def _setup_environment(self):
        """设置环境变量"""
        # 设置YARA相关路径
        yara_config = self.get_yara_config()
        
        for key, value in yara_config.items():
            os.environ[key] = str(value)
    
    def get_yara_config(self) -> Dict[str, Any]:
        """获取YARA配置"""
        config = {
            'ENABLE_YARA_SCAN': 'true',
            'YARA_LOG_LEVEL': 'INFO',
            'YARA_SCAN_TIMEOUT': '30',
            'YARA_MAX_FILE_SIZE': '100',
            'YARA_ALLOWED_EXTENSIONS': '.exe,.dll,.ps1,.bat,.cmd,.py,.js,.vbs,.jar,.zip,.rar',
            'YARA_EXCLUDE_DIRS': 'node_modules,.git,__pycache__,.venv,venv',
        }
        
        # 动态设置路径
        if self.is_production:
            # 生产环境：使用相对于应用根目录的路径
            config.update({
                'YARA_RULES_PATH': str(self.base_path / 'yara' / 'rules' / 'rules.yar'),
                'YARA_OUTPUT_DIR': str(self.base_path / 'yara' / 'output'),
            })
        else:
            # 开发环境：使用现有配置或相对路径
            config.update({
                'YARA_RULES_PATH': os.getenv('YARA_RULES_PATH', str(self.base_path / 'yara' / 'rules' / 'rules.yar')),
                'YARA_OUTPUT_DIR': os.getenv('YARA_OUTPUT_DIR', str(self.base_path / 'yara' / 'output')),
            })
        
        return config
    
    def ensure_directories(self):
        """确保必要的目录存在"""
        config = self.get_yara_config()
        
        # 创建输出目录
        output_dir = Path(config['YARA_OUTPUT_DIR'])
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查规则文件是否存在
        rules_path = Path(config['YARA_RULES_PATH'])
        if not rules_path.exists():
            # 如果规则文件不存在，创建一个基本的规则文件
            self._create_default_rules(rules_path)
    
    def _create_default_rules(self, rules_path: Path):
        """创建默认的YARA规则文件"""
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        
        default_rules = '''/*
YARA Rules for File Security Scanning
生产环境安全扫描规则
*/

rule SuspiciousExecutable
{
    meta:
        description = "检测可疑的可执行文件"
        severity = "medium"
    
    strings:
        $exe_header = { 4D 5A }  // MZ header
        $suspicious1 = "cmd.exe" nocase
        $suspicious2 = "powershell" nocase
        $suspicious3 = "eval(" nocase
        
    condition:
        $exe_header at 0 or any of ($suspicious*)
}

rule SuspiciousScript
{
    meta:
        description = "检测可疑的脚本文件"
        severity = "high"
    
    strings:
        $script1 = "javascript:" nocase
        $script2 = "<script" nocase
        $script3 = "document.write" nocase
        $script4 = "eval(" nocase
        $script5 = "setTimeout(" nocase
        
    condition:
        any of them
}

rule PotentialMalware
{
    meta:
        description = "检测潜在恶意软件特征"
        severity = "critical"
    
    strings:
        $mal1 = "CreateProcess" nocase
        $mal2 = "ShellExecute" nocase
        $mal3 = "WinExec" nocase
        $mal4 = "system(" nocase
        
    condition:
        any of them
}
'''
        
        with open(rules_path, 'w', encoding='utf-8') as f:
            f.write(default_rules)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        config = self.get_yara_config()
        return {
            'environment': 'production' if self.is_production else 'development',
            'base_path': str(self.base_path),
            'yara_rules_path': config['YARA_RULES_PATH'],
            'yara_output_dir': config['YARA_OUTPUT_DIR'],
            'rules_file_exists': Path(config['YARA_RULES_PATH']).exists(),
            'output_dir_exists': Path(config['YARA_OUTPUT_DIR']).exists(),
        }


# 全局配置实例
production_config = ProductionYaraConfig()

def initialize_yara_for_production():
    """初始化生产环境YARA配置"""
    # 使用环境变量检查是否已经初始化过
    if os.getenv('YARA_CONFIG_INITIALIZED') == 'true':
        return True
        
    try:
        production_config.ensure_directories()
        print(f"✅ YARA生产环境配置初始化完成")
        print(f"环境类型: {'生产环境' if production_config.is_production else '开发环境'}")
        print(f"项目根目录: {production_config.base_path}")
        print(f"规则文件: {os.getenv('YARA_RULES_PATH')}")
        print(f"输出目录: {os.getenv('YARA_OUTPUT_DIR')}")
        
        # 设置初始化标志
        os.environ['YARA_CONFIG_INITIALIZED'] = 'true'
        return True
    except Exception as e:
        print(f"❌ YARA配置初始化失败: {e}")
        return False


if __name__ == "__main__":
    # 测试配置
    print("YARA生产环境配置测试")
    print("=" * 50)
    
    summary = production_config.get_config_summary()
    for key, value in summary.items():
        print(f"{key}: {value}")
    
    print("\n初始化测试:")
    initialize_yara_for_production()
