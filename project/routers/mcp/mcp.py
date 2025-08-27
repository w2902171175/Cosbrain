# project/routers/mcp/mcp.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import httpx
from datetime import datetime

from database import get_db
from dependencies import get_current_user_id
from models import UserMcpConfig
import schemas
from ai_providers.security_utils import decrypt_key, encrypt_key

router = APIRouter(
    prefix="/mcp-configs",
    tags=["MCP服务配置"]
)

# --- 辅助函数：检查MCP服务连通性 (可以根据MCP实际API调整) ---
async def check_mcp_api_connectivity(base_url: str, protocol_type: str,
                                     api_key: Optional[str] = None) -> schemas.McpStatusResponse:
    """
    尝试ping MCP服务的健康检查端点或一个简单的公共API。
    此处为简化实现，实际应根据MCP的具体API文档实现。
    """
    print(f"DEBUG_MCP: Checking connectivity for {base_url} with protocol {protocol_type}")

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        if "modelscope" in base_url.lower():
            headers["X-DashScope-Apikey"] = api_key  # 为Modelscope添加专用header

    # 使用 httpx.AsyncClient 进行异步请求
    async with httpx.AsyncClient() as client:
        try:
            is_modelscope_inference_url = "mcp.api-inference.modelscope.net" in base_url.lower() \
                                          or "modelscope.cn/api/v1/inference" in base_url.lower()

            if is_modelscope_inference_url:
                print(f"DEBUG_MCP: Attempting HEAD on ModelScope inference URL: {base_url}")
                response = await client.head(base_url, headers=headers, timeout=5)
                # 对于推理服务，如果返回 405 (Method Not Allowed), 表示服务器可达，但不支持HEAD，这仍可视为成功连通
                if response.status_code == 405:
                    return schemas.McpStatusResponse(
                        status="success",
                        message=f"ModelScope推理服务可达 (HTTP 405 Method Not Allowed): {base_url}",
                        timestamp=datetime.now()
                    )
                # 404 (Not Found) 表示该 URL 路径确实不存在，是真正的失败
                if response.status_code == 404:
                    raise httpx.RequestError(f"Endpoint not found: {base_url}", request=response.request)  # 转换为请求错误

                response.raise_for_status()  # 对其他 4xx/5xx 状态码抛出异常
                return schemas.McpStatusResponse(
                    status="success",
                    message=f"成功连接到ModelScope推理服务 ({response.status_code}): {base_url}",
                    timestamp=datetime.now()
                )

            # Case 2: 纯 SSE/Streamable HTTP (通用，非特定ModelScope的健康检查)
            elif protocol_type.lower() == "sse" or protocol_type.lower() == "streamable_http":
                # 对于通用SSE，假设存在 /health 端点。
                test_health_url = base_url.rstrip('/') + "/health"
                print(f"DEBUG_MCP: Attempting GET on general SSE health URL: {test_health_url}")
                response = await client.get(test_health_url, headers=headers, timeout=5)
                response.raise_for_status()
                return schemas.McpStatusResponse(
                    status="success",
                    message=f"成功连接到MCP服务 (SSE/Streamable HTTP连通性): {test_health_url}",
                    timestamp=datetime.now()
                )

            # Case 3: 标准 HTTP API (通用 REST API，包括非推理部分的ModelScope，以及LLM API)
            else:  # 默认为 http_rest 或其他通用类型
                test_api_url = base_url.rstrip('/')
                # 对于通用 ModelScope API (非推理服务)，或当 base_url 仅为域名时
                # 尝试访问其 /api/v1/models 或类似的通用发现端点。
                # 如果 base_url 已经包含如 /api/v1 等路径，则不重复追加。
                if ("modelscope.cn" in base_url.lower() or "modelscope.net" in base_url.lower()) and \
                        not any(suffix in base_url.lower() for suffix in
                                ["/sse", "/api/v1/inference", "/v1/models", "/health", "/status"]):
                    test_api_url = base_url.rstrip('/') + "/api/v1/models"  # 常见 ModelScope 通用 API 路径
                elif not base_url.lower().endswith("health") and not base_url.lower().endswith("status"):
                    # 对于其他通用自定义 HTTP API，如果没有明确指定健康检查路径，假设为 /health。
                    test_api_url = base_url.rstrip('/') + "/health"

                print(f"DEBUG_MCP: Attempting GET on standard HTTP API URL: {test_api_url}")
                # 使用标准的 GET 请求
                response = await client.get(test_api_url, headers=headers, timeout=5)
                response.raise_for_status()  # 对 4xx/5xx 状态码抛出异常
                return schemas.McpStatusResponse(
                    status="success",
                    message=f"成功连接到MCP服务: {test_api_url}",
                    timestamp=datetime.now()
                )

        except httpx.TimeoutException:
            print(f"ERROR_MCP: 连接MCP服务超时: {base_url}")
            return schemas.McpStatusResponse(
                status="timeout",
                message=f"连接MCP服务超时: {base_url}",
                timestamp=datetime.now()
            )
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            print(f"ERROR_MCP: 连接MCP服务失败 (HTTP {status_code}): {e}")
            return schemas.McpStatusResponse(
                status="failure",
                message=f"连接MCP服务失败 (HTTP {status_code})",
                timestamp=datetime.now()
            )
        except httpx.RequestError as e:
            print(f"ERROR_MCP: 连接MCP服务请求错误: {e}")
            return schemas.McpStatusResponse(
                status="failure",
                message=f"连接MCP服务请求错误",
                timestamp=datetime.now()
            )
        except Exception as e:
            print(f"ERROR_MCP: 检查MCP服务时发生未知错误: {e}")
            return schemas.McpStatusResponse(
                status="failure",
                message=f"内部错误，无法检查MCP服务",
                timestamp=datetime.now()
            )

# --- MCP服务配置管理接口 ---
@router.post("/", response_model=schemas.UserMcpConfigResponse, summary="创建新的MCP配置")
async def create_mcp_config(
        config_data: schemas.UserMcpConfigCreate,
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建MCP配置: {config_data.name}")

    encrypted_key = None
    if config_data.api_key:
        encrypted_key = encrypt_key(config_data.api_key)

    # 检查是否已存在同名且活跃的配置，避免用户创建重复的配置
    existing_config = db.query(UserMcpConfig).filter(
        UserMcpConfig.owner_id == current_user_id,
        UserMcpConfig.name == config_data.name,
        UserMcpConfig.is_active == True  # 只检查活跃的配置是否有重名
    ).first()

    if existing_config:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="已存在同名且活跃的MCP配置。请选择其他名称或停用旧配置。")

    # 创建数据库记录
    db_config = UserMcpConfig(
        owner_id=current_user_id,  # 设置拥有者为当前用户
        name=config_data.name,
        mcp_type=config_data.mcp_type,
        base_url=config_data.base_url,
        protocol_type=config_data.protocol_type,
        api_key_encrypted=encrypted_key,
        is_active=config_data.is_active,
        description=config_data.description
    )

    db.add(db_config)
    db.commit()  # 提交事务
    db.refresh(db_config)  # 刷新以获取数据库生成的ID和时间戳

    # 确保不返回明文 API 密钥，使用字典构造确保安全
    response_dict = {
        'id': db_config.id,
        'owner_id': db_config.owner_id,
        'name': db_config.name,
        'mcp_type': db_config.mcp_type,
        'base_url': db_config.base_url,
        'protocol_type': db_config.protocol_type,
        'is_active': db_config.is_active,
        'description': db_config.description,
        'created_at': db_config.created_at or datetime.now(),
        'updated_at': db_config.updated_at or db_config.created_at or datetime.now(),
        'api_key_encrypted': None  # 明确设置为None
    }

    print(f"DEBUG: 用户 {current_user_id} 的MCP配置 '{db_config.name}' (ID: {db_config.id}) 创建成功。")
    return schemas.UserMcpConfigResponse(**response_dict)

@router.get("/", response_model=List[schemas.UserMcpConfigResponse], summary="获取当前用户所有MCP服务配置")
async def get_all_mcp_configs(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        is_active: Optional[bool] = None  # 过滤条件：只获取启用或禁用的配置
):
    """
    获取当前用户配置的所有MCP服务。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的MCP配置列表。")
    query = db.query(UserMcpConfig).filter(UserMcpConfig.owner_id == current_user_id)
    if is_active is not None:
        query = query.filter(UserMcpConfig.is_active == is_active)

    configs = query.order_by(UserMcpConfig.created_at.desc()).all()

    # 安全处理：确保不返回任何敏感信息
    result_configs = []
    for config in configs:
        config_dict = {
            'id': config.id,
            'owner_id': config.owner_id,
            'name': config.name,
            'mcp_type': config.mcp_type,
            'base_url': config.base_url,
            'protocol_type': config.protocol_type,
            'is_active': config.is_active,
            'description': config.description,
            'created_at': config.created_at or datetime.now(),
            'updated_at': config.updated_at or config.created_at or datetime.now(),
            'api_key_encrypted': None  # 明确设置为None，确保不泄露
        }
        result_configs.append(schemas.UserMcpConfigResponse(**config_dict))

    print(f"DEBUG: 获取到 {len(result_configs)} 条MCP配置。")
    return result_configs

# 用户MCP配置接口部分
@router.put("/{config_id}", response_model=schemas.UserMcpConfigResponse, summary="更新指定MCP配置")
async def update_mcp_config(
        config_id: int,  # 从路径中获取配置ID
        config_data: schemas.UserMcpConfigBase,  # 用于更新的数据
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 更新MCP配置 ID: {config_id}。")
    # 核心权限检查：根据配置ID和拥有者ID来检索，确保操作的是当前用户的配置
    db_config = db.query(UserMcpConfig).filter(
        UserMcpConfig.id == config_id,
        UserMcpConfig.owner_id == current_user_id  # 确保当前用户是该配置的拥有者
    ).first()

    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP配置未找到或无权访问")

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
        # del update_data["api_key"]
        # 在使用 setattr 循环时，这里删除 api_key，避免将其明文赋给 ORM 对象的其他字段

    # 检查名称冲突 (如果名称在更新中改变了)
    if "name" in update_data and update_data["name"] != db_config.name:
        # 查找当前用户下是否已存在与新名称相同的活跃配置
        existing_config_with_new_name = db.query(UserMcpConfig).filter(
            UserMcpConfig.owner_id == current_user_id,
            UserMcpConfig.name == update_data["name"],
            UserMcpConfig.is_active == True,  # 只检查活跃的配置
            UserMcpConfig.id != config_id  # **排除当前正在更新的配置本身**
        ).first()
        if existing_config_with_new_name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="新配置名称已存在于您的活跃配置中。")

    # 应用其他更新：通过循环处理所有可能更新的字段，更简洁和全面
    fields_to_update = ["name", "mcp_type", "base_url", "protocol_type", "is_active", "description"]
    for field in fields_to_update:
        if field in update_data:  # 只有当传入的数据包含这个字段时才更新
            setattr(db_config, field, update_data[field])

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    # 安全处理：确保敏感的API密钥不会返回给客户端，使用字典构造
    response_dict = {
        'id': db_config.id,
        'owner_id': db_config.owner_id,
        'name': db_config.name,
        'mcp_type': db_config.mcp_type,
        'base_url': db_config.base_url,
        'protocol_type': db_config.protocol_type,
        'is_active': db_config.is_active,
        'description': db_config.description,
        'created_at': db_config.created_at or datetime.now(),
        'updated_at': db_config.updated_at or datetime.now(),
        'api_key_encrypted': None  # 明确设置为None
    }

    print(f"DEBUG: MCP配置 {db_config.id} 更新成功。")
    return schemas.UserMcpConfigResponse(**response_dict)

@router.delete("/{config_id}", summary="删除指定MCP服务配置")
async def delete_mcp_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的MCP服务配置。用户只能删除自己的配置。
    """
    print(f"DEBUG: 删除MCP配置 ID: {config_id}。")
    db_config = db.query(UserMcpConfig).filter(UserMcpConfig.id == config_id,
                                               UserMcpConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP config not found or not authorized")

    db.delete(db_config)
    db.commit()
    print(f"DEBUG: MCP配置 {config_id} 删除成功。")
    return {"message": "MCP config deleted successfully"}

@router.post("/{config_id}/check-status", response_model=schemas.McpStatusResponse,
          summary="检查指定MCP服务的连通性")
async def check_mcp_config_status(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    检查指定ID的MCP服务配置的API连通性。
    """
    print(f"DEBUG: 检查MCP配置 ID: {config_id} 的连通性。")
    db_config = db.query(UserMcpConfig).filter(UserMcpConfig.id == config_id,
                                               UserMcpConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP config not found or not authorized")

    decrypted_key = None
    if db_config.api_key_encrypted:
        try:
            decrypted_key = decrypt_key(db_config.api_key_encrypted)
        except Exception as e:
            return schemas.McpStatusResponse(
                status="failure",
                message=f"无法解密API密钥，请检查密钥是否正确或重新配置。错误: {e}",
                service_name=db_config.name,
                config_id=config_id,
                timestamp=datetime.now()
            )

    status_response = await check_mcp_api_connectivity(db_config.base_url, db_config.protocol_type,
                                                       decrypted_key)  # 传递协议类型
    status_response.service_name = db_config.name
    status_response.config_id = config_id

    print(f"DEBUG: MCP配置 {config_id} 连通性检查结果: {status_response.status}")
    return status_response