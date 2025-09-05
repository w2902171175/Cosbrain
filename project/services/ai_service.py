# project/services/ai_service.py
"""
AI模块服务层 - 专项优化AI功能
基于优化框架为 AI 模块提供高效的AI功能服务层实现
"""
from typing import List, Optional, Dict, Any, Tuple, Union
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import logging
import json
import asyncio

# 模型导入
from project.models import (
    User, AIConversation, AIConversationMessage, 
    AIConversationTemporaryFile
)
import project.schemas as schemas

# 工具导入
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.async_cache.cache_manager import cache_result, invalidate_cache_pattern
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import get_cache_key, monitor_performance

logger = logging.getLogger(__name__)

class AIConversationService:
    """AI对话服务类"""
    
    @staticmethod
    @handle_database_errors
    def get_conversations_optimized(
        db: Session, 
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[AIConversation], int]:
        """获取用户对话列表 - 优化版本"""
        
        # 预加载消息统计
        query = db.query(AIConversation).filter(
            AIConversation.user_id == user_id
        ).order_by(AIConversation.updated_at.desc())
        
        conversations = query.offset(offset).limit(limit).all()
        total = query.count()
        
        # 批量获取消息计数
        conversation_ids = [conv.id for conv in conversations]
        if conversation_ids:
            message_counts = db.query(
                AIConversationMessage.conversation_id,
                func.count(AIConversationMessage.id).label('count')
            ).filter(
                AIConversationMessage.conversation_id.in_(conversation_ids)
            ).group_by(AIConversationMessage.conversation_id).all()
            
            # 创建计数映射
            count_map = {conv_id: count for conv_id, count in message_counts}
            
            # 附加消息计数到对话对象
            for conv in conversations:
                conv._message_count = count_map.get(conv.id, 0)
        
        logger.info(f"获取用户 {user_id} 的对话列表：{len(conversations)} 个对话")
        return conversations, total
    
    @staticmethod
    @handle_database_errors
    def get_conversation_optimized(
        db: Session, 
        conversation_id: int, 
        user_id: int
    ) -> AIConversation:
        """获取对话详情 - 优化版本"""
        
        conversation = db.query(AIConversation).filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == user_id
        ).first()
        
        if not conversation:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在"
            )
        
        # 获取消息计数
        message_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conversation_id
        ).count()
        conversation._message_count = message_count
        
        logger.info(f"获取对话详情：{conversation_id}（用户 {user_id}）")
        return conversation
    
    @staticmethod
    @handle_database_errors
    def create_conversation_optimized(
        db: Session,
        user_id: int,
        title: Optional[str] = None,
        initial_message: Optional[str] = None
    ) -> AIConversation:
        """创建对话 - 优化版本"""
        
        # 生成标题
        if not title and initial_message:
            title = initial_message[:50] + "..." if len(initial_message) > 50 else initial_message
        elif not title:
            title = f"对话 {datetime.now().strftime('%m-%d %H:%M')}"
        
        # 创建对话
        conversation = AIConversation(
            user_id=user_id,
            title=title,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(conversation)
        db.flush()  # 获取ID
        
        # 如果有初始消息，添加到对话中
        if initial_message:
            message = AIConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content=initial_message,
                created_at=datetime.utcnow()
            )
            db.add(message)
        
        logger.info(f"用户 {user_id} 创建对话 {conversation.id}：{title}")
        return conversation
    
    @staticmethod
    @handle_database_errors
    def update_conversation_optimized(
        db: Session,
        conversation_id: int,
        user_id: int,
        title: Optional[str] = None
    ) -> AIConversation:
        """更新对话 - 优化版本"""
        
        conversation = AIConversationService.get_conversation_optimized(
            db, conversation_id, user_id
        )
        
        if title:
            conversation.title = title
        
        conversation.updated_at = datetime.utcnow()
        db.add(conversation)
        
        logger.info(f"用户 {user_id} 更新对话 {conversation_id}")
        return conversation
    
    @staticmethod
    @handle_database_errors
    def delete_conversation_optimized(
        db: Session,
        conversation_id: int,
        user_id: int
    ) -> None:
        """删除对话 - 优化版本"""
        
        conversation = AIConversationService.get_conversation_optimized(
            db, conversation_id, user_id
        )
        
        # 删除所有消息
        db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conversation_id
        ).delete()
        
        # 删除临时文件记录
        db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.conversation_id == conversation_id
        ).delete()
        
        # 删除对话
        db.delete(conversation)
        
        logger.info(f"用户 {user_id} 删除对话 {conversation_id}")

class AIMessageService:
    """AI消息服务类"""
    
    @staticmethod
    @handle_database_errors
    def get_messages_optimized(
        db: Session,
        conversation_id: int,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[AIConversationMessage], int]:
        """获取对话消息 - 优化版本"""
        
        # 验证对话权限
        AIConversationService.get_conversation_optimized(db, conversation_id, user_id)
        
        # 获取消息列表
        query = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conversation_id
        ).order_by(AIConversationMessage.created_at.asc())
        
        messages = query.offset(offset).limit(limit).all()
        total = query.count()
        
        logger.info(f"获取对话 {conversation_id} 的消息：{len(messages)} 条")
        return messages, total
    
    @staticmethod
    @handle_database_errors
    def add_message_optimized(
        db: Session,
        conversation_id: int,
        user_id: int,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AIConversationMessage:
        """添加消息 - 优化版本"""
        
        # 验证对话权限
        conversation = AIConversationService.get_conversation_optimized(
            db, conversation_id, user_id
        )
        
        # 创建消息
        message = AIConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata or {},
            created_at=datetime.utcnow()
        )
        
        db.add(message)
        
        # 更新对话时间
        conversation.updated_at = datetime.utcnow()
        db.add(conversation)
        
        logger.info(f"在对话 {conversation_id} 中添加 {role} 消息")
        return message
    
    @staticmethod
    @handle_database_errors
    def delete_message_optimized(
        db: Session,
        message_id: int,
        user_id: int
    ) -> None:
        """删除消息 - 优化版本"""
        
        # 获取消息并验证权限
        message = db.query(AIConversationMessage).join(AIConversation).filter(
            AIConversationMessage.id == message_id,
            AIConversation.user_id == user_id
        ).first()
        
        if not message:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="消息不存在"
            )
        
        # 删除消息
        db.delete(message)
        
        logger.info(f"用户 {user_id} 删除消息 {message_id}")

class AIChatService:
    """AI聊天服务类"""
    
    @staticmethod
    @handle_database_errors
    async def process_chat_optimized(
        db: Session,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """处理聊天请求 - 优化版本"""
        
        options = options or {}
        
        # 获取或创建对话
        if conversation_id:
            conversation = AIConversationService.get_conversation_optimized(
                db, conversation_id, user_id
            )
        else:
            conversation = AIConversationService.create_conversation_optimized(
                db, user_id, initial_message=message
            )
            db.flush()
        
        # 添加用户消息
        user_message = AIMessageService.add_message_optimized(
            db, conversation.id, user_id, "user", message
        )
        
        # 处理AI响应
        try:
            ai_response = await AIChatService._generate_ai_response(
                db, user_id, message, conversation.id, options
            )
            
            # 添加AI消息
            ai_message = AIMessageService.add_message_optimized(
                db, conversation.id, user_id, "assistant", 
                ai_response["content"], ai_response.get("metadata", {})
            )
            
            return {
                "conversation_id": conversation.id,
                "user_message_id": user_message.id,
                "ai_message_id": ai_message.id,
                "response": ai_response["content"],
                "metadata": ai_response.get("metadata", {})
            }
            
        except Exception as e:
            logger.error(f"AI响应生成失败: {e}")
            # 添加错误消息
            error_message = f"抱歉，AI服务暂时不可用：{str(e)}"
            ai_message = AIMessageService.add_message_optimized(
                db, conversation.id, user_id, "assistant", 
                error_message, {"error": True}
            )
            
            return {
                "conversation_id": conversation.id,
                "user_message_id": user_message.id,
                "ai_message_id": ai_message.id,
                "response": error_message,
                "metadata": {"error": True}
            }
    
    @staticmethod
    async def _generate_ai_response(
        db: Session,
        user_id: int,
        message: str,
        conversation_id: int,
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成AI响应 - 内部方法"""
        
        try:
            # 导入AI服务组件
            from project.ai_providers.agent_orchestrator import AgentOrchestrator
            from project.ai_providers.security_utils import decrypt_key
            from project.ai_providers.ai_config import get_user_model_for_provider
            
            # 获取用户配置
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.llm_api_key_encrypted:
                raise Exception("用户AI配置不完整")
            
            # 解密API密钥
            api_key = decrypt_key(user.llm_api_key_encrypted)
            
            # 获取模型配置
            model_id = get_user_model_for_provider(
                user.llm_model_ids,
                user.llm_api_type,
                user.llm_model_id
            )
            
            # 初始化编排器
            orchestrator = AgentOrchestrator(
                api_key=api_key,
                api_type=user.llm_api_type,
                api_base_url=user.llm_api_base_url,
                model_id=model_id,
                user_id=user_id,
                db_session=db
            )
            
            # 获取对话历史
            recent_messages, _ = AIMessageService.get_messages_optimized(
                db, conversation_id, user_id, limit=10
            )
            
            # 构建上下文
            context_messages = []
            for msg in recent_messages[-10:]:  # 最近10条消息
                context_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # 处理请求
            request_params = {
                "message": message,
                "context_messages": context_messages,
                "conversation_id": str(conversation_id),
                **options
            }
            
            response = await orchestrator.process_request(request_params)
            
            return {
                "content": response.get("content", "抱歉，无法生成回复。"),
                "metadata": {
                    "model_used": response.get("model", model_id),
                    "tokens_used": response.get("tokens_used", 0),
                    "tools_used": response.get("tools_used", []),
                    "processing_time": response.get("processing_time", 0),
                    "cached": response.get("cached", False)
                }
            }
            
        except ImportError:
            # 降级处理
            logger.warning("AI提供者不可用，使用简化响应")
            return {
                "content": f"收到您的消息：{message}。AI服务正在维护中。",
                "metadata": {"fallback_mode": True}
            }
        except Exception as e:
            logger.error(f"AI响应生成失败: {e}")
            raise

class AISemanticSearchService:
    """AI语义搜索服务类"""
    
    @staticmethod
    @handle_database_errors
    async def semantic_search_optimized(
        db: Session,
        user_id: int,
        query: str,
        item_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """语义搜索 - 优化版本"""
        
        try:
            # 导入语义搜索组件
            from project.ai_providers.embedding_provider import get_embeddings_from_api
            from project.ai_providers.search_provider import SemanticSearchProvider
            
            # 获取查询向量
            query_embedding = await get_embeddings_from_api([query])
            if not query_embedding:
                raise Exception("无法生成查询向量")
            
            # 初始化搜索提供者
            search_provider = SemanticSearchProvider(db_session=db, user_id=user_id)
            
            # 执行搜索
            results = await search_provider.search(
                query_vector=query_embedding[0],
                item_types=item_types,
                limit=limit
            )
            
            logger.info(f"用户 {user_id} 语义搜索 '{query}'：找到 {len(results)} 个结果")
            return results
            
        except ImportError:
            logger.warning("语义搜索组件不可用")
            return []
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            raise

class AIUtilities:
    """AI工具类"""
    
    @staticmethod
    def format_conversation_response(
        conversation: AIConversation, 
        include_message_count: bool = True
    ) -> Dict[str, Any]:
        """格式化对话响应"""
        
        response = {
            "id": conversation.id,
            "title": conversation.title or "未命名对话",
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at
        }
        
        if include_message_count:
            response["message_count"] = getattr(conversation, '_message_count', 0)
        
        return response
    
    @staticmethod
    def format_message_response(message: AIConversationMessage) -> Dict[str, Any]:
        """格式化消息响应"""
        
        return {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "metadata": message.metadata or {},
            "created_at": message.created_at
        }
    
    @staticmethod
    def validate_chat_request(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证聊天请求数据"""
        
        # 验证消息内容
        message = data.get("message", "").strip()
        if not message:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="消息内容不能为空"
            )
        
        if len(message) > 10000:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="消息内容过长，最多10000个字符"
            )
        
        # 验证温度参数
        temperature = data.get("temperature", 0.7)
        if not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="温度参数必须在0-2之间"
            )
        
        return data
    
    @staticmethod
    def get_user_ai_stats(db: Session, user_id: int) -> Dict[str, Any]:
        """获取用户AI使用统计"""
        
        # 对话数量
        conversation_count = db.query(AIConversation).filter(
            AIConversation.user_id == user_id
        ).count()
        
        # 消息数量
        message_count = db.query(AIConversationMessage).join(AIConversation).filter(
            AIConversation.user_id == user_id
        ).count()
        
        # 今日消息数量
        today = datetime.now().date()
        today_message_count = db.query(AIConversationMessage).join(AIConversation).filter(
            AIConversation.user_id == user_id,
            func.date(AIConversationMessage.created_at) == today
        ).count()
        
        # 最近活跃对话
        recent_conversation = db.query(AIConversation).filter(
            AIConversation.user_id == user_id
        ).order_by(AIConversation.updated_at.desc()).first()
        
        return {
            "total_conversations": conversation_count,
            "total_messages": message_count,
            "today_messages": today_message_count,
            "last_conversation_time": recent_conversation.updated_at if recent_conversation else None
        }

logger.info("🤖 AI Service - AI服务层初始化完成")
