# project/routers/mcp/mcp_optimized.py
"""
MCP模块优化版本 - 应用统一优化框架
基于成功优化模式，优化MCP模块的配置管理和连接功能
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

# 核心依赖
from project.database import get_db
from project.utils import get_current_user_id
from project.models import UserMcpConfig
import project.schemas as schemas

# 服务层导入
from project.services.mcp_service import (
    MCPConfigService, MCPConnectionService, MCPToolsService, MCPUtilities
)

# 优化工具导入
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/mcp", tags=["MCP模型上下文协议"])

# ===== MCP配置管理路由 =====

@router.get("/configs", response_model=List[schemas.UserMcpConfigResponse], summary="获取MCP配置列表")
@optimized_route("获取MCP配置列表")
@handle_database_errors
async def get_user_mcp_configs(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(50, ge=1, le=100, description="返回的记录数")
):
    """获取用户MCP配置列表 - 优化版本"""
    
    # 尝试从缓存获取
    cache_key = f"user_mcp_configs_{current_user_id}_{skip}_{limit}"
    cached_data = cache_manager.get(cache_key)
    if cached_data:
        return cached_data
    
    configs, total = MCPConfigService.get_user_configs_optimized(
        db, current_user_id, skip, limit
    )
    
    # 构建安全响应
    response_data = [
        MCPUtilities.build_safe_response_dict(config) for config in configs
    ]
    
    # 缓存结果
    cache_manager.set(cache_key, response_data, ttl=300)
    
    logger.info(f"用户 {current_user_id} 获取MCP配置列表: {len(configs)} 个配置")
    return response_data

@router.post("/configs", response_model=schemas.UserMcpConfigResponse, summary="创建MCP配置")
@optimized_route("创建MCP配置")
@handle_database_errors
async def create_mcp_config(
    config_data: schemas.UserMcpConfigCreate,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建MCP配置 - 优化版本"""
    
    with database_transaction(db):
        config = MCPConfigService.create_mcp_config_optimized(
            db, current_user_id, config_data.dict()
        )
        
        # 异步测试连接
        submit_background_task(
            background_tasks,
            MCPConnectionService.test_mcp_connection_optimized,
            TaskPriority.LOW,
            db, config.id, current_user_id
        )
        
        response_data = MCPUtilities.build_safe_response_dict(config)
        
        logger.info(f"用户 {current_user_id} 创建MCP配置: {config.id}")
        return response_data

@router.get("/configs/{config_id}", response_model=schemas.UserMcpConfigResponse, summary="获取MCP配置详情")
@optimized_route("获取MCP配置详情")
@handle_database_errors
async def get_mcp_config(
    config_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取MCP配置详情 - 优化版本"""
    
    # 尝试从缓存获取
    cache_key = f"mcp_config_{config_id}_{current_user_id}"
    cached_data = cache_manager.get(cache_key)
    if cached_data:
        return cached_data
    
    config = MCPConfigService.get_mcp_config_optimized(db, config_id, current_user_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCP配置未找到或无权访问"
        )
    
    response_data = MCPUtilities.build_safe_response_dict(config)
    
    # 缓存结果
    cache_manager.set(cache_key, response_data, ttl=600)
    
    logger.info(f"用户 {current_user_id} 获取MCP配置详情: {config_id}")
    return response_data

@router.put("/configs/{config_id}", response_model=schemas.UserMcpConfigResponse, summary="更新MCP配置")
@optimized_route("更新MCP配置")
@handle_database_errors
async def update_mcp_config(
    config_id: int,
    update_data: schemas.UserMcpConfigCreate,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新MCP配置 - 优化版本"""
    
    with database_transaction(db):
        config = MCPConfigService.update_mcp_config_optimized(
            db, config_id, current_user_id, update_data.dict(exclude_unset=True)
        )
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="MCP配置未找到或无权访问"
            )
        
        # 异步重新测试连接
        submit_background_task(
            background_tasks,
            MCPConnectionService.test_mcp_connection_optimized,
            TaskPriority.MEDIUM,
            db, config.id, current_user_id
        )
        
        response_data = MCPUtilities.build_safe_response_dict(config)
        
        logger.info(f"用户 {current_user_id} 更新MCP配置: {config_id}")
        return response_data

@router.delete("/configs/{config_id}", summary="删除MCP配置")
@optimized_route("删除MCP配置")
@handle_database_errors
async def delete_mcp_config(
    config_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除MCP配置 - 优化版本"""
    
    with database_transaction(db):
        success = MCPConfigService.delete_mcp_config_optimized(db, config_id, current_user_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="MCP配置未找到或无权访问"
            )
        
        logger.info(f"用户 {current_user_id} 删除MCP配置: {config_id}")
        return {"message": "MCP配置删除成功", "config_id": config_id}

# ===== MCP连接测试路由 =====

@router.post("/configs/{config_id}/test", response_model=schemas.McpStatusResponse, summary="测试MCP连接")
@optimized_route("测试MCP连接")
@handle_database_errors
async def test_mcp_connection(
    config_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """测试MCP连接状态 - 优化版本"""
    
    result = await MCPConnectionService.test_mcp_connection_optimized(
        db, config_id, current_user_id
    )
    
    # 构建响应
    status_response = schemas.McpStatusResponse(
        status=result.get("status", "error"),
        message=result.get("message", "未知错误"),
        timestamp=datetime.fromisoformat(result.get("timestamp", datetime.now().isoformat())),
        response_time=result.get("response_time")
    )
    
    logger.info(f"用户 {current_user_id} 测试MCP连接 {config_id}: {result['status']}")
    return status_response

@router.get("/configs/{config_id}/status", response_model=schemas.McpStatusResponse, summary="获取MCP连接状态")
@optimized_route("获取MCP连接状态")
@handle_database_errors
async def get_mcp_status(
    config_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取MCP连接状态 - 优化版本（从缓存返回）"""
    
    # 检查缓存的连接状态
    cache_key = f"mcp_connection_status_{config_id}"
    cached_status = cache_manager.get(cache_key)
    
    if cached_status:
        status_response = schemas.McpStatusResponse(
            status=cached_status.get("status", "unknown"),
            message=cached_status.get("message", "缓存状态"),
            timestamp=datetime.fromisoformat(cached_status.get("timestamp", datetime.now().isoformat())),
            response_time=cached_status.get("response_time")
        )
        return status_response
    
    # 如果没有缓存，返回未知状态
    return schemas.McpStatusResponse(
        status="unknown",
        message="连接状态未知，请先进行连接测试",
        timestamp=datetime.now()
    )

# ===== MCP工具管理路由 =====

@router.get("/configs/{config_id}/tools", response_model=List[schemas.McpToolDefinition], summary="获取MCP工具列表")
@optimized_route("获取MCP工具列表")
@handle_database_errors
async def get_mcp_tools(
    config_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取MCP工具列表 - 优化版本"""
    
    tools_data = await MCPToolsService.get_mcp_tools_optimized(
        db, config_id, current_user_id
    )
    
    # 转换为响应模型
    tools_list = []
    for tool in tools_data:
        try:
            tool_def = schemas.McpToolDefinition(**tool)
            tools_list.append(tool_def)
        except Exception as e:
            logger.warning(f"跳过无效的工具定义: {e}")
            continue
    
    logger.info(f"用户 {current_user_id} 获取MCP工具列表 (配置 {config_id}): {len(tools_list)} 个工具")
    return tools_list

# ===== 批量操作路由 =====

@router.post("/configs/batch-test", summary="批量测试MCP连接")
@optimized_route("批量测试MCP连接")
@handle_database_errors
async def batch_test_mcp_connections(
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    config_ids: List[int] = Query(..., description="要测试的配置ID列表")
):
    """批量测试MCP连接 - 优化版本"""
    
    if not config_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供要测试的配置ID列表"
        )
    
    if len(config_ids) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="一次最多只能测试20个配置"
        )
    
    # 异步执行所有连接测试
    for config_id in config_ids:
        submit_background_task(
            background_tasks,
            MCPConnectionService.test_mcp_connection_optimized,
            TaskPriority.LOW,
            db, config_id, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 启动批量MCP连接测试: {len(config_ids)} 个配置")
    return {
        "message": f"已启动 {len(config_ids)} 个MCP配置的连接测试",
        "config_ids": config_ids,
        "status": "testing_started"
    }

# ===== 统计和监控路由 =====

@router.get("/stats", summary="获取MCP统计信息")
@optimized_route("获取MCP统计信息")
@handle_database_errors
async def get_mcp_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取MCP统计信息 - 优化版本"""
    
    # 尝试从缓存获取
    cache_key = f"mcp_stats_{current_user_id}"
    cached_stats = cache_manager.get(cache_key)
    if cached_stats:
        return cached_stats
    
    # 计算统计信息
    total_configs = db.query(UserMcpConfig).filter(
        UserMcpConfig.owner_id == current_user_id
    ).count()
    
    active_configs = db.query(UserMcpConfig).filter(
        UserMcpConfig.owner_id == current_user_id,
        UserMcpConfig.is_active == True
    ).count()
    
    stats = {
        "total_configs": total_configs,
        "active_configs": active_configs,
        "inactive_configs": total_configs - active_configs,
        "last_updated": datetime.now().isoformat()
    }
    
    # 缓存统计信息
    cache_manager.set(cache_key, stats, ttl=300)
    
    logger.info(f"用户 {current_user_id} 获取MCP统计信息")
    return stats

# ===== 健康检查路由 =====

@router.get("/health", summary="MCP模块健康检查")
@optimized_route("MCP健康检查")
async def mcp_health_check():
    """MCP模块健康检查 - 优化版本"""
    
    health_status = {
        "service": "MCP",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0-optimized",
        "features": [
            "配置管理",
            "连接测试", 
            "工具列表",
            "批量操作",
            "性能监控",
            "缓存优化"
        ]
    }
    
    logger.info("MCP模块健康检查通过")
    return health_status

# 模块加载日志
logger.info("🔗 MCP Module - 模型上下文协议模块已加载")
