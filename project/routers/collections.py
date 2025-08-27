# project/routers/collections.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal, Union, Tuple
import numpy as np
from datetime import timedelta, datetime, timezone, date
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, ForeignKey
from jose import JWTError, jwt
import requests, secrets, json, os, uuid, asyncio, httpx, re, traceback, time

# 导入数据库和模型
from database import SessionLocal, engine, init_db, get_db
from models import Student, Project, Note, KnowledgeBase, KnowledgeArticle, Course, UserCourse, CollectionItem, \
    DailyRecord, Folder, CollectedContent, ChatRoom, ChatMessage, ForumTopic, ForumComment, ForumLike, UserFollow, \
    UserMcpConfig, UserSearchEngineConfig, KnowledgeDocument, KnowledgeDocumentChunk, ChatRoomMember, \
    ChatRoomJoinRequest, Achievement, UserAchievement, PointTransaction, CourseMaterial, AIConversation, \
    AIConversationMessage, ProjectApplication, ProjectMember, KnowledgeBaseFolder, AIConversationTemporaryFile, \
    CourseLike, ProjectLike, ProjectFile
from dependencies import get_current_user_id
from utils import _get_text_part
import schemas
import oss_utils  # 添加缺失的导入
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_user_model_for_provider
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key
from ai_providers.config import get_user_model_for_provider

# --- 前端URL前缀常量 ---
FRONTEND_PROJECT_DETAIL_URL_PREFIX = "/projects/"  # 例如，将形成 /projects/123
FRONTEND_COURSE_DETAIL_URL_PREFIX = "/courses/"  # 例如，将形成 /courses/456
FRONTEND_FORUM_TOPIC_DETAIL_URL_PREFIX = "/forum/topics/"  # 例如，将形成 /forum/topics/789

router = APIRouter(
    prefix="/collections",
    tags=["收藏管理"],
    responses={404: {"description": "Not found"}},
)

# --- 辅助函数：创建收藏内容的内部逻辑 (用于复用) ---
async def _create_collected_content_item_internal(
        db: Session,
        current_user_id: int,
        content_data: schemas.CollectedContentBase,
        uploaded_file_bytes: Optional[bytes] = None,
        uploaded_file_object_name: Optional[str] = None,
        uploaded_file_content_type: Optional[str] = None,
        uploaded_file_original_filename: Optional[str] = None,
        uploaded_file_size: Optional[int] = None,
) -> CollectedContent:
    """
    内部辅助函数：处理收藏内容的创建逻辑，包括从共享项提取信息和生成嵌入。
    支持直接文件/媒体上传到OSS。
    """
    # 1. 验证目标文件夹是否存在且属于当前用户 (如果提供了folder_id)
    final_folder_id = content_data.folder_id
    if final_folder_id is None:  # 如果用户没有指定文件夹ID
        default_folder_name = "默认文件夹"
        default_folder = db.query(Folder).filter(
            Folder.owner_id == current_user_id,
            Folder.name == default_folder_name,
            Folder.parent_id.is_(None)  # 确保是顶级的"默认文件夹"
        ).first()

        if not default_folder:
            # 如果"默认文件夹"不存在，则创建它
            print(f"DEBUG_COLLECTION: 用户 {current_user_id} 的 '{default_folder_name}' 不存在，正在创建。")
            new_default_folder = Folder(
                owner_id=current_user_id,
                name=default_folder_name,
                description="自动创建的默认收藏文件夹。",
                parent_id=None  # 确保是顶级文件夹
            )
            db.add(new_default_folder)
            db.flush()  # 刷新以获取ID，但不提交，因为整个函数结束后才统一提交
            final_folder_id = new_default_folder.id
        else:
            final_folder_id = default_folder.id
        print(f"DEBUG_COLLECTION: 收藏将放入文件夹 ID: {final_folder_id} ('{default_folder_name}')")
    else:
        # 如果用户指定了 folder_id，验证其存在性和权限
        target_folder = db.query(Folder).filter(
            Folder.id == final_folder_id,
            Folder.owner_id == current_user_id
        ).first()
        if not target_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="目标文件夹未找到或无权访问。")

    # 这些变量将存储最终用于创建CollectedContent实例的值
    final_title = content_data.title
    final_type = content_data.type
    final_url = content_data.url
    final_content = content_data.content
    final_author = content_data.author
    final_tags = content_data.tags
    final_thumbnail = content_data.thumbnail
    final_duration = content_data.duration
    final_file_size = content_data.file_size
    final_status = content_data.status

    # 优先处理直接上传的文件/媒体
    if uploaded_file_bytes and uploaded_file_object_name and uploaded_file_content_type:
        final_url = f"{oss_utils.S3_BASE_URL.rstrip('/')}/{uploaded_file_object_name}"
        final_file_size = uploaded_file_size
        # 自动推断文件类型
        if uploaded_file_content_type.startswith("image/"):
            final_type = "image"
        elif uploaded_file_content_type.startswith("video/"):
            final_type = "video"
        else:
            final_type = "file"  # 其他文件类型

        # 如果没有提供title，使用文件名作为标题
        if not final_title and uploaded_file_original_filename:
            final_title = uploaded_file_original_filename

        # 如果没有提供content，使用文件描述作为内容
        if not final_content and uploaded_file_original_filename:
            final_content = f"Uploaded {final_type}: {uploaded_file_original_filename}"

    # 如果有 shared_item_type，说明是收藏内部资源 (但直接上传的文件更优先)
    elif content_data.shared_item_type and content_data.shared_item_id is not None:
        model_map = {
            "project": Project,
            "course": Course,
            "forum_topic": ForumTopic,
            "note": Note,
            "daily_record": DailyRecord,
            "knowledge_article": KnowledgeArticle,
            "chat_message": ChatMessage,
            "knowledge_document": KnowledgeDocument
        }
        source_model = model_map.get(content_data.shared_item_type)

        if not source_model:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的共享项类型: {content_data.shared_item_type}")

        # 获取源数据对象
        source_item = db.get(source_model, content_data.shared_item_id)  # 使用 db.get 更高效
        if not source_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"共享项 (类型: {content_data.shared_item_type}, ID: {content_data.shared_item_id}) 未找到。")

        # 从源数据对象提取信息来填充收藏内容，仅当对应字段在 content_data 中为 None (且未被直接上传文件填充) 时才进行填充
        if final_title is None:
            final_title = getattr(source_item, 'title', None) or getattr(source_item, 'name',
                                                                         None) or f"{content_data.shared_item_type} #{content_data.shared_item_id}"

        if final_content is None:
            final_content = getattr(source_item, 'description', None) or getattr(source_item, 'content', None)

        # 从 source_item 提取 URL
        if final_url is None:  # 只有当用户没有明确提供 URL 且没有直接上传文件时才从共享项中提取
            if hasattr(source_item, 'url') and source_item.url:
                final_url = source_item.url
            # For ChatMessage, check media_url
            elif hasattr(source_item,
                         'media_url') and source_item.media_url and content_data.shared_item_type == "chat_message":
                final_url = source_item.media_url
            # For KnowledgeDocument, file_path is the OSS URL
            elif hasattr(source_item, 'file_path') and source_item.file_path and content_data.shared_item_type in [
                "knowledge_document", "course_material"]:
                final_url = source_item.file_path  # file_path is now the OSS URL

        if final_author is None:
            if hasattr(source_item, 'owner') and source_item.owner and hasattr(source_item.owner, 'name'):
                final_author = source_item.owner.name
            elif hasattr(source_item, 'creator') and source_item.creator and hasattr(source_item.creator, 'name'):
                final_author = source_item.creator.name
            elif hasattr(source_item, 'author') and source_item.author and hasattr(source_item.author, 'name'):
                final_author = source_item.author.name
            elif hasattr(source_item, 'sender') and source_item.sender and hasattr(source_item.sender,
                                                                                   'name'):  # chat_message
                final_author = source_item.sender.name

        if final_tags is None:
            final_tags = getattr(source_item, 'tags', None)

        # 自动确定收藏类型，仅当 final_type 为 None 时才进行自动推断
        if final_type is None:  # 只有在 content_data.type 为 None (且没有直接上传文件) 时才推断
            if content_data.shared_item_type == "chat_message" and final_url:
                if "image/" in (getattr(source_item, 'message_type', '') or getattr(source_item, 'media_url',
                                                                                    '') or '').lower() or re.match(
                    r"(https?://.*\.(?:png|jpg|jpeg|gif|webp|bmp))", final_url, re.IGNORECASE):
                    final_type = "image"
                elif "video/" in (getattr(source_item, 'message_type', '') or getattr(source_item, 'media_url',
                                                                                      '') or '').lower() or re.match(
                    r"(https?://.*\.(?:mp4|avi|mov|mkv))", final_url, re.IGNORECASE):
                    final_type = "video"
                elif final_url.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):  # 常见文档格式
                    final_type = "document"  # Use 'document' for general files
                elif final_url:  # Everything else with a URL is a link
                    final_type = "link"
                else:  # Fallback for text-only chat messages
                    final_type = "text"
            elif content_data.shared_item_type in ["knowledge_document", "course_material"]:
                if (hasattr(source_item, 'file_type') and source_item.file_type and source_item.file_type.startswith(
                        'image/')) or \
                        (hasattr(source_item, 'type') and source_item.type == 'image'):
                    final_type = "image"
                elif (hasattr(source_item, 'file_type') and source_item.file_type and source_item.file_type.startswith(
                        'video/')) or \
                        (hasattr(source_item, 'type') and source_item.type == 'video'):
                    final_type = "video"
                elif (hasattr(source_item,
                              'file_type') and source_item.file_type and not source_item.file_type.startswith(
                    'text/plain')) or \
                        (hasattr(source_item, 'type') and source_item.type == 'file'):
                    final_type = "file"  # Fallback to generic_file or document
                elif (hasattr(source_item, 'type') and source_item.type == 'link'):
                    final_type = "link"
                else:  # Fallback for documents content or text material
                    final_type = "document"  # Use 'document' for general documents/text assets
            elif content_data.shared_item_type in ["project", "course", "forum_topic", "note", "daily_record",
                                                   "knowledge_article"]:
                final_type = content_data.shared_item_type  # 例如：type="project", type="course"
            else:
                final_type = "text"  # 兜底，如果没有明确类型，默认文本

        # 对于文件大小和持续时间，优先使用传入的content_data，否则从source_item获取
        if final_file_size is None and hasattr(source_item, 'size_bytes'):
            final_file_size = getattr(source_item, 'size_bytes')
        if final_duration is None and hasattr(source_item, 'duration'):
            final_duration = getattr(source_item, 'duration')
        if final_thumbnail is None:
            final_thumbnail = getattr(source_item, 'thumbnail', None) or getattr(source_item, 'cover_image_url', None)

    else:  # 如果不是共享内部资源，也不是直接上传文件，则使用用户提交的 title, type, url, content
        if final_type is None: final_type = "text"  # 如果没有提供共享项，且未指定类型，默认为文本

    # 如果此时 final_title 依然为空，进行最后兜底
    if not final_title:
        if final_type == "text" and final_content:
            final_title = final_content[:30] + "..." if len(final_content) > 30 else final_content
        elif final_type == "link" and final_url:  # Changed from "url" to "link"
            final_title = final_url
        elif final_type in ["file", "image", "video"] and (uploaded_file_original_filename or content_data.title):
            final_title = uploaded_file_original_filename or content_data.title
        elif content_data.shared_item_type and content_data.shared_item_id:
            final_title = f"{content_data.shared_item_type.capitalize()} #{content_data.shared_item_id}"  # 兜底标题格式
        else:
            final_title = "无标题收藏"

    # 3. 组合文本用于嵌入 (现在使用最终确定的值)
    combined_text_for_embedding = ". ".join(filter(None, [
        _get_text_part(final_title),
        _get_text_part(final_content),
        _get_text_part(final_url),
        _get_text_part(final_tags),
        _get_text_part(final_type),
        _get_text_part(final_author)
    ])).strip()

    embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量

    # 获取当前用户的LLM配置用于嵌入生成
    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    user_llm_api_key = None
    user_llm_type = None
    user_llm_base_url = None
    user_llm_model_id = None

    if current_user_obj.llm_api_type == "siliconflow" and current_user_obj.llm_api_key_encrypted:
        try:
            user_llm_api_key = decrypt_key(current_user_obj.llm_api_key_encrypted)
            user_llm_type = current_user_obj.llm_api_type
            user_llm_base_url = current_user_obj.llm_api_base_url
            # 优先使用新的多模型配置，fallback到原模型ID
            user_llm_model_id = get_user_model_for_provider(
                current_user_obj.llm_model_ids,
                current_user_obj.llm_api_type,
                current_user_obj.llm_model_id
            )
            print(f"DEBUG_EMBEDDING_KEY: 使用收藏创建者配置的硅基流动 API 密钥为收藏内容生成嵌入。")
        except Exception as e:
            print(
                f"WARNING_COLLECTION_EMBEDDING: 解密用户 {current_user_id} LLM API密钥失败: {e}. 收藏内容嵌入将使用零向量或默认行为。")
            user_llm_api_key = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 收藏创建者未配置硅基流动 API 类型或密钥，收藏内容嵌入将使用零向量或默认行为。")

    if combined_text_for_embedding:
        try:
            new_embedding = await get_embeddings_from_api(
                [combined_text_for_embedding],
                api_key=user_llm_api_key,
                llm_type=user_llm_type,
                llm_base_url=user_llm_base_url,
                llm_model_id=user_llm_model_id
            )
            if new_embedding:
                embedding = new_embedding[0]
            print(f"DEBUG: 收藏内容嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成收藏内容嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 收藏内容 combined_text 为空，嵌入向量设为零。")

    # 4. 创建数据库记录
    db_item = CollectedContent(
        owner_id=current_user_id,
        folder_id=final_folder_id,
        title=final_title,
        type=final_type,
        url=final_url,
        content=final_content,
        tags=final_tags,
        priority=content_data.priority,
        notes=content_data.notes,
        is_starred=content_data.is_starred,
        thumbnail=final_thumbnail,
        author=final_author,
        duration=final_duration,
        file_size=final_file_size,
        status=final_status,

        shared_item_type=content_data.shared_item_type,
        shared_item_id=content_data.shared_item_id,

        combined_text=combined_text_for_embedding,
        embedding=embedding
    )

    db.add(db_item)
    try:
        db.commit()
        db.refresh(db_item)
        return db_item
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建收藏内容发生完整性约束错误: {e}")
        # Rollback logic for uploaded file if DB commit fails
        if uploaded_file_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(uploaded_file_object_name))
            print(
                f"DEBUG_COLLECTED_CONTENT: DB commit failed, attempting to delete OSS file: {uploaded_file_object_name}")
        if "_owner_shared_item_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="此内容已被您收藏。")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建收藏内容失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        # Rollback logic for uploaded file if any other error
        if uploaded_file_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(uploaded_file_object_name))
            print(f"DEBUG_COLLECTED_CONTENT: Unknown error, attempting to delete OSS file: {uploaded_file_object_name}")
        print(f"ERROR_DB: 创建收藏内容发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建收藏内容失败: {e}")

# --- 具体收藏内容管理接口 ---
@router.post("/", response_model=schemas.CollectedContentResponse, summary="创建新收藏内容")
async def create_collected_content(
        # Changed to Depends() to allow mixing body (JSON) and file (form-data)
        content_data: schemas.CollectedContentBase = Depends(),
        file: Optional[UploadFile] = File(None, description="可选：上传文件或图片作为收藏内容"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新收藏内容。支持直接创建文本/链接/媒体内容，
    或通过 shared_item_type 和 shared_item_id 收藏平台内部资源。
    如果上传文件，将存储到OSS并保存URL。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试创建收藏。标题: {content_data.title}, 共享类型: {content_data.shared_item_type}, 有文件: {bool(file)}")

    uploaded_file_object_name = None  # For rollback
    uploaded_file_size = None

    # Handle direct file upload to OSS first
    if file:
        if content_data.type not in ["file", "image", "video"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="当上传文件时，收藏类型 (type) 必须为 'file', 'image' 或 'video'。")

        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        content_type = file.content_type
        uploaded_file_size = file.size

        # Determine OSS path prefix based on content type
        oss_path_prefix = "collected_files"
        if content_type.startswith('image/'):
            oss_path_prefix = "collected_images"
        elif content_type.startswith('video/'):
            oss_path_prefix = "collected_videos"

        uploaded_file_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

        try:
            # Upload to OSS
            await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=uploaded_file_object_name,
                content_type=content_type
            )
            print(f"DEBUG_COLLECTED_CONTENT: File '{file.filename}' uploaded to OSS as '{uploaded_file_object_name}'.")

        except HTTPException as e:
            print(f"ERROR_COLLECTED_CONTENT: Upload to OSS failed for {file.filename}: {e.detail}")
            raise e
        except Exception as e:
            print(f"ERROR_COLLECTED_CONTENT: Unknown error during OSS upload for {file.filename}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

        # If file uploaded, the `final_url` will be set by _create_collected_content_item_internal
        # But we need to pass along original filename for _create_collected_content_item_internal to use in title/content

    # 调用内部辅助函数来处理所有业务逻辑
    # Pass uploaded file details to the internal helper
    return await _create_collected_content_item_internal(
        db=db,
        current_user_id=current_user_id,
        content_data=content_data,
        uploaded_file_bytes=file_bytes if file else None,  # Pass bytes only if file exists
        uploaded_file_object_name=uploaded_file_object_name,
        uploaded_file_content_type=file.content_type if file else None,
        uploaded_file_original_filename=file.filename if file else None,
        uploaded_file_size=uploaded_file_size
    )

@router.post("/add-from-platform", response_model=schemas.CollectedContentResponse,
          summary="快速收藏平台内部内容（课程、项目、话题等）")
async def add_platform_item_to_collection(
        request_data: schemas.CollectedContentSharedItemAddRequest,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    用户可以通过这个便捷接口，将平台内的课程、项目、论坛话题、笔记、随手记录、知识库文章或聊天消息等内容，
    快速添加到自己的收藏中。后端将自动提取并填充标题、内容等信息。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试快速收藏平台内容。类型: {request_data.shared_item_type}, ID: {request_data.shared_item_id}")

    # 创建类型映射，将shared_item_type映射到CollectedContentBase允许的type值
    type_mapping = {
        "knowledge_document": None,  # 留空，由后端自动推断为合适的类型（document/image/video/file等）
        "course_material": None,     # 留空，由后端自动推断为合适的类型
        "project": "project",
        "course": "course", 
        "forum_topic": "forum_topic",
        "note": "note",
        "daily_record": "daily_record",
        "knowledge_article": "knowledge_article",
        "chat_message": None  # 留空，由后端自动推断为合适的类型（image/video/link/text等）
    }
    
    # 获取映射后的类型，如果映射结果为None，则让后端自动推断
    mapped_type = type_mapping.get(request_data.shared_item_type, request_data.shared_item_type)

    # 构造一个 CollectedContentBase 对象，只填充 shared_item 相关字段和用户主动提供的可选字段
    # 其他默认字段（如 title, type, url, content, tags, author等）将留空，由 _create_collected_content_item_internal 自动填充。
    collected_content_base_data = schemas.CollectedContentBase(
        title=request_data.title,  # 允许快速收藏时提供一个标题，如果不提供则由后端推断
        type=mapped_type,  # 使用映射后的类型，如果为None则由后端推断
        url=None,  # URL由后端推断
        content=None,  # content由后端推断
        tags=None,  # 标签由后端推断
        priority=None,  # 优先级使用默认
        notes=request_data.notes,  # 备注从请求中获取
        is_starred=request_data.is_starred,  # 星标从请求中获取
        thumbnail=None,  # 缩略图由后端推断
        author=None,  # 作者由后端推断
        duration=None,  # 时长由后端推断
        file_size=None,  # 文件大小由后端推断
        status=None,  # 状态由后端推断

        shared_item_type=request_data.shared_item_type,
        shared_item_id=request_data.shared_item_id,
        folder_id=request_data.folder_id
    )

    # 调用核心辅助函数进行实际的收藏创建
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_base_data)

@router.get("/", response_model=List[schemas.CollectedContentResponse], summary="获取当前用户所有收藏内容")
async def get_all_collected_contents(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        folder_id: Optional[int] = Query(None, description="按文件夹ID过滤。传入0表示顶级文件夹（即folder_id为NULL）"),
        type_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        is_starred: Optional[bool] = None,
        status_filter: Optional[str] = None
):
    """
    获取当前用户的所有收藏内容。
    支持通过文件夹ID、类型、标签、星标状态和内容状态进行过滤。
    如果 folder_id 为 None，则返回所有。传入0视为顶级文件夹（未指定文件夹）。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有收藏内容。文件夹ID: {folder_id}")
    query = db.query(CollectedContent).filter(CollectedContent.owner_id == current_user_id)

    if folder_id is not None:
        if folder_id == 0:  # folder_id=0 表示根目录，即 folder_id 为 None
            query = query.filter(CollectedContent.folder_id.is_(None))
        else:
            query = query.filter(CollectedContent.folder_id == folder_id)
    else:  # 默认不传 folder_id，显示所有
        pass

    if type_filter:
        query = query.filter(CollectedContent.type == type_filter)
    if tag_filter:
        query = query.filter(CollectedContent.tags.ilike(f"%{tag_filter}%"))
    if is_starred is not None:
        query = query.filter(CollectedContent.is_starred == is_starred)
    if status_filter:
        query = query.filter(CollectedContent.status == status_filter)

    contents = query.order_by(CollectedContent.created_at.desc()).all()

    # <<< 新增：填充文件夹名称用于响应 >>>
    # 提前加载所有相关文件夹，避免N+1查询
    folder_ids_in_results = list(set([item.folder_id for item in contents if item.folder_id is not None]))
    folder_map = {f.id: f.name for f in db.query(Folder).filter(Folder.id.in_(folder_ids_in_results)).all()}

    for item in contents:
        if item.folder_id and item.folder_id in folder_map:
            item.folder_name_for_response = folder_map[item.folder_id]
        elif item.folder_id is None:
            item.folder_name_for_response = "未分类"  # 或其他表示根目录的字符串
    # <<< 新增结束 >>>

    print(f"DEBUG: 获取到 {len(contents)} 条收藏内容。")
    return contents

@router.get("/{content_id}", response_model=schemas.CollectedContentResponse, summary="获取指定收藏内容详情")
async def get_collected_content_by_id(
        content_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的收藏内容详情。用户只能获取自己的收藏。
    每次访问会自动增加 access_count。
    """
    print(f"DEBUG: 获取收藏内容 ID: {content_id} 的详情。")
    item = db.query(CollectedContent).filter(CollectedContent.id == content_id,
                                             CollectedContent.owner_id == current_user_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    # 增加访问次数
    item.access_count += 1
    db.add(item)
    db.commit()
    db.refresh(item)

    # <<< 新增：填充文件夹名称用于响应 >>>
    if item.folder_id:
        folder_obj = db.query(Folder).filter(Folder.id == item.folder_id).first()
        if folder_obj:
            item.folder_name_for_response = folder_obj.name
        else:
            item.folder_name_for_response = "未知文件夹"  # 或处理错误情况
    elif item.folder_id is None:
        item.folder_name_for_response = "未分类"  # 或其他表示根目录的字符串
    # <<< 新增结束 >>>

    return item

@router.put("/{content_id}", response_model=schemas.CollectedContentResponse, summary="更新指定收藏内容")
async def update_collected_content(
        content_id: int,
        content_data: schemas.CollectedContentBase = Depends(),  # 使用 Depends 处理 form-data 混合
        file: Optional[UploadFile] = File(None, description="可选：上传新文件或图片替换旧的"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的收藏内容。用户只能更新自己的收藏。
    如果上传新文件，将替换旧文件。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新收藏内容 ID: {content_id}。有文件: {bool(file)}")
    db_item = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not db_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    update_dict = content_data.model_dump(exclude_unset=True) if hasattr(content_data, 'model_dump') else content_data.dict(exclude_unset=True)

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_item.url 中提取旧的 OSS object name
    oss_base_url_parsed = oss_utils.S3_BASE_URL.rstrip('/') + '/'
    if db_item.url and db_item.url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_item.url.replace(oss_base_url_parsed, '', 1)

    # 处理类型变更逻辑
    # 如果传入的 update_dict 包含 'type' 字段，并且类型发生了变化
    type_changed = "type" in update_dict and update_dict["type"] != db_item.type
    new_type_from_data = update_dict.get("type", db_item.type)  # 如果类型没有在update_dict中，沿用旧的类型

    if type_changed:
        # 如果旧类型是文件/图片/视频，需要删除旧的OSS文件
        if db_item.type in ["file", "image", "video"] and old_media_oss_object_name:
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(f"DEBUG_COLLECTED_CONTENT: Deleted old OSS file {old_media_oss_object_name} due to type change.")
            except Exception as e:
                print(
                    f"ERROR_COLLECTED_CONTENT: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during type change: {e}")

        # 清除不适用于新类型的字段
        if new_type_from_data not in ["file", "image", "video"]:  # 如果新类型是非媒体类型
            db_item.url = None
            db_item.file_size = None
            db_item.duration = None
            db_item.thumbnail = None  # 媒体专属字段

        if new_type_from_data == "text":
            # 如果新类型是text，要求 content 字段
            if not update_dict.get('content') and not db_item.content:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'text' 时，'content' 字段为必填。")
            db_item.url = None  # Text type should not have URL

        elif new_type_from_data == "link":
            # 如果新类型是link，要求 url 字段
            if not update_dict.get('url') and not db_item.url:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'link' 时，'url' 字段为必填。")
            # content for links is optional, but if it came from a file, clear it.
            if db_item.type in ["file", "image", "video"]: db_item.content = None

        db_item.type = new_type_from_data  # 更新类型

    # 处理文件上传（如果提供了新文件或新的类型是 file/image/video）
    if file:
        current_type_after_update_check = update_dict.get("type", db_item.type)  # 获取最新材料类型
        if current_type_after_update_check not in ["file", "image", "video"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="只有类型为 'file', 'image' 或 'video' 的收藏才能上传文件。如需更改材料类型，请在content_data中同时指定 type。")

        # 如果旧的OSS文件存在且当前类型是文件/图片/视频，先删除旧文件
        if db_item.type in ["file", "image", "video"] and old_media_oss_object_name:
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(f"DEBUG_COLLECTED_CONTENT: Deleted old OSS file: {old_media_oss_object_name} for replacement.")
            except Exception as e:
                print(
                    f"ERROR_COLLECTED_CONTENT: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during replacement: {e}")

        # 读取新文件内容并上传到OSS
        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        content_type = file.content_type
        uploaded_file_size = file.size

        oss_path_prefix = "collected_files"
        if content_type.startswith('image/'):
            oss_path_prefix = "collected_images"
        elif content_type.startswith('video/'):
            oss_path_prefix = "collected_videos"

        new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

        try:
            db_item.url = await oss_utils.upload_file_to_oss(  # 存储OSS URL
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_item.file_size = uploaded_file_size  # Update file size
            # Update type if it was not already "file" / "image" / "video" but a file was sent
            if db_item.type not in ["file", "image", "video"]:
                if content_type.startswith('image/'):
                    db_item.type = "image"
                elif content_type.startswith('video/'):
                    db_item.type = "video"
                else:
                    db_item.type = "file"
                print(
                    f"DEBUG_COLLECTED_CONTENT: Material type automatically changed to '{db_item.type}' due to file upload.")

            # Clear content if it's a text-based content before but now replaced by file
            if "content" not in update_dict:  # Only clear if content was not explicitly sent or it was a text type
                db_item.content = None

            print(f"DEBUG_COLLECTED_CONTENT: New file '{file.filename}' uploaded to OSS: {db_item.url}")
        except HTTPException as e:
            print(f"ERROR_COLLECTED_CONTENT: Upload new file to OSS failed: {e.detail}")
            raise e
        except Exception as e:
            print(f"ERROR_COLLECTED_CONTENT: Unknown error during new file upload to OSS: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

    # 验证新的文件夹 (如果folder_id被修改)
    if "folder_id" in update_dict and update_dict["folder_id"] is not None:
        new_folder_id = update_dict["folder_id"]
        if new_folder_id == 0:
            setattr(db_item, "folder_id", None)
        else:
            target_folder = db.query(Folder).filter(
                Folder.id == new_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not target_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="Target folder not found or not authorized.")
            setattr(db_item, "folder_id", new_folder_id)
        update_dict.pop("folder_id")  # Remove already handled field
    elif "folder_id" in update_dict and update_dict["folder_id"] is None:
        setattr(db_item, "folder_id", None)
        update_dict.pop("folder_id")  # Remove already handled field

    # 应用其他 update_dict 中的字段
    # Skip fields already handled or fields that should not be updated from here if file was uploaded
    fields_to_skip_after_file_upload = ["type", "url", "file_size", "duration", "thumbnail", "file", "content_text"]
    for key, value in update_dict.items():
        if key in fields_to_skip_after_file_upload:
            continue
        if hasattr(db_item, key) and value is not None:
            setattr(db_item, key, value)
        elif hasattr(db_item,
                     key) and value is None:  # Allow clearing fields (except `title` if it's mandatory non-null)
            if key == "title":  # Title is mandatory, cannot be None or empty
                if not value or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="收藏内容标题不能为空。")
            setattr(db_item, key, value)  # Allow setting to None for optional fields

    # 重新生成 combined_text
    db_item.combined_text = ". ".join(filter(None, [
        _get_text_part(db_item.title),
        _get_text_part(db_item.content),
        _get_text_part(db_item.url),  # Now contains OSS URL for files
        _get_text_part(db_item.tags),
        _get_text_part(db_item.type),
        _get_text_part(db_item.author),
        _get_text_part(db_item.original_filename if hasattr(db_item, 'original_filename') else None),
        # For existing files
        _get_text_part(db_item.file_type if hasattr(db_item, 'file_type') else None),  # For existing files
    ])).strip()

    # 获取当前用户的LLM配置用于嵌入更新
    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    user_llm_api_key = None
    user_llm_type = None
    user_llm_base_url = None
    user_llm_model_id = None

    if current_user_obj and current_user_obj.llm_api_type == "siliconflow" and current_user_obj.llm_api_key_encrypted:
        try:
            user_llm_api_key = decrypt_key(current_user_obj.llm_api_key_encrypted)
            user_llm_type = current_user_obj.llm_api_type
            user_llm_base_url = current_user_obj.llm_api_base_url
            user_llm_model_id = current_user_obj.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用收藏更新者配置的硅基流动 API 密钥更新收藏内容嵌入。")
        except Exception as e:
            print(
                f"WARNING_COLLECTED_CONTENT_EMBEDDING: 解密用户 {current_user_id} LLM API密钥失败: {e}. 收藏内容嵌入将使用零向量。")
            user_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 收藏更新者未配置硅基流动 API 类型或密钥，收藏内容嵌入将使用零向量或默认行为。")

    embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if db_item.combined_text:
        try:
            new_embedding = await get_embeddings_from_api(
                [db_item.combined_text],
                api_key=user_llm_api_key,
                llm_type=user_llm_type,
                llm_base_url=user_llm_base_url,
                llm_model_id=user_llm_model_id
            )
            if new_embedding:
                embedding_recalculated = new_embedding[0]
            print(f"DEBUG: 收藏内容 {db_item.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新收藏内容 {db_item.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 收藏内容 combined_text 为空，嵌入向量设为零。")
        embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db_item.embedding = embedding_recalculated  # 赋值给DB对象

    db.add(db_item)
    try:
        db.commit()
        db.refresh(db_item)
    except IntegrityError as e:
        db.rollback()
        # Rollback logic for newly uploaded file if DB commit fails
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(
                f"DEBUG_COLLECTED_CONTENT: Update DB commit failed, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_DB: 更新收藏内容发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新收藏内容失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        # Rollback logic for newly uploaded file if any other error
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(
                f"DEBUG_COLLECTED_CONTENT: Unknown error during update, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_DB: 更新收藏内容发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新收藏内容失败: {e}")

    print(f"DEBUG: 收藏内容 {db_item.id} 更新成功。")
    return db_item

@router.delete("/{content_id}", summary="删除指定收藏内容")
async def delete_collected_content(
        content_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的收藏内容。用户只能删除自己的收藏。
    如果收藏的内容是文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    """
    print(f"DEBUG: 删除收藏内容 ID: {content_id}。")
    db_item = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not db_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    # 如果是 'file', 'image', 'video' 类型，并且有 OSS URL，则尝试删除 OSS 文件
    if db_item.type in ["file", "image", "video"] and db_item.url:
        oss_base_url_parsed = oss_utils.S3_BASE_URL.rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_item.url.replace(oss_base_url_parsed, '', 1) if db_item.url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_COLLECTED_CONTENT: 删除了OSS文件: {object_name} (For collected content {content_id})")
            except Exception as e:
                print(f"ERROR_COLLECTED_CONTENT: 删除OSS文件 {object_name} 失败: {e}")
                # 这里不抛出异常，即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_COLLECTED_CONTENT: 收藏内容 {content_id} 的 URL ({db_item.url}) 无效或非OSS URL，跳过OSS文件删除。")

    db.delete(db_item)
    db.commit()
    print(f"DEBUG: 收藏内容 {content_id} 删除成功。")
    return {"message": "Collected content deleted successfully"}

# --- 新增：收藏指定平台内容的路由 ---

@router.post("/{project_id}/projects", response_model=schemas.CollectedContentResponse, summary="收藏指定项目")
async def collect_project(
        project_id: int,
        collect_data: schemas.CollectItemRequestBase,  # 使用新的通用请求体
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许用户收藏一个项目。\n
    如果用户没有指定 `folder_id`，系统会自动将收藏放入名为"默认文件夹"的文件夹中。\n
    如果没有"默认文件夹"，系统会先自动创建一个。
    """
    print(f"DEBUG_COLLECT: 用户 {current_user_id} 尝试收藏项目 ID: {project_id}")

    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 构造 CollectedContentBase payload，并填充项目特有的信息
    collected_content_data = schemas.CollectedContentBase(
        title=collect_data.title or db_project.title,  # 优先使用用户自定义标题，否则使用项目标题
        type="project",  # 显式设置为"project"类型
        url=f"{FRONTEND_PROJECT_DETAIL_URL_PREFIX}{project_id}",  # 收藏的URL是前端项目详情页URL
        content=db_project.description,  # 将项目描述作为收藏内容
        tags=db_project.keywords,  # 将项目关键词作为标签
        priority=collect_data.priority,  # 沿用请求中提供的优先级
        notes=collect_data.notes,  # 沿用请求中提供的备注
        is_starred=collect_data.is_starred,  # 沿用请求中提供的星标状态
        thumbnail=None,  # 项目Schema中没有直接的缩略图，可根据实际情况填充
        author=db_project.creator.name if db_project.creator else None,  # 获取项目创建者姓名
        shared_item_type="project",  # 标记为收藏的内部类型
        shared_item_id=project_id,  # 标记为收藏的内部ID
        folder_id=collect_data.folder_id  # 文件夹ID将由 _create_collected_content_item_internal 处理
    )

    # 调用核心辅助函数来创建 CollectedContent 记录
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_data)

@router.post("/{course_id}/courses", response_model=schemas.CollectedContentResponse, summary="收藏指定课程")
async def collect_course(
        course_id: int,
        collect_data: schemas.CollectItemRequestBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许用户收藏一个课程。\n
    如果用户没有指定 `folder_id`，系统会自动将收藏放入名为"默认文件夹"的文件夹中。\n
    如果没有"默认文件夹"，系统会先自动创建一个。
    """
    print(f"DEBUG_COLLECT: 用户 {current_user_id} 尝试收藏课程 ID: {course_id}")

    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 重新解析或处理课程的 skills，因为它们在数据库中是 JSONB 格式
    course_required_skills_text = ""
    if db_course.required_skills:
        try:
            # 尝试从JSON字符串解析，如果已经是列表则直接使用
            parsed_skills = json.loads(db_course.required_skills) if isinstance(db_course.required_skills,
                                                                                str) else db_course.required_skills
            if isinstance(parsed_skills, list):
                course_required_skills_text = ", ".join(
                    [skill.get("name", "") for skill in parsed_skills if isinstance(skill, dict) and skill.get("name")])
        except (json.JSONDecodeError, AttributeError):
            course_required_skills_text = ""  # 解析失败时回退

    # 构造 CollectedContentBase payload，并填充课程特有的信息
    collected_content_data = schemas.CollectedContentBase(
        title=collect_data.title or db_course.title,  # 优先使用用户自定义标题，否则使用课程标题
        type="course",  # 显式设置为"course"类型
        url=f"{FRONTEND_COURSE_DETAIL_URL_PREFIX}{course_id}",  # 收藏的URL是前端课程详情页URL
        content=db_course.description + (
            f" 所需技能: {course_required_skills_text}" if course_required_skills_text else ""),  # 将课程描述和技能作为收藏内容
        tags=db_course.category,  # 将课程分类作为标签
        priority=collect_data.priority,  # 沿用请求中提供的优先级
        notes=collect_data.notes,  # 沿用请求中提供的备注
        is_starred=collect_data.is_starred,  # 沿用请求中提供的星标状态
        thumbnail=db_course.cover_image_url,  # 使用课程封面图片作为缩略图
        author=db_course.instructor,  # 使用讲师作为作者
        shared_item_type="course",  # 标记为收藏的内部类型
        shared_item_id=course_id,  # 标记为收藏的内部ID
        folder_id=collect_data.folder_id  # 文件夹ID将由 _create_collected_content_item_internal 处理
    )

    # 调用核心辅助函数来创建 CollectedContent 记录
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_data)

@router.post("/topics/{topic_id}/forum", response_model=schemas.CollectedContentResponse,
          summary="收藏指定论坛话题")
async def collect_forum_topic(
        topic_id: int,
        collect_data: schemas.CollectItemRequestBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许用户收藏一个论坛话题。\n
    如果用户没有指定 `folder_id`，系统会自动将收藏放入名为"默认文件夹"的文件夹中。\n
    如果没有"默认文件夹"，系统会先自动创建一个。
    """
    print(f"DEBUG_COLLECT: 用户 {current_user_id} 尝试收藏论坛话题 ID: {topic_id}")

    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="论坛话题未找到。")

    # 构造 CollectedContentBase payload，并填充话题特有的信息
    collected_content_data = schemas.CollectedContentBase(
        title=collect_data.title or db_topic.title or "(无标题)",  # 优先使用用户自定义标题，否则使用话题标题，最后用默认标题
        type="forum_topic",  # 显式设置为"forum_topic"类型
        url=f"{FRONTEND_FORUM_TOPIC_DETAIL_URL_PREFIX}{topic_id}",  # 收藏的URL是前端话题详情页URL
        content=db_topic.content,  # 将话题内容作为收藏内容
        tags=db_topic.tags,  # 将话题标签作为标签
        priority=collect_data.priority,  # 沿用请求中提供的优先级
        notes=collect_data.notes,  # 沿用请求中提供的备注
        is_starred=collect_data.is_starred,  # 沿用请求中提供的星标状态
        thumbnail=db_topic.media_url if db_topic.media_type == "image" else None,  # 如果话题是图片则使用其URL作为缩略图
        author=db_topic.owner.name if db_topic.owner else None,  # 获取话题发布者姓名
        shared_item_type="forum_topic",  # 标记为收藏的内部类型
        shared_item_id=topic_id,  # 标记为收藏的内部ID
        folder_id=collect_data.folder_id  # 文件夹ID将由 _create_collected_content_item_internal 处理
    )

    # 调用核心辅助函数来创建 CollectedContent 记录
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_data)

# --- 收藏文件夹管理接口 ---
@router.post("/{content_id}/folders/", response_model=schemas.FolderResponse, summary="在指定收藏中创建新文件夹")
async def create_collection_folder(
        content_id: int,
        folder_data: schemas.FolderBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    在指定收藏内容下创建一个新文件夹。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试在收藏内容 {content_id} 中创建文件夹: {folder_data.name}")

    # 验证收藏内容是否存在且属于当前用户
    collected_content = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not collected_content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="收藏内容未找到或无权访问")

    # 验证父文件夹是否存在且属于当前用户 (如果提供了parent_id)
    if folder_data.parent_id:
        parent_folder = db.query(Folder).filter(
            Folder.id == folder_data.parent_id,
            Folder.owner_id == current_user_id
        ).first()
        if not parent_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="父文件夹未找到或无权访问")

    db_folder = Folder(
        owner_id=current_user_id,
        name=folder_data.name,
        description=folder_data.description,
        color=folder_data.color,
        icon=folder_data.icon,
        parent_id=folder_data.parent_id,
        order=folder_data.order
    )

    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)

    print(f"DEBUG: 文件夹 '{db_folder.name}' (ID: {db_folder.id}) 在收藏内容 {content_id} 中创建成功。")
    return db_folder

@router.get("/{content_id}/folders/", response_model=List[schemas.FolderResponse], summary="获取指定收藏下所有文件夹和软链接内容")
async def get_collection_folders(
        content_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        parent_id: Optional[int] = None  # 过滤条件: 只获取指定父文件夹下的子文件夹
):
    """
    获取指定收藏内容下的所有文件夹。
    可以通过 parent_id 过滤，获取特定父文件夹下的子文件夹。
    """
    print(f"DEBUG: 获取收藏内容 {content_id} 下的文件夹，parent_id过滤: {parent_id}")
    
    # 验证收藏内容是否存在且属于当前用户
    collected_content = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not collected_content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="收藏内容未找到或无权访问")

    query = db.query(Folder).filter(Folder.owner_id == current_user_id)

    if parent_id is not None:  # Note: parent_id can be 0 for root
        query = query.filter(Folder.parent_id == parent_id)
    else:  # 如果 parent_id 没有被显式提供，获取顶级文件夹（parent_id 为 None）
        query = query.filter(Folder.parent_id.is_(None))  # 顶级文件夹 parent_id 为 None

    folders = query.order_by(Folder.order).all()

    # 计算每个文件夹的 item_count (包含的直属 collected_contents 和子文件夹数量)
    for folder in folders:
        folder.item_count = db.query(CollectedContent).filter(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.folder_id == folder.id
        ).count() + db.query(Folder).filter(
            Folder.owner_id == current_user_id,
            Folder.parent_id == folder.id
        ).count()

    print(f"DEBUG: 获取到 {len(folders)} 个文件夹。")
    return folders

@router.get("/{content_id}/folders/{content_folder_id}", response_model=schemas.FolderResponse, summary="获取指定收藏文件夹详情及其内容")
async def get_collection_folder_by_id(
        content_id: int,
        content_folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定收藏内容下的指定文件夹详情。用户只能获取自己的文件夹。
    """
    print(f"DEBUG: 获取收藏内容 {content_id} 下文件夹 ID: {content_folder_id} 的详情。")
    
    # 验证收藏内容是否存在且属于当前用户
    collected_content = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not collected_content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="收藏内容未找到或无权访问")

    folder = db.query(Folder).filter(
        Folder.id == content_folder_id, 
        Folder.owner_id == current_user_id
    ).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹未找到或无权访问")

    # 计算当前文件夹的 item_count
    folder.item_count = db.query(CollectedContent).filter(
        CollectedContent.owner_id == current_user_id,
        CollectedContent.folder_id == folder.id
    ).count() + db.query(Folder).filter(
        Folder.owner_id == current_user_id,
        Folder.parent_id == folder.id
    ).count()

    return folder

@router.put("/{content_id}/folders/{content_folder_id}", response_model=schemas.FolderResponse, summary="更新指定收藏文件夹")
async def update_collection_folder(
        content_id: int,
        content_folder_id: int,
        folder_data: schemas.FolderBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定收藏内容下的指定文件夹信息。用户只能更新自己的文件夹。
    """
    print(f"DEBUG: 更新收藏内容 {content_id} 下文件夹 ID: {content_folder_id} 的信息。")
    
    # 验证收藏内容是否存在且属于当前用户
    collected_content = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not collected_content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="收藏内容未找到或无权访问")

    db_folder = db.query(Folder).filter(
        Folder.id == content_folder_id, 
        Folder.owner_id == current_user_id
    ).first()
    if not db_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹未找到或无权访问")

    update_data = folder_data.model_dump(exclude_unset=True) if hasattr(folder_data, 'model_dump') else folder_data.dict(exclude_unset=True)

    # 验证新的父文件夹 (如果parent_id被修改)
    if "parent_id" in update_data and update_data["parent_id"] is not None:
        new_parent_id = update_data["parent_id"]
        # 不能将自己设为父文件夹
        if new_parent_id == content_folder_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹不能成为自己的父文件夹")
        # 检查新父文件夹是否存在且属于当前用户
        new_parent_folder = db.query(Folder).filter(
            Folder.id == new_parent_id,
            Folder.owner_id == current_user_id
        ).first()
        if not new_parent_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="新父文件夹未找到或无权访问")
        # 检查是否会形成循环 (简单检查，深度循环需要递归检测)
        temp_parent = new_parent_folder
        while temp_parent:
            if temp_parent.id == content_folder_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="检测到循环父子关系")
            temp_parent = temp_parent.parent  # 假设关系已经被正确加载

    for key, value in update_data.items():
        setattr(db_folder, key, value)

    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)

    # 重新计算 item_count
    db_folder.item_count = db.query(CollectedContent).filter(
        CollectedContent.owner_id == current_user_id,
        CollectedContent.folder_id == db_folder.id
    ).count() + db.query(Folder).filter(
        Folder.owner_id == current_user_id,
        Folder.parent_id == db_folder.id
    ).count()

    print(f"DEBUG: 文件夹 {db_folder.id} 更新成功。")
    return db_folder

@router.delete("/{content_id}/folders/{content_folder_id}", summary="删除指定收藏文件夹")
async def delete_collection_folder(
        content_id: int,
        content_folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定收藏内容下的指定文件夹及其包含的所有子文件夹和收藏内容。用户只能删除自己的文件夹。
    """
    print(f"DEBUG: 删除收藏内容 {content_id} 下文件夹 ID: {content_folder_id}。")
    
    # 验证收藏内容是否存在且属于当前用户
    collected_content = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not collected_content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="收藏内容未找到或无权访问")

    db_folder = db.query(Folder).filter(
        Folder.id == content_folder_id, 
        Folder.owner_id == current_user_id
    ).first()
    if not db_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件夹未找到或无权访问")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_folder)时自动处理子文件夹和收藏内容
    db.delete(db_folder)
    db.commit()
    print(f"DEBUG: 文件夹 {content_folder_id} 及其内容删除成功。")
    return {"message": "文件夹及其内容删除成功"}
