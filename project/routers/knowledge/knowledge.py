# project/routers/knowledge/knowledge.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, or_
from typing import List, Optional, Any
from datetime import datetime
import uuid, os, asyncio

# 导入数据库和模型
from database import get_db, SessionLocal
from models import (KnowledgeBase, KnowledgeBaseFolder, KnowledgeArticle, KnowledgeDocument, 
                   KnowledgeDocumentChunk, Note, Folder, CollectedContent, Course, Student)
from dependencies import get_current_user_id
import schemas, oss_utils
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_user_model_for_provider
from ai_providers.document_processor import chunk_text, extract_text_from_document
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key

router = APIRouter(
    tags=["知识库管理"],
    responses={404: {"description": "Not found"}},
)

# --- 辅助函数 ---
def _get_text_part(value: Any) -> str:
    """
    Helper to get string from potentially None, empty string, datetime, or int/float
    Ensures that values used in combined_text are non-empty strings.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")  # 格式化日期，只保留年月日
    if isinstance(value, (int, float)):
        # 为小时数添加单位，或根据需要返回原始字符串表示
        return str(value) + ""  # 此处不需要加"小时"，因为这只是一个通用函数
    return str(value).strip() if str(value).strip() else ""

# --- 知识库基础管理接口 ---

@router.post("/knowledge-bases/", response_model=schemas.KnowledgeBaseResponse, summary="创建新知识库")
async def create_knowledge_base(
        kb_data: schemas.KnowledgeBaseBase,
        current_user_id: int = Depends(get_current_user_id),  # 依赖项，已正确获取当前用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建知识库: {kb_data.name}")
    try:
        # 创建新的知识库实例，将其 owner_id 设置为当前认证用户的ID
        db_kb = KnowledgeBase(
            owner_id=current_user_id,
            name=kb_data.name,
            description=kb_data.description,
            access_type=kb_data.access_type
        )

        db.add(db_kb)
        db.commit()  # 提交到数据库
        db.refresh(db_kb)  # 刷新 db_kb 对象以获取数据库生成的ID和创建时间等

        print(f"DEBUG: 知识库 '{db_kb.name}' (ID: {db_kb.id}) 创建成功。")
        return db_kb  # 现在可以直接返回ORM对象，因为 schemas.py 已经处理了datetime的序列化问题

    except IntegrityError:
        # 捕获数据库完整性错误，例如如果某个知识库名称在用户的知识库下必须唯一
        db.rollback()  # 回滚事务
        # 给出更明确的错误提示，说明是名称冲突
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="知识库名称已存在。")
    except Exception as e:
        # 捕获其他任何未预期错误
        db.rollback()  # 确保在异常时回滚
        print(f"ERROR_DB: 数据库会话使用过程中发生异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建知识库失败: {e}")

@router.get("/knowledge-bases/", response_model=List[schemas.KnowledgeBaseResponse], summary="获取当前用户所有知识库")
async def get_all_knowledge_bases(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取用户 {current_user_id} 的所有知识库。")
    knowledge_bases = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == current_user_id).all()
    print(f"DEBUG: 获取到 {len(knowledge_bases)} 个知识库。")
    return knowledge_bases

@router.get("/knowledge-bases/{kb_id}", response_model=schemas.KnowledgeBaseResponse, summary="获取指定知识库详情")
async def get_knowledge_base_by_id(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取知识库 ID: {kb_id} 的详情。")
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问")
    return knowledge_base

@router.put("/knowledge-bases/{kb_id}", response_model=schemas.KnowledgeBaseResponse, summary="更新指定知识库")
async def update_knowledge_base(
        kb_id: int,
        kb_data: schemas.KnowledgeBaseBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 更新知识库 ID: {kb_id}。")
    db_kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == current_user_id).first()
    if not db_kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问")

    update_data = kb_data.dict(exclude_unset=True)
    if "name" in update_data and update_data["name"] != db_kb.name:
        # 检查新名称是否已存在 (仅当名称改变时)
        existing_kb = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == current_user_id,
                                                     KnowledgeBase.name == update_data["name"]).first()
        if existing_kb:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="新知识库名称已存在。")

    for key, value in update_data.items():
        setattr(db_kb, key, value)

    db.add(db_kb)
    db.commit()
    db.refresh(db_kb)
    print(f"DEBUG: 知识库 {kb_id} 更新成功。")
    return db_kb

@router.delete("/knowledge-bases/{kb_id}", summary="删除指定知识库")
async def delete_knowledge_base(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 删除知识库 ID: {kb_id}。")
    db_kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == current_user_id).first()
    if not db_kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问")

    db.delete(db_kb)
    db.commit()
    print(f"DEBUG: 知识库 {kb_id} 及其所有文章文档删除成功。")
    return {"message": "Knowledge base and its articles/documents deleted successfully"}

# --- 知识库文件夹管理接口 ---

@router.post("/knowledge-bases/{kb_id}/folders/", response_model=schemas.KnowledgeBaseFolderResponse,
          summary="在指定知识库中创建新文件夹")
async def create_knowledge_base_folder(
        kb_id: int,
        folder_data: schemas.KnowledgeBaseFolderBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    在指定知识库中创建一个新文件夹。
    支持创建普通文件夹和软链接文件夹（链接到课程笔记文件夹或收藏文件夹）。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试在知识库 {kb_id} 中创建文件夹: {folder_data.name}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    # 2. 验证父文件夹（如果提供了parent_id且不为NULL）
    if folder_data.parent_id is not None:
        parent_folder = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == folder_data.parent_id,
            KnowledgeBaseFolder.kb_id == kb_id,
            KnowledgeBaseFolder.owner_id == current_user_id
        ).first()
        if not parent_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父文件夹未找到或无权访问。")

    # 3. 验证软链接目标文件夹 (如果是软链接文件夹)
    if folder_data.linked_folder_type and folder_data.linked_folder_id is not None:
        # 软链接文件夹不能有父文件夹
        if folder_data.parent_id is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="软链接文件夹只能是顶级文件夹，不能拥有父文件夹。")

        # 验证外部文件夹是否存在和不包含视频文件
        external_folder = None
        if folder_data.linked_folder_type == "note_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == folder_data.linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="引用的课程笔记文件夹未找到或无权访问。")

            notes_in_folder = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == folder_data.linked_folder_id
            ).all()
            for note in notes_in_folder:
                if note.media_type == "video" and oss_utils.is_oss_url(note.media_url):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="链接的课程笔记文件夹中包含视频文件（非外部链接），不支持链接。")

        elif folder_data.linked_folder_type == "collected_content_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == folder_data.linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="引用的收藏文件夹未找到或无权访问。")

            collected_contents_in_folder = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == folder_data.linked_folder_id
            ).all()
            for content_item in collected_contents_in_folder:
                if content_item.type == "video" and oss_utils.is_oss_url(content_item.url):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="链接的收藏文件夹中包含视频文件（非外部链接），不支持链接。")

        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的链接文件夹类型: {folder_data.linked_folder_type}。")

        # 如果名称未提供，使用外部文件夹的名称
        if not folder_data.name and external_folder:
            folder_data.name = external_folder.name

    # 4. 创建知识库文件夹
    db_kb_folder = KnowledgeBaseFolder(
        kb_id=kb_id,
        owner_id=current_user_id,
        name=folder_data.name,
        description=folder_data.description,
        parent_id=folder_data.parent_id,
        order=folder_data.order,
        linked_folder_type=folder_data.linked_folder_type,
        linked_folder_id=folder_data.linked_folder_id
    )

    db.add(db_kb_folder)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if "_kb_folder_name_uc" in str(e) or "_kb_folder_root_name_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="在当前父文件夹下（或根目录）已存在同名文件夹。")
        elif "_kb_folder_linked_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"该外部文件夹 ({folder_data.linked_folder_type} ID:{folder_data.linked_folder_id}) 已被链接到此知识库。")
        print(f"ERROR_DB: 创建知识库文件夹发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建知识库文件夹失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 创建知识库文件夹发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建知识库文件夹失败: {e}")

    db.refresh(db_kb_folder)

    # 填充响应模型中的动态字段
    kb_name_obj = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    db_kb_folder.kb_name_for_response = kb_name_obj.name if kb_name_obj else "未知知识库"
    if db_kb_folder.parent_id:
        parent_folder_obj = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == db_kb_folder.parent_id).first()
        db_kb_folder.parent_folder_name_for_response = parent_folder_obj.name if parent_folder_obj else f"ID为{db_kb_folder.parent_id}的父文件夹"

    print(f"DEBUG: 知识库 {kb_id} 中的文件夹 '{db_kb_folder.name}' (ID: {db_kb_folder.id}) 创建成功。")
    return db_kb_folder

@router.get("/knowledge-bases/{kb_id}/folders/", response_model=List[schemas.KnowledgeBaseFolderResponse],
         summary="获取指定知识库下所有文件夹和软链接内容")
async def get_knowledge_base_folders(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        parent_id: Optional[int] = Query(None, description="按父文件夹ID过滤。传入0表示顶级文件夹（即parent_id为NULL）")
):
    """
    获取指定知识库下当前用户创建的所有文件夹。
    可通过 parent_id 过滤，获取特定父文件夹下的子文件夹。
    对于软链接文件夹，会包含其链接的外部文件夹的名称，以及其包含的有效内容数量。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 在知识库 {kb_id} 中的文件夹列表。父ID: {parent_id}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    query = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.kb_id == kb_id,
        KnowledgeBaseFolder.owner_id == current_user_id
    )

    if parent_id is not None:
        if parent_id == 0:  # 0 表示顶级文件夹，即 parent_id 为 NULL
            query = query.filter(KnowledgeBaseFolder.parent_id.is_(None))
        else:  # 查询特定父文件夹下的子文件夹，并验证父文件夹存在且属于该知识库
            existing_parent_folder = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == parent_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not existing_parent_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父文件夹未找到或无权访问。")
            query = query.filter(KnowledgeBaseFolder.parent_id == parent_id)
    else:  # 默认获取所有顶级文件夹
        query = query.filter(KnowledgeBaseFolder.parent_id.is_(None))

    folders = query.order_by(KnowledgeBaseFolder.order, KnowledgeBaseFolder.name).all()

    # 填充响应模型中的动态字段：kb_name 和 parent_folder_name 以及 item_count 和 linked_object_names
    kb_name_map = {knowledge_base.id: knowledge_base.name}
    parent_folder_names_map = {
        f.parent_id: db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == f.parent_id).first().name for f in
        folders if f.parent_id}

    for folder in folders:
        folder.kb_name_for_response = kb_name_map.get(folder.kb_id)
        if folder.parent_id and folder.parent_id in parent_folder_names_map:
            folder.parent_folder_name_for_response = parent_folder_names_map[folder.parent_id]

        # 处理软链接文件夹的 item_count 和 linked_object_names
        if folder.linked_folder_type and folder.linked_folder_id is not None:
            if folder.linked_folder_type == "note_folder":
                linked_notes = db.query(Note).filter(
                    Note.owner_id == current_user_id,
                    Note.folder_id == folder.linked_folder_id
                ).all()
                folder.item_count = len(linked_notes)
                folder.linked_object_names_for_response = [n.title or n.content[:30] if n.content else n.media_url for
                                                           n in linked_notes]
            elif folder.linked_folder_type == "collected_content_folder":
                linked_contents = db.query(CollectedContent).filter(
                    CollectedContent.owner_id == current_user_id,
                    CollectedContent.folder_id == folder.linked_folder_id
                ).all()
                folder.item_count = len(linked_contents)
                folder.linked_object_names_for_response = [c.title or c.content or c.url for c in
                                                           linked_contents]
            else:
                folder.item_count = 0
                folder.linked_object_names_for_response = []
        else:
            # 计算非软链接文件夹的 item_count: 直属文章数量 + 直属文档数量 + 直属子文件夹数量
            folder.item_count = db.query(KnowledgeArticle).filter(
                KnowledgeArticle.kb_id == kb_id,
                KnowledgeArticle.author_id == current_user_id,
                KnowledgeArticle.kb_folder_id == folder.id
            ).count() + \
                                db.query(KnowledgeDocument).filter(
                                    KnowledgeDocument.kb_id == kb_id,
                                    KnowledgeDocument.owner_id == current_user_id,
                                    KnowledgeDocument.kb_folder_id == folder.id
                                ).count() + \
                                db.query(KnowledgeBaseFolder).filter(
                                    KnowledgeBaseFolder.kb_id == kb_id,
                                    KnowledgeBaseFolder.owner_id == current_user_id,
                                    KnowledgeBaseFolder.parent_id == folder.id
                                ).count()
            # 非软链接文件夹不返回 linked_object_names
            folder.linked_object_names_for_response = None

    print(f"DEBUG: 获取到 {len(folders)} 个知识库文件夹。")
    return folders

@router.get("/knowledge-bases/{kb_id}/folders/{kb_folder_id}", response_model=schemas.KnowledgeBaseFolderContentResponse,
         summary="获取指定知识库文件夹详情及其内容")
async def get_knowledge_base_folder_by_id(
        kb_id: int,
        kb_folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        include_contents: bool = Query(False, description="是否包含软链接文件夹的实际内容（仅适用于软链接文件夹）")
):
    """
    获取指定ID的知识库文件夹详情。用户只能获取自己知识库下的文件夹。
    如果文件夹是软链接，且指定 include_contents=True，则会返回其链接的实际内容列表。
    """
    print(f"DEBUG: 获取知识库 {kb_id} 中文件夹 ID: {kb_folder_id} 的详情。")
    folder = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.id == kb_folder_id,
        KnowledgeBaseFolder.kb_id == kb_id,
        KnowledgeBaseFolder.owner_id == current_user_id
    ).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="知识库文件夹未找到、不属于该知识库或无权访问。")

    # 填充响应模型中的动态字段：kb_name 和 parent_folder_name 以及 item_count
    kb_name_obj = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    folder.kb_name_for_response = kb_name_obj.name if kb_name_obj else "未知知识库"
    if folder.parent_id:
        parent_folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == folder.parent_id).first()
        folder.parent_folder_name_for_response = parent_folder_obj.name if parent_folder_obj else f"ID为{folder.parent_id}的父文件夹"

    # 处理软链接文件夹的 item_count 和 linked_object_names 和 contents
    actual_contents = []
    if folder.linked_folder_type and folder.linked_folder_id is not None:
        if folder.linked_folder_type == "note_folder":
            linked_notes = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == folder.linked_folder_id
            ).all()
            folder.item_count = len(linked_notes)
            folder.linked_object_names_for_response = [n.title or n.content[:30] if n.content else n.media_url for n in
                                                       linked_notes]

            if include_contents:
                for note in linked_notes:
                    if note.folder_id:
                        linked_note_folder_obj = db.query(Folder).filter(Folder.id == note.folder_id).first()
                        if linked_note_folder_obj:
                            note.folder_name_for_response = linked_note_folder_obj.name
                    if note.course_id:
                        linked_note_course_obj = db.query(Course).filter(Course.id == note.course_id).first()
                        if linked_note_course_obj:
                            note.course_title_for_response = linked_note_course_obj.title
                    actual_contents.append(schemas.NoteResponse.model_validate(note, from_attributes=True))

        elif folder.linked_folder_type == "collected_content_folder":
            linked_contents_from_collection = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == folder.linked_folder_id
            ).all()
            folder.item_count = len(linked_contents_from_collection)
            folder.linked_object_names_for_response = [c.title or c.content or c.url for c in
                                                       linked_contents_from_collection]

            if include_contents:
                for content_item in linked_contents_from_collection:
                    if content_item.folder_id:
                        linked_cc_folder_obj = db.query(Folder).filter(Folder.id == content_item.folder_id).first()
                        if linked_cc_folder_obj:
                            content_item.folder_name_for_response = linked_cc_folder_obj.name
                    actual_contents.append(
                        schemas.CollectedContentResponse.model_validate(content_item, from_attributes=True))
        else:
            folder.item_count = 0
            folder.linked_object_names_for_response = []
    else:
        # 计算非软链接文件夹的 item_count: 直属文章数量 + 直属文档数量 + 直属子文件夹数量
        folder.item_count = db.query(KnowledgeArticle).filter(
            KnowledgeArticle.kb_id == kb_id,
            KnowledgeArticle.author_id == current_user_id,
            KnowledgeArticle.kb_folder_id == folder.id
        ).count() + \
                            db.query(KnowledgeDocument).filter(
                                KnowledgeDocument.kb_id == kb_id,
                                KnowledgeDocument.owner_id == current_user_id,
                                KnowledgeDocument.kb_folder_id == folder.id
                            ).count() + \
                            db.query(KnowledgeBaseFolder).filter(
                                KnowledgeBaseFolder.kb_id == kb_id,
                                KnowledgeBaseFolder.owner_id == current_user_id,
                                KnowledgeBaseFolder.parent_id == folder.id
                            ).count()
        folder.linked_object_names_for_response = None

        # 对于非软链接文件夹，如果 include_contents 为 True，可以返回其直属文章和文档列表
        if include_contents:
            direct_articles = db.query(KnowledgeArticle).filter(
                KnowledgeArticle.kb_id == kb_id,
                KnowledgeArticle.author_id == current_user_id,
                KnowledgeArticle.kb_folder_id == folder.id
            ).all()
            direct_documents = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.kb_id == kb_id,
                KnowledgeDocument.owner_id == current_user_id,
                KnowledgeDocument.kb_folder_id == folder.id
            ).all()
            for art in direct_articles:
                art.kb_folder_name_for_response = folder.name
                actual_contents.append(schemas.KnowledgeArticleResponse.model_validate(art, from_attributes=True))
            for doc in direct_documents:
                doc.kb_folder_name_for_response = folder.name
                actual_contents.append(schemas.KnowledgeDocumentResponse.model_validate(doc, from_attributes=True))

    # 创建响应对象
    response_folder = schemas.KnowledgeBaseFolderContentResponse.model_validate(folder, from_attributes=True)
    response_folder.contents = actual_contents

    return response_folder

@router.put("/knowledge-bases/{kb_id}/folders/{kb_folder_id}", response_model=schemas.KnowledgeBaseFolderResponse,
         summary="更新指定知识库文件夹")
async def update_knowledge_base_folder(
        kb_id: int,
        kb_folder_id: int,
        folder_data: schemas.KnowledgeBaseFolderBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的知识库文件夹信息。用户只能更新自己知识库下的文件夹。
    支持修改名称、描述、父文件夹和排序。
    如果文件夹是软链接，其链接类型和ID也可更新（但有限制）。
    """
    print(f"DEBUG: 更新知识库 {kb_id} 中文件夹 ID: {kb_folder_id} 的信息。")
    db_kb_folder = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.id == kb_folder_id,
        KnowledgeBaseFolder.kb_id == kb_id,
        KnowledgeBaseFolder.owner_id == current_user_id
    ).first()
    if not db_kb_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="知识库文件夹未找到、不属于该知识库或无权访问。")

    update_dict = folder_data.dict(exclude_unset=True)

    # 1. 处理软链接相关字段的更新逻辑
    old_linked_folder_type = db_kb_folder.linked_folder_type
    old_linked_folder_id = db_kb_folder.linked_folder_id

    new_linked_folder_type = update_dict.get("linked_folder_type", old_linked_folder_type)
    new_linked_folder_id = update_dict.get("linked_folder_id", old_linked_folder_id)

    # 检查是否尝试修改为软链接状态，或修改软链接目标
    is_becoming_linked = (new_linked_folder_type and new_linked_folder_id is not None) and (
            not old_linked_folder_type or old_linked_folder_id is None or new_linked_folder_type != old_linked_folder_type or new_linked_folder_id != old_linked_folder_id)
    is_changing_from_linked_to_regular = (
            old_linked_folder_type and (new_linked_folder_type is None or new_linked_folder_id is None))

    # 规则：软链接文件夹和普通文件夹不能互相转换
    if (is_becoming_linked and (
            db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_folder_id == kb_folder_id).count() > 0 or 
            db.query(KnowledgeDocument).filter(KnowledgeDocument.kb_folder_id == kb_folder_id).count() > 0 or 
            db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.parent_id == kb_folder_id).count() > 0)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="包含内容的普通文件夹不能转换为软链接文件夹。请清空内容或删除后重新创建链接。")

    if is_changing_from_linked_to_regular and db_kb_folder.linked_folder_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="软链接文件夹不能转换为普通文件夹。如需取消链接，请删除此链接文件夹。")

    # 如果是软链接，并且链接目标正在被修改
    if is_becoming_linked:
        # 软链接文件夹不能有父文件夹
        if db_kb_folder.parent_id is not None or ("parent_id" in update_dict and update_dict["parent_id"] is not None):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="软链接文件夹只能是顶级文件夹，不能拥有父文件夹。")

        # 验证新的软链接目标文件夹是否存在且没有视频文件
        external_folder = None
        if new_linked_folder_type == "note_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == new_linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="引用的课程笔记文件夹未找到或无权访问。")

            notes_in_folder = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == new_linked_folder_id
            ).all()
            for note in notes_in_folder:
                if note.media_type == "video" and oss_utils.is_oss_url(note.media_url):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="链接的课程笔记文件夹中包含视频文件（非外部链接），不支持链接。")

        elif new_linked_folder_type == "collected_content_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == new_linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="引用的收藏文件夹未找到或无权访问。")

            collected_contents_in_folder = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == new_linked_folder_id
            ).all()
            for content_item in collected_contents_in_folder:
                if content_item.type == "video" and oss_utils.is_oss_url(content_item.url):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="链接的收藏文件夹中包含视频文件（非外部链接），不支持链接。")

        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的链接文件夹类型: {new_linked_folder_type}。")

        # 更新软链接字段
        db_kb_folder.linked_folder_type = new_linked_folder_type
        db_kb_folder.linked_folder_id = new_linked_folder_id
        db_kb_folder.parent_id = None  # 软链接文件夹必须是顶级的
        # 如果名称没有提供，默认使用外部文件夹的名称
        if not update_dict.get("name") and external_folder:
            db_kb_folder.name = external_folder.name

        # 移除已处理字段
        update_dict.pop("linked_folder_type", None)
        update_dict.pop("linked_folder_id", None)
        update_dict.pop("parent_id", None)

    # 2. 处理普通文件夹的父文件夹和名称更新
    elif not old_linked_folder_type:
        # 2.1 验证新的父文件夹
        if "parent_id" in update_dict:
            new_parent_id = update_dict["parent_id"]
            # 不能将自己设为父文件夹
            if new_parent_id == kb_folder_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹不能是自身的父级。")

            if new_parent_id is not None:
                new_parent_folder = db.query(KnowledgeBaseFolder).filter(
                    KnowledgeBaseFolder.id == new_parent_id,
                    KnowledgeBaseFolder.kb_id == kb_id,
                    KnowledgeBaseFolder.owner_id == current_user_id
                ).first()
                if not new_parent_folder:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                        detail="新的父文件夹未找到、不属于该知识库或无权访问。")

                # 检查是否会形成循环（简单检查）
                temp_check_folder = new_parent_folder
                while temp_check_folder:
                    if temp_check_folder.id == kb_folder_id:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                            detail="检测到循环依赖，无法将此文件夹设为父文件夹。")
                    temp_check_folder = db.query(KnowledgeBaseFolder).filter(
                        KnowledgeBaseFolder.id == temp_check_folder.parent_id).first() if temp_check_folder.parent_id else None

            db_kb_folder.parent_id = new_parent_id
            update_dict.pop("parent_id", None)

        # 2.2 检查名称冲突
        if "name" in update_dict and update_dict["name"] != db_kb_folder.name:
            existing_name_folder_query = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id,
                KnowledgeBaseFolder.name == update_dict["name"],
                KnowledgeBaseFolder.id != kb_folder_id
            )
            if db_kb_folder.parent_id is None:
                existing_name_folder_query = existing_name_folder_query.filter(KnowledgeBaseFolder.parent_id.is_(None))
            else:
                existing_name_folder_query = existing_name_folder_query.filter(
                    KnowledgeBaseFolder.parent_id == db_kb_folder.parent_id)

            if existing_name_folder_query.first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="在当前父文件夹下已存在同名文件夹。")

            db_kb_folder.name = update_dict["name"]
            update_dict.pop("name", None)

        # 如果是普通文件夹，但尝试提供软链接字段，则拒绝
        if "linked_folder_type" in update_dict or "linked_folder_id" in update_dict:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="普通文件夹不能指定软链接信息。")

    # 3. 应用其他字段更新
    for key, value in update_dict.items():
        if key in ["linked_folder_type", "linked_folder_id", "name", "parent_id"]:
            continue
        if hasattr(db_kb_folder, key) and value is not None:
            setattr(db_kb_folder, key, value)
        elif hasattr(db_kb_folder, key) and value is None:
            if key == "description":
                setattr(db_kb_folder, key, value)

    db.add(db_kb_folder)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识库文件夹发生完整性约束错误: {e}")
        if "_kb_folder_name_uc" in str(e) or "_kb_folder_root_name_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="更新知识库文件夹失败，在当前父文件夹下（或根目录）已存在同名文件夹。")
        elif "_kb_folder_linked_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"该外部文件夹 ({db_kb_folder.linked_folder_type} ID:{db_kb_folder.linked_folder_id}) 已被链接到此知识库。")
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新知识库文件夹失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识库文件夹发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新知识库文件夹失败: {e}")

    db.refresh(db_kb_folder)

    # 填充响应模型中的动态字段
    kb_name_obj = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    db_kb_folder.kb_name_for_response = kb_name_obj.name if kb_name_obj else "未知知识库"
    if db_kb_folder.parent_id:
        parent_folder_obj = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == db_kb_folder.parent_id).first()
        db_kb_folder.parent_folder_name_for_response = parent_folder_obj.name if parent_folder_obj else f"ID为{db_kb_folder.parent_id}的父文件夹"

    # 重新计算 item_count 和 linked_object_names
    if db_kb_folder.linked_folder_type and db_kb_folder.linked_folder_id is not None:
        if db_kb_folder.linked_folder_type == "note_folder":
            linked_notes = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == db_kb_folder.linked_folder_id
            ).all()
            db_kb_folder.item_count = len(linked_notes)
            db_kb_folder.linked_object_names_for_response = [n.title or n.content[:30] if n.content else n.media_url
                                                             for n in linked_notes]
        elif db_kb_folder.linked_folder_type == "collected_content_folder":
            linked_contents = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == db_kb_folder.linked_folder_id
            ).all()
            db_kb_folder.item_count = len(linked_contents)
            db_kb_folder.linked_object_names_for_response = [c.title or c.content or c.url for c in linked_contents]
    else:
        db_kb_folder.item_count = db.query(KnowledgeArticle).filter(
            KnowledgeArticle.kb_id == kb_id, KnowledgeArticle.author_id == current_user_id,
            KnowledgeArticle.kb_folder_id == db_kb_folder.id
        ).count() + \
                                  db.query(KnowledgeDocument).filter(
                                      KnowledgeDocument.kb_id == kb_id, KnowledgeDocument.owner_id == current_user_id,
                                      KnowledgeDocument.kb_folder_id == db_kb_folder.id
                                  ).count() + \
                                  db.query(KnowledgeBaseFolder).filter(
                                      KnowledgeBaseFolder.kb_id == kb_id,
                                      KnowledgeBaseFolder.owner_id == current_user_id,
                                      KnowledgeBaseFolder.parent_id == kb_folder_id
                                  ).count()
        db_kb_folder.linked_object_names_for_response = None

    print(f"DEBUG: 知识库文件夹 {kb_folder_id} 更新成功。")
    return db_kb_folder

@router.delete("/knowledge-bases/{kb_id}/folders/{kb_folder_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定知识库文件夹")
async def delete_knowledge_base_folder(
        kb_id: int,
        kb_folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的知识库文件夹。
    如果是非软链接的普通文件夹，将级联删除其下所有直属文章、文档和子文件夹。
    如果是软链接文件夹，将只删除链接本身（KnowledgeBaseFolder记录），不影响被链接的原始笔记文件夹或收藏文件夹中的内容。
    用户只能删除自己知识库下的文件夹。
    """
    print(f"DEBUG: 删除知识库 {kb_id} 中的文件夹 ID: {kb_folder_id}。")
    db_kb_folder = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.id == kb_folder_id,
        KnowledgeBaseFolder.kb_id == kb_id,
        KnowledgeBaseFolder.owner_id == current_user_id
    ).first()
    if not db_kb_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="知识库文件夹未找到、不属于该知识库或无权访问。")

    # 判断是否是软链接文件夹
    if db_kb_folder.linked_folder_type and db_kb_folder.linked_folder_id is not None:
        # 如果是软链接文件夹，只删除 KnowledgeBaseFolder 记录自身
        db.delete(db_kb_folder)
        db.commit()
        print(
            f"DEBUG: 知识库软链接文件夹 {kb_folder_id} (链接到 {db_kb_folder.linked_folder_type} ID: {db_kb_folder.linked_folder_id}) 已成功删除（仅删除链接）。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    else:
        # 如果是普通文件夹，则删除文件夹及其所有内容（文章、文档、子文件夹）
        db.delete(db_kb_folder)
        db.commit()
        print(f"DEBUG: 知识库普通文件夹 {kb_folder_id} 及其内容已成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- 知识文章 (手动创建内容) 管理接口 ---

@router.post("/knowledge-bases/{kb_id}/articles/", response_model=schemas.KnowledgeArticleResponse,
          summary="在指定知识库中创建新文章")
async def create_knowledge_article(
        kb_id: int,
        article_data: schemas.KnowledgeArticleBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    在指定知识库中创建一篇新知识文章。
    文章内容会生成嵌入并存储。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试在知识库 {kb_id} 中创建文章: {article_data.title} (文件夹ID: {article_data.kb_folder_id})")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    # 2. 验证文件夹是否存在且属于同一知识库和同一用户
    target_kb_folder = None
    if article_data.kb_folder_id is not None:
        target_kb_folder = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == article_data.kb_folder_id,
            KnowledgeBaseFolder.kb_id == kb_id,
            KnowledgeBaseFolder.owner_id == current_user_id
        ).first()
        if not target_kb_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="目标文件夹未找到、不属于该知识库或无权访问。")

    # 3. 组合文本用于嵌入
    folder_context = ""
    if target_kb_folder:
        folder_context = f"属于文件夹: {target_kb_folder.name}."

    combined_text = ". ".join(filter(None, [
        _get_text_part(article_data.title),
        _get_text_part(article_data.content),
        _get_text_part(article_data.tags),
        _get_text_part(folder_context),
    ])).strip()

    embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR

    # 获取文章作者的LLM配置进行嵌入生成
    author_user = db.query(Student).filter(Student.id == current_user_id).first()
    author_llm_api_key = None
    author_llm_type = None
    author_llm_base_url = None
    author_llm_model_id = None

    if author_user and author_user.llm_api_type == "siliconflow" and author_user.llm_api_key_encrypted:
        try:
            author_llm_api_key = decrypt_key(author_user.llm_api_key_encrypted)
            author_llm_type = author_user.llm_api_type
            author_llm_base_url = author_user.llm_api_base_url
            author_llm_model_id = author_user.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用文章作者配置的硅基流动 API 密钥为文章生成嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密文章作者硅基流动 API 密钥失败: {e}。文章嵌入将使用零向量或默认行为。")
            author_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 文章作者未配置硅基流动 API 类型或密钥，文章嵌入将使用零向量或默认行为。")

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
            print(f"DEBUG: 文章嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成文章嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 文章 combined_text 为空，嵌入向量设为零。")

    # 4. 创建数据库记录
    db_article = KnowledgeArticle(
        kb_id=kb_id,
        author_id=current_user_id,
        title=article_data.title,
        content=article_data.content,
        version=article_data.version,
        tags=article_data.tags,
        kb_folder_id=article_data.kb_folder_id,
        combined_text=combined_text,
        embedding=embedding
    )

    db.add(db_article)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建知识文章发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建知识文章失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 创建知识文章发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建知识文章失败: {e}")

    db.refresh(db_article)

    # 填充响应模型中的动态字段
    if db_article.kb_folder_id:
        if target_kb_folder:
            db_article.kb_folder_name_for_response = target_kb_folder.name
        else:
            folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == db_article.kb_folder_id).first()
            db_article.kb_folder_name_for_response = folder_obj.name if folder_obj else f"ID为{db_article.kb_folder_id}的文件夹"

    print(f"DEBUG: 知识文章 (ID: {db_article.id}) 创建成功。")
    return db_article

@router.get("/knowledge-bases/{kb_id}/articles/", response_model=List[schemas.KnowledgeArticleResponse],
         summary="获取指定知识库的所有文章")
async def get_articles_in_knowledge_base(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        kb_folder_id: Optional[int] = Query(None,
                                            description="按知识库文件夹ID过滤。传入0表示顶级文件夹（即kb_folder_id为NULL）"),
        query_str: Optional[str] = Query(None, description="按关键词搜索文章标题或内容"),
        tag_filter: Optional[str] = Query(None, description="按标签过滤，支持模糊匹配"),
        page: int = Query(1, ge=1, description="页码，从1开始"),
        page_size: int = Query(20, ge=1, le=100, description="每页文章数量")
):
    print(f"DEBUG: 获取知识库 {kb_id} 的文章列表，用户 {current_user_id}。文件夹ID: {kb_folder_id}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    query = db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_id == kb_id,
                                              KnowledgeArticle.author_id == current_user_id)

    # 2. 应用文件夹过滤
    if kb_folder_id is not None:
        if kb_folder_id == 0:  # 0 表示顶级文件夹，即 kb_folder_id 为 NULL
            query = query.filter(KnowledgeArticle.kb_folder_id.is_(None))
        else:  # 查询特定文件夹下的文章，并验证文件夹存在且属于该知识库
            existing_kb_folder = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == kb_folder_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not existing_kb_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定知识库文件夹未找到或无权访问。")
            query = query.filter(KnowledgeArticle.kb_folder_id == kb_folder_id)

    # 3. 应用关键词搜索 (标题或内容)
    if query_str:
        query = query.filter(
            or_(
                KnowledgeArticle.title.ilike(f"%{query_str}%"),
                KnowledgeArticle.content.ilike(f"%{query_str}%")
            )
        )

    # 4. 应用标签过滤
    if tag_filter:
        query = query.filter(KnowledgeArticle.tags.ilike(f"%{tag_filter}%"))

    # 5. 应用分页
    offset = (page - 1) * page_size
    articles = query.order_by(KnowledgeArticle.created_at.desc()).offset(offset).limit(page_size).all()

    # 6. 填充响应模型中的动态字段：文件夹名称
    # 提前加载所有相关知识库文件夹，避免 N+1 查询
    kb_folder_ids_in_results = list(
        set([article.kb_folder_id for article in articles if article.kb_folder_id is not None]))
    kb_folder_map = {f.id: f.name for f in
                     db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id.in_(kb_folder_ids_in_results)).all()}

    for article in articles:
        if article.kb_folder_id and article.kb_folder_id in kb_folder_map:
            article.kb_folder_name_for_response = kb_folder_map[article.kb_folder_id]
        elif article.kb_folder_id is None:
            article.kb_folder_name_for_response = "未分类"

    print(f"DEBUG: 知识库 {kb_id} 获取到 {len(articles)} 篇文章。")
    return articles

# --- 知识文档和文章路由 ---

@router.put("/knowledge-bases/{kb_id}/articles/{article_id}", response_model=schemas.KnowledgeArticleResponse,
         summary="更新指定知识文章")
async def update_knowledge_article(
        kb_id: int,
        article_id: int,
        article_data: schemas.KnowledgeArticleBase = Depends(),  # now contains kb_folder_id
        current_user_id: int = Depends(get_current_user_id),  # 只有文章作者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的知识文章内容。只有文章作者能更新。
    支持更新所属知识库文件夹。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新知识文章 ID: {article_id}。用户: {current_user_id}。文件夹ID: {article_data.kb_folder_id}")
    db_article = db.query(KnowledgeArticle).filter(
        KnowledgeArticle.id == article_id,
        KnowledgeArticle.kb_id == kb_id,
        KnowledgeArticle.author_id == current_user_id
    ).first()
    if not db_article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识文章未找到或无权访问。")

    update_dict = article_data.dict(exclude_unset=True)

    # 1. 验证知识库文件夹是否存在且属于同一知识库和同一用户 (如果 kb_folder_id 被修改)
    target_kb_folder_for_update = None
    if "kb_folder_id" in update_dict:  # 已经由 schema 转换为 None/int
        new_kb_folder_id = update_dict["kb_folder_id"]
        if new_kb_folder_id is not None:
            target_kb_folder_for_update = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == new_kb_folder_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not target_kb_folder_for_update:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="目标知识库文件夹未找到、不属于该知识库或无权访问。")
        db_article.kb_folder_id = new_kb_folder_id  # Update folder_id in ORM object

    # 2. 应用其他 update_dict 中的字段
    for key, value in update_dict.items():
        if key == "kb_folder_id":  # This was handled manually
            continue
        if hasattr(db_article, key) and value is not None:
            setattr(db_article, key, value)
        elif hasattr(db_article, key) and value is None:  # Allow clearing tags, content etc. if None is passed
            if key in ["title", "content"]:  # title and content are generally never None/empty
                if not value or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"文章'{key}'不能为空。")
            setattr(db_article, key, value)

    # 3. 重新生成 combined_text
    # 优先使用已经获取的 target_kb_folder_for_update，如果没有，再根据 db_article.kb_folder_id 查询
    folder_context_text = ""
    if db_article.kb_folder_id:
        if target_kb_folder_for_update:
            folder_context_text = f"属于文件夹: {target_kb_folder_for_update.name}."
        else:  # If folder_id changed to an existing ID but not via update_dict, query it.
            current_kb_folder_from_db = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == db_article.kb_folder_id).first()
            folder_context_text = f"属于文件夹: {current_kb_folder_from_db.name}." if current_kb_folder_from_db else ""

    combined_text = ". ".join(filter(None, [
        _get_text_part(db_article.title),
        _get_text_part(db_article.content),
        _get_text_part(db_article.tags),
        _get_text_part(folder_context_text),  # 包含文件夹上下文
    ])).strip()
    if not combined_text:
        combined_text = ""

    # 获取文章作者的LLM配置用于嵌入更新 (作者已在权限依赖中确认)
    author_user = db.query(Student).filter(Student.id == current_user_id).first()
    author_llm_api_key = None
    author_llm_type = None
    author_llm_base_url = None
    author_llm_model_id = None

    if author_user and author_user.llm_api_type == "siliconflow" and author_user.llm_api_key_encrypted:
        try:
            author_llm_api_key = decrypt_key(author_user.llm_api_key_encrypted)
            author_llm_type = author_user.llm_api_type
            author_llm_base_url = author_user.llm_api_base_url
            author_llm_model_id = author_user.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用文章作者配置的硅基流动 API 密钥更新文章嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密文章作者硅基流动 API 密钥失败: {e}。文章嵌入将使用零向量或默认行为。")
            author_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 文章作者未配置硅基流动 API 类型或密钥，文章嵌入将使用零向量或默认行为。")

    embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
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
                embedding_recalculated = new_embedding[0]
            print(f"DEBUG: 文章 {db_article.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新文章 {db_article.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 文章 combined_text 为空，嵌入向量设为零。")
        embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db_article.embedding = embedding_recalculated  # 赋值给DB对象

    db.add(db_article)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识文章发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新知识文章失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识文章发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新知识文章失败: {e}")

    db.refresh(db_article)
    # 填充响应模型中的动态字段
    if db_article.kb_folder_id:
        if target_kb_folder_for_update:  # Use already fetched folder if available
            db_article.kb_folder_name_for_response = target_kb_folder_for_update.name
        else:  # Fallback in case folder_id exists but was not just fetched as target_kb_folder_for_update
            folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == db_article.kb_folder_id).first()
            db_article.kb_folder_name_for_response = folder_obj.name if folder_obj else f"ID为{db_article.kb_folder_id}的文件夹"

    print(f"INFO: 知识文章 {db_article.id} 更新成功。")
    return db_article

@router.get("/articles/{article_id}", response_model=schemas.KnowledgeArticleResponse, summary="获取指定文章详情")
async def get_knowledge_article_by_id(
        article_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取文章 ID: {article_id} 的详情。")
    # 用户只能查看自己知识库下的文章
    article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id,
                                                KnowledgeArticle.author_id == current_user_id).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章未找到或无权访问")

    # 填充文件夹名称用于响应
    if article.kb_folder_id:
        kb_folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == article.kb_folder_id).first()
        if kb_folder_obj:
            article.kb_folder_name_for_response = kb_folder_obj.name
        else:
            article.kb_folder_name_for_response = "未知文件夹"  # 或处理错误情况
    elif article.kb_folder_id is None:
        article.kb_folder_name_for_response = "未分类"  # 或其他表示根目录的字符串

    return article

@router.delete("/articles/{article_id}", summary="删除指定文章")
async def delete_knowledge_article(
        article_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 删除文章 ID: {article_id}。")
    db_article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id,
                                                   KnowledgeArticle.author_id == current_user_id).first()
    if not db_article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章未找到或无权访问")

    db.delete(db_article)
    db.commit()
    print(f"DEBUG: 文章 {article_id} 删除成功。")
    return {"message": "Knowledge article deleted successfully"}

# --- 知识文档上传和管理接口 (用于智库文件) ---
@router.post("/knowledge-bases/{kb_id}/documents/", response_model=schemas.KnowledgeDocumentResponse,
          status_code=status.HTTP_202_ACCEPTED, summary="上传新知识文档到知识库")
async def upload_knowledge_document(
        kb_id: int,
        file: UploadFile = File(...),  # 接收上传的文件
        kb_folder_id: Optional[int] = Query(None,
                                            description="可选：指定知识库文件夹ID。传入0表示顶级文件夹（即kb_folder_id为NULL）"),
        # New parameter for folder association
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    上传一个新文档（TXT, MD, PDF, DOCX, 图片文件）到指定知识库。
    不支持上传视频文件。
    文档内容将在后台异步处理，包括文本提取、分块和嵌入生成。
    """
    print(
        f"DEBUG_UPLOAD: 用户 {current_user_id} 尝试上传文件 '{file.filename}' 到知识库 {kb_id} (文件夹ID: {kb_folder_id})。")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    # 2. 验证知识库文件夹是否存在且属于同一知识库和同一用户 (如果提供了kb_folder_id)
    target_kb_folder = None
    if kb_folder_id is not None:  # Note: 0 已经被 schema 转换为 None
        target_kb_folder = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == kb_folder_id,
            KnowledgeBaseFolder.kb_id == kb_id,  # 必须属于同一知识库
            KnowledgeBaseFolder.owner_id == current_user_id
        ).first()
        if not target_kb_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="目标知识库文件夹未找到、不属于该知识库或无权访问。")
        # 验证目标文件夹是否是"软链接"文件夹
        # Linked_folder_type 字段将在下一步添加到 KnowledgeBaseFolder 模型中，请确保它存在
        if hasattr(target_kb_folder, 'linked_folder_type') and target_kb_folder.linked_folder_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能将文件上传到软链接文件夹。")

    # 3. 验证文件类型：只允许特定文档和图片，拒绝视频
    allowed_mime_types = [
        "text/plain",  # .txt
        "text/markdown",  # .md
        "application/pdf",  # .pdf
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "text/html",  # .html (可选，如果也要处理网页)
        "application/vnd.ms-excel",  # .xls (可选)
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx (可选)
        "application/vnd.ms-powerpoint",  # .ppt (可选)
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx (可选)
        "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"  # 常见图片类型
    ]
    if file.content_type not in allowed_mime_types:
        if file.content_type.startswith('video/'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持上传视频文件到知识库。")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的文件类型: {file.content_type}。仅支持TXT, MD, PDF, DOCX, 图片文件及常见Office文档。")

    # 4. 将文件上传到OSS
    file_bytes = await file.read()  # 读取文件所有字节
    file_extension = os.path.splitext(file.filename)[1]  # 获取文件扩展名

    # 根据文件类型确定OSS存储路径前缀
    oss_path_prefix = "knowledge_documents"  # 默认文档
    if file.content_type.startswith('image/'):
        oss_path_prefix = "knowledge_images"
    # 如果要支持更多类型，这里可以扩展
    # elif file.content_type.startswith('application/vnd.openxmlformats-officedocument'):
    #     oss_path_prefix = "knowledge_office_files"

    object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"  # OSS上的文件路径和名称

    try:
        oss_url = await oss_utils.upload_file_to_oss(
            file_bytes=file_bytes,
            object_name=object_name,
            content_type=file.content_type
        )
        print(f"DEBUG_UPLOAD: 文件 '{file.filename}' 上传到OSS成功，URL: {oss_url}")
    except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
        print(f"ERROR_UPLOAD: 上传文件到OSS失败: {e.detail}")
        raise e  # 直接重新抛出，让FastAPI处理
    except Exception as e:
        print(f"ERROR_UPLOAD: 上传文件到OSS时发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

    # 5. 在数据库中创建初始文档记录 (状态为 processing)
    # file_path 现在存储的是 OSS 的 URL
    db_document = KnowledgeDocument(
        kb_id=kb_id,
        owner_id=current_user_id,
        file_name=file.filename,
        file_path=oss_url,  # 现在存储的是OSS URL
        file_type=file.content_type,
        kb_folder_id=kb_folder_id,  # <<< 存储文件夹ID
        status="processing",
        processing_message="文件已上传到云存储，等待处理..."
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    # 6. 异步启动后台处理任务 (传入 db.session 的当前状态)
    background_db_session = SessionLocal()  # 创建一个新的会话
    asyncio.create_task(
        process_document_in_background(
            db_document.id,
            current_user_id,
            kb_id,
            object_name,  # 这里传递OSS对象名称
            file.content_type,
            background_db_session
        )
    )

    # Fill folder name for response
    if db_document.kb_folder_id:
        if target_kb_folder:
            db_document.kb_folder_name_for_response = target_kb_folder.name
        else:  # Fallback query
            folder_obj = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == db_document.kb_folder_id).first()
            db_document.kb_folder_name_for_response = folder_obj.name if folder_obj else "未分类"  # Or handle as error
    else:
        db_document.kb_folder_name_for_response = "未分类"  # For top-level documents

    print(f"DEBUG_UPLOAD: 文档 {db_document.id} 已接受上传，后台处理中。")
    return db_document

@router.get("/knowledge-bases/{kb_id}/documents/", response_model=List[schemas.KnowledgeDocumentResponse],
         summary="获取知识库下所有知识文档")
async def get_knowledge_base_documents(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        kb_folder_id: Optional[int] = Query(None,
                                            description="按知识库文件夹ID过滤。传入0表示顶级文件夹（即kb_folder_id为NULL）"),
        # <<< 新增这行
        status_filter: Optional[str] = Query(None, description="按处理状态过滤（processing, completed, failed）"),
        # 根据状态过滤
        query_str: Optional[str] = Query(None, description="按关键词搜索文件名"),  # 新增搜索功能
        page: int = Query(1, ge=1, description="页码，从1开始"),  # 新增分页
        page_size: int = Query(20, ge=1, le=100, description="每页文档数量")  # 新增分页
):
    """
    获取指定知识库下所有知识文档（已上传文件）的列表。
    可以按文件夹ID、处理状态和文件名关键词进行过滤。
    """
    print(f"DEBUG: 获取知识库 {kb_id} 的文档列表，用户 {current_user_id}。文件夹ID: {kb_folder_id}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    query = db.query(KnowledgeDocument).filter(KnowledgeDocument.kb_id == kb_id,
                                               KnowledgeDocument.owner_id == current_user_id)

    # 2. 应用文件夹过滤
    if kb_folder_id is not None:
        if kb_folder_id == 0:  # 0 表示顶级文件夹，即 kb_folder_id 为 NULL
            query = query.filter(KnowledgeDocument.kb_folder_id.is_(None))
        else:  # 查询特定文件夹下的文档，并验证文件夹存在且属于该知识库
            existing_kb_folder = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == kb_folder_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not existing_kb_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定知识库文件夹未找到或无权访问。")
            query = query.filter(KnowledgeDocument.kb_folder_id == kb_folder_id)

    # 3. 应用状态过滤
    if status_filter:
        query = query.filter(KnowledgeDocument.status == status_filter)

    # 4. 应用关键词搜索 (文件名)
    if query_str:
        query = query.filter(KnowledgeDocument.file_name.ilike(f"%{query_str}%"))

    # 5. 应用分页
    offset = (page - 1) * page_size
    documents = query.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(page_size).all()

    # 6. 填充响应模型中的动态字段：文件夹名称
    # 提前加载所有相关知识库文件夹，避免 N+1 查询
    kb_folder_ids_in_results = list(set([doc.kb_folder_id for doc in documents if doc.kb_folder_id is not None]))
    kb_folder_map = {f.id: f.name for f in
                     db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id.in_(kb_folder_ids_in_results)).all()}

    for doc in documents:
        if doc.kb_folder_id and doc.kb_folder_id in kb_folder_map:
            doc.kb_folder_name_for_response = kb_folder_map[doc.kb_folder_id]
        elif doc.kb_folder_id is None:
            doc.kb_folder_name_for_response = "未分类"  # 或其他表示根目录的字符串

    print(f"DEBUG: 知识库 {kb_id} 获取到 {len(documents)} 个文档。")
    return documents

@router.get("/knowledge-bases/{kb_id}/documents/{document_id}", response_model=schemas.KnowledgeDocumentResponse,
         summary="获取指定知识文档详情")
async def get_knowledge_document_detail(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定知识库下指定知识文档的详情。
    """
    print(f"DEBUG: 获取文档 ID: {document_id} 的详情。")
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    if document.kb_folder_id:
        kb_folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == document.kb_folder_id).first()
        if kb_folder_obj:
            document.kb_folder_name_for_response = kb_folder_obj.name
        else:
            document.kb_folder_name_for_response = "未知文件夹"  # 或处理错误情况
    elif document.kb_folder_id is None:
        document.kb_folder_name_for_response = "未分类"  # 或其他表示根目录的字符串

    return document

@router.delete("/knowledge-bases/{kb_id}/documents/{document_id}", summary="删除指定知识文档")
async def delete_knowledge_document(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定知识库下的指定知识文档及其所有文本块和OSS文件。
    """
    print(f"DEBUG: 删除文档 ID: {document_id}。")
    db_document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not db_document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    # <<< 修改：从OSS删除文件 >>>
    # 从OSS URL中解析出 object_name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    object_name = db_document.file_path.replace(oss_base_url_parsed, '', 1) if db_document.file_path.startswith(
        oss_base_url_parsed) else db_document.file_path

    if object_name:
        try:
            await oss_utils.delete_file_from_oss(object_name)
            print(f"DEBUG: 已删除OSS文件: {object_name}")
        except Exception as e:
            print(f"ERROR: 删除OSS文件 {object_name} 失败: {e}")
            # 这里不抛出异常，即使OSS文件删除失败，也应该允许数据库记录被删除
    else:
        print(f"WARNING: 文档 {document_id} 的 file_path 无效或非OSS URL: {db_document.file_path}，跳过OSS文件删除。")

    # 删除数据库记录（级联删除所有文本块）
    db.delete(db_document)
    db.commit()
    print(f"DEBUG: 文档 {document_id} 及其文本块已从数据库删除。")
    return {"message": "Knowledge document deleted successfully"}

# --- GET 请求获取文档内容 (为了方便调试检查后台处理结果) ---
@router.get("/knowledge-bases/{kb_id}/documents/{document_id}/content", summary="获取知识文档的原始文本内容 (DEBUG)")
async def get_document_raw_content(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定知识文档的原始文本内容 (用于调试，慎用，因为可能返回大量文本)。
    """
    print(f"DEBUG: 获取文档 ID: {document_id} 的原始内容。")
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    # if document.status != "completed": # 原始如果只从 chunk 拿就检查完成状态
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
    #                         detail=f"文档状态为 '{document.status}'，文本处理尚未完成或失败。")

    # 直接从数据库的 chunks 获取完整内容，而不是尝试重新解析文件
    # 拼接所有文本块的内容
    # 这是一个更可靠的方式来获取处理后的文档文本
    chunks = db.query(KnowledgeDocumentChunk).filter(
        KnowledgeDocumentChunk.document_id == document_id
    ).order_by(KnowledgeDocumentChunk.chunk_index).all()

    if not chunks:
        # 如果没有文本块，但文档状态是 completed，说明可能内容为空
        if document.status == "completed":
            return {"content": "文档已处理完成，但内容为空。"}
        else:  # 否则还在处理中或失败
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"文档状态为 '{document.status}'，文本处理尚未完成或失败，暂无内容。")

    full_content = "\n".join([c.content for c in chunks])
    return {"content": full_content}

@router.get("/knowledge-bases/{kb_id}/documents/{document_id}/chunks",
         response_model=List[schemas.KnowledgeDocumentChunkResponse], summary="获取知识文档文本块列表 (DEBUG)")
async def get_document_chunks(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
):
    """
    获取指定知识文档的所有文本块列表 (用于调试)。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试获取知识库 {kb_id} 中文档 {document_id} 的文本块。")
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    # 核心权限检查2：确保文档已经处理完成 (如果还在处理中，则没有文本块可返回或者不应该暴露)
    if document.status != "completed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="文档仍在处理中，文本块暂不可用。")

    # 检索对应文档的所有文本块
    chunks = db.query(KnowledgeDocumentChunk).filter(
        KnowledgeDocumentChunk.document_id == document_id,
        KnowledgeDocumentChunk.kb_id == kb_id,  # 确保文本块也属于这个知识库
        KnowledgeDocumentChunk.owner_id == current_user_id
    ).order_by(KnowledgeDocumentChunk.chunk_index).all()  # 按索引排序，方便查看

    print(f"DEBUG: 文档 {document_id} 获取到 {len(chunks)} 个文本块。")
    return chunks

# --- 后台处理函数 ---

async def process_document_in_background(
        document_id: int,
        owner_id: int,
        kb_id: int,
        oss_object_name: str,
        file_type: str,
        db_session: Session  # 传入会话
):
    """
    在后台处理上传的文档：提取文本、分块、生成嵌入并存储。
    文件从OSS下载后处理，而不是从本地文件系统读取。
    """
    print(f"DEBUG_DOC_PROCESS: 开始后台处理文档 ID: {document_id}")
    loop = asyncio.get_running_loop()
    db_document = None  # 初始化 db_document, 防止在try块中它未被赋值而finally块需要用
    try:
        # 获取文档对象 (需要在新的会话中获取，因为这是独立的任务)
        db_document = db_session.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
        if not db_document:
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 在后台处理中未找到。")
            return

        db_document.status = "processing"
        db_document.processing_message = "正在从云存储下载文件..."
        db_session.add(db_document)
        db_session.commit()

        # 从OSS下载文件内容
        downloaded_bytes = await oss_utils.download_file_from_oss(oss_object_name)
        if not downloaded_bytes:  # 如果下载失败或文件内容为空
            db_document.status = "failed"
            db_document.processing_message = "从云存储下载文件失败或文件内容为空。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 从OSS下载失败或内容为空。")
            return

        db_document.processing_message = "正在提取文本..."
        db_session.add(db_document)
        db_session.commit()

        # 1. 提取文本
        # 传递文件内容的字节流给 extract_text_from_document
        extracted_text = await loop.run_in_executor(
            None,  # 使用默认的线程池执行器
            extract_text_from_document,  # 要执行的同步函数
            downloaded_bytes,  # 传递字节流
            file_type  # 传递给函数的第二个参数
        )

        if not extracted_text:
            db_document.status = "failed"
            db_document.processing_message = "文本提取失败或文件内容为空。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 文本提取失败。")
            return

        # 2. 文本分块
        chunks = chunk_text(extracted_text)
        if not chunks:
            db_document.status = "failed"
            db_document.processing_message = "文本分块失败，可能文本过短。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 文本分块失败。")
            return

        db_document.processing_message = f"总计 {len(chunks)} 块，正在生成嵌入..."
        db_session.add(db_document)
        db_session.commit()

        # 3. 生成嵌入并存储
        # 获取文档所有者（知识库的owner）的LLM配置进行嵌入生成
        document_owner = db_session.query(Student).filter(Student.id == owner_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if document_owner and document_owner.llm_api_type == "siliconflow" and document_owner.llm_api_key_encrypted:
            try:
                owner_llm_api_key = decrypt_key(document_owner.llm_api_key_encrypted)
                owner_llm_type = document_owner.llm_api_type
                owner_llm_base_url = document_owner.llm_api_base_url
                # 优先使用新的多模型配置，fallback到原模型ID
                owner_llm_model_id = get_user_model_for_provider(
                    document_owner.llm_model_ids,
                    document_owner.llm_api_type,
                    document_owner.llm_model_id
                )
                print(f"DEBUG_EMBEDDING_KEY_DOC: 使用文档拥有者配置的硅基流动 API 密钥为文档生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY_DOC: 解密文档拥有者硅基流动 API 密钥失败: {e}。文档嵌入将使用零向量。")
        else:
            print(f"DEBUG_EMBEDDING_KEY_DOC: 文档拥有者未配置硅基流动 API 类型或密钥，文档嵌入将使用零向量或默认行为。")

        all_embeddings = await get_embeddings_from_api(
            chunks,
            api_key=owner_llm_api_key,
            llm_type=owner_llm_type,
            llm_base_url=owner_llm_base_url,
            llm_model_id=owner_llm_model_id
        )

        if not all_embeddings or len(all_embeddings) != len(chunks):
            db_document.status = "failed"
            db_document.processing_message = "嵌入生成失败或数量不匹配。请检查您的LLM配置。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 嵌入生成失败或数量不匹配。")
            return

        for i, chunk_content in enumerate(chunks):
            db_chunk = KnowledgeDocumentChunk(
                document_id=document_id,
                owner_id=owner_id,
                kb_id=kb_id,
                chunk_index=i,
                content=chunk_content,
                embedding=all_embeddings[i]
            )
            db_session.add(db_chunk)

        db_session.commit()  # 提交所有文本块

        # 4. 更新文档状态
        db_document.status = "completed"
        db_document.processing_message = f"文档处理完成，共 {len(chunks)} 个文本块。"
        db_document.total_chunks = len(chunks)
        db_session.add(db_document)
        db_session.commit()
        print(f"DEBUG_DOC_PROCESS: 文档 {document_id} 处理完成，{len(chunks)} 个块已嵌入。")

    except Exception as e:
        print(f"ERROR_DOC_PROCESS: 后台处理文档 {document_id} 发生未预期错误: {type(e).__name__}: {e}")
        # 尝试更新文档状态为失败
        if db_document:  # 仅当 db_document 已经被正确赋值后才尝试更新其状态
            try:
                db_document.status = "failed"
                db_document.processing_message = f"处理失败: {e}"
                db_session.add(db_document)
                db_session.commit()
            except Exception as update_e:
                print(f"CRITICAL_ERROR: 无法更新文档 {document_id} 的失败状态: {update_e}")
    finally:
        db_session.close()  # 确保会话关闭