# project/routers/projects/projects_optimized.py
"""
项目模块优化版本 - 应用统一优化模式
基于成功优化模式，优化projects模块 (948行 → 优化版本)
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Literal
import logging
import json
import uuid
import os

# 核心依赖
from project.database import get_db
from project.utils import get_current_user_id
import project.schemas as schemas
import project.oss_utils as oss_utils

# 优化工具导入
from project.services.projects_service import (
    ProjectService, ProjectApplicationService, ProjectMemberService, 
    ProjectFileService, ProjectLikeService, ProjectUtils
)
from project.utils.core.error_decorators import database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["项目管理"])

# ===== 项目基础路由 =====

@router.get("", response_model=List[schemas.ProjectResponse], summary="获取所有项目")
@optimized_route("获取项目列表")
async def get_all_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取项目列表 - 优化版本"""
    
    if category or difficulty or status:
        # 如果有筛选条件，使用搜索服务
        projects, total = ProjectService.search_projects_optimized(
            db, query="", category=category, difficulty=difficulty,
            skip=skip, limit=limit
        )
    else:
        # 常规列表查询
        projects, total = ProjectService.get_projects_optimized(
            db, current_user_id, skip, limit
        )
    
    return [ProjectUtils.format_project_response(project, current_user_id) for project in projects]

@router.get("/{project_id}", response_model=schemas.ProjectResponse, summary="获取项目详情")
@optimized_route("获取项目详情")
async def get_project_by_id(
    project_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取项目详情 - 优化版本"""
    
    project = ProjectService.get_project_optimized(db, project_id, current_user_id)
    return ProjectUtils.format_project_response(project, current_user_id)

@router.post("", response_model=schemas.ProjectResponse, summary="创建新项目")
@optimized_route("创建项目")
async def create_project(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    difficulty: str = Form("中等"),
    required_skills: str = Form("[]"),
    max_members: int = Form(10),
    cover_image: Optional[UploadFile] = File(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建项目 - 优化版本"""
    
    # 解析技能列表
    try:
        skills_list = json.loads(required_skills) if required_skills else []
    except json.JSONDecodeError:
        skills_list = [skill.strip() for skill in required_skills.split(",") if skill.strip()]
    
    # 处理封面图片
    cover_image_url = None
    if cover_image and cover_image.filename:
        # 验证文件类型
        if not cover_image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="封面必须是图片文件"
            )
        
        # 生成文件名并上传
        file_extension = os.path.splitext(cover_image.filename)[1]
        oss_object_name = f"project-covers/{uuid.uuid4().hex}{file_extension}"
        
        try:
            file_bytes = await cover_image.read()
            cover_image_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=oss_object_name,
                content_type=cover_image.content_type
            )
        except Exception as e:
            logger.error(f"上传封面失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="封面上传失败"
            )
    
    # 准备项目数据
    project_data = ProjectUtils.validate_project_data({
        "title": title,
        "description": description,
        "category": category,
        "difficulty": difficulty,
        "required_skills": skills_list,
        "max_members": max_members,
        "cover_image_url": cover_image_url
    })
    
    # 使用事务创建项目
    with database_transaction(db):
        project = ProjectService.create_project_optimized(db, project_data, current_user_id)
        
        # 异步处理项目创建后任务
        submit_background_task(
            background_tasks,
            "process_new_project",
            {
                "project_id": project.id,
                "creator_id": current_user_id,
                "category": category
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"用户 {current_user_id} 创建项目 {project.id}: {title}")
    return ProjectUtils.format_project_response(project, current_user_id)

@router.put("/{project_id}", response_model=schemas.ProjectResponse, summary="更新项目信息")
@optimized_route("更新项目")
async def update_project(
    project_id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    difficulty: Optional[str] = Form(None),
    required_skills: Optional[str] = Form(None),
    max_members: Optional[int] = Form(None),
    status: Optional[str] = Form(None),
    cover_image: Optional[UploadFile] = File(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新项目信息 - 优化版本"""
    
    # 准备更新数据
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if description is not None:
        update_data["description"] = description
    if category is not None:
        update_data["category"] = category
    if difficulty is not None:
        update_data["difficulty"] = difficulty
    if max_members is not None:
        update_data["max_members"] = max_members
    if status is not None:
        update_data["status"] = status
    
    # 处理技能列表
    if required_skills is not None:
        try:
            skills_list = json.loads(required_skills) if required_skills else []
        except json.JSONDecodeError:
            skills_list = [skill.strip() for skill in required_skills.split(",") if skill.strip()]
        update_data["required_skills"] = skills_list
    
    # 处理新封面图片
    if cover_image and cover_image.filename:
        if not cover_image.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="封面必须是图片文件"
            )
        
        # 上传新封面
        file_extension = os.path.splitext(cover_image.filename)[1]
        oss_object_name = f"project-covers/{uuid.uuid4().hex}{file_extension}"
        
        try:
            file_bytes = await cover_image.read()
            cover_image_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=oss_object_name,
                content_type=cover_image.content_type
            )
            update_data["cover_image_url"] = cover_image_url
        except Exception as e:
            logger.error(f"更新封面失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="封面更新失败"
            )
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个要更新的字段"
        )
    
    # 验证更新数据
    ProjectUtils.validate_project_data(update_data)
    
    # 使用事务更新
    with database_transaction(db):
        project = ProjectService.update_project_optimized(
            db, project_id, update_data, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 更新项目 {project_id}")
    return ProjectUtils.format_project_response(project, current_user_id)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除项目")
@optimized_route("删除项目")
async def delete_project(
    project_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除项目 - 优化版本"""
    
    with database_transaction(db):
        ProjectService.delete_project_optimized(db, project_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 删除项目 {project_id}")

# ===== 项目申请路由 =====

@router.post("/{project_id}/apply", response_model=schemas.ProjectApplicationResponse, summary="申请加入项目")
@optimized_route("申请加入项目")
async def apply_to_project(
    project_id: int,
    background_tasks: BackgroundTasks,
    motivation: str = Form(...),
    skills: str = Form("[]"),
    experience: str = Form(""),
    contact_info: str = Form(""),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """申请加入项目 - 优化版本"""
    
    # 解析技能列表
    try:
        skills_list = json.loads(skills) if skills else []
    except json.JSONDecodeError:
        skills_list = [skill.strip() for skill in skills.split(",") if skill.strip()]
    
    # 准备申请数据
    application_data = {
        "motivation": motivation,
        "skills": skills_list,
        "experience": experience,
        "contact_info": contact_info
    }
    
    # 使用事务创建申请
    with database_transaction(db):
        application = ProjectApplicationService.apply_to_project_optimized(
            db, project_id, application_data, current_user_id
        )
        
        # 异步通知项目创建者
        submit_background_task(
            background_tasks,
            "notify_project_application",
            {
                "application_id": application.id,
                "project_id": project_id,
                "applicant_id": current_user_id
            },
            priority=TaskPriority.HIGH
        )
    
    logger.info(f"用户 {current_user_id} 申请加入项目 {project_id}")
    return application

@router.get("/{project_id}/applications", response_model=List[schemas.ProjectApplicationResponse], summary="获取项目申请列表")
@optimized_route("获取项目申请")
async def get_project_applications(
    project_id: int,
    status_filter: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取项目申请列表 - 优化版本"""
    
    applications, total = ProjectApplicationService.get_project_applications_optimized(
        db, project_id, current_user_id, status_filter, skip, limit
    )
    
    return applications

@router.put("/applications/{application_id}/{action}", response_model=schemas.ProjectApplicationResponse, summary="处理项目申请")
@optimized_route("处理项目申请")
async def process_project_application(
    application_id: int,
    action: Literal["accept", "reject"],
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """处理项目申请 - 优化版本"""
    
    with database_transaction(db):
        application = ProjectApplicationService.process_application_optimized(
            db, application_id, action, current_user_id
        )
        
        # 异步通知申请者
        submit_background_task(
            background_tasks,
            "notify_application_result",
            {
                "application_id": application_id,
                "action": action,
                "applicant_id": application.applicant_id,
                "project_id": application.project_id
            },
            priority=TaskPriority.HIGH
        )
    
    logger.info(f"申请 {application_id} 被{action}")
    return application

# ===== 项目成员路由 =====

@router.get("/{project_id}/members", response_model=List[schemas.ProjectMemberResponse], summary="获取项目成员列表")
@optimized_route("获取项目成员")
async def get_project_members(
    project_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取项目成员列表 - 优化版本"""
    
    members = ProjectMemberService.get_project_members_optimized(
        db, project_id, current_user_id
    )
    
    return members

@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT, summary="移除项目成员")
@optimized_route("移除项目成员")
async def remove_project_member(
    project_id: int,
    member_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """移除项目成员 - 优化版本"""
    
    with database_transaction(db):
        ProjectMemberService.remove_member_optimized(
            db, project_id, member_id, current_user_id
        )
        
        # 异步通知被移除的成员
        submit_background_task(
            background_tasks,
            "notify_member_removed",
            {
                "project_id": project_id,
                "removed_member_id": member_id,
                "removed_by_id": current_user_id
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"从项目 {project_id} 移除成员 {member_id}")

# ===== 项目文件路由 =====

@router.post("/{project_id}/files", response_model=schemas.ProjectFileResponse, summary="上传项目文件")
@optimized_route("上传项目文件")
async def upload_project_file(
    project_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: str = Form(""),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """上传项目文件 - 优化版本"""
    
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择要上传的文件"
        )
    
    # 验证文件大小（最大50MB）
    max_size = 50 * 1024 * 1024
    if file.size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件大小不能超过50MB"
        )
    
    # 生成文件名并上传
    file_extension = os.path.splitext(file.filename)[1]
    oss_object_name = f"project-files/{project_id}/{uuid.uuid4().hex}{file_extension}"
    
    try:
        file_bytes = await file.read()
        file_url = await oss_utils.upload_file_to_oss(
            file_bytes=file_bytes,
            object_name=oss_object_name,
            content_type=file.content_type
        )
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文件上传失败"
        )
    
    # 准备文件数据
    file_data = {
        "filename": file.filename,
        "file_url": file_url,
        "file_type": file.content_type,
        "file_size": file.size,
        "description": description
    }
    
    # 使用事务创建文件记录
    with database_transaction(db):
        project_file = ProjectFileService.upload_project_file_optimized(
            db, project_id, file_data, current_user_id
        )
        
        # 异步处理文件
        submit_background_task(
            background_tasks,
            "process_project_file",
            {
                "file_id": project_file.id,
                "project_id": project_id,
                "file_type": file.content_type
            },
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 向项目 {project_id} 上传文件: {file.filename}")
    return project_file

@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除项目文件")
@optimized_route("删除项目文件")
async def delete_project_file(
    file_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除项目文件 - 优化版本"""
    
    with database_transaction(db):
        ProjectFileService.delete_project_file_optimized(
            db, file_id, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 删除项目文件 {file_id}")

# ===== 项目点赞路由 =====

@router.post("/{project_id}/like", response_model=schemas.ProjectLikeResponse, summary="点赞项目")
@optimized_route("点赞项目")
async def like_project(
    project_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """点赞项目 - 优化版本"""
    
    with database_transaction(db):
        like = ProjectLikeService.like_project_optimized(
            db, project_id, current_user_id
        )
        
        # 异步通知项目创建者
        submit_background_task(
            background_tasks,
            "notify_project_liked",
            {
                "project_id": project_id,
                "liker_id": current_user_id
            },
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 点赞项目 {project_id}")
    return like

@router.delete("/{project_id}/unlike", status_code=status.HTTP_204_NO_CONTENT, summary="取消点赞项目")
@optimized_route("取消点赞项目")
async def unlike_project(
    project_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """取消点赞项目 - 优化版本"""
    
    with database_transaction(db):
        ProjectLikeService.unlike_project_optimized(
            db, project_id, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 取消点赞项目 {project_id}")

# ===== 搜索和统计路由 =====

@router.get("/search", response_model=List[schemas.ProjectResponse], summary="搜索项目")
@optimized_route("搜索项目")
async def search_projects(
    background_tasks: BackgroundTasks,
    q: str = Query(..., min_length=2, description="搜索关键词"),
    category: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    skills: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """搜索项目 - 优化版本"""
    
    # 解析技能列表
    skills_list = None
    if skills:
        try:
            skills_list = json.loads(skills) if skills else None
        except json.JSONDecodeError:
            skills_list = [skill.strip() for skill in skills.split(",") if skill.strip()]
    
    # 执行搜索
    projects, total = ProjectService.search_projects_optimized(
        db, q, category, difficulty, skills_list, skip, limit
    )
    
    # 异步记录搜索日志
    submit_background_task(
        background_tasks,
        "log_project_search",
        {
            "user_id": current_user_id,
            "query": q,
            "category": category,
            "difficulty": difficulty,
            "skills": skills_list,
            "result_count": total
        },
        priority=TaskPriority.LOW
    )
    
    logger.info(f"用户 {current_user_id} 搜索项目: {q}，找到 {total} 个结果")
    return [ProjectUtils.format_project_response(project, current_user_id) for project in projects]

@router.get("/stats", response_model=schemas.ProjectStatsResponse, summary="获取项目统计信息")
@optimized_route("项目统计")
async def get_project_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取项目统计信息 - 优化版本"""
    
    stats = ProjectUtils.get_or_create_user_stats(db, current_user_id)
    return stats

# 使用路由优化器应用批量优化
# router_optimizer.apply_batch_optimizations(router, {
#     "cache_ttl": 300,
#     "enable_compression": True,
#     "rate_limit": "100/minute",
#     "monitoring": True
# })

logger.info("📁 Projects Router - 项目路由已加载")
