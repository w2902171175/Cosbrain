# project/services/quick_notes_service.py
"""
随手记录服务层 - 统一随手记录管理业务逻辑
应用成熟的优化模式到quick_notes模块
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple, Union

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func, asc, between
import logging

from project.models import DailyRecord, User
from project.utils.optimization.production_utils import cache_manager
from project.utils import generate_embedding_safe, get_user_resource_or_404

logger = logging.getLogger(__name__)

class QuickNotesService:
    """随手记录核心业务逻辑服务"""
    
    @staticmethod
    def create_record_optimized(
        db: Session, user_id: int, record_data: Dict[str, Any], 
        combined_text: str, embedding: List[float]
    ) -> DailyRecord:
        """优化的记录创建"""
        db_record = DailyRecord(
            owner_id=user_id,
            content=record_data.get("content", ""),
            mood=record_data.get("mood"),
            tags=record_data.get("tags"),
            combined_text=combined_text,
            embedding=embedding
        )
        
        db.add(db_record)
        db.flush()  # 获取ID但不提交
        
        # 缓存新记录
        cache_key = f"daily_record:{db_record.id}"
        cache_manager.set(cache_key, db_record, expire=3600)
        
        return db_record
    
    @staticmethod
    def get_record_optimized(db: Session, record_id: int, user_id: int) -> DailyRecord:
        """优化的记录查询 - 使用缓存和权限检查"""
        cache_key = f"daily_record:{record_id}"
        
        # 尝试从缓存获取
        cached_record = cache_manager.get(cache_key)
        if cached_record and cached_record.owner_id == user_id:
            return cached_record
        
        # 从数据库查询
        record = get_user_resource_or_404(
            db, DailyRecord, record_id, user_id, 
            "owner_id", "Daily record not found or not authorized"
        )
        
        # 缓存结果
        cache_manager.set(cache_key, record, expire=3600)
        return record
    
    @staticmethod
    def get_user_records_optimized(
        db: Session, user_id: int, 
        page: int = 1, page_size: int = 20,
        mood: Optional[str] = None, tag: Optional[str] = None,
        sort_by: str = "created_at", sort_order: str = "desc"
    ) -> Tuple[List[DailyRecord], int]:
        """优化的用户记录列表查询 - 支持分页、过滤和排序"""
        
        # 构建基础查询
        query = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id)
        
        # 应用过滤条件
        if mood:
            query = query.filter(DailyRecord.mood == mood)
        if tag:
            query = query.filter(DailyRecord.tags.ilike(f"%{tag}%"))
        
        # 获取总数
        total_count = query.count()
        
        # 应用排序
        order_field = getattr(DailyRecord, sort_by, DailyRecord.created_at)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(order_field))
        else:
            query = query.order_by(asc(order_field))
        
        # 应用分页
        offset = (page - 1) * page_size
        records = query.offset(offset).limit(page_size).all()
        
        return records, total_count
    
    @staticmethod
    def save_record_optimized(db: Session, record: DailyRecord):
        """优化的记录保存"""
        db.add(record)
        
        # 更新缓存
        cache_key = f"daily_record:{record.id}"
        cache_manager.set(cache_key, record, expire=3600)
    
    @staticmethod
    def delete_record_optimized(db: Session, record_id: int, user_id: int):
        """优化的记录删除"""
        record = QuickNotesService.get_record_optimized(db, record_id, user_id)
        
        db.delete(record)
        
        # 清除缓存
        cache_key = f"daily_record:{record_id}"
        cache_manager.delete(cache_key)
    
    @staticmethod
    def get_analytics_summary_optimized(
        db: Session, user_id: int, days: int = 30
    ) -> Dict[str, Any]:
        """优化的分析摘要生成"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 获取时间范围内的记录
        records = db.query(DailyRecord).filter(
            and_(
                DailyRecord.owner_id == user_id,
                DailyRecord.created_at >= start_date,
                DailyRecord.created_at <= end_date
            )
        ).all()
        
        # 统计分析
        total_records = len(records)
        mood_stats = {}
        tag_stats = {}
        
        for record in records:
            # 心情统计
            if record.mood:
                mood_stats[record.mood] = mood_stats.get(record.mood, 0) + 1
            
            # 标签统计
            if record.tags:
                tags = [tag.strip() for tag in record.tags.split(",")]
                for tag in tags:
                    if tag:
                        tag_stats[tag] = tag_stats.get(tag, 0) + 1
        
        # 按天统计记录数量
        daily_counts = {}
        for record in records:
            date_key = record.created_at.date().isoformat()
            daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
        
        return {
            "total_records": total_records,
            "days_analyzed": days,
            "avg_records_per_day": round(total_records / days, 2),
            "mood_distribution": mood_stats,
            "tag_distribution": tag_stats,
            "daily_counts": daily_counts,
            "most_frequent_mood": max(mood_stats.items(), key=lambda x: x[1])[0] if mood_stats else None,
            "most_frequent_tag": max(tag_stats.items(), key=lambda x: x[1])[0] if tag_stats else None
        }
    
    @staticmethod
    async def search_records_optimized(
        db: Session, user_id: int, query: str, limit: int = 10
    ) -> List[Tuple[DailyRecord, float]]:
        """优化的记录搜索 - 支持语义搜索"""
        
        # 生成查询的嵌入向量
        query_embedding = await generate_embedding_safe(query, user_id=user_id)
        
        # 获取用户的所有记录
        records = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id).all()
        
        # 计算相似度并排序
        scored_records = []
        for record in records:
            if record.embedding:
                # 计算余弦相似度
                similarity = QuickNotesUtils.calculate_cosine_similarity(
                    query_embedding, record.embedding
                )
                scored_records.append((record, similarity))
        
        # 按相似度排序并限制结果数量
        scored_records.sort(key=lambda x: x[1], reverse=True)
        return scored_records[:limit]
    
    @staticmethod
    def export_records_optimized(
        db: Session, user_id: int, format: str = "json",
        date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """优化的记录导出"""
        query = db.query(DailyRecord).filter(DailyRecord.owner_id == user_id)
        
        # 应用日期过滤
        if date_from:
            start_date = datetime.fromisoformat(date_from)
            query = query.filter(DailyRecord.created_at >= start_date)
        
        if date_to:
            end_date = datetime.fromisoformat(date_to)
            query = query.filter(DailyRecord.created_at <= end_date)
        
        records = query.order_by(DailyRecord.created_at.asc()).all()
        
        # 根据格式处理数据
        if format.lower() == "json":
            return {
                "format": "json",
                "export_date": datetime.now().isoformat(),
                "total_records": len(records),
                "records": [QuickNotesUtils.format_record_for_export(record) for record in records]
            }
        elif format.lower() == "csv":
            # CSV格式导出逻辑
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Content", "Mood", "Tags", "Created At"])
            
            for record in records:
                writer.writerow([
                    record.id, record.content, record.mood or "", 
                    record.tags or "", record.created_at.isoformat()
                ])
            
            return {
                "format": "csv",
                "content": output.getvalue(),
                "total_records": len(records)
            }
        else:
            # 默认文本格式
            text_content = []
            for record in records:
                text_content.append(
                    f"[{record.created_at.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"{record.content}\n"
                    f"心情: {record.mood or '无'} | 标签: {record.tags or '无'}\n"
                    f"{'='*50}\n"
                )
            
            return {
                "format": "text",
                "content": "\n".join(text_content),
                "total_records": len(records)
            }

class QuickNotesUtils:
    """随手记录工具类"""
    
    @staticmethod
    def validate_record_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证记录数据"""
        validated_data = {}
        
        # 验证内容
        content = data.get("content", "").strip()
        if not content:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="记录内容不能为空"
            )
        validated_data["content"] = content
        
        # 验证心情
        mood = data.get("mood", "").strip() if data.get("mood") else None
        if mood:
            validated_data["mood"] = mood
        
        # 验证标签
        tags = data.get("tags", "").strip() if data.get("tags") else None
        if tags:
            # 清理和格式化标签
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
            validated_data["tags"] = ", ".join(tag_list)
        
        return validated_data
    
    @staticmethod
    def build_combined_text(content: str, mood: str, tags: str) -> str:
        """构建组合文本"""
        parts = []
        
        if content:
            parts.append(content)
        if mood:
            parts.append(f"心情: {mood}")
        if tags:
            parts.append(f"标签: {tags}")
        
        return ". ".join(parts)
    
    @staticmethod
    def format_record_response(record: DailyRecord) -> Dict[str, Any]:
        """格式化记录响应"""
        return {
            "id": record.id,
            "content": record.content,
            "mood": record.mood,
            "tags": record.tags,
            "combined_text": record.combined_text,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "owner_id": record.owner_id
        }
    
    @staticmethod
    def format_record_for_export(record: DailyRecord) -> Dict[str, Any]:
        """格式化记录用于导出"""
        return {
            "id": record.id,
            "content": record.content,
            "mood": record.mood,
            "tags": record.tags,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat() if record.updated_at else None
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

class QuickNotesEmbeddingService:
    """随手记录嵌入向量服务"""
    
    @staticmethod
    async def generate_embedding_optimized(text: str, user_id: int) -> List[float]:
        """优化的嵌入向量生成"""
        # 使用缓存避免重复计算
        cache_key = f"embedding:quicknote:{hash(text)}"
        cached_embedding = cache_manager.get(cache_key)
        
        if cached_embedding:
            return cached_embedding
        
        # 生成新的嵌入向量
        embedding = await generate_embedding_safe(text, user_id=user_id)
        
        # 缓存结果
        cache_manager.set(cache_key, embedding, expire=86400)  # 24小时
        
        return embedding
