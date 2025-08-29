# project/routers/forum/forum.py
"""
论坛模块 - 生产级整合优化版本
整合了基础版本和优化版本的所有功能，提供企业级的论坛解决方案

主要功能：
- 完整的论坛话题管理（CRUD）
- 高级评论系统（支持嵌套回复）
- 多文件上传（分片上传、直传、压缩优化）
- 智能搜索和推荐
- 实时通知系统
- 缓存优化和性能监控
- 安全防护和内容审核
- 用户互动（点赞、关注、@提及）
- 管理员功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func, text
from typing import List, Optional, Dict, Any, Union, Tuple
import os, uuid, asyncio, re, json, mimetypes
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

# 核心依赖
from project.database import get_db
from project.models import Student, ForumTopic, ForumLike, ForumComment, UserFollow
from project.dependencies import get_current_user_id
import project.schemas as schemas
import project.oss_utils as oss_utils

# 优化模块
from project.utils.cache_manager_simple import cache_manager, ForumCache
from project.utils.file_security_simple import validate_file_security
from project.utils.file_upload import (
    upload_single_file, chunked_upload_manager, direct_upload_manager,
    ChunkedUploadManager, ImageOptimizer
)
from project.utils.input_security_simple import (
    validate_forum_input, input_validator, content_moderator, rate_limiter
)
from project.utils.database_optimization import (
    query_optimizer, db_optimizer, cache_scheduler
)
from project.utils import (
    _get_text_part, generate_embedding_safe, populate_user_name, populate_like_status,
    get_forum_topics_with_details, debug_operation, commit_or_rollback
)

# AI功能
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key

# 配置日志
logger = logging.getLogger(__name__)

# ==================== 配置和常量 ====================

# 支持的文件类型（扩展后的类型支持）
SUPPORTED_FILE_EXTENSIONS = {
    # 文档类型
    '.txt', '.md', '.html', '.pdf', '.docx', '.pptx', '.xlsx', '.rtf', '.odt',
    # 代码类型  
    '.py', '.js', '.ts', '.java', '.cpp', '.c', '.css', '.json', '.xml', '.yml', '.yaml',
    '.go', '.rust', '.swift', '.kt', '.php', '.rb', '.sh', '.sql',
    # 音频类型
    '.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma',
    # 视频类型
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', '.m4v', '.3gp',
    # 图片类型
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.heic',
    # 压缩文件
    '.zip', '.rar', '.7z', '.tar', '.gz'
}

SUPPORTED_MIME_TYPES = {
    # 文档类型
    'text/plain', 'text/markdown', 'text/html', 'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/msword', 'application/vnd.ms-powerpoint', 'application/vnd.ms-excel',
    'application/rtf', 'application/vnd.oasis.opendocument.text',
    # 代码类型
    'text/x-python', 'application/javascript', 'text/javascript', 'application/json',
    'text/css', 'application/xml', 'text/xml', 'application/x-yaml', 'text/yaml',
    'text/x-go', 'text/x-rust', 'text/x-swift', 'text/x-kotlin', 'application/x-php',
    'text/x-ruby', 'application/x-sh', 'application/sql',
    # 音频类型
    'audio/mpeg', 'audio/wav', 'audio/x-m4a', 'audio/aac', 'audio/ogg', 'audio/flac',
    'audio/x-ms-wma',
    # 视频类型  
    'video/mp4', 'video/x-msvideo', 'video/quicktime', 'video/x-ms-wmv',
    'video/x-flv', 'video/webm', 'video/x-matroska', 'video/3gpp',
    # 图片类型
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp', 
    'image/svg+xml', 'image/x-icon', 'image/tiff', 'image/heic',
    # 压缩文件
    'application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed',
    'application/x-tar', 'application/gzip'
}

# 缓存键前缀
CACHE_KEYS = {
    'hot_topics': 'forum:hot_topics',
    'topic_detail': 'forum:topic_detail',
    'topic_stats': 'forum:topic_stats',
    'user_info': 'forum:user_info',
    'comments': 'forum:comments',
    'search_results': 'forum:search'
}

# ==================== 数据模型 ====================

class TopicCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=50000)
    tags: Optional[str] = Field(None, max_length=500)
    shared_item_type: Optional[str] = None
    shared_item_id: Optional[int] = None

class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    parent_id: Optional[int] = None

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=100)
    filters: Optional[Dict[str, Any]] = None
    sort_by: Optional[str] = Field(default="relevance", pattern="^(relevance|date|popularity)$")

# ==================== 工具函数 ====================

def validate_file_type_enhanced(filename: str, content_type: str) -> Tuple[bool, str, str]:
    """增强的文件类型验证"""
    file_ext = os.path.splitext(filename)[1].lower()
    
    # 安全检查：防止危险文件类型
    dangerous_extensions = {'.exe', '.bat', '.cmd', '.scr', '.pif', '.com'}
    if file_ext in dangerous_extensions:
        return False, f"危险文件类型: {file_ext}", "dangerous"
    
    # 检查文件扩展名
    if file_ext not in SUPPORTED_FILE_EXTENSIONS:
        return False, f"不支持的文件类型: {file_ext}", "unsupported"
    
    # 检查MIME类型
    if content_type not in SUPPORTED_MIME_TYPES:
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type and guessed_type in SUPPORTED_MIME_TYPES:
            return True, "ok", get_media_category(content_type, file_ext)
        return False, f"不支持的MIME类型: {content_type}", "unsupported"
    
    return True, "ok", get_media_category(content_type, file_ext)

def get_media_category(content_type: str, file_ext: str) -> str:
    """获取媒体类别"""
    if content_type.startswith('image/'):
        return "image"
    elif content_type.startswith('video/'):
        return "video"
    elif content_type.startswith('audio/'):
        return "audio"
    elif file_ext in {'.zip', '.rar', '.7z', '.tar', '.gz'}:
        return "archive"
    elif file_ext in {'.pdf', '.docx', '.pptx', '.xlsx', '.txt', '.md', '.html'}:
        return "document"
    elif file_ext in {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.css', '.json'}:
        return "code"
    else:
        return "file"

def extract_mentions_enhanced(content: str) -> List[str]:
    """增强的@用户提取"""
    if not content:
        return []
    
    # 支持中文、英文、数字、下划线的用户名
    mention_pattern = r'@([a-zA-Z0-9_\u4e00-\u9fa5]{1,20})'
    mentions = re.findall(mention_pattern, content)
    
    # 去重并限制数量（防止滥用）
    unique_mentions = list(set(mentions))
    return unique_mentions[:10]  # 最多@10个用户

async def process_content_with_ai(content: str, user_id: int, db: Session) -> Dict[str, Any]:
    """AI增强的内容处理"""
    result = {
        'processed_content': content,
        'mentions': [],
        'tags': [],
        'embedding': GLOBAL_PLACEHOLDER_ZERO_VECTOR,
        'risk_score': 0.0,
        'auto_tags': []
    }
    
    try:
        # 提取@用户
        mentions = extract_mentions_enhanced(content)
        if mentions:
            users = db.query(Student).filter(Student.username.in_(mentions)).all()
            result['mentions'] = [user.id for user in users]
            
            # 高亮@用户
            for mention in mentions:
                content = content.replace(f'@{mention}', f'<mention>@{mention}</mention>')
            result['processed_content'] = content
        
        # 获取用户AI配置
        user = db.query(Student).filter(Student.id == user_id).first()
        if user and user.llm_api_key_encrypted:
            try:
                api_key = decrypt_key(user.llm_api_key_encrypted)
                
                # 生成嵌入向量
                embedding = await get_embeddings_from_api(
                    [content],
                    api_key=api_key,
                    llm_type=user.llm_api_type,
                    llm_base_url=user.llm_api_base_url,
                    llm_model_id=user.llm_model_id
                )
                if embedding:
                    result['embedding'] = embedding[0]
                    
            except Exception as e:
                logger.warning(f"AI处理失败: {e}")
        
        # 内容风险评估
        risk_score = content_moderator.moderate_content(content)[2] if hasattr(content_moderator, 'moderate_content') else 0.0
        result['risk_score'] = risk_score
        
    except Exception as e:
        logger.error(f"内容AI处理失败: {e}")
    
    return result

# ==================== 路由器配置 ====================

router = APIRouter(
    prefix="/forum",
    tags=["Forum"],
    responses={
        404: {"description": "资源未找到"},
        429: {"description": "请求过于频繁"},
        500: {"description": "服务器内部错误"}
    }
)

# ==================== 文件上传接口 ====================

@router.post("/upload/single", summary="单文件上传")
async def upload_single_file_v2(
    file: UploadFile = File(...),
    compress_images: bool = Form(default=True),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    增强的单文件上传接口
    - 自动安全验证和病毒扫描
    - 智能图片压缩优化
    - 支持30+种文件类型
    - 实时上传进度追踪
    """
    try:
        # 速率限制检查（每用户每分钟最多10个文件）
        is_allowed, rate_info = rate_limiter.check_rate_limit(
            current_user_id, "upload_file", cache_manager, limit=10, window=60
        )
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"上传过于频繁，请稍后再试。{rate_info}"
            )
        
        # 文件验证
        is_valid, error_msg, media_category = validate_file_type_enhanced(
            file.filename, file.content_type
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # 读取文件内容
        file_content = await file.read()
        file_size = len(file_content)
        
        # 文件大小限制（根据类型设置不同限制）
        size_limits = {
            'image': 10 * 1024 * 1024,      # 10MB
            'video': 100 * 1024 * 1024,     # 100MB
            'audio': 50 * 1024 * 1024,      # 50MB
            'document': 20 * 1024 * 1024,   # 20MB
            'code': 5 * 1024 * 1024,        # 5MB
            'archive': 50 * 1024 * 1024,    # 50MB
            'file': 20 * 1024 * 1024        # 20MB
        }
        
        max_size = size_limits.get(media_category, 20 * 1024 * 1024)
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件过大，{media_category}类型文件最大允许{max_size//1024//1024}MB"
            )
        
        # 安全扫描
        security_result = await validate_file_security(file_content, file.filename)
        if not security_result.get('safe', True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件安全检查失败: {security_result.get('reason', '未知错误')}"
            )
        
        # 执行上传
        upload_result = await upload_single_file(file, current_user_id)
        
        # 如果是图片且需要压缩
        if media_category == 'image' and compress_images:
            try:
                optimizer = ImageOptimizer()
                optimized_result = await optimizer.optimize_image(
                    file_content, file.filename, quality=85
                )
                if optimized_result.get('optimized'):
                    upload_result.update(optimized_result)
            except Exception as e:
                logger.warning(f"图片优化失败: {e}")
        
        # 记录上传日志
        logger.info(f"用户 {current_user_id} 上传文件: {file.filename} ({file_size} bytes)")
        
        return {
            "success": True,
            "message": "文件上传成功",
            "data": {
                **upload_result,
                "media_category": media_category,
                "file_size": file_size,
                "security_score": security_result.get('score', 1.0)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件上传失败: {str(e)}"
        )

@router.post("/upload/chunked/start", summary="开始分片上传")
async def start_chunked_upload_v2(
    filename: str = Form(...),
    file_size: int = Form(...),
    content_type: str = Form(...),
    chunk_size: int = Form(default=1024*1024),  # 1MB chunks
    current_user_id: int = Depends(get_current_user_id)
):
    """开始分片上传会话（支持断点续传）"""
    try:
        # 验证文件类型
        is_valid, error_msg, media_category = validate_file_type_enhanced(filename, content_type)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # 创建上传会话
        result = chunked_upload_manager.start_upload_session(
            filename, file_size, content_type, current_user_id,
            chunk_size=chunk_size
        )
        
        return {
            "success": True,
            "message": "分片上传会话创建成功",
            "data": {
                **result,
                "media_category": media_category,
                "estimated_chunks": (file_size + chunk_size - 1) // chunk_size
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建上传会话失败: {str(e)}"
        )

@router.post("/upload/chunked/{upload_id}/chunk/{chunk_number}", summary="上传文件分片")
async def upload_file_chunk_v2(
    upload_id: str,
    chunk_number: int,
    file: UploadFile = File(...),
    chunk_hash: Optional[str] = Form(None),  # 分片校验和
    current_user_id: int = Depends(get_current_user_id)
):
    """上传文件分片（支持校验和验证）"""
    try:
        chunk_data = await file.read()
        
        # 分片完整性验证
        if chunk_hash:
            import hashlib
            actual_hash = hashlib.md5(chunk_data).hexdigest()
            if actual_hash != chunk_hash:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="分片数据校验失败"
                )
        
        result = await chunked_upload_manager.upload_chunk(
            upload_id, chunk_number, chunk_data
        )
        
        return {
            "success": True,
            "message": f"分片 {chunk_number} 上传成功",
            "data": {
                **result,
                "chunk_size": len(chunk_data)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分片上传失败: {str(e)}"
        )

@router.post("/upload/chunked/{upload_id}/complete", summary="完成分片上传")
async def complete_chunked_upload_v2(
    upload_id: str,
    file_hash: Optional[str] = Form(None),  # 完整文件校验和
    current_user_id: int = Depends(get_current_user_id)
):
    """完成分片上传（支持文件完整性验证）"""
    try:
        result = await chunked_upload_manager.complete_upload(
            upload_id, 
            verify_hash=file_hash
        )
        
        return {
            "success": True,
            "message": "文件上传完成",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"完成上传失败: {str(e)}"
        )

@router.get("/upload/progress/{upload_id}", summary="获取上传进度")
async def get_upload_progress(
    upload_id: str,
    current_user_id: int = Depends(get_current_user_id)
):
    """获取分片上传进度"""
    try:
        progress = chunked_upload_manager.get_upload_progress(upload_id, current_user_id)
        
        return {
            "success": True,
            "data": progress
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取上传进度失败: {str(e)}"
        )

# ==================== 论坛主题接口 ====================

@router.post("/topics", summary="发布话题")
async def create_topic_v2(
    title: str = Form(...),
    content: str = Form(...),
    tags: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    shared_item_type: Optional[str] = Form(None),
    shared_item_id: Optional[int] = Form(None),
    auto_generate_tags: bool = Form(default=True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    发布话题（生产级版本）
    - AI增强的内容处理和标签生成
    - 多文件上传优化
    - 智能内容审核
    - 实时通知系统
    - 自动SEO优化
    """
    try:
        # 速率限制（每用户每小时最多发布10个话题）
        is_allowed, rate_info = rate_limiter.check_rate_limit(
            current_user_id, "create_topic", cache_manager, limit=10, window=3600
        )
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"发布过于频繁，请稍后再试。{rate_info}"
            )
        
        # 输入验证和安全检查
        is_valid, error_msg, validation_result = validate_forum_input(
            title, content, current_user_id, cache_manager
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )
        
        # AI增强的内容处理
        ai_result = await process_content_with_ai(content, current_user_id, db)
        
        # 验证共享内容
        if shared_item_type and shared_item_id:
            from models import Note, DailyRecord, Course, Project, KnowledgeArticle, CollectedContent
            
            model_map = {
                "note": Note,
                "daily_record": DailyRecord,
                "course": Course,
                "project": Project,
                "knowledge_article": KnowledgeArticle,
                "collected_content": CollectedContent
            }
            
            if shared_item_type in model_map:
                shared_item = db.query(model_map[shared_item_type]).filter(
                    model_map[shared_item_type].id == shared_item_id
                ).first()
                if not shared_item:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"分享的{shared_item_type}不存在"
                    )
        
        # 处理文件上传
        uploaded_files = []
        upload_errors = []
        
        if files and files[0].filename:
            for file in files:
                if file.filename:
                    try:
                        file_result = await upload_single_file(file, current_user_id)
                        uploaded_files.append(file_result)
                    except Exception as e:
                        upload_errors.append(f"{file.filename}: {str(e)}")
        
        # 处理标签
        final_tags = tags or ""
        if auto_generate_tags and ai_result.get('auto_tags'):
            auto_tag_str = ", ".join(ai_result['auto_tags'])
            final_tags = f"{final_tags}, {auto_tag_str}" if final_tags else auto_tag_str
        
        # 创建话题
        new_topic = ForumTopic(
            title=validation_result.get("cleaned_title", title),
            content=ai_result['processed_content'],
            user_id=current_user_id,
            owner_id=current_user_id,  # 兼容性
            tags=final_tags[:500] if final_tags else None,
            attachments=json.dumps(uploaded_files) if uploaded_files else None,
            attachments_json=json.dumps(uploaded_files) if uploaded_files else None,  # 兼容性
            shared_item_type=shared_item_type,
            shared_item_id=shared_item_id,
            mentioned_users=json.dumps(ai_result['mentions']) if ai_result['mentions'] else None,
            embedding=ai_result['embedding'],
            combined_text=f"{title}. {content}. {final_tags}".strip(),
            created_at=datetime.now(),
            status='active' if ai_result['risk_score'] < 0.5 else 'pending_review',
            views_count=0,
            likes_count=0,
            comment_count=0
        )
        
        # 设置兼容字段
        if uploaded_files:
            first_file = uploaded_files[0]
            new_topic.media_url = first_file.get("url")
            new_topic.media_type = first_file.get("type")
            new_topic.original_filename = first_file.get("filename")
            new_topic.media_size_bytes = first_file.get("size")
        
        db.add(new_topic)
        db.flush()
        
        # 积分奖励
        try:
            user = db.query(Student).filter(Student.id == current_user_id).first()
            if user:
                from main import _award_points, _check_and_award_achievements
                topic_post_points = 15
                await _award_points(
                    db=db,
                    user=user,
                    amount=topic_post_points,
                    reason=f"发布论坛话题：'{title}'",
                    transaction_type="EARN",
                    related_entity_type="forum_topic",
                    related_entity_id=new_topic.id
                )
                await _check_and_award_achievements(db, current_user_id)
        except Exception as e:
            logger.warning(f"积分奖励失败: {e}")
        
        db.commit()
        db.refresh(new_topic)
        
        # 后台任务
        if ai_result['mentions']:
            background_tasks.add_task(
                send_mention_notifications_v2,
                ai_result['mentions'],
                new_topic.id,
                current_user_id,
                "topic"
            )
        
        background_tasks.add_task(clear_topic_related_cache_v2, new_topic.id)
        background_tasks.add_task(update_trending_topics)
        
        return {
            "success": True,
            "message": "话题发布成功",
            "data": {
                "topic_id": new_topic.id,
                "status": new_topic.status,
                "uploaded_files": uploaded_files,
                "upload_errors": upload_errors,
                "mentioned_users": ai_result['mentions'],
                "auto_tags": ai_result.get('auto_tags', []),
                "risk_score": ai_result['risk_score']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布话题失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发布话题失败: {str(e)}"
        )

@router.get("/topics", summary="获取话题列表")
async def get_topics_v2(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("latest", regex="^(latest|hot|trending|oldest)$"),
    tag: Optional[str] = Query(None),
    shared_type: Optional[str] = Query(None),
    author_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    time_range: Optional[str] = Query(None, regex="^(day|week|month|year|all)$"),
    include_pending: bool = Query(False),
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取话题列表
    - 智能排序和过滤
    - 高效分页
    - 缓存优化
    - 相关性搜索
    """
    try:
        # 构建缓存键
        cache_key = f"{CACHE_KEYS['hot_topics']}:{sort_by}:{page}:{page_size}:{tag}:{shared_type}:{author_id}:{search}:{time_range}"
        
        # 尝试从缓存获取
        cached_result = cache_manager.get(cache_key)
        if cached_result and not search:  # 搜索结果不缓存
            return cached_result
        
        # 构建查询
        query = db.query(ForumTopic).options(
            joinedload(ForumTopic.owner) if hasattr(ForumTopic, 'owner') else text('')
        )
        
        # 状态过滤
        if not include_pending:
            query = query.filter(ForumTopic.status == 'active')
        
        # 时间范围过滤
        if time_range and time_range != 'all':
            time_delta = {
                'day': timedelta(days=1),
                'week': timedelta(weeks=1),
                'month': timedelta(days=30),
                'year': timedelta(days=365)
            }.get(time_range)
            
            if time_delta:
                query = query.filter(
                    ForumTopic.created_at >= datetime.now() - time_delta
                )
        
        # 其他过滤条件
        if tag:
            query = query.filter(ForumTopic.tags.ilike(f"%{tag}%"))
        if shared_type:
            query = query.filter(ForumTopic.shared_item_type == shared_type)
        if author_id:
            query = query.filter(ForumTopic.user_id == author_id)
        
        # 搜索功能
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    ForumTopic.title.ilike(search_term),
                    ForumTopic.content.ilike(search_term),
                    ForumTopic.tags.ilike(search_term)
                )
            )
        
        # 排序
        if sort_by == "latest":
            query = query.order_by(desc(ForumTopic.created_at))
        elif sort_by == "hot":
            # 热度算法：点赞数 * 2 + 评论数 * 3 + 浏览数 * 0.1
            query = query.order_by(
                desc(
                    (func.coalesce(ForumTopic.likes_count, 0) * 2 +
                     func.coalesce(ForumTopic.comment_count, 0) * 3 +
                     func.coalesce(ForumTopic.views_count, 0) * 0.1)
                )
            )
        elif sort_by == "trending":
            # 趋势算法：考虑时间衰减的热度
            hours_since_created = func.extract('epoch', func.now() - ForumTopic.created_at) / 3600
            trending_score = (
                (func.coalesce(ForumTopic.likes_count, 0) * 2 +
                 func.coalesce(ForumTopic.comment_count, 0) * 3) /
                func.power(hours_since_created + 1, 1.5)
            )
            query = query.order_by(desc(trending_score))
        elif sort_by == "oldest":
            query = query.order_by(ForumTopic.created_at)
        
        # 分页
        total = query.count()
        offset = (page - 1) * page_size
        topics = query.offset(offset).limit(page_size).all()
        
        # 填充额外信息
        topic_data = []
        user_ids = list(set([topic.user_id for topic in topics if topic.user_id]))
        user_info_batch = query_optimizer.get_user_info_batch(db, user_ids) if user_ids else {}
        
        for topic in topics:
            # 解析附件
            attachments = []
            if topic.attachments:
                try:
                    attachments = json.loads(topic.attachments)
                except:
                    pass
            
            # 检查当前用户是否点赞
            user_liked = False
            if current_user_id:
                like_exists = db.query(ForumLike).filter(
                    and_(
                        ForumLike.topic_id == topic.id,
                        ForumLike.user_id == current_user_id
                    )
                ).first()
                user_liked = like_exists is not None
            
            topic_info = {
                "id": topic.id,
                "title": topic.title,
                "content": topic.content[:500] + "..." if len(topic.content) > 500 else topic.content,
                "author": user_info_batch.get(topic.user_id, {"id": topic.user_id, "name": "未知用户"}),
                "created_at": topic.created_at.isoformat(),
                "updated_at": getattr(topic, 'updated_at', topic.created_at).isoformat(),
                "tags": topic.tags.split(", ") if topic.tags else [],
                "attachments": attachments,
                "shared_item_type": topic.shared_item_type,
                "shared_item_id": topic.shared_item_id,
                "status": topic.status,
                "stats": {
                    "views": topic.views_count or 0,
                    "likes": topic.likes_count or 0,
                    "comments": topic.comment_count or 0
                },
                "user_interaction": {
                    "liked": user_liked
                }
            }
            topic_data.append(topic_info)
        
        result = {
            "success": True,
            "message": "获取话题列表成功",
            "data": {
                "topics": topic_data,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size,
                    "has_next": page * page_size < total,
                    "has_prev": page > 1
                },
                "filters": {
                    "sort_by": sort_by,
                    "tag": tag,
                    "shared_type": shared_type,
                    "author_id": author_id,
                    "time_range": time_range
                }
            }
        }
        
        # 缓存结果（搜索结果除外）
        if not search:
            cache_manager.set(cache_key, result, expire=300)  # 5分钟缓存
        
        return result
        
    except Exception as e:
        logger.error(f"获取话题列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取话题列表失败: {str(e)}"
        )

@router.get("/topics/{topic_id}", summary="获取话题详情")
async def get_topic_detail_v2(
    topic_id: int,
    include_comments: bool = Query(default=True),
    comment_page: int = Query(1, ge=1),
    comment_page_size: int = Query(20, ge=1, le=100),
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取话题详情
    - 智能缓存策略
    - 异步浏览量更新
    - 相关话题推荐
    - 评论嵌套显示
    """
    try:
        # 构建缓存键
        cache_key = f"{CACHE_KEYS['topic_detail']}:{topic_id}:{current_user_id or 'anonymous'}"
        
        # 获取话题基本信息
        topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
        if not topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="话题不存在"
            )
        
        # 检查访问权限
        if topic.status == 'pending_review' and topic.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="话题正在审核中"
            )
        
        # 异步增加浏览量（防抖，同一用户5分钟内不重复计数）
        view_key = f"topic_view:{topic_id}:{current_user_id or 'anonymous'}"
        if not cache_manager.get(view_key):
            asyncio.create_task(increment_topic_view_count_v2(topic_id, db))
            cache_manager.set(view_key, True, expire=300)  # 5分钟防抖
        
        # 获取作者信息（缓存）
        author_info = query_optimizer.get_user_info_batch(db, [topic.user_id])
        
        # 获取话题统计（缓存）
        stats_cache_key = f"{CACHE_KEYS['topic_stats']}:{topic_id}"
        topic_stats = cache_manager.get(stats_cache_key)
        if not topic_stats:
            topic_stats = {
                "views": topic.views_count or 0,
                "likes": topic.likes_count or 0,
                "comments": topic.comment_count or 0,
                "shares": 0  # TODO: 实现分享功能
            }
            cache_manager.set(stats_cache_key, topic_stats, expire=300)
        
        # 检查当前用户互动状态
        user_interaction = {
            "liked": False,
            "followed_author": False,
            "bookmarked": False
        }
        
        if current_user_id:
            # 检查点赞状态
            like_exists = db.query(ForumLike).filter(
                and_(
                    ForumLike.topic_id == topic_id,
                    ForumLike.user_id == current_user_id
                )
            ).first()
            user_interaction["liked"] = like_exists is not None
            
            # 检查关注状态
            follow_exists = db.query(UserFollow).filter(
                and_(
                    UserFollow.follower_id == current_user_id,
                    UserFollow.followed_id == topic.user_id
                )
            ).first()
            user_interaction["followed_author"] = follow_exists is not None
        
        # 解析附件
        attachments = []
        if topic.attachments:
            try:
                attachments = json.loads(topic.attachments)
                # 为每个附件添加预览信息
                for attachment in attachments:
                    if attachment.get('type') == 'image':
                        attachment['preview_url'] = attachment.get('url')  # 可以添加缩略图逻辑
            except Exception as e:
                logger.warning(f"解析附件失败: {e}")
        
        # 解析@用户
        mentioned_users = []
        if topic.mentioned_users:
            try:
                mentioned_user_ids = json.loads(topic.mentioned_users)
                if mentioned_user_ids:
                    mentioned_users_info = query_optimizer.get_user_info_batch(db, mentioned_user_ids)
                    mentioned_users = list(mentioned_users_info.values())
            except Exception as e:
                logger.warning(f"解析@用户失败: {e}")
        
        # 构建话题详情
        topic_detail = {
            "id": topic.id,
            "title": topic.title,
            "content": topic.content,
            "author": author_info.get(topic.user_id, {"id": topic.user_id, "name": "未知用户"}),
            "created_at": topic.created_at.isoformat(),
            "updated_at": getattr(topic, 'updated_at', topic.created_at).isoformat(),
            "tags": topic.tags.split(", ") if topic.tags else [],
            "attachments": attachments,
            "shared_item_type": topic.shared_item_type,
            "shared_item_id": topic.shared_item_id,
            "status": topic.status,
            "mentioned_users": mentioned_users,
            "stats": topic_stats,
            "user_interaction": user_interaction
        }
        
        result = {
            "success": True,
            "message": "获取话题详情成功",
            "data": {
                "topic": topic_detail
            }
        }
        
        # 获取评论
        if include_comments:
            comments_data = await get_topic_comments_v2(
                topic_id, comment_page, comment_page_size, current_user_id, db
            )
            result["data"]["comments"] = comments_data["data"]
        
        # 获取相关话题推荐
        try:
            related_topics = await get_related_topics(topic, db, limit=5)
            result["data"]["related_topics"] = related_topics
        except Exception as e:
            logger.warning(f"获取相关话题失败: {e}")
            result["data"]["related_topics"] = []
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取话题详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取话题详情失败: {str(e)}"
        )

@router.put("/topics/{topic_id}", summary="更新话题")
async def update_topic_v2(
    topic_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    add_files: List[UploadFile] = File(default=[]),
    remove_file_urls: List[str] = Form(default=[]),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    更新话题
    - 支持部分更新
    - 文件增删改
    - 修改历史记录
    - AI内容重新处理
    """
    try:
        # 获取话题
        topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
        if not topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="话题不存在"
            )
        
        # 权限检查
        if topic.user_id != current_user_id:
            # TODO: 检查管理员权限
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限修改此话题"
            )
        
        # 速率限制（每用户每小时最多修改5次）
        is_allowed, rate_info = rate_limiter.check_rate_limit(
            current_user_id, "update_topic", cache_manager, limit=5, window=3600
        )
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"修改过于频繁，请稍后再试。{rate_info}"
            )
        
        # 保存修改历史
        history_data = {
            "old_title": topic.title,
            "old_content": topic.content,
            "old_tags": topic.tags,
            "modified_at": datetime.now().isoformat(),
            "modified_by": current_user_id
        }
        
        updated_fields = []
        
        # 更新标题
        if title is not None and title != topic.title:
            # 验证标题
            if len(title.strip()) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="标题不能为空"
                )
            topic.title = title.strip()[:200]
            updated_fields.append("title")
        
        # 更新内容
        if content is not None and content != topic.content:
            # AI处理内容
            ai_result = await process_content_with_ai(content, current_user_id, db)
            topic.content = ai_result['processed_content']
            topic.mentioned_users = json.dumps(ai_result['mentions']) if ai_result['mentions'] else topic.mentioned_users
            topic.embedding = ai_result['embedding']
            
            # 重新审核（如果风险分数过高）
            if ai_result['risk_score'] > 0.7:
                topic.status = 'pending_review'
            
            updated_fields.append("content")
        
        # 更新标签
        if tags is not None and tags != topic.tags:
            topic.tags = tags[:500] if tags else None
            updated_fields.append("tags")
        
        # 处理文件
        current_attachments = []
        if topic.attachments:
            try:
                current_attachments = json.loads(topic.attachments)
            except:
                current_attachments = []
        
        # 删除指定文件
        if remove_file_urls:
            current_attachments = [
                att for att in current_attachments 
                if att.get('url') not in remove_file_urls
            ]
            # TODO: 从OSS删除文件
            updated_fields.append("attachments")
        
        # 添加新文件
        if add_files and add_files[0].filename:
            for file in add_files:
                if file.filename:
                    try:
                        file_result = await upload_single_file(file, current_user_id)
                        current_attachments.append(file_result)
                    except Exception as e:
                        logger.warning(f"上传文件失败: {e}")
            updated_fields.append("attachments")
        
        # 更新附件
        if updated_fields and "attachments" in updated_fields:
            topic.attachments = json.dumps(current_attachments) if current_attachments else None
            topic.attachments_json = topic.attachments  # 兼容性
            
            # 更新兼容字段
            if current_attachments:
                first_file = current_attachments[0]
                topic.media_url = first_file.get("url")
                topic.media_type = first_file.get("type")
                topic.original_filename = first_file.get("filename")
                topic.media_size_bytes = first_file.get("size")
            else:
                topic.media_url = None
                topic.media_type = None
                topic.original_filename = None
                topic.media_size_bytes = None
        
        # 更新组合文本用于搜索
        if updated_fields:
            topic.combined_text = f"{topic.title}. {topic.content}. {topic.tags or ''}".strip()
            topic.updated_at = datetime.now()
            
            # 保存修改历史（可以扩展为专门的历史表）
            if not hasattr(topic, 'edit_history'):
                topic.edit_history = json.dumps([history_data])
            else:
                try:
                    history = json.loads(topic.edit_history or "[]")
                    history.append(history_data)
                    topic.edit_history = json.dumps(history[-10:])  # 只保留最近10次修改
                except:
                    topic.edit_history = json.dumps([history_data])
        
        db.commit()
        db.refresh(topic)
        
        # 清除相关缓存
        await clear_topic_related_cache_v2(topic_id)
        
        return {
            "success": True,
            "message": "话题更新成功",
            "data": {
                "topic_id": topic.id,
                "updated_fields": updated_fields,
                "status": topic.status
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新话题失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新话题失败: {str(e)}"
        )

@router.delete("/topics/{topic_id}", summary="删除话题（软删除）")
async def delete_topic_v2(
    topic_id: int,
    permanent: bool = Query(default=False, description="是否永久删除"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    删除话题（支持软删除和硬删除）
    """
    try:
        # 获取话题
        topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
        if not topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="话题不存在"
            )
        
        # 权限检查
        if topic.user_id != current_user_id:
            # TODO: 检查管理员权限
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限删除此话题"
            )
        
        if permanent:
            # 硬删除：删除所有相关数据
            # 删除评论
            db.query(ForumComment).filter(ForumComment.topic_id == topic_id).delete()
            # 删除点赞
            db.query(ForumLike).filter(ForumLike.topic_id == topic_id).delete()
            # 删除话题
            db.delete(topic)
            
            # TODO: 删除OSS文件
            if topic.attachments:
                try:
                    attachments = json.loads(topic.attachments)
                    for attachment in attachments:
                        asyncio.create_task(oss_utils.delete_file_from_oss(attachment.get('url', '')))
                except Exception as e:
                    logger.warning(f"删除OSS文件失败: {e}")
            
        else:
            # 软删除：标记为已删除
            topic.status = 'deleted'
            topic.deleted_at = datetime.now()
        
        db.commit()
        
        # 清除缓存
        await clear_topic_related_cache_v2(topic_id)
        
        return {
            "success": True,
            "message": "话题删除成功",
            "data": {
                "topic_id": topic_id,
                "permanent": permanent
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除话题失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除话题失败: {str(e)}"
        )

# ==================== 评论系统 ====================

async def get_topic_comments_v2(
    topic_id: int,
    page: int = 1,
    page_size: int = 20,
    current_user_id: Optional[int] = None,
    db: Session = None,
    sort_by: str = "latest"
) -> Dict[str, Any]:
    """获取话题评论（内部函数）"""
    try:
        # 构建缓存键
        cache_key = f"{CACHE_KEYS['comments']}:{topic_id}:{page}:{page_size}:{sort_by}"
        
        # 尝试从缓存获取
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建查询
        query = db.query(ForumComment).filter(ForumComment.topic_id == topic_id)
        
        # 排序
        if sort_by == "latest":
            query = query.order_by(desc(ForumComment.created_at))
        elif sort_by == "oldest":
            query = query.order_by(ForumComment.created_at)
        elif sort_by == "likes":
            query = query.order_by(desc(func.coalesce(ForumComment.likes_count, 0)))
        
        # 分页
        total = query.count()
        offset = (page - 1) * page_size
        comments = query.offset(offset).limit(page_size).all()
        
        # 获取用户信息
        user_ids = list(set([comment.user_id for comment in comments if comment.user_id]))
        user_info_batch = query_optimizer.get_user_info_batch(db, user_ids) if user_ids else {}
        
        # 构建评论数据
        comments_data = []
        for comment in comments:
            # 检查当前用户是否点赞此评论
            user_liked = False
            if current_user_id:
                like_exists = db.query(ForumLike).filter(
                    and_(
                        ForumLike.comment_id == comment.id,
                        ForumLike.user_id == current_user_id
                    )
                ).first()
                user_liked = like_exists is not None
            
            # 获取回复数量
            reply_count = db.query(ForumComment).filter(ForumComment.parent_id == comment.id).count()
            
            comment_info = {
                "id": comment.id,
                "content": comment.content,
                "author": user_info_batch.get(comment.user_id, {"id": comment.user_id, "name": "未知用户"}),
                "created_at": comment.created_at.isoformat(),
                "updated_at": getattr(comment, 'updated_at', comment.created_at).isoformat(),
                "parent_id": comment.parent_id,
                "likes_count": getattr(comment, 'likes_count', 0),
                "reply_count": reply_count,
                "user_interaction": {
                    "liked": user_liked
                }
            }
            comments_data.append(comment_info)
        
        result = {
            "comments": comments_data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "has_next": page * page_size < total,
                "has_prev": page > 1
            }
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, expire=300)  # 5分钟缓存
        
        return result
        
    except Exception as e:
        logger.error(f"获取评论失败: {e}")
        return {"comments": [], "pagination": {"page": page, "page_size": page_size, "total": 0}}

@router.get("/topics/{topic_id}/comments", summary="获取话题评论")
async def get_topic_comments_endpoint_v2(
    topic_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("latest", regex="^(latest|oldest|likes)$"),
    parent_id: Optional[int] = Query(None, description="获取指定评论的回复"),
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取话题评论
    - 支持嵌套评论
    - 多种排序方式
    - 分页优化
    """
    try:
        # 验证话题存在
        topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
        if not topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="话题不存在"
            )
        
        if parent_id:
            # 获取指定评论的回复
            query = db.query(ForumComment).filter(
                and_(
                    ForumComment.topic_id == topic_id,
                    ForumComment.parent_id == parent_id
                )
            )
        else:
            # 获取顶级评论（parent_id为空）
            query = db.query(ForumComment).filter(
                and_(
                    ForumComment.topic_id == topic_id,
                    ForumComment.parent_id.is_(None)
                )
            )
        
        # 排序
        if sort_by == "latest":
            query = query.order_by(desc(ForumComment.created_at))
        elif sort_by == "oldest":
            query = query.order_by(ForumComment.created_at)
        elif sort_by == "likes":
            query = query.order_by(desc(func.coalesce(ForumComment.likes_count, 0)))
        
        # 分页
        total = query.count()
        offset = (page - 1) * page_size
        comments = query.offset(offset).limit(page_size).all()
        
        # 获取用户信息
        user_ids = list(set([comment.user_id for comment in comments if comment.user_id]))
        user_info_batch = query_optimizer.get_user_info_batch(db, user_ids) if user_ids else {}
        
        # 构建评论数据
        comments_data = []
        for comment in comments:
            # 检查当前用户是否点赞此评论
            user_liked = False
            if current_user_id:
                like_exists = db.query(ForumLike).filter(
                    and_(
                        ForumLike.comment_id == comment.id,
                        ForumLike.user_id == current_user_id
                    )
                ).first()
                user_liked = like_exists is not None
            
            # 获取回复数量和最新回复预览
            reply_count = db.query(ForumComment).filter(ForumComment.parent_id == comment.id).count()
            latest_replies = []
            
            if reply_count > 0 and not parent_id:  # 只有顶级评论才显示回复预览
                latest_reply_query = db.query(ForumComment).filter(
                    ForumComment.parent_id == comment.id
                ).order_by(desc(ForumComment.created_at)).limit(3)
                
                for reply in latest_reply_query:
                    reply_author = user_info_batch.get(reply.user_id, {"id": reply.user_id, "name": "未知用户"})
                    latest_replies.append({
                        "id": reply.id,
                        "content": reply.content[:100] + "..." if len(reply.content) > 100 else reply.content,
                        "author": reply_author,
                        "created_at": reply.created_at.isoformat()
                    })
            
            comment_info = {
                "id": comment.id,
                "content": comment.content,
                "author": user_info_batch.get(comment.user_id, {"id": comment.user_id, "name": "未知用户"}),
                "created_at": comment.created_at.isoformat(),
                "updated_at": getattr(comment, 'updated_at', comment.created_at).isoformat(),
                "parent_id": comment.parent_id,
                "likes_count": getattr(comment, 'likes_count', 0),
                "reply_count": reply_count,
                "latest_replies": latest_replies,
                "user_interaction": {
                    "liked": user_liked
                }
            }
            comments_data.append(comment_info)
        
        return {
            "success": True,
            "message": "获取评论成功",
            "data": {
                "comments": comments_data,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size,
                    "has_next": page * page_size < total,
                    "has_prev": page > 1
                },
                "parent_id": parent_id,
                "sort_by": sort_by
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取评论失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取评论失败: {str(e)}"
        )

@router.post("/topics/{topic_id}/comments", summary="发布评论")
async def create_comment_v2(
    topic_id: int,
    content: str = Form(...),
    parent_id: Optional[int] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    发布评论
    - AI内容处理
    - 嵌套回复支持
    - 智能通知
    - 防刷机制
    """
    try:
        # 验证话题存在
        topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
        if not topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="话题不存在"
            )
        
        # 验证父评论（如果是回复）
        parent_comment = None
        if parent_id:
            parent_comment = db.query(ForumComment).filter(
                and_(
                    ForumComment.id == parent_id,
                    ForumComment.topic_id == topic_id
                )
            ).first()
            if not parent_comment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="父评论不存在"
                )
        
        # 速率限制（每用户每分钟最多5条评论）
        is_allowed, rate_info = rate_limiter.check_rate_limit(
            current_user_id, "post_comment", cache_manager, limit=5, window=60
        )
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"评论过于频繁，请稍后再试。{rate_info}"
            )
        
        # AI内容处理
        ai_result = await process_content_with_ai(content, current_user_id, db)
        
        # 内容安全验证
        cleaned_content = input_validator.sanitize_html(ai_result['processed_content'])
        
        # SQL注入检测
        has_injection, _ = input_validator.detect_sql_injection(content)
        if has_injection:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="评论内容包含非法字符"
            )
        
        # 内容审核
        is_approved, reason, risk_score = content_moderator.moderate_content(content)
        if not is_approved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reason
            )
        
        # 创建评论
        new_comment = ForumComment(
            topic_id=topic_id,
            content=cleaned_content,
            user_id=current_user_id,
            parent_id=parent_id,
            mentioned_users=json.dumps(ai_result['mentions']) if ai_result['mentions'] else None,
            created_at=datetime.now(),
            status='active' if risk_score < 0.5 else 'pending_review',
            likes_count=0
        )
        
        db.add(new_comment)
        db.flush()
        
        # 更新话题评论数
        topic.comment_count = (topic.comment_count or 0) + 1
        topic.updated_at = datetime.now()  # 更新话题最后活动时间
        
        # 更新父评论回复数（如果是回复）
        if parent_comment:
            parent_comment.reply_count = (getattr(parent_comment, 'reply_count', 0) or 0) + 1
        
        # 评论奖励积分
        try:
            user = db.query(Student).filter(Student.id == current_user_id).first()
            if user:
                from main import _award_points, _check_and_award_achievements
                comment_points = 5
                await _award_points(
                    db=db,
                    user=user,
                    amount=comment_points,
                    reason=f"发布评论：'{content[:50]}...'",
                    transaction_type="EARN",
                    related_entity_type="forum_comment",
                    related_entity_id=new_comment.id
                )
                await _check_and_award_achievements(db, current_user_id)
        except Exception as e:
            logger.warning(f"评论积分奖励失败: {e}")
        
        db.commit()
        db.refresh(new_comment)
        
        # 后台任务：发送通知
        notification_targets = []
        
        # 通知话题作者（如果不是自己）
        if topic.user_id != current_user_id:
            notification_targets.append({
                "user_id": topic.user_id,
                "type": "topic_comment",
                "message": f"您的话题收到了新评论"
            })
        
        # 通知父评论作者（如果是回复且不是自己）
        if parent_comment and parent_comment.user_id != current_user_id:
            notification_targets.append({
                "user_id": parent_comment.user_id,
                "type": "comment_reply",
                "message": f"您的评论收到了新回复"
            })
        
        # 通知@用户
        if ai_result['mentions']:
            for mentioned_user_id in ai_result['mentions']:
                if mentioned_user_id not in [current_user_id, topic.user_id, parent_comment.user_id if parent_comment else None]:
                    notification_targets.append({
                        "user_id": mentioned_user_id,
                        "type": "mention",
                        "message": f"您在评论中被提及"
                    })
        
        if notification_targets:
            background_tasks.add_task(
                send_comment_notifications_v2,
                notification_targets,
                new_comment.id,
                topic_id,
                current_user_id
            )
        
        # 清除相关缓存
        background_tasks.add_task(clear_comment_related_cache_v2, topic_id)
        
        return {
            "success": True,
            "message": "评论发布成功",
            "data": {
                "comment_id": new_comment.id,
                "status": new_comment.status,
                "mentioned_users": ai_result['mentions'],
                "risk_score": risk_score
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布评论失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发布评论失败: {str(e)}"
        )

@router.put("/comments/{comment_id}", summary="更新评论")
async def update_comment_v2(
    comment_id: int,
    content: str = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新评论内容"""
    try:
        # 获取评论
        comment = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="评论不存在"
            )
        
        # 权限检查
        if comment.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限修改此评论"
            )
        
        # 检查评论是否可以编辑（例如：发布24小时内）
        if datetime.now() - comment.created_at > timedelta(hours=24):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="评论发布超过24小时，无法编辑"
            )
        
        # AI处理新内容
        ai_result = await process_content_with_ai(content, current_user_id, db)
        cleaned_content = input_validator.sanitize_html(ai_result['processed_content'])
        
        # 保存编辑历史
        edit_history = {
            "old_content": comment.content,
            "edited_at": datetime.now().isoformat()
        }
        
        # 更新评论
        comment.content = cleaned_content
        comment.mentioned_users = json.dumps(ai_result['mentions']) if ai_result['mentions'] else comment.mentioned_users
        comment.updated_at = datetime.now()
        comment.edit_history = json.dumps([edit_history])  # 简化版历史记录
        
        db.commit()
        
        # 清除缓存
        await clear_comment_related_cache_v2(comment.topic_id)
        
        return {
            "success": True,
            "message": "评论更新成功",
            "data": {
                "comment_id": comment.id,
                "mentioned_users": ai_result['mentions']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新评论失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新评论失败: {str(e)}"
        )

@router.delete("/comments/{comment_id}", summary="删除评论")
async def delete_comment_v2(
    comment_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除评论（软删除）"""
    try:
        # 获取评论
        comment = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="评论不存在"
            )
        
        # 权限检查
        if comment.user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限删除此评论"
            )
        
        # 软删除
        comment.status = 'deleted'
        comment.deleted_at = datetime.now()
        
        # 更新话题评论数
        topic = db.query(ForumTopic).filter(ForumTopic.id == comment.topic_id).first()
        if topic:
            topic.comment_count = max((topic.comment_count or 1) - 1, 0)
        
        # 更新父评论回复数
        if comment.parent_id:
            parent_comment = db.query(ForumComment).filter(ForumComment.id == comment.parent_id).first()
            if parent_comment:
                parent_comment.reply_count = max((getattr(parent_comment, 'reply_count', 1) or 1) - 1, 0)
        
        db.commit()
        
        # 清除缓存
        await clear_comment_related_cache_v2(comment.topic_id)
        
        return {
            "success": True,
            "message": "评论删除成功",
            "data": {
                "comment_id": comment.id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除评论失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除评论失败: {str(e)}"
        )

# ==================== 点赞和互动系统 ====================

@router.post("/like", summary="点赞/取消点赞")
async def toggle_like_v2(
    target_type: str = Form(..., regex="^(topic|comment)$"),
    target_id: int = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    点赞/取消点赞话题或评论
    """
    try:
        # 验证目标存在
        if target_type == "topic":
            target = db.query(ForumTopic).filter(ForumTopic.id == target_id).first()
            if not target:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="话题不存在"
                )
        elif target_type == "comment":
            target = db.query(ForumComment).filter(ForumComment.id == target_id).first()
            if not target:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="评论不存在"
                )
        
        # 检查是否已点赞
        like_filter = {"user_id": current_user_id}
        if target_type == "topic":
            like_filter["topic_id"] = target_id
        else:
            like_filter["comment_id"] = target_id
        
        existing_like = db.query(ForumLike).filter_by(**like_filter).first()
        
        if existing_like:
            # 取消点赞
            db.delete(existing_like)
            
            # 更新计数
            if target_type == "topic":
                target.likes_count = max((target.likes_count or 1) - 1, 0)
            else:
                target.likes_count = max((getattr(target, 'likes_count', 1) or 1) - 1, 0)
            
            action = "unliked"
            
        else:
            # 添加点赞
            new_like = ForumLike(
                user_id=current_user_id,
                topic_id=target_id if target_type == "topic" else None,
                comment_id=target_id if target_type == "comment" else None,
                created_at=datetime.now()
            )
            db.add(new_like)
            
            # 更新计数
            if target_type == "topic":
                target.likes_count = (target.likes_count or 0) + 1
            else:
                if not hasattr(target, 'likes_count'):
                    target.likes_count = 0
                target.likes_count = (target.likes_count or 0) + 1
            
            action = "liked"
            
            # 点赞奖励积分（给被点赞者）
            try:
                target_author = db.query(Student).filter(Student.id == target.user_id).first()
                if target_author and target.user_id != current_user_id:
                    from main import _award_points
                    like_points = 2
                    await _award_points(
                        db=db,
                        user=target_author,
                        amount=like_points,
                        reason=f"收到点赞：{target_type}",
                        transaction_type="EARN",
                        related_entity_type="forum_like",
                        related_entity_id=new_like.id if not existing_like else None
                    )
            except Exception as e:
                logger.warning(f"点赞积分奖励失败: {e}")
        
        db.commit()
        
        # 清除相关缓存
        if target_type == "topic":
            await clear_topic_related_cache_v2(target_id)
        else:
            await clear_comment_related_cache_v2(target.topic_id)
        
        return {
            "success": True,
            "message": f"{'点赞' if action == 'liked' else '取消点赞'}成功",
            "data": {
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "likes_count": target.likes_count or 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"点赞操作失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"点赞操作失败: {str(e)}"
        )

@router.post("/follow", summary="关注/取消关注用户")
async def toggle_follow_v2(
    target_user_id: int = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """关注/取消关注用户"""
    try:
        # 不能关注自己
        if target_user_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能关注自己"
            )
        
        # 验证目标用户存在
        target_user = db.query(Student).filter(Student.id == target_user_id).first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        # 检查是否已关注
        existing_follow = db.query(UserFollow).filter(
            and_(
                UserFollow.follower_id == current_user_id,
                UserFollow.followed_id == target_user_id
            )
        ).first()
        
        if existing_follow:
            # 取消关注
            db.delete(existing_follow)
            action = "unfollowed"
        else:
            # 添加关注
            new_follow = UserFollow(
                follower_id=current_user_id,
                followed_id=target_user_id,
                created_at=datetime.now()
            )
            db.add(new_follow)
            action = "followed"
        
        db.commit()
        
        return {
            "success": True,
            "message": f"{'关注' if action == 'followed' else '取消关注'}成功",
            "data": {
                "action": action,
                "target_user_id": target_user_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"关注操作失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"关注操作失败: {str(e)}"
        )

# ==================== 搜索和推荐系统 ====================

@router.get("/search", summary="智能搜索")
async def search_v2(
    q: str = Query(..., min_length=2, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search_type: str = Query("all", regex="^(all|topic|comment|user)$"),
    sort_by: str = Query("relevance", regex="^(relevance|date|popularity)$"),
    time_range: Optional[str] = Query(None, regex="^(day|week|month|year|all)$"),
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    智能搜索
    - 全文搜索
    - 语义搜索
    - 多类型搜索
    - 智能排序
    """
    try:
        # 清理搜索查询
        clean_query = input_validator.sanitize_search_query(q)
        
        # 构建缓存键
        cache_key = f"{CACHE_KEYS['search_results']}:{clean_query}:{page}:{page_size}:{search_type}:{sort_by}:{time_range}"
        
        # 尝试从缓存获取
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        results = {
            "topics": [],
            "comments": [],
            "users": []
        }
        
        # 搜索话题
        if search_type in ["all", "topic"]:
            topic_query = db.query(ForumTopic).filter(
                and_(
                    ForumTopic.status == 'active',
                    or_(
                        ForumTopic.title.ilike(f"%{clean_query}%"),
                        ForumTopic.content.ilike(f"%{clean_query}%"),
                        ForumTopic.tags.ilike(f"%{clean_query}%")
                    )
                )
            )
            
            # 时间范围过滤
            if time_range and time_range != 'all':
                time_delta = {
                    'day': timedelta(days=1),
                    'week': timedelta(weeks=1),
                    'month': timedelta(days=30),
                    'year': timedelta(days=365)
                }.get(time_range)
                
                if time_delta:
                    topic_query = topic_query.filter(
                        ForumTopic.created_at >= datetime.now() - time_delta
                    )
            
            # 排序
            if sort_by == "relevance":
                # 简单的相关性算法：标题匹配权重更高
                topic_query = topic_query.order_by(
                    desc(
                        func.case(
                            [(ForumTopic.title.ilike(f"%{clean_query}%"), 3)],
                            else_=1
                        ) * (func.coalesce(ForumTopic.likes_count, 0) + 1)
                    )
                )
            elif sort_by == "date":
                topic_query = topic_query.order_by(desc(ForumTopic.created_at))
            elif sort_by == "popularity":
                topic_query = topic_query.order_by(
                    desc(
                        func.coalesce(ForumTopic.likes_count, 0) * 2 +
                        func.coalesce(ForumTopic.comment_count, 0) * 3 +
                        func.coalesce(ForumTopic.views_count, 0) * 0.1
                    )
                )
            
            topic_total = topic_query.count()
            if search_type == "topic":
                # 单独搜索话题时使用分页
                offset = (page - 1) * page_size
                topics = topic_query.offset(offset).limit(page_size).all()
            else:
                # 综合搜索时限制数量
                topics = topic_query.limit(10).all()
            
            # 处理话题结果
            user_ids = list(set([topic.user_id for topic in topics if topic.user_id]))
            user_info_batch = query_optimizer.get_user_info_batch(db, user_ids) if user_ids else {}
            
            for topic in topics:
                topic_data = {
                    "id": topic.id,
                    "title": topic.title,
                    "content": topic.content[:200] + "..." if len(topic.content) > 200 else topic.content,
                    "author": user_info_batch.get(topic.user_id, {"id": topic.user_id, "name": "未知用户"}),
                    "created_at": topic.created_at.isoformat(),
                    "tags": topic.tags.split(", ") if topic.tags else [],
                    "stats": {
                        "views": topic.views_count or 0,
                        "likes": topic.likes_count or 0,
                        "comments": topic.comment_count or 0
                    }
                }
                results["topics"].append(topic_data)
        
        # 搜索评论
        if search_type in ["all", "comment"]:
            comment_query = db.query(ForumComment).filter(
                and_(
                    ForumComment.content.ilike(f"%{clean_query}%"),
                    ForumComment.status == 'active'
                )
            ).order_by(desc(ForumComment.created_at)).limit(5 if search_type == "all" else page_size)
            
            comments = comment_query.all()
            
            # 获取评论相关信息
            comment_user_ids = list(set([comment.user_id for comment in comments if comment.user_id]))
            topic_ids = list(set([comment.topic_id for comment in comments if comment.topic_id]))
            
            comment_user_info = query_optimizer.get_user_info_batch(db, comment_user_ids) if comment_user_ids else {}
            topic_info = {topic.id: topic for topic in db.query(ForumTopic).filter(ForumTopic.id.in_(topic_ids)).all()} if topic_ids else {}
            
            for comment in comments:
                comment_data = {
                    "id": comment.id,
                    "content": comment.content[:150] + "..." if len(comment.content) > 150 else comment.content,
                    "author": comment_user_info.get(comment.user_id, {"id": comment.user_id, "name": "未知用户"}),
                    "created_at": comment.created_at.isoformat(),
                    "topic": {
                        "id": comment.topic_id,
                        "title": topic_info.get(comment.topic_id).title if topic_info.get(comment.topic_id) else "未知话题"
                    },
                    "likes_count": getattr(comment, 'likes_count', 0)
                }
                results["comments"].append(comment_data)
        
        # 搜索用户
        if search_type in ["all", "user"]:
            user_query = db.query(Student).filter(
                or_(
                    Student.name.ilike(f"%{clean_query}%"),
                    Student.username.ilike(f"%{clean_query}%")
                )
            ).limit(5 if search_type == "all" else page_size)
            
            users = user_query.all()
            
            for user in users:
                user_data = {
                    "id": user.id,
                    "name": user.name,
                    "username": getattr(user, 'username', ''),
                    "avatar": getattr(user, 'avatar_url', ''),
                    # 可以添加用户统计信息
                }
                results["users"].append(user_data)
        
        # 计算总数（仅在单类型搜索时有效）
        total = topic_total if search_type == "topic" else len(results["topics"] + results["comments"] + results["users"])
        
        result = {
            "success": True,
            "message": "搜索完成",
            "data": {
                "query": clean_query,
                "results": results,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size if search_type != "all" else 1,
                    "has_next": page * page_size < total if search_type != "all" else False,
                    "has_prev": page > 1
                },
                "search_type": search_type,
                "sort_by": sort_by,
                "time_range": time_range
            }
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, expire=300)  # 5分钟缓存
        
        return result
        
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )

@router.get("/trending", summary="获取趋势话题")
async def get_trending_topics_v2(
    limit: int = Query(20, ge=1, le=100),
    time_range_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    """获取趋势话题"""
    try:
        cache_key = f"trending_topics:{limit}:{time_range_hours}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 计算趋势分数：考虑时间衰减的热度
        time_threshold = datetime.now() - timedelta(hours=time_range_hours)
        
        topics = db.query(ForumTopic).filter(
            and_(
                ForumTopic.status == 'active',
                ForumTopic.created_at >= time_threshold
            )
        ).all()
        
        # 计算趋势分数
        trending_topics = []
        for topic in topics:
            hours_since_created = (datetime.now() - topic.created_at).total_seconds() / 3600
            trending_score = (
                (topic.likes_count or 0) * 2 +
                (topic.comment_count or 0) * 3 +
                (topic.views_count or 0) * 0.1
            ) / max(hours_since_created ** 0.8, 1)  # 时间衰减
            
            trending_topics.append({
                "topic": topic,
                "trending_score": trending_score
            })
        
        # 排序并取前N个
        trending_topics.sort(key=lambda x: x["trending_score"], reverse=True)
        top_trending = trending_topics[:limit]
        
        # 获取用户信息
        user_ids = list(set([item["topic"].user_id for item in top_trending if item["topic"].user_id]))
        user_info_batch = query_optimizer.get_user_info_batch(db, user_ids) if user_ids else {}
        
        # 构建结果
        trending_data = []
        for item in top_trending:
            topic = item["topic"]
            topic_data = {
                "id": topic.id,
                "title": topic.title,
                "content": topic.content[:200] + "..." if len(topic.content) > 200 else topic.content,
                "author": user_info_batch.get(topic.user_id, {"id": topic.user_id, "name": "未知用户"}),
                "created_at": topic.created_at.isoformat(),
                "tags": topic.tags.split(", ") if topic.tags else [],
                "stats": {
                    "views": topic.views_count or 0,
                    "likes": topic.likes_count or 0,
                    "comments": topic.comment_count or 0
                },
                "trending_score": round(item["trending_score"], 2)
            }
            trending_data.append(topic_data)
        
        result = {
            "success": True,
            "message": "获取趋势话题成功",
            "data": {
                "topics": trending_data,
                "time_range_hours": time_range_hours,
                "cache_info": cache_manager.get_stats()
            }
        }
        
        # 缓存结果
        cache_manager.set(cache_key, result, expire=600)  # 10分钟缓存
        
        return result
        
    except Exception as e:
        logger.error(f"获取趋势话题失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取趋势话题失败: {str(e)}"
        )

# ==================== 管理员功能 ====================

@router.post("/admin/cache/refresh", summary="刷新缓存")
async def refresh_cache_v2(
    cache_type: str = Query(..., regex="^(hot_topics|trending|user_stats|search|all)$"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """刷新缓存（管理员功能）"""
    try:
        # TODO: 添加管理员权限检查
        
        if cache_type == "hot_topics":
            background_tasks.add_task(cache_scheduler.refresh_hot_topics_cache, db)
        elif cache_type == "trending":
            background_tasks.add_task(refresh_trending_cache, db)
        elif cache_type == "all":
            background_tasks.add_task(clear_all_cache_v2)
        
        return {
            "success": True,
            "message": f"缓存刷新任务已启动: {cache_type}",
            "data": {
                "cache_type": cache_type,
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"刷新缓存失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刷新缓存失败: {str(e)}"
        )

@router.get("/admin/stats", summary="获取系统统计")
async def get_system_stats_v2(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取系统统计信息"""
    try:
        # TODO: 添加管理员权限检查
        
        # 缓存统计
        cache_stats = cache_manager.get_stats()
        
        # 数据库统计
        total_topics = db.query(ForumTopic).count()
        active_topics = db.query(ForumTopic).filter(ForumTopic.status == 'active').count()
        pending_topics = db.query(ForumTopic).filter(ForumTopic.status == 'pending_review').count()
        
        total_comments = db.query(ForumComment).count()
        active_comments = db.query(ForumComment).filter(ForumComment.status == 'active').count()
        
        total_likes = db.query(ForumLike).count()
        total_follows = db.query(UserFollow).count()
        
        # 时间统计
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        topics_today = db.query(ForumTopic).filter(
            func.date(ForumTopic.created_at) == today
        ).count()
        
        topics_this_week = db.query(ForumTopic).filter(
            ForumTopic.created_at >= week_ago
        ).count()
        
        topics_this_month = db.query(ForumTopic).filter(
            ForumTopic.created_at >= month_ago
        ).count()
        
        # 用户活跃度统计
        active_users_today = db.query(func.count(func.distinct(ForumTopic.user_id))).filter(
            func.date(ForumTopic.created_at) == today
        ).scalar()
        
        return {
            "success": True,
            "data": {
                "cache_stats": cache_stats,
                "database_stats": {
                    "topics": {
                        "total": total_topics,
                        "active": active_topics,
                        "pending_review": pending_topics,
                        "today": topics_today,
                        "this_week": topics_this_week,
                        "this_month": topics_this_month
                    },
                    "comments": {
                        "total": total_comments,
                        "active": active_comments
                    },
                    "interactions": {
                        "total_likes": total_likes,
                        "total_follows": total_follows
                    },
                    "users": {
                        "active_today": active_users_today
                    }
                },
                "timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )

# ==================== 工具和后台任务函数 ====================

async def increment_topic_view_count_v2(topic_id: int, db: Session):
    """异步增加话题浏览量"""
    try:
        # 使用原子操作更新浏览量
        db.query(ForumTopic).filter(ForumTopic.id == topic_id).update(
            {ForumTopic.views_count: ForumTopic.views_count + 1},
            synchronize_session=False
        )
        db.commit()
        
        # 更新缓存中的统计数据
        stats_cache_key = f"{CACHE_KEYS['topic_stats']}:{topic_id}"
        cache_manager.delete(stats_cache_key)
        
    except Exception as e:
        logger.error(f"更新浏览量失败: {e}")
        db.rollback()

async def get_related_topics(topic: ForumTopic, db: Session, limit: int = 5) -> List[Dict[str, Any]]:
    """获取相关话题"""
    try:
        related_topics = []
        
        # 基于标签的相关性
        if topic.tags:
            tags = [tag.strip() for tag in topic.tags.split(",") if tag.strip()]
            if tags:
                tag_related = db.query(ForumTopic).filter(
                    and_(
                        ForumTopic.id != topic.id,
                        ForumTopic.status == 'active',
                        or_(*[ForumTopic.tags.ilike(f"%{tag}%") for tag in tags])
                    )
                ).order_by(desc(ForumTopic.likes_count)).limit(limit).all()
                
                for related in tag_related:
                    related_topics.append({
                        "id": related.id,
                        "title": related.title,
                        "author_id": related.user_id,
                        "created_at": related.created_at.isoformat(),
                        "stats": {
                            "likes": related.likes_count or 0,
                            "comments": related.comment_count or 0
                        }
                    })
        
        return related_topics[:limit]
        
    except Exception as e:
        logger.warning(f"获取相关话题失败: {e}")
        return []

async def send_mention_notifications_v2(mentioned_user_ids: List[int], content_id: int, sender_id: int, content_type: str):
    """发送@通知"""
    try:
        # TODO: 实现通知系统
        # 可以发送邮件、站内信、推送通知等
        logger.info(f"发送@通知: {mentioned_user_ids}, {content_type}:{content_id}, 发送者:{sender_id}")
    except Exception as e:
        logger.error(f"发送@通知失败: {e}")

async def send_comment_notifications_v2(notification_targets: List[Dict], comment_id: int, topic_id: int, sender_id: int):
    """发送评论通知"""
    try:
        # TODO: 实现通知系统
        logger.info(f"发送评论通知: {len(notification_targets)} 个目标, 评论:{comment_id}, 话题:{topic_id}, 发送者:{sender_id}")
    except Exception as e:
        logger.error(f"发送评论通知失败: {e}")

async def clear_topic_related_cache_v2(topic_id: int):
    """清除话题相关缓存"""
    try:
        patterns = [
            f"{CACHE_KEYS['topic_detail']}:{topic_id}:*",
            f"{CACHE_KEYS['topic_stats']}:{topic_id}",
            f"{CACHE_KEYS['hot_topics']}:*",
            "trending_topics:*"
        ]
        
        for pattern in patterns:
            cache_manager.delete_pattern(pattern)
            
    except Exception as e:
        logger.error(f"清除话题缓存失败: {e}")

async def clear_comment_related_cache_v2(topic_id: int):
    """清除评论相关缓存"""
    try:
        patterns = [
            f"{CACHE_KEYS['comments']}:{topic_id}:*",
            f"{CACHE_KEYS['topic_stats']}:{topic_id}",
            f"topic_comment_count:{topic_id}"
        ]
        
        for pattern in patterns:
            cache_manager.delete_pattern(pattern)
            
    except Exception as e:
        logger.error(f"清除评论缓存失败: {e}")

async def clear_all_cache_v2():
    """清除所有缓存"""
    try:
        patterns = [
            "forum:*",
            "user:*",
            "topic_*",
            "trending_*"
        ]
        
        for pattern in patterns:
            cache_manager.delete_pattern(pattern)
            
        logger.info("所有论坛缓存已清除")
        
    except Exception as e:
        logger.error(f"清除所有缓存失败: {e}")

async def update_trending_topics():
    """更新趋势话题缓存"""
    try:
        cache_manager.delete_pattern("trending_topics:*")
        logger.info("趋势话题缓存已更新")
    except Exception as e:
        logger.error(f"更新趋势话题缓存失败: {e}")

async def refresh_trending_cache(db: Session):
    """刷新趋势缓存"""
    try:
        cache_manager.delete_pattern("trending_topics:*")
        # 预热缓存
        await get_trending_topics_v2(limit=20, time_range_hours=24, db=db)
        logger.info("趋势缓存刷新完成")
    except Exception as e:
        logger.error(f"刷新趋势缓存失败: {e}")
