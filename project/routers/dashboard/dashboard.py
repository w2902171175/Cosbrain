# project/routers/dashboard/dashboard.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
import json

# 导入数据库和模型
from project.database import get_db
from project.models import (
    Student, Project, Course, UserCourse, ChatRoom, ProjectMember
)
from project.dependencies import get_current_user_id
from sqlalchemy import or_
import project.schemas as schemas

router = APIRouter(
    prefix="/dashboard",
    tags=["仪表板"]
)


@router.get("/summary", response_model=schemas.DashboardSummaryResponse, summary="获取首页工作台概览数据")
async def get_dashboard_summary(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    try:
        print(f"DEBUG: 获取用户 {current_user_id} 的仪表板概览数据。")
        # 项目数量
        total_projects = db.query(Project).count()
        active_projects_count = db.query(Project).filter(Project.project_status == "进行中").count()
        completed_projects_count = db.query(Project).filter(Project.project_status == "已完成").count()

        # 课程数量 (仅统计用户参与的课程，优化查询)
        learning_courses_count = db.query(UserCourse).filter(
            UserCourse.student_id == current_user_id,
            UserCourse.status == "in_progress"
        ).count()
        completed_courses_count = db.query(UserCourse).filter(
            UserCourse.student_id == current_user_id,
            UserCourse.status == "completed"
        ).count()

        # 聊天室和未读消息（简化）
        active_chats_count = db.query(ChatRoom).filter(ChatRoom.creator_id == current_user_id).count()  # 假设用户活跃的聊天室是他创建的
        unread_messages_count = 0  # 暂时为0，待实现实时消息和未读计数

        # 简历完成度 (模拟，可根据实际用户资料填写程度计算)
        student = db.query(Student).filter(Student.id == current_user_id).first()
        resume_completion_percentage = 0.0
        if student:
            completed_fields = 0
            total_fields = 10  # 假设 10 个关键字段
            
            # 安全检查每个字段
            if getattr(student, 'name', None) and student.name != "张三": 
                completed_fields += 1
            if getattr(student, 'major', None): 
                completed_fields += 1
            if getattr(student, 'skills', None): 
                completed_fields += 1
            if getattr(student, 'interests', None): 
                completed_fields += 1
            if getattr(student, 'bio', None): 
                completed_fields += 1
            if getattr(student, 'awards_competitions', None): 
                completed_fields += 1
            if getattr(student, 'academic_achievements', None): 
                completed_fields += 1
            if getattr(student, 'soft_skills', None): 
                completed_fields += 1
            if getattr(student, 'portfolio_link', None): 
                completed_fields += 1
            if getattr(student, 'preferred_role', None): 
                completed_fields += 1
            if getattr(student, 'availability', None): 
                completed_fields += 1
            
            resume_completion_percentage = (completed_fields / total_fields) * 100 if total_fields > 0 else 0

        return schemas.DashboardSummaryResponse(
            active_projects_count=active_projects_count,
            completed_projects_count=completed_projects_count,
            learning_courses_count=learning_courses_count,
            completed_courses_count=completed_courses_count,
            active_chats_count=active_chats_count,
            unread_messages_count=unread_messages_count,
            resume_completion_percentage=round(resume_completion_percentage, 2)
        )
    except Exception as e:
        print(f"ERROR: 获取仪表板概览数据失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取仪表板概览数据失败"
        )


@router.get("/projects", response_model=List[schemas.DashboardProjectCard],
         summary="获取当前用户参与的项目卡片列表")
async def get_dashboard_projects(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[str] = None
):
    """
    获取当前用户参与的（作为创建者或成员）项目卡片列表。
    可选择通过 `status_filter` (例如 "进行中", "已完成") 筛选项目。
    """
    try:
        print(f"DEBUG: 获取用户 {current_user_id} 参与的仪表板项目列表。")

        # 验证状态过滤器
        valid_statuses = ["进行中", "已完成", "待开始", "已暂停"]
        if status_filter and status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的状态过滤器。有效值: {', '.join(valid_statuses)}"
            )

        # 查询条件：用户是项目的创建者 或者 用户是项目的成员
        # 方法1：用户是项目创建者
        creator_projects = db.query(Project).filter(Project.creator_id == current_user_id)
        
        # 方法2：用户是项目成员
        member_projects = db.query(Project).join(ProjectMember).filter(
            ProjectMember.student_id == current_user_id
        )
        
        # 合并两个查询结果，使用 union 避免重复
        query = creator_projects.union(member_projects)

        if status_filter:
            query = query.filter(Project.project_status == status_filter)

        # 排序，例如按创建时间或更新时间
        projects = query.order_by(Project.created_at.desc()).all()

        project_cards = []
        for p in projects:
            # 这里模拟进度。如果项目状态是"进行中"，可以给一个默认的进行中进度（例如 0.5）。
            # 如果是"已完成"，则为 1.0 (100%)。其他状态（如"待开始"）为 0.0。
            progress = 0.0
            if p.project_status == "进行中":
                progress = 0.5  # 默认进行中进度
            elif p.project_status == "已完成":
                progress = 1.0  # 完成项目进度

            project_cards.append(schemas.DashboardProjectCard(
                id=p.id,
                title=p.title,
                progress=progress
            ))

        print(f"DEBUG: 获取到用户 {current_user_id} 参与的 {len(project_cards)} 个项目卡片。")
        return project_cards
    
    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        print(f"ERROR: 获取用户项目列表失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取项目列表失败"
        )


@router.get("/courses", response_model=List[schemas.DashboardCourseCard],
         summary="获取当前用户学习的课程卡片列表")
async def get_dashboard_courses(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[str] = None
):
    """
    获取当前用户学习的课程卡片列表。
    可选择通过 `status_filter` (例如 "in_progress", "completed") 筛选课程。
    """
    try:
        print(f"DEBUG: 获取用户 {current_user_id} 的仪表板课程列表。")

        # 验证状态过滤器
        valid_statuses = ["in_progress", "completed", "not_started"]
        if status_filter and status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的状态过滤器。有效值: {', '.join(valid_statuses)}"
            )

        # 优化查询：使用 joinedload 预加载关联的 Course 对象，避免 N+1 查询问题
        query = db.query(UserCourse).options(joinedload(UserCourse.course)).filter(UserCourse.student_id == current_user_id)

        if status_filter:
            query = query.filter(UserCourse.status == status_filter)

        user_courses = query.all()

        course_cards = []
        for uc in user_courses:
            # 确保 uc.course (预加载的 Course 对象) 存在
            if uc.course:
                # 确保 Course 对象的 required_skills 字段在返回时是正确的列表形式
                # 尽管 DashboardCourseCard 不直接显示 skills，但 Course 对象本身可能在ORM层加载了。
                # 这里统一处理其解析，以防万一或作为良好实践。
                course_skills = getattr(uc.course, 'required_skills', None)
                if isinstance(course_skills, str):
                    try:
                        course_skills = json.loads(course_skills)
                    except json.JSONDecodeError:
                        course_skills = []
                elif course_skills is None:
                    course_skills = []
                
                # 安全地更新ORM对象
                if hasattr(uc.course, 'required_skills'):
                    uc.course.required_skills = course_skills  # 更新ORM对象确保一致性

                course_cards.append(schemas.DashboardCourseCard(
                    id=uc.course.id,  # 直接从预加载的 Course 对象获取 ID
                    title=uc.course.title,  # 直接从预加载的 Course 对象获取 Title
                    progress=uc.progress,
                    last_accessed=uc.last_accessed
                ))
            else:
                print(f"WARNING: 用户 {current_user_id} 关联的课程 {getattr(uc, 'course_id', 'unknown')} 未找到。")

        print(f"DEBUG: 获取到 {len(course_cards)} 门课程卡片。")
        return course_cards
    
    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        print(f"ERROR: 获取用户课程列表失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取课程列表失败"
        )