# project/routers/collections/program_collections.py
"""
类似GitHub星标的项目和课程收藏功能API

提供简化的收藏体验，用户可以像GitHub星标一样快速收藏/取消收藏项目和课程
核心特性：
1. 一键收藏/取消收藏项目和课程
2. 获取用户收藏的项目和课程列表 
3. 检查特定项目/课程的收藏状态
4. 收藏数统计和热门内容推荐
5. 与现有的新一代收藏系统集成
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timezone
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc

# 导入数据库和模型
from project.database import get_db
from project.models import (
    Student, Project, Course, CollectedContent, Folder, 
    ProjectLike, CourseLike, PointTransaction
)
from project.dependencies.dependencies import get_current_user_id
import project.schemas as schemas

router = APIRouter(
    prefix="/program-collections",
    tags=["项目课程收藏（类似GitHub星标）"],
    responses={404: {"description": "Not found"}},
)

# ================== 项目收藏 API ==================

@router.post("/projects/{project_id}/star", summary="收藏项目（类似GitHub星标）")
async def star_project(
    project_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    收藏一个项目，类似GitHub的星标功能
    - 如果已收藏，返回409冲突错误
    - 收藏成功后会在用户的默认收藏文件夹中创建收藏记录
    - 同时会在项目点赞表中创建点赞记录（保持点赞和收藏的一致性）
    """
    try:
        print(f"DEBUG_STAR: 用户 {current_user_id} 尝试收藏项目 ID: {project_id}")
        
        # 1. 验证项目是否存在
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到")
        
        # 2. 检查是否已经收藏过
        existing_collection = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "project",
                CollectedContent.shared_item_id == project_id,
                CollectedContent.status == "active"
            )
        ).first()
        
        if existing_collection:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已经收藏过该项目")
        
        # 3. 获取或创建用户的"我的项目收藏"文件夹
        project_folder = db.query(Folder).filter(
            and_(
                Folder.owner_id == current_user_id,
                Folder.name == "我的项目收藏"
            )
        ).first()
        
        if not project_folder:
            project_folder = Folder(
                owner_id=current_user_id,
                name="我的项目收藏",
                description="自动创建的项目收藏文件夹",
                color="#FF6B6B",
                icon="project"
            )
            db.add(project_folder)
            db.flush()  # 获取文件夹ID
        
        # 4. 创建收藏记录
        collection_item = CollectedContent(
            owner_id=current_user_id,
            folder_id=project_folder.id,
            title=db_project.title,
            type="project",
            shared_item_type="project", 
            shared_item_id=project_id,
            content=db_project.description or "",
            excerpt=db_project.description[:200] if db_project.description else "",
            author=getattr(db_project.creator, 'name', '未知') if db_project.creator else '未知',
            is_starred=True,  # 默认加星标
            status="active"
        )
        db.add(collection_item)
        
        # 5. 检查是否已点赞，如果没有则同时点赞
        existing_like = db.query(ProjectLike).filter(
            and_(
                ProjectLike.owner_id == current_user_id,
                ProjectLike.project_id == project_id
            )
        ).first()
        
        if not existing_like:
            # 创建点赞记录
            project_like = ProjectLike(
                owner_id=current_user_id,
                project_id=project_id
            )
            db.add(project_like)
            
            # 增加项目点赞数
            db_project.likes_count = (db_project.likes_count or 0) + 1
            db.add(db_project)
        
        db.commit()
        db.refresh(collection_item)
        
        print(f"DEBUG_STAR: 用户 {current_user_id} 成功收藏项目 {project_id}")
        return {
            "message": "项目收藏成功",
            "collection_id": collection_item.id,
            "project_id": project_id,
            "project_title": db_project.title,
            "folder_name": project_folder.name,
            "also_liked": not bool(existing_like)  # 是否同时进行了点赞
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR_STAR: 收藏项目失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="收藏项目失败")


@router.delete("/projects/{project_id}/unstar", status_code=status.HTTP_204_NO_CONTENT, summary="取消收藏项目")
async def unstar_project(
    project_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    取消收藏一个项目
    - 会删除收藏记录但保留点赞记录（用户可能想保留点赞但不收藏）
    """
    try:
        print(f"DEBUG_UNSTAR: 用户 {current_user_id} 尝试取消收藏项目 ID: {project_id}")
        
        # 1. 查找收藏记录
        collection_item = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "project",
                CollectedContent.shared_item_id == project_id,
                CollectedContent.status == "active"
            )
        ).first()
        
        if not collection_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该项目的收藏记录")
        
        # 2. 删除收藏记录（软删除）
        collection_item.status = "deleted"
        db.add(collection_item)
        
        db.commit()
        print(f"DEBUG_UNSTAR: 用户 {current_user_id} 成功取消收藏项目 {project_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR_UNSTAR: 取消收藏项目失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取消收藏项目失败")


@router.get("/projects/{project_id}/star-status", summary="检查项目收藏状态")
async def check_project_star_status(
    project_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    检查当前用户是否已收藏指定项目
    """
    try:
        # 验证项目是否存在
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到")
        
        # 检查收藏状态
        is_starred = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "project",
                CollectedContent.shared_item_id == project_id,
                CollectedContent.status == "active"
            )
        ).first() is not None
        
        # 检查点赞状态
        is_liked = db.query(ProjectLike).filter(
            and_(
                ProjectLike.owner_id == current_user_id,
                ProjectLike.project_id == project_id
            )
        ).first() is not None
        
        return {
            "project_id": project_id,
            "project_title": db_project.title,
            "is_starred": is_starred,
            "is_liked": is_liked,
            "total_stars": db.query(CollectedContent).filter(
                and_(
                    CollectedContent.shared_item_type == "project",
                    CollectedContent.shared_item_id == project_id,
                    CollectedContent.status == "active"
                )
            ).count(),
            "total_likes": db_project.likes_count or 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: 检查项目收藏状态失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="检查收藏状态失败")


# ================== 课程收藏 API ==================

@router.post("/courses/{course_id}/star", summary="收藏课程（类似GitHub星标）")
async def star_course(
    course_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    收藏一个课程，类似GitHub的星标功能
    - 如果已收藏，返回409冲突错误
    - 收藏成功后会在用户的默认收藏文件夹中创建收藏记录
    - 同时会在课程点赞表中创建点赞记录（保持点赞和收藏的一致性）
    """
    try:
        print(f"DEBUG_STAR: 用户 {current_user_id} 尝试收藏课程 ID: {course_id}")
        
        # 1. 验证课程是否存在
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if not db_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到")
        
        # 2. 检查是否已经收藏过
        existing_collection = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "course",
                CollectedContent.shared_item_id == course_id,
                CollectedContent.status == "active"
            )
        ).first()
        
        if existing_collection:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已经收藏过该课程")
        
        # 3. 获取或创建用户的"我的课程收藏"文件夹
        course_folder = db.query(Folder).filter(
            and_(
                Folder.owner_id == current_user_id,
                Folder.name == "我的课程收藏"
            )
        ).first()
        
        if not course_folder:
            course_folder = Folder(
                owner_id=current_user_id,
                name="我的课程收藏",
                description="自动创建的课程收藏文件夹",
                color="#4ECDC4",
                icon="course"
            )
            db.add(course_folder)
            db.flush()  # 获取文件夹ID
        
        # 4. 创建收藏记录
        collection_item = CollectedContent(
            owner_id=current_user_id,
            folder_id=course_folder.id,
            title=db_course.title,
            type="course",
            shared_item_type="course",
            shared_item_id=course_id,
            content=db_course.description or "",
            excerpt=db_course.description[:200] if db_course.description else "",
            author=db_course.instructor or "未知讲师",
            is_starred=True,  # 默认加星标
            status="active"
        )
        db.add(collection_item)
        
        # 5. 检查是否已点赞，如果没有则同时点赞
        existing_like = db.query(CourseLike).filter(
            and_(
                CourseLike.owner_id == current_user_id,
                CourseLike.course_id == course_id
            )
        ).first()
        
        if not existing_like:
            # 创建点赞记录
            course_like = CourseLike(
                owner_id=current_user_id,
                course_id=course_id
            )
            db.add(course_like)
            
            # 增加课程点赞数
            db_course.likes_count = (db_course.likes_count or 0) + 1
            db.add(db_course)
        
        db.commit()
        db.refresh(collection_item)
        
        print(f"DEBUG_STAR: 用户 {current_user_id} 成功收藏课程 {course_id}")
        return {
            "message": "课程收藏成功",
            "collection_id": collection_item.id,
            "course_id": course_id,
            "course_title": db_course.title,
            "folder_name": course_folder.name,
            "also_liked": not bool(existing_like)  # 是否同时进行了点赞
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR_STAR: 收藏课程失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="收藏课程失败")


@router.delete("/courses/{course_id}/unstar", status_code=status.HTTP_204_NO_CONTENT, summary="取消收藏课程")
async def unstar_course(
    course_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    取消收藏一个课程
    - 会删除收藏记录但保留点赞记录（用户可能想保留点赞但不收藏）
    """
    try:
        print(f"DEBUG_UNSTAR: 用户 {current_user_id} 尝试取消收藏课程 ID: {course_id}")
        
        # 1. 查找收藏记录
        collection_item = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "course",
                CollectedContent.shared_item_id == course_id,
                CollectedContent.status == "active"
            )
        ).first()
        
        if not collection_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该课程的收藏记录")
        
        # 2. 删除收藏记录（软删除）
        collection_item.status = "deleted"
        db.add(collection_item)
        
        db.commit()
        print(f"DEBUG_UNSTAR: 用户 {current_user_id} 成功取消收藏课程 {course_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR_UNSTAR: 取消收藏课程失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取消收藏课程失败")


@router.get("/courses/{course_id}/star-status", summary="检查课程收藏状态")
async def check_course_star_status(
    course_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    检查当前用户是否已收藏指定课程
    """
    try:
        # 验证课程是否存在
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if not db_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到")
        
        # 检查收藏状态
        is_starred = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "course",
                CollectedContent.shared_item_id == course_id,
                CollectedContent.status == "active"
            )
        ).first() is not None
        
        # 检查点赞状态
        is_liked = db.query(CourseLike).filter(
            and_(
                CourseLike.owner_id == current_user_id,
                CourseLike.course_id == course_id
            )
        ).first() is not None
        
        return {
            "course_id": course_id,
            "course_title": db_course.title,
            "is_starred": is_starred,
            "is_liked": is_liked,
            "total_stars": db.query(CollectedContent).filter(
                and_(
                    CollectedContent.shared_item_type == "course",
                    CollectedContent.shared_item_id == course_id,
                    CollectedContent.status == "active"
                )
            ).count(),
            "total_likes": db_course.likes_count or 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: 检查课程收藏状态失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="检查收藏状态失败")


# ================== 收藏列表查询 API ==================

@router.get("/my-starred-projects", summary="获取我收藏的项目列表")
async def get_my_starred_projects(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    sort_by: Literal["created_at", "title", "updated_at"] = Query("created_at", description="排序字段"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="排序方向")
):
    """
    获取当前用户收藏的项目列表
    """
    try:
        offset = (page - 1) * page_size
        
        # 构建查询
        query = db.query(CollectedContent).options(
            joinedload(CollectedContent.folder)
        ).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "project",
                CollectedContent.status == "active"
            )
        )
        
        # 排序
        if sort_by == "title":
            order_field = CollectedContent.title
        elif sort_by == "updated_at":
            order_field = CollectedContent.updated_at
        else:
            order_field = CollectedContent.created_at
            
        if sort_order == "desc":
            query = query.order_by(desc(order_field))
        else:
            query = query.order_by(order_field)
        
        # 分页
        total = query.count()
        collections = query.offset(offset).limit(page_size).all()
        
        # 获取项目详细信息
        result = []
        for collection in collections:
            project = db.query(Project).filter(Project.id == collection.shared_item_id).first()
            if project:
                # 检查点赞状态
                is_liked = db.query(ProjectLike).filter(
                    and_(
                        ProjectLike.owner_id == current_user_id,
                        ProjectLike.project_id == project.id
                    )
                ).first() is not None
                
                result.append({
                    "collection_id": collection.id,
                    "project_id": project.id,
                    "title": project.title,
                    "description": project.description,
                    "project_type": project.project_type,
                    "project_status": project.project_status,
                    "likes_count": project.likes_count or 0,
                    "is_liked": is_liked,
                    "starred_at": collection.created_at,
                    "folder_name": collection.folder.name if collection.folder else None,
                    "personal_notes": collection.notes
                })
        
        return {
            "projects": result,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size
            }
        }
        
    except Exception as e:
        print(f"ERROR: 获取收藏项目列表失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取收藏列表失败")


@router.get("/my-starred-courses", summary="获取我收藏的课程列表")
async def get_my_starred_courses(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    sort_by: Literal["created_at", "title", "updated_at"] = Query("created_at", description="排序字段"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="排序方向")
):
    """
    获取当前用户收藏的课程列表
    """
    try:
        offset = (page - 1) * page_size
        
        # 构建查询
        query = db.query(CollectedContent).options(
            joinedload(CollectedContent.folder)
        ).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "course",
                CollectedContent.status == "active"
            )
        )
        
        # 排序
        if sort_by == "title":
            order_field = CollectedContent.title
        elif sort_by == "updated_at":
            order_field = CollectedContent.updated_at
        else:
            order_field = CollectedContent.created_at
            
        if sort_order == "desc":
            query = query.order_by(desc(order_field))
        else:
            query = query.order_by(order_field)
        
        # 分页
        total = query.count()
        collections = query.offset(offset).limit(page_size).all()
        
        # 获取课程详细信息
        result = []
        for collection in collections:
            course = db.query(Course).filter(Course.id == collection.shared_item_id).first()
            if course:
                # 检查点赞状态
                is_liked = db.query(CourseLike).filter(
                    and_(
                        CourseLike.owner_id == current_user_id,
                        CourseLike.course_id == course.id
                    )
                ).first() is not None
                
                result.append({
                    "collection_id": collection.id,
                    "course_id": course.id,
                    "title": course.title,
                    "description": course.description,
                    "instructor": course.instructor,
                    "category": course.category,
                    "total_lessons": course.total_lessons,
                    "avg_rating": course.avg_rating,
                    "likes_count": course.likes_count or 0,
                    "is_liked": is_liked,
                    "starred_at": collection.created_at,
                    "folder_name": collection.folder.name if collection.folder else None,
                    "personal_notes": collection.notes
                })
        
        return {
            "courses": result,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size
            }
        }
        
    except Exception as e:
        print(f"ERROR: 获取收藏课程列表失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取收藏列表失败")


# ================== 统计和推荐 API ==================

@router.get("/statistics", summary="获取收藏统计信息")
async def get_collection_statistics(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的收藏统计信息
    """
    try:
        # 统计收藏的项目数量
        starred_projects_count = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "project",
                CollectedContent.status == "active"
            )
        ).count()
        
        # 统计收藏的课程数量
        starred_courses_count = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "course",
                CollectedContent.status == "active"
            )
        ).count()
        
        # 最近收藏的项目（前5个）
        recent_starred_projects = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "project",
                CollectedContent.status == "active"
            )
        ).order_by(desc(CollectedContent.created_at)).limit(5).all()
        
        # 最近收藏的课程（前5个）
        recent_starred_courses = db.query(CollectedContent).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "course",
                CollectedContent.status == "active"
            )
        ).order_by(desc(CollectedContent.created_at)).limit(5).all()
        
        return {
            "starred_projects_count": starred_projects_count,
            "starred_courses_count": starred_courses_count,
            "total_starred": starred_projects_count + starred_courses_count,
            "recent_starred_projects": [
                {
                    "collection_id": item.id,
                    "project_id": item.shared_item_id,
                    "title": item.title,
                    "starred_at": item.created_at
                } for item in recent_starred_projects
            ],
            "recent_starred_courses": [
                {
                    "collection_id": item.id,
                    "course_id": item.shared_item_id,
                    "title": item.title,
                    "starred_at": item.created_at
                } for item in recent_starred_courses
            ]
        }
        
    except Exception as e:
        print(f"ERROR: 获取收藏统计失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取统计信息失败")


@router.get("/popular-projects", summary="获取热门收藏项目")
async def get_popular_starred_projects(
    db: Session = Depends(get_db),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制")
):
    """
    获取平台上收藏次数最多的项目
    """
    try:
        # 统计每个项目的收藏次数
        popular_projects = db.query(
            CollectedContent.shared_item_id,
            func.count(CollectedContent.id).label('star_count')
        ).filter(
            and_(
                CollectedContent.shared_item_type == "project",
                CollectedContent.status == "active"
            )
        ).group_by(CollectedContent.shared_item_id).order_by(
            desc(func.count(CollectedContent.id))
        ).limit(limit).all()
        
        result = []
        for project_id, star_count in popular_projects:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                result.append({
                    "project_id": project.id,
                    "title": project.title,
                    "description": project.description,
                    "project_type": project.project_type,
                    "likes_count": project.likes_count or 0,
                    "star_count": star_count
                })
        
        return {"popular_projects": result}
        
    except Exception as e:
        print(f"ERROR: 获取热门项目失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取热门项目失败")


@router.get("/popular-courses", summary="获取热门收藏课程")
async def get_popular_starred_courses(
    db: Session = Depends(get_db),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制")
):
    """
    获取平台上收藏次数最多的课程
    """
    try:
        # 统计每个课程的收藏次数
        popular_courses = db.query(
            CollectedContent.shared_item_id,
            func.count(CollectedContent.id).label('star_count')
        ).filter(
            and_(
                CollectedContent.shared_item_type == "course",
                CollectedContent.status == "active"
            )
        ).group_by(CollectedContent.shared_item_id).order_by(
            desc(func.count(CollectedContent.id))
        ).limit(limit).all()
        
        result = []
        for course_id, star_count in popular_courses:
            course = db.query(Course).filter(Course.id == course_id).first()
            if course:
                result.append({
                    "course_id": course.id,
                    "title": course.title,
                    "description": course.description,
                    "instructor": course.instructor,
                    "category": course.category,
                    "avg_rating": course.avg_rating,
                    "likes_count": course.likes_count or 0,
                    "star_count": star_count
                })
        
        return {"popular_courses": result}
        
    except Exception as e:
        print(f"ERROR: 获取热门课程失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取热门课程失败")


# ================== 批量操作 API ==================

@router.post("/batch-star", summary="批量收藏项目和课程")
async def batch_star_items(
    items: List[Dict[str, Any]],  # [{"type": "project", "id": 1}, {"type": "course", "id": 2}]
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    批量收藏项目和课程
    请求体格式: [{"type": "project", "id": 1}, {"type": "course", "id": 2}]
    """
    try:
        results = []
        
        for item in items:
            item_type = item.get("type")
            item_id = item.get("id")
            
            if item_type not in ["project", "course"]:
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": False,
                    "message": "无效的类型，只支持 project 或 course"
                })
                continue
            
            try:
                # 检查是否已收藏
                existing = db.query(CollectedContent).filter(
                    and_(
                        CollectedContent.owner_id == current_user_id,
                        CollectedContent.shared_item_type == item_type,
                        CollectedContent.shared_item_id == item_id,
                        CollectedContent.status == "active"
                    )
                ).first()
                
                if existing:
                    results.append({
                        "type": item_type,
                        "id": item_id,
                        "success": False,
                        "message": "已经收藏过"
                    })
                    continue
                
                # 获取对象信息
                if item_type == "project":
                    obj = db.query(Project).filter(Project.id == item_id).first()
                    folder_name = "我的项目收藏"
                    color = "#FF6B6B"
                    icon = "project"
                else:  # course
                    obj = db.query(Course).filter(Course.id == item_id).first()
                    folder_name = "我的课程收藏"
                    color = "#4ECDC4"
                    icon = "course"
                
                if not obj:
                    results.append({
                        "type": item_type,
                        "id": item_id,
                        "success": False,
                        "message": f"{item_type}不存在"
                    })
                    continue
                
                # 获取或创建文件夹
                folder = db.query(Folder).filter(
                    and_(
                        Folder.owner_id == current_user_id,
                        Folder.name == folder_name
                    )
                ).first()
                
                if not folder:
                    folder = Folder(
                        owner_id=current_user_id,
                        name=folder_name,
                        description=f"自动创建的{item_type}收藏文件夹",
                        color=color,
                        icon=icon
                    )
                    db.add(folder)
                    db.flush()
                
                # 创建收藏记录
                collection_item = CollectedContent(
                    owner_id=current_user_id,
                    folder_id=folder.id,
                    title=obj.title,
                    type=item_type,
                    shared_item_type=item_type,
                    shared_item_id=item_id,
                    content=obj.description or "",
                    excerpt=obj.description[:200] if obj.description else "",
                    author=getattr(obj, 'instructor', None) or getattr(obj.creator, 'name', '未知') if hasattr(obj, 'creator') and obj.creator else '未知',
                    is_starred=True,
                    status="active"
                )
                db.add(collection_item)
                
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": True,
                    "message": "收藏成功",
                    "collection_id": collection_item.id
                })
                
            except Exception as e:
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": False,
                    "message": f"收藏失败: {str(e)}"
                })
        
        db.commit()
        
        success_count = len([r for r in results if r["success"]])
        return {
            "total": len(items),
            "success_count": success_count,
            "failed_count": len(items) - success_count,
            "results": results
        }
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: 批量收藏失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="批量收藏失败")


@router.delete("/batch-unstar", summary="批量取消收藏")
async def batch_unstar_items(
    items: List[Dict[str, Any]],  # [{"type": "project", "id": 1}, {"type": "course", "id": 2}]
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    批量取消收藏项目和课程
    请求体格式: [{"type": "project", "id": 1}, {"type": "course", "id": 2}]
    """
    try:
        results = []
        
        for item in items:
            item_type = item.get("type")
            item_id = item.get("id")
            
            if item_type not in ["project", "course"]:
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": False,
                    "message": "无效的类型，只支持 project 或 course"
                })
                continue
            
            try:
                # 查找收藏记录
                collection_item = db.query(CollectedContent).filter(
                    and_(
                        CollectedContent.owner_id == current_user_id,
                        CollectedContent.shared_item_type == item_type,
                        CollectedContent.shared_item_id == item_id,
                        CollectedContent.status == "active"
                    )
                ).first()
                
                if not collection_item:
                    results.append({
                        "type": item_type,
                        "id": item_id,
                        "success": False,
                        "message": "未找到收藏记录"
                    })
                    continue
                
                # 软删除收藏记录
                collection_item.status = "deleted"
                db.add(collection_item)
                
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": True,
                    "message": "取消收藏成功"
                })
                
            except Exception as e:
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": False,
                    "message": f"取消收藏失败: {str(e)}"
                })
        
        db.commit()
        
        success_count = len([r for r in results if r["success"]])
        return {
            "total": len(items),
            "success_count": success_count,
            "failed_count": len(items) - success_count,
            "results": results
        }
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: 批量取消收藏失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="批量取消收藏失败")
