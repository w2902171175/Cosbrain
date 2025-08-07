# project/main.py
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal  # 导入 Literal 用于固定选项
import numpy as np
import requests
import json
import os
from datetime import datetime
from sqlalchemy.sql import func
import uuid
import asyncio

# 密码哈希
from passlib.context import CryptContext

# 导入数据库和模型
from database import SessionLocal, engine, init_db, get_db
from models import Student, Project, Note, KnowledgeBase, KnowledgeArticle, Course, UserCourse, CollectionItem, DailyRecord, Folder, CollectedContent,ChatRoom, ChatMessage, ForumTopic, ForumComment, ForumLike, UserFollow,UserMcpConfig, UserSearchEngineConfig, KnowledgeDocument, KnowledgeDocumentChunk
# 导入Pydantic Schemas
import schemas

# 导入重构后的 ai_core 模块
import ai_core

# --- FastAPI 应用实例 ---
app = FastAPI(
    title="鸿庆书云创新协作平台后端API",
    description="为学生提供智能匹配、知识管理、课程学习和协作支持的综合平台。",
    version="0.1.0",
)


# --- 密码哈希上下文 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# --- 认证依赖 (简化版，未来替换为JWT) ---
async def get_current_user_id(db: Session = Depends(get_db)):
    # ！！！请确保这里的 user_id 是你希望测试的用户的实际ID！！！
    user_id = 1  # 例如，你之前注册的“创想小助手”的ID
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated or user not found (Hardcoded ID used for testing)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


# --- WebSocket 连接管理：为每个聊天室分配一个管理器 ---
class ConnectionManager:
    def __init__(self):
        # 键是 room_id，值是该房间内 {user_id: WebSocket} 的字典
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user_id: int):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = {}
        self.active_connections[room_id][user_id] = websocket
        print(f"DEBUG_WS: 用户 {user_id} 加入房间 {room_id}。当前房间连接数: {len(self.active_connections[room_id])}")

    def disconnect(self, room_id: int, user_id: int):
        if room_id in self.active_connections and user_id in self.active_connections[room_id]:
            del self.active_connections[room_id][user_id]
            if not self.active_connections[room_id]: # 如果房间空了，移除房间入口
                del self.active_connections[room_id]
            print(f"DEBUG_WS: 用户 {user_id} 离开房间 {room_id}。当前房间连接数: {len(self.active_connections.get(room_id, {}))}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str, room_id: int):
        if room_id in self.active_connections:
            for user_id, connection in self.active_connections[room_id].items():
                try:
                    await connection.send_text(message)
                except RuntimeError as e:
                    print(f"WARNING_WS: 无法向用户 {user_id} (房间 {room_id}) 发送消息: {e}. 可能连接已关闭。")
                except Exception as e:
                    print(f"ERROR_WS: 广播消息时发生未知错误: {e}")

manager = ConnectionManager() # 创建一个全局的连接管理器实例


# --- CORS 中间件 (跨域资源共享) ---
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
    # ... 添加前端域名和端口
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 辅助函数：检查MCP服务连通性 (可以根据MCP实际API调整) ---
async def check_mcp_api_connectivity(base_url: str, protocol_type: str,
                                     api_key: Optional[str] = None) -> schemas.McpStatusResponse:
    """
    尝试ping MCP服务的健康检查端点或一个简单的公共API。
    此处为简化模拟，实际应根据MCP的具体API文档实现。
    """
    print(f"DEBUG_MCP: Checking connectivity for {base_url} with protocol {protocol_type}")

    test_url = base_url.rstrip('/')
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # 模拟不同的协议连通性检查
    if protocol_type.lower() == "sse" or protocol_type.lower() == "streamable_http":
        # 对于 SEE/Streamable HTTP，可能没有简单的GET端点返回JSON
        # 我们只能模拟一个成功的连接尝试或ping
        try:
            # 尝试一个HEAD请求或小范围GET请求，看是否能建立连接
            # 对于SEE，通常是客户端监听，简单的GET请求可能直接挂起
            # 这里我们假设一个 /health 或 /status 端点存在
            test_health_url = base_url.rstrip('/') + "/health"  # 假设模型服务有健康检查端口
            # 对于魔搭社区这类，通常是GET base_url本身，或者 /v1/models /v1/ping 等
            # 具体 ModelScope SEE 服务的 API 连通性检查方式，需要查阅其文档
            # 这里简化为尝试HTTP GET
            response = requests.get(test_health_url, headers=headers, stream=True, timeout=5)  # 用stream=True防止阻塞
            response.raise_for_status()
            return schemas.McpStatusResponse(
                status="success",
                message=f"成功连接到MCP服务 (模拟SSE/Streamable HTTP连通性)：{base_url}",
                timestamp=datetime.now()
            )
        except requests.exceptions.Timeout:
            return schemas.McpStatusResponse(
                status="timeout",
                message=f"连接MCP服务超时 (SSE/Streamable HTTP): {base_url}",
                timestamp=datetime.now()
            )
        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, 'status_code', 'N/A')
            return schemas.McpStatusResponse(
                status="failure",
                message=f"连接MCP服务失败 (SSE/Streamable HTTP, {status_code}): {e}",
                timestamp=datetime.now()
            )
        except Exception as e:
            return schemas.McpStatusResponse(
                status="failure",
                message=f"内部错误，无法检查MCP服务 (SSE/Streamable HTTP)：{e}",
                timestamp=datetime.now()
            )
    else:  # 默认为传统的HTTP API (包括LLM API类型)
        # 例如 ModelScope 的公共接口通常是 /api/vX 或 /v1/models
        # 对魔搭社区的通用服务，可以尝试访问其 models 列表
        test_api_url = base_url.rstrip('/') + '/v1/models'  # 尝试访问一个通用models列表接口
        # 例子： https://mcp.api-inference.modelscope.net/00bcc54bf7fb49/sse
        # 对于这种特定服务，可能没有统一的 /v1/models 接口，连通性可能需要直接调用服务的特定API
        # 这里为了演示，我们先假设 /v1/models 存在
        if "modelscope" in base_url.lower():  # 特别处理modelscope的通用api
            test_api_url = base_url.rstrip('/') + "/api/v1/models"  # 或者/v1/inference 一般需要看文档

        try:
            response = requests.get(test_api_url, headers=headers, timeout=5)
            response.raise_for_status()
            return schemas.McpStatusResponse(
                status="success",
                message=f"成功连接到MCP服务：{base_url}",
                timestamp=datetime.now()
            )
        except requests.exceptions.Timeout:
            return schemas.McpStatusResponse(
                status="timeout",
                message=f"连接MCP服务超时：{base_url}",
                timestamp=datetime.now()
            )
        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, 'status_code', 'N/A')
            return schemas.McpStatusResponse(
                status="failure",
                message=f"连接MCP服务失败 ({status_code}): {e}. 请检查URL或API密钥。",
                timestamp=datetime.now()
            )
        except Exception as e:
            return schemas.McpStatusResponse(
                status="failure",
                message=f"内部错误，无法检查MCP服务：{e}",
                timestamp=datetime.now()
            )


# --- 辅助函数：检查搜索引擎服务连通性 ---
async def check_search_engine_connectivity(engine_type: str, api_key: str,
                                           base_url: Optional[str] = None) -> schemas.SearchEngineStatusResponse:
    """
    尝试检查搜索引擎API的连通性。
    此处为简化模拟，实际应根据搜索引擎的API文档实现。
    """
    print(f"DEBUG_SEARCH: Checking connectivity for {engine_type} search engine.")

    # 模拟一个简单的查询，例如 "test"
    test_query = "test"

    try:
        # 复用 ai_core 中的搜索逻辑进行测试
        await ai_core.call_web_search_api(test_query, engine_type, api_key, base_url)
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
    except Exception as e:
        return schemas.SearchEngineStatusResponse(
            status="failure",
            message=f"无法检查 {engine_type} 搜索引擎连通性: {e}",
            timestamp=datetime.now()
        )


# --- 搜索引擎配置管理接口 ---
@app.post("/search-engine-configs/", response_model=schemas.UserSearchEngineConfigResponse,
          summary="添加新的搜索引擎配置")
async def create_search_engine_config(
        config_data: schemas.UserSearchEngineConfigCreate,
        current_user_id: int = Depends(get_current_user_id),  # 配置所属用户
        db: Session = Depends(get_db)
):
    """
    为当前用户添加一个新的搜索引擎配置（例如Bing, Tavily等）。
    如果提供了API密钥，将加密存储。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试添加搜索引擎配置: {config_data.name}")

    if config_data.api_key:
        encrypted_key = ai_core.encrypt_key(config_data.api_key)
    else:
        encrypted_key = None

    db_config = UserSearchEngineConfig(
        owner_id=current_user_id,
        name=config_data.name,
        engine_type=config_data.engine_type,
        api_key_encrypted=encrypted_key,
        is_active=config_data.is_active,
        description=config_data.description
        # base_url 字段从 schemas.UserSearchEngineConfigCreate 中移除，因为它不是所有搜索引擎的通用字段，
        # 且通常由 ai_core 内部管理默认值。如果需要自定义，可以在 description 或其他字段说明。
    )

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    db_config.api_key = None  # 不返回密钥

    print(f"DEBUG: 搜索引擎配置 '{db_config.name}' (ID: {db_config.id}) 添加成功。")
    return db_config


@app.get("/search-engine-configs/", response_model=List[schemas.UserSearchEngineConfigResponse],
         summary="获取当前用户所有搜索引擎配置")
async def get_all_search_engine_configs(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        is_active: Optional[bool] = None  # 过滤条件：只获取启用或禁用的配置
):
    """
    获取当前用户配置的所有搜索引擎。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的搜索引擎配置列表。")
    query = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.owner_id == current_user_id)
    if is_active is not None:
        query = query.filter(UserSearchEngineConfig.is_active == is_active)

    configs = query.order_by(UserSearchEngineConfig.created_at.desc()).all()
    for config in configs:
        config.api_key = None  # 不返回密钥
    print(f"DEBUG: 获取到 {len(configs)} 条搜索引擎配置。")
    return configs


@app.get("/search-engine-configs/{config_id}", response_model=schemas.UserSearchEngineConfigResponse,
         summary="获取指定搜索引擎配置详情")
async def get_search_engine_config_by_id(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的搜索引擎配置详情。用户只能获取自己的配置。
    """
    print(f"DEBUG: 获取搜索引擎配置 ID: {config_id} 的详情。")
    config = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.id == config_id,
                                                     UserSearchEngineConfig.owner_id == current_user_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Search engine config not found or not authorized")

    config.api_key = None  # 不返回密钥
    return config


@app.put("/search-engine-configs/{config_id}", response_model=schemas.UserSearchEngineConfigResponse,
         summary="更新指定搜索引擎配置")
async def update_search_engine_config(
        config_id: int,
        config_data: schemas.UserSearchEngineConfigBase,  # 注意这里使用BaseModel，所有字段可选
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的搜索引擎配置。用户只能更新自己的配置。
    如果提供了API密钥，将加密存储。
    """
    print(f"DEBUG: 更新搜索引擎配置 ID: {config_id}。")
    db_config = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.id == config_id,
                                                        UserSearchEngineConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Search engine config not found or not authorized")

    update_data = config_data.dict(exclude_unset=True)

    if "name" in update_data:
        db_config.name = update_data["name"]
    if "engine_type" in update_data:
        db_config.engine_type = update_data["engine_type"]
    if "is_active" in update_data:
        db_config.is_active = update_data["is_active"]
    if "description" in update_data:
        db_config.description = update_data["description"]

    if "api_key" in update_data and update_data["api_key"] is not None:
        encrypted_key = ai_core.encrypt_key(update_data["api_key"])
        db_config.api_key_encrypted = encrypted_key
        print(f"DEBUG: 搜索引擎配置 {config_id} 的API密钥已加密存储。")
    elif "api_key" in update_data and update_data["api_key"] is None:
        db_config.api_key_encrypted = None

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    db_config.api_key = None
    print(f"DEBUG: 搜索引擎配置 {db_config.id} 更新成功。")
    return db_config


@app.delete("/search-engine-configs/{config_id}", summary="删除指定搜索引擎配置")
async def delete_search_engine_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的搜索引擎配置。用户只能删除自己的配置。
    """
    print(f"DEBUG: 删除搜索引擎配置 ID: {config_id}。")
    db_config = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.id == config_id,
                                                        UserSearchEngineConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Search engine config not found or not authorized")

    db.delete(db_config)
    db.commit()
    print(f"DEBUG: 搜索引擎配置 {config_id} 删除成功。")
    return {"message": "Search engine config deleted successfully"}


@app.post("/search-engine-configs/{config_id}/check-status", response_model=schemas.SearchEngineStatusResponse,
          summary="检查指定搜索引擎的连通性")
async def check_search_engine_config_status(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    检查指定ID的搜索引擎配置的API连通性。
    """
    print(f"DEBUG: 检查搜索引擎配置 ID: {config_id} 的连通性。")
    db_config = db.query(UserSearchEngineConfig).filter(UserSearchEngineConfig.id == config_id,
                                                        UserSearchEngineConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Search engine config not found or not authorized")

    decrypted_key = None
    if db_config.api_key_encrypted:
        try:
            decrypted_key = ai_core.decrypt_key(db_config.api_key_encrypted)
        except Exception as e:
            return schemas.SearchEngineStatusResponse(
                status="failure",
                message=f"无法解密API密钥，请检查密钥是否正确或重新配置。错误: {e}",
                engine_name=db_config.name,
                config_id=config_id
            )

    # 调用辅助函数进行实际连通性检查
    status_response = await check_search_engine_connectivity(db_config.engine_type, decrypted_key,
                                                             getattr(db_config, 'base_url', None))
    status_response.engine_name = db_config.name
    status_response.config_id = config_id

    print(f"DEBUG: 搜索引擎配置 {config_id} 连通性检查结果: {status_response.status}")
    return status_response


# --- 通用的网络搜索 API ---
@app.post("/ai/web-search", response_model=schemas.WebSearchResponse, summary="执行一次网络搜索")
async def perform_web_search(
        search_request: schemas.WebSearchRequest,  # 定义新的request schema
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    使用用户配置的搜索引擎执行网络搜索。
    可以指定使用的搜索引擎配置ID。
    """
    print(f"DEBUG: 用户 {current_user_id} 执行网络搜索：'{search_request.query}'。")

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
            decrypted_key = ai_core.decrypt_key(db_config.api_key_encrypted)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="无法解密API密钥，请检查配置。")

    start_time = datetime.now()
    try:
        # 调用 ai_core 中的实际搜索逻辑
        # Note: getattr(db_config, 'base_url', None) 确保即使模型没有此属性也不会报错
        results = await ai_core.call_web_search_api(
            search_request.query,
            db_config.engine_type,
            decrypted_key,
            getattr(db_config, 'base_url', None)  # 传递 base_url
        )
        search_time = (datetime.now() - start_time).total_seconds()

        print(f"DEBUG: 网络搜索完成，使用 '{db_config.name}' ({db_config.engine_type})，找到 {len(results)} 条结果。")
        return schemas.WebSearchResponse(
            query=search_request.query,
            engine_used=db_config.name,
            results=results,
            total_results=len(results),
            search_time=round(search_time, 2)
        )
    except Exception as e:
        print(f"ERROR: 网络搜索请求失败: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"网络搜索服务调用失败: {e}")


# --- 语言服务 - 文本转语音 (TTS) 接口 ---
@app.post("/audio/tts", summary="将文本转换为语音")
async def text_to_speech(
        tts_request: schemas.TTSTextRequest,
        current_user_id: int = Depends(get_current_user_id),  # 仅用于权限检查，确保登录
) -> Dict[str, str]:
    """
    将提供的文本转换为语音文件，并返回可访问的MP3文件URL。
    支持 'zh-CN' (中文), 'en' (英文) 等 gTTS 支持的语言代码。
    """
    print(f"DEBUG: 用户 {current_user_id} 请求将文本转换为语音。")
    try:
        # 调用 ai_core 中的 TTS 核心逻辑
        # ai_core.synthesize_speech 返回的是文件系统路径
        filepath = await ai_core.synthesize_speech(tts_request.text,
                                                   lang=tts_request.lang)  # <-- **修改这里，使用 tts_request.text 和 tts_request.lang**

        # 将文件系统路径转换为可访问的HTTP URL
        audio_url = f"/audio/{os.path.basename(filepath)}"

        print(f"DEBUG: TTS 转换成功，音频URL: {audio_url}")
        return {"audio_url": audio_url}
    except Exception as e:
        print(f"ERROR: TTS 转换失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文本转语音失败: {e}")




# --- 健康检查接口 ---
@app.get("/health", summary="健康检查", response_description="返回API服务状态")
def health_check():
    """检查API服务是否正常运行。"""
    return {"status": "ok", "message": "鸿庆书云创新协作平台后端API运行正常！"}


# --- 异步处理文档的辅助函数 ---
async def process_document_in_background(
        document_id: int,
        owner_id: int,
        kb_id: int,
        filepath: str,
        file_type: str,
        db_session: Session  # 传入会话
):
    """
    在后台处理上传的文档：提取文本、分块、生成嵌入并存储。
    """
    print(f"DEBUG_DOC_PROCESS: 开始后台处理文档 ID: {document_id}")
    loop = asyncio.get_running_loop()
    try:
        # 获取文档对象 (需要在新的会话中获取，因为这是独立的任务)
        db_document = db_session.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
        if not db_document:
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 在后台处理中未找到。")
            return

        db_document.status = "processing"
        db_document.processing_message = "正在提取文本..."
        db_session.add(db_document)
        db_session.commit()

        # 1. 提取文本
        extracted_text = await loop.run_in_executor(
            None,  # 使用默认的线程池执行器
            ai_core.extract_text_from_document,  # 要执行的同步函数
            filepath,  # 传递给函数的第一个参数
            file_type  # 传递给函数的第二个参数
        )

        if not extracted_text:
            db_document.status = "failed"
            db_document.processing_message = "文本提取失败或文件内容为空。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 文本提取失败。")
            return

        # 2. 文本分块
        chunks = ai_core.chunk_text(extracted_text)
        if not chunks:
            db_document.status = "failed"
            db_document.processing_message = "文本分块失败，可能文本过短。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 文本分块失败。")
            return

        db_document.processing_message = f"总计 {len(chunks)} 块，正在生成嵌入..."
        db_session.add(db_document)
        db_session.commit()

        # 3. 生成嵌入并存储
        all_embeddings = await loop.run_in_executor(
            None,  # 使用默认的线程池执行器
            ai_core.get_embeddings_from_api,  # 要执行的同步函数
            chunks  # 传递给函数的参数
        )

        if not all_embeddings or len(all_embeddings) != len(chunks):
            db_document.status = "failed"
            db_document.processing_message = "嵌入生成失败或数量不匹配。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 嵌入生成失败。")
            return

        for i, chunk_content in enumerate(chunks):
            db_chunk = KnowledgeDocumentChunk(
                document_id=document_id,
                owner_id=owner_id,
                kb_id=kb_id,
                chunk_index=i,
                content=chunk_content,
                embedding=all_embeddings[i]
            )
            db_session.add(db_chunk)

        db_session.commit()

        # 4. 更新文档状态
        db_document.status = "completed"
        db_document.processing_message = f"文档处理完成，共 {len(chunks)} 个文本块。"
        db_document.total_chunks = len(chunks)
        db_session.add(db_document)
        db_session.commit()
        print(f"DEBUG_DOC_PROCESS: 文档 {document_id} 处理完成，{len(chunks)} 个块已嵌入。")

    except Exception as e:
        print(f"ERROR_DOC_PROCESS: 后台处理文档 {document_id} 发生未预期错误: {e}")
        # 尝试更新文档状态为失败
        try:
            db_document.status = "failed"
            db_document.processing_message = f"处理失败: {e}"
            db_session.add(db_document)
            db_session.commit()
        except Exception as update_e:
            print(f"CRITICAL_ERROR: 无法更新文档 {document_id} 的失败状态: {update_e}")
    finally:
        db_session.close()  # 确保会话关闭



# --- 用户认证与管理接口 ---
@app.post("/auth/register", response_model=schemas.StudentResponse, summary="用户注册")
async def register_user(student_data: schemas.StudentCreate, db: Session = Depends(get_db)):
    """
    新用户注册，邮箱必须唯一，密码会被哈希存储。
    """
    print(f"DEBUG: 尝试注册用户: {student_data.email}")
    db_student = db.query(Student).filter(Student.email == student_data.email).first()
    if db_student:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    hashed_password = get_password_hash(student_data.password)

    new_student = Student(
        email=student_data.email,
        password_hash=hashed_password,
        name=student_data.name,
        major=student_data.major,
        skills=student_data.skills,
        interests=student_data.interests,
        bio=student_data.bio,
        awards_competitions=student_data.awards_competitions,
        academic_achievements=student_data.academic_achievements,
        soft_skills=student_data.soft_skills,
        portfolio_link=student_data.portfolio_link,
        preferred_role=student_data.preferred_role,
        availability=student_data.availability,
        combined_text="",
        embedding=[0.0] * 1024
    )

    db.add(new_student)
    db.commit()
    db.refresh(new_student)
    print(f"DEBUG: 用户 {new_student.email} 注册成功，ID: {new_student.id}")
    return new_student


@app.post("/auth/login", summary="用户登录")
async def login_for_access_token(
        form_data: schemas.UserLogin,
        db: Session = Depends(get_db)
):
    """
    用户登录，验证邮箱和密码。
    """
    print(f"DEBUG: 尝试用户登录: {form_data.email}")
    student = db.query(Student).filter(Student.email == form_data.email).first()
    if not student or not verify_password(form_data.password, student.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    print(f"DEBUG: 用户 {student.email} 登录成功。")
    return {"message": "Login successful", "user_id": student.id}


@app.get("/users/me", response_model=schemas.StudentResponse, summary="获取当前登录用户详情")
async def read_users_me(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    获取当前登录用户的详细信息。
    """
    print(f"DEBUG: 获取当前用户 ID: {current_user_id} 的详情。")
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.put("/users/me", response_model=schemas.StudentResponse, summary="更新当前登录用户详情")
async def update_users_me(
        student_update_data: schemas.StudentBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新当前登录用户的个人信息。
    """
    print(f"DEBUG: 更新用户 ID: {current_user_id} 的信息。")
    db_student = db.query(Student).filter(Student.id == current_user_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = student_update_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_student, key, value)

    db_student.combined_text = (
            (db_student.major or "") + ". " +
            (db_student.skills or "") + ". " +
            (db_student.interests or "") + ". " +
            (db_student.bio or "") + ". " +
            (db_student.awards_competitions or "") + ". " +
            (db_student.academic_achievements or "") + ". " +
            (db_student.soft_skills or "") + ". " +
            (db_student.portfolio_link or "") + ". " +
            (db_student.preferred_role or "") + ". " +
            (db_student.availability or "")
    ).strip()

    if db_student.combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([db_student.combined_text])
            db_student.embedding = new_embedding[0]
            print(f"DEBUG: 用户 {db_student.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新用户 {db_student.id} 嵌入向量失败: {e}")

    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    print(f"DEBUG: 用户 {current_user_id} 信息更新成功。")
    return db_student


# --- 用户LLM配置接口 ---
@app.put("/users/me/llm-config", response_model=schemas.StudentResponse, summary="更新当前用户LLM配置")
async def update_llm_config(
        llm_config_data: schemas.UserLLMConfigUpdate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新当前用户的LLM（大语言模型）API配置，密钥会加密存储（此处为模拟加密）。
    """
    print(f"DEBUG: 更新用户 {current_user_id} 的LLM配置。")
    db_student = db.query(Student).filter(Student.id == current_user_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = llm_config_data.dict(exclude_unset=True)

    if "llm_api_type" in update_data:
        db_student.llm_api_type = update_data["llm_api_type"]

    if "llm_api_base_url" in update_data:
        db_student.llm_api_base_url = update_data["llm_api_base_url"]

    # ！！！新增：保存用户选择的 llm_model_id ！！！
    if "llm_model_id" in update_data:
        db_student.llm_model_id = update_data["llm_model_id"]

    if "llm_api_key" in update_data and update_data["llm_api_key"]:
        encrypted_key = ai_core.encrypt_key(update_data["llm_api_key"])
        db_student.llm_api_key_encrypted = encrypted_key
        print(f"DEBUG: 用户 {current_user_id} 的LLM API密钥已加密存储。")
    elif "llm_api_key" in update_data and not update_data["llm_api_key"]:  # 允许清空密钥
        db_student.llm_api_key_encrypted = None

    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    print(f"DEBUG: 用户 {current_user_id} LLM配置更新成功。")
    return db_student


# --- 获取可用LLM模型配置接口 ---
@app.get("/llm/available-models", summary="获取可配置的LLM服务商及模型列表")
async def get_available_llm_models():
    """
    返回所有支持的LLM服务商类型及其默认模型和可用模型列表。
    """
    print("DEBUG: 获取可用LLM模型列表。")
    return ai_core.get_available_llm_configs()


# --- 学生相关接口  ---
@app.get("/students/", response_model=List[schemas.StudentResponse], summary="获取所有学生列表")
def get_all_students(db: Session = Depends(get_db)):
    students = db.query(Student).all()
    print(f"DEBUG: 获取所有学生列表，共 {len(students)} 名。")
    return students


@app.get("/students/{student_id}", response_model=schemas.StudentResponse, summary="获取指定学生详情")
def get_student_by_id(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")
    print(f"DEBUG: 获取学生 ID: {student_id} 的详情。")
    return student


# --- 项目相关接口  ---
@app.get("/projects/", response_model=List[schemas.ProjectResponse], summary="获取所有项目列表")
def get_all_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    print(f"DEBUG: 获取所有项目列表，共 {len(projects)} 个。")
    return projects


@app.get("/projects/{project_id}", response_model=schemas.ProjectResponse, summary="获取指定项目详情")
def get_project_by_id(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    print(f"DEBUG: 获取项目 ID: {project_id} 的详情。")
    return project


# --- AI匹配接口 ---
@app.get("/recommend/projects/{student_id}", response_model=List[schemas.MatchedProject], summary="为指定学生推荐项目")
async def recommend_projects_for_student(
        student_id: int,
        db: Session = Depends(get_db),
        initial_k: int = ai_core.INITIAL_CANDIDATES_K,
        final_k: int = ai_core.FINAL_TOP_K
):
    print(f"DEBUG_AI: 为学生 {student_id} 推荐项目。")
    try:
        recommendations = await ai_core.find_matching_projects_for_student(db, student_id, initial_k, final_k)
        if not recommendations:
            print(f"DEBUG_AI: 未为学生 {student_id} 找到项目推荐。")
        return recommendations
    except Exception as e:
        print(f"ERROR_AI: 推荐项目失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"项目推荐失败: {e}")


@app.get("/projects/{project_id}/match-students", response_model=List[schemas.MatchedStudent],
         summary="为指定项目推荐学生")
async def match_students_for_project(
        project_id: int,
        db: Session = Depends(get_db),
        initial_k: int = ai_core.INITIAL_CANDIDATES_K,
        final_k: int = ai_core.FINAL_TOP_K
):
    print(f"DEBUG_AI: 为项目 {project_id} 推荐学生。")
    try:
        recommendations = await ai_core.find_matching_students_for_project(db, project_id, initial_k, final_k)
        if not recommendations:
            print(f"DEBUG_AI: 未为项目 {project_id} 找到学生推荐。")
        return recommendations
    except Exception as e:
        print(f"ERROR_AI: 推荐学生失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"学生推荐失败: {e}")


# --- 仪表板（首页个人工作台）相关接口 ---
@app.get("/dashboard/summary", response_model=schemas.DashboardSummaryResponse, summary="获取首页工作台概览数据")
async def get_dashboard_summary(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取用户 {current_user_id} 的仪表板概览数据。")
    # 项目数量
    total_projects = db.query(Project).count()
    active_projects_count = db.query(Project).filter(Project.project_status == "进行中").count()
    completed_projects_count = db.query(Project).filter(Project.project_status == "已完成").count()

    # 课程数量 (仅统计用户参与的课程，简化处理)
    user_courses = db.query(UserCourse).filter(UserCourse.student_id == current_user_id).all()
    learning_courses_count = len([uc for uc in user_courses if uc.status == "in_progress"])
    completed_courses_count = len([uc for uc in user_courses if uc.status == "completed"])

    # 聊天室和未读消息（简化）
    # 实际需要聊天室模块支持成员关系和消息已读未读状态
    active_chats_count = db.query(ChatRoom).filter(ChatRoom.creator_id == current_user_id).count()  # 假设用户活跃的聊天室是他创建的
    unread_messages_count = 0  # 暂时为0，待实现实时消息和未读计数

    # 简历完成度 (模拟，可根据实际用户资料填写程度计算)
    student = db.query(Student).filter(Student.id == current_user_id).first()
    resume_completion_percentage = 0.0
    if student:
        completed_fields = 0
        total_fields = 10  # 假设 10 个关键字段
        if student.name and student.name != "张三": total_fields += 1  # 如果是默认值，不算完成
        if student.major: completed_fields += 1
        if student.skills: completed_fields += 1
        if student.interests: completed_fields += 1
        if student.bio: completed_fields += 1
        if student.awards_competitions: completed_fields += 1
        if student.academic_achievements: completed_fields += 1
        if student.soft_skills: completed_fields += 1
        if student.portfolio_link: completed_fields += 1
        if student.preferred_role: completed_fields += 1
        if student.availability: completed_fields += 1
        resume_completion_percentage = (completed_fields / total_fields) * 100 if total_fields > 0 else 0

    return schemas.DashboardSummaryResponse(
        active_projects_count=active_projects_count,
        completed_projects_count=completed_projects_count,
        learning_courses_count=learning_courses_count,
        completed_courses_count=completed_courses_count,
        active_chats_count=active_chats_count,
        unread_messages_count=unread_messages_count,
        resume_completion_percentage=round(resume_completion_percentage, 2)
    )


@app.get("/dashboard/projects", response_model=List[schemas.DashboardProjectCard],
         summary="获取当前用户参与的项目卡片列表")
async def get_dashboard_projects(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[str] = None
):
    print(f"DEBUG: 获取用户 {current_user_id} 的仪表板项目列表。")
    # 假设用户参与的项目可以从 Student.projects 关系获取，或者通过 Project 筛选
    # 这里简化为获取所有项目，实际应根据学生匹配到的项目来
    query = db.query(Project)
    if status_filter:
        query = query.filter(Project.project_status == status_filter)

    # 实际项目中，这里需要结合学生与项目的关系表
    # 为了演示，直接返回所有项目
    projects = query.all()

    # 模拟进度，实际可以记录在 StudentProject 或 ProjectTeam 表中
    project_cards = []
    for p in projects:
        project_cards.append(schemas.DashboardProjectCard(
            id=p.id,
            title=p.title,
            progress=np.random.uniform(0.1, 0.9) if p.project_status == "进行中" else (
                1.0 if p.project_status == "已完成" else 0.0)  # 模拟进度
        ))

    return project_cards


@app.get("/dashboard/courses", response_model=List[schemas.DashboardCourseCard],
         summary="获取当前用户学习的课程卡片列表")
async def get_dashboard_courses(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[str] = None
):
    print(f"DEBUG: 获取用户 {current_user_id} 的仪表板课程列表。")
    query = db.query(UserCourse).filter(UserCourse.student_id == current_user_id)

    if status_filter:
        query = query.filter(UserCourse.status == status_filter)

    user_courses = query.all()

    course_cards = []
    for uc in user_courses:
        # 获取 Course 详情
        course = db.query(Course).filter(Course.id == uc.course_id).first()
        if course:
            course_cards.append(schemas.DashboardCourseCard(
                id=course.id,
                title=course.title,
                progress=uc.progress,
                last_accessed=uc.last_accessed
            ))

    return course_cards


# --- 笔记管理接口 ---
@app.post("/notes/", response_model=schemas.NoteResponse, summary="创建新笔记")
async def create_note(
        note_data: schemas.NoteBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建笔记: {note_data.title}")

    # 组合文本用于嵌入
    combined_text = (note_data.title or "") + ". " + (note_data.content or "") + ". " + (note_data.tags or "")

    embedding = [0.0] * 1024  # 默认零向量
    if combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([combined_text])
            embedding = new_embedding[0]
            print(f"DEBUG: 笔记嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成笔记嵌入向量失败: {e}")
            # 不阻止笔记创建，但记录错误

    db_note = Note(
        owner_id=current_user_id,
        title=note_data.title,
        content=note_data.content,
        note_type=note_data.note_type,
        course_id=note_data.course_id,
        tags=note_data.tags,
        combined_text=combined_text,
        embedding=embedding
    )

    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    print(f"DEBUG: 笔记 (ID: {db_note.id}) 创建成功。")
    return db_note


@app.get("/notes/", response_model=List[schemas.NoteResponse], summary="获取当前用户所有笔记")
async def get_all_notes(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        note_type: Optional[str] = None
):
    print(f"DEBUG: 获取用户 {current_user_id} 的所有笔记。")
    query = db.query(Note).filter(Note.owner_id == current_user_id)
    if note_type:
        query = query.filter(Note.note_type == note_type)

    notes = query.order_by(Note.created_at.desc()).all()
    print(f"DEBUG: 获取到 {len(notes)} 条笔记。")
    return notes


@app.get("/notes/{note_id}", response_model=schemas.NoteResponse, summary="获取指定笔记详情")
async def get_note_by_id(
        note_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取笔记 ID: {note_id} 的详情。")
    note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")
    return note


@app.put("/notes/{note_id}", response_model=schemas.NoteResponse, summary="更新指定笔记")
async def update_note(
        note_id: int,
        note_data: schemas.NoteBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 更新笔记 ID: {note_id}。")
    db_note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not db_note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")

    update_data = note_data.dict(exclude_unset=True)  # 只更新传入的字段
    for key, value in update_data.items():
        setattr(db_note, key, value)

    # 重新生成 combined_text
    db_note.combined_text = (db_note.title or "") + ". " + (db_note.content or "") + ". " + (db_note.tags or "")

    if db_note.combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([db_note.combined_text])
            db_note.embedding = new_embedding[0]
            print(f"DEBUG: 笔记 {db_note.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新笔记 {db_note.id} 嵌入向量失败: {e}")

    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    print(f"DEBUG: 笔记 {db_note.id} 更新成功。")
    return db_note


@app.delete("/notes/{note_id}", summary="删除指定笔记")
async def delete_note(
        note_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 删除笔记 ID: {note_id}。")
    db_note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not db_note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")

    db.delete(db_note)
    db.commit()
    print(f"DEBUG: 笔记 {note_id} 删除成功。")
    return {"message": "Note deleted successfully"}


# --- 知识库管理接口 ---
@app.post("/knowledge-bases/", response_model=schemas.KnowledgeBaseResponse, summary="创建新知识库")
async def create_knowledge_base(
        kb_data: schemas.KnowledgeBaseBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建知识库: {kb_data.name}")
    try:
        db_kb = KnowledgeBase(
            owner_id=current_user_id,
            name=kb_data.name,
            description=kb_data.description,
            access_type=kb_data.access_type
        )
        db.add(db_kb)
        db.commit()
        db.refresh(db_kb)  # 刷新 db_kb 对象以加载默认值和生成ID

        # 为了更鲁棒地处理 Pydantic 序列化问题，显式地转换为字典
        # db.refresh(db_kb) 通常已经足够，但如果遇到 Input should be a valid dictionary or object to extract fields from，可以尝试 force_dict
        # force_dict = schemas.KnowledgeBaseResponse.model_validate(db_kb).model_dump(mode='json')
        # print(f"DEBUG: 知识库 '{db_kb.name}' (ID: {db_kb.id}) 创建成功。")
        # return force_dict # 返回字典

        print(f"DEBUG: 知识库 '{db_kb.name}' (ID: {db_kb.id}) 创建成功。")
        # 再次尝试直接返回 ORM 对象，如果 schemas.py 修复得当，这应该是可以的
        return db_kb

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="知识库名称已存在或创建失败。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 数据库会话使用过程中发生异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建知识库失败: {e}")


@app.get("/knowledge-bases/", response_model=List[schemas.KnowledgeBaseResponse], summary="获取当前用户所有知识库")
async def get_all_knowledge_bases(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取用户 {current_user_id} 的所有知识库。")
    knowledge_bases = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == current_user_id).all()
    print(f"DEBUG: 获取到 {len(knowledge_bases)} 个知识库。")
    return knowledge_bases


@app.get("/knowledge-bases/{kb_id}", response_model=schemas.KnowledgeBaseResponse, summary="获取指定知识库详情")
async def get_knowledge_base_by_id(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取知识库 ID: {kb_id} 的详情。")
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问")
    return knowledge_base


@app.put("/knowledge-bases/{kb_id}", response_model=schemas.KnowledgeBaseResponse, summary="更新指定知识库")
async def update_knowledge_base(
        kb_id: int,
        kb_data: schemas.KnowledgeBaseBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 更新知识库 ID: {kb_id}。")
    db_kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == current_user_id).first()
    if not db_kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问")

    update_data = kb_data.dict(exclude_unset=True)
    if "name" in update_data and update_data["name"] != db_kb.name:
        # 检查新名称是否已存在 (仅当名称改变时)
        existing_kb = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == current_user_id,
                                                     KnowledgeBase.name == update_data["name"]).first()
        if existing_kb:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="新知识库名称已存在。")

    for key, value in update_data.items():
        setattr(db_kb, key, value)

    db.add(db_kb)
    db.commit()
    db.refresh(db_kb)
    print(f"DEBUG: 知识库 {kb_id} 更新成功。")
    return db_kb


@app.delete("/knowledge-bases/{kb_id}", summary="删除指定知识库")
async def delete_knowledge_base(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 删除知识库 ID: {kb_id}。")
    db_kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == current_user_id).first()
    if not db_kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问")

    db.delete(db_kb)
    db.commit()
    print(f"DEBUG: 知识库 {kb_id} 及其所有文章文档删除成功。")
    return {"message": "Knowledge base and its articles/documents deleted successfully"}


# --- 知识文章管理接口 ---
@app.post("/knowledge-bases/{kb_id}/articles/", response_model=schemas.KnowledgeArticleResponse,
          summary="在指定知识库中创建新文章")
async def create_knowledge_article(
        kb_id: int,
        article_data: schemas.KnowledgeArticleBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试在知识库 {kb_id} 中创建文章: {article_data.title}")
    # 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问")

    # 组合文本用于嵌入
    combined_text = (article_data.title or "") + ". " + (article_data.content or "") + ". " + (article_data.tags or "")

    embedding = [0.0] * 1024  # 默认零向量
    if combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([combined_text])
            embedding = new_embedding[0]
            print(f"DEBUG: 文章嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成文章嵌入向量失败: {e}")

    db_article = KnowledgeArticle(
        kb_id=kb_id,
        author_id=current_user_id,
        title=article_data.title,
        content=article_data.content,
        version=article_data.version,
        tags=article_data.tags,
        combined_text=combined_text,
        embedding=embedding
    )

    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    print(f"DEBUG: 知识文章 (ID: {db_article.id}) 创建成功。")
    return db_article


@app.get("/knowledge-bases/{kb_id}/articles/", response_model=List[schemas.KnowledgeArticleResponse],
         summary="获取指定知识库的所有文章")
async def get_articles_in_knowledge_base(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取知识库 {kb_id} 的文章列表，用户 {current_user_id}。")
    # 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    articles = db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_id == kb_id,
                                                 KnowledgeArticle.author_id == current_user_id).all()
    print(f"DEBUG: 知识库 {kb_id} 获取到 {len(articles)} 篇文章。")
    return articles


@app.get("/articles/{article_id}", response_model=schemas.KnowledgeArticleResponse, summary="获取指定文章详情")
async def get_knowledge_article_by_id(
        article_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取文章 ID: {article_id} 的详情。")
    # 用户只能查看自己知识库下的文章
    article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id,
                                                KnowledgeArticle.author_id == current_user_id).first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章未找到或无权访问")
    return article


@app.put("/articles/{article_id}", response_model=schemas.KnowledgeArticleResponse, summary="更新指定文章")
async def update_knowledge_article(
        article_id: int,
        article_data: schemas.KnowledgeArticleBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 更新文章 ID: {article_id}。")
    db_article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id,
                                                   KnowledgeArticle.author_id == current_user_id).first()
    if not db_article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章未找到或无权访问")

    update_data = article_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_article, key, value)

    # 重新生成 combined_text
    db_article.combined_text = (db_article.title or "") + ". " + (db_article.content or "") + ". " + (
                db_article.tags or "")
    if db_article.combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([db_article.combined_text])
            db_article.embedding = new_embedding[0]
            print(f"DEBUG: 文章 {db_article.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新文章 {db_article.id} 嵌入向量失败: {e}")

    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    print(f"DEBUG: 文章 {db_article.id} 更新成功。")
    return db_article


@app.delete("/articles/{article_id}", summary="删除指定文章")
async def delete_knowledge_article(
        article_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 删除文章 ID: {article_id}。")
    db_article = db.query(KnowledgeArticle).filter(KnowledgeArticle.id == article_id,
                                                   KnowledgeArticle.author_id == current_user_id).first()
    if not db_article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章未找到或无权访问")

    db.delete(db_article)
    db.commit()
    print(f"DEBUG: 文章 {article_id} 删除成功。")
    return {"message": "Knowledge article deleted successfully"}


# --- 知识文档上传和管理接口 (用于智库文件) ---
@app.post("/knowledge-bases/{kb_id}/documents/", response_model=schemas.KnowledgeDocumentResponse,
          status_code=status.HTTP_202_ACCEPTED, summary="上传新知识文档到知识库")
async def upload_knowledge_document(
        kb_id: int,
        file: UploadFile = File(...),  # 接收上传的文件
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    上传一个新文档（PDF, DOCX, TXT）到指定知识库。
    文档内容将在后台异步处理，包括文本提取、分块和嵌入生成。
    """
    print(f"DEBUG_UPLOAD: 用户 {current_user_id} 尝试上传文件 '{file.filename}' 到知识库 {kb_id}。")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    # 2. 保存文件到本地 (使用 ai_core 中的常量)
    file_extension = os.path.splitext(file.filename)[1]  # 获取文件扩展名
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
    file_path = os.path.join(ai_core.UPLOAD_DIRECTORY, unique_filename)

    try:
        with open(file_path, "wb") as f:
            while contents := await file.read(1024 * 1024):  # 分块读取，防止大文件爆内存
                f.write(contents)
        print(f"DEBUG_UPLOAD: 文件 '{file.filename}' 保存到 {file_path}")
    except Exception as e:
        print(f"ERROR_UPLOAD: 保存文件失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件保存失败: {e}")

    # 3. 在数据库中创建初始文档记录 (状态为 processing)
    db_document = KnowledgeDocument(
        kb_id=kb_id,
        owner_id=current_user_id,
        file_name=file.filename,
        file_path=file_path,
        file_type=file.content_type,
        status="processing",
        processing_message="文件已上传，等待处理..."
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    # 4. 异步启动后台处理任务 (传入 db.session 的当前状态)
    # 注意：这里需要创建一个新的Session，因为后台任务是在另一个协程中运行
    from database import SessionLocal  # 假设 SessionLocal 可以在 base.py 导入
    background_db_session = SessionLocal()  # 创建一个新的会话
    asyncio.create_task(
        process_document_in_background(
            db_document.id,
            current_user_id,
            kb_id,
            file_path,
            file.content_type,
            background_db_session  # 传递新会话
        )
    )

    print(f"DEBUG_UPLOAD: 文档 {db_document.id} 已接受上传，后台处理中。")
    return db_document


@app.get("/knowledge-bases/{kb_id}/documents/", response_model=List[schemas.KnowledgeDocumentResponse],
         summary="获取知识库下所有知识文档")
async def get_knowledge_base_documents(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[str] = None  # 根据状态过滤
):
    """
    获取指定知识库下所有知识文档（已上传文件）的列表。
    """
    print(f"DEBUG: 获取知识库 {kb_id} 的文档列表，用户 {current_user_id}。")
    # 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    query = db.query(KnowledgeDocument).filter(KnowledgeDocument.kb_id == kb_id,
                                               KnowledgeDocument.owner_id == current_user_id)

    if status_filter:
        query = query.filter(KnowledgeDocument.status == status_filter)

    documents = query.order_by(KnowledgeDocument.created_at.desc()).all()
    print(f"DEBUG: 知识库 {kb_id} 获取到 {len(documents)} 个文档。")
    return documents


@app.get("/knowledge-bases/{kb_id}/documents/{document_id}", response_model=schemas.KnowledgeDocumentResponse,
         summary="获取指定知识文档详情")
async def get_knowledge_document_detail(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定知识库下指定知识文档的详情。
    """
    print(f"DEBUG: 获取文档 ID: {document_id} 的详情。")
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")
    return document


@app.delete("/knowledge-bases/{kb_id}/documents/{document_id}", summary="删除指定知识文档")
async def delete_knowledge_document(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定知识库下的指定知识文档及其所有文本块和本地文件。
    """
    print(f"DEBUG: 删除文档 ID: {document_id}。")
    db_document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not db_document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    # 删除本地文件
    if os.path.exists(db_document.file_path):
        os.remove(db_document.file_path)
        print(f"DEBUG: 已删除本地文件: {db_document.file_path}")

    # 删除数据库记录（级联删除所有文本块）
    db.delete(db_document)
    db.commit()
    print(f"DEBUG: 文档 {document_id} 及其文本块已从数据库删除。")
    return {"message": "Knowledge document deleted successfully"}


# --- GET 请求获取文档内容 (为了方便调试和检查后台处理结果) ---
@app.get("/knowledge-bases/{kb_id}/documents/{document_id}/content", summary="获取知识文档的原始文本内容 (DEBUG)")
async def get_document_raw_content(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定知识文档的原始文本内容 (用于调试，慎用，因为可能返回大量文本)。
    """
    print(f"DEBUG: 获取文档 ID: {document_id} 的原始内容。")
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    if document.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"文档状态为 '{document.status}'，文本处理尚未完成或失败。")

    # 拼接所有文本块的内容
    chunks = db.query(KnowledgeDocumentChunk).filter(
        KnowledgeDocumentChunk.document_id == document_id
    ).order_by(KnowledgeDocumentChunk.chunk_index).all()

    if not chunks:
        return {"content": "无文本块或文本为空。"}

    full_content = "\n".join([c.content for c in chunks])
    return {"content": full_content}


@app.get("/knowledge-bases/{kb_id}/documents/{document_id}/chunks",
         response_model=List[schemas.KnowledgeDocumentChunkResponse], summary="获取知识文档的文本块列表 (DEBUG)")
async def get_document_chunks(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = 10,
        offset: int = 0
):
    """
    获取指定知识文档的所有文本块列表 (用于调试)。
    """
    print(f"DEBUG: 获取文档 ID: {document_id} 的文本块。")
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    chunks = db.query(KnowledgeDocumentChunk).filter(
        KnowledgeDocumentChunk.document_id == document_id
    ).order_by(KnowledgeDocumentChunk.chunk_index).offset(offset).limit(limit).all()

    return chunks




# --- AI问答与智能搜索接口 ---

# project/main.py

# ... (AI问答与智能搜索接口) ...

@app.post("/ai/qa", response_model=schemas.AIQAResponse, summary="AI智能问答 (通用、RAG或工具调用)")
async def ai_qa(
        qa_request: schemas.AIQARequest,  # 现在使用包含新字段的 AIQARequest
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    使用LLM进行问答。
    - 如果 `use_tools` 为 `False` (默认值)：行为与旧版类似，仅提供通用问答。（此时 `kb_ids`, `note_ids` 不再直接控制 RAG，而是成为 `invoke_agent` 的参数，让智能体决定是否使用 RAG）
    - 如果 `use_tools` 为 `True`: LLM将尝试智能选择并调用工具 (RAG、网络搜索、MCP工具)。
    - `preferred_tools` 可用于引导AI优先使用某些工具。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 提问: {qa_request.query}，使用工具模式: {qa_request.use_tools}，偏好工具: {qa_request.preferred_tools}")

    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未找到。")

    # 获取用户LLM配置
    llm_type = user.llm_api_type
    llm_key_encrypted = user.llm_api_key_encrypted
    llm_base_url = user.llm_api_base_url
    llm_model_id = qa_request.llm_model_id or user.llm_model_id  # 优先使用请求中的模型，其次用户默认配置

    if not llm_type or not llm_key_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="用户未配置LLM API 类型或密钥。请前往用户设置页面配置。")

    try:
        llm_key = ai_core.decrypt_key(llm_key_encrypted)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="无法解密LLM API密钥，请重新配置。")

    final_response_data = {}  # 用于存储 invoke_agent 的结果

    if qa_request.use_tools:
        # 调用智能体，让它自主决策是否使用工具
        print(f"DEBUG: 激活AI智能体模式。")
        try:
            final_response_data = await ai_core.invoke_agent(
                db=db,
                user_id=current_user_id,
                query=qa_request.query,
                llm_api_type=llm_type,
                llm_api_key=llm_key,
                llm_api_base_url=llm_base_url,
                llm_model_id=llm_model_id,
                kb_ids=qa_request.kb_ids,  # 传递给智能体，RAG工具会使用
                note_ids=qa_request.note_ids,  # 传递给智能体，RAG工具会使用
                preferred_tools=qa_request.preferred_tools  # 传递给智能体，引导工具选择
            )
        except Exception as e:
            print(f"ERROR: AI智能体调用失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"AI智能体调用失败: {e}")
    else:
        # 如果不使用工具，直接进行通用问答
        print(f"DEBUG: AI智能体未激活，执行通用问答模式。")
        # 直接调用LLM，不再传入工具，强制它生成纯文本回答
        messages = [{"role": "user", "content": qa_request.query}]
        try:
            llm_response_data = await ai_core.call_llm_api(
                messages,
                llm_type,
                llm_key,
                llm_base_url,
                llm_model_id,
                tools=None,  # 不提供工具
                tool_choice="none"  # 不允许工具调用
            )
            if 'choices' in llm_response_data and llm_response_data['choices'][0]['message'].get('content'):
                final_response_data["answer"] = llm_response_data['choices'][0]['message']['content']
                final_response_data["answer_mode"] = "General_mode"
            else:
                final_response_data["answer"] = "AI未能生成明确答案。请重试或换个问题。"
                final_response_data["answer_mode"] = "Failed_General_mode"

        except Exception as e:
            print(f"ERROR: 通用问答LLM调用失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"通用问答失败: {e}")

        final_response_data["llm_type_used"] = llm_type
        final_response_data["llm_model_used"] = llm_model_id

    # 从 invoke_agent 返回的字典直接构建 AIQAResponse
    return schemas.AIQAResponse(**final_response_data)


@app.post("/search/semantic", response_model=List[schemas.SemanticSearchResult], summary="智能语义搜索")
async def semantic_search(
        search_request: schemas.SemanticSearchRequest,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    通过语义搜索，在用户可访问的项目、课程、知识库文章和笔记中查找相关内容。
    """
    print(f"DEBUG: 用户 {current_user_id} 语义搜索: {search_request.query}，范围: {search_request.item_types}")

    searchable_items = []

    target_types = search_request.item_types if search_request.item_types else ["project", "course",
                                                                                "knowledge_article", "note"]

    if "project" in target_types:
        projects = db.query(Project).all()
        for p in projects:
            if p.embedding is not None:
                searchable_items.append({"obj": p, "type": "project"})

    if "course" in target_types:
        courses = db.query(Course).all()
        for c in courses:
            if c.embedding is not None:
                searchable_items.append({"obj": c, "type": "course"})

    if "knowledge_article" in target_types:
        kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user_id) | (KnowledgeBase.access_type == "public")
        ).all()
        for kb in kbs:
            articles = db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_id == kb.id).all()
            for article in articles:
                if article.embedding is not None:
                    searchable_items.append({"obj": article, "type": "knowledge_article"})

    if "note" in target_types:
        notes = db.query(Note).filter(Note.owner_id == current_user_id).all()
        for note in notes:
            if note.embedding is not None:
                searchable_items.append({"obj": note, "type": "note"})

    if not searchable_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可搜索的内容或指定类型无数据。")

    # 2. 获取查询嵌入
    query_embedding_list = ai_core.get_embeddings_from_api([search_request.query])
    if not query_embedding_list:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="无法生成查询嵌入。")
    query_embedding_np = np.array(query_embedding_list[0]).reshape(1, -1)

    # 3. 粗召回 (Embedding Similarity)
    item_combined_texts = [item['obj'].combined_text for item in searchable_items]
    item_embeddings_np = np.array([item['obj'].embedding for item in searchable_items])

    similarities = ai_core.cosine_similarity(query_embedding_np, item_embeddings_np)[0]

    initial_candidates = []
    for i, sim in enumerate(similarities):
        initial_candidates.append({
            'obj': searchable_items[i]['obj'],
            'type': searchable_items[i]['type'],
            'similarity_stage1': float(sim)
        })
    initial_candidates.sort(key=lambda x: x['similarity_stage1'], reverse=True)
    initial_candidates = initial_candidates[:ai_core.INITIAL_CANDIDATES_K]

    if not initial_candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到与查询相关的初步结果。")

    # 4. 精排 (Reranker)
    rerank_candidate_texts = [c['obj'].combined_text for c in initial_candidates]
    print(f"DEBUG_AI: 正在对 {len(rerank_candidate_texts)} 个候选搜索结果进行重排...")
    rerank_scores = ai_core.get_rerank_scores_from_api(search_request.query, rerank_candidate_texts)

    for i, score in enumerate(rerank_scores):
        initial_candidates[i]['relevance_score'] = float(score)
    initial_candidates.sort(key=lambda x: x['relevance_score'], reverse=True)

    # 5. 格式化最终结果
    final_results = []
    for item in initial_candidates[:search_request.limit]:
        obj = item['obj']
        content_snippet = ""
        if hasattr(obj, 'content') and obj.content:
            content_snippet = obj.content[:150] + "..." if len(obj.content) > 150 else obj.content
        elif hasattr(obj, 'description') and obj.description:
            content_snippet = obj.description[:150] + "..." if len(obj.description) > 150 else obj.description

        final_results.append(schemas.SemanticSearchResult(
            id=obj.id,
            title=obj.title if hasattr(obj, 'title') else obj.name,
            type=item['type'],
            content_snippet=content_snippet,
            relevance_score=item['relevance_score']
        ))

    print(f"DEBUG_AI: 语义搜索完成，返回 {len(final_results)} 个结果。")
    return final_results


# --- 随手记录管理接口 ---
@app.post("/daily-records/", response_model=schemas.DailyRecordResponse, summary="创建新随手记录")
async def create_daily_record(
        record_data: schemas.DailyRecordBase,  # 接收记录内容
        current_user_id: int = Depends(get_current_user_id),  # 记录属于当前用户
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

    embedding = [0.0] * 1024  # 默认零向量
    if combined_text:
        try:
            # 调用AI服务生成嵌入
            new_embedding = ai_core.get_embeddings_from_api([combined_text])
            embedding = new_embedding[0]
            print(f"DEBUG: 随手记录嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成随手记录嵌入向量失败: {e}")
            # 不阻止记录创建，但记录错误

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


@app.get("/daily-records/", response_model=List[schemas.DailyRecordResponse], summary="获取当前用户所有随手记录")
async def get_all_daily_records(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        mood: Optional[str] = None,  # 可选过滤条件
        tag: Optional[str] = None  # 可选标签过滤
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


@app.get("/daily-records/{record_id}", response_model=schemas.DailyRecordResponse, summary="获取指定随手记录详情")
async def get_daily_record_by_id(
        record_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的随手记录详情。用户只能获取自己的记录。
    """
    print(f"DEBUG: 获取随手记录 ID: {record_id} 的详情。")
    record = db.query(DailyRecord).filter(DailyRecord.id == record_id, DailyRecord.owner_id == current_user_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily record not found or not authorized")
    return record


@app.put("/daily-records/{record_id}", response_model=schemas.DailyRecordResponse, summary="更新指定随手记录")
async def update_daily_record(
        record_id: int,
        record_data: schemas.DailyRecordBase,  # 接收部分更新数据
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

    if db_record.combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([db_record.combined_text])
            db_record.embedding = new_embedding[0]
            print(f"DEBUG: 随手记录 {db_record.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新随手记录 {db_record.id} 嵌入向量失败: {e}")

    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    print(f"DEBUG: 随手记录 {db_record.id} 更新成功。")
    return db_record


@app.delete("/daily-records/{record_id}", summary="删除指定随手记录")
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

# --- 文件夹管理接口 ---
@app.post("/folders/", response_model=schemas.FolderResponse, summary="创建新文件夹")
async def create_folder(
        folder_data: schemas.FolderBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一个新文件夹。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试创建文件夹: {folder_data.name}")

    # 验证父文件夹是否存在且属于当前用户 (如果提供了parent_id)
    if folder_data.parent_id:
        parent_folder = db.query(Folder).filter(
            Folder.id == folder_data.parent_id,
            Folder.owner_id == current_user_id
        ).first()
        if not parent_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Parent folder not found or not authorized.")

    db_folder = Folder(
        owner_id=current_user_id,
        name=folder_data.name,
        description=folder_data.description,
        color=folder_data.color,
        icon=folder_data.icon,
        parent_id=folder_data.parent_id,
        order=folder_data.order
    )

    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)

    # 刷新父文件夹的 item_count (这里暂时不做，因为item_count在FolderResponse中是computed property)
    print(f"DEBUG: 文件夹 '{db_folder.name}' (ID: {db_folder.id}) 创建成功。")
    return db_folder


@app.get("/folders/", response_model=List[schemas.FolderResponse], summary="获取当前用户所有文件夹")
async def get_all_folders(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        parent_id: Optional[int] = None  # 过滤条件: 只获取指定父文件夹下的子文件夹
):
    """
    获取当前用户的所有文件夹。
    可以通过 parent_id 过滤，获取特定父文件夹下的子文件夹。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有文件夹，parent_id过滤: {parent_id}")
    query = db.query(Folder).filter(Folder.owner_id == current_user_id)

    if parent_id is not None:  # Note: parent_id can be 0 for root
        query = query.filter(Folder.parent_id == parent_id)
    else:  # If parent_id is not explicitly provided, fetch top-level folders without a parent.
        query = query.filter(Folder.parent_id.is_(None))  # 顶级文件夹 parent_id 为 None

    folders = query.order_by(Folder.order).all()

    # 计算每个文件夹的 item_count (包含的直属 collected_contents 和子文件夹数量)
    for folder in folders:
        folder.item_count = db.query(CollectedContent).filter(
            CollectedContent.owner_id == current_user_id,
            CollectedContent.folder_id == folder.id
        ).count() + db.query(Folder).filter(
            Folder.owner_id == current_user_id,
            Folder.parent_id == folder.id
        ).count()

    print(f"DEBUG: 获取到 {len(folders)} 个文件夹。")
    return folders


@app.get("/folders/{folder_id}", response_model=schemas.FolderResponse, summary="获取指定文件夹详情")
async def get_folder_by_id(
        folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的文件夹详情。用户只能获取自己的文件夹。
    """
    print(f"DEBUG: 获取文件夹 ID: {folder_id} 的详情。")
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == current_user_id).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found or not authorized")

    # 计算当前文件夹的 item_count
    folder.item_count = db.query(CollectedContent).filter(
        CollectedContent.owner_id == current_user_id,
        CollectedContent.folder_id == folder.id
    ).count() + db.query(Folder).filter(
        Folder.owner_id == current_user_id,
        Folder.parent_id == folder.id
    ).count()

    return folder


@app.put("/folders/{folder_id}", response_model=schemas.FolderResponse, summary="更新指定文件夹")
async def update_folder(
        folder_id: int,
        folder_data: schemas.FolderBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的文件夹信息。用户只能更新自己的文件夹。
    """
    print(f"DEBUG: 更新文件夹 ID: {folder_id} 的信息。")
    db_folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == current_user_id).first()
    if not db_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found or not authorized")

    update_data = folder_data.dict(exclude_unset=True)

    # 验证新的父文件夹 (如果parent_id被修改)
    if "parent_id" in update_data and update_data["parent_id"] is not None:
        new_parent_id = update_data["parent_id"]
        # 不能将自己设为父文件夹
        if new_parent_id == folder_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder cannot be its own parent.")
        # 检查新父文件夹是否存在且属于当前用户
        new_parent_folder = db.query(Folder).filter(
            Folder.id == new_parent_id,
            Folder.owner_id == current_user_id
        ).first()
        if not new_parent_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="New parent folder not found or not authorized.")
        # 检查是否会形成循环 (简单检查，深度循环需要递归检测)
        # 这里只是简单的检查，如果需要更严格的循环检测，需要实现一个递归函数
        temp_parent = new_parent_folder
        while temp_parent:
            if temp_parent.id == folder_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Circular parent relationship detected.")
            temp_parent = temp_parent.parent  # 假设关系已经被正确加载

    for key, value in update_data.items():
        setattr(db_folder, key, value)

    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)

    # 重新计算 item_count
    db_folder.item_count = db.query(CollectedContent).filter(
        CollectedContent.owner_id == current_user_id,
        CollectedContent.folder_id == db_folder.id
    ).count() + db.query(Folder).filter(
        Folder.owner_id == current_user_id,
        Folder.parent_id == db_folder.id
    ).count()

    print(f"DEBUG: 文件夹 {db_folder.id} 更新成功。")
    return db_folder


@app.delete("/folders/{folder_id}", summary="删除指定文件夹")
async def delete_folder(
        folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的文件夹及其包含的所有子文件夹和收藏内容。用户只能删除自己的文件夹。
    """
    print(f"DEBUG: 删除文件夹 ID: {folder_id}。")
    db_folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == current_user_id).first()
    if not db_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found or not authorized")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_folder)时自动处理子文件夹和收藏内容
    db.delete(db_folder)
    db.commit()
    print(f"DEBUG: 文件夹 {folder_id} 及其内容删除成功。")
    return {"message": "Folder and its contents deleted successfully"}


# --- 具体收藏内容管理接口 (/collections 作为更友好的路径) ---
@app.post("/collections/", response_model=schemas.CollectedContentResponse, summary="创建新收藏内容")
async def create_collected_content(
        content_data: schemas.CollectedContentBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新收藏内容。
    后端会根据内容生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试创建收藏: {content_data.title}")

    # 验证文件夹是否存在且属于当前用户 (如果提供了folder_id)
    if content_data.folder_id:
        target_folder = db.query(Folder).filter(
            Folder.id == content_data.folder_id,
            Folder.owner_id == current_user_id
        ).first()
        if not target_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Target folder not found or not authorized.")

    # 组合文本用于嵌入
    combined_text = (
            (content_data.title or "") + ". " +
            (content_data.content or "") + ". " +
            (content_data.tags or "") + ". " +
            (content_data.type or "") + ". " +
            (content_data.author or "")
    ).strip()

    embedding = [0.0] * 1024  # 默认零向量
    if combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([combined_text])
            embedding = new_embedding[0]
            print(f"DEBUG: 收藏内容嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成收藏内容嵌入向量失败: {e}")

    db_item = CollectedContent(
        owner_id=current_user_id,
        folder_id=content_data.folder_id,
        title=content_data.title,
        type=content_data.type,
        url=content_data.url,
        content=content_data.content,
        tags=content_data.tags,
        priority=content_data.priority,
        notes=content_data.notes,
        is_starred=content_data.is_starred,
        thumbnail=content_data.thumbnail,
        author=content_data.author,
        duration=content_data.duration,
        file_size=content_data.file_size,
        status=content_data.status,
        combined_text=combined_text,
        embedding=embedding
    )

    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    print(f"DEBUG: 收藏内容 '{db_item.title}' (ID: {db_item.id}) 创建成功。")
    return db_item


@app.get("/collections/", response_model=List[schemas.CollectedContentResponse], summary="获取当前用户所有收藏内容")
async def get_all_collected_contents(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        folder_id: Optional[int] = None,  # 按文件夹过滤，null表示无文件夹（根目录项目）
        type_filter: Optional[str] = None,  # 按类型过滤
        tag_filter: Optional[str] = None,  # 按标签过滤
        is_starred: Optional[bool] = None,  # 只看星标
        status_filter: Optional[str] = None  # 按状态过滤
):
    """
    获取当前用户的所有收藏内容。
    支持通过文件夹ID、类型、标签、星标状态和内容状态进行过滤。
    如果 folder_id 为 None，则返回所有不在任何文件夹中的收藏。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有收藏内容。")
    query = db.query(CollectedContent).filter(CollectedContent.owner_id == current_user_id)

    if folder_id is not None:
        if folder_id == 0:  # 约定：folder_id=0 表示根目录，即 folder_id 为 None
            query = query.filter(CollectedContent.folder_id.is_(None))
        else:
            query = query.filter(CollectedContent.folder_id == folder_id)
    else:  # 默认不传 folder_id，显示所有
        pass

    if type_filter:
        query = query.filter(CollectedContent.type == type_filter)
    if tag_filter:
        query = query.filter(CollectedContent.tags.ilike(f"%{tag_filter}%"))
    if is_starred is not None:
        query = query.filter(CollectedContent.is_starred == is_starred)
    if status_filter:
        query = query.filter(CollectedContent.status == status_filter)

    contents = query.order_by(CollectedContent.created_at.desc()).all()
    print(f"DEBUG: 获取到 {len(contents)} 条收藏内容。")
    return contents


@app.get("/collections/{content_id}", response_model=schemas.CollectedContentResponse, summary="获取指定收藏内容详情")
async def get_collected_content_by_id(
        content_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的收藏内容详情。用户只能获取自己的收藏。
    每次访问会自动增加 access_count。
    """
    print(f"DEBUG: 获取收藏内容 ID: {content_id} 的详情。")
    item = db.query(CollectedContent).filter(CollectedContent.id == content_id,
                                             CollectedContent.owner_id == current_user_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    # 增加访问次数
    item.access_count += 1
    db.add(item)
    db.commit()
    db.refresh(item)

    return item


@app.put("/collections/{content_id}", response_model=schemas.CollectedContentResponse, summary="更新指定收藏内容")
async def update_collected_content(
        content_id: int,
        content_data: schemas.CollectedContentBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的收藏内容。用户只能更新自己的收藏。
    更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新收藏内容 ID: {content_id}。")
    db_item = db.query(CollectedContent).filter(CollectedContent.id == content_id,
                                                CollectedContent.owner_id == current_user_id).first()
    if not db_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    update_data = content_data.dict(exclude_unset=True)

    # 验证新的文件夹 (如果folder_id被修改)
    if "folder_id" in update_data and update_data["folder_id"] is not None:
        new_folder_id = update_data["folder_id"]
        # 如果 new_folder_id 是 0，表示移到根目录，将 folder_id 设为 None
        if new_folder_id == 0:
            setattr(db_item, "folder_id", None)
        else:
            target_folder = db.query(Folder).filter(
                Folder.id == new_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not target_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="Target folder not found or not authorized.")
            setattr(db_item, "folder_id", new_folder_id)
        # 移除 update_data 中的 folder_id，因为它已经手动处理了
        update_data.pop("folder_id")
    elif "folder_id" in update_data and update_data["folder_id"] is None:  # 允许显式设为None
        setattr(db_item, "folder_id", None)
        update_data.pop("folder_id")

    for key, value in update_data.items():
        setattr(db_item, key, value)

    # 重新生成 combined_text
    db_item.combined_text = (
            (db_item.title or "") + ". " +
            (db_item.content or "") + ". " +
            (db_item.tags or "") + ". " +
            (db_item.type or "") + ". " +
            (db_item.author or "")
    ).strip()

    if db_item.combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([db_item.combined_text])
            db_item.embedding = new_embedding[0]
            print(f"DEBUG: 收藏内容 {db_item.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新收藏内容 {db_item.id} 嵌入向量失败: {e}")

    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    print(f"DEBUG: 收藏内容 {db_item.id} 更新成功。")
    return db_item


@app.delete("/collections/{content_id}", summary="删除指定收藏内容")
async def delete_collected_content(
        content_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的收藏内容。用户只能删除自己的收藏。
    """
    print(f"DEBUG: 删除收藏内容 ID: {content_id}。")
    db_item = db.query(CollectedContent).filter(CollectedContent.id == content_id,
                                                CollectedContent.owner_id == current_user_id).first()
    if not db_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    db.delete(db_item)
    db.commit()
    print(f"DEBUG: 收藏内容 {content_id} 删除成功。")
    return {"message": "Collected content deleted successfully"}

# --- 聊天室管理接口 ---
@app.post("/chatrooms/", response_model=schemas.ChatRoomResponse, summary="创建新聊天室")
async def create_chat_room(
        room_data: schemas.ChatRoomCreate,
        current_user_id: int = Depends(get_current_user_id),  # 聊天室创建者为当前用户
        db: Session = Depends(get_db)
):
    """
    创建一个新的聊天室。可以是项目群组、课程群组、私人聊天或普通群组。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试创建聊天室: {room_data.name}")

    if room_data.project_id:
        project = db.query(Project).filter(Project.id == room_data.project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        # 检查项目是否已有关联聊天室
        if project.chat_room:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Project already has an associated chat room.")

    if room_data.course_id:
        course = db.query(Course).filter(Course.id == room_data.course_id).first()
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
        # 检查课程是否已有关联聊天室
        if course.chat_room:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Course already has an associated chat room.")

    db_room = ChatRoom(
        name=room_data.name,
        type=room_data.type,
        project_id=room_data.project_id,
        course_id=room_data.course_id,
        creator_id=current_user_id,
        color=room_data.color
    )

    db.add(db_room)
    db.commit()
    db.refresh(db_room)

    # 对于新创建的聊天室，member_count 等统计信息初始为0
    db_room.members_count = 1  # 至少包含创建者
    db_room.last_message = {"sender": "系统", "content": "聊天室已创建！"}

    print(f"DEBUG: 聊天室 '{db_room.name}' (ID: {db_room.id}) 创建成功。")
    return db_room


@app.get("/chatrooms/", response_model=List[schemas.ChatRoomResponse], summary="获取当前用户所属的所有聊天室")
async def get_all_chat_rooms(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        room_type: Optional[str] = None  # 类型过滤
):
    """
    获取当前用户所属（创建或参与）的所有聊天室列表。
    目前简化为获取用户创建的所有聊天室。
    可以通过 type 过滤（例如：project_group, course_group）。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有聊天室，类型过滤: {room_type}")
    query = db.query(ChatRoom).filter(ChatRoom.creator_id == current_user_id)  # 简化：只获取创建的

    # TODO: 后续需要实现用户与聊天室的多对多关系，以获取用户参与的所有聊天室

    if room_type:
        query = query.filter(ChatRoom.type == room_type)

    rooms = query.order_by(ChatRoom.updated_at.desc()).all()

    # 填充动态统计字段
    for room in rooms:
        # 简化：成员数量为1（创建者），除非有实际的成员管理系统
        room.members_count = 1
        # 获取最后一条消息
        last_msg = db.query(ChatMessage).filter(ChatMessage.room_id == room.id) \
            .order_by(ChatMessage.sent_at.desc()).first()
        if last_msg:
            room.last_message = {
                "sender": db.query(Student).filter(Student.id == last_msg.sender_id).first().name or "未知",
                "content": last_msg.content_text[:50] + "..." if len(
                    last_msg.content_text) > 50 else last_msg.content_text
            }
        else:
            room.last_message = {"sender": "系统", "content": "暂无消息"}
        # 未读消息数和在线状态暂时模拟为0
        room.unread_messages_count = 0
        room.online_members_count = 0

    print(f"DEBUG: 获取到 {len(rooms)} 个聊天室。")
    return rooms


@app.get("/chatrooms/{room_id}", response_model=schemas.ChatRoomResponse, summary="获取指定聊天室详情")
async def get_chat_room_by_id(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 确保用户有权查看（简化为创建者）
        db: Session = Depends(get_db)
):
    """
    获取指定ID的聊天室详情。目前简化为只有创建者才能查看。
    """
    print(f"DEBUG: 获取聊天室 ID: {room_id} 的详情。")
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id, ChatRoom.creator_id == current_user_id).first()  # 简化权限
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found or not authorized")

    # 填充动态统计字段
    room.members_count = 1
    last_msg = db.query(ChatMessage).filter(ChatMessage.room_id == room.id) \
        .order_by(ChatMessage.sent_at.desc()).first()
    if last_msg:
        room.last_message = {
            "sender": db.query(Student).filter(Student.id == last_msg.sender_id).first().name or "未知",
            "content": last_msg.content_text[:50] + "..." if len(last_msg.content_text) > 50 else last_msg.content_text
        }
    else:
        room.last_message = {"sender": "系统", "content": "暂无消息"}
    room.unread_messages_count = 0
    room.online_members_count = 0

    return room


@app.put("/chatrooms/{room_id}", response_model=schemas.ChatRoomResponse, summary="更新指定聊天室")
async def update_chat_room(
        room_id: int,
        room_data: schemas.ChatRoomBase,
        current_user_id: int = Depends(get_current_user_id),  # 只有创建者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的聊天室信息。目前简化为只有创建者能更新。
    """
    print(f"DEBUG: 更新聊天室 ID: {room_id} 的信息。")
    db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id, ChatRoom.creator_id == current_user_id).first()
    if not db_room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found or not authorized")

    update_data = room_data.dict(exclude_unset=True)

    # 验证 project_id / course_id 关联
    if "project_id" in update_data and update_data["project_id"] is not None:
        project = db.query(Project).filter(Project.id == update_data["project_id"]).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        # 检查项目是否已有关联聊天室，或是否是当前聊天室自己
        if project.chat_room and project.chat_room.id != room_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Project already has an associated chat room.")

    if "course_id" in update_data and update_data["course_id"] is not None:
        course = db.query(Course).filter(Course.id == update_data["course_id"]).first()
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
        # 检查课程是否已有关联聊天室，或是否是当前聊天室自己
        if course.chat_room and course.chat_room.id != room_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Course already has an associated chat room.")

    for key, value in update_data.items():
        setattr(db_room, key, value)

    db.add(db_room)
    db.commit()
    db.refresh(db_room)

    # 刷新动态统计字段
    db_room.members_count = 1
    last_msg = db.query(ChatMessage).filter(ChatMessage.room_id == db_room.id) \
        .order_by(ChatMessage.sent_at.desc()).first()
    if last_msg:
        db_room.last_message = {
            "sender": db.query(Student).filter(Student.id == last_msg.sender_id).first().name or "未知",
            "content": last_msg.content_text[:50] + "..." if len(last_msg.content_text) > 50 else last_msg.content_text
        }
    else:
        db_room.last_message = {"sender": "系统", "content": "暂无消息"}
    db_room.unread_messages_count = 0
    db_room.online_members_count = 0

    print(f"DEBUG: 聊天室 {db_room.id} 更新成功。")
    return db_room


@app.delete("/chatrooms/{room_id}", summary="删除指定聊天室")
async def delete_chat_room(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 只有创建者能删除
        db: Session = Depends(get_db)
):
    """
    删除指定ID的聊天室及其所有消息。目前简化为只有创建者能删除。
    """
    print(f"DEBUG: 删除聊天室 ID: {room_id}。")
    db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id, ChatRoom.creator_id == current_user_id).first()
    if not db_room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found or not authorized")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_room)时自动处理所有消息
    db.delete(db_room)
    db.commit()
    print(f"DEBUG: 聊天室 {room_id} 及其消息删除成功。")
    return {"message": "Chat room and messages deleted successfully"}


# --- 聊天消息管理接口 ---
@app.post("/chatrooms/{room_id}/messages/", response_model=schemas.ChatMessageResponse,
          summary="在指定聊天室发送新消息")
async def send_chat_message(
        room_id: int,
        message_data: schemas.ChatMessageCreate,
        current_user_id: int = Depends(get_current_user_id),  # 发送者为当前用户
        db: Session = Depends(get_db)
):
    """
    在指定聊天室中发送一条新消息。
    目前简化为只要房间存在且用户存在即可发送。
    """
    print(f"DEBUG: 用户 {current_user_id} 在聊天室 {room_id} 发送消息。")

    # 验证聊天室是否存在
    db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found.")

    # 验证发送者是否存在 (get_current_user_id 已经验证了，这里是双重检查)
    db_sender = db.query(Student).filter(Student.id == current_user_id).first()
    if not db_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sender user not found.")

    db_message = ChatMessage(
        room_id=room_id,
        sender_id=current_user_id,
        content_text=message_data.content_text,
        message_type=message_data.message_type,
        media_url=message_data.media_url
    )

    db.add(db_message)
    # 更新聊天室的 updated_at，作为最后活跃时间
    db_room.updated_at = func.now()
    db.add(db_room)  # SQLAlchemy会自动识别这是更新
    db.commit()
    db.refresh(db_message)

    # 填充 sender_name
    db_message.sender_name = db_sender.name  # 补齐 sender_name 字段

    print(f"DEBUG: 聊天室 {room_id} 收到消息 (ID: {db_message.id})。")
    return db_message


@app.get("/chatrooms/{room_id}/messages/", response_model=List[schemas.ChatMessageResponse],
         summary="获取指定聊天室的历史消息")
async def get_chat_messages(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 确保用户有权查看
        db: Session = Depends(get_db),
        limit: int = 50,  # 限制返回消息数量
        offset: int = 0  # 偏移量，用于分页加载
):
    """
    获取指定聊天室的历史消息。用户只能获取自己所属聊天室的消息。
    """
    print(f"DEBUG: 获取聊天室 {room_id} 的历史消息，用户 {current_user_id}。")

    # 验证聊天室是否存在且用户有访问权限 (简化为创建者)
    db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id, ChatRoom.creator_id == current_user_id).first()
    if not db_room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found or not authorized.")

    messages = db.query(ChatMessage).filter(ChatMessage.room_id == room_id) \
        .order_by(ChatMessage.sent_at.asc()) \
        .offset(offset).limit(limit).all()

    # 填充 sender_name
    response_messages = []
    for msg in messages:
        sender_name = db.query(Student).filter(Student.id == msg.sender_id).first().name or "未知"
        msg.sender_name = sender_name
        response_messages.append(msg)

    print(f"DEBUG: 聊天室 {room_id} 获取到 {len(messages)} 条历史消息。")
    return response_messages


# --- 小论坛 - 话题管理接口 ---
@app.post("/forum/topics/", response_model=schemas.ForumTopicResponse, summary="发布新论坛话题")
async def create_forum_topic(
        topic_data: schemas.ForumTopicBase,
        current_user_id: int = Depends(get_current_user_id),  # 话题发布者
        db: Session = Depends(get_db)
):
    """
    发布一个新论坛话题。可选择关联分享平台其他内容。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试发布话题: {topic_data.title}")

    # 验证共享内容是否存在 (如果提供了 shared_item_type 和 shared_item_id)
    if topic_data.shared_item_type and topic_data.shared_item_id:
        model = None
        if topic_data.shared_item_type == "note":
            model = Note
        elif topic_data.shared_item_type == "daily_record":
            model = DailyRecord
        elif topic_data.shared_item_type == "course":
            model = Course
        elif topic_data.shared_item_type == "project":
            model = Project
        elif topic_data.shared_item_type == "knowledge_article":
            model = KnowledgeArticle
        # Add more types if needed

        if model:
            shared_item = db.query(model).filter(model.id == topic_data.shared_item_id).first()
            if not shared_item:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail=f"Shared item of type {topic_data.shared_item_type} with ID {topic_data.shared_item_id} not found.")

    # 组合文本用于嵌入
    combined_text = (
            (topic_data.title or "") + ". " +
            (topic_data.content or "") + ". " +
            (topic_data.tags or "") + ". " +
            (topic_data.shared_item_type or "")
    ).strip()

    embedding = [0.0] * 1024  # 默认零向量
    if combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([combined_text])
            embedding = new_embedding[0]
            print(f"DEBUG: 话题嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成话题嵌入向量失败: {e}")

    db_topic = ForumTopic(
        owner_id=current_user_id,
        title=topic_data.title,
        content=topic_data.content,
        shared_item_type=topic_data.shared_item_type,
        shared_item_id=topic_data.shared_item_id,
        tags=topic_data.tags,
        combined_text=combined_text,
        embedding=embedding
    )

    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)

    # 填充 owner_name
    owner_name = db.query(Student).filter(Student.id == current_user_id).first().name or "未知用户"
    db_topic.owner_name = owner_name

    print(f"DEBUG: 话题 '{db_topic.title}' (ID: {db_topic.id}) 发布成功。")
    return db_topic


# 辅助函数：获取话题列表并填充动态信息
async def _get_forum_topics_with_details(query, current_user_id: int, db: Session):
    topics = query.all()
    for topic in topics:
        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == topic.owner_id).first()
        topic.owner_name = owner_obj.name if owner_obj else "未知用户"

        # 填充 is_liked_by_current_user
        topic.is_liked_by_current_user = False
        if current_user_id:  # 只有登录用户才检查是否点赞
            like = db.query(ForumLike).filter(
                ForumLike.owner_id == current_user_id,
                ForumLike.topic_id == topic.id
            ).first()
            if like:
                topic.is_liked_by_current_user = True

        # is_collected_by_current_user 暂时简化，需要定义论坛话题的收藏类型
        # 例如: if current_user_id and db.query(CollectionItem).filter(CollectionItem.user_id == current_user_id, CollectionItem.item_type == "forum_topic", CollectionItem.item_id == topic.id).first():
        #     topic.is_collected_by_current_user = True
        pass
    return topics


@app.get("/forum/topics/", response_model=List[schemas.ForumTopicResponse], summary="获取论坛话题列表")
async def get_forum_topics(
        current_user_id: int = Depends(get_current_user_id),  # 用于判断点赞/收藏状态
        db: Session = Depends(get_db),
        query_str: Optional[str] = None,  # 搜索关键词
        tag: Optional[str] = None,  # 标签过滤
        shared_type: Optional[str] = None,  # 分享类型过滤
        limit: int = 10,
        offset: int = 0
):
    """
    获取论坛话题列表，支持关键词、标签和分享类型过滤。
    """
    print(f"DEBUG: 获取论坛话题列表，用户 {current_user_id}，查询: {query_str}")
    query = db.query(ForumTopic)

    if query_str:
        # TODO: 考虑使用语义搜索 instead of LIKE for content search
        query = query.filter(
            (ForumTopic.title.ilike(f"%{query_str}%")) |
            (ForumTopic.content.ilike(f"%{query_str}%"))
        )
    if tag:
        query = query.filter(ForumTopic.tags.ilike(f"%{tag}%"))
    if shared_type:
        query = query.filter(ForumTopic.shared_item_type == shared_type)

    query = query.order_by(ForumTopic.created_at.desc()).offset(offset).limit(limit)

    return await _get_forum_topics_with_details(query, current_user_id, db)


@app.get("/forum/topics/{topic_id}", response_model=schemas.ForumTopicResponse, summary="获取指定论坛话题详情")
async def get_forum_topic_by_id(
        topic_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的论坛话题详情。每次访问会增加浏览数。
    """
    print(f"DEBUG: 获取话题 ID: {topic_id} 的详情。")
    topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")

    # 增加浏览数
    topic.views_count += 1
    db.add(topic)
    db.commit()
    db.refresh(topic)

    # 填充 owner_name, is_liked_by_current_user
    owner_obj = db.query(Student).filter(Student.id == topic.owner_id).first()
    topic.owner_name = owner_obj.name if owner_obj else "未知用户"
    topic.is_liked_by_current_user = False
    if current_user_id:
        like = db.query(ForumLike).filter(
            ForumLike.owner_id == current_user_id,
            ForumLike.topic_id == topic.id
        ).first()
        if like:
            topic.is_liked_by_current_user = True

    return topic


@app.put("/forum/topics/{topic_id}", response_model=schemas.ForumTopicResponse, summary="更新指定论坛话题")
async def update_forum_topic(
        topic_id: int,
        topic_data: schemas.ForumTopicBase,
        current_user_id: int = Depends(get_current_user_id),  # 只有话题发布者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的论坛话题内容。只有话题发布者能更新。
    更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新话题 ID: {topic_id}。")
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id, ForumTopic.owner_id == current_user_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found or not authorized.")

    update_data = topic_data.dict(exclude_unset=True)

    # 验证共享内容是否存在 (如果修改了 shared_item)
    if ("shared_item_type" in update_data and update_data["shared_item_type"]) or \
            ("shared_item_id" in update_data and update_data["shared_item_id"]):
        if update_data.get("shared_item_type") and update_data.get("shared_item_id"):
            model = None
            if update_data["shared_item_type"] == "note":
                model = Note
            elif update_data["shared_item_type"] == "daily_record":
                model = DailyRecord
            elif update_data["shared_item_type"] == "course":
                model = Course
            elif update_data["shared_item_type"] == "project":
                model = Project
            elif update_data["shared_item_type"] == "knowledge_article":
                model = KnowledgeArticle

            if model:
                shared_item = db.query(model).filter(model.id == update_data["shared_item_id"]).first()
                if not shared_item:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                        detail=f"Shared item of type {update_data['shared_item_type']} with ID {update_data['shared_item_id']} not found.")
        else:  # 如果只提供了一部分共享信息，但不能构成完整指向
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Both shared_item_type and shared_item_id must be provided together, or neither.")

    for key, value in update_data.items():
        setattr(db_topic, key, value)

    # 重新生成 combined_text
    db_topic.combined_text = (
            (db_topic.title or "") + ". " +
            (db_topic.content or "") + ". " +
            (db_topic.tags or "") + ". " +
            (db_topic.shared_item_type or "")
    ).strip()

    if db_topic.combined_text:
        try:
            new_embedding = ai_core.get_embeddings_from_api([db_topic.combined_text])
            db_topic.embedding = new_embedding[0]
            print(f"DEBUG: 话题 {db_topic.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新话题 {db_topic.id} 嵌入向量失败: {e}")

    db.add(db_topic)
    db.commit()
    db.refresh(db_topic)

    # 填充 owner_name, is_liked_by_current_user
    owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
    db_topic.owner_name = owner_obj.name if owner_obj else "未知用户"
    db_topic.is_liked_by_current_user = False  # Update does not change like status

    print(f"DEBUG: 话题 {db_topic.id} 更新成功。")
    return db_topic


@app.delete("/forum/topics/{topic_id}", summary="删除指定论坛话题")
async def delete_forum_topic(
        topic_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 只有话题发布者能删除
        db: Session = Depends(get_db)
):
    """
    删除指定ID的论坛话题及其所有评论和点赞。只有话题发布者能删除。
    """
    print(f"DEBUG: 删除话题 ID: {topic_id}。")
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id, ForumTopic.owner_id == current_user_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found or not authorized")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_topic)时自动处理所有评论和点赞
    db.delete(db_topic)
    db.commit()
    print(f"DEBUG: 话题 {topic_id} 及其评论点赞删除成功。")
    return {"message": "Forum topic and its comments/likes deleted successfully"}


# --- 小论坛 - 评论管理接口 ---
@app.post("/forum/topics/{topic_id}/comments/", response_model=schemas.ForumCommentResponse,
          summary="为论坛话题添加评论")
async def add_forum_comment(
        topic_id: int,
        comment_data: schemas.ForumCommentBase,
        current_user_id: int = Depends(get_current_user_id),  # 评论发布者
        db: Session = Depends(get_db)
):
    """
    为指定论坛话题添加评论。可选择回复某个已有评论（楼中楼）。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试为话题 {topic_id} 添加评论。")

    # 验证话题是否存在
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")

    # 验证父评论是否存在 (如果提供了 parent_comment_id)
    if comment_data.parent_comment_id:
        parent_comment = db.query(ForumComment).filter(
            ForumComment.id == comment_data.parent_comment_id,
            ForumComment.topic_id == topic_id  # 确保父评论属于同一话题
        ).first()
        if not parent_comment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found in this topic.")

    db_comment = ForumComment(
        topic_id=topic_id,
        owner_id=current_user_id,
        content=comment_data.content,
        parent_comment_id=comment_data.parent_comment_id
    )

    db.add(db_comment)
    # 更新话题的评论数
    db_topic.comments_count += 1
    db.add(db_topic)  # SQLAlchemy会自动识别这是更新
    db.commit()
    db.refresh(db_comment)

    # 填充 owner_name
    owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
    db_comment._owner_name = owner_obj.name  # Access private attribute to set
    db_comment.is_liked_by_current_user = False  # Default state

    print(f"DEBUG: 话题 {topic_id} 收到评论 (ID: {db_comment.id})。")
    return db_comment


@app.get("/forum/topics/{topic_id}/comments/", response_model=List[schemas.ForumCommentResponse],
         summary="获取论坛话题的评论列表")
async def get_forum_comments(
        topic_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        parent_comment_id: Optional[int] = None,  # 过滤条件: 只获取指定父评论下的子评论 (实现楼中楼)
        limit: int = 50,  # 限制返回消息数量
        offset: int = 0  # 偏移量，用于分页加载
):
    """
    获取指定论坛话题的评论列表。
    可以过滤以获取特定评论的回复（楼中楼）。
    """
    print(f"DEBUG: 获取话题 {topic_id} 的评论，用户 {current_user_id}，父评论ID: {parent_comment_id}。")

    # 验证话题是否存在
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")

    query = db.query(ForumComment).filter(ForumComment.topic_id == topic_id)

    if parent_comment_id is not None:
        query = query.filter(ForumComment.parent_comment_id == parent_comment_id)
    else:  # 默认获取一级评论 (parent_comment_id 为 None)
        query = query.filter(ForumComment.parent_comment_id.is_(None))

    comments = query.order_by(ForumComment.created_at.asc()).offset(offset).limit(limit).all()

    response_comments = []
    for comment in comments:
        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == comment.owner_id).first()
        comment._owner_name = owner_obj.name if owner_obj else "未知用户"

        # 填充 is_liked_by_current_user
        comment.is_liked_by_current_user = False
        if current_user_id:
            like = db.query(ForumLike).filter(
                ForumLike.owner_id == current_user_id,
                ForumLike.comment_id == comment.id
            ).first()
            if like:
                comment.is_liked_by_current_user = True

        response_comments.append(comment)

    print(f"DEBUG: 话题 {topic_id} 获取到 {len(comments)} 条评论。")
    return response_comments


@app.put("/forum/comments/{comment_id}", response_model=schemas.ForumCommentResponse, summary="更新指定论坛评论")
async def update_forum_comment(
        comment_id: int,
        comment_data: schemas.ForumCommentBase,  # 只允许更新内容
        current_user_id: int = Depends(get_current_user_id),  # 只有评论发布者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的论坛评论。只有评论发布者能更新。
    """
    print(f"DEBUG: 更新评论 ID: {comment_id}。")
    db_comment = db.query(ForumComment).filter(ForumComment.id == comment_id,
                                               ForumComment.owner_id == current_user_id).first()
    if not db_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found or not authorized.")

    update_data = comment_data.dict(exclude_unset=True)

    if "content" in update_data:
        setattr(db_comment, "content", update_data["content"])

    # 不允许修改 parent_comment_id
    if "parent_comment_id" in update_data and update_data["parent_comment_id"] != db_comment.parent_comment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot change parent_comment_id of a comment.")

    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    # 填充 owner_name
    owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
    db_comment._owner_name = owner_obj.name
    db_comment.is_liked_by_current_user = False  # Update does not change like status

    print(f"DEBUG: 评论 {db_comment.id} 更新成功。")
    return db_comment


@app.delete("/forum/comments/{comment_id}", summary="删除指定论坛评论")
async def delete_forum_comment(
        comment_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 只有评论发布者能删除
        db: Session = Depends(get_db)
):
    """
    删除指定ID的论坛评论。如果评论有子评论，则会级联删除所有回复。
    只有评论发布者能删除。
    """
    print(f"DEBUG: 删除评论 ID: {comment_id}。")
    db_comment = db.query(ForumComment).filter(ForumComment.id == comment_id,
                                               ForumComment.owner_id == current_user_id).first()
    if not db_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found or not authorized.")

    # 获取所属话题以便更新 comments_count
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == db_comment.topic_id).first()
    if db_topic:
        db_topic.comments_count -= 1
        db.add(db_topic)

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_comment)时自动处理所有子评论和点赞
    db.delete(db_comment)
    db.commit()
    print(f"DEBUG: 评论 {comment_id} 及其子评论点赞删除成功。")
    return {"message": "Forum comment and its children/likes deleted successfully"}


# --- 小论坛 - 点赞管理接口 ---
@app.post("/forum/likes/", response_model=schemas.ForumLikeResponse, summary="点赞论坛话题或评论")
async def like_forum_item(
        like_data: Dict[str, Any],  # 接收 topic_id 或 comment_id
        current_user_id: int = Depends(get_current_user_id),  # 点赞者
        db: Session = Depends(get_db)
):
    """
    点赞一个论坛话题或评论。
    必须提供 topic_id 或 comment_id 中的一个。同一用户不能重复点赞同一项。
    """
    topic_id = like_data.get("topic_id")
    comment_id = like_data.get("comment_id")

    if not topic_id and not comment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Either topic_id or comment_id must be provided.")
    if topic_id and comment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only one of topic_id or comment_id can be provided.")

    existing_like = None
    if topic_id:
        existing_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                                   ForumLike.topic_id == topic_id).first()
        if not existing_like:
            target_item = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
            if not target_item:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")
            target_item.likes_count += 1
            db.add(target_item)
    elif comment_id:
        existing_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                                   ForumLike.comment_id == comment_id).first()
        if not existing_like:
            target_item = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
            if not target_item:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found.")
            target_item.likes_count += 1
            db.add(target_item)

    if existing_like:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already liked this item.")

    db_like = ForumLike(
        owner_id=current_user_id,
        topic_id=topic_id,
        comment_id=comment_id
    )

    db.add(db_like)
    db.commit()
    db.refresh(db_like)
    print(f"DEBUG: 用户 {current_user_id} 点赞成功 (Topic ID: {topic_id or 'N/A'}, Comment ID: {comment_id or 'N/A'})。")
    return db_like


@app.delete("/forum/likes/", summary="取消点赞论坛话题或评论")
async def unlike_forum_item(
        unlike_data: Dict[str, Any],  # 接收 topic_id 或 comment_id
        current_user_id: int = Depends(get_current_user_id),  # 取消点赞者
        db: Session = Depends(get_db)
):
    """
    取消点赞一个论坛话题或评论。
    必须提供 topic_id 或 comment_id 中的一个。
    """
    topic_id = unlike_data.get("topic_id")
    comment_id = unlike_data.get("comment_id")

    if not topic_id and not comment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Either topic_id or comment_id must be provided.")
    if topic_id and comment_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only one of topic_id or comment_id can be provided.")

    db_like = None
    if topic_id:
        db_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                             ForumLike.topic_id == topic_id).first()
        if db_like:
            target_item = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
            if target_item and target_item.likes_count > 0:
                target_item.likes_count -= 1
                db.add(target_item)
    elif comment_id:
        db_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                             ForumLike.comment_id == comment_id).first()
        if db_like:
            target_item = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
            if target_item and target_item.likes_count > 0:
                target_item.likes_count -= 1
                db.add(target_item)

    if not db_like:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Like not found for this item by current user.")

    db.delete(db_like)
    db.commit()
    print(
        f"DEBUG: 用户 {current_user_id} 取消点赞成功 (Topic ID: {topic_id or 'N/A'}, Comment ID: {comment_id or 'N/A'})。")
    return {"message": "Like removed successfully"}


# --- 小论坛 - 用户关注管理接口 ---
@app.post("/forum/follow/", response_model=schemas.UserFollowResponse, summary="关注一个用户")
async def follow_user(
        follow_data: Dict[str, Any],  # 接收 followed_id
        current_user_id: int = Depends(get_current_user_id),  # 关注者
        db: Session = Depends(get_db)
):
    """
    允许当前用户关注另一个用户。
    """
    followed_id = follow_data.get("followed_id")
    if not followed_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="followed_id must be provided.")

    if followed_id == current_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself.")

    # 验证被关注用户是否存在
    followed_user = db.query(Student).filter(Student.id == followed_id).first()
    if not followed_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User to follow not found.")

    # 检查是否已关注
    existing_follow = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user_id,
        UserFollow.followed_id == followed_id
    ).first()
    if existing_follow:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following this user.")

    db_follow = UserFollow(
        follower_id=current_user_id,
        followed_id=followed_id
    )

    db.add(db_follow)
    db.commit()
    db.refresh(db_follow)
    print(f"DEBUG: 用户 {current_user_id} 关注用户 {followed_id} 成功。")
    return db_follow


@app.delete("/forum/unfollow/", summary="取消关注一个用户")
async def unfollow_user(
        unfollow_data: Dict[str, Any],  # 接收 followed_id
        current_user_id: int = Depends(get_current_user_id),  # 取消关注者
        db: Session = Depends(get_db)
):
    """
    允许当前用户取消关注另一个用户。
    """
    followed_id = unfollow_data.get("followed_id")
    if not followed_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="followed_id must be provided.")

    db_follow = db.query(UserFollow).filter(
        UserFollow.follower_id == current_user_id,
        UserFollow.followed_id == followed_id
    ).first()
    if not db_follow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not currently following this user.")

    db.delete(db_follow)
    db.commit()
    print(f"DEBUG: 用户 {current_user_id} 取消关注用户 {followed_id} 成功。")
    return {"message": "Unfollowed successfully"}



# --- MCP服务配置管理接口 ---
@app.post("/mcp-configs/", response_model=schemas.UserMcpConfigResponse, summary="添加新的MCP服务配置")
async def create_mcp_config(
        config_data: schemas.UserMcpConfigCreate,
        current_user_id: int = Depends(get_current_user_id),  # 配置所属用户
        db: Session = Depends(get_db)
):
    """
    为当前用户添加一个新的MCP（ModelScope Community Platform或其他类MCP服务）配置。
    如果提供了API密钥，将加密存储。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试添加MCP配置: {config_data.name}")

    if config_data.api_key:
        encrypted_key = ai_core.encrypt_key(config_data.api_key)
    else:
        encrypted_key = None

    db_config = UserMcpConfig(
        owner_id=current_user_id,
        name=config_data.name,
        mcp_type=config_data.mcp_type,
        base_url=config_data.base_url,
        protocol_type=config_data.protocol_type,  # 保存协议类型
        api_key_encrypted=encrypted_key,
        is_active=config_data.is_active,
        description=config_data.description
    )

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    # 手动设置api_key为 None 或空字符串，避免响应中包含明文密钥
    db_config.api_key = None

    print(f"DEBUG: MCP配置 '{db_config.name}' (ID: {db_config.id}) 添加成功。")
    return db_config


@app.get("/mcp-configs/", response_model=List[schemas.UserMcpConfigResponse], summary="获取当前用户所有MCP服务配置")
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
    for config in configs:
        config.api_key = None  # 不返回密钥
    print(f"DEBUG: 获取到 {len(configs)} 条MCP配置。")
    return configs


@app.get("/mcp-configs/{config_id}", response_model=schemas.UserMcpConfigResponse, summary="获取指定MCP服务配置详情")
async def get_mcp_config_by_id(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的MCP服务配置详情。用户只能获取自己的配置。
    """
    print(f"DEBUG: 获取MCP配置 ID: {config_id} 的详情。")
    config = db.query(UserMcpConfig).filter(UserMcpConfig.id == config_id,
                                            UserMcpConfig.owner_id == current_user_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP config not found or not authorized")

    config.api_key = None  # 不返回密钥
    return config


@app.put("/mcp-configs/{config_id}", response_model=schemas.UserMcpConfigResponse, summary="更新指定MCP服务配置")
async def update_mcp_config(
        config_id: int,
        config_data: schemas.UserMcpConfigBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的MCP服务配置。用户只能更新自己的配置。
    如果提供了API密钥，将加密存储。
    """
    print(f"DEBUG: 更新MCP配置 ID: {config_id}。")
    db_config = db.query(UserMcpConfig).filter(UserMcpConfig.id == config_id,
                                               UserMcpConfig.owner_id == current_user_id).first()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP config not found or not authorized")

    update_data = config_data.dict(exclude_unset=True)

    if "name" in update_data:
        db_config.name = update_data["name"]
    if "mcp_type" in update_data:
        db_config.mcp_type = update_data["mcp_type"]
    if "base_url" in update_data:
        db_config.base_url = update_data["base_url"]
    if "protocol_type" in update_data:  # 更新协议类型
        db_config.protocol_type = update_data["protocol_type"]
    if "is_active" in update_data:
        db_config.is_active = update_data["is_active"]
    if "description" in update_data:
        db_config.description = update_data["description"]

    if "api_key" in update_data and update_data["api_key"] is not None:
        encrypted_key = ai_core.encrypt_key(update_data["api_key"])
        db_config.api_key_encrypted = encrypted_key
        print(f"DEBUG: MCP配置 {config_id} 的API密钥已加密存储。")
    elif "api_key" in update_data and update_data["api_key"] is None:
        db_config.api_key_encrypted = None

    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    db_config.api_key = None
    print(f"DEBUG: MCP配置 {db_config.id} 更新成功。")
    return db_config


@app.delete("/mcp-configs/{config_id}", summary="删除指定MCP服务配置")
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


@app.post("/mcp-configs/{config_id}/check-status", response_model=schemas.McpStatusResponse,
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
            decrypted_key = ai_core.decrypt_key(db_config.api_key_encrypted)
        except Exception as e:
            return schemas.McpStatusResponse(
                status="failure",
                message=f"无法解密API密钥，请检查密钥是否正确或重新配置。错误: {e}",
                service_name=db_config.name,
                config_id=config_id
            )

    status_response = await check_mcp_api_connectivity(db_config.base_url, db_config.protocol_type,
                                                       decrypted_key)  # 传递协议类型
    status_response.service_name = db_config.name
    status_response.config_id = config_id

    print(f"DEBUG: MCP配置 {config_id} 连通性检查结果: {status_response.status}")
    return status_response


@app.get("/llm/mcp-available-tools", response_model=List[schemas.McpToolDefinition],
         summary="获取智库聊天可用的MCP工具列表")
async def get_mcp_available_tools(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    根据用户已配置且启用的MCP服务，返回可用于智库聊天中的工具列表。
    这里模拟ModelScope MCP可能提供的工具。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 可用的MCP工具。")

    active_mcp_configs = db.query(UserMcpConfig).filter(
        UserMcpConfig.owner_id == current_user_id,
        UserMcpConfig.is_active == True  # 只返回启用的服务
    ).all()

    available_tools = []
    # 模拟工具的返回
    for config in active_mcp_configs:
        # 可以根据 config.mcp_type 或 config.base_url 来更智能地模拟
        # 例如，如果 base_url 类似于 ModelScope 的可视化图表服务，则返回可视化工具
        if "modelscope" in config.base_url.lower() and config.protocol_type.lower() == "sse":
            # 这里可以根据 config.name 或 config.description 来模拟提供不同的工具
            if "图表" in config.name or "chart" in config.name.lower() or "visual" in config.name.lower():
                # 模拟一个可视化图表工具
                available_tools.append(schemas.McpToolDefinition(
                    tool_id="visual_chart_generator",
                    name="可视化图表生成器",
                    description=f"通过MCP服务 {config.name} ({config.base_url}) 将数据转换为多种类型的图表，支持折线图、柱状图、饼图等。",
                    mcp_config_id=config.id,
                    mcp_config_name=config.name,
                    input_schema={
                        "type": "object",
                        "properties": {
                            "chart_type": {"type": "string", "enum": ["line", "bar", "pie"], "description": "图表类型"},
                            "data_points": {"type": "array", "items": {"type": "object",
                                                                       "properties": {"label": {"type": "string"},
                                                                                      "value": {"type": "number"}}}},
                            "title": {"type": "string", "description": "图表标题", "nullable": True}
                        },
                        "required": ["chart_type", "data_points"]
                    },
                    output_schema={"type": "string", "description": "生成的图表图片URL"}
                ))
            if "图像生成" in config.name or "image" in config.name.lower() or "gen" in config.name.lower():
                # 模拟一个图像生成工具
                available_tools.append(schemas.McpToolDefinition(
                    tool_id="image_generator",
                    name="文生图工具",
                    description=f"通过MCP服务 {config.name} ({config.base_url}) 根据文本描述生成高质量图像。",
                    mcp_config_id=config.id,
                    mcp_config_name=config.name,
                    input_schema={
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "生成图像的文本提示词"},
                            "style": {"type": "string", "enum": ["realistic", "cartoon", "abstract"],
                                      "description": "图像风格", "nullable": True}
                        },
                        "required": ["prompt"]
                    },
                    output_schema={"type": "string", "description": "生成的图像URL"}
                ))
        # 更多通用工具类型模拟，可以添加到这里
        # 例如，假设有个私有的MCP服务提供了文本摘要功能
        elif "my_private_mcp" == config.mcp_type:
            available_tools.append(schemas.McpToolDefinition(
                tool_id="text_summary_tool",
                name="长文本摘要工具",
                description=f"通过您定义的MCP服务 {config.name} 对长文本进行概括总结。",
                mcp_config_id=config.id,
                mcp_config_name=config.name,
                input_schema={"type": "object",
                              "properties": {"text": {"type": "string", "description": "待摘要的文本"}},
                              "required": ["text"]},
                output_schema={"type": "string", "description": "文本摘要结果"}
            ))

    print(f"DEBUG: 找到 {len(available_tools)} 个可用的MCP工具。")
    return available_tools


# --- WebSocket 聊天室接口 ---
@app.websocket("/ws/chat/{room_id}/{user_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        room_id: int,
        user_id: int,  # 这里 user_id 只是为了演示方便从路径获取，生产环境应从认证Token中提取并验证
        db: Session = Depends(get_db)  # WebSocket 中也可以使用 FastAPI 的依赖注入来获取数据库会话
):
    """
    WebSocket 聊天室端点。允许用户加入指定聊天室发送和接收实时消息。
    - room_id: 聊天室的ID
    - user_id: 当前连接的用户ID (生产环境应从认证Token中提取)
    """
    print(f"DEBUG_WS: 尝试连接房间 {room_id}，用户 {user_id}。")

    # 验证聊天室是否存在 (仅简单验证，后续可增强权限检查)
    chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not chat_room:
        # 如果聊天室不存在，关闭连接并给出理由
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Chat room not found.")
        print(f"DEBUG_WS: 房间 {room_id} 未找到，连接关闭。")
        return

    # TODO（待办事项）：
    # 在生产环境中，此处应添加更严格的用户权限检查，例如：
    #   - 验证 user_id 是否合法 (通过 JWT Token 解析而不是路径变量)
    #   - 检查该 user_id 是否是 `room_id` 的成员
    # 如果验证失败，调用 await websocket.close(...)

    try:
        # 1. 连接：将新进来的WebSocket添加到管理器中
        await manager.connect(websocket, room_id, user_id)

        # 2. 发送欢迎消息给新连接的用户
        await manager.send_personal_message(f"欢迎用户 {user_id} 加入聊天室 {room_id}！", websocket)

        # 3. 广播用户加入的消息给所有其他人 (可选)
        await manager.broadcast(f"用户 {user_id} 加入了聊天室。", room_id)

        # 4. 持续循环：接收客户端发送的消息，并进行处理
        while True:
            # 尝试接收文本消息 (也可以是JSON等)
            data = await websocket.receive_text()
            print(f"DEBUG_WS: 收到来自用户 {user_id} (房间 {room_id}) 的消息: {data}")

            # 5. 消息持久化：将消息保存到数据库
            db_message = ChatMessage(
                room_id=room_id,
                sender_id=user_id,
                content_text=data,
                message_type="text"  # 默认为文本消息，可以扩展为'image', 'file'等
            )
            db.add(db_message)
            db.commit()  # 立即提交
            db.refresh(db_message)  # 刷新以获取ID和时间戳

            # 6. 消息广播：将收到的消息（通常会带上发送者信息和时间戳）广播给房间内所有活跃连接
            # 这里我们广播一个包含发送者名称或ID的消息
            # 实际可以构建更复杂的 JSON 格式消息，例如:
            # message_to_broadcast = json.dumps({"sender_id": user_id, "content": data, "timestamp": str(db_message.sent_at)})
            await manager.broadcast(f"用户 {user_id}: {data}", room_id)

    except WebSocketDisconnect:
        # 7. 断开连接：当客户端主动断开或连接异常时触发
        manager.disconnect(room_id, user_id)  # 从管理器中移除连接
        print(f"DEBUG_WS: 用户 {user_id} 从房间 {room_id} 断开连接。")
        # 广播用户离开消息 (可选)
        await manager.broadcast(f"用户 {user_id} 离开了聊天室。", room_id)
    except Exception as e:
        # 8. 错误处理：捕获其他意外错误
        print(f"ERROR_WS: WebSocket 意外错误: {e}")
        manager.disconnect(room_id, user_id)  # 即使错误也尝试断开连接
        # 关闭WebSocket连接，并发送错误码和原因
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason=f"服务器错误: {e}")


# --- 配置静态文件服务，用于提供生成的音频文件 ---
os.makedirs("temp_audio", exist_ok=True)
app.mount("/audio", StaticFiles(directory="temp_audio"), name="audio")

