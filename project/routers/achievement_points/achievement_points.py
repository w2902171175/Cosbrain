# project/routers/achievement_points/achievement_points.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Literal

# 导入数据库和模型
from database import get_db
from models import Student, Achievement, UserAchievement, PointTransaction
from dependencies import get_current_user_id
from schemas import StudentResponse, AchievementResponse, UserAchievementResponse, PointTransactionResponse
import schemas

# 创建路由器
router = APIRouter(
    prefix="",  # 不使用前缀，因为路由已经包含完整路径
    tags=["积分成就"],
    responses={404: {"description": "Not found"}},
)


# --- 成就定义查询接口 (所有用户可访问) ---
@router.get("/achievements/definitions", response_model=List[AchievementResponse],
            summary="获取所有成就定义（可供所有用户查看）")
async def get_all_achievement_definitions(
        db: Session = Depends(get_db),
        is_active: Optional[bool] = None,  # 过滤条件：只获取启用或禁用的成就
        criteria_type: Optional[str] = None  # 过滤条件：按类型过滤
):
    """
    获取平台所有成就的定义列表。非管理员用户也可访问此接口以了解成就体系。
    可选择按激活状态和条件类型过滤。
    """
    print("DEBUG_ACHIEVEMENT: 获取所有成就定义。")
    query = db.query(Achievement)

    if is_active is not None:
        query = query.filter(Achievement.is_active == is_active)
    if criteria_type:
        query = query.filter(Achievement.criteria_type == criteria_type)

    achievements = query.order_by(Achievement.name).all()
    print(f"DEBUG_ACHIEVEMENT: 获取到 {len(achievements)} 条成就定义。")
    return achievements


@router.get("/achievements/definitions/{achievement_id}", response_model=AchievementResponse,
            summary="获取指定成就定义详情")
async def get_achievement_definition_by_id(
        achievement_id: int,
        db: Session = Depends(get_db)
):
    """
    获取指定ID的成就定义详情。非管理员用户也可访问。
    """
    print(f"DEBUG_ACHIEVEMENT: 获取成就定义 ID: {achievement_id} 的详情。")
    achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成就定义未找到。")
    return achievement


# --- 用户积分和成就查询接口 ---
@router.get("/users/me/points", response_model=schemas.StudentResponse, summary="获取当前用户积分余额和上次登录时间")
async def get_my_points_and_login_status(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取当前用户总积分余额和上次登录时间。
    """
    print(f"DEBUG_POINTS_QUERY: 获取用户 {current_user_id} 的积分信息。")
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未找到。")
    return user  # StudentResponse 会自动包含 total_points 和 last_login_at


@router.get("/users/me/points/history", response_model=List[PointTransactionResponse], summary="获取当前用户积分交易历史")
async def get_my_points_history(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        transaction_type: Optional[Literal["EARN", "CONSUME", "ADMIN_ADJUST"]] = None,
        limit: int = 20,
        offset: int = 0
):
    """
    获取当前用户的积分交易历史记录。
    可按交易类型过滤，并支持分页。
    """
    print(f"DEBUG_POINTS_QUERY: 获取用户 {current_user_id} 的积分历史。")
    query = db.query(PointTransaction).filter(PointTransaction.user_id == current_user_id)

    if transaction_type:
        query = query.filter(PointTransaction.transaction_type == transaction_type)

    transactions = query.order_by(PointTransaction.created_at.desc()).offset(offset).limit(limit).all()
    print(f"DEBUG_POINTS_QUERY: 获取到 {len(transactions)} 条积分交易记录。")
    return transactions


@router.get("/users/me/achievements", response_model=List[UserAchievementResponse], summary="获取当前用户已获得的成就列表")
async def get_my_achievements(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取当前用户已获得的成就列表，包含成就的详细元数据。
    """
    print(f"DEBUG_ACHIEVEMENT_QUERY: 获取用户 {current_user_id} 的已获得成就列表。")
    # 使用 joinedload 预加载关联的 Achievement 对象，避免 N+1 查询问题
    user_achievements = db.query(UserAchievement).options(
        joinedload(UserAchievement.achievement)  # 预加载成就定义
    ).filter(UserAchievement.user_id == current_user_id).all()

    # 填充 UserAchievementResponse 中的成就详情字段
    response_list = []
    for ua in user_achievements:
        response_data = UserAchievementResponse(
            id=ua.id,
            user_id=ua.user_id,
            achievement_id=ua.achievement_id,
            earned_at=ua.earned_at,
            is_notified=ua.is_notified,
            # 从关联的 achievement 对象中获取数据
            achievement_name=ua.achievement.name if ua.achievement else None,
            achievement_description=ua.achievement.description if ua.achievement else None,
            badge_url=ua.achievement.badge_url if ua.achievement else None,
            reward_points=ua.achievement.reward_points if ua.achievement else 0
        )
        response_list.append(response_data)

    print(f"DEBUG_ACHIEVEMENT_QUERY: 用户 {current_user_id} 获取到 {len(response_list)} 个成就。")
    return response_list
