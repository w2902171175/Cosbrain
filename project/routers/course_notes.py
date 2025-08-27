# project/routers/course_notes.py
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional, Any
from datetime import datetime
import json, os, uuid, asyncio

# 导入数据库和模型
from database import get_db
from models import Note, Course, Folder, Student
from dependencies import get_current_user_id
from utils import _get_text_part
import schemas, oss_utils
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key

# 创建路由器
router = APIRouter(
    prefix="/notes",
    tags=["课程笔记"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.NoteResponse, summary="创建新笔记")

@router.post("/", response_model=schemas.NoteResponse, summary="创建新笔记")
async def create_note(
        note_data: schemas.NoteBase,  # 对于JSON请求
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新笔记（纯JSON请求，不支持文件上传）。
    支持关联课程章节信息或用户自定义文件夹。
    如需上传文件，请使用 /notes/with-file/ 端点。
    """
    return await _create_note_internal(note_data, None, current_user_id, db)

@router.post("/with-file/", response_model=schemas.NoteResponse, summary="创建带文件的新笔记")
async def create_note_with_file(
        note_data_json: str = Form(..., description="笔记数据，JSON字符串格式"),
        file: UploadFile = File(..., description="上传图片、视频或文件作为笔记的附件"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新笔记（支持文件上传）。
    使用multipart/form-data格式，笔记数据通过JSON字符串传递。
    """
    # 解析JSON数据
    try:
        note_data_dict = json.loads(note_data_json)
        note_data = schemas.NoteBase(**note_data_dict)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的JSON格式: {e}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"数据验证失败: {e}"
        )
    
    return await _create_note_internal(note_data, file, current_user_id, db)

async def _create_note_internal(
        note_data: schemas.NoteBase,
        file: Optional[UploadFile],
        current_user_id: int,
        db: Session
):
    """
    创建笔记的内部实现
    """
    # 验证标题：标题是必需的，不能为空
    if note_data.title is None or (isinstance(note_data.title, str) and not note_data.title.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="笔记标题不能为空。"
        )
    
    print(
        f"DEBUG: 用户 {current_user_id} 尝试创建笔记。标题: {note_data.title}，有文件：{bool(file)}，文件夹ID：{note_data.folder_id}，课程ID：{note_data.course_id}")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 0. 验证关联关系的存在和权限：课程/章节 或 文件夹
        if note_data.course_id:
            db_course = db.query(Course).filter(Course.id == note_data.course_id).first()
            if not db_course:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的课程不存在。")

        if note_data.folder_id is not None:  # 如果指定了文件夹ID (0 已经被 schema 转换为 None)
            target_folder = db.query(Folder).filter(
                Folder.id == note_data.folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not target_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="目标文件夹未找到或无权访问。")

        # 1. 处理文件上传（如果提供了文件）
        final_media_url = note_data.media_url
        final_media_type = note_data.media_type
        final_original_filename = note_data.original_filename
        final_media_size_bytes = note_data.media_size_bytes

        if file:
            if final_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            # 根据文件类型确定OSS存储路径前缀
            oss_path_prefix = "note_files"  # 默认文件
            if content_type.startswith('image/'):
                oss_path_prefix = "note_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "note_videos"

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
            # 验证 media_url 和 media_type 的一致性 (由 schema 校验，这里不重复，但假设通过)
            pass

        # 1.5. 验证笔记内容完整性 - 在文件处理之后进行
        # 检查是否有有效的文本内容（非空且非纯空白字符）
        has_valid_content = note_data.content and note_data.content.strip()
        has_media_file = final_media_url is not None
        
        if not has_valid_content and not has_media_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="笔记内容 (content) 和媒体文件 (media_url) 至少需要提供一个。"
            )

        # 2. 组合文本用于嵌入
        # 根据是课程笔记还是文件夹笔记，调整combined_text内容
        context_identifier = ""
        if note_data.course_id:
            course_title = db_course.title if db_course else f"课程 {note_data.course_id}"
            context_identifier = f"课程: {course_title}. 章节: {note_data.chapter or '未指定'}."
        elif note_data.folder_id is not None:
            folder_name = target_folder.name if target_folder else f"文件夹 {note_data.folder_id}"
            context_identifier = f"文件夹: {folder_name}."

        combined_text = ". ".join(filter(None, [
            _get_text_part(note_data.title),
            _get_text_part(note_data.content),
            _get_text_part(note_data.tags),
            _get_text_part(context_identifier),  # 包含课程/文件夹上下文
            _get_text_part(final_media_url),  # 包含媒体URL
            _get_text_part(final_media_type),  # 包含媒体类型
            _get_text_part(final_original_filename),  # 包含原始文件名
        ])).strip()
        if not combined_text:
            combined_text = ""

        embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量

        # 获取当前用户的LLM配置用于嵌入生成
        note_owner = db.query(Student).filter(Student.id == current_user_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if note_owner and note_owner.llm_api_type == "siliconflow" and note_owner.llm_api_key_encrypted:
            try:
                owner_llm_api_key = decrypt_key(note_owner.llm_api_key_encrypted)
                owner_llm_type = note_owner.llm_api_type
                owner_llm_base_url = note_owner.llm_api_base_url
                owner_llm_model_id = note_owner.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用笔记创建者配置的硅基流动 API 密钥为笔记生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密笔记创建者硅基流动 API 密钥失败: {e}。笔记嵌入将使用零向量。")
                owner_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 笔记创建者未配置硅基流动 API 类型或密钥，笔记嵌入将使用零向量或默认行为。")

        if combined_text:
            try:
                new_embedding = await get_embeddings_from_api(
                    [combined_text],
                    api_key=owner_llm_api_key,
                    llm_type=owner_llm_type,
                    llm_base_url=owner_llm_base_url,
                    llm_model_id=owner_llm_model_id
                )
                if new_embedding:
                    embedding = new_embedding[0]
                else:
                    embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保为零向量
                print(f"DEBUG: 笔记嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR: 生成笔记嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING_EMBEDDING: 笔记 combined_text 为空，嵌入向量设为零。")

        # 3. 创建数据库记录
        db_note = Note(
            owner_id=current_user_id,
            title=note_data.title,
            content=note_data.content,
            note_type=note_data.note_type,
            course_id=note_data.course_id,  # 存储课程ID
            tags=note_data.tags,
            chapter=note_data.chapter,  # 存储章节信息
            media_url=final_media_url,  # 存储最终的媒体URL
            media_type=final_media_type,  # 存储最终的媒体类型
            original_filename=final_original_filename,  # 存储原始文件名
            media_size_bytes=final_media_size_bytes,  # 存储文件大小
            folder_id=note_data.folder_id,  # <<< 存储文件夹ID
            combined_text=combined_text,
            embedding=embedding
        )

        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        print(f"DEBUG: 笔记 (ID: {db_note.id}) 创建成功。")
        return db_note

    except HTTPException as e:  # 捕获FastAPI异常，包括OSS上传时抛出的
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
        print(f"ERROR_CREATE_NOTE_GLOBAL: 创建笔记失败，事务已回滚: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建笔记失败: {e}")

@router.get("/", response_model=List[schemas.NoteResponse], summary="获取当前用户所有笔记")
async def get_all_notes(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        note_type: Optional[str] = None,
        course_id: Optional[int] = Query(None, description="按课程ID过滤笔记"),  # 新增课程ID过滤
        chapter: Optional[str] = Query(None, description="按章节名称过滤笔记"),  # 新增章节过滤
        folder_id: Optional[int] = Query(None,
                                         description="按自定义文件夹ID过滤笔记。传入0表示顶级文件夹（即folder_id为NULL）"),
        # 新增文件夹ID过滤
        tags: Optional[str] = Query(None, description="按标签过滤，支持模糊匹配"),  # 标签过滤 (从原有的tag改为tags)
        # Note: 原来的 tag 参数名改为 tags，与 Note 模型字段名保持一致，更清晰。
        limit: int = Query(100, description="返回的最大笔记数量"),  # 新增 limit/offset
        offset: int = Query(0, description="查询的偏移量")  # 新增 limit/offset

):
    """
    获取当前用户的所有笔记。
    可以按笔记类型 (note_type)，关联的课程ID (course_id)，章节 (chapter)，自定义文件夹ID (folder_id)，或标签 (tags) 进行过滤。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有笔记。")
    print(
        f"DEBUG_NOTE_QUERY: note_type={note_type}, course_id={course_id}, chapter={chapter}, folder_id={folder_id}, tags={tags}")

    query = db.query(Note).filter(Note.owner_id == current_user_id)

    # 过滤条件优先级或互斥性检查：
    # 根据 NoteBase 的验证逻辑，笔记不能同时属于课程/章节和自定义文件夹。
    # 因此，查询时也应保持这种互斥性。

    if folder_id is not None:  # 如果指定了 folder_id (包括 0，表示顶级文件夹)
        if course_id is not None or (chapter is not None and chapter.strip() != ""):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="无法同时按课程/章节和自定义文件夹ID过滤笔记。请选择一种方式。")
        if folder_id == 0:  # 0 表示顶级文件夹，即 folder_id 为 NULL
            query = query.filter(Note.folder_id.is_(None))
        else:
            query = query.filter(Note.folder_id == folder_id)
    elif course_id is not None:  # 如果没有指定 folder_id，但指定了 course_id
        query = query.filter(Note.course_id == course_id)
        if chapter is not None and chapter.strip() != "":
            query = query.filter(Note.chapter == chapter)
    elif chapter is not None and chapter.strip() != "":  # 如果只指定了 chapter 但没有 course_id
        # 按照 schemas.py 的验证，没有 course_id 的 chapter 是非法的，但这里可以做一个柔性处理或额外提示
        # 不过为了严格性，如果仅有 chapter 没有 course_id 则不进行过滤或报错
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="若要按章节过滤，必须同时提供课程ID (course_id)。")
    else:  # 默认情况：不按课程/章节也不按文件夹过滤，获取所有非课程非文件夹的笔记，或者所有笔记
        # 如果没有指定任何组织方式的过滤，可以默认显示所有非课程非文件夹的笔记，或者所有笔记。
        # 这里选择默认不加folder_id和course_id的过滤，即显示所有无关联的笔记，或者根据其他过滤器显示。
        # 如果需要显示所有笔记，则此处不加任何 folder_id 或 chapter/course_id 相关的 filter
        pass

    if note_type:
        query = query.filter(Note.note_type == note_type)

    if tags:  # 修改了原来 tag 变量名
        # 使用 LIKE 进行模糊匹配，因为标签是逗号分隔字符串
        query = query.filter(Note.tags.ilike(f"%{tags}%"))

    # 应用排序和分页
    notes = query.order_by(Note.created_at.desc()).offset(offset).limit(limit).all()

    # Optional: Fill folder name and course name for response based on IDs for better display
    for note in notes:
        # 如果 note 有 folder_id，加载文件夹名称
        if note.folder_id:
            # 假定 Folder model 有 name 属性
            folder_obj = db.query(Folder).filter(Folder.id == note.folder_id).first()
            if folder_obj:
                note.folder_name_for_response = folder_obj.name  # Assign to a temporary or @property in schema
        # 如果 note 有 course_id，加载课程名称
        if note.course_id:
            course_obj = db.query(Course).filter(Course.id == note.course_id).first()
            if course_obj:
                note.course_title_for_response = course_obj.title  # Assign to a temporary or @property in schema

    print(f"DEBUG: 获取到 {len(notes)} 条笔记。")
    return notes

@router.get("/{note_id}", response_model=schemas.NoteResponse, summary="获取指定笔记详情")
async def get_note_by_id(
        note_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取笔记 ID: {note_id} 的详情。")
    note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")

    # 填充文件夹名称和课程标题用于响应
    # 如果笔记有 folder_id，加载文件夹名称
    if note.folder_id:
        folder_obj = db.query(Folder).filter(Folder.id == note.folder_id).first()
        if folder_obj:
            note.folder_name_for_response = folder_obj.name

    # 如果笔记有 course_id，加载课程名称
    if note.course_id:
        course_obj = db.query(Course).filter(Course.id == note.course_id).first()
        if course_obj:
            note.course_title_for_response = course_obj.title

    return note

@router.put("/{note_id}", response_model=schemas.NoteResponse, summary="更新指定笔记")
async def update_note(
        note_id: int,
        note_data: schemas.NoteBase,  # 移除 Depends()，只支持JSON请求
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的笔记内容（纯JSON请求）。用户只能更新自己的记录。
    如需更新文件，请使用 /notes/{note_id}/with-file 端点。
    """
    print(f"DEBUG: 更新笔记 ID: {note_id}")
    print(f"DEBUG: 更新数据内容: title='{note_data.title}', content='{note_data.content}', note_type='{note_data.note_type}'")
    
    return await _update_note_internal(note_id, note_data, None, current_user_id, db)

@router.put("/{note_id}/with-file", response_model=schemas.NoteResponse, summary="更新笔记并支持文件上传")
async def update_note_with_file(
        note_id: int,
        note_data_json: str = Form(..., description="笔记数据，JSON字符串格式"),
        file: Optional[UploadFile] = File(None, description="可选：上传图片、视频或文件作为笔记的附件"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的笔记内容并支持文件上传（multipart请求）。
    """
    # 解析JSON数据
    try:
        note_data_dict = json.loads(note_data_json)
        note_data = schemas.NoteBase(**note_data_dict)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的JSON格式: {e}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"数据验证失败: {e}"
        )
    
    print(f"DEBUG: 更新笔记 ID: {note_id}。有文件: {bool(file)}")
    return await _update_note_internal(note_id, note_data, file, current_user_id, db)

async def _update_note_internal(
        note_id: int,
        note_data: schemas.NoteBase,
        file: Optional[UploadFile],
        current_user_id: int,
        db: Session
):
    """
    更新笔记的内部实现
    """
    db_note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not db_note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")

    update_dict = note_data.dict(exclude_unset=True)
    print(f"DEBUG: update_dict 内容: {update_dict}")
    
    # 手动检查哪些字段真正被设置了（非默认值）
    # 对于JSON请求，我们可以检查字段是否为None来判断是否被设置
    actual_updates = {}
    for key, value in update_dict.items():
        if key == "title" and value is not None:
            actual_updates[key] = value
        elif key == "content" and value is not None:
            actual_updates[key] = value
        elif key == "note_type" and value != "general":  # general是默认值
            actual_updates[key] = value
        elif key in ["course_id", "folder_id", "tags", "chapter"] and value is not None:
            actual_updates[key] = value
        elif key in ["media_url", "media_type", "original_filename", "media_size_bytes"] and value is not None:
            actual_updates[key] = value
    
    print(f"DEBUG: 实际要更新的字段: {actual_updates}")
    update_dict = actual_updates

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_note.media_url 中提取旧的 OSS object name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_note.media_url and db_note.media_url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_note.media_url.replace(oss_base_url_parsed, '', 1)

    try:
        # 0. 验证关联关系的存在和权限：课程/章节 或 文件夹（如果这些字段被修改）
        # 检查 course_id 和 chapter 的变化
        new_course_id = update_dict.get("course_id", db_note.course_id)
        new_chapter = update_dict.get("chapter", db_note.chapter)

        if new_course_id is not None:
            db_course = db.query(Course).filter(Course.id == new_course_id).first()
            if not db_course:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的课程不存在。")

        # 检查 folder_id 的变化
        new_folder_id = update_dict.get("folder_id", db_note.folder_id)
        if new_folder_id is not None:  # 如果指定了文件夹ID (0 已经被 schema 转换为 None)
            target_folder = db.query(Folder).filter(
                Folder.id == new_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not target_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="目标文件夹未找到或无权访问。")

        # Re-apply mutual exclusivity validation for course/chapter vs folder
        is_course_note_candidate = (new_course_id is not None) or (
                new_chapter is not None and new_chapter.strip() != "")
        is_folder_note_candidate = (new_folder_id is not None)

        if is_course_note_candidate and is_folder_note_candidate:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="笔记不能同时关联到课程/章节和自定义文件夹。请选择一种组织方式。")

        # If it's a course note, course_id must accompany chapter
        if (new_chapter is not None and new_chapter.strip() != "") and (new_course_id is None):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="为了关联章节信息，课程ID (course_id) 不能为空。")

        # Check if media_url or media_type are explicitly being cleared or updated to non-media type
        media_url_being_cleared = "media_url" in update_dict and update_dict["media_url"] is None
        media_type_being_set = "media_type" in update_dict
        new_media_type_from_data = update_dict.get("media_type")

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
            db_note.media_url = None
            db_note.media_type = None
            db_note.original_filename = None
            db_note.media_size_bytes = None

        # 1. 处理文件上传（如果提供了新文件）
        if file:
            target_media_type = update_dict.get("media_type")  # Get proposed media_type from client
            if target_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            # If new file replaces existing media, delete old OSS file
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

            oss_path_prefix = "note_files"
            if content_type.startswith('image/'):
                oss_path_prefix = "note_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "note_videos"

            new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

            # Upload to OSS
            db_note.media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_note.original_filename = file.filename
            db_note.media_size_bytes = file_size
            db_note.media_type = target_media_type  # Use the media_type from request body

            print(f"DEBUG: New file '{file.filename}' uploaded to OSS: {db_note.media_url}")

            # If `content` was not provided in update, and it was previously text, clear it for media-only note
            if "content" not in update_dict and db_note.content:
                db_note.content = None

        elif "media_url" in update_dict and update_dict[
            "media_url"] is not None and not file:  # User provided a new URL but no file
            # If new media_url is provided without a file, it's assumed to be an external URL
            db_note.media_url = update_dict["media_url"]
            db_note.media_type = update_dict.get("media_type")  # Should be provided via schema validator
            db_note.original_filename = None
            db_note.media_size_bytes = None
            # content is optional in this case (already handled by schema)

        # 2. 应用其他 update_dict 中的字段
        # 清理掉已通过文件上传或手动处理的 media 字段，防止再次覆盖
        fields_to_skip_manual_update = ["media_url", "media_type", "original_filename", "media_size_bytes", "file"]
        for key, value in update_dict.items():
            if key in fields_to_skip_manual_update:
                continue
            if hasattr(db_note, key):
                if key == "content":  # Must not be empty if there's no media
                    if value is None or (isinstance(value, str) and not value.strip()):
                        if db_note.media_url is None:  # If no media, content must be there
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="笔记内容不能为空。")
                        else:  # If there's media, content can be cleared
                            setattr(db_note, key, value)
                    else:  # Content value is not None/empty
                        setattr(db_note, key, value)
                elif key == "title":  # Title is mandatory, cannot be None or empty when provided
                    if value is None or (isinstance(value, str) and not value.strip()):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, 
                            detail="笔记标题不能为空。如果不想修改标题，请不要包含此字段。"
                        )
                    setattr(db_note, key, value)
                elif key == "folder_id":  # Handle folder_id separately if it's 0 to mean None
                    if value == 0:
                        db_note.folder_id = None
                    else:
                        db_note.folder_id = value
                else:  # For other fields, just apply
                    setattr(db_note, key, value)

        # 2.5. 验证笔记内容完整性 - 在所有字段更新之后进行
        # 检查是否有有效的文本内容（非空且非纯空白字符）
        has_valid_content = db_note.content and db_note.content.strip()
        has_media_file = db_note.media_url is not None
        
        if not has_valid_content and not has_media_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="笔记内容 (content) 和媒体文件 (media_url) 至少需要提供一个。"
            )

        # 3. 重新生成 combined_text
        context_identifier = ""
        # 优先使用更新后的值来判断
        current_course_id = db_note.course_id
        current_chapter = db_note.chapter
        current_folder_id = db_note.folder_id

        if current_course_id:
            db_course_for_text = db.query(Course).filter(Course.id == current_course_id).first()
            course_title = db_course_for_text.title if db_course_for_text else f"课程 {current_course_id}"
            context_identifier = f"课程: {course_title}. 章节: {current_chapter or '未指定'}."
        elif current_folder_id is not None:
            db_folder_for_text = db.query(Folder).filter(Folder.id == current_folder_id).first()
            folder_name = db_folder_for_text.name if db_folder_for_text else f"文件夹 {current_folder_id}"
            context_identifier = f"文件夹: {folder_name}."

        db_note.combined_text = ". ".join(filter(None, [
            _get_text_part(db_note.title),
            _get_text_part(db_note.content),
            _get_text_part(db_note.tags),
            _get_text_part(context_identifier),  # 包含课程/文件夹上下文
            _get_text_part(db_note.media_url),  # 包含新的媒体URL
            _get_text_part(db_note.media_type),  # 包含新的媒体类型
            _get_text_part(db_note.original_filename),  # 包含原始文件名
        ])).strip()
        if not db_note.combined_text:
            db_note.combined_text = ""

        # 4. 获取当前用户的LLM配置用于嵌入更新
        note_owner = db.query(Student).filter(Student.id == current_user_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if note_owner and note_owner.llm_api_type == "siliconflow" and note_owner.llm_api_key_encrypted:
            try:
                owner_llm_api_key = decrypt_key(note_owner.llm_api_key_encrypted)
                owner_llm_type = note_owner.llm_api_type
                owner_llm_base_url = note_owner.llm_api_base_url
                owner_llm_model_id = note_owner.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用笔记创建者配置的硅基流动 API 密钥更新笔记嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密笔记创建者硅基流动 API 密钥失败: {e}。笔记嵌入将使用零向量。")
                owner_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 笔记创建者未配置硅基流动 API 类型或密钥，笔记嵌入将使用零向量或默认行为。")

        embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
        if db_note.combined_text:
            try:
                new_embedding = await get_embeddings_from_api(
                    [db_note.combined_text],
                    api_key=owner_llm_api_key,
                    llm_type=owner_llm_type,
                    llm_base_url=owner_llm_base_url,
                    llm_model_id=owner_llm_model_id
                )
                if new_embedding:
                    embedding_recalculated = new_embedding[0]
                print(f"DEBUG: 笔记 {db_note.id} 嵌入向量已更新。")
            except Exception as e:
                print(f"ERROR: 更新笔记 {db_note.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING: 笔记 combined_text 为空，嵌入向量设为零。")
            embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db_note.embedding = embedding_recalculated  # 赋值给DB对象

        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        print(f"DEBUG: 笔记 {db_note.id} 更新成功。")
        return db_note

    except HTTPException as e:  # 捕获FastAPI异常，包括OSS上传时抛出的
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {new_uploaded_oss_object_name}")
        raise e
    except Exception as e:
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_UPDATE_NOTE_GLOBAL: 更新笔记失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新笔记失败: {e}",
        )

@router.delete("/{note_id}", summary="删除指定笔记")
async def delete_note(
        note_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的笔记。用户只能删除自己的记录。
    如果笔记关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    """
    print(f"DEBUG: 删除笔记 ID: {note_id}。")
    db_note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not db_note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")

    # <<< 新增：如果笔记关联了文件或媒体，并且是OSS URL，则尝试从OSS删除文件 >>>
    if db_note.media_type in ["image", "video", "file"] and db_note.media_url:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_note.media_url.replace(oss_base_url_parsed, '', 1) if db_note.media_url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_NOTE: 删除了笔记 {note_id} 关联的OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_NOTE: 删除笔记 {note_id} 关联的OSS文件 {object_name} 失败: {e}")
                # 即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(f"WARNING_NOTE: 笔记 {note_id} 的 media_url ({db_note.media_url}) 无效或非OSS URL，跳过OSS文件删除。")

    db.delete(db_note)
    db.commit()
    print(f"DEBUG: 笔记 {note_id} 及其关联文件删除成功。")
    return {"message": "Note deleted successfully"}
