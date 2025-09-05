# project/routers/llm.py
"""
LLM模块路由层 - 优化版本
集成优化框架提供高性能的LLM配置管理、对话管理和推理API
支持分布式缓存、流式响应、负载均衡等高级功能
"""
from typing import Optional, List, Dict, Any, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json
import asyncio
import logging
from datetime import datetime, timedelta

# 核心导入
from project.database import get_db
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route
import project.schemas as schemas
from project.services.llm_service import (
    LLMProviderService, LLMConfigService, LLMConversationService, 
    LLMInferenceService, LLMMonitoringService, LLMUtilities
)

# 工具导入
from project.utils.optimization.production_utils import cache_manager
from project.utils import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/llm", tags=["LLM大语言模型"])

# ===== LLM提供商管理路由 =====

@router.get("/providers", response_model=schemas.PaginatedResponse)
@optimized_route
@handle_database_errors
async def get_llm_providers(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(50, ge=1, le=100, description="返回的记录数"),
    provider_type: Optional[str] = Query(None, description="提供商类型过滤"),
    is_active: Optional[bool] = Query(None, description="活跃状态过滤"),
    db: Session = Depends(get_db)
):
    """
    获取LLM提供商列表
    
    - **skip**: 分页跳过的记录数
    - **limit**: 返回的记录数量限制  
    - **provider_type**: 按提供商类型过滤
    - **is_active**: 按活跃状态过滤
    """
    try:
        # 检查缓存
        cache_key = f"llm_providers_{skip}_{limit}_{provider_type}_{is_active}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        providers, total = LLMProviderService.get_llm_providers_optimized(
            db, skip, limit, provider_type, is_active
        )
        
        # 构建响应
        provider_list = [{
            "id": p.id,
            "name": p.name,
            "provider_type": p.provider_type,
            "base_url": p.base_url,
            "is_active": p.is_active,
            "supported_models": getattr(p, 'supported_models', []),
            "created_at": p.created_at
        } for p in providers]
        
        result = {
            "items": provider_list,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, ttl=600)  # 10分钟缓存
        
        logger.info(f"获取LLM提供商列表: {len(provider_list)} 个提供商")
        return result
        
    except Exception as e:
        logger.error(f"获取LLM提供商列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取LLM提供商列表失败")

@router.post("/providers", response_model=schemas.Response)
@optimized_route
@handle_database_errors
@database_transaction
async def create_llm_provider(
    provider_data: Dict[str, Any] = Body(..., description="LLM提供商数据"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    创建新的LLM提供商
    
    - **provider_data**: LLM提供商数据，包含名称、类型、API地址等
    """
    try:
        # 创建提供商
        new_provider = LLMProviderService.create_llm_provider_optimized(
            db, provider_data
        )
        
        # 后台任务：清理相关缓存
        background_tasks.add_task(
            cache_manager.delete_pattern, 
            "llm_providers_*"
        )
        
        result = {
            "id": new_provider.id,
            "name": new_provider.name,
            "provider_type": new_provider.provider_type,
            "base_url": new_provider.base_url,
            "is_active": new_provider.is_active,
            "created_at": new_provider.created_at
        }
        
        logger.info(f"用户 {current_user_id} 创建LLM提供商: {new_provider.name}")
        return {
            "message": "LLM提供商创建成功",
            "data": result
        }
        
    except ValueError as e:
        logger.warning(f"LLM提供商创建参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建LLM提供商失败: {e}")
        raise HTTPException(status_code=500, detail="创建LLM提供商失败")

# ===== 用户LLM配置管理路由 =====

@router.get("/configs", response_model=schemas.PaginatedResponse)
@optimized_route
@handle_database_errors
async def get_user_llm_configs(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(50, ge=1, le=100, description="返回的记录数"),
    provider_type: Optional[str] = Query(None, description="提供商类型过滤"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取用户LLM配置列表
    
    - **skip**: 分页跳过的记录数
    - **limit**: 返回的记录数量限制
    - **provider_type**: 按提供商类型过滤
    """
    try:
        # 检查缓存
        cache_key = f"user_llm_configs_{current_user_id}_{skip}_{limit}_{provider_type}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        configs, total = LLMConfigService.get_user_llm_configs_optimized(
            db, current_user_id, skip, limit, provider_type
        )
        
        # 构建响应
        config_list = [LLMUtilities.build_safe_response_dict(config) for config in configs]
        result = {
            "items": config_list,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, ttl=300)  # 5分钟缓存
        
        logger.info(f"用户 {current_user_id} 获取LLM配置列表: {len(config_list)} 个配置")
        return result
        
    except Exception as e:
        logger.error(f"获取LLM配置列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取LLM配置列表失败")

@router.post("/configs", response_model=schemas.Response)
@optimized_route
@handle_database_errors
@database_transaction
async def create_llm_config(
    config_data: Dict[str, Any] = Body(..., description="LLM配置数据"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    创建新的LLM配置
    
    - **config_data**: LLM配置数据，包含提供商ID、配置名称、模型参数等
    """
    try:
        # 创建配置
        new_config = LLMConfigService.create_llm_config_optimized(
            db, current_user_id, config_data
        )
        
        # 后台任务：清理相关缓存
        background_tasks.add_task(
            LLMUtilities.clear_user_cache, 
            current_user_id
        )
        
        result = LLMUtilities.build_safe_response_dict(new_config)
        
        logger.info(f"用户 {current_user_id} 创建LLM配置 {new_config.id}")
        return {
            "message": "LLM配置创建成功",
            "data": result
        }
        
    except ValueError as e:
        logger.warning(f"LLM配置创建参数错误: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建LLM配置失败: {e}")
        raise HTTPException(status_code=500, detail="创建LLM配置失败")

# ===== 对话管理路由 =====

@router.get("/conversations", response_model=schemas.PaginatedResponse)
@optimized_route
@handle_database_errors
async def get_user_conversations(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(50, ge=1, le=100, description="返回的记录数"),
    with_messages: bool = Query(False, description="是否包含消息内容"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取用户对话列表
    
    - **skip**: 分页跳过的记录数
    - **limit**: 返回的记录数量限制
    - **with_messages**: 是否包含消息内容
    """
    try:
        # 检查缓存
        cache_key = f"user_conversations_{current_user_id}_{skip}_{limit}_{with_messages}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        conversations, total = LLMConversationService.get_user_conversations_optimized(
            db, current_user_id, skip, limit, with_messages
        )
        
        # 构建响应
        conversation_list = []
        for conv in conversations:
            conv_dict = {
                "id": conv.id,
                "title": conv.title,
                "model_name": conv.model_name,
                "message_count": len(conv.messages) if hasattr(conv, 'messages') else 0,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at
            }
            
            if with_messages and hasattr(conv, 'messages'):
                conv_dict["messages"] = [{
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at
                } for msg in conv.messages]
            
            conversation_list.append(conv_dict)
        
        result = {
            "items": conversation_list,
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + limit < total
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, ttl=180)  # 3分钟缓存
        
        logger.info(f"用户 {current_user_id} 获取对话列表: {len(conversation_list)} 个对话")
        return result
        
    except Exception as e:
        logger.error(f"获取对话列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取对话列表失败")

@router.post("/conversations", response_model=schemas.Response)
@optimized_route
@handle_database_errors
@database_transaction
async def create_conversation(
    conversation_data: Dict[str, Any] = Body(..., description="对话数据"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    创建新的对话
    
    - **conversation_data**: 对话数据，包含标题、模型名称、系统提示等
    """
    try:
        # 创建对话
        new_conversation = LLMConversationService.create_conversation_optimized(
            db, current_user_id, conversation_data
        )
        
        # 后台任务：清理相关缓存
        background_tasks.add_task(
            cache_manager.delete_pattern, 
            f"user_conversations_{current_user_id}_*"
        )
        
        result = {
            "id": new_conversation.id,
            "title": new_conversation.title,
            "model_name": new_conversation.model_name,
            "system_prompt": new_conversation.system_prompt,
            "created_at": new_conversation.created_at
        }
        
        logger.info(f"用户 {current_user_id} 创建对话 {new_conversation.id}")
        return {
            "message": "对话创建成功",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"创建对话失败: {e}")
        raise HTTPException(status_code=500, detail="创建对话失败")

# ===== LLM推理路由 =====

@router.post("/chat", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def chat_with_llm(
    chat_request: Dict[str, Any] = Body(
        ..., 
        description="聊天请求",
        example={
            "content": "你好，请介绍一下你自己",
            "conversation_id": None,
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 2048,
            "system_prompt": "你是一个有帮助的AI助手"
        }
    ),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    与LLM进行对话
    
    - **content**: 消息内容
    - **conversation_id**: 对话ID（可选，新对话则不传）
    - **model**: 使用的模型名称
    - **temperature**: 温度参数
    - **max_tokens**: 最大生成长度
    - **system_prompt**: 系统提示（可选）
    """
    try:
        # 验证请求参数
        content = chat_request.get("content")
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        
        conversation_id = chat_request.get("conversation_id")
        
        # 执行LLM推理
        response = await LLMInferenceService.generate_response_optimized(
            db, current_user_id, conversation_id, chat_request, stream=False
        )
        
        if response.get("status") == "error":
            raise HTTPException(
                status_code=400, 
                detail=response.get("message", "LLM推理失败")
            )
        
        # 后台任务：清理相关缓存
        background_tasks.add_task(
            cache_manager.delete_pattern, 
            f"user_conversations_{current_user_id}_*"
        )
        
        logger.info(f"用户 {current_user_id} 完成LLM对话，对话ID: {response.get('conversation_id')}")
        return {
            "message": "对话成功",
            "data": response
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LLM对话失败: {e}")
        raise HTTPException(status_code=500, detail="LLM对话服务错误")

@router.post("/chat/stream")
@optimized_route
@handle_database_errors
async def chat_with_llm_stream(
    chat_request: Dict[str, Any] = Body(..., description="流式聊天请求"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    与LLM进行流式对话
    
    - **content**: 消息内容
    - **conversation_id**: 对话ID（可选）
    - **model**: 使用的模型名称
    - **temperature**: 温度参数
    - **max_tokens**: 最大生成长度
    """
    try:
        # 验证请求参数
        content = chat_request.get("content")
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        
        conversation_id = chat_request.get("conversation_id")
        
        async def generate_stream():
            try:
                # 执行流式推理
                response = await LLMInferenceService.generate_response_optimized(
                    db, current_user_id, conversation_id, chat_request, stream=True
                )
                
                if response.get("status") == "error":
                    yield f"data: {json.dumps({'error': response.get('message')})}\n\n"
                    return
                
                # 模拟流式输出
                full_response = response.get("response", "")
                words = full_response.split()
                
                for i, word in enumerate(words):
                    chunk_data = {
                        "content": word + (" " if i < len(words) - 1 else ""),
                        "conversation_id": response.get("conversation_id"),
                        "finished": i == len(words) - 1
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    
                    # 模拟延迟
                    await asyncio.sleep(0.05)
                
                # 发送结束标志
                yield f"data: {json.dumps({'finished': True, 'conversation_id': response.get('conversation_id')})}\n\n"
                
            except Exception as e:
                logger.error(f"流式对话生成失败: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"流式LLM对话失败: {e}")
        raise HTTPException(status_code=500, detail="流式LLM对话服务错误")

# ===== 监控和统计路由 =====

@router.get("/statistics", response_model=schemas.Response)
@optimized_route
@handle_database_errors
async def get_llm_statistics(
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取LLM使用统计
    
    - **start_date**: 统计开始日期
    - **end_date**: 统计结束日期
    """
    try:
        # 解析日期参数
        start_dt = None
        end_dt = None
        
        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        
        # 检查缓存
        cache_key = f"llm_stats_{current_user_id}_{start_date}_{end_date}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 获取统计数据
        stats = await LLMMonitoringService.get_usage_statistics_optimized(
            db, current_user_id, start_dt, end_dt
        )
        
        result = {
            "message": "获取LLM统计成功",
            "data": stats
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, ttl=1800)  # 30分钟缓存
        
        return result
        
    except ValueError as e:
        logger.warning(f"日期参数错误: {e}")
        raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD 格式")
    except Exception as e:
        logger.error(f"获取LLM统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取LLM统计失败")

@router.get("/health", response_model=schemas.Response)
@optimized_route
async def llm_health_check():
    """LLM模块健康检查"""
    try:
        # 检查缓存连接
        cache_status = "healthy" if cache_manager.is_connected() else "error"
        
        health_data = {
            "status": "healthy",
            "module": "LLM",
            "timestamp": datetime.now().isoformat(),
            "cache_status": cache_status,
            "distributed_cache": "enabled",
            "features": [
                "对话管理",
                "流式响应", 
                "多提供商支持",
                "分布式缓存",
                "使用统计"
            ],
            "version": "2.0.0"
        }
        
        logger.info("LLM模块健康检查")
        return {
            "message": "LLM模块运行正常",
            "data": health_data
        }
        
    except Exception as e:
        logger.error(f"LLM健康检查失败: {e}")
        return {
            "message": "LLM模块健康检查异常",
            "data": {
                "status": "error",
                "error": str(e)
            }
        }

# 模块加载日志
logger.info("🤖 LLM Module - 大语言模型模块已加载")
