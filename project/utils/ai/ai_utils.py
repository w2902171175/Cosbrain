"""
AI工具函数
从路由层移动过来的AI相关工具函数，提高代码复用性
"""

import asyncio
import time
import os
import re
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

# 项目依赖
from project.models import User, AIConversationTemporaryFile
from project.ai_providers.document_processor import extract_text_from_document
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_user_model_for_provider
import project.oss_utils as oss_utils

# 企业级日志
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    logger = get_ai_logger("ai_utils")
except ImportError:
    import logging
    logger = logging.getLogger("ai_utils")


def clean_optional_json_string_input(input_str: Optional[str]) -> Optional[str]:
    """
    清理从表单接收到的可选JSON字符串参数。
    将 None, 空字符串, 或常见的默认值字面量转换为 None。
    
    Args:
        input_str: 待清理的输入字符串
        
    Returns:
        清理后的字符串或None
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
) -> bool:
    """
    在后台处理AI对话的临时上传文件：从OSS下载、提取文本、生成嵌入并更新记录。
    
    Args:
        temp_file_id: 临时文件ID
        user_id: 用户ID
        oss_object_name: OSS对象名称
        file_type: 文件类型
        db_session: 数据库会话
        
    Returns:
        bool: 处理是否成功
    """
    logger.info(f"开始后台处理AI临时文件 ID: {temp_file_id} (OSS: {oss_object_name})")
    
    try:
        # 获取临时文件记录
        db_temp_file_record = await _get_temp_file_record(temp_file_id, db_session)
        if not db_temp_file_record:
            return False

        # 下载文件
        downloaded_bytes = await _download_file_from_oss(
            db_temp_file_record, oss_object_name, db_session
        )
        if not downloaded_bytes:
            return False

        # 提取文本
        extracted_text = await _extract_text_from_file(
            db_temp_file_record, downloaded_bytes, file_type, db_session
        )
        if not extracted_text:
            return False

        # 生成嵌入
        success = await _generate_and_store_embeddings(
            db_temp_file_record, extracted_text, user_id, db_session
        )
        
        if success:
            await _update_file_status(db_temp_file_record, "completed", 
                                    "文件处理完成", db_session)
            logger.info(f"AI临时文件 {temp_file_id} 处理完成")
        
        return success

    except Exception as e:
        logger.error(f"AI临时文件 {temp_file_id} 处理失败: {e}")
        if 'db_temp_file_record' in locals():
            await _update_file_status(db_temp_file_record, "failed", 
                                    f"处理失败: {str(e)}", db_session)
        return False


async def _get_temp_file_record(temp_file_id: int, db_session: Session) -> Optional[AIConversationTemporaryFile]:
    """获取临时文件记录"""
    db_temp_file_record = db_session.query(AIConversationTemporaryFile).filter(
        AIConversationTemporaryFile.id == temp_file_id).first()
    
    if not db_temp_file_record:
        logger.error(f"AI临时文件 {temp_file_id} 在后台处理中未找到")
        return None

    # 更新状态为processing
    db_temp_file_record.status = "processing"
    db_temp_file_record.processing_message = "正在从云存储下载文件..."
    db_session.add(db_temp_file_record)
    db_session.commit()
    
    return db_temp_file_record


async def _download_file_from_oss(
    db_temp_file_record: AIConversationTemporaryFile, 
    oss_object_name: str, 
    db_session: Session
) -> Optional[bytes]:
    """从OSS下载文件"""
    try:
        downloaded_bytes = await oss_utils.download_file_from_oss(oss_object_name)
        if not downloaded_bytes:
            await _update_file_status(db_temp_file_record, "failed", 
                                    "从云存储下载文件失败或文件内容为空。", db_session)
            logger.error(f"AI临时文件 {db_temp_file_record.id} 从OSS下载失败或内容为空")
            return None
        return downloaded_bytes
    except Exception as oss_error:
        await _update_file_status(db_temp_file_record, "failed", 
                                f"OSS下载失败: {oss_error}", db_session)
        logger.error(f"AI临时文件 {db_temp_file_record.id} OSS下载异常: {oss_error}")
        return None


async def _extract_text_from_file(
    db_temp_file_record: AIConversationTemporaryFile,
    downloaded_bytes: bytes,
    file_type: str,
    db_session: Session
) -> Optional[str]:
    """从文件中提取文本"""
    try:
        await _update_file_status(db_temp_file_record, "processing", 
                                "正在提取文本...", db_session)
        
        loop = asyncio.get_running_loop()
        extracted_text = await loop.run_in_executor(
            None,
            extract_text_from_document,
            downloaded_bytes,
            file_type
        )
        
        if not extracted_text or len(extracted_text.strip()) == 0:
            await _update_file_status(db_temp_file_record, "failed", 
                                    "文件中未提取到有效文本内容。", db_session)
            logger.error(f"AI临时文件 {db_temp_file_record.id} 未提取到有效文本")
            return None
        
        return extracted_text
        
    except Exception as extract_error:
        await _update_file_status(db_temp_file_record, "failed", 
                                f"文本提取失败: {extract_error}", db_session)
        logger.error(f"AI临时文件 {db_temp_file_record.id} 文本提取异常: {extract_error}")
        return None


async def _generate_and_store_embeddings(
    db_temp_file_record: AIConversationTemporaryFile,
    extracted_text: str,
    user_id: int,
    db_session: Session
) -> bool:
    """生成并存储嵌入向量"""
    try:
        # 生成嵌入
        user_config = await _get_user_llm_config(user_id, db_session)
        
        await _update_file_status(db_temp_file_record, "processing", 
                                "正在生成嵌入向量...", db_session)

        try:
            embeddings_list = await get_embeddings_from_api(
                [extracted_text],
                api_key=user_config.get('api_key'),
                llm_type=user_config.get('llm_type'),
                llm_base_url=user_config.get('base_url'),
                llm_model_id=user_config.get('model_id')
            )
        except Exception as embedding_error:
            logger.warning(f"文件 {db_temp_file_record.id} 嵌入生成失败: {embedding_error}，使用零向量")
            embeddings_list = []

        final_embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if embeddings_list and len(embeddings_list) > 0:
            final_embedding = embeddings_list[0]

        # 更新数据库记录
        db_temp_file_record.extracted_text = extracted_text
        db_temp_file_record.embedding = final_embedding
        db_session.add(db_temp_file_record)
        db_session.commit()
        
        logger.info(f"AI临时文件 {db_temp_file_record.id} 嵌入生成完成。提取文本长度: {len(extracted_text)} 字符")
        return True

    except Exception as e:
        logger.error(f"AI临时文件 {db_temp_file_record.id} 嵌入生成失败: {e}")
        return False


async def _update_file_status(
    db_temp_file_record: AIConversationTemporaryFile, 
    status: str, 
    message: str, 
    db_session: Session
) -> None:
    """更新文件处理状态的辅助函数"""
    db_temp_file_record.status = status
    db_temp_file_record.processing_message = message
    db_session.add(db_temp_file_record)
    db_session.commit()


async def _get_user_llm_config(user_id: int, db_session: Session) -> Dict[str, Any]:
    """获取用户LLM配置的辅助函数"""
    user_obj = db_session.query(User).filter(User.id == user_id).first()
    config = {
        'api_key': None,
        'llm_type': None,
        'base_url': None,
        'model_id': None
    }

    if user_obj and user_obj.llm_api_type == "siliconflow" and user_obj.llm_api_key_encrypted:
        try:
            config['api_key'] = decrypt_key(user_obj.llm_api_key_encrypted)
            config['llm_type'] = user_obj.llm_api_type
            config['base_url'] = user_obj.llm_api_base_url
            config['model_id'] = get_user_model_for_provider(
                user_obj.llm_model_ids,
                user_obj.llm_api_type,
                user_obj.llm_model_id
            )
        except Exception as e:
            logger.error(f"解密用户 {user_id} LLM API 密钥失败: {e}")

    return config


def format_response_time(start_time: float) -> float:
    """格式化响应时间（毫秒）"""
    return round((time.time() - start_time) * 1000, 2)


def validate_file_type(filename: str, allowed_types: list) -> bool:
    """验证文件类型是否被允许"""
    file_ext = os.path.splitext(filename)[1].lower()
    return file_ext in allowed_types


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除不安全字符"""
    # 移除路径分隔符和其他不安全字符
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 限制长度
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    return sanitized


def get_file_size_mb(file_size: int) -> float:
    """将文件大小转换为MB"""
    return round(file_size / (1024 * 1024), 2)
