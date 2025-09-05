# project/routers/collections/program_collections.py
"""
统一收藏和发现功能API - 优化版本

提供简化的收藏体验，用户可以像GitHub星标一样快速收藏/取消收藏各种类型的内容
统一整合了项目、课程、知识库、课程笔记文件夹的发现和收藏功能

核心特性：
1. 一键收藏/取消收藏四种类型的内容（项目、课程、知识库、笔记文件夹）
2. 统一的收藏管理界面，支持分类查看和搜索
3. 获取用户收藏的内容列表，支持分类查看
4. 检查特定内容的收藏状态
5. 收藏数统计和热门内容推荐
6. 批量收藏操作支持
7. 与现有的收藏系统完全集成

支持的内容类型：
- project: 项目
- course: 课程  
- knowledge_base: 知识库（仅限公开的）
- note_folder: 课程笔记文件夹（仅限公开的）

统一优化特性：
- 使用@optimized_route和@handle_database_errors装饰器
- 统一的database_transaction事务管理
- 异步任务处理和缓存优化
- 专业服务类和工具函数
- 统一错误处理和响应格式
- 优化数据库查询，减少N+1问题
- 批量操作支持

API整合说明：
- 本模块整合了原本分散在各模块的公开内容发现功能
- 替代了 course_notes 模块中的 /public 相关API
- 为知识库新增了发现功能
- 提供完整的发现→收藏→管理流程
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Literal

# FastAPI核心依赖
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc

# 项目核心依赖
from project.database import get_db
from project.models import (
    Project, Course, CollectedContent, Folder,
    KnowledgeBase, Note
)
from project.utils import get_current_user_id
import project.schemas as schemas

# 业务工具函数
from project.utils.core.collections_utils import (
    get_or_create_collection_folder,
    check_item_exists,
    check_already_collected,
    create_collection_item,
    handle_like_logic,
    get_collection_status,
    unstar_item,
    format_star_response,
    CollectionManager
)
from project.config.collections_config import COLLECTION_CONFIGS
from project.services.collections_batch_service import OptimizedBatchOperations

# 业务服务层
from project.services.collections_service import (
    CollectionsFolderService, 
    CollectedContentService, 
    CollectionsUtils
)

# 优化工具
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager

# 装饰器
from project.utils.core.decorators import log_operation

# 配置日志和路由器
logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/program-collections",
    tags=["统一收藏和发现"],
    responses={404: {"description": "Not found"}},
)

# ==================== 核心收藏功能 ====================

@router.post("/{item_type}/{item_id}/star", summary="收藏项目、课程、知识库或笔记文件夹")
@optimized_route("收藏项目或课程")
@handle_database_errors
async def star_item(
    item_type: Literal["project", "course", "knowledge_base", "note_folder"],
    item_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    收藏一个项目、课程、知识库或笔记文件夹 - 优化版本
    - 支持项目、课程、知识库、笔记文件夹的统一收藏接口
    - 如果已收藏，返回409冲突错误
    - 收藏成功后会在用户的默认收藏文件夹中创建收藏记录
    - 对于项目和课程，同时会在点赞表中创建点赞记录（保持点赞和收藏的一致性）
    - 知识库和笔记文件夹只支持收藏，不支持点赞
    """
    logger.info(f"用户 {current_user_id} 尝试收藏{item_type} ID: {item_id}")
    
    # 1. 验证项目/课程是否存在
    item = await check_item_exists(db, item_type, item_id)
    
    # 2. 检查是否已经收藏过
    if await check_already_collected(db, current_user_id, item_type, item_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail=f"已经收藏过该{item_type}"
        )
    
    # 3. 使用事务管理
    with database_transaction(db):
        # 获取或创建收藏文件夹
        folder = await get_or_create_collection_folder(db, current_user_id, item_type)
        
        # 创建收藏记录
        collection_item = await create_collection_item(
            db, current_user_id, folder, item, item_type, item_id
        )
        
        # 处理点赞逻辑
        also_liked = await handle_like_logic(
            db, current_user_id, item, item_type, item_id
        )
    
    logger.info(f"用户 {current_user_id} 成功收藏{item_type} {item_id}")
    return format_star_response(
        collection_item, item, folder, item_type, item_id, also_liked
    )

@router.delete("/{item_type}/{item_id}/unstar", status_code=status.HTTP_204_NO_CONTENT, summary="取消收藏项目、课程、知识库或笔记文件夹")
@optimized_route("取消收藏项目或课程")
@handle_database_errors
async def unstar_item_endpoint(
    item_type: Literal["project", "course", "knowledge_base", "note_folder"],
    item_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    取消收藏一个项目、课程、知识库或笔记文件夹 - 优化版本
    - 会删除收藏记录但保留点赞记录（仅对项目和课程，用户可能想保留点赞但不收藏）
    - 知识库和笔记文件夹只删除收藏记录
    """
    logger.info(f"用户 {current_user_id} 尝试取消收藏{item_type} ID: {item_id}")
    
    with database_transaction(db):
        await unstar_item(db, current_user_id, item_type, item_id)
    
    logger.info(f"用户 {current_user_id} 成功取消收藏{item_type} {item_id}")

@router.get("/{item_type}/{item_id}/star-status", summary="检查项目、课程、知识库或笔记文件夹收藏状态")
@optimized_route("检查收藏状态")
@handle_database_errors
async def check_star_status(
    item_type: Literal["project", "course", "knowledge_base", "note_folder"],
    item_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    检查当前用户是否已收藏指定项目、课程、知识库或笔记文件夹 - 优化版本
    """
    # 验证项目/课程是否存在
    item = await check_item_exists(db, item_type, item_id)
    
    # 获取收藏和点赞状态
    status_info = await get_collection_status(db, current_user_id, item_type, item_id)
    
    # 根据类型获取不同的标题字段
    if item_type in ["project", "course", "knowledge_base"]:
        title_field = "title"
        total_likes = getattr(item, "likes_count", 0) or 0 if item_type in ["project", "course"] else 0
    elif item_type == "note_folder":
        title_field = "name"  # 笔记文件夹使用name字段
        total_likes = 0  # 笔记文件夹不支持点赞
    else:
        title_field = "title"
        total_likes = 0
    
    return {
        f"{item_type}_id": item_id,
        f"{item_type}_title": getattr(item, title_field, ""),
        **status_info,
        "total_likes": total_likes
    }

# ==================== 收藏管理功能 ====================

@router.get("/my-starred/{item_type}", summary="获取我收藏的项目、课程、知识库或笔记文件夹列表")
@optimized_route("获取收藏列表")
@handle_database_errors
async def get_my_starred_items(
    item_type: Literal["project", "course", "knowledge_base", "note_folder"],
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    sort_by: Literal["created_at", "title", "updated_at"] = Query("created_at", description="排序字段"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="排序方向")
):
    """
    获取当前用户收藏的项目、课程、知识库或笔记文件夹列表（优化版本，减少N+1查询）
    """
    offset = (page - 1) * page_size
    
    # 构建查询 - 使用joinedload优化
    config = COLLECTION_CONFIGS[item_type]
    model = config["model"]
    like_model = config["like_model"]
    like_field = config["like_field"]
    
    # 使用子查询获取收藏的ID列表
    subquery = db.query(CollectedContent.shared_item_id).filter(
        and_(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.shared_item_type == item_type,
            CollectedContent.status == "active"
        )
    ).subquery()
    
    # 主查询 - 一次性获取所有需要的数据
    main_query = db.query(
        model,
        CollectedContent
    ).join(
        CollectedContent,
        and_(
            CollectedContent.shared_item_id == model.id,
            CollectedContent.shared_item_type == item_type,
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status == "active"
        )
    ).options(
        joinedload(CollectedContent.folder)
    ).filter(
        model.id.in_(subquery)
    )
    
    # 仅对支持点赞的类型添加点赞状态查询
    if like_model and like_field:
        # 添加点赞状态查询
        main_query = db.query(
            model,
            CollectedContent,
            # 使用EXISTS检查点赞状态，避免额外查询
            db.query(like_model).filter(
                and_(
                    getattr(like_model, "owner_id") == current_user_id,
                    getattr(like_model, like_field) == model.id
                )
            ).exists().label('is_liked')
        ).join(
            CollectedContent,
            and_(
                CollectedContent.shared_item_id == model.id,
                CollectedContent.shared_item_type == item_type,
                CollectedContent.owner_id == current_user_id,
                CollectedContent.status == "active"
            )
        ).options(
            joinedload(CollectedContent.folder)
        ).filter(
            model.id.in_(subquery)
        )
    
    # 排序
    title_field = "title" if item_type in ["project", "course", "knowledge_base"] else "name"  # 笔记文件夹使用name字段
    
    if sort_by == "title":
        order_field = getattr(model, title_field)
    elif sort_by == "updated_at":
        order_field = CollectedContent.updated_at
    else:
        order_field = CollectedContent.created_at
        
    if sort_order == "desc":
        main_query = main_query.order_by(desc(order_field))
    else:
        main_query = main_query.order_by(order_field)
    
    # 分页
    total = main_query.count()
    results = main_query.offset(offset).limit(page_size).all()
    
    # 格式化结果
    formatted_results = []
    for result_tuple in results:
        if like_model and like_field:
            # 有点赞功能的类型
            item_obj, collection, is_liked = result_tuple
        else:
            # 没有点赞功能的类型
            item_obj, collection = result_tuple
            is_liked = False
        
        # 获取标题字段
        title = getattr(item_obj, title_field, "")
        
        result_data = {
            "collection_id": collection.id,
            f"{item_type}_id": item_obj.id,
            "title": title,
            "description": getattr(item_obj, "description", ""),
            "likes_count": getattr(item_obj, "likes_count", 0) or 0 if item_type in ["project", "course"] else 0,
            "is_liked": is_liked,
            "starred_at": collection.created_at,
            "folder_name": collection.folder.name if collection.folder else None,
            "personal_notes": collection.notes
        }
        
        # 添加类型特定字段
        if item_type == "project":
            result_data.update({
                "project_type": item_obj.project_type,
                "project_status": item_obj.project_status
            })
        elif item_type == "course":
            result_data.update({
                "instructor": item_obj.instructor,
                "category": item_obj.category,
                "total_lessons": item_obj.total_lessons,
                "avg_rating": item_obj.avg_rating
            })
        elif item_type == "knowledge_base":
            result_data.update({
                "is_public": getattr(item_obj, "is_public", False),
                "type": getattr(item_obj, "type", None)
            })
        elif item_type == "note_folder":
            result_data.update({
                "parent_id": item_obj.parent_id,
                "color": getattr(item_obj, "color", None),
                "icon": getattr(item_obj, "icon", None),
                "is_public": getattr(item_obj, "is_public", False),
                "order": getattr(item_obj, "order", 0)
            })
        
        formatted_results.append(result_data)
    
    return {
        f"{item_type}s": formatted_results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    }

@router.get("/statistics", summary="获取收藏统计信息")
@optimized_route("获取收藏统计")
@handle_database_errors
async def get_collection_statistics(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的收藏统计信息 - 优化版本
    """
    # 使用单个查询获取所有统计信息
    stats_query = db.query(
        CollectedContent.shared_item_type,
        func.count(CollectedContent.id).label('count')
    ).filter(
        and_(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.shared_item_type.in_(["project", "course", "knowledge_base", "note_folder"]),
            CollectedContent.status == "active"
        )
    ).group_by(CollectedContent.shared_item_type).all()
    
    stats_dict = {stat.shared_item_type: stat.count for stat in stats_query}
    starred_projects_count = stats_dict.get("project", 0)
    starred_courses_count = stats_dict.get("course", 0)
    starred_knowledge_bases_count = stats_dict.get("knowledge_base", 0)
    starred_note_folders_count = stats_dict.get("note_folder", 0)
    
    # 获取最近收藏的内容（优化查询）
    recent_collections = db.query(CollectedContent).filter(
        and_(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.shared_item_type.in_(["project", "course", "knowledge_base", "note_folder"]),
            CollectedContent.status == "active"
        )
    ).order_by(desc(CollectedContent.created_at)).limit(20).all()  # 增加限制以容纳更多类型
    
    # 分离不同类型
    recent_projects = []
    recent_courses = []
    recent_knowledge_bases = []
    recent_note_folders = []
    
    for collection in recent_collections:
        data = {
            f"{collection.shared_item_type}_id": collection.shared_item_id,
            "title": collection.shared_item_title,
            "starred_at": collection.created_at
        }
        
        if collection.shared_item_type == "project":
            recent_projects.append(data)
        elif collection.shared_item_type == "course":
            recent_courses.append(data)
        elif collection.shared_item_type == "knowledge_base":
            recent_knowledge_bases.append(data)
        elif collection.shared_item_type == "note_folder":
            recent_note_folders.append(data)
    
    return {
        "starred_projects_count": starred_projects_count,
        "starred_courses_count": starred_courses_count,
        "starred_knowledge_bases_count": starred_knowledge_bases_count,
        "starred_note_folders_count": starred_note_folders_count,
        "total_starred": starred_projects_count + starred_courses_count + starred_knowledge_bases_count + starred_note_folders_count,
        "recent_starred_projects": recent_projects[:5],
        "recent_starred_courses": recent_courses[:5],
        "recent_starred_knowledge_bases": recent_knowledge_bases[:5],
        "recent_starred_note_folders": recent_note_folders[:5]
    }

@router.get("/popular/{item_type}", summary="获取热门收藏项目、课程、知识库或笔记文件夹")
@optimized_route("获取热门收藏")
@handle_database_errors
async def get_popular_starred_items(
    item_type: Literal["project", "course", "knowledge_base", "note_folder"],
    db: Session = Depends(get_db),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制")
):
    """
    获取平台上收藏次数最多的项目、课程、知识库或笔记文件夹 - 优化版本
    """
    config = COLLECTION_CONFIGS[item_type]
    model = config["model"]
    
    # 使用一个查询获取热门项目/课程/文件夹
    popular_items = db.query(
        model,
        func.count(CollectedContent.id).label('star_count')
    ).join(
        CollectedContent,
        and_(
            CollectedContent.shared_item_type == item_type,
            CollectedContent.shared_item_id == model.id,
            CollectedContent.status == "active"
        )
    ).group_by(model.id).order_by(
        desc(func.count(CollectedContent.id))
    ).limit(limit).all()
    
    result = []
    title_field = "title" if item_type in ["project", "course", "knowledge_base"] else "name"
    
    for item, star_count in popular_items:
        item_data = {
            f"{item_type}_id": item.id,
            "title": getattr(item, title_field, ""),
            "description": getattr(item, "description", ""),
            "star_count": star_count,
            "likes_count": getattr(item, "likes_count", 0) or 0 if item_type in ["project", "course"] else 0
        }
        
        # 添加类型特定字段
        if item_type == "project":
            item_data.update({
                "project_type": item.project_type,
                "project_status": item.project_status
            })
        elif item_type == "course":
            item_data.update({
                "instructor": item.instructor,
                "category": item.category,
                "total_lessons": item.total_lessons,
                "avg_rating": item.avg_rating
            })
        elif item_type == "knowledge_base":
            item_data.update({
                "is_public": getattr(item, "is_public", False),
                "type": getattr(item, "type", None),
                "owner_id": item.owner_id
            })
        elif item_type == "note_folder":
            item_data.update({
                "parent_id": item.parent_id,
                "color": getattr(item, "color", None),
                "icon": getattr(item, "icon", None),
                "is_public": getattr(item, "is_public", False),
                "owner_id": item.owner_id
            })
        
        result.append(item_data)
    
    return {
        f"popular_{item_type}s": result,
        "total_count": len(result)
    }

# ==================== 批量操作功能 ====================

@router.post("/batch-star", summary="批量收藏项目、课程、知识库和笔记文件夹")
@optimized_route("批量收藏")
@handle_database_errors
@log_operation("批量收藏")
async def batch_star_items(
    items: List[Dict[str, Any]],  # [{"type": "project", "id": 1}, {"type": "course", "id": 2}, {"type": "knowledge_base", "id": 3}, {"type": "note_folder", "id": 4}]
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    批量收藏项目、课程、知识库和笔记文件夹 - 优化版本
    请求体格式: [{"type": "project", "id": 1}, {"type": "course", "id": 2}, {"type": "knowledge_base", "id": 3}, {"type": "note_folder", "id": 4}]
    使用优化后的批量操作提高性能
    """
    if not items:
        return {
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "results": [],
            "message": "没有要处理的项目"
        }
    
    # 使用优化后的批量收藏功能
    collection_manager = CollectionManager(db)
    
    with database_transaction(db):
        # 准备批量收藏数据
        batch_operations = OptimizedBatchOperations(db, current_user_id)
        results = await batch_operations.batch_star_items(items)
    
    return results

@router.delete("/batch-unstar", summary="批量取消收藏")
@optimized_route("批量取消收藏")
@handle_database_errors
@log_operation("批量取消收藏")
async def batch_unstar_items(
    items: List[Dict[str, Any]],  # [{"type": "project", "id": 1}, {"type": "course", "id": 2}, {"type": "knowledge_base", "id": 3}, {"type": "note_folder", "id": 4}]
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    批量取消收藏项目、课程、知识库和笔记文件夹 - 优化版本
    请求体格式: [{"type": "project", "id": 1}, {"type": "course", "id": 2}, {"type": "knowledge_base", "id": 3}, {"type": "note_folder", "id": 4}]
    """
    if not items:
        return {
            "total": 0,
            "success_count": 0,
            "failed_count": 0,
            "results": [],
            "message": "没有要处理的项目"
        }
    
    results = []
    success_count = 0
    
    with database_transaction(db):
        for item in items:
            item_type = item.get("type")
            item_id = item.get("id")
            
            try:
                # 验证参数
                if not item_type or not item_id:
                    results.append({
                        "type": item_type,
                        "id": item_id,
                        "success": False,
                        "message": "缺少必要参数 type 或 id"
                    })
                    continue
                
                # 取消收藏
                await unstar_item(db, current_user_id, item_type, item_id)
                
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": True,
                    "message": "取消收藏成功"
                })
                success_count += 1
                
            except Exception as e:
                results.append({
                    "type": item_type,
                    "id": item_id,
                    "success": False,
                    "message": str(e)
                })
    
    return {
        "total": len(items),
        "success_count": success_count,
        "failed_count": len(items) - success_count,
        "results": results,
        "message": f"批量取消收藏完成，成功 {success_count}/{len(items)}"
    }

# ==================== 内容发现功能 ====================

@router.get("/discover/knowledge-bases", summary="发现公开的知识库")
@optimized_route("发现公开知识库")
@handle_database_errors
async def discover_public_knowledge_bases(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    search: str = Query(None, description="搜索关键词"),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    发现平台上公开的知识库，用户可以浏览并收藏感兴趣的知识库
    """
    offset = (page - 1) * page_size
    
    # 构建基础查询
    query = db.query(KnowledgeBase).filter(
        KnowledgeBase.is_public == True
    ).options(
        joinedload(KnowledgeBase.owner)
    )
    
    # 添加搜索条件
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                KnowledgeBase.title.ilike(search_pattern),
                KnowledgeBase.description.ilike(search_pattern)
            )
        )
    
    # 按创建时间倒序排列
    query = query.order_by(desc(KnowledgeBase.created_at))
    
    # 分页
    total = query.count()
    knowledge_bases = query.offset(offset).limit(page_size).all()
    
    # 批量检查收藏状态
    kb_ids = [kb.id for kb in knowledge_bases]
    collected_kb_ids = set()
    if kb_ids:
        collected_items = db.query(CollectedContent.shared_item_id).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "knowledge_base",
                CollectedContent.shared_item_id.in_(kb_ids),
                CollectedContent.status == "active"
            )
        ).all()
        collected_kb_ids = {item.shared_item_id for item in collected_items}
    
    # 格式化结果
    result_knowledge_bases = []
    for kb in knowledge_bases:
        kb_data = {
            "knowledge_base_id": kb.id,
            "title": kb.title,
            "description": kb.description,
            "owner_id": kb.owner_id,
            "owner_name": kb.owner.name if kb.owner else "未知用户",
            "is_collected": kb.id in collected_kb_ids,
            "created_at": kb.created_at,
            "updated_at": kb.updated_at
        }
        result_knowledge_bases.append(kb_data)
    
    return {
        "knowledge_bases": result_knowledge_bases,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    }

@router.get("/discover/note-folders", summary="发现公开的课程笔记文件夹")
@optimized_route("发现公开笔记文件夹")
@handle_database_errors
async def discover_public_note_folders(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    search: str = Query(None, description="搜索关键词"),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    发现平台上公开的课程笔记文件夹，用户可以浏览并收藏感兴趣的文件夹
    """
    offset = (page - 1) * page_size
    
    # 构建基础查询
    query = db.query(Folder).filter(
        Folder.is_public == True
    ).options(
        joinedload(Folder.owner)
    )
    
    # 添加搜索条件
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Folder.name.ilike(search_pattern),
                Folder.description.ilike(search_pattern)
            )
        )
    
    # 按创建时间倒序排列
    query = query.order_by(desc(Folder.created_at))
    
    # 分页
    total = query.count()
    folders = query.offset(offset).limit(page_size).all()
    
    # 批量检查收藏状态
    folder_ids = [folder.id for folder in folders]
    collected_folder_ids = set()
    if folder_ids:
        collected_items = db.query(CollectedContent.shared_item_id).filter(
            and_(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.shared_item_type == "note_folder",
                CollectedContent.shared_item_id.in_(folder_ids),
                CollectedContent.status == "active"
            )
        ).all()
        collected_folder_ids = {item.shared_item_id for item in collected_items}
    
    # 格式化结果
    result_folders = []
    for folder in folders:
        # 统计文件夹中的笔记数量
        notes_count = db.query(func.count(Note.id)).filter(
            Note.folder_id == folder.id
        ).scalar() or 0
        
        folder_data = {
            "note_folder_id": folder.id,
            "name": folder.name,
            "description": folder.description,
            "color": folder.color,
            "icon": folder.icon,
            "owner_id": folder.owner_id,
            "owner_name": folder.owner.name if folder.owner else "未知用户",
            "parent_id": folder.parent_id,
            "notes_count": notes_count,
            "is_collected": folder.id in collected_folder_ids,
            "created_at": folder.created_at,
            "updated_at": folder.updated_at
        }
        result_folders.append(folder_data)
    
    return {
        "folders": result_folders,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    }

# ==================== 模块完成标记 ====================

logger.info("⭐ Program Collections Module - 统一收藏模块已加载完成")
