# project/routers/knowledge/knowledge.py
"""
知识库管理模块

提供知识库的完整管理功能：
- 知识库CRUD操作
- 文档上传和管理  
- 智能搜索功能
- 公开知识库浏览
- 分析统计功能
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

# FastAPI核心依赖
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session, joinedload

# 项目核心依赖
from project.database import get_db
from project.models import KnowledgeBase, KnowledgeDocument
from project.utils import get_current_user_id
import project.schemas as schemas

# 业务服务层
from project.services.knowledge_service import (
    KnowledgeBaseService, 
    KnowledgeDocumentService, 
    KnowledgeSearchService, 
    KnowledgeUtils
)

# 优化工具
from project.utils.core.error_decorators import handle_database_errors, database_transaction
from project.utils.optimization.router_optimization import optimized_route
from project.utils.async_cache.async_tasks import submit_background_task, TaskPriority
from project.utils.optimization.production_utils import cache_manager, validate_file_upload

# 配置日志和路由器
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["知识库管理"])

# ==================== 知识库基础管理 ====================

@router.post("/kb", response_model=schemas.KnowledgeBaseSimpleResponse, summary="创建知识库")
@optimized_route("创建知识库")
@handle_database_errors
async def create_knowledge_base(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(False),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """创建知识库 - 优化版本"""
    
    # 验证输入数据
    kb_data = KnowledgeUtils.validate_knowledge_base_data({
        "name": name,
        "description": description,
        "is_public": is_public
    })
    
    # 使用事务创建知识库
    with database_transaction(db):
        kb = KnowledgeBaseService.create_knowledge_base_optimized(db, kb_data, current_user_id)
        
        # 异步初始化知识库
        submit_background_task(
            background_tasks,
            "initialize_knowledge_base",
            {"kb_id": kb.id, "user_id": current_user_id},
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"用户 {current_user_id} 创建知识库 {kb.id} 成功")
    return KnowledgeUtils.format_knowledge_base_response(kb)

@router.get("/kb", response_model=List[schemas.KnowledgeBaseSimpleResponse], summary="获取知识库列表")
@optimized_route("获取知识库列表")
@handle_database_errors
async def get_knowledge_bases(
    skip: int = Query(0, ge=0, description="跳过条数"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取知识库列表 - 优化版本"""
    
    knowledge_bases, total = KnowledgeBaseService.get_knowledge_bases_list_optimized(
        db, current_user_id, skip, limit, search
    )
    
    return [KnowledgeUtils.format_knowledge_base_response(kb) for kb in knowledge_bases]

@router.get("/kb/{kb_id}", response_model=schemas.KnowledgeBaseSimpleResponse, summary="获取知识库详情")
@optimized_route("获取知识库详情")
@handle_database_errors
async def get_knowledge_base(
    kb_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取知识库详情 - 优化版本"""
    
    kb = KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, current_user_id)
    return KnowledgeUtils.format_knowledge_base_response(kb)

@router.put("/kb/{kb_id}", response_model=schemas.KnowledgeBaseSimpleResponse, summary="更新知识库")
@optimized_route("更新知识库")
@handle_database_errors
async def update_knowledge_base(
    kb_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_public: Optional[bool] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新知识库 - 优化版本"""
    
    # 准备更新数据
    update_data = {}
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if is_public is not None:
        update_data["is_public"] = is_public
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个要更新的字段"
        )
    
    # 验证数据
    KnowledgeUtils.validate_knowledge_base_data(update_data)
    
    # 使用事务更新
    with database_transaction(db):
        kb = KnowledgeBaseService.update_knowledge_base_optimized(db, kb_id, update_data, current_user_id)
    
    logger.info(f"用户 {current_user_id} 更新知识库 {kb_id} 成功")
    return KnowledgeUtils.format_knowledge_base_response(kb)

@router.delete("/kb/{kb_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除知识库")
@optimized_route("删除知识库")
@handle_database_errors
async def delete_knowledge_base(
    kb_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除知识库 - 优化版本"""
    
    with database_transaction(db):
        KnowledgeBaseService.delete_knowledge_base_optimized(db, kb_id, current_user_id)
        
        # 异步清理相关资源
        submit_background_task(
            background_tasks,
            "cleanup_knowledge_base_resources",
            {"kb_id": kb_id},
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 删除知识库 {kb_id} 成功")

@router.get("/kb/{kb_id}/stats", summary="获取知识库统计信息")
@optimized_route("知识库统计")
@handle_database_errors
async def get_knowledge_base_stats(
    kb_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取知识库统计信息 - 优化版本"""
    
    stats = KnowledgeBaseService.get_knowledge_base_stats_optimized(db, kb_id, current_user_id)
    return stats

# ==================== 文档管理功能 ====================

@router.post("/kb/{kb_id}/documents/upload", response_model=schemas.KnowledgeDocumentSimpleResponse, summary="智能文档上传")
@optimized_route("文档上传")
@handle_database_errors
async def upload_document(
    kb_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """智能文档上传 - 优化版本"""
    
    # 验证文件
    validate_file_upload(file)
    
    # 准备文档数据
    file_content = await file.read()
    content_type = KnowledgeUtils.get_content_type_from_file(file.filename)
    
    doc_data = KnowledgeUtils.validate_document_data({
        "title": title or file.filename,
        "content_type": content_type,
        "file_size": len(file_content),
        "mime_type": file.content_type
    })
    
    # 使用事务创建文档
    with database_transaction(db):
        doc = KnowledgeDocumentService.create_document_optimized(db, kb_id, doc_data, current_user_id)
        
        # 异步处理文件上传和内容提取
        submit_background_task(
            background_tasks,
            "process_document_upload",
            {
                "doc_id": doc.id,
                "kb_id": kb_id,
                "file_content": file_content,
                "filename": file.filename,
                "content_type": content_type
            },
            priority=TaskPriority.HIGH
        )
    
    logger.info(f"用户 {current_user_id} 在知识库 {kb_id} 上传文档 {doc.id}")
    return KnowledgeUtils.format_document_response(doc)

@router.post("/kb/{kb_id}/documents/add-url", response_model=schemas.KnowledgeDocumentSimpleResponse, summary="添加网址内容")
@optimized_route("添加网址")
@handle_database_errors
async def add_url_content(
    kb_id: int,
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    title: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """添加网址内容 - 优化版本"""
    
    # 验证URL
    if not KnowledgeUtils.validate_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的URL格式"
        )
    
    # 准备文档数据
    doc_data = KnowledgeUtils.validate_document_data({
        "title": title or f"网址内容 - {url}",
        "content_type": "url",
        "url": url
    })
    
    # 使用事务创建文档
    with database_transaction(db):
        doc = KnowledgeDocumentService.create_document_optimized(db, kb_id, doc_data, current_user_id)
        
        # 异步抓取网址内容
        submit_background_task(
            background_tasks,
            "extract_url_content",
            {
                "doc_id": doc.id,
                "kb_id": kb_id,
                "url": url
            },
            priority=TaskPriority.MEDIUM
        )
    
    logger.info(f"用户 {current_user_id} 在知识库 {kb_id} 添加网址 {url}")
    return KnowledgeUtils.format_document_response(doc)

@router.get("/kb/{kb_id}/documents", response_model=List[schemas.KnowledgeDocumentSimpleResponse], summary="获取文档列表")
@optimized_route("获取文档列表")
@handle_database_errors
async def get_documents(
    kb_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    content_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取文档列表 - 优化版本"""
    
    documents, total = KnowledgeDocumentService.get_documents_list_optimized(
        db, kb_id, current_user_id, skip, limit, content_type, search
    )
    
    return [KnowledgeUtils.format_document_response(doc) for doc in documents]

@router.get("/kb/{kb_id}/documents/{document_id}", response_model=schemas.KnowledgeDocumentSimpleResponse, summary="获取文档详情")
@optimized_route("获取文档详情")
@handle_database_errors
async def get_document(
    kb_id: int,
    document_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取文档详情 - 优化版本"""
    
    doc = KnowledgeDocumentService.get_document_optimized(db, kb_id, document_id, current_user_id)
    return KnowledgeUtils.format_document_response(doc)

@router.put("/kb/{kb_id}/documents/{document_id}", response_model=schemas.KnowledgeDocumentSimpleResponse, summary="更新文档信息")
@optimized_route("更新文档")
@handle_database_errors
async def update_document(
    kb_id: int,
    document_id: int,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新文档信息 - 优化版本"""
    
    # 准备更新数据
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if content is not None:
        update_data["content"] = content
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要提供一个要更新的字段"
        )
    
    # 使用事务更新
    with database_transaction(db):
        doc = KnowledgeDocumentService.update_document_optimized(
            db, kb_id, document_id, update_data, current_user_id
        )
    
    logger.info(f"用户 {current_user_id} 更新文档 {document_id} 成功")
    return KnowledgeUtils.format_document_response(doc)

@router.delete("/kb/{kb_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除文档")
@optimized_route("删除文档")
@handle_database_errors
async def delete_document(
    kb_id: int,
    document_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除文档 - 优化版本"""
    
    with database_transaction(db):
        KnowledgeDocumentService.delete_document_optimized(db, kb_id, document_id, current_user_id)
        
        # 异步清理文档资源
        submit_background_task(
            background_tasks,
            "cleanup_document_resources",
            {"doc_id": document_id, "kb_id": kb_id},
            priority=TaskPriority.LOW
        )
    
    logger.info(f"用户 {current_user_id} 删除文档 {document_id} 成功")

# ==================== 搜索和查询功能 ====================

@router.get("/kb/{kb_id}/search", response_model=schemas.KnowledgeSearchResponse, summary="智能搜索")
@optimized_route("知识搜索")
@handle_database_errors
async def search_knowledge(
    kb_id: int,
    background_tasks: BackgroundTasks,
    q: str = Query(..., min_length=2, description="搜索关键词"),
    content_types: Optional[List[str]] = Query(None, description="内容类型过滤"),
    limit: int = Query(20, ge=1, le=100),
    use_ai: bool = Query(True, description="是否使用AI搜索"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """智能搜索 - 优化版本"""
    
    # 执行搜索
    search_result = KnowledgeSearchService.search_knowledge_optimized(
        db, kb_id, q, current_user_id, content_types, limit, use_ai
    )
    
    # 异步记录搜索日志
    submit_background_task(
        background_tasks,
        "log_knowledge_search",
        {
            "user_id": current_user_id,
            "kb_id": kb_id,
            "query": q,
            "result_count": search_result["total_results"],
            "from_cache": search_result.get("from_cache", False)
        },
        priority=TaskPriority.LOW
    )
    
    logger.info(f"用户 {current_user_id} 在知识库 {kb_id} 搜索: {q}")
    return search_result

# ==================== 分析统计功能 ====================

@router.get("/kb/{kb_id}/analytics", summary="知识库分析统计")
@optimized_route("知识库分析")
@handle_database_errors
async def get_knowledge_analytics(
    kb_id: int,
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """知识库分析统计 - 优化版本"""
    
    cache_key = f"analytics:kb:{kb_id}:days:{days}"
    cached_analytics = cache_manager.get(cache_key)
    if cached_analytics:
        return cached_analytics
    
    # 验证权限
    KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, current_user_id)
    
    # 获取统计数据（简化版本）
    analytics = {
        "kb_id": kb_id,
        "period_days": days,
        "basic_stats": KnowledgeBaseService.get_knowledge_base_stats_optimized(db, kb_id, current_user_id),
        "growth_trend": [],  # 可以扩展添加增长趋势分析
        "popular_content_types": [],  # 可以扩展添加热门内容类型
        "search_trends": [],  # 可以扩展添加搜索趋势
        "generated_at": datetime.utcnow().isoformat()
    }
    
    # 缓存分析结果
    cache_manager.set(cache_key, analytics, expire_time=3600)  # 1小时缓存
    return analytics

@router.get("/monitoring/performance", summary="获取系统性能指标")
@optimized_route("性能监控")
@handle_database_errors
async def get_performance_metrics(
    current_user_id: int = Depends(get_current_user_id)
):
    """获取系统性能指标 - 优化版本"""
    
    cache_key = "monitoring:performance"
    cached_metrics = cache_manager.get(cache_key)
    if cached_metrics:
        return cached_metrics
    
    # 简化的性能指标
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "cache_stats": {
            "hit_rate": 0.85,  # 模拟缓存命中率
            "total_keys": 1000,
            "memory_usage": "256MB"
        },
        "database_stats": {
            "active_connections": 15,
            "query_avg_time": "25ms",
            "slow_queries": 2
        },
        "system_stats": {
            "cpu_usage": "35%",
            "memory_usage": "68%",
            "disk_usage": "45%"
        }
    }
    
    # 缓存性能指标
    cache_manager.set(cache_key, metrics, expire_time=60)  # 1分钟缓存
    return metrics

# ==================== 任务状态管理 ====================

@router.get("/tasks/{task_id}/status", summary="获取任务状态")
@optimized_route("任务状态")
@handle_database_errors
async def get_task_status(
    task_id: str,
    current_user_id: int = Depends(get_current_user_id)
):
    """获取任务状态 - 优化版本"""
    
    cache_key = f"task:status:{task_id}"
    task_status = cache_manager.get(cache_key)
    
    if not task_status:
        # 如果缓存中没有任务状态，返回默认状态
        task_status = {
            "task_id": task_id,
            "status": "unknown",
            "message": "任务状态未知",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat()
        }
    
    return task_status

# ==================== 公开知识库功能 ====================

@router.get("/public", response_model=List[schemas.KnowledgeBaseSimpleResponse], summary="浏览公开知识库")
@optimized_route("获取公开知识库")
@handle_database_errors
async def get_public_knowledge_bases(
    background_tasks: BackgroundTasks,
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(20, ge=1, le=100, description="返回的记录数"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    浏览平台上的公开知识库
    支持搜索和分页，所有用户都可以访问
    """
    
    # 获取公开知识库
    knowledge_bases, total = KnowledgeBaseService.get_public_knowledge_bases_optimized(
        db, skip, limit, search
    )
    
    # 异步记录访问日志
    if current_user_id:
        submit_background_task(
            background_tasks,
            "log_public_knowledge_access",
            {
                "user_id": current_user_id,
                "search_query": search,
                "result_count": total
            },
            priority=TaskPriority.LOW
        )
    
    # 格式化响应
    kb_responses = []
    for kb in knowledge_bases:
        kb_response = KnowledgeUtils.format_knowledge_base_response(kb)
        kb_response["owner_username"] = kb.owner.username if kb.owner else "未知用户"
        kb_responses.append(kb_response)
    
    logger.info(f"返回 {len(knowledge_bases)} 个公开知识库")
    return kb_responses

@router.get("/public/search", response_model=List[schemas.KnowledgeBaseSimpleResponse], summary="搜索公开的知识库")
@optimized_route("搜索公开知识库")
@handle_database_errors
async def search_public_knowledge_bases(
    background_tasks: BackgroundTasks,
    q: str = Query(..., min_length=2, description="搜索关键词"),
    owner: Optional[str] = Query(None, description="创建者用户名"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(20, ge=1, le=100, description="返回的记录数"),
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    搜索公开的知识库
    支持按知识库名称、描述和创建者搜索
    """
    
    # 执行搜索
    knowledge_bases, total = KnowledgeBaseService.search_public_knowledge_bases_optimized(
        db, q, skip, limit, owner
    )
    
    # 异步记录搜索日志
    if current_user_id:
        submit_background_task(
            background_tasks,
            "log_public_knowledge_search",
            {
                "user_id": current_user_id,
                "query": q,
                "owner_filter": owner,
                "result_count": total
            },
            priority=TaskPriority.LOW
        )
    
    # 格式化响应
    kb_responses = []
    for kb in knowledge_bases:
        kb_response = KnowledgeUtils.format_knowledge_base_response(kb)
        kb_response["owner_username"] = kb.owner.username if kb.owner else "未知用户"
        kb_responses.append(kb_response)
    
    logger.info(f"搜索返回 {len(knowledge_bases)} 个公开知识库")
    return kb_responses

@router.get("/public/{kb_id}", response_model=schemas.KnowledgeBaseSimpleResponse, summary="获取公开知识库详情")
@optimized_route("获取公开知识库详情")
@handle_database_errors
async def get_public_knowledge_base_detail(
    kb_id: int,
    background_tasks: BackgroundTasks,
    current_user_id: Optional[int] = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取公开知识库的详细信息
    包括知识库内的文档列表
    """
    
    # 获取公开知识库
    try:
        kb = db.query(KnowledgeBase).options(
            joinedload(KnowledgeBase.owner),
            joinedload(KnowledgeBase.documents)
        ).filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.is_public == True
        ).first()

        if not kb:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="公开知识库不存在"
            )
    except Exception as e:
        logger.error(f"获取公开知识库失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取知识库信息失败"
        )
    
    # 异步记录访问日志
    if current_user_id:
        submit_background_task(
            background_tasks,
            "log_public_knowledge_view",
            {
                "user_id": current_user_id,
                "kb_id": kb_id,
                "kb_owner_id": kb.owner_id
            },
            priority=TaskPriority.LOW
        )
    
    # 格式化响应
    kb_response = KnowledgeUtils.format_knowledge_base_response(kb)
    kb_response["owner_username"] = kb.owner.username if kb.owner else "未知用户"
    
    # 添加文档列表
    if kb.documents:
        kb_response["documents"] = [
            KnowledgeUtils.format_document_response(doc) 
            for doc in kb.documents 
            if hasattr(doc, 'status') and doc.status == 'completed'  # 只显示处理完成的文档
        ]
    
    logger.info(f"返回公开知识库 {kb_id} 详情")
    return kb_response

@router.patch("/kb/{kb_id}/visibility", response_model=schemas.KnowledgeBaseSimpleResponse, summary="切换知识库公开状态")
@optimized_route("切换知识库公开状态")
@handle_database_errors
async def toggle_knowledge_base_visibility(
    kb_id: int,
    visibility_data: schemas.KnowledgeBaseVisibilityUpdate,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    切换知识库的公开/私密状态
    只有知识库所有者可以修改
    """
    
    # 使用事务更新
    with database_transaction(db):
        update_data = {"is_public": visibility_data.is_public}
        kb = KnowledgeBaseService.update_knowledge_base_optimized(
            db, kb_id, update_data, current_user_id
        )
        
        # 清除公开知识库缓存
        cache_manager.delete_pattern("public_knowledge_bases:*")
        cache_manager.delete_pattern("search_public_knowledge_bases:*")
    
    # 异步记录状态变更
    submit_background_task(
        background_tasks,
        "log_knowledge_visibility_change",
        {
            "user_id": current_user_id,
            "kb_id": kb_id,
            "is_public": visibility_data.is_public,
            "timestamp": datetime.now().isoformat()
        },
        priority=TaskPriority.MEDIUM
    )
    
    logger.info(f"知识库 {kb_id} 公开状态已更新为: {'公开' if visibility_data.is_public else '私密'}")
    return KnowledgeUtils.format_knowledge_base_response(kb)

# ==================== 模块完成标记 ====================

logger.info("📚 Knowledge Module - 知识库模块已加载完成")
