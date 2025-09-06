# project/utils/uploads/upload.py
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

from project.oss_utils import get_s3_client, S3_BUCKET_NAME, S3_BASE_URL
from ..security.file_security import EnhancedFileSecurityValidator, validate_file_security

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
            "total_chunks": total_chunks,
            "chunk_size": self.chunk_size
        }
    
    async def upload_chunk(self, upload_id: str, chunk_number: int, chunk_data: bytes) -> Dict[str, Any]:
        """上传文件分片"""
        if upload_id not in self.upload_sessions:
            raise HTTPException(status_code=404, detail="上传会话不存在")
        
        session = self.upload_sessions[upload_id]
        
        # 验证分片序号
        if chunk_number < 1 or chunk_number > session["total_chunks"]:
            raise HTTPException(status_code=400, detail="分片序号无效")
        
        # 验证分片大小
        expected_size = self.chunk_size
        if chunk_number == session["total_chunks"]:
            # 最后一片可能较小
            remaining = session["file_size"] % self.chunk_size
            if remaining > 0:
                expected_size = remaining
        
        if len(chunk_data) != expected_size:
            raise HTTPException(
                status_code=400, 
                detail=f"分片大小不正确，期望 {expected_size} 字节，实际 {len(chunk_data)} 字节"
            )
        
        # 上传到S3
        try:
            s3_client = get_s3_client()
            response = s3_client.upload_part(
                Bucket=S3_BUCKET_NAME,
                Key=f"forum/attachments/{session['secure_filename']}",
                PartNumber=chunk_number,
                UploadId=session["s3_upload_id"],
                Body=chunk_data
            )
            
            # 存储分片信息
            session["uploaded_chunks"][chunk_number] = {
                "etag": response["ETag"],
                "uploaded_at": time.time()
            }
            
            return {
                "chunk_number": chunk_number,
                "uploaded": True,
                "uploaded_chunks": len(session["uploaded_chunks"]),
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
            raise HTTPException(
                status_code=400, 
                detail=f"上传未完成，已上传 {len(session['uploaded_chunks'])} / {session['total_chunks']} 分片"
            )
        
        # 准备完成多部分上传的参数
        parts = []
        for chunk_number in sorted(session["uploaded_chunks"].keys()):
            parts.append({
                "ETag": session["uploaded_chunks"][chunk_number]["etag"],
                "PartNumber": chunk_number
            })
        
        try:
            # 完成S3多部分上传
            s3_client = get_s3_client()
            result = s3_client.complete_multipart_upload(
                Bucket=S3_BUCKET_NAME,
                Key=f"forum/attachments/{session['secure_filename']}",
                UploadId=session["s3_upload_id"],
                MultipartUpload={"Parts": parts}
            )
            
            # 清理会话信息
            del self.upload_sessions[upload_id]
            
            file_url = f"{S3_BASE_URL}/forum/attachments/{session['secure_filename']}"
            
            return {
                "success": True,
                "filename": session["filename"],
                "secure_filename": session["secure_filename"],
                "file_size": session["file_size"],
                "file_url": file_url,
                "upload_completed_at": time.time()
            }
            
        except Exception as e:
            logger.error(f"完成分片上传失败: {e}")
            raise HTTPException(status_code=500, detail="完成上传失败")
    
    def cancel_upload(self, upload_id: str) -> Dict[str, Any]:
        """取消分片上传"""
        if upload_id not in self.upload_sessions:
            raise HTTPException(status_code=404, detail="上传会话不存在")
        
        session = self.upload_sessions[upload_id]
        
        try:
            # 取消S3多部分上传
            s3_client = get_s3_client()
            s3_client.abort_multipart_upload(
                Bucket=S3_BUCKET_NAME,
                Key=f"forum/attachments/{session['secure_filename']}",
                UploadId=session["s3_upload_id"]
            )
            
            # 清理会话信息
            del self.upload_sessions[upload_id]
            
            return {"success": True, "message": "上传已取消"}
            
        except Exception as e:
            logger.error(f"取消上传失败: {e}")
            raise HTTPException(status_code=500, detail="取消上传失败")
    
    def get_upload_status(self, upload_id: str) -> Dict[str, Any]:
        """获取上传状态"""
        if upload_id not in self.upload_sessions:
            raise HTTPException(status_code=404, detail="上传会话不存在")
        
        session = self.upload_sessions[upload_id]
        
        return {
            "upload_id": upload_id,
            "filename": session["filename"],
            "file_size": session["file_size"],
            "total_chunks": session["total_chunks"],
            "uploaded_chunks": len(session["uploaded_chunks"]),
            "progress": len(session["uploaded_chunks"]) / session["total_chunks"] * 100,
            "created_at": session["created_at"]
        }


class ImageOptimizer:
    """图片优化器"""
    
    @staticmethod
    def optimize_image(image_data: bytes, max_width: int = 1920, max_height: int = 1080, quality: int = 85) -> bytes:
        """优化图片大小和质量"""
        try:
            # 打开图片
            image = Image.open(BytesIO(image_data))
            
            # 获取原始格式
            original_format = image.format
            if original_format not in ['JPEG', 'PNG', 'WEBP']:
                original_format = 'JPEG'
            
            # 转换为RGB模式（如果需要）
            if image.mode in ('RGBA', 'LA', 'P'):
                if original_format == 'JPEG':
                    # JPEG不支持透明度，创建白色背景
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'P':
                        image = image.convert('RGBA')
                    background.paste(image, mask=image.split()[-1] if len(image.split()) > 3 else None)
                    image = background
                else:
                    image = image.convert('RGBA')
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 自动旋转（根据EXIF信息）
            image = ImageOps.exif_transpose(image)
            
            # 调整大小
            if image.width > max_width or image.height > max_height:
                image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # 保存优化后的图片
            output = BytesIO()
            if original_format == 'PNG' and image.mode == 'RGBA':
                image.save(output, format='PNG', optimize=True)
            else:
                image.save(output, format='JPEG', quality=quality, optimize=True)
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"图片优化失败: {e}")
            # 如果优化失败，返回原始数据
            return image_data


class OSSDirectUploadManager:
    """OSS直传管理器"""
    
    def __init__(self):
        self.security_validator = EnhancedFileSecurityValidator()
    
    def generate_upload_token(self, filename: str, content_type: str, user_id: int) -> Dict[str, Any]:
        """生成OSS直传令牌"""
        try:
            # 验证文件安全性
            is_valid, message = self.security_validator.validate_filename(filename)
            if not is_valid:
                raise HTTPException(status_code=400, detail=message)
            
            is_valid, message = self.security_validator.validate_mime_type(content_type, filename)
            if not is_valid:
                raise HTTPException(status_code=400, detail=message)
            
            # 生成安全文件名
            secure_filename = self.security_validator.generate_secure_filename(filename)
            
            # 生成上传路径
            upload_path = f"forum/direct/{secure_filename}"
            
            # 这里可以添加OSS直传签名逻辑
            # 目前返回基本信息
            
            return {
                "upload_url": f"{S3_BASE_URL}/{upload_path}",
                "upload_path": upload_path,
                "secure_filename": secure_filename,
                "expires_in": 3600  # 1小时过期
            }
            
        except Exception as e:
            logger.error(f"生成上传令牌失败: {e}")
            raise HTTPException(status_code=500, detail="生成上传令牌失败")


# 实例化管理器
chunked_upload_manager = ChunkedUploadManager()
image_optimizer = ImageOptimizer()
oss_direct_manager = OSSDirectUploadManager()


async def upload_single_file(file: UploadFile, user_id: int) -> Dict[str, Any]:
    """单文件上传"""
    try:
        # 读取文件内容
        content = await file.read()
        
        # 安全验证
        security_result = await validate_file_security(content, file.filename, file.content_type)
        if not security_result["is_safe"]:
            raise HTTPException(status_code=400, detail=security_result["message"])
        
        # 生成安全文件名
        validator = EnhancedFileSecurityValidator()
        secure_filename = validator.generate_secure_filename(file.filename)
        
        # 图片优化
        if file.content_type and file.content_type.startswith('image/'):
            content = image_optimizer.optimize_image(content)
        
        # 上传到S3
        s3_client = get_s3_client()
        key = f"forum/attachments/{secure_filename}"
        
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=file.content_type
        )
        
        file_url = f"{S3_BASE_URL}/{key}"
        
        return {
            "success": True,
            "filename": file.filename,
            "secure_filename": secure_filename,
            "file_size": len(content),
            "file_url": file_url,
            "content_type": file.content_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail="文件上传失败")


async def upload_avatar(file: UploadFile, user_id: int) -> Dict[str, Any]:
    """上传用户头像"""
    try:
        # 验证是否为图片
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="头像必须是图片文件")
        
        # 读取文件内容
        content = await file.read()
        
        # 图片大小限制 (2MB)
        if len(content) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="头像文件不能超过2MB")
        
        # 安全验证
        security_result = await validate_file_security(content, file.filename, file.content_type)
        if not security_result["is_safe"]:
            raise HTTPException(status_code=400, detail=security_result["message"])
        
        # 生成头像文件名
        file_ext = os.path.splitext(file.filename)[1].lower()
        avatar_filename = f"avatar_{user_id}_{int(time.time())}{file_ext}"
        
        # 头像专用优化（较小尺寸）
        optimized_content = image_optimizer.optimize_image(
            content, 
            max_width=300, 
            max_height=300, 
            quality=80
        )
        
        # 上传到S3
        s3_client = get_s3_client()
        key = f"avatars/{avatar_filename}"
        
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=optimized_content,
            ContentType=file.content_type
        )
        
        avatar_url = f"{S3_BASE_URL}/{key}"
        
        return {
            "success": True,
            "avatar_url": avatar_url,
            "filename": avatar_filename,
            "file_size": len(optimized_content)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"头像上传失败: {e}")
        raise HTTPException(status_code=500, detail="头像上传失败")
