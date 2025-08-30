# project/routers/quick_notes/quick_notes.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

# 使用正确的相对导入
from project.database import get_db
from project.models import DailyRecord, Student
from project.dependencies import get_current_user_id
from project.utils import (_get_text_part, generate_embedding_safe, get_user_resource_or_404, 
                  debug_operation, commit_or_rollback, create_and_add_resource, update_embedding_safe)

import schemas
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key

router = APIRouter(
    prefix="/daily-records",
    tags=["随手记录"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=schemas.DailyRecordResponse, summary="创建新随手记录")
async def create_daily_record(
        record_data: schemas.DailyRecordBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新随手记录。
    后端会根据记录内容生成 combined_text 和 embedding，用于未来智能分析或搜索。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试创建随手记录。")

    # 组合文本用于嵌入
    combined_text = (
            (record_data.content or "") + ". " +
            (record_data.mood or "") + ". " +
            (record_data.tags or "")
    ).strip()
    # 如果组合文本为空，直接跳过嵌入
    if not combined_text:
        combined_text = ""

    # 获取当前用户的LLM配置用于嵌入生成
    record_owner = db.query(Student).filter(Student.id == current_user_id).first()
    owner_llm_api_key = None
    owner_llm_type = None
    owner_llm_base_url = None
    owner_llm_model_id = None

    # 检查用户是否配置了硅基流动的LLM，并尝试解密API Key
    if record_owner and record_owner.llm_api_type == "siliconflow" and record_owner.llm_api_key_encrypted:
        try:
            owner_llm_api_key = decrypt_key(record_owner.llm_api_key_encrypted)
            owner_llm_type = record_owner.llm_api_type
            owner_llm_base_url = record_owner.llm_api_base_url
            owner_llm_model_id = record_owner.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用随手记录创建者配置的硅基流动 API 密钥为随手记录生成嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密随手记录创建者硅基流动 API 密钥失败: {e}。随手记录嵌入将使用零向量。")
            owner_llm_api_key = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 随手记录创建者未配置硅基流动 API 类型或密钥，随手记录嵌入将使用零向量或默认行为。")

    embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if combined_text:
        try:
            new_embedding = await get_embeddings_from_api(
                [combined_text],
                api_key=owner_llm_api_key,
                llm_type=owner_llm_type,
                llm_base_url=owner_llm_base_url,
                llm_model_id=owner_llm_model_id
            )
            if new_embedding:
                embedding = new_embedding[0]
            # else: get_embeddings_from_api 已经在不生成时返回零向量的List
            print(f"DEBUG: 随手记录嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成随手记录嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 发生错误时，确保设置为零向量
    else:
        print(f"WARNING_EMBEDDING: 随手记录 combined_text 为空，嵌入向量设为零。")
        # 如果 combined_text 为空，embedding 保持为默认的零向量

    db_record = DailyRecord(
        owner_id=current_user_id,
        content=record_data.content,
        mood=record_data.mood,
        tags=record_data.tags,
        combined_text=combined_text,
        embedding=embedding
    )

    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    print(f"DEBUG: 随手记录 (ID: {db_record.id}) 创建成功。")
    return db_record

@router.get("/", response_model=List[schemas.DailyRecordResponse], summary="获取当前用户所有随手记录")
async def get_all_daily_records(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        mood: Optional[str] = None,
        tag: Optional[str] = None
):
    """
    获取当前用户的所有随手记录。
    可以通过心情（mood）或标签（tag）进行过滤。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有随手记录，心情过滤: {mood}, 标签过滤: {tag}")
    query = db.query(DailyRecord).filter(DailyRecord.owner_id == current_user_id)
    if mood:
        query = query.filter(DailyRecord.mood == mood)
    if tag:
        # 使用 LIKE 进行模糊匹配，因为标签是逗号分隔字符串
        query = query.filter(DailyRecord.tags.ilike(f"%{tag}%"))

    records = query.order_by(DailyRecord.created_at.desc()).all()  # 按创建时间降序
    print(f"DEBUG: 获取到 {len(records)} 条随手记录。")
    return records

@router.get("/{record_id}", response_model=schemas.DailyRecordResponse, summary="获取指定随手记录详情")
async def get_daily_record_by_id(
        record_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的随手记录详情。用户只能获取自己的记录。
    """
    debug_operation("获取随手记录详情", user_id=current_user_id, resource_id=record_id, resource_type="随手记录")
    record = get_user_resource_or_404(db, DailyRecord, record_id, current_user_id, 
                                     "owner_id", "Daily record not found or not authorized")
    return record

@router.put("/{record_id}", response_model=schemas.DailyRecordResponse, summary="更新指定随手记录")
async def update_daily_record(
        record_id: int,
        record_data: schemas.DailyRecordBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的随手记录内容。用户只能更新自己的记录。
    更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新随手记录 ID: {record_id} 的内容。")
    db_record = db.query(DailyRecord).filter(DailyRecord.id == record_id,
                                             DailyRecord.owner_id == current_user_id).first()
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily record not found or not authorized")

    update_data = record_data.dict(exclude_unset=True)  # 只更新传入的字段
    for key, value in update_data.items():
        setattr(db_record, key, value)

    # 重新生成 combined_text
    db_record.combined_text = (
            (db_record.content or "") + ". " +
            (db_record.mood or "") + ". " +
            (db_record.tags or "")
    ).strip()
    # 如果组合文本为空，跳过嵌入
    if not db_record.combined_text:
        db_record.combined_text = ""

    # 获取当前用户的LLM配置用于嵌入更新
    record_owner = db.query(Student).filter(Student.id == current_user_id).first()
    owner_llm_api_key = None
    owner_llm_type = None
    owner_llm_base_url = None
    owner_llm_model_id = None

    if record_owner and record_owner.llm_api_type == "siliconflow" and record_owner.llm_api_key_encrypted:
        try:
            owner_llm_api_key = decrypt_key(record_owner.llm_api_key_encrypted)
            owner_llm_type = record_owner.llm_api_type
            owner_llm_base_url = record_owner.llm_api_base_url
            owner_llm_model_id = record_owner.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用随手记录创建者配置的硅基流动 API 密钥更新随手记录嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密随手记录创建者硅基流动 API 密钥失败: {e}。随手记录嵌入将使用零向量。")
            owner_llm_api_key = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 随手记录创建者未配置硅基流动 API 类型或密钥，随手记录嵌入将使用零向量或默认行为。")

    embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if db_record.combined_text:
        try:
            new_embedding = await get_embeddings_from_api(
                [db_record.combined_text],
                api_key=owner_llm_api_key,
                llm_type=owner_llm_type,
                llm_base_url=owner_llm_base_url,
                llm_model_id=owner_llm_model_id
            )
            if new_embedding:
                embedding_recalculated = new_embedding[0]
            print(f"DEBUG: 随手记录 {db_record.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新随手记录 {db_record.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding_recalculated = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING_EMBEDDING: 随手记录 combined_text 为空，嵌入向量设为零。")
        # 如果 combined_text 为空，embedding 保持为默认的零向量

    db_record.embedding = embedding_recalculated  # 赋值给DB对象

    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    print(f"DEBUG: 随手记录 {db_record.id} 更新成功。")
    return db_record

@router.delete("/{record_id}", summary="删除指定随手记录")
async def delete_daily_record(
        record_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的随手记录。用户只能删除自己的记录。
    """
    print(f"DEBUG: 删除随手记录 ID: {record_id}。")
    db_record = db.query(DailyRecord).filter(DailyRecord.id == record_id,
                                             DailyRecord.owner_id == current_user_id).first()
    if not db_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily record not found or not authorized")

    db.delete(db_record)
    db.commit()
    print(f"DEBUG: 随手记录 {record_id} 删除成功。")
    return {"message": "Daily record deleted successfully"}