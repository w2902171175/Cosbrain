# project/main.py

# === 标准库导入 ===
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

# === 第三方库导入 ===
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

# === 项目内部导入 ===
# 核心模块
from project.database import get_db
from project.dependencies.dependencies import (
    SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token, get_current_user_id, verify_password, get_password_hash, is_admin_user
)
from project.utils.utils import _award_points, _check_and_award_achievements, _get_text_part

# 数据模型
from project.models import (
    Student, Project, UserCourse, ForumTopic, ForumComment, ForumLike, 
    ChatMessage, Achievement, UserAchievement, PointTransaction
)

# 路由模块
from project.routers import (
    admin, projects, dashboard, course_notes, quick_notes, auth, achievement_points, 
    tts, llm, mcp, search_engine, courses, knowledge, forum, chatrooms, ai, recommend,
    ai_admin_router, ai_monitoring_router
)
# 导入收藏系统模块
from project.routers.collections import router as collections_router

# 加载环境变量
load_dotenv()

# === FastAPI 应用实例 ===
app = FastAPI(
    title="鸿庆书云创新协作平台后端API",
    description="为学生提供智能匹配、知识管理、课程学习和协作支持的综合平台。",
    version="0.1.0",
)

# === CORS 中间件配置 ===
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost:5173",
    # 添加前端域名和端口
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 路由器注册 ===
app.include_router(auth)
app.include_router(admin)
app.include_router(projects)
app.include_router(course_notes)
app.include_router(dashboard)
app.include_router(quick_notes)
app.include_router(achievement_points)
app.include_router(tts)
app.include_router(llm)
app.include_router(mcp)
app.include_router(search_engine)
app.include_router(courses)
app.include_router(knowledge)
app.include_router(forum)
app.include_router(chatrooms)
# 收藏系统 - 基于文件夹的新架构（统一路由）
app.include_router(collections_router)  # 新一代收藏管理系统
app.include_router(ai)
app.include_router(ai_admin_router)  # AI管理路由
app.include_router(ai_monitoring_router)  # AI监控路由
app.include_router(recommend)

# === 认证配置 ===
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")  # 指向登录接口的URL
bearer_scheme = HTTPBearer(auto_error=False)
