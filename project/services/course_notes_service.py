# project/services/course_notes_service.py
"""
课程笔记服务层 - 统一课程笔记管理业务逻辑
应用成熟的优化模式到course_notes模块
"""
import asyncio
import uuid
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Union

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func, asc
import logging

from project.models import Note, Folder, Course, User
from project.utils.optimization.production_utils import cache_manager
from project.utils import get_user_resource_or_404
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
import project.oss_utils as oss_utils

logger = logging.getLogger(__name__)

class CourseNotesFolderService:
    """课程笔记文件夹核心业务逻辑服务"""
    
    @staticmethod
    def create_folder_optimized(
        db: Session, user_id: int, folder_data: Dict[str, Any]
    ) -> Folder:
        """优化的文件夹创建"""
        db_folder = Folder(
            owner_id=user_id,
            name=folder_data["name"],
            description=folder_data.get("description"),
            parent_id=folder_data.get("parent_id"),
            icon=folder_data.get("icon", "📁"),
            color=folder_data.get("color", "#3498db"),
            is_public=folder_data.get("is_public", False)
        )
        
        db.add(db_folder)
        db.flush()  # 获取ID但不提交
        
        # 缓存新文件夹
        cache_key = f"course_notes_folder:{db_folder.id}"
        cache_manager.set(cache_key, db_folder, expire=3600)
        
        return db_folder
    
    @staticmethod
    def get_folder_optimized(db: Session, folder_id: int, user_id: int) -> Folder:
        """优化的文件夹查询 - 使用缓存和预加载"""
        cache_key = f"course_notes_folder:{folder_id}"
        
        # 尝试从缓存获取
        cached_folder = cache_manager.get(cache_key)
        if cached_folder and cached_folder.owner_id == user_id:
            return cached_folder
        
        # 使用预加载查询
        folder = db.query(Folder).options(
            joinedload(Folder.notes),
            joinedload(Folder.children),
            joinedload(Folder.parent)
        ).filter(
            Folder.id == folder_id,
            Folder.owner_id == user_id
        ).first()
        
        if not folder:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件夹不存在或无权访问"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, folder, expire=3600)
        return folder
    
    @staticmethod
    def get_user_folders_tree_optimized(db: Session, user_id: int) -> List[Folder]:
        """优化的文件夹树查询"""
        cache_key = f"course_notes_folders_tree:{user_id}"
        
        # 尝试从缓存获取
        cached_tree = cache_manager.get(cache_key)
        if cached_tree:
            return cached_tree
        
        # 查询所有文件夹并构建树结构
        folders = db.query(Folder).options(
            joinedload(Folder.notes),
            joinedload(Folder.children)
        ).filter(
            Folder.owner_id == user_id
        ).order_by(Folder.name).all()
        
        # 构建树形结构
        folder_tree = CourseNotesUtils.build_folder_tree(folders)
        
        # 缓存结果
        cache_manager.set(cache_key, folder_tree, expire=1800)  # 30分钟
        
        return folder_tree
    
    @staticmethod
    def update_folder_optimized(
        db: Session, folder_id: int, user_id: int, update_data: Dict[str, Any]
    ) -> Folder:
        """优化的文件夹更新"""
        folder = CourseNotesFolderService.get_folder_optimized(db, folder_id, user_id)
        
        # 更新字段
        for key, value in update_data.items():
            if hasattr(folder, key):
                setattr(folder, key, value)
        
        folder.updated_at = datetime.now()
        db.add(folder)
        
        # 更新缓存
        cache_key = f"course_notes_folder:{folder_id}"
        cache_manager.set(cache_key, folder, expire=3600)
        
        # 清除树形结构缓存
        tree_cache_key = f"course_notes_folders_tree:{user_id}"
        cache_manager.delete(tree_cache_key)
        
        return folder
    
    @staticmethod
    def delete_folder_optimized(db: Session, folder_id: int, user_id: int):
        """优化的文件夹删除"""
        folder = CourseNotesFolderService.get_folder_optimized(db, folder_id, user_id)
        
        # 检查是否有子文件夹或笔记
        children_count = db.query(func.count(Folder.id)).filter(
            Folder.parent_id == folder_id
        ).scalar()
        
        notes_count = db.query(func.count(Note.id)).filter(
            Note.folder_id == folder_id
        ).scalar()
        
        if children_count > 0 or notes_count > 0:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件夹非空，无法删除"
            )
        
        db.delete(folder)
        
        # 清除缓存
        cache_key = f"course_notes_folder:{folder_id}"
        cache_manager.delete(cache_key)
        
        tree_cache_key = f"course_notes_folders_tree:{user_id}"
        cache_manager.delete(tree_cache_key)
    
    @staticmethod
    def get_public_folders_optimized(
        db: Session, skip: int = 0, limit: int = 20, search_query: Optional[str] = None
    ) -> Tuple[List[Folder], int]:
        """获取公开的课程笔记文件夹"""
        cache_key = f"public_course_notes_folders:{skip}:{limit}:{search_query or 'all'}"
        
        # 尝试从缓存获取
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建查询
        query = db.query(Folder).options(
            joinedload(Folder.owner),
            joinedload(Folder.notes)
        ).filter(Folder.is_public == True)
        
        # 添加搜索条件
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    Folder.name.ilike(search_term),
                    Folder.description.ilike(search_term)
                )
            )
        
        # 获取总数
        total = query.count()
        
        # 获取分页数据
        folders = query.order_by(desc(Folder.updated_at)).offset(skip).limit(limit).all()
        
        result = (folders, total)
        
        # 缓存结果
        cache_manager.set(cache_key, result, expire=300)  # 5分钟缓存
        
        return result
    
    @staticmethod
    def search_public_folders_optimized(
        db: Session, 
        query_text: str,
        skip: int = 0, 
        limit: int = 20,
        owner_name: Optional[str] = None
    ) -> Tuple[List[Folder], int]:
        """搜索公开的课程笔记文件夹"""
        cache_key = f"search_public_folders:{query_text}:{owner_name or 'all'}:{skip}:{limit}"
        
        # 尝试从缓存获取
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建查询
        query = db.query(Folder).options(
            joinedload(Folder.owner),
            joinedload(Folder.notes)
        ).filter(Folder.is_public == True)
        
        # 添加搜索条件
        search_term = f"%{query_text}%"
        query = query.filter(
            or_(
                Folder.name.ilike(search_term),
                Folder.description.ilike(search_term)
            )
        )
        
        # 添加创建者筛选
        if owner_name:
            from project.models import User
            query = query.join(User).filter(User.username.ilike(f"%{owner_name}%"))
        
        # 获取总数
        total = query.count()
        
        # 获取分页数据
        folders = query.order_by(desc(Folder.updated_at)).offset(skip).limit(limit).all()
        
        result = (folders, total)
        
        # 缓存结果
        cache_manager.set(cache_key, result, expire=300)  # 5分钟缓存
        
        return result

class CourseNotesService:
    """课程笔记核心业务逻辑服务"""
    
    @staticmethod
    def create_note_optimized(
        db: Session, user_id: int, folder_id: int, note_data: Dict[str, Any],
        embedding: Optional[List[float]] = None
    ) -> Note:
        """优化的笔记创建"""
        db_note = Note(
            owner_id=user_id,
            folder_id=folder_id,
            title=note_data["title"],
            content=note_data["content"],
            course_id=note_data.get("course_id"),
            tags=note_data.get("tags"),
            is_public=note_data.get("is_public", False),
            file_path=note_data.get("file_path"),
            embedding=embedding or GLOBAL_PLACEHOLDER_ZERO_VECTOR
        )
        
        db.add(db_note)
        db.flush()  # 获取ID但不提交
        
        # 缓存新笔记
        cache_key = f"course_note:{db_note.id}"
        cache_manager.set(cache_key, db_note, expire=3600)
        
        return db_note
    
    @staticmethod
    def get_note_optimized(db: Session, note_id: int, user_id: int) -> Note:
        """优化的笔记查询 - 使用缓存和预加载"""
        cache_key = f"course_note:{note_id}"
        
        # 尝试从缓存获取
        cached_note = cache_manager.get(cache_key)
        if cached_note and cached_note.owner_id == user_id:
            return cached_note
        
        # 使用预加载查询
        note = db.query(Note).options(
            joinedload(Note.folder),
            joinedload(Note.course),
            joinedload(Note.owner)
        ).filter(
            Note.id == note_id,
            Note.owner_id == user_id
        ).first()
        
        if not note:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="笔记不存在或无权访问"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, note, expire=3600)
        return note
    
    @staticmethod
    def get_folder_notes_optimized(
        db: Session, folder_id: int, user_id: int,
        page: int = 1, page_size: int = 20,
        course_id: Optional[int] = None,
        sort_by: str = "created_at", sort_order: str = "desc"
    ) -> Tuple[List[Note], int]:
        """优化的文件夹笔记查询 - 支持分页和过滤"""
        
        # 构建基础查询
        query = db.query(Note).options(
            joinedload(Note.course),
            joinedload(Note.folder)
        ).filter(
            Note.folder_id == folder_id,
            Note.owner_id == user_id
        )
        
        # 应用课程过滤
        if course_id:
            query = query.filter(Note.course_id == course_id)
        
        # 获取总数
        total_count = query.count()
        
        # 应用排序
        order_field = getattr(Note, sort_by, Note.created_at)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(order_field))
        else:
            query = query.order_by(asc(order_field))
        
        # 应用分页
        offset = (page - 1) * page_size
        notes = query.offset(offset).limit(page_size).all()
        
        return notes, total_count
    
    @staticmethod
    def update_note_optimized(
        db: Session, note_id: int, user_id: int, update_data: Dict[str, Any],
        new_embedding: Optional[List[float]] = None
    ) -> Note:
        """优化的笔记更新"""
        note = CourseNotesService.get_note_optimized(db, note_id, user_id)
        
        # 更新字段
        for key, value in update_data.items():
            if hasattr(note, key):
                setattr(note, key, value)
        
        if new_embedding:
            note.embedding = new_embedding
        
        note.updated_at = datetime.now()
        db.add(note)
        
        # 更新缓存
        cache_key = f"course_note:{note_id}"
        cache_manager.set(cache_key, note, expire=3600)
        
        return note
    
    @staticmethod
    def delete_note_optimized(db: Session, note_id: int, user_id: int):
        """优化的笔记删除"""
        note = CourseNotesService.get_note_optimized(db, note_id, user_id)
        
        # 删除关联的文件
        if note.file_path:
            try:
                oss_utils.delete_file(note.file_path)
            except Exception as e:
                logger.warning(f"删除文件失败: {e}")
        
        db.delete(note)
        
        # 清除缓存
        cache_key = f"course_note:{note_id}"
        cache_manager.delete(cache_key)
    
    @staticmethod
    def move_note_optimized(
        db: Session, note_id: int, user_id: int, target_folder_id: int
    ) -> Note:
        """优化的笔记移动"""
        note = CourseNotesService.get_note_optimized(db, note_id, user_id)
        
        # 验证目标文件夹
        target_folder = CourseNotesFolderService.get_folder_optimized(
            db, target_folder_id, user_id
        )
        
        note.folder_id = target_folder_id
        note.updated_at = datetime.now()
        db.add(note)
        
        # 更新缓存
        cache_key = f"course_note:{note_id}"
        cache_manager.set(cache_key, note, expire=3600)
        
        return note
    
    @staticmethod
    def batch_move_notes_optimized(
        db: Session, note_ids: List[int], user_id: int, target_folder_id: int
    ) -> Dict[str, Any]:
        """优化的批量笔记移动"""
        # 验证目标文件夹
        target_folder = CourseNotesFolderService.get_folder_optimized(
            db, target_folder_id, user_id
        )
        
        success_count = 0
        failed_notes = []
        
        for note_id in note_ids:
            try:
                note = CourseNotesService.get_note_optimized(db, note_id, user_id)
                note.folder_id = target_folder_id
                note.updated_at = datetime.now()
                db.add(note)
                
                # 更新缓存
                cache_key = f"course_note:{note_id}"
                cache_manager.set(cache_key, note, expire=3600)
                
                success_count += 1
            except Exception as e:
                failed_notes.append({"note_id": note_id, "error": str(e)})
        
        return {
            "success_count": success_count,
            "failed_count": len(failed_notes),
            "failed_notes": failed_notes
        }
    
    @staticmethod
    def batch_delete_notes_optimized(
        db: Session, note_ids: List[int], user_id: int
    ) -> Dict[str, Any]:
        """优化的批量笔记删除"""
        success_count = 0
        failed_notes = []
        
        for note_id in note_ids:
            try:
                CourseNotesService.delete_note_optimized(db, note_id, user_id)
                success_count += 1
            except Exception as e:
                failed_notes.append({"note_id": note_id, "error": str(e)})
        
        return {
            "success_count": success_count,
            "failed_count": len(failed_notes),
            "failed_notes": failed_notes
        }
    
    @staticmethod
    async def search_notes_optimized(
        db: Session, user_id: int, query: str,
        folder_id: Optional[int] = None,
        course_id: Optional[int] = None,
        limit: int = 20
    ) -> List[Tuple[Note, float]]:
        """优化的笔记搜索 - 支持语义搜索"""
        
        # 构建基础查询
        base_query = db.query(Note).options(
            joinedload(Note.folder),
            joinedload(Note.course)
        ).filter(Note.owner_id == user_id)
        
        # 应用过滤条件
        if folder_id:
            base_query = base_query.filter(Note.folder_id == folder_id)
        if course_id:
            base_query = base_query.filter(Note.course_id == course_id)
        
        # 关键词搜索
        keyword_results = base_query.filter(
            or_(
                Note.title.ilike(f"%{query}%"),
                Note.content.ilike(f"%{query}%"),
                Note.tags.ilike(f"%{query}%")
            )
        ).limit(limit).all()
        
        # 语义搜索（如果有嵌入向量）
        try:
            query_embedding = await get_embeddings_from_api([query])
            if query_embedding:
                semantic_results = []
                all_notes = base_query.all()
                
                for note in all_notes:
                    if note.embedding and note.embedding != GLOBAL_PLACEHOLDER_ZERO_VECTOR:
                        similarity = CourseNotesUtils.calculate_cosine_similarity(
                            query_embedding[0], note.embedding
                        )
                        semantic_results.append((note, similarity))
                
                # 合并结果并去重
                combined_results = []
                keyword_note_ids = {note.id for note in keyword_results}
                
                # 添加关键词结果（相似度设为1.0）
                for note in keyword_results:
                    combined_results.append((note, 1.0))
                
                # 添加语义搜索结果（排除已有的关键词结果）
                for note, similarity in semantic_results:
                    if note.id not in keyword_note_ids and similarity > 0.7:
                        combined_results.append((note, similarity))
                
                # 按相似度排序
                combined_results.sort(key=lambda x: x[1], reverse=True)
                return combined_results[:limit]
        
        except Exception as e:
            logger.warning(f"语义搜索失败，使用关键词搜索: {e}")
        
        # 返回关键词搜索结果
        return [(note, 1.0) for note in keyword_results]
    
    @staticmethod
    def get_notes_statistics_optimized(
        db: Session, user_id: int, folder_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """优化的笔记统计"""
        base_query = db.query(Note).filter(Note.owner_id == user_id)
        
        if folder_id:
            base_query = base_query.filter(Note.folder_id == folder_id)
        
        # 基础统计
        total_notes = base_query.count()
        public_notes = base_query.filter(Note.is_public == True).count()
        
        # 按课程统计
        course_stats = db.query(
            Course.name,
            func.count(Note.id).label('note_count')
        ).join(Note, Note.course_id == Course.id).filter(
            Note.owner_id == user_id
        ).group_by(Course.id, Course.name).all()
        
        # 按文件夹统计
        folder_stats = db.query(
            Folder.name,
            func.count(Note.id).label('note_count')
        ).join(Note, Note.folder_id == Folder.id).filter(
            Note.owner_id == user_id
        ).group_by(Folder.id, Folder.name).all()
        
        # 最近活动
        recent_notes = base_query.order_by(desc(Note.updated_at)).limit(5).all()
        
        return {
            "total_notes": total_notes,
            "public_notes": public_notes,
            "private_notes": total_notes - public_notes,
            "course_distribution": [
                {"course_name": name, "note_count": count} 
                for name, count in course_stats
            ],
            "folder_distribution": [
                {"folder_name": name, "note_count": count} 
                for name, count in folder_stats
            ],
            "recent_activity": [
                CourseNotesUtils.format_note_response(note) 
                for note in recent_notes
            ]
        }
    
    @staticmethod
    def export_notes_optimized(notes: List[Note], format: str = "json") -> Dict[str, Any]:
        """优化的笔记导出"""
        if format.lower() == "json":
            return {
                "format": "json",
                "export_date": datetime.now().isoformat(),
                "total_notes": len(notes),
                "notes": [CourseNotesUtils.format_note_for_export(note) for note in notes]
            }
        elif format.lower() == "markdown":
            markdown_content = []
            for note in notes:
                markdown_content.append(f"# {note.title}\n\n")
                if note.course:
                    markdown_content.append(f"**课程**: {note.course.name}\n\n")
                if note.tags:
                    markdown_content.append(f"**标签**: {note.tags}\n\n")
                markdown_content.append(f"{note.content}\n\n")
                markdown_content.append(f"---\n\n")
            
            return {
                "format": "markdown",
                "content": "".join(markdown_content),
                "total_notes": len(notes)
            }
        else:
            # 默认文本格式
            text_content = []
            for note in notes:
                text_content.append(f"标题: {note.title}\n")
                if note.course:
                    text_content.append(f"课程: {note.course.name}\n")
                if note.tags:
                    text_content.append(f"标签: {note.tags}\n")
                text_content.append(f"内容:\n{note.content}\n")
                text_content.append(f"创建时间: {note.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
                text_content.append("="*50 + "\n\n")
            
            return {
                "format": "text",
                "content": "".join(text_content),
                "total_notes": len(notes)
            }

class CourseNotesUtils:
    """课程笔记工具类"""
    
    @staticmethod
    def validate_note_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证笔记数据"""
        validated_data = {}
        
        # 验证标题
        title = data.get("title", "").strip()
        if not title:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="笔记标题不能为空"
            )
        validated_data["title"] = title
        
        # 验证内容
        content = data.get("content", "").strip()
        validated_data["content"] = content
        
        # 验证其他字段
        if "course_id" in data:
            validated_data["course_id"] = data["course_id"]
        if "tags" in data:
            validated_data["tags"] = data["tags"]
        if "is_public" in data:
            validated_data["is_public"] = data["is_public"]
        if "file_path" in data:
            validated_data["file_path"] = data["file_path"]
        
        return validated_data
    
    @staticmethod
    def validate_folder_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证文件夹数据"""
        validated_data = {}
        
        # 验证名称
        name = data.get("name", "").strip()
        if not name:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件夹名称不能为空"
            )
        validated_data["name"] = name
        
        # 验证其他字段
        if "description" in data:
            validated_data["description"] = data["description"]
        if "parent_id" in data:
            validated_data["parent_id"] = data["parent_id"]
        if "icon" in data:
            validated_data["icon"] = data["icon"]
        if "color" in data:
            validated_data["color"] = data["color"]
        
        return validated_data
    
    @staticmethod
    def build_folder_tree(folders: List[Folder]) -> List[Folder]:
        """构建文件夹树形结构"""
        folder_map = {folder.id: folder for folder in folders}
        root_folders = []
        
        for folder in folders:
            if folder.parent_id is None:
                root_folders.append(folder)
            else:
                parent = folder_map.get(folder.parent_id)
                if parent:
                    if not hasattr(parent, '_children'):
                        parent._children = []
                    parent._children.append(folder)
        
        return root_folders
    
    @staticmethod
    def format_note_response(note: Note) -> Dict[str, Any]:
        """格式化笔记响应"""
        return {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "course_id": note.course_id,
            "course_name": note.course.name if note.course else None,
            "folder_id": note.folder_id,
            "folder_name": note.folder.name if note.folder else None,
            "tags": note.tags,
            "is_public": note.is_public,
            "file_path": note.file_path,
            "created_at": note.created_at,
            "updated_at": note.updated_at,
            "owner_id": note.owner_id
        }
    
    @staticmethod
    def format_folder_response(folder: Folder) -> Dict[str, Any]:
        """格式化文件夹响应"""
        return {
            "id": folder.id,
            "name": folder.name,
            "description": folder.description,
            "parent_id": folder.parent_id,
            "icon": folder.icon,
            "color": folder.color,
            "is_public": folder.is_public,
            "note_count": len(folder.notes) if folder.notes else 0,
            "children_count": len(folder.children) if folder.children else 0,
            "created_at": folder.created_at,
            "updated_at": folder.updated_at,
            "owner_id": folder.owner_id
        }
    
    @staticmethod
    def format_note_for_export(note: Note) -> Dict[str, Any]:
        """格式化笔记用于导出"""
        return {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "course_name": note.course.name if note.course else None,
            "folder_name": note.folder.name if note.folder else None,
            "tags": note.tags,
            "is_public": note.is_public,
            "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat() if note.updated_at else None
        }
    
    @staticmethod
    def calculate_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import math
        
        # 计算点积
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        
        # 计算向量长度
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))
        
        # 避免除零错误
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)

class CourseNotesEmbeddingService:
    """课程笔记嵌入向量服务"""
    
    @staticmethod
    async def generate_note_embedding_optimized(
        title: str, content: str, tags: Optional[str] = None
    ) -> List[float]:
        """优化的笔记嵌入向量生成"""
        # 构建用于嵌入的文本
        text_parts = [title, content]
        if tags:
            text_parts.append(f"标签: {tags}")
        
        combined_text = ". ".join(filter(None, text_parts))
        
        # 使用缓存避免重复计算
        cache_key = f"embedding:course_note:{hash(combined_text)}"
        cached_embedding = cache_manager.get(cache_key)
        
        if cached_embedding:
            return cached_embedding
        
        # 生成新的嵌入向量
        try:
            embeddings = await get_embeddings_from_api([combined_text])
            if embeddings and embeddings[0]:
                embedding = embeddings[0]
            else:
                embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        except Exception as e:
            logger.warning(f"生成嵌入向量失败: {e}")
            embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        
        # 缓存结果
        cache_manager.set(cache_key, embedding, expire=86400)  # 24小时
        
        return embedding
