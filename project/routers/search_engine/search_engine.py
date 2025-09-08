# project/routers/search_engine/search_engine.py
"""
搜索引擎路由模块 - 统一优化版本
提供搜索引擎配置管理和搜索功能
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

# 核心依赖
from project.database import get_db
from project.models import UserSearchEngineConfig
from project.utils import get_current_user_id
import project.schemas as schemas

# 优化工具导入
from project.services.search_service import (
    SearchEngineService, WebSearchService, InternalSearchService, SearchUtils
)
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search-engine", tags=["搜索引擎配置管理"])

# ===== 搜索配置管理 =====

@router.post("/config", response_model=schemas.UserSearchEngineConfigResponse, summary="创建搜索引擎配置")
@optimized_route("创建搜索配置")
@handle_database_errors
async def create_search_config(
    config_data: schemas.UserSearchEngineConfigCreate,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建搜索引擎配置 - 优化版本"""
    
    # 使用事务创建配置
    with database_transaction(db):
        config = SearchEngineService.create_search_config_optimized(
            db, config_data.dict(), current_user_id
        )
        
        # 异步检查连通性
        submit_background_task(
            background_tasks,
            "check_search_engine_connectivity",
            {
                "config_id": config.id,
                "engine_type": config.engine_type,
                "api_key": config.api_key,
                "base_url": config.base_url
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"用户 {current_user_id} 创建搜索配置 {config.id} 成功")
    return SearchUtils.format_search_config_response(config)

@router.get("/config", response_model=schemas.UserSearchEngineConfigResponse, summary="获取当前搜索配置")
@optimized_route("获取搜索配置")
@handle_database_errors
async def get_search_config(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取当前用户的搜索配置 - 优化版本"""
    
    config = SearchEngineService.get_user_config_optimized(db, current_user_id)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到搜索引擎配置"
        )
    
    return SearchUtils.format_search_config_response(config)

@router.post("/web-search", response_model=schemas.WebSearchResponse, summary="执行网络搜索")
@optimized_route("网络搜索")
@handle_database_errors
async def perform_web_search(
    background_tasks: BackgroundTasks,
    query: str = Query(..., min_length=2, description="搜索关键词"),
    count: int = Query(10, ge=1, le=50, description="返回结果数量"),
    market: str = Query("zh-CN", description="搜索市场"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """执行网络搜索 - 优化版本"""
    
    # 验证搜索查询
    cleaned_query = SearchUtils.validate_search_query(query)
    
    # 获取用户搜索配置
    config = SearchEngineService.get_user_config_optimized(db, current_user_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="请先配置搜索引擎"
        )
    
    try:
        # 执行搜索
        search_result = await WebSearchService.perform_web_search_optimized(
            cleaned_query, config, count, market
        )
        
        # 异步记录搜索日志
        submit_background_task(
            background_tasks,
            "log_search_activity",
            {
                "user_id": current_user_id,
                "query": cleaned_query,
                "engine_type": config.engine_type,
                "result_count": len(search_result.get("results", [])),
                "from_cache": search_result.get("from_cache", False)
            },
            priority=TaskPriority.LOW
        )
        
        logger.info(f"用户 {current_user_id} 执行网络搜索: {cleaned_query}")
        return search_result
        
    except Exception as e:
        logger.error(f"网络搜索失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )

@router.get("/internal-search", summary="内部内容搜索")
@optimized_route("内部内容搜索")
@handle_database_errors
async def search_internal_content(
    background_tasks: BackgroundTasks,
    query: str = Query(..., min_length=2, description="搜索关键词"),
    content_types: Optional[List[str]] = Query(None, description="内容类型过滤"),
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """搜索内部内容 - 优化版本"""
    
    # 验证搜索查询
    cleaned_query = SearchUtils.validate_search_query(query)
    
    # 默认搜索类型
    if content_types is None:
        content_types = ["topics", "projects", "notes"]
    
    # 验证内容类型
    valid_types = ["topics", "projects", "notes"]
    invalid_types = [t for t in content_types if t not in valid_types]
    if invalid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的内容类型: {invalid_types}"
        )
    
    # 执行内部搜索
    search_result = InternalSearchService.search_internal_content_optimized(
        db, cleaned_query, content_types, skip, limit
    )
    
    # 异步记录内部搜索日志
    submit_background_task(
        background_tasks,
        "log_internal_search_activity",
        {
            "user_id": current_user_id,
            "query": cleaned_query,
            "content_types": content_types,
            "result_count": search_result["total_found"]
        },
        priority=TaskPriority.LOW
    )
    
    logger.info(f"用户 {current_user_id or 'anonymous'} 执行内部搜索: {cleaned_query}")
    return search_result

# 使用路由优化器应用批量优化
# router_optimizer.apply_batch_optimizations(router, {
#     "cache_ttl": 300,
#     "enable_compression": True,
#     "rate_limit": "100/minute",
#     "monitoring": True
# })

logger.info("🔍 Search Engine - 搜索引擎路由已加载")
