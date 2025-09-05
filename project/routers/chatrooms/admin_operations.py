# project/routers/chatrooms/admin_operations.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from project.database import get_db
from project.utils import get_current_user_id
from project.models import ChatRoom, ChatRoomMember, ChatMessage, User
import project.schemas as schemas
from project.services.chatroom_service import ChatRoomService
from project.services.file_service import FileUploadService
from project.utils.security.permissions import check_admin_role
from project.utils.async_cache.cache import cache

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/admin/optimize-storage", summary="优化存储（管理员）")
async def optimize_storage(
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="清理多少天前的文件")
):
    """优化存储空间（管理员功能）"""
    try:
        # 检查管理员权限
        check_admin_role(db, current_user_id)
        
        # 添加后台任务清理过期文件
        background_tasks.add_task(FileUploadService.cleanup_expired_files, db, days)
        
        logger.info(f"管理员 {current_user_id} 启动了存储优化任务")
        
        return {
            "message": f"存储优化任务已启动，将清理 {days} 天前的过期文件",
            "started_at": datetime.now().isoformat(),
            "cleanup_days": days
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动存储优化失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="启动存储优化失败"
        )

@router.post("/admin/cleanup-connections", summary="清理过期WebSocket连接（管理员）")
async def cleanup_connections(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """清理过期的WebSocket连接"""
    try:
        # 检查管理员权限
        check_admin_role(db, current_user_id)
        
        # 获取连接管理器并清理过期连接
        from project.routers.chatrooms.websocket_handler import manager
        await manager.cleanup_expired_connections()
        
        # 获取清理后的统计信息
        stats = manager.get_connection_stats()
        
        logger.info(f"管理员 {current_user_id} 清理了过期的WebSocket连接")
        
        return {
            "message": "过期连接清理完成",
            "connection_stats": stats,
            "cleaned_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清理连接失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="清理连接失败"
        )

@router.get("/admin/system-health", summary="系统健康检查（管理员）")
async def system_health_check(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """系统健康检查"""
    try:
        # 检查管理员权限
        check_admin_role(db, current_user_id)
        
        # 数据库健康检查
        db_health = await check_database_health(db)
        
        # 缓存健康检查
        cache_health = await check_cache_health()
        
        # WebSocket连接状态
        from project.routers.chatrooms.websocket_handler import manager
        connection_stats = manager.get_connection_stats()
        
        # 系统统计
        system_stats = await get_system_statistics(db)
        
        health_status = {
            "overall_status": "healthy" if db_health["status"] == "ok" and cache_health["status"] == "ok" else "degraded",
            "timestamp": datetime.now().isoformat(),
            "database": db_health,
            "cache": cache_health,
            "websocket_connections": connection_stats,
            "system_statistics": system_stats
        }
        
        return health_status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"系统健康检查失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="系统健康检查失败"
        )

@router.post("/admin/security-scan", summary="安全扫描（管理员）")
async def security_scan(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    scan_type: str = Query("basic", description="扫描类型 (basic/full)")
):
    """执行安全扫描"""
    try:
        # 检查管理员权限
        check_admin_role(db, current_user_id)
        
        scan_results = {
            "scan_type": scan_type,
            "started_at": datetime.now().isoformat(),
            "issues": []
        }
        
        # 基础安全检查
        basic_issues = await perform_basic_security_scan(db)
        scan_results["issues"].extend(basic_issues)
        
        # 完整安全检查
        if scan_type == "full":
            full_issues = await perform_full_security_scan(db)
            scan_results["issues"].extend(full_issues)
        
        scan_results["completed_at"] = datetime.now().isoformat()
        scan_results["total_issues"] = len(scan_results["issues"])
        scan_results["severity_summary"] = {
            "critical": len([i for i in scan_results["issues"] if i["severity"] == "critical"]),
            "high": len([i for i in scan_results["issues"] if i["severity"] == "high"]),
            "medium": len([i for i in scan_results["issues"] if i["severity"] == "medium"]),
            "low": len([i for i in scan_results["issues"] if i["severity"] == "low"])
        }
        
        logger.info(f"管理员 {current_user_id} 执行了安全扫描，发现 {scan_results['total_issues']} 个问题")
        
        return scan_results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"安全扫描失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="安全扫描失败"
        )

@router.post("/admin/batch-cleanup", summary="批量清理操作（管理员）")
async def batch_cleanup(
    background_tasks: BackgroundTasks,
    cleanup_options: schemas.BatchCleanupOptions,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """批量清理操作"""
    try:
        # 检查管理员权限
        check_admin_role(db, current_user_id)
        
        cleanup_tasks = []
        
        # 清理已删除的聊天室
        if cleanup_options.cleanup_deleted_rooms:
            deleted_rooms = await cleanup_deleted_rooms(db, cleanup_options.days_threshold)
            cleanup_tasks.append(f"清理了 {deleted_rooms} 个已删除的聊天室")
        
        # 清理过期消息
        if cleanup_options.cleanup_old_messages:
            old_messages = await cleanup_old_messages(db, cleanup_options.days_threshold)
            cleanup_tasks.append(f"清理了 {old_messages} 条过期消息")
        
        # 清理无效成员
        if cleanup_options.cleanup_invalid_members:
            invalid_members = await cleanup_invalid_members(db)
            cleanup_tasks.append(f"清理了 {invalid_members} 个无效成员")
        
        # 清理过期文件（后台任务）
        if cleanup_options.cleanup_expired_files:
            background_tasks.add_task(
                FileUploadService.cleanup_expired_files, 
                db, 
                cleanup_options.days_threshold
            )
            cleanup_tasks.append("启动了过期文件清理任务")
        
        logger.info(f"管理员 {current_user_id} 执行了批量清理操作")
        
        return {
            "message": "批量清理操作完成",
            "completed_tasks": cleanup_tasks,
            "completed_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量清理操作失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="批量清理操作失败"
        )

@router.get("/admin/real-time-stats", summary="实时统计数据（管理员）")
async def get_real_time_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取实时统计数据"""
    try:
        # 检查管理员权限
        check_admin_role(db, current_user_id)
        
        # 获取实时统计
        stats = await get_real_time_statistics(db)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "statistics": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取实时统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取实时统计失败"
        )

@router.get("/admin/chatroom-stats", summary="获取聊天室统计信息（管理员）")
async def get_chatroom_stats(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=365, description="统计天数")
):
    """获取聊天室统计信息"""
    try:
        # 检查管理员权限
        check_admin_role(db, current_user_id)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 聊天室统计
        total_rooms = db.query(ChatRoom).filter(ChatRoom.is_deleted != True).count()
        active_rooms = db.query(ChatRoom).join(ChatMessage).filter(
            ChatRoom.is_deleted != True,
            ChatMessage.created_at >= start_date
        ).distinct().count()
        
        # 用户活跃度统计
        active_users = db.query(ChatMessage.sender_id).filter(
            ChatMessage.created_at >= start_date
        ).distinct().count()
        
        # 消息统计
        total_messages = db.query(ChatMessage).filter(
            ChatMessage.created_at >= start_date,
            ChatMessage.is_deleted != True
        ).count()
        
        # 按类型统计消息
        message_types = db.query(
            ChatMessage.message_type,
            func.count(ChatMessage.id).label('count')
        ).filter(
            ChatMessage.created_at >= start_date,
            ChatMessage.is_deleted != True
        ).group_by(ChatMessage.message_type).all()
        
        # 最活跃的聊天室
        top_rooms = db.query(
            ChatRoom.id,
            ChatRoom.name,
            func.count(ChatMessage.id).label('message_count')
        ).join(ChatMessage).filter(
            ChatRoom.is_deleted != True,
            ChatMessage.created_at >= start_date,
            ChatMessage.is_deleted != True
        ).group_by(ChatRoom.id, ChatRoom.name).order_by(
            func.count(ChatMessage.id).desc()
        ).limit(10).all()
        
        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "room_statistics": {
                "total_rooms": total_rooms,
                "active_rooms": active_rooms,
                "room_activity_rate": (active_rooms / total_rooms * 100) if total_rooms > 0 else 0
            },
            "user_statistics": {
                "active_users": active_users
            },
            "message_statistics": {
                "total_messages": total_messages,
                "message_types": {row.message_type: row.count for row in message_types}
            },
            "top_active_rooms": [
                {
                    "room_id": row.id,
                    "room_name": row.name,
                    "message_count": row.message_count
                }
                for row in top_rooms
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取聊天室统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取统计信息失败"
        )

# 辅助函数
async def check_database_health(db: Session) -> Dict:
    """检查数据库健康状态"""
    try:
        # 简单的数据库查询测试
        db.execute("SELECT 1").fetchone()
        return {"status": "ok", "message": "数据库连接正常"}
    except Exception as e:
        return {"status": "error", "message": f"数据库连接异常: {str(e)}"}

async def check_cache_health() -> Dict:
    """检查缓存健康状态"""
    try:
        if cache.is_available:
            # 测试缓存连接
            await cache.redis_client.ping()
            return {"status": "ok", "message": "缓存连接正常"}
        else:
            return {"status": "warning", "message": "缓存服务不可用"}
    except Exception as e:
        return {"status": "error", "message": f"缓存连接异常: {str(e)}"}

async def get_system_statistics(db: Session) -> Dict:
    """获取系统统计信息"""
    try:
        total_users = db.query(User).count()
        total_rooms = db.query(ChatRoom).filter(ChatRoom.is_deleted != True).count()
        total_messages = db.query(ChatMessage).filter(ChatMessage.is_deleted != True).count()
        total_members = db.query(ChatRoomMember).filter(ChatRoomMember.status == "active").count()
        
        return {
            "total_users": total_users,
            "total_rooms": total_rooms,
            "total_messages": total_messages,
            "total_active_members": total_members
        }
    except Exception as e:
        logger.error(f"获取系统统计失败: {e}")
        return {}

async def perform_basic_security_scan(db: Session) -> List[Dict]:
    """执行基础安全扫描"""
    issues = []
    
    # 检查是否有过多的管理员
    admin_count = db.query(User).filter(User.role == 'admin').count()
    if admin_count > 5:
        issues.append({
            "type": "too_many_admins",
            "severity": "medium",
            "message": f"系统中有 {admin_count} 个管理员，建议减少管理员数量",
            "count": admin_count
        })
    
    # 检查是否有异常大的聊天室
    large_rooms = db.query(ChatRoom).join(ChatRoomMember).filter(
        ChatRoom.is_deleted != True,
        ChatRoomMember.status == "active"
    ).group_by(ChatRoom.id).having(
        func.count(ChatRoomMember.id) > 1000
    ).all()
    
    if large_rooms:
        issues.append({
            "type": "large_chatrooms",
            "severity": "low",
            "message": f"发现 {len(large_rooms)} 个成员数超过1000的聊天室",
            "count": len(large_rooms)
        })
    
    return issues

async def perform_full_security_scan(db: Session) -> List[Dict]:
    """执行完整安全扫描"""
    issues = []
    
    # 检查是否有大量消息的用户（可能是机器人）
    heavy_senders = db.query(
        ChatMessage.sender_id,
        func.count(ChatMessage.id).label('message_count')
    ).filter(
        ChatMessage.created_at >= datetime.now() - timedelta(days=1),
        ChatMessage.is_deleted != True
    ).group_by(ChatMessage.sender_id).having(
        func.count(ChatMessage.id) > 1000
    ).all()
    
    if heavy_senders:
        issues.append({
            "type": "potential_bots",
            "severity": "high",
            "message": f"发现 {len(heavy_senders)} 个用户在24小时内发送了超过1000条消息",
            "users": [{"user_id": row.sender_id, "message_count": row.message_count} for row in heavy_senders]
        })
    
    return issues

async def get_real_time_statistics(db: Session) -> Dict:
    """获取实时统计数据"""
    from project.routers.chatrooms.websocket_handler import manager
    
    # WebSocket连接统计
    connection_stats = manager.get_connection_stats()
    
    # 最近1小时的活动统计
    recent_time = datetime.now() - timedelta(hours=1)
    recent_messages = db.query(ChatMessage).filter(
        ChatMessage.created_at >= recent_time,
        ChatMessage.is_deleted != True
    ).count()
    
    recent_users = db.query(ChatMessage.sender_id).filter(
        ChatMessage.created_at >= recent_time,
        ChatMessage.is_deleted != True
    ).distinct().count()
    
    return {
        "websocket_connections": connection_stats,
        "recent_activity": {
            "messages_last_hour": recent_messages,
            "active_users_last_hour": recent_users
        },
        "cache_status": {
            "available": cache.is_available
        }
    }

async def cleanup_deleted_rooms(db: Session, days: int) -> int:
    """清理已删除的聊天室"""
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 查找需要永久删除的聊天室
    rooms_to_delete = db.query(ChatRoom).filter(
        ChatRoom.is_deleted == True,
        ChatRoom.deleted_at < cutoff_date
    ).all()
    
    count = len(rooms_to_delete)
    
    # 删除相关数据
    for room in rooms_to_delete:
        # 删除成员记录
        db.query(ChatRoomMember).filter(ChatRoomMember.room_id == room.id).delete()
        # 删除消息记录
        db.query(ChatMessage).filter(ChatMessage.room_id == room.id).delete()
        # 删除聊天室
        db.delete(room)
    
    db.commit()
    return count

async def cleanup_old_messages(db: Session, days: int) -> int:
    """清理过期消息"""
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 软删除过期消息
    result = db.query(ChatMessage).filter(
        ChatMessage.created_at < cutoff_date,
        ChatMessage.is_deleted != True
    ).update({
        "is_deleted": True,
        "deleted_at": datetime.now()
    })
    
    db.commit()
    return result

async def cleanup_invalid_members(db: Session) -> int:
    """清理无效成员"""
    # 清理关联用户不存在的成员记录
    invalid_members = db.query(ChatRoomMember).outerjoin(User).filter(
        User.id.is_(None)
    ).all()
    
    count = len(invalid_members)
    
    for member in invalid_members:
        db.delete(member)
    
    db.commit()
    return count
