# project/routers/knowledge/knowledge.py
"""
现代化知识库API - 生产级多媒体内容管理系统
支持文档、图片、视频、网址、网站五大内容类型
提供完整的生命周期管理、智能处理和高级搜索功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_, desc, func
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
from enum import Enum
import uuid
import os
import mimetypes
import asyncio
import re
from urllib.parse import urlparse, unquote
from PIL import Image
import io
import logging
from pathlib import Path
import httpx  # 使用httpx替代aiohttp

# 配置结构化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入数据库和模型
from database import get_db
from models import KnowledgeBase, KnowledgeDocument, Student
from dependencies import get_current_user_id
from schemas.knowledge_schemas import (
    KnowledgeBaseSimpleBase, KnowledgeBaseSimpleCreate, KnowledgeBaseSimpleResponse,
    KnowledgeDocumentSimpleBase, KnowledgeDocumentSimpleCreate, KnowledgeDocumentSimpleResponse,
    KnowledgeDocumentUrlCreate, KnowledgeSearchResponse
)
import oss_utils
from ai_providers.document_processor import extract_text_from_document, chunk_text
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.config import get_user_model_for_provider

# 内容类型枚举
class ContentType(str, Enum):
    FILE = "file"
    IMAGE = "image" 
    VIDEO = "video"
    URL = "url"
    WEBSITE = "website"

# 处理状态枚举
class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

router = APIRouter(
    prefix="/knowledge",
    tags=["知识库管理"],
    responses={
        404: {"description": "资源不存在"},
        403: {"description": "权限不足"},
        422: {"description": "数据验证失败"},
        500: {"description": "服务器内部错误"}
    },
)

# ===== 配置常量 =====

class Config:
    """应用配置常量"""
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    THUMBNAIL_SIZE = (300, 300)  # 高质量缩略图
    THUMBNAIL_QUALITY = 90  # JPEG质量
    MAX_FILENAME_LENGTH = 255
    MAX_URL_LENGTH = 2048
    DEFAULT_CHUNK_SIZE = 1000
    REQUEST_TIMEOUT = 30  # 网络请求超时
    MAX_RETRIES = 3  # 最大重试次数
    
    # 支持的文件类型 - 按MIME类型分类
    SUPPORTED_TYPES = {
        ContentType.FILE: {
            'text/plain': ['.txt'],
            'text/markdown': ['.md'],
            'text/html': ['.html', '.htm'],
            'application/pdf': ['.pdf'],
            'application/vnd.ms-powerpoint': ['.ppt'],
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
            'application/vnd.ms-excel': ['.xls'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
            'application/msword': ['.doc'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
            'text/x-python': ['.py'],
            'application/json': ['.json'],
            'text/csv': ['.csv'],
            'application/rtf': ['.rtf']
        },
        ContentType.IMAGE: {
            'image/jpeg': ['.jpg', '.jpeg'],
            'image/png': ['.png'],
            'image/gif': ['.gif'],
            'image/bmp': ['.bmp'],
            'image/webp': ['.webp'],
            'image/svg+xml': ['.svg'],
            'image/tiff': ['.tiff', '.tif'],
            'image/x-icon': ['.ico']
        },
        ContentType.VIDEO: {
            'video/mp4': ['.mp4'],
            'video/avi': ['.avi'],
            'video/quicktime': ['.mov'],
            'video/x-msvideo': ['.avi'],
            'video/x-ms-wmv': ['.wmv'],
            'video/x-flv': ['.flv'],
            'video/webm': ['.webm'],
            'video/x-matroska': ['.mkv'],
            'video/3gpp': ['.3gp'],
            'video/x-m4v': ['.m4v']
        }
    }

# ===== 工具函数 =====

class FileValidator:
    """文件验证器"""
    
    @staticmethod
    def get_content_type_by_extension(filename: str) -> ContentType:
        """根据文件扩展名智能判断内容类型"""
        if not filename:
            return ContentType.FILE
            
        ext = Path(filename).suffix.lower()
        
        for content_type, mime_dict in Config.SUPPORTED_TYPES.items():
            for mime_type, extensions in mime_dict.items():
                if ext in extensions:
                    return content_type
        
        return ContentType.FILE  # 默认为文件类型
    
    @staticmethod
    def is_supported_type(filename: str, expected_type: ContentType) -> bool:
        """验证文件是否为支持的类型"""
        if not filename:
            return False
            
        detected_type = FileValidator.get_content_type_by_extension(filename)
        return detected_type == expected_type
    
    @staticmethod
    def get_supported_extensions(content_type: ContentType) -> List[str]:
        """获取指定内容类型支持的扩展名列表"""
        extensions = []
        if content_type in Config.SUPPORTED_TYPES:
            for mime_type, exts in Config.SUPPORTED_TYPES[content_type].items():
                extensions.extend(exts)
        return sorted(set(extensions))

class FileUtils:
    """文件工具类"""
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理和标准化文件名"""
        if not filename:
            return "unknown_file"
        
        # 解码URL编码的文件名
        filename = unquote(filename)
        
        # 移除或替换危险字符
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        
        # 移除连续的点和空格
        safe_name = re.sub(r'\.{2,}', '.', safe_name)
        safe_name = re.sub(r'\s+', ' ', safe_name).strip()
        
        # 确保文件名不为空且不超过长度限制
        if not safe_name or safe_name in ['.', '..']:
            safe_name = f"file_{uuid.uuid4().hex[:8]}"
        
        # 截断过长的文件名，保留扩展名
        if len(safe_name) > Config.MAX_FILENAME_LENGTH:
            name, ext = os.path.splitext(safe_name)
            max_name_len = Config.MAX_FILENAME_LENGTH - len(ext)
            safe_name = name[:max_name_len] + ext
        
        return safe_name
    
    @staticmethod
    def validate_file_size(size: int) -> bool:
        """验证文件大小"""
        return 0 < size <= Config.MAX_FILE_SIZE
    
    @staticmethod
    def format_file_size(size: int) -> str:
        """格式化文件大小显示"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

class URLValidator:
    """URL验证器"""
    
    @staticmethod
    def validate_url(url: str) -> Dict[str, Any]:
        """验证URL并返回解析结果"""
        if not url:
            raise ValueError("URL不能为空")
        
        if len(url) > Config.MAX_URL_LENGTH:
            raise ValueError(f"URL长度超过限制 ({Config.MAX_URL_LENGTH})")
        
        try:
            parsed = urlparse(url)
            
            if not parsed.scheme:
                # 尝试添加默认协议
                url = f"https://{url}"
                parsed = urlparse(url)
            
            if parsed.scheme not in ['http', 'https']:
                raise ValueError("仅支持HTTP和HTTPS协议")
            
            if not parsed.netloc:
                raise ValueError("无效的域名")
            
            return {
                "valid": True,
                "url": url,
                "domain": parsed.netloc,
                "scheme": parsed.scheme,
                "path": parsed.path
            }
            
        except Exception as e:
            raise ValueError(f"URL格式无效: {str(e)}")

class ThumbnailGenerator:
    """缩略图生成器"""
    
    @staticmethod
    async def generate_image_thumbnail(
        file_content: bytes, 
        user_id: int, 
        kb_id: int
    ) -> Optional[str]:
        """为图片生成高质量缩略图"""
        try:
            # 打开并处理图片
            with Image.open(io.BytesIO(file_content)) as image:
                # 转换为RGB模式（处理RGBA和P模式）
                if image.mode in ("RGBA", "P", "LA"):
                    # 创建白色背景
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    if image.mode == "P":
                        image = image.convert("RGBA")
                    background.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
                    image = background
                elif image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                
                # 使用高质量重采样算法生成缩略图
                image.thumbnail(Config.THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                
                # 保存为高质量JPEG
                thumbnail_io = io.BytesIO()
                image.save(thumbnail_io, format='JPEG', quality=Config.THUMBNAIL_QUALITY, optimize=True)
                thumbnail_content = thumbnail_io.getvalue()
                
                # 上传到OSS
                thumbnail_key = f"knowledge/{user_id}/{kb_id}/thumbnails/{uuid.uuid4().hex}.jpg"
                return oss_utils.upload_file_to_oss(thumbnail_content, thumbnail_key)
                
        except Exception as e:
            logger.error(f"生成图片缩略图失败: {str(e)}", extra={
                "user_id": user_id,
                "kb_id": kb_id,
                "file_size": len(file_content)
            })
            return None
    
    @staticmethod
    async def generate_video_thumbnail(
        file_path: str, 
        user_id: int, 
        kb_id: int
    ) -> Optional[str]:
        """为视频生成缩略图（需要ffmpeg支持）"""
        # TODO: 实现视频缩略图生成
        # 这里可以集成ffmpeg或其他视频处理库
        logger.info("视频缩略图生成功能待实现", extra={
            "user_id": user_id,
            "kb_id": kb_id,
            "file_path": file_path
        })
        return None

# ===== 知识库基础管理 =====

@router.post("/knowledge-bases", response_model=KnowledgeBaseSimpleResponse, summary="创建知识库")
async def create_knowledge_base(
    kb_data: KnowledgeBaseSimpleCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> KnowledgeBaseSimpleResponse:
    """创建新的知识库"""
    try:
        db_kb = KnowledgeBase(
            owner_id=current_user_id,
            name=kb_data.name.strip(),
            description=kb_data.description.strip() if kb_data.description else None,
            access_type=kb_data.access_type or "private"
        )
        
        db.add(db_kb)
        db.commit()
        db.refresh(db_kb)
        
        logger.info("知识库创建成功", extra={
            "user_id": current_user_id,
            "kb_id": db_kb.id,
            "kb_name": db_kb.name
        })
        
        return db_kb
        
    except IntegrityError as e:
        db.rollback()
        logger.warning("知识库名称冲突", extra={
            "user_id": current_user_id,
            "kb_name": kb_data.name,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库名称已存在"
        )
    except Exception as e:
        db.rollback()
        logger.error("创建知识库失败", extra={
            "user_id": current_user_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="创建知识库失败"
        )

@router.get("/knowledge-bases", response_model=List[KnowledgeBaseSimpleResponse], summary="获取知识库列表")
async def get_knowledge_bases(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量")
) -> List[KnowledgeBaseSimpleResponse]:
    """获取当前用户的知识库列表（分页）"""
    try:
        offset = (page - 1) * size
        
        # 查询知识库并添加文档统计
        knowledge_bases = db.query(
            KnowledgeBase,
            func.count(KnowledgeDocument.id).label('document_count')
        ).outerjoin(
            KnowledgeDocument, 
            KnowledgeBase.id == KnowledgeDocument.kb_id
        ).filter(
            KnowledgeBase.owner_id == current_user_id
        ).group_by(
            KnowledgeBase.id
        ).order_by(
            desc(KnowledgeBase.updated_at)
        ).offset(offset).limit(size).all()
        
        # 添加文档统计到结果中
        result = []
        for kb, doc_count in knowledge_bases:
            kb_dict = {
                **kb.__dict__,
                'document_count': doc_count
            }
            result.append(KnowledgeBaseSimpleResponse(**kb_dict))
        
        return result
        
    except Exception as e:
        logger.error("获取知识库列表失败", extra={
            "user_id": current_user_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取知识库列表失败"
        )

@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseSimpleResponse, summary="获取知识库详情")
async def get_knowledge_base(
    kb_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> KnowledgeBaseSimpleResponse:
    """获取指定知识库的详情"""
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.owner_id == current_user_id
    ).first()
    
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在或无权访问"
        )
    
    # 添加详细统计信息
    stats = db.query(
        KnowledgeDocument.content_type,
        func.count(KnowledgeDocument.id).label('count')
    ).filter(
        KnowledgeDocument.kb_id == kb_id
    ).group_by(KnowledgeDocument.content_type).all()
    
    document_stats = {stat.content_type: stat.count for stat in stats}
    total_documents = sum(document_stats.values())
    
    kb_dict = {
        **kb.__dict__,
        'document_count': total_documents,
        'document_stats': document_stats
    }
    
    return KnowledgeBaseSimpleResponse(**kb_dict)

@router.put("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseSimpleResponse, summary="更新知识库")
async def update_knowledge_base(
    kb_id: int,
    kb_data: KnowledgeBaseSimpleBase,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> KnowledgeBaseSimpleResponse:
    """更新知识库信息"""
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.owner_id == current_user_id
    ).first()
    
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在或无权访问"
        )
    
    try:
        # 更新字段
        update_data = kb_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key in ['name', 'description'] and value:
                setattr(kb, key, str(value).strip())
            else:
                setattr(kb, key, value)
        
        kb.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(kb)
        
        logger.info("知识库更新成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "updates": list(update_data.keys())
        })
        
        return kb
        
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库名称已存在"
        )
    except Exception as e:
        db.rollback()
        logger.error("更新知识库失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新知识库失败"
        )

@router.delete("/knowledge-bases/{kb_id}", summary="删除知识库")
async def delete_knowledge_base(
    kb_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> JSONResponse:
    """删除知识库及其所有文档"""
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.owner_id == current_user_id
    ).first()
    
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在或无权访问"
        )
    
    try:
        # 获取所有关联文档的文件路径
        documents = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.kb_id == kb_id
        ).all()
        
        file_paths = []
        for doc in documents:
            if doc.file_path and oss_utils.is_oss_url(doc.file_path):
                file_paths.append(doc.file_path)
            if doc.thumbnail_path and oss_utils.is_oss_url(doc.thumbnail_path):
                file_paths.append(doc.thumbnail_path)
        
        # 删除数据库记录
        db.delete(kb)
        db.commit()
        
        # 后台异步删除OSS文件
        if file_paths:
            background_tasks.add_task(cleanup_oss_files, file_paths)
        
        logger.info("知识库删除成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "kb_name": kb.name,
            "documents_count": len(documents),
            "files_to_cleanup": len(file_paths)
        })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "知识库删除成功",
                "deleted_documents": len(documents),
                "files_cleanup_scheduled": len(file_paths)
            }
        )
        
    except Exception as e:
        db.rollback()
        logger.error("删除知识库失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除知识库失败"
        )

async def cleanup_oss_files(file_paths: List[str]) -> None:
    """后台任务：清理OSS文件"""
    success_count = 0
    for file_path in file_paths:
        try:
            oss_utils.delete_file_from_oss(file_path)
            success_count += 1
        except Exception as e:
            logger.warning(f"删除OSS文件失败: {file_path}", extra={"error": str(e)})
    
    logger.info(f"OSS文件清理完成", extra={
        "total_files": len(file_paths),
        "success_count": success_count,
        "failed_count": len(file_paths) - success_count
    })

# ===== 辅助函数 =====

async def get_user_knowledge_base(kb_id: int, user_id: int, db: Session) -> KnowledgeBase:
    """获取用户的知识库，验证权限"""
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.owner_id == user_id
    ).first()
    
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在或无权访问"
        )
    
    return kb

async def process_document_comprehensive(
    document_id: int,
    file_content: bytes,
    content_type: ContentType,
    user_id: int,
    kb_id: int
) -> None:
    """综合处理文档：生成缩略图、提取文本、创建向量嵌入"""
    from database import get_db
    
    db = next(get_db())
    try:
        document = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.id == document_id
        ).first()
        
        if not document:
            logger.error("文档不存在", extra={"document_id": document_id})
            return
        
        document.status = ProcessingStatus.PROCESSING.value
        db.commit()
        
        # 生成缩略图
        if content_type in [ContentType.IMAGE, ContentType.VIDEO]:
            try:
                if content_type == ContentType.IMAGE:
                    thumbnail_url = await ThumbnailGenerator.generate_image_thumbnail(
                        file_content, user_id, kb_id
                    )
                    if thumbnail_url:
                        document.thumbnail_path = thumbnail_url
                        db.commit()
            except Exception as e:
                logger.warning(f"生成缩略图失败", extra={
                    "document_id": document_id,
                    "content_type": content_type.value,
                    "error": str(e)
                })
        
        # 提取文本内容（仅对文档类型）
        if content_type == ContentType.FILE:
            try:
                text_content = extract_text_from_document(document.file_path)
                
                if text_content:
                    # 文本分块
                    chunks = chunk_text(text_content, chunk_size=Config.DEFAULT_CHUNK_SIZE)
                    document.total_chunks = len(chunks)
                    
                    # 生成向量嵌入
                    try:
                        model_config = get_user_model_for_provider(user_id, "embedding", db)
                        if model_config and chunks:
                            await get_embeddings_from_api(chunks, model_config)
                            logger.info("文档向量化完成", extra={
                                "document_id": document_id,
                                "chunks_count": len(chunks)
                            })
                    except Exception as e:
                        logger.warning("生成向量嵌入失败", extra={
                            "document_id": document_id,
                            "error": str(e)
                        })
                else:
                    logger.warning("无法提取文档内容", extra={
                        "document_id": document_id,
                        "file_path": document.file_path
                    })
            except Exception as e:
                logger.error("文档文本提取失败", extra={
                    "document_id": document_id,
                    "error": str(e)
                })
        
        # 标记处理完成
        document.status = ProcessingStatus.COMPLETED.value
        document.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info("文档处理完成", extra={
            "document_id": document_id,
            "content_type": content_type.value,
            "user_id": user_id
        })
        
    except Exception as e:
        logger.error("文档处理失败", extra={
            "document_id": document_id,
            "error": str(e)
        })
        try:
            document = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.id == document_id
            ).first()
            if document:
                document.status = ProcessingStatus.FAILED.value
                document.processing_message = str(e)
                db.commit()
        except Exception as db_error:
            logger.error("更新文档状态失败", extra={
                "document_id": document_id,
                "error": str(db_error)
            })
    finally:
        db.close()

async def process_url_content(
    document_id: int,
    url_info: Dict[str, Any],
    content_type: str,
    user_id: int
) -> None:
    """异步处理URL内容：获取网页信息、提取文本"""
    from database import get_db
    
    db = next(get_db())
    try:
        document = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.id == document_id
        ).first()
        
        if not document:
            logger.error("文档不存在", extra={"document_id": document_id})
            return
        
        document.status = ProcessingStatus.PROCESSING.value
        db.commit()
        
        # 使用httpx获取网页内容
        async with httpx.AsyncClient(
            timeout=Config.REQUEST_TIMEOUT,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        ) as client:
            try:
                response = await client.get(url_info["url"])
                
                if response.status_code == 200:
                    content = response.text
                    
                    # 这里可以使用BeautifulSoup等库来提取网页信息
                    # 简化实现：提取基本信息
                    title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
                    if title_match and not document.website_title:
                        document.website_title = title_match.group(1).strip()
                    
                    # 提取description meta标签
                    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', content, re.IGNORECASE)
                    if desc_match and not document.website_description:
                        document.website_description = desc_match.group(1).strip()
                    
                    # 更新文档名称
                    if document.website_title and not document.file_name:
                        document.file_name = document.website_title
                    
                    logger.info("网页内容获取成功", extra={
                        "document_id": document_id,
                        "url": url_info["url"],
                        "title": document.website_title
                    })
                else:
                    logger.warning("网页访问失败", extra={
                        "document_id": document_id,
                        "url": url_info["url"],
                        "status_code": response.status_code
                    })
            except httpx.TimeoutException:
                logger.warning("网页访问超时", extra={
                    "document_id": document_id,
                    "url": url_info["url"]
                })
            except Exception as e:
                logger.warning("网页内容获取失败", extra={
                    "document_id": document_id,
                    "url": url_info["url"],
                    "error": str(e)
                })
        
        # 标记处理完成
        document.status = ProcessingStatus.COMPLETED.value
        document.updated_at = datetime.utcnow()
        db.commit()
        
    except Exception as e:
        logger.error("URL内容处理失败", extra={
            "document_id": document_id,
            "url": url_info.get("url"),
            "error": str(e)
        })
        try:
            document = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.id == document_id
            ).first()
            if document:
                document.status = ProcessingStatus.FAILED.value
                document.processing_message = str(e)
                db.commit()
        except Exception as db_error:
            logger.error("更新文档状态失败", extra={
                "document_id": document_id,
                "error": str(db_error)
            })
    finally:
        db.close()

# ===== 高级文档管理 =====

@router.post("/knowledge-bases/{kb_id}/documents/upload", response_model=KnowledgeDocumentSimpleResponse, summary="智能文档上传")
async def upload_document(
    kb_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    content_type: Optional[ContentType] = Form(None, description="指定内容类型，留空则自动检测"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> KnowledgeDocumentSimpleResponse:
    """智能文档上传 - 支持自动类型检测和多种内容格式"""
    
    # 验证知识库权限
    kb = await get_user_knowledge_base(kb_id, current_user_id, db)
    
    # 验证文件
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空"
        )
    
    # 读取文件内容
    try:
        file_content = await file.read()
        file_size = len(file_content)
        
        # 验证文件大小
        if not FileUtils.validate_file_size(file_size):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件过大，最大允许 {FileUtils.format_file_size(Config.MAX_FILE_SIZE)}"
            )
        
    except Exception as e:
        logger.error("读取上传文件失败", extra={
            "user_id": current_user_id,
            "filename": file.filename,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件读取失败"
        )
    
    # 智能检测或验证内容类型
    detected_type = FileValidator.get_content_type_by_extension(file.filename)
    
    if content_type is None:
        content_type = detected_type
    elif not FileValidator.is_supported_type(file.filename, content_type):
        supported = FileValidator.get_supported_extensions(content_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件类型不匹配。{content_type.value}类型支持的扩展名: {', '.join(supported)}"
        )
    
    # 清理文件名
    safe_filename = FileUtils.sanitize_filename(file.filename)
    
    # 获取MIME类型
    mime_type, _ = mimetypes.guess_type(safe_filename)
    
    try:
        # 生成唯一文件路径
        file_id = uuid.uuid4().hex
        file_key = f"knowledge/{current_user_id}/{kb_id}/{content_type.value}/{file_id[:8]}/{safe_filename}"
        
        # 上传到OSS
        file_url = oss_utils.upload_file_to_oss(file_content, file_key)
        
        # 创建文档记录
        db_document = KnowledgeDocument(
            kb_id=kb_id,
            owner_id=current_user_id,
            file_name=safe_filename,
            file_path=file_url,
            file_type=file.content_type,
            content_type=content_type.value,
            file_size=file_size,
            mime_type=mime_type,
            status=ProcessingStatus.PENDING.value
        )
        
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        
        # 异步处理文档
        background_tasks.add_task(
            process_document_comprehensive,
            db_document.id,
            file_content,
            content_type,
            current_user_id,
            kb_id
        )
        
        logger.info("文档上传成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_id": db_document.id,
            "filename": safe_filename,
            "content_type": content_type.value,
            "file_size": file_size
        })
        
        return db_document
        
    except Exception as e:
        db.rollback()
        logger.error("文档上传失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "filename": safe_filename,
            "content_type": content_type.value if content_type else None,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档上传失败"
        )

@router.post("/knowledge-bases/{kb_id}/documents/add-url", response_model=KnowledgeDocumentSimpleResponse, summary="添加网址内容")
async def add_url_document(
    kb_id: int,
    background_tasks: BackgroundTasks,
    url_data: KnowledgeDocumentUrlCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> KnowledgeDocumentSimpleResponse:
    """添加网址或网站内容到知识库"""
    
    # 验证知识库权限
    kb = await get_user_knowledge_base(kb_id, current_user_id, db)
    
    # 验证URL
    try:
        url_info = URLValidator.validate_url(url_data.url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # 验证内容类型
    if url_data.content_type not in [ContentType.URL, ContentType.WEBSITE]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL内容类型必须是 'url' 或 'website'"
        )
    
    try:
        # 创建文档记录
        db_document = KnowledgeDocument(
            kb_id=kb_id,
            owner_id=current_user_id,
            file_name=url_data.title or url_info["domain"],
            file_path="",  # URL类型不需要文件路径
            file_type="text/html",
            content_type=url_data.content_type,
            url=url_info["url"],
            website_title=url_data.title,
            website_description=url_data.description,
            status=ProcessingStatus.PENDING.value
        )
        
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        
        # 异步获取网页内容
        background_tasks.add_task(
            process_url_content,
            db_document.id,
            url_info,
            url_data.content_type,
            current_user_id
        )
        
        logger.info("URL内容添加成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_id": db_document.id,
            "url": url_info["url"],
            "content_type": url_data.content_type
        })
        
        return db_document
        
    except Exception as e:
        db.rollback()
        logger.error("添加URL内容失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "url": url_data.url,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="添加URL内容失败"
        )

# ===== 文档查询和管理 =====

@router.get("/knowledge-bases/{kb_id}/documents", response_model=List[KnowledgeDocumentSimpleResponse], summary="获取文档列表")
async def get_documents(
    kb_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    content_type: Optional[ContentType] = Query(None, description="按内容类型筛选"),
    status: Optional[ProcessingStatus] = Query(None, description="按处理状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向: asc, desc")
) -> List[KnowledgeDocumentSimpleResponse]:
    """获取知识库文档列表（支持筛选、分页、排序）"""
    
    # 验证知识库权限
    await get_user_knowledge_base(kb_id, current_user_id, db)
    
    try:
        # 构建查询
        query = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        )
        
        # 应用筛选条件
        if content_type:
            query = query.filter(KnowledgeDocument.content_type == content_type.value)
        
        if status:
            query = query.filter(KnowledgeDocument.status == status.value)
        
        # 应用排序
        if hasattr(KnowledgeDocument, sort_by):
            sort_column = getattr(KnowledgeDocument, sort_by)
            if sort_order.lower() == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(sort_column)
        else:
            query = query.order_by(desc(KnowledgeDocument.created_at))
        
        # 应用分页
        offset = (page - 1) * size
        documents = query.offset(offset).limit(size).all()
        
        return documents
        
    except Exception as e:
        logger.error("获取文档列表失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取文档列表失败"
        )

@router.get("/knowledge-bases/{kb_id}/documents/{document_id}", response_model=KnowledgeDocumentSimpleResponse, summary="获取文档详情")
async def get_document(
    kb_id: int,
    document_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> KnowledgeDocumentSimpleResponse:
    """获取文档详细信息"""
    
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在或无权访问"
        )
    
    return document

@router.put("/knowledge-bases/{kb_id}/documents/{document_id}", response_model=KnowledgeDocumentSimpleResponse, summary="更新文档信息")
async def update_document(
    kb_id: int,
    document_id: int,
    update_data: KnowledgeDocumentSimpleBase,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> KnowledgeDocumentSimpleResponse:
    """更新文档元信息"""
    
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在或无权访问"
        )
    
    try:
        # 更新允许的字段
        updatable_fields = ['file_name', 'website_title', 'website_description']
        update_dict = update_data.model_dump(exclude_unset=True)
        
        for field, value in update_dict.items():
            if field in updatable_fields and value is not None:
                setattr(document, field, str(value).strip())
        
        document.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(document)
        
        logger.info("文档更新成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_id": document_id,
            "updated_fields": list(update_dict.keys())
        })
        
        return document
        
    except Exception as e:
        db.rollback()
        logger.error("更新文档失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_id": document_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新文档失败"
        )

@router.delete("/knowledge-bases/{kb_id}/documents/{document_id}", summary="删除文档")
async def delete_document(
    kb_id: int,
    document_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> JSONResponse:
    """删除文档及其关联文件"""
    
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在或无权访问"
        )
    
    try:
        # 收集需要删除的文件路径
        files_to_delete = []
        if document.file_path and oss_utils.is_oss_url(document.file_path):
            files_to_delete.append(document.file_path)
        if document.thumbnail_path and oss_utils.is_oss_url(document.thumbnail_path):
            files_to_delete.append(document.thumbnail_path)
        
        # 删除数据库记录
        document_info = {
            "name": document.file_name,
            "content_type": document.content_type,
            "file_size": document.file_size
        }
        
        db.delete(document)
        db.commit()
        
        # 后台删除文件
        if files_to_delete:
            background_tasks.add_task(cleanup_oss_files, files_to_delete)
        
        logger.info("文档删除成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_id": document_id,
            "document_name": document_info["name"],
            "files_to_cleanup": len(files_to_delete)
        })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "文档删除成功",
                "document": document_info,
                "files_cleanup_scheduled": len(files_to_delete)
            }
        )
        
    except Exception as e:
        db.rollback()
        logger.error("删除文档失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_id": document_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除文档失败"
        )

@router.get("/knowledge-bases/{kb_id}/documents/stats", summary="获取文档统计信息")
async def get_document_stats(
    kb_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取知识库文档的详细统计信息"""
    
    # 验证知识库权限
    kb = await get_user_knowledge_base(kb_id, current_user_id, db)
    
    try:
        # 统计各类型文档数量
        content_type_stats = db.query(
            KnowledgeDocument.content_type,
            func.count(KnowledgeDocument.id).label('count'),
            func.sum(KnowledgeDocument.file_size).label('total_size')
        ).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        ).group_by(KnowledgeDocument.content_type).all()
        
        stats = {}
        total_count = 0
        total_size = 0
        
        for stat in content_type_stats:
            count = stat.count
            size = stat.total_size or 0
            stats[stat.content_type] = {
                "count": count,
                "total_size": size,
                "formatted_size": FileUtils.format_file_size(size)
            }
            total_count += count
            total_size += size
        
        # 状态统计
        status_stats = db.query(
            KnowledgeDocument.status,
            func.count(KnowledgeDocument.id).label('count')
        ).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        ).group_by(KnowledgeDocument.status).all()
        
        status_counts = {stat.status: stat.count for stat in status_stats}
        
        return {
            "kb_id": kb_id,
            "kb_name": kb.name,
            "summary": {
                "total_documents": total_count,
                "total_size": total_size,
                "formatted_total_size": FileUtils.format_file_size(total_size)
            },
            "content_type_stats": stats,
            "status_stats": status_counts
        }
        
    except Exception as e:
        logger.error("获取文档统计失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取文档统计失败"
        )

@router.get("/knowledge-bases/{kb_id}/documents/{document_id}/status", summary="获取文档处理状态")
async def get_document_processing_status(
    kb_id: int,
    document_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> JSONResponse:
    """获取文档的详细处理状态信息"""
    
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在或无权访问"
        )
    
    try:
        status_info = {
            "document_id": document_id,
            "status": document.status,
            "processing_message": document.processing_message,
            "content_type": document.content_type,
            "file_size": document.file_size,
            "total_chunks": document.total_chunks,
            "has_thumbnail": bool(document.thumbnail_path),
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat() if document.updated_at else None
        }
        
        # 添加处理进度信息
        if document.status == ProcessingStatus.PROCESSING.value:
            status_info["estimated_completion"] = "处理中，请稍后查询"
        elif document.status == ProcessingStatus.COMPLETED.value:
            status_info["completion_time"] = document.updated_at.isoformat() if document.updated_at else None
        elif document.status == ProcessingStatus.FAILED.value:
            status_info["error_details"] = document.processing_message
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=status_info
        )
        
    except Exception as e:
        logger.error("获取文档状态失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_id": document_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取文档状态失败"
        )

# ===== 高级搜索和统计 =====

@router.get("/knowledge-bases/{kb_id}/search", response_model=KnowledgeSearchResponse, summary="智能搜索")
async def search_knowledge(
    kb_id: int,
    q: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    content_type: Optional[ContentType] = Query(None, description="按内容类型筛选"),
    status: Optional[ProcessingStatus] = Query(None, description="按处理状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    search_mode: str = Query("basic", description="搜索模式: basic, semantic")
) -> KnowledgeSearchResponse:
    """智能搜索知识库内容 - 支持基础搜索和语义搜索"""
    
    # 验证知识库权限
    await get_user_knowledge_base(kb_id, current_user_id, db)
    
    try:
        search_term = f"%{q.strip()}%"
        results = []
        
        # 构建搜索查询
        query = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        )
        
        # 应用筛选条件
        if content_type:
            query = query.filter(KnowledgeDocument.content_type == content_type.value)
        
        if status:
            query = query.filter(KnowledgeDocument.status == status.value)
        
        # 基础文本搜索
        if search_mode == "basic":
            query = query.filter(
                or_(
                    KnowledgeDocument.file_name.ilike(search_term),
                    KnowledgeDocument.website_title.ilike(search_term),
                    KnowledgeDocument.website_description.ilike(search_term),
                    KnowledgeDocument.url.ilike(search_term)
                )
            )
        
        # 应用分页
        offset = (page - 1) * size
        documents = query.order_by(
            desc(KnowledgeDocument.updated_at)
        ).offset(offset).limit(size).all()
        
        # 构建搜索结果
        for document in documents:
            result_item = {
                "type": "document",
                "id": document.id,
                "title": document.website_title or document.file_name,
                "content": document.website_description or f"文件大小: {FileUtils.format_file_size(document.file_size or 0)}",
                "file_type": document.file_type,
                "status": document.status,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
                "content_type": document.content_type,
                "url": document.url,
                "thumbnail_path": document.thumbnail_path,
                "file_size": document.file_size
            }
            results.append(result_item)
        
        # 获取总数（用于分页）
        total_query = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        )
        
        if content_type:
            total_query = total_query.filter(KnowledgeDocument.content_type == content_type.value)
        
        if status:
            total_query = total_query.filter(KnowledgeDocument.status == status.value)
        
        if search_mode == "basic":
            total_query = total_query.filter(
                or_(
                    KnowledgeDocument.file_name.ilike(search_term),
                    KnowledgeDocument.website_title.ilike(search_term),
                    KnowledgeDocument.website_description.ilike(search_term),
                    KnowledgeDocument.url.ilike(search_term)
                )
            )
        
        total_count = total_query.count()
        
        return KnowledgeSearchResponse(
            query=q,
            total=total_count,
            results=results,
            page=page,
            size=size,
            search_mode=search_mode,
            content_type_filter=content_type.value if content_type else None,
            status_filter=status.value if status else None
        )
        
    except Exception as e:
        logger.error("搜索失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "query": q,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="搜索失败"
        )

@router.get("/knowledge-bases/{kb_id}/analytics", summary="知识库分析统计")
async def get_knowledge_base_analytics(
    kb_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="统计天数")
) -> JSONResponse:
    """获取知识库的详细分析统计"""
    
    # 验证知识库权限
    kb = await get_user_knowledge_base(kb_id, current_user_id, db)
    
    try:
        # 时间范围
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # 基础统计
        base_query = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        )
        
        # 按内容类型统计
        content_type_stats = db.query(
            KnowledgeDocument.content_type,
            func.count(KnowledgeDocument.id).label('count'),
            func.sum(KnowledgeDocument.file_size).label('total_size')
        ).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        ).group_by(KnowledgeDocument.content_type).all()
        
        content_stats = {}
        total_size = 0
        for stat in content_type_stats:
            content_stats[stat.content_type] = {
                "count": stat.count,
                "total_size": stat.total_size or 0,
                "formatted_size": FileUtils.format_file_size(stat.total_size or 0)
            }
            total_size += stat.total_size or 0
        
        # 按状态统计
        status_stats = db.query(
            KnowledgeDocument.status,
            func.count(KnowledgeDocument.id).label('count')
        ).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        ).group_by(KnowledgeDocument.status).all()
        
        status_counts = {stat.status: stat.count for stat in status_stats}
        
        # 时间序列统计（按天）
        daily_stats = db.query(
            func.date(KnowledgeDocument.created_at).label('date'),
            func.count(KnowledgeDocument.id).label('count')
        ).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id,
            KnowledgeDocument.created_at >= start_date
        ).group_by(
            func.date(KnowledgeDocument.created_at)
        ).order_by(func.date(KnowledgeDocument.created_at)).all()
        
        daily_counts = [
            {
                "date": stat.date.isoformat(),
                "count": stat.count
            }
            for stat in daily_stats
        ]
        
        # 最近活动
        recent_documents = base_query.order_by(
            desc(KnowledgeDocument.created_at)
        ).limit(10).all()
        
        recent_activity = [
            {
                "id": doc.id,
                "name": doc.website_title or doc.file_name,
                "content_type": doc.content_type,
                "status": doc.status,
                "created_at": doc.created_at.isoformat(),
                "file_size": doc.file_size
            }
            for doc in recent_documents
        ]
        
        # 总数统计
        total_documents = sum(stat["count"] for stat in content_stats.values())
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "kb_id": kb_id,
                "kb_name": kb.name,
                "analysis_period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days
                },
                "summary": {
                    "total_documents": total_documents,
                    "total_size": total_size,
                    "formatted_total_size": FileUtils.format_file_size(total_size),
                    "average_size": total_size // total_documents if total_documents > 0 else 0
                },
                "content_type_distribution": content_stats,
                "status_distribution": status_counts,
                "daily_upload_trend": daily_counts,
                "recent_activity": recent_activity,
                "top_file_types": await get_top_file_types(kb_id, current_user_id, db)
            }
        )
        
    except Exception as e:
        logger.error("获取分析统计失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取分析统计失败"
        )

async def get_top_file_types(kb_id: int, user_id: int, db: Session) -> List[Dict[str, Any]]:
    """获取最常用的文件类型统计"""
    try:
        file_type_stats = db.query(
            KnowledgeDocument.file_type,
            func.count(KnowledgeDocument.id).label('count')
        ).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == user_id,
            KnowledgeDocument.file_type.isnot(None)
        ).group_by(
            KnowledgeDocument.file_type
        ).order_by(
            desc(func.count(KnowledgeDocument.id))
        ).limit(10).all()
        
        return [
            {
                "file_type": stat.file_type,
                "count": stat.count
            }
            for stat in file_type_stats
        ]
    except Exception as e:
        logger.warning("获取文件类型统计失败", extra={
            "kb_id": kb_id,
            "user_id": user_id,
            "error": str(e)
        })
        return []

# ===== 批量操作 =====

@router.post("/knowledge-bases/{kb_id}/documents/batch-delete", summary="批量删除文档")
async def batch_delete_documents(
    kb_id: int,
    document_ids: List[int],
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> JSONResponse:
    """批量删除文档"""
    
    # 验证知识库权限
    await get_user_knowledge_base(kb_id, current_user_id, db)
    
    if not document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档ID列表不能为空"
        )
    
    if len(document_ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="一次最多删除100个文档"
        )
    
    try:
        # 查询要删除的文档
        documents = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.id.in_(document_ids),
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        ).all()
        
        if not documents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到可删除的文档"
            )
        
        # 收集文件路径
        files_to_delete = []
        deleted_documents = []
        
        for doc in documents:
            if doc.file_path and oss_utils.is_oss_url(doc.file_path):
                files_to_delete.append(doc.file_path)
            if doc.thumbnail_path and oss_utils.is_oss_url(doc.thumbnail_path):
                files_to_delete.append(doc.thumbnail_path)
            
            deleted_documents.append({
                "id": doc.id,
                "name": doc.file_name,
                "content_type": doc.content_type
            })
            
            db.delete(doc)
        
        db.commit()
        
        # 后台删除文件
        if files_to_delete:
            background_tasks.add_task(cleanup_oss_files, files_to_delete)
        
        logger.info("批量删除文档成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "deleted_count": len(deleted_documents),
            "files_to_cleanup": len(files_to_delete)
        })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": f"成功删除 {len(deleted_documents)} 个文档",
                "deleted_documents": deleted_documents,
                "files_cleanup_scheduled": len(files_to_delete)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("批量删除文档失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "document_ids": document_ids,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="批量删除文档失败"
        )

@router.get("/knowledge-bases/{kb_id}/export", summary="导出知识库")
async def export_knowledge_base(
    kb_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    format: str = Query("json", description="导出格式: json, csv"),
    include_content: bool = Query(False, description="是否包含文件内容")
) -> JSONResponse:
    """导出知识库元数据"""
    
    # 验证知识库权限
    kb = await get_user_knowledge_base(kb_id, current_user_id, db)
    
    try:
        documents = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.owner_id == current_user_id
        ).all()
        
        export_data = {
            "knowledge_base": {
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "created_at": kb.created_at.isoformat(),
                "updated_at": kb.updated_at.isoformat() if kb.updated_at else None
            },
            "documents": [],
            "export_info": {
                "exported_at": datetime.utcnow().isoformat(),
                "total_documents": len(documents),
                "include_content": include_content
            }
        }
        
        for doc in documents:
            doc_data = {
                "id": doc.id,
                "file_name": doc.file_name,
                "content_type": doc.content_type,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "status": doc.status,
                "url": doc.url,
                "website_title": doc.website_title,
                "website_description": doc.website_description,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None
            }
            
            # 根据需要包含文件内容
            if include_content and not doc.url:
                doc_data["file_path"] = doc.file_path
                doc_data["thumbnail_path"] = doc.thumbnail_path
            
            export_data["documents"].append(doc_data)
        
        logger.info("知识库导出成功", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "format": format,
            "documents_count": len(documents)
        })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=export_data
        )
        
    except Exception as e:
        logger.error("导出知识库失败", extra={
            "user_id": current_user_id,
            "kb_id": kb_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="导出知识库失败"
        )
