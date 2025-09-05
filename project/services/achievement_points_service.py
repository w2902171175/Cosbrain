# project/services/achievement_points_service.py
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_
from typing import List, Optional, Dict, Any, Tuple
import logging
from datetime import datetime, timezone
from decimal import Decimal

from project.models.achievement_points import (
    Achievement, UserAchievement, PointTransaction, DEFAULT_ACHIEVEMENTS
)
from project.models.auth import User
from project.utils.core.common_utils import _check_and_award_achievements
from project.utils.async_cache.cache_manager import get_cache_manager_instance

# 获取缓存管理器实例
cache_manager = get_cache_manager_instance()

logger = logging.getLogger(__name__)


class AchievementPointsService:
    """成就积分综合服务类"""

    @staticmethod
    def initialize_default_achievements(db: Session) -> int:
        """
        初始化默认成就到数据库中，如果同名成就已存在则跳过。
        
        Args:
            db: 数据库会话
            
        Returns:
            int: 成功插入的成就数量
        """
        logger.info("开始检查并插入默认成就...")
        
        try:
            inserted_count = 0
            for achievement_data in DEFAULT_ACHIEVEMENTS:
                existing_achievement = db.query(Achievement).filter(
                    Achievement.name == achievement_data["name"]
                ).first()
                
                if existing_achievement:
                    logger.debug(f"成就 '{achievement_data['name']}' 已存在，跳过。")
                    continue

                new_achievement = Achievement(
                    name=achievement_data["name"],
                    description=achievement_data["description"],
                    criteria_type=achievement_data["criteria_type"],
                    criteria_value=achievement_data["criteria_value"],
                    badge_url=achievement_data["badge_url"],
                    reward_points=achievement_data["reward_points"],
                    is_active=achievement_data["is_active"]
                )
                db.add(new_achievement)
                logger.info(f"插入成就: {new_achievement.name}")
                inserted_count += 1

            db.commit()
            logger.info(f"默认成就初始化完成，共插入 {inserted_count} 个新成就。")
            return inserted_count
            
        except Exception as e:
            db.rollback()
            logger.error(f"初始化默认成就失败: {e}")
            raise

    @staticmethod
    def get_all_achievements(db: Session, active_only: bool = True) -> List[Achievement]:
        """
        获取所有成就列表
        
        Args:
            db: 数据库会话
            active_only: 是否只获取激活的成就
            
        Returns:
            List[Achievement]: 成就列表
        """
        query = db.query(Achievement)
        if active_only:
            query = query.filter(Achievement.is_active == True)
        return query.all()

    @staticmethod
    def get_achievement_by_id(db: Session, achievement_id: int) -> Optional[Achievement]:
        """
        根据ID获取成就
        
        Args:
            db: 数据库会话
            achievement_id: 成就ID
            
        Returns:
            Optional[Achievement]: 成就对象或None
        """
        return db.query(Achievement).filter(Achievement.id == achievement_id).first()

    @staticmethod
    async def check_user_achievements(db: Session, user_id: int):
        """
        检查并授予用户成就
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        """
        await _check_and_award_achievements(db, user_id)

    @staticmethod
    def create_custom_achievement(
        db: Session,
        name: str,
        description: str,
        criteria_type: str,
        criteria_value: float,
        badge_url: Optional[str] = None,
        reward_points: int = 0,
        is_active: bool = True
    ) -> Achievement:
        """
        创建自定义成就
        
        Args:
            db: 数据库会话
            name: 成就名称
            description: 成就描述
            criteria_type: 条件类型
            criteria_value: 条件值
            badge_url: 徽章URL
            reward_points: 奖励积分
            is_active: 是否激活
            
        Returns:
            Achievement: 创建的成就对象
        """
        # 检查名称是否已存在
        existing = db.query(Achievement).filter(Achievement.name == name).first()
        if existing:
            raise ValueError(f"成就名称 '{name}' 已存在")

        achievement = Achievement(
            name=name,
            description=description,
            criteria_type=criteria_type,
            criteria_value=criteria_value,
            badge_url=badge_url,
            reward_points=reward_points,
            is_active=is_active
        )
        
        db.add(achievement)
        db.commit()
        db.refresh(achievement)
        
        logger.info(f"创建自定义成就: {achievement.name}")
        return achievement

    @staticmethod
    def update_achievement(
        db: Session,
        achievement_id: int,
        **update_data
    ) -> Achievement:
        """
        更新成就信息
        
        Args:
            db: 数据库会话
            achievement_id: 成就ID
            **update_data: 更新的数据
            
        Returns:
            Achievement: 更新后的成就对象
        """
        achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
        if not achievement:
            raise ValueError(f"成就 ID {achievement_id} 不存在")

        # 如果更新名称，检查是否冲突
        if 'name' in update_data:
            existing = db.query(Achievement).filter(
                Achievement.name == update_data['name'],
                Achievement.id != achievement_id
            ).first()
            if existing:
                raise ValueError(f"成就名称 '{update_data['name']}' 已存在")

        # 更新字段
        for key, value in update_data.items():
            if hasattr(achievement, key):
                setattr(achievement, key, value)

        db.commit()
        db.refresh(achievement)
        
        logger.info(f"更新成就: {achievement.name}")
        return achievement

    @staticmethod
    def delete_achievement(db: Session, achievement_id: int) -> bool:
        """
        删除成就（软删除，设置为非激活状态）
        
        Args:
            db: 数据库会话
            achievement_id: 成就ID
            
        Returns:
            bool: 删除是否成功
        """
        achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
        if not achievement:
            return False

        achievement.is_active = False
        db.commit()
        
        logger.info(f"删除成就: {achievement.name}")
        return True

    @staticmethod
    async def get_achievement_definitions(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        active_only: bool = True
    ) -> Dict[str, Any]:
        """
        获取成就定义列表
        
        Args:
            db: 数据库会话
            page: 页码
            page_size: 每页大小
            active_only: 是否只获取激活的成就
            
        Returns:
            Dict[str, Any]: 分页的成就定义数据
        """
        # 构建缓存键
        cache_key = f"achievement_definitions:{page}:{page_size}:{active_only}"
        
        # 尝试从缓存获取
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"从缓存获取成就定义: page={page}")
            return cached_result

        # 计算偏移量
        offset = (page - 1) * page_size
        
        # 构建查询
        query = db.query(Achievement)
        if active_only:
            query = query.filter(Achievement.is_active == True)
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        achievements = query.order_by(Achievement.created_at.desc()).offset(offset).limit(page_size).all()
        
        # 构建返回数据
        result = {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "achievements": [
                {
                    "id": achievement.id,
                    "name": achievement.name,
                    "description": achievement.description,
                    "criteria_type": achievement.criteria_type,
                    "criteria_value": float(achievement.criteria_value),
                    "badge_url": achievement.badge_url,
                    "reward_points": achievement.reward_points,
                    "is_active": achievement.is_active,
                    "created_at": achievement.created_at.isoformat() if achievement.created_at else None
                }
                for achievement in achievements
            ]
        }
        
        # 缓存结果
        await cache_manager.set(cache_key, result, ttl=300)  # 5分钟缓存
        
        logger.info(f"获取成就定义列表: page={page}, total={total}")
        return result

    @staticmethod
    async def get_user_points(
        db: Session,
        user_id: int,
        include_history: bool = False
    ) -> Dict[str, Any]:
        """
        获取用户积分信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            include_history: 是否包含积分历史
            
        Returns:
            Dict[str, Any]: 用户积分信息
        """
        # 构建缓存键
        cache_key = f"user_points:{user_id}:{include_history}"
        
        # 尝试从缓存获取
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"从缓存获取用户积分: user_id={user_id}")
            return cached_result

        # 获取用户信息
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"用户 {user_id} 不存在")

        # 计算总积分和消费积分
        total_earned = db.query(func.sum(PointTransaction.amount)).filter(
            PointTransaction.user_id == user_id,
            PointTransaction.amount > 0
        ).scalar() or 0
        
        total_spent = abs(db.query(func.sum(PointTransaction.amount)).filter(
            PointTransaction.user_id == user_id,
            PointTransaction.amount < 0
        ).scalar() or 0)

        # 构建基本结果
        result = {
            "user_id": user_id,
            "total_points": user.total_points,
            "available_points": user.total_points,
            "lifetime_earned": total_earned,
            "lifetime_spent": total_spent,
            "last_updated": None  # 可以从最新的交易记录获取
        }
        
        # 如果需要包含历史记录
        if include_history:
            history = db.query(PointTransaction).filter(
                PointTransaction.user_id == user_id
            ).order_by(PointTransaction.created_at.desc()).limit(20).all()
            
            result["recent_history"] = [
                {
                    "id": record.id,
                    "action": "earn" if record.amount > 0 else "spend",
                    "points": record.amount,
                    "reason": record.reason,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                    "transaction_type": record.transaction_type
                }
                for record in history
            ]
            
            if history:
                result["last_updated"] = history[0].created_at.isoformat()
        
        # 缓存结果
        await cache_manager.set(cache_key, result, ttl=60)  # 1分钟缓存
        
        logger.info(f"获取用户积分信息: user_id={user_id}, points={user.total_points}")
        return result

    @staticmethod
    async def get_points_history(
        db: Session,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        action_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取用户积分历史记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            page: 页码
            page_size: 每页大小
            action_filter: 操作类型过滤
            
        Returns:
            Dict[str, Any]: 分页的积分历史数据
        """
        # 构建缓存键
        cache_key = f"points_history:{user_id}:{page}:{page_size}:{action_filter}"
        
        # 尝试从缓存获取
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"从缓存获取积分历史: user_id={user_id}, page={page}")
            return cached_result

        # 计算偏移量
        offset = (page - 1) * page_size
        
        # 构建查询
        query = db.query(PointTransaction).filter(PointTransaction.user_id == user_id)
        
        if action_filter:
            if action_filter == "earn":
                query = query.filter(PointTransaction.amount > 0)
            elif action_filter == "spend":
                query = query.filter(PointTransaction.amount < 0)
            else:
                query = query.filter(PointTransaction.transaction_type == action_filter)
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        history = query.order_by(PointTransaction.created_at.desc()).offset(offset).limit(page_size).all()
        
        # 构建返回数据
        result = {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "history": [
                {
                    "id": record.id,
                    "action": "earn" if record.amount > 0 else "spend",
                    "points": record.amount,
                    "reason": record.reason,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                    "transaction_type": record.transaction_type,
                    "related_entity_type": record.related_entity_type,
                    "related_entity_id": record.related_entity_id
                }
                for record in history
            ]
        }
        
        # 缓存结果
        await cache_manager.set(cache_key, result, ttl=180)  # 3分钟缓存
        
        logger.info(f"获取积分历史: user_id={user_id}, page={page}, total={total}")
        return result

    @staticmethod
    async def get_user_achievements(
        db: Session,
        user_id: int,
        include_locked: bool = False
    ) -> Dict[str, Any]:
        """
        获取用户成就信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            include_locked: 是否包含未解锁的成就
            
        Returns:
            Dict[str, Any]: 用户成就信息
        """
        # 构建缓存键
        cache_key = f"user_achievements:{user_id}:{include_locked}"
        
        # 尝试从缓存获取
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"从缓存获取用户成就: user_id={user_id}")
            return cached_result

        # 获取用户已获得的成就
        user_achievements = db.query(UserAchievement).filter(
            UserAchievement.user_id == user_id
        ).all()
        
        # 创建已获得成就的映射
        achieved_map = {ua.achievement_id: ua for ua in user_achievements}
        
        # 获取所有激活的成就定义
        all_achievements = db.query(Achievement).filter(
            Achievement.is_active == True
        ).all()
        
        # 构建结果
        achieved_achievements = []
        locked_achievements = []
        
        for achievement in all_achievements:
            if achievement.id in achieved_map:
                user_achievement = achieved_map[achievement.id]
                achieved_achievements.append({
                    "id": achievement.id,
                    "name": achievement.name,
                    "description": achievement.description,
                    "badge_url": achievement.badge_url,
                    "reward_points": achievement.reward_points,
                    "achieved_at": user_achievement.achieved_at.isoformat() if user_achievement.achieved_at else None,
                    "progress": 100  # 已完成
                })
            elif include_locked:
                locked_achievements.append({
                    "id": achievement.id,
                    "name": achievement.name,
                    "description": achievement.description,
                    "badge_url": achievement.badge_url,
                    "reward_points": achievement.reward_points,
                    "criteria_type": achievement.criteria_type,
                    "criteria_value": float(achievement.criteria_value),
                    "progress": 0  # 未开始
                })
        
        # 计算统计信息
        total_achievements = len(all_achievements)
        achieved_count = len(achieved_achievements)
        completion_rate = (achieved_count / total_achievements * 100) if total_achievements > 0 else 0
        
        result = {
            "user_id": user_id,
            "total_achievements": total_achievements,
            "achieved_count": achieved_count,
            "completion_rate": round(completion_rate, 2),
            "achieved_achievements": achieved_achievements
        }
        
        if include_locked:
            result["locked_achievements"] = locked_achievements
        
        # 缓存结果
        await cache_manager.set(cache_key, result, ttl=120)  # 2分钟缓存
        
        logger.info(f"获取用户成就: user_id={user_id}, achieved={achieved_count}/{total_achievements}")
        return result


class PointsService:
    """积分管理服务类"""

    @staticmethod
    async def add_points(
        db: Session,
        user_id: int,
        points: int,
        reason: str,
        details: Optional[str] = None,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None
    ) -> User:
        """
        为用户添加积分
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            points: 积分数量
            reason: 积分原因
            details: 详细信息
            related_entity_type: 关联实体类型
            related_entity_id: 关联实体ID
            
        Returns:
            User: 更新后的用户对象
        """
        from project.utils.core.common_utils import _award_points_to_user
        
        # 使用现有的积分奖励功能
        transaction = _award_points_to_user(
            db=db,
            user_id=user_id,
            amount=points,
            reason=reason,
            transaction_type="EARN",
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id
        )
        
        db.commit()
        
        # 获取更新后的用户对象
        user = db.query(User).filter(User.id == user_id).first()
        
        # 清除相关缓存
        await cache_manager.delete(f"user_points:{user_id}:*")
        await cache_manager.delete(f"points_history:{user_id}:*")

        logger.info(f"用户 {user_id} 获得 {points} 积分, 原因: {reason}")
        return user

    @staticmethod
    async def deduct_points(
        db: Session,
        user_id: int,
        points: int,
        reason: str,
        details: Optional[str] = None,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None
    ) -> User:
        """
        扣除用户积分
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            points: 积分数量
            reason: 扣除原因
            details: 详细信息
            related_entity_type: 关联实体类型
            related_entity_id: 关联实体ID
            
        Returns:
            User: 更新后的用户对象
        """
        from project.utils.core.common_utils import _award_points_to_user
        
        # 检查用户是否存在以及积分是否足够
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"用户 {user_id} 不存在")

        if user.total_points < points:
            raise ValueError(f"用户 {user_id} 积分不足")

        # 使用现有的积分系统扣除积分（负数）
        transaction = _award_points_to_user(
            db=db,
            user_id=user_id,
            amount=-points,
            reason=reason,
            transaction_type="SPEND",
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id
        )

        db.commit()
        
        # 获取更新后的用户对象
        user = db.query(User).filter(User.id == user_id).first()

        # 清除相关缓存
        await cache_manager.delete(f"user_points:{user_id}:*")
        await cache_manager.delete(f"points_history:{user_id}:*")

        logger.info(f"用户 {user_id} 消耗 {points} 积分, 原因: {reason}")
        return user


class AchievementPointsUtils:
    """成就积分工具类"""

    @staticmethod
    async def trigger_achievement_check(db: Session, user_id: int):
        """
        触发成就检查
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        """
        try:
            await _check_and_award_achievements(db, user_id)
            
            # 清除用户成就缓存
            await cache_manager.delete(f"user_achievements:{user_id}:*")
            
            logger.info(f"为用户 {user_id} 触发成就检查")
        except Exception as e:
            logger.error(f"成就检查失败 user_id={user_id}: {e}")

    @staticmethod
    def validate_points_amount(points: int) -> bool:
        """
        验证积分数量是否有效
        
        Args:
            points: 积分数量
            
        Returns:
            bool: 是否有效
        """
        return isinstance(points, int) and points > 0

    @staticmethod
    def format_achievement_progress(current: float, target: float) -> Dict[str, Any]:
        """
        格式化成就进度信息
        
        Args:
            current: 当前进度
            target: 目标值
            
        Returns:
            Dict[str, Any]: 进度信息
        """
        percentage = min((current / target * 100) if target > 0 else 0, 100)
        
        return {
            "current": current,
            "target": target,
            "percentage": round(percentage, 2),
            "completed": current >= target
        }

    @staticmethod
    async def get_leaderboard(
        db: Session,
        limit: int = 10,
        period: str = "all_time"
    ) -> List[Dict[str, Any]]:
        """
        获取积分排行榜
        
        Args:
            db: 数据库会话
            limit: 限制数量
            period: 时间段 (all_time, monthly, weekly)
            
        Returns:
            List[Dict[str, Any]]: 排行榜数据
        """
        # 构建缓存键
        cache_key = f"points_leaderboard:{limit}:{period}"
        
        # 尝试从缓存获取
        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"从缓存获取积分排行榜: period={period}")
            return cached_result

        # 查询用户积分信息，按总积分排序
        query = db.query(User).filter(
            User.total_points > 0
        ).order_by(
            desc(User.total_points)
        ).limit(limit)

        users = query.all()
        
        # 构建排行榜数据
        leaderboard = []
        for rank, user in enumerate(users, 1):
            # 计算用户的总获得积分
            lifetime_earned = db.query(func.sum(PointTransaction.amount)).filter(
                PointTransaction.user_id == user.id,
                PointTransaction.amount > 0
            ).scalar() or 0
            
            leaderboard.append({
                "rank": rank,
                "user_id": user.id,
                "username": user.username,
                "avatar_url": user.avatar_url,
                "total_points": user.total_points,
                "lifetime_earned": lifetime_earned
            })
        
        # 缓存结果
        await cache_manager.set(cache_key, leaderboard, ttl=600)  # 10分钟缓存
        
        logger.info(f"获取积分排行榜: period={period}, count={len(leaderboard)}")
        return leaderboard
