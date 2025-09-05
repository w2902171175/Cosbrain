# project/services/collections_service.py
"""
收藏服务层 - 统一收藏管理业务逻辑
应用成熟的优化模式到collections模块
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Union

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func, asc
import logging

from project.models import (
    Folder, CollectedContent, Project, Course, 
    ChatMessage, ForumTopic, User, ChatRoomMember
)
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)

class CollectionsFolderService:
    """收藏文件夹核心业务逻辑服务"""
    
    @staticmethod
    def get_folder_optimized(db: Session, folder_id: int, user_id: int) -> Folder:
        """优化的文件夹查询 - 使用预加载和缓存"""
        cache_key = f"folder:{folder_id}:detail"
        
        # 尝试从缓存获取
        cached_folder = cache_manager.get(cache_key)
        if cached_folder:
            return cached_folder
        
        # 使用joinedload预加载相关数据
        folder = db.query(Folder).options(
            joinedload(Folder.collected_contents),
            joinedload(Folder.parent),
            joinedload(Folder.children)
        ).filter(
            Folder.id == folder_id,
            Folder.user_id == user_id,
            Folder.is_deleted == False
        ).first()
        
        if not folder:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件夹不存在"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, folder, expire_time=600)  # 10分钟缓存
        return folder
    
    @staticmethod
    def get_user_folders_tree_optimized(db: Session, user_id: int) -> List[Folder]:
        """优化的用户文件夹树查询"""
        cache_key = f"folders:tree:user:{user_id}"
        
        # 尝试从缓存获取
        cached_tree = cache_manager.get(cache_key)
        if cached_tree:
            return cached_tree
        
        # 获取所有文件夹并构建树结构
        folders = db.query(Folder).options(
            joinedload(Folder.collected_contents)
        ).filter(
            Folder.user_id == user_id,
            Folder.is_deleted == False
        ).order_by(asc(Folder.name)).all()
        
        # 构建树结构
        folder_dict = {folder.id: folder for folder in folders}
        root_folders = []
        
        for folder in folders:
            if folder.parent_id is None:
                root_folders.append(folder)
            else:
                parent = folder_dict.get(folder.parent_id)
                if parent:
                    if not hasattr(parent, '_children_list'):
                        parent._children_list = []
                    parent._children_list.append(folder)
        
        # 缓存结果
        cache_manager.set(cache_key, root_folders, expire_time=300)  # 5分钟缓存
        return root_folders
    
    @staticmethod
    def create_folder_optimized(db: Session, folder_data: dict, user_id: int) -> Folder:
        """优化的文件夹创建"""
        
        # 验证父文件夹（如果指定）
        if folder_data.get("parent_id"):
            parent_folder = CollectionsFolderService.get_folder_optimized(
                db, folder_data["parent_id"], user_id
            )
            if parent_folder.user_id != user_id:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无权限在此文件夹下创建子文件夹"
                )
        
        # 创建文件夹
        folder = Folder(
            name=folder_data["name"],
            description=folder_data.get("description"),
            parent_id=folder_data.get("parent_id"),
            user_id=user_id,
            icon=folder_data.get("icon", "📁"),
            color=folder_data.get("color", "#3498db"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(folder)
        db.flush()
        db.refresh(folder)
        
        # 异步清除相关缓存
        asyncio.create_task(
            cache_manager.delete_pattern(f"folders:tree:user:{user_id}")
        )
        
        return folder
    
    @staticmethod
    def update_folder_optimized(
        db: Session,
        folder_id: int,
        update_data: dict,
        user_id: int
    ) -> Folder:
        """优化的文件夹更新"""
        
        folder = CollectionsFolderService.get_folder_optimized(db, folder_id, user_id)
        
        # 权限检查
        if folder.user_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限修改此文件夹"
            )
        
        # 验证父文件夹移动（避免循环引用）
        if "parent_id" in update_data and update_data["parent_id"] != folder.parent_id:
            if update_data["parent_id"] is not None:
                new_parent = CollectionsFolderService.get_folder_optimized(
                    db, update_data["parent_id"], user_id
                )
                
                # 检查是否会造成循环引用
                if CollectionsFolderService._would_create_cycle(db, folder_id, update_data["parent_id"]):
                    from fastapi import HTTPException, status
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="不能将文件夹移动到其子文件夹中"
                    )
        
        # 更新字段
        for field, value in update_data.items():
            if hasattr(folder, field) and value is not None:
                setattr(folder, field, value)
        
        folder.updated_at = datetime.utcnow()
        db.flush()
        db.refresh(folder)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"folder:{folder_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"folders:tree:user:{user_id}"))
        
        return folder
    
    @staticmethod
    def delete_folder_optimized(db: Session, folder_id: int, user_id: int) -> bool:
        """优化的文件夹删除"""
        
        folder = CollectionsFolderService.get_folder_optimized(db, folder_id, user_id)
        
        # 权限检查
        if folder.user_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限删除此文件夹"
            )
        
        # 检查是否有子文件夹或内容
        has_children = db.query(Folder).filter(
            Folder.parent_id == folder_id,
            Folder.is_deleted == False
        ).first() is not None
        
        has_contents = db.query(CollectedContent).filter(
            CollectedContent.folder_id == folder_id,
            CollectedContent.is_deleted == False
        ).first() is not None
        
        if has_children or has_contents:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法删除包含子文件夹或收藏内容的文件夹"
            )
        
        # 软删除文件夹
        folder.is_deleted = True
        folder.deleted_at = datetime.utcnow()
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"folder:{folder_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"folders:tree:user:{user_id}"))
        
        return True
    
    @staticmethod
    def _would_create_cycle(db: Session, folder_id: int, new_parent_id: int) -> bool:
        """检查移动文件夹是否会创建循环引用"""
        current_id = new_parent_id
        
        while current_id is not None:
            if current_id == folder_id:
                return True
            
            parent = db.query(Folder).filter(Folder.id == current_id).first()
            current_id = parent.parent_id if parent else None
        
        return False
    
    @staticmethod
    def get_folder_stats_optimized(db: Session, user_id: int) -> Dict[str, Any]:
        """优化的文件夹统计"""
        cache_key = f"folders:stats:user:{user_id}"
        cached_stats = cache_manager.get(cache_key)
        if cached_stats:
            return cached_stats
        
        stats = {
            "total_folders": db.query(func.count(Folder.id)).filter(
                Folder.user_id == user_id,
                Folder.is_deleted == False
            ).scalar() or 0,
            
            "total_contents": db.query(func.count(CollectedContent.id)).join(
                Folder, CollectedContent.folder_id == Folder.id
            ).filter(
                Folder.user_id == user_id,
                Folder.is_deleted == False,
                CollectedContent.is_deleted == False
            ).scalar() or 0,
            
            "contents_by_type": db.query(
                CollectedContent.content_type,
                func.count(CollectedContent.id)
            ).join(
                Folder, CollectedContent.folder_id == Folder.id
            ).filter(
                Folder.user_id == user_id,
                Folder.is_deleted == False,
                CollectedContent.is_deleted == False
            ).group_by(CollectedContent.content_type).all(),
            
            "recent_activity": db.query(func.count(CollectedContent.id)).join(
                Folder, CollectedContent.folder_id == Folder.id
            ).filter(
                Folder.user_id == user_id,
                CollectedContent.created_at >= datetime.utcnow() - timedelta(days=7),
                Folder.is_deleted == False,
                CollectedContent.is_deleted == False
            ).scalar() or 0
        }
        
        # 格式化统计结果
        formatted_stats = {
            "total_folders": stats["total_folders"],
            "total_contents": stats["total_contents"],
            "contents_by_type": {content_type: count for content_type, count in stats["contents_by_type"]},
            "recent_activity": stats["recent_activity"]
        }
        
        # 缓存统计结果
        cache_manager.set(cache_key, formatted_stats, expire_time=300)
        return formatted_stats

class CollectedContentService:
    """收藏内容核心业务逻辑服务"""
    
    @staticmethod
    def get_content_optimized(db: Session, content_id: int, user_id: int) -> CollectedContent:
        """优化的收藏内容查询"""
        cache_key = f"content:{content_id}:detail"
        
        # 尝试从缓存获取
        cached_content = cache_manager.get(cache_key)
        if cached_content:
            return cached_content
        
        # 查询内容
        content = db.query(CollectedContent).options(
            joinedload(CollectedContent.folder)
        ).filter(
            CollectedContent.id == content_id,
            CollectedContent.is_deleted == False
        ).first()
        
        if not content:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="收藏内容不存在"
            )
        
        # 权限检查
        if content.folder.user_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问此收藏内容"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, content, expire_time=600)
        return content
    
    @staticmethod
    def get_folder_contents_optimized(
        db: Session,
        folder_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        content_type: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[CollectedContent], int]:
        """优化的文件夹内容查询"""
        
        cache_key = f"folder:{folder_id}:contents:{skip}:{limit}:{content_type or 'all'}:{search or 'all'}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 验证文件夹权限
        CollectionsFolderService.get_folder_optimized(db, folder_id, user_id)
        
        # 构建查询
        query = db.query(CollectedContent).filter(
            CollectedContent.folder_id == folder_id,
            CollectedContent.is_deleted == False
        )
        
        # 应用过滤条件
        if content_type:
            query = query.filter(CollectedContent.content_type == content_type)
        
        if search:
            query = query.filter(
                or_(
                    CollectedContent.title.contains(search),
                    CollectedContent.description.contains(search)
                )
            )
        
        # 排序
        query = query.order_by(desc(CollectedContent.created_at))
        
        # 获取总数和分页结果
        total = query.count()
        contents = query.offset(skip).limit(limit).all()
        
        result = (contents, total)
        cache_manager.set(cache_key, result, expire_time=300)
        return result
    
    @staticmethod
    def create_collected_content_optimized(
        db: Session,
        folder_id: int,
        content_data: dict,
        user_id: int
    ) -> CollectedContent:
        """优化的收藏内容创建"""
        
        # 验证文件夹权限
        folder = CollectionsFolderService.get_folder_optimized(db, folder_id, user_id)
        
        if folder.user_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限在此文件夹中添加收藏"
            )
        
        # 检查是否已收藏
        if content_data.get("resource_type") and content_data.get("resource_id"):
            existing = db.query(CollectedContent).filter(
                CollectedContent.resource_type == content_data["resource_type"],
                CollectedContent.resource_id == content_data["resource_id"],
                CollectedContent.is_deleted == False
            ).first()
            
            if existing:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="该内容已被收藏"
                )
        
        # 创建收藏内容
        content = CollectedContent(
            folder_id=folder_id,
            title=content_data["title"],
            description=content_data.get("description"),
            content_type=content_data["content_type"],
            resource_type=content_data.get("resource_type"),
            resource_id=content_data.get("resource_id"),
            url=content_data.get("url"),
            file_path=content_data.get("file_path"),
            metadata=content_data.get("metadata", {}),
            tags=content_data.get("tags", []),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(content)
        db.flush()
        db.refresh(content)
        
        # 更新文件夹更新时间
        folder.updated_at = datetime.utcnow()
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"folder:{folder_id}:contents:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"folders:stats:user:{user_id}"))
        
        return content
    
    @staticmethod
    def update_collected_content_optimized(
        db: Session,
        content_id: int,
        update_data: dict,
        user_id: int
    ) -> CollectedContent:
        """优化的收藏内容更新"""
        
        content = CollectedContentService.get_content_optimized(db, content_id, user_id)
        
        # 更新字段
        for field, value in update_data.items():
            if hasattr(content, field) and value is not None:
                setattr(content, field, value)
        
        content.updated_at = datetime.utcnow()
        db.flush()
        db.refresh(content)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"content:{content_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"folder:{content.folder_id}:contents:*"))
        
        return content
    
    @staticmethod
    def delete_collected_content_optimized(
        db: Session,
        content_id: int,
        user_id: int
    ) -> bool:
        """优化的收藏内容删除"""
        
        content = CollectedContentService.get_content_optimized(db, content_id, user_id)
        
        # 软删除内容
        content.is_deleted = True
        content.deleted_at = datetime.utcnow()
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"content:{content_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"folder:{content.folder_id}:contents:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"folders:stats:user:{user_id}"))
        
        return True
    
    @staticmethod
    def search_collected_content_optimized(
        db: Session,
        user_id: int,
        query: str,
        content_type: Optional[str] = None,
        folder_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[CollectedContent], int]:
        """优化的收藏内容搜索"""
        
        cache_key = f"search:contents:user:{user_id}:query:{hash(query)}:type:{content_type or 'all'}:folder:{folder_id or 'all'}:{skip}:{limit}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建搜索查询
        search_query = db.query(CollectedContent).join(
            Folder, CollectedContent.folder_id == Folder.id
        ).filter(
            Folder.user_id == user_id,
            Folder.is_deleted == False,
            CollectedContent.is_deleted == False,
            or_(
                CollectedContent.title.contains(query),
                CollectedContent.description.contains(query)
            )
        )
        
        # 应用过滤条件
        if content_type:
            search_query = search_query.filter(
                CollectedContent.content_type == content_type
            )
        
        if folder_id:
            search_query = search_query.filter(
                CollectedContent.folder_id == folder_id
            )
        
        # 执行搜索
        total = search_query.count()
        contents = search_query.order_by(
            desc(CollectedContent.updated_at)
        ).offset(skip).limit(limit).all()
        
        result = (contents, total)
        cache_manager.set(cache_key, result, expire_time=300)
        return result
    
    @staticmethod
    def batch_move_contents_optimized(
        db: Session,
        content_ids: List[int],
        target_folder_id: int,
        user_id: int
    ) -> List[CollectedContent]:
        """优化的批量移动收藏内容"""
        
        # 验证目标文件夹权限
        target_folder = CollectionsFolderService.get_folder_optimized(db, target_folder_id, user_id)
        
        if target_folder.user_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限移动到此文件夹"
            )
        
        # 批量移动内容
        moved_contents = []
        for content_id in content_ids:
            try:
                content = CollectedContentService.get_content_optimized(db, content_id, user_id)
                old_folder_id = content.folder_id
                
                content.folder_id = target_folder_id
                content.updated_at = datetime.utcnow()
                db.flush()
                
                moved_contents.append(content)
                
                # 清除相关缓存
                asyncio.create_task(cache_manager.delete_pattern(f"content:{content_id}:*"))
                asyncio.create_task(cache_manager.delete_pattern(f"folder:{old_folder_id}:contents:*"))
                asyncio.create_task(cache_manager.delete_pattern(f"folder:{target_folder_id}:contents:*"))
                
            except Exception as e:
                logger.warning(f"移动收藏内容 {content_id} 失败: {str(e)}")
                continue
        
        return moved_contents

class CollectionsUtils:
    """收藏工具类"""
    
    @staticmethod
    def validate_folder_data(data: dict) -> dict:
        """验证文件夹数据"""
        errors = []
        
        if not data.get("name") or len(data["name"].strip()) < 1:
            errors.append("文件夹名称不能为空")
        
        if data.get("name") and len(data["name"]) > 100:
            errors.append("文件夹名称不能超过100个字符")
        
        if data.get("description") and len(data["description"]) > 500:
            errors.append("文件夹描述不能超过500个字符")
        
        if errors:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"errors": errors}
            )
        
        return data
    
    @staticmethod
    def validate_content_data(data: dict) -> dict:
        """验证收藏内容数据"""
        errors = []
        
        if not data.get("title") or len(data["title"].strip()) < 1:
            errors.append("标题不能为空")
        
        if data.get("title") and len(data["title"]) > 200:
            errors.append("标题不能超过200个字符")
        
        valid_content_types = ["project", "course", "url", "file", "chat_message", "forum_topic"]
        if not data.get("content_type") or data["content_type"] not in valid_content_types:
            errors.append(f"内容类型必须是: {', '.join(valid_content_types)}")
        
        if errors:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"errors": errors}
            )
        
        return data
    
    @staticmethod
    def format_folder_response(folder: Folder) -> dict:
        """格式化文件夹响应"""
        return {
            "id": folder.id,
            "name": folder.name,
            "description": folder.description,
            "parent_id": folder.parent_id,
            "icon": folder.icon,
            "color": folder.color,
            "content_count": len(folder.collected_contents) if folder.collected_contents else 0,
            "children": [
                CollectionsUtils.format_folder_response(child) 
                for child in getattr(folder, '_children_list', [])
            ],
            "created_at": folder.created_at,
            "updated_at": folder.updated_at
        }
    
    @staticmethod
    def format_content_response(content: CollectedContent) -> dict:
        """格式化收藏内容响应"""
        return {
            "id": content.id,
            "folder_id": content.folder_id,
            "title": content.title,
            "description": content.description,
            "content_type": content.content_type,
            "resource_type": content.resource_type,
            "resource_id": content.resource_id,
            "url": content.url,
            "metadata": content.metadata,
            "tags": content.tags,
            "created_at": content.created_at,
            "updated_at": content.updated_at
        }
    
    @staticmethod
    def get_or_create_default_folder(db: Session, user_id: int, folder_name: str = "默认收藏") -> Folder:
        """获取或创建默认文件夹"""
        folder = db.query(Folder).filter(
            Folder.user_id == user_id,
            Folder.name == folder_name,
            Folder.parent_id.is_(None),
            Folder.is_deleted == False
        ).first()
        
        if not folder:
            folder = Folder(
                name=folder_name,
                description="系统默认创建的收藏文件夹",
                user_id=user_id,
                icon="📁",
                color="#3498db",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(folder)
            db.flush()
            db.refresh(folder)
        
        return folder
