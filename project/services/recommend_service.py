# project/services/recommend_service.py
"""
推荐系统模块服务层 - 业务逻辑分离
基于优化框架为推荐系统提供高效的服务层实现
支持多种推荐算法、实时计算、批量处理等功能
"""
from typing import List, Optional, Dict, Any, Tuple, Union
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc, text
from datetime import datetime, timedelta
import logging
import json
import math
from collections import defaultdict

# 核心导入
from project.models import (
    User, Course, Project, KnowledgeItem, ForumPost, 
    UserBehavior, RecommendationLog
)
import project.schemas as schemas
from project.utils.optimization.production_utils import cache_manager
from project.ai_providers.matching_engine import MatchingEngine

logger = logging.getLogger(__name__)

class RecommendationService:
    """推荐系统核心服务"""
    
    @staticmethod
    async def get_user_recommendations_optimized(
        db: Session,
        user_id: int,
        recommendation_type: str,
        limit: int = 20,
        algorithm: str = "hybrid"
    ) -> List[Dict[str, Any]]:
        """获取用户个性化推荐 - 优化版本"""
        try:
            # 检查缓存
            cache_key = f"user_recommendations_{user_id}_{recommendation_type}_{algorithm}_{limit}"
            cached_result = cache_manager.get(cache_key)
            if cached_result:
                return cached_result
            
            # 根据推荐类型选择推荐算法
            if recommendation_type == "courses":
                recommendations = await RecommendationService._recommend_courses(
                    db, user_id, limit, algorithm
                )
            elif recommendation_type == "projects":
                recommendations = await RecommendationService._recommend_projects(
                    db, user_id, limit, algorithm
                )
            elif recommendation_type == "knowledge":
                recommendations = await RecommendationService._recommend_knowledge(
                    db, user_id, limit, algorithm
                )
            elif recommendation_type == "forum":
                recommendations = await RecommendationService._recommend_forum_posts(
                    db, user_id, limit, algorithm
                )
            else:
                raise ValueError(f"不支持的推荐类型: {recommendation_type}")
            
            # 记录推荐日志
            await RecommendationService._log_recommendations(
                db, user_id, recommendation_type, algorithm, recommendations
            )
            
            # 缓存结果
            cache_manager.set(cache_key, recommendations, ttl=1800)  # 30分钟缓存
            
            logger.info(f"用户 {user_id} 获取 {recommendation_type} 推荐: {len(recommendations)} 项")
            return recommendations
            
        except Exception as e:
            logger.error(f"获取用户推荐失败: {e}")
            raise
    
    @staticmethod
    async def _recommend_courses(
        db: Session,
        user_id: int,
        limit: int,
        algorithm: str
    ) -> List[Dict[str, Any]]:
        """课程推荐算法"""
        try:
            # 获取用户学习历史和偏好
            user_profile = await RecommendationService._get_user_profile(db, user_id)
            
            if algorithm == "collaborative":
                # 协同过滤推荐
                return await RecommendationService._collaborative_filter_courses(
                    db, user_id, user_profile, limit
                )
            elif algorithm == "content":
                # 基于内容的推荐
                return await RecommendationService._content_based_courses(
                    db, user_id, user_profile, limit
                )
            else:  # hybrid
                # 混合推荐算法
                collab_courses = await RecommendationService._collaborative_filter_courses(
                    db, user_id, user_profile, limit // 2
                )
                content_courses = await RecommendationService._content_based_courses(
                    db, user_id, user_profile, limit // 2
                )
                
                # 合并并去重
                course_dict = {}
                for course in collab_courses + content_courses:
                    course_id = course['id']
                    if course_id not in course_dict:
                        course_dict[course_id] = course
                    else:
                        # 合并评分
                        course_dict[course_id]['score'] = (
                            course_dict[course_id]['score'] + course['score']
                        ) / 2
                
                # 按评分排序
                recommendations = sorted(
                    course_dict.values(),
                    key=lambda x: x['score'],
                    reverse=True
                )[:limit]
                
                return recommendations
            
        except Exception as e:
            logger.error(f"课程推荐失败: {e}")
            return []
    
    @staticmethod
    async def _recommend_projects(
        db: Session,
        user_id: int,
        limit: int,
        algorithm: str
    ) -> List[Dict[str, Any]]:
        """项目推荐算法"""
        try:
            # 获取用户技能标签和兴趣
            user_profile = await RecommendationService._get_user_profile(db, user_id)
            user_skills = user_profile.get('skills', [])
            user_interests = user_profile.get('interests', [])
            
            # 查询项目
            projects_query = db.query(Project).filter(
                Project.is_active == True,
                Project.id.notin_(
                    # 排除用户已参与的项目
                    db.query(Project.id).filter(
                        Project.participants.any(id=user_id)
                    ).subquery()
                )
            )
            
            projects = projects_query.all()
            recommendations = []
            
            for project in projects:
                # 计算匹配度
                score = RecommendationService._calculate_project_score(
                    project, user_skills, user_interests
                )
                
                if score > 0.3:  # 设定阈值
                    recommendations.append({
                        'id': project.id,
                        'title': project.title,
                        'description': project.description,
                        'difficulty': getattr(project, 'difficulty', 'medium'),
                        'required_skills': getattr(project, 'required_skills', []),
                        'score': score,
                        'type': 'project',
                        'reason': RecommendationService._generate_project_reason(
                            project, user_skills, user_interests
                        )
                    })
            
            # 按评分排序并限制数量
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            return recommendations[:limit]
            
        except Exception as e:
            logger.error(f"项目推荐失败: {e}")
            return []
    
    @staticmethod
    async def _recommend_knowledge(
        db: Session,
        user_id: int,
        limit: int,
        algorithm: str
    ) -> List[Dict[str, Any]]:
        """知识推荐算法"""
        try:
            # 获取用户学习路径和知识偏好
            user_profile = await RecommendationService._get_user_profile(db, user_id)
            user_knowledge_areas = user_profile.get('knowledge_areas', [])
            
            # 查询知识项目
            knowledge_query = db.query(KnowledgeItem).filter(
                KnowledgeItem.is_published == True,
                KnowledgeItem.id.notin_(
                    # 排除用户已学习的知识
                    db.query(KnowledgeItem.id).join(UserBehavior).filter(
                        UserBehavior.user_id == user_id,
                        UserBehavior.action_type == 'knowledge_learned'
                    ).subquery()
                )
            )
            
            knowledge_items = knowledge_query.all()
            recommendations = []
            
            for item in knowledge_items:
                # 使用匹配引擎计算相似度
                score = await RecommendationService._calculate_knowledge_similarity(
                    item, user_knowledge_areas
                )
                
                if score > 0.4:  # 设定阈值
                    recommendations.append({
                        'id': item.id,
                        'title': item.title,
                        'content_type': getattr(item, 'content_type', 'article'),
                        'category': getattr(item, 'category', 'general'),
                        'difficulty_level': getattr(item, 'difficulty_level', 'beginner'),
                        'score': score,
                        'type': 'knowledge',
                        'estimated_time': getattr(item, 'estimated_time', 30),
                        'reason': f"基于你的学习领域 {', '.join(user_knowledge_areas[:3])} 推荐"
                    })
            
            # 按评分排序并限制数量
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            return recommendations[:limit]
            
        except Exception as e:
            logger.error(f"知识推荐失败: {e}")
            return []
    
    @staticmethod
    async def _recommend_forum_posts(
        db: Session,
        user_id: int,
        limit: int,
        algorithm: str
    ) -> List[Dict[str, Any]]:
        """论坛帖子推荐算法"""
        try:
            # 获取用户兴趣标签
            user_profile = await RecommendationService._get_user_profile(db, user_id)
            user_interests = user_profile.get('interests', [])
            
            # 查询热门帖子
            posts_query = db.query(ForumPost).filter(
                ForumPost.is_published == True,
                ForumPost.created_at >= datetime.now() - timedelta(days=30)  # 最近30天
            ).order_by(
                desc(ForumPost.view_count + ForumPost.like_count * 2)
            )
            
            posts = posts_query.limit(limit * 3).all()  # 获取更多候选
            recommendations = []
            
            for post in posts:
                # 计算相关性评分
                score = RecommendationService._calculate_post_relevance(
                    post, user_interests
                )
                
                if score > 0.2:  # 设定阈值
                    recommendations.append({
                        'id': post.id,
                        'title': post.title,
                        'content_preview': post.content[:200] + "..." if len(post.content) > 200 else post.content,
                        'author': post.author.username if hasattr(post, 'author') else 'Anonymous',
                        'view_count': getattr(post, 'view_count', 0),
                        'like_count': getattr(post, 'like_count', 0),
                        'comment_count': getattr(post, 'comment_count', 0),
                        'score': score,
                        'type': 'forum_post',
                        'created_at': post.created_at.isoformat(),
                        'reason': "基于你的兴趣和热门度推荐"
                    })
            
            # 按评分排序并限制数量
            recommendations.sort(key=lambda x: x['score'], reverse=True)
            return recommendations[:limit]
            
        except Exception as e:
            logger.error(f"论坛帖子推荐失败: {e}")
            return []

class UserProfileService:
    """用户画像服务"""
    
    @staticmethod
    async def get_user_profile_optimized(
        db: Session,
        user_id: int
    ) -> Dict[str, Any]:
        """获取用户画像 - 优化版本"""
        try:
            # 检查缓存
            cache_key = f"user_profile_{user_id}"
            cached_profile = cache_manager.get(cache_key)
            if cached_profile:
                return cached_profile
            
            # 获取用户基本信息
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError(f"用户不存在: {user_id}")
            
            # 构建用户画像
            profile = {
                'user_id': user_id,
                'username': user.username,
                'interests': await UserProfileService._extract_user_interests(db, user_id),
                'skills': await UserProfileService._extract_user_skills(db, user_id),
                'knowledge_areas': await UserProfileService._extract_knowledge_areas(db, user_id),
                'learning_style': await UserProfileService._analyze_learning_style(db, user_id),
                'activity_level': await UserProfileService._calculate_activity_level(db, user_id),
                'preferred_difficulty': await UserProfileService._analyze_difficulty_preference(db, user_id),
                'updated_at': datetime.now().isoformat()
            }
            
            # 缓存用户画像
            cache_manager.set(cache_key, profile, ttl=3600)  # 1小时缓存
            
            logger.info(f"构建用户 {user_id} 的画像")
            return profile
            
        except Exception as e:
            logger.error(f"获取用户画像失败: {e}")
            raise
    
    @staticmethod
    async def _extract_user_interests(db: Session, user_id: int) -> List[str]:
        """提取用户兴趣标签"""
        try:
            # 从用户行为分析兴趣
            behavior_query = db.query(UserBehavior).filter(
                UserBehavior.user_id == user_id,
                UserBehavior.created_at >= datetime.now() - timedelta(days=90)
            )
            
            behaviors = behavior_query.all()
            interest_counts = defaultdict(int)
            
            for behavior in behaviors:
                # 根据行为类型和目标提取兴趣标签
                tags = RecommendationUtilities.extract_tags_from_behavior(behavior)
                for tag in tags:
                    interest_counts[tag] += 1
            
            # 返回前10个兴趣标签
            interests = [tag for tag, _ in sorted(
                interest_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]]
            
            return interests
            
        except Exception as e:
            logger.error(f"提取用户兴趣失败: {e}")
            return []
    
    @staticmethod
    async def _extract_user_skills(db: Session, user_id: int) -> List[str]:
        """提取用户技能标签"""
        try:
            # 从完成的课程和项目中提取技能
            skills = set()
            
            # 从课程中提取技能
            course_completions = db.query(UserBehavior).filter(
                UserBehavior.user_id == user_id,
                UserBehavior.action_type == 'course_completed'
            ).all()
            
            for completion in course_completions:
                course_skills = RecommendationUtilities.extract_skills_from_course(
                    completion.target_id
                )
                skills.update(course_skills)
            
            return list(skills)[:15]  # 返回前15个技能
            
        except Exception as e:
            logger.error(f"提取用户技能失败: {e}")
            return []

class RecommendationUtilities:
    """推荐系统工具类"""
    
    @staticmethod
    async def _get_user_profile(db: Session, user_id: int) -> Dict[str, Any]:
        """获取用户画像（内部方法）"""
        return await UserProfileService.get_user_profile_optimized(db, user_id)
    
    @staticmethod
    def _calculate_project_score(
        project: Project,
        user_skills: List[str],
        user_interests: List[str]
    ) -> float:
        """计算项目匹配评分"""
        try:
            score = 0.0
            
            # 技能匹配度
            project_skills = getattr(project, 'required_skills', [])
            if project_skills:
                skill_match = len(set(user_skills) & set(project_skills)) / len(project_skills)
                score += skill_match * 0.6
            
            # 兴趣匹配度
            project_tags = getattr(project, 'tags', [])
            if project_tags:
                interest_match = len(set(user_interests) & set(project_tags)) / len(project_tags)
                score += interest_match * 0.4
            
            return min(score, 1.0)
            
        except Exception as e:
            logger.error(f"计算项目评分失败: {e}")
            return 0.0
    
    @staticmethod
    def _generate_project_reason(
        project: Project,
        user_skills: List[str],
        user_interests: List[str]
    ) -> str:
        """生成项目推荐理由"""
        try:
            reasons = []
            
            # 技能匹配
            project_skills = getattr(project, 'required_skills', [])
            matched_skills = set(user_skills) & set(project_skills)
            if matched_skills:
                reasons.append(f"匹配你的技能: {', '.join(list(matched_skills)[:3])}")
            
            # 兴趣匹配
            project_tags = getattr(project, 'tags', [])
            matched_interests = set(user_interests) & set(project_tags)
            if matched_interests:
                reasons.append(f"符合你的兴趣: {', '.join(list(matched_interests)[:2])}")
            
            return "; ".join(reasons) if reasons else "适合你的学习阶段"
            
        except Exception as e:
            logger.error(f"生成项目推荐理由失败: {e}")
            return "为你推荐"
    
    @staticmethod
    async def _calculate_knowledge_similarity(
        item: KnowledgeItem,
        user_areas: List[str]
    ) -> float:
        """计算知识相似度"""
        try:
            # 使用匹配引擎计算相似度
            item_content = f"{item.title} {getattr(item, 'summary', '')}"
            user_content = " ".join(user_areas)
            
            # 这里应该调用实际的匹配引擎
            # 简化实现
            similarity = MatchingEngine.calculate_text_similarity(
                item_content, user_content
            ) if hasattr(MatchingEngine, 'calculate_text_similarity') else 0.5
            
            return similarity
            
        except Exception as e:
            logger.error(f"计算知识相似度失败: {e}")
            return 0.0
    
    @staticmethod
    def _calculate_post_relevance(
        post: ForumPost,
        user_interests: List[str]
    ) -> float:
        """计算帖子相关性"""
        try:
            score = 0.0
            
            # 兴趣匹配度
            post_tags = getattr(post, 'tags', [])
            if post_tags and user_interests:
                interest_match = len(set(user_interests) & set(post_tags)) / len(user_interests)
                score += interest_match * 0.5
            
            # 热门度评分
            view_count = getattr(post, 'view_count', 0)
            like_count = getattr(post, 'like_count', 0)
            
            # 归一化热门度评分
            popularity_score = min((view_count + like_count * 2) / 1000, 1.0)
            score += popularity_score * 0.3
            
            # 时间新鲜度
            days_ago = (datetime.now() - post.created_at).days
            freshness_score = max(1 - days_ago / 30, 0.1)  # 30天内线性衰减
            score += freshness_score * 0.2
            
            return min(score, 1.0)
            
        except Exception as e:
            logger.error(f"计算帖子相关性失败: {e}")
            return 0.0
    
    @staticmethod
    def extract_tags_from_behavior(behavior: UserBehavior) -> List[str]:
        """从用户行为中提取标签"""
        try:
            tags = []
            
            # 根据行为类型和元数据提取标签
            metadata = getattr(behavior, 'metadata', {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            
            # 提取类别标签
            if 'category' in metadata:
                tags.append(metadata['category'])
            
            # 提取主题标签
            if 'topic' in metadata:
                tags.append(metadata['topic'])
            
            # 根据行为类型推断兴趣
            action_type = behavior.action_type
            if action_type in ['course_view', 'course_completed']:
                tags.append('learning')
            elif action_type in ['project_view', 'project_join']:
                tags.append('coding')
            elif action_type in ['forum_post', 'forum_reply']:
                tags.append('discussion')
            
            return tags
            
        except Exception as e:
            logger.error(f"提取行为标签失败: {e}")
            return []
    
    @staticmethod
    def extract_skills_from_course(course_id: int) -> List[str]:
        """从课程中提取技能标签"""
        try:
            # 这里应该根据实际的课程数据提取技能
            # 简化实现，返回一些通用技能
            skill_mapping = {
                1: ['Python', 'Programming'],
                2: ['JavaScript', 'Web Development'],
                3: ['Data Science', 'Machine Learning'],
                4: ['Database', 'SQL'],
                5: ['DevOps', 'Docker']
            }
            
            return skill_mapping.get(course_id, ['General Programming'])
            
        except Exception as e:
            logger.error(f"提取课程技能失败: {e}")
            return []
    
    @staticmethod
    async def _log_recommendations(
        db: Session,
        user_id: int,
        recommendation_type: str,
        algorithm: str,
        recommendations: List[Dict[str, Any]]
    ):
        """记录推荐日志"""
        try:
            log_entry = RecommendationLog(
                user_id=user_id,
                recommendation_type=recommendation_type,
                algorithm=algorithm,
                item_count=len(recommendations),
                items=[item['id'] for item in recommendations],
                created_at=datetime.now()
            )
            
            db.add(log_entry)
            db.commit()
            
        except Exception as e:
            logger.error(f"记录推荐日志失败: {e}")
    
    @staticmethod
    def clear_user_cache(user_id: int):
        """清除用户相关缓存"""
        cache_patterns = [
            f"user_recommendations_{user_id}_*",
            f"user_profile_{user_id}",
            f"recommendation_stats_{user_id}_*"
        ]
        for pattern in cache_patterns:
            cache_manager.delete_pattern(pattern)
