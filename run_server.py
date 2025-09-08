#!/usr/bin/env python3
"""
服务器启动脚本
使用这个脚本来启动FastAPI应用，避免相对导入问题
"""
import warnings
# 抑制 passlib bcrypt 版本兼容性警告
warnings.filterwarnings("ignore", message=".*error reading bcrypt version.*")
warnings.filterwarnings("ignore", message=".*bcrypt.*", category=UserWarning)

import uvicorn
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 加载.env文件
load_dotenv(os.path.join(project_root, '.env'))

def print_banner():
    """打印启动横幅"""
    print("\n" + "="*80)
    print("🚀 鸿庆书云创新协作平台")
    print("="*80)
    print(f"📅 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 项目根目录: {project_root}")
    print(f"🐍 Python版本: {sys.version.split()[0]}")
    print("="*80)

def print_section_header(title: str):
    """打印章节标题"""
    print(f"\n📋 {title}")
    print("-" * 60)

# 初始化YARA生产环境配置
def initialize_yara():
    """初始化YARA环境"""
    print_section_header("YARA安全扫描系统初始化")
    
    # 检查是否为重载进程：如果存在重载标志或者父进程，则跳过初始化
    if (os.getenv('RUN_MAIN') or 
        os.getenv('YARA_SYSTEM_INITIALIZED') == 'true' or
        hasattr(sys, '_called_from_test')):
        print("   ⏭️  跳过重复初始化")
        return True
        
    try:
        # 添加yara_security脚本目录到路径
        yara_scripts_path = os.path.join(project_root, 'yara_security', 'scripts')
        if yara_scripts_path not in sys.path:
            sys.path.insert(0, yara_scripts_path)
        
        # 动态导入配置模块，避免静态分析错误
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "production_config", 
            os.path.join(yara_scripts_path, "production_config.py")
        )
        production_config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(production_config_module)
        initialize_yara_for_production = production_config_module.initialize_yara_for_production
        
        # 初始化
        success = initialize_yara_for_production()
        
        if success:
            print("   ✅ YARA安全扫描系统已初始化")
            # 设置系统初始化标志
            os.environ['YARA_SYSTEM_INITIALIZED'] = 'true'
            return True
        else:
            print("   ❌ YARA生产环境初始化失败")
            return False
            
    except Exception as e:
        print(f"   ⚠️  YARA初始化失败: {e}")
        print("   📝 应用将继续运行，但文件安全扫描功能可能不可用")
        return False

if __name__ == "__main__":
    # 打印启动横幅
    print_banner()
    
    # 首先初始化YARA
    initialize_yara()
    
    # 打印服务器启动信息
    print_section_header("服务器启动配置")
    print(f"   🌐 服务地址: http://0.0.0.0:8001")
    print(f"   🔄 热重载: 启用")
    print(f"   📂 监控目录: {os.path.join(project_root, 'project')}")
    print("\n" + "="*80)
    print("🚀 正在启动服务器...")
    print("="*80 + "\n")
    
    # 启动uvicorn服务器
    uvicorn.run(
        "project.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=[os.path.join(project_root, "project")]
    )
