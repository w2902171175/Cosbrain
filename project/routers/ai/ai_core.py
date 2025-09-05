# project/routers/ai/ai_core.py
"""
AI模块优化版本 - 专项AI功能优化
基于成功优化模式，专门优化AI模块的核心功能
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query, Form
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Union, Literal
from datetime import datetime
import logging
import time

# 核心依赖
from project.database import get_db
from project.utils import get_current_user_id
import project.schemas as schemas
from pydantic import BaseModel, Field, validator, ConfigDict

# 优化工具导入
from project.services.ai_service import (
    AIConversationService, AIMessageService, AIChatService, 
    AISemanticSearchService, AIUtilities
)
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

# 导入AI配置
try:
    from project.ai_providers.ai_config import EnterpriseAIRouterConfig
    config = EnterpriseAIRouterConfig()
except ImportError:
    config = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI智能服务"])

# ===== 请求/响应模型 =====

class ChatRequest(BaseModel):
    """优化的聊天请求模型"""
    model_config = ConfigDict(protected_namespaces=())
    
    message: str = Field(..., max_length=10000, description="用户消息内容")
    conversation_id: Optional[int] = Field(None, description="对话ID")
    model_preference: Optional[str] = Field(None, description="偏好模型")
    temperature: float = Field(default=0.7, ge=0, le=2, description="生成温度")
    max_tokens: Optional[int] = Field(default=None, gt=0, le=8192, description="最大token数")
    tools_enabled: bool = Field(default=True, description="是否启用工具")
    rag_enabled: bool = Field(default=True, description="是否启用RAG检索")
    stream: bool = Field(default=False, description="是否流式响应")
    
    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError('消息内容不能为空')
        return v.strip()

class ChatResponse(BaseModel):
    """优化的聊天响应模型"""
    model_config = ConfigDict(protected_namespaces=())
    
    conversation_id: int
    user_message_id: int
    ai_message_id: int
    content: str
    model_used: str
    tokens_used: int
    response_time_ms: float
    tools_used: List[str] = []
    cached: bool = False

class SemanticSearchRequest(BaseModel):
    """语义搜索请求模型"""
    query: str = Field(..., min_length=1, max_length=1000)
    item_types: Optional[List[str]] = Field(default=None)
    limit: int = Field(default=10, ge=1, le=50)

# ===== AI聊天路由 =====

@router.post("/chat", response_model=ChatResponse, summary="AI智能对话")
@optimized_route("AI聊天")
@handle_database_errors
async def chat_with_ai(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """AI智能对话 - 优化版本"""
    
    start_time = time.time()
    
    # 验证请求数据
    chat_data = AIUtilities.validate_chat_request(request.dict())
    
    # 构建聊天选项
    options = {
        "model_preference": request.model_preference,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "tools_enabled": request.tools_enabled,
        "rag_enabled": request.rag_enabled,
        "stream": request.stream
    }
    
    # 使用事务处理聊天
    with database_transaction(db):
        result = await AIChatService.process_chat_optimized(
            db, current_user_id, request.message, 
            request.conversation_id, options
        )
        
        # 异步处理聊天后任务
        submit_background_task(
            background_tasks,
            "process_ai_chat_analytics",
            {
                "user_id": current_user_id,
                "conversation_id": result["conversation_id"],
                "message_length": len(request.message),
                "tools_used": result["metadata"].get("tools_used", [])
            },
            priority=TaskPriority.LOW
        )
    
    response_time = (time.time() - start_time) * 1000
    
    logger.info(f"用户 {current_user_id} AI聊天完成，耗时 {response_time:.2f}ms")
    
    return ChatResponse(
        conversation_id=result["conversation_id"],
        user_message_id=result["user_message_id"],
        ai_message_id=result["ai_message_id"],
        content=result["response"],
        model_used=result["metadata"].get("model_used", "unknown"),
        tokens_used=result["metadata"].get("tokens_used", 0),
        response_time_ms=response_time,
        tools_used=result["metadata"].get("tools_used", []),
        cached=result["metadata"].get("cached", False)
    )

@router.post("/chat/stream", summary="流式AI对话")
@optimized_route("流式AI聊天")
@handle_database_errors
async def stream_chat_with_ai(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """流式AI对话 - 优化版本"""
    
    # 强制启用流式模式
    request.stream = True
    
    # 处理与普通聊天相同，但返回流式响应
    # 这里简化处理，实际应该返回 StreamingResponse
    result = await chat_with_ai(request, background_tasks, current_user_id, db)
    
    return {"message": "流式响应功能开发中", "fallback_result": result}

# ===== 对话管理路由 =====

@router.get("/conversations", response_model=List[schemas.AIConversationResponse], summary="获取对话列表")
@optimized_route("获取对话列表")
@handle_database_errors
async def get_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户的AI对话列表 - 优化版本"""
    
    conversations, total = AIConversationService.get_conversations_optimized(
        db, current_user_id, limit, offset
    )
    
    return [AIUtilities.format_conversation_response(conv) for conv in conversations]

@router.post("/conversations", response_model=schemas.AIConversationResponse, summary="创建新对话")
@optimized_route("创建对话")
@handle_database_errors
async def create_conversation(
    title: Optional[str] = Form(None),
    initial_message: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建新对话 - 优化版本"""
    
    with database_transaction(db):
        conversation = AIConversationService.create_conversation_optimized(
            db, current_user_id, title, initial_message
        )
    
    logger.info(f"用户 {current_user_id} 创建对话 {conversation.id}")
    return AIUtilities.format_conversation_response(conversation)

@router.get("/conversations/{conversation_id}", response_model=schemas.AIConversationResponse, summary="获取对话详情")
@optimized_route("获取对话详情")
@handle_database_errors
async def get_conversation(
    conversation_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取对话详情 - 优化版本"""
    
    conversation = AIConversationService.get_conversation_optimized(
        db, conversation_id, current_user_id
    )
    
    return AIUtilities.format_conversation_response(conversation)

@router.put("/conversations/{conversation_id}", response_model=schemas.AIConversationResponse, summary="更新对话")
@optimized_route("更新对话")
@handle_database_errors
async def update_conversation(
    conversation_id: int,
    title: str = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新对话信息 - 优化版本"""
    
    with database_transaction(db):
        conversation = AIConversationService.update_conversation_optimized(
            db, conversation_id, current_user_id, title
        )
    
    logger.info(f"用户 {current_user_id} 更新对话 {conversation_id}")
    return AIUtilities.format_conversation_response(conversation)

@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除对话")
@optimized_route("删除对话")
@handle_database_errors
async def delete_conversation(
    conversation_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除对话 - 优化版本"""
    
    with database_transaction(db):
        AIConversationService.delete_conversation_optimized(
            db, conversation_id, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 删除对话 {conversation_id}")

# ===== 消息管理路由 =====

@router.get("/conversations/{conversation_id}/messages", response_model=List[schemas.AIConversationMessageResponse], summary="获取对话消息")
@optimized_route("获取对话消息")
@handle_database_errors
async def get_conversation_messages(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取对话消息列表 - 优化版本"""
    
    messages, total = AIMessageService.get_messages_optimized(
        db, conversation_id, current_user_id, limit, offset
    )
    
    return [AIUtilities.format_message_response(msg) for msg in messages]

@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除消息")
@optimized_route("删除消息")
@handle_database_errors
async def delete_message(
    message_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除消息 - 优化版本"""
    
    with database_transaction(db):
        AIMessageService.delete_message_optimized(db, message_id, current_user_id)
    
    logger.info(f"用户 {current_user_id} 删除消息 {message_id}")

# ===== 语义搜索路由 =====

@router.post("/semantic-search", response_model=List[Dict[str, Any]], summary="语义搜索")
@optimized_route("语义搜索")
@handle_database_errors
async def semantic_search(
    request: SemanticSearchRequest,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """智能语义搜索 - 优化版本"""
    
    results = await AISemanticSearchService.semantic_search_optimized(
        db, current_user_id, request.query, request.item_types, request.limit
    )
    
    # 异步记录搜索日志
    submit_background_task(
        background_tasks,
        "log_semantic_search",
        {
            "user_id": current_user_id,
            "query": request.query,
            "item_types": request.item_types,
            "result_count": len(results)
        },
        priority=TaskPriority.LOW
    )
    
    logger.info(f"用户 {current_user_id} 语义搜索 '{request.query}'：{len(results)} 个结果")
    return results

# ===== AI配置和状态路由 =====

@router.get("/config", summary="获取AI配置")
@optimized_route("获取AI配置")
@handle_database_errors
async def get_ai_config(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户AI配置 - 优化版本"""
    
    # 获取用户AI配置
    from project.models import User
    user = db.query(User).filter(User.id == current_user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return {
        "has_api_key": bool(user.llm_api_key_encrypted),
        "api_type": user.llm_api_type,
        "model_id": user.llm_model_id,
        "model_ids": user.llm_model_ids or [],
        "api_base_url": user.llm_api_base_url
    }

@router.get("/stats", summary="获取AI使用统计")
@optimized_route("AI使用统计")
@handle_database_errors
async def get_ai_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取AI使用统计 - 优化版本"""
    
    stats = AIUtilities.get_user_ai_stats(db, current_user_id)
    return stats

@router.get("/health", summary="AI服务健康检查")
@optimized_route("AI健康检查")
@handle_database_errors
async def health_check():
    """AI服务健康检查 - 优化版本"""
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "environment": "production"
    }
    
    # 检查AI服务组件
    try:
        from project.ai_providers.agent_orchestrator import AgentOrchestrator
        health_status["ai_orchestrator"] = "available"
    except ImportError:
        health_status["ai_orchestrator"] = "unavailable"
    
    try:
        from project.ai_providers.embedding_provider import get_embeddings_from_api
        health_status["embedding_service"] = "available"
    except ImportError:
        health_status["embedding_service"] = "unavailable"
    
    return health_status

# ===== 批量操作路由 =====

@router.post("/conversations/batch-delete", summary="批量删除对话")
@optimized_route("批量删除对话")
@handle_database_errors
async def batch_delete_conversations(
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    conversation_ids: List[int] = Form(...)
):
    """批量删除对话 - 优化版本"""
    
    if not conversation_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供要删除的对话ID列表"
        )
    
    if len(conversation_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="一次最多只能删除50个对话"
        )
    
    deleted_count = 0
    
    with database_transaction(db):
        for conversation_id in conversation_ids:
            try:
                AIConversationService.delete_conversation_optimized(
                    db, conversation_id, current_user_id
                )
                deleted_count += 1
            except HTTPException:
                # 跳过不存在或无权限的对话
                continue
        
        # 异步记录批量操作日志
        submit_background_task(
            background_tasks,
            "log_batch_operation",
            {
                "user_id": current_user_id,
                "operation": "batch_delete_conversations",
                "conversation_ids": conversation_ids,
                "success_count": deleted_count
            },
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 批量删除 {deleted_count} 个对话")
    return {
        "message": f"成功删除 {deleted_count} 个对话",
        "deleted_count": deleted_count,
        "total_requested": len(conversation_ids)
    }

# ===== 特殊AI功能路由 =====

@router.post("/summarize", summary="智能摘要")
@optimized_route("智能摘要")
@handle_database_errors
async def generate_summary(
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    text: str = Form(..., max_length=20000),
    summary_type: str = Form("brief", regex="^(brief|detailed|key_points)$")
):
    """生成智能摘要 - 优化版本"""
    
    if len(text.strip()) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文本内容至少需要100个字符"
        )
    
    # 构建摘要提示
    prompts = {
        "brief": "请为以下内容生成简要摘要：",
        "detailed": "请为以下内容生成详细摘要：",
        "key_points": "请提取以下内容的关键要点："
    }
    
    summary_prompt = f"{prompts[summary_type]}\n\n{text}"
    
    # 使用聊天服务生成摘要
    options = {
        "temperature": 0.3,  # 较低温度确保摘要准确性
        "max_tokens": 1000,
        "tools_enabled": False,  # 摘要不需要工具
        "rag_enabled": False    # 摘要不需要RAG
    }
    
    with database_transaction(db):
        result = await AIChatService.process_chat_optimized(
            db, current_user_id, summary_prompt, None, options
        )
        
        # 异步记录摘要使用
        submit_background_task(
            background_tasks,
            "log_ai_summary_usage",
            {
                "user_id": current_user_id,
                "text_length": len(text),
                "summary_type": summary_type,
                "summary_length": len(result["response"])
            },
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 生成 {summary_type} 摘要")
    return {
        "summary": result["response"],
        "summary_type": summary_type,
        "original_length": len(text),
        "summary_length": len(result["response"]),
        "compression_ratio": len(result["response"]) / len(text)
    }

# 使用路由优化器应用批量优化
# # router_optimizer.apply_batch_optimizations(router, {
# #     "cache_ttl": 300,
# #     "enable_compression": True,
# #     "rate_limit": "200/minute",  # AI功能需要更高限额
# #     "monitoring": True
# # })

logger.info("🧠 AI Core - AI核心模块已加载 (全功能版本)")
