# project/routers/search_engine.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import requests
import logging

# 导入数据库和模型
from database import get_db
from models import UserSearchEngineConfig
from dependencies import get_current_user_id
import schemas
from ai_providers.search_provider import call_web_search_api
from ai_providers.security_utils import decrypt_key, encrypt_key

# 配置日志
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/search-engine",
    tags=["搜索引擎配置管理"],
    responses={404: {"description": "Not found"}},
)

# --- 辅助函数：检查搜索引擎服务连通性 ---
async def check_search_engine_connectivity(engine_type: str, api_key: str,
                                           base_url: Optional[str] = None) -> schemas.SearchEngineStatusResponse:
    """
    尝试检查搜索引擎API的连通性。
    此处为简化模拟，实际应根据搜索引擎的API文档实现。
    """
    logger.info(f"Checking connectivity for {engine_type} search engine")

    # 模拟一个简单的查询，例如 "test"
    test_query = "connectivity_test"

    try:
        # 复用 ai_providers 中的搜索逻辑进行测试
        await call_web_search_api(test_query, engine_type, api_key, base_url)
        return schemas.SearchEngineStatusResponse(
            status="success",
            message=f"成功连接到 {engine_type} 搜索引擎服务。",
            timestamp=datetime.now()
        )
    except requests.exceptions.Timeout:
        return schemas.SearchEngineStatusResponse(
            status="timeout",
            message=f"连接 {engine_type} 搜索引擎超时。",
            timestamp=datetime.now()
        )
    except requests.exceptions.HTTPError as e:
        return schemas.SearchEngineStatusResponse(
            status="failure",
            message=f"{engine_type} 搜索引擎HTTP错误 ({e.response.status_code}): {e.response.text}",
            timestamp=datetime.now()
        )
    except (ValueError, KeyError) as e:
        return schemas.SearchEngineStatusResponse(
            status="failure",
            message=f"{engine_type} 搜索引擎配置错误: {e}",
            timestamp=datetime.now()
        )
    except Exception as e:
        return schemas.SearchEngineStatusResponse(
            status="failure",
            message=f"无法检查 {engine_type} 搜索引擎连通性: 未知错误",
            timestamp=datetime.now()
        )

# --- 搜索引擎配置管理接口 ---
@router.post("/", response_model=schemas.UserSearchEngineConfigResponse,
          summary="创建新的搜索引擎配置")
async def create_search_engine_config(
        config_data: schemas.UserSearchEngineConfigCreate,
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    logger.info(f"User {current_user_id} attempting to create search engine config: {config_data.name}")

    # 核心：确保 API 密钥存在且不为空 (对于大多数搜索引擎这是必需的)
    if not config_data.api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API 密钥不能为空。")

    # 检查是否已存在同名且活跃的配置，避免用户创建重复的配置
    existing_config = db.query(UserSearchEngineConfig).filter(
        UserSearchEngineConfig.owner_id == current_user_id,
        UserSearchEngineConfig.name == config_data.name,
        UserSearchEngineConfig.is_active == True  # 只检查活跃的配置是否有重名
    ).first()

    if existing_config:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="已存在同名且活跃的搜索引擎配置。请选择其他名称或停用旧配置。")

    # 加密 API 密钥
    encrypted_key = encrypt_key(config_data.api_key)

    # 创建数据库记录
    db_config = UserSearchEngineConfig(
        owner_id=current_user_id,
        name=config_data.name,
        engine_type=config_data.engine_type,
        api_key_encrypted=encrypted_key,
        is_active=config_data.is_active,
        description=config_data.description,
        base_url=config_data.base_url
    )

    db.add(db_config)
    db.commit()  # 提交事务
    db.refresh(db_config)  # 刷新以获取数据库生成的ID和时间戳

    logger.info(f"Successfully created search engine config '{db_config.name}' (ID: {db_config.id}) for user {current_user_id}")
    return db_config

@router.get("/", response_model=List[schemas.UserSearchEngineConfigResponse],
         summary="获取当前用户所有搜索引擎配置")
async def get_all_search_engine_configs(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        is_active: Optional[bool] = None  # 过滤条件：只获取启用或禁用的配置
):
    """
    获取当前用户配置的所有搜索引擎。
    """
    logger.debug(f"Retrieving search engine configs for user {current_user_id}")
    query = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.owner_id == current_user_id)
    if is_active is not None:
        query = query.filter(UserSearchEngineConfig.is_active == is_active)

    configs = query.order_by(UserSearchEngineConfig.created_at.desc()).all()
    for config in configs:
        config.api_key = None
    logger.debug(f"Retrieved {len(configs)} search engine configs")
    return configs

@router.get("/{config_id}", response_model=schemas.UserSearchEngineConfigResponse,
         summary="获取指定搜索引擎配置详情")
async def get_search_engine_config_by_id(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的搜索引擎配置详情。用户只能获取自己的配置。
    """
    logger.debug(f"Retrieving search engine config ID: {config_id}")
    config = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.id == config_id,
                                                     UserSearchEngineConfig.owner_id == current_user_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Search engine config not found or not authorized")

    config.api_key = None  # 不返回密钥
    return config

@router.put("/{config_id}", response_model=schemas.UserSearchEngineConfigResponse,
         summary="更新指定搜索引擎配置")
async def update_search_engine_config(
        config_id: int,  # 从路径中获取配置ID
        config_data: schemas.UserSearchEngineConfigBase,  # 用于更新的数据
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    logger.debug(f"Updating search engine config ID: {config_id}")
    # 核心权限检查：根据配置ID和拥有者ID来检索，确保操作的是当前用户的配置
    db_config = db.query(UserSearchEngineConfig).filter(
        UserSearchEngineConfig.id == config_id,
        UserSearchEngineConfig.owner_id == current_user_id  # 确保当前用户是该配置的拥有者
    ).first()

    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="搜索引擎配置未找到或无权访问")

    # 排除未设置的字段，只更新传入的字段
    update_data = config_data.dict(exclude_unset=True)

    # 处理 API 密钥的更新：加密或清空
    if "api_key" in update_data:  # 检查传入数据中是否有 api_key 字段
        if update_data["api_key"] is not None and update_data["api_key"] != "":
            # 如果提供了新的密钥且不为空，加密并存储
            db_config.api_key_encrypted = encrypt_key(update_data["api_key"])
        else:
            # 如果传入的是 None 或空字符串，表示清空密钥
            db_config.api_key_encrypted = None

    if "name" in update_data and update_data["name"] != db_config.name:
        # 查找当前用户下是否已存在与新名称相同的活跃配置
        existing_config_with_new_name = db.query(UserSearchEngineConfig).filter(
            UserSearchEngineConfig.owner_id == current_user_id,
            UserSearchEngineConfig.name == update_data["name"],
            UserSearchEngineConfig.is_active == True,  # 只检查活跃的配置
            UserSearchEngineConfig.id != config_id  # 排除当前正在更新的配置本身
        ).first()
        if existing_config_with_new_name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="新配置名称已存在于您的活跃配置中。")

    # 应用其他更新：通过循环处理所有可能更新的字段，更简洁和全面
    fields_to_update = ["name", "engine_type", "is_active", "description", "base_url"]
    for field in fields_to_update:
        if field in update_data:  # 只有当传入的数据包含这个字段时才更新
            setattr(db_config, field, update_data[field])

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    # 安全处理：确保敏感的API密钥不会返回给客户端
    db_config.api_key = None  # 确保不返回明文密钥

    logger.info(f"Successfully updated search engine config {config_id}")
    return db_config

@router.delete("/{config_id}", summary="删除指定搜索引擎配置")
async def delete_search_engine_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的搜索引擎配置。用户只能删除自己的配置。
    """
    logger.debug(f"Deleting search engine config ID: {config_id}")
    db_config = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.id == config_id,
                                                        UserSearchEngineConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Search engine config not found or not authorized")

    db.delete(db_config)
    db.commit()
    logger.info(f"Successfully deleted search engine config {config_id}")
    return {"message": "Search engine config deleted successfully"}

@router.post("/{config_id}/check-status", response_model=schemas.SearchEngineStatusResponse,
          summary="检查指定搜索引擎的连通性")
async def check_search_engine_config_status(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    检查指定ID的搜索引擎配置的API连通性。
    """
    logger.debug(f"Checking connectivity for search engine config ID: {config_id}")
    db_config = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.id == config_id,
                                                        UserSearchEngineConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Search engine config not found or not authorized")

    decrypted_key = None
    if db_config.api_key_encrypted:
        try:
            decrypted_key = decrypt_key(db_config.api_key_encrypted)
        except (ValueError, KeyError) as e:
            return schemas.SearchEngineStatusResponse(
                status="failure",
                message=f"无法解密API密钥，密钥格式错误: {e}",
                engine_name=db_config.name,
                config_id=config_id
            )
        except Exception as e:
            return schemas.SearchEngineStatusResponse(
                status="failure",
                message="无法解密API密钥，请检查密钥是否正确或重新配置",
                engine_name=db_config.name,
                config_id=config_id
            )

    # 调用辅助函数进行实际连通性检查
    status_response = await check_search_engine_connectivity(db_config.engine_type, decrypted_key,
                                                             getattr(db_config, 'base_url', None))
    status_response.engine_name = db_config.name
    status_response.config_id = config_id

    logger.info(f"Connectivity check result for config {config_id}: {status_response.status}")
    return status_response

# --- 网络搜索接口 ---
@router.post("/web-search", response_model=schemas.WebSearchResponse, summary="执行一次网络搜索")
async def perform_web_search(
        search_request: schemas.WebSearchRequest,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    使用用户配置的搜索引擎执行网络搜索。
    可以指定使用的搜索引擎配置ID。
    """
    logger.info(f"User {current_user_id} performing web search: '{search_request.query}'")

    if not search_request.engine_config_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须指定一个搜索引擎配置ID。")

    db_config = db.query(UserSearchEngineConfig).filter(
        UserSearchEngineConfig.id == search_request.engine_config_id,
        UserSearchEngineConfig.owner_id == current_user_id,
        UserSearchEngineConfig.is_active == True  # 确保配置已启用
    ).first()

    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的搜索引擎配置不存在、未启用或无权访问。")

    decrypted_key = None
    if db_config.api_key_encrypted:
        try:
            decrypted_key = decrypt_key(db_config.api_key_encrypted)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API密钥格式错误，请重新配置。")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="无法解密API密钥，请检查配置。")

    start_time = datetime.now()
    try:
        # 调用 ai_providers 中的实际搜索逻辑
        # Note: getattr(db_config, 'base_url', None) 确保即使模型没有此属性也不会报错
        results = await call_web_search_api(
            search_request.query,
            db_config.engine_type,
            decrypted_key,
            getattr(db_config, 'base_url', None)  # 传递 base_url
        )
        search_time = (datetime.now() - start_time).total_seconds()

        logger.info(f"Web search completed using '{db_config.name}' ({db_config.engine_type}), found {len(results)} results")
        return schemas.WebSearchResponse(
            query=search_request.query,
            engine_used=db_config.name,
            results=results,
            total_results=len(results),
            search_time=round(search_time, 2)
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Web search request failed: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="搜索服务暂时不可用，请稍后重试。")
    except Exception as e:
        logger.error(f"Web search request failed: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="网络搜索服务调用失败。")
