# project/routers/collections_advanced/collections_advanced.py
"""
收藏管理系统的高级功能扩展
- 批量操作
- 统计分析
- 导入导出
- 分享协作
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Union, Tuple
from datetime import datetime, date, timedelta
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc, asc, text
import asyncio, uuid, json, csv, io, zipfile

from database import get_db
from models import Student, Folder, CollectedContent
from dependencies import get_current_user_id
import schemas
import oss_utils

router = APIRouter(
    prefix="/folders/advanced",
    tags=["高级收藏管理"],
    responses={404: {"description": "Not found"}},
)

# ================== 批量操作 API ==================

@router.post("/batch-operation", response_model=schemas.BatchOperationResponse, summary="批量操作收藏内容")
async def batch_operation(
    request: schemas.BatchOperationRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    对多个收藏内容执行批量操作
    支持移动、复制、删除、归档、标星等操作
    """
    success_count = 0
    failed_count = 0
    errors = []
    
    # 验证所有项目都属于当前用户
    items = db.query(CollectedContent).filter(
        CollectedContent.id.in_(request.item_ids),
        CollectedContent.owner_id == current_user_id
    ).all()
    
    if len(items) != len(request.item_ids):
        found_ids = {item.id for item in items}
        missing_ids = set(request.item_ids) - found_ids
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"以下项目不存在或无权访问: {list(missing_ids)}"
        )
    
    # 执行批量操作
    try:
        if request.operation == "move":
            success_count, errors = await _batch_move_items(
                db, items, request.target_folder_id, current_user_id
            )
        elif request.operation == "copy":
            success_count, errors = await _batch_copy_items(
                db, items, request.target_folder_id, current_user_id
            )
        elif request.operation == "delete":
            success_count, errors = await _batch_delete_items(
                db, items, background_tasks
            )
        elif request.operation == "archive":
            success_count, errors = await _batch_update_status(
                db, items, "archived"
            )
        elif request.operation == "star":
            success_count, errors = await _batch_update_starred(
                db, items, True
            )
        elif request.operation == "unstar":
            success_count, errors = await _batch_update_starred(
                db, items, False
            )
        elif request.operation == "tag":
            success_count, errors = await _batch_add_tags(
                db, items, request.tags or []
            )
        elif request.operation == "untag":
            success_count, errors = await _batch_remove_tags(
                db, items, request.tags or []
            )
        elif request.operation == "change_priority":
            success_count, errors = await _batch_update_priority(
                db, items, request.priority
            )
        elif request.operation == "change_status":
            success_count, errors = await _batch_update_status(
                db, items, request.status
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的操作类型: {request.operation}"
            )
        
        failed_count = len(request.item_ids) - success_count
        
    except Exception as e:
        failed_count = len(request.item_ids)
        errors.append({"error": str(e), "items": request.item_ids})
    
    return schemas.BatchOperationResponse(
        success_count=success_count,
        failed_count=failed_count,
        errors=errors if errors else None
    )

# ================== 统计分析 API ==================

@router.get("/stats", response_model=schemas.CollectionStatsResponse, summary="获取收藏统计信息")
async def get_collection_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    folder_id: Optional[int] = None,
    group_by: str = "day"
):
    """
    获取收藏的统计分析信息
    - 按类型、文件夹、日期分组统计
    - 存储空间使用统计
    - 最近活动和热门内容
    """
    # 基础统计查询
    base_query = db.query(CollectedContent).filter(
        CollectedContent.owner_id == current_user_id
    )
    
    if date_from:
        base_query = base_query.filter(CollectedContent.created_at >= date_from)
    if date_to:
        date_to_end = datetime.combine(date_to, datetime.max.time())
        base_query = base_query.filter(CollectedContent.created_at <= date_to_end)
    if folder_id:
        base_query = base_query.filter(CollectedContent.folder_id == folder_id)
    
    # 总计统计
    total_items = base_query.count()
    total_folders = db.query(Folder).filter(Folder.owner_id == current_user_id).count()
    
    # 按类型统计
    by_type = {}
    type_stats = base_query.with_entities(
        CollectedContent.type,
        func.count(CollectedContent.id).label('count')
    ).group_by(CollectedContent.type).all()
    
    for type_name, count in type_stats:
        by_type[type_name or 'unknown'] = count
    
    # 按文件夹统计
    by_folder = {}
    folder_stats = base_query.join(Folder, CollectedContent.folder_id == Folder.id).with_entities(
        Folder.name,
        func.count(CollectedContent.id).label('count')
    ).group_by(Folder.name).all()
    
    for folder_name, count in folder_stats:
        by_folder[folder_name] = count
    
    # 按日期统计
    by_date = []
    if group_by == "day":
        date_stats = base_query.with_entities(
            func.date(CollectedContent.created_at).label('date'),
            func.count(CollectedContent.id).label('count')
        ).group_by(func.date(CollectedContent.created_at)).order_by('date').all()
    elif group_by == "week":
        date_stats = base_query.with_entities(
            func.date_trunc('week', CollectedContent.created_at).label('date'),
            func.count(CollectedContent.id).label('count')
        ).group_by(func.date_trunc('week', CollectedContent.created_at)).order_by('date').all()
    elif group_by == "month":
        date_stats = base_query.with_entities(
            func.date_trunc('month', CollectedContent.created_at).label('date'),
            func.count(CollectedContent.id).label('count')
        ).group_by(func.date_trunc('month', CollectedContent.created_at)).order_by('date').all()
    else:
        date_stats = []
    
    for date_val, count in date_stats:
        by_date.append({
            "date": date_val.isoformat() if date_val else None,
            "count": count
        })
    
    # 存储统计
    storage_stats = base_query.with_entities(
        func.sum(CollectedContent.file_size).label('total_size')
    ).first()
    total_storage = storage_stats.total_size or 0
    
    storage_by_type = {}
    storage_type_stats = base_query.with_entities(
        CollectedContent.type,
        func.sum(CollectedContent.file_size).label('size')
    ).group_by(CollectedContent.type).all()
    
    for type_name, size in storage_type_stats:
        storage_by_type[type_name or 'unknown'] = size or 0
    
    # 最近活动（最近7天的收藏）
    recent_date = datetime.now() - timedelta(days=7)
    recent_items = base_query.filter(
        CollectedContent.created_at >= recent_date
    ).order_by(desc(CollectedContent.created_at)).limit(10).all()
    
    recent_activity = []
    for item in recent_items:
        recent_activity.append({
            "id": item.id,
            "title": item.title,
            "type": item.type,
            "created_at": item.created_at.isoformat(),
            "folder_id": item.folder_id
        })
    
    # 最常访问的内容
    top_accessed = base_query.filter(
        CollectedContent.access_count > 0
    ).order_by(desc(CollectedContent.access_count)).limit(10).all()
    
    top_accessed_list = []
    for item in top_accessed:
        top_accessed_list.append({
            "id": item.id,
            "title": item.title,
            "type": item.type,
            "access_count": item.access_count,
            "folder_id": item.folder_id
        })
    
    return schemas.CollectionStatsResponse(
        total_items=total_items,
        total_folders=total_folders,
        by_type=by_type,
        by_folder=by_folder,
        by_date=by_date,
        total_storage=total_storage,
        storage_by_type=storage_by_type,
        recent_activity=recent_activity,
        top_accessed=top_accessed_list
    )

# ================== 导入导出 API ==================

@router.post("/import", summary="导入收藏数据")
async def import_collections(
    file: UploadFile = File(..., description="导入文件"),
    request: schemas.ImportRequest = Depends(),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    从外部文件导入收藏数据
    支持浏览器书签、JSON、CSV、Markdown 格式
    """
    # 验证目标文件夹
    target_folder = None
    if request.target_folder_id:
        target_folder = db.query(Folder).filter(
            Folder.id == request.target_folder_id,
            Folder.owner_id == current_user_id
        ).first()
        if not target_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目标文件夹不存在或无权访问"
            )
    
    # 读取文件内容
    file_content = await file.read()
    
    imported_count = 0
    errors = []
    
    try:
        if request.source_type == "json":
            imported_count, errors = await _import_from_json(
                file_content, db, current_user_id, request
            )
        elif request.source_type == "csv":
            imported_count, errors = await _import_from_csv(
                file_content, db, current_user_id, request
            )
        elif request.source_type == "browser":
            imported_count, errors = await _import_from_browser_bookmarks(
                file_content, db, current_user_id, request
            )
        elif request.source_type == "markdown":
            imported_count, errors = await _import_from_markdown(
                file_content, db, current_user_id, request
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的导入格式: {request.source_type}"
            )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"导入失败: {str(e)}"
        )
    
    return {
        "message": f"导入完成，成功导入 {imported_count} 项",
        "imported_count": imported_count,
        "errors": errors if errors else None
    }

@router.post("/export", summary="导出收藏数据")
async def export_collections(
    request: schemas.ExportRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    导出收藏数据到文件
    支持 JSON、CSV、HTML、Markdown 格式
    """
    # 构建查询
    query = db.query(CollectedContent).filter(
        CollectedContent.owner_id == current_user_id
    )
    
    if request.folder_ids:
        query = query.filter(CollectedContent.folder_id.in_(request.folder_ids))
    
    items = query.all()
    
    # 生成导出文件
    if request.format == "json":
        export_data = await _export_to_json(items, db, request)
        filename = f"collections_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        media_type = "application/json"
    elif request.format == "csv":
        export_data = await _export_to_csv(items, db, request)
        filename = f"collections_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        media_type = "text/csv"
    elif request.format == "html":
        export_data = await _export_to_html(items, db, request)
        filename = f"collections_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        media_type = "text/html"
    elif request.format == "markdown":
        export_data = await _export_to_markdown(items, db, request)
        filename = f"collections_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        media_type = "text/markdown"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的导出格式: {request.format}"
        )
    
    # 上传到OSS并返回下载链接
    object_name = f"exports/{current_user_id}/{filename}"
    await oss_utils.upload_file_to_oss(
        export_data.encode('utf-8') if isinstance(export_data, str) else export_data,
        object_name,
        media_type
    )
    
    download_url = f"{oss_utils.S3_BASE_URL.rstrip('/')}/{object_name}"
    
    return {
        "download_url": download_url,
        "filename": filename,
        "exported_count": len(items)
    }

# ================== 辅助函数 ==================

async def _batch_move_items(db: Session, items: List[CollectedContent], target_folder_id: int, user_id: int):
    """批量移动项目到指定文件夹"""
    success_count = 0
    errors = []
    
    # 验证目标文件夹
    if target_folder_id:
        target_folder = db.query(Folder).filter(
            Folder.id == target_folder_id,
            Folder.owner_id == user_id
        ).first()
        if not target_folder:
            errors.append({"error": "目标文件夹不存在", "items": [item.id for item in items]})
            return 0, errors
    
    try:
        for item in items:
            item.folder_id = target_folder_id
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

async def _batch_copy_items(db: Session, items: List[CollectedContent], target_folder_id: int, user_id: int):
    """批量复制项目到指定文件夹"""
    success_count = 0
    errors = []
    
    # 验证目标文件夹
    if target_folder_id:
        target_folder = db.query(Folder).filter(
            Folder.id == target_folder_id,
            Folder.owner_id == user_id
        ).first()
        if not target_folder:
            errors.append({"error": "目标文件夹不存在", "items": [item.id for item in items]})
            return 0, errors
    
    try:
        for item in items:
            # 创建副本
            new_item = CollectedContent(
                owner_id=item.owner_id,
                folder_id=target_folder_id,
                title=f"{item.title} (副本)",
                type=item.type,
                url=item.url,
                content=item.content,
                tags=item.tags,
                priority=item.priority,
                notes=item.notes,
                is_starred=item.is_starred,
                thumbnail=item.thumbnail,
                author=item.author,
                duration=item.duration,
                file_size=item.file_size,
                status=item.status,
                shared_item_type=item.shared_item_type,
                shared_item_id=item.shared_item_id
            )
            db.add(new_item)
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

async def _batch_delete_items(db: Session, items: List[CollectedContent], background_tasks):
    """批量删除项目"""
    success_count = 0
    errors = []
    
    try:
        for item in items:
            # 如果有关联的OSS文件，添加到后台删除任务
            if item.url and item.url.startswith(oss_utils.S3_BASE_URL):
                object_name = item.url.replace(f"{oss_utils.S3_BASE_URL.rstrip('/')}/", "")
                if background_tasks:
                    background_tasks.add_task(oss_utils.delete_file_from_oss, object_name)
            
            db.delete(item)
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

async def _batch_update_starred(db: Session, items: List[CollectedContent], is_starred: bool):
    """批量更新星标状态"""
    success_count = 0
    errors = []
    
    try:
        for item in items:
            item.is_starred = is_starred
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

async def _batch_update_status(db: Session, items: List[CollectedContent], status: str):
    """批量更新状态"""
    success_count = 0
    errors = []
    
    try:
        for item in items:
            item.status = status
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

async def _batch_add_tags(db: Session, items: List[CollectedContent], tags: List[str]):
    """批量添加标签"""
    success_count = 0
    errors = []
    
    tags_str = ",".join(tags)
    
    try:
        for item in items:
            if item.tags:
                existing_tags = set(item.tags.split(","))
                new_tags = existing_tags.union(set(tags))
                item.tags = ",".join(new_tags)
            else:
                item.tags = tags_str
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

async def _batch_remove_tags(db: Session, items: List[CollectedContent], tags: List[str]):
    """批量移除标签"""
    success_count = 0
    errors = []
    
    tags_to_remove = set(tags)
    
    try:
        for item in items:
            if item.tags:
                existing_tags = set(item.tags.split(","))
                remaining_tags = existing_tags - tags_to_remove
                item.tags = ",".join(remaining_tags) if remaining_tags else None
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

async def _batch_update_priority(db: Session, items: List[CollectedContent], priority: int):
    """批量更新优先级"""
    success_count = 0
    errors = []
    
    try:
        for item in items:
            item.priority = priority
            success_count += 1
        
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append({"error": str(e), "items": [item.id for item in items]})
        success_count = 0
    
    return success_count, errors

# 导入导出辅助函数
async def _import_from_json(file_content: bytes, db: Session, user_id: int, request: schemas.ImportRequest):
    """从JSON文件导入"""
    data = json.loads(file_content.decode('utf-8'))
    imported_count = 0
    errors = []
    
    # JSON格式应该是 {"collections": [...], "folders": [...]}
    collections = data.get("collections", [])
    
    for item_data in collections:
        try:
            # 创建收藏项
            new_item = CollectedContent(
                owner_id=user_id,
                folder_id=request.target_folder_id,
                title=item_data.get("title", "导入项目"),
                type=item_data.get("type", "link"),
                url=item_data.get("url"),
                content=item_data.get("content"),
                tags=item_data.get("tags"),
                priority=item_data.get("priority"),
                notes=item_data.get("notes"),
                is_starred=item_data.get("is_starred", False)
            )
            db.add(new_item)
            imported_count += 1
        except Exception as e:
            errors.append({"error": str(e), "item": item_data})
    
    db.commit()
    return imported_count, errors

async def _import_from_csv(file_content: bytes, db: Session, user_id: int, request: schemas.ImportRequest):
    """从CSV文件导入"""
    csv_data = file_content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(csv_data))
    
    imported_count = 0
    errors = []
    
    for row in reader:
        try:
            new_item = CollectedContent(
                owner_id=user_id,
                folder_id=request.target_folder_id,
                title=row.get("title", "导入项目"),
                type=row.get("type", "link"),
                url=row.get("url"),
                content=row.get("content"),
                tags=row.get("tags"),
                notes=row.get("notes")
            )
            db.add(new_item)
            imported_count += 1
        except Exception as e:
            errors.append({"error": str(e), "row": row})
    
    db.commit()
    return imported_count, errors

async def _export_to_json(items: List[CollectedContent], db: Session, request: schemas.ExportRequest):
    """导出到JSON格式"""
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "total_items": len(items),
        "collections": []
    }
    
    for item in items:
        item_data = {
            "id": item.id,
            "title": item.title,
            "type": item.type,
            "url": item.url,
            "content": item.content if request.include_content else None,
            "tags": item.tags,
            "created_at": item.created_at.isoformat(),
        }
        
        if request.include_metadata:
            item_data.update({
                "priority": item.priority,
                "notes": item.notes,
                "is_starred": item.is_starred,
                "status": item.status,
                "author": item.author,
                "file_size": item.file_size,
                "access_count": item.access_count
            })
        
        export_data["collections"].append(item_data)
    
    return json.dumps(export_data, ensure_ascii=False, indent=2)

async def _export_to_csv(items: List[CollectedContent], db: Session, request: schemas.ExportRequest):
    """导出到CSV格式"""
    output = io.StringIO()
    
    fieldnames = ["title", "type", "url", "tags", "created_at"]
    if request.include_content:
        fieldnames.append("content")
    if request.include_metadata:
        fieldnames.extend(["priority", "notes", "is_starred", "status", "author"])
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for item in items:
        row = {
            "title": item.title,
            "type": item.type,
            "url": item.url,
            "tags": item.tags,
            "created_at": item.created_at.isoformat()
        }
        
        if request.include_content:
            row["content"] = item.content
        
        if request.include_metadata:
            row.update({
                "priority": item.priority,
                "notes": item.notes,
                "is_starred": item.is_starred,
                "status": item.status,
                "author": item.author
            })
        
        writer.writerow(row)
    
    return output.getvalue()

async def _export_to_markdown(items: List[CollectedContent], db: Session, request: schemas.ExportRequest):
    """导出到Markdown格式"""
    md_content = f"# 收藏导出\n\n导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n总数: {len(items)} 项\n\n"
    
    # 按类型分组
    by_type = {}
    for item in items:
        item_type = item.type or "其他"
        if item_type not in by_type:
            by_type[item_type] = []
        by_type[item_type].append(item)
    
    for type_name, type_items in by_type.items():
        md_content += f"## {type_name.upper()}\n\n"
        
        for item in type_items:
            md_content += f"### {item.title}\n\n"
            
            if item.url:
                md_content += f"链接: [{item.url}]({item.url})\n\n"
            
            if request.include_content and item.content:
                md_content += f"内容: {item.content}\n\n"
            
            if item.tags:
                md_content += f"标签: {item.tags}\n\n"
            
            if request.include_metadata:
                md_content += f"创建时间: {item.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                if item.is_starred:
                    md_content += "⭐ 已加星标\n\n"
            
            md_content += "---\n\n"
    
    return md_content


# ================== 辅助函数实现 ==================

async def _import_from_browser_bookmarks(data: bytes, folder_id: int, db: Session, current_user_id: int) -> Tuple[int, List]:
    """从浏览器书签导入"""
    import json
    try:
        bookmarks_data = json.loads(data.decode('utf-8'))
        imported_count = 0
        errors = []
        
        # 简化的书签导入逻辑
        def process_bookmark_folder(folder_data, parent_folder_id=None):
            nonlocal imported_count, errors
            
            if 'children' in folder_data:
                for child in folder_data['children']:
                    try:
                        if child.get('type') == 'url' and child.get('url'):
                            # 创建收藏内容
                            content = CollectedContent(
                                title=child.get('name', ''),
                                url=child.get('url'),
                                type='link',
                                folder_id=parent_folder_id or folder_id,
                                owner_id=current_user_id
                            )
                            db.add(content)
                            imported_count += 1
                        elif child.get('type') == 'folder':
                            # 递归处理子文件夹
                            process_bookmark_folder(child, parent_folder_id or folder_id)
                    except Exception as e:
                        errors.append(f"导入书签失败: {str(e)}")
        
        if 'roots' in bookmarks_data:
            for root_key, root_data in bookmarks_data['roots'].items():
                process_bookmark_folder(root_data, folder_id)
        
        db.commit()
        return imported_count, errors
        
    except Exception as e:
        return 0, [f"解析书签文件失败: {str(e)}"]


async def _import_from_markdown(data: bytes, folder_id: int, db: Session, current_user_id: int) -> Tuple[int, List]:
    """从Markdown文件导入"""
    try:
        content = data.decode('utf-8')
        imported_count = 0
        errors = []
        
        # 简单的Markdown链接提取
        import re
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        matches = re.findall(link_pattern, content)
        
        for title, url in matches:
            try:
                content_item = CollectedContent(
                    title=title,
                    url=url,
                    type='link',
                    folder_id=folder_id,
                    owner_id=current_user_id
                )
                db.add(content_item)
                imported_count += 1
            except Exception as e:
                errors.append(f"导入链接失败: {title} - {str(e)}")
        
        db.commit()
        return imported_count, errors
        
    except Exception as e:
        return 0, [f"解析Markdown文件失败: {str(e)}"]


async def _export_to_html(items: List[CollectedContent], db: Session, request) -> str:
    """导出为HTML格式"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>收藏夹导出</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .item { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
            .title { font-size: 18px; font-weight: bold; color: #333; }
            .url { color: #0066cc; text-decoration: none; }
            .meta { color: #666; font-size: 12px; margin-top: 10px; }
            .content { margin: 10px 0; }
            .starred { color: #ff9500; }
        </style>
    </head>
    <body>
        <h1>我的收藏夹</h1>
    """
    
    for item in items:
        html_content += '<div class="item">'
        
        # 标题
        if item.url:
            html_content += f'<div class="title"><a href="{item.url}" class="url">{item.title or "无标题"}</a>'
        else:
            html_content += f'<div class="title">{item.title or "无标题"}'
        
        if item.is_starred:
            html_content += ' <span class="starred">⭐</span>'
        html_content += '</div>'
        
        # 内容
        if item.content:
            html_content += f'<div class="content">{item.content}</div>'
        
        # 元数据
        if request.include_metadata:
            html_content += f'<div class="meta">创建时间: {item.created_at.strftime("%Y-%m-%d %H:%M:%S")}</div>'
        
        html_content += '</div>'
    
    html_content += """
    </body>
    </html>
    """
    
    return html_content
