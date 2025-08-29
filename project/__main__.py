#!/usr/bin/env python3
"""
项目主模块入口点
允许通过 python -m project 来运行应用
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "project.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )
