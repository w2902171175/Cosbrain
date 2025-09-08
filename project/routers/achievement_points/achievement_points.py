# project/routers/achievement_points/achievement_points.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from project.database import get_db
from project.utils.core.error_decorators import database_transaction
from project.models.achievement_points import Achievement, UserAchievement, PointTransaction
from project.models.auth import User
from project.services.achievement_points_service import (
    AchievementPointsService, PointsService, AchievementPointsUtils
)
from project.utils import get_current_user
from project.utils.core.common_utils import _check_and_award_achievements

router = APIRouter(
    prefix="/achievement-points",
    tags=["achievement-points"]
)


@router.get("/achievements", summary="获取成就定义列表")
async def get_achievement_definitions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    active_only: bool = Query(True, description="是否只获取激活的成就"),
    db: Session = Depends(get_db)
):
    """获取成就定义列表"""
    with database_transaction(db):
        return await AchievementPointsService.get_achievement_definitions(
            db=db,
            page=page,
            page_size=page_size,
            active_only=active_only
        )


@router.get("/users/{user_id}/points", summary="获取用户积分信息")
async def get_user_points(
    user_id: int,
    include_history: bool = Query(False, description="是否包含积分历史"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户积分信息"""
    # 检查权限：只能查看自己的积分或管理员可以查看任何人的积分
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限查看该用户的积分信息")

    with database_transaction(db):
        return await AchievementPointsService.get_user_points(
            db=db,
            user_id=user_id,
            include_history=include_history
        )


@router.get("/users/{user_id}/points/history", summary="获取用户积分历史")
async def get_user_points_history(
    user_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    action: Optional[str] = Query(None, description="操作类型过滤"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户积分历史记录"""
    # 检查权限
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限查看该用户的积分历史")

    with database_transaction(db):
        return await AchievementPointsService.get_points_history(
            db=db,
            user_id=user_id,
            page=page,
            page_size=page_size,
            action_filter=action
        )


@router.get("/users/{user_id}/achievements", summary="获取用户成就")
async def get_user_achievements(
    user_id: int,
    include_locked: bool = Query(False, description="是否包含未解锁的成就"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户成就信息"""
    # 检查权限
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限查看该用户的成就信息")

    with database_transaction(db):
        return await AchievementPointsService.get_user_achievements(
            db=db,
            user_id=user_id,
            include_locked=include_locked
        )


@router.post("/achievements/init", summary="初始化默认成就")
async def initialize_achievements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """初始化默认成就到数据库"""
    # 检查管理员权限
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")

    with database_transaction(db):
        count = AchievementPointsService.initialize_default_achievements(db)
        return {"message": f"成功初始化 {count} 个默认成就"}


@router.post("/users/{user_id}/check-achievements", summary="检查用户成就")
async def check_user_achievements(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """手动触发用户成就检查"""
    # 检查权限：只能检查自己的成就或管理员可以检查任何人的成就
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="没有权限触发该用户的成就检查")

    with database_transaction(db):
        # 触发成就检查
        await AchievementPointsUtils.trigger_achievement_check(db, user_id)
        return {"message": "成就检查已完成"}


@router.get("/leaderboard", summary="获取积分排行榜")
async def get_points_leaderboard(
    limit: int = Query(10, ge=1, le=100, description="排行榜数量"),
    period: str = Query("all_time", description="时间段 (all_time, monthly, weekly)"),
    db: Session = Depends(get_db)
):
    """获取积分排行榜"""
    with database_transaction(db):
        return await AchievementPointsUtils.get_leaderboard(
            db=db,
            limit=limit,
            period=period
        )
