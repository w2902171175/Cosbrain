# project/routers/quick_notes/quick_notes.py
"""
随手记录模块优化版本 - 应用统一优化模式
基于成功优化模式，优化quick_notes模块
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import logging

# 核心依赖
from project.database import get_db
from project.models import DailyRecord, User
from project.utils import get_current_user_id
import project.schemas as schemas

# 优化工具导入
from project.services.quick_notes_service import (
    QuickNotesService, QuickNotesUtils, QuickNotesEmbeddingService
)
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

# 工具函数导入
from project.utils import (
    generate_embedding_safe, get_user_resource_or_404, 
    debug_operation, update_embedding_safe
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/daily-records",
    tags=["随手记录"],
    responses={404: {"description": "Not found"}},
)

# ===== 辅助函数优化 =====

async def _build_combined_text_and_embedding_optimized(
    content: str, mood: str, tags: str, user_id: int
) -> Tuple[str, List[float]]:
    """
    构建组合文本并生成嵌入向量的辅助函数 - 优化版本
    
    Args:
        content: 记录内容
        mood: 心情
        tags: 标签
        user_id: 用户ID
    
    Returns:
        tuple: (combined_text, embedding)
    """
    # 使用专业服务类处理文本组合
    combined_text = QuickNotesUtils.build_combined_text(content, mood, tags)
    
    # 使用专业嵌入服务
    embedding = await QuickNotesEmbeddingService.generate_embedding_optimized(
        combined_text, user_id=user_id
    )
    
    logger.debug(f"随手记录嵌入向量已生成，用户ID: {user_id}")
    return combined_text, embedding

# ===== 核心API路由 =====

@router.post("/", response_model=schemas.DailyRecordResponse, summary="创建新随手记录")
@optimized_route("创建随手记录")
@handle_database_errors
async def create_daily_record(
    background_tasks: BackgroundTasks,
    record_data: schemas.DailyRecordBase,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新随手记录 - 优化版本
    后端会根据记录内容生成 combined_text 和 embedding，用于未来智能分析或搜索。
    """
    logger.info(f"用户 {current_user_id} 尝试创建随手记录")

    # 验证输入数据
    record_data_dict = QuickNotesUtils.validate_record_data(record_data.dict())
    
    # 使用事务创建记录
    with database_transaction(db):
        # 使用辅助函数构建组合文本和嵌入向量
        combined_text, embedding = await _build_combined_text_and_embedding_optimized(
            record_data.content, record_data.mood, record_data.tags, current_user_id
        )

        # 使用专业服务类创建记录
        db_record = QuickNotesService.create_record_optimized(
            db, current_user_id, record_data_dict, combined_text, embedding
        )
        
        # 异步处理后续任务
        submit_background_task(
            background_tasks,
            "process_quick_note_analytics",
            {"record_id": db_record.id, "user_id": current_user_id},
            priority=TaskPriority.LOW
        )

    logger.info(f"随手记录 (ID: {db_record.id}) 创建成功")
    return QuickNotesUtils.format_record_response(db_record)

@router.get("/", response_model=List[schemas.DailyRecordResponse], summary="获取当前用户所有随手记录")
@optimized_route("获取随手记录列表")
@handle_database_errors
async def get_all_daily_records(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    mood: Optional[str] = Query(None, description="心情过滤"),
    tag: Optional[str] = Query(None, description="标签过滤"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向")
):
    """
    获取当前用户的所有随手记录 - 优化版本
    可以通过心情（mood）或标签（tag）进行过滤，支持分页和排序。
    """
    logger.debug(f"获取用户 {current_user_id} 的随手记录列表，心情过滤: {mood}, 标签过滤: {tag}")
    
    # 使用专业服务类获取记录列表
    records, total_count = QuickNotesService.get_user_records_optimized(
        db, current_user_id, 
        page=page, page_size=page_size,
        mood=mood, tag=tag,
        sort_by=sort_by, sort_order=sort_order
    )
    
    # 格式化响应
    formatted_records = [QuickNotesUtils.format_record_response(record) for record in records]
    
    # 添加分页信息
    response = {
        "records": formatted_records,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total_count,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    }
    
    logger.debug(f"获取到 {len(records)} 条随手记录")
    return formatted_records

@router.get("/{record_id}", response_model=schemas.DailyRecordResponse, summary="获取指定随手记录详情")
@optimized_route("获取随手记录详情")
@handle_database_errors
async def get_daily_record_by_id(
    record_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取指定ID的随手记录详情 - 优化版本
    用户只能获取自己的记录。
    """
    debug_operation("获取随手记录详情", user_id=current_user_id, resource_id=record_id, resource_type="随手记录")
    
    # 使用专业服务类获取记录
    record = QuickNotesService.get_record_optimized(db, record_id, current_user_id)
    
    return QuickNotesUtils.format_record_response(record)

@router.put("/{record_id}", response_model=schemas.DailyRecordResponse, summary="更新指定随手记录")
@optimized_route("更新随手记录")
@handle_database_errors
async def update_daily_record(
    record_id: int,
    background_tasks: BackgroundTasks,
    record_data: schemas.DailyRecordBase,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    更新指定ID的随手记录内容 - 优化版本
    用户只能更新自己的记录。更新后会重新生成 combined_text 和 embedding。
    """
    logger.info(f"更新随手记录 ID: {record_id} 的内容，用户: {current_user_id}")
    
    # 验证输入数据
    update_data = QuickNotesUtils.validate_record_data(record_data.dict(exclude_unset=True))
    
    # 使用事务更新记录
    with database_transaction(db):
        # 使用专业服务类获取和更新记录
        db_record = QuickNotesService.get_record_optimized(db, record_id, current_user_id)
        
        # 更新字段
        for key, value in update_data.items():
            setattr(db_record, key, value)

        # 重新生成 combined_text 和 embedding
        combined_text, embedding = await _build_combined_text_and_embedding_optimized(
            db_record.content, db_record.mood, db_record.tags, current_user_id
        )
        
        db_record.combined_text = combined_text
        db_record.embedding = embedding
        
        # 保存更新
        QuickNotesService.save_record_optimized(db, db_record)
        
        # 异步处理更新后的分析
        submit_background_task(
            background_tasks,
            "analyze_updated_quick_note",
            {"record_id": record_id, "user_id": current_user_id},
            priority=TaskPriority.LOW
        )

    logger.info(f"随手记录 {db_record.id} 更新成功")
    return QuickNotesUtils.format_record_response(db_record)

@router.delete("/{record_id}", summary="删除指定随手记录")
@optimized_route("删除随手记录")
@handle_database_errors
async def delete_daily_record(
    record_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    删除指定ID的随手记录 - 优化版本
    用户只能删除自己的记录。
    """
    debug_operation("删除随手记录", user_id=current_user_id, resource_id=record_id, resource_type="随手记录")
    
    # 使用事务删除记录
    with database_transaction(db):
        # 使用专业服务类删除记录
        QuickNotesService.delete_record_optimized(db, record_id, current_user_id)

    logger.info(f"随手记录 {record_id} 删除成功")
    return {"message": "Daily record deleted successfully", "record_id": record_id}

# ===== 扩展功能API =====

@router.get("/analytics/summary", summary="获取随手记录分析摘要")
@optimized_route("获取记录分析")
@handle_database_errors
async def get_records_analytics(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="分析天数")
):
    """
    获取用户随手记录的分析摘要 - 优化版本
    包括心情趋势、标签分布、记录频率等统计信息
    """
    logger.info(f"获取用户 {current_user_id} 的随手记录分析摘要")
    
    # 使用专业服务类进行分析
    analytics = QuickNotesService.get_analytics_summary_optimized(
        db, current_user_id, days
    )
    
    return analytics

@router.post("/search", summary="搜索随手记录")
@optimized_route("搜索随手记录")
@handle_database_errors
async def search_daily_records(
    query: str = Query(..., description="搜索关键词"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = Query(10, ge=1, le=50, description="返回结果数量")
):
    """
    基于内容和嵌入向量搜索随手记录 - 优化版本
    支持语义搜索和关键词搜索
    """
    logger.info(f"用户 {current_user_id} 搜索随手记录，关键词: {query}")
    
    # 使用专业服务类进行搜索
    search_results = await QuickNotesService.search_records_optimized(
        db, current_user_id, query, limit
    )
    
    # 格式化搜索结果
    formatted_results = [
        {
            **QuickNotesUtils.format_record_response(record),
            "similarity_score": score
        }
        for record, score in search_results
    ]
    
    return {
        "query": query,
        "results": formatted_results,
        "total_found": len(formatted_results)
    }

@router.get("/export", summary="导出随手记录")
@optimized_route("导出随手记录")
@handle_database_errors
async def export_daily_records(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    format: str = Query("json", description="导出格式（json/csv/txt）"),
    date_from: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD")
):
    """
    导出用户的随手记录 - 优化版本
    支持多种格式和日期范围过滤
    """
    logger.info(f"用户 {current_user_id} 导出随手记录，格式: {format}")
    
    # 使用专业服务类进行导出
    export_data = QuickNotesService.export_records_optimized(
        db, current_user_id, format, date_from, date_to
    )
    
    return export_data

# 模块加载日志
logger.info("📒 Quick Notes Module - 随手记录模块已加载（统一优化版本）")
