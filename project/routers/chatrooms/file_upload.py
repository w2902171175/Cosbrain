# project/routers/chatrooms/file_upload.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import List, Union

from project.database import get_db
from project.utils import get_current_user_id
from project.models import ChatRoom, ChatRoomMember, ChatMessage
import project.schemas as schemas
from project.services.file_service import FileUploadService
from project.utils.security.permissions import check_room_access
from project.utils.async_cache.cache import cache
from project.utils import _award_points
from project.services.chatroom_base_service import ChatRoomBaseService

logger = logging.getLogger(__name__)
router = APIRouter()

# 文件类型配置
FILE_TYPE_CONFIG = {
    "audio": {"max_count": 1, "points": 2},
    "image": {"max_count": 9, "points": 2},
    "document": {"max_count": 5, "points": 3},
    "video": {"max_count": 1, "points": 5}
}

@router.post("/chatrooms/{room_id}/upload/", response_model=Union[schemas.ChatMessageResponse, dict], summary="统一文件上传接口")
@ChatRoomBaseService.handle_chatroom_operation(require_room_access=True, invalidate_cache=True)
async def upload_files(
    room_id: int,
    file_type: str = Form(..., description="文件类型: audio, image, document, video"),
    files: List[UploadFile] = File(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    reply_to_id: int = Form(None),
    room=None,  # 由装饰器注入
    member=None  # 由装饰器注入
):
    """统一的文件上传接口"""
    # 验证文件类型
    if file_type not in FILE_TYPE_CONFIG:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型: {file_type}"
        )
    
    config = FILE_TYPE_CONFIG[file_type]
    
    # 验证文件数量
    ChatRoomBaseService.validate_file_limits(files, config["max_count"], file_type)
    
    # 处理单文件上传（音频、视频）
    if file_type in ["audio", "video"] and len(files) == 1:
        file_info = await FileUploadService.validate_and_upload_file(
            file=files[0],
            user_id=current_user_id,
            file_type=file_type
        )
        
        content_prefix = {"audio": "[音频]", "video": "[视频]"}[file_type]
        db_message = await ChatRoomBaseService.create_message_with_cache(
            db=db,
            room_id=room_id,
            sender_id=current_user_id,
            content=f"{content_prefix} {file_info['original_filename']}",
            message_type=file_type,
            media_url=file_info["media_url"],
            reply_to_id=reply_to_id,
            file_info=file_info
        )
        
        # 奖励积分
        await _award_points(db, current_user_id, config["points"], f"上传{file_type}")
        
        logger.info(f"用户 {current_user_id} 在聊天室 {room_id} 上传了{file_type}文件")
        return db_message
    
    # 处理批量文件上传（图片、文档）
    else:
        result = await ChatRoomBaseService.batch_process_uploads(
            files=files,
            user_id=current_user_id,
            file_type=file_type,
            room_id=room_id,
            db=db,
            reply_to_id=reply_to_id
        )
        
        # 奖励积分
        await _award_points(db, current_user_id, result["successful_count"] * config["points"], f"上传{file_type}")
        
        logger.info(f"用户 {current_user_id} 在聊天室 {room_id} 上传了 {result['successful_count']} 个{file_type}文件")
        
        return result

# 保留旧的API端点以维持向后兼容性
@router.post("/chatrooms/{room_id}/upload-audio/", response_model=schemas.ChatMessageResponse, summary="上传音频文件（兼容接口）")
async def upload_audio_file_legacy(
    room_id: int,
    audio_file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    reply_to_id: int = Form(None)
):
    """上传音频文件到聊天室（兼容接口）"""
    return await upload_files(
        room_id=room_id,
        file_type="audio",
        files=[audio_file],
        current_user_id=current_user_id,
        db=db,
        reply_to_id=reply_to_id
    )

@router.post("/chatrooms/{room_id}/upload-gallery/", response_model=dict, summary="批量上传图片（兼容接口）")
async def upload_gallery_files_legacy(
    room_id: int,
    gallery_files: List[UploadFile] = File(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    reply_to_id: int = Form(None)
):
    """批量上传图片到聊天室（兼容接口）"""
    return await upload_files(
        room_id=room_id,
        file_type="image",
        files=gallery_files,
        current_user_id=current_user_id,
        db=db,
        reply_to_id=reply_to_id
    )

@router.post("/chatrooms/{room_id}/upload-documents/", response_model=dict, summary="批量上传文档（兼容接口）")
async def upload_document_files_legacy(
    room_id: int,
    document_files: List[UploadFile] = File(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    reply_to_id: int = Form(None)
):
    """批量上传文档到聊天室（兼容接口）"""
    return await upload_files(
        room_id=room_id,
        file_type="document",
        files=document_files,
        current_user_id=current_user_id,
        db=db,
        reply_to_id=reply_to_id
    )

@router.post("/chatrooms/{room_id}/upload-video/", response_model=schemas.ChatMessageResponse, summary="上传视频文件（兼容接口）")
async def upload_video_file_legacy(
    room_id: int,
    video_file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    reply_to_id: int = Form(None)
):
    """上传视频文件到聊天室（兼容接口）"""
    return await upload_files(
        room_id=room_id,
        file_type="video",
        files=[video_file],
        current_user_id=current_user_id,
        db=db,
        reply_to_id=reply_to_id
    )

@router.get("/files/{file_id}/access", summary="验证文件访问权限")
async def verify_file_access(
    file_id: str,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """验证用户对文件的访问权限"""
    try:
        # 通过文件URL或ID查找相关消息
        message = db.query(ChatMessage).filter(
            ChatMessage.media_url.contains(file_id)
        ).first()
        
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件不存在"
            )
        
        # 检查用户是否有访问该聊天室的权限
        try:
            check_room_access(db, message.room_id, current_user_id)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您没有访问此文件的权限"
            )
        
        return {
            "file_id": file_id,
            "access_granted": True,
            "room_id": message.room_id,
            "message_id": message.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证文件访问权限失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="验证文件权限失败"
        )

@router.get("/chatrooms/{room_id}/storage-quota", summary="获取用户存储配额")
async def get_user_storage_quota(
    room_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """获取用户在特定聊天室的存储配额使用情况"""
    try:
        # 检查访问权限
        check_room_access(db, room_id, current_user_id)
        
        # 计算用户在该聊天室的文件使用量
        total_size = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.sender_id == current_user_id,
            ChatMessage.media_url.isnot(None),
            ChatMessage.is_deleted != True
        ).count()  # 这里应该计算实际文件大小，简化为文件数量
        
        # 假设配额限制（这些应该从配置或用户等级获取）
        quota_limits = {
            "max_files_per_room": 100,
            "max_total_size_mb": 500
        }
        
        return {
            "room_id": room_id,
            "user_id": current_user_id,
            "used_files": total_size,
            "quota_limits": quota_limits,
            "usage_percentage": min(100, (total_size / quota_limits["max_files_per_room"]) * 100)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取存储配额失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取存储配额失败"
        )
