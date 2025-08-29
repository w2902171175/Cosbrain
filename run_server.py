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

if __name__ == "__main__":
    # 启动uvicorn服务器
    uvicorn.run(
        "project.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=[os.path.join(project_root, "project")]
    )
