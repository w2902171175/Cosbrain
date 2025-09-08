# project/services/llm_service.py
"""
LLM模块服务层 - 业务逻辑分离
基于优化框架为 LLM 模块提供高效的服务层实现
支持分布式缓存、负载均衡、异步处理等高级功能
"""
from typing import List, Optional, Dict, Any, Tuple, Union
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc, asc
from datetime import datetime, timedelta
import asyncio
import logging
import json
import time
from concurrent.futures import ThreadPoolExecutor

# 核心导入
from project.models import LLMProvider, UserLLMConfig, LLMConversation, LLMMessage
import project.schemas as schemas
from project.ai_providers.security_utils import decrypt_key, encrypt_key
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)

class LLMProviderService:
    """LLM提供商管理服务"""
    
    @staticmethod
    def get_llm_providers_optimized(
        db: Session, 
        skip: int = 0, 
        limit: int = 50,
        provider_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[List[LLMProvider], int]:
        """获取LLM提供商列表 - 优化版本"""
        try:
            # 构建查询
            query = db.query(LLMProvider)
            
            # 应用过滤条件
            if provider_type:
                query = query.filter(LLMProvider.provider_type == provider_type)
            if is_active is not None:
                query = query.filter(LLMProvider.is_active == is_active)
            
            # 排序：活跃状态优先，然后按创建时间
            query = query.order_by(
                desc(LLMProvider.is_active),
                desc(LLMProvider.created_at)
            )
            
            total = query.count()
            providers = query.offset(skip).limit(limit).all()
            
            logger.info(f"获取到 {len(providers)} 个LLM提供商")
            return providers, total
            
        except Exception as e:
            logger.error(f"获取LLM提供商列表失败: {e}")
            raise
    
    @staticmethod
    def create_llm_provider_optimized(
        db: Session, 
        provider_data: Dict[str, Any]
    ) -> LLMProvider:
        """创建LLM提供商 - 优化版本"""
        try:
            # 数据验证和处理
            validated_data = LLMUtilities.validate_provider_data(provider_data)
            
            # 创建提供商对象
            db_provider = LLMProvider(**validated_data)
            
            db.add(db_provider)
            db.commit()
            db.refresh(db_provider)
            
            # 清除相关缓存
            cache_manager.delete_pattern("llm_providers_*")
            
            logger.info(f"创建LLM提供商: {db_provider.name}")
            return db_provider
            
        except IntegrityError as e:
            db.rollback()
            logger.error(f"创建LLM提供商数据完整性错误: {e}")
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"创建LLM提供商失败: {e}")
            raise

class LLMConfigService:
    """用户LLM配置管理服务"""
    
    @staticmethod
    def get_user_llm_configs_optimized(
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 50,
        provider_type: Optional[str] = None
    ) -> Tuple[List[UserLLMConfig], int]:
        """获取用户LLM配置列表 - 优化版本"""
        try:
            # 优化查询：使用joinedload避免N+1问题
            query = db.query(UserLLMConfig).options(
                joinedload(UserLLMConfig.provider)
            ).filter(UserLLMConfig.owner_id == user_id)
            
            # 应用过滤条件
            if provider_type:
                query = query.join(LLMProvider).filter(
                    LLMProvider.provider_type == provider_type
                )
            
            # 排序：活跃配置优先，然后按更新时间
            query = query.order_by(
                desc(UserLLMConfig.is_active),
                desc(UserLLMConfig.updated_at)
            )
            
            total = query.count()
            configs = query.offset(skip).limit(limit).all()
            
            logger.info(f"用户 {user_id} 获取到 {len(configs)} 个LLM配置")
            return configs, total
            
        except Exception as e:
            logger.error(f"获取用户LLM配置失败: {e}")
            raise
    
    @staticmethod
    def create_llm_config_optimized(
        db: Session, 
        user_id: int, 
        config_data: Dict[str, Any]
    ) -> UserLLMConfig:
        """创建LLM配置 - 优化版本"""
        try:
            # 数据验证和处理
            validated_data = LLMUtilities.validate_config_data(config_data)
            
            # 加密API密钥
            if validated_data.get('api_key'):
                validated_data['api_key_encrypted'] = encrypt_key(validated_data.pop('api_key'))
            
            # 如果设置为激活，则先禁用其他配置
            if validated_data.get('is_active', False):
                LLMConfigService._deactivate_other_configs(db, user_id, validated_data.get('provider_id'))
            
            # 创建配置对象
            db_config = UserLLMConfig(
                owner_id=user_id,
                **validated_data
            )
            
            db.add(db_config)
            db.commit()
            db.refresh(db_config)
            
            # 清除相关缓存
            LLMUtilities.clear_user_cache(user_id)
            
            logger.info(f"用户 {user_id} 创建LLM配置 {db_config.id}")
            return db_config
            
        except IntegrityError as e:
            db.rollback()
            logger.error(f"创建LLM配置数据完整性错误: {e}")
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"创建LLM配置失败: {e}")
            raise
    
    @staticmethod
    def _deactivate_other_configs(
        db: Session, 
        user_id: int, 
        provider_id: Optional[int] = None,
        exclude_config_id: Optional[int] = None
    ):
        """禁用用户的其他LLM配置"""
        query = db.query(UserLLMConfig).filter(
            UserLLMConfig.owner_id == user_id,
            UserLLMConfig.is_active == True
        )
        
        if provider_id:
            query = query.filter(UserLLMConfig.provider_id == provider_id)
        
        if exclude_config_id:
            query = query.filter(UserLLMConfig.id != exclude_config_id)
        
        configs = query.all()
        for config in configs:
            config.is_active = False
        
        db.commit()

class LLMConversationService:
    """LLM对话管理服务"""
    
    @staticmethod
    def create_conversation_optimized(
        db: Session,
        user_id: int,
        conversation_data: Dict[str, Any]
    ) -> LLMConversation:
        """创建对话 - 优化版本"""
        try:
            # 验证数据
            validated_data = LLMUtilities.validate_conversation_data(conversation_data)
            
            # 创建对话对象
            db_conversation = LLMConversation(
                user_id=user_id,
                **validated_data
            )
            
            db.add(db_conversation)
            db.commit()
            db.refresh(db_conversation)
            
            logger.info(f"用户 {user_id} 创建对话 {db_conversation.id}")
            return db_conversation
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建对话失败: {e}")
            raise
    
    @staticmethod
    def get_user_conversations_optimized(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
        with_messages: bool = False
    ) -> Tuple[List[LLMConversation], int]:
        """获取用户对话列表 - 优化版本"""
        try:
            # 构建查询
            query = db.query(LLMConversation).filter(
                LLMConversation.user_id == user_id
            )
            
            # 可选加载消息
            if with_messages:
                query = query.options(selectinload(LLMConversation.messages))
            
            # 排序：按更新时间倒序
            query = query.order_by(desc(LLMConversation.updated_at))
            
            total = query.count()
            conversations = query.offset(skip).limit(limit).all()
            
            logger.info(f"用户 {user_id} 获取到 {len(conversations)} 个对话")
            return conversations, total
            
        except Exception as e:
            logger.error(f"获取用户对话失败: {e}")
            raise

class LLMInferenceService:
    """LLM推理服务"""
    
    @staticmethod
    async def generate_response_optimized(
        db: Session,
        user_id: int,
        conversation_id: Optional[int],
        message_data: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """生成LLM响应 - 优化版本"""
        try:
            # 获取用户激活的LLM配置
            active_config = await LLMInferenceService._get_active_config(db, user_id)
            if not active_config:
                return {
                    "status": "error",
                    "message": "用户没有激活的LLM配置"
                }
            
            # 检查分布式缓存
            cache_key = f"llm_response_{user_id}_{hash(str(message_data))}"
            cached_result = await LLMUtilities.get_distributed_cache(cache_key)
            if cached_result and not stream:
                return cached_result
            
            # 创建或获取对话
            conversation = await LLMInferenceService._get_or_create_conversation(
                db, user_id, conversation_id, message_data
            )
            
            # 保存用户消息
            user_message = await LLMInferenceService._save_user_message(
                db, conversation.id, message_data
            )
            
            # 执行推理
            inference_result = await LLMInferenceService._perform_inference(
                active_config, conversation, message_data, stream
            )
            
            # 保存AI响应
            if inference_result.get("status") == "success":
                await LLMInferenceService._save_ai_message(
                    db, conversation.id, inference_result.get("response", "")
                )
                
                # 缓存结果
                if not stream:
                    await LLMUtilities.set_distributed_cache(
                        cache_key, inference_result, ttl=1800
                    )
            
            return inference_result
            
        except Exception as e:
            logger.error(f"LLM推理失败: {e}")
            return {
                "status": "error",
                "message": f"推理失败: {str(e)}"
            }
    
    @staticmethod
    async def _get_active_config(db: Session, user_id: int) -> Optional[UserLLMConfig]:
        """获取用户激活的LLM配置"""
        return db.query(UserLLMConfig).options(
            joinedload(UserLLMConfig.provider)
        ).filter(
            UserLLMConfig.owner_id == user_id,
            UserLLMConfig.is_active == True
        ).first()
    
    @staticmethod
    async def _get_or_create_conversation(
        db: Session,
        user_id: int,
        conversation_id: Optional[int],
        message_data: Dict[str, Any]
    ) -> LLMConversation:
        """获取或创建对话"""
        if conversation_id:
            conversation = db.query(LLMConversation).filter(
                LLMConversation.id == conversation_id,
                LLMConversation.user_id == user_id
            ).first()
            if conversation:
                return conversation
        
        # 创建新对话
        conversation_data = {
            "title": message_data.get("content", "")[:50] + "...",
            "model_name": message_data.get("model", "default"),
            "system_prompt": message_data.get("system_prompt")
        }
        
        return LLMConversationService.create_conversation_optimized(
            db, user_id, conversation_data
        )
    
    @staticmethod
    async def _save_user_message(
        db: Session,
        conversation_id: int,
        message_data: Dict[str, Any]
    ) -> LLMMessage:
        """保存用户消息"""
        db_message = LLMMessage(
            conversation_id=conversation_id,
            role="user",
            content=message_data.get("content", ""),
            metadata=message_data.get("metadata", {})
        )
        
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        return db_message
    
    @staticmethod
    async def _save_ai_message(
        db: Session,
        conversation_id: int,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LLMMessage:
        """保存AI响应消息"""
        db_message = LLMMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            metadata=metadata or {}
        )
        
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        return db_message
    
    @staticmethod
    async def _perform_inference(
        config: UserLLMConfig,
        conversation: LLMConversation,
        message_data: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """执行实际的推理"""
        try:
            # 构建推理参数
            inference_params = {
                "model": message_data.get("model", "gpt-3.5-turbo"),
                "messages": await LLMInferenceService._build_message_history(conversation),
                "temperature": message_data.get("temperature", 0.7),
                "max_tokens": message_data.get("max_tokens", 2048),
                "stream": stream
            }
            
            # 记录推理开始时间
            start_time = time.time()
            
            # 模拟推理过程（实际应该调用具体的LLM API）
            if stream:
                response = await LLMInferenceService._mock_stream_inference(inference_params)
            else:
                response = await LLMInferenceService._mock_inference(inference_params)
            
            # 计算推理时间
            inference_time = time.time() - start_time
            
            return {
                "status": "success",
                "response": response,
                "conversation_id": conversation.id,
                "inference_time": inference_time,
                "token_usage": {
                    "prompt_tokens": len(str(inference_params["messages"])) // 4,
                    "completion_tokens": len(response) // 4,
                    "total_tokens": (len(str(inference_params["messages"])) + len(response)) // 4
                },
                "model": inference_params["model"],
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"推理执行失败: {e}")
            return {
                "status": "error",
                "message": f"推理执行失败: {str(e)}"
            }
    
    @staticmethod
    async def _build_message_history(conversation: LLMConversation) -> List[Dict[str, str]]:
        """构建消息历史"""
        messages = []
        
        # 添加系统提示
        if conversation.system_prompt:
            messages.append({
                "role": "system",
                "content": conversation.system_prompt
            })
        
        # 添加历史消息（限制数量以控制上下文长度）
        recent_messages = conversation.messages[-20:] if conversation.messages else []
        for msg in recent_messages:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return messages
    
    @staticmethod
    async def _mock_inference(params: Dict[str, Any]) -> str:
        """模拟推理（实际应该调用真实的LLM API）"""
        # 模拟推理延迟
        await asyncio.sleep(0.1)
        
        user_content = ""
        for msg in params["messages"]:
            if msg["role"] == "user":
                user_content = msg["content"]
                break
        
        return f"这是对 '{user_content[:30]}...' 的回复。这是一个模拟的LLM响应。"
    
    @staticmethod
    async def _mock_stream_inference(params: Dict[str, Any]) -> str:
        """模拟流式推理"""
        full_response = await LLMInferenceService._mock_inference(params)
        
        # 这里应该返回一个异步生成器，简化为返回完整响应
        return full_response

class LLMMonitoringService:
    """LLM监控服务"""
    
    @staticmethod
    async def get_usage_statistics_optimized(
        db: Session,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """获取使用统计 - 优化版本"""
        try:
            # 构建查询
            query = db.query(LLMMessage)
            
            if user_id:
                query = query.join(LLMConversation).filter(
                    LLMConversation.user_id == user_id
                )
            
            if start_date:
                query = query.filter(LLMMessage.created_at >= start_date)
            
            if end_date:
                query = query.filter(LLMMessage.created_at <= end_date)
            
            # 统计数据
            total_messages = query.count()
            user_messages = query.filter(LLMMessage.role == "user").count()
            ai_messages = query.filter(LLMMessage.role == "assistant").count()
            
            # 按模型统计
            model_stats = {}
            conversations = query.join(LLMConversation).with_entities(
                LLMConversation.model_name,
                func.count(LLMMessage.id)
            ).group_by(LLMConversation.model_name).all()
            
            for model, count in conversations:
                model_stats[model] = count
            
            return {
                "total_messages": total_messages,
                "user_messages": user_messages,
                "ai_messages": ai_messages,
                "model_stats": model_stats,
                "period": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None
                }
            }
            
        except Exception as e:
            logger.error(f"获取使用统计失败: {e}")
            raise

class LLMUtilities:
    """LLM工具类"""
    
    @staticmethod
    def validate_provider_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证LLM提供商数据"""
        required_fields = ['name', 'provider_type', 'base_url']
        for field in required_fields:
            if not data.get(field):
                raise ValueError(f"缺少必需字段: {field}")
        
        # 验证提供商类型
        valid_providers = ['openai', 'azure', 'anthropic', 'google', 'baidu', 'alibaba', 'local']
        if data.get('provider_type') not in valid_providers:
            raise ValueError(f"不支持的LLM提供商: {data.get('provider_type')}")
        
        return data
    
    @staticmethod
    def validate_config_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证LLM配置数据"""
        required_fields = ['provider_id', 'config_name']
        for field in required_fields:
            if not data.get(field):
                raise ValueError(f"缺少必需字段: {field}")
        
        return data
    
    @staticmethod
    def validate_conversation_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证对话数据"""
        allowed_fields = ['title', 'model_name', 'system_prompt', 'metadata']
        
        validated_data = {}
        for key, value in data.items():
            if key in allowed_fields and value is not None:
                validated_data[key] = value
        
        return validated_data
    
    @staticmethod
    async def get_distributed_cache(key: str) -> Optional[Any]:
        """获取分布式缓存"""
        try:
            return cache_manager.get(key)
        except Exception as e:
            logger.warning(f"获取分布式缓存失败: {e}")
            return None
    
    @staticmethod
    async def set_distributed_cache(key: str, value: Any, ttl: int = 3600):
        """设置分布式缓存"""
        try:
            cache_manager.set(key, value, ttl=ttl)
        except Exception as e:
            logger.warning(f"设置分布式缓存失败: {e}")
    
    @staticmethod
    def clear_user_cache(user_id: int):
        """清除用户相关缓存"""
        cache_patterns = [
            f"user_llm_configs_{user_id}*",
            f"llm_response_{user_id}_*",
            f"user_conversations_{user_id}*"
        ]
        for pattern in cache_patterns:
            cache_manager.delete_pattern(pattern)
    
    @staticmethod
    def clear_config_cache(config_id: int):
        """清除配置相关缓存"""
        cache_key = f"llm_config_{config_id}"
        cache_manager.delete(cache_key)
    
    @staticmethod
    def build_safe_response_dict(config: UserLLMConfig) -> Dict[str, Any]:
        """构建安全的响应字典"""
        return {
            'id': config.id,
            'owner_id': config.owner_id,
            'provider_id': config.provider_id,
            'config_name': config.config_name,
            'model_name': getattr(config, 'model_name', None),
            'temperature': getattr(config, 'temperature', None),
            'max_tokens': getattr(config, 'max_tokens', None),
            'is_active': config.is_active,
            'created_at': config.created_at or datetime.now(),
            'updated_at': config.updated_at or config.created_at or datetime.now(),
            'provider': {
                'name': config.provider.name if config.provider else None,
                'provider_type': config.provider.provider_type if config.provider else None
            } if hasattr(config, 'provider') and config.provider else None,
            'api_key_encrypted': None  # 永远不返回加密的密钥
        }
