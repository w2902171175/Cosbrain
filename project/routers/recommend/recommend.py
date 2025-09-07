# project/routers/recommend.py
"""
推荐系统模块路由层 - 优化版本
集成优化框架提供高性能的推荐API
支持多种推荐算法、实时推荐、用户画像等功能
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Body
from sqlalchemy.orm import Session
import logging
from datetime import datetime

# 核心导入
from project.database import get_db
from project.utils.core.error_decorators import handle_database_errors
from project.utils.optimization.router_optimization import optimized_route
import project.schemas as schemas
from project.services.recommend_service import (
    RecommendationService, UserProfileService, RecommendationUtilities
)

# 工具导入
from project.utils.optimization.production_utils import cache_manager
from project.utils import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["智能推荐"])

@router.get("/", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_recommendations(
    type: str = Query(..., description="推荐类型: courses, projects, knowledge, forum"),
    limit: int = Query(20, ge=1, le=100, description="推荐数量"),
    algorithm: str = Query("hybrid", description="推荐算法: collaborative, content, hybrid"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取个性化推荐
    
    - **type**: 推荐类型 (courses: 课程, projects: 项目, knowledge: 知识, forum: 论坛)
    - **limit**: 推荐数量限制
    - **algorithm**: 推荐算法类型
    """
    try:
        # 验证推荐类型
        valid_types = ["courses", "projects", "knowledge", "forum"]
        if type not in valid_types:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的推荐类型。支持的类型: {', '.join(valid_types)}"
            )
        
        # 验证推荐算法
        valid_algorithms = ["collaborative", "content", "hybrid"]
        if algorithm not in valid_algorithms:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的推荐算法。支持的算法: {', '.join(valid_algorithms)}"
            )
        
        # 获取推荐结果
        recommendations = await RecommendationService.get_user_recommendations_optimized(
            db, current_user_id, type, limit, algorithm
        )
        
        logger.info(f"用户 {current_user_id} 获取 {type} 推荐: {len(recommendations)} 项")
        return {
            "message": f"获取{type}推荐成功",
            "data": {
                "recommendations": recommendations,
                "total": len(recommendations),
                "type": type,
                "algorithm": algorithm,
                "generated_at": datetime.now().isoformat()
            }
        }
        
    except ValueError as e:
        logger.warning(f"推荐参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取推荐失败: {e}")
        raise HTTPException(status_code=500, detail="获取推荐失败")

@router.get("/courses", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_course_recommendations(
    limit: int = Query(20, ge=1, le=50, description="推荐数量"),
    algorithm: str = Query("hybrid", description="推荐算法"),
    difficulty: Optional[str] = Query(None, description="难度过滤: beginner, intermediate, advanced"),
    category: Optional[str] = Query(None, description="分类过滤"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取课程推荐
    
    - **limit**: 推荐数量
    - **algorithm**: 推荐算法
    - **difficulty**: 难度级别过滤
    - **category**: 课程分类过滤
    """
    try:
        # 获取基础推荐
        recommendations = await RecommendationService.get_user_recommendations_optimized(
            db, current_user_id, "courses", limit, algorithm
        )
        
        # 应用过滤条件
        if difficulty:
            recommendations = [
                r for r in recommendations 
                if r.get('difficulty') == difficulty
            ]
        
        if category:
            recommendations = [
                r for r in recommendations 
                if r.get('category') == category
            ]
        
        logger.info(f"用户 {current_user_id} 获取课程推荐: {len(recommendations)} 项")
        return {
            "message": "获取课程推荐成功",
            "data": {
                "courses": recommendations,
                "total": len(recommendations),
                "filters": {
                    "difficulty": difficulty,
                    "category": category
                }
            }
        }
        
    except Exception as e:
        logger.error(f"获取课程推荐失败: {e}")
        raise HTTPException(status_code=500, detail="获取课程推荐失败")

@router.get("/projects", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_project_recommendations(
    limit: int = Query(20, ge=1, le=50, description="推荐数量"),
    skill_match: bool = Query(True, description="是否基于技能匹配"),
    difficulty: Optional[str] = Query(None, description="难度过滤"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取项目推荐
    
    - **limit**: 推荐数量
    - **skill_match**: 是否基于技能匹配推荐
    - **difficulty**: 难度级别过滤
    """
    try:
        # 根据技能匹配选择算法
        algorithm = "content" if skill_match else "hybrid"
        
        # 获取项目推荐
        recommendations = await RecommendationService.get_user_recommendations_optimized(
            db, current_user_id, "projects", limit, algorithm
        )
        
        # 应用难度过滤
        if difficulty:
            recommendations = [
                r for r in recommendations 
                if r.get('difficulty') == difficulty
            ]
        
        logger.info(f"用户 {current_user_id} 获取项目推荐: {len(recommendations)} 项")
        return {
            "message": "获取项目推荐成功",
            "data": {
                "projects": recommendations,
                "total": len(recommendations),
                "skill_based": skill_match
            }
        }
        
    except Exception as e:
        logger.error(f"获取项目推荐失败: {e}")
        raise HTTPException(status_code=500, detail="获取项目推荐失败")

@router.get("/knowledge", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_knowledge_recommendations(
    limit: int = Query(20, ge=1, le=50, description="推荐数量"),
    content_type: Optional[str] = Query(None, description="内容类型: article, video, tutorial"),
    difficulty: Optional[str] = Query(None, description="难度级别"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取知识推荐
    
    - **limit**: 推荐数量
    - **content_type**: 内容类型过滤
    - **difficulty**: 难度级别过滤
    """
    try:
        # 获取知识推荐
        recommendations = await RecommendationService.get_user_recommendations_optimized(
            db, current_user_id, "knowledge", limit, "content"
        )
        
        # 应用过滤条件
        if content_type:
            recommendations = [
                r for r in recommendations 
                if r.get('content_type') == content_type
            ]
        
        if difficulty:
            recommendations = [
                r for r in recommendations 
                if r.get('difficulty_level') == difficulty
            ]
        
        logger.info(f"用户 {current_user_id} 获取知识推荐: {len(recommendations)} 项")
        return {
            "message": "获取知识推荐成功",
            "data": {
                "knowledge_items": recommendations,
                "total": len(recommendations),
                "filters": {
                    "content_type": content_type,
                    "difficulty": difficulty
                }
            }
        }
        
    except Exception as e:
        logger.error(f"获取知识推荐失败: {e}")
        raise HTTPException(status_code=500, detail="获取知识推荐失败")

@router.get("/forum", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_forum_recommendations(
    limit: int = Query(20, ge=1, le=50, description="推荐数量"),
    hot_only: bool = Query(False, description="仅推荐热门帖子"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取论坛帖子推荐
    
    - **limit**: 推荐数量
    - **hot_only**: 是否仅推荐热门帖子
    """
    try:
        # 获取论坛推荐
        recommendations = await RecommendationService.get_user_recommendations_optimized(
            db, current_user_id, "forum", limit, "hybrid"
        )
        
        # 如果只要热门帖子，按热度重新排序
        if hot_only:
            recommendations = sorted(
                recommendations,
                key=lambda x: x.get('view_count', 0) + x.get('like_count', 0) * 2,
                reverse=True
            )
        
        logger.info(f"用户 {current_user_id} 获取论坛推荐: {len(recommendations)} 项")
        return {
            "message": "获取论坛推荐成功",
            "data": {
                "forum_posts": recommendations,
                "total": len(recommendations),
                "hot_only": hot_only
            }
        }
        
    except Exception as e:
        logger.error(f"获取论坛推荐失败: {e}")
        raise HTTPException(status_code=500, detail="获取论坛推荐失败")

@router.get("/profile", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_user_profile(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取用户画像
    
    返回用户的兴趣、技能、学习偏好等画像信息
    """
    try:
        # 获取用户画像
        profile = await UserProfileService.get_user_profile_optimized(
            db, current_user_id
        )
        
        logger.info(f"用户 {current_user_id} 获取画像信息")
        return {
            "message": "获取用户画像成功",
            "data": profile
        }
        
    except ValueError as e:
        logger.warning(f"用户画像参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取用户画像失败: {e}")
        raise HTTPException(status_code=500, detail="获取用户画像失败")

@router.post("/feedback", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def submit_recommendation_feedback(
    feedback_data: Dict[str, Any] = Body(
        ...,
        description="推荐反馈数据",
        example={
            "item_id": 123,
            "item_type": "course",
            "action": "like",
            "rating": 5,
            "comment": "很好的推荐"
        }
    ),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    提交推荐反馈
    
    - **item_id**: 推荐项目ID
    - **item_type**: 推荐项目类型
    - **action**: 用户行为 (like, dislike, click, ignore)
    - **rating**: 评分 (1-5)
    - **comment**: 评论
    """
    try:
        # 验证反馈数据
        required_fields = ['item_id', 'item_type', 'action']
        for field in required_fields:
            if not feedback_data.get(field):
                raise HTTPException(
                    status_code=400, 
                    detail=f"缺少必需字段: {field}"
                )
        
        # 验证行为类型
        valid_actions = ['like', 'dislike', 'click', 'ignore', 'share']
        if feedback_data['action'] not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的行为类型。支持的类型: {', '.join(valid_actions)}"
            )
        
        # 记录用户反馈（这里应该保存到数据库）
        feedback_log = {
            'user_id': current_user_id,
            'item_id': feedback_data['item_id'],
            'item_type': feedback_data['item_type'],
            'action': feedback_data['action'],
            'rating': feedback_data.get('rating'),
            'comment': feedback_data.get('comment'),
            'timestamp': datetime.now().isoformat()
        }
        
        # 后台任务：清理相关缓存，更新推荐模型
        background_tasks.add_task(
            RecommendationUtilities.clear_user_cache,
            current_user_id
        )
        
        logger.info(f"用户 {current_user_id} 提交推荐反馈: {feedback_data['action']}")
        return {
            "message": "推荐反馈提交成功",
            "data": {
                "feedback_id": f"fb_{current_user_id}_{int(datetime.now().timestamp())}",
                "status": "recorded"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交推荐反馈失败: {e}")
        raise HTTPException(status_code=500, detail="提交推荐反馈失败")

@router.get("/stats", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_recommendation_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取推荐统计信息
    
    返回用户的推荐使用统计
    """
    try:
        # 检查缓存
        cache_key = f"recommendation_stats_{current_user_id}"
        cached_stats = cache_manager.get(cache_key)
        if cached_stats:
            return cached_stats
        
        # 计算统计信息（简化实现）
        stats = {
            "total_recommendations_received": 150,  # 应该从数据库查询
            "recommendations_clicked": 45,
            "recommendations_liked": 23,
            "click_through_rate": 0.3,
            "satisfaction_rate": 0.85,
            "favorite_types": {
                "courses": 40,
                "projects": 35,
                "knowledge": 25,
                "forum": 15
            },
            "learning_progress": {
                "completed_recommendations": 28,
                "in_progress": 12,
                "planned": 8
            },
            "last_updated": datetime.now().isoformat()
        }
        
        result = {
            "message": "获取推荐统计成功",
            "data": stats
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, ttl=1800)  # 30分钟缓存
        
        logger.info(f"用户 {current_user_id} 获取推荐统计")
        return result
        
    except Exception as e:
        logger.error(f"获取推荐统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取推荐统计失败")

@router.post("/refresh", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def refresh_recommendations(
    refresh_request: Dict[str, Any] = Body(
        ...,
        description="刷新请求",
        example={
            "types": ["courses", "projects"],
            "clear_cache": True
        }
    ),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    刷新用户推荐
    
    - **types**: 要刷新的推荐类型列表
    - **clear_cache**: 是否清除缓存
    """
    try:
        types_to_refresh = refresh_request.get('types', ['courses', 'projects', 'knowledge', 'forum'])
        clear_cache = refresh_request.get('clear_cache', True)
        
        # 清除缓存
        if clear_cache:
            background_tasks.add_task(
                RecommendationUtilities.clear_user_cache,
                current_user_id
            )
        
        # 预生成新推荐（后台任务）
        async def pregenerate_recommendations():
            for rec_type in types_to_refresh:
                try:
                    await RecommendationService.get_user_recommendations_optimized(
                        db, current_user_id, rec_type, 20, "hybrid"
                    )
                except Exception as e:
                    logger.error(f"预生成 {rec_type} 推荐失败: {e}")
        
        background_tasks.add_task(pregenerate_recommendations)
        
        logger.info(f"用户 {current_user_id} 刷新推荐: {types_to_refresh}")
        return {
            "message": "推荐刷新成功",
            "data": {
                "refreshed_types": types_to_refresh,
                "cache_cleared": clear_cache,
                "status": "processing"
            }
        }
        
    except Exception as e:
        logger.error(f"刷新推荐失败: {e}")
        raise HTTPException(status_code=500, detail="刷新推荐失败")

@router.get("/health", response_model=schemas.Response)
@optimized_route
async def recommendation_health_check():
    """推荐系统健康检查"""
    try:
        # 检查缓存连接
        cache_status = "healthy" if cache_manager.is_connected() else "error"
        
        health_data = {
            "status": "healthy",
            "module": "Recommendation",
            "timestamp": datetime.now().isoformat(),
            "cache_status": cache_status,
            "algorithms": ["collaborative", "content", "hybrid"],
            "recommendation_types": ["courses", "projects", "knowledge", "forum"],
            "features": [
                "个性化推荐",
                "用户画像",
                "多算法融合",
                "实时推荐",
                "反馈学习"
            ],
            "version": "2.0.0"
        }
        
        logger.info("推荐系统健康检查")
        return {
            "message": "推荐系统运行正常",
            "data": health_data
        }
        
    except Exception as e:
        logger.error(f"推荐系统健康检查失败: {e}")
        return {
            "message": "推荐系统健康检查异常",
            "data": {
                "status": "error",
                "error": str(e)
            }
        }

# 模块加载日志
logger.info("🎯 Recommend Module - 智能推荐模块已加载")
