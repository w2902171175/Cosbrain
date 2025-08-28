# project/routers/tts/tts.py
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

# 导入数据库和模型
from database import get_db
from models.models import UserTTSConfig
from schemas.schemas import UserTTSConfigCreate, UserTTSConfigUpdate, UserTTSConfigResponse
from dependencies.dependencies import get_current_user_id

from jose import JWTError, jwt
from dependencies.dependencies import SECRET_KEY, ALGORITHM
from ai_providers.security_utils import encrypt_key

router = APIRouter(
    prefix="/users/me/tts_configs",
    tags=["TTS配置管理"],
    responses={404: {"description": "Not found"}},
)

async def get_active_tts_config(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
) -> Optional[UserTTSConfig]:
    """获取当前用户激活的TTS配置"""
    return db.query(UserTTSConfig).filter(
        UserTTSConfig.owner_id == current_user_id,
        UserTTSConfig.is_active == True
    ).first()

@router.post("", response_model=UserTTSConfigResponse, summary="为当前用户创建新的TTS配置")
async def create_user_tts_config(
        tts_config_data: UserTTSConfigCreate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建新的TTS配置: {tts_config_data.name}")

    # 检查配置名称是否已存在
    existing_config = db.query(UserTTSConfig).filter(
        UserTTSConfig.owner_id == current_user_id,
        UserTTSConfig.name == tts_config_data.name
    ).first()
    if existing_config:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"已存在同名TTS配置: '{tts_config_data.name}'。")

    # 检查是否有其他配置被意外设置为 active (防止前端逻辑错误，这里再确认一次)
    # 理论上数据库约束会处理，但在此业务逻辑层再做一遍，保证数据一致性
    if tts_config_data.is_active:
        active_config_for_user = db.query(UserTTSConfig).filter(
            UserTTSConfig.owner_id == current_user_id,
            UserTTSConfig.is_active == True
        ).first()
        if active_config_for_user:
            active_config_for_user.is_active = False  # 将旧的激活配置设为非激活
            db.add(active_config_for_user)
            print(f"DEBUG: 将用户 {current_user_id} 的旧激活TTS配置 '{active_config_for_user.name}' 置为非激活。")

    encrypted_key = None
    if tts_config_data.api_key:
        try:
            encrypted_key = encrypt_key(tts_config_data.api_key)
        except Exception as e:
            print(f"ERROR: 加密TTS API密钥失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="加密API密钥失败。")

    new_tts_config = UserTTSConfig(
        owner_id=current_user_id,
        name=tts_config_data.name,
        tts_type=tts_config_data.tts_type,
        api_key_encrypted=encrypted_key,
        base_url=tts_config_data.base_url,
        model_id=tts_config_data.model_id,
        voice_name=tts_config_data.voice_name,
        is_active=tts_config_data.is_active  # 如果创建时就设为激活，则激活
    )

    db.add(new_tts_config)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建TTS配置发生完整性约束错误: {e}")
        # 捕获数据库层面的活跃配置唯一性冲突
        if "_owner_id_active_tts_config_uc" in str(e):  # 根据models.py中的唯一约束名称判断
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="每个用户只能有一个激活的TTS配置。请先设置现有配置为非激活，或更新现有激活配置。")
        elif "_owner_id_tts_config_name_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TTS配置名称已存在。")
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="创建TTS配置失败，请检查输入或联系管理员。")

    db.refresh(new_tts_config)
    print(f"DEBUG: 用户 {current_user_id} 成功创建TTS配置: {new_tts_config.name} (ID: {new_tts_config.id})")
    return new_tts_config

@router.get("", response_model=List[UserTTSConfigResponse], summary="获取当前用户的所有TTS配置")
async def get_user_tts_configs(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取用户 {current_user_id} 的所有TTS配置。")
    tts_configs = db.query(UserTTSConfig).filter(UserTTSConfig.owner_id == current_user_id).all()
    return tts_configs

@router.get("/{config_id}", response_model=UserTTSConfigResponse, summary="获取指定TTS配置详情")
async def get_single_user_tts_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取用户 {current_user_id} 的TTS配置 ID: {config_id}。")
    tts_config = db.query(UserTTSConfig).filter(
        UserTTSConfig.id == config_id,
        UserTTSConfig.owner_id == current_user_id
    ).first()
    if not tts_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TTS配置未找到或无权访问。")
    return tts_config

@router.put("/{config_id}", response_model=UserTTSConfigResponse, summary="更新指定TTS配置")
async def update_user_tts_config(
        config_id: int,
        tts_config_data: UserTTSConfigUpdate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试更新TTS配置 ID: {config_id}。")
    db_tts_config = db.query(UserTTSConfig).filter(
        UserTTSConfig.id == config_id,
        UserTTSConfig.owner_id == current_user_id
    ).first()
    if not db_tts_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TTS配置未找到或无权访问。")

    update_data = tts_config_data.dict(exclude_unset=True)

    # 如果尝试改变名称，检查新名称是否冲突
    if "name" in update_data and update_data["name"] is not None and update_data["name"] != db_tts_config.name:
        existing_name_config = db.query(UserTTSConfig).filter(
            UserTTSConfig.owner_id == current_user_id,
            UserTTSConfig.name == update_data["name"],
            UserTTSConfig.id != config_id
        ).first()
        if existing_name_config:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"TTS配置名称 '{update_data['name']}' 已被使用。")

    # 特殊处理 is_active 字段的逻辑：确保只有一个配置为 active
    if "is_active" in update_data and update_data["is_active"] is True:
        # 找到当前用户的所有其他处于 active 状态的配置，并将其设为 False
        active_configs = db.query(UserTTSConfig).filter(
            UserTTSConfig.owner_id == current_user_id,
            UserTTSConfig.is_active == True,
            UserTTSConfig.id != config_id  # 排除当前正在更新的配置
        ).all()
        for config_to_deactivate in active_configs:
            config_to_deactivate.is_active = False
            db.add(config_to_deactivate)
            print(f"DEBUG: 将用户 {current_user_id} 的旧激活TTS配置 '{config_to_deactivate.name}' 置为非激活。")
    # 如果 is_active 从 True 变为 False，不需要特殊处理，直接更新即可

    # 特殊处理 api_key：加密后再存储
    if "api_key" in update_data and update_data["api_key"] is not None:
        try:
            db_tts_config.api_key_encrypted = encrypt_key(update_data["api_key"])
            del update_data["api_key"]  # 从 update_data 中移除，防止通用循环再次处理
        except Exception as e:
            print(f"ERROR: 加密TTS API密钥失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="加密API密钥失败。")

    for key, value in update_data.items():
        setattr(db_tts_config, key, value)

    db.add(db_tts_config)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新TTS配置发生完整性约束错误: {e}")
        # 根据 models.py 中的唯一约束名称判断
        if "_owner_id_active_tts_config_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="每个用户只能有一个激活的TTS配置。")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新TTS配置失败。")

    db.refresh(db_tts_config)
    print(f"DEBUG: 用户 {current_user_id} 成功更新TTS配置 ID: {config_id}.")
    return db_tts_config

@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定TTS配置")
async def delete_user_tts_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试删除TTS配置 ID: {config_id}。")
    db_tts_config = db.query(UserTTSConfig).filter(
        UserTTSConfig.id == config_id,
        UserTTSConfig.owner_id == current_user_id
    ).first()
    if not db_tts_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TTS配置未找到或无权访问。")

    db.delete(db_tts_config)
    db.commit()
    print(f"DEBUG: 用户 {current_user_id} 成功删除TTS配置 ID: {config_id}.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.put("/{config_id}/set_active", response_model=UserTTSConfigResponse,
         summary="设置指定TTS配置为激活状态")
async def set_active_user_tts_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试设置TTS配置 ID: {config_id} 为激活状态。")

    # 1. 找到并验证要激活的配置
    db_tts_config_to_activate = db.query(UserTTSConfig).filter(
        UserTTSConfig.id == config_id,
        UserTTSConfig.owner_id == current_user_id
    ).first()
    if not db_tts_config_to_activate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TTS配置未找到或无权访问。")

    # 2. 将用户所有其他TTS配置的 is_active 设为 False
    # 排除当前要激活的配置
    configs_to_deactivate = db.query(UserTTSConfig).filter(
        UserTTSConfig.owner_id == current_user_id,
        UserTTSConfig.is_active == True,
        UserTTSConfig.id != config_id
    ).all()

    for config in configs_to_deactivate:
        config.is_active = False
        db.add(config)
        print(f"DEBUG: 将用户 {current_user_id} 的旧激活TTS配置 '{config.name}' 置为非激活。")

    # 3. 将目标配置设为 True
    db_tts_config_to_activate.is_active = True
    db.add(db_tts_config_to_activate)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # 理论上这里的唯一约束已经在模型中用 postgresql_where 处理，并在这里的应用层逻辑中确保了唯一性。
        # 但为防止意外，保留捕获。
        print(f"ERROR_DB: 设置激活TTS配置发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="设置激活TTS配置失败。")

    db.refresh(db_tts_config_to_activate)
    print(f"DEBUG: 用户 {current_user_id} 成功设置TTS配置 ID: {config_id} 为激活状态。")
    return db_tts_config_to_activate