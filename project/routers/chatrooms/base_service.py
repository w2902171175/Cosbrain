# project/routers/chatrooms/base_service.py
"""
聊天室基础服务类 - 消除重复代码
"""
import logging
from functools import wraps
from typing import Callable, Any, Dict, Optional
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from project.utils.security.permissions import check_room_access
from project.utils.async_cache.cache import cache
from project.utils import _award_points

logger = logging.getLogger(__name__)

class ChatRoomBaseService:
    """聊天室基础服务类，提供通用功能"""
    
# project/routers/chatrooms/base_service.py
"""
聊天室基础服务类 - 消除重复代码
"""
import logging
from functools import wraps
from typing import Callable, Any, Dict, Optional
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from project.utils.security.permissions import check_room_access
from project.utils.async_cache.cache import cache
from project.utils import _award_points
from .performance_monitor import monitor_performance
from .config import CACHE_CONFIG, POINTS_CONFIG

logger = logging.getLogger(__name__)

class ChatRoomBaseService:
    """聊天室基础服务类，提供通用功能"""
    
    @staticmethod
    def handle_chatroom_operation(
        require_room_access: bool = True,
        award_points: Optional[int] = None,
        points_reason: Optional[str] = None,
        invalidate_cache: bool = True,
        monitor_name: Optional[str] = None
    ):
        """
        聊天室操作装饰器，统一处理：
        - 权限检查
        - 错误处理
        - 缓存管理
        - 积分奖励
        - 日志记录
        - 性能监控
        """
        def decorator(func: Callable) -> Callable:
            # 添加性能监控
            if monitor_name:
                func = monitor_performance(monitor_name)(func)
            else:
                func = monitor_performance(func.__name__)(func)
            
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 提取通用参数
                room_id = kwargs.get('room_id') or (args[0] if args else None)
                current_user_id = kwargs.get('current_user_id')
                db = kwargs.get('db')
                
                try:
                    # 权限检查
                    if require_room_access and room_id and current_user_id and db:
                        room, member = check_room_access(db, room_id, current_user_id)
                        kwargs['room'] = room
                        kwargs['member'] = member
                    
                    # 执行原函数
                    result = await func(*args, **kwargs)
                    
                    # 奖励积分
                    if award_points and current_user_id and db:
                        await _award_points(db, current_user_id, award_points, points_reason or "聊天室操作")
                    
                    # 智能缓存管理
                    if invalidate_cache and room_id:
                        from .performance_monitor import CacheOptimizer
                        await CacheOptimizer.invalidate_related_caches(room_id, current_user_id)
                    
                    # 记录操作日志
                    operation_name = func.__name__
                    logger.info(f"用户 {current_user_id} 在聊天室 {room_id} 执行了 {operation_name} 操作")
                    
                    return result
                    
                except HTTPException:
                    raise
                except Exception as e:
                    operation_name = func.__name__
                    logger.error(f"{operation_name} 操作失败: {e}")
                    if db:
                        db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"{operation_name} 操作失败"
                    )
            
            return wrapper
        return decorator
    
    @staticmethod
    async def create_message_with_cache(
        db: Session,
        room_id: int,
        sender_id: int,
        content: str,
        message_type: str = "text",
        media_url: Optional[str] = None,
        reply_to_id: Optional[int] = None,
        file_info: Optional[Dict] = None
    ):
        """统一的消息创建和缓存更新"""
        from project.services.message_service import MessageService
        
        # 创建消息
        db_message = await MessageService.create_message_async(
            db=db,
            room_id=room_id,
            sender_id=sender_id,
            content=content,
            message_type=message_type,
            media_url=media_url,
            reply_to_id=reply_to_id,
            file_info=file_info
        )
        
        # 添加到缓存
        await cache.add_recent_message(room_id, db_message.__dict__)
        
        return db_message
    
    @staticmethod
    async def handle_pagination(
        query_func: Callable,
        page: int = 1,
        size: int = 50,
        **kwargs
    ) -> Dict[str, Any]:
        """统一的分页处理"""
        # 计算偏移量
        offset = (page - 1) * size
        
        # 执行查询
        items, total = await query_func(
            offset=offset,
            limit=size,
            **kwargs
        )
        
        # 计算总页数
        total_pages = (total + size - 1) // size
        
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "size": size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
    
    @staticmethod
    def validate_file_limits(files, max_count: int, file_type: str):
        """统一的文件数量验证"""
        if len(files) > max_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"一次最多只能上传{max_count}个{file_type}文件"
            )
    
    @staticmethod
    async def batch_process_uploads(
        files,
        user_id: int,
        file_type: str,
        room_id: int,
        db: Session,
        reply_to_id: Optional[int] = None
    ):
        """统一的批量文件上传处理"""
        from project.services.file_service import FileUploadService
        
        # 批量上传文件
        upload_results = await FileUploadService.batch_upload_files(
            files=files,
            user_id=user_id,
            file_type=file_type
        )
        
        # 处理上传结果
        messages = []
        successful_uploads = []
        failed_uploads = []
        
        for i, (file, result) in enumerate(zip(files, upload_results)):
            if "error" not in result:
                successful_uploads.append(result)
                
                # 创建消息记录
                message_type = "gallery" if file_type == "image" and len(successful_uploads) > 1 else file_type
                content_prefix = {"image": "[图片]", "audio": "[音频]", "document": "[文档]", "video": "[视频]"}.get(file_type, "[文件]")
                
                db_message = await ChatRoomBaseService.create_message_with_cache(
                    db=db,
                    room_id=room_id,
                    sender_id=user_id,
                    content=f"{content_prefix} {result['original_filename']}",
                    message_type=message_type,
                    media_url=result["media_url"],
                    reply_to_id=reply_to_id if i == 0 else None,  # 只有第一个文件关联回复
                    file_info=result
                )
                
                messages.append(db_message)
            else:
                failed_uploads.append(result)
        
        if not successful_uploads:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="所有文件上传失败"
            )
        
        return {
            "messages": messages,
            "successful_count": len(successful_uploads),
            "failed_count": len(failed_uploads),
            "failed_files": [result.get("filename") for result in failed_uploads]
        }
