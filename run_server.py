#!/usr/bin/env python3
"""
服务器启动脚本
使用这个脚本来启动FastAPI应用，避免相对导入问题
"""
import uvicorn
import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 初始化YARA生产环境配置
def initialize_yara():
    """初始化YARA环境"""
    try:
        # 添加yara脚本目录到路径
        yara_scripts_path = os.path.join(project_root, 'yara', 'scripts')
        sys.path.insert(0, yara_scripts_path)
        
        # 导入配置模块
        from production_config import initialize_yara_for_production
        
        # 初始化
        success = initialize_yara_for_production()
        
        if success:
            print("✅ YARA安全扫描系统已初始化")
            return True
        else:
            print("❌ YARA生产环境初始化失败")
            return False
            
    except Exception as e:
        print(f"⚠️ YARA初始化失败: {e}")
        print("应用将继续运行，但文件安全扫描功能可能不可用")
        return False

# 执行YARA初始化
initialize_yara()

if __name__ == "__main__":
    # 启动uvicorn服务器
    uvicorn.run(
        "project.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=[os.path.join(project_root, "project")]
    )
