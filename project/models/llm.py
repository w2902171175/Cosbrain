# project/models/llm.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, event, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from project.base import Base
from project import oss_utils
from .mixins import TimestampMixin, OwnerMixin, UserServiceConfigMixin
import threading
import asyncio


class LLMProvider(Base, TimestampMixin):
    """LLM提供商模型"""
    __tablename__ = "llm_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, comment="提供商名称")
    provider_type = Column(String, nullable=False, comment="提供商类型")
    base_url = Column(String, nullable=True, comment="API基础URL")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    description = Column(Text, nullable=True, comment="提供商描述")
    
    # 关系
    user_configs = relationship("UserLLMConfig", back_populates="provider")

    def __repr__(self):
        return f"<LLMProvider(id={self.id}, name='{self.name}', type='{self.provider_type}')>"


class UserLLMConfig(Base, UserServiceConfigMixin):
    """用户LLM配置模型"""
    __tablename__ = "user_llm_configs"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("llm_providers.id"), nullable=False, comment="LLM提供商ID")
    
    # LLM特定配置
    model_name = Column(String, nullable=True, comment="模型名称")
    model_ids = Column(Text, nullable=True, comment="JSON格式存储多个模型ID")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    
    # 关系
    provider = relationship("LLMProvider", back_populates="user_configs")
    owner = relationship("User", back_populates="llm_configs")
    conversations = relationship("LLMConversation", back_populates="config")

    __table_args__ = (
        UniqueConstraint('owner_id', 'name', name='_user_llm_configs_owner_name_uc'),
    )

    def __repr__(self):
        return f"<UserLLMConfig(id={self.id}, user_id={self.owner_id}, name='{self.name}')>"


class LLMConversation(Base, TimestampMixin, OwnerMixin):
    """LLM对话模型"""
    __tablename__ = "llm_conversations"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("user_llm_configs.id"), nullable=True, comment="使用的LLM配置ID")
    title = Column(String, nullable=True, comment="对话标题")
    model_name = Column(String, nullable=True, comment="使用的模型名称")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    conversation_metadata = Column(JSONB, nullable=True, comment="对话元数据")
    
    # 关系
    config = relationship("UserLLMConfig", back_populates="conversations")
    messages = relationship("LLMMessage", back_populates="conversation", 
                          order_by="LLMMessage.created_at", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<LLMConversation(id={self.id}, user_id={self.owner_id}, title='{self.title}')>"


class LLMMessage(Base, TimestampMixin):
    """LLM消息模型"""
    __tablename__ = "llm_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("llm_conversations.id"), nullable=False, index=True, comment="对话ID")
    role = Column(String, nullable=False, comment="消息角色: user, assistant, system")
    content = Column(Text, nullable=False, comment="消息内容")
    message_metadata = Column(JSONB, nullable=True, comment="消息元数据")
    
    # 关系
    conversation = relationship("LLMConversation", back_populates="messages")

    def __repr__(self):
        return f"<LLMMessage(id={self.id}, role='{self.role}', conv_id={self.conversation_id})>"


class AIConversation(Base, TimestampMixin):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    
    # 用户关联
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="对话所属用户ID")
    title = Column(String, nullable=True, comment="对话标题（可由AI生成或用户自定义）")
    
    # 重写时间戳字段以保持现有字段名
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
                          comment="对话最后更新时间")

    user_owner = relationship("User", back_populates="ai_conversations")
    messages = relationship("AIConversationMessage", back_populates="conversation",
                            order_by="AIConversationMessage.sent_at", cascade="all, delete-orphan")
    temp_files = relationship("AIConversationTemporaryFile", back_populates="conversation",
                              cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AIConversation(id={self.id}, user_id={self.user_id}, title='{self.title[:20] if self.title else ''}')>"


class AIConversationMessage(Base):
    __tablename__ = "ai_conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), nullable=False, index=True,
                             comment="所属对话ID")

    # 消息角色: "user" (用户输入), "assistant" (LLM回答), "tool_call" (LLM决定调用工具), "tool_output" (工具执行结果)
    role = Column(String, nullable=False, comment="消息角色")
    content = Column(Text, nullable=False, comment="消息内容（文本）")

    # 存储工具调用和工具输出的原始JSON数据，以便更详细的记录和回放
    tool_calls_json = Column(JSONB, nullable=True, comment="如果角色是'tool_call'，存储工具调用的JSON数据")
    tool_output_json = Column(JSONB, nullable=True, comment="如果角色是'tool_output'，存储工具输出的JSON数据")

    # 存储本次消息生成时使用的LLM信息（如果角色是 assistant）
    llm_type_used = Column(String, nullable=True, comment="本次消息使用的LLM类型")
    llm_model_used = Column(String, nullable=True, comment="本次消息使用的LLM模型ID")

    sent_at = Column(DateTime, server_default=func.now(), nullable=False, comment="消息发送时间")

    conversation = relationship("AIConversation", back_populates="messages")

    def to_dict(self):
        """将AIConversationMessage对象转换为字典，用于LLM调用"""
        data = {
            "role": self.role,
            "content": self.content
        }
        if self.tool_calls_json:
            data["tool_calls_json"] = self.tool_calls_json
        if self.tool_output_json:
            data["tool_output_json"] = self.tool_output_json
        return data

    def __repr__(self):
        return f"<AIConversationMessage(id={self.id}, role='{self.role}', conv_id={self.conversation_id}, sent_at='{self.sent_at}')>"


class AIConversationTemporaryFile(Base):
    __tablename__ = "ai_conversation_temporary_files"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id"), nullable=False, index=True,
                             comment="所属AI对话的ID")
    oss_object_name = Column(String, nullable=False, comment="文件在OSS中的对象名称")
    original_filename = Column(String, nullable=True, comment="原始上传文件名")
    file_type = Column(String, nullable=False, comment="文件MIME类型")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    extracted_text = Column(Text, nullable=True, comment="从文件中提取的文本内容，用于RAG")
    embedding = Column(Vector(1024), nullable=True, comment="提取文本的嵌入向量")
    status = Column(String, default="pending", nullable=False, comment="处理状态：'pending', 'processing', 'completed', 'failed'")
    processing_message = Column(Text, nullable=True, comment="处理状态消息")

    conversation = relationship("AIConversation", back_populates="temp_files")

    __table_args__ = (
        # 确保同一个对话中，OSS对象名称是唯一的，防止重复记录
        UniqueConstraint('conversation_id', 'oss_object_name', name='_conv_temp_file_uc'),
    )

    def __repr__(self):
        return f"<AIConversationTemporaryFile(id={self.id}, conv_id={self.conversation_id}, filename='{self.original_filename}', status='{self.status}')>"


@event.listens_for(AIConversationTemporaryFile, 'before_delete')
def receive_before_delete(mapper, connection, target: AIConversationTemporaryFile):
    """
    在 AIConversationTemporaryFile 记录删除之前，从 OSS 删除对应的文件。
    """
    oss_object_name = target.oss_object_name
    if oss_object_name:
        print(f"DEBUG_OSS_DELETE_EVENT: 准备删除 OSS 文件: {oss_object_name} (关联 AI 临时文件 ID: {target.id})")
        # 使用同步方式调度异步任务，避免在事务中创建不安全的异步任务
        try:
            def delete_oss_file():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(oss_utils.delete_file_from_oss(oss_object_name))
                finally:
                    loop.close()
            
            thread = threading.Thread(target=delete_oss_file, daemon=True)
            thread.start()
        except Exception as e:
            print(f"ERROR_OSS_DELETE_EVENT: 删除OSS文件失败: {e}")
    else:
        print(f"WARNING_OSS_DELETE_EVENT: AI 临时文件 ID: {target.id} 没有关联的 OSS 对象名称，跳过 OSS 文件删除。")