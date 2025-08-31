# project/utils/file_upload.py
import os
import asyncio
import uuid
import hashlib
import tempfile
import time
from typing import Dict, List, Optional, Tuple, Any
from fastapi import UploadFile, HTTPException
from PIL import Image, ImageOps
from io import BytesIO
import logging

from oss_utils import get_s3_client, S3_BUCKET_NAME, S3_BASE_URL
from .file_security import EnhancedFileSecurityValidator, validate_file_security

logger = logging.getLogger(__name__)

class ChunkedUploadManager:
    """分片上传管理器"""
    
    def __init__(self):
        self.upload_sessions = {}  # 存储上传会话信息
        self.chunk_size = 5 * 1024 * 1024  # 5MB 每片
        self.max_chunks = 1000  # 最大分片数
        
    def start_upload_session(self, filename: str, file_size: int, content_type: str, user_id: int) -> Dict[str, Any]:
        """开始分片上传会话"""
        # 验证文件基本信息
        validator = EnhancedFileSecurityValidator()
        
        is_valid, message = validator.validate_filename(filename)
        if not is_valid:
            raise HTTPException(status_code=400, detail=message)
            
        is_valid, message = validator.validate_file_size(file_size, filename)
        if not is_valid:
            raise HTTPException(status_code=400, detail=message)
            
        is_valid, message = validator.validate_mime_type(content_type, filename)
        if not is_valid:
            raise HTTPException(status_code=400, detail=message)
        
        # 计算分片数量
        total_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        if total_chunks > self.max_chunks:
            raise HTTPException(status_code=400, detail=f"文件过大，最多支持{self.max_chunks}个分片")
        
        # 生成上传会话ID
        upload_id = str(uuid.uuid4())
        secure_filename = validator.generate_secure_filename(filename)
        
        # 创建S3多部分上传
        try:
            s3_client = get_s3_client()
            response = s3_client.create_multipart_upload(
                Bucket=S3_BUCKET_NAME,
                Key=f"forum/attachments/{secure_filename}",
                ContentType=content_type
            )
            s3_upload_id = response['UploadId']
        except Exception as e:
            logger.error(f"创建S3多部分上传失败: {e}")
            raise HTTPException(status_code=500, detail="创建上传会话失败")
        
        # 存储会话信息
        session_info = {
            "upload_id": upload_id,
            "s3_upload_id": s3_upload_id,
            "filename": filename,
            "secure_filename": secure_filename,
            "file_size": file_size,
            "content_type": content_type,
            "total_chunks": total_chunks,
            "uploaded_chunks": {},
            "user_id": user_id,
            "created_at": time.time()
        }
        
        self.upload_sessions[upload_id] = session_info
        
        return {
            "upload_id": upload_id,
            "chunk_size": self.chunk_size,
            "total_chunks": total_chunks,
            "secure_filename": secure_filename
        }
    
    async def upload_chunk(self, upload_id: str, chunk_number: int, chunk_data: bytes) -> Dict[str, Any]:
        """上传文件分片"""
        if upload_id not in self.upload_sessions:
            raise HTTPException(status_code=404, detail="上传会话不存在")
        
        session = self.upload_sessions[upload_id]
        
        # 验证分片号
        if chunk_number < 1 or chunk_number > session["total_chunks"]:
            raise HTTPException(status_code=400, detail="无效的分片号")
        
        # 验证分片大小
        expected_size = self.chunk_size
        if chunk_number == session["total_chunks"]:
            # 最后一片可能较小
            expected_size = session["file_size"] - (chunk_number - 1) * self.chunk_size
        
        if len(chunk_data) > expected_size:
            raise HTTPException(status_code=400, detail="分片大小超出限制")
        
        try:
            # 上传分片到S3
            s3_client = get_s3_client()
            response = s3_client.upload_part(
                Bucket=S3_BUCKET_NAME,
                Key=f"forum/attachments/{session['secure_filename']}",
                PartNumber=chunk_number,
                UploadId=session["s3_upload_id"],
                Body=chunk_data
            )
            
            # 记录分片信息
            session["uploaded_chunks"][chunk_number] = {
                "etag": response['ETag'],
                "size": len(chunk_data)
            }
            
            logger.info(f"上传分片 {chunk_number}/{session['total_chunks']} 成功")
            
            return {
                "chunk_number": chunk_number,
                "uploaded": True,
                "total_uploaded": len(session["uploaded_chunks"]),
                "total_chunks": session["total_chunks"]
            }
            
        except Exception as e:
            logger.error(f"上传分片失败: {e}")
            raise HTTPException(status_code=500, detail="上传分片失败")
    
    async def complete_upload(self, upload_id: str) -> Dict[str, Any]:
        """完成分片上传"""
        if upload_id not in self.upload_sessions:
            raise HTTPException(status_code=404, detail="上传会话不存在")
        
        session = self.upload_sessions[upload_id]
        
        # 检查是否所有分片都已上传
        if len(session["uploaded_chunks"]) != session["total_chunks"]:
            missing_chunks = []
            for i in range(1, session["total_chunks"] + 1):
                if i not in session["uploaded_chunks"]:
                    missing_chunks.append(i)
            raise HTTPException(status_code=400, detail=f"缺少分片: {missing_chunks}")
        
        try:
            # 构建分片列表
            parts = []
            for chunk_num in sorted(session["uploaded_chunks"].keys()):
                parts.append({
                    'ETag': session["uploaded_chunks"][chunk_num]["etag"],
                    'PartNumber': chunk_num
                })
            
            # 完成S3多部分上传
            s3_client = get_s3_client()
            s3_client.complete_multipart_upload(
                Bucket=S3_BUCKET_NAME,
                Key=f"forum/attachments/{session['secure_filename']}",
                UploadId=session["s3_upload_id"],
                MultipartUpload={'Parts': parts}
            )
            
            file_url = f"{S3_BASE_URL}/forum/attachments/{session['secure_filename']}"
            
            # 清理会话
            del self.upload_sessions[upload_id]
            
            return {
                "success": True,
                "filename": session["secure_filename"],
                "original_filename": session["filename"],
                "file_url": file_url,
                "file_size": session["file_size"],
                "content_type": session["content_type"]
            }
            
        except Exception as e:
            logger.error(f"完成上传失败: {e}")
            # 取消上传
            try:
                s3_client = get_s3_client()
                s3_client.abort_multipart_upload(
                    Bucket=S3_BUCKET_NAME,
                    Key=f"forum/attachments/{session['secure_filename']}",
                    UploadId=session["s3_upload_id"]
                )
            except (s3_client.exceptions.NoSuchUpload, s3_client.exceptions.ClientError) as e:
                logger.warning(f"Failed to abort multipart upload for {upload_id}: {e}")
            
            raise HTTPException(status_code=500, detail="完成上传失败")
    
    def cancel_upload(self, upload_id: str) -> bool:
        """取消分片上传"""
        if upload_id not in self.upload_sessions:
            return False
        
        session = self.upload_sessions[upload_id]
        
        try:
            # 取消S3多部分上传
            s3_client = get_s3_client()
            s3_client.abort_multipart_upload(
                Bucket=S3_BUCKET_NAME,
                Key=f"forum/attachments/{session['secure_filename']}",
                UploadId=session["s3_upload_id"]
            )
        except Exception as e:
            logger.error(f"取消S3上传失败: {e}")
        
        # 清理会话
        del self.upload_sessions[upload_id]
        return True
    
    def get_upload_status(self, upload_id: str) -> Optional[Dict[str, Any]]:
        """获取上传状态"""
        if upload_id not in self.upload_sessions:
            return None
        
        session = self.upload_sessions[upload_id]
        return {
            "upload_id": upload_id,
            "filename": session["filename"],
            "total_chunks": session["total_chunks"],
            "uploaded_chunks": len(session["uploaded_chunks"]),
            "progress": len(session["uploaded_chunks"]) / session["total_chunks"] * 100
        }

class ImageOptimizer:
    """图片优化器"""
    
    @staticmethod
    def optimize_image(image_content: bytes, max_width: int = 1920, max_height: int = 1080, 
                      quality: int = 85) -> bytes:
        """优化图片大小和质量"""
        try:
            # 打开图片
            image = Image.open(BytesIO(image_content))
            
            # 如果是RGBA模式的PNG，转换为RGB
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image, mask=image.split()[-1])
                image = background
            
            # 自动旋转（根据EXIF信息）
            image = ImageOps.exif_transpose(image)
            
            # 调整大小
            if image.width > max_width or image.height > max_height:
                image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # 保存优化后的图片
            output = BytesIO()
            
            # 根据原格式选择输出格式
            format_map = {
                'JPEG': 'JPEG',
                'PNG': 'PNG',
                'GIF': 'PNG',  # GIF转为PNG
                'BMP': 'JPEG',
                'WEBP': 'WEBP'
            }
            
            output_format = format_map.get(image.format, 'JPEG')
            
            if output_format == 'JPEG':
                image.save(output, format='JPEG', quality=quality, optimize=True)
            elif output_format == 'PNG':
                image.save(output, format='PNG', optimize=True)
            elif output_format == 'WEBP':
                image.save(output, format='WEBP', quality=quality, optimize=True)
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"图片优化失败: {e}")
            return image_content  # 返回原图

class DirectUploadManager:
    """OSS直传管理器"""
    
    @staticmethod
    def generate_presigned_post(filename: str, content_type: str, user_id: int, 
                               expires_in: int = 3600) -> Dict[str, Any]:
        """生成OSS直传签名"""
        try:
            validator = EnhancedFileSecurityValidator()
            
            # 验证文件信息
            is_valid, message = validator.validate_filename(filename)
            if not is_valid:
                raise HTTPException(status_code=400, detail=message)
                
            is_valid, message = validator.validate_mime_type(content_type, filename)
            if not is_valid:
                raise HTTPException(status_code=400, detail=message)
            
            # 生成安全文件名
            secure_filename = validator.generate_secure_filename(filename)
            key = f"forum/attachments/{secure_filename}"
            
            # 生成预签名POST
            s3_client = get_s3_client()
            
            # 设置上传条件
            conditions = [
                {"bucket": S3_BUCKET_NAME},
                {"key": key},
                {"Content-Type": content_type},
                ["content-length-range", 1, validator.config.file_size_limits.get(
                    validator.get_file_category(filename), 10 * 1024 * 1024)]
            ]
            
            fields = {
                "key": key,
                "Content-Type": content_type
            }
            
            response = s3_client.generate_presigned_post(
                Bucket=S3_BUCKET_NAME,
                Key=key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expires_in
            )
            
            return {
                "upload_url": response["url"],
                "fields": response["fields"],
                "secure_filename": secure_filename,
                "file_url": f"{S3_BASE_URL}/{key}"
            }
            
        except Exception as e:
            logger.error(f"生成直传签名失败: {e}")
            raise HTTPException(status_code=500, detail="生成上传签名失败")

async def upload_single_file(file: UploadFile, user_id: int) -> Dict[str, Any]:
    """单文件上传"""
    # 读取文件内容
    file_content = await file.read()
    
    # 安全验证
    is_valid, message, file_info = validate_file_security(
        file.filename, file_content, file.content_type
    )
    
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    try:
        # 如果是图片，进行优化
        if file_info["category"] == "images":
            file_content = ImageOptimizer.optimize_image(file_content)
        
        # 上传到OSS
        s3_client = get_s3_client()
        key = f"forum/attachments/{file_info['secure_filename']}"
        
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=file_content,
            ContentType=file_info["content_type"]
        )
        
        file_url = f"{S3_BASE_URL}/{key}"
        
        return {
            "success": True,
            "filename": file_info["secure_filename"],
            "original_filename": file_info["original_filename"],
            "file_url": file_url,
            "file_size": len(file_content),
            "content_type": file_info["content_type"],
            "file_hash": file_info["file_hash"],
            "category": file_info["category"]
        }
        
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail="文件上传失败")

# 全局实例
chunked_upload_manager = ChunkedUploadManager()
direct_upload_manager = DirectUploadManager()
