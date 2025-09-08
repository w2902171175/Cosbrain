# project/routers/course_notes/course_notes.py
"""
课程笔记模块优化版本 - 应用统一优化模式
以文件夹为中心的笔记管理系统（统一优化版本）

基于成功优化模式，优化course_notes模块

主要改进：
1. 所有笔记都必须属于某个文件夹（默认文件夹或用户创建的文件夹）
2. 提供基于文件夹的层级管理和组织
3. 简化课程关联逻辑，将其作为笔记的属性而非组织结构
4. 增强文件夹的统计和管理功能
5. 智能接口设计，单一接口支持多种请求格式
6. 完整的批量操作和高级搜索功能

统一优化特性：
- 使用@optimized_route装饰器（已包含错误处理）
- 统一的database_transaction事务管理
- 异步任务处理和缓存优化
- 专业服务类和工具函数
- 统一错误处理和响应格式
- 优化数据库查询，减少N+1问题
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query, Path, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Any, Dict
from datetime import datetime
import json
import logging

# 核心依赖
from project.database import get_db
from project.models import Note, Course, Folder, User
from project.utils import get_current_user_id
import project.schemas as schemas
import project.oss_utils as oss_utils

# 优化工具导入
from project.services.course_notes_service import (
    CourseNotesFolderService, CourseNotesService, CourseNotesUtils,
    CourseNotesEmbeddingService
)
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route, router_optimizer
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

# 导入工具函数
from project.utils.core.course_notes_utils import (
    parse_note_data_from_request, validate_folder_access,
    validate_batch_operation_limit, log_operation
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/course-notes",
    tags=["课程笔记管理"],
    responses={404: {"description": "Not found"}},
)

# ==================== 文件夹管理接口 ====================

@router.post("/", response_model=schemas.FolderResponseNew, summary="创建文件夹")
@optimized_route("创建课程笔记文件夹")
async def create_folder(
    background_tasks: BackgroundTasks,
    folder_data: schemas.FolderCreateNew,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    创建新的文件夹 - 优化版本
    如果不指定parent_id，则创建为根级文件夹。
    """
    log_operation("创建文件夹", current_user_id, f"文件夹名: {folder_data.name}")
    
    # 验证输入数据
    validated_data = CourseNotesUtils.validate_folder_data(folder_data.dict())
    
    # 验证父文件夹是否存在且属于当前用户
    if validated_data.get("parent_id"):
        parent_folder = validate_folder_access(
            validated_data["parent_id"], current_user_id, db, allow_none=False
        )
    
    # 使用事务创建文件夹
    with database_transaction(db):
        db_folder = CourseNotesFolderService.create_folder_optimized(
            db, current_user_id, validated_data
        )
        
        # 异步初始化文件夹
        submit_background_task(
            background_tasks,
            "initialize_course_notes_folder",
            {"folder_id": db_folder.id, "user_id": current_user_id},
            priority=TaskPriority.LOW
        )
    
    logger.info(f"文件夹 {db_folder.id} 创建成功")
    return CourseNotesUtils.format_folder_response(db_folder)

@router.get("/", response_model=List[schemas.FolderResponseNew], summary="获取用户的文件夹树")
@optimized_route("获取课程笔记文件夹树")
async def get_user_folders(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取用户的文件夹树 - 优化版本
    返回层级结构的文件夹列表，包含每个文件夹的笔记数量统计。
    """
    folders = CourseNotesFolderService.get_user_folders_tree_optimized(db, current_user_id)
    return [CourseNotesUtils.format_folder_response(folder) for folder in folders]

@router.get("/{folder_id}", response_model=schemas.FolderResponseNew, summary="获取文件夹详情")
@optimized_route("获取课程笔记文件夹详情")
async def get_folder_detail(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取文件夹详情 - 优化版本
    包含文件夹的基本信息、子文件夹和笔记数量统计。
    """
    folder = CourseNotesFolderService.get_folder_optimized(db, folder_id, current_user_id)
    return CourseNotesUtils.format_folder_response(folder)

@router.put("/{folder_id}", response_model=schemas.FolderResponseNew, summary="更新文件夹")
@optimized_route("更新课程笔记文件夹")
async def update_folder(
    folder_id: int,
    folder_data: schemas.FolderUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    更新文件夹信息 - 优化版本
    可以更新名称、描述、父文件夹等信息。
    """
    log_operation("更新文件夹", current_user_id, f"文件夹ID: {folder_id}")
    
    # 验证输入数据
    update_data = CourseNotesUtils.validate_folder_data(
        folder_data.dict(exclude_unset=True)
    )
    
    # 使用事务更新
    with database_transaction(db):
        folder = CourseNotesFolderService.update_folder_optimized(
            db, folder_id, current_user_id, update_data
        )
    
    logger.info(f"文件夹 {folder_id} 更新成功")
    return CourseNotesUtils.format_folder_response(folder)

@router.delete("/{folder_id}", summary="删除文件夹")
@optimized_route("删除课程笔记文件夹")
async def delete_folder(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    删除文件夹 - 优化版本
    只能删除空文件夹（无子文件夹和笔记）。
    """
    log_operation("删除文件夹", current_user_id, f"文件夹ID: {folder_id}")
    
    # 使用事务删除
    with database_transaction(db):
        CourseNotesFolderService.delete_folder_optimized(db, folder_id, current_user_id)
    
    logger.info(f"文件夹 {folder_id} 删除成功")
    return {"message": "Folder deleted successfully", "folder_id": folder_id}

# ==================== 笔记管理接口 ====================

@router.post("/{folder_id}/notes", response_model=schemas.NoteResponse, summary="在指定文件夹中创建笔记")
@optimized_route("创建课程笔记")
async def create_note_in_folder(
    folder_id: int,
    background_tasks: BackgroundTasks,
    note_data: Optional[schemas.NoteBase] = None,
    note_data_json: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    在指定文件夹中创建笔记 - 优化版本
    支持JSON和multipart/form-data两种请求格式，可以同时上传文件。
    """
    log_operation("创建笔记", current_user_id, f"文件夹ID: {folder_id}")
    
    # 解析笔记数据
    parsed_note_data = parse_note_data_from_request(note_data, note_data_json, file)
    
    # 验证文件夹访问权限
    validate_folder_access(folder_id, current_user_id, db)
    
    # 验证笔记数据
    validated_data = CourseNotesUtils.validate_note_data(parsed_note_data.dict())
    
    # 处理文件上传
    file_path = None
    if file:
        try:
            file_path = await oss_utils.upload_file(file, "course_notes")
            validated_data["file_path"] = file_path
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"文件上传失败: {str(e)}"
            )
    
    # 使用事务创建笔记
    with database_transaction(db):
        # 生成嵌入向量
        embedding = await CourseNotesEmbeddingService.generate_note_embedding_optimized(
            validated_data["title"], validated_data["content"], validated_data.get("tags")
        )
        
        # 创建笔记
        db_note = CourseNotesService.create_note_optimized(
            db, current_user_id, folder_id, validated_data, embedding
        )
        
        # 异步处理笔记分析
        submit_background_task(
            background_tasks,
            "analyze_course_note",
            {"note_id": db_note.id, "user_id": current_user_id},
            priority=TaskPriority.LOW
        )
    
    logger.info(f"笔记 {db_note.id} 创建成功")
    return CourseNotesUtils.format_note_response(db_note)

@router.get("/{folder_id}/notes", response_model=List[schemas.NoteResponse], summary="获取文件夹中的笔记")
@optimized_route("获取文件夹笔记列表")
async def get_folder_notes(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    course_id: Optional[int] = Query(None, description="按课程过滤"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向")
):
    """
    获取文件夹中的笔记 - 优化版本
    支持分页、按课程过滤和排序。
    """
    # 验证文件夹访问权限
    validate_folder_access(folder_id, current_user_id, db)
    
    # 获取笔记列表
    notes, total_count = CourseNotesService.get_folder_notes_optimized(
        db, folder_id, current_user_id,
        page=page, page_size=page_size,
        course_id=course_id,
        sort_by=sort_by, sort_order=sort_order
    )
    
    # 格式化响应
    formatted_notes = [CourseNotesUtils.format_note_response(note) for note in notes]
    
    # 添加分页信息到响应头
    response_data = {
        "notes": formatted_notes,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total_count,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    }
    
    return formatted_notes

@router.get("/notes/{note_id}", response_model=schemas.NoteResponse, summary="获取指定笔记详情")
@optimized_route("获取课程笔记详情")
async def get_note_detail(
    note_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取指定笔记详情 - 优化版本
    返回笔记的完整信息，包括关联的课程和文件夹信息。
    """
    note = CourseNotesService.get_note_optimized(db, note_id, current_user_id)
    return CourseNotesUtils.format_note_response(note)

@router.get("/notes", response_model=List[schemas.NoteResponse], summary="获取用户所有笔记")
@optimized_route("获取用户所有课程笔记")
async def get_user_notes(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    course_id: Optional[int] = Query(None, description="按课程过滤"),
    folder_id: Optional[int] = Query(None, description="按文件夹过滤"),
    sort_by: str = Query("updated_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向")
):
    """
    获取用户所有笔记 - 优化版本
    支持多维度过滤、分页和排序。
    """
    # 如果指定了文件夹，使用文件夹笔记查询
    if folder_id:
        validate_folder_access(folder_id, current_user_id, db)
        notes, total_count = CourseNotesService.get_folder_notes_optimized(
            db, folder_id, current_user_id,
            page=page, page_size=page_size,
            course_id=course_id,
            sort_by=sort_by, sort_order=sort_order
        )
    else:
        # 获取所有笔记的逻辑需要在服务类中实现
        # 这里简化处理，实际应该添加到服务类中
        from sqlalchemy import desc, asc
        
        query = db.query(Note).filter(Note.owner_id == current_user_id)
        
        if course_id:
            query = query.filter(Note.course_id == course_id)
        
        total_count = query.count()
        
        # 排序
        order_field = getattr(Note, sort_by, Note.updated_at)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(order_field))
        else:
            query = query.order_by(asc(order_field))
        
        # 分页
        offset = (page - 1) * page_size
        notes = query.offset(offset).limit(page_size).all()
    
    # 格式化响应
    formatted_notes = [CourseNotesUtils.format_note_response(note) for note in notes]
    
    return formatted_notes

@router.put("/notes/{note_id}", response_model=schemas.NoteResponse, summary="更新笔记")
@optimized_route("更新课程笔记")
async def update_note(
    note_id: int,
    background_tasks: BackgroundTasks,
    note_data: schemas.NoteUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    更新笔记 - 优化版本
    可以更新标题、内容、课程关联、标签等信息。
    """
    log_operation("更新笔记", current_user_id, f"笔记ID: {note_id}")
    
    # 验证输入数据
    update_data = CourseNotesUtils.validate_note_data(
        note_data.dict(exclude_unset=True)
    )
    
    # 使用事务更新
    with database_transaction(db):
        # 如果更新了关键内容，重新生成嵌入向量
        new_embedding = None
        if any(key in update_data for key in ["title", "content", "tags"]):
            note = CourseNotesService.get_note_optimized(db, note_id, current_user_id)
            
            new_title = update_data.get("title", note.title)
            new_content = update_data.get("content", note.content)
            new_tags = update_data.get("tags", note.tags)
            
            new_embedding = await CourseNotesEmbeddingService.generate_note_embedding_optimized(
                new_title, new_content, new_tags
            )
        
        # 更新笔记
        updated_note = CourseNotesService.update_note_optimized(
            db, note_id, current_user_id, update_data, new_embedding
        )
        
        # 异步处理更新后的分析
        submit_background_task(
            background_tasks,
            "reanalyze_course_note",
            {"note_id": note_id, "user_id": current_user_id},
            priority=TaskPriority.LOW
        )
    
    logger.info(f"笔记 {note_id} 更新成功")
    return CourseNotesUtils.format_note_response(updated_note)

@router.delete("/notes/{note_id}", summary="删除笔记")
@optimized_route("删除课程笔记")
async def delete_note(
    note_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    删除笔记 - 优化版本
    同时删除关联的文件（如果有）。
    """
    log_operation("删除笔记", current_user_id, f"笔记ID: {note_id}")
    
    # 使用事务删除
    with database_transaction(db):
        CourseNotesService.delete_note_optimized(db, note_id, current_user_id)
    
    logger.info(f"笔记 {note_id} 删除成功")
    return {"message": "Note deleted successfully", "note_id": note_id}

@router.post("/notes/{note_id}/move", response_model=schemas.NoteResponse, summary="移动笔记到其他文件夹")
@optimized_route("移动课程笔记")
async def move_note(
    note_id: int,
    target_folder_id: int = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    移动笔记到其他文件夹 - 优化版本
    """
    log_operation("移动笔记", current_user_id, f"笔记ID: {note_id} -> 文件夹ID: {target_folder_id}")
    
    # 使用事务移动
    with database_transaction(db):
        moved_note = CourseNotesService.move_note_optimized(
            db, note_id, current_user_id, target_folder_id
        )
    
    logger.info(f"笔记 {note_id} 移动成功")
    return CourseNotesUtils.format_note_response(moved_note)

# ==================== 批量操作接口 ====================

@router.post("/notes/batch-move", summary="批量移动笔记")
@optimized_route("批量移动课程笔记")
async def batch_move_notes(
    note_ids: List[int] = Form(...),
    target_folder_id: int = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    批量移动笔记到指定文件夹 - 优化版本
    """
    log_operation("批量移动笔记", current_user_id, f"笔记数量: {len(note_ids)}")
    
    # 验证批量操作限制
    validate_batch_operation_limit(note_ids)
    
    # 使用事务批量移动
    with database_transaction(db):
        result = CourseNotesService.batch_move_notes_optimized(
            db, note_ids, current_user_id, target_folder_id
        )
    
    logger.info(f"批量移动完成，成功: {result['success_count']}, 失败: {result['failed_count']}")
    return result

@router.delete("/notes/batch-delete", summary="批量删除笔记")
@optimized_route("批量删除课程笔记")
async def batch_delete_notes(
    note_ids: List[int] = Form(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    批量删除笔记 - 优化版本
    """
    log_operation("批量删除笔记", current_user_id, f"笔记数量: {len(note_ids)}")
    
    # 验证批量操作限制
    validate_batch_operation_limit(note_ids)
    
    # 使用事务批量删除
    with database_transaction(db):
        result = CourseNotesService.batch_delete_notes_optimized(
            db, note_ids, current_user_id
        )
    
    logger.info(f"批量删除完成，成功: {result['success_count']}, 失败: {result['failed_count']}")
    return result

# ==================== 搜索和统计接口 ====================

@router.get("/search", response_model=List[schemas.NoteResponse], summary="搜索笔记")
@optimized_route("搜索课程笔记")
async def search_notes(
    query: str = Query(..., description="搜索关键词"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    folder_id: Optional[int] = Query(None, description="限制在指定文件夹内搜索"),
    course_id: Optional[int] = Query(None, description="限制在指定课程内搜索"),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量")
):
    """
    搜索笔记 - 优化版本
    支持关键词搜索和语义搜索，可以限制搜索范围。
    """
    logger.info(f"用户 {current_user_id} 搜索课程笔记，关键词: {query}")
    
    # 执行搜索
    search_results = await CourseNotesService.search_notes_optimized(
        db, current_user_id, query, folder_id, course_id, limit
    )
    
    # 格式化搜索结果
    formatted_results = []
    for note, similarity_score in search_results:
        note_data = CourseNotesUtils.format_note_response(note)
        note_data["similarity_score"] = similarity_score
        formatted_results.append(note_data)
    
    return formatted_results

@router.get("/stats", response_model=schemas.FolderStatsResponse, summary="获取统计信息")
@optimized_route("获取课程笔记统计")
async def get_notes_statistics(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    folder_id: Optional[int] = Query(None, description="指定文件夹的统计")
):
    """
    获取笔记统计信息 - 优化版本
    包括总数、分布、最近活动等统计数据。
    """
    logger.info(f"获取用户 {current_user_id} 的课程笔记统计")
    
    # 如果指定了文件夹，验证访问权限
    if folder_id:
        validate_folder_access(folder_id, current_user_id, db)
    
    # 获取统计信息
    statistics = CourseNotesService.get_notes_statistics_optimized(
        db, current_user_id, folder_id
    )
    
    return statistics

# ==================== 导出功能 ====================

@router.get("/export", summary="导出笔记")
@optimized_route("导出课程笔记")
async def export_notes(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    format: str = Query("json", description="导出格式（json/markdown/txt）"),
    folder_id: Optional[int] = Query(None, description="指定文件夹"),
    course_id: Optional[int] = Query(None, description="指定课程")
):
    """
    导出笔记 - 优化版本
    支持多种格式导出，可以按文件夹或课程过滤。
    """
    logger.info(f"用户 {current_user_id} 导出课程笔记，格式: {format}")
    
    # 构建查询
    query = db.query(Note).filter(Note.owner_id == current_user_id)
    
    if folder_id:
        validate_folder_access(folder_id, current_user_id, db)
        query = query.filter(Note.folder_id == folder_id)
    
    if course_id:
        query = query.filter(Note.course_id == course_id)
    
    notes = query.order_by(Note.created_at.asc()).all()
    
    # 根据格式处理数据
    export_data = CourseNotesService.export_notes_optimized(notes, format)
    
    return export_data

# ==================== 公开文件夹管理接口（已废弃，迁移至收藏模块） ====================
# 注意：公开文件夹的发现功能已迁移到 program_collections 模块
# 请使用以下API替代：
# - GET /program-collections/discover/note-folders
# - 收藏功能：POST /program-collections/note_folder/{folder_id}/star
#
# 下面的接口保留是为了向后兼容，建议逐步迁移到新的统一收藏系统

# 注释掉重复的发现API，保留在 program_collections 模块中
# 但保留管理类API如 toggle_folder_visibility

# @router.get("/public", response_model=List[schemas.FolderResponseNew], summary="获取公开的课程笔记文件夹（已废弃）")
# @router.get("/public/search", response_model=List[schemas.FolderResponseNew], summary="搜索公开的课程笔记文件夹（已废弃）")  
# @router.get("/public/{folder_id}", response_model=schemas.FolderResponseNew, summary="获取公开文件夹详情（已废弃）")
# 这些API已迁移到 /program-collections/discover/note-folders

@router.patch("/{folder_id}/visibility", response_model=schemas.FolderResponseNew, summary="切换文件夹公开状态")
@optimized_route("切换文件夹公开状态")
async def toggle_folder_visibility(
    folder_id: int,
    visibility_data: schemas.FolderVisibilityUpdate,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    切换文件夹的公开/私密状态
    只有文件夹所有者可以修改
    """
    log_operation("切换文件夹公开状态", current_user_id, f"文件夹ID: {folder_id}, 设为公开: {visibility_data.is_public}")
    
    # 验证文件夹所有权
    folder = validate_folder_access(folder_id, current_user_id, db, allow_none=False)
    
    # 使用事务更新
    with database_transaction(db):
        update_data = {"is_public": visibility_data.is_public}
        folder = CourseNotesFolderService.update_folder_optimized(
            db, folder_id, current_user_id, update_data
        )
        
        # 清除公开文件夹缓存
        cache_manager.delete_pattern("public_course_notes_folders:*")
        cache_manager.delete_pattern("search_public_folders:*")
    
    # 异步记录状态变更
    submit_background_task(
        background_tasks,
        "log_folder_visibility_change",
        {
            "user_id": current_user_id,
            "folder_id": folder_id,
            "is_public": visibility_data.is_public,
            "timestamp": datetime.now().isoformat()
        },
        priority=TaskPriority.MEDIUM
    )
    
    logger.info(f"文件夹 {folder_id} 公开状态已更新为: {'公开' if visibility_data.is_public else '私密'}")
    return CourseNotesUtils.format_folder_response(folder)

# 模块加载日志
logger.info("📝 Course Notes Module - 课程笔记模块已加载（统一优化版本）")
