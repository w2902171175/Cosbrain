# project/services/file_service.py
import os
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from project.models import ChatRoom, ChatRoomMember
import project.oss_utils as oss_utils

# 可选的 magic 导入
try:
    import magic
except ImportError:
    magic = None

class FileUploadService:
    # 安全配置
    MAX_FILE_SIZE_MB = {
        'image': 10,      # 图片最大10MB
        'video': 100,     # 视频最大100MB
        'audio': 50,      # 音频最大50MB
        'document': 20,   # 文档最大20MB
        'general': 20     # 通用文件最大20MB
    }
    
    # 允许的文件类型
    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    ALLOWED_VIDEO_TYPES = {'video/mp4', 'video/avi', 'video/mov', 'video/wmv'}
    ALLOWED_AUDIO_TYPES = {'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/m4a'}
    ALLOWED_DOCUMENT_TYPES = {
        'application/pdf', 'application/msword', 'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'text/plain'
    }
    
    # 危险文件扩展名
    DANGEROUS_EXTENSIONS = {
        '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar',
        '.php', '.asp', '.aspx', '.jsp', '.sh', '.ps1', '.py', '.rb', '.pl'
    }

    @staticmethod
    async def validate_file_security(file_content: bytes, filename: str, content_type: str) -> bool:
        """验证文件安全性"""
        # 检查文件扩展名
        file_ext = os.path.splitext(filename.lower())[1]
        if file_ext in FileUploadService.DANGEROUS_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不允许的文件类型: {file_ext}"
            )
        
        # 检查文件头部魔数
        if magic:
            try:
                detected_type = magic.from_buffer(file_content, mime=True)
                if detected_type != content_type:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="文件类型与内容不匹配"
                    )
            except Exception:
                pass  # 如果检测失败，跳过此检查
        
        # 检查文件大小
        if len(file_content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件为空"
            )
        
        return True

    @staticmethod
    async def generate_secure_filename(original_filename: str, user_id: int) -> str:
        """生成安全的文件名"""
        # 获取文件扩展名
        file_ext = os.path.splitext(original_filename)[1].lower()
        
        # 生成UUID文件名
        unique_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return f"{user_id}_{timestamp}_{unique_id}{file_ext}"

    @staticmethod
    async def validate_and_upload_file(
        file: UploadFile, 
        user_id: int, 
        file_type: str = "general"
    ) -> Dict[str, str]:
        """统一的文件验证和上传逻辑"""
        # 读取文件内容
        file_bytes = await file.read()
        
        # 检查文件大小限制
        max_size_mb = FileUploadService.MAX_FILE_SIZE_MB.get(file_type, 20)
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if len(file_bytes) > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件大小超过限制 ({max_size_mb}MB)"
            )
        
        # 安全验证
        await FileUploadService.validate_file_security(file_bytes, file.filename, file.content_type)
        
        # 验证文件类型
        await FileUploadService._validate_file_type(file.content_type, file_type)
        
        # 生成安全文件名
        secure_filename = await FileUploadService.generate_secure_filename(file.filename, user_id)
        
        # 上传到OSS
        try:
            media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=f"chat_files/{secure_filename}",
                content_type=file.content_type
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"文件上传失败: {str(e)}"
            )
        
        return {
            "media_url": media_url,
            "file_size": len(file_bytes),
            "original_filename": file.filename,
            "secure_filename": secure_filename,
            "content_type": file.content_type
        }

    @staticmethod
    async def _validate_file_type(content_type: str, file_type: str) -> bool:
        """验证文件类型"""
        type_mapping = {
            'image': FileUploadService.ALLOWED_IMAGE_TYPES,
            'video': FileUploadService.ALLOWED_VIDEO_TYPES,
            'audio': FileUploadService.ALLOWED_AUDIO_TYPES,
            'document': FileUploadService.ALLOWED_DOCUMENT_TYPES,
        }
        
        if file_type in type_mapping:
            allowed_types = type_mapping[file_type]
            if content_type not in allowed_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的{file_type}文件类型: {content_type}"
                )
        
        return True

    @staticmethod
    async def stream_upload_file(file: UploadFile, chunk_size: int = 8192, max_size: int = 100 * 1024 * 1024) -> bytes:
        """流式处理文件上传"""
        chunks = []
        total_size = 0
        
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            
            chunks.append(chunk)
            total_size += len(chunk)
            
            # 检查文件大小限制
            if total_size > max_size:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="文件过大"
                )
        
        return b''.join(chunks)

    @staticmethod
    async def batch_upload_files(
        files: List[UploadFile], 
        user_id: int, 
        file_type: str = "general"
    ) -> List[Dict[str, str]]:
        """批量上传文件"""
        if len(files) > 10:  # 限制批量上传数量
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="单次最多只能上传10个文件"
            )
        
        results = []
        for file in files:
            try:
                result = await FileUploadService.validate_and_upload_file(file, user_id, file_type)
                results.append(result)
            except Exception as e:
                # 如果某个文件上传失败，记录错误但继续处理其他文件
                results.append({
                    "error": str(e),
                    "filename": file.filename
                })
        
        return results

    @staticmethod
    async def cleanup_expired_files(db: Session, days: int = 30):
        """清理过期文件（管理员功能）"""
        # 这里应该实现文件清理逻辑
        # 由于涉及到OSS文件删除，需要谨慎处理
        expiry_date = datetime.now() - timedelta(days=days)
        
        # 查找过期的临时文件记录
        # 实际实现需要根据具体的文件记录表结构来调整
        pass
