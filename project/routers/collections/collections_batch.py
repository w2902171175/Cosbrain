# project/routers/collections/collections_batch.py
"""
优化的批量操作模块
- 真正的批量数据库操作
- 减少数据库往返次数
- 智能缓存机制
"""

import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.sql import func, text
from sqlalchemy import and_, or_, select, insert, update, delete
from datetime import datetime, timezone, timedelta
import json

from project.models import Folder, CollectedContent, Project, Course

logger = logging.getLogger(__name__)


class OptimizedBatchOperations:
    """优化的批量操作类"""
    
    def __init__(self, db: Session, max_cache_size: int = 1000):
        self.db = db
        self._cache = {}
        self._cache_access_order = []  # 记录访问顺序，实现LRU
        self._cache_ttl = timedelta(minutes=5)  # 缓存5分钟
        self._max_cache_size = max_cache_size
    
    def _get_cache_key(self, operation: str, **kwargs) -> str:
        """生成缓存键"""
        key_parts = [operation]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        return "|".join(key_parts)
    
    def _evict_lru_cache(self) -> None:
        """LRU缓存淘汰机制"""
        while len(self._cache) >= self._max_cache_size and self._cache_access_order:
            oldest_key = self._cache_access_order.pop(0)
            if oldest_key in self._cache:
                del self._cache[oldest_key]
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据 - 改进的LRU实现"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._cache_ttl:
                # 更新访问顺序
                if key in self._cache_access_order:
                    self._cache_access_order.remove(key)
                self._cache_access_order.append(key)
                return data
            else:
                # 清理过期缓存
                del self._cache[key]
                if key in self._cache_access_order:
                    self._cache_access_order.remove(key)
        return None
    
    def _set_cache(self, key: str, data: Any) -> None:
        """设置缓存 - 改进的LRU实现"""
        # 先淘汰过期和超量的缓存
        self._evict_lru_cache()
        
        # 设置新缓存
        self._cache[key] = (data, datetime.now())
        if key in self._cache_access_order:
            self._cache_access_order.remove(key)
        self._cache_access_order.append(key)
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._cache_access_order.clear()
    
    def bulk_get_folders_stats(self, folder_ids: List[int], user_id: int) -> Dict[int, Dict[str, Any]]:
        """
        批量获取文件夹统计信息 - 优化版本
        使用单个复杂查询替代多个简单查询
        """
        if not folder_ids:
            return {}
        
        cache_key = self._get_cache_key("folders_stats", folder_ids=tuple(sorted(folder_ids)), user_id=user_id)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        # 使用更高效的SQL查询
        query = text("""
            WITH folder_content_stats AS (
                SELECT 
                    cc.folder_id,
                    COUNT(cc.id) as content_count,
                    SUM(COALESCE(cc.file_size, 0)) as total_size,
                    MAX(cc.updated_at) as last_accessed
                FROM collected_contents cc
                WHERE cc.folder_id = ANY(:folder_ids)
                    AND cc.owner_id = :user_id
                    AND cc.status != 'deleted'
                GROUP BY cc.folder_id
            ),
            folder_subfolder_stats AS (
                SELECT 
                    f.parent_id,
                    COUNT(f.id) as subfolder_count
                FROM folders f
                WHERE f.parent_id = ANY(:folder_ids)
                    AND f.owner_id = :user_id
                GROUP BY f.parent_id
            )
            SELECT 
                f.id as folder_id,
                COALESCE(fcs.content_count, 0) as content_count,
                COALESCE(fcs.total_size, 0) as total_size,
                fcs.last_accessed,
                COALESCE(fss.subfolder_count, 0) as subfolder_count,
                (COALESCE(fcs.content_count, 0) + COALESCE(fss.subfolder_count, 0)) as total_count
            FROM (SELECT unnest(:folder_ids) as id) f
            LEFT JOIN folder_content_stats fcs ON f.id = fcs.folder_id
            LEFT JOIN folder_subfolder_stats fss ON f.id = fss.parent_id
        """)
        
        result = self.db.execute(query, {
            'folder_ids': folder_ids,
            'user_id': user_id
        }).fetchall()
        
        stats_dict = {}
        for row in result:
            stats_dict[row.folder_id] = {
                'content_count': row.content_count,
                'subfolder_count': row.subfolder_count,
                'total_size': row.total_size,
                'last_accessed': row.last_accessed,
                'total_count': row.total_count
            }
        
        self._set_cache(cache_key, stats_dict)
        return stats_dict
    
    def bulk_calculate_folder_depths_and_paths(self, folder_ids: List[int], user_id: int) -> Dict[int, Dict[str, Any]]:
        """
        批量计算文件夹深度和路径信息
        
        Args:
            folder_ids: 文件夹ID列表
            user_id: 用户ID
            
        Returns:
            Dict[int, Dict[str, Any]]: {folder_id: {"depth": 2, "path": [...]}}
        """
        if not folder_ids:
            return {}
        
        cache_key = self._get_cache_key("folder_depths_paths", folder_ids=tuple(sorted(folder_ids)), user_id=user_id)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        # 使用 CTE 递归查询计算所有文件夹的深度和路径
        query = text("""
            WITH RECURSIVE folder_hierarchy AS (
                -- 为每个目标文件夹找到根路径
                SELECT 
                    f.id as target_id,
                    f.id as current_id,
                    f.name as current_name,
                    f.parent_id,
                    f.color,
                    f.icon,
                    0 as depth,
                    ARRAY[f.id] as path_ids,
                    ARRAY[f.name] as path_names,
                    ARRAY[f.color] as path_colors,
                    ARRAY[f.icon] as path_icons
                FROM folders f
                WHERE f.id = ANY(:folder_ids) AND f.owner_id = :user_id
                
                UNION ALL
                
                -- 向上递归找父文件夹
                SELECT 
                    fh.target_id,
                    f.id as current_id,
                    f.name as current_name,
                    f.parent_id,
                    f.color,
                    f.icon,
                    fh.depth + 1,
                    f.id || fh.path_ids,
                    f.name || fh.path_names,
                    f.color || fh.path_colors,
                    f.icon || fh.path_icons
                FROM folders f
                INNER JOIN folder_hierarchy fh ON f.id = fh.parent_id
                WHERE f.owner_id = :user_id
            )
            SELECT 
                target_id,
                MAX(depth) as max_depth,
                (array_agg(path_ids ORDER BY depth DESC))[1] as final_path_ids,
                (array_agg(path_names ORDER BY depth DESC))[1] as final_path_names,
                (array_agg(path_colors ORDER BY depth DESC))[1] as final_path_colors,
                (array_agg(path_icons ORDER BY depth DESC))[1] as final_path_icons
            FROM folder_hierarchy
            GROUP BY target_id
        """)
        
        result = self.db.execute(query, {
            'folder_ids': folder_ids,
            'user_id': user_id
        }).fetchall()
        
        depths_and_paths = {}
        for row in result:
            # 构建路径信息
            path_info = []
            if row.final_path_ids:
                for i, folder_id in enumerate(row.final_path_ids):
                    path_info.append({
                        "id": folder_id,
                        "name": row.final_path_names[i] if i < len(row.final_path_names) else "Unknown",
                        "color": row.final_path_colors[i] if i < len(row.final_path_colors) else None,
                        "icon": row.final_path_icons[i] if i < len(row.final_path_icons) else None
                    })
            
            depths_and_paths[row.target_id] = {
                'depth': row.max_depth,
                'path': path_info
            }
        
        # 为没有查询到的文件夹设置默认值
        for folder_id in folder_ids:
            if folder_id not in depths_and_paths:
                depths_and_paths[folder_id] = {
                    'depth': 0,
                    'path': []
                }
        
        self._set_cache(cache_key, depths_and_paths)
        return depths_and_paths
    
    def bulk_create_collections(self, collections_data: List[Dict[str, Any]], user_id: int) -> List[int]:
        """
        批量创建收藏记录
        
        Args:
            collections_data: [
                {
                    "folder_id": 1,
                    "type": "project",
                    "title": "项目标题",
                    "shared_item_type": "project",
                    "shared_item_id": 123,
                    "url": "optional_url",
                    "content": "optional_content"
                }
            ]
        
        Returns:
            List[int]: 创建的收藏记录ID列表
        """
        if not collections_data:
            return []
        
        try:
            # 准备批量插入数据
            insert_data = []
            for data in collections_data:
                insert_data.append({
                    'owner_id': user_id,
                    'folder_id': data['folder_id'],
                    'type': data['type'],
                    'title': data['title'],
                    'url': data.get('url'),
                    'content': data.get('content'),
                    'shared_item_type': data['shared_item_type'],
                    'shared_item_id': data['shared_item_id'],
                    'status': 'active',
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc),
                    'embedding': None  # 可以后续异步生成
                })
            
            # 批量插入
            stmt = insert(CollectedContent).values(insert_data)
            result = self.db.execute(stmt)
            self.db.commit()
            
            # 获取插入的ID（这里需要根据数据库类型调整）
            # PostgreSQL 可以使用 RETURNING
            return list(range(result.lastrowid - len(insert_data) + 1, result.lastrowid + 1))
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量创建收藏记录失败: {str(e)}")
            raise
    
    def bulk_update_folder_stats(self, folder_ids: List[int]) -> None:
        """
        批量更新文件夹统计信息
        适用于文件夹内容变化后的统计更新
        """
        if not folder_ids:
            return
        
        try:
            # 使用单个SQL语句更新所有文件夹的统计信息
            update_query = text("""
                UPDATE folders 
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY(:folder_ids)
            """)
            
            self.db.execute(update_query, {'folder_ids': folder_ids})
            self.db.commit()
            
            # 清空相关缓存
            for folder_id in folder_ids:
                cache_keys_to_remove = [k for k in self._cache.keys() if f"folder_id:{folder_id}" in k]
                for key in cache_keys_to_remove:
                    self._cache.pop(key, None)
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量更新文件夹统计失败: {str(e)}")
            raise
    
    def bulk_delete_collections(self, collection_ids: List[int], user_id: int, hard_delete: bool = False) -> int:
        """
        批量删除收藏记录
        
        Args:
            collection_ids: 收藏记录ID列表
            user_id: 用户ID（用于权限验证）
            hard_delete: 是否硬删除，False为软删除
        
        Returns:
            int: 实际删除的记录数
        """
        if not collection_ids:
            return 0
        
        try:
            if hard_delete:
                # 硬删除
                stmt = delete(CollectedContent).where(
                    and_(
                        CollectedContent.id.in_(collection_ids),
                        CollectedContent.owner_id == user_id
                    )
                )
            else:
                # 软删除
                stmt = update(CollectedContent).where(
                    and_(
                        CollectedContent.id.in_(collection_ids),
                        CollectedContent.owner_id == user_id
                    )
                ).values(
                    status='deleted',
                    updated_at=datetime.now(timezone.utc)
                )
            
            result = self.db.execute(stmt)
            self.db.commit()
            
            deleted_count = result.rowcount
            logger.info(f"批量{'硬' if hard_delete else '软'}删除了 {deleted_count} 条收藏记录")
            
            # 清空相关缓存
            self.clear_cache()
            
            return deleted_count
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量删除收藏记录失败: {str(e)}")
            raise
    
    def bulk_move_collections(self, collection_ids: List[int], target_folder_id: int, user_id: int) -> int:
        """
        批量移动收藏记录到指定文件夹
        
        Args:
            collection_ids: 收藏记录ID列表
            target_folder_id: 目标文件夹ID
            user_id: 用户ID（用于权限验证）
        
        Returns:
            int: 实际移动的记录数
        """
        if not collection_ids:
            return 0
        
        try:
            # 验证目标文件夹权限
            target_folder = self.db.query(Folder).filter(
                Folder.id == target_folder_id,
                Folder.owner_id == user_id
            ).first()
            
            if not target_folder:
                raise ValueError(f"目标文件夹不存在或无权访问: {target_folder_id}")
            
            # 批量更新
            stmt = update(CollectedContent).where(
                and_(
                    CollectedContent.id.in_(collection_ids),
                    CollectedContent.owner_id == user_id
                )
            ).values(
                folder_id=target_folder_id,
                updated_at=datetime.now(timezone.utc)
            )
            
            result = self.db.execute(stmt)
            self.db.commit()
            
            moved_count = result.rowcount
            logger.info(f"批量移动了 {moved_count} 条收藏记录到文件夹 {target_folder_id}")
            
            # 清空相关缓存
            self.clear_cache()
            
            return moved_count
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量移动收藏记录失败: {str(e)}")
            raise
    
    def bulk_check_duplicates(self, items_to_check: List[Dict[str, Any]], user_id: int) -> Dict[str, bool]:
        """
        批量检查重复收藏
        
        Args:
            items_to_check: [
                {"type": "project", "id": 1},
                {"type": "course", "id": 2}
            ]
        
        Returns:
            Dict[str, bool]: {"project_1": True, "course_2": False}
        """
        if not items_to_check:
            return {}
        
        # 构建查询条件
        conditions = []
        for item in items_to_check:
            conditions.append(
                and_(
                    CollectedContent.shared_item_type == item["type"],
                    CollectedContent.shared_item_id == item["id"]
                )
            )
        
        if not conditions:
            return {}
        
        # 批量查询
        existing_items = self.db.query(
            CollectedContent.shared_item_type,
            CollectedContent.shared_item_id
        ).filter(
            CollectedContent.owner_id == user_id,
            CollectedContent.status != 'deleted',
            or_(*conditions)
        ).all()
        
        # 构建结果字典
        existing_set = {f"{item.shared_item_type}_{item.shared_item_id}" for item in existing_items}
        
        result = {}
        for item in items_to_check:
            key = f"{item['type']}_{item['id']}"
            result[key] = key in existing_set
        
        return result
    
    def get_user_collection_summary(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户收藏概览统计
        """
        cache_key = self._get_cache_key("user_summary", user_id=user_id)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        # 使用复杂查询一次性获取所有统计信息
        query = text("""
            SELECT 
                COUNT(*) as total_collections,
                COUNT(CASE WHEN shared_item_type = 'project' THEN 1 END) as project_collections,
                COUNT(CASE WHEN shared_item_type = 'course' THEN 1 END) as course_collections,
                COUNT(CASE WHEN shared_item_type = 'chat_message' THEN 1 END) as chat_collections,
                COUNT(CASE WHEN shared_item_type IN ('forum_topic', 'forum_comment') THEN 1 END) as forum_collections,
                SUM(COALESCE(file_size, 0)) as total_storage,
                COUNT(DISTINCT folder_id) as folder_count,
                MAX(updated_at) as last_collection_time
            FROM collected_contents
            WHERE owner_id = :user_id AND status != 'deleted'
        """)
        
        result = self.db.execute(query, {'user_id': user_id}).fetchone()
        
        summary = {
            'total_collections': result.total_collections,
            'collections_by_type': {
                'project': result.project_collections,
                'course': result.course_collections,
                'chat': result.chat_collections,
                'forum': result.forum_collections
            },
            'total_storage_bytes': result.total_storage,
            'folder_count': result.folder_count,
            'last_collection_time': result.last_collection_time
        }
        
        self._set_cache(cache_key, summary)
        return summary


class BatchOperationHandler:
    """批量操作处理器 - 向后兼容的接口"""
    
    def __init__(self, db: Session):
        self.operations = OptimizedBatchOperations(db)
    
    def handle_batch_operation(self, operation_type: str, **kwargs) -> Any:
        """处理批量操作的统一入口"""
        operation_map = {
            'get_folders_stats': self.operations.bulk_get_folders_stats,
            'create_collections': self.operations.bulk_create_collections,
            'delete_collections': self.operations.bulk_delete_collections,
            'move_collections': self.operations.bulk_move_collections,
            'check_duplicates': self.operations.bulk_check_duplicates,
            'get_summary': self.operations.get_user_collection_summary
        }
        
        if operation_type not in operation_map:
            raise ValueError(f"不支持的批量操作类型: {operation_type}")
        
        return operation_map[operation_type](**kwargs)


# 移除了废弃的全局变量和向后兼容代码
# 如需使用批量操作，请直接实例化 OptimizedBatchOperations 类
