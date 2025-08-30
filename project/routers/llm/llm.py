# project/routers/llm/llm.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, List, Optional

from project.database import get_db
from project.models import Student
from project.dependencies import get_current_user_id
import project.schemas as schemas
from project.ai_providers.ai_config import GLOBAL_PLACEHOLDER_ZERO_VECTOR, get_available_llm_configs, get_user_model_for_provider, parse_llm_model_ids, serialize_llm_model_ids
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key, encrypt_key

router = APIRouter(
    tags=["LLM管理"],
    responses={404: {"description": "Not found"}},
)

@router.put("/users/me/llm-config", response_model=schemas.StudentResponse, summary="更新当前用户LLM配置")
async def update_llm_config(
        llm_config_data: schemas.UserLLMConfigUpdate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新当前用户的LLM（大语言模型）API配置，密钥会加密存储。
    **成功更新配置后，会尝试重新计算用户个人资料的嵌入向量。**
    """
    print(f"DEBUG: 更新用户 {current_user_id} 的LLM配置。")
    db_student = db.query(Student).filter(Student.id == current_user_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = llm_config_data.dict(exclude_unset=True)

    # 保存旧的 LLM Key 和 Type，以便在处理新 Key 时进行比较
    # old_llm_api_type = db_student.llm_api_type # 暂时不需要旧值，因为会直接用db_student的当前值
    # old_llm_api_key_encrypted = db_student.llm_api_key_encrypted # 暂时不需要旧值，因为会直接用db_student的当前值

    if "llm_api_type" in update_data:
        db_student.llm_api_type = update_data["llm_api_type"]

    if "llm_api_base_url" in update_data:
        db_student.llm_api_base_url = update_data["llm_api_base_url"]

    if "llm_model_id" in update_data:
        db_student.llm_model_id = update_data["llm_model_id"]

    # 处理新的多模型ID配置
    if "llm_model_ids" in update_data and update_data["llm_model_ids"]:
        try:
            # 序列化多模型配置为JSON字符串
            db_student.llm_model_ids = serialize_llm_model_ids(update_data["llm_model_ids"])
            print(f"DEBUG: 用户 {current_user_id} 的多模型ID配置已更新。")
        except Exception as e:
            print(f"ERROR: 序列化多模型ID配置失败: {e}。将保持原有配置。")

    # 处理 API 密钥的更新：加密或清空
    decrypted_new_key: Optional[str] = None  # 用于后面嵌入重计算
    if "llm_api_key" in update_data and update_data["llm_api_key"]:
        try:
            encrypted_key = encrypt_key(update_data["llm_api_key"])
            db_student.llm_api_key_encrypted = encrypted_key
            decrypted_new_key = update_data["llm_api_key"]  # 存储新密钥的明文供即时使用
            print(f"DEBUG: 用户 {current_user_id} 的LLM API密钥已加密存储。")
        except Exception as e:
            print(f"ERROR: 加密LLM API密钥失败: {e}. 将使用旧密钥或跳过加密。")
            # 即使加密失败，也应该继续，但要确保db_student.llm_api_key_encrypted没有被错误修改
            # 此时 decrypted_new_key 仍为 None，不会导致使用无效密钥
    elif "llm_api_key" in update_data and not update_data["llm_api_key"]:  # 允许清空密钥
        db_student.llm_api_key_encrypted = None
        print(f"DEBUG: 用户 {current_user_id} 的LLM API密钥已清空。")

    db.add(db_student)  # 将所有 LLM 配置的修改暂存到session中

    # 在LLM配置更新后重新计算用户嵌入向量
    # 目的：确保用户的个人资料嵌入与新的LLM配置同步
    # 只有当用户个人资料的 combined_text 存在时才进行计算
    if db_student.combined_text:
        print(f"DEBUG_EMBEDDING_RECALC: 尝试为用户 {current_user_id} 重新计算嵌入向量。")

        # 确定用于嵌入的API密钥和LLM配置
        # 优先使用本次更新提供的明文密钥；否则尝试解密现有密钥
        key_for_embedding_recalc = None  # 最终传递给 ai_core 的解密密钥

        # 从 db_student 获取最新的 LLM 配置字段，确保是更新后的值
        effective_llm_api_type = db_student.llm_api_type
        effective_llm_api_base_url = db_student.llm_api_base_url
        # 优先使用新的多模型配置，fallback到原模型ID
        effective_llm_model_id = get_user_model_for_provider(
            db_student.llm_model_ids,
            db_student.llm_api_type,
            db_student.llm_model_id
        )

        if decrypted_new_key:  # 如果本次更新显式提供了新的明文密钥
            key_for_embedding_recalc = decrypted_new_key
        elif db_student.llm_api_key_encrypted:  # 否则，尝试解密数据库中现有的加密密钥
            try:
                key_for_embedding_recalc = decrypt_key(db_student.llm_api_key_encrypted)
            except Exception as e:
                print(
                    f"WARNING_EMBEDDING_RECALC: 解密用户 {current_user_id} 的LLM API Key失败: {e}。嵌入将使用零向量或默认行为。")
                key_for_embedding_recalc = None  # 无法解密则不使用用户密钥

        try:
            # 将用户 LLM 配置的各个参数传入 get_embeddings_from_api
            new_embedding = await get_embeddings_from_api(
                [db_student.combined_text],
                api_key=key_for_embedding_recalc,  # 传入解密后的API Key
                llm_type=effective_llm_api_type,  # 传入用户配置的LLM类型，用于ai_core判断
                llm_base_url=effective_llm_api_base_url,
                llm_model_id=effective_llm_model_id
            )
            if new_embedding:
                db_student.embedding = new_embedding[0]
                print(f"DEBUG_EMBEDDING_RECALC: 用户 {current_user_id} 嵌入向量已成功重新计算。")
            else:
                # 这种情况应该由 ai_core 处理，但这里也确保一下
                db_student.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
                print(f"DEBUG_EMBEDDING_RECALC: 嵌入API未返回结果。用户 {current_user_id} 嵌入向量设为零。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_RECALC: 为用户 {current_user_id} 重新计算嵌入向量失败: {e}。嵌入向量设为零。")
            db_student.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING_EMBEDDING_RECALC: 用户 {current_user_id} 的 combined_text 为空，无法重新计算嵌入向量。")
        # 确保embedding字段是有效的向量格式，即使没内容也为零向量
        if db_student.embedding is None:
            db_student.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db.commit()  # 提交所有更改，包括LLM配置更新和新的嵌入向量
    db.refresh(db_student)
    print(f"DEBUG: 用户 {current_user_id} LLM配置及嵌入更新成功。")
    return db_student

@router.get("/llm/available-configs", summary="获取可用的LLM服务商配置信息")
async def get_available_llm_configs_api():
    """
    获取所有可用的LLM服务商配置信息，包括默认模型和可用模型列表。
    用于前端展示给用户选择。
    """
    configs = get_available_llm_configs()
    return {
        "available_providers": configs,
        "description": "每个服务商的可用模型列表，用户可以为每个服务商配置多个模型ID"
    }

@router.get("/users/me/llm-model-ids", summary="获取当前用户的多模型ID配置")
async def get_user_llm_model_ids(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取当前用户为不同LLM服务商配置的模型ID列表。
    """
    db_student = db.query(Student).filter(Student.id == current_user_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    model_ids_dict = parse_llm_model_ids(db_student.llm_model_ids)

    # 获取清理后的 fallback_model_id，使用与当前服务商配置一致的逻辑
    fallback_model_id = None
    if db_student.llm_api_type:
        user_models = model_ids_dict.get(db_student.llm_api_type, [])
        if user_models:
            fallback_model_id = user_models[0]
        else:
            # 获取系统默认模型
            available_configs = get_available_llm_configs()
            provider_config = available_configs.get(db_student.llm_api_type, {})
            fallback_model_id = provider_config.get("default_model")

    return {
        "llm_model_ids": model_ids_dict,
        "current_provider": db_student.llm_api_type,
        "fallback_model_id": fallback_model_id,  # 兼容性字段，现在使用清理后的模型ID
        "available_providers": get_available_llm_configs()
    }

@router.get("/users/me/current-provider-models", summary="获取当前用户LLM服务商的可用模型")
async def get_current_provider_models(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取用户当前LLM服务商配置的模型ID列表，用于在聊天界面显示可选模型。
    """
    db_student = db.query(Student).filter(Student.id == current_user_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not db_student.llm_api_type:
        return {
            "current_provider": None,
            "user_configured_models": [],
            "system_available_models": [],
            "recommended_model": None,
            "message": "用户未配置LLM服务商"
        }

    # 获取用户为当前服务商配置的模型
    model_ids_dict = parse_llm_model_ids(db_student.llm_model_ids)
    user_models = model_ids_dict.get(db_student.llm_api_type, [])

    # 获取系统为该服务商提供的默认模型列表
    available_configs = get_available_llm_configs()
    provider_config = available_configs.get(db_student.llm_api_type, {})
    system_models = provider_config.get("available_models", [])

    # 推荐模型：用户配置的第一个，或系统默认模型
    recommended_model = None
    if user_models:
        recommended_model = user_models[0]
    elif provider_config.get("default_model"):
        recommended_model = provider_config["default_model"]

    # fallback_model 使用与 recommended_model 相同的逻辑，而不是直接使用可能包含方括号的 llm_model_id
    fallback_model = recommended_model

    return {
        "current_provider": db_student.llm_api_type,
        "user_configured_models": user_models,
        "system_available_models": system_models,
        "recommended_model": recommended_model,
        "fallback_model": fallback_model  # 兼容性字段，现在使用清理后的模型ID
    }

@router.put("/users/me/llm-model-ids", summary="更新当前用户的多模型ID配置")
async def update_user_llm_model_ids(
        model_ids_update: Dict[str, List[str]],
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新当前用户为不同LLM服务商配置的模型ID列表。
    请求体格式：{"openai": ["gpt-4", "gpt-3.5-turbo"], "zhipu": ["glm-4.5v"]}
    """
    db_student = db.query(Student).filter(Student.id == current_user_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # 验证输入格式
    if not isinstance(model_ids_update, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid format: expected object")

    for provider, models in model_ids_update.items():
        if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid format for provider '{provider}': expected list of strings"
            )

    try:
        # 序列化并保存
        db_student.llm_model_ids = serialize_llm_model_ids(model_ids_update)
        db.add(db_student)
        db.commit()
        db.refresh(db_student)

        print(f"DEBUG: 用户 {current_user_id} 的多模型ID配置已更新。")

        # 返回更新后的配置
        updated_model_ids = parse_llm_model_ids(db_student.llm_model_ids)
        return {
            "message": "模型ID配置更新成功",
            "llm_model_ids": updated_model_ids
        }

    except Exception as e:
        print(f"ERROR: 更新用户 {current_user_id} 多模型ID配置失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新配置失败")

@router.get("/llm/available-models", summary="获取可配置的LLM服务商及模型列表")
async def get_available_llm_models_api():
    """
    返回所有支持的LLM服务商类型及其默认模型和可用模型列表。
    """
    print("DEBUG: 获取可用LLM模型列表。")
    return get_available_llm_configs()