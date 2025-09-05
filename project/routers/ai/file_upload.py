"""
AI文件上传处理路由
专门处理文件上传和处理功能
"""

import uuid
import os
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session

# 项目依赖
from project.database import get_db, SessionLocal
from project.utils import get_current_user_id
from project.models import AIConversationTemporaryFile
import project.oss_utils as oss_utils
from .utils import (
    process_ai_temp_file_in_background,
    validate_file_type,
    sanitize_filename,
    get_file_size_mb
)
from .ai_config import EnterpriseAIRouterConfig

# 企业级日志
try:
    from logs.ai_providers.ai_logger import get_ai_logger
    logger = get_ai_logger("ai_file_upload")
except ImportError:
    import logging
    logger = logging.getLogger("ai_file_upload")


# 加载配置
config = EnterpriseAIRouterConfig()

router = APIRouter(
    prefix="/ai/files",
    tags=["AI文件处理"],
    responses={404: {"description": "资源未找到"}},
)


@router.post("/upload", summary="上传AI对话临时文件")
async def upload_ai_temp_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    conversation_id: Optional[int] = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    上传AI对话的临时文件，支持PDF、DOCX等格式
    文件将在后台异步处理，提取文本和生成嵌入
    """
    try:
        # 验证文件
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件名不能为空"
            )

        # 检查文件类型
        if not validate_file_type(file.filename, config.supported_file_types):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件类型。支持的类型: {', '.join(config.supported_file_types)}"
            )

        # 检查文件大小
        file_content = await file.read()
        if len(file_content) > config.max_upload_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件太大。最大支持 {get_file_size_mb(config.max_upload_size)} MB"
            )

        # 清理文件名
        clean_filename = sanitize_filename(file.filename)
        file_ext = os.path.splitext(clean_filename)[1].lower()

        # 生成唯一的OSS对象名
        unique_id = str(uuid.uuid4())
        timestamp = int(time.time())
        oss_object_name = f"ai_temp_files/{user_id}/{timestamp}_{unique_id}{file_ext}"

        # 上传到OSS
        try:
            upload_success = await oss_utils.upload_file_to_oss(file_content, oss_object_name)
            if not upload_success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="文件上传到云存储失败"
                )
        except Exception as e:
            logger.error(f"OSS上传失败: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"文件上传失败: {str(e)}"
            )

        # 创建数据库记录
        db_temp_file = AIConversationTemporaryFile(
            conversation_id=conversation_id,
            user_id=user_id,
            original_filename=clean_filename,
            file_type=file_ext,
            file_size=len(file_content),
            oss_object_name=oss_object_name,
            status="uploaded",
            processing_message="文件已上传，等待处理..."
        )
        
        db.add(db_temp_file)
        db.commit()
        db.refresh(db_temp_file)

        # 启动后台任务处理文件
        background_tasks.add_task(
            process_ai_temp_file_in_background,
            db_temp_file.id,
            user_id,
            oss_object_name,
            file_ext,
            SessionLocal()
        )

        logger.info(f"用户 {user_id} 上传文件 {clean_filename}，开始后台处理")

        return {
            "file_id": str(db_temp_file.id),
            "status": "uploaded",
            "message": "文件上传成功，正在后台处理",
            "filename": clean_filename,
            "size_mb": get_file_size_mb(len(file_content))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传AI临时文件时发生错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件上传失败: {str(e)}"
        )


@router.get("/status/{file_id}", summary="查询文件处理状态")
async def get_file_processing_status(
    file_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """查询文件处理状态"""
    temp_file = db.query(AIConversationTemporaryFile).filter(
        AIConversationTemporaryFile.id == file_id,
        AIConversationTemporaryFile.user_id == user_id
    ).first()

    if not temp_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件记录未找到"
        )

    return {
        "file_id": str(temp_file.id),
        "filename": temp_file.original_filename,
        "status": temp_file.status,
        "processing_message": temp_file.processing_message,
        "uploaded_at": temp_file.uploaded_at,
        "has_text": bool(temp_file.extracted_text),
        "text_length": len(temp_file.extracted_text) if temp_file.extracted_text else 0
    }


@router.delete("/{file_id}", summary="删除临时文件")
async def delete_temp_file(
    file_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """删除临时文件记录和OSS文件"""
    temp_file = db.query(AIConversationTemporaryFile).filter(
        AIConversationTemporaryFile.id == file_id,
        AIConversationTemporaryFile.user_id == user_id
    ).first()

    if not temp_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件记录未找到"
        )

    try:
        # 删除OSS文件
        if temp_file.oss_object_name:
            try:
                await oss_utils.delete_file_from_oss(temp_file.oss_object_name)
            except Exception as e:
                logger.warning(f"删除OSS文件失败: {e}")

        # 删除数据库记录
        db.delete(temp_file)
        db.commit()

        logger.info(f"用户 {user_id} 删除了临时文件 {file_id}")

        return {"message": "文件删除成功"}

    except Exception as e:
        db.rollback()
        logger.error(f"删除临时文件失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除文件失败"
        )
