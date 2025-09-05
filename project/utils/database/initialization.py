# project/utils/database/initialization.py
"""
数据库初始化工具模块
用于处理系统启动时的数据初始化任务
"""
from sqlalchemy.orm import Session
import logging

from project.services.achievement_points_service import AchievementPointsService

logger = logging.getLogger(__name__)


def initialize_system_data(db: Session) -> dict:
    """
    初始化系统基础数据
    
    Args:
        db: 数据库会话
        
    Returns:
        dict: 初始化结果统计
    """
    logger.info("开始初始化系统基础数据...")
    
    results = {
        "achievements_inserted": 0,
        "errors": []
    }
    
    try:
        # 初始化默认成就
        achievements_count = AchievementPointsService.initialize_default_achievements(db)
        results["achievements_inserted"] = achievements_count
        
        logger.info(f"系统基础数据初始化完成: {results}")
        
    except Exception as e:
        error_msg = f"系统数据初始化失败: {e}"
        logger.error(error_msg)
        results["errors"].append(error_msg)
        raise
        
    return results


def reset_achievements(db: Session) -> dict:
    """
    重置成就系统（删除所有成就并重新初始化）
    
    Args:
        db: 数据库会话
        
    Returns:
        dict: 重置结果统计
    """
    logger.warning("开始重置成就系统...")
    
    from project.models.achievement_points import Achievement, UserAchievement
    
    try:
        # 删除所有用户成就记录
        user_achievements_count = db.query(UserAchievement).count()
        db.query(UserAchievement).delete()
        
        # 删除所有成就定义
        achievements_count = db.query(Achievement).count()
        db.query(Achievement).delete()
        
        db.commit()
        
        # 重新初始化默认成就
        new_achievements_count = AchievementPointsService.initialize_default_achievements(db)
        
        results = {
            "deleted_user_achievements": user_achievements_count,
            "deleted_achievements": achievements_count,
            "new_achievements_inserted": new_achievements_count
        }
        
        logger.info(f"成就系统重置完成: {results}")
        return results
        
    except Exception as e:
        db.rollback()
        error_msg = f"成就系统重置失败: {e}"
        logger.error(error_msg)
        raise


def check_system_integrity(db: Session) -> dict:
    """
    检查系统数据完整性
    
    Args:
        db: 数据库会话
        
    Returns:
        dict: 检查结果
    """
    from project.models.achievement_points import Achievement, DEFAULT_ACHIEVEMENTS
    
    results = {
        "total_achievements_in_db": 0,
        "missing_default_achievements": [],
        "extra_achievements": [],
        "inactive_achievements": []
    }
    
    try:
        # 获取数据库中的所有成就
        db_achievements = db.query(Achievement).all()
        results["total_achievements_in_db"] = len(db_achievements)
        
        # 检查默认成就是否都存在
        db_achievement_names = {ach.name for ach in db_achievements}
        default_achievement_names = {ach["name"] for ach in DEFAULT_ACHIEVEMENTS}
        
        results["missing_default_achievements"] = list(
            default_achievement_names - db_achievement_names
        )
        
        # 查找非活跃的成就
        results["inactive_achievements"] = [
            ach.name for ach in db_achievements if not ach.is_active
        ]
        
        logger.info(f"系统完整性检查完成: {results}")
        
    except Exception as e:
        logger.error(f"系统完整性检查失败: {e}")
        raise
        
    return results
