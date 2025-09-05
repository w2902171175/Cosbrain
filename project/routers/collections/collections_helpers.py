# project/routers/collections/collections_helpers.py
"""
收藏系统内部辅助函数

提供收藏系统内部使用的辅助函数，包括：
- 文件上传处理
- 内容类型判断
- 收藏内容创建的内部逻辑
- 响应对象构建
"""

import os
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# 第三方库导入
from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session

# 项目内导入
from project.models import CollectedContent, Folder, ChatMessage, ForumTopic
import project.schemas as schemas
import project.oss_utils as oss_utils
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR

# 工具函数导入
from .collections_utils import (
    extract_shared_item_info,
    extract_url_info,
    generate_auto_tags,
    get_folder_path
)

# 设置日志记录器
logger = logging.getLogger(__name__)

# ================== 文件处理配置 ==================

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {
    'image': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'},
    'video': {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm'},
    'audio': {'.mp3', '.wav', '.aac', '.ogg', '.m4a'},
    'document': {'.pdf', '.doc', '.docx', '.txt', '.rtf', '.md'},
    'archive': {'.zip', '.rar', '.7z', '.tar', '.gz'},
    'other': {'.json', '.xml', '.csv', '.xlsx', '.pptx'}
}

# ================== 文件处理函数 ==================

def validate_file_upload(file: UploadFile) -> Dict[str, Any]:
    """验证文件上传"""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )
    
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    # 确定文件类型
    file_type = 'other'
    for type_name, extensions in ALLOWED_EXTENSIONS.items():
        if file_extension in extensions:
            file_type = type_name
            break
    
    return {
        'file_type': file_type,
        'file_extension': file_extension,
        'original_filename': file.filename
    }

async def handle_file_upload(file: UploadFile) -> Dict[str, Any]:
    """处理文件上传 - 优化版本"""
    try:
        # 验证文件
        validation_result = validate_file_upload(file)
        
        # 读取文件内容
        file_bytes = await file.read()
        file_size = len(file_bytes)
        
        # 检查文件大小
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE // (1024*1024)}MB）"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件内容为空"
            )
        
        # 生成唯一文件名
        file_extension = validation_result['file_extension']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        object_name = f"collections/{validation_result['file_type']}/{timestamp}_{unique_id}{file_extension}"
        
        # 上传到OSS
        await oss_utils.upload_file_to_oss(file_bytes, object_name, file.content_type)
        
        logger.info(f"文件上传成功: {object_name}, 大小: {file_size} bytes")
        
        return {
            "bytes": file_bytes,
            "object_name": object_name,
            "content_type": file.content_type,
            "filename": validation_result['original_filename'],
            "size": file_size,
            "file_type": validation_result['file_type'],
            "url": f"{oss_utils.S3_BASE_URL.rstrip('/')}/{object_name}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件上传失败: {str(e)}"
        )

# ================== 内容类型判断函数 ==================

def get_content_type_from_chat_message(chat_message: ChatMessage) -> str:
    """根据聊天消息确定收藏内容类型"""
    if chat_message.message_type == "image":
        return "image"
    elif chat_message.message_type == "video":
        return "video"
    elif chat_message.message_type == "audio" or chat_message.message_type == "voice":
        return "audio"
    elif chat_message.message_type == "file":
        return "file"
    else:
        return "text"

def get_content_type_from_forum_topic(forum_topic: ForumTopic) -> str:
    """根据论坛话题确定收藏内容类型"""
    if forum_topic.media_url:
        if forum_topic.media_type == "image":
            return "image"
        elif forum_topic.media_type == "video":
            return "video"
        elif forum_topic.media_type == "file":
            return "file"
    return "forum_topic"

# ================== 收藏内容创建函数 ==================

async def create_collected_content_item_internal(
    db: Session,
    current_user_id: int,
    content_data: schemas.CollectedContentCreateNew,
    uploaded_file_info: Optional[Dict[str, Any]] = None
) -> CollectedContent:
    """内部辅助函数：处理收藏内容的创建逻辑 - 优化版本"""
    try:
        # 验证文件夹权限
        if content_data.folder_id:
            from .collections_utils import PermissionValidator
            PermissionValidator.check_folder_access(db, content_data.folder_id, current_user_id)
        
        # 验证必填字段
        if not any([content_data.title, content_data.content, content_data.url, 
                   content_data.shared_item_id, uploaded_file_info]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="至少需要提供标题、内容、URL、关联资源或上传文件中的一个"
            )
        
        # 初始化最终值
        final_title = content_data.title
        final_type = content_data.type
        final_url = content_data.url
        final_content = content_data.content
        final_author = content_data.author
        final_tags = content_data.tags
        final_thumbnail = content_data.thumbnail
        final_duration = content_data.duration
        final_file_size = content_data.file_size
        final_status = content_data.status or "active"
        
        # 处理上传文件
        if uploaded_file_info:
            final_url = uploaded_file_info["url"]
            final_file_size = uploaded_file_info["size"]
            final_type = uploaded_file_info.get("file_type", "file")
            
            if not final_title and uploaded_file_info["filename"]:
                final_title = uploaded_file_info["filename"]
            
            if not final_content:
                final_content = f"上传的{final_type}: {uploaded_file_info['filename']}"
        
        # 处理内部资源收藏
        elif content_data.shared_item_type and content_data.shared_item_id:
            try:
                source_info = await extract_shared_item_info(
                    db, content_data.shared_item_type, content_data.shared_item_id
                )
                
                if not final_title:
                    final_title = source_info.get("title", f"{content_data.shared_item_type} #{content_data.shared_item_id}")
                if not final_content:
                    final_content = source_info.get("content")
                if not final_url:
                    final_url = source_info.get("url")
                if not final_author:
                    final_author = source_info.get("author")
                if not final_tags:
                    final_tags = source_info.get("tags")
                if not final_type:
                    final_type = content_data.shared_item_type
                if not final_thumbnail:
                    final_thumbnail = source_info.get("thumbnail")
            except Exception as e:
                logger.warning(f"获取内部资源信息失败: {e}")
        
        # 处理网页链接
        elif content_data.url and getattr(content_data, 'auto_extract', False):
            try:
                extracted_info = await extract_url_info(content_data.url)
                if not final_title:
                    final_title = extracted_info.get("title")
                if not final_content:
                    final_content = extracted_info.get("description")
                if not final_thumbnail:
                    final_thumbnail = extracted_info.get("thumbnail")
                if not final_author:
                    final_author = extracted_info.get("author")
            except Exception as e:
                logger.warning(f"网页信息提取失败 {content_data.url}: {e}")
        
        # 设置默认值
        if not final_title:
            if final_type == "link" and final_url:
                final_title = final_url
            else:
                final_title = "无标题收藏"
        
        if not final_type:
            final_type = "link" if final_url else "text"
        
        # 处理标签
        if isinstance(final_tags, list):
            final_tags = ",".join(final_tags)
        
        # 自动生成标签
        if getattr(content_data, 'auto_tag', False) and not final_tags:
            final_tags = generate_auto_tags(final_title, final_content, final_type)
        
        # 构建组合文本
        combined_text_parts = []
        if final_title:
            combined_text_parts.append(final_title)
        if final_content:
            combined_text_parts.append(final_content)
        if final_author:
            combined_text_parts.append(final_author)
        if final_tags:
            combined_text_parts.append(final_tags)
        
        combined_text = " ".join(combined_text_parts)
        
        # 创建收藏内容实例
        collected_content = CollectedContent(
            owner_id=current_user_id,
            folder_id=content_data.folder_id,
            title=final_title,
            type=final_type,
            url=final_url,
            content=final_content,
            author=final_author,
            tags=final_tags,
            thumbnail=final_thumbnail,
            duration=final_duration,
            file_size=final_file_size,
            status=final_status,
            priority=content_data.priority or 3,
            notes=content_data.notes,
            is_starred=content_data.is_starred or False,
            shared_item_type=content_data.shared_item_type,
            shared_item_id=content_data.shared_item_id,
            combined_text=combined_text,
            embedding=GLOBAL_PLACEHOLDER_ZERO_VECTOR,
            access_count=0
        )
        
        return collected_content
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建收藏内容失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建收藏内容失败: {str(e)}"
        )

# ================== 响应构建函数 ==================

async def build_content_response(
    content: CollectedContent, 
    db: Session, 
    current_user_id: int
) -> schemas.CollectedContentResponseNew:
    """构建收藏内容响应对象"""
    try:
        # 获取文件夹信息
        folder = db.query(Folder).filter(Folder.id == content.folder_id).first()
        folder_path = await get_folder_path(db, content.folder_id, current_user_id)
        folder_path_names = [item["name"] for item in folder_path] if folder_path else []
        
        return schemas.CollectedContentResponseNew(
            id=content.id,
            owner_id=content.owner_id,
            title=content.title,
            type=content.type,
            url=content.url,
            content=content.content,
            tags=content.tags.split(",") if content.tags else [],
            folder_id=content.folder_id,
            priority=content.priority,
            notes=content.notes,
            is_starred=content.is_starred,
            thumbnail=content.thumbnail,
            author=content.author,
            duration=content.duration,
            file_size=content.file_size,
            status=content.status,
            shared_item_type=content.shared_item_type,
            shared_item_id=content.shared_item_id,
            access_count=content.access_count,
            folder_name=folder.name if folder else None,
            folder_path=folder_path_names,
            created_at=content.created_at,
            updated_at=content.updated_at
        )
    
    except Exception as e:
        logger.error(f"构建响应对象失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"构建响应对象失败: {str(e)}"
        )
