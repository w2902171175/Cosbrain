# project/services/projects_service.py
"""
项目模块服务层 - 业务逻辑分离
基于优化框架为 projects 模块提供高效的服务层实现
"""
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from datetime import datetime
import logging
import json
import uuid
import os

# 模型导入
from project.models import (
    User, Project, ProjectApplication, ProjectMember, 
    ProjectFile, ProjectLike
)
import project.schemas as schemas
import project.oss_utils as oss_utils

# 工具导入
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.async_cache.cache_manager import cache_result, invalidate_cache_pattern
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import get_cache_key, monitor_performance

logger = logging.getLogger(__name__)

class ProjectService:
    """项目核心服务类"""
    
    @staticmethod
    @handle_database_errors
    def get_projects_optimized(
        db: Session, 
        current_user_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> Tuple[List[Project], int]:
        """获取项目列表 - 优化版本"""
        
        # 预加载相关数据以解决 N+1 查询
        query = db.query(Project).options(
            joinedload(Project.creator),
            joinedload(Project.members).joinedload(ProjectMember.user),
            joinedload(Project.applications),
            joinedload(Project.files),
            joinedload(Project.likes)
        ).filter(Project.is_deleted == False)
        
        # 分页查询
        projects = query.offset(skip).limit(limit).all()
        total = query.count()
        
        logger.info(f"获取项目列表：{len(projects)} 个项目（用户 {current_user_id}）")
        return projects, total
    
    @staticmethod
    @handle_database_errors
    def get_project_optimized(
        db: Session, 
        project_id: int, 
        current_user_id: int
    ) -> Project:
        """获取项目详情 - 优化版本"""
        
        project = db.query(Project).options(
            joinedload(Project.creator),
            joinedload(Project.members).joinedload(ProjectMember.user),
            joinedload(Project.applications).joinedload(ProjectApplication.applicant),
            joinedload(Project.files),
            joinedload(Project.likes)
        ).filter(
            Project.id == project_id,
            Project.is_deleted == False
        ).first()
        
        if not project:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="项目不存在"
            )
        
        logger.info(f"获取项目详情：{project_id}（用户 {current_user_id}）")
        return project
    
    @staticmethod
    @handle_database_errors
    def create_project_optimized(
        db: Session,
        project_data: Dict[str, Any],
        current_user_id: int
    ) -> Project:
        """创建项目 - 优化版本"""
        
        # 创建项目实例
        project = Project(
            creator_id=current_user_id,
            title=project_data["title"],
            description=project_data.get("description", ""),
            category=project_data.get("category", "其他"),
            difficulty=project_data.get("difficulty", "中等"),
            required_skills=project_data.get("required_skills", []),
            max_members=project_data.get("max_members", 10),
            cover_image_url=project_data.get("cover_image_url"),
            status="招募中",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(project)
        db.flush()  # 获取ID但不提交
        
        # 创建项目创始人成员记录
        creator_member = ProjectMember(
            project_id=project.id,
            user_id=current_user_id,
            role="项目负责人",
            joined_at=datetime.utcnow()
        )
        db.add(creator_member)
        
        logger.info(f"用户 {current_user_id} 创建项目 {project.id}：{project.title}")
        return project
    
    @staticmethod
    @handle_database_errors
    def update_project_optimized(
        db: Session,
        project_id: int,
        update_data: Dict[str, Any],
        current_user_id: int
    ) -> Project:
        """更新项目 - 优化版本"""
        
        # 获取项目并验证权限
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        # 验证是否为项目创建者
        if project.creator_id != current_user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有项目创建者可以修改项目信息"
            )
        
        # 更新字段
        for field, value in update_data.items():
            if hasattr(project, field) and value is not None:
                setattr(project, field, value)
        
        project.updated_at = datetime.utcnow()
        db.add(project)
        
        logger.info(f"用户 {current_user_id} 更新项目 {project_id}")
        return project
    
    @staticmethod
    @handle_database_errors
    def delete_project_optimized(
        db: Session,
        project_id: int,
        current_user_id: int
    ) -> None:
        """删除项目 - 优化版本"""
        
        # 获取项目并验证权限
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        # 验证是否为项目创建者
        if project.creator_id != current_user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有项目创建者可以删除项目"
            )
        
        # 软删除
        project.is_deleted = True
        project.updated_at = datetime.utcnow()
        db.add(project)
        
        logger.info(f"用户 {current_user_id} 删除项目 {project_id}")
    
    @staticmethod
    @handle_database_errors
    def search_projects_optimized(
        db: Session,
        query: str,
        category: Optional[str] = None,
        difficulty: Optional[str] = None,
        skills: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[Project], int]:
        """搜索项目 - 优化版本"""
        
        # 构建查询
        search_query = db.query(Project).options(
            joinedload(Project.creator),
            joinedload(Project.members),
            joinedload(Project.files)
        ).filter(Project.is_deleted == False)
        
        # 文本搜索
        if query:
            search_query = search_query.filter(
                func.or_(
                    Project.title.ilike(f"%{query}%"),
                    Project.description.ilike(f"%{query}%")
                )
            )
        
        # 分类筛选
        if category:
            search_query = search_query.filter(Project.category == category)
        
        # 难度筛选
        if difficulty:
            search_query = search_query.filter(Project.difficulty == difficulty)
        
        # 技能筛选
        if skills:
            for skill in skills:
                search_query = search_query.filter(
                    Project.required_skills.contains([skill])
                )
        
        # 分页
        projects = search_query.offset(skip).limit(limit).all()
        total = search_query.count()
        
        logger.info(f"搜索项目：查询词'{query}'，找到 {total} 个结果")
        return projects, total

class ProjectApplicationService:
    """项目申请服务类"""
    
    @staticmethod
    @handle_database_errors
    def apply_to_project_optimized(
        db: Session,
        project_id: int,
        application_data: Dict[str, Any],
        current_user_id: int
    ) -> ProjectApplication:
        """申请加入项目 - 优化版本"""
        
        # 验证项目存在
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        # 检查是否已申请
        existing_application = db.query(ProjectApplication).filter(
            ProjectApplication.project_id == project_id,
            ProjectApplication.applicant_id == current_user_id,
            ProjectApplication.status == "pending"
        ).first()
        
        if existing_application:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经申请过该项目，请等待审核"
            )
        
        # 检查是否已是成员
        existing_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user_id
        ).first()
        
        if existing_member:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经是该项目的成员"
            )
        
        # 创建申请
        application = ProjectApplication(
            project_id=project_id,
            applicant_id=current_user_id,
            motivation=application_data.get("motivation", ""),
            skills=application_data.get("skills", []),
            experience=application_data.get("experience", ""),
            contact_info=application_data.get("contact_info", ""),
            status="pending",
            applied_at=datetime.utcnow()
        )
        
        db.add(application)
        db.flush()
        
        logger.info(f"用户 {current_user_id} 申请加入项目 {project_id}")
        return application
    
    @staticmethod
    @handle_database_errors
    def process_application_optimized(
        db: Session,
        application_id: int,
        action: str,
        current_user_id: int
    ) -> ProjectApplication:
        """处理项目申请 - 优化版本"""
        
        # 获取申请
        application = db.query(ProjectApplication).options(
            joinedload(ProjectApplication.project),
            joinedload(ProjectApplication.applicant)
        ).filter(ProjectApplication.id == application_id).first()
        
        if not application:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="申请不存在"
            )
        
        # 验证权限（只有项目创建者可以处理申请）
        if application.project.creator_id != current_user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有项目创建者可以处理申请"
            )
        
        # 验证申请状态
        if application.status != "pending":
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该申请已经被处理过"
            )
        
        # 处理申请
        if action == "accept":
            # 检查项目成员数量限制
            member_count = db.query(ProjectMember).filter(
                ProjectMember.project_id == application.project_id
            ).count()
            
            if member_count >= application.project.max_members:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="项目成员数量已达上限"
                )
            
            # 创建项目成员
            member = ProjectMember(
                project_id=application.project_id,
                user_id=application.applicant_id,
                role="项目成员",
                joined_at=datetime.utcnow()
            )
            db.add(member)
            
            application.status = "accepted"
            logger.info(f"项目申请 {application_id} 被接受")
            
        elif action == "reject":
            application.status = "rejected"
            logger.info(f"项目申请 {application_id} 被拒绝")
        
        application.processed_at = datetime.utcnow()
        db.add(application)
        
        return application
    
    @staticmethod
    @handle_database_errors
    def get_project_applications_optimized(
        db: Session,
        project_id: int,
        current_user_id: int,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[ProjectApplication], int]:
        """获取项目申请列表 - 优化版本"""
        
        # 验证项目权限
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        if project.creator_id != current_user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有项目创建者可以查看申请"
            )
        
        # 构建查询
        query = db.query(ProjectApplication).options(
            joinedload(ProjectApplication.applicant),
            joinedload(ProjectApplication.project)
        ).filter(ProjectApplication.project_id == project_id)
        
        # 状态筛选
        if status_filter:
            query = query.filter(ProjectApplication.status == status_filter)
        
        # 分页
        applications = query.offset(skip).limit(limit).all()
        total = query.count()
        
        logger.info(f"获取项目 {project_id} 的申请列表：{len(applications)} 条")
        return applications, total

class ProjectMemberService:
    """项目成员服务类"""
    
    @staticmethod
    @handle_database_errors
    def get_project_members_optimized(
        db: Session,
        project_id: int,
        current_user_id: int
    ) -> List[ProjectMember]:
        """获取项目成员列表 - 优化版本"""
        
        # 验证项目存在
        ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        # 获取成员列表
        members = db.query(ProjectMember).options(
            joinedload(ProjectMember.user),
            joinedload(ProjectMember.project)
        ).filter(ProjectMember.project_id == project_id).all()
        
        logger.info(f"获取项目 {project_id} 的成员列表：{len(members)} 名成员")
        return members
    
    @staticmethod
    @handle_database_errors
    def remove_member_optimized(
        db: Session,
        project_id: int,
        member_id: int,
        current_user_id: int
    ) -> None:
        """移除项目成员 - 优化版本"""
        
        # 验证项目权限
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        if project.creator_id != current_user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有项目创建者可以移除成员"
            )
        
        # 获取成员记录
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == member_id
        ).first()
        
        if not member:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="成员不存在"
            )
        
        # 不能移除项目创建者
        if member.user_id == project.creator_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能移除项目创建者"
            )
        
        # 删除成员记录
        db.delete(member)
        
        logger.info(f"从项目 {project_id} 移除成员 {member_id}")

class ProjectFileService:
    """项目文件服务类"""
    
    @staticmethod
    @handle_database_errors
    def upload_project_file_optimized(
        db: Session,
        project_id: int,
        file_data: Dict[str, Any],
        current_user_id: int
    ) -> ProjectFile:
        """上传项目文件 - 优化版本"""
        
        # 验证项目权限
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        # 检查是否为项目成员
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user_id
        ).first()
        
        if not member:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有项目成员可以上传文件"
            )
        
        # 创建文件记录
        project_file = ProjectFile(
            project_id=project_id,
            uploader_id=current_user_id,
            filename=file_data["filename"],
            file_url=file_data["file_url"],
            file_type=file_data.get("file_type", ""),
            file_size=file_data.get("file_size", 0),
            description=file_data.get("description", ""),
            uploaded_at=datetime.utcnow()
        )
        
        db.add(project_file)
        db.flush()
        
        logger.info(f"用户 {current_user_id} 向项目 {project_id} 上传文件：{file_data['filename']}")
        return project_file
    
    @staticmethod
    @handle_database_errors
    def delete_project_file_optimized(
        db: Session,
        file_id: int,
        current_user_id: int
    ) -> None:
        """删除项目文件 - 优化版本"""
        
        # 获取文件记录
        project_file = db.query(ProjectFile).options(
            joinedload(ProjectFile.project)
        ).filter(ProjectFile.id == file_id).first()
        
        if not project_file:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件不存在"
            )
        
        # 验证权限（文件上传者或项目创建者）
        if (project_file.uploader_id != current_user_id and 
            project_file.project.creator_id != current_user_id):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有文件上传者或项目创建者可以删除文件"
            )
        
        # 删除文件记录
        db.delete(project_file)
        
        logger.info(f"用户 {current_user_id} 删除项目文件 {file_id}")

class ProjectLikeService:
    """项目点赞服务类"""
    
    @staticmethod
    @handle_database_errors
    def like_project_optimized(
        db: Session,
        project_id: int,
        current_user_id: int
    ) -> ProjectLike:
        """点赞项目 - 优化版本"""
        
        # 验证项目存在
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        # 检查是否已点赞
        existing_like = db.query(ProjectLike).filter(
            ProjectLike.project_id == project_id,
            ProjectLike.owner_id == current_user_id
        ).first()
        
        if existing_like:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经点赞过该项目"
            )
        
        # 创建点赞记录
        like = ProjectLike(
            project_id=project_id,
            owner_id=current_user_id,
            created_at=datetime.utcnow()
        )
        db.add(like)
        
        # 更新项目点赞数
        project.likes_count = (project.likes_count or 0) + 1
        db.add(project)
        
        logger.info(f"用户 {current_user_id} 点赞项目 {project_id}")
        return like
    
    @staticmethod
    @handle_database_errors
    def unlike_project_optimized(
        db: Session,
        project_id: int,
        current_user_id: int
    ) -> None:
        """取消点赞项目 - 优化版本"""
        
        # 验证项目存在
        project = ProjectService.get_project_optimized(db, project_id, current_user_id)
        
        # 查找点赞记录
        like = db.query(ProjectLike).filter(
            ProjectLike.project_id == project_id,
            ProjectLike.owner_id == current_user_id
        ).first()
        
        if not like:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="您尚未点赞该项目"
            )
        
        # 删除点赞记录
        db.delete(like)
        
        # 更新项目点赞数
        if project.likes_count > 0:
            project.likes_count -= 1
            db.add(project)
        
        logger.info(f"用户 {current_user_id} 取消点赞项目 {project_id}")

class ProjectUtils:
    """项目工具类"""
    
    @staticmethod
    def format_project_response(project: Project, current_user_id: int) -> Dict[str, Any]:
        """格式化项目响应数据"""
        
        # 检查用户是否点赞
        user_liked = any(like.owner_id == current_user_id for like in project.likes)
        
        # 检查用户是否为成员
        user_is_member = any(member.user_id == current_user_id for member in project.members)
        
        return {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "category": project.category,
            "difficulty": project.difficulty,
            "required_skills": project.required_skills or [],
            "max_members": project.max_members,
            "current_members": len(project.members),
            "status": project.status,
            "cover_image_url": project.cover_image_url,
            "likes_count": project.likes_count or 0,
            "user_liked": user_liked,
            "user_is_member": user_is_member,
            "creator": {
                "id": project.creator.id,
                "username": project.creator.username,
                "avatar_url": getattr(project.creator, 'avatar_url', None)
            } if project.creator else None,
            "created_at": project.created_at,
            "updated_at": project.updated_at
        }
    
    @staticmethod
    def validate_project_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证项目数据"""
        
        # 验证必填字段
        if not data.get("title", "").strip():
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="项目标题不能为空"
            )
        
        # 验证字段长度
        if len(data.get("title", "")) > 100:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="项目标题长度不能超过100个字符"
            )
        
        if len(data.get("description", "")) > 2000:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="项目描述长度不能超过2000个字符"
            )
        
        # 验证成员数量限制
        max_members = data.get("max_members", 10)
        if not isinstance(max_members, int) or max_members < 1 or max_members > 50:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="最大成员数必须是1-50之间的整数"
            )
        
        return data
    
    @staticmethod
    def get_or_create_user_stats(db: Session, user_id: int) -> Dict[str, Any]:
        """获取或创建用户项目统计"""
        
        # 创建的项目数
        created_count = db.query(Project).filter(
            Project.creator_id == user_id,
            Project.is_deleted == False
        ).count()
        
        # 参与的项目数
        participated_count = db.query(ProjectMember).join(Project).filter(
            ProjectMember.user_id == user_id,
            Project.is_deleted == False
        ).count()
        
        # 申请的项目数
        applied_count = db.query(ProjectApplication).join(Project).filter(
            ProjectApplication.applicant_id == user_id,
            Project.is_deleted == False
        ).count()
        
        return {
            "created_projects": created_count,
            "participated_projects": participated_count,
            "applied_projects": applied_count
        }

logger.info("🚀 Projects Service - 项目服务已加载")
