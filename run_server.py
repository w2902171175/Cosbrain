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

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 初始化YARA生产环境配置
def initialize_yara():
    """初始化YARA环境"""
    # 检查是否为重载进程：如果存在重载标志或者父进程，则跳过初始化
    if (os.getenv('RUN_MAIN') or 
        os.getenv('YARA_SYSTEM_INITIALIZED') == 'true' or
        hasattr(sys, '_called_from_test')):
        return True
        
    try:
        # 添加yara脚本目录到路径
        yara_scripts_path = os.path.join(project_root, 'yara', 'scripts')
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
            print("✅ YARA安全扫描系统已初始化")
            # 设置系统初始化标志
            os.environ['YARA_SYSTEM_INITIALIZED'] = 'true'
            return True
        else:
            print("❌ YARA生产环境初始化失败")
            return False
            
    except Exception as e:
        print(f"⚠️ YARA初始化失败: {e}")
        print("应用将继续运行，但文件安全扫描功能可能不可用")
        return False

if __name__ == "__main__":
    # 首先初始化YARA
    initialize_yara()
    
    # 启动uvicorn服务器
    uvicorn.run(
        "project.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=[os.path.join(project_root, "project")]
    )
