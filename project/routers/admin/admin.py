# project/routers/admin/admin.py
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Literal, Optional

# 使用正确的相对导入
from database import get_db
from models.models import Student, Achievement, PointTransaction, KnowledgeArticle, KnowledgeDocument, KnowledgeDocumentChunk, Note
from dependencies.dependencies import get_current_user_id, is_admin_user
from utils.utils import _award_points
import schemas.schemas as schemas

router = APIRouter(prefix="/admin", tags=["管理员"])


@router.put("/users/{user_id}/set-admin", response_model=schemas.StudentResponse,
         summary="【管理员专用】设置系统管理员权限")
async def set_user_admin_status(
        user_id: int,  # 目标用户ID
        admin_status: schemas.UserAdminStatusUpdate,  # 包含 is_admin 值
        current_user_id: str = Depends(get_current_user_id),  # 已认证的系统管理员ID
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)  # 转换为整数

    print(f"DEBUG_ADMIN: 管理员 {current_user_id_int} 尝试设置用户 {user_id} 的管理员权限为 {admin_status.is_admin}。")

    try:
        # 1. 验证操作者是否为系统管理员
        current_admin = db.query(Student).filter(Student.id == current_user_id_int).first()
        if not current_admin or not current_admin.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权执行此操作。只有系统管理员才能设置用户管理员权限。")

        # 2. 查找目标用户
        target_user = db.query(Student).filter(Student.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户未找到。")

        # 3. 不允许系统管理员取消自己的系统管理员权限 (防止误操作导致失去最高权限)
        if current_user_id_int == user_id and not admin_status.is_admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="系统管理员不能取消自己的管理员权限。请联系其他系统管理员协助。")

        # 4. 更新目标用户的管理员状态
        target_user.is_admin = admin_status.is_admin
        db.add(target_user)
        db.commit()
        db.refresh(target_user)

        print(f"DEBUG_ADMIN: 用户 {user_id} 的管理员权限已成功设置为 {admin_status.is_admin}。")
        return target_user

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 设置管理员权限失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"设置管理员权限失败: {e}")


@router.post("/achievements/definitions", response_model=schemas.AchievementResponse, summary="【管理员专用】创建新的成就定义")
async def create_achievement_definition(
        achievement_data: schemas.AchievementCreate,
        # 只有管理员才能访问此接口
        current_admin_user: Student = Depends(is_admin_user),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 尝试创建成就：{achievement_data.name}")

    # 检查成就名称是否已存在
    existing_achievement = db.query(Achievement).filter(Achievement.name == achievement_data.name).first()
    if existing_achievement:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"成就名称 '{achievement_data.name}' 已存在。")

    new_achievement = Achievement(
        name=achievement_data.name,
        description=achievement_data.description,
        criteria_type=achievement_data.criteria_type,
        criteria_value=achievement_data.criteria_value,
        badge_url=achievement_data.badge_url,
        reward_points=achievement_data.reward_points,
        is_active=achievement_data.is_active
    )

    db.add(new_achievement)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建成就定义发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建成就定义失败，可能存在名称冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 创建成就定义失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建成就定义失败: {e}")

    db.refresh(new_achievement)
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 成功创建成就 ID: {new_achievement.id}.")
    return new_achievement


@router.put("/achievements/definitions/{achievement_id}", response_model=schemas.AchievementResponse,
         summary="【管理员专用】更新指定成就定义")
async def update_achievement_definition(
        achievement_id: int,
        achievement_data: schemas.AchievementUpdate,
        current_admin_user: Student = Depends(is_admin_user),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 尝试更新成就 ID: {achievement_id}")

    db_achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not db_achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成就定义未找到。")

    update_data = achievement_data.dict(exclude_unset=True)

    # 如果尝试改变名称，检查新名称是否冲突
    if "name" in update_data and update_data["name"] is not None and update_data["name"] != db_achievement.name:
        existing_name_achievement = db.query(Achievement).filter(
            Achievement.name == update_data["name"],
            Achievement.id != achievement_id
        ).first()
        if existing_name_achievement:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"成就名称 '{update_data['name']}' 已被使用。")

    for key, value in update_data.items():
        setattr(db_achievement, key, value)

    db.add(db_achievement)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新成就定义发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新成就定义失败，可能存在名称冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 更新成就定义失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新成就定义失败: {e}")

    db.refresh(db_achievement)
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 成功更新成就 ID: {achievement_id}.")
    return db_achievement


@router.delete("/achievements/definitions/{achievement_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="【管理员专用】删除指定成就定义")
async def delete_achievement_definition(
        achievement_id: int,
        current_admin_user: Student = Depends(is_admin_user),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 尝试删除成就 ID: {achievement_id}")

    db_achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not db_achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成就定义未找到。")

    # 删除成就定义也将删除所有用户获得的该成就记录 (UserAchievement)
    # 如果希望保留用户获得的成就记录但禁用成就，应使用 PUT 接口将 is_active 设为 False
    db.delete(db_achievement)
    db.commit()
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 成功删除成就 ID: {achievement_id}。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/points/reward", response_model=schemas.PointTransactionResponse,
          summary="【管理员专用】为指定用户手动发放/扣除积分")
async def admin_reward_or_deduct_points(
        reward_request: schemas.PointsRewardRequest,  # 接收积分变动请求
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能操作
        db: Session = Depends(get_db)
):
    """
    管理员可以手动为指定用户发放或扣除积分。
    """
    print(
        f"DEBUG_ADMIN_POINTS: 管理员 {current_admin_user.id} 尝试为用户 {reward_request.user_id} 手动调整积分：{reward_request.amount}")

    target_user = db.query(Student).filter(Student.id == reward_request.user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户未找到。")

    # 调用积分奖励辅助函数
    await _award_points(
        db=db,
        user=target_user,
        amount=reward_request.amount,
        reason=reward_request.reason or f"管理员手动调整 (由{current_admin_user.username})",
        transaction_type=reward_request.transaction_type,
        related_entity_type=reward_request.related_entity_type,
        related_entity_id=reward_request.related_entity_id
    )
    # 刷新并获取最新的交易记录（或直接返回 _award_points 生成的 transaction 对象）
    # 这里为了返回 PointsRewardRequest 的响应类型，通常需要重新查询或构建
    # 假设 _award_points 内部会commit并生成事务对象，这里查询最新的那个
    latest_transaction = db.query(PointTransaction).filter(
        PointTransaction.user_id == target_user.id
    ).order_by(PointTransaction.created_at.desc()).first()

    print(f"DEBUG_ADMIN_POINTS: 管理员 {current_admin_user.id} 成功调整用户 {target_user.id} 积分。")
    return latest_transaction  # 返回最新的交易记录


@router.get("/rag/status", summary="RAG功能状态检查（管理员）")
async def get_rag_status(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    检查RAG功能的整体状态和性能指标（仅管理员可访问）
    """
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问此功能")

    try:
        # from rag_utils import rag_monitor
        # stats = rag_monitor.get_stats()
        # 暂时注释掉rag_utils导入，提供基本统计
        stats = {"status": "rag_utils module not available"}

        # 统计系统整体数据
        total_articles = db.query(KnowledgeArticle).count()
        articles_with_embedding = db.query(KnowledgeArticle).filter(KnowledgeArticle.embedding.isnot(None)).count()
        total_documents = db.query(KnowledgeDocument).count()
        completed_documents = db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "completed").count()
        total_chunks = db.query(KnowledgeDocumentChunk).count()
        chunks_with_embedding = db.query(KnowledgeDocumentChunk).filter(
            KnowledgeDocumentChunk.embedding.isnot(None)).count()
        total_notes = db.query(Note).count()
        notes_with_embedding = db.query(Note).filter(Note.embedding.isnot(None)).count()

        return {
            "status": "ok",
            "performance_metrics": stats,
            "data_statistics": {
                "articles": {
                    "total": total_articles,
                    "with_embedding": articles_with_embedding,
                    "embedding_rate": articles_with_embedding / total_articles if total_articles > 0 else 0
                },
                "documents": {
                    "total": total_documents,
                    "completed": completed_documents,
                    "completion_rate": completed_documents / total_documents if total_documents > 0 else 0
                },
                "chunks": {
                    "total": total_chunks,
                    "with_embedding": chunks_with_embedding,
                    "embedding_rate": chunks_with_embedding / total_chunks if total_chunks > 0 else 0
                },
                "notes": {
                    "total": total_notes,
                    "with_embedding": notes_with_embedding,
                    "embedding_rate": notes_with_embedding / total_notes if total_notes > 0 else 0
                }
            }
        }
    except ImportError:
        return {
            "status": "monitoring_unavailable",
            "message": "RAG监控模块未启用"
        }
