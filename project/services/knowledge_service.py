# project/services/knowledge_service.py
"""
知识库服务层 - 统一知识管理业务逻辑
应用成熟的优化模式到最大的knowledge模块
"""
import asyncio
import hashlib
import json
import mimetypes
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Union
from urllib.parse import urlparse

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func, text
import logging

from project.models import KnowledgeBase, KnowledgeDocument, User
from project.utils.optimization.production_utils import cache_manager
from project.utils.database.optimization import query_optimizer

logger = logging.getLogger(__name__)

class KnowledgeBaseService:
    """知识库核心业务逻辑服务"""
    
    @staticmethod
    def get_knowledge_base_optimized(db: Session, kb_id: int, user_id: int) -> KnowledgeBase:
        """优化的知识库查询 - 使用预加载和缓存"""
        cache_key = f"kb:{kb_id}:detail"
        
        # 尝试从缓存获取
        cached_kb = cache_manager.get(cache_key)
        if cached_kb:
            return cached_kb
        
        # 使用joinedload预加载相关数据
        kb = db.query(KnowledgeBase).options(
            joinedload(KnowledgeBase.owner),
            joinedload(KnowledgeBase.documents)
        ).filter(
            KnowledgeBase.id == kb_id,
            or_(
                KnowledgeBase.owner_id == user_id,
                KnowledgeBase.is_public == True
            )
        ).first()
        
        if not kb:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="知识库不存在或无访问权限"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, kb, expire_time=600)  # 10分钟缓存
        return kb
    
    @staticmethod
    def get_knowledge_bases_list_optimized(
        db: Session,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None
    ) -> Tuple[List[KnowledgeBase], int]:
        """优化的知识库列表查询"""
        
        cache_key = f"kb:list:user:{user_id}:{skip}:{limit}:{search or 'all'}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建基础查询
        query = db.query(KnowledgeBase).options(
            joinedload(KnowledgeBase.owner)
        ).filter(
            or_(
                KnowledgeBase.owner_id == user_id,
                KnowledgeBase.is_public == True
            )
        )
        
        # 应用搜索过滤
        if search:
            query = query.filter(
                or_(
                    KnowledgeBase.name.contains(search),
                    KnowledgeBase.description.contains(search)
                )
            )
        
        # 排序
        query = query.order_by(desc(KnowledgeBase.updated_at))
        
        # 获取总数和分页结果
        total = query.count()
        knowledge_bases = query.offset(skip).limit(limit).all()
        
        result = (knowledge_bases, total)
        cache_manager.set(cache_key, result, expire_time=300)  # 5分钟缓存
        return result
    
    @staticmethod
    def create_knowledge_base_optimized(db: Session, kb_data: dict, user_id: int) -> KnowledgeBase:
        """优化的知识库创建"""
        
        # 创建知识库
        kb = KnowledgeBase(
            name=kb_data["name"],
            description=kb_data.get("description"),
            is_public=kb_data.get("is_public", False),
            owner_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(kb)
        db.flush()
        db.refresh(kb)
        
        # 异步清除相关缓存
        asyncio.create_task(
            cache_manager.delete_pattern(f"kb:list:user:{user_id}:*")
        )
        
        return kb
    
    @staticmethod
    def update_knowledge_base_optimized(
        db: Session,
        kb_id: int,
        update_data: dict,
        user_id: int
    ) -> KnowledgeBase:
        """优化的知识库更新"""
        
        kb = KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, user_id)
        
        # 权限检查
        if kb.owner_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限修改此知识库"
            )
        
        # 更新字段
        for field, value in update_data.items():
            if hasattr(kb, field) and value is not None:
                setattr(kb, field, value)
        
        kb.updated_at = datetime.utcnow()
        db.flush()
        db.refresh(kb)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"kb:list:user:{user_id}:*"))
        
        return kb
    
    @staticmethod
    def delete_knowledge_base_optimized(db: Session, kb_id: int, user_id: int) -> bool:
        """优化的知识库删除"""
        
        kb = KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, user_id)
        
        # 权限检查
        if kb.owner_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限删除此知识库"
            )
        
        # 软删除知识库和相关文档
        kb.is_deleted = True
        kb.deleted_at = datetime.utcnow()
        
        # 删除相关文档
        db.query(KnowledgeDocument).filter(
            KnowledgeDocument.knowledge_base_id == kb_id
        ).update({
            "is_deleted": True,
            "deleted_at": datetime.utcnow()
        })
        
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"kb:list:user:{user_id}:*"))
        
        return True
    
    @staticmethod
    def get_public_knowledge_bases_optimized(
        db: Session, skip: int = 0, limit: int = 20, search_query: Optional[str] = None
    ) -> Tuple[List[KnowledgeBase], int]:
        """获取公开的知识库"""
        cache_key = f"public_knowledge_bases:{skip}:{limit}:{search_query or 'all'}"
        
        # 尝试从缓存获取
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建查询
        query = db.query(KnowledgeBase).options(
            joinedload(KnowledgeBase.owner),
            joinedload(KnowledgeBase.documents)
        ).filter(KnowledgeBase.is_public == True)
        
        # 添加搜索条件
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                or_(
                    KnowledgeBase.name.ilike(search_term),
                    KnowledgeBase.description.ilike(search_term)
                )
            )
        
        # 获取总数
        total = query.count()
        
        # 获取分页数据
        knowledge_bases = query.order_by(desc(KnowledgeBase.updated_at)).offset(skip).limit(limit).all()
        
        result = (knowledge_bases, total)
        
        # 缓存结果
        cache_manager.set(cache_key, result, expire=300)  # 5分钟缓存
        
        return result
    
    @staticmethod
    def search_public_knowledge_bases_optimized(
        db: Session, 
        query_text: str,
        skip: int = 0, 
        limit: int = 20,
        owner_name: Optional[str] = None
    ) -> Tuple[List[KnowledgeBase], int]:
        """搜索公开的知识库"""
        cache_key = f"search_public_knowledge_bases:{query_text}:{owner_name or 'all'}:{skip}:{limit}"
        
        # 尝试从缓存获取
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 构建查询
        query = db.query(KnowledgeBase).options(
            joinedload(KnowledgeBase.owner),
            joinedload(KnowledgeBase.documents)
        ).filter(KnowledgeBase.is_public == True)
        
        # 添加搜索条件
        search_term = f"%{query_text}%"
        query = query.filter(
            or_(
                KnowledgeBase.name.ilike(search_term),
                KnowledgeBase.description.ilike(search_term)
            )
        )
        
        # 添加创建者筛选
        if owner_name:
            query = query.join(User).filter(User.username.ilike(f"%{owner_name}%"))
        
        # 获取总数
        total = query.count()
        
        # 获取分页数据
        knowledge_bases = query.order_by(desc(KnowledgeBase.updated_at)).offset(skip).limit(limit).all()
        
        result = (knowledge_bases, total)
        
        # 缓存结果
        cache_manager.set(cache_key, result, expire=300)  # 5分钟缓存
        
        return result

    @staticmethod
    def get_knowledge_base_stats_optimized(db: Session, kb_id: int, user_id: int) -> Dict[str, Any]:
        """优化的知识库统计"""
        
        cache_key = f"kb:{kb_id}:stats"
        cached_stats = cache_manager.get(cache_key)
        if cached_stats:
            return cached_stats
        
        # 验证权限
        KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, user_id)
        
        # 统计查询
        stats = {
            "total_documents": db.query(func.count(KnowledgeDocument.id)).filter(
                KnowledgeDocument.knowledge_base_id == kb_id,
                KnowledgeDocument.is_deleted == False
            ).scalar() or 0,
            
            "documents_by_type": db.query(
                KnowledgeDocument.content_type,
                func.count(KnowledgeDocument.id)
            ).filter(
                KnowledgeDocument.knowledge_base_id == kb_id,
                KnowledgeDocument.is_deleted == False
            ).group_by(KnowledgeDocument.content_type).all(),
            
            "processing_status": db.query(
                KnowledgeDocument.processing_status,
                func.count(KnowledgeDocument.id)
            ).filter(
                KnowledgeDocument.knowledge_base_id == kb_id,
                KnowledgeDocument.is_deleted == False
            ).group_by(KnowledgeDocument.processing_status).all(),
            
            "total_size": db.query(func.sum(KnowledgeDocument.file_size)).filter(
                KnowledgeDocument.knowledge_base_id == kb_id,
                KnowledgeDocument.is_deleted == False
            ).scalar() or 0
        }
        
        # 格式化统计结果
        formatted_stats = {
            "total_documents": stats["total_documents"],
            "total_size_mb": round((stats["total_size"] or 0) / 1024 / 1024, 2),
            "documents_by_type": {content_type: count for content_type, count in stats["documents_by_type"]},
            "processing_status": {status: count for status, count in stats["processing_status"]}
        }
        
        # 缓存统计结果
        cache_manager.set(cache_key, formatted_stats, expire_time=300)  # 5分钟缓存
        return formatted_stats

class KnowledgeDocumentService:
    """知识文档核心业务逻辑服务"""
    
    @staticmethod
    def get_document_optimized(db: Session, kb_id: int, doc_id: int, user_id: int) -> KnowledgeDocument:
        """优化的文档查询"""
        
        cache_key = f"kb:{kb_id}:doc:{doc_id}"
        cached_doc = cache_manager.get(cache_key)
        if cached_doc:
            return cached_doc
        
        # 验证知识库权限
        KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, user_id)
        
        # 查询文档
        doc = db.query(KnowledgeDocument).options(
            joinedload(KnowledgeDocument.knowledge_base)
        ).filter(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.knowledge_base_id == kb_id,
            KnowledgeDocument.is_deleted == False
        ).first()
        
        if not doc:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        # 缓存结果
        cache_manager.set(cache_key, doc, expire_time=600)
        return doc
    
    @staticmethod
    def get_documents_list_optimized(
        db: Session,
        kb_id: int,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        content_type: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[KnowledgeDocument], int]:
        """优化的文档列表查询"""
        
        cache_key = f"kb:{kb_id}:docs:{skip}:{limit}:{content_type or 'all'}:{search or 'all'}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 验证知识库权限
        KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, user_id)
        
        # 构建查询
        query = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.knowledge_base_id == kb_id,
            KnowledgeDocument.is_deleted == False
        )
        
        # 应用过滤条件
        if content_type:
            query = query.filter(KnowledgeDocument.content_type == content_type)
        
        if search:
            query = query.filter(
                or_(
                    KnowledgeDocument.title.contains(search),
                    KnowledgeDocument.content.contains(search)
                )
            )
        
        # 排序
        query = query.order_by(desc(KnowledgeDocument.created_at))
        
        # 获取总数和分页结果
        total = query.count()
        documents = query.offset(skip).limit(limit).all()
        
        result = (documents, total)
        cache_manager.set(cache_key, result, expire_time=300)
        return result
    
    @staticmethod
    def create_document_optimized(
        db: Session,
        kb_id: int,
        doc_data: dict,
        user_id: int
    ) -> KnowledgeDocument:
        """优化的文档创建"""
        
        # 验证知识库权限
        kb = KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, user_id)
        
        if kb.owner_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限在此知识库中创建文档"
            )
        
        # 创建文档
        doc = KnowledgeDocument(
            knowledge_base_id=kb_id,
            title=doc_data["title"],
            content=doc_data.get("content", ""),
            content_type=doc_data["content_type"],
            file_path=doc_data.get("file_path"),
            file_size=doc_data.get("file_size", 0),
            mime_type=doc_data.get("mime_type"),
            url=doc_data.get("url"),
            processing_status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(doc)
        db.flush()
        db.refresh(doc)
        
        # 更新知识库更新时间
        kb.updated_at = datetime.utcnow()
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:docs:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:stats"))
        
        return doc
    
    @staticmethod
    def update_document_optimized(
        db: Session,
        kb_id: int,
        doc_id: int,
        update_data: dict,
        user_id: int
    ) -> KnowledgeDocument:
        """优化的文档更新"""
        
        doc = KnowledgeDocumentService.get_document_optimized(db, kb_id, doc_id, user_id)
        
        # 权限检查
        if doc.knowledge_base.owner_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限修改此文档"
            )
        
        # 更新字段
        for field, value in update_data.items():
            if hasattr(doc, field) and value is not None:
                setattr(doc, field, value)
        
        doc.updated_at = datetime.utcnow()
        db.flush()
        db.refresh(doc)
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:doc:{doc_id}"))
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:docs:*"))
        
        return doc
    
    @staticmethod
    def delete_document_optimized(
        db: Session,
        kb_id: int,
        doc_id: int,
        user_id: int
    ) -> bool:
        """优化的文档删除"""
        
        doc = KnowledgeDocumentService.get_document_optimized(db, kb_id, doc_id, user_id)
        
        # 权限检查
        if doc.knowledge_base.owner_id != user_id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限删除此文档"
            )
        
        # 软删除文档
        doc.is_deleted = True
        doc.deleted_at = datetime.utcnow()
        db.flush()
        
        # 清除相关缓存
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:doc:{doc_id}"))
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:docs:*"))
        asyncio.create_task(cache_manager.delete_pattern(f"kb:{kb_id}:stats"))
        
        return True

class KnowledgeSearchService:
    """知识搜索服务"""
    
    @staticmethod
    def search_knowledge_optimized(
        db: Session,
        kb_id: int,
        query: str,
        user_id: int,
        content_types: Optional[List[str]] = None,
        limit: int = 20,
        use_ai: bool = True
    ) -> Dict[str, Any]:
        """优化的知识搜索"""
        
        cache_key = f"search:kb:{kb_id}:query:{hashlib.md5(query.encode()).hexdigest()}:{':'.join(content_types or [])}:{limit}:{use_ai}"
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            cached_result["from_cache"] = True
            return cached_result
        
        # 验证知识库权限
        KnowledgeBaseService.get_knowledge_base_optimized(db, kb_id, user_id)
        
        # 构建搜索查询
        search_query = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.knowledge_base_id == kb_id,
            KnowledgeDocument.is_deleted == False,
            or_(
                KnowledgeDocument.title.contains(query),
                KnowledgeDocument.content.contains(query)
            )
        )
        
        # 应用内容类型过滤
        if content_types:
            search_query = search_query.filter(
                KnowledgeDocument.content_type.in_(content_types)
            )
        
        # 执行搜索
        documents = search_query.order_by(desc(KnowledgeDocument.updated_at)).limit(limit).all()
        
        # 格式化搜索结果
        results = []
        for doc in documents:
            # 计算相关度分数（简单的关键词匹配）
            relevance_score = KnowledgeSearchService._calculate_relevance(doc, query)
            
            results.append({
                "id": doc.id,
                "title": doc.title,
                "content": doc.content[:200] + "..." if len(doc.content) > 200 else doc.content,
                "content_type": doc.content_type,
                "relevance_score": relevance_score,
                "created_at": doc.created_at.isoformat(),
                "url": doc.url
            })
        
        # 按相关度排序
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        search_result = {
            "query": query,
            "total_results": len(results),
            "results": results,
            "search_time": datetime.utcnow().isoformat(),
            "from_cache": False
        }
        
        # 缓存搜索结果
        cache_manager.set(cache_key, search_result, expire_time=600)  # 10分钟缓存
        return search_result
    
    @staticmethod
    def _calculate_relevance(doc: KnowledgeDocument, query: str) -> float:
        """计算文档与查询的相关度"""
        query_lower = query.lower()
        title_lower = doc.title.lower()
        content_lower = doc.content.lower()
        
        score = 0.0
        
        # 标题匹配权重更高
        if query_lower in title_lower:
            score += 2.0
        
        # 内容匹配
        if query_lower in content_lower:
            score += 1.0
        
        # 词频分析
        query_words = query_lower.split()
        for word in query_words:
            score += title_lower.count(word) * 0.5
            score += content_lower.count(word) * 0.1
        
        return score

class KnowledgeUtils:
    """知识库工具类"""
    
    @staticmethod
    def validate_knowledge_base_data(data: dict) -> dict:
        """验证知识库数据"""
        errors = []
        
        if not data.get("name") or len(data["name"].strip()) < 2:
            errors.append("知识库名称至少需要2个字符")
        
        if data.get("name") and len(data["name"]) > 100:
            errors.append("知识库名称不能超过100个字符")
        
        if data.get("description") and len(data["description"]) > 500:
            errors.append("知识库描述不能超过500个字符")
        
        if errors:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"errors": errors}
            )
        
        return data
    
    @staticmethod
    def validate_document_data(data: dict) -> dict:
        """验证文档数据"""
        errors = []
        
        if not data.get("title") or len(data["title"].strip()) < 2:
            errors.append("文档标题至少需要2个字符")
        
        if data.get("title") and len(data["title"]) > 200:
            errors.append("文档标题不能超过200个字符")
        
        valid_content_types = ["document", "image", "video", "url", "website"]
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
    def format_knowledge_base_response(kb: KnowledgeBase) -> dict:
        """格式化知识库响应"""
        return {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "is_public": kb.is_public,
            "owner": {
                "id": kb.owner.id,
                "username": kb.owner.username
            } if kb.owner else None,
            "document_count": len(kb.documents) if kb.documents else 0,
            "created_at": kb.created_at,
            "updated_at": kb.updated_at
        }
    
    @staticmethod
    def format_document_response(doc: KnowledgeDocument) -> dict:
        """格式化文档响应"""
        return {
            "id": doc.id,
            "title": doc.title,
            "content_type": doc.content_type,
            "processing_status": doc.processing_status,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "url": doc.url,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at
        }
    
    @staticmethod
    def get_content_type_from_file(filename: str) -> str:
        """根据文件名判断内容类型"""
        file_ext = os.path.splitext(filename)[1].lower()
        
        document_exts = ['.pdf', '.doc', '.docx', '.txt', '.md', '.rtf']
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']
        video_exts = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm']
        
        if file_ext in document_exts:
            return "document"
        elif file_ext in image_exts:
            return "image"
        elif file_ext in video_exts:
            return "video"
        else:
            return "document"  # 默认为文档类型
    
    @staticmethod
    def generate_file_hash(file_content: bytes) -> str:
        """生成文件内容哈希"""
        return hashlib.md5(file_content).hexdigest()
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """验证URL格式"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
