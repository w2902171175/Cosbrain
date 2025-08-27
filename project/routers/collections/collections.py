# project/routers/collections_new/collections_new.py
"""
重新设计的收藏管理系统 - 以文件夹为中心的设计

核心设计思路：
1. 文件夹是收藏系统的核心实体，所有收藏内容都围绕文件夹展开
2. 支持多级文件夹嵌套，提供类似文件系统的体验
3. 统一的收藏接口，无论是内部资源还是外部链接
4. 智能的默认分类和自动标签
5. 高效的搜索和过滤功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal, Union, Tuple
import numpy as np
from datetime import timedelta, datetime, timezone, date
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc, asc, text
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
import oss_utils
from ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_user_model_for_provider
from ai_providers.embedding_provider import get_embeddings_from_api
from ai_providers.security_utils import decrypt_key

router = APIRouter(
    prefix="/folders",
    tags=["收藏文件夹管理"],
    responses={404: {"description": "Not found"}},
)

# ================== 核心设计理念 ==================
"""
新的收藏系统设计思路：

1. 文件夹优先：
   - 用户首先创建和管理文件夹
   - 所有收藏操作都基于文件夹进行
   - 文件夹可以嵌套，支持多级分类

2. 统一收藏接口：
   - 一个统一的收藏接口处理所有类型的内容
   - 内部资源（课程、项目等）和外部链接使用相同的接口
   - 自动智能分类和标签生成

3. 智能组织：
   - 自动创建默认分类文件夹
   - 基于内容类型自动建议文件夹
   - 智能标签和分类推荐

4. 增强的搜索：
   - 基于文件夹的层级搜索
   - 跨文件夹的全局搜索
   - 智能过滤和排序
"""

# ================== 文件夹管理 API ==================

@router.get("/", response_model=List[schemas.FolderResponseNew], summary="获取用户的文件夹树结构")
async def get_folder_tree(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    parent_id: Optional[int] = Query(None, description="父文件夹ID，为空时获取根级文件夹"),
    include_empty: bool = Query(True, description="是否包含空文件夹"),
    expand_all: bool = Query(False, description="是否展开所有子文件夹")
):
    """
    获取用户的文件夹树结构
    - 支持层级展示
    - 可选择是否包含空文件夹
    - 自动计算每个文件夹的内容数量
    """
    base_query = db.query(Folder).filter(
        Folder.owner_id == current_user_id,
        Folder.parent_id == parent_id
    ).order_by(Folder.order.asc(), Folder.name.asc())
    
    folders = base_query.all()
    
    # 为每个文件夹计算内容数量
    result = []
    for folder in folders:
        # 计算直接收藏内容数量
        content_count = db.query(CollectedContent).filter(
            CollectedContent.folder_id == folder.id,
            CollectedContent.owner_id == current_user_id
        ).count()
        
        # 计算子文件夹数量
        subfolder_count = db.query(Folder).filter(
            Folder.parent_id == folder.id,
            Folder.owner_id == current_user_id
        ).count()
        
        total_count = content_count + subfolder_count
        
        # 如果不包含空文件夹且文件夹为空，跳过
        if not include_empty and total_count == 0:
            continue
            
        folder.item_count = total_count
        
        # 如果需要展开所有子文件夹，递归获取子文件夹
        if expand_all:
            # 这里可以添加递归逻辑，暂时保持简单
            pass
            
        result.append(folder)
    
    return result

@router.post("/", response_model=schemas.FolderResponseNew, summary="创建新文件夹")
async def create_folder(
    folder_data: schemas.FolderCreateNew,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    创建新的收藏文件夹
    - 支持多级嵌套
    - 自动验证名称唯一性（同级别下）
    - 智能设置默认图标和颜色
    """
    # 验证父文件夹权限（如果指定了父文件夹）
    if folder_data.parent_id:
        parent_folder = db.query(Folder).filter(
            Folder.id == folder_data.parent_id,
            Folder.owner_id == current_user_id
        ).first()
        if not parent_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="父文件夹不存在或无权访问"
            )
    
    # 检查同级别下名称唯一性
    existing_folder = db.query(Folder).filter(
        Folder.owner_id == current_user_id,
        Folder.name == folder_data.name,
        Folder.parent_id == folder_data.parent_id
    ).first()
    
    if existing_folder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="同级目录下已存在相同名称的文件夹"
        )
    
    # 自动设置默认值
    if not folder_data.color:
        # 根据文件夹名称智能设置颜色
        folder_data.color = _suggest_folder_color(folder_data.name)
    
    if not folder_data.icon:
        # 根据文件夹名称智能设置图标
        folder_data.icon = _suggest_folder_icon(folder_data.name)
    
    # 设置排序值
    if folder_data.order is None:
        # 获取同级最大排序值
        max_order = db.query(func.max(Folder.order)).filter(
            Folder.owner_id == current_user_id,
            Folder.parent_id == folder_data.parent_id
        ).scalar() or 0
        folder_data.order = max_order + 1
    
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
    
    # 计算初始内容数量（应该为0）
    db_folder.item_count = 0
    
    return db_folder

@router.get("/{folder_id}", response_model=schemas.FolderResponseNew, summary="获取文件夹详情")
async def get_folder_details(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    获取指定文件夹的详细信息
    - 包含统计信息
    - 包含路径信息
    """
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == current_user_id
    ).first()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在或无权访问"
        )
    
    # 计算内容统计
    content_count = db.query(CollectedContent).filter(
        CollectedContent.folder_id == folder_id,
        CollectedContent.owner_id == current_user_id
    ).count()
    
    subfolder_count = db.query(Folder).filter(
        Folder.parent_id == folder_id,
        Folder.owner_id == current_user_id
    ).count()
    
    folder.item_count = content_count + subfolder_count
    
    return folder

@router.put("/{folder_id}", response_model=schemas.FolderResponseNew, summary="更新文件夹信息")
async def update_folder(
    folder_id: int,
    folder_data: schemas.FolderUpdateNew,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    更新文件夹信息
    - 支持移动到其他父文件夹
    - 防止循环引用
    - 验证名称唯一性
    """
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == current_user_id
    ).first()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在或无权访问"
        )
    
    update_data = folder_data.model_dump(exclude_unset=True)
    
    # 如果要移动文件夹，验证新的父文件夹
    if "parent_id" in update_data:
        new_parent_id = update_data["parent_id"]
        
        # 防止设置自己为父文件夹
        if new_parent_id == folder_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能将文件夹设置为自己的子文件夹"
            )
        
        # 防止循环引用
        if new_parent_id and _would_create_cycle(db, folder_id, new_parent_id, current_user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="移动操作会创建循环引用"
            )
        
        # 验证新父文件夹权限
        if new_parent_id:
            parent_folder = db.query(Folder).filter(
                Folder.id == new_parent_id,
                Folder.owner_id == current_user_id
            ).first()
            if not parent_folder:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="目标父文件夹不存在或无权访问"
                )
    
    # 如果要修改名称，验证唯一性
    if "name" in update_data and update_data["name"] != folder.name:
        new_parent_id = update_data.get("parent_id", folder.parent_id)
        existing_folder = db.query(Folder).filter(
            Folder.owner_id == current_user_id,
            Folder.name == update_data["name"],
            Folder.parent_id == new_parent_id,
            Folder.id != folder_id
        ).first()
        
        if existing_folder:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="同级目录下已存在相同名称的文件夹"
            )
    
    # 应用更新
    for key, value in update_data.items():
        setattr(folder, key, value)
    
    db.commit()
    db.refresh(folder)
    
    # 重新计算内容数量
    content_count = db.query(CollectedContent).filter(
        CollectedContent.folder_id == folder_id,
        CollectedContent.owner_id == current_user_id
    ).count()
    
    subfolder_count = db.query(Folder).filter(
        Folder.parent_id == folder_id,
        Folder.owner_id == current_user_id
    ).count()
    
    folder.item_count = content_count + subfolder_count
    
    return folder

@router.delete("/{folder_id}", summary="删除文件夹")
async def delete_folder(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    force: bool = Query(False, description="是否强制删除（包含内容的文件夹）"),
    move_content_to: Optional[int] = Query(None, description="将内容移动到指定文件夹ID")
):
    """
    删除文件夹
    - 可选择强制删除或移动内容到其他文件夹
    - 级联删除所有子文件夹和内容
    """
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == current_user_id
    ).first()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在或无权访问"
        )
    
    # 检查文件夹是否包含内容
    content_count = db.query(CollectedContent).filter(
        CollectedContent.folder_id == folder_id
    ).count()
    
    subfolder_count = db.query(Folder).filter(
        Folder.parent_id == folder_id
    ).count()
    
    if (content_count > 0 or subfolder_count > 0) and not force and move_content_to is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件夹不为空，请指定 force=true 强制删除或 move_content_to 参数移动内容"
        )
    
    # 如果指定了移动目标，先移动内容
    if move_content_to is not None:
        target_folder = db.query(Folder).filter(
            Folder.id == move_content_to,
            Folder.owner_id == current_user_id
        ).first()
        
        if not target_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目标移动文件夹不存在或无权访问"
            )
        
        # 移动收藏内容
        db.query(CollectedContent).filter(
            CollectedContent.folder_id == folder_id
        ).update({"folder_id": move_content_to})
        
        # 移动子文件夹
        db.query(Folder).filter(
            Folder.parent_id == folder_id
        ).update({"parent_id": move_content_to})
        
        db.commit()
    
    # 删除文件夹（如果设置了级联，会自动删除子内容）
    db.delete(folder)
    db.commit()
    
    return {"message": "文件夹删除成功"}

# ================== 文件夹内容管理 API ==================

@router.get("/{folder_id}/contents", response_model=List[schemas.CollectedContentResponseNew], summary="获取文件夹内容")
async def get_folder_contents(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    content_type: Optional[str] = Query(None, description="过滤内容类型"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(50, description="返回数量限制"),
    offset: int = Query(0, description="偏移量")
):
    """
    获取指定文件夹的内容
    - 支持类型过滤
    - 支持搜索
    - 支持排序
    - 支持分页
    """
    # 验证文件夹权限
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == current_user_id
    ).first()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在或无权访问"
        )
    
    # 构建查询
    query = db.query(CollectedContent).filter(
        CollectedContent.folder_id == folder_id,
        CollectedContent.owner_id == current_user_id
    )
    
    # 应用过滤器
    if content_type:
        query = query.filter(CollectedContent.type == content_type)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                CollectedContent.title.like(search_pattern),
                CollectedContent.content.like(search_pattern),
                CollectedContent.tags.like(search_pattern)
            )
        )
    
    # 应用排序
    sort_column = getattr(CollectedContent, sort_by, CollectedContent.created_at)
    if sort_order.lower() == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # 应用分页
    contents = query.offset(offset).limit(limit).all()
    
    return contents

@router.post("/{folder_id}/collect", response_model=schemas.CollectedContentResponseNew, summary="向文件夹添加收藏")
async def add_to_folder(
    folder_id: int,
    content_data: schemas.CollectedContentCreateNew = Depends(),
    file: Optional[UploadFile] = File(None, description="可选：上传文件"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    向指定文件夹添加收藏内容
    - 统一处理各种类型的收藏
    - 自动智能分类和标签
    - 支持文件上传
    """
    # 验证文件夹权限
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == current_user_id
    ).first()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在或无权访问"
        )
    
    # 设置文件夹ID
    content_data.folder_id = folder_id
    
    # 处理文件上传
    uploaded_file_info = None
    if file:
        uploaded_file_info = await _handle_file_upload(file)
    
    # 调用原有的内部创建逻辑（从原collections.py改进）
    collected_content = await _create_collected_content_item_internal(
        db=db,
        current_user_id=current_user_id,
        content_data=content_data,
        uploaded_file_bytes=uploaded_file_info["bytes"] if uploaded_file_info else None,
        uploaded_file_object_name=uploaded_file_info["object_name"] if uploaded_file_info else None,
        uploaded_file_content_type=uploaded_file_info["content_type"] if uploaded_file_info else None,
        uploaded_file_original_filename=uploaded_file_info["filename"] if uploaded_file_info else None,
        uploaded_file_size=uploaded_file_info["size"] if uploaded_file_info else None,
    )
    
    db.add(collected_content)
    db.commit()
    db.refresh(collected_content)
    
    return collected_content

# ================== 快速收藏 API ==================

@router.post("/quick-collect", response_model=schemas.CollectedContentResponseNew, summary="快速收藏")
async def quick_collect(
    url: Optional[str] = Form(None, description="要收藏的URL"),
    title: Optional[str] = Form(None, description="自定义标题"),
    folder_id: Optional[int] = Form(None, description="目标文件夹ID"),
    shared_item_type: Optional[str] = Form(None, description="内部资源类型"),
    shared_item_id: Optional[int] = Form(None, description="内部资源ID"),
    file: Optional[UploadFile] = File(None, description="上传文件"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    快速收藏接口
    - 智能判断收藏类型
    - 自动选择或创建合适的文件夹
    - 支持多种收藏方式
    """
    # 确定目标文件夹
    target_folder_id = await _determine_target_folder(
        db, current_user_id, folder_id, shared_item_type, url, file
    )
    
    # 构建收藏数据
    content_data = schemas.CollectedContentCreateNew(
        title=title,
        url=url,
        folder_id=target_folder_id,
        shared_item_type=shared_item_type,
        shared_item_id=shared_item_id
    )
    
    # 处理文件上传
    uploaded_file_info = None
    if file:
        uploaded_file_info = await _handle_file_upload(file)
    
    # 创建收藏内容
    collected_content = await _create_collected_content_item_internal(
        db=db,
        current_user_id=current_user_id,
        content_data=content_data,
        uploaded_file_bytes=uploaded_file_info["bytes"] if uploaded_file_info else None,
        uploaded_file_object_name=uploaded_file_info["object_name"] if uploaded_file_info else None,
        uploaded_file_content_type=uploaded_file_info["content_type"] if uploaded_file_info else None,
        uploaded_file_original_filename=uploaded_file_info["filename"] if uploaded_file_info else None,
        uploaded_file_size=uploaded_file_info["size"] if uploaded_file_info else None,
    )
    
    db.add(collected_content)
    db.commit()
    db.refresh(collected_content)
    
    return collected_content

# ================== 搜索和过滤 API ==================

@router.get("/search", response_model=List[schemas.CollectedContentResponseNew], summary="搜索收藏内容")
async def search_collections(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    query: str = Query(..., description="搜索关键词"),
    folder_id: Optional[int] = Query(None, description="限制在特定文件夹"),
    content_type: Optional[str] = Query(None, description="内容类型过滤"),
    date_from: Optional[date] = Query(None, description="开始日期"),
    date_to: Optional[date] = Query(None, description="结束日期"),
    limit: int = Query(50, description="返回数量限制"),
    offset: int = Query(0, description="偏移量")
):
    """
    搜索用户的收藏内容
    - 支持全文搜索
    - 支持文件夹范围限制
    - 支持多维度过滤
    """
    # 构建基础查询
    base_query = db.query(CollectedContent).filter(
        CollectedContent.owner_id == current_user_id
    )
    
    # 应用搜索条件
    search_pattern = f"%{query}%"
    base_query = base_query.filter(
        or_(
            CollectedContent.title.like(search_pattern),
            CollectedContent.content.like(search_pattern),
            CollectedContent.tags.like(search_pattern),
            CollectedContent.author.like(search_pattern)
        )
    )
    
    # 应用过滤条件
    if folder_id:
        base_query = base_query.filter(CollectedContent.folder_id == folder_id)
    
    if content_type:
        base_query = base_query.filter(CollectedContent.type == content_type)
    
    if date_from:
        base_query = base_query.filter(CollectedContent.created_at >= date_from)
    
    if date_to:
        # 将date_to转换为当天的23:59:59
        date_to_end = datetime.combine(date_to, datetime.max.time())
        base_query = base_query.filter(CollectedContent.created_at <= date_to_end)
    
    # 排序和分页
    results = base_query.order_by(
        desc(CollectedContent.created_at)
    ).offset(offset).limit(limit).all()
    
    return results

# ================== 辅助函数 ==================

def _suggest_folder_color(name: str) -> str:
    """根据文件夹名称智能推荐颜色"""
    color_mapping = {
        "工作": "#FF6B6B",
        "学习": "#4ECDC4", 
        "项目": "#45B7D1",
        "课程": "#96CEB4",
        "文档": "#FFEAA7",
        "图片": "#DDA0DD",
        "视频": "#FF7675",
        "代码": "#2D3436",
        "笔记": "#81ECEC",
        "收藏": "#FD79A8"
    }
    
    name_lower = name.lower()
    for keyword, color in color_mapping.items():
        if keyword in name_lower:
            return color
    
    # 默认颜色
    return "#74B9FF"

def _suggest_folder_icon(name: str) -> str:
    """根据文件夹名称智能推荐图标"""
    icon_mapping = {
        "工作": "briefcase",
        "学习": "book",
        "项目": "folder-open",
        "课程": "graduation-cap",
        "文档": "file-text",
        "图片": "image",
        "视频": "video",
        "代码": "code",
        "笔记": "edit-3",
        "收藏": "heart"
    }
    
    name_lower = name.lower()
    for keyword, icon in icon_mapping.items():
        if keyword in name_lower:
            return icon
    
    # 默认图标
    return "folder"

def _would_create_cycle(db: Session, folder_id: int, new_parent_id: int, user_id: int) -> bool:
    """检查移动文件夹是否会创建循环引用"""
    current_id = new_parent_id
    visited = set()
    
    while current_id and current_id not in visited:
        if current_id == folder_id:
            return True
        
        visited.add(current_id)
        parent_folder = db.query(Folder).filter(
            Folder.id == current_id,
            Folder.owner_id == user_id
        ).first()
        
        current_id = parent_folder.parent_id if parent_folder else None
    
    return False

async def _determine_target_folder(
    db: Session, 
    user_id: int, 
    specified_folder_id: Optional[int],
    shared_item_type: Optional[str],
    url: Optional[str],
    file: Optional[UploadFile]
) -> int:
    """智能确定目标文件夹"""
    # 如果明确指定了文件夹
    if specified_folder_id:
        folder = db.query(Folder).filter(
            Folder.id == specified_folder_id,
            Folder.owner_id == user_id
        ).first()
        if folder:
            return specified_folder_id
    
    # 基于内容类型智能选择文件夹
    auto_folder_name = None
    
    if shared_item_type:
        type_mapping = {
            "project": "项目收藏",
            "course": "课程收藏", 
            "forum_topic": "论坛收藏",
            "knowledge_article": "知识收藏"
        }
        auto_folder_name = type_mapping.get(shared_item_type, "其他收藏")
    elif file:
        if file.content_type.startswith("image/"):
            auto_folder_name = "图片收藏"
        elif file.content_type.startswith("video/"):
            auto_folder_name = "视频收藏"
        else:
            auto_folder_name = "文件收藏"
    elif url:
        auto_folder_name = "链接收藏"
    else:
        auto_folder_name = "默认收藏"
    
    # 查找或创建自动分类文件夹
    auto_folder = db.query(Folder).filter(
        Folder.owner_id == user_id,
        Folder.name == auto_folder_name,
        Folder.parent_id.is_(None)
    ).first()
    
    if not auto_folder:
        auto_folder = Folder(
            owner_id=user_id,
            name=auto_folder_name,
            description=f"自动创建的{auto_folder_name}文件夹",
            color=_suggest_folder_color(auto_folder_name),
            icon=_suggest_folder_icon(auto_folder_name),
            parent_id=None,
            order=0
        )
        db.add(auto_folder)
        db.flush()
    
    return auto_folder.id

async def _handle_file_upload(file: UploadFile) -> Dict[str, Any]:
    """处理文件上传"""
    file_bytes = await file.read()
    file_size = len(file_bytes)
    
    # 生成唯一文件名
    file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
    object_name = f"collections/{uuid.uuid4()}{file_extension}"
    
    # 上传到OSS
    await oss_utils.upload_file_to_oss(file_bytes, object_name, file.content_type)
    
    return {
        "bytes": file_bytes,
        "object_name": object_name,
        "content_type": file.content_type,
        "filename": file.filename,
        "size": file_size
    }

# 从原来的 collections.py 中复制并改进内部创建逻辑
async def _create_collected_content_item_internal(
    db: Session,
    current_user_id: int,
    content_data: schemas.CollectedContentCreateNew,
    uploaded_file_bytes: Optional[bytes] = None,
    uploaded_file_object_name: Optional[str] = None,
    uploaded_file_content_type: Optional[str] = None,
    uploaded_file_original_filename: Optional[str] = None,
    uploaded_file_size: Optional[int] = None,
) -> CollectedContent:
    """
    内部辅助函数：处理收藏内容的创建逻辑
    这是从原 collections.py 改进的版本，专注于文件夹为中心的设计
    """
    # 验证文件夹权限
    if content_data.folder_id:
        target_folder = db.query(Folder).filter(
            Folder.id == content_data.folder_id,
            Folder.owner_id == current_user_id
        ).first()
        if not target_folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目标文件夹不存在或无权访问"
            )
    
    # 初始化最终值
    final_title = content_data.title
    final_type = content_data.type
    final_url = content_data.url
    final_content = content_data.content
    final_author = content_data.author
    final_tags = content_data.tags
    final_thumbnail = content_data.thumbnail
    final_duration = content_data.duration
    final_file_size = content_data.file_size
    final_status = content_data.status or "active"
    
    # 处理直接上传的文件
    if uploaded_file_bytes and uploaded_file_object_name:
        final_url = f"{oss_utils.S3_BASE_URL.rstrip('/')}/{uploaded_file_object_name}"
        final_file_size = uploaded_file_size
        
        # 自动推断文件类型
        if uploaded_file_content_type.startswith("image/"):
            final_type = "image"
        elif uploaded_file_content_type.startswith("video/"):
            final_type = "video"
        else:
            final_type = "file"
        
        # 自动设置标题
        if not final_title and uploaded_file_original_filename:
            final_title = uploaded_file_original_filename
        
        # 自动设置内容描述
        if not final_content:
            final_content = f"上传的{final_type}: {uploaded_file_original_filename}"
    
    # 处理平台内部资源收藏
    elif content_data.shared_item_type and content_data.shared_item_id:
        source_info = await _extract_shared_item_info(
            db, content_data.shared_item_type, content_data.shared_item_id
        )
        
        # 填充缺失的信息
        if not final_title:
            final_title = source_info.get("title", f"{content_data.shared_item_type} #{content_data.shared_item_id}")
        if not final_content:
            final_content = source_info.get("content")
        if not final_url:
            final_url = source_info.get("url")
        if not final_author:
            final_author = source_info.get("author")
        if not final_tags:
            final_tags = source_info.get("tags")
        if not final_type:
            final_type = content_data.shared_item_type
        if not final_thumbnail:
            final_thumbnail = source_info.get("thumbnail")
    
    # 设置默认值
    if not final_title:
        if final_type == "link" and final_url:
            final_title = final_url
        else:
            final_title = "无标题收藏"
    
    if not final_type:
        final_type = "text"
    
    # 生成嵌入向量（简化版本）
    embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    
    # 创建收藏内容实例
    collected_content = CollectedContent(
        owner_id=current_user_id,
        folder_id=content_data.folder_id,
        title=final_title,
        type=final_type,
        url=final_url,
        content=final_content,
        author=final_author,
        tags=final_tags,
        thumbnail=final_thumbnail,
        duration=final_duration,
        file_size=final_file_size,
        status=final_status,
        priority=content_data.priority,
        notes=content_data.notes,
        is_starred=content_data.is_starred,
        shared_item_type=content_data.shared_item_type,
        shared_item_id=content_data.shared_item_id,
        embedding_vector=embedding,
        access_count=0
    )
    
    return collected_content

async def _extract_shared_item_info(db: Session, item_type: str, item_id: int) -> Dict[str, Any]:
    """从共享项中提取信息"""
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
    
    source_model = model_map.get(item_type)
    if not source_model:
        return {}
    
    source_item = db.get(source_model, item_id)
    if not source_item:
        return {}
    
    # 提取通用信息
    info = {}
    
    # 标题
    info["title"] = (
        getattr(source_item, 'title', None) or 
        getattr(source_item, 'name', None) or
        f"{item_type} #{item_id}"
    )
    
    # 内容
    info["content"] = (
        getattr(source_item, 'description', None) or
        getattr(source_item, 'content', None)
    )
    
    # URL
    if hasattr(source_item, 'url') and source_item.url:
        info["url"] = source_item.url
    elif hasattr(source_item, 'media_url') and source_item.media_url:
        info["url"] = source_item.media_url
    elif hasattr(source_item, 'file_path') and source_item.file_path:
        info["url"] = source_item.file_path
    
    # 作者
    if hasattr(source_item, 'owner') and source_item.owner:
        info["author"] = source_item.owner.name
    elif hasattr(source_item, 'creator') and source_item.creator:
        info["author"] = source_item.creator.name
    elif hasattr(source_item, 'sender') and source_item.sender:
        info["author"] = source_item.sender.name
    
    # 标签
    info["tags"] = getattr(source_item, 'tags', None)
    
    # 缩略图
    info["thumbnail"] = (
        getattr(source_item, 'thumbnail', None) or
        getattr(source_item, 'cover_image_url', None)
    )
    
    return info
