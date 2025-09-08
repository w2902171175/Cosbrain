# project/routers/admin/admin_service.py
"""
管理员业务逻辑服务层
分离业务逻辑和路由处理，提高代码的可测试性和可维护性
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import func, case
from fastapi import HTTPException, status

from project.models import User, Achievement, PointTransaction, KnowledgeDocument, KnowledgeDocumentChunk, Note
from project.utils import _award_points
import project.schemas as schemas

logger = logging.getLogger(__name__)


class AdminService:
    """管理员服务类"""
    
    @staticmethod
    def get_user_by_id_or_404(db: Session, user_id: int, error_message: str = "用户未找到") -> User:
        """获取用户或抛出404错误"""
        user: User = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.warning(f"用户未找到: {user_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
        return user
    
    @staticmethod
    def get_achievement_by_id_or_404(db: Session, achievement_id: int) -> Achievement:
        """获取成就或抛出404错误"""
        achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
        if not achievement:
            logger.warning(f"成就未找到: {achievement_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成就定义未找到")
        return achievement
    
    @staticmethod
    def check_achievement_name_conflict(db: Session, name: str, exclude_id: Optional[int] = None) -> None:
        """检查成就名称冲突"""
        query = db.query(Achievement).filter(Achievement.name == name)
        if exclude_id:
            query = query.filter(Achievement.id != exclude_id)
        
        if query.first():
            logger.warning(f"成就名称冲突: {name}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=f"成就名称 '{name}' 已存在"
            )
    
    @staticmethod
    async def set_user_admin_status(
        db: Session, 
        user_id: int, 
        admin_status: bool, 
        current_admin: User
    ) -> User:
        """设置用户管理员状态"""
        # 防止管理员取消自己的权限
        if current_admin.id == user_id and not admin_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="系统管理员不能取消自己的管理员权限"
            )
        
        # 获取目标用户
        target_user = AdminService.get_user_by_id_or_404(db, user_id, "目标用户未找到")
        
        try:
            target_user.is_admin = admin_status
            db.add(target_user)
            db.commit()
            db.refresh(target_user)
            
            logger.info(f"用户 {user_id} 的管理员权限已设置为 {admin_status}")
            return target_user
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"设置管理员权限失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="设置管理员权限失败"
            )
    
    @staticmethod
    async def create_achievement(
        db: Session, 
        achievement_data: schemas.AchievementCreate
    ) -> Achievement:
        """创建新成就"""
        # 检查名称冲突
        AdminService.check_achievement_name_conflict(db, achievement_data.name)
        
        new_achievement = Achievement(
            name=achievement_data.name,
            description=achievement_data.description,
            criteria_type=achievement_data.criteria_type,
            criteria_value=achievement_data.criteria_value,
            badge_url=achievement_data.badge_url,
            reward_points=achievement_data.reward_points,
            is_active=achievement_data.is_active
        )
        
        try:
            db.add(new_achievement)
            db.commit()
            db.refresh(new_achievement)
            
            logger.info(f"成功创建成就 ID: {new_achievement.id}")
            return new_achievement
            
        except IntegrityError:
            db.rollback()
            logger.error(f"创建成就失败：名称冲突 - {achievement_data.name}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail="创建成就失败，名称已存在"
            )
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"创建成就失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="创建成就失败"
            )
    
    @staticmethod
    async def update_achievement(
        db: Session, 
        achievement_id: int, 
        achievement_data: schemas.AchievementUpdate
    ) -> Achievement:
        """更新成就"""
        # 获取现有成就
        db_achievement = AdminService.get_achievement_by_id_or_404(db, achievement_id)
        
        # 获取更新数据
        update_data = achievement_data.dict(exclude_unset=True)
        
        # 检查名称冲突（如果要更新名称）
        if "name" in update_data and update_data["name"] != db_achievement.name:
            AdminService.check_achievement_name_conflict(db, update_data["name"], achievement_id)
        
        try:
            # 批量更新属性
            for key, value in update_data.items():
                setattr(db_achievement, key, value)
            
            db.add(db_achievement)
            db.commit()
            db.refresh(db_achievement)
            
            logger.info(f"成功更新成就 ID: {achievement_id}")
            return db_achievement
            
        except IntegrityError:
            db.rollback()
            logger.error(f"更新成就失败：名称冲突 - {update_data.get('name', '未知')}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail="更新成就失败，名称已被使用"
            )
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"更新成就失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="更新成就失败"
            )
    
    @staticmethod
    async def delete_achievement(db: Session, achievement_id: int) -> None:
        """删除成就"""
        # 获取成就
        db_achievement = AdminService.get_achievement_by_id_or_404(db, achievement_id)
        
        try:
            db.delete(db_achievement)
            db.commit()
            logger.info(f"成功删除成就 ID: {achievement_id}")
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"删除成就失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="删除成就失败"
            )
    
    @staticmethod
    async def adjust_user_points(
        db: Session,
        reward_request: schemas.PointsRewardRequest,
        admin_user: User
    ) -> PointTransaction:
        """调整用户积分"""
        # 获取目标用户
        target_user = AdminService.get_user_by_id_or_404(db, reward_request.user_id, "目标用户未找到")
        
        # 构建默认原因
        default_reason = f"管理员手动调整 (由 {admin_user.username} 操作)"
        reason = reward_request.reason or default_reason
        
        try:
            # 调用积分奖励辅助函数
            transaction = await _award_points(
                db=db,
                user=target_user,
                amount=reward_request.amount,
                reason=reason,
                transaction_type=reward_request.transaction_type,
                related_entity_type=reward_request.related_entity_type,
                related_entity_id=reward_request.related_entity_id
            )
            
            if transaction is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="积分调整数量不能为0"
                )
            
            # 提交事务
            db.commit()
            db.refresh(transaction)
            
            logger.info(f"成功调整用户 {target_user.id} 积分")
            return transaction
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"积分调整失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="积分调整失败"
            )
    
    @staticmethod
    def get_rag_statistics(db: Session) -> Dict[str, Any]:
        """获取RAG系统统计信息"""
        try:
            # 使用高效的聚合查询获取统计信息
            documents_stats = db.query(
                func.count(KnowledgeDocument.id).label('total'),
                func.sum(case([(KnowledgeDocument.status == 'completed', 1)], else_=0)).label('completed')
            ).first()
            
            chunks_stats = db.query(
                func.count(KnowledgeDocumentChunk.id).label('total'),
                func.sum(case([(KnowledgeDocumentChunk.embedding.isnot(None), 1)], else_=0)).label('with_embedding')
            ).first()
            
            notes_stats = db.query(
                func.count(Note.id).label('total'),
                func.sum(case([(Note.embedding.isnot(None), 1)], else_=0)).label('with_embedding')
            ).first()
            
            # 获取AI监控状态
            performance_metrics = AdminService._get_ai_monitoring_status()
            
            # 构建统计数据
            total_docs = documents_stats.total or 0
            completed_docs = documents_stats.completed or 0
            total_chunks = chunks_stats.total or 0
            chunks_with_emb = chunks_stats.with_embedding or 0
            total_notes = notes_stats.total or 0
            notes_with_emb = notes_stats.with_embedding or 0
            
            return {
                "status": "ok",
                "performance_metrics": performance_metrics,
                "data_statistics": {
                    "documents": {
                        "total": total_docs,
                        "completed": completed_docs,
                        "completion_rate": completed_docs / total_docs if total_docs > 0 else 0
                    },
                    "chunks": {
                        "total": total_chunks,
                        "with_embedding": chunks_with_emb,
                        "embedding_rate": chunks_with_emb / total_chunks if total_chunks > 0 else 0
                    },
                    "notes": {
                        "total": total_notes,
                        "with_embedding": notes_with_emb,
                        "embedding_rate": notes_with_emb / total_notes if total_notes > 0 else 0
                    }
                }
            }
            
        except SQLAlchemyError as e:
            logger.error(f"RAG状态检查数据库错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="RAG状态检查失败：数据库错误"
            )
    
    @staticmethod
    def _get_ai_monitoring_status() -> Dict[str, Any]:
        """获取AI监控状态"""
        try:
            from logs.ai_providers import ai_logger
            return {
                "status": "monitoring_enabled",
                "modules": ["ai_logger", "config_manager"],
                "last_check": "available"
            }
        except ImportError:
            return {
                "status": "monitoring_disabled", 
                "reason": "AI监控模块未安装",
                "modules": [],
                "last_check": "unavailable"
            }


class AdminValidators:
    """管理员数据验证器"""
    
    @staticmethod
    def validate_points_amount(amount: int) -> None:
        """验证积分数量"""
        if abs(amount) > 1000000:  # 设置合理的积分上限
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="积分调整数量超出允许范围 (-1,000,000 到 1,000,000)"
            )
    
    @staticmethod
    def validate_achievement_data(achievement_data: schemas.AchievementCreate) -> None:
        """验证成就数据"""
        if achievement_data.criteria_value is not None and achievement_data.criteria_value < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="成就条件值不能为负数"
            )
        
        if achievement_data.reward_points is not None and achievement_data.reward_points < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="奖励积分不能为负数"
            )
