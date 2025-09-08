# project/services/dashboard_service.py
"""
仪表板服务层 - 数据聚合和实时缓存优化
基于优化框架为 Dashboard 模块提供高效的数据聚合服务层实现
"""
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import logging
import json

# 模型导入
from project.models import (
    User, Project, Course, UserCourse, ChatRoom, ProjectMember,
    AIConversation, ForumTopic, CollectedContent, ProjectApplication
)
import project.schemas as schemas

# 工具导入
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.async_cache.cache_manager import cache_result, invalidate_cache_pattern
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import get_cache_key, monitor_performance

logger = logging.getLogger(__name__)

class DashboardDataService:
    """仪表板数据聚合服务类"""
    
    @staticmethod
    @handle_database_errors
    @cache_result(expire=300, key_prefix="dashboard_summary")
    def get_dashboard_summary_optimized(
        db: Session, 
        user_id: int
    ) -> Dict[str, Any]:
        """获取仪表板概览数据 - 优化版本"""
        
        # 一次性查询获取所有项目统计
        project_stats = db.query(
            func.count(Project.id).label('total_projects'),
            func.sum(func.case(
                (Project.creator_id == user_id, 1), 
                else_=0
            )).label('created_projects'),
            func.sum(func.case(
                (Project.project_status == "进行中", 1), 
                else_=0
            )).label('active_projects'),
            func.sum(func.case(
                (Project.project_status == "已完成", 1), 
                else_=0
            )).label('completed_projects')
        ).filter(
            func.or_(
                Project.creator_id == user_id,
                Project.id.in_(
                    db.query(ProjectMember.project_id).filter(
                        ProjectMember.user_id == user_id
                    )
                )
            )
        ).first()
        
        # 一次性查询获取所有课程统计
        course_stats = db.query(
            func.count(UserCourse.id).label('total_courses'),
            func.sum(func.case(
                (UserCourse.status == "in_progress", 1), 
                else_=0
            )).label('learning_courses'),
            func.sum(func.case(
                (UserCourse.status == "completed", 1), 
                else_=0
            )).label('completed_courses'),
            func.avg(UserCourse.progress).label('avg_progress')
        ).filter(UserCourse.student_id == user_id).first()
        
        # 获取AI对话统计
        ai_stats = db.query(
            func.count(AIConversation.id).label('total_conversations'),
            func.sum(func.case(
                (func.date(AIConversation.updated_at) == datetime.now().date(), 1),
                else_=0
            )).label('today_conversations')
        ).filter(AIConversation.user_id == user_id).first()
        
        # 获取论坛活动统计
        forum_stats = db.query(
            func.count(ForumTopic.id).label('forum_topics'),
            func.sum(ForumTopic.likes_count).label('total_likes')
        ).filter(ForumTopic.author_id == user_id).first()
        
        # 获取收藏统计
        collection_stats = db.query(
            func.count(CollectedContent.id).label('collected_items')
        ).join(CollectedContent.folder).filter(
            CollectedContent.folder.has(creator_id=user_id)
        ).first()
        
        # 获取用户信息和简历完成度
        user = db.query(User).filter(User.id == user_id).first()
        resume_completion = DashboardUtilities.calculate_resume_completion(user)
        
        # 获取最近活动
        recent_activities = DashboardDataService._get_recent_activities_optimized(db, user_id)
        
        summary_data = {
            # 项目相关
            "total_projects": project_stats.total_projects or 0,
            "created_projects": project_stats.created_projects or 0,
            "active_projects": project_stats.active_projects or 0,
            "completed_projects": project_stats.completed_projects or 0,
            
            # 课程相关
            "total_courses": course_stats.total_courses or 0,
            "learning_courses": course_stats.learning_courses or 0,
            "completed_courses": course_stats.completed_courses or 0,
            "avg_course_progress": float(course_stats.avg_progress or 0),
            
            # AI对话相关
            "total_ai_conversations": ai_stats.total_conversations or 0,
            "today_ai_conversations": ai_stats.today_conversations or 0,
            
            # 论坛相关
            "forum_topics_created": forum_stats.forum_topics or 0,
            "total_forum_likes": forum_stats.total_likes or 0,
            
            # 收藏相关
            "collected_items": collection_stats.collected_items or 0,
            
            # 用户信息
            "resume_completion_percentage": resume_completion,
            "user_level": DashboardUtilities.calculate_user_level(user),
            "recent_activities": recent_activities
        }
        
        logger.info(f"获取用户 {user_id} 的仪表板概览数据")
        return summary_data
    
    @staticmethod
    @handle_database_errors
    def _get_recent_activities_optimized(
        db: Session, 
        user_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取最近活动 - 优化版本"""
        
        activities = []
        
        # 最近的项目活动
        recent_projects = db.query(Project).filter(
            func.or_(
                Project.creator_id == user_id,
                Project.id.in_(
                    db.query(ProjectMember.project_id).filter(
                        ProjectMember.user_id == user_id
                    )
                )
            )
        ).order_by(Project.updated_at.desc()).limit(3).all()
        
        for project in recent_projects:
            activities.append({
                "type": "project",
                "title": f"项目: {project.title}",
                "description": f"状态: {project.project_status}",
                "timestamp": project.updated_at,
                "link": f"/projects/{project.id}"
            })
        
        # 最近的AI对话
        recent_conversations = db.query(AIConversation).filter(
            AIConversation.user_id == user_id
        ).order_by(AIConversation.updated_at.desc()).limit(3).all()
        
        for conv in recent_conversations:
            activities.append({
                "type": "ai_conversation",
                "title": f"AI对话: {conv.title or '未命名对话'}",
                "description": "AI智能助手对话",
                "timestamp": conv.updated_at,
                "link": f"/ai/conversations/{conv.id}"
            })
        
        # 最近的论坛话题
        recent_topics = db.query(ForumTopic).filter(
            ForumTopic.author_id == user_id
        ).order_by(ForumTopic.created_at.desc()).limit(3).all()
        
        for topic in recent_topics:
            activities.append({
                "type": "forum_topic",
                "title": f"论坛话题: {topic.title}",
                "description": f"分类: {topic.category}",
                "timestamp": topic.created_at,
                "link": f"/forum/topics/{topic.id}"
            })
        
        # 按时间排序并限制数量
        activities.sort(key=lambda x: x["timestamp"], reverse=True)
        return activities[:limit]
    
    @staticmethod
    @handle_database_errors
    @cache_result(expire=180, key_prefix="dashboard_projects")
    def get_dashboard_projects_optimized(
        db: Session,
        user_id: int,
        status_filter: Optional[str] = None,
        limit: int = 20
    ) -> Tuple[List[Project], Dict[str, Any]]:
        """获取仪表板项目列表 - 优化版本"""
        
        # 构建查询，预加载相关数据
        query = db.query(Project).options(
            joinedload(Project.creator),
            joinedload(Project.members),
            joinedload(Project.applications)
        ).filter(
            func.or_(
                Project.creator_id == user_id,
                Project.id.in_(
                    db.query(ProjectMember.project_id).filter(
                        ProjectMember.user_id == user_id
                    )
                )
            )
        )
        
        # 应用状态筛选
        if status_filter:
            query = query.filter(Project.project_status == status_filter)
        
        # 按更新时间排序
        projects = query.order_by(Project.updated_at.desc()).limit(limit).all()
        
        # 计算统计信息
        stats = {
            "total_count": len(projects),
            "status_distribution": {},
            "avg_progress": 0
        }
        
        # 计算状态分布和平均进度
        total_progress = 0
        for project in projects:
            status = project.project_status
            stats["status_distribution"][status] = stats["status_distribution"].get(status, 0) + 1
            total_progress += DashboardUtilities.calculate_project_progress(status)
        
        if projects:
            stats["avg_progress"] = total_progress / len(projects)
        
        logger.info(f"获取用户 {user_id} 的仪表板项目列表：{len(projects)} 个项目")
        return projects, stats
    
    @staticmethod
    @handle_database_errors
    @cache_result(expire=180, key_prefix="dashboard_courses")
    def get_dashboard_courses_optimized(
        db: Session,
        user_id: int,
        status_filter: Optional[str] = None,
        limit: int = 20
    ) -> Tuple[List[UserCourse], Dict[str, Any]]:
        """获取仪表板课程列表 - 优化版本"""
        
        # 构建查询，预加载课程信息
        query = db.query(UserCourse).options(
            joinedload(UserCourse.course),
            joinedload(UserCourse.student)
        ).filter(UserCourse.student_id == user_id)
        
        # 应用状态筛选
        if status_filter:
            query = query.filter(UserCourse.status == status_filter)
        
        # 按最后访问时间排序
        user_courses = query.order_by(UserCourse.last_accessed.desc()).limit(limit).all()
        
        # 计算统计信息
        stats = {
            "total_count": len(user_courses),
            "status_distribution": {},
            "avg_progress": 0,
            "total_study_time": 0
        }
        
        # 计算状态分布和平均进度
        total_progress = 0
        for uc in user_courses:
            status = uc.status
            stats["status_distribution"][status] = stats["status_distribution"].get(status, 0) + 1
            total_progress += uc.progress or 0
            stats["total_study_time"] += uc.study_time or 0
        
        if user_courses:
            stats["avg_progress"] = total_progress / len(user_courses)
        
        logger.info(f"获取用户 {user_id} 的仪表板课程列表：{len(user_courses)} 门课程")
        return user_courses, stats

class DashboardAnalyticsService:
    """仪表板分析服务类"""
    
    @staticmethod
    @handle_database_errors
    @cache_result(expire=600, key_prefix="dashboard_analytics")
    def get_user_analytics_optimized(
        db: Session,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """获取用户分析数据 - 优化版本"""
        
        start_date = datetime.now() - timedelta(days=days)
        
        # 活动趋势分析
        daily_activities = db.query(
            func.date(Project.updated_at).label('date'),
            func.count(Project.id).label('project_activities')
        ).filter(
            Project.updated_at >= start_date,
            func.or_(
                Project.creator_id == user_id,
                Project.id.in_(
                    db.query(ProjectMember.project_id).filter(
                        ProjectMember.user_id == user_id
                    )
                )
            )
        ).group_by(func.date(Project.updated_at)).all()
        
        # 学习进度分析
        learning_progress = db.query(
            func.avg(UserCourse.progress).label('avg_progress'),
            func.count(UserCourse.id).label('course_count'),
            func.sum(UserCourse.study_time).label('total_study_time')
        ).filter(
            UserCourse.student_id == user_id,
            UserCourse.last_accessed >= start_date
        ).first()
        
        # AI使用分析
        ai_usage = db.query(
            func.count(AIConversation.id).label('conversation_count'),
            func.date(AIConversation.created_at).label('date')
        ).filter(
            AIConversation.user_id == user_id,
            AIConversation.created_at >= start_date
        ).group_by(func.date(AIConversation.created_at)).all()
        
        analytics_data = {
            "period_days": days,
            "activity_trend": [
                {
                    "date": str(activity.date),
                    "project_activities": activity.project_activities
                }
                for activity in daily_activities
            ],
            "learning_metrics": {
                "avg_progress": float(learning_progress.avg_progress or 0),
                "active_courses": learning_progress.course_count or 0,
                "total_study_hours": (learning_progress.total_study_time or 0) / 3600  # 转换为小时
            },
            "ai_usage_trend": [
                {
                    "date": str(usage.date),
                    "conversations": usage.conversation_count
                }
                for usage in ai_usage
            ]
        }
        
        logger.info(f"获取用户 {user_id} 的分析数据（{days}天）")
        return analytics_data
    
    @staticmethod
    @handle_database_errors
    def get_productivity_metrics_optimized(
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """获取生产力指标 - 优化版本"""
        
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # 今日活动
        today_activities = {
            "projects_updated": db.query(Project).filter(
                func.date(Project.updated_at) == today,
                func.or_(
                    Project.creator_id == user_id,
                    Project.id.in_(
                        db.query(ProjectMember.project_id).filter(
                            ProjectMember.user_id == user_id
                        )
                    )
                )
            ).count(),
            "ai_conversations": db.query(AIConversation).filter(
                AIConversation.user_id == user_id,
                func.date(AIConversation.created_at) == today
            ).count(),
            "forum_posts": db.query(ForumTopic).filter(
                ForumTopic.author_id == user_id,
                func.date(ForumTopic.created_at) == today
            ).count()
        }
        
        # 本周完成项目
        week_completed = db.query(Project).filter(
            Project.project_status == "已完成",
            Project.updated_at >= week_ago,
            func.or_(
                Project.creator_id == user_id,
                Project.id.in_(
                    db.query(ProjectMember.project_id).filter(
                        ProjectMember.user_id == user_id
                    )
                )
            )
        ).count()
        
        # 本月学习时长
        month_study_time = db.query(
            func.sum(UserCourse.study_time).label('total_time')
        ).filter(
            UserCourse.student_id == user_id,
            UserCourse.last_accessed >= month_ago
        ).first()
        
        productivity_data = {
            "today_activities": today_activities,
            "week_completed_projects": week_completed,
            "month_study_hours": (month_study_time.total_time or 0) / 3600,
            "productivity_score": DashboardUtilities.calculate_productivity_score(
                today_activities, week_completed, month_study_time.total_time or 0
            )
        }
        
        logger.info(f"获取用户 {user_id} 的生产力指标")
        return productivity_data

class DashboardUtilities:
    """仪表板工具类"""
    
    @staticmethod
    def calculate_resume_completion(user: User) -> float:
        """计算简历完成度"""
        
        if not user:
            return 0.0
        
        resume_fields = [
            'name', 'major', 'skills', 'interests', 'bio', 
            'awards_competitions', 'academic_achievements', 'soft_skills',
            'portfolio_link', 'preferred_role', 'availability'
        ]
        
        completed_fields = 0
        for field in resume_fields:
            value = getattr(user, field, None)
            if value and str(value).strip() and value != "张三":  # 排除默认值
                completed_fields += 1
        
        return (completed_fields / len(resume_fields)) * 100 if resume_fields else 0.0
    
    @staticmethod
    def calculate_project_progress(status: str) -> float:
        """计算项目进度"""
        
        progress_map = {
            "进行中": 0.6,
            "已完成": 1.0,
            "待开始": 0.0,
            "已暂停": 0.3,
            "已取消": 0.0
        }
        return progress_map.get(status, 0.0)
    
    @staticmethod
    def calculate_user_level(user: User) -> str:
        """计算用户等级"""
        
        if not user:
            return "新手"
        
        # 基于多个维度计算用户等级
        points = 0
        
        # 简历完成度
        resume_completion = DashboardUtilities.calculate_resume_completion(user)
        points += int(resume_completion / 10)
        
        # 可以添加更多维度，如项目数量、课程完成数等
        # 这里简化处理
        
        if points >= 80:
            return "专家"
        elif points >= 60:
            return "高级"
        elif points >= 40:
            return "中级"
        elif points >= 20:
            return "初级"
        else:
            return "新手"
    
    @staticmethod
    def calculate_productivity_score(
        today_activities: Dict[str, int],
        week_completed: int,
        month_study_time: int
    ) -> float:
        """计算生产力评分"""
        
        score = 0.0
        
        # 今日活动得分 (0-30分)
        daily_score = min(30, sum(today_activities.values()) * 3)
        score += daily_score
        
        # 本周完成项目得分 (0-40分)
        weekly_score = min(40, week_completed * 10)
        score += weekly_score
        
        # 本月学习时长得分 (0-30分)
        study_hours = month_study_time / 3600
        study_score = min(30, study_hours * 2)
        score += study_score
        
        return min(100.0, score)
    
    @staticmethod
    def format_dashboard_card(
        item_id: int,
        title: str,
        progress: float,
        item_type: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """格式化仪表板卡片数据"""
        
        return {
            "id": item_id,
            "title": title,
            "progress": round(progress, 2),
            "type": item_type,
            "metadata": metadata or {},
            "status_color": DashboardUtilities._get_progress_color(progress)
        }
    
    @staticmethod
    def _get_progress_color(progress: float) -> str:
        """根据进度获取状态颜色"""
        
        if progress >= 0.8:
            return "green"
        elif progress >= 0.5:
            return "orange"
        elif progress > 0:
            return "blue"
        else:
            return "gray"
    
    @staticmethod
    def validate_status_filter(
        status_filter: Optional[str],
        valid_statuses: List[str],
        entity_type: str
    ) -> None:
        """验证状态筛选器"""
        
        if status_filter and status_filter not in valid_statuses:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的{entity_type}状态筛选器。有效值: {', '.join(valid_statuses)}"
            )

logger.info("📊 Dashboard Service - 仪表板服务已加载")
