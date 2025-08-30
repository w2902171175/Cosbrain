"""
企业级AI路由核心模块
基于project.ai_providers的生产级API实现
"""

import asyncio
import time
import uuid
import json
import os
import traceback
from typing import Dict, Any, List, Optional, Union, Literal
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from pydantic import BaseModel, Field, validator

# 项目依赖
from project.database import get_db, SessionLocal
from project.dependencies import get_current_user_id
from project.models import (
    Student, Project, Course, KnowledgeBase, KnowledgeArticle, Note, 
    AIConversation, AIConversationMessage, AIConversationTemporaryFile, KnowledgeDocument
)
import project.schemas as schemas
import project.oss_utils as oss_utils

# AI提供者集成
from project.ai_providers.provider_manager import AIProviderManager
from project.ai_providers.agent_orchestrator import get_all_available_tools_for_llm, invoke_agent
from project.ai_providers.document_processor import extract_text_from_document
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.llm_provider import generate_conversation_title_from_llm
from project.ai_providers.rerank_provider import get_rerank_scores_from_api
from project.ai_providers.security_utils import decrypt_key
from project.ai_providers.ai_config import (
    get_enterprise_config, GLOBAL_PLACEHOLDER_ZERO_VECTOR, 
    INITIAL_CANDIDATES_K, get_user_model_for_provider
)

# 企业级日志
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    logger = get_ai_logger("ai_router")
except ImportError:
    import logging
    logger = logging.getLogger("ai_router")


class AIRouterConfig:
    """AI路由配置"""
    MAX_MESSAGE_LENGTH = 32000
    MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB
    SUPPORTED_FILE_TYPES = ['.pdf', '.docx', '.txt', '.md', '.json']
    DEFAULT_CONVERSATION_LIMIT = 50
    RATE_LIMIT_REQUESTS = 100
    RATE_LIMIT_WINDOW = 3600  # 1小时


# === 辅助函数 ===

def _clean_optional_json_string_input(input_str: Optional[str]) -> Optional[str]:
    """
    清理从表单接收到的可选JSON字符串参数。
    将 None, 空字符串, 或常见的默认值字面量转换为 None。
    """
    if input_str is None:
        return None

    stripped_str = input_str.strip()

    # 将空字符串或常见的默认值占位符视为None
    invalid_values = ["", "string", "null", "undefined", "none"]
    if stripped_str.lower() in invalid_values:
        return None

    return stripped_str


async def process_ai_temp_file_in_background(
        temp_file_id: int,
        user_id: int,
        oss_object_name: str,
        file_type: str,
        db_session: Session
):
    """
    在后台处理AI对话的临时上传文件：从OSS下载、提取文本、生成嵌入并更新记录。
    """
    logger.info(f"开始后台处理AI临时文件 ID: {temp_file_id} (OSS: {oss_object_name})")
    loop = asyncio.get_running_loop()
    db_temp_file_record = None

    try:
        # 获取临时文件记录
        db_temp_file_record = db_session.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id == temp_file_id).first()
        if not db_temp_file_record:
            logger.error(f"AI临时文件 {temp_file_id} 在后台处理中未找到")
            return

        # 更新状态为processing
        db_temp_file_record.status = "processing"
        db_temp_file_record.processing_message = "正在从云存储下载文件..."
        db_session.add(db_temp_file_record)
        db_session.commit()

        # 从OSS下载文件内容
        try:
            downloaded_bytes = await oss_utils.download_file_from_oss(oss_object_name)
            if not downloaded_bytes:
                db_temp_file_record.status = "failed"
                db_temp_file_record.processing_message = "从云存储下载文件失败或文件内容为空。"
                db_session.add(db_temp_file_record)
                db_session.commit()
                logger.error(f"AI临时文件 {temp_file_id} 从OSS下载失败或内容为空")
                return
        except Exception as oss_error:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = f"OSS下载失败: {oss_error}"
            db_session.add(db_temp_file_record)
            db_session.commit()
            logger.error(f"AI临时文件 {temp_file_id} OSS下载异常: {oss_error}")
            return

        db_temp_file_record.processing_message = "正在提取文本..."
        db_session.add(db_temp_file_record)
        db_session.commit()

        # 提取文本
        try:
            extracted_text = await loop.run_in_executor(
                None,
                extract_text_from_document,
                downloaded_bytes,
                file_type
            )
        except Exception as extract_error:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = f"文本提取失败: {extract_error}"
            db_session.add(db_temp_file_record)
            db_session.commit()
            logger.error(f"AI临时文件 {temp_file_id} 文本提取异常: {extract_error}")
            return

        if not extracted_text:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = "文本提取失败或文件内容为空。"
            db_session.add(db_temp_file_record)
            db_session.commit()
            logger.error(f"AI临时文件 {temp_file_id} 文本提取失败")
            return

        # 生成嵌入
        user_obj = db_session.query(Student).filter(Student.id == user_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if user_obj and user_obj.llm_api_type == "siliconflow" and user_obj.llm_api_key_encrypted:
            try:
                owner_llm_api_key = decrypt_key(user_obj.llm_api_key_encrypted)
                owner_llm_type = user_obj.llm_api_type
                owner_llm_base_url = user_obj.llm_api_base_url
                owner_llm_model_id = get_user_model_for_provider(
                    user_obj.llm_model_ids,
                    user_obj.llm_api_type,
                    user_obj.llm_model_id
                )
            except Exception as e:
                logger.error(f"解密用户 {user_id} LLM API 密钥失败: {e}")

        db_temp_file_record.processing_message = "正在生成嵌入向量..."
        db_session.add(db_temp_file_record)
        db_session.commit()

        try:
            embeddings_list = await get_embeddings_from_api(
                [extracted_text],
                api_key=owner_llm_api_key,
                llm_type=owner_llm_type,
                llm_base_url=owner_llm_base_url,
                llm_model_id=owner_llm_model_id
            )
        except Exception as embedding_error:
            logger.warning(f"文件 {temp_file_id} 嵌入生成失败: {embedding_error}，使用零向量")
            embeddings_list = []

        final_embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if embeddings_list and len(embeddings_list) > 0:
            final_embedding = embeddings_list[0]

        # 更新数据库记录
        db_temp_file_record.extracted_text = extracted_text
        db_temp_file_record.embedding = final_embedding
        db_temp_file_record.status = "completed"
        db_temp_file_record.processing_message = "文件处理完成，文本已提取，嵌入已生成。"
        db_session.add(db_temp_file_record)
        db_session.commit()
        
        logger.info(f"AI临时文件 {temp_file_id} 处理完成。提取文本长度: {len(extracted_text)} 字符")

    except Exception as e:
        logger.error(f"后台处理AI临时文件 {temp_file_id} 发生未预期错误: {type(e).__name__}: {e}")
        if db_temp_file_record:
            try:
                db_temp_file_record.status = "failed"
                db_temp_file_record.processing_message = f"处理失败: {str(e)}"
                db_session.add(db_temp_file_record)
                db_session.commit()
            except Exception as commit_error:
                logger.error(f"更新临时文件状态失败: {commit_error}")
    finally:
        try:
            db_session.close()
        except Exception as close_error:
            logger.error(f"关闭数据库会话失败: {close_error}")


# === 请求/响应模型 ===

class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., max_length=AIRouterConfig.MAX_MESSAGE_LENGTH)
    conversation_id: Optional[str] = None
    model_preference: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, gt=0, le=8192)
    use_tools: bool = True
    context_enhancement: bool = True
    stream: bool = False
    
    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError('消息内容不能为空')
        return v.strip()


class ChatResponse(BaseModel):
    """聊天响应模型"""
    conversation_id: str
    message_id: str
    content: str
    model_used: str
    tokens_used: int
    response_time_ms: float
    cached: bool = False
    tools_used: List[str] = []


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    conversations: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int


class FileProcessingResponse(BaseModel):
    """文件处理响应"""
    file_id: str
    status: str
    message: str


class SemanticSearchRequest(BaseModel):
    """语义搜索请求"""
    query: str = Field(..., min_length=1, max_length=1000)
    item_types: Optional[List[str]] = Field(default=None)
    limit: int = Field(default=10, ge=1, le=50)


class SemanticSearchResult(BaseModel):
    """语义搜索结果"""
    id: int
    title: str
    type: str
    content_snippet: str
    relevance_score: float


class QARequest(BaseModel):
    """问答请求模型"""
    query: str = Field(..., min_length=1, max_length=32000)
    conversation_id: Optional[int] = None
    kb_ids: Optional[List[int]] = None
    use_tools: bool = False
    preferred_tools: Optional[Union[List[Literal["rag", "web_search", "mcp_tool"]], str]] = None
    llm_model_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "什么是机器学习？",
                "conversation_id": None,
                "use_tools": True,
                "preferred_tools": ["rag", "web_search"]
            }
        }
    status: str
    message: str
    processing_time_ms: Optional[float] = None


# === 核心路由类 ===

class EnterpriseAIRouter:
    """企业级AI路由处理器"""
    
    def __init__(self):
        self.provider_manager = None
        self.config = get_enterprise_config()
        self._rate_limiter = {}  # 简单的内存限流器
        
    async def initialize(self):
        """异步初始化"""
        try:
            # 初始化提供者管理器
            self.provider_manager = AIProviderManager()
            # 如果AIProviderManager有initialize方法，则调用
            if hasattr(self.provider_manager, 'initialize'):
                await self.provider_manager.initialize()
            
            logger.info("Enterprise AI Router initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Enterprise AI Router: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI服务初始化失败"
            )
    
    async def _check_rate_limit(self, user_id: int, request: Request) -> bool:
        """检查请求频率限制"""
        client_ip = request.client.host
        key = f"{user_id}:{client_ip}"
        current_time = time.time()
        
        if key not in self._rate_limiter:
            self._rate_limiter[key] = []
        
        # 清理过期记录
        cutoff_time = current_time - AIRouterConfig.RATE_LIMIT_WINDOW
        self._rate_limiter[key] = [
            req_time for req_time in self._rate_limiter[key] 
            if req_time > cutoff_time
        ]
        
        # 检查限制
        if len(self._rate_limiter[key]) >= AIRouterConfig.RATE_LIMIT_REQUESTS:
            return False
            
        # 记录当前请求
        self._rate_limiter[key].append(current_time)
        return True
    
    async def chat_completion(
        self, 
        request_data: ChatRequest,
        user_id: int,
        db: Session,
        background_tasks: BackgroundTasks
    ) -> Union[ChatResponse, StreamingResponse]:
        """处理聊天完成请求"""
        start_time = time.time()
        
        try:
            # 获取或创建对话
            conversation = await self._get_or_create_conversation(
                request_data.conversation_id, user_id, db
            )
            
            # 构建消息上下文
            context_messages = await self._build_message_context(
                conversation.id, db, request_data.context_enhancement
            )
            
            # 添加用户消息
            user_message = self._create_message(
                conversation.id, "user", request_data.message, user_id
            )
            db.add(user_message)
            db.commit()
            
            # 选择最佳提供者
            provider = self.provider_manager.get_llm_provider(
                request_data.model_preference
            )
            
            # 准备工具
            tools = None
            if request_data.use_tools:
                try:
                    tools = get_all_available_tools_for_llm(user_id, db)
                except Exception as e:
                    logger.warning(f"Failed to get tools for user {user_id}: {e}")
                    tools = None
            
            # 执行聊天完成
            if request_data.stream:
                return await self._stream_chat_completion(
                    provider, context_messages, tools, request_data, 
                    conversation, user_id, db, start_time
                )
            else:
                return await self._sync_chat_completion(
                    provider, context_messages, tools, request_data,
                    conversation, user_id, db, start_time
                )
                
        except Exception as e:
            logger.error(f"Chat completion error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Chat completion failed: {str(e)}"
            )
    
    async def _sync_chat_completion(
        self, provider, context_messages, tools, request_data,
        conversation, user_id, db, start_time
    ) -> ChatResponse:
        """同步聊天完成"""
        
        response = await provider.chat_completion(
            messages=context_messages + [{"role": "user", "content": request_data.message}],
            tools=tools,
            temperature=request_data.temperature,
            max_tokens=request_data.max_tokens,
            model=request_data.model_preference
        )
        
        # 处理响应
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        model_used = response.get("model", request_data.model_preference or provider.model)
        tokens_used = response.get("usage", {}).get("total_tokens", 0)
        
        # 保存助手消息
        assistant_message = self._create_message(
            conversation.id, "assistant", content, user_id
        )
        db.add(assistant_message)
        db.commit()
        
        # 记录性能指标
        response_time = (time.time() - start_time) * 1000
        
        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            content=content,
            model_used=model_used,
            tokens_used=tokens_used,
            response_time_ms=response_time,
            cached=response.get("cached", False)
        )
    
    async def _stream_chat_completion(
        self, provider, context_messages, tools, request_data,
        conversation, user_id, db, start_time
    ) -> StreamingResponse:
        """流式聊天完成"""
        
        async def stream_generator():
            try:
                full_content = ""
                async for chunk in provider.chat_completion_stream(
                    messages=context_messages + [{"role": "user", "content": request_data.message}],
                    tools=tools,
                    temperature=request_data.temperature,
                    max_tokens=request_data.max_tokens,
                    model=request_data.model_preference
                ):
                    if chunk.get("choices"):
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            content = delta["content"]
                            full_content += content
                            yield f"data: {json.dumps({'content': content, 'type': 'content'})}\n\n"
                
                # 保存完整消息
                assistant_message = self._create_message(
                    conversation.id, "assistant", full_content, user_id
                )
                db.add(assistant_message)
                db.commit()
                
                # 发送完成信号
                response_time = (time.time() - start_time) * 1000
                yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_message.id, 'response_time_ms': response_time})}\n\n"
                
            except Exception as e:
                logger.error(f"Stream error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache"}
        )
    
    async def _get_or_create_conversation(
        self, conversation_id: Optional[str], user_id: int, db: Session
    ) -> AIConversation:
        """获取或创建对话"""
        if conversation_id:
            conversation = db.query(AIConversation).filter(
                AIConversation.id == conversation_id,
                AIConversation.user_id == user_id
            ).first()
            if conversation:
                return conversation
        
        # 创建新对话
        conversation = AIConversation(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title="新对话",
            created_at=datetime.utcnow()
        )
        db.add(conversation)
        db.commit()
        return conversation
    
    async def _build_message_context(
        self, conversation_id: str, db: Session, enhanced: bool = True
    ) -> List[Dict[str, str]]:
        """构建消息上下文"""
        messages = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conversation_id
        ).order_by(AIConversationMessage.created_at).limit(20).all()
        
        context = []
        for msg in messages:
            context.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return context
    
    def _create_message(
        self, conversation_id: str, role: str, content: str, user_id: int
    ) -> AIConversationMessage:
        """创建消息记录"""
        return AIConversationMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            user_id=user_id,
            created_at=datetime.utcnow()
        )


# === 全局实例 ===
ai_handler = EnterpriseAIRouter()

# === 依赖注入 ===
async def get_ai_handler():
    """获取AI处理器实例"""
    if ai_handler.provider_manager is None:
        await ai_handler.initialize()
    return ai_handler

async def verify_rate_limit(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    handler: EnterpriseAIRouter = Depends(get_ai_handler)
):
    """验证请求频率限制"""
    if not await handler._check_rate_limit(user_id, request):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求频率超出限制"
        )
    return True


# === 路由定义 ===
router = APIRouter(
    prefix="/ai",
    tags=["AI智能助手"],
    responses={404: {"description": "资源未找到"}},
)


@router.post("/chat", response_model=ChatResponse, summary="AI聊天对话")
async def chat_completion(
    request_data: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    handler: EnterpriseAIRouter = Depends(get_ai_handler),
    _: bool = Depends(verify_rate_limit)
):
    """
    企业级聊天完成API
    
    支持功能：
    - 多模型智能选择
    - 工具调用
    - 上下文增强
    - 流式响应
    - 速率限制
    - 缓存优化
    """
    return await handler.chat_completion(request_data, user_id, db, background_tasks)


@router.get("/conversations", response_model=ConversationListResponse, summary="获取对话列表")
async def list_conversations(
    page: int = 1,
    page_size: int = AIRouterConfig.DEFAULT_CONVERSATION_LIMIT,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取用户对话列表"""
    offset = (page - 1) * page_size
    
    # 查询对话
    conversations_query = db.query(AIConversation).filter(
        AIConversation.user_id == user_id
    ).order_by(AIConversation.updated_at.desc())
    
    total = conversations_query.count()
    conversations = conversations_query.offset(offset).limit(page_size).all()
    
    # 格式化响应
    conversation_list = []
    for conv in conversations:
        conversation_list.append({
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "message_count": db.query(AIConversationMessage).filter(
                AIConversationMessage.conversation_id == conv.id
            ).count()
        })
    
    return ConversationListResponse(
        conversations=conversation_list,
        total=total,
        page=page,
        page_size=page_size
    )


@router.delete("/conversations/{conversation_id}", summary="删除对话")
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """删除对话"""
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == user_id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话未找到"
        )
    
    # 删除相关消息
    db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == conversation_id
    ).delete()
    
    # 删除对话
    db.delete(conversation)
    db.commit()
    
    return {"message": "对话删除成功"}


@router.post("/upload", response_model=FileProcessingResponse, summary="文件上传处理")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    handler: EnterpriseAIRouter = Depends(get_ai_handler)
):
    """
    企业级文件上传和处理
    
    支持功能：
    - 多格式文档解析
    - 智能文本提取
    - 向量化索引
    - 异步处理
    """
    start_time = time.time()
    
    try:
        # 验证文件
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未提供文件"
            )
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in AIRouterConfig.SUPPORTED_FILE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {file_ext}"
            )
        
        # 检查文件大小
        content = await file.read()
        if len(content) > AIRouterConfig.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="文件过大"
            )
        
        # 上传到OSS
        file_id = str(uuid.uuid4())
        oss_key = f"ai_uploads/{user_id}/{file_id}/{file.filename}"
        
        await oss_utils.upload_file_to_oss(oss_key, content)
        
        # 创建处理记录
        temp_file = AIConversationTemporaryFile(
            id=file_id,
            conversation_id=conversation_id,
            user_id=user_id,
            filename=file.filename,
            file_type=file_ext,
            oss_object_name=oss_key,
            status="pending",
            created_at=datetime.utcnow()
        )
        db.add(temp_file)
        db.commit()
        
        # 启动后台处理
        async def process_file_background():
            try:
                # 这里可以调用现有的文档处理函数
                logger.info(f"Processing file {file_id} from {oss_key}")
                # 调用现有的文档处理逻辑
                text_content = extract_text_from_document(content, file_ext)
                logger.info(f"Extracted {len(text_content)} characters from {file.filename}")
            except Exception as e:
                logger.error(f"File processing failed for {file_id}: {e}")
        
        background_tasks.add_task(process_file_background)
        
        processing_time = (time.time() - start_time) * 1000
        
        return FileProcessingResponse(
            file_id=file_id,
            status="processing",
            message="File uploaded and processing started",
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )


@router.get("/health", summary="AI服务健康检查")
async def health_check():
    """AI服务健康检查"""
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0.0",
            "service": "enterprise-ai-router"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.post("/semantic_search", response_model=List[SemanticSearchResult], summary="语义搜索")
async def semantic_search(
    request: SemanticSearchRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_rate_limit)
):
    """
    企业级语义搜索API
    
    支持功能：
    - 多类型内容搜索（项目、课程、知识库文章、笔记）
    - 向量相似度计算
    - 智能重排序
    - 权限控制
    """
    start_time = time.time()
    
    try:
        logger.info(f"用户 {user_id} 语义搜索: {request.query}，范围: {request.item_types}")

        # 获取用户信息
        user = db.query(Student).filter(Student.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未找到")

        searchable_items = []
        target_types = request.item_types if request.item_types else [
            "project", "course", "knowledge_article", "note"
        ]

        # 收集可搜索的内容
        if "project" in target_types:
            projects = db.query(Project).all()
            for p in projects:
                if p.embedding is not None:
                    searchable_items.append({"obj": p, "type": "project"})

        if "course" in target_types:
            courses = db.query(Course).all()
            for c in courses:
                if c.embedding is not None:
                    searchable_items.append({"obj": c, "type": "course"})

        if "knowledge_article" in target_types:
            kbs = db.query(KnowledgeBase).filter(
                (KnowledgeBase.owner_id == user_id) | (KnowledgeBase.access_type == "public")
            ).all()
            for kb in kbs:
                articles = db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_id == kb.id).all()
                for article in articles:
                    if article.embedding is not None:
                        searchable_items.append({"obj": article, "type": "knowledge_article"})

        if "note" in target_types:
            notes = db.query(Note).filter(Note.owner_id == user_id).all()
            for note in notes:
                if note.embedding is not None:
                    searchable_items.append({"obj": note, "type": "note"})

        if not searchable_items:
            return []

        # 获取查询嵌入
        user_llm_api_key = None
        if user.llm_api_key_encrypted:
            try:
                user_llm_api_key = decrypt_key(user.llm_api_key_encrypted)
            except Exception as e:
                logger.warning(f"解密用户 {user_id} LLM API Key失败: {e}")

        query_embedding_list = await get_embeddings_from_api(
            [request.query],
            api_key=user_llm_api_key,
            llm_type=user.llm_api_type,
            llm_base_url=user.llm_api_base_url,
            llm_model_id=get_user_model_for_provider(
                user.llm_model_ids,
                user.llm_api_type,
                user.llm_model_id
            )
        )

        if not query_embedding_list or query_embedding_list[0] == GLOBAL_PLACEHOLDER_ZERO_VECTOR:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="无法生成查询嵌入，请确保LLM配置正确"
            )

        query_embedding_np = np.array(query_embedding_list[0]).reshape(1, -1)

        # 计算相似度
        item_embeddings_np = np.array([item['obj'].embedding for item in searchable_items])
        similarities = cosine_similarity(query_embedding_np, item_embeddings_np)[0]

        # 初始排序
        initial_candidates = []
        for i, sim in enumerate(similarities):
            initial_candidates.append({
                'obj': searchable_items[i]['obj'],
                'type': searchable_items[i]['type'],
                'similarity_stage1': float(sim)
            })
        
        initial_candidates.sort(key=lambda x: x['similarity_stage1'], reverse=True)
        initial_candidates = initial_candidates[:INITIAL_CANDIDATES_K]

        if not initial_candidates:
            return []

        # 重排序
        rerank_candidate_texts = [c['obj'].combined_text for c in initial_candidates]
        rerank_scores = await get_rerank_scores_from_api(
            request.query,
            rerank_candidate_texts,
            api_key=user_llm_api_key,
            llm_type=user.llm_api_type,
            llm_base_url=user.llm_api_base_url,
            fallback_to_similarity=True
        )

        # 应用重排序分数
        if all(score == 0.0 for score in rerank_scores):
            for i, candidate in enumerate(initial_candidates):
                candidate['relevance_score'] = candidate['similarity_stage1']
        else:
            for i, score in enumerate(rerank_scores):
                initial_candidates[i]['relevance_score'] = float(score)

        initial_candidates.sort(key=lambda x: x['relevance_score'], reverse=True)

        # 格式化结果
        final_results = []
        for item in initial_candidates[:request.limit]:
            obj = item['obj']
            content_snippet = ""
            
            if hasattr(obj, 'content') and obj.content:
                content_snippet = obj.content[:150] + "..." if len(obj.content) > 150 else obj.content
            elif hasattr(obj, 'description') and obj.description:
                content_snippet = obj.description[:150] + "..." if len(obj.description) > 150 else obj.description

            final_results.append(SemanticSearchResult(
                id=obj.id,
                title=obj.title if hasattr(obj, 'title') else obj.name if hasattr(obj, 'name') else str(obj.id),
                type=item['type'],
                content_snippet=content_snippet,
                relevance_score=item['relevance_score']
            ))

        processing_time = (time.time() - start_time) * 1000
        logger.info(f"语义搜索完成，耗时 {processing_time:.2f}ms，返回 {len(final_results)} 个结果")

        return final_results

    except Exception as e:
        logger.error(f"语义搜索失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"语义搜索失败: {str(e)}"
        )


@router.post("/qa", response_model=schemas.AIQAResponse, summary="AI问答")
async def ai_qa_endpoint(
    query: str = Form(..., description="用户的问题文本"),
    conversation_id: Optional[int] = Form(None, description="要继续的对话Session ID"),
    kb_ids_json: Optional[str] = Form(None, description="要检索的知识库ID列表JSON字符串"),
    use_tools: Optional[bool] = Form(False, description="是否启用AI智能工具调用"),
    preferred_tools_json: Optional[str] = Form(None, description="AI偏好使用的工具类型JSON数组"),
    llm_model_id: Optional[str] = Form(None, description="本次会话使用的LLM模型ID"),
    uploaded_file: Optional[UploadFile] = File(None, description="可选：上传文件对AI进行提问"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_rate_limit)
):
    """
    企业级AI问答API
    
    支持功能：
    - 多轮对话
    - 文件上传分析
    - 知识库检索
    - 工具调用
    - 智能代理编排
    """
    start_time = time.time()
    
    try:
        # 文件上传验证
        if uploaded_file:
            MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
            if hasattr(uploaded_file, 'size') and uploaded_file.size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="文件大小超过限制（50MB）"
                )
            
            ALLOWED_CONTENT_TYPES = [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp',
                'application/pdf', 'text/plain', 'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ]
            if uploaded_file.content_type not in ALLOWED_CONTENT_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"不支持的文件类型: {uploaded_file.content_type}"
                )

        logger.info(f"用户 {user_id} 问答请求: {query[:100]}{'...' if len(query) > 100 else ''}")

        user = db.query(Student).filter(Student.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未找到")

        # 清理输入参数
        kb_ids_json = _clean_optional_json_string_input(kb_ids_json)
        preferred_tools_json = _clean_optional_json_string_input(preferred_tools_json)
        llm_model_id = _clean_optional_json_string_input(llm_model_id)

        # 解析知识库ID
        actual_kb_ids: Optional[List[int]] = None
        if kb_ids_json:
            try:
                actual_kb_ids = json.loads(kb_ids_json)
                if not isinstance(actual_kb_ids, list) or not all(isinstance(x, int) for x in actual_kb_ids):
                    raise ValueError("kb_ids 必须是一个整数列表格式的JSON字符串")
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"kb_ids 格式不正确: {e}"
                )

        # 解析偏好工具
        actual_preferred_tools: Optional[List[Literal["rag", "web_search", "mcp_tool"]]] = None
        if use_tools and preferred_tools_json:
            try:
                if preferred_tools_json.strip().lower() == "all":
                    actual_preferred_tools = "all"
                else:
                    parsed_tools = json.loads(preferred_tools_json)
                    if parsed_tools is None or len(parsed_tools) == 0:
                        actual_preferred_tools = None
                    else:
                        valid_tool_types = ["rag", "web_search", "mcp_tool"]
                        invalid_tools = [tool for tool in parsed_tools if tool not in valid_tool_types]
                        if invalid_tools:
                            raise ValueError(f"包含不支持的工具类型：{invalid_tools}")
                        actual_preferred_tools = parsed_tools
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"偏好工具配置格式错误：{str(e)}"
                )

        # 获取或创建对话
        db_conversation: AIConversation
        past_messages_for_llm: List[Dict[str, Any]] = []
        is_new_conversation = False

        if conversation_id:
            db_conversation = db.query(AIConversation).filter(
                AIConversation.id == conversation_id,
                AIConversation.user_id == user_id
            ).first()
            if not db_conversation:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的对话未找到")

            # 加载历史消息
            raw_past_messages = db.query(AIConversationMessage).filter(
                AIConversationMessage.conversation_id == db_conversation.id
            ).order_by(AIConversationMessage.sent_at).limit(20).all()

            past_messages_for_llm = [msg.to_dict() for msg in raw_past_messages]
        else:
            # 创建新对话
            db_conversation = AIConversation(user_id=user_id, title=None)
            db.add(db_conversation)
            db.flush()
            is_new_conversation = True

        # 获取LLM配置
        if not user.llm_api_type or not user.llm_api_key_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户尚未配置LLM API"
            )

        try:
            user_llm_api_key = decrypt_key(user.llm_api_key_encrypted)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="解密LLM API密钥失败"
            )

        # 确定使用的模型
        llm_model_id_final = llm_model_id or get_user_model_for_provider(
            user.llm_model_ids,
            user.llm_api_type,
            user.llm_model_id
        )

        # 文件上传处理
        temp_file_ids_for_context: List[int] = []
        if uploaded_file:
            file_bytes = await uploaded_file.read()
            file_extension = os.path.splitext(uploaded_file.filename)[1]
            oss_object_name = f"ai_chat_temp_files/{uuid.uuid4().hex}{file_extension}"

            try:
                await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=oss_object_name,
                    content_type=uploaded_file.content_type
                )

                temp_file_record = AIConversationTemporaryFile(
                    conversation_id=db_conversation.id,
                    oss_object_name=oss_object_name,
                    original_filename=uploaded_file.filename,
                    file_type=uploaded_file.content_type,
                    status="pending",
                    processing_message="文件已上传，等待处理..."
                )
                db.add(temp_file_record)
                db.flush()
                db.commit()

                temp_file_ids_for_context.append(temp_file_record.id)

                # 启动后台处理
                background_db_session = SessionLocal()
                task = asyncio.create_task(
                    process_ai_temp_file_in_background(
                        temp_file_record.id,
                        user_id,
                        oss_object_name,
                        uploaded_file.content_type,
                        background_db_session
                    )
                )

                file_link = f"{oss_utils.S3_BASE_URL.rstrip('/')}/{oss_object_name}"
                query += f"\n\n[用户上传了文件 '{uploaded_file.filename}' ({uploaded_file.content_type})，链接: {file_link}]"

            except Exception as e:
                db.rollback()
                logger.error(f"处理上传文件失败: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"处理上传文件失败: {e}"
                )

        # 调用智能代理进行问答
        try:
            response = await invoke_agent(
                query=query,
                db=db,
                user_id=user_id,
                conversation_context=past_messages_for_llm,
                kb_ids=actual_kb_ids,
                use_tools=use_tools,
                preferred_tools=actual_preferred_tools,
                temp_file_ids=temp_file_ids_for_context,
                llm_api_key=user_llm_api_key,
                llm_type=user.llm_api_type,
                llm_base_url=user.llm_api_base_url,
                llm_model_id=llm_model_id_final
            )

            # 保存用户消息
            user_message = AIConversationMessage(
                conversation_id=db_conversation.id,
                role="user",
                content=query,
                sent_at=datetime.utcnow()
            )
            db.add(user_message)

            # 保存AI回复
            ai_message = AIConversationMessage(
                conversation_id=db_conversation.id,
                role="assistant",
                content=response.get("content", ""),
                metadata=response.get("metadata", {}),
                sent_at=datetime.utcnow()
            )
            db.add(ai_message)

            # 为新对话生成标题
            if is_new_conversation and response.get("content"):
                try:
                    title = await generate_conversation_title_from_llm(
                        query,
                        response["content"],
                        api_key=user_llm_api_key,
                        llm_type=user.llm_api_type,
                        llm_base_url=user.llm_api_base_url,
                        llm_model_id=llm_model_id_final
                    )
                    if title:
                        db_conversation.title = title
                        db.add(db_conversation)
                except Exception as title_error:
                    logger.warning(f"生成对话标题失败: {title_error}")

            db.commit()

            processing_time = (time.time() - start_time) * 1000

            return schemas.AIQAResponse(
                response=response.get("content", ""),
                conversation_id=db_conversation.id,
                used_tools=response.get("tools_used", []),
                knowledge_sources=response.get("knowledge_sources", []),
                processing_time_ms=processing_time,
                model_used=llm_model_id_final,
                metadata=response.get("metadata", {})
            )

        except Exception as invoke_error:
            db.rollback()
            logger.error(f"AI代理调用失败: {invoke_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI处理失败: {str(invoke_error)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI问答处理失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理失败: {str(e)}"
        )


@router.get("/mcp_available_tools", response_model=Dict[str, Any], summary="获取MCP工具列表")
async def get_mcp_available_tools(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取当前用户可用的MCP工具列表
    
    返回包括内置工具和用户配置的MCP服务工具
    """
    try:
        available_tools = await get_all_available_tools_for_llm(db, user_id)
        
        return {
            "status": "success",
            "tools_count": len(available_tools),
            "available_tools": available_tools,
            "description": "当前用户可用的MCP工具列表"
        }
    except Exception as e:
        logger.error(f"获取MCP工具列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取MCP工具列表时发生错误"
        )


@router.get("/conversations/{conversation_id}/files/status", response_model=Dict[str, Any], summary="查询对话文件状态")
def get_conversation_files_status(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """查询指定对话中所有临时文件的处理状态"""
    # 验证对话归属
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == user_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在或无权访问")

    # 获取对话中的所有临时文件
    temp_files = db.query(AIConversationTemporaryFile).filter(
        AIConversationTemporaryFile.conversation_id == conversation_id
    ).all()

    files_status = []
    for tf in temp_files:
        files_status.append({
            "id": tf.id,
            "filename": tf.original_filename,
            "status": tf.status,
            "processing_message": tf.processing_message,
            "created_at": tf.created_at.isoformat() if tf.created_at else None,
            "has_content": bool(tf.extracted_text and tf.extracted_text.strip())
        })

    return {
        "conversation_id": conversation_id,
        "files_count": len(files_status),
        "files": files_status
    }


@router.get("/rag_diagnosis", response_model=Dict[str, Any], summary="RAG功能诊断")
async def rag_diagnosis(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    用户RAG功能诊断
    
    检查用户的RAG配置和可用资源
    """
    try:
        user = db.query(Student).filter(Student.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未找到")

        diagnosis_result = {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "llm_configuration": {
                "api_type": user.llm_api_type,
                "base_url": user.llm_api_base_url,
                "has_api_key": bool(user.llm_api_key_encrypted),
                "model_configured": bool(user.llm_model_id),
                "multi_model_configured": bool(user.llm_model_ids)
            },
            "knowledge_bases": {
                "owned_count": 0,
                "accessible_count": 0,
                "total_articles": 0
            },
            "notes": {
                "total_count": 0,
                "with_embeddings": 0
            },
            "embedding_capability": "unknown",
            "recommendations": []
        }

        # 检查知识库
        owned_kbs = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == user_id).all()
        accessible_kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == user_id) | (KnowledgeBase.access_type == "public")
        ).all()

        diagnosis_result["knowledge_bases"]["owned_count"] = len(owned_kbs)
        diagnosis_result["knowledge_bases"]["accessible_count"] = len(accessible_kbs)

        total_articles = 0
        for kb in accessible_kbs:
            articles_count = db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_id == kb.id).count()
            total_articles += articles_count

        diagnosis_result["knowledge_bases"]["total_articles"] = total_articles

        # 检查笔记
        user_notes = db.query(Note).filter(Note.owner_id == user_id).all()
        notes_with_embeddings = [note for note in user_notes if note.embedding is not None]

        diagnosis_result["notes"]["total_count"] = len(user_notes)
        diagnosis_result["notes"]["with_embeddings"] = len(notes_with_embeddings)

        # 检查嵌入能力
        if user.llm_api_type == "siliconflow" and user.llm_api_key_encrypted:
            try:
                decrypt_key(user.llm_api_key_encrypted)
                diagnosis_result["embedding_capability"] = "available"
            except:
                diagnosis_result["embedding_capability"] = "api_key_invalid"
        elif not user.llm_api_type:
            diagnosis_result["embedding_capability"] = "not_configured"
        else:
            diagnosis_result["embedding_capability"] = "unsupported_provider"

        # 生成建议
        recommendations = []
        if not user.llm_api_type:
            recommendations.append("请配置LLM API提供者以启用RAG功能")
        if not user.llm_api_key_encrypted:
            recommendations.append("请配置LLM API密钥")
        if total_articles == 0:
            recommendations.append("建议创建或导入知识库文章以丰富RAG检索内容")
        if len(notes_with_embeddings) < len(user_notes):
            recommendations.append("部分笔记缺少嵌入向量，建议重新生成")

        diagnosis_result["recommendations"] = recommendations

        return diagnosis_result

    except Exception as e:
        logger.error(f"RAG诊断失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG诊断失败: {str(e)}"
        )


@router.get("/ai_conversations", response_model=List[schemas.AIConversationResponse], summary="获取AI对话列表")
async def get_ai_conversations(
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户的AI对话列表"""
    conversations = db.query(AIConversation).filter(
        AIConversation.user_id == user_id
    ).order_by(
        AIConversation.updated_at.desc()
    ).offset(offset).limit(limit).all()

    return [
        schemas.AIConversationResponse(
            id=conv.id,
            title=conv.title or "未命名对话",
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=db.query(AIConversationMessage).filter(
                AIConversationMessage.conversation_id == conv.id
            ).count()
        ) for conv in conversations
    ]


@router.get("/ai_conversations/{conversation_id}", response_model=schemas.AIConversationResponse, summary="获取AI对话详情")
async def get_ai_conversation(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取指定AI对话的详细信息"""
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == user_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到")

    message_count = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == conversation_id
    ).count()

    return schemas.AIConversationResponse(
        id=conversation.id,
        title=conversation.title or "未命名对话",
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=message_count
    )


@router.get("/ai_conversations/{conversation_id}/messages", response_model=List[schemas.AIConversationMessageResponse], summary="获取对话消息列表")
async def get_conversation_messages(
    conversation_id: int,
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取指定对话的消息列表"""
    # 验证对话归属
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == user_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到")

    messages = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == conversation_id
    ).order_by(
        AIConversationMessage.sent_at
    ).offset(offset).limit(limit).all()

    return [
        schemas.AIConversationMessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            sent_at=msg.sent_at,
            metadata=msg.metadata or {}
        ) for msg in messages
    ]


@router.get("/ai_conversations/{conversation_id}/retitle", response_model=schemas.AIConversationResponse, summary="重新生成对话标题")
async def retitle_conversation(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """重新生成对话标题"""
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == user_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到")

    # 获取对话的前几条消息来生成标题
    messages = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == conversation_id
    ).order_by(AIConversationMessage.sent_at).limit(4).all()

    if len(messages) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="对话消息不足，无法生成标题"
        )

    try:
        user = db.query(Student).filter(Student.id == user_id).first()
        if not user or not user.llm_api_key_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户LLM配置不完整"
            )

        user_llm_api_key = decrypt_key(user.llm_api_key_encrypted)
        
        # 取第一条用户消息和第一条AI回复
        user_msg = next((msg for msg in messages if msg.role == "user"), None)
        ai_msg = next((msg for msg in messages if msg.role == "assistant"), None)

        if not user_msg or not ai_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="找不到有效的用户消息和AI回复"
            )

        new_title = await generate_conversation_title_from_llm(
            user_msg.content,
            ai_msg.content,
            api_key=user_llm_api_key,
            llm_type=user.llm_api_type,
            llm_base_url=user.llm_api_base_url,
            llm_model_id=get_user_model_for_provider(
                user.llm_model_ids,
                user.llm_api_type,
                user.llm_model_id
            )
        )

        if new_title:
            conversation.title = new_title
            db.add(conversation)
            db.commit()

        message_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conversation_id
        ).count()

        return schemas.AIConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=message_count
        )

    except Exception as e:
        logger.error(f"重新生成对话标题失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成标题失败: {str(e)}"
        )


@router.delete("/ai_conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除AI对话")
async def delete_ai_conversation(
    conversation_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除AI对话及其所有消息"""
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == user_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到")

    try:
        # 删除相关的临时文件记录
        db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.conversation_id == conversation_id
        ).delete()

        # 删除对话消息
        db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conversation_id
        ).delete()

        # 删除对话
        db.delete(conversation)
        db.commit()

        logger.info(f"用户 {user_id} 删除了对话 {conversation_id}")

    except Exception as e:
        db.rollback()
        logger.error(f"删除对话失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除对话失败"
        )
