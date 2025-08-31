# project/routers/collections/collections.py
"""
新一代收藏管理系统 - 以文件夹为核心的设计

设计理念：
1. 文件夹是收藏系统的核心实体，所有收藏内容都围绕文件夹展开
2. 支持多级文件夹嵌套，提供类似文件系统的体验
3. 统一的收藏接口，无论是内部资源还是外部链接
4. 智能的默认分类和自动标签
5. 高效的搜索和过滤功能
6. 支持聊天室内容收藏：文件、图片、视频、语音
7. 支持论坛内容收藏：附件、论坛话题
"""

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal, Union, Tuple
import numpy as np
import logging
from datetime import timedelta, datetime, timezone, date
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc, asc, text
from jose import JWTError, jwt
import requests, secrets, json, os, uuid, asyncio, httpx, re, traceback, time

# 导入数据库和模型
from project.database import SessionLocal, engine, init_db, get_db
from project.models import Student, Project, Note, KnowledgeBase, Course, UserCourse, CollectionItem, \
    Folder, CollectedContent, ChatRoom, ChatMessage, ForumTopic, ForumComment, ForumLike, UserFollow, \
    UserMcpConfig, UserSearchEngineConfig, ChatRoomMember, \
    ChatRoomJoinRequest, Achievement, UserAchievement, PointTransaction, CourseMaterial, AIConversation, \
    AIConversationMessage, ProjectApplication, ProjectMember, KnowledgeBaseFolder, AIConversationTemporaryFile, \
    CourseLike, ProjectLike, ProjectFile
from project.dependencies.dependencies import get_current_user_id
from project.utils.utils import _get_text_part
import project.schemas as schemas
import project.oss_utils as oss_utils
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_user_model_for_provider
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key

# 设置日志记录器
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/collections",
    tags=["新一代收藏管理"],
    responses={404: {"description": "Not found"}},
)

# ================== 文件夹管理 API ==================

@router.get("/folders", response_model=List[schemas.FolderResponseNew], summary="获取用户的文件夹树结构")
async def get_folder_tree(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    parent_id: Optional[int] = Query(None, description="父文件夹ID，为空时获取根级文件夹"),
    include_empty: bool = Query(True, description="是否包含空文件夹"),
    expand_all: bool = Query(False, description="是否展开所有子文件夹"),
    include_stats: bool = Query(True, description="是否包含统计信息")
):
    """
    获取用户的文件夹树结构
    - 支持层级展示
    - 可选择是否包含空文件夹
    - 自动计算每个文件夹的内容数量和统计信息
    """
    try:
        base_query = db.query(Folder).filter(
            Folder.owner_id == current_user_id,
            Folder.parent_id == parent_id
        ).order_by(Folder.order.asc(), Folder.name.asc())
        
        folders = base_query.all()
        
        result = []
        for folder in folders:
            # 计算内容统计
            content_count = db.query(CollectedContent).filter(
                CollectedContent.folder_id == folder.id,
                CollectedContent.owner_id == current_user_id,
                CollectedContent.status != "deleted"
            ).count()
            
            subfolder_count = db.query(Folder).filter(
                Folder.parent_id == folder.id,
                Folder.owner_id == current_user_id
            ).count()
            
            total_count = content_count + subfolder_count
            
            # 如果不包含空文件夹且文件夹为空，跳过
            if not include_empty and total_count == 0:
                continue
            
            # 创建响应对象
            folder_response = schemas.FolderResponseNew(
                id=folder.id,
                owner_id=folder.owner_id,
                name=folder.name,
                description=folder.description,
                color=folder.color,
                icon=folder.icon,
                parent_id=folder.parent_id,
                order=folder.order,
                item_count=total_count,
                content_count=content_count,
                subfolder_count=subfolder_count,
                created_at=folder.created_at,
                updated_at=folder.updated_at
            )
            
            # 包含统计信息
            if include_stats:
                # 计算文件夹深度
                folder_response.depth = await _calculate_folder_depth(db, folder.id)
                
                # 计算文件夹路径
                folder_response.path = await _get_folder_path(db, folder.id, current_user_id)
                
                # 计算总文件大小
                total_size = db.query(func.sum(CollectedContent.file_size)).filter(
                    CollectedContent.folder_id == folder.id,
                    CollectedContent.owner_id == current_user_id,
                    CollectedContent.status != "deleted"
                ).scalar() or 0
                folder_response.total_size = total_size
                
                # 最后访问时间（基于收藏内容的最新访问）
                last_accessed = db.query(func.max(CollectedContent.updated_at)).filter(
                    CollectedContent.folder_id == folder.id,
                    CollectedContent.owner_id == current_user_id
                ).scalar()
                folder_response.last_accessed = last_accessed
            
            # 如果需要展开所有子文件夹，递归获取
            if expand_all:
                children = await get_folder_tree(
                    current_user_id=current_user_id,
                    db=db,
                    parent_id=folder.id,
                    include_empty=include_empty,
                    expand_all=True,
                    include_stats=include_stats
                )
                folder_response.children = children
            
            result.append(folder_response)
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文件夹树失败: {str(e)}"
        )

@router.post("/folders", response_model=schemas.FolderResponseNew, summary="创建新文件夹")
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
    try:
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
            folder_data.color = _suggest_folder_color(folder_data.name)
        
        if not folder_data.icon:
            folder_data.icon = _suggest_folder_icon(folder_data.name)
        
        # 设置排序值
        if folder_data.order is None:
            max_order = db.query(func.max(Folder.order)).filter(
                Folder.owner_id == current_user_id,
                Folder.parent_id == folder_data.parent_id
            ).scalar() or 0
            folder_data.order = max_order + 1
        
        # 创建文件夹
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
        
        # 创建响应对象
        folder_response = schemas.FolderResponseNew(
            id=db_folder.id,
            owner_id=db_folder.owner_id,
            name=db_folder.name,
            description=db_folder.description,
            color=db_folder.color,
            icon=db_folder.icon,
            parent_id=db_folder.parent_id,
            order=db_folder.order,
            item_count=0,
            content_count=0,
            subfolder_count=0,
            total_size=0,
            depth=await _calculate_folder_depth(db, db_folder.id),
            created_at=db_folder.created_at,
            updated_at=db_folder.updated_at
        )
        
        return folder_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建文件夹失败: {str(e)}"
        )

@router.get("/folders/{folder_id}", response_model=schemas.FolderResponseNew, summary="获取文件夹详情")
async def get_folder_details(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    include_children: bool = Query(False, description="是否包含子文件夹"),
    include_contents: bool = Query(False, description="是否包含收藏内容预览")
):
    """
    获取指定文件夹的详细信息
    - 包含完整统计信息
    - 包含路径信息
    - 可选包含子文件夹和内容预览
    """
    try:
        folder = db.query(Folder).filter(
            Folder.id == folder_id,
            Folder.owner_id == current_user_id
        ).first()
        
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件夹不存在或无权访问"
            )
        
        # 计算统计信息
        content_count = db.query(CollectedContent).filter(
            CollectedContent.folder_id == folder_id,
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status != "deleted"
        ).count()
        
        subfolder_count = db.query(Folder).filter(
            Folder.parent_id == folder_id,
            Folder.owner_id == current_user_id
        ).count()
        
        total_size = db.query(func.sum(CollectedContent.file_size)).filter(
            CollectedContent.folder_id == folder_id,
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status != "deleted"
        ).scalar() or 0
        
        # 内容类型统计
        content_type_stats = db.query(
            CollectedContent.type,
            func.count(CollectedContent.id).label('count')
        ).filter(
            CollectedContent.folder_id == folder_id,
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status != "deleted"
        ).group_by(CollectedContent.type).all()
        
        content_by_type = {stat.type: stat.count for stat in content_type_stats}
        
        # 创建响应对象
        folder_response = schemas.FolderResponseNew(
            id=folder.id,
            owner_id=folder.owner_id,
            name=folder.name,
            description=folder.description,
            color=folder.color,
            icon=folder.icon,
            parent_id=folder.parent_id,
            order=folder.order,
            item_count=content_count + subfolder_count,
            content_count=content_count,
            subfolder_count=subfolder_count,
            total_size=total_size,
            depth=await _calculate_folder_depth(db, folder.id),
            path=await _get_folder_path(db, folder.id, current_user_id),
            created_at=folder.created_at,
            updated_at=folder.updated_at,
            stats={
                "content_by_type": content_by_type,
                "total_items": content_count + subfolder_count,
                "storage_used": total_size
            }
        )
        
        # 包含子文件夹
        if include_children:
            children = await get_folder_tree(
                current_user_id=current_user_id,
                db=db,
                parent_id=folder_id,
                include_empty=True,
                expand_all=False,
                include_stats=True
            )
            folder_response.children = children
        
        return folder_response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文件夹详情失败: {str(e)}"
        )

@router.put("/folders/{folder_id}", response_model=schemas.FolderResponseNew, summary="更新文件夹信息")
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
    try:
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
            if new_parent_id and await _would_create_cycle(db, folder_id, new_parent_id, current_user_id):
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
        
        # 返回更新后的文件夹详情
        return await get_folder_details(folder_id, current_user_id, db)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新文件夹失败: {str(e)}"
        )

@router.delete("/folders/{folder_id}", summary="删除文件夹")
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
    try:
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
            CollectedContent.folder_id == folder_id,
            CollectedContent.status != "deleted"
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
        
        # 删除文件夹（级联删除会自动处理子内容）
        db.delete(folder)
        db.commit()
        
        return {"message": "文件夹删除成功", "deleted_folder_id": folder_id}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除文件夹失败: {str(e)}"
        )

# ================== 收藏内容管理 API ==================

@router.get("/folders/{folder_id}/contents", response_model=List[schemas.CollectedContentResponseNew], summary="获取文件夹内容")
async def get_folder_contents(
    folder_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    content_type: Optional[str] = Query(None, description="过滤内容类型"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(50, description="返回数量限制"),
    offset: int = Query(0, description="偏移量"),
    status: str = Query("active", description="内容状态过滤")
):
    """
    获取指定文件夹的内容
    - 支持类型过滤
    - 支持搜索
    - 支持排序
    - 支持分页
    """
    try:
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
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status == status
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
                    CollectedContent.tags.like(search_pattern),
                    CollectedContent.author.like(search_pattern)
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
        
        # 转换为响应模型
        result = []
        for content in contents:
            # 获取文件夹路径
            folder_path = await _get_folder_path(db, content.folder_id, current_user_id)
            folder_path_names = [item["name"] for item in folder_path] if folder_path else []
            
            content_response = schemas.CollectedContentResponseNew(
                id=content.id,
                owner_id=content.owner_id,
                title=content.title,
                type=content.type,
                url=content.url,
                content=content.content,
                tags=content.tags.split(",") if content.tags else [],
                folder_id=content.folder_id,
                priority=content.priority,
                notes=content.notes,
                is_starred=content.is_starred,
                thumbnail=content.thumbnail,
                author=content.author,
                duration=content.duration,
                file_size=content.file_size,
                status=content.status,
                shared_item_type=content.shared_item_type,
                shared_item_id=content.shared_item_id,
                access_count=content.access_count,
                folder_name=folder.name,
                folder_path=folder_path_names,
                created_at=content.created_at,
                updated_at=content.updated_at
            )
            result.append(content_response)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文件夹内容失败: {str(e)}"
        )

@router.post("/folders/{folder_id}/collect", response_model=schemas.CollectedContentResponseNew, summary="向文件夹添加收藏")
async def add_to_folder(
    folder_id: int,
    content_data: schemas.CollectedContentCreateNew,
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
    try:
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
        
        # 创建收藏内容
        collected_content = await _create_collected_content_item_internal(
            db=db,
            current_user_id=current_user_id,
            content_data=content_data,
            uploaded_file_info=uploaded_file_info
        )
        
        db.add(collected_content)
        db.commit()
        db.refresh(collected_content)
        
        # 返回响应模型
        folder_path = await _get_folder_path(db, folder_id, current_user_id)
        folder_path_names = [item["name"] for item in folder_path] if folder_path else []
        
        content_response = schemas.CollectedContentResponseNew(
            id=collected_content.id,
            owner_id=collected_content.owner_id,
            title=collected_content.title,
            type=collected_content.type,
            url=collected_content.url,
            content=collected_content.content,
            tags=collected_content.tags.split(",") if collected_content.tags else [],
            folder_id=collected_content.folder_id,
            priority=collected_content.priority,
            notes=collected_content.notes,
            is_starred=collected_content.is_starred,
            thumbnail=collected_content.thumbnail,
            author=collected_content.author,
            duration=collected_content.duration,
            file_size=collected_content.file_size,
            status=collected_content.status,
            shared_item_type=collected_content.shared_item_type,
            shared_item_id=collected_content.shared_item_id,
            access_count=collected_content.access_count,
            folder_name=folder.name,
            folder_path=folder_path_names,
            created_at=collected_content.created_at,
            updated_at=collected_content.updated_at
        )
        
        return content_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加收藏失败: {str(e)}"
        )

# ================== 快速收藏 API ==================

@router.post("/quick-collect", response_model=schemas.CollectedContentResponseNew, summary="快速收藏")
async def quick_collect(
    request: schemas.QuickCollectRequest,
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
    try:
        # 确定目标文件夹
        target_folder_id = await _determine_target_folder(
            db, current_user_id, request.folder_id, request.folder_name,
            request.shared_item_type, request.url, file
        )
        
        # 构建收藏数据
        content_data = schemas.CollectedContentCreateNew(
            title=request.title,
            url=request.url,
            folder_id=target_folder_id,
            shared_item_type=request.shared_item_type,
            shared_item_id=request.shared_item_id,
            priority=request.priority,
            is_starred=request.is_starred,
            notes=request.notes,
            auto_extract=request.auto_extract,
            auto_classify=request.auto_classify,
            auto_tag=request.auto_tag
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
            uploaded_file_info=uploaded_file_info
        )
        
        db.add(collected_content)
        db.commit()
        db.refresh(collected_content)
        
        # 获取文件夹信息
        folder = db.query(Folder).filter(Folder.id == target_folder_id).first()
        folder_path = await _get_folder_path(db, target_folder_id, current_user_id)
        folder_path_names = [item["name"] for item in folder_path] if folder_path else []
        
        # 返回响应
        content_response = schemas.CollectedContentResponseNew(
            id=collected_content.id,
            owner_id=collected_content.owner_id,
            title=collected_content.title,
            type=collected_content.type,
            url=collected_content.url,
            content=collected_content.content,
            tags=collected_content.tags.split(",") if collected_content.tags else [],
            folder_id=collected_content.folder_id,
            priority=collected_content.priority,
            notes=collected_content.notes,
            is_starred=collected_content.is_starred,
            thumbnail=collected_content.thumbnail,
            author=collected_content.author,
            duration=collected_content.duration,
            file_size=collected_content.file_size,
            status=collected_content.status,
            shared_item_type=collected_content.shared_item_type,
            shared_item_id=collected_content.shared_item_id,
            access_count=collected_content.access_count,
            folder_name=folder.name if folder else None,
            folder_path=folder_path_names,
            created_at=collected_content.created_at,
            updated_at=collected_content.updated_at
        )
        
        return content_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"快速收藏失败: {str(e)}"
        )

# ================== 聊天室内容收藏 API ==================

@router.post("/collect-chat-message/{message_id}", response_model=schemas.CollectedContentResponseNew, summary="收藏聊天消息")
async def collect_chat_message(
    message_id: int,
    folder_id: Optional[int] = Query(None, description="目标文件夹ID"),
    notes: Optional[str] = Query(None, description="收藏备注"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    收藏聊天室消息（支持文件、图片、视频、语音）
    """
    try:
        # 获取聊天消息
        chat_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id
        ).first()
        
        if not chat_message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聊天消息不存在"
            )
        
        # 检查是否有权限访问该聊天室
        room_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == chat_message.room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first()
        
        if not room_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问该聊天室"
            )
        
        # 确定目标文件夹
        if not folder_id:
            folder_id = await _determine_target_folder(
                db, current_user_id, None, None, "chat_message", None, None
            )
        
        # 根据消息类型确定收藏类型
        content_type = _get_content_type_from_chat_message(chat_message)
        
        # 构建收藏数据
        content_data = schemas.CollectedContentCreateNew(
            title=f"聊天消息 - {chat_message.sender.name if chat_message.sender else '未知用户'}",
            type=content_type,
            url=chat_message.media_url,
            content=chat_message.content_text,
            author=chat_message.sender.name if chat_message.sender else None,
            file_size=chat_message.file_size,
            duration=str(chat_message.audio_duration) if chat_message.audio_duration else None,
            folder_id=folder_id,
            shared_item_type="chat_message",
            shared_item_id=message_id,
            notes=notes
        )
        
        # 创建收藏内容
        collected_content = await _create_collected_content_item_internal(
            db=db,
            current_user_id=current_user_id,
            content_data=content_data
        )
        
        db.add(collected_content)
        db.commit()
        db.refresh(collected_content)
        
        # 构建响应
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
        folder_path = await _get_folder_path(db, folder_id, current_user_id)
        folder_path_names = [item["name"] for item in folder_path] if folder_path else []
        
        content_response = schemas.CollectedContentResponseNew(
            id=collected_content.id,
            owner_id=collected_content.owner_id,
            title=collected_content.title,
            type=collected_content.type,
            url=collected_content.url,
            content=collected_content.content,
            tags=collected_content.tags.split(",") if collected_content.tags else [],
            folder_id=collected_content.folder_id,
            priority=collected_content.priority,
            notes=collected_content.notes,
            is_starred=collected_content.is_starred,
            thumbnail=collected_content.thumbnail,
            author=collected_content.author,
            duration=collected_content.duration,
            file_size=collected_content.file_size,
            status=collected_content.status,
            shared_item_type=collected_content.shared_item_type,
            shared_item_id=collected_content.shared_item_id,
            access_count=collected_content.access_count,
            folder_name=folder.name if folder else None,
            folder_path=folder_path_names,
            created_at=collected_content.created_at,
            updated_at=collected_content.updated_at
        )
        
        return content_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"收藏聊天消息失败: {str(e)}"
        )

# ================== 论坛内容收藏 API ==================

@router.post("/collect-forum-topic/{topic_id}", response_model=schemas.CollectedContentResponseNew, summary="收藏论坛话题")
async def collect_forum_topic(
    topic_id: int,
    folder_id: Optional[int] = Query(None, description="目标文件夹ID"),
    notes: Optional[str] = Query(None, description="收藏备注"),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    收藏论坛话题（包括附件）
    """
    try:
        # 获取论坛话题
        forum_topic = db.query(ForumTopic).filter(
            ForumTopic.id == topic_id
        ).first()
        
        if not forum_topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="论坛话题不存在"
            )
        
        # 确定目标文件夹
        if not folder_id:
            folder_id = await _determine_target_folder(
                db, current_user_id, None, None, "forum_topic", None, None
            )
        
        # 根据话题类型确定收藏类型
        content_type = _get_content_type_from_forum_topic(forum_topic)
        
        # 构建收藏数据
        content_data = schemas.CollectedContentCreateNew(
            title=forum_topic.title or f"论坛话题 #{topic_id}",
            type=content_type,
            url=forum_topic.media_url,
            content=forum_topic.content,
            author=forum_topic.owner.name if forum_topic.owner else None,
            file_size=forum_topic.media_size_bytes,
            tags=forum_topic.tags.split(",") if forum_topic.tags else [],
            folder_id=folder_id,
            shared_item_type="forum_topic",
            shared_item_id=topic_id,
            notes=notes
        )
        
        # 创建收藏内容
        collected_content = await _create_collected_content_item_internal(
            db=db,
            current_user_id=current_user_id,
            content_data=content_data
        )
        
        db.add(collected_content)
        db.commit()
        db.refresh(collected_content)
        
        # 构建响应
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
        folder_path = await _get_folder_path(db, folder_id, current_user_id)
        folder_path_names = [item["name"] for item in folder_path] if folder_path else []
        
        content_response = schemas.CollectedContentResponseNew(
            id=collected_content.id,
            owner_id=collected_content.owner_id,
            title=collected_content.title,
            type=collected_content.type,
            url=collected_content.url,
            content=collected_content.content,
            tags=collected_content.tags.split(",") if collected_content.tags else [],
            folder_id=collected_content.folder_id,
            priority=collected_content.priority,
            notes=collected_content.notes,
            is_starred=collected_content.is_starred,
            thumbnail=collected_content.thumbnail,
            author=collected_content.author,
            duration=collected_content.duration,
            file_size=collected_content.file_size,
            status=collected_content.status,
            shared_item_type=collected_content.shared_item_type,
            shared_item_id=collected_content.shared_item_id,
            access_count=collected_content.access_count,
            folder_name=folder.name if folder else None,
            folder_path=folder_path_names,
            created_at=collected_content.created_at,
            updated_at=collected_content.updated_at
        )
        
        return content_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"收藏论坛话题失败: {str(e)}"
        )

# ================== 收藏内容管理 API ==================

@router.get("/contents/{content_id}", response_model=schemas.CollectedContentResponseNew, summary="获取收藏内容详情")
async def get_content_details(
    content_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取收藏内容详情"""
    try:
        content = db.query(CollectedContent).filter(
            CollectedContent.id == content_id,
            CollectedContent.owner_id == current_user_id
        ).first()
        
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="收藏内容不存在或无权访问"
            )
        
        # 更新访问计数
        content.access_count = (content.access_count or 0) + 1
        db.commit()
        
        # 获取文件夹信息
        folder = db.query(Folder).filter(Folder.id == content.folder_id).first()
        folder_path = await _get_folder_path(db, content.folder_id, current_user_id)
        folder_path_names = [item["name"] for item in folder_path] if folder_path else []
        
        content_response = schemas.CollectedContentResponseNew(
            id=content.id,
            owner_id=content.owner_id,
            title=content.title,
            type=content.type,
            url=content.url,
            content=content.content,
            tags=content.tags.split(",") if content.tags else [],
            folder_id=content.folder_id,
            priority=content.priority,
            notes=content.notes,
            is_starred=content.is_starred,
            thumbnail=content.thumbnail,
            author=content.author,
            duration=content.duration,
            file_size=content.file_size,
            status=content.status,
            shared_item_type=content.shared_item_type,
            shared_item_id=content.shared_item_id,
            access_count=content.access_count,
            folder_name=folder.name if folder else None,
            folder_path=folder_path_names,
            created_at=content.created_at,
            updated_at=content.updated_at
        )
        
        return content_response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取内容详情失败: {str(e)}"
        )

@router.put("/contents/{content_id}", response_model=schemas.CollectedContentResponseNew, summary="更新收藏内容")
async def update_content(
    content_id: int,
    content_data: schemas.CollectedContentUpdateNew,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """更新收藏内容"""
    try:
        content = db.query(CollectedContent).filter(
            CollectedContent.id == content_id,
            CollectedContent.owner_id == current_user_id
        ).first()
        
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="收藏内容不存在或无权访问"
            )
        
        # 如果要移动到其他文件夹，验证文件夹权限
        if content_data.folder_id and content_data.folder_id != content.folder_id:
            folder = db.query(Folder).filter(
                Folder.id == content_data.folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not folder:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="目标文件夹不存在或无权访问"
                )
        
        # 应用更新
        update_data = content_data.model_dump(exclude_unset=True)
        
        # 处理标签
        if "tags" in update_data and isinstance(update_data["tags"], list):
            update_data["tags"] = ",".join(update_data["tags"])
        
        for key, value in update_data.items():
            setattr(content, key, value)
        
        db.commit()
        db.refresh(content)
        
        # 返回更新后的内容
        return await get_content_details(content_id, current_user_id, db)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新收藏内容失败: {str(e)}"
        )

@router.delete("/contents/{content_id}", summary="删除收藏内容")
async def delete_content(
    content_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    permanent: bool = Query(False, description="是否永久删除")
):
    """删除收藏内容"""
    try:
        content = db.query(CollectedContent).filter(
            CollectedContent.id == content_id,
            CollectedContent.owner_id == current_user_id
        ).first()
        
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="收藏内容不存在或无权访问"
            )
        
        if permanent:
            # 永久删除
            db.delete(content)
        else:
            # 软删除
            content.status = "deleted"
        
        db.commit()
        
        return {"message": "收藏内容删除成功", "deleted_content_id": content_id, "permanent": permanent}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除收藏内容失败: {str(e)}"
        )

# ================== 搜索和过滤 API ==================

@router.get("/search", response_model=List[schemas.CollectedContentResponseNew], summary="搜索收藏内容")
async def search_collections(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    query: str = Query(..., description="搜索关键词"),
    folder_ids: Optional[List[int]] = Query(None, description="限制在特定文件夹"),
    include_subfolders: bool = Query(True, description="是否包含子文件夹"),
    content_types: Optional[List[str]] = Query(None, description="内容类型过滤"),
    exclude_types: Optional[List[str]] = Query(None, description="排除的内容类型"),
    date_from: Optional[date] = Query(None, description="开始日期"),
    date_to: Optional[date] = Query(None, description="结束日期"),
    is_starred: Optional[bool] = Query(None, description="是否只搜索加星内容"),
    status: str = Query("active", description="内容状态"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    limit: int = Query(50, description="返回数量限制"),
    offset: int = Query(0, description="偏移量")
):
    """
    搜索用户的收藏内容
    - 支持全文搜索
    - 支持文件夹范围限制
    - 支持多维度过滤
    """
    try:
        # 构建基础查询
        base_query = db.query(CollectedContent).filter(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status == status
        )
        
        # 应用搜索条件
        search_pattern = f"%{query}%"
        base_query = base_query.filter(
            or_(
                CollectedContent.title.like(search_pattern),
                CollectedContent.content.like(search_pattern),
                CollectedContent.tags.like(search_pattern),
                CollectedContent.author.like(search_pattern),
                CollectedContent.notes.like(search_pattern)
            )
        )
        
        # 文件夹过滤
        if folder_ids:
            if include_subfolders:
                # 获取所有子文件夹
                all_folder_ids = set(folder_ids)
                for folder_id in folder_ids:
                    subfolder_ids = await _get_all_subfolder_ids(db, folder_id, current_user_id)
                    all_folder_ids.update(subfolder_ids)
                base_query = base_query.filter(CollectedContent.folder_id.in_(all_folder_ids))
            else:
                base_query = base_query.filter(CollectedContent.folder_id.in_(folder_ids))
        
        # 内容类型过滤
        if content_types:
            base_query = base_query.filter(CollectedContent.type.in_(content_types))
        
        if exclude_types:
            base_query = base_query.filter(~CollectedContent.type.in_(exclude_types))
        
        # 日期过滤
        if date_from:
            base_query = base_query.filter(CollectedContent.created_at >= date_from)
        
        if date_to:
            date_to_end = datetime.combine(date_to, datetime.max.time())
            base_query = base_query.filter(CollectedContent.created_at <= date_to_end)
        
        # 星标过滤
        if is_starred is not None:
            base_query = base_query.filter(CollectedContent.is_starred == is_starred)
        
        # 排序
        sort_column = getattr(CollectedContent, sort_by, CollectedContent.created_at)
        if sort_order.lower() == "desc":
            base_query = base_query.order_by(desc(sort_column))
        else:
            base_query = base_query.order_by(asc(sort_column))
        
        # 分页
        results = base_query.offset(offset).limit(limit).all()
        
        # 转换为响应模型
        response_list = []
        for content in results:
            folder = db.query(Folder).filter(Folder.id == content.folder_id).first()
            folder_path = await _get_folder_path(db, content.folder_id, current_user_id)
            folder_path_names = [item["name"] for item in folder_path] if folder_path else []
            
            content_response = schemas.CollectedContentResponseNew(
                id=content.id,
                owner_id=content.owner_id,
                title=content.title,
                type=content.type,
                url=content.url,
                content=content.content,
                tags=content.tags.split(",") if content.tags else [],
                folder_id=content.folder_id,
                priority=content.priority,
                notes=content.notes,
                is_starred=content.is_starred,
                thumbnail=content.thumbnail,
                author=content.author,
                duration=content.duration,
                file_size=content.file_size,
                status=content.status,
                shared_item_type=content.shared_item_type,
                shared_item_id=content.shared_item_id,
                access_count=content.access_count,
                folder_name=folder.name if folder else None,
                folder_path=folder_path_names,
                created_at=content.created_at,
                updated_at=content.updated_at
            )
            response_list.append(content_response)
        
        return response_list
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )

@router.get("/stats", response_model=schemas.FolderStatsResponse, summary="获取收藏统计信息")
async def get_collection_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户的收藏统计信息"""
    try:
        # 总文件夹数
        total_folders = db.query(Folder).filter(
            Folder.owner_id == current_user_id
        ).count()
        
        # 总收藏内容数
        total_contents = db.query(CollectedContent).filter(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status == "active"
        ).count()
        
        # 按类型统计内容
        content_type_stats = db.query(
            CollectedContent.type,
            func.count(CollectedContent.id).label('count')
        ).filter(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status == "active"
        ).group_by(CollectedContent.type).all()
        
        content_by_type = {stat.type: stat.count for stat in content_type_stats}
        
        # 总存储使用量
        storage_used = db.query(func.sum(CollectedContent.file_size)).filter(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.status == "active"
        ).scalar() or 0
        
        # 最近活动（最近30天创建的内容）
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_contents = db.query(CollectedContent).filter(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.created_at >= thirty_days_ago,
            CollectedContent.status == "active"
        ).order_by(desc(CollectedContent.created_at)).limit(10).all()
        
        recent_activity = []
        for content in recent_contents:
            folder = db.query(Folder).filter(Folder.id == content.folder_id).first()
            recent_activity.append({
                "id": content.id,
                "title": content.title,
                "type": content.type,
                "folder_name": folder.name if folder else None,
                "created_at": content.created_at.isoformat()
            })
        
        stats_response = schemas.FolderStatsResponse(
            total_folders=total_folders,
            total_contents=total_contents,
            content_by_type=content_by_type,
            storage_used=storage_used,
            recent_activity=recent_activity
        )
        
        return stats_response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )

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
        "收藏": "#FD79A8",
        "聊天": "#A29BFE",
        "论坛": "#6C5CE7",
        "文件": "#FDCB6E",
        "链接": "#74B9FF",
        "音频": "#E17055",
        "语音": "#E17055"
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
        "收藏": "heart",
        "聊天": "message-circle",
        "论坛": "users",
        "文件": "file",
        "链接": "link",
        "音频": "music",
        "语音": "mic"
    }
    
    name_lower = name.lower()
    for keyword, icon in icon_mapping.items():
        if keyword in name_lower:
            return icon
    
    # 默认图标
    return "folder"

async def _calculate_folder_depth(db: Session, folder_id: int) -> int:
    """计算文件夹深度"""
    depth = 0
    current_id = folder_id
    
    while current_id:
        folder = db.query(Folder).filter(Folder.id == current_id).first()
        if folder and folder.parent_id:
            depth += 1
            current_id = folder.parent_id
        else:
            break
    
    return depth

async def _get_folder_path(db: Session, folder_id: int, user_id: int) -> List[Dict[str, Any]]:
    """获取文件夹路径"""
    path = []
    current_id = folder_id
    
    while current_id:
        folder = db.query(Folder).filter(
            Folder.id == current_id,
            Folder.owner_id == user_id
        ).first()
        
        if folder:
            path.insert(0, {
                "id": folder.id,
                "name": folder.name,
                "icon": folder.icon,
                "color": folder.color
            })
            current_id = folder.parent_id
        else:
            break
    
    return path

async def _would_create_cycle(db: Session, folder_id: int, new_parent_id: int, user_id: int) -> bool:
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

async def _get_all_subfolder_ids(db: Session, folder_id: int, user_id: int) -> List[int]:
    """递归获取所有子文件夹ID"""
    subfolder_ids = []
    
    direct_subfolders = db.query(Folder).filter(
        Folder.parent_id == folder_id,
        Folder.owner_id == user_id
    ).all()
    
    for subfolder in direct_subfolders:
        subfolder_ids.append(subfolder.id)
        # 递归获取子文件夹的子文件夹
        nested_ids = await _get_all_subfolder_ids(db, subfolder.id, user_id)
        subfolder_ids.extend(nested_ids)
    
    return subfolder_ids

async def _determine_target_folder(
    db: Session, 
    user_id: int, 
    specified_folder_id: Optional[int],
    folder_name: Optional[str],
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
    
    # 如果指定了文件夹名称，查找或创建
    if folder_name:
        folder = db.query(Folder).filter(
            Folder.owner_id == user_id,
            Folder.name == folder_name,
            Folder.parent_id.is_(None)
        ).first()
        
        if folder:
            return folder.id
        else:
            # 创建新文件夹
            new_folder = Folder(
                owner_id=user_id,
                name=folder_name,
                description=f"自动创建的{folder_name}文件夹",
                color=_suggest_folder_color(folder_name),
                icon=_suggest_folder_icon(folder_name),
                parent_id=None,
                order=0
            )
            db.add(new_folder)
            db.flush()
            return new_folder.id
    
    # 基于内容类型智能选择文件夹
    auto_folder_name = None
    
    if shared_item_type:
        type_mapping = {
            "project": "项目收藏",
            "course": "课程收藏", 
            "forum_topic": "论坛收藏",
            "note": "笔记收藏",
            "chat_message": "聊天收藏"
        }
        auto_folder_name = type_mapping.get(shared_item_type, "其他收藏")
    elif file:
        if file.content_type.startswith("image/"):
            auto_folder_name = "图片收藏"
        elif file.content_type.startswith("video/"):
            auto_folder_name = "视频收藏"
        elif file.content_type.startswith("audio/"):
            auto_folder_name = "音频收藏"
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
        "size": file_size,
        "url": f"{oss_utils.S3_BASE_URL.rstrip('/')}/{object_name}"
    }

def _get_content_type_from_chat_message(chat_message: ChatMessage) -> str:
    """根据聊天消息确定收藏内容类型"""
    if chat_message.message_type == "image":
        return "image"
    elif chat_message.message_type == "video":
        return "video"
    elif chat_message.message_type == "audio" or chat_message.message_type == "voice":
        return "audio"
    elif chat_message.message_type == "file":
        return "file"
    else:
        return "text"

def _get_content_type_from_forum_topic(forum_topic: ForumTopic) -> str:
    """根据论坛话题确定收藏内容类型"""
    if forum_topic.media_type == "image":
        return "image"
    elif forum_topic.media_type == "video":
        return "video"
    elif forum_topic.media_type == "file":
        return "file"
    else:
        return "forum_topic"

async def _create_collected_content_item_internal(
    db: Session,
    current_user_id: int,
    content_data: schemas.CollectedContentCreateNew,
    uploaded_file_info: Optional[Dict[str, Any]] = None
) -> CollectedContent:
    """
    内部辅助函数：处理收藏内容的创建逻辑
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
    if uploaded_file_info:
        final_url = uploaded_file_info["url"]
        final_file_size = uploaded_file_info["size"]
        
        # 自动推断文件类型
        content_type = uploaded_file_info["content_type"]
        if content_type.startswith("image/"):
            final_type = "image"
        elif content_type.startswith("video/"):
            final_type = "video"
        elif content_type.startswith("audio/"):
            final_type = "audio"
        else:
            final_type = "file"
        
        # 自动设置标题
        if not final_title and uploaded_file_info["filename"]:
            final_title = uploaded_file_info["filename"]
        
        # 自动设置内容描述
        if not final_content:
            final_content = f"上传的{final_type}: {uploaded_file_info['filename']}"
    
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
    
    # 自动提取网页信息（如果是链接）
    elif content_data.url and content_data.auto_extract:
        try:
            extracted_info = await _extract_url_info(content_data.url)
            if not final_title:
                final_title = extracted_info.get("title")
            if not final_content:
                final_content = extracted_info.get("description")
            if not final_thumbnail:
                final_thumbnail = extracted_info.get("thumbnail")
            if not final_author:
                final_author = extracted_info.get("author")
        except (ValueError, httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning(f"Failed to extract URL info for {content_data.url}: {e}")
            # 提取失败不影响收藏
    
    # 设置默认值
    if not final_title:
        if final_type == "link" and final_url:
            final_title = final_url
        else:
            final_title = "无标题收藏"
    
    if not final_type:
        if final_url:
            final_type = "link"
        else:
            final_type = "text"
    
    # 处理标签
    if isinstance(final_tags, list):
        final_tags = ",".join(final_tags)
    
    # 自动生成标签
    if content_data.auto_tag and not final_tags:
        final_tags = _generate_auto_tags(final_title, final_content, final_type)
    
    # 生成嵌入向量（简化版本）
    embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    
    # 构建组合文本用于搜索
    combined_text_parts = []
    if final_title:
        combined_text_parts.append(final_title)
    if final_content:
        combined_text_parts.append(final_content)
    if final_author:
        combined_text_parts.append(final_author)
    if final_tags:
        combined_text_parts.append(final_tags)
    
    combined_text = " ".join(combined_text_parts)
    
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
        priority=content_data.priority or 3,
        notes=content_data.notes,
        is_starred=content_data.is_starred or False,
        shared_item_type=content_data.shared_item_type,
        shared_item_id=content_data.shared_item_id,
        combined_text=combined_text,
        embedding=embedding,
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
        "chat_message": ChatMessage
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
        getattr(source_item, 'content', None) or
        getattr(source_item, 'content_text', None)
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

async def _extract_url_info(url: str) -> Dict[str, Any]:
    """提取URL的基本信息"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            if response.status_code == 200:
                content = response.text
                
                # 简单的HTML解析提取标题
                import re
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else None
                
                # 提取description meta标签
                desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', content, re.IGNORECASE)
                description = desc_match.group(1).strip() if desc_match else None
                
                return {
                    "title": title,
                    "description": description,
                    "thumbnail": None,
                    "author": None
                }
    except (httpx.TimeoutException, httpx.HTTPError, ValueError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to extract URL info from {url}: {e}")
    
    return {}

def _generate_auto_tags(title: str, content: str, content_type: str) -> str:
    """自动生成标签"""
    tags = []
    
    # 基于类型的标签
    type_tags = {
        "image": ["图片", "视觉"],
        "video": ["视频", "影像"],
        "audio": ["音频", "声音"],
        "file": ["文件", "资料"],
        "link": ["链接", "网页"],
        "forum_topic": ["论坛", "讨论"],
        "chat_message": ["聊天", "消息"],
        "project": ["项目"],
        "course": ["课程", "学习"],
        "note": ["笔记", "记录"]
    }
    
    if content_type in type_tags:
        tags.extend(type_tags[content_type])
    
    # 基于关键词的标签
    text_content = f"{title or ''} {content or ''}".lower()
    keyword_tags = {
        "学习": ["学习", "教程", "课程", "教育"],
        "工作": ["工作", "项目", "任务", "业务"],
        "技术": ["技术", "编程", "开发", "代码"],
        "设计": ["设计", "UI", "UX", "界面"],
        "文档": ["文档", "说明", "手册", "指南"]
    }
    
    for tag, keywords in keyword_tags.items():
        if any(keyword in text_content for keyword in keywords):
            tags.append(tag)
    
    return ",".join(tags[:5])  # 最多5个标签
