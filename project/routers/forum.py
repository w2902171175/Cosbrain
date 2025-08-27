# project/routers/forum.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import os, uuid, asyncio

# 导入数据库和模型
from database import get_db
from models import Student, ForumTopic, ForumLike, ForumComment, UserFollow
from dependencies import get_current_user_id
import schemas
import oss_utils
from utils import (_get_text_part, generate_embedding_safe, populate_user_name, populate_like_status,
                  get_forum_topics_with_details, debug_operation, commit_or_rollback)
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key

# 创建路由器
router = APIRouter(
    prefix="/forum",
    tags=["论坛管理"]
)

@router.post("/topics/", response_model=schemas.ForumTopicResponse, summary="发布新论坛话题")
async def create_forum_topic(
        topic_data: schemas.ForumTopicBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传图片、视频或文件作为话题的附件"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 话题发布者
        db: Session = Depends(get_db)
):
    """
    发布一个新论坛话题。可选择关联分享平台其他内容，或直接上传文件。
    """
    from models import Note, DailyRecord, Course, Project, KnowledgeArticle, CollectedContent
    
    print(f"DEBUG: 用户 {current_user_id} 尝试发布话题: {topic_data.title or '(无标题)'}，有文件：{bool(file)}")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 1. 验证共享内容是否存在 (如果提供了 shared_item_type 和 shared_item_id)
        if topic_data.shared_item_type and topic_data.shared_item_id:
            model = None
            if topic_data.shared_item_type == "note":
                model = Note
            elif topic_data.shared_item_type == "daily_record":
                model = DailyRecord
            elif topic_data.shared_item_type == "course":
                model = Course
            elif topic_data.shared_item_type == "project":
                model = Project
            elif topic_data.shared_item_type == "knowledge_article":
                model = KnowledgeArticle
            elif topic_data.shared_item_type == "collected_content":  # 支持引用收藏
                model = CollectedContent

            if model:
                shared_item = db.query(model).filter(model.id == topic_data.shared_item_id).first()
                if not shared_item:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                        detail=f"Shared item of type {topic_data.shared_item_type} with ID {topic_data.shared_item_id} not found.")

        # 2. 处理文件上传（如果提供了文件）
        final_media_url = topic_data.media_url
        final_media_type = topic_data.media_type
        final_original_filename = topic_data.original_filename
        final_media_size_bytes = topic_data.media_size_bytes

        if file:
            if final_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            # 根据文件类型确定OSS存储路径前缀
            oss_path_prefix = "forum_files"  # 默认文件
            if content_type.startswith('image/'):
                oss_path_prefix = "forum_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "forum_videos"

            current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=content_type
                )
                final_original_filename = file.filename
                final_media_size_bytes = file_size
                # 确保 media_type 与实际上传的文件类型一致
                if content_type.startswith('image/'):
                    final_media_type = "image"
                elif content_type.startswith('video/'):
                    final_media_type = "video"
                else:
                    final_media_type = "file"

                print(f"DEBUG: 文件 '{file.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_media_url}")

            except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
                print(f"ERROR: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出，让FastAPI处理
            except Exception as e:
                print(f"ERROR: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=f"文件上传到云存储失败: {e}")
        else:  # 没有上传文件，但可能提供了 media_url (例如用户粘贴的外部链接)
            # 验证 media_url 和 media_type 的一致性
            if final_media_url and not final_media_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="media_url 存在时，media_type 不能为空。")
            
            # 如果设置了 media_type 但没有 media_url，且没有上传文件，清空 media_type
            if final_media_type and not final_media_url:
                print(f"DEBUG: 检测到设置了 media_type='{final_media_type}' 但没有 media_url 和上传文件，自动清空 media_type")
                final_media_type = None
                final_original_filename = None
                final_media_size_bytes = None

        # 3. 组合文本用于嵌入
        combined_text = ". ".join(filter(None, [
            _get_text_part(topic_data.title),
            _get_text_part(topic_data.content),
            _get_text_part(topic_data.tags),
            _get_text_part(topic_data.shared_item_type),
            _get_text_part(final_media_url),  # 加入媒体URL
            _get_text_part(final_media_type),  # 加入媒体类型
            _get_text_part(final_original_filename),  # 加入原始文件名
        ])).strip()

        # 获取话题发布者的LLM配置用于嵌入生成
        topic_author = db.query(Student).filter(Student.id == current_user_id).first()
        author_llm_api_key = None
        author_llm_type = None
        author_llm_base_url = None
        author_llm_model_id = None

        if topic_author and topic_author.llm_api_type == "siliconflow" and topic_author.llm_api_key_encrypted:
            try:
                author_llm_api_key = decrypt_key(topic_author.llm_api_key_encrypted)
                author_llm_type = topic_author.llm_api_type
                author_llm_base_url = topic_author.llm_api_base_url
                author_llm_model_id = topic_author.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用话题发布者配置的硅基流动 API 密钥为话题生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密话题发布者硅基流动 API 密钥失败: {e}。话题嵌入将使用零向量或默认行为。")
                author_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 话题发布者未配置硅基流动 API 类型或密钥，话题嵌入将使用零向量或默认行为。")

        embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
        if combined_text:
            try:
                new_embedding = await get_embeddings_from_api(
                    [combined_text],
                    api_key=author_llm_api_key,
                    llm_type=author_llm_type,
                    llm_base_url=author_llm_base_url,
                    llm_model_id=author_llm_model_id
                )
                if new_embedding:
                    embedding = new_embedding[0]
                print(f"DEBUG: 话题嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR: 生成话题嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING: 话题 combined_text 为空，嵌入向量设为零。")

        # 4. 创建数据库记录
        db_topic = ForumTopic(
            owner_id=current_user_id,
            title=topic_data.title,
            content=topic_data.content,
            shared_item_type=topic_data.shared_item_type,
            shared_item_id=topic_data.shared_item_id,
            tags=topic_data.tags,
            media_url=final_media_url,  # 保存最终的媒体URL
            media_type=final_media_type,  # 保存最终的媒体类型
            original_filename=final_original_filename,  # 保存原始文件名
            media_size_bytes=final_media_size_bytes,  # 保存文件大小
            combined_text=combined_text,
            embedding=embedding
        )

        db.add(db_topic)
        db.flush()
        print(f"DEBUG_FLUSH: 话题 {db_topic.id} 已刷新到会话。")

        # 发布话题奖励积分
        if topic_author:
            # 导入积分奖励相关函数
            from main import _award_points, _check_and_award_achievements
            topic_post_points = 15
            await _award_points(
                db=db,
                user=topic_author,
                amount=topic_post_points,
                reason=f"发布论坛话题：'{db_topic.title or '(无标题)'}'",
                transaction_type="EARN",
                related_entity_type="forum_topic",
                related_entity_id=db_topic.id
            )
            await _check_and_award_achievements(db, current_user_id)
            print(
                f"DEBUG_POINTS_ACHIEVEMENT: 用户 {current_user_id} 发布话题，获得 {topic_post_points} 积分并检查成就 (待提交)。")

        db.commit()
        db.refresh(db_topic)

        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
        db_topic.owner_name = owner_obj.name if owner_obj else "未知用户"
        db_topic.is_liked_by_current_user = False

        print(f"DEBUG: 话题 '{db_topic.title or '(无标题)'}' (ID: {db_topic.id}) 发布成功，所有事务已提交。")
        return db_topic

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_CREATE_TOPIC_GLOBAL: 创建论坛话题失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建论坛话题失败: {e}",
        )

@router.get("/topics/", response_model=List[schemas.ForumTopicResponse], summary="获取论坛话题列表")
async def get_forum_topics(
        current_user_id: int = Depends(get_current_user_id),  # 用于判断点赞/收藏状态
        db: Session = Depends(get_db),
        query_str: Optional[str] = None,  # 搜索关键词
        tag: Optional[str] = None,  # 标签过滤
        shared_type: Optional[str] = None,  # 分享类型过滤
        limit: int = 10,
        offset: int = 0
):
    """
    获取论坛话题列表，支持关键词、标签和分享类型过滤。
    """
    print(f"DEBUG: 获取论坛话题列表，用户 {current_user_id}，查询: {query_str}")
    query = db.query(ForumTopic)

    if query_str:
        # TODO: 考虑使用语义搜索 instead of LIKE for content search
        query = query.filter(
            (ForumTopic.title.ilike(f"%{query_str}%")) |
            (ForumTopic.content.ilike(f"%{query_str}%"))
        )
    if tag:
        query = query.filter(ForumTopic.tags.ilike(f"%{tag}%"))
    if shared_type:
        query = query.filter(ForumTopic.shared_item_type == shared_type)

    query = query.order_by(ForumTopic.created_at.desc()).offset(offset).limit(limit)

    return await get_forum_topics_with_details(query, current_user_id, db)

@router.get("/topics/{topic_id}", response_model=schemas.ForumTopicResponse, summary="获取指定论坛话题详情")
async def get_forum_topic_by_id(
        topic_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的论坛话题详情。每次访问会增加浏览数。
    """
    print(f"DEBUG: 获取话题 ID: {topic_id} 的详情。")
    topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")

    # 增加浏览数
    topic.views_count += 1
    db.add(topic)
    db.commit()
    db.refresh(topic)

    # 填充 owner_name, is_liked_by_current_user
    owner_obj = db.query(Student).filter(Student.id == topic.owner_id).first()
    topic.owner_name = owner_obj.name if owner_obj else "未知用户"
    topic.is_liked_by_current_user = False
    if current_user_id:
        like = db.query(ForumLike).filter(
            ForumLike.owner_id == current_user_id,
            ForumLike.topic_id == topic.id
        ).first()
        if like:
            topic.is_liked_by_current_user = True

    return topic

@router.put("/topics/{topic_id}", response_model=schemas.ForumTopicResponse, summary="更新指定论坛话题")
async def update_forum_topic(
        topic_id: int,
        topic_data: schemas.ForumTopicBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传新图片、视频或文件替换旧的"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 只有话题发布者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的论坛话题内容。只有话题发布者能更新。
    支持替换附件文件。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新话题 ID: {topic_id}。有文件: {bool(file)}")
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id, ForumTopic.owner_id == current_user_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found or not authorized.")

    update_dict = topic_data.dict(exclude_unset=True)

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_topic.media_url 中提取旧的 OSS object name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_topic.media_url and db_topic.media_url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_topic.media_url.replace(oss_base_url_parsed, '', 1)

    # 1. 处理共享内容和直接上传媒体的互斥校验
    # 这个逻辑在 schema.py 的 model_validator 里已经处理了，但为了健壮性，这里可以再次检查或确保不覆盖。
    # 理论上如果 update_dict 中同时提供了 shared_item_type 和 media_url，会在 schema 验证阶段就抛错。
    # 所以无需再次手动检查互斥性。

    # Check if media_url or media_type are explicitly being cleared or updated to non-file type
    media_url_being_cleared = "media_url" in update_dict and update_dict["media_url"] is None
    media_type_being_cleared_or_changed_to_null = "media_type" in update_dict and update_dict["media_type"] is None

    # Check if type is changing to non-media type from existing media type
    type_changing_from_media = False
    if "media_type" in update_dict and update_dict["media_type"] != db_topic.media_type:
        if db_topic.media_type in ["image", "video", "file"] and update_dict["media_type"] is None:
            type_changing_from_media = True  # 从有媒体类型变为无媒体类型

    # If media content is being explicitly removed or type changed, delete old OSS file
    if old_media_oss_object_name and (
            media_url_being_cleared or media_type_being_cleared_or_changed_to_null or type_changing_from_media):
        try:
            asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
            print(
                f"DEBUG: Deleted old OSS file {old_media_oss_object_name} due to media content clearance/type change.")
        except Exception as e:
            print(
                f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during media content clearance: {e}")

        # 清空数据库中的相关媒体字段
        db_topic.media_url = None
        db_topic.media_type = None
        db_topic.original_filename = None
        db_topic.media_size_bytes = None

    # 2. 处理文件上传（如果提供了新文件或更新了媒体类型）
    if file:
        target_media_type = update_dict.get("media_type")
        if target_media_type not in ["file", "image", "video"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

        # If an old file existed, delete it (already handled by previous block or if new file is replacing it)
        if old_media_oss_object_name and not media_url_being_cleared and not media_type_being_cleared_or_changed_to_null:
            try:
                # If a new file replaces it, schedule old file deletion.
                # Avoids double deletion if old_media_oss_object_name was already handled by clearance logic.
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(f"DEBUG: Deleted old OSS file: {old_media_oss_object_name} for replacement.")
            except Exception as e:
                print(
                    f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during replacement: {e}")

        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        content_type = file.content_type
        file_size = file.size

        oss_path_prefix = "forum_files"
        if content_type.startswith('image/'):
            oss_path_prefix = "forum_images"
        elif content_type.startswith('video/'):
            oss_path_prefix = "forum_videos"

        new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

        try:
            db_topic.media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_topic.original_filename = file.filename
            db_topic.media_size_bytes = file_size
            db_topic.media_type = target_media_type  # Use the media_type from request body

            print(f"DEBUG: New file '{file.filename}' uploaded to OSS: {db_topic.media_url}")
        except HTTPException as e:
            print(f"ERROR: Upload new file to OSS failed: {e.detail}")
            raise e
        except Exception as e:
            print(f"ERROR: Unknown error during new file upload to OSS: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

    # 3. 应用其他 update_dict 中的字段
    # 清理掉已通过文件上传或手动处理的 media 字段，防止再次覆盖
    fields_to_skip_manual_update = ["media_url", "media_type", "original_filename", "media_size_bytes", "file"]
    for key, value in update_dict.items():
        if key in fields_to_skip_manual_update:
            continue
        if hasattr(db_topic, key) and value is not None:
            setattr(db_topic, key, value)
        elif hasattr(db_topic, key) and value is None:  # Allow clearing optional fields (except title)
            if key == "title":  # Title is mandatory, cannot be None or empty
                if not value or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="话题标题不能为空。")
            setattr(db_topic, key, value)

    # 4. 重新生成 combined_text 和 embedding
    combined_text = ". ".join(filter(None, [
        _get_text_part(db_topic.title),
        _get_text_part(db_topic.content),
        _get_text_part(db_topic.tags),
        _get_text_part(db_topic.shared_item_type),
        _get_text_part(db_topic.media_url),  # 包含新的媒体URL
        _get_text_part(db_topic.media_type),  # 包含新的媒体类型
        _get_text_part(db_topic.original_filename),  # 包含原始文件名
    ])).strip()

    topic_author = db.query(Student).filter(Student.id == current_user_id).first()
    author_llm_api_key = None
    author_llm_type = None
    author_llm_base_url = None
    author_llm_model_id = None

    if topic_author and topic_author.llm_api_type == "siliconflow" and topic_author.llm_api_key_encrypted:
        try:
            author_llm_api_key = decrypt_key(topic_author.llm_api_key_encrypted)
            author_llm_type = topic_author.llm_api_type
            author_llm_base_url = topic_author.llm_api_base_url
            author_llm_model_id = topic_author.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用话题发布者配置的硅基流动 API 密钥更新话题嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密话题发布者硅基流动 API 密钥失败: {e}。话题嵌入将使用零向量或默认行为。")
            author_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 话题发布者未配置硅基流动 API 类型或密钥，话题嵌入将使用零向量或默认行为。")

    if combined_text:
        try:
            new_embedding = await get_embeddings_from_api(
                [combined_text],
                api_key=author_llm_api_key,
                llm_type=author_llm_type,
                llm_base_url=author_llm_base_url,
                llm_model_id=author_llm_model_id
            )
            if new_embedding:
                db_topic.embedding = new_embedding[0]
            else:
                db_topic.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
            print(f"DEBUG: 话题 {db_topic.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新话题 {db_topic.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            db_topic.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 话题 combined_text 为空，嵌入向量设为零。")
        db_topic.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db.add(db_topic)
    try:
        db.commit()
        db.refresh(db_topic)
    except Exception as e:
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: Update DB commit failed, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_UPDATE_TOPIC_GLOBAL: 更新话题失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新话题失败: {e}",
        )

    # 填充 owner_name, is_liked_by_current_user
    owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
    db_topic.owner_name = owner_obj.name if owner_obj else "未知用户"
    db_topic.is_liked_by_current_user = False
    if current_user_id:
        like = db.query(ForumLike).filter(
            ForumLike.owner_id == current_user_id,
            ForumLike.topic_id == db_topic.id
        ).first()
        if like:
            db_topic.is_liked_by_current_user = True

    return db_topic

@router.delete("/topics/{topic_id}", summary="删除指定论坛话题")
async def delete_forum_topic(
        topic_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 只有话题发布者能删除
        db: Session = Depends(get_db)
):
    """
    删除指定ID的论坛话题及其所有评论和点赞。如果话题关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    只有话题发布者能删除。
    """
    print(f"DEBUG: 删除话题 ID: {topic_id}。")
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id, ForumTopic.owner_id == current_user_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found or not authorized")

    # <<< 新增：如果话题关联了文件或媒体，并且是OSS URL，则尝试从OSS删除文件 >>>
    if db_topic.media_type in ["image", "video", "file"] and db_topic.media_url:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_topic.media_url.replace(oss_base_url_parsed, '', 1) if db_topic.media_url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_FORUM: 删除了话题 {topic_id} 关联的OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_FORUM: 删除话题 {topic_id} 关联的OSS文件 {object_name} 失败: {e}")
                # 即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_FORUM: 话题 {topic_id} 的 media_url ({db_topic.media_url}) 无效或非OSS URL，跳过OSS文件删除。")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_topic)时自动处理所有评论和点赞
    db.delete(db_topic)
    db.commit()
    print(f"DEBUG: 话题 {topic_id} 及其评论点赞和关联文件删除成功。")
    return {"message": "Forum topic and its comments/likes/associated media deleted successfully"}

# --- 论坛评论管理接口 ---
@router.post("/topics/{topic_id}/comments/", response_model=schemas.ForumCommentResponse,
          summary="为论坛话题添加评论")
async def add_forum_comment(
        topic_id: int,
        comment_data: schemas.ForumCommentBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传图片、视频或文件作为评论的附件"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 评论发布者
        db: Session = Depends(get_db)
):
    """
    为指定论坛话题添加评论。可选择回复某个已有评论（楼中楼），或直接上传文件作为附件。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试为话题 {topic_id} 添加评论。有文件：{bool(file)}")

    # 导入积分奖励相关函数
    from main import _award_points, _check_and_award_achievements

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 1. 验证话题是否存在
        db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
        if not db_topic:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")

        # 2. 验证父评论是否存在 (如果提供了 parent_comment_id)
        if comment_data.parent_comment_id:
            parent_comment = db.query(ForumComment).filter(
                ForumComment.id == comment_data.parent_comment_id,
                ForumComment.topic_id == topic_id  # 确保父评论属于同一话题
            ).first()
            if not parent_comment:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="Parent comment not found in this topic.")

        # 3. 处理文件上传（如果提供了文件）
        final_media_url = comment_data.media_url
        final_media_type = comment_data.media_type
        final_original_filename = comment_data.original_filename
        final_media_size_bytes = comment_data.media_size_bytes

        if file:
            if final_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            # 根据文件类型确定OSS存储路径前缀 (与话题的路径一致，方便管理)
            oss_path_prefix = "forum_files"
            if content_type.startswith('image/'):
                oss_path_prefix = "forum_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "forum_videos"

            current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=content_type
                )
                final_original_filename = file.filename
                final_media_size_bytes = file_size
                # 确保 media_type 与实际上传的文件类型一致
                if content_type.startswith('image/'):
                    final_media_type = "image"
                elif content_type.startswith('video/'):
                    final_media_type = "video"
                else:
                    final_media_type = "file"

                print(f"DEBUG: 文件 '{file.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_media_url}")

            except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
                print(f"ERROR: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出，让FastAPI处理
            except Exception as e:
                print(f"ERROR: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=f"文件上传到云存储失败: {e}")
        else:  # 没有上传文件，但可能提供了 media_url (例如用户粘贴的外部链接)
            # 验证 media_url 和 media_type 的一致性
            if final_media_url and not final_media_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="media_url 存在时，media_type 不能为空。")
            
            # 如果设置了 media_type 但没有 media_url，且没有上传文件，清空 media_type
            if final_media_type and not final_media_url:
                print(f"DEBUG: 检测到设置了 media_type='{final_media_type}' 但没有 media_url 和上传文件，自动清空 media_type")
                final_media_type = None
                final_original_filename = None
                final_media_size_bytes = None

        # 4. 创建评论记录
        db_comment = ForumComment(
            topic_id=topic_id,
            owner_id=current_user_id,
            content=comment_data.content,
            parent_comment_id=comment_data.parent_comment_id,
            media_url=final_media_url,  # 保存最终的媒体URL
            media_type=final_media_type,  # 保存最终的媒体类型
            original_filename=final_original_filename,  # 保存原始文件名
            media_size_bytes=final_media_size_bytes  # 保存文件大小
        )

        db.add(db_comment)
        # 更新话题的评论数 (这是一个在会话中修改的操作，等待最终提交)
        db_topic.comments_count += 1
        db.add(db_topic)  # SQLAlchemy会自动识别这是更新

        # 在检查成就前，强制刷新会话，使 db_comment 和 db_topic 对查询可见！
        db.flush()
        print(f"DEBUG_FLUSH: 评论 {db_comment.id} 和话题 {db_topic.id} 更新已刷新到会话。")

        # 发布评论奖励积分
        comment_author = db.query(Student).filter(Student.id == current_user_id).first()
        if comment_author:
            comment_post_points = 5
            await _award_points(
                db=db,
                user=comment_author,
                amount=comment_post_points,
                reason=f"发布论坛评论：'{db_comment.content[:20]}...'",
                transaction_type="EARN",
                related_entity_type="forum_comment",
                related_entity_id=db_comment.id
            )
            await _check_and_award_achievements(db, current_user_id)
            print(
                f"DEBUG_POINTS_ACHIEVEMENT: 用户 {current_user_id} 发布评论，获得 {comment_post_points} 积分并检查成就 (待提交)。")

        db.commit()  # 现在，这里是唯一也是最终的提交！
        db.refresh(db_comment)  # 提交后刷新db_comment以返回完整对象

        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
        db_comment.owner_name = owner_obj.name  # 访问私有属性以设置
        db_comment.is_liked_by_current_user = False

        print(f"DEBUG: 话题 {db_topic.id} 收到评论 (ID: {db_comment.id})，所有事务已提交。")
        return db_comment

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:  # 捕获所有异常并回滚
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_ADD_COMMENT_GLOBAL: 添加论坛评论失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加论坛评论失败: {e}",
        )

@router.get("/topics/{topic_id}/comments/", response_model=List[schemas.ForumCommentResponse],
         summary="获取论坛话题的评论列表")
async def get_forum_comments(
        topic_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        parent_comment_id: Optional[int] = None,  # 过滤条件: 只获取指定父评论下的子评论 (实现楼中楼)
        limit: int = 50,  # 限制返回消息数量
        offset: int = 0  # 偏移量，用于分页加载
):
    """
    获取指定论坛话题的评论列表。
    可以过滤以获取特定评论的回复（楼中楼）。
    """
    print(f"DEBUG: 获取话题 {topic_id} 的评论，用户 {current_user_id}，父评论ID: {parent_comment_id}。")

    # 验证话题是否存在
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")

    query = db.query(ForumComment).filter(ForumComment.topic_id == topic_id)

    if parent_comment_id is not None:
        query = query.filter(ForumComment.parent_comment_id == parent_comment_id)
    else:  # 默认获取一级评论 (parent_comment_id 为 None)
        query = query.filter(ForumComment.parent_comment_id.is_(None))

    comments = query.order_by(ForumComment.created_at.asc()).offset(offset).limit(limit).all()

    response_comments = []
    for comment in comments:
        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == comment.owner_id).first()
        comment._owner_name = owner_obj.name if owner_obj else "未知用户"

        # 填充 is_liked_by_current_user
        comment.is_liked_by_current_user = False
        if current_user_id:
            like = db.query(ForumLike).filter(
                ForumLike.owner_id == current_user_id,
                ForumLike.comment_id == comment.id
            ).first()
            if like:
                comment.is_liked_by_current_user = True

        response_comments.append(comment)

    print(f"DEBUG: 话题 {topic_id} 获取到 {len(comments)} 条评论。")
    return response_comments

@router.put("/comments/{comment_id}", response_model=schemas.ForumCommentResponse, summary="更新指定论坛评论")
async def update_forum_comment(
        comment_id: int,
        comment_data: schemas.ForumCommentBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传新图片、视频或文件替换旧的"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 只有评论发布者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的论坛评论。只有评论发布者能更新。
    支持替换附件文件。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新评论 ID: {comment_id}。有文件: {bool(file)}")
    db_comment = db.query(ForumComment).filter(ForumComment.id == comment_id,
                                               ForumComment.owner_id == current_user_id).first()
    if not db_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found or not authorized.")

    update_dict = comment_data.dict(exclude_unset=True)

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_comment.media_url 中提取旧的 OSS object name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_comment.media_url and db_comment.media_url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_comment.media_url.replace(oss_base_url_parsed, '', 1)

    try:
        # Check if media_url or media_type are explicitly being cleared or updated to non-media type
        media_url_being_cleared = "media_url" in update_dict and update_dict["media_url"] is None
        media_type_being_set = "media_type" in update_dict
        new_media_type_from_data = update_dict.get("media_type")

        # If old media existed and it's explicitly being cleared, or type changes away from media
        should_delete_old_media_file = False
        if old_media_oss_object_name:
            if media_url_being_cleared:  # media_url is set to None
                should_delete_old_media_file = True
            elif media_type_being_set and new_media_type_from_data is None:  # media_type is set to None
                should_delete_old_media_file = True
            elif media_type_being_set and (
                    new_media_type_from_data not in ["image", "video", "file"]):  # media_type changes to non-media
                should_delete_old_media_file = True

        if should_delete_old_media_file:
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(
                    f"DEBUG: Deleted old OSS file {old_media_oss_object_name} due to media content clearance/type change.")
            except Exception as e:
                print(
                    f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during media content clearance: {e}")

            # 清空数据库中的相关媒体字段
            db_comment.media_url = None
            db_comment.media_type = None
            db_comment.original_filename = None
            db_comment.media_size_bytes = None

        # 1. 处理文件上传（如果提供了新文件）
        if file:
            target_media_type = update_dict.get("media_type")
            if target_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            # 如果新文件替换了现有文件，且现有文件是OSS上的，则删除它
            if old_media_oss_object_name and not should_delete_old_media_file:  # Avoid double deletion
                try:
                    asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                    print(f"DEBUG: Deleted old OSS file: {old_media_oss_object_name} for replacement.")
                except Exception as e:
                    print(
                        f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during replacement: {e}")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            oss_path_prefix = "forum_files"
            if content_type.startswith('image/'):
                oss_path_prefix = "forum_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "forum_videos"

            new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

            # Upload to OSS
            db_comment.media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_comment.original_filename = file.filename
            db_comment.media_size_bytes = file_size
            db_comment.media_type = target_media_type  # Use the media_type from request body

            print(f"DEBUG: New file '{file.filename}' uploaded to OSS: {db_comment.media_url}")

            # Clear text content if this is a file-only comment and content was not provided in update
            if "content" not in update_dict and db_comment.content:
                db_comment.content = None  # If updating with a file, clear existing text content if user didn't specify new text
        elif "media_url" in update_dict and update_dict[
            "media_url"] is not None and not file:  # User provided a new URL but no file
            # If new media_url is provided without a file, it's assumed to be an external URL
            db_comment.media_url = update_dict["media_url"]
            db_comment.media_type = update_dict.get("media_type")  # Should be provided via schema validator
            db_comment.original_filename = None
            db_comment.media_size_bytes = None
            # content is optional in this case

        # 2. 应用其他 update_dict 中的字段
        # 清理掉已通过文件上传或手动处理的 media 字段，防止再次覆盖
        fields_to_skip_manual_update = ["media_url", "media_type", "original_filename", "media_size_bytes", "file"]
        for key, value in update_dict.items():
            if key in fields_to_skip_manual_update:
                continue
            if hasattr(db_comment, key):
                if key == "content":  # Content is mandatory for text-based comments
                    if value is None or (isinstance(value, str) and not value.strip()):
                        # Only raise error if it's a text-based comment. For media-only, content can be null.
                        if db_comment.media_url is None:  # If no media, content must be there
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="评论内容不能为空。")
                        else:  # If there's media, content can be cleared
                            setattr(db_comment, key, value)
                    else:  # Content value is not None/empty
                        setattr(db_comment, key, value)
                elif key == "parent_comment_id":  # Cannot change parent_comment_id
                    if value != db_comment.parent_comment_id:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                            detail="Cannot change parent_comment_id of a comment.")
                else:  # For other fields
                    setattr(db_comment, key, value)

        db.add(db_comment)
        db.commit()
        db.refresh(db_comment)

        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
        db_comment.owner_name = owner_obj.name
        db_comment.is_liked_by_current_user = False  # 更新不会像状态一样更改

        print(f"DEBUG: 评论 {db_comment.id} 更新成功。")
        return db_comment

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: HTTP exception, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        raise e
    except Exception as e:
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(
                f"DEBUG: Unknown error during update, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_UPDATE_COMMENT_GLOBAL: 更新评论失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新评论失败: {e}",
        )

@router.delete("/comments/{comment_id}", summary="删除指定论坛评论")
async def delete_forum_comment(
        comment_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 只有评论发布者能删除
        db: Session = Depends(get_db)
):
    """
    删除指定ID的论坛评论。如果评论有子评论，则会级联删除所有回复。
    如果评论关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    只有评论发布者能删除。
    """
    print(f"DEBUG: 删除评论 ID: {comment_id}。")
    db_comment = db.query(ForumComment).filter(ForumComment.id == comment_id,
                                               ForumComment.owner_id == current_user_id).first()
    if not db_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found or not authorized")

    # 获取所属话题以便更新 comments_count
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == db_comment.topic_id).first()
    if db_topic:
        # 评论数减少的逻辑应该在实际删除完评论后进行，并且需要考虑级联删除子评论的情况
        # 但在简单的计数器场景下，这里先进行初步减一，或者在钩子中处理会更好。
        # 这里仅为直接评论减一，子评论的删除不会反映在这里。
        db_topic.comments_count -= 1
        db.add(db_topic)

    # <<< 新增：如果评论关联了文件或媒体，并且是OSS URL，则尝试从OSS删除文件 >>>
    if db_comment.media_type in ["image", "video", "file"] and db_comment.media_url:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_comment.media_url.replace(oss_base_url_parsed, '', 1) if db_comment.media_url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_FORUM: 删除了评论 {comment_id} 关联的OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_FORUM: 删除评论 {comment_id} 关联的OSS文件 {object_name} 失败: {e}")
                # 即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_FORUM: 评论 {comment_id} 的 media_url ({db_comment.media_url}) 无效或非OSS URL，跳过OSS文件删除。")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_comment)时自动处理所有子评论和点赞
    db.delete(db_comment)
    db.commit()
    print(f"DEBUG: 评论 {comment_id} 及其子评论点赞和关联文件删除成功。")
    return {"message": "Forum comment and its children/likes/associated media deleted successfully"}

# --- 论坛点赞管理接口 ---
@router.post("/likes/", response_model=schemas.ForumLikeResponse, summary="点赞论坛话题或评论")
async def like_forum_item(
        like_data: Dict[str, Any],  # 接收 topic_id 或 comment_id
        current_user_id: int = Depends(get_current_user_id),  # 点赞者
        db: Session = Depends(get_db)
):
    """
    点赞一个论坛话题或评论。
    必须提供 topic_id 或 comment_id 中的一个。同一用户不能重复点赞同一项。
    点赞成功后，为被点赞的话题/评论的作者奖励积分，并检查其成就。
    """
    # 导入积分奖励相关函数
    from main import _award_points, _check_and_award_achievements
    
    print(f"DEBUG: 用户 {current_user_id} 尝试点赞。")
    try:  # 将整个接口逻辑包裹在一个 try 块中，统一提交
        topic_id = like_data.get("topic_id")
        comment_id = like_data.get("comment_id")

        if not topic_id and not comment_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Either topic_id or comment_id must be provided.")
        if topic_id and comment_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Only one of topic_id or comment_id can be provided.")

        existing_like = None
        target_item_owner_id = None
        related_entity_type = None
        related_entity_id = None

        if topic_id:
            existing_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                                       ForumLike.topic_id == topic_id).first()
            if not existing_like:
                target_item = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
                if not target_item:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")
                target_item.likes_count += 1
                db.add(target_item)  # 在会话中更新点赞数
                target_item_owner_id = target_item.owner_id  # 获取话题作者ID
                related_entity_type = "forum_topic"
                related_entity_id = topic_id
        elif comment_id:
            existing_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                                       ForumLike.comment_id == comment_id).first()
            if not existing_like:
                target_item = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
                if not target_item:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found.")
                target_item.likes_count += 1
                db.add(target_item)  # 在会话中更新点赞数
                target_item_owner_id = target_item.owner_id  # 获取评论作者ID
                related_entity_type = "forum_comment"
                related_entity_id = comment_id

        if existing_like:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already liked this item.")

        db_like = ForumLike(
            owner_id=current_user_id,
            topic_id=topic_id,
            comment_id=comment_id
        )

        db.add(db_like)  # 将点赞记录添加到会话

        # 在检查成就前，强制刷新会话，使 db_like 和 target_item 对查询可见
        db.flush()  # 确保点赞记录和被点赞项的更新已刷新到数据库会话，供 _check_and_award_achievements 查询
        print(f"DEBUG_FLUSH: 点赞记录 {db_like.id} 和被点赞项更新已刷新到会话。")

        # 为被点赞的作者奖励积分和检查成就
        if target_item_owner_id and target_item_owner_id != current_user_id:  # 奖励积分，但不能点赞自己给自己加分
            owner_user = db.query(Student).filter(Student.id == target_item_owner_id).first()
            if owner_user:
                like_points = 5
                await _award_points(
                    db=db,
                    user=owner_user,
                    amount=like_points,
                    reason=f"获得点赞：{target_item.title if topic_id else target_item.content[:20]}...",
                    transaction_type="EARN",
                    related_entity_type=related_entity_type,
                    related_entity_id=related_entity_id
                )
                await _check_and_award_achievements(db, target_item_owner_id)
                print(
                    f"DEBUG_POINTS_ACHIEVEMENT: 用户 {target_item_owner_id} 因获得点赞奖励 {like_points} 积分并检查成就 (待提交)。")

        db.commit()  # 这里是唯一也是最终的提交
        db.refresh(db_like)  # 提交后刷新db_like以返回完整对象

        print(
            f"DEBUG: 用户 {current_user_id} 点赞成功 (Topic ID: {topic_id or 'N/A'}, Comment ID: {comment_id or 'N/A'})。所有事务已提交。")
        return db_like

    except Exception as e:  # 捕获所有异常并回滚
        db.rollback()
        print(f"ERROR_LIKE_FORUM_GLOBAL: 点赞失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"点赞失败: {e}",
        )

@router.delete("/likes/", summary="取消点赞论坛话题或评论")
async def unlike_forum_item(
        unlike_data: Dict[str, Any],  # 接收 topic_id 或 comment_id
        current_user_id: int = Depends(get_current_user_id),  # 取消点赞者
        db: Session = Depends(get_db)
):
    """
    取消点赞一个论坛话题或评论。
    必须提供 topic_id 或 comment_id 中的一个。
    """
    topic_id = unlike_data.get("topic_id")
    comment_id = unlike_data.get("comment_id")

    if not topic_id and not comment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Either topic_id or comment_id must be provided.")
    if topic_id and comment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only one of topic_id or comment_id can be provided.")

    db_like = None
    if topic_id:
        db_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                             ForumLike.topic_id == topic_id).first()
        if db_like:
            target_item = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
            if target_item and target_item.likes_count > 0:
                target_item.likes_count -= 1
                db.add(target_item)
    elif comment_id:
        db_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                             ForumLike.comment_id == comment_id).first()
        if db_like:
            target_item = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
            if target_item and target_item.likes_count > 0:
                target_item.likes_count -= 1
                db.add(target_item)

    if not db_like:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Like not found for this item by current user.")

    db.delete(db_like)
    db.commit()
    print(
        f"DEBUG: 用户 {current_user_id} 取消点赞成功 (Topic ID: {topic_id or 'N/A'}, Comment ID: {comment_id or 'N/A'})。")
    return {"message": "Like removed successfully"}

# --- 论坛用户关注管理接口 ---
@router.post("/follow/", response_model=schemas.UserFollowResponse, summary="关注一个用户")
async def follow_user(
        follow_data: Dict[str, Any],  # 接收 followed_id
        current_user_id: int = Depends(get_current_user_id),  # 关注者
        db: Session = Depends(get_db)
):
    """
    允许当前用户关注另一个用户。
    """
    followed_id = follow_data.get("followed_id")
    if not followed_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="followed_id must be provided.")

    if followed_id == current_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself.")

    # 验证被关注用户是否存在
    followed_user = db.query(Student).filter(Student.id == followed_id).first()
    if not followed_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to follow not found.")

    # 检查是否已关注
    existing_follow = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user_id,
        UserFollow.followed_id == followed_id
    ).first()
    if existing_follow:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following this user.")

    db_follow = UserFollow(
        follower_id=current_user_id,
        followed_id=followed_id
    )

    db.add(db_follow)
    db.commit()
    db.refresh(db_follow)
    print(f"DEBUG: 用户 {current_user_id} 关注用户 {followed_id} 成功。")
    return db_follow

@router.delete("/unfollow/", summary="取消关注一个用户")
async def unfollow_user(
        unfollow_data: Dict[str, Any],  # 接收 followed_id
        current_user_id: int = Depends(get_current_user_id),  # 取消关注者
        db: Session = Depends(get_db)
):
    """
    允许当前用户取消关注另一个用户。
    """
    followed_id = unfollow_data.get("followed_id")
    if not followed_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="followed_id must be provided.")

    db_follow = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user_id,
        UserFollow.followed_id == followed_id
    ).first()
    if not db_follow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not currently following this user.")

    db.delete(db_follow)
    db.commit()
    print(f"DEBUG: 用户 {current_user_id} 取消关注用户 {followed_id} 成功。")
    return {"message": "Unfollowed successfully"}
