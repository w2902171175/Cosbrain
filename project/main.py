# project/main.py
from fastapi.responses import PlainTextResponse, Response
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, WebSocket, WebSocketDisconnect, Query, \
    Response, Form
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal, Union, Tuple
import numpy as np
from datetime import timedelta, datetime, timezone, date
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, ForeignKey
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
import requests, secrets, json, os, uuid, asyncio, httpx, re, traceback, time

load_dotenv()
# 密码哈希
from passlib.context import CryptContext

# 导入数据库和模型
from database import SessionLocal, engine, init_db, get_db
from models import Student, Project, Note, KnowledgeBase, KnowledgeArticle, Course, UserCourse, CollectionItem, \
    DailyRecord, Folder, CollectedContent, ChatRoom, ChatMessage, ForumTopic, ForumComment, ForumLike, UserFollow, \
    UserMcpConfig, UserSearchEngineConfig, KnowledgeDocument, KnowledgeDocumentChunk, ChatRoomMember, \
    ChatRoomJoinRequest, UserTTSConfig, Achievement, UserAchievement, PointTransaction, CourseMaterial, AIConversation, \
    AIConversationMessage, ProjectApplication, ProjectMember, KnowledgeBaseFolder, AIConversationTemporaryFile, \
    CourseLike, ProjectLike, ProjectFile
from dependencies import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from schemas import UserTTSConfigBase, UserTTSConfigCreate, UserTTSConfigUpdate, UserTTSConfigResponse, AchievementBase, \
    AchievementCreate, AchievementUpdate, AchievementResponse, UserAchievementResponse, PointTransactionResponse, \
    PointsRewardRequest, CountResponse, AIQARequest, AIQAResponse, AIConversationResponse, \
    AIConversationMessageResponse, CollectedContentSharedItemAddRequest, ProjectApplicationResponse, \
    ProjectApplicationProcess, ProjectMemberResponse

import ai_core, oss_utils, schemas

# --- FastAPI 应用实例 ---
app = FastAPI(
    title="鸿庆书云创新协作平台后端API",
    description="为学生提供智能匹配、知识管理、课程学习和协作支持的综合平台。",
    version="0.1.0",
)

# 令牌认证方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")  # 指向登录接口的URL
bearer_scheme = HTTPBearer(auto_error=False)

# --- 密码哈希上下文 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# --- 依赖项：获取当前登录用户ID ---
async def get_current_user_id(
        # 依赖于 bearer_scheme 来获取 Authorization: Bearer <token>
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        db: Session = Depends(get_db)
) -> int:
    """
    从 JWT 令牌中提取并验证用户ID。
    如果令牌无效或缺失，抛出 HTTPException。
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")  # JWT payload 中的 'sub' (subject) 字段通常存放用户ID

        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT 令牌中缺少用户ID信息")

        # 验证用户是否存在
        user = db.query(Student).filter(Student.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT 令牌指向的用户不存在")

        print(f"DEBUG_AUTH: 已认证用户 ID: {user_id}")
        return user_id

    except JWTError:  # 如果 JWT 验证失败 (如签名错误, 过期等)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的 JWT 令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        print(f"ERROR_AUTH: 认证过程中发生未知错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="认证过程中发生服务器错误"
        )


# --- 依赖项：验证用户是否为管理员 ---
async def is_admin_user(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    验证当前用户是否是系统管理员。如果不是，则抛出403 Forbidden异常。
    返回完整的 Student 对象，方便后续操作。
    """
    print(f"DEBUG_ADMIN_AUTH: 验证用户 {current_user_id} 是否为管理员。")
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作，此功能仅限系统管理员。")
    return user  # 返回整个用户对象，方便需要用户详情的接口


async def get_active_tts_config(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
) -> Optional[UserTTSConfig]:
    """获取当前用户激活的TTS配置"""
    return db.query(UserTTSConfig).filter(
        UserTTSConfig.owner_id == current_user_id,
        UserTTSConfig.is_active == True
    ).first()


# --- 辅助函数：积分奖励和成就检查 ---
async def _award_points(
        db: Session,
        user: Student,
        amount: int,
        reason: str,
        transaction_type: Literal["EARN", "CONSUME", "ADMIN_ADJUST"],
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None
):
    """
    奖励或扣除用户积分，并记录积分交易日志。
    """
    if amount == 0:
        return

    user.total_points += amount
    if user.total_points < 0:  # 确保积分不为负（如果业务不允许）
        user.total_points = 0

    db.add(user)

    transaction = PointTransaction(
        user_id=user.id,
        amount=amount,
        reason=reason,
        transaction_type=transaction_type,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id
    )
    db.add(transaction)

    print(
        f"DEBUG_POINTS_PENDING: 用户 {user.id} 积分变动：{amount}，当前总积分（提交前）：{user.total_points}，原因：{reason}。")


async def _check_and_award_achievements(db: Session, user_id: int):
    """
    检查用户是否达到了任何成就条件，并授予未获得的成就。
    此函数会定期或在关键事件后调用。它只添加对象到会话，不进行commit。
    """
    print(f"DEBUG_ACHIEVEMENT: 检查用户 {user_id} 的成就。")
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        print(f"WARNING_ACHIEVEMENT: 用户 {user_id} 不存在。")
        return

    # 获取所有活跃且未被该用户获取的成就定义
    unearned_achievements_query = db.query(Achievement).outerjoin(
        UserAchievement,
        and_(
            UserAchievement.achievement_id == Achievement.id,
            UserAchievement.user_id == user_id
        )
    ).filter(
        Achievement.is_active == True,  # 仅检查活跃的成就
        UserAchievement.id.is_(None)  # 用户的 UserAchievement 记录不存在（即尚未获得）
    )

    unearned_achievements = unearned_achievements_query.all()
    print(
        f"DEBUG_ACHIEVEMENT_RAW_QUERY: Raw query result for unearned achievements for user {user_id}: {unearned_achievements}")

    if not unearned_achievements:
        print(f"DEBUG_ACHIEVEMENT: 用户 {user_id} 没有未获得的活跃成就。")
        return

    # 预先计算用户相关数据，避免在循环中重复查询
    user_data_for_achievements = {
        "PROJECT_COMPLETED_COUNT": db.query(Project.id).filter(
            Project.creator_id == user_id,
            Project.project_status == "已完成"
        ).count(),
        "COURSE_COMPLETED_COUNT": db.query(UserCourse.course_id).filter(
            UserCourse.student_id == user_id,
            UserCourse.status == "completed"
        ).count(),
        "FORUM_LIKES_RECEIVED": db.query(ForumLike).filter(
            or_(
                # 用户的话题获得的点赞
                ForumLike.topic_id.in_(db.query(ForumTopic.id).filter(ForumTopic.owner_id == user_id)),
                # 用户的评论获得的点赞
                ForumLike.comment_id.in_(db.query(ForumComment.id).filter(ForumComment.owner_id == user_id))
            )
        ).count(),
        "FORUM_POSTS_COUNT": db.query(ForumTopic).filter(ForumTopic.owner_id == user_id).count(),
        "CHAT_MESSAGES_SENT_COUNT": db.query(ChatMessage).filter(
            ChatMessage.sender_id == user_id,
            ChatMessage.deleted_at.is_(None)  # 排除已删除的消息
        ).count(),
        "LOGIN_COUNT": user.login_count
    }

    print(f"DEBUG_ACHIEVEMENT_DATA: User {user_id} counts: {user_data_for_achievements}")

    awarded_count = 0
    for achievement in unearned_achievements:
        is_achieved = False
        criteria_value = achievement.criteria_value

        print(
            f"DEBUG_ACHIEVEMENT_CHECK: Checking achievement '{achievement.name}' (Criteria: {achievement.criteria_type}={criteria_value}) for user {user_id}")

        if achievement.criteria_type == "PROJECT_COMPLETED_COUNT":
            if user_data_for_achievements["PROJECT_COMPLETED_COUNT"] >= criteria_value:
                is_achieved = True
        elif achievement.criteria_type == "COURSE_COMPLETED_COUNT":
            if user_data_for_achievements["COURSE_COMPLETED_COUNT"] >= criteria_value:
                is_achieved = True
        elif achievement.criteria_type == "FORUM_LIKES_RECEIVED":
            if user_data_for_achievements["FORUM_LIKES_RECEIVED"] >= criteria_value:
                is_achieved = True
        elif achievement.criteria_type == "FORUM_POSTS_COUNT":
            if user_data_for_achievements["FORUM_POSTS_COUNT"] >= criteria_value:
                is_achieved = True
        elif achievement.criteria_type == "CHAT_MESSAGES_SENT_COUNT":
            if user_data_for_achievements["CHAT_MESSAGES_SENT_COUNT"] >= criteria_value:
                is_achieved = True
        elif achievement.criteria_type == "LOGIN_COUNT":
            user_login_count_val = user_data_for_achievements["LOGIN_COUNT"]
            crit_val_float = float(criteria_value)
            user_count_float = float(user_login_count_val)

            print(
                f"DEBUG_ACHIEVEMENT_LOGIN_VALUE_TYPE: Achievement '{achievement.name}' criteria_value = {crit_val_float} (Type: {type(crit_val_float)})")
            print(
                f"DEBUG_ACHIEVEMENT_LOGIN_VALUE_TYPE: User LOGIN_COUNT = {user_count_float} (Type: {type(user_count_float)})")

            if user_count_float >= crit_val_float:
                is_achieved = True

            print(
                f"DEBUG_ACHIEVEMENT_LOGIN_CHECK: Comparison result: {user_count_float} >= {crit_val_float} is {is_achieved}")
        elif achievement.criteria_type == "DAILY_LOGIN_STREAK":
            # 保持 is_achieved 为 False (除非额外开发连续登录计数器)。
            pass
        if is_achieved:
            user_achievement = UserAchievement(
                user_id=user_id,
                achievement_id=achievement.id,
                earned_at=func.now(),
                is_notified=False  # 默认设置为未通知，等待后续推送
            )
            db.add(user_achievement)

            if achievement.reward_points > 0:
                await _award_points(
                    db=db,
                    user=user,  # 传递已经存在于会话中的 user 对象
                    amount=achievement.reward_points,
                    reason=f"获得成就：{achievement.name}",
                    transaction_type="EARN",
                    related_entity_type="achievement",
                    related_entity_id=achievement.id
                )

            print(
                f"SUCCESS_ACHIEVEMENT_PENDING: 用户 {user_id} 获得成就: {achievement.name}！奖励 {achievement.reward_points} 积分 (待提交)。")
            awarded_count += 1
    if awarded_count > 0:
        print(f"INFO_ACHIEVEMENT: 用户 {user_id} 本次共获得 {awarded_count} 个成就 (待提交)。")


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
            if not self.active_connections[room_id]:  # 如果房间空了，移除房间入口
                del self.active_connections[room_id]
            print(
                f"DEBUG_WS: 用户 {user_id} 离开房间 {room_id}。当前房间连接数: {len(self.active_connections.get(room_id, {}))}")

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


manager = ConnectionManager()  # 创建一个全局的连接管理器实例


# --- 辅助函数：创建 JWT 访问令牌 ---
def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None):
    """
    根据提供的用户信息创建 JWT 访问令牌。
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta  # 使用 UTC 时间，更严谨
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})  # 将过期时间添加到payload
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)  # 使用定义的秘密密钥和算法编码
    return encoded_jwt


# --- CORS 中间件 (跨域资源共享) ---
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost:5173",
    # 添加前端域名和端口
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


# --- 辅助函数：安全地获取文本部分 (现在是全局的了！) ---
def _get_text_part(value: Any) -> str:
    """
    Helper to get string from potentially None, empty string, datetime, or int/float
    Ensures that values used in combined_text are non-empty strings.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")  # 格式化日期，只保留年月日
    if isinstance(value, (int, float)):
        # 为小时数添加单位，或根据需要返回原始字符串表示
        return str(value) + ""  # 此处不需要加“小时”，因为这只是一个通用函数
    return str(value).strip() if str(value).strip() else ""


# --- 辅助函数：创建收藏内容的内部逻辑 (用于复用) ---
async def _create_collected_content_item_internal(
        db: Session,
        current_user_id: int,
        content_data: schemas.CollectedContentBase,
        uploaded_file_bytes: Optional[bytes] = None,
        uploaded_file_object_name: Optional[str] = None,
        uploaded_file_content_type: Optional[str] = None,
        uploaded_file_original_filename: Optional[str] = None,
        uploaded_file_size: Optional[int] = None,
) -> CollectedContent:
    """
    内部辅助函数：处理收藏内容的创建逻辑，包括从共享项提取信息和生成嵌入。
    支持直接文件/媒体上传到OSS。
    """
    # 1. 验证目标文件夹是否存在且属于当前用户 (如果提供了folder_id)
    final_folder_id = content_data.folder_id
    if final_folder_id is None:  # 如果用户没有指定文件夹ID
        default_folder_name = "默认文件夹"
        default_folder = db.query(Folder).filter(
            Folder.owner_id == current_user_id,
            Folder.name == default_folder_name,
            Folder.parent_id.is_(None)  # 确保是顶级的“默认文件夹”
        ).first()

        if not default_folder:
            # 如果“默认文件夹”不存在，则创建它
            print(f"DEBUG_COLLECTION: 用户 {current_user_id} 的 '{default_folder_name}' 不存在，正在创建。")
            new_default_folder = Folder(
                owner_id=current_user_id,
                name=default_folder_name,
                description="自动创建的默认收藏文件夹。",
                parent_id=None  # 确保是顶级文件夹
            )
            db.add(new_default_folder)
            db.flush()  # 刷新以获取ID，但不提交，因为整个函数结束后才统一提交
            final_folder_id = new_default_folder.id
        else:
            final_folder_id = default_folder.id
        print(f"DEBUG_COLLECTION: 收藏将放入文件夹 ID: {final_folder_id} ('{default_folder_name}')")
    else:
        # 如果用户指定了 folder_id，验证其存在性和权限
        target_folder = db.query(Folder).filter(
            Folder.id == final_folder_id,
            Folder.owner_id == current_user_id
        ).first()
        if not target_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="目标文件夹未找到或无权访问。")

    # 这些变量将存储最终用于创建CollectedContent实例的值
    final_title = content_data.title
    final_type = content_data.type
    final_url = content_data.url
    final_content = content_data.content
    final_author = content_data.author
    final_tags = content_data.tags
    final_thumbnail = content_data.thumbnail
    final_duration = content_data.duration
    final_file_size = content_data.file_size
    final_status = content_data.status

    # 优先处理直接上传的文件/媒体
    if uploaded_file_bytes and uploaded_file_object_name and uploaded_file_content_type:
        final_url = f"{oss_utils.OSS_BASE_URL.rstrip('/')}/{uploaded_file_object_name}"
        final_file_size = uploaded_file_size
        # 自动推断文件类型
        if uploaded_file_content_type.startswith("image/"):
            final_type = "image"
        elif uploaded_file_content_type.startswith("video/"):
            final_type = "video"
        else:
            final_type = "file"  # 其他文件类型

        # 如果没有提供title，使用文件名作为标题
        if not final_title and uploaded_file_original_filename:
            final_title = uploaded_file_original_filename

        # 如果没有提供content，使用文件描述作为内容
        if not final_content and uploaded_file_original_filename:
            final_content = f"Uploaded {final_type}: {uploaded_file_original_filename}"


    # 如果有 shared_item_type，说明是收藏内部资源 (但直接上传的文件更优先)
    elif content_data.shared_item_type and content_data.shared_item_id is not None:
        model_map = {
            "project": Project,
            "course": Course,
            "forum_topic": ForumTopic,
            "note": Note,
            "daily_record": DailyRecord,
            "knowledge_article": KnowledgeArticle,
            "chat_message": ChatMessage,
            "knowledge_document": KnowledgeDocument
        }
        source_model = model_map.get(content_data.shared_item_type)

        if not source_model:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的共享项类型: {content_data.shared_item_type}")

        # 获取源数据对象
        source_item = db.get(source_model, content_data.shared_item_id)  # 使用 db.get 更高效
        if not source_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"共享项 (类型: {content_data.shared_item_type}, ID: {content_data.shared_item_id}) 未找到。")

        # 从源数据对象提取信息来填充收藏内容，仅当对应字段在 content_data 中为 None (且未被直接上传文件填充) 时才进行填充
        if final_title is None:
            final_title = getattr(source_item, 'title', None) or getattr(source_item, 'name',
                                                                         None) or f"{content_data.shared_item_type} #{content_data.shared_item_id}"

        if final_content is None:
            final_content = getattr(source_item, 'description', None) or getattr(source_item, 'content', None)

        # 从 source_item 提取 URL
        if final_url is None:  # 只有当用户没有明确提供 URL 且没有直接上传文件时才从共享项中提取
            if hasattr(source_item, 'url') and source_item.url:
                final_url = source_item.url
            # For ChatMessage, check media_url
            elif hasattr(source_item,
                         'media_url') and source_item.media_url and content_data.shared_item_type == "chat_message":
                final_url = source_item.media_url
            # For KnowledgeDocument, file_path is the OSS URL
            elif hasattr(source_item, 'file_path') and source_item.file_path and content_data.shared_item_type in [
                "knowledge_document", "course_material"]:
                final_url = source_item.file_path  # file_path is now the OSS URL

        if final_author is None:
            if hasattr(source_item, 'owner') and source_item.owner and hasattr(source_item.owner, 'name'):
                final_author = source_item.owner.name
            elif hasattr(source_item, 'creator') and source_item.creator and hasattr(source_item.creator, 'name'):
                final_author = source_item.creator.name
            elif hasattr(source_item, 'author') and source_item.author and hasattr(source_item.author, 'name'):
                final_author = source_item.author.name
            elif hasattr(source_item, 'sender') and source_item.sender and hasattr(source_item.sender,
                                                                                   'name'):  # chat_message
                final_author = source_item.sender.name

        if final_tags is None:
            final_tags = getattr(source_item, 'tags', None)

        # 自动确定收藏类型，仅当 final_type 为 None 时才进行自动推断
        if final_type is None:  # 只有在 content_data.type 为 None (且没有直接上传文件) 时才推断
            if content_data.shared_item_type == "chat_message" and final_url:
                if "image/" in (getattr(source_item, 'message_type', '') or getattr(source_item, 'media_url',
                                                                                    '') or '').lower() or re.match(
                    r"(https?://.*\.(?:png|jpg|jpeg|gif|webp|bmp))", final_url, re.IGNORECASE):
                    final_type = "image"
                elif "video/" in (getattr(source_item, 'message_type', '') or getattr(source_item, 'media_url',
                                                                                      '') or '').lower() or re.match(
                    r"(https?://.*\.(?:mp4|avi|mov|mkv))", final_url, re.IGNORECASE):
                    final_type = "video"
                elif final_url.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):  # 常见文档格式
                    final_type = "document"  # Use 'document' for general files
                elif final_url:  # Everything else with a URL is a link
                    final_type = "link"
                else:  # Fallback for text-only chat messages
                    final_type = "text"
            elif content_data.shared_item_type in ["knowledge_document", "course_material"]:
                if (hasattr(source_item, 'file_type') and source_item.file_type and source_item.file_type.startswith(
                        'image/')) or \
                        (hasattr(source_item, 'type') and source_item.type == 'image'):
                    final_type = "image"
                elif (hasattr(source_item, 'file_type') and source_item.file_type and source_item.file_type.startswith(
                        'video/')) or \
                        (hasattr(source_item, 'type') and source_item.type == 'video'):
                    final_type = "video"
                elif (hasattr(source_item,
                              'file_type') and source_item.file_type and not source_item.file_type.startswith(
                    'text/plain')) or \
                        (hasattr(source_item, 'type') and source_item.type == 'file'):
                    final_type = "file"  # Fallback to generic_file or document
                elif (hasattr(source_item, 'type') and source_item.type == 'link'):
                    final_type = "link"
                else:  # Fallback for documents content or text material
                    final_type = "document"  # Use 'document' for general documents/text assets
            elif content_data.shared_item_type in ["project", "course", "forum_topic", "note", "daily_record",
                                                   "knowledge_article"]:
                final_type = content_data.shared_item_type  # 例如：type="project", type="course"
            else:
                final_type = "text"  # 兜底，如果没有明确类型，默认文本

        # 对于文件大小和持续时间，优先使用传入的content_data，否则从source_item获取
        if final_file_size is None and hasattr(source_item, 'size_bytes'):
            final_file_size = getattr(source_item, 'size_bytes')
        if final_duration is None and hasattr(source_item, 'duration'):
            final_duration = getattr(source_item, 'duration')
        if final_thumbnail is None:
            final_thumbnail = getattr(source_item, 'thumbnail', None) or getattr(source_item, 'cover_image_url', None)

    else:  # 如果不是共享内部资源，也不是直接上传文件，则使用用户提交的 title, type, url, content
        if final_type is None: final_type = "text"  # 如果没有提供共享项，且未指定类型，默认为文本

    # 如果此时 final_title 依然为空，进行最后兜底
    if not final_title:
        if final_type == "text" and final_content:
            final_title = final_content[:30] + "..." if len(final_content) > 30 else final_content
        elif final_type == "link" and final_url:  # Changed from "url" to "link"
            final_title = final_url
        elif final_type in ["file", "image", "video"] and (uploaded_file_original_filename or content_data.title):
            final_title = uploaded_file_original_filename or content_data.title
        elif content_data.shared_item_type and content_data.shared_item_id:
            final_title = f"{content_data.shared_item_type.capitalize()} #{content_data.shared_item_id}"  # 兜底标题格式
        else:
            final_title = "无标题收藏"

    # 3. 组合文本用于嵌入 (现在使用最终确定的值)
    combined_text_for_embedding = ". ".join(filter(None, [
        _get_text_part(final_title),
        _get_text_part(final_content),
        _get_text_part(final_url),
        _get_text_part(final_tags),
        _get_text_part(final_type),
        _get_text_part(final_author)
    ])).strip()

    embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量

    # 获取当前用户的LLM配置用于嵌入生成
    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    user_llm_api_key = None
    user_llm_type = None
    user_llm_base_url = None
    user_llm_model_id = None

    if current_user_obj.llm_api_type == "siliconflow" and current_user_obj.llm_api_key_encrypted:
        try:
            user_llm_api_key = ai_core.decrypt_key(current_user_obj.llm_api_key_encrypted)
            user_llm_type = current_user_obj.llm_api_type
            user_llm_base_url = current_user_obj.llm_api_base_url
            # 优先使用新的多模型配置，fallback到原模型ID
            user_llm_model_id = ai_core.get_user_model_for_provider(
                current_user_obj.llm_model_ids,
                current_user_obj.llm_api_type,
                current_user_obj.llm_model_id
            )
            print(f"DEBUG_EMBEDDING_KEY: 使用收藏创建者配置的硅基流动 API 密钥为收藏内容生成嵌入。")
        except Exception as e:
            print(
                f"WARNING_COLLECTION_EMBEDDING: 解密用户 {current_user_id} LLM API密钥失败: {e}. 收藏内容嵌入将使用零向量或默认行为。")
            user_llm_api_key = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 收藏创建者未配置硅基流动 API 类型或密钥，收藏内容嵌入将使用零向量或默认行为。")

    if combined_text_for_embedding:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text_for_embedding],
                api_key=user_llm_api_key,
                llm_type=user_llm_type,
                llm_base_url=user_llm_base_url,
                llm_model_id=user_llm_model_id
            )
            if new_embedding:
                embedding = new_embedding[0]
            print(f"DEBUG: 收藏内容嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成收藏内容嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 收藏内容 combined_text 为空，嵌入向量设为零。")

    # 4. 创建数据库记录
    db_item = CollectedContent(
        owner_id=current_user_id,
        folder_id=final_folder_id,
        title=final_title,
        type=final_type,
        url=final_url,
        content=final_content,
        tags=final_tags,
        priority=content_data.priority,
        notes=content_data.notes,
        is_starred=content_data.is_starred,
        thumbnail=final_thumbnail,
        author=final_author,
        duration=final_duration,
        file_size=final_file_size,
        status=final_status,

        shared_item_type=content_data.shared_item_type,
        shared_item_id=content_data.shared_item_id,

        combined_text=combined_text_for_embedding,
        embedding=embedding
    )

    db.add(db_item)
    try:
        db.commit()
        db.refresh(db_item)
        return db_item
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建收藏内容发生完整性约束错误: {e}")
        # Rollback logic for uploaded file if DB commit fails
        if uploaded_file_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(uploaded_file_object_name))
            print(
                f"DEBUG_COLLECTED_CONTENT: DB commit failed, attempting to delete OSS file: {uploaded_file_object_name}")
        if "_owner_shared_item_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="此内容已被您收藏。")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建收藏内容失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        # Rollback logic for uploaded file if any other error
        if uploaded_file_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(uploaded_file_object_name))
            print(f"DEBUG_COLLECTED_CONTENT: Unknown error, attempting to delete OSS file: {uploaded_file_object_name}")
        print(f"ERROR_DB: 创建收藏内容发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建收藏内容失败: {e}")


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


# --- 辅助函数：安全地获取文本部分 ---
def _get_text_part(value: Any) -> str:
    """
    Helper to get string from potentially None, empty string, datetime, or int/float
    Ensures that values used in combined_text are non-empty strings.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")  # 格式化日期，只保留年月日
    if isinstance(value, (int, float)):
        # 因为这个函数是通用的，不是所有数字都代表小时
        return str(value)
    return str(value).strip() if str(value).strip() else ""


# --- 搜索引擎配置管理接口 ---
@app.post("/search-engine-configs/", response_model=schemas.UserSearchEngineConfigResponse,
          summary="创建新的搜索引擎配置")
async def create_search_engine_config(
        config_data: schemas.UserSearchEngineConfigCreate,
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建搜索引擎配置: {config_data.name}")

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
    encrypted_key = ai_core.encrypt_key(config_data.api_key)

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

    print(f"DEBUG: 用户 {current_user_id} 的搜索引擎配置 '{db_config.name}' (ID: {db_config.id}) 创建成功。")
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
        config.api_key = None
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
        config_id: int,  # 从路径中获取配置ID
        config_data: schemas.UserSearchEngineConfigBase,  # 用于更新的数据
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 更新搜索引擎配置 ID: {config_id}。")
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
            db_config.api_key_encrypted = ai_core.encrypt_key(update_data["api_key"])
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

    print(f"DEBUG: 搜索引擎��置 {config_id} 更新成功。")
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
        search_request: schemas.WebSearchRequest,
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


# --- 用户TTS配置管理接口 ---
@app.post("/users/me/tts_configs", response_model=UserTTSConfigResponse, summary="为当前用户创建新的TTS配置")
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
            encrypted_key = ai_core.encrypt_key(tts_config_data.api_key)
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


@app.get("/users/me/tts_configs", response_model=List[UserTTSConfigResponse], summary="获取当前用户的所有TTS配置")
async def get_user_tts_configs(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 获取用户 {current_user_id} 的所有TTS配置。")
    tts_configs = db.query(UserTTSConfig).filter(UserTTSConfig.owner_id == current_user_id).all()
    return tts_configs


@app.get("/users/me/tts_configs/{config_id}", response_model=UserTTSConfigResponse, summary="获取指定TTS配置详情")
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


@app.put("/users/me/tts_configs/{config_id}", response_model=UserTTSConfigResponse, summary="更新指定TTS配置")
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
            db_tts_config.api_key_encrypted = ai_core.encrypt_key(update_data["api_key"])
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


@app.delete("/users/me/tts_configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除指定TTS配置")
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


@app.put("/users/me/tts_configs/{config_id}/set_active", response_model=UserTTSConfigResponse,
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
        oss_object_name: str,
        file_type: str,
        db_session: Session  # 传入会话
):
    """
    在后台处理上传的文档：提取文本、分块、生成嵌入并存储。
    文件从OSS下载后处理，而不是从本地文件系统读取。
    """
    print(f"DEBUG_DOC_PROCESS: 开始后台处理文档 ID: {document_id}")
    loop = asyncio.get_running_loop()
    db_document = None  # 初始化 db_document, 防止在try块中它未被赋值而finally块需要用
    try:
        # 获取文档对象 (需要在新的会话中获取，因为这是独立的任务)
        db_document = db_session.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
        if not db_document:
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 在后台处理中未找到。")
            return

        db_document.status = "processing"
        db_document.processing_message = "正在从云存储下载文件..."
        db_session.add(db_document)
        db_session.commit()

        # 从OSS下载文件内容
        downloaded_bytes = await oss_utils.download_file_from_oss(oss_object_name)
        if not downloaded_bytes:  # 如果下载失败或文件内容为空
            db_document.status = "failed"
            db_document.processing_message = "从云存储下载文件失败或文件内容为空。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 从OSS下载失败或内容为空。")
            return

        db_document.processing_message = "正在提取文本..."
        db_session.add(db_document)
        db_session.commit()

        # 1. 提取文本
        # 传递文件内容的字节流给 ai_core.extract_text_from_document
        extracted_text = await loop.run_in_executor(
            None,  # 使用默认的线程池执行器
            ai_core.extract_text_from_document,  # 要执行的同步函数
            downloaded_bytes,  # 传递字节流
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
        # 获取文档所有者（知识库的owner）的LLM配置进行嵌入生成
        document_owner = db_session.query(Student).filter(Student.id == owner_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if document_owner and document_owner.llm_api_type == "siliconflow" and document_owner.llm_api_key_encrypted:
            try:
                owner_llm_api_key = ai_core.decrypt_key(document_owner.llm_api_key_encrypted)
                owner_llm_type = document_owner.llm_api_type
                owner_llm_base_url = document_owner.llm_api_base_url
                # 优先使用新的多模型配置，fallback到原模型ID
                owner_llm_model_id = ai_core.get_user_model_for_provider(
                    document_owner.llm_model_ids,
                    document_owner.llm_api_type,
                    document_owner.llm_model_id
                )
                print(f"DEBUG_EMBEDDING_KEY_DOC: 使用文档拥有者配置的硅基流动 API 密钥为文档生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY_DOC: 解密文档拥有者硅基流动 API 密钥失败: {e}。文档嵌入将使用零向量。")
        else:
            print(f"DEBUG_EMBEDDING_KEY_DOC: 文档拥有者未配置硅基流动 API 类型或密钥，文档嵌入将使用零向量或默认行为。")

        all_embeddings = await ai_core.get_embeddings_from_api(
            chunks,
            api_key=owner_llm_api_key,
            llm_type=owner_llm_type,
            llm_base_url=owner_llm_base_url,
            llm_model_id=owner_llm_model_id
        )

        if not all_embeddings or len(all_embeddings) != len(chunks):
            db_document.status = "failed"
            db_document.processing_message = "嵌入生成失败或数量不匹配。请检查您的LLM配置。"
            db_session.add(db_document)
            db_session.commit()
            print(f"ERROR_DOC_PROCESS: 文档 {document_id} 嵌入生成失败或数量不匹配。")
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

        db_session.commit()  # 提交所有文本块

        # 4. 更新文档状态
        db_document.status = "completed"
        db_document.processing_message = f"文档处理完成，共 {len(chunks)} 个文本块。"
        db_document.total_chunks = len(chunks)
        db_session.add(db_document)
        db_session.commit()
        print(f"DEBUG_DOC_PROCESS: 文档 {document_id} 处理完成，{len(chunks)} 个块已嵌入。")

    except Exception as e:
        print(f"ERROR_DOC_PROCESS: 后台处理文档 {document_id} 发生未预期错误: {type(e).__name__}: {e}")
        # 尝试更新文档状态为失败
        if db_document:  # 仅当 db_document 已经被正确赋值后才尝试更新其状态
            try:
                db_document.status = "failed"
                db_document.processing_message = f"处理失败: {e}"
                db_session.add(db_document)
                db_session.commit()
            except Exception as update_e:
                print(f"CRITICAL_ERROR: 无法更新文档 {document_id} 的失败状态: {update_e}")
    finally:
        db_session.close()  # 确保会话关闭


async def process_ai_temp_file_in_background(
        temp_file_id: int,
        user_id: int,  # 需要用户ID来获取其LLM配置
        oss_object_name: str,
        file_type: str,
        db_session: Session  # 传入会话
):
    """
    在后台处理AI对话的临时上传文件：从OSS下载、提取文本、生成嵌入并更新记录。
    """
    print(f"DEBUG_AI_TEMP_FILE_PROCESS: 开始后台处理AI临时文件 ID: {temp_file_id} (OSS: {oss_object_name})")
    loop = asyncio.get_running_loop()
    db_temp_file_record = None  # 初始化，防止在try块中它未被赋值而finally块需要用

    try:
        print(f"DEBUG_AI_TEMP_FILE_PROCESS: 步骤1 - 获取数据库记录...")
        # 获取临时文件记录 (需要在新的会话中获取，因为这是独立的任务)
        db_temp_file_record = db_session.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id == temp_file_id).first()
        if not db_temp_file_record:
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 在后台处理中未找到。")
            return

        print(f"DEBUG_AI_TEMP_FILE_PROCESS: 步骤2 - 更新状态为processing...")
        db_temp_file_record.status = "processing"
        db_temp_file_record.processing_message = "正在从云存储下载文件..."
        db_session.add(db_temp_file_record)
        db_session.commit()  # 立即提交状态更新，让前端能看到

        # 从OSS下载文件内容
        print(f"DEBUG_AI_TEMP_FILE_PROCESS: 开始从OSS下载文件: {oss_object_name}")
        try:
            downloaded_bytes = await oss_utils.download_file_from_oss(oss_object_name)
            if not downloaded_bytes:
                db_temp_file_record.status = "failed"
                db_temp_file_record.processing_message = "从云存储下载文件失败或文件内容为空。"
                db_session.add(db_temp_file_record)
                db_session.commit()
                print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 从OSS下载失败或内容为空。")
                return
            print(f"DEBUG_AI_TEMP_FILE_PROCESS: OSS下载成功，文件大小: {len(downloaded_bytes)} 字节")
        except Exception as oss_error:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = f"OSS下载失败: {oss_error}"
            db_session.add(db_temp_file_record)
            db_session.commit()
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} OSS下载异常: {oss_error}")
            return

        db_temp_file_record.processing_message = "正在提取文本..."
        db_session.add(db_temp_file_record)
        db_session.commit()

        # 1. 提取文本 (注意：ai_core.extract_text_from_document 是同步的，需要在线程池中运行)
        try:
            extracted_text = await loop.run_in_executor(
                None,  # 使用默认的线程池执行器
                ai_core.extract_text_from_document,  # 要执行的同步函数
                downloaded_bytes,
                file_type
            )
            print(
                f"DEBUG_AI_TEMP_FILE_PROCESS: 文件 {temp_file_id} 文本提取成功，长度: {len(extracted_text) if extracted_text else 0}")
        except Exception as extract_error:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = f"文本提取失败: {extract_error}"
            db_session.add(db_temp_file_record)
            db_session.commit()
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 文本提取异常: {extract_error}")
            return

        if not extracted_text:
            db_temp_file_record.status = "failed"
            db_temp_file_record.processing_message = "文本提取失败或文件内容为空。"
            db_session.add(db_temp_file_record)
            db_session.commit()
            print(f"ERROR_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 文本提取失败。")
            return

        # 2. 生成嵌入 (需要获取用户的LLM配置)
        user_obj = db_session.query(Student).filter(Student.id == user_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if user_obj and user_obj.llm_api_type == "siliconflow" and user_obj.llm_api_key_encrypted:
            try:
                owner_llm_api_key = ai_core.decrypt_key(user_obj.llm_api_key_encrypted)
                owner_llm_type = user_obj.llm_api_type
                owner_llm_base_url = user_obj.llm_api_base_url
                # 优先使用新的多模型配置，fallback到原模型ID
                owner_llm_model_id = ai_core.get_user_model_for_provider(
                    user_obj.llm_model_ids,
                    user_obj.llm_api_type,
                    user_obj.llm_model_id
                )
                print(
                    f"DEBUG_AI_TEMP_FILE_EMBEDDING_KEY: 使用用户 {user_id} 配置的硅基流动 API 密钥为临时文件生成嵌入。")
            except Exception as e:
                print(
                    f"ERROR_AI_TEMP_FILE_EMBEDDING_KEY: 解密用户 {user_id} 硅基流动 API 密钥失败: {e}。临时文件嵌入将使用零向量或默认行为。")
                # 即使解密失败，也跳过，使用默认的零向量
        else:
            print(
                f"DEBUG_AI_TEMP_FILE_EMBEDDING_KEY: 用户 {user_id} 未配置硅基流动 API 类型或密钥，临时文件嵌入将使用零向量或默认行为。")

        db_temp_file_record.processing_message = "正在生成嵌入向量..."
        db_session.add(db_temp_file_record)
        db_session.commit()

        try:
            embeddings_list = await ai_core.get_embeddings_from_api(
                [extracted_text],  # 传入提取的文本
                api_key=owner_llm_api_key,
                llm_type=owner_llm_type,
                llm_base_url=owner_llm_base_url,
                llm_model_id=owner_llm_model_id
            )
            print(f"DEBUG_AI_TEMP_FILE_PROCESS: 文件 {temp_file_id} 嵌入生成成功")
        except Exception as embedding_error:
            print(f"WARNING_AI_TEMP_FILE_PROCESS: 文件 {temp_file_id} 嵌入生成失败: {embedding_error}，使用零向量")
            embeddings_list = []

        final_embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if embeddings_list and len(embeddings_list) > 0:
            final_embedding = embeddings_list[0]
        else:
            print(f"WARNING_AI_TEMP_FILE_EMBEDDING: 临时文件 {temp_file_id} 嵌入生成失败或返回空，使用零向量。")

        # 3. 更新数据库记录
        db_temp_file_record.extracted_text = extracted_text
        db_temp_file_record.embedding = final_embedding
        db_temp_file_record.status = "completed"
        db_temp_file_record.processing_message = "文件处理完成，文本已提取，嵌入已生成。"
        db_session.add(db_temp_file_record)
        db_session.commit()
        print(
            f"DEBUG_AI_TEMP_FILE_PROCESS: AI临时文件 {temp_file_id} 处理完成。提取文本长度: {len(extracted_text)} 字符")
        print(
            f"DEBUG_AI_TEMP_FILE_PROCESS: 文本内容预览: {extracted_text[:200]}..." if extracted_text else "DEBUG_AI_TEMP_FILE_PROCESS: 提取的文本为空")

    except Exception as e:
        print(f"ERROR_AI_TEMP_FILE_PROCESS: 后台处理AI临时文件 {temp_file_id} 发生未预期错误: {type(e).__name__}: {e}")
        # 尝试更新文档状态为失败
        if db_temp_file_record:
            try:
                db_temp_file_record.status = "failed"
                db_temp_file_record.processing_message = f"处理失败: {e}"
                db_session.add(db_temp_file_record)
                db_session.commit()
            except Exception as update_e:
                print(f"CRITICAL_ERROR: 无法更新AI临时文件 {temp_file_id} 的失败状态: {update_e}")
    finally:
        db_session.close()  # 确保会话关闭


# --- 用户认证与管理接口 ---
@app.post("/register", response_model=schemas.StudentResponse, summary="用户注册")
async def register_user(
        user_data: schemas.StudentCreate,
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 尝试注册用户。邮箱: {user_data.email}, 手机号: {user_data.phone_number}")

    # 1. 检查邮箱和手机号的唯一性
    if user_data.email:
        existing_user_email = db.query(Student).filter(Student.email == user_data.email).first()
        if existing_user_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被注册。")

    if user_data.phone_number:
        existing_user_phone = db.query(Student).filter(Student.phone_number == user_data.phone_number).first()
        if existing_user_phone:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="手机号已被注册。")

    # 2. 处理用户名: 如果用户未提供，则自动生成一个唯一用户名
    final_username = user_data.username
    if not final_username:
        unique_username_found = False
        attempts = 0
        max_attempts = 10
        while not unique_username_found and attempts < max_attempts:
            random_suffix = secrets.token_hex(4)
            proposed_username = f"新用户_{random_suffix}"
            if not db.query(Student).filter(Student.username == proposed_username).first():
                final_username = proposed_username
                unique_username_found = True
            attempts += 1

        if not unique_username_found:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="无法生成唯一用户名，请稍后再试或提供一个自定义用户名。")
        print(f"DEBUG: 用户未提供用户名，自动生成唯一用户名: {final_username}")
    else:
        existing_user_username = db.query(Student).filter(Student.username == final_username).first()
        if existing_user_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被使用。")

    # 哈希密码
    hashed_password = pwd_context.hash(user_data.password)

    # 处理 skills 字段
    skills_list_for_db = []
    if user_data.skills:
        skills_list_for_db = [skill.model_dump() for skill in user_data.skills]

    user_skills_text = ""
    if skills_list_for_db:
        user_skills_text = ", ".join(
            [s.get("name", "") for s in skills_list_for_db if isinstance(s, dict) and s.get("name")])

    combined_text_content = ". ".join(filter(None, [
        _get_text_part(user_data.name),
        _get_text_part(user_data.major),
        _get_text_part(user_skills_text),
        _get_text_part(user_data.interests),
        _get_text_part(user_data.bio),
        _get_text_part(user_data.awards_competitions),
        _get_text_part(user_data.academic_achievements),
        _get_text_part(user_data.soft_skills),
        _get_text_part(user_data.portfolio_link),
        _get_text_part(user_data.preferred_role),
        _get_text_part(user_data.availability),
        _get_text_part(user_data.location)
    ])).strip()

    if not combined_text_content:
        combined_text_content = f"{user_data.name if user_data.name else final_username} 的简介。"

    print(f"DEBUG_REGISTER: 为用户 '{final_username}' 生成 combined_text: '{combined_text_content[:100]}...'")

    embedding = None
    if combined_text_content:
        try:
            # 对于新注册用户，LLM配置最初是空的。ai_core.get_embeddings_from_api会返回零向量。
            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text_content],
                api_key=None,  # 新注册用户未配置密钥
                llm_type=None,  # 新注册用户未配置LLM类型
                llm_base_url=None,
                llm_model_id=None
            )
            if new_embedding:  # ai_core现在会在没有有效key时返回零向量的List
                embedding = new_embedding[0]
            print(f"DEBUG_REGISTER: 用户嵌入向量已生成。")  # 此时应是零向量
        except Exception as e:
            print(f"ERROR_REGISTER: 生成用户嵌入向量失败: {e}")
    else:
        print(f"WARNING_REGISTER: 用户的 combined_text 为空，无法生成嵌入向量。")

    db_user = Student(
        email=user_data.email,
        phone_number=user_data.phone_number,
        password_hash=hashed_password,
        username=final_username,
        school=user_data.school,

        name=user_data.name if user_data.name else final_username,
        major=user_data.major if user_data.major else "未填写",
        skills=skills_list_for_db,
        interests=user_data.interests if user_data.interests else "未填写",
        bio=user_data.bio if user_data.bio else "欢迎使用本平台！",

        awards_competitions=user_data.awards_competitions,
        academic_achievements=user_data.academic_achievements,
        soft_skills=user_data.soft_skills,
        portfolio_link=user_data.portfolio_link,
        preferred_role=user_data.preferred_role,
        availability=user_data.availability,
        location=user_data.location,

        combined_text=combined_text_content,
        embedding=embedding,

        llm_api_type=None,
        llm_api_key_encrypted=None,
        llm_api_base_url=None,
        llm_model_id=None,
        is_admin=False
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    if isinstance(db_user.skills, str):
        try:
            db_user.skills = json.loads(db_user.skills)
            print(f"DEBUG_REGISTER: 强制转换 db_user.skills 为列表。")
        except json.JSONDecodeError as e:
            print(f"ERROR_REGISTER: 转换为列表失败，JSON解码错误: {e}")
            db_user.skills = []
    elif db_user.skills is None:
        db_user.skills = []

    print(f"DEBUG_REGISTER: db_user.skills type: {type(db_user.skills)}, content: {db_user.skills}")
    print(
        f"DEBUG: 用户 {db_user.email if db_user.email else db_user.phone_number} (ID: {db_user.id}) 注册成功。用户名: {db_user.username}")
    return db_user


@app.post("/token", response_model=schemas.Token, summary="用户登录并获取JWT令牌")
async def login_for_access_token(
        form_data: OAuth2PasswordRequestForm = Depends(),  # 使用 OAuth2PasswordRequestForm 适应标准登录表单
        db: Session = Depends(get_db)
):
    """
    通过邮箱或手机号或手机号和密码获取 JWT 访问令牌。
    - username (实际上可以是邮箱或手机号): 用户邮箱或手机号
    - password: 用户密码
    """
    credential = form_data.username  # 获取用户输入的凭证 (邮箱或手机号)
    password = form_data.password

    print(f"DEBUG_AUTH: 尝试用户登录: {credential}")

    user = None
    # 尝试通过邮箱或手机号查找用户
    if "@" in credential:
        user = db.query(Student).filter(Student.email == credential).first()
        print(f"DEBUG_AUTH: 尝试通过邮箱 '{credential}' 查找用户。")
    elif credential.isdigit() and len(credential) >= 7 and len(credential) <= 15:  # 假设手机号是纯数字且合理长度
        user = db.query(Student).filter(Student.phone_number == credential).first()
        print(f"DEBUG_AUTH: 尝试通过手机号 '{credential}' 查找用户。")
    else:
        print(f"DEBUG_AUTH: 凭证 '{credential}' 格式不正确，登录失败。")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不正确的邮箱/手机号或密码",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 密码验证
    if not user or not pwd_context.verify(password, user.password_hash):
        print(f"DEBUG_AUTH: 用户 '{credential}' 登录失败：不正确的邮箱/手机号或密码。")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="不正确的邮箱/手机号或密码",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 每日登录打卡和积分奖励逻辑
    # 获取用户最初的积分和登录次数，用于对比和调试
    initial_total_points = user.total_points
    initial_login_count = user.login_count

    # 检查是否需要每日打卡奖励
    today = date.today()
    if user.last_login_at is None or user.last_login_at.date() < today:
        daily_points = 10  # 每日登录奖励积分
        # _award_points 现在只往 session 里 add，不 commit
        await _award_points(
            db=db,
            user=user,  # 传递会话中的 user 对象
            amount=daily_points,
            reason="每日登录打卡",
            transaction_type="EARN",
            related_entity_type="login_daily"
        )
        user.last_login_at = func.now()  # 更新上次登录时间
        user.login_count += 1  # 增加登录计数
        # db.add(user) # user对象已经在session中被跟踪和修改，无需再次add了

        print(
            f"DEBUG_LOGIN_PENDING: 用户 {user.id} 成功完成每日打卡，获得 {daily_points} 积分。总登录天数: {user.login_count} (待提交)")

        # 触发成就检查 (例如，总登录次数类的成就)
        # _check_and_award_achievements 也会将对象 add 到 session
        await _check_and_award_achievements(db, user.id)
    else:
        print(f"DEBUG_LOGIN: 用户 {user.id} 今日已打卡。")

    # 登录成功，创建访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )

    # 显式提交事务，并确保总积分在提交后更新
    try:
        db.commit()  # 提交所有待处理的数据库更改（包括 User, PointTransaction, UserAchievement）
        # db.refresh(user) 不再在这里 refresh，避免状态覆盖

        # 在所有更改提交后，重新从数据库载入 user 对象，确保准确显示最终的 total_points
        # 这确保我们看到的是所有奖励（包括成就奖励）都生效后的总积分。
        final_user_state = db.query(Student).filter(Student.id == user.id).first()
        if final_user_state:
            print(
                f"DEBUG_AUTH_FINAL: 用户 {final_user_state.email if final_user_state.email else final_user_state.phone_number} (ID: {final_user_state.id}) 登录成功，颁发JWT令牌。**最终积分: {final_user_state.total_points}, 登录次数: {final_user_state.login_count}**")
            # 可以在这里验证一下是否有新成就
            earned_achievements_count = db.query(UserAchievement).filter(
                UserAchievement.user_id == final_user_state.id).count()
            print(f"DEBUG_AUTH_FINAL: 用户 {final_user_state.id} 现有成就数量: {earned_achievements_count}")
        else:
            print(f"WARNING_AUTH_FINAL: 无法在提交后重新加载用户 {user.id} 的最终状态。")

        return schemas.Token(
            access_token=access_token,
            token_type="bearer",
            expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    except Exception as e:
        db.rollback()  # 如果提交过程中发生任何错误，回滚事务
        print(f"ERROR_LOGIN_COMMIT: 用户 {user.id} 登录事务提交失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录成功但数据保存失败，请重试或联系管理员。",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/users/me", response_model=schemas.StudentResponse, summary="获取当前登录用户详情")
async def read_users_me(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """
    获取当前登录用户的详细信息，包括其完成的项目和课程数量。
    """
    print(f"DEBUG: 获取当前用户 ID: {current_user_id} 的详情。")
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # 计算用户完成的项目和课程数量
    completed_projects_count = db.query(Project).filter(
        Project.creator_id == current_user_id,
        Project.project_status == "已完成"
    ).count()

    completed_courses_count = db.query(UserCourse).filter(
        UserCourse.student_id == current_user_id,
        UserCourse.status == "completed"
    ).count()

    # 从 ORM 对象创建 StudentResponse 的基本实例，这将负责映射所有已存在的字段
    response_data = schemas.StudentResponse.model_validate(user, from_attributes=True)

    # 手动填充计算出的字段
    response_data.completed_projects_count = completed_projects_count
    response_data.completed_courses_count = completed_courses_count

    print(
        f"DEBUG: 用户 {current_user_id} 详情查询完成。完成项目: {completed_projects_count}, 完成课程: {completed_courses_count}。")
    return response_data


@app.put("/users/me", response_model=schemas.StudentResponse, summary="更新当前登录用户详情")
async def update_users_me(
        student_update_data: schemas.StudentUpdate,
        current_user_id: str = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)

    print(f"DEBUG: 更新用户 ID: {current_user_id_int} 的信息。")
    db_student = db.query(Student).filter(Student.id == current_user_id_int).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = student_update_data.dict(exclude_unset=True)

    # --- 1. 特殊处理 username 的唯一性检查和更新 ---
    if "username" in update_data and update_data["username"] is not None:
        new_username = update_data["username"]
        if new_username != db_student.username:
            existing_user_with_username = db.query(Student).filter(
                Student.username == new_username,
                Student.id != current_user_id_int
            ).first()
            if existing_user_with_username:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被其他用户使用。")
        db_student.username = new_username
        print(f"DEBUG: 用户 {current_user_id_int} 用户名更新为: {new_username}")
        del update_data["username"]

    # --- 2. 特殊处理 phone_number 的唯一性检查和更新 ---
    if "phone_number" in update_data:
        new_phone_number = update_data["phone_number"]
        if new_phone_number is not None and new_phone_number != db_student.phone_number:
            existing_user_with_phone = db.query(Student).filter(
                Student.phone_number == new_phone_number,
                Student.id != current_user_id_int
            ).first()
            if existing_user_with_phone:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="手机号已被其他用户使用。")
        db_student.phone_number = new_phone_number
        print(f"DEBUG: 用户 {current_user_id_int} 手机号更新为: {new_phone_number}")
        del update_data["phone_number"]

    # --- 3. 特殊处理 skills 字段的更新 ---
    if "skills" in update_data:
        new_skills_data_for_db = update_data["skills"]
        db_student.skills = new_skills_data_for_db
        print(f"DEBUG: 用户 {current_user_id_int} 技能更新为: {db_student.skills}")
        del update_data["skills"]

    # --- 4. 通用循环处理其余字段 (例如 school, name, major, location 等) ---
    for key, value in update_data.items():
        if hasattr(db_student, key) and value is not None:
            setattr(db_student, key, value)
            print(f"DEBUG: 更新字段 {key}: {value}")
        elif hasattr(db_student, key) and value is None:
            if key in ["major", "school", "interests", "bio", "awards_competitions",
                       "academic_achievements", "soft_skills", "portfolio_link",
                       "preferred_role", "availability", "name", "location"]:
                setattr(db_student, key, value)
                print(f"DEBUG: 清空字段 {key}")

    # 重建 combined_text
    current_skills_for_text = db_student.skills
    parsed_skills_for_text = []

    if isinstance(current_skills_for_text, str):
        try:
            parsed_skills_for_text = json.loads(current_skills_for_text)
        except json.JSONDecodeError:
            parsed_skills_for_text = []
    elif isinstance(current_skills_for_text, list):
        parsed_skills_for_text = current_skills_for_text
    elif current_skills_for_text is None:
        parsed_skills_for_text = []

    skills_text = ""
    if isinstance(parsed_skills_for_text, list):
        skills_text = ", ".join(
            [s.get("name", "") for s in parsed_skills_for_text if isinstance(s, dict) and s.get("name")])

    db_student.combined_text = ". ".join(filter(None, [
        _get_text_part(db_student.major),
        _get_text_part(skills_text),
        _get_text_part(db_student.interests),
        _get_text_part(db_student.bio),
        _get_text_part(db_student.awards_competitions),
        _get_text_part(db_student.academic_achievements),
        _get_text_part(db_student.soft_skills),
        _get_text_part(db_student.portfolio_link),
        _get_text_part(db_student.preferred_role),
        _get_text_part(db_student.availability),
        _get_text_part(db_student.location)
    ])).strip()

    # 获取用户配置的硅基流动 API 密钥用于生成嵌入向量
    siliconflow_api_key_for_embedding = None
    if db_student.llm_api_type == "siliconflow" and db_student.llm_api_key_encrypted:
        try:
            siliconflow_api_key_for_embedding = ai_core.decrypt_key(db_student.llm_api_key_encrypted)
            print(f"DEBUG_EMBEDDING_KEY: 使用用户配置的硅基流动 API 密钥进行嵌入生成。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密用户硅基流动 API 密钥失败: {e}。将跳过嵌入生成。")
            siliconflow_api_key_for_embedding = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 用户未配置硅基流动 API 类型或密钥，使用默认占位符。")

    # 更新 embedding
    # 确定用于嵌入的API密钥和LLM配置
    user_llm_api_type_for_embedding = db_student.llm_api_type
    user_llm_api_base_url_for_embedding = db_student.llm_api_base_url
    # 优先使用新的多模型配置，fallback到原模型ID
    user_llm_model_id_for_embedding = ai_core.get_user_model_for_provider(
        db_student.llm_model_ids,
        db_student.llm_api_type,
        db_student.llm_model_id
    )
    user_api_key_for_embedding = None

    if db_student.llm_api_key_encrypted:
        try:
            user_api_key_for_embedding = ai_core.decrypt_key(db_student.llm_api_key_encrypted)
            print(f"DEBUG_EMBEDDING_KEY: 使用当前用户配置的LLM API 密钥进行嵌入生成。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密用户LLM API 密钥失败: {e}。将使用零向量。")
            user_api_key_for_embedding = None

    if db_student.combined_text:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [db_student.combined_text],
                api_key=user_api_key_for_embedding,
                llm_type=user_llm_api_type_for_embedding,
                llm_base_url=user_llm_api_base_url_for_embedding,
                llm_model_id=user_llm_model_id_for_embedding  # 尽管 embedding API 不直接用，但传过去更好
            )
            if new_embedding:
                db_student.embedding = new_embedding[0]
                print(f"DEBUG: 用户 {db_student.id} 嵌入向量已更新。")
            else:
                db_student.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保为零向量
        except Exception as e:
            print(f"ERROR: 更新用户 {db_student.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            db_student.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING_EMBEDDING_RECALC: 用户 {current_user_id} 的 combined_text 为空，无法重新计算嵌入向量。")
        if db_student.embedding is None:
            db_student.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db.add(db_student)
    db.commit()
    db.refresh(db_student)

    if isinstance(db_student.skills, str):
        try:
            db_student.skills = json.loads(db_student.skills)
            print(f"DEBUG_UPDATE: 强制转换 db_student.skills 为列表。")
        except json.JSONDecodeError as e:
            print(f"ERROR_UPDATE: 转换为列表失败，JSON解码错误: {e}")
            db_student.skills = []
    elif db_student.skills is None:
        db_student.skills = []

    print(f"DEBUG: 用户 {current_user_id_int} 信息更新成功。")
    return db_student


# --- 用户LLM配置接口 ---
@app.put("/users/me/llm-config", response_model=schemas.StudentResponse, summary="更新当前用户LLM配置")
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
            db_student.llm_model_ids = ai_core.serialize_llm_model_ids(update_data["llm_model_ids"])
            print(f"DEBUG: 用户 {current_user_id} 的多模型ID配置已更新。")
        except Exception as e:
            print(f"ERROR: 序列化多模型ID配置失败: {e}。将保持原有配置。")

    # 处理 API 密钥的更新：加密或清空
    decrypted_new_key: Optional[str] = None  # 用于后面嵌入重计算
    if "llm_api_key" in update_data and update_data["llm_api_key"]:
        try:
            encrypted_key = ai_core.encrypt_key(update_data["llm_api_key"])
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
        effective_llm_model_id = ai_core.get_user_model_for_provider(
            db_student.llm_model_ids,
            db_student.llm_api_type,
            db_student.llm_model_id
        )

        if decrypted_new_key:  # 如果本次更新显式提供了新的明文密钥
            key_for_embedding_recalc = decrypted_new_key
        elif db_student.llm_api_key_encrypted:  # 否则，尝试解密数据库中现有的加密密钥
            try:
                key_for_embedding_recalc = ai_core.decrypt_key(db_student.llm_api_key_encrypted)
            except Exception as e:
                print(
                    f"WARNING_EMBEDDING_RECALC: 解密用户 {current_user_id} 的LLM API Key失败: {e}。嵌入将使用零向量或默认行为。")
                key_for_embedding_recalc = None  # 无法解密则不使用用户密钥

        try:
            # 将用户 LLM 配置的各个参数传入 get_embeddings_from_api
            new_embedding = await ai_core.get_embeddings_from_api(
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
                db_student.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
                print(f"DEBUG_EMBEDDING_RECALC: 嵌入API未返回结果。用户 {current_user_id} 嵌入向量设为零。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_RECALC: 为用户 {current_user_id} 重新计算嵌入向量失败: {e}。嵌入向量设为零。")
            db_student.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING_EMBEDDING_RECALC: 用户 {current_user_id} 的 combined_text 为空，无法重新计算嵌入向量。")
        # 确保embedding字段是有效的向量格式，即使没内容也为零向量
        if db_student.embedding is None:
            db_student.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db.commit()  # 提交所有更改，包括LLM配置更新和新的嵌入向量
    db.refresh(db_student)
    print(f"DEBUG: 用户 {current_user_id} LLM配置及嵌入更新成功。")
    return db_student


@app.get("/llm/available-configs", summary="获取可用的LLM服务商配置信息")
async def get_available_llm_configs():
    """
    获取所有可用的LLM服务商配置信息，包括默认模型和可用模型列表。
    用于前端展示给用户选择。
    """
    configs = ai_core.get_available_llm_configs()
    return {
        "available_providers": configs,
        "description": "每个服务商的可用模型列表，用户可以为每个服务商配置多个模型ID"
    }


@app.get("/users/me/llm-model-ids", summary="获取当前用户的多模型ID配置")
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

    model_ids_dict = ai_core.parse_llm_model_ids(db_student.llm_model_ids)

    # 获取清理后的 fallback_model_id，使用与当前服务商配置一致的逻辑
    fallback_model_id = None
    if db_student.llm_api_type:
        user_models = model_ids_dict.get(db_student.llm_api_type, [])
        if user_models:
            fallback_model_id = user_models[0]
        else:
            # 获取系统默认模型
            available_configs = ai_core.get_available_llm_configs()
            provider_config = available_configs.get(db_student.llm_api_type, {})
            fallback_model_id = provider_config.get("default_model")

    return {
        "llm_model_ids": model_ids_dict,
        "current_provider": db_student.llm_api_type,
        "fallback_model_id": fallback_model_id,  # 兼容性字段，现在使用清理后的模型ID
        "available_providers": ai_core.get_available_llm_configs()
    }


@app.get("/users/me/current-provider-models", summary="获取当前用户LLM服务商的可用模型")
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
    model_ids_dict = ai_core.parse_llm_model_ids(db_student.llm_model_ids)
    user_models = model_ids_dict.get(db_student.llm_api_type, [])

    # 获取系统为该服务商提供的默认模型列表
    available_configs = ai_core.get_available_llm_configs()
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


@app.put("/users/me/llm-model-ids", summary="更新当前用户的多模型ID配置")
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

    try:
        # 验证输入格式
        if not isinstance(model_ids_update, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid format: expected object")

        for provider, models in model_ids_update.items():
            if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid format for provider '{provider}': expected list of strings"
                )

        # 序列化并保存
        db_student.llm_model_ids = ai_core.serialize_llm_model_ids(model_ids_update)
        db.add(db_student)
        db.commit()
        db.refresh(db_student)

        print(f"DEBUG: 用户 {current_user_id} 的多模型ID配置已更新。")

        # 返回更新后的配置
        updated_model_ids = ai_core.parse_llm_model_ids(db_student.llm_model_ids)
        return {
            "message": "模型ID配置更新成功",
            "llm_model_ids": updated_model_ids
        }

    except Exception as e:
        print(f"ERROR: 更新用户 {current_user_id} 多模型ID配置失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新配置失败")


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
async def get_all_projects(current_user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    query = db.query(Project)
    projects = await _get_projects_with_details(query, current_user_id, db)
    print(f"DEBUG: 获取所有项目列表，共 {len(projects)} 个。")
    return projects


@app.get("/projects/{project_id}", response_model=schemas.ProjectResponse, summary="获取指定项目详情")
async def get_project_by_id(project_id: int, current_user_id: int = Depends(get_current_user_id),
                            db: Session = Depends(get_db)):
    """
    获取指定项目详情，包括项目封面信息和关联的项目文件列表。
    项目文件将根据其访问权限和当前用户的项目成员身份进行过滤。
    """
    print(f"DEBUG: 获取项目 ID: {project_id} 的详情。用户 {current_user_id}。")
    # 使用 joinedload 预加载 project_files 及其 uploader，以及 creator 和 likes，避免N+1查询
    project = db.query(Project).options(
        joinedload(Project.project_files).joinedload(ProjectFile.uploader),  # 确保上传者信息被预加载
        joinedload(Project.creator),
        joinedload(Project.likes)
    ).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 填充 creator_name (直接从预加载的 creator 对象获取)
    # 确保 project.creator 不为 None，再访问其 name 属性
    project._creator_name = project.creator.name if project.creator else "未知用户"

    # 填充 is_liked_by_current_user
    project.is_liked_by_current_user = False
    if current_user_id:
        # 由于已经 joinedload 了 project.likes，可以直接在内存中检查点赞关系
        if any(like.owner_id == current_user_id for like in project.likes):
            project.is_liked_by_current_user = True

    # --- 1. 获取项目成员身份（用于文件访问权限判断）---
    is_project_creator = (project.creator_id == current_user_id)
    is_project_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id,
        ProjectMember.status == "active"
    ).first() is not None

    visible_project_files = []
    # 遍历预加载的 project.project_files 列表
    for file_record in project.project_files:
        # 'public' 文件对所有用户可见
        if file_record.access_type == "public":
            # 直接访问预加载的 uploader 关系来获取上传者姓名，避免重复查询
            file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
            visible_project_files.append(file_record)
        # 'member_only' 文件仅对项目创建者或成员可见
        elif file_record.access_type == "member_only":
            if is_project_creator or is_project_member:
                # 直接访问预加载的 uploader 关系来获取上传者姓名
                file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
                visible_project_files.append(file_record)

    # --- 2. 将过滤后的 project_files 列表赋值给 project 对象 ---
    # Pydantic 响应模型会从 ORM 对象的 `project_files` 属性中加载数据
    # 这里我们直接替换 ORM 对象的 `project_files` 列表为过滤后的列表
    project.project_files = visible_project_files

    print(f"DEBUG: 项目 {project_id} 详情查询完成。可见文件数: {len(visible_project_files)}。")
    return project


@app.post("/projects/{project_id}/apply", response_model=schemas.ProjectApplicationResponse, summary="学生申请加入项目")
async def apply_to_project(
        project_id: int,
        application_data: schemas.ProjectApplicationCreate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许学生申请加入指定项目。
    - 如果用户已是项目成员，则无法申请。
    - 如果用户已提交待处理的申请，则无法重复申请。
    """
    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id} 尝试申请加入项目 {project_id}。")

    # 1. 验证项目是否存在
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 2. 检查用户是否已是项目成员
    existing_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id
    ).first()
    if existing_member:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="您已经是该项目的成员，无需申请加入。")

    # 3. 检查是否已有待处理或已拒绝的申请
    existing_application = db.query(ProjectApplication).filter(
        ProjectApplication.project_id == project_id,
        ProjectApplication.student_id == current_user_id
    ).first()

    if existing_application:
        if existing_application.status == "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="您已有待处理的项目申请，请勿重复提交。")
        elif existing_application.status == "approved":
            # 理论上这里不会走到，因为如果 approved 就会成为 ProjectMember
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="您已批准加入该项目，请勿重复申请。")
        elif existing_application.status == "rejected":
            # 如果是已拒绝的申请，可以考虑是返回冲突，还是允许重新申请
            # 这里选择返回冲突，如果需要重新申请，可能由前端引导用户先删除旧申请
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="您有此项目已被拒绝的申请，请联系项目创建者。")

            # 4. 创建新的项目申请
    db_application = ProjectApplication(
        project_id=project_id,
        student_id=current_user_id,
        message=application_data.message,  # 允许 message 为 None
        status="pending"
    )

    db.add(db_application)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 提交项目申请时发生完整性错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="提交申请失败：可能已存在您的申请，或发生并发冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 提交项目申请 {project_id} 失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"提交项目申请失败: {e}")
    db.refresh(db_application)

    # Populate applicant name/email for response
    applicant_user = db.query(Student).filter(Student.id == current_user_id).first()
    if applicant_user:
        db_application.applicant_name = applicant_user.name
        db_application.applicant_email = applicant_user.email
    else:
        db_application.applicant_name = "未知用户"  # 理论上不发生
        db_application.applicant_email = None

    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id} 成功向项目 {project_id} 提交了申请 (ID: {db_application.id})。")
    return db_application


# --- Configuration for Frontend URLs (placeholders for now) ---
# 假设这些是前端应用中显示具体项目、课程、论坛话题详情的路由。
# 这里的路径是API返回给前端的“软链接”路径，前端需要自行拼接 BASE_URL。
FRONTEND_PROJECT_DETAIL_URL_PREFIX = "/projects/"  # 例如，将形成 /projects/123
FRONTEND_COURSE_DETAIL_URL_PREFIX = "/courses/"  # 例如，将形成 /courses/456
FRONTEND_FORUM_TOPIC_DETAIL_URL_PREFIX = "/forum/topics/"  # 例如，将形成 /forum/topics/789


@app.post("/projects/{project_id}/collect", response_model=schemas.CollectedContentResponse, summary="收藏指定项目")
async def collect_project(
        project_id: int,
        collect_data: schemas.CollectItemRequestBase,  # 使用新的通用请求体
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许用户收藏一个项目。\n
    如果用户没有指定 `folder_id`，系统会自动将收藏放入名为“默认文件夹”的文件夹中。\n
    如果没有“默认文件夹”，系统会先自动创建一个。
    """
    print(f"DEBUG_COLLECT: 用户 {current_user_id} 尝试收藏项目 ID: {project_id}")

    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 构造 CollectedContentBase payload，并填充项目特有的信息
    collected_content_data = schemas.CollectedContentBase(
        title=collect_data.title or db_project.title,  # 优先使用用户自定义标题，否则使用项目标题
        type="project",  # 显式设置为“project”类型
        url=f"{FRONTEND_PROJECT_DETAIL_URL_PREFIX}{project_id}",  # 收藏的URL是前端项目详情页URL
        content=db_project.description,  # 将项目描述作为收藏内容
        tags=db_project.keywords,  # 将项目关键词作为标签
        priority=collect_data.priority,  # 沿用请求中提供的优先级
        notes=collect_data.notes,  # 沿用请求中提供的备注
        is_starred=collect_data.is_starred,  # 沿用请求中提供的星标状态
        thumbnail=None,  # 项目Schema中没有直接的缩略图，可根据实际情况填充
        author=db_project.creator.name if db_project.creator else None,  # 获取项目创建者姓名
        shared_item_type="project",  # 标记为收藏的内部类型
        shared_item_id=project_id,  # 标记为收藏的内部ID
        folder_id=collect_data.folder_id  # 文件夹ID将由 _create_collected_content_item_internal 处理
    )

    # 调用核心辅助函数来创建 CollectedContent 记录
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_data)


@app.post("/courses/{course_id}/collect", response_model=schemas.CollectedContentResponse, summary="收藏指定课程")
async def collect_course(
        course_id: int,
        collect_data: schemas.CollectItemRequestBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许用户收藏一个课程。\n
    如果用户没有指定 `folder_id`，系统会自动将收藏放入名为“默认文件夹”的文件夹中。\n
    如果没有“默认文件夹”，系统会先自动创建一个。
    """
    print(f"DEBUG_COLLECT: 用户 {current_user_id} 尝试收藏课程 ID: {course_id}")

    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 重新解析或处理课程的 skills，因为它们在数据库中是 JSONB 格式
    course_required_skills_text = ""
    if db_course.required_skills:
        try:
            # 尝试从JSON字符串解析，如果已经是列表则直接使用
            parsed_skills = json.loads(db_course.required_skills) if isinstance(db_course.required_skills,
                                                                                str) else db_course.required_skills
            if isinstance(parsed_skills, list):
                course_required_skills_text = ", ".join(
                    [skill.get("name", "") for skill in parsed_skills if isinstance(skill, dict) and skill.get("name")])
        except (json.JSONDecodeError, AttributeError):
            course_required_skills_text = ""  # 解析失败时回退

    # 构造 CollectedContentBase payload，并填充课程特有的信息
    collected_content_data = schemas.CollectedContentBase(
        title=collect_data.title or db_course.title,  # 优先使用用户自定义标题，否则使用课程标题
        type="course",  # 显式设置为“course”类型
        url=f"{FRONTEND_COURSE_DETAIL_URL_PREFIX}{course_id}",  # 收藏的URL是前端课程详情页URL
        content=db_course.description + (
            f" 所需技能: {course_required_skills_text}" if course_required_skills_text else ""),  # 将课程描述和技能作为收藏内容
        tags=db_course.category,  # 将课程分类作为标签
        priority=collect_data.priority,  # 沿用请求中提供的优先级
        notes=collect_data.notes,  # 沿用请求中提供的备注
        is_starred=collect_data.is_starred,  # 沿用请求中提供的星标状态
        thumbnail=db_course.cover_image_url,  # 使用课程封面图片作为缩略图
        author=db_course.instructor,  # 使用讲师作为作者
        shared_item_type="course",  # 标记为收藏的内部类型
        shared_item_id=course_id,  # 标记为收藏的内部ID
        folder_id=collect_data.folder_id  # 文件夹ID将由 _create_collected_content_item_internal 处理
    )

    # 调用核心辅助函数来创建 CollectedContent 记录
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_data)


@app.post("/forum/topics/{topic_id}/collect", response_model=schemas.CollectedContentResponse,
          summary="收藏指定论坛话题")
async def collect_forum_topic(
        topic_id: int,
        collect_data: schemas.CollectItemRequestBase,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许用户收藏一个论坛话题。\n
    如果用户没有指定 `folder_id`，系统会自动将收藏放入名为“默认文件夹”的文件夹中。\n
    如果没有“默认文件夹”，系统会先自动创建一个。
    """
    print(f"DEBUG_COLLECT: 用户 {current_user_id} 尝试收藏论坛话题 ID: {topic_id}")

    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="论坛话题未找到。")

    # 构造 CollectedContentBase payload，并填充话题特有的信息
    collected_content_data = schemas.CollectedContentBase(
        title=collect_data.title or db_topic.title or "(无标题)",  # 优先使用用户自定义标题，否则使用话题标题，最后用默认标题
        type="forum_topic",  # 显式设置为“forum_topic”类型
        url=f"{FRONTEND_FORUM_TOPIC_DETAIL_URL_PREFIX}{topic_id}",  # 收藏的URL是前端话题详情页URL
        content=db_topic.content,  # 将话题内容作为收藏内容
        tags=db_topic.tags,  # 将话题标签作为标签
        priority=collect_data.priority,  # 沿用请求中提供的优先级
        notes=collect_data.notes,  # 沿用请求中提供的备注
        is_starred=collect_data.is_starred,  # 沿用请求中提供的星标状态
        thumbnail=db_topic.media_url if db_topic.media_type == "image" else None,  # 如果话题是图片则使用其URL作为缩略图
        author=db_topic.owner.name if db_topic.owner else None,  # 获取话题发布者姓名
        shared_item_type="forum_topic",  # 标记为收藏的内部类型
        shared_item_id=topic_id,  # 标记为收藏的内部ID
        folder_id=collect_data.folder_id  # 文件夹ID将由 _create_collected_content_item_internal 处理
    )

    # 调用核心辅助函数来创建 CollectedContent 记录
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_data)


@app.get("/projects/{project_id}/applications", response_model=List[schemas.ProjectApplicationResponse],
         summary="获取项目所有申请列表")
async def get_project_applications(
        project_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[Literal["pending", "approved", "rejected"]] = None
):

    # --- 新增：强制类型转换为整数 ---
    current_user_id_int = int(current_user_id)
    # --------------------------------

    """
    项目创建者或系统管理员可以获取指定项目的申请列表。
    可根据 status_filter (pending, approved, rejected) 筛选。
    """
    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id} 尝试获取项目 {project_id} 的申请列表。")

    # 1. 验证项目和权限 (只有项目创建者或系统管理员能查看)
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user_obj:  # 理论上不会发生
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

    # --- 开始修改权限检查 ---

    # 检查1: 用户是否为项目创建者
    is_creator = (db_project.creator_id == current_user_id_int)

    # 检查2: 用户是否为系统管理员
    is_system_admin = current_user_obj.is_admin

    # 检查3: 用户是否为该项目的管理员
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id_int,
        ProjectMember.role == 'admin',  # 明确检查角色是否为 'admin'
        ProjectMember.status == 'active'
    ).first()
    is_project_admin = (membership is not None)

    # 只要满足以上任一条件，就授予权限
    if not (is_creator or is_system_admin or is_project_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权查看该项目的申请列表。只有项目创建者、项目管理员或系统管理员可以。")

    if not (db_project.creator_id == current_user_id_int or current_user_obj.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权查看该项目的申请列表。只有项目创建者或系统管理员可以。")

    # 2. 查询申请列表，并预加载申请者信息
    # 使用 joinedload 避免 N+1 查询问题
    query = db.query(ProjectApplication).options(joinedload(ProjectApplication.applicant)).filter(
        ProjectApplication.project_id == project_id
    )
    if status_filter:
        query = query.filter(ProjectApplication.status == status_filter)

    applications = query.order_by(ProjectApplication.applied_at.desc()).all()

    # 3. 填充响应模型
    response_applications = []
    for app in applications:
        app_response = schemas.ProjectApplicationResponse.model_validate(app, from_attributes=True)
        app_response.applicant_name = app.applicant.name if app.applicant else "未知用户"
        app_response.applicant_email = app.applicant.email if app.applicant else None

        # 填充审批者信息 (如果已处理)
        if app.processed_by_id:
            processor_user = db.query(Student).filter(Student.id == app.processed_by_id).first()
            app_response.processor_name = processor_user.name if processor_user else "未知审批者"
        response_applications.append(app_response)

    print(f"DEBUG_PROJECT_APP: 项目 {project_id} 获取到 {len(response_applications)} 条申请。")
    return response_applications


@app.post("/projects/applications/{application_id}/process", response_model=schemas.ProjectApplicationResponse,
          summary="处理项目申请")
async def process_project_application(
        application_id: int,
        process_data: schemas.ProjectApplicationProcess,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    项目创建者、项目管理员或系统管理员可以批准或拒绝项目申请。
    如果申请被批准，用户将成为项目成员。
    """
    # --- 1. 强制类型转换为整数 (关键修复点) ---
    current_user_id_int = int(current_user_id)
    print(f"DEBUG_PROJECT_APP: 用户 {current_user_id_int} 尝试处理申请 {application_id} 为 '{process_data.status}'。")

    # 2. 验证申请是否存在且为 'pending' 状态
    db_application = db.query(ProjectApplication).filter(ProjectApplication.id == application_id).first()
    if not db_application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目申请未找到。")
    if db_application.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该申请已处理或状态异常，无法再次处理。")

    # 3. 验证操作者权限 (只有项目创建者、项目管理员或系统管理员能处理)
    db_project = db.query(Project).filter(Project.id == db_application.project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的项目未找到。")

    current_user_obj = db.query(Student).filter(Student.id == current_user_id_int).first()  # 使用 int
    if not current_user_obj:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

    # --- 4. 实现完整的三重权限检查 (关键修复点) ---
    is_creator = (db_project.creator_id == current_user_id_int)  # 使用 int
    is_system_admin = current_user_obj.is_admin

    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == db_project.id,
        ProjectMember.student_id == current_user_id_int,  # 使用 int
        ProjectMember.role == 'admin',
        ProjectMember.status == 'active'
    ).first()
    is_project_admin = (membership is not None)

    if not (is_creator or is_system_admin or is_project_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权处理该项目申请。只有项目创建者、项目管理员或系统管理员可以。")

    # 5. 更新申请状态
    db_application.status = process_data.status
    db_application.processed_at = func.now()
    db_application.processed_by_id = current_user_id_int  # 使用 int
    db_application.message = process_data.process_message if process_data.process_message is not None else db_application.message

    db.add(db_application)

    # 6. 如果批准，则添加为项目成员或激活现有成员
    if process_data.status == "approved":
        existing_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == db_application.project_id,
            ProjectMember.student_id == db_application.student_id
        ).first()

        if existing_member:
            existing_member.status = "active"  # 确保是激活状态
            existing_member.role = "member"
            existing_member.joined_at = func.now()
            db.add(existing_member)
            print(
                f"DEBUG_PROJECT_APP: 用户 {db_application.student_id} 已再次激活为项目 {db_application.project_id} 的成员。")
        else:
            new_member = ProjectMember(
                project_id=db_application.project_id,
                student_id=db_application.student_id,
                role="member",
                status="active"  # 新成员也应是 active 状态
            )
            db.add(new_member)
            print(
                f"DEBUG_PROJECT_APP: 用户 {db_application.student_id} 已添加为项目 {db_application.project_id} 的新成员。")

    db.commit()
    db.refresh(db_application)

    # 7. 填充响应模型 (这部分可以优化，但功能上没问题)
    applicant_user = db.query(Student).filter(Student.id == db_application.student_id).first()
    processor_user = current_user_obj  # 直接复用前面查过的 current_user_obj，更高效

    db_application.applicant_name = applicant_user.name if applicant_user else "未知用户"
    db_application.applicant_email = applicant_user.email if applicant_user else None
    db_application.processor_name = processor_user.name if processor_user else "未知审批者"

    print(f"DEBUG_PROJECT_APP: 项目申请 {db_application.id} 已处理为 '{process_data.status}'。")
    return db_application

@app.get("/projects/{project_id}/members", response_model=List[schemas.ProjectMemberResponse],
         summary="获取项目成员列表")
async def get_project_members(
        project_id: int,
        # 保持登录认证，确保只有已认证用户能访问
        # 如果希望未登录用户也能访问，请移除上面的 `current_user_id: int = Depends(get_current_user_id)`
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定项目的所有成员列表。
    现在所有已认证用户都可以查看。
    """
    print(f"DEBUG_PROJECT_MEMBERS: 用户 {current_user_id} 尝试获取项目 {project_id} 的成员列表。")

    # 1. 验证项目是否存在
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 2. 查询成员列表，并预加载成员信息
    # 使用 joinedload 避免 N+1 查询问题
    query = db.query(ProjectMember).options(joinedload(ProjectMember.member)).filter(
        ProjectMember.project_id == project_id
    )

    memberships = query.order_by(ProjectMember.joined_at).all()

    # 3. 填充响应模型
    response_members = []
    for member_ship in memberships:
        member_response = schemas.ProjectMemberResponse.model_validate(member_ship, from_attributes=True)
        member_response.member_name = member_ship.member.name if member_ship.member else "未知用户"
        member_response.member_email = member_ship.member.email if member_ship.member else None
        response_members.append(member_response)

    print(f"DEBUG_PROJECT_MEMBERS: 项目 {project_id} 获取到 {len(response_members)} 位成员。")
    return response_members


# --- 课程管理接口 ---
@app.post("/courses/", response_model=schemas.CourseResponse, summary="创建新课程")
async def create_course(
        course_data: schemas.CourseBase,
        # 接收 CourseBase 数据 (包含 cover_image_url 和 required_skills)
        # current_user_id: str = Depends(get_current_user_id), # 暂时不需要普通用户ID
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能创建课程
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 管理员 {current_admin_user.id} 尝试创建课程: {course_data.title}")

    # 将 required_skills 转换为数据库存储格式（列表或JSONB）
    required_skills_list_for_db = []
    if course_data.required_skills:
        required_skills_list_for_db = [skill.model_dump() for skill in course_data.required_skills]

    # 重建 combined_text
    skills_text = ""
    if required_skills_list_for_db:
        skills_text = ", ".join(
            [s.get("name", "") for s in required_skills_list_for_db if isinstance(s, dict) and s.get("name")])

    combined_text_content = ". ".join(filter(None, [
        _get_text_part(course_data.title),
        _get_text_part(course_data.description),
        _get_text_part(course_data.instructor),
        _get_text_part(course_data.category),
        _get_text_part(skills_text),  # 新增
        _get_text_part(course_data.total_lessons),
        _get_text_part(course_data.avg_rating)
    ])).strip()

    embedding = None
    if combined_text_content:
        try:
            admin_api_key_for_embedding = None
            admin_llm_type = current_admin_user.llm_api_type
            admin_llm_base_url = current_admin_user.llm_api_base_url
            admin_llm_model_id = current_admin_user.llm_model_id

            if admin_llm_type == "siliconflow" and current_admin_user.llm_api_key_encrypted:
                try:
                    admin_api_key_for_embedding = ai_core.decrypt_key(current_admin_user.llm_api_key_encrypted)
                    print(f"DEBUG_EMBEDDING_KEY: 使用管理员配置的硅基流动 API 密钥为课程生成嵌入。")
                except Exception as e:
                    print(f"ERROR_EMBEDDING_KEY: 解密管理员硅基流动 API 密钥失败: {e}。课程嵌入将使用零向量或默认行为。")
                    admin_api_key_for_embedding = None
            else:
                print(f"DEBUG_EMBEDDING_KEY: 管理员未配置硅基流动 API 类型或密钥，课程嵌入将使用零向量或默认行为。")

            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text_content],
                api_key=admin_api_key_for_embedding,
                llm_type=admin_llm_type,
                llm_base_url=admin_llm_base_url,
                llm_model_id=admin_llm_model_id  # 传入管理员的模型ID
            )
            if new_embedding:
                embedding = new_embedding[0]
            print(f"DEBUG: 课程嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成课程嵌入向量失败: {e}")

    try:
        db_course = Course(
            title=course_data.title,
            description=course_data.description,
            instructor=course_data.instructor,
            category=course_data.category,
            total_lessons=course_data.total_lessons,
            avg_rating=course_data.avg_rating,
            cover_image_url=course_data.cover_image_url,
            required_skills=required_skills_list_for_db,
            combined_text=combined_text_content,
            embedding=embedding
        )

        db.add(db_course)
        db.commit()
        db.refresh(db_course)

        # 确保返回时 required_skills 是解析后的列表形式
        if isinstance(db_course.required_skills, str):
            try:
                db_course.required_skills = json.loads(db_course.required_skills)
            except json.JSONDecodeError:
                db_course.required_skills = []
        elif db_course.required_skills is None:
            db_course.required_skills = []

        print(f"DEBUG: 课程 '{db_course.title}' (ID: {db_course.id}) 创建成功。")
        return db_course
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建课程发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建课程失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 创建课程发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建课程失败: {e}")


@app.get("/courses/", response_model=List[schemas.CourseResponse], summary="获取所有课程列表")
async def get_all_courses(current_user_id: int = Depends(get_current_user_id),
                          db: Session = Depends(get_db)):  # 添加 current_user_id 依赖
    """
    获取平台上所有课程的概要列表。
    """
    query = db.query(Course)
    # 调用新的辅助函数来填充 is_liked_by_current_user
    courses = await _get_courses_with_details(query, current_user_id, db)  # 修改这里

    print(f"DEBUG: 获取所有课程列表，共 {len(courses)} 个。")

    for course in courses:
        if isinstance(course.required_skills, str):
            try:
                course.required_skills = json.loads(course.required_skills)
            except json.JSONDecodeError:
                course.required_skills = []
        elif course.required_skills is None:
            course.required_skills = []

    return courses


@app.get("/courses/{course_id}", response_model=schemas.CourseResponse, summary="获取指定课程详情")
async def get_course_by_id(course_id: int, current_user_id: int = Depends(get_current_user_id),
                           db: Session = Depends(get_db)):  # 添加 current_user_id 依赖
    """
    获取指定ID的课程详情。
    """
    print(f"DEBUG: 获取课程 ID: {course_id} 的详情。")
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 填充 is_liked_by_current_user
    course.is_liked_by_current_user = False
    if current_user_id:
        like = db.query(CourseLike).filter(
            CourseLike.owner_id == current_user_id,
            CourseLike.course_id == course.id
        ).first()
        if like:
            course.is_liked_by_current_user = True

    # 确保返回时 required_skills 是解析后的列表形式
    if isinstance(course.required_skills, str):
        try:
            course.required_skills = json.loads(course.required_skills)
        except json.JSONDecodeError:
            course.required_skills = []
    elif course.required_skills is None:
        course.required_skills = []

    return course


@app.put("/courses/{course_id}", response_model=schemas.CourseResponse, summary="更新指定课程")
async def update_course(
        course_id: int,
        course_data: schemas.CourseUpdate,  # 接收 CourseUpdate
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能更新课程
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 管理员 {current_admin_user.id} 尝试更新课程 ID: {course_id}。")

    try:
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if not db_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

        update_data = course_data.dict(exclude_unset=True)

        # 特殊处理 required_skills
        if "required_skills" in update_data:
            db_course.required_skills = update_data["required_skills"]  # 直接赋值列表或 None
            del update_data["required_skills"]  # 避免通用循环再次处理

        # 应用其他字段更新
        for key, value in update_data.items():
            if hasattr(db_course, key):
                setattr(db_course, key, value)

        db.add(db_course)

        # 重建 combined_text
        skills_text = ""
        current_skills_for_text = db_course.required_skills
        if isinstance(current_skills_for_text, str):
            try:
                current_skills_for_text = json.loads(current_skills_for_text)
            except json.JSONDecodeError:
                current_skills_for_text = []

        if isinstance(current_skills_for_text, list):
            skills_text = ", ".join(
                [s.get("name", "") for s in current_skills_for_text if isinstance(s, dict) and s.get("name")])

        db_course.combined_text = ". ".join(filter(None, [
            _get_text_part(db_course.title),
            _get_text_part(db_course.description),
            _get_text_part(db_course.instructor),
            _get_text_part(db_course.category),
            _get_text_part(skills_text),
            _get_text_part(db_course.total_lessons),
            _get_text_part(db_course.avg_rating),
            _get_text_part(db_course.cover_image_url)
        ])).strip()

        # 重新生成 embedding
        embedding = None  # 每次更新都重新生成
        if db_course.combined_text:
            try:
                admin_api_key_for_embedding = None
                admin_llm_type = current_admin_user.llm_api_type
                admin_llm_base_url = current_admin_user.llm_api_base_url
                admin_llm_model_id = current_admin_user.llm_model_id  # 传入管理员的模型ID

                if admin_llm_type == "siliconflow" and current_admin_user.llm_api_key_encrypted:
                    try:
                        admin_api_key_for_embedding = ai_core.decrypt_key(current_admin_user.llm_api_key_encrypted)
                    except Exception:
                        pass

                new_embedding = await ai_core.get_embeddings_from_api(
                    [db_course.combined_text],
                    api_key=admin_api_key_for_embedding,
                    llm_type=admin_llm_type,
                    llm_base_url=admin_llm_base_url,
                    llm_model_id=admin_llm_model_id
                )
                if new_embedding:
                    db_course.embedding = new_embedding[0]
                else:  # 如果没有返回嵌入，设为零向量
                    db_course.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
                print(f"DEBUG: 课程 {course_id} 嵌入向量已更新。")
            except Exception as e:
                print(f"ERROR: 更新课程 {course_id} 嵌入向量失败: {e}")
                db_course.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保失败时是零向量
        else:  # 如果combined_text为空，也确保embedding是零向量
            db_course.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db.add(db_course)

        db.commit()
        db.refresh(db_course)

        # 确保返回时 required_skills 是解析后的列表形式
        if isinstance(db_course.required_skills, str):
            try:
                db_course.required_skills = json.loads(db_course.required_skills)
            except json.JSONDecodeError:
                db_course.required_skills = []
        elif db_course.required_skills is None:
            db_course.required_skills = []

        print(f"DEBUG: 课程 {course_id} 信息更新成功。")
        return db_course

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新课程发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新课程失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 更新课程发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新课程失败: {e}")


@app.get("/recommend/courses/{student_id}", response_model=List[schemas.MatchedCourse], summary="为指定学生推荐课程")
async def recommend_courses_for_student(
        student_id: int,
        db: Session = Depends(get_db),
        initial_k: int = ai_core.INITIAL_CANDIDATES_K,
        final_k: int = ai_core.FINAL_TOP_K
):
    """
    为指定学生推荐相关课程。
    """
    print(f"DEBUG_AI: 为学生 {student_id} 推荐课程。")
    try:
        recommendations = await ai_core.find_matching_courses_for_student(db, student_id, initial_k, final_k)
        if not recommendations:
            print(f"DEBUG_AI: 未为学生 {student_id} 找到课程推荐。")
        return recommendations
    except Exception as e:
        print(f"ERROR_AI: 推荐课程失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"课程推荐失败: {e}")


@app.post("/projects/", response_model=schemas.ProjectResponse, summary="创建新项目")
async def create_project(
        project_data_json: str = Form(..., description="项目主体数据，JSON字符串格式"),
        # Optional: project cover image upload
        cover_image: Optional[UploadFile] = File(None, description="可选：上传项目封面图片"),
        # Optional: multiple project files/attachments upload with their metadata
        project_files_meta_json: Optional[str] = Form(None,
                                                      description="项目附件的元数据列表，JSON字符串格式。例如: '[{\"file_name\":\"doc.pdf\", \"description\":\"概述\", \"access_type\":\"public\"}]'"),
        project_files: Optional[List[UploadFile]] = File(None, description="可选：上传项目附件文件列表"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)

    print(f"DEBUG_RECEIVE_PROJECT: 接收到 project_data_json: '{project_data_json}'")
    print(
        f"DEBUG_RECEIVE_COVER: 接收到 cover_image: {cover_image.filename if cover_image else 'None'}, size: {cover_image.size if cover_image else 'N/A'}")
    print(f"DEBUG_RECEIVE_FILES_META: 接收到 project_files_meta_json: '{project_files_meta_json}'")
    print(f"DEBUG_RECEIVE_FILES: 接收到 project_files count: {len(project_files) if project_files else 0}")

    try:
        project_data = schemas.ProjectCreate.model_validate_json(project_data_json)
        print(f"DEBUG: 用户 {current_user_id_int} 尝试创建项目: {project_data.title}")
    except json.JSONDecodeError as e:
        print(f"ERROR_JSON_DECODE: 项目数据 JSON 解析失败: {e}. 原始字符串: '{project_data_json}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"项目数据 JSON 格式不正确: {e}")
    except ValueError as e:
        print(f"ERROR_PYDANTIC_VALIDATION: 项目数据 Pydantic 验证失败: {e}. 原始字符串: '{project_data_json}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"项目数据验证失败: {e}")

    current_user = db.query(Student).filter(Student.id == current_user_id_int).first()
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

    # List to store OSS objects that were newly uploaded during this request, for rollback purposes
    newly_uploaded_oss_objects_for_rollback: List[str] = []

    try:
        final_cover_image_url = None
        final_cover_image_original_filename = None
        final_cover_image_type = None
        final_cover_image_size_bytes = None

        # --- Process Cover Image Upload ---
        if cover_image and cover_image.filename:
            # 即使文件对象存在，也要检查其大小或文件名是否有效，避免处理空文件部分
            if cover_image.size == 0 or not cover_image.filename.strip():
                print(f"WARNING: 接收到一个空封面文件或文件名为 ' ' 的封面文件。跳过封面处理。")
                # 将其视为没有有效的封面文件上传
            else:
                print("DEBUG: 接收到有效封面文件。开始处理封面上传。")

                if not cover_image.content_type.startswith("image/"):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"不支持的封面文件类型: {cover_image.content_type}。项目封面只接受图片文件。")

                file_bytes = await cover_image.read()
                file_extension = os.path.splitext(cover_image.filename)[1]
                content_type = cover_image.content_type
                file_size = cover_image.size

                oss_path_prefix = "project_covers"
                current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
                newly_uploaded_oss_objects_for_rollback.append(current_oss_object_name)  # Add to rollback list

                try:
                    final_cover_image_url = await oss_utils.upload_file_to_oss(
                        file_bytes=file_bytes,
                        object_name=current_oss_object_name,
                        content_type=content_type
                    )
                    final_cover_image_original_filename = cover_image.filename
                    final_cover_image_type = content_type
                    final_cover_image_size_bytes = file_size

                    print(
                        f"DEBUG: 封面文件 '{cover_image.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_cover_image_url}")

                except HTTPException as e:
                    print(f"ERROR: 上传封面文件到OSS失败: {e.detail}")
                    raise e
                except Exception as e:
                    print(f"ERROR: 上传封面文件到OSS时发生未知错误: {e}")
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                        detail=f"封面文件上传到云存储失败: {e}")
        else:
            print("DEBUG: 未接收到有效封面文件。")

        # --- Parse and Validate Project Files Metadata ---
        parsed_project_files_meta: List[schemas.ProjectFileCreate] = []
        if project_files_meta_json:
            try:
                raw_meta = json.loads(project_files_meta_json)
                if not isinstance(raw_meta, list):
                    raise ValueError("project_files_meta_json 必须是 JSON 列表。")
                parsed_project_files_meta = [schemas.ProjectFileCreate(**f) for f in raw_meta]
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"项目附件元数据 JSON 格式不正确或验证失败: {e}")

        # --- Validate consistency between file attachments and their metadata ---
        if project_files:
            if not parsed_project_files_meta or len(project_files) != len(parsed_project_files_meta):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="项目附件文件数量与提供的元数据数量不匹配，或缺失附件元数据。")
            # Enforce file_name consistency for user provided metadata with actual uploaded file's filename
            for i, file_obj in enumerate(project_files):
                if parsed_project_files_meta[i].file_name != file_obj.filename:
                    # For a stricter API, you could raise an error here.
                    # For more flexibility, we'll overwrite metadata's file_name with actual filename.
                    print(
                        f"WARNING: 附件元数据中的文件名 '{parsed_project_files_meta[i].file_name}' 与实际上传文件名 '{file_obj.filename}' 不匹配，将使用实际文件名。")
                    parsed_project_files_meta[i].file_name = file_obj.filename
        elif parsed_project_files_meta:  # metadata exists but no files were provided (error condition)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="提供了项目附件元数据但未上传任何文件。")

        # --- Create Project Record (before files, to get project_id) ---
        # The db_project object needs to exist before ProjectFiles can be related to it
        # This will be the first DB commit point, if this fails, earlier OSS uploads need to be cleaned up
        db_project = Project(
            title=project_data.title,
            description=project_data.description,
            # Ensure skills and roles are converted to list format if they are Pydantic models from input
            required_skills=[skill.model_dump() for skill in
                             project_data.required_skills] if project_data.required_skills else [],
            required_roles=project_data.required_roles if project_data.required_roles else [],
            keywords=project_data.keywords,
            project_type=project_data.project_type,
            expected_deliverables=project_data.expected_deliverables,
            contact_person_info=project_data.contact_person_info,
            learning_outcomes=project_data.learning_outcomes,
            team_size_preference=project_data.team_size_preference,
            project_status=project_data.project_status,
            start_date=project_data.start_date,
            end_date=project_data.end_date,
            estimated_weekly_hours=project_data.estimated_weekly_hours,
            location=project_data.location,
            creator_id=current_user_id_int,
            cover_image_url=final_cover_image_url,
            cover_image_original_filename=final_cover_image_original_filename,
            cover_image_type=final_cover_image_type,
            cover_image_size_bytes=final_cover_image_size_bytes,
            combined_text="",  # Will be updated after all files are processed
            embedding=None  # Will be updated after all files are processed
        )
        db.add(db_project)
        db.flush()  # Flush to get the ID for db_project, but don't commit yet to allow rollback of files

        # --- 新增逻辑：将创建者自动添加为项目的第一个成员 ---
        print(f"DEBUG: 准备将创建者 {current_user_id_int} 自动添加为项目 {db_project.id} 的成员。")
        initial_member = ProjectMember(
            project_id=db_project.id,  # 使用刚生成的项目ID
            student_id=current_user_id_int,  # 创建者的ID
            role="admin",  # 或者 "管理员", "负责人" 等，根据你的系统设计
            status="active",  # 状态设为活跃
            # join_date=datetime.utcnow()     # 如果你的模型有加入日期字段
        )
        db.add(initial_member)
        print(f"DEBUG: 创建者已作为成员添加到数据库会话中。")
        # --- 新增逻辑结束 ---

        # --- Process Project Attachment Files ---
        project_files_for_db = []
        allowed_file_mime_types = [
            "text/plain", "text/markdown", "application/pdf",
            "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/json", "application/xml", "text/html", "text/css", "text/javascript",
            "application/x-python-code", "text/x-python", "application/x-sh",
            # 可以根据需要添加其他文件类型
        ]

        if project_files:
            for index, file_obj in enumerate(project_files):
                file_metadata = parsed_project_files_meta[index]

                if file_obj.content_type.startswith('image/'):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"项目附件不支持图片文件：{file_obj.filename}。请使用项目封面上传或作为图片消息在聊天室上传。")
                if file_obj.content_type.startswith('video/'):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"项目附件不支持视频文件：{file_obj.filename}。请作为视频消息在聊天室上传。")
                if file_obj.content_type not in allowed_file_mime_types:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"不支持的项目附件文件类型: {file_obj.filename} ({file_obj.content_type})。仅支持常见文档、文本和代码文件。")

                file_bytes_content = await file_obj.read()
                file_extension = os.path.splitext(file_obj.filename)[1]

                # IMPORTANT: Use the newly created project ID in the OSS path
                oss_path_prefix = f"project_attachments/{db_project.id}"
                current_oss_object_name_attach = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
                newly_uploaded_oss_objects_for_rollback.append(current_oss_object_name_attach)  # Add to rollback list

                attachment_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes_content,
                    object_name=current_oss_object_name_attach,
                    content_type=file_obj.content_type
                )

                new_project_file = ProjectFile(
                    project_id=db_project.id,
                    upload_by_id=current_user_id_int,
                    file_name=file_obj.filename,
                    oss_object_name=current_oss_object_name_attach,
                    file_path=attachment_url,
                    file_type=file_obj.content_type,
                    size_bytes=file_obj.size,
                    description=file_metadata.description,
                    access_type=file_metadata.access_type
                )
                project_files_for_db.append(new_project_file)
                db.add(new_project_file)  # Add to session
                print(f"DEBUG: 项目附件文件 '{file_obj.filename}' 已上传并添加到session。")

        # --- Rebuild combined_text and Update Embedding for Project ---
        _required_skills_text = ", ".join(
            [s.get("name", "") for s in db_project.required_skills if isinstance(s, dict) and s.get("name")])
        _required_roles_text = "、".join(db_project.required_roles)

        # Include attachment filenames and descriptions in combined_text if attachments exist
        attachments_text = ""
        if project_files_for_db:
            attachment_snippets = []
            for pf in project_files_for_db:
                snippet = f"{pf.file_name}"
                if pf.description:
                    snippet += f" ({pf.description})"
                attachment_snippets.append(snippet)
            attachments_text = "。附件列表：" + "。".join(attachment_snippets)

        db_project.combined_text = ". ".join(filter(None, [
            _get_text_part(db_project.title),
            _get_text_part(db_project.description),
            _get_text_part(_required_skills_text),
            _get_text_part(_required_roles_text),
            _get_text_part(db_project.keywords),
            _get_text_part(db_project.project_type),
            _get_text_part(db_project.expected_deliverables),
            _get_text_part(db_project.learning_outcomes),
            _get_text_part(db_project.team_size_preference),
            _get_text_part(db_project.project_status),
            _get_text_part(db_project.start_date),
            _get_text_part(db_project.end_date),
            _get_text_part(db_project.estimated_weekly_hours),
            _get_text_part(db_project.location),
            _get_text_part(db_project.cover_image_original_filename),
            _get_text_part(db_project.cover_image_type),
            attachments_text  # Include attachments in combined_text
        ])).strip()

        # Determine LLM API key for embedding generation (using project creator's config)
        project_creator_llm_api_key = None
        project_creator_llm_type = current_user.llm_api_type
        project_creator_llm_base_url = current_user.llm_api_base_url
        project_creator_llm_model_id = current_user.llm_model_id

        if project_creator_llm_type == "siliconflow" and current_user.llm_api_key_encrypted:
            try:
                project_creator_llm_api_key = ai_core.decrypt_key(current_user.llm_api_key_encrypted)
                print(
                    f"DEBUG_EMBEDDING_KEY: (Recalculating embedding) 使用创建者配置的硅基流动 API 密钥为项目生成嵌入。")
            except Exception as e:
                print(
                    f"ERROR_EMBEDDING_KEY: (Recalculating embedding) 解密创建者硅基流动 API 密钥失败: {e}。项目嵌入将使用零向量或默认行为。")
                project_creator_llm_api_key = None
        else:
            print(
                f"DEBUG_EMBEDDING_KEY: (Recalculating embedding) 项目创建者未配置硅基流动 API 类型或密钥，项目嵌入将使用占位符。")

        embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if db_project.combined_text:
            try:
                new_embedding = await ai_core.get_embeddings_from_api(
                    [db_project.combined_text],
                    api_key=project_creator_llm_api_key,
                    llm_type=project_creator_llm_type,
                    llm_base_url=project_creator_llm_base_url,
                    llm_model_id=project_creator_llm_model_id
                )
                if new_embedding:
                    db_project.embedding = new_embedding[0]
                else:
                    db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
                print(f"DEBUG: 项目嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR: 生成项目嵌入向量失败: {e}")
                db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db.add(db_project)  # Ensure the project object with updated combined_text and embedding is marked for a commit

        db.commit()  # FINAL COMMIT of all DB changes (project, ProjectFiles)
        db.refresh(db_project)

        # Populate `project_files` and `creator_name` for the ProjectResponse schema
        # We need to re-fetch with joinedload for project_files and uploader information.
        db_project_with_files_and_uploader = db.query(Project).options(
            joinedload(Project.project_files).joinedload(ProjectFile.uploader)
        ).filter(Project.id == db_project.id).first()

        visible_project_files_for_response = []
        is_project_creator_after_commit = (db_project.creator_id == current_user_id_int)
        is_project_member_after_commit = db.query(ProjectMember).filter(
            ProjectMember.project_id == db_project.id,
            ProjectMember.student_id == current_user_id_int,
            ProjectMember.status == "active"
        ).first() is not None

        if db_project_with_files_and_uploader and db_project_with_files_and_uploader.project_files:
            for file_record in db_project_with_files_and_uploader.project_files:
                if file_record.access_type == "public":
                    file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
                    visible_project_files_for_response.append(file_record)
                elif file_record.access_type == "member_only":
                    if is_project_creator_after_commit or is_project_member_after_commit:
                        file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
                        visible_project_files_for_response.append(file_record)
        db_project.project_files = visible_project_files_for_response  # Assign to the ORM object being returned

        db_project._creator_name = current_user.name if current_user else "未知用户"  # Set creator name for response

        # Ensure required_skills and required_roles are correct list format for Pydantic response
        if isinstance(db_project.required_skills, str):
            try:
                db_project.required_skills = json.loads(db_project.required_skills)
            except json.JSONDecodeError:
                db_project.required_skills = []
        elif db_project.required_skills is None:
            db_project.required_skills = []

        if isinstance(db_project.required_roles, str):
            try:
                db_project.required_roles = json.loads(db_project.required_roles)
            except json.JSONDecodeError:
                db_project.required_roles = []
        elif db_project.required_roles is None:
            db_project.required_roles = []

        print(f"DEBUG: 项目 '{db_project.title}' (ID: {db_project.id}) 创建成功。")
        return db_project
    except HTTPException as e:  # Catch FastAPI's HTTP exceptions
        db.rollback()
        # Rollback logic for any newly uploaded OSS objects
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG: HTTP exception occurred, attempting to delete new OSS file: {obj_name}")
        raise e
    except IntegrityError as e:  # Catch database integrity errors
        db.rollback()
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG: DB integrity error occurred, attempting to delete new OSS file: {obj_name}")
        print(f"ERROR_DB: 创建项目发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建项目失败，可能存在数据冲突或唯一性约束。")
    except Exception as e:  # Catch any other unexpected errors
        db.rollback()
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG: Unknown error occurred, attempting to delete new OSS file: {obj_name}")
        print(f"ERROR_DB: 创建项目发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建项目失败: {e}")


@app.put("/projects/{project_id}", response_model=schemas.ProjectResponse, summary="更新指定项目")
async def update_project(
        project_id: int,
        # 使用 Form() 接收 JSON 字符串数据
        project_data_json: str = Form(..., description="要更新的项目主体数据，JSON字符串格式"),
        # Optional: project cover image upload
        cover_image: Optional[UploadFile] = File(None, description="可选：上传项目封面图片，将替换现有封面"),
        # Optional: multiple project files/attachments upload with their metadata
        # 注意：这里是新上传的文件的元数据。现有文件的元数据更新通过 files_to_update_metadata_json
        project_files_meta_json: Optional[str] = Form(None,
                                                      description="新项目附件的元数据列表，JSON字符串格式。例如: '[{\"file_name\":\"doc.pdf\", \"description\":\"概述\", \"access_type\":\"public\"}]'"),
        project_files: Optional[List[UploadFile]] = File(None,
                                                         description="可选：上传的新项目附件文件列表，与 project_files_meta_json 对应"),
        # Files to delete or update metadata for
        files_to_delete_ids_json: Optional[str] = Form(None,
                                                       description="要删除的项目文件ID列表，JSON字符串格式，例如: '[1, 2, 3]'"),
        files_to_update_metadata_json: Optional[str] = Form(None, description="要更新元数据的文件列表，JSON字符串格式"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)
    print(f"DEBUG_UPDATE_PROJECT: 用户 {current_user_id_int} 尝试更新项目 ID: {project_id}。")

    # List to store OSS objects that were newly uploaded during this request, for rollback purposes
    newly_uploaded_oss_objects_for_rollback: List[str] = []

    try:
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        current_user = db.query(Student).filter(Student.id == current_user_id_int).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        is_creator = (db_project.creator_id == current_user_id_int)
        is_system_admin = current_user.is_admin

        print(
            f"DEBUG_PERM_PROJECT: Project Creator ID: {db_project.creator_id}, Current User ID: {current_user_id_int}, Is Creator: {is_creator}, Is System Admin: {is_system_admin}")

        # 权限检查：只有项目创建者或系统管理员可以修改项目（包括其文件）
        if not (is_creator or is_system_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权更新此项目。只有项目创建者或系统管理员可以修改。")

        # --- 1. 解析传入的 JSON 字符串数据 ---
        try:
            # 解析项目主体数据
            project_data_dict = json.loads(project_data_json)
            update_project_data_schema = schemas.ProjectUpdate(**project_data_dict)  # 用 ProjectUpdate Schema 校验
            update_data = update_project_data_schema.dict(exclude_unset=True)  # Only fields passed in body

            # 解析新上传文件元数据
            parsed_project_files_meta: List[schemas.ProjectFileCreate] = []
            if project_files_meta_json:
                raw_meta = json.loads(project_files_meta_json)
                if not isinstance(raw_meta, list):
                    raise ValueError("project_files_meta_json 必须是 JSON 列表。")
                parsed_project_files_meta = [schemas.ProjectFileCreate(**f) for f in raw_meta]

            # 解析要删除的文件ID
            files_to_delete_ids: Optional[List[int]] = None
            if files_to_delete_ids_json:
                files_to_delete_ids = json.loads(files_to_delete_ids_json)
                if not isinstance(files_to_delete_ids, list) or not all(
                        isinstance(i, int) for i in files_to_delete_ids):
                    raise ValueError("files_to_delete_ids_json 必须是整数ID的列表。")
                files_to_delete_ids = list(set(files_to_delete_ids))  # 去重，避免重复删除

            # 解析要更新元数据的文件列表
            files_to_update_metadata: Optional[List[schemas.ProjectFileUpdateData]] = []
            if files_to_update_metadata_json:
                parsed_files_to_update = json.loads(files_to_update_metadata_json)
                files_to_update_metadata = [schemas.ProjectFileUpdateData(**f) for f in
                                            parsed_files_to_update]  # 用 ProjectFileUpdateData Schema 校验

        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"JSON数据解析失败或格式不正确: {e}")

        # --- 2. 处理项目主体信息更新，包括封面图片 ---
        old_project_status = db_project.project_status
        new_project_status = update_data.get("project_status", old_project_status)  # Get new status, default to old one
        has_status_changed_to_completed = False
        if new_project_status == "已完成" and old_project_status != "已完成":
            has_status_changed_to_completed = True
            print(
                f"DEBUG_PROJECT_STATUS: detecting status change from '{old_project_status}' to '{new_project_status}' for project {project_id}.")

        # --- Handle Cover Image Upload/Update/Clear ---
        # Get old OSS object name for cover image (if any)
        old_cover_oss_object_name = None
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        if db_project.cover_image_url and db_project.cover_image_url.startswith(oss_base_url_parsed):
            old_cover_oss_object_name = db_project.cover_image_url.replace(oss_base_url_parsed, '', 1)

        # Priority 1: If a new cover image file is uploaded via 'cover_image' parameter
        if cover_image and cover_image.filename and cover_image.size > 0:
            print("DEBUG: 接收到新的封面图片文件。处理上传。")
            if not cover_image.content_type.startswith("image/"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"不支持的封面文件类型: {cover_image.content_type}。项目封面只接受图片文件。")

            # Delete old cover image from OSS if it exists
            if old_cover_oss_object_name:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_cover_oss_object_name))
                print(f"DEBUG_PROJECT: Deleted old cover image from OSS for replacement: {old_cover_oss_object_name}")

            # Upload new cover image
            file_bytes = await cover_image.read()
            file_extension = os.path.splitext(cover_image.filename)[1]
            content_type = cover_image.content_type
            file_size = cover_image.size

            oss_path_prefix = "project_covers"
            current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
            newly_uploaded_oss_objects_for_rollback.append(current_oss_object_name)  # Add to rollback list

            final_cover_image_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=current_oss_object_name,
                content_type=content_type
            )
            db_project.cover_image_url = final_cover_image_url
            db_project.cover_image_original_filename = cover_image.filename
            db_project.cover_image_type = content_type
            db_project.cover_image_size_bytes = file_size

            # Ensure these fields are not overwritten by update_data later if they were also present
            update_data.pop("cover_image_url", None)
            update_data.pop("cover_image_original_filename", None)
            update_data.pop("cover_image_type", None)
            update_data.pop("cover_image_size_bytes", None)

            print(
                f"DEBUG_PROJECT: 新封面图片 '{cover_image.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_cover_image_url}")

        # Priority 2: If 'cover_image_url' (or related meta fields) is explicitly provided in project_data_json
        # This branch is only taken if 'cover_image' (UploadFile) was NOT provided in the request
        elif "cover_image_url" in update_data:
            new_cover_image_url_from_json = update_data.get("cover_image_url")  # Can be str or None

            # Check if existing cover needs to be deleted
            if old_cover_oss_object_name:
                # If new URL is None/empty OR new URL is different and not an OSS URL (e.g., external or different OSS bucket)
                new_cover_is_oss_url = new_cover_image_url_from_json and new_cover_image_url_from_json.startswith(
                    oss_base_url_parsed)
                if not new_cover_image_url_from_json or \
                        (new_cover_image_url_from_json != db_project.cover_image_url and not new_cover_is_oss_url):
                    asyncio.create_task(oss_utils.delete_file_from_oss(old_cover_oss_object_name))
                    print(
                        f"DEBUG_PROJECT: Deleted old cover image from OSS because it's being replaced by non-OSS URL or cleared: {old_cover_oss_object_name}")

            # Apply updates for cover image fields from JSON
            db_project.cover_image_url = new_cover_image_url_from_json
            db_project.cover_image_original_filename = update_data.get("cover_image_original_filename", None)
            db_project.cover_image_type = update_data.get("cover_image_type", None)
            db_project.cover_image_size_bytes = update_data.get("cover_image_size_bytes", None)

            # Ensure these fields are popped after being handled
            update_data.pop("cover_image_url", None)
            update_data.pop("cover_image_original_filename", None)
            update_data.pop("cover_image_type", None)
            update_data.pop("cover_image_size_bytes", None)
        else:
            print("DEBUG: 未接收到新的封面图片文件，也未在JSON中指定封面URL更新。")

        # Apply other general updates from project_data_json
        for key, value in update_data.items():
            if hasattr(db_project, key):
                setattr(db_project, key, value)

        db.add(db_project)  # Add the updated project to the session

        # Flush to allow subsequent operations (like file deletion/attachment to project) to see latest project state
        db.flush()

        # --- Check for Project Completion and Award Points (after main project update is flushed) ---
        if has_status_changed_to_completed:
            print(f"DEBUG_FLUSH: 项目 {project_id} 状态更新已刷新到会话。")
            project_creator_user = db.query(Student).filter(Student.id == db_project.creator_id).first()
            if project_creator_user:
                project_completion_points = 50
                await _award_points(
                    db=db,
                    user=project_creator_user,
                    amount=project_completion_points,
                    reason=f"完成项目：'{db_project.title}'",
                    transaction_type="EARN",
                    related_entity_type="project",
                    related_entity_id=db_project.id
                )
                await _check_and_award_achievements(db, db_project.creator_id)
                print(
                    f"DEBUG_POINTS_ACHIEVEMENT: 项目 {db_project.id} 已完成，项目创建者 {db_project.creator_id} 获得 {project_completion_points} 积分并检查成就 (待提交)。")
            else:
                print(f"WARNING: 项目 {db_project.id} 完成，但项目创建者 {db_project.creator_id} 未找到，无法奖励积分。")

        # --- 3. Process File Deletions ---
        if files_to_delete_ids:
            for file_id in files_to_delete_ids:
                db_project_file_to_delete = db.query(ProjectFile).filter(
                    ProjectFile.id == file_id,
                    ProjectFile.project_id == project_id
                ).first()
                if db_project_file_to_delete:
                    # Verify permission: either uploader, project creator, or system admin
                    if db_project_file_to_delete.upload_by_id == current_user_id_int or is_creator or is_system_admin:
                        # OSS deletion is handled by SQLAlchemy 'before_delete' event listener
                        db.delete(db_project_file_to_delete)
                        print(f"DEBUG_PROJECT_FILE: 文件 {file_id} 已标记删除。")
                    else:
                        print(
                            f"WARNING_PROJECT_FILE: 用户 {current_user_id_int} 无权删除文件 {file_id} (不拥有或非项目创建者/管理员)。跳过。")
                else:
                    print(f"WARNING_PROJECT_FILE: 请求删除的文件 {file_id} 未找到或不属于项目 {project_id}。")

        # --- 4. Process File Metadata Updates ---
        if files_to_update_metadata:
            for file_update_data in files_to_update_metadata:
                db_project_file_to_update = db.query(ProjectFile).filter(
                    ProjectFile.id == file_update_data.id,
                    ProjectFile.project_id == project_id
                ).first()
                if db_project_file_to_update:
                    # Verify permission to update: uploader, project creator, or system admin
                    if db_project_file_to_update.upload_by_id == current_user_id_int or is_creator or is_system_admin:
                        update_file_data_dict = file_update_data.dict(exclude_unset=True)
                        for key, value in update_file_data_dict.items():
                            if key != "id" and hasattr(db_project_file_to_update, key):
                                setattr(db_project_file_to_update, key, value)
                        db.add(db_project_file_to_update)
                        print(f"DEBUG_PROJECT_FILE: 文件 {file_update_data.id} 元数据已更新。")
                    else:
                        print(
                            f"WARNING_PROJECT_FILE: 用户 {current_user_id_int} 无权更新文件 {file_update_data.id} (不拥有或非项目创建者/管理员)。跳过。")
                else:
                    print(
                        f"WARNING_PROJECT_FILE: 请求更新的文件 {file_update_data.id} 未找到或不属于项目 {project_id}。")

        # --- 5. Process New Project Attachment Files Upload ---
        allowed_file_mime_types = [
            "text/plain", "text/markdown", "application/pdf",
            "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/json", "application/xml", "text/html", "text/css", "text/javascript",
            "application/x-python-code", "text/x-python", "application/x-sh"
        ]

        if project_files:
            if not parsed_project_files_meta or len(project_files) != len(parsed_project_files_meta):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="新上传项目附件数量与提供的元数据数量不匹配，或缺失附件元数据。")

            for index, file_obj in enumerate(project_files):
                file_metadata = parsed_project_files_meta[index]

                if file_obj.content_type.startswith('image/'):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"项目附件不支持图片文件：{file_obj.filename}。请使用项目封面上传或作为图片消息在聊天室上传。")
                if file_obj.content_type.startswith('video/'):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"项目附件不支持视频文件：{file_obj.filename}。请作为视频消息在聊天室上传。")
                if file_obj.content_type not in allowed_file_mime_types:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail=f"不支持的项目附件文件类型: {file_obj.filename} ({file_obj.content_type})。仅支持常见文档、文本和代码文件。")

                file_bytes_content = await file_obj.read()
                file_extension = os.path.splitext(file_obj.filename)[1]
                oss_path_prefix = f"project_attachments/{project_id}"  # Use existing project_id for attachments
                current_oss_object_name_attach = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
                newly_uploaded_oss_objects_for_rollback.append(current_oss_object_name_attach)  # Add to rollback list

                attachment_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes_content,
                    object_name=current_oss_object_name_attach,
                    content_type=file_obj.content_type
                )

                new_project_file = ProjectFile(
                    project_id=project_id,
                    upload_by_id=current_user_id_int,
                    file_name=file_obj.filename,
                    oss_object_name=current_oss_object_name_attach,
                    file_path=attachment_url,
                    file_type=file_obj.content_type,
                    size_bytes=file_obj.size,
                    description=file_metadata.description,
                    access_type=file_metadata.access_type
                )
                db.add(new_project_file)
                print(f"DEBUG_PROJECT_FILE: 新项目附件文件 '{file_obj.filename}' 已上传并标记添加。")

        db.flush()  # Ensure all additions/deletions on ProjectFile are reflected in the session before querying relationships

        # Populate required_skills and required_roles as needed for text generation
        _required_skills_text = ""
        if db_project.required_skills:
            if isinstance(db_project.required_skills, str):  # Handle if it's still a JSON string
                try:
                    db_project.required_skills = json.loads(db_project.required_skills)
                except json.JSONDecodeError:
                    db_project.required_skills = []
            if isinstance(db_project.required_skills, list):
                _required_skills_text = ", ".join(
                    [s.get("name", "") for s in db_project.required_skills if isinstance(s, dict) and s.get("name")])

        _required_roles_text = ""
        if db_project.required_roles:
            if isinstance(db_project.required_roles, str):  # Handle if it's still a JSON string
                try:
                    db_project.required_roles = json.loads(db_project.required_roles)
                except json.JSONDecodeError:
                    db_project.required_roles = []
            if isinstance(db_project.required_roles, list):
                _required_roles_text = "、".join(db_project.required_roles)

        # Re-fetch ProjectFiles from the session to get the latest list INCLUDING newly added ones
        # and EXCLUDING deleted ones (due to cascade logic and .delete operations earlier).
        current_attached_files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()
        attachments_text = ""
        if current_attached_files:
            attachment_snippets = []
            for pf in current_attached_files:
                snippet = f"{pf.file_name}"
                if pf.description:
                    snippet += f" ({pf.description})"
                attachment_snippets.append(snippet)
            attachments_text = "。附件列表：" + "。".join(attachment_snippets)

        db_project.combined_text = ". ".join(filter(None, [
            _get_text_part(db_project.title),
            _get_text_part(db_project.description),
            _get_text_part(_required_skills_text),
            _get_text_part(_required_roles_text),
            _get_text_part(db_project.keywords),
            _get_text_part(db_project.project_type),
            _get_text_part(db_project.expected_deliverables),
            _get_text_part(db_project.learning_outcomes),
            _get_text_part(db_project.team_size_preference),
            _get_text_part(db_project.project_status),
            _get_text_part(db_project.start_date),
            _get_text_part(db_project.end_date),
            _get_text_part(db_project.estimated_weekly_hours),
            _get_text_part(db_project.location),
            _get_text_part(db_project.cover_image_original_filename),
            _get_text_part(db_project.cover_image_type),
            attachments_text  # Now includes current attachments
        ])).strip()

        # Determine LLM API key for embedding generation (using project creator's config)
        project_creator_llm_api_key = None
        project_creator = db.query(Student).filter(Student.id == db_project.creator_id).first()
        if project_creator:  # Should always exist, as creator_id is not nullable
            project_creator_llm_type = project_creator.llm_api_type
            project_creator_llm_base_url = project_creator.llm_api_base_url
            project_creator_llm_model_id = project_creator.llm_model_id

            if project_creator_llm_type == "siliconflow" and project_creator.llm_api_key_encrypted:
                try:
                    project_creator_llm_api_key = ai_core.decrypt_key(project_creator.llm_api_key_encrypted)
                    print(
                        f"DEBUG_EMBEDDING_KEY: (Recalculating embedding) 使用创建者配置的硅基流动 API 密钥为项目更新嵌入。")
                except Exception as e:
                    print(
                        f"ERROR_EMBEDDING_KEY: (Recalculating embedding) 解密创建者硅基流动 API 密钥失败: {e}。项目嵌入将使用零向量或默认行为。")
                    project_creator_llm_api_key = None
            else:
                print(
                    f"DEBUG_EMBEDDING_KEY: (Recalculating embedding) 项目创建者未配置硅基流动 API 类型或密钥，项目嵌入将使用占位符。")
        else:  # Fallback if creator not found (shouldn't happen)
            project_creator_llm_type = None
            project_creator_llm_base_url = None
            project_creator_llm_model_id = None

        embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if db_project.combined_text:
            try:
                new_embedding = await ai_core.get_embeddings_from_api(
                    [db_project.combined_text],
                    api_key=project_creator_llm_api_key,
                    llm_type=project_creator_llm_type,
                    llm_base_url=project_creator_llm_base_url,
                    llm_model_id=project_creator_llm_model_id
                )
                if new_embedding:
                    db_project.embedding = new_embedding[0]
                else:
                    db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
                print(f"DEBUG: 项目 {project_id} 嵌入向量已更新。")
            except Exception as e:
                print(f"ERROR: 更新项目 {project_id} 嵌入向量失败: {e}. 嵌入向量设为零。")
                db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db.add(db_project)  # Ensure the project object with updated combined_text and embedding is marked for a commit

        db.commit()  # FINAL COMMIT of all DB changes (project, ProjectFiles)

        # Refresh Project instance to ensure all relationships are loaded for the response model after commit
        db.refresh(db_project)

        # Populate `project_files` and `creator_name` for the ProjectResponse schema
        # We need to re-fetch with joinedload for project_files and uploader information.
        # This ensures that the response always contains the fully updated and filtered list of files.
        db_project_for_response = db.query(Project).options(
            joinedload(Project.project_files).joinedload(ProjectFile.uploader)
        ).filter(Project.id == project_id).first()

        visible_project_files_for_response = []
        # Re-verify permissions based on the state after commit (for member_only files)
        is_current_user_project_creator_for_response = (db_project_for_response.creator_id == current_user_id_int)
        is_current_user_project_member_for_response = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.student_id == current_user_id_int,
            ProjectMember.status == "active"
        ).first() is not None

        if db_project_for_response and db_project_for_response.project_files:
            for file_record in db_project_for_response.project_files:
                if file_record.access_type == "public":
                    file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
                    visible_project_files_for_response.append(file_record)
                elif file_record.access_type == "member_only":
                    if is_current_user_project_creator_for_response or is_current_user_project_member_for_response:
                        file_record._uploader_name = file_record.uploader.name if file_record.uploader else "未知用户"
                        visible_project_files_for_response.append(file_record)
        # Assign the filtered files to the ORM object that will be returned
        db_project_for_response.project_files = visible_project_files_for_response

        # Populate creator_name for response
        if db_project_for_response.creator:
            db_project_for_response._creator_name = db_project_for_response.creator.name
        else:
            db_project_for_response._creator_name = "未知用户"

        print(f"DEBUG: 项目 {project_id} 信息和文件更新请求处理完毕，所有事务已提交。")
        return db_project_for_response  # Return the ORM object, Pydantic will map it

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        # 如果有新上传的文件，但DB事务回滚，则删除OSS上的文件
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG_PROJECT_UPDATE_ERROR: HTTP exception, attempting to delete new OSS file: {obj_name}")
        raise e
    except Exception as e:  # 捕获所有其他意外错误，并执行回滚
        db.rollback()
        # 如果有新上传的文件，但DB事务回滚，则删除OSS上的文件
        if newly_uploaded_oss_objects_for_rollback:
            for obj_name in newly_uploaded_oss_objects_for_rollback:
                asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                print(f"DEBUG_PROJECT_UPDATE_ERROR: Unknown error, attempting to delete new OSS file: {obj_name}")
        print(f"ERROR_PROJECT_UPDATE_GLOBAL: 项目 {project_id} 更新过程中发生错误，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"项目更新失败：{e}",
        )


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定项目（仅限项目创建者或系统管理员）")
async def delete_project(
        project_id: int,  # 要删除的项目ID
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    """
    删除指定ID的项目。只有项目的创建者或系统管理员可以执行此操作。
    此操作将级联删除项目的所有关联数据，包括：
    - 项目文件（及其OSS文件）
    - 项目申请
    - 项目成员
    - 项目点赞
    - 关联的聊天室（及其消息和成员）
    注意：项目的封面图片如果托管在OSS，也将在删除项目时被移除。
    """
    print(f"DEBUG_DELETE_PROJECT: 用户 {current_user_id} 尝试删除项目 ID: {project_id}。")

    try:
        # 1. 获取项目信息和当前用户信息
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:  # 理论上不会发生，因为 get_current_user_id 已经验证
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        # 2. 权限检查：只有项目创建者或系统管理员可以删除
        is_creator = (db_project.creator_id == current_user_id)
        is_system_admin = current_user.is_admin

        print(f"DEBUG_DELETE_PROJECT_PERM: 项目创建者ID: {db_project.creator_id}, 当前用户ID: {current_user_id}, "
              f"是创建者: {is_creator}, 是系统管理员: {is_system_admin}")

        if not (is_creator or is_system_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权删除此项目。只有项目创建者或系统管理员可以执行此操作。")

        # 3. 删除项目封面图片（如果托管在OSS）
        # Project 模型的 cover_image_url 是直接 string，没有像 ProjectFile 那样的 event listener
        # 所以这里需要手动删除 OSS 上的封面文件
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        cover_image_oss_object_name = None
        if db_project.cover_image_url and db_project.cover_image_url.startswith(oss_base_url_parsed):
            cover_image_oss_object_name = db_project.cover_image_url.replace(oss_base_url_parsed, '', 1)

        if cover_image_oss_object_name:
            try:
                # 异步删除文件，不阻塞数据库事务
                asyncio.create_task(oss_utils.delete_file_from_oss(cover_image_oss_object_name))
                print(f"DEBUG_DELETE_PROJECT: 安排删除项目封面OSS文件: {cover_image_oss_object_name}")
            except Exception as e:
                print(f"ERROR_DELETE_PROJECT: 安排删除项目封面OSS文件 {cover_image_oss_object_name} 失败: {e}")
                # 即使删除OSS文件失败，也应允许数据库记录被删除，不中断流程

        # 4. 删除数据库中的项目记录
        # 由于 Project 模型对 ProjectFile、ProjectApplication、ProjectMember、ChatRoom 等
        # 关系设置了 cascade="all, delete-orphan"，所有关联记录将随项目一并删除。
        # ProjectFile 的 before_delete 事件会处理其对应的OSS文件删除。
        db.delete(db_project)
        db.commit()  # 提交删除操作

        print(f"DEBUG_DELETE_PROJECT: 项目 {project_id} 及其所有关联数据已成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)  # 返回 204 No Content 表示成功且无响应体

    except HTTPException as e:
        db.rollback()  # 遇到 HTTPException 也回滚，确保数据库状态一致
        raise e
    except Exception as e:
        db.rollback()  # 捕获其他所有异常并回滚
        print(f"ERROR_DELETE_PROJECT_GLOBAL: 删除项目 {project_id} 过程中发生未知错误，事务已回滚: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除项目失败: {e}")


@app.delete("/projects/{project_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定项目的附件文件")
async def delete_project_file(
        project_id: int,  # 所属项目ID
        file_id: int,  # 要删除的文件ID
        current_user_id: int = Depends(get_current_user_id),  # 当前操作用户ID
        db: Session = Depends(get_db)
):
    """
    从指定项目中删除一个附件文件。
    只有文件的上传者、项目创建者、项目活跃成员或系统管理员可以执行此操作。
    文件将从数据库中删除，并且其对应的OSS文件也会被自动删除。
    """
    print(f"DEBUG_DELETE_PROJECT_FILE: 用户 {current_user_id} 尝试删除项目 {project_id} 中的文件 ID: {file_id}。")

    try:
        # 1. 验证项目和文件是否存在，并确保文件属于该项目
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        db_project_file = db.query(ProjectFile).filter(
            ProjectFile.id == file_id,
            ProjectFile.project_id == project_id
        ).first()

        if not db_project_file:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目文件未找到或不属于该项目。")

        # 2. 获取当前操作用户和项目创建者的信息
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:  # 理论上不会发生
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        # 3. 权限检查
        is_uploader = (db_project_file.upload_by_id == current_user_id)
        is_project_creator = (db_project.creator_id == current_user_id)
        is_project_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.student_id == current_user_id,
            ProjectMember.status == "active"
        ).first() is not None
        is_system_admin = current_user.is_admin

        print(f"DEBUG_DELETE_PROJECT_FILE_PERM: "
              f"文件上传者ID: {db_project_file.upload_by_id}, 项目创建者ID: {db_project.creator_id}, "
              f"当前用户ID: {current_user_id}, "
              f"是上传者: {is_uploader}, 是项目创建者: {is_project_creator}, "
              f"是项目成员: {is_project_member}, 是系统管理员: {is_system_admin}")

        if not (is_uploader or is_project_creator or is_project_member or is_system_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权删除此文件。只有文件上传者、项目创建者、项目成员或系统管理员可以删除。")

        # 4. 删除数据库记录
        # ProjectFile 模型的 'before_delete' 事件监听器会自动处理OSS文件的删除
        db.delete(db_project_file)
        db.commit()

        # 5. 可选：更新项目的 combined_text 和 embedding
        # 因为文件被删除，项目的描述性文本可能改变，需要重新生成 embedding
        # 重新加载 db_project，确保它反映了文件删除后的最新状态
        db.refresh(db_project)  # refresh db_project to get updated project_files relationship

        _required_skills_text = ""
        if db_project.required_skills:
            if isinstance(db_project.required_skills, str):
                try:
                    db_project.required_skills = json.loads(db_project.required_skills)
                except json.JSONDecodeError:
                    db_project.required_skills = []
            if isinstance(db_project.required_skills, list):
                _required_skills_text = ", ".join(
                    [s.get("name", "") for s in db_project.required_skills if isinstance(s, dict) and s.get("name")])

        _required_roles_text = ""
        if db_project.required_roles:
            if isinstance(db_project.required_roles, str):
                try:
                    db_project.required_roles = json.loads(db_project.required_roles)
                except json.JSONDecodeError:
                    db_project.required_roles = []
            if isinstance(db_project.required_roles, list):
                _required_roles_text = "、".join(db_project.required_roles)

        # Re-fetch ProjectFiles from the session to get the latest list AFTER deletion.
        # This is direct query, ensuring up-to-date relationships.
        current_attached_files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()
        attachments_text = ""
        if current_attached_files:
            attachment_snippets = []
            for pf in current_attached_files:
                snippet = f"{pf.file_name}"
                if pf.description:
                    snippet += f" ({pf.description})"
                attachment_snippets.append(snippet)
            attachments_text = "。附件列表：" + "。".join(attachment_snippets)

        db_project.combined_text = ". ".join(filter(None, [
            _get_text_part(db_project.title),
            _get_text_part(db_project.description),
            _get_text_part(_required_skills_text),
            _get_text_part(_required_roles_text),
            _get_text_part(db_project.keywords),
            _get_text_part(db_project.project_type),
            _get_text_part(db_project.expected_deliverables),
            _get_text_part(db_project.learning_outcomes),
            _get_text_part(db_project.team_size_preference),
            _get_text_part(db_project.project_status),
            _get_text_part(db_project.start_date),
            _get_text_part(db_project.end_date),
            _get_text_part(db_project.estimated_weekly_hours),
            _get_text_part(db_project.location),
            _get_text_part(db_project.cover_image_original_filename),
            _get_text_part(db_project.cover_image_type),
            attachments_text  # Re-include current attachments after deletion
        ])).strip()

        # Determine LLM API key for embedding generation (using project creator's config)
        project_creator_llm_api_key = None
        project_creator = db.query(Student).filter(Student.id == db_project.creator_id).first()
        if project_creator and project_creator.llm_api_type == "siliconflow" and project_creator.llm_api_key_encrypted:
            try:
                project_creator_llm_api_key = ai_core.decrypt_key(project_creator.llm_api_key_encrypted)
            except Exception:
                project_creator_llm_api_key = None  # Decryption failed

        project_creator_llm_type = project_creator.llm_api_type if project_creator else None
        project_creator_llm_base_url = project_creator.llm_api_base_url if project_creator else None
        project_creator_llm_model_id = project_creator.llm_model_id if project_creator else None

        embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        if db_project.combined_text:
            try:
                new_embedding = await ai_core.get_embeddings_from_api(
                    [db_project.combined_text],
                    api_key=project_creator_llm_api_key,
                    llm_type=project_creator_llm_type,
                    llm_base_url=project_creator_llm_base_url,
                    llm_model_id=project_creator_llm_model_id
                )
                if new_embedding:
                    db_project.embedding = new_embedding[0]
                else:
                    db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
                print(f"DEBUG_DELETE_PROJECT_FILE: 项目 {project_id} 嵌入向量已更新。")
            except Exception as e:
                print(f"ERROR_DELETE_PROJECT_FILE: 更新项目 {project_id} 嵌入向量失败: {e}. 嵌入向量设为零。")
                db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            db_project.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db.add(db_project)  # Mark the project for re-saving with updated embedding
        db.commit()  # Commit the project embedding update

        print(f"DEBUG_DELETE_PROJECT_FILE: 项目文件 ID: {file_id} 已成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DELETE_PROJECT_FILE_GLOBAL: 删除项目文件 {file_id} 过程中发生未知错误，事务已回滚: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除项目文件失败: {e}")


# --- Project File Management Interfaces ---
@app.post("/projects/{project_id}/files/", response_model=schemas.ProjectFileResponse,
          status_code=status.HTTP_201_CREATED, summary="为指定项目上传文件")
async def upload_project_file(
        project_id: int,
        file: UploadFile = File(..., description="要上传的项目文件（文档、代码文件等）"),
        file_data: schemas.ProjectFileCreate = Depends(),  # 使用 Depends() 来解析表单中的JSON数据
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为指定项目上传一个新文件（支持文本、文档、代码等多种文件类型）。
    只有项目的创建者或项目成员可以上传文件。
    上传时可以指定文件描述和访问权限（仅成员可见或公开）。
    """
    print(f"DEBUG_PROJECT_FILE: 用户 {current_user_id} 尝试为项目 {project_id} 上传文件 '{file.filename}'。")

    # 1. 验证项目是否存在
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

    # 2. 权限检查：只有项目创建者或项目成员可以上传文件
    is_project_creator = (db_project.creator_id == current_user_id)
    is_project_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.student_id == current_user_id,
        ProjectMember.status == "active"
    ).first() is not None

    if not (is_project_creator or is_project_member):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="无权为该项目上传文件。只有项目创建者或成员可以上传。")

    # 3. 验证文件类型：允许常见的文档、代码、文本文件
    # 允许的文件 MIME 类型（可根据需要扩展）
    allowed_mime_types = [
        "text/plain",  # .txt, .log
        "text/markdown",  # .md
        "application/pdf",  # .pdf
        "application/msword",  # .doc
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.ms-excel",  # .xls
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-powerpoint",  # .ppt
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
        "application/json",  # .json
        "application/xml",  # .xml
        "text/html",  # .html
        "text/css",  # .css
        "text/javascript",  # .js
        "application/x-python-code",  # .pyc
        "text/x-python",  # .py
        "application/x-sh",  # .sh
        # ... 更多可以添加
    ]
    # 检查是否是图片，如果不是则通过
    if file.content_type.startswith('image/'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="项目文件不支持直接上传图片。请通过项目封面上传图片，或上传图片到其他模块。")
    if file.content_type not in allowed_mime_types:
        print(f"WARNING_PROJECT_FILE: 不支持的文件类型 '{file.content_type}'。")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"不支持的文件类型: {file.content_type}。仅支持常见文档（如PDF, DOCX, XLSX）、文本和代码文件。")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已文件的变量
    oss_object_name_for_rollback = None
    try:
        # 4. 将文件上传到OSS
        file_bytes = await file.read()  # 读取文件所有字节
        file_extension = os.path.splitext(file.filename)[1]  # 获取文件扩展名

        # OSS上的文件存储路径：project_files/{project_id}/UUID.ext
        oss_path_prefix = f"project_files/{project_id}"
        current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
        oss_object_name_for_rollback = current_oss_object_name

        file_url = await oss_utils.upload_file_to_oss(
            file_bytes=file_bytes,
            object_name=current_oss_object_name,
            content_type=file.content_type
        )
        print(f"DEBUG_PROJECT_FILE: 文件 '{file.filename}' (类型: {file.content_type}) 上传到OSS成功，URL: {file_url}")

        # 5. 在数据库中创建 ProjectFile 记录
        db_project_file = ProjectFile(
            project_id=project_id,
            upload_by_id=current_user_id,
            file_name=file.filename,
            oss_object_name=current_oss_object_name,
            file_path=file_url,
            file_type=file.content_type,
            size_bytes=file.size,
            description=file_data.description,  # 从表单数据中获取描述
            access_type=file_data.access_type  # 从表单数据中获取访问权限
        )
        db.add(db_project_file)
        db.commit()
        db.refresh(db_project_file)

        # 填充上传者姓名
        uploader_student = db.query(Student).filter(Student.id == current_user_id).first()
        db_project_file._uploader_name = uploader_student.name if uploader_student else "未知用户"

        print(
            f"DEBUG_PROJECT_FILE: 项目 {project_id} 文件 '{db_project_file.file_name}' (ID: {db_project_file.id}) 上传成功，状态码 201。")
        return db_project_file

    except HTTPException as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_PROJECT_FILE: HTTP Exception raised, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_PROJECT_FILE: Unknown error during project file upload, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_PROJECT_FILE: 上传项目文件失败：{e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"上传项目文件失败: {e}")


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
    active_chats_count = db.query(ChatRoom).filter(ChatRoom.creator_id == current_user_id).count()  # 假设用户活跃的聊天室是他创建的
    unread_messages_count = 0  # 暂时为0，待实现实时消息和未读计数

    # 简历完成度 (模拟，可根据实际用户资料填写程度计算)
    student = db.query(Student).filter(Student.id == current_user_id).first()
    resume_completion_percentage = 0.0
    if student:
        completed_fields = 0
        total_fields = 10  # 假设 10 个关键字段
        if student.name and student.name != "张三": total_fields += 1
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
    """
    获取当前用户参与的（作为创建者或成员）项目卡片列表。
    可选择通过 `status_filter` (例如 "进行中", "已完成") 筛选项目。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 参与的仪表板项目列表。")

    # 查询条件：用户是项目的创建者 或者 用户是项目的成员
    # 移除 ProjectMember.status == "active" 条件，因为 ProjectMember 模型没有 status 字段
    user_is_creator_condition = Project.creator_id == current_user_id
    user_is_member_condition = db.query(ProjectMember.id).filter(
        ProjectMember.project_id == Project.id,
        ProjectMember.student_id == current_user_id
    ).exists()  # 仅检查是否存在成员记录

    query = db.query(Project).filter(or_(user_is_creator_condition, user_is_member_condition))

    if status_filter:
        query = query.filter(Project.project_status == status_filter)

    # 排序，例如按创建时间或更新时间
    projects = query.order_by(Project.created_at.desc()).all()

    project_cards = []
    for p in projects:
        # 这里模拟进度。如果项目状态是“进行中”，可以给一个默认的进行中进度（例如 0.5）。
        # 如果是“已完成”，则为 1.0 (100%)。其他状态（如“待开始”）为 0.0。
        progress = 0.0
        if p.project_status == "进行中":
            progress = 0.5  # 默认进行中进度
        elif p.project_status == "已完成":
            progress = 1.0  # 完成项目进度

        project_cards.append(schemas.DashboardProjectCard(
            id=p.id,
            title=p.title,
            progress=progress
        ))

    print(f"DEBUG: 获取到用户 {current_user_id} 参与的 {len(project_cards)} 个项目卡片。")
    return project_cards


@app.get("/dashboard/courses", response_model=List[schemas.DashboardCourseCard],
         summary="获取当前用户学习的课程卡片列表")
async def get_dashboard_courses(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[str] = None
):
    """
    获取当前用户学习的课程卡片列表。
    可选择通过 `status_filter` (例如 "in_progress", "completed") 筛选课程。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的仪表板课程列表。")

    # 优化查询：使用 joinedload 预加载关联的 Course 对象，避免 N+1 查询问题
    query = db.query(UserCourse).options(joinedload(UserCourse.course)).filter(UserCourse.student_id == current_user_id)

    if status_filter:
        query = query.filter(UserCourse.status == status_filter)

    user_courses = query.all()

    course_cards = []
    for uc in user_courses:
        # 确保 uc.course (预加载的 Course 对象) 存在
        if uc.course:
            # 确保 Course 对象的 required_skills 字段在返回时是正确的列表形式
            # 尽管 DashboardCourseCard 不直接显示 skills，但 Course 对象本身可能在ORM层加载了。
            # 这里统一处理其解析，以防万一或作为良好实践。
            course_skills = uc.course.required_skills
            if isinstance(course_skills, str):
                try:
                    course_skills = json.loads(course_skills)
                except json.JSONDecodeError:
                    course_skills = []
            elif course_skills is None:
                course_skills = []
            uc.course.required_skills = course_skills  # 更新ORM对象确保一致性

            course_cards.append(schemas.DashboardCourseCard(
                id=uc.course.id,  # 直接从预加载的 Course 对象获取 ID
                title=uc.course.title,  # 直接从预加载的 Course 对象获取 Title
                progress=uc.progress,
                last_accessed=uc.last_accessed
            ))
        else:
            print(f"WARNING: 用户 {current_user_id} 关联的课程 {uc.course_id} 未找到。")

    print(f"DEBUG: 获取到 {len(course_cards)} 门课程卡片。")
    return course_cards


# --- 笔记管理接口 ---
@app.post("/notes/", response_model=schemas.NoteResponse, summary="创建新笔记")
async def create_note(
        note_data: schemas.NoteBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传图片、视频或文件作为笔记的附件"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新笔记。
    支持直接上传文件作为附件，并支持关联课程章节信息或用户自定义文件夹。
    后端会根据记录内容生成 combined_text 和 embedding。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试创建笔记。标题: {note_data.title}，有文件：{bool(file)}，文件夹ID：{note_data.folder_id}，课程ID：{note_data.course_id}")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 0. 验证关联关系的存在和权限：课程/章节 或 文件夹
        if note_data.course_id:
            db_course = db.query(Course).filter(Course.id == note_data.course_id).first()
            if not db_course:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的课程不存在。")

        if note_data.folder_id is not None:  # 如果指定了文件夹ID (0 已经被 schema 转换为 None)
            target_folder = db.query(Folder).filter(
                Folder.id == note_data.folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not target_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="目标文件夹未找到或无权访问。")

        # 1. 处理文件上传（如果提供了文件）
        final_media_url = note_data.media_url
        final_media_type = note_data.media_type
        final_original_filename = note_data.original_filename
        final_media_size_bytes = note_data.media_size_bytes

        if file:
            if final_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            # 根据文件类型确定OSS存储路径前缀
            oss_path_prefix = "note_files"  # 默认文件
            if content_type.startswith('image/'):
                oss_path_prefix = "note_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "note_videos"

            current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=content_type
                )
                final_original_filename = file.filename
                final_media_size_bytes = file_size
                # 确保 media_type 与实际上传的文件类型一致
                if content_type.startswith('image/'):
                    final_media_type = "image"
                elif content_type.startswith('video/'):
                    final_media_type = "video"
                else:
                    final_media_type = "file"

                print(f"DEBUG: 文件 '{file.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_media_url}")

            except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
                print(f"ERROR: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出，让FastAPI处理
            except Exception as e:
                print(f"ERROR: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=f"文件上传到云存储失败: {e}")
        else:  # 没有上传文件，但可能提供了 media_url (例如用户粘贴的外部链接)
            # 验证 media_url 和 media_type 的一致性 (由 schema 校验，这里不重复，但假设通过)
            pass

        # 2. 组合文本用于嵌入
        # 根据是课程笔记还是文件夹笔记，调整combined_text内容
        context_identifier = ""
        if note_data.course_id:
            course_title = db_course.title if db_course else f"课程 {note_data.course_id}"
            context_identifier = f"课程: {course_title}. 章节: {note_data.chapter or '未指定'}."
        elif note_data.folder_id is not None:
            folder_name = target_folder.name if target_folder else f"文件夹 {note_data.folder_id}"
            context_identifier = f"文件夹: {folder_name}."

        combined_text = ". ".join(filter(None, [
            _get_text_part(note_data.title),
            _get_text_part(note_data.content),
            _get_text_part(note_data.tags),
            _get_text_part(context_identifier),  # 包含课程/文件夹上下文
            _get_text_part(final_media_url),  # 包含媒体URL
            _get_text_part(final_media_type),  # 包含媒体类型
            _get_text_part(final_original_filename),  # 包含原始文件名
        ])).strip()
        if not combined_text:
            combined_text = ""

        embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量

        # 获取当前用户的LLM配置用于嵌入生成
        note_owner = db.query(Student).filter(Student.id == current_user_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if note_owner and note_owner.llm_api_type == "siliconflow" and note_owner.llm_api_key_encrypted:
            try:
                owner_llm_api_key = ai_core.decrypt_key(note_owner.llm_api_key_encrypted)
                owner_llm_type = note_owner.llm_api_type
                owner_llm_base_url = note_owner.llm_api_base_url
                owner_llm_model_id = note_owner.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用笔记创建者配置的硅基流动 API 密钥为笔记生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密笔记创建者硅基流动 API 密钥失败: {e}。笔记嵌入将使用零向量。")
                owner_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 笔记创建者未配置硅基流动 API 类型或密钥，笔记嵌入将使用零向量或默认行为。")

        if combined_text:
            try:
                new_embedding = await ai_core.get_embeddings_from_api(
                    [combined_text],
                    api_key=owner_llm_api_key,
                    llm_type=owner_llm_type,
                    llm_base_url=owner_llm_base_url,
                    llm_model_id=owner_llm_model_id
                )
                if new_embedding:
                    embedding = new_embedding[0]
                else:
                    embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保为零向量
                print(f"DEBUG: 笔记嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR: 生成笔记嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING_EMBEDDING: 笔记 combined_text 为空，嵌入向量设为零。")

        # 3. 创建数据库记录
        db_note = Note(
            owner_id=current_user_id,
            title=note_data.title,
            content=note_data.content,
            note_type=note_data.note_type,
            course_id=note_data.course_id,  # 存储课程ID
            tags=note_data.tags,
            chapter=note_data.chapter,  # 存储章节信息
            media_url=final_media_url,  # 存储最终的媒体URL
            media_type=final_media_type,  # 存储最终的媒体类型
            original_filename=final_original_filename,  # 存储原始文件名
            media_size_bytes=final_media_size_bytes,  # 存储文件大小
            folder_id=note_data.folder_id,  # <<< 存储文件夹ID
            combined_text=combined_text,
            embedding=embedding
        )

        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        print(f"DEBUG: 笔记 (ID: {db_note.id}) 创建成功。")
        return db_note

    except HTTPException as e:  # 捕获FastAPI异常，包括OSS上传时抛出的
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_CREATE_NOTE_GLOBAL: 创建笔记失败，事务已回滚: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建笔记失败: {e}")


@app.get("/notes/", response_model=List[schemas.NoteResponse], summary="获取当前用户所有笔记")
async def get_all_notes(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        note_type: Optional[str] = None,
        course_id: Optional[int] = Query(None, description="按课程ID过滤笔记"),  # 新增课程ID过滤
        chapter: Optional[str] = Query(None, description="按章节名称过滤笔记"),  # 新增章节过滤
        folder_id: Optional[int] = Query(None,
                                         description="按自定义文件夹ID过滤笔记。传入0表示顶级文件夹（即folder_id为NULL）"),
        # 新增文件夹ID过滤
        tags: Optional[str] = Query(None, description="按标签过滤，支持模糊匹配"),  # 标签过滤 (从原有的tag改为tags)
        # Note: 原来的 tag 参数名改为 tags，与 Note 模型字段名保持一致，更清晰。
        limit: int = Query(100, description="返回的最大笔记数量"),  # 新增 limit/offset
        offset: int = Query(0, description="查询的偏移量")  # 新增 limit/offset

):
    """
    获取当前用户的所有笔记。
    可以按笔记类型 (note_type)，关联的课程ID (course_id)，章节 (chapter)，自定义文件夹ID (folder_id)，或标签 (tags) 进行过滤。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有笔记。")
    print(
        f"DEBUG_NOTE_QUERY: note_type={note_type}, course_id={course_id}, chapter={chapter}, folder_id={folder_id}, tags={tags}")

    query = db.query(Note).filter(Note.owner_id == current_user_id)

    # 过滤条件优先级或互斥性检查：
    # 根据 NoteBase 的验证逻辑，笔记不能同时属于课程/章节和自定义文件夹。
    # 因此，查询时也应保持这种互斥性。

    if folder_id is not None:  # 如果指定了 folder_id (包括 0，表示顶级文件夹)
        if course_id is not None or (chapter is not None and chapter.strip() != ""):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="无法同时按课程/章节和自定义文件夹ID过滤笔记。请选择一种方式。")
        if folder_id == 0:  # 0 表示顶级文件夹，即 folder_id 为 NULL
            query = query.filter(Note.folder_id.is_(None))
        else:
            query = query.filter(Note.folder_id == folder_id)
    elif course_id is not None:  # 如果没有指定 folder_id，但指定了 course_id
        query = query.filter(Note.course_id == course_id)
        if chapter is not None and chapter.strip() != "":
            query = query.filter(Note.chapter == chapter)
    elif chapter is not None and chapter.strip() != "":  # 如果只指定了 chapter 但没有 course_id
        # 按照 schemas.py 的验证，没有 course_id 的 chapter 是非法的，但这里可以做一个柔性处理或额外提示
        # 不过为了严格性，如果仅有 chapter 没有 course_id 则不进行过滤或报错
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="若要按章节过滤，必须同时提供课程ID (course_id)。")
    else:  # 默认情况：不按课程/章节也不按文件夹过滤，获取所有非课程非文件夹的笔记，或者所有笔记
        # 如果没有指定任何组织方式的过滤，可以默认显示所有非课程非文件夹的笔记，或者所有笔记。
        # 这里选择默认不加folder_id和course_id的过滤，即显示所有无关联的笔记，或者根据其他过滤器显示。
        # 如果需要显示所有笔记，则此处不加任何 folder_id 或 chapter/course_id 相关的 filter
        pass

    if note_type:
        query = query.filter(Note.note_type == note_type)

    if tags:  # 修改了原来 tag 变量名
        # 使用 LIKE 进行模糊匹配，因为标签是逗号分隔字符串
        query = query.filter(Note.tags.ilike(f"%{tags}%"))

    # 应用排序和分页
    notes = query.order_by(Note.created_at.desc()).offset(offset).limit(limit).all()

    # Optional: Fill folder name and course name for response based on IDs for better display
    for note in notes:
        # 如果 note 有 folder_id，加载文件夹名称
        if note.folder_id:
            # 假定 Folder model 有 name 属性
            folder_obj = db.query(Folder).filter(Folder.id == note.folder_id).first()
            if folder_obj:
                note.folder_name_for_response = folder_obj.name  # Assign to a temporary or @property in schema
        # 如果 note 有 course_id，加载课程名称
        if note.course_id:
            course_obj = db.query(Course).filter(Course.id == note.course_id).first()
            if course_obj:
                note.course_title_for_response = course_obj.title  # Assign to a temporary or @property in schema

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

    # 填充文件夹名称和课程标题用于响应
    # 如果笔记有 folder_id，加载文件夹名称
    if note.folder_id:
        folder_obj = db.query(Folder).filter(Folder.id == note.folder_id).first()
        if folder_obj:
            note.folder_name_for_response = folder_obj.name

    # 如果笔记有 course_id，加载课程名称
    if note.course_id:
        course_obj = db.query(Course).filter(Course.id == note.course_id).first()
        if course_obj:
            note.course_title_for_response = course_obj.title

    return note


@app.put("/notes/{note_id}", response_model=schemas.NoteResponse, summary="更新指定笔记")
async def update_note(
        note_id: int,
        note_data: schemas.NoteBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传图片、视频或文件作为笔记的附件"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的笔记内容。用户只能更新自己的记录。
    支持替换附件文件和更新所属课程/章节或自定义文件夹。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新笔记 ID: {note_id}。有文件: {bool(file)}")
    db_note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not db_note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")

    update_dict = note_data.dict(exclude_unset=True)

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_note.media_url 中提取旧的 OSS object name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_note.media_url and db_note.media_url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_note.media_url.replace(oss_base_url_parsed, '', 1)

    try:
        # 0. 验证关联关系的存在和权限：课程/章节 或 文件夹（如果这些字段被修改）
        # 检查 course_id 和 chapter 的变化
        new_course_id = update_dict.get("course_id", db_note.course_id)
        new_chapter = update_dict.get("chapter", db_note.chapter)

        if new_course_id is not None:
            db_course = db.query(Course).filter(Course.id == new_course_id).first()
            if not db_course:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的课程不存在。")

        # 检查 folder_id 的变化
        new_folder_id = update_dict.get("folder_id", db_note.folder_id)
        if new_folder_id is not None:  # 如果指定了文件夹ID (0 已经被 schema 转换为 None)
            target_folder = db.query(Folder).filter(
                Folder.id == new_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not target_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="目标文件夹未找到或无权访问。")

        # Re-apply mutual exclusivity validation for course/chapter vs folder
        is_course_note_candidate = (new_course_id is not None) or (
                new_chapter is not None and new_chapter.strip() != "")
        is_folder_note_candidate = (new_folder_id is not None)

        if is_course_note_candidate and is_folder_note_candidate:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="笔记不能同时关联到课程/章节和自定义文件夹。请选择一种组织方式。")

        # If it's a course note, course_id must accompany chapter
        if (new_chapter is not None and new_chapter.strip() != "") and (new_course_id is None):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="为了关联章节信息，课程ID (course_id) 不能为空。")

        # Check if media_url or media_type are explicitly being cleared or updated to non-media type
        media_url_being_cleared = "media_url" in update_dict and update_dict["media_url"] is None
        media_type_being_set = "media_type" in update_dict
        new_media_type_from_data = update_dict.get("media_type")

        should_delete_old_media_file = False
        if old_media_oss_object_name:
            if media_url_being_cleared:  # media_url is set to None
                should_delete_old_media_file = True
            elif media_type_being_set and new_media_type_from_data is None:  # media_type is set to None
                should_delete_old_media_file = True
            elif media_type_being_set and (
                    new_media_type_from_data not in ["image", "video", "file"]):  # media_type changes to non-media
                should_delete_old_media_file = True

        if should_delete_old_media_file:
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(
                    f"DEBUG: Deleted old OSS file {old_media_oss_object_name} due to media content clearance/type change.")
            except Exception as e:
                print(
                    f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during media content clearance: {e}")

            # 清空数据库中的相关媒体字段
            db_note.media_url = None
            db_note.media_type = None
            db_note.original_filename = None
            db_note.media_size_bytes = None

        # 1. 处理文件上传（如果提供了新文件）
        if file:
            target_media_type = update_dict.get("media_type")  # Get proposed media_type from client
            if target_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            # If new file replaces existing media, delete old OSS file
            if old_media_oss_object_name and not should_delete_old_media_file:  # Avoid double deletion
                try:
                    asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                    print(f"DEBUG: Deleted old OSS file: {old_media_oss_object_name} for replacement.")
                except Exception as e:
                    print(
                        f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during replacement: {e}")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            oss_path_prefix = "note_files"
            if content_type.startswith('image/'):
                oss_path_prefix = "note_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "note_videos"

            new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

            # Upload to OSS
            db_note.media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_note.original_filename = file.filename
            db_note.media_size_bytes = file_size
            db_note.media_type = target_media_type  # Use the media_type from request body

            print(f"DEBUG: New file '{file.filename}' uploaded to OSS: {db_note.media_url}")

            # If `content` was not provided in update, and it was previously text, clear it for media-only note
            if "content" not in update_dict and db_note.content:
                db_note.content = None

        elif "media_url" in update_dict and update_dict[
            "media_url"] is not None and not file:  # User provided a new URL but no file
            # If new media_url is provided without a file, it's assumed to be an external URL
            db_note.media_url = update_dict["media_url"]
            db_note.media_type = update_dict.get("media_type")  # Should be provided via schema validator
            db_note.original_filename = None
            db_note.media_size_bytes = None
            # content is optional in this case (already handled by schema)

        # 2. 应用其他 update_dict 中的字段
        # 清理掉已通过文件上传或手动处理的 media 字段，防止再次覆盖
        fields_to_skip_manual_update = ["media_url", "media_type", "original_filename", "media_size_bytes", "file"]
        for key, value in update_dict.items():
            if key in fields_to_skip_manual_update:
                continue
            if hasattr(db_note, key):
                if key == "content":  # Must not be empty if there's no media
                    if value is None or (isinstance(value, str) and not value.strip()):
                        if db_note.media_url is None:  # If no media, content must be there
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="笔记内容不能为空。")
                        else:  # If there's media, content can be cleared
                            setattr(db_note, key, value)
                    else:  # Content value is not None/empty
                        setattr(db_note, key, value)
                elif key == "title":  # Title is mandatory, cannot be None or empty
                    if value is None or (isinstance(value, str) and not value.strip()):
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="笔记标题不能为空。")
                    setattr(db_note, key, value)
                elif key == "folder_id":  # Handle folder_id separately if it's 0 to mean None
                    if value == 0:
                        db_note.folder_id = None
                    else:
                        db_note.folder_id = value
                else:  # For other fields, just apply
                    setattr(db_note, key, value)

        # 3. 重新生成 combined_text
        context_identifier = ""
        # 优先使用更新后的值来判断
        current_course_id = db_note.course_id
        current_chapter = db_note.chapter
        current_folder_id = db_note.folder_id

        if current_course_id:
            db_course_for_text = db.query(Course).filter(Course.id == current_course_id).first()
            course_title = db_course_for_text.title if db_course_for_text else f"课程 {current_course_id}"
            context_identifier = f"课程: {course_title}. 章节: {current_chapter or '未指定'}."
        elif current_folder_id is not None:
            db_folder_for_text = db.query(Folder).filter(Folder.id == current_folder_id).first()
            folder_name = db_folder_for_text.name if db_folder_for_text else f"文件夹 {current_folder_id}"
            context_identifier = f"文件夹: {folder_name}."

        db_note.combined_text = ". ".join(filter(None, [
            _get_text_part(db_note.title),
            _get_text_part(db_note.content),
            _get_text_part(db_note.tags),
            _get_text_part(context_identifier),  # 包含课程/文件夹上下文
            _get_text_part(db_note.media_url),  # 包含新的媒体URL
            _get_text_part(db_note.media_type),  # 包含新的媒体类型
            _get_text_part(db_note.original_filename),  # 包含原始文件名
        ])).strip()
        if not db_note.combined_text:
            db_note.combined_text = ""

        # 4. 获取当前用户的LLM配置用于嵌入更新
        note_owner = db.query(Student).filter(Student.id == current_user_id).first()
        owner_llm_api_key = None
        owner_llm_type = None
        owner_llm_base_url = None
        owner_llm_model_id = None

        if note_owner and note_owner.llm_api_type == "siliconflow" and note_owner.llm_api_key_encrypted:
            try:
                owner_llm_api_key = ai_core.decrypt_key(note_owner.llm_api_key_encrypted)
                owner_llm_type = note_owner.llm_api_type
                owner_llm_base_url = note_owner.llm_api_base_url
                owner_llm_model_id = note_owner.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用笔记创建者配置的硅基流动 API 密钥更新笔记嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密笔记创建者硅基流动 API 密钥失败: {e}。笔记嵌入将使用零向量。")
                owner_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 笔记创建者未配置硅基流动 API 类型或密钥，笔记嵌入将使用零向量或默认行为。")

        embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
        if db_note.combined_text:
            try:
                new_embedding = await ai_core.get_embeddings_from_api(
                    [db_note.combined_text],
                    api_key=owner_llm_api_key,
                    llm_type=owner_llm_type,
                    llm_base_url=owner_llm_base_url,
                    llm_model_id=owner_llm_model_id
                )
                if new_embedding:
                    embedding_recalculated = new_embedding[0]
                print(f"DEBUG: 笔记 {db_note.id} 嵌入向量已更新。")
            except Exception as e:
                print(f"ERROR: 更新笔记 {db_note.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING: 笔记 combined_text 为空，嵌入向量设为零。")
            embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

        db_note.embedding = embedding_recalculated  # 赋值给DB对象

        db.add(db_note)
        db.commit()
        db.refresh(db_note)
        print(f"DEBUG: 笔记 {db_note.id} 更新成功。")
        return db_note

    except HTTPException as e:  # 捕获FastAPI异常，包括OSS上传时抛出的
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {new_uploaded_oss_object_name}")
        raise e
    except Exception as e:
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_UPDATE_NOTE_GLOBAL: 更新笔记失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新笔记失败: {e}",
        )


@app.delete("/notes/{note_id}", summary="删除指定笔记")
async def delete_note(
        note_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的笔记。用户只能删除自己的记录。
    如果笔记关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    """
    print(f"DEBUG: 删除笔记 ID: {note_id}。")
    db_note = db.query(Note).filter(Note.id == note_id, Note.owner_id == current_user_id).first()
    if not db_note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or not authorized")

    # <<< 新增：如果笔记关联了文件或媒体，并且是OSS URL，则尝试从OSS删除文件 >>>
    if db_note.media_type in ["image", "video", "file"] and db_note.media_url:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_note.media_url.replace(oss_base_url_parsed, '', 1) if db_note.media_url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_NOTE: 删除了笔记 {note_id} 关联的OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_NOTE: 删除笔记 {note_id} 关联的OSS文件 {object_name} 失败: {e}")
                # 即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(f"WARNING_NOTE: 笔记 {note_id} 的 media_url ({db_note.media_url}) 无效或非OSS URL，跳过OSS文件删除。")

    db.delete(db_note)
    db.commit()
    print(f"DEBUG: 笔记 {note_id} 及其关联文件删除成功。")
    return {"message": "Note deleted successfully"}


# --- 知识库管理接口 ---
@app.post("/knowledge-bases/", response_model=schemas.KnowledgeBaseResponse, summary="创建新知识库")
async def create_knowledge_base(
        kb_data: schemas.KnowledgeBaseBase,
        current_user_id: int = Depends(get_current_user_id),  # 依赖项，已正确获取当前用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建知识库: {kb_data.name}")
    try:
        # 创建新的知识库实例，将其 owner_id 设置为当前认证用户的ID
        db_kb = KnowledgeBase(
            owner_id=current_user_id,
            name=kb_data.name,
            description=kb_data.description,
            access_type=kb_data.access_type
        )

        db.add(db_kb)
        db.commit()  # 提交到数据库
        db.refresh(db_kb)  # 刷新 db_kb 对象以获取数据库生成的ID和创建时间等

        print(f"DEBUG: 知识库 '{db_kb.name}' (ID: {db_kb.id}) 创建成功。")
        return db_kb  # 现在可以直接返回ORM对象，因为 schemas.py 已经处理了datetime的序列化问题

    except IntegrityError:
        # 捕获数据库完整性错误，例如如果某个知识库名称在用户的知识库下必须唯一
        db.rollback()  # 回滚事务
        # 给出更明确的错误提示，说明是名称冲突
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="知识库名称已存在。")
    except Exception as e:
        # 捕获其他任何未预期错误
        db.rollback()  # 确保在异常时回滚
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


# --- 知识库文件夹管理接口 ---
@app.post("/knowledge-bases/{kb_id}/folders/", response_model=schemas.KnowledgeBaseFolderResponse,
          summary="在指定知识库中创建新文件夹")
async def create_knowledge_base_folder(
        kb_id: int,
        folder_data: schemas.KnowledgeBaseFolderCreate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    在指定知识库中为当前用户创建一个新文件夹。
    可通过 parent_id 指定父文件夹，实现嵌套。
    也可作为软链接文件夹，链接课程笔记文件夹或收藏文件夹。
    如果链接的外部文件夹包含非URL视频，则拒绝链接。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试在知识库 {kb_id} 中创建文件夹: {folder_data.name} (父ID: {folder_data.parent_id})，链接类型: {folder_data.linked_folder_type}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    # 2. 处理软链接文件夹的逻辑
    if folder_data.linked_folder_type and folder_data.linked_folder_id is not None:
        # Validate that this is a top-level folder (enforced by schema already, but reinforce)
        if folder_data.parent_id is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="软链接文件夹只能是顶级文件夹，不能拥有父文件夹。")

        # Check source folder and its contents for forbidden media (video files)
        external_folder = None
        if folder_data.linked_folder_type == "note_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == folder_data.linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="引用的课程笔记文件夹未找到或无权访问。")

            # Check contents of the Note folder for video files (those hosted on OSS/local, not external streaming URLs like YouTube)
            notes_in_folder = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == folder_data.linked_folder_id
            ).all()
            for note in notes_in_folder:
                if note.media_type == "video":
                    # If it's a video type, check if its URL is an OSS URL (implies uploaded file)
                    if oss_utils.is_oss_url(note.media_url):
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                            detail="链接的课程笔记文件夹中包含视频文件（非外部链接），不支持链接。")

        elif folder_data.linked_folder_type == "collected_content_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == folder_data.linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="引用的收藏文件夹未找到或无权访问。")

            # Check contents of the CollectedContent folder for video files
            collected_contents_in_folder = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == folder_data.linked_folder_id
            ).all()

            for content_item in collected_contents_in_folder:
                if content_item.type == "video":
                    if oss_utils.is_oss_url(content_item.url):
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                            detail="链接的收藏文件夹中包含视频文件（非外部链接），不支持链接。")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的链接文件夹类型: {folder_data.linked_folder_type}。")

        # Set the name of the linked folder in KB to be the same as the external folder
        # unless a specific name is provided in folder_data.name
        if not folder_data.name and external_folder:
            folder_data.name = external_folder.name  # Use original folder name if not provided
        elif not folder_data.name:  # Fallback if no name and no external folder name
            folder_data.name = f"linked_{folder_data.linked_folder_type}_{folder_data.linked_folder_id}"

    else:  # 3. 验证父文件夹是否存在且属于同一知识库和同一用户 (如果提供了parent_id) - 仅当不是软链接时
        if folder_data.parent_id is not None:
            parent_folder = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == folder_data.parent_id,
                KnowledgeBaseFolder.kb_id == kb_id,  # 必须属于同一知识库
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not parent_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="父文件夹未找到、不属于该知识库或无权访问。")

        # A regular folder must have a name
        if not folder_data.name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹名称不能为空。")

    # 4. 创建文件夹实例
    db_kb_folder = KnowledgeBaseFolder(
        kb_id=kb_id,
        owner_id=current_user_id,
        name=folder_data.name,
        description=folder_data.description,
        parent_id=folder_data.parent_id,
        order=folder_data.order,
        linked_folder_type=folder_data.linked_folder_type,  # <<< 将软链接字段传入
        linked_folder_id=folder_data.linked_folder_id  # <<< 将软链接字段传入
    )

    db.add(db_kb_folder)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # 捕获数据库完整性错误，例如文件夹名称冲突或软链接重复
        if "_kb_folder_name_uc" in str(e) or "_kb_folder_root_name_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="在当前父文件夹下（或根目录）已存在同名文件夹。")
        elif "_kb_folder_linked_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"该外部文件夹 ({folder_data.linked_folder_type} ID:{folder_data.linked_folder_id}) 已被链接到此知识库。")
        print(f"ERROR_DB: 创建知识库文件夹发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建知识库文件夹失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 创建知识库文件夹发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建知识库文件夹失败: {e}")

    db.refresh(db_kb_folder)

    # 填充响应模型中的动态字段
    kb_name_obj = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    db_kb_folder.kb_name_for_response = kb_name_obj.name if kb_name_obj else "未知知识库"
    if db_kb_folder.parent_id:
        parent_folder_obj = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == db_kb_folder.parent_id).first()
        db_kb_folder.parent_folder_name_for_response = parent_folder_obj.name if parent_folder_obj else f"ID为{db_kb_folder.parent_id}的父文件夹"

    print(f"DEBUG: 知识库 {kb_id} 中的文件夹 '{db_kb_folder.name}' (ID: {db_kb_folder.id}) 创建成功。")
    return db_kb_folder


@app.get("/knowledge-bases/{kb_id}/folders/", response_model=List[schemas.KnowledgeBaseFolderResponse],
         summary="获取指定知识库下所有文件夹和软链接内容")
async def get_knowledge_base_folders(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        parent_id: Optional[int] = Query(None, description="按父文件夹ID过滤。传入0表示顶级文件夹（即parent_id为NULL）")
):
    """
    获取指定知识库下当前用户创建的所有文件夹。
    可通过 parent_id 过滤，获取特定父文件夹下的子文件夹。
    对于软链接文件夹，会包含其链接的外部文件夹的名称，以及其包含的有效内容数量。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 在知识库 {kb_id} 中的文件夹列表。父ID: {parent_id}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    query = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.kb_id == kb_id,
        KnowledgeBaseFolder.owner_id == current_user_id
    )

    if parent_id is not None:
        if parent_id == 0:  # 0 表示顶级文件夹，即 parent_id 为 NULL
            query = query.filter(KnowledgeBaseFolder.parent_id.is_(None))
        else:  # 查询特定父文件夹下的子文件夹，并验证父文件夹存在且属于该知识库
            existing_parent_folder = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == parent_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not existing_parent_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父文件夹未找到或无权访问。")
            query = query.filter(KnowledgeBaseFolder.parent_id == parent_id)
    else:  # 默认获取所有顶级文件夹
        query = query.filter(KnowledgeBaseFolder.parent_id.is_(None))

    folders = query.order_by(KnowledgeBaseFolder.order, KnowledgeBaseFolder.name).all()

    # 填充响应模型中的动态字段：kb_name 和 parent_folder_name 以及 item_count 和 linked_object_names
    kb_name_map = {knowledge_base.id: knowledge_base.name}  # 只有一个 knowledge_base object
    parent_folder_names_map = {
        f.parent_id: db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == f.parent_id).first().name for f in
        folders if f.parent_id}

    for folder in folders:
        folder.kb_name_for_response = kb_name_map.get(folder.kb_id)
        if folder.parent_id and folder.parent_id in parent_folder_names_map:
            folder.parent_folder_name_for_response = parent_folder_names_map[folder.parent_id]

        # 处理软链接文件夹的 item_count 和 linked_object_names
        if folder.linked_folder_type and folder.linked_folder_id is not None:
            if folder.linked_folder_type == "note_folder":
                linked_notes = db.query(Note).filter(
                    Note.owner_id == current_user_id,
                    Note.folder_id == folder.linked_folder_id
                ).all()
                folder.item_count = len(linked_notes)
                folder.linked_object_names_for_response = [n.title or n.content[:30] if n.content else n.media_url for
                                                           n in linked_notes]  # 填充笔记标题或内容片段
            elif folder.linked_folder_type == "collected_content_folder":
                linked_contents = db.query(CollectedContent).filter(
                    CollectedContent.owner_id == current_user_id,
                    CollectedContent.folder_id == folder.linked_folder_id
                ).all()
                folder.item_count = len(linked_contents)
                folder.linked_object_names_for_response = [c.title or c.content or c.url for c in
                                                           linked_contents]  # 填充收藏内容标题、文本或URL
            else:  # Should not happen if schema validation is correct
                folder.item_count = 0
                folder.linked_object_names_for_response = []
        else:
            # 计算非软链接文件夹的 item_count: 直属文章数量 + 直属文档数量 + 直属子文件夹数量
            folder.item_count = db.query(KnowledgeArticle).filter(
                KnowledgeArticle.kb_id == kb_id,
                KnowledgeArticle.author_id == current_user_id,
                KnowledgeArticle.kb_folder_id == folder.id
            ).count() + \
                                db.query(KnowledgeDocument).filter(
                                    KnowledgeDocument.kb_id == kb_id,
                                    KnowledgeDocument.owner_id == current_user_id,
                                    KnowledgeDocument.kb_folder_id == folder.id
                                ).count() + \
                                db.query(KnowledgeBaseFolder).filter(
                                    KnowledgeBaseFolder.kb_id == kb_id,
                                    KnowledgeBaseFolder.owner_id == current_user_id,
                                    KnowledgeBaseFolder.parent_id == folder.id
                                ).count()
            # 非软链接文件夹不返回 linked_object_names
            folder.linked_object_names_for_response = None

    print(f"DEBUG: 获取到 {len(folders)} 个知识库文件夹。")
    return folders


@app.get("/knowledge-bases/{kb_id}/folders/{kb_folder_id}", response_model=schemas.KnowledgeBaseFolderContentResponse,
         summary="获取指定知识库文件夹详情及其内容")  # <<< 修改 response_model
async def get_knowledge_base_folder_by_id(
        kb_id: int,
        kb_folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        include_contents: bool = Query(False, description="是否包含软链接文件夹的实际内容（仅适用于软链接文件夹）")
        # 新增参数
):
    """
    获取指定ID的知识库文件夹详情。用户只能获取自己知识库下的文件夹。
    如果文件夹是软链接，且指定 include_contents=True，则会返回其链接的实际内容列表。
    """
    print(f"DEBUG: 获取知识库 {kb_id} 中文件夹 ID: {kb_folder_id} 的详情。")
    folder = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.id == kb_folder_id,
        KnowledgeBaseFolder.kb_id == kb_id,  # 确保属于指定知识库
        KnowledgeBaseFolder.owner_id == current_user_id
    ).first()
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="知识库文件夹未找到、不属于该知识库或无权访问。")

    # 填充响应模型中的动态字段：kb_name 和 parent_folder_name 以及 item_count
    kb_name_obj = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    folder.kb_name_for_response = kb_name_obj.name if kb_name_obj else "未知知识库"
    if folder.parent_id:
        parent_folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == folder.parent_id).first()
        folder.parent_folder_name_for_response = parent_folder_obj.name if parent_folder_obj else f"ID为{folder.parent_id}的父文件夹"

    # 处理软链接文件夹的 item_count 和 linked_object_names 和 contents
    actual_contents = []  # 用于存储软链接文件夹的实际内容
    if folder.linked_folder_type and folder.linked_folder_id is not None:
        if folder.linked_folder_type == "note_folder":
            linked_notes = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == folder.linked_folder_id
            ).all()
            folder.item_count = len(linked_notes)
            folder.linked_object_names_for_response = [n.title or n.content[:30] if n.content else n.media_url for n in
                                                       linked_notes]

            if include_contents:  # 如果请求包含实际内容
                for note in linked_notes:
                    # 动态填充 NoteResponse 的 folder_name 和 course_title 便于展示
                    if note.folder_id:
                        linked_note_folder_obj = db.query(Folder).filter(Folder.id == note.folder_id).first()
                        if linked_note_folder_obj:
                            note.folder_name_for_response = linked_note_folder_obj.name
                    if note.course_id:
                        linked_note_course_obj = db.query(Course).filter(Course.id == note.course_id).first()
                        if linked_note_course_obj:
                            note.course_title_for_response = linked_note_course_obj.title
                    actual_contents.append(schemas.NoteResponse.model_validate(note, from_attributes=True))

        elif folder.linked_folder_type == "collected_content_folder":
            linked_contents_from_collection = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == folder.linked_folder_id
            ).all()
            folder.item_count = len(linked_contents_from_collection)
            folder.linked_object_names_for_response = [c.title or c.content or c.url for c in
                                                       linked_contents_from_collection]

            if include_contents:  # 如果请求包含实际内容
                for content_item in linked_contents_from_collection:
                    # 动态填充 CollectedContentResponse 的 folder_name
                    if content_item.folder_id:
                        linked_cc_folder_obj = db.query(Folder).filter(Folder.id == content_item.folder_id).first()
                        if linked_cc_folder_obj:
                            content_item.folder_name_for_response = linked_cc_folder_obj.name
                    actual_contents.append(
                        schemas.CollectedContentResponse.model_validate(content_item, from_attributes=True))
        else:  # Should not happen if schema validation is correct
            folder.item_count = 0
            folder.linked_object_names_for_response = []
    else:
        # 计算非软链接文件夹的 item_count: 直属文章数量 + 直属文档数量 + 直属子文件夹数量
        folder.item_count = db.query(KnowledgeArticle).filter(
            KnowledgeArticle.kb_id == kb_id,
            KnowledgeArticle.author_id == current_user_id,
            KnowledgeArticle.kb_folder_id == folder.id
        ).count() + \
                            db.query(KnowledgeDocument).filter(
                                KnowledgeDocument.kb_id == kb_id,
                                KnowledgeDocument.owner_id == current_user_id,
                                KnowledgeDocument.kb_folder_id == folder.id
                            ).count() + \
                            db.query(KnowledgeBaseFolder).filter(
                                KnowledgeBaseFolder.kb_id == kb_id,
                                KnowledgeBaseFolder.owner_id == current_user_id,
                                KnowledgeBaseFolder.parent_id == folder.id
                            ).count()
        # 非软链接文件夹不返回 linked_object_names 和 contents
        folder.linked_object_names_for_response = None

        # 对于非软链接文件夹，如果 include_contents 为 True，可以返回其直属文章和文档列表
        if include_contents:
            direct_articles = db.query(KnowledgeArticle).filter(
                KnowledgeArticle.kb_id == kb_id,
                KnowledgeArticle.author_id == current_user_id,
                KnowledgeArticle.kb_folder_id == folder.id
            ).all()
            direct_documents = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.kb_id == kb_id,
                KnowledgeDocument.owner_id == current_user_id,
                KnowledgeDocument.kb_folder_id == folder.id
            ).all()
            for art in direct_articles:
                art.kb_folder_name_for_response = folder.name
                actual_contents.append(schemas.KnowledgeArticleResponse.model_validate(art, from_attributes=True))
            for doc in direct_documents:
                doc.kb_folder_name_for_response = folder.name
                actual_contents.append(schemas.KnowledgeDocumentResponse.model_validate(doc, from_attributes=True))

    # Finally, assign the collected contents to the 'contents' field
    # Create the KnowledgeBaseFolderContentResponse instance by first validating the folder object against KnowledgeBaseFolderBase (which covers common properties)
    # Then manually add the 'contents' field.
    response_folder = schemas.KnowledgeBaseFolderContentResponse.model_validate(folder, from_attributes=True)
    response_folder.contents = actual_contents

    return response_folder


# project/main.py

# ... (前面的导入和类定义保持不变，确保 oss_utils 已导入) ...

@app.put("/knowledge-bases/{kb_id}/folders/{kb_folder_id}", response_model=schemas.KnowledgeBaseFolderResponse,
         summary="更新指定知识库文件夹")
async def update_knowledge_base_folder(
        kb_id: int,
        kb_folder_id: int,
        folder_data: schemas.KnowledgeBaseFolderBase,  # now includes linked_folder_type, linked_folder_id
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的知识库文件夹信息。用户只能更新自己知识库下的文件夹。
    支持修改名称、描述、父文件夹和排序。
    如果文件夹是软链接，其链接类型和ID也可更新（但有限制）。
    """
    print(f"DEBUG: 更新知识库 {kb_id} 中文件夹 ID: {kb_folder_id} 的信息。")
    db_kb_folder = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.id == kb_folder_id,
        KnowledgeBaseFolder.kb_id == kb_id,  # 确保属于指定知识库
        KnowledgeBaseFolder.owner_id == current_user_id
    ).first()
    if not db_kb_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="知识库文件夹未找到、不属于该知识库或无权访问。")

    update_dict = folder_data.dict(exclude_unset=True)

    # 1. 处理软链接相关字段的更新逻辑
    old_linked_folder_type = db_kb_folder.linked_folder_type
    old_linked_folder_id = db_kb_folder.linked_folder_id

    new_linked_folder_type = update_dict.get("linked_folder_type", old_linked_folder_type)
    new_linked_folder_id = update_dict.get("linked_folder_id", old_linked_folder_id)

    # 检查是否尝试修改为软链接状态，或修改软链接目标
    is_becoming_linked = (new_linked_folder_type and new_linked_folder_id is not None) and (
            not old_linked_folder_type or old_linked_folder_id is None or new_linked_folder_type != old_linked_folder_type or new_linked_folder_id != old_linked_folder_id)
    is_changing_from_linked_to_regular = (
            old_linked_folder_type and (new_linked_folder_type is None or new_linked_folder_id is None))

    # 规则：软链接文件夹和普通文件夹不能互相转换 (避免复杂的数据迁移和业务逻辑)
    if (is_becoming_linked and (
            db_kb_folder.articles.count() > 0 or db_kb_folder.documents.count() > 0 or db_kb_folder.children.count() > 0)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="包含内容的普通文件夹不能转换为软链接文件夹。请清空内容或删除后重新创建链接。")

    if is_changing_from_linked_to_regular and db_kb_folder.linked_folder_type:  # 如果当前就是软链接，且尝试取消链接
        # 软链接文件夹不能转换为普通文件夹（因为其本身不包含实际内容）
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="软链接文件夹不能转换为普通文件夹。如需取消链接，请删除此链接文件夹。")

    # 如果是软链接，并且链接目标正在被修改 (或首次设置)
    if is_becoming_linked:
        # 软链接文件夹不能有父文件夹
        if db_kb_folder.parent_id is not None or ("parent_id" in update_dict and update_dict[
            "parent_id"] is not None):  ## Allow setting to NULL if it had a parent, but then it must become a top-level link
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="软链接文件夹只能是顶级文件夹，不能拥有父文件夹。")

        # 验证新的软链接目标文件夹是否存在且没有视频文件
        external_folder = None
        if new_linked_folder_type == "note_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == new_linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="引用的课程笔记文件夹未找到或无权访问。")

            notes_in_folder = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == new_linked_folder_id
            ).all()
            for note in notes_in_folder:
                if note.media_type == "video" and oss_utils.is_oss_url(note.media_url):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="链接的课程笔记文件夹中包含视频文件（非外部链接），不支持链接。")

        elif new_linked_folder_type == "collected_content_folder":
            external_folder = db.query(Folder).filter(
                Folder.id == new_linked_folder_id,
                Folder.owner_id == current_user_id
            ).first()
            if not external_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="引用的收藏文件夹未找到或无权访问。")

            collected_contents_in_folder = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == new_linked_folder_id
            ).all()
            for content_item in collected_contents_in_folder:
                if content_item.type == "video" and oss_utils.is_oss_url(content_item.url):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="链接的收藏文件夹中包含视频文件（非外部链接），不支持链接。")

        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的链接文件夹类型: {new_linked_folder_type}。")

        # 更新软链接字段
        db_kb_folder.linked_folder_type = new_linked_folder_type
        db_kb_folder.linked_folder_id = new_linked_folder_id
        # 清空普通文件夹相关的字段
        db_kb_folder.parent_id = None  # 软链接文件夹必须是顶级的
        # 如果名称没有提供，默认使用外部文件夹的名称
        if not update_dict.get("name") and external_folder:
            db_kb_folder.name = external_folder.name

        # 移除已处理字段
        update_dict.pop("linked_folder_type", None)
        update_dict.pop("linked_folder_id", None)
        update_dict.pop("parent_id", None)  # Remove it if it was provided

    # 2. 处理普通文件夹的父文件夹和名称更新
    elif not old_linked_folder_type:  # 只有当它本身不是软链接时才处理这些逻辑
        # 2.1 验证新的父文件夹 (如果parent_id被修改)
        if "parent_id" in update_dict:  # 已经由 schema 转换为 None/int
            new_parent_id = update_dict["parent_id"]
            # 不能将自己设为父文件夹
            if new_parent_id == kb_folder_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹不能是自身的父级。")

            if new_parent_id is not None:  # 如果指定了新的父文件夹
                # 检查新的父文件夹是否存在，属于同一知识库，且属于当前用户
                new_parent_folder = db.query(KnowledgeBaseFolder).filter(
                    KnowledgeBaseFolder.id == new_parent_id,
                    KnowledgeBaseFolder.kb_id == kb_id,
                    KnowledgeBaseFolder.owner_id == current_user_id
                ).first()
                if not new_parent_folder:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                        detail="新的父文件夹未找到、不属于该知识库或无权访问。")

                # 检查是否会形成循环 (简单检查，深度循环需要递归检测)
                temp_check_folder = new_parent_folder
                while temp_check_folder:
                    if temp_check_folder.id == kb_folder_id:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                            detail="检测到循环依赖，无法将此文件夹设为父文件夹。")
                    temp_check_folder = temp_check_folder.parent  # 假设关系已经被正确加载到ORM对象

            db_kb_folder.parent_id = new_parent_id  # Update parent_id
            update_dict.pop("parent_id", None)  # Remove it from dict since handled

        # 2.2 检查名称冲突 (如果名称在更新中改变了)
        if "name" in update_dict and update_dict["name"] != db_kb_folder.name:
            existing_name_folder_query = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id,
                KnowledgeBaseFolder.name == update_dict["name"],
                KnowledgeBaseFolder.id != kb_folder_id  # 排除自身
            )
            # 根据父文件夹情况检查名称唯一性
            if db_kb_folder.parent_id is None:  # 当前文件夹是顶级文件夹
                existing_name_folder_query = existing_name_folder_query.filter(KnowledgeBaseFolder.parent_id.is_(None))
            else:  # 当前文件夹有父文件夹
                existing_name_folder_query = existing_name_folder_query.filter(
                    KnowledgeBaseFolder.parent_id == db_kb_folder.parent_id)

            if existing_name_folder_query.first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="在当前父文件夹下已存在同名文件夹。")

            db_kb_folder.name = update_dict["name"]  # Update name
            update_dict.pop("name", None)  # Remove it from dict since handled

        # 如果是普通文件夹，但尝试提供软链接字段，则拒绝
        if "linked_folder_type" in update_dict or "linked_folder_id" in update_dict:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="普通文件夹不能指定软链接信息。")

    # 3. 应用其他字段更新 (description, order)
    # 确保不覆盖已显式处理的字段
    for key, value in update_dict.items():
        if key in ["linked_folder_type", "linked_folder_id", "name", "parent_id"]:  # These were handled manually
            continue
        if hasattr(db_kb_folder, key) and value is not None:
            setattr(db_kb_folder, key, value)
        elif hasattr(db_kb_folder, key) and value is None:  # Allow clearing description
            if key == "description":
                setattr(db_kb_folder, key, value)

    db.add(db_kb_folder)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识库文件夹发生完整性约束错误: {e}")
        # 这里捕获唯一性约束的通用 IntegrityError
        if "_kb_folder_name_uc" in str(e) or "_kb_folder_root_name_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="更新知识库文件夹失败，在当前父文件夹下（或根目录）已存在同名文件夹。")
        elif "_kb_folder_linked_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"该外部文件夹 ({db_kb_folder.linked_folder_type} ID:{db_kb_folder.linked_folder_id}) 已被链接到此知识库。")
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新知识库文件夹失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识库文件夹发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新知识库文件夹失败: {e}")

    db.refresh(db_kb_folder)

    # 填充响应模型中的动态字段
    kb_name_obj = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    db_kb_folder.kb_name_for_response = kb_name_obj.name if kb_name_obj else "未知知识库"
    if db_kb_folder.parent_id:
        parent_folder_obj = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == db_kb_folder.parent_id).first()
        db_kb_folder.parent_folder_name_for_response = parent_folder_obj.name if parent_folder_obj else f"ID为{db_kb_folder.parent_id}的父文件夹"

    # 重新计算 item_count 和 linked_object_names
    if db_kb_folder.linked_folder_type and db_kb_folder.linked_folder_id is not None:
        if db_kb_folder.linked_folder_type == "note_folder":
            linked_notes = db.query(Note).filter(
                Note.owner_id == current_user_id,
                Note.folder_id == db_kb_folder.linked_folder_id
            ).all()
            db_kb_folder.item_count = len(linked_notes)
            db_kb_folder.linked_object_names_for_response = [n.title or n.content[:30] if n.content else n.media_url
                                                             for n in linked_notes]
        elif db_kb_folder.linked_folder_type == "collected_content_folder":
            linked_contents = db.query(CollectedContent).filter(
                CollectedContent.owner_id == current_user_id,
                CollectedContent.folder_id == db_kb_folder.linked_folder_id
            ).all()
            db_kb_folder.item_count = len(linked_contents)
            db_kb_folder.linked_object_names_for_response = [c.title or c.content or c.url for c in linked_contents]
    else:
        db_kb_folder.item_count = db.query(KnowledgeArticle).filter(
            KnowledgeArticle.kb_id == kb_id, KnowledgeArticle.author_id == current_user_id,
            KnowledgeArticle.kb_folder_id == db_kb_folder.id
        ).count() + \
                                  db.query(KnowledgeDocument).filter(
                                      KnowledgeDocument.kb_id == kb_id, KnowledgeDocument.owner_id == current_user_id,
                                      KnowledgeDocument.kb_folder_id == db_kb_folder.id
                                  ).count() + \
                                  db.query(KnowledgeBaseFolder).filter(
                                      KnowledgeBaseFolder.kb_id == kb_id,
                                      KnowledgeBaseFolder.owner_id == current_user_id,
                                      KnowledgeBaseFolder.parent_id == kb_folder_id
                                  ).count()
        db_kb_folder.linked_object_names_for_response = None

    print(f"DEBUG: 知识库文件夹 {kb_folder_id} 更新成功。")
    return db_kb_folder


@app.delete("/knowledge-bases/{kb_id}/folders/{kb_folder_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定知识库文件夹")
async def delete_knowledge_base_folder(
        kb_id: int,
        kb_folder_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定ID的知识库文件夹。
    如果是非软链接的普通文件夹，将级联删除其下所有直属文章、文档和子文件夹。
    如果是软链接文件夹，将只删除链接本身（KnowledgeBaseFolder记录），不影响被链接的原始笔记文件夹或收藏文件夹中的内容。
    用户只能删除自己知识库下的文件夹。
    """
    print(f"DEBUG: 删除知识库 {kb_id} 中的文件夹 ID: {kb_folder_id}。")
    db_kb_folder = db.query(KnowledgeBaseFolder).filter(
        KnowledgeBaseFolder.id == kb_folder_id,
        KnowledgeBaseFolder.kb_id == kb_id,
        KnowledgeBaseFolder.owner_id == current_user_id
    ).first()
    if not db_kb_folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="知识库文件夹未找到、不属于该知识库或无权访问。")

    # 判断是否是软链接文件夹
    if db_kb_folder.linked_folder_type and db_kb_folder.linked_folder_id is not None:
        # 如果是软链接文件夹，只删除 KnowledgeBaseFolder 记录自身
        # 不触发级联删除，因为它不“拥有”实际内容
        # SQLAlchemy 会自动处理不带 cascade 的关系
        db.delete(db_kb_folder)
        db.commit()
        print(
            f"DEBUG: 知识库软链接文件夹 {kb_folder_id} (链接到 {db_kb_folder.linked_folder_type} ID: {db_kb_folder.linked_folder_id}) 已成功删除（仅删除链接）。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    else:
        # 如果是普通文件夹，则删除文件夹及其所有内容（文章、文档、子文件夹）
        # `models.py` 中 KnowledgeBaseFolder 对 `articles`, `documents`, `children` 的 `cascade="all, delete-orphan"` 会处理级联删除。
        # KnowledgeDocument 和 KnowledgeArticle 的删除逻辑中包含了对应的OSS文件删除。
        db.delete(db_kb_folder)
        db.commit()
        print(f"DEBUG: 知识库普通文件夹 {kb_folder_id} 及其内容已成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 知识文章 (手动创建内容) 管理接口 ---
@app.post("/knowledge-bases/{kb_id}/articles/", response_model=schemas.KnowledgeArticleResponse,
          summary="在指定知识库中创建新文章")
async def create_knowledge_article(
        kb_id: int,
        article_data: schemas.KnowledgeArticleBase,  # now contains kb_folder_id
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    在指定知识库中创建一篇新知识文章。
    文章内容会生成嵌入并存储。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试在知识库 {kb_id} 中创建文章: {article_data.title} (文件夹ID: {article_data.kb_folder_id})")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    # 2. 验证文件夹是否存在且属于同一知识库和同一用户 (如果提供了kb_folder_id)
    target_kb_folder = None
    if article_data.kb_folder_id is not None:  # Note: 0 已经被 schema 转换为 None
        target_kb_folder = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == article_data.kb_folder_id,
            KnowledgeBaseFolder.kb_id == kb_id,  # 必须属于同一知识库
            KnowledgeBaseFolder.owner_id == current_user_id
        ).first()
        if not target_kb_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="目标文件夹未找到、不属于该知识库或无权访问。")

    # 3. 组合文本用于嵌入
    folder_context = ""
    if target_kb_folder:
        folder_context = f"属于文件夹: {target_kb_folder.name}."

    combined_text = ". ".join(filter(None, [
        _get_text_part(article_data.title),
        _get_text_part(article_data.content),
        _get_text_part(article_data.tags),
        _get_text_part(folder_context),  # 新增：包含文件夹上下文
    ])).strip()

    embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量

    # 获取文章作者的LLM配置进行嵌入生成
    author_user = db.query(Student).filter(Student.id == current_user_id).first()
    author_llm_api_key = None
    author_llm_type = None
    author_llm_base_url = None
    author_llm_model_id = None

    if author_user and author_user.llm_api_type == "siliconflow" and author_user.llm_api_key_encrypted:
        try:
            author_llm_api_key = ai_core.decrypt_key(author_user.llm_api_key_encrypted)
            author_llm_type = author_user.llm_api_type
            author_llm_base_url = author_user.llm_api_base_url
            author_llm_model_id = author_user.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用文章作者配置的硅基流动 API 密钥为文章生成嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密文章作者硅基流动 API 密钥失败: {e}。文章嵌入将使用零向量或默认行为。")
            author_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 文章作者未配置硅基流动 API 类型或密钥，文章嵌入将使用零向量或默认行为。")

    if combined_text:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text],
                api_key=author_llm_api_key,
                llm_type=author_llm_type,
                llm_base_url=author_llm_base_url,
                llm_model_id=author_llm_model_id
            )
            if new_embedding:
                embedding = new_embedding[0]
            print(f"DEBUG: 文章嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成文章嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 文章 combined_text 为空，嵌入向量设为零。")

    # 4. 创建数据库记录
    db_article = KnowledgeArticle(
        kb_id=kb_id,
        author_id=current_user_id,
        title=article_data.title,
        content=article_data.content,
        version=article_data.version,
        tags=article_data.tags,
        kb_folder_id=article_data.kb_folder_id,  # <<< 新增：存储文件夹ID
        combined_text=combined_text,
        embedding=embedding
    )

    db.add(db_article)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建知识文章发生完整性约束错误: {e}")
        # 这里可以根据具体的唯一性约束错误进行更细致的区分
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建知识文章失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 创建知识文章发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建知识文章失败: {e}")

    db.refresh(db_article)

    # 填充响应模型中的动态字段
    if db_article.kb_folder_id:
        if target_kb_folder:  # Use already fetched folder if available
            db_article.kb_folder_name_for_response = target_kb_folder.name
        else:  # Fallback in case target_kb_folder was not fetched (e.g., in a different flow)
            folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == db_article.kb_folder_id).first()
            db_article.kb_folder_name_for_response = folder_obj.name if folder_obj else f"ID为{db_article.kb_folder_id}的文件夹"

    print(f"DEBUG: 知识文章 (ID: {db_article.id}) 创建成功。")
    return db_article


@app.get("/knowledge-bases/{kb_id}/articles/", response_model=List[schemas.KnowledgeArticleResponse],
         summary="获取指定知识库的所有文章")
async def get_articles_in_knowledge_base(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        kb_folder_id: Optional[int] = Query(None,
                                            description="按知识库文件夹ID过滤。传入0表示顶级文件夹（即kb_folder_id为NULL）"),
        # <<< 新增这行
        query_str: Optional[str] = Query(None, description="按关键词搜索文章标题或内容"),  # 新增搜索功能
        tag_filter: Optional[str] = Query(None, description="按标签过滤，支持模糊匹配"),  # 新增标签过滤
        page: int = Query(1, ge=1, description="页码，从1开始"),  # 新增分页
        page_size: int = Query(20, ge=1, le=100, description="每页文章数量")  # 新增分页
):
    print(f"DEBUG: 获取知识库 {kb_id} 的文章列表，用户 {current_user_id}。文件夹ID: {kb_folder_id}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    query = db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_id == kb_id,
                                              KnowledgeArticle.author_id == current_user_id)

    # 2. 应用文件夹过滤
    if kb_folder_id is not None:
        if kb_folder_id == 0:  # 0 表示顶级文件夹，即 kb_folder_id 为 NULL
            query = query.filter(KnowledgeArticle.kb_folder_id.is_(None))
        else:  # 查询特定文件夹下的文章，并验证文件夹存在且属于该知识库
            existing_kb_folder = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == kb_folder_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not existing_kb_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定知识库文件夹未找到或无权访问。")
            query = query.filter(KnowledgeArticle.kb_folder_id == kb_folder_id)

    # 3. 应用关键词搜索 (标题或内容)
    if query_str:
        query = query.filter(
            or_(
                KnowledgeArticle.title.ilike(f"%{query_str}%"),
                KnowledgeArticle.content.ilike(f"%{query_str}%")
            )
        )

    # 4. 应用标签过滤
    if tag_filter:
        query = query.filter(KnowledgeArticle.tags.ilike(f"%{tag_filter}%"))

    # 5. 应用分页
    offset = (page - 1) * page_size
    articles = query.order_by(KnowledgeArticle.created_at.desc()).offset(offset).limit(page_size).all()

    # 6. 填充响应模型中的动态字段：文件夹名称
    # 提前加载所有相关知识库文件夹，避免 N+1 查询
    kb_folder_ids_in_results = list(
        set([article.kb_folder_id for article in articles if article.kb_folder_id is not None]))
    kb_folder_map = {f.id: f.name for f in
                     db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id.in_(kb_folder_ids_in_results)).all()}

    for article in articles:
        if article.kb_folder_id and article.kb_folder_id in kb_folder_map:
            article.kb_folder_name_for_response = kb_folder_map[article.kb_folder_id]
        elif article.kb_folder_id is None:
            article.kb_folder_name_for_response = "未分类"  # 或其他表示根目录的字符串

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

    # 填充文件夹名称用于响应
    if article.kb_folder_id:
        kb_folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == article.kb_folder_id).first()
        if kb_folder_obj:
            article.kb_folder_name_for_response = kb_folder_obj.name
        else:
            article.kb_folder_name_for_response = "未知文件夹"  # 或处理错误情况
    elif article.kb_folder_id is None:
        article.kb_folder_name_for_response = "未分类"  # 或其他表示根目录的字符串

    return article


@app.put("/knowledge-bases/{kb_id}/articles/{article_id}", response_model=schemas.KnowledgeArticleResponse,
         summary="更新指定知识文章")
async def update_knowledge_article(
        kb_id: int,
        article_id: int,
        article_data: schemas.KnowledgeArticleBase = Depends(),  # now contains kb_folder_id
        current_user_id: int = Depends(get_current_user_id),  # 只有文章作者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的知识文章内容。只有文章作者能更新。
    支持更新所属知识库文件夹。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新知识文章 ID: {article_id}。用户: {current_user_id}。文件夹ID: {article_data.kb_folder_id}")
    db_article = db.query(KnowledgeArticle).filter(
        KnowledgeArticle.id == article_id,
        KnowledgeArticle.kb_id == kb_id,
        KnowledgeArticle.author_id == current_user_id
    ).first()
    if not db_article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识文章未找到或无权访问。")

    update_dict = article_data.dict(exclude_unset=True)

    # 1. 验证知识库文件夹是否存在且属于同一知识库和同一用户 (如果 kb_folder_id 被修改)
    target_kb_folder_for_update = None
    if "kb_folder_id" in update_dict:  # 已经由 schema 转换为 None/int
        new_kb_folder_id = update_dict["kb_folder_id"]
        if new_kb_folder_id is not None:
            target_kb_folder_for_update = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == new_kb_folder_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not target_kb_folder_for_update:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="目标知识库文件夹未找到、不属于该知识库或无权访问。")
        db_article.kb_folder_id = new_kb_folder_id  # Update folder_id in ORM object

    # 2. 应用其他 update_dict 中的字段
    for key, value in update_dict.items():
        if key == "kb_folder_id":  # This was handled manually
            continue
        if hasattr(db_article, key) and value is not None:
            setattr(db_article, key, value)
        elif hasattr(db_article, key) and value is None:  # Allow clearing tags, content etc. if None is passed
            if key in ["title", "content"]:  # title and content are generally never None/empty
                if not value or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"文章'{key}'不能为空。")
            setattr(db_article, key, value)

    # 3. 重新生成 combined_text
    # 优先使用已经获取的 target_kb_folder_for_update，如果没有，再根据 db_article.kb_folder_id 查询
    folder_context_text = ""
    if db_article.kb_folder_id:
        if target_kb_folder_for_update:
            folder_context_text = f"属于文件夹: {target_kb_folder_for_update.name}."
        else:  # If folder_id changed to an existing ID but not via update_dict, query it.
            current_kb_folder_from_db = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == db_article.kb_folder_id).first()
            folder_context_text = f"属于文件夹: {current_kb_folder_from_db.name}." if current_kb_folder_from_db else ""

    combined_text = ". ".join(filter(None, [
        _get_text_part(db_article.title),
        _get_text_part(db_article.content),
        _get_text_part(db_article.tags),
        _get_text_part(folder_context_text),  # 包含文件夹上下文
    ])).strip()
    if not combined_text:
        combined_text = ""

    # 获取文章作者的LLM配置用于嵌入更新 (作者已在权限依赖中确认)
    author_user = db.query(Student).filter(Student.id == current_user_id).first()
    author_llm_api_key = None
    author_llm_type = None
    author_llm_base_url = None
    author_llm_model_id = None

    if author_user and author_user.llm_api_type == "siliconflow" and author_user.llm_api_key_encrypted:
        try:
            author_llm_api_key = ai_core.decrypt_key(author_user.llm_api_key_encrypted)
            author_llm_type = author_user.llm_api_type
            author_llm_base_url = author_user.llm_api_base_url
            author_llm_model_id = author_user.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用文章作者配置的硅基流动 API 密钥更新文章嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密文章作者硅基流动 API 密钥失败: {e}。文章嵌入将使用零向量或默认行为。")
            author_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 文章作者未配置硅基流动 API 类型或密钥，文章嵌入将使用零向量或默认行为。")

    embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if combined_text:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text],
                api_key=author_llm_api_key,
                llm_type=author_llm_type,
                llm_base_url=author_llm_base_url,
                llm_model_id=author_llm_model_id
            )
            if new_embedding:
                embedding_recalculated = new_embedding[0]
            print(f"DEBUG: 文章 {db_article.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新文章 {db_article.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 文章 combined_text 为空，嵌入向量设为零。")
        embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db_article.embedding = embedding_recalculated  # 赋值给DB对象

    db.add(db_article)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识文章发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新知识文章失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 更新知识文章发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新知识文章失败: {e}")

    db.refresh(db_article)
    # 填充响应模型中的动态字段
    if db_article.kb_folder_id:
        if target_kb_folder_for_update:  # Use already fetched folder if available
            db_article.kb_folder_name_for_response = target_kb_folder_for_update.name
        else:  # Fallback in case folder_id exists but was not just fetched as target_kb_folder_for_update
            folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == db_article.kb_folder_id).first()
            db_article.kb_folder_name_for_response = folder_obj.name if folder_obj else f"ID为{db_article.kb_folder_id}的文件夹"

    print(f"INFO: 知识文章 {db_article.id} 更新成功。")
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
        kb_folder_id: Optional[int] = Query(None,
                                            description="可选：指定知识库文件夹ID。传入0表示顶级文件夹（即kb_folder_id为NULL）"),
        # New parameter for folder association
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    上传一个新文档（TXT, MD, PDF, DOCX, 图片文件）到指定知识库。
    不支持上传视频文件。
    文档内容将在后台异步处理，包括文本提取、分块和嵌入生成。
    """
    print(
        f"DEBUG_UPLOAD: 用户 {current_user_id} 尝试上传文件 '{file.filename}' 到知识库 {kb_id} (文件夹ID: {kb_folder_id})。")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    # 2. 验证知识库文件夹是否存在且属于同一知识库和同一用户 (如果提供了kb_folder_id)
    target_kb_folder = None
    if kb_folder_id is not None:  # Note: 0 已经被 schema 转换为 None
        target_kb_folder = db.query(KnowledgeBaseFolder).filter(
            KnowledgeBaseFolder.id == kb_folder_id,
            KnowledgeBaseFolder.kb_id == kb_id,  # 必须属于同一知识库
            KnowledgeBaseFolder.owner_id == current_user_id
        ).first()
        if not target_kb_folder:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="目标知识库文件夹未找到、不属于该知识库或无权访问。")
        # 验证目标文件夹是否是“软链接”文件夹
        # Linked_folder_type 字段将在下一步添加到 KnowledgeBaseFolder 模型中，请确保它存在
        if hasattr(target_kb_folder, 'linked_folder_type') and target_kb_folder.linked_folder_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能将文件上传到软链接文件夹。")

    # 3. 验证文件类型：只允许特定文档和图片，拒绝视频
    allowed_mime_types = [
        "text/plain",  # .txt
        "text/markdown",  # .md
        "application/pdf",  # .pdf
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "text/html",  # .html (可选，如果也要处理网页)
        "application/vnd.ms-excel",  # .xls (可选)
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx (可选)
        "application/vnd.ms-powerpoint",  # .ppt (可选)
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx (可选)
        "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"  # 常见图片类型
    ]
    if file.content_type not in allowed_mime_types:
        if file.content_type.startswith('video/'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持上传视频文件到知识库。")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的文件类型: {file.content_type}。仅支持TXT, MD, PDF, DOCX, 图片文件及常见Office文档。")

    # 4. 将文件上传到OSS
    file_bytes = await file.read()  # 读取文件所有字节
    file_extension = os.path.splitext(file.filename)[1]  # 获取文件扩展名

    # 根据文件类型确定OSS存储路径前缀
    oss_path_prefix = "knowledge_documents"  # 默认文档
    if file.content_type.startswith('image/'):
        oss_path_prefix = "knowledge_images"
    # 如果要支持更多类型，这里可以扩展
    # elif file.content_type.startswith('application/vnd.openxmlformats-officedocument'):
    #     oss_path_prefix = "knowledge_office_files"

    object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"  # OSS上的文件路径和名称

    try:
        oss_url = await oss_utils.upload_file_to_oss(
            file_bytes=file_bytes,
            object_name=object_name,
            content_type=file.content_type
        )
        print(f"DEBUG_UPLOAD: 文件 '{file.filename}' 上传到OSS成功，URL: {oss_url}")
    except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
        print(f"ERROR_UPLOAD: 上传文件到OSS失败: {e.detail}")
        raise e  # 直接重新抛出，让FastAPI处理
    except Exception as e:
        print(f"ERROR_UPLOAD: 上传文件到OSS时发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

    # 5. 在数据库中创建初始文档记录 (状态为 processing)
    # file_path 现在存储的是 OSS 的 URL
    db_document = KnowledgeDocument(
        kb_id=kb_id,
        owner_id=current_user_id,
        file_name=file.filename,
        file_path=oss_url,  # 现在存储的是OSS URL
        file_type=file.content_type,
        kb_folder_id=kb_folder_id,  # <<< 存储文件夹ID
        status="processing",
        processing_message="文件已上传到云存储，等待处理..."
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    # 6. 异步启动后台处理任务 (传入 db.session 的当前状态)
    from database import SessionLocal
    background_db_session = SessionLocal()  # 创建一个新的会话
    asyncio.create_task(
        process_document_in_background(
            db_document.id,
            current_user_id,
            kb_id,
            object_name,  # 这里传递OSS对象名称
            file.content_type,
            background_db_session
        )
    )

    # Fill folder name for response
    if db_document.kb_folder_id:
        if target_kb_folder:
            db_document.kb_folder_name_for_response = target_kb_folder.name
        else:  # Fallback query
            folder_obj = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == db_document.kb_folder_id).first()
            db_document.kb_folder_name_for_response = folder_obj.name if folder_obj else "未分类"  # Or handle as error
    else:
        db_document.kb_folder_name_for_response = "未分类"  # For top-level documents

    print(f"DEBUG_UPLOAD: 文档 {db_document.id} 已接受上传，后台处理中。")
    return db_document


@app.get("/knowledge-bases/{kb_id}/documents/", response_model=List[schemas.KnowledgeDocumentResponse],
         summary="获取知识库下所有知识文档")
async def get_knowledge_base_documents(
        kb_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        kb_folder_id: Optional[int] = Query(None,
                                            description="按知识库文件夹ID过滤。传入0表示顶级文件夹（即kb_folder_id为NULL）"),
        # <<< 新增这行
        status_filter: Optional[str] = Query(None, description="按处理状态过滤（processing, completed, failed）"),
        # 根据状态过滤
        query_str: Optional[str] = Query(None, description="按关键词搜索文件名"),  # 新增搜索功能
        page: int = Query(1, ge=1, description="页码，从1开始"),  # 新增分页
        page_size: int = Query(20, ge=1, le=100, description="每页文档数量")  # 新增分页
):
    """
    获取指定知识库下所有知识文档（已上传文件）的列表。
    可以按文件夹ID、处理状态和文件名关键词进行过滤。
    """
    print(f"DEBUG: 获取知识库 {kb_id} 的文档列表，用户 {current_user_id}。文件夹ID: {kb_folder_id}")

    # 1. 验证知识库是否存在且属于当前用户
    knowledge_base = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id,
                                                    KnowledgeBase.owner_id == current_user_id).first()
    if not knowledge_base:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库未找到或无权访问。")

    query = db.query(KnowledgeDocument).filter(KnowledgeDocument.kb_id == kb_id,
                                               KnowledgeDocument.owner_id == current_user_id)

    # 2. 应用文件夹过滤
    if kb_folder_id is not None:
        if kb_folder_id == 0:  # 0 表示顶级文件夹，即 kb_folder_id 为 NULL
            query = query.filter(KnowledgeDocument.kb_folder_id.is_(None))
        else:  # 查询特定文件夹下的文档，并验证文件夹存在且属于该知识库
            existing_kb_folder = db.query(KnowledgeBaseFolder).filter(
                KnowledgeBaseFolder.id == kb_folder_id,
                KnowledgeBaseFolder.kb_id == kb_id,
                KnowledgeBaseFolder.owner_id == current_user_id
            ).first()
            if not existing_kb_folder:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定知识库文件夹未找到或无权访问。")
            query = query.filter(KnowledgeDocument.kb_folder_id == kb_folder_id)

    # 3. 应用状态过滤
    if status_filter:
        query = query.filter(KnowledgeDocument.status == status_filter)

    # 4. 应用关键词搜索 (文件名)
    if query_str:
        query = query.filter(KnowledgeDocument.file_name.ilike(f"%{query_str}%"))

    # 5. 应用分页
    offset = (page - 1) * page_size
    documents = query.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(page_size).all()

    # 6. 填充响应模型中的动态字段：文件夹名称
    # 提前加载所有相关知识库文件夹，避免 N+1 查询
    kb_folder_ids_in_results = list(set([doc.kb_folder_id for doc in documents if doc.kb_folder_id is not None]))
    kb_folder_map = {f.id: f.name for f in
                     db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id.in_(kb_folder_ids_in_results)).all()}

    for doc in documents:
        if doc.kb_folder_id and doc.kb_folder_id in kb_folder_map:
            doc.kb_folder_name_for_response = kb_folder_map[doc.kb_folder_id]
        elif doc.kb_folder_id is None:
            doc.kb_folder_name_for_response = "未分类"  # 或其他表示根目录的字符串

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

    if document.kb_folder_id:
        kb_folder_obj = db.query(KnowledgeBaseFolder).filter(KnowledgeBaseFolder.id == document.kb_folder_id).first()
        if kb_folder_obj:
            document.kb_folder_name_for_response = kb_folder_obj.name
        else:
            document.kb_folder_name_for_response = "未知文件夹"  # 或处理错误情况
    elif document.kb_folder_id is None:
        document.kb_folder_name_for_response = "未分类"  # 或其他表示根目录的字符串

    return document


@app.delete("/knowledge-bases/{kb_id}/documents/{document_id}", summary="删除指定知识文档")
async def delete_knowledge_document(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定知识库下的指定知识文档及其所有文本块和OSS文件。
    """
    print(f"DEBUG: 删除文档 ID: {document_id}。")
    db_document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not db_document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    # <<< 修改：从OSS删除文件 >>>
    # 从OSS URL中解析出 object_name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    object_name = db_document.file_path.replace(oss_base_url_parsed, '', 1) if db_document.file_path.startswith(
        oss_base_url_parsed) else db_document.file_path

    if object_name:
        try:
            await oss_utils.delete_file_from_oss(object_name)
            print(f"DEBUG: 已删除OSS文件: {object_name}")
        except Exception as e:
            print(f"ERROR: 删除OSS文件 {object_name} 失败: {e}")
            # 这里不抛出异常，即使OSS文件删除失败，也应该允许数据库记录被删除
    else:
        print(f"WARNING: 文档 {document_id} 的 file_path 无效或非OSS URL: {db_document.file_path}，跳过OSS文件删除。")

    # 删除数据库记录（级联删除所有文本块）
    db.delete(db_document)
    db.commit()
    print(f"DEBUG: 文档 {document_id} 及其文本块已从数据库删除。")
    return {"message": "Knowledge document deleted successfully"}


# --- GET 请求获取文档内容 (为了方便调试检查后台处理结果) ---
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

    # if document.status != "completed": # 原始如果只从 chunk 拿就检查完成状态
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
    #                         detail=f"文档状态为 '{document.status}'，文本处理尚未完成或失败。")

    # 直接从数据库的 chunks 获取完整内容，而不是尝试重新解析文件
    # 拼接所有文本块的内容
    # 这是一个更可靠的方式来获取处理后的文档文本
    chunks = db.query(KnowledgeDocumentChunk).filter(
        KnowledgeDocumentChunk.document_id == document_id
    ).order_by(KnowledgeDocumentChunk.chunk_index).all()

    if not chunks:
        # 如果没有文本块，但文档状态是 completed，说明可能内容为空
        if document.status == "completed":
            return {"content": "文档已处理完成，但内容为空。"}
        else:  # 否则还在处理中或失败
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"文档状态为 '{document.status}'，文本处理尚未完成或失败，暂无内容。")

    full_content = "\n".join([c.content for c in chunks])
    return {"content": full_content}


@app.get("/knowledge-bases/{kb_id}/documents/{document_id}/chunks",
         response_model=List[schemas.KnowledgeDocumentChunkResponse], summary="获取知识文档文本块列表 (DEBUG)")
async def get_document_chunks(
        kb_id: int,
        document_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
):
    """
    获取指定知识文档的所有文本块列表 (用于调试)。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试获取知识库 {kb_id} 中文档 {document_id} 的文本块。")
    document = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.kb_id == kb_id,
        KnowledgeDocument.owner_id == current_user_id
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档未找到或无权访问。")

    # 核心权限检查2：确保文档已经处理完成 (如果还在处理中，则没有文本块可返回或者不应该暴露)
    if document.status != "completed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="文档仍在处理中，文本块暂不可用。")

    # 检索对应文档的所有文本块
    chunks = db.query(KnowledgeDocumentChunk).filter(
        KnowledgeDocumentChunk.document_id == document_id,
        KnowledgeDocumentChunk.kb_id == kb_id,  # 确保文本块也属于这个知识库
        KnowledgeDocumentChunk.owner_id == current_user_id
    ).order_by(KnowledgeDocumentChunk.chunk_index).all()  # 按索引排序，方便查看

    print(f"DEBUG: 文档 {document_id} 获取到 {len(chunks)} 个文本块。")
    return chunks


# 辅助函数：清理可选的 JSON 字符串参数
def _clean_optional_json_string_input(input_str: Optional[str]) -> Optional[str]:
    """
    清理从表单接收到的可选JSON字符串参数。
    将 None, 空字符串, 或常见的默认值字面量转换为 None。

    """
    if input_str is None:
        return None

    stripped_str = input_str.strip()

    # 将空字符串或常见的默认值占位符视为None
    invalid_values = ["", "string", "null", "undefined", "none"]
    if stripped_str.lower() in invalid_values:
        return None

    return stripped_str


@app.get("/ai/conversations/{conversation_id}/files/status", summary="查询对话中文件处理状态")
async def get_conversation_files_status(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """查询指定对话中所有临时文件的处理状态"""
    # 验证对话归属
    conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在或无权访问")

    # 获取对话中的所有临时文件
    temp_files = db.query(AIConversationTemporaryFile).filter(
        AIConversationTemporaryFile.conversation_id == conversation_id
    ).all()

    files_status = []
    for tf in temp_files:
        files_status.append({
            "id": tf.id,
            "filename": tf.original_filename,
            "status": tf.status,
            "processing_message": tf.processing_message,
            "created_at": tf.created_at.isoformat() if tf.created_at else None,
            "has_content": bool(tf.extracted_text and tf.extracted_text.strip())
        })

    return {
        "conversation_id": conversation_id,
        "files_count": len(files_status),
        "files": files_status
    }


@app.post("/ai/qa", response_model=schemas.AIQAResponse, summary="AI智能问答 (通用、RAG或工具调用)")
async def ai_qa(
        query: str = Form(..., description="用户的问题文本"),
        conversation_id: Optional[int] = Form(None, description="要继续的对话Session ID。如果为空，则开始新的对话。"),
        kb_ids_json: Optional[str] = Form(None, description="要检索的知识库ID列表，格式为JSON字符串。例如: '[1, 2, 3]'"),
        use_tools: Optional[bool] = Form(False, description="是否启用AI智能工具调用"),
        preferred_tools_json: Optional[str] = Form(None,
                                                   description="AI在工具模式下偏好使用的工具类型。支持: JSON数组('[\"rag\", \"mcp_tool\"]')、'All'(所有工具)、或None(无工具)"),
        llm_model_id: Optional[str] = Form(None, description="本次会话使用的LLM模型ID"),  # <- 这里会从表单接收
        uploaded_file: Optional[UploadFile] = File(None,
                                                   description="可选：上传文件（图片或文档）对AI进行提问"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    使用LLM进行问答，并支持对话历史记录。
    支持上传文件或图片作为临时上下文对AI进行提问。

    - `query`：用户的问题文本。
    - `conversation_id`：如果为空，则开始新的对话。否则，加载指定对话的历史记录作为LLM的上下文。
    - `use_tools` 为 `False`：通用问答。
    - `use_tools` 为 `True`：启用工具模式，具体行为取决于 `preferred_tools_json`：
      * `preferred_tools_json` = `None`：不启用任何工具
      * `preferred_tools_json` = `"All"`：启用所有可用工具（RAG、网络搜索、MCP工具）
      * `preferred_tools_json` = `'["rag", "mcp_tool"]'`：只启用指定的工具类型
      * `preferred_tools_json` = `'[]'`：明确不启用任何工具
    """
    print(
        f"DEBUG: 用户 {current_user_id} 提问: {query}，使用工具模式: {use_tools}，偏好工具(json): {preferred_tools_json}，文件: {uploaded_file.filename if uploaded_file else '无'}")

    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    kb_ids_json = _clean_optional_json_string_input(kb_ids_json)
    preferred_tools_json = _clean_optional_json_string_input(preferred_tools_json)
    # --- 新增 --- 对 llm_model_id 进行清理，解决 "string" 的问题
    llm_model_id = _clean_optional_json_string_input(llm_model_id)
    # -------------

    actual_kb_ids: Optional[List[int]] = None
    if kb_ids_json:
        try:
            actual_kb_ids = json.loads(kb_ids_json)
            if not isinstance(actual_kb_ids, list) or not all(isinstance(x, int) for x in actual_kb_ids):
                raise ValueError("kb_ids 必须是一个整数列表格式的JSON字符串。")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"kb_ids 格式不正确: {e}。应为 JSON 整数列表。")

    actual_preferred_tools: Optional[List[Literal["rag", "web_search", "mcp_tool"]]] = None
    # 只有在启用工具时才解析preferred_tools_json，避免不必要的处理
    if use_tools and preferred_tools_json:
        try:
            # 特殊处理："All" 表示使用所有可用工具
            if preferred_tools_json.strip().lower() == "all":
                actual_preferred_tools = "all"  # 特殊标记，表示使用所有工具
                print(f"DEBUG: 用户选择启用所有可用工具")
            else:
                parsed_tools = json.loads(preferred_tools_json)

                # 改进：处理 JSON null 值
                if parsed_tools is None:
                    actual_preferred_tools = None
                    print(f"DEBUG: 用户提供了 JSON null 值，视为不使用任何工具")
                elif not isinstance(parsed_tools, list):
                    raise ValueError("偏好工具配置必须是工具名称列表（如 '[\"rag\", \"mcp_tool\"]'）或 'All'。")
                elif not all(isinstance(x, str) for x in parsed_tools):
                    raise ValueError("偏好工具配置中的所有工具名称必须是字符串。")
                elif len(parsed_tools) == 0:
                    # 如果解析后是空数组，视为None处理
                    actual_preferred_tools = None
                    print(f"DEBUG: 用户提供了空的工具列表，视为不使用任何工具")
                else:
                    valid_tool_types = ["rag", "web_search", "mcp_tool"]
                    invalid_tools = [tool for tool in parsed_tools if tool not in valid_tool_types]
                    if invalid_tools:
                        raise ValueError(f"包含不支持的工具类型：{invalid_tools}。支持的工具类型：{valid_tool_types}")
                    actual_preferred_tools = parsed_tools
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"偏好工具配置格式错误：{str(e)} 请使用工具名称的JSON数组格式（如 '[\"rag\", \"mcp_tool\"]'）或 'All' 表示所有工具。")
    elif use_tools and not preferred_tools_json:
        # 改进：当工具启用但没有提供偏好工具配置时，给出更明确的提示
        actual_preferred_tools = None
        print(
            f"DEBUG: 用户 {current_user_id} 启用了工具模式但未指定偏好工具，将不启用任何工具。建议明确指定工具类型或使用 'All'。")
    elif not use_tools and preferred_tools_json:
        # 当工具未启用但提供了偏好工具配置时，给出警告信息
        print(f"WARNING: 用户 {current_user_id} 提供了偏好工具配置但未启用工具模式，偏好工具配置将被忽略。")

    # 1. 获取或创建 AI Conversation
    db_conversation: AIConversation
    past_messages_for_llm: List[Dict[str, Any]] = []

    # 标识是否是新创建的对话，用于决定是否在第一轮问答后生成标题
    is_new_and_first_message_exchange = False

    if conversation_id:
        db_conversation = db.query(AIConversation).filter(
            AIConversation.id == conversation_id,
            AIConversation.user_id == current_user_id
        ).first()
        if not db_conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="指定的对话未找到或无权访问。")

        # 加载历史消息作为LLM的上下文，并转换为字典格式
        raw_past_messages = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == db_conversation.id
        ).order_by(AIConversationMessage.sent_at).limit(20).all()  # 限制为最近20条消息

        past_messages_for_llm = [msg.to_dict() for msg in raw_past_messages]

        print(f"DEBUG_AI_CONV: 加载了 {len(past_messages_for_llm)} 条历史消息作为上下文。")

    else:
        # 创建新对话时，标题先为 None，表示等待AI生成
        db_conversation = AIConversation(user_id=current_user_id, title=None)
        db.add(db_conversation)
        db.flush()  # 这里刷新一次以获取新对话的 ID
        is_new_and_first_message_exchange = True  # 标记为新对话的首次消息交换
        print(f"DEBUG_AI_CONV: 创建了新的对话 session ID: {db_conversation.id}，标题待生成。")

    # --- LLM配置变量的初始化，确保作用域和默认值 ---
    user_llm_api_type: Optional[str] = None
    user_llm_api_key: Optional[str] = None
    user_llm_api_base_url: Optional[str] = None
    user_llm_model_id_configured: Optional[str] = None

    # 从用户配置中获取LLM信息
    user_llm_api_type = user.llm_api_type
    user_llm_api_base_url = user.llm_api_base_url
    user_llm_model_id_configured = user.llm_model_id  # 用户配置的模型ID（兼容性）

    # 优先级：1. 请求指定的模型 2. 用户多模型配置 3. 用户单模型配置
    if llm_model_id:
        llm_model_id_final = llm_model_id
    else:
        llm_model_id_final = ai_core.get_user_model_for_provider(
            user.llm_model_ids,
            user.llm_api_type,
            user.llm_model_id
        )

    if not user_llm_api_type or not user.llm_api_key_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="User has not configured LLM API type or key. Please configure it in user settings.")

    try:
        user_llm_api_key = ai_core.decrypt_key(user.llm_api_key_encrypted)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to decrypt LLM API key. Please reconfigure.")

    # 文件上传处理逻辑
    temp_file_ids_for_context: List[int] = []
    if uploaded_file:
        allowed_mime_types = [
            "text/plain", "text/markdown", "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"
        ]
        if uploaded_file.content_type not in allowed_mime_types:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"不支持的文件类型: {uploaded_file.content_type}。仅支持文本、PDF、DOCX和图片文件。")

        file_bytes = await uploaded_file.read()
        file_extension = os.path.splitext(uploaded_file.filename)[1]

        oss_object_name = f"ai_chat_temp_files/{uuid.uuid4().hex}{file_extension}"

        try:
            await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=oss_object_name,
                content_type=uploaded_file.content_type
            )
            print(f"DEBUG_AI_QA: 文件 '{uploaded_file.filename}' 上传到OSS成功: {oss_object_name}")

            temp_file_record = AIConversationTemporaryFile(
                conversation_id=db_conversation.id,
                oss_object_name=oss_object_name,
                original_filename=uploaded_file.filename,
                file_type=uploaded_file.content_type,
                status="pending",
                processing_message="文件已上传，等待处理文本和生成嵌入..."
            )
            db.add(temp_file_record)
            db.flush()  # 获取ID

            # 立即提交这条记录，确保后台任务能够看到它
            db.commit()

            temp_file_ids_for_context.append(temp_file_record.id)

            from database import SessionLocal
            # 创建一个独立的会话用于后台任务，避免与当前请求事务冲突
            background_db_session = SessionLocal()

            # 立即启动后台任务并添加错误处理
            task = asyncio.create_task(
                process_ai_temp_file_in_background(
                    temp_file_record.id,
                    current_user_id,
                    oss_object_name,
                    uploaded_file.content_type,
                    background_db_session
                )
            )

            # 添加任务完成回调来处理异常
            def task_done_callback(task_result):
                try:
                    if task_result.exception():
                        print(f"ERROR_AI_TEMP_FILE_TASK: 后台任务异常: {task_result.exception()}")
                    else:
                        print(f"DEBUG_AI_TEMP_FILE_TASK: 后台任务完成")
                except Exception as e:
                    print(f"ERROR_AI_TEMP_FILE_TASK: 任务回调异常: {e}")

            task.add_done_callback(task_done_callback)

            print(f"DEBUG_AI_QA: 后台文件处理任务已启动，任务ID: {temp_file_record.id}")

            file_link = f"{oss_utils.OSS_BASE_URL.rstrip('/')}/{oss_object_name}"
            # 将文件信息加入当前查询，提示LLM
            file_prompt = f"\n\n[用户上传了一个文件，名为 '{uploaded_file.filename}' ({uploaded_file.content_type})。链接: {file_link}。请尝试利用其内容。文件内容将通过RAG工具提供。]"
            query += file_prompt

        except Exception as e:
            db.rollback()
            print(f"ERROR_AI_QA: 处理上传文件失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"处理上传文件失败: {e}")

    # --- 优化：快速检查文件处理状态，不长时间等待 ---
    if temp_file_ids_for_context:
        print(f"DEBUG_AI_QA: 检查 {len(temp_file_ids_for_context)} 个临时文件的初始状态...")

        # 快速检查一次，不等待
        completed_files = db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
            AIConversationTemporaryFile.status == "completed"
        ).all()

        pending_files = db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
            AIConversationTemporaryFile.status.in_(["pending", "processing"])
        ).all()

        failed_files = db.query(AIConversationTemporaryFile).filter(
            AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
            AIConversationTemporaryFile.status == "failed"
        ).all()

        print(
            f"DEBUG_AI_QA: 文件状态统计 - 已完成: {len(completed_files)}, 处理中: {len(pending_files)}, 失败: {len(failed_files)}")

        # 如果有文件正在处理，只等待很短时间（最多5秒）
        if pending_files:
            print(f"DEBUG_AI_QA: 有文件正在处理中，等待最多5秒...")
            wait_count = 0
            max_quick_wait = 5  # 最多等待5秒

            while wait_count < max_quick_wait and pending_files:
                await asyncio.sleep(1)
                wait_count += 1

                # 重新检查状态
                pending_files = db.query(AIConversationTemporaryFile).filter(
                    AIConversationTemporaryFile.id.in_(temp_file_ids_for_context),
                    AIConversationTemporaryFile.status.in_(["pending", "processing"])
                ).all()

                if not pending_files:
                    print(f"DEBUG_AI_QA: 所有文件处理完成，用时 {wait_count} 秒")
                    break

            if pending_files:
                print(f"DEBUG_AI_QA: 快速等待结束，仍有 {len(pending_files)} 个文件在处理中，继续AI查询")

        # 刷新数据库会话
        db.expire_all()
        db.commit()

    try:
        # 2. 调用 invoke_agent 获取当前轮次的所有消息和最终答案
        agent_raw_response = await ai_core.invoke_agent(
            db=db,
            user_id=current_user_id,
            query=query,
            llm_api_type=user_llm_api_type,
            llm_api_key=user_llm_api_key,
            llm_api_base_url=user_llm_api_base_url,
            llm_model_id=llm_model_id_final,
            kb_ids=actual_kb_ids,
            # note_ids 参数已移除，不再支持笔记RAG
            preferred_tools=actual_preferred_tools,
            past_messages=past_messages_for_llm,
            temp_file_ids=temp_file_ids_for_context,
            conversation_id_for_temp_files=db_conversation.id,
            enable_tool_use=use_tools
        )

        # 3. 持久化当前轮次的所有消息并立即刷新，以便获取 ID 和时间戳
        messages_for_db_commit = []
        for msg_data in agent_raw_response.get("turn_messages_to_log", []):
            db_message = AIConversationMessage(
                conversation_id=db_conversation.id,
                role=msg_data["role"],
                content=msg_data["content"],
                tool_calls_json=msg_data.get("tool_calls_json"),
                tool_output_json=msg_data.get("tool_output_json"),
                llm_type_used=msg_data.get("llm_type_used"),
                llm_model_used=msg_data.get("llm_model_used")
            )
            db.add(db_message)
            messages_for_db_commit.append(db_message)

        db.flush()

        final_turn_messages_for_response: List = []
        for db_msg in messages_for_db_commit:
            db.refresh(db_msg)
            final_turn_messages_for_response.append(
                schemas.AIConversationMessageResponse.model_validate(db_msg, from_attributes=True)
            )

        # --- IMPORTANT: AI Title Generation Logic for NEW conversations (在第一轮问答后生成标题) ---
        # 只有当对话是刚刚新建的 (is_new_and_first_message_exchange 为 True) 并且标题仍然是 None 时才尝试生成
        if is_new_and_first_message_exchange and db_conversation.title is None:
            first_exchange_messages_from_db = db.query(AIConversationMessage).filter(
                AIConversationMessage.conversation_id == db_conversation.id
            ).order_by(AIConversationMessage.sent_at).limit(2).all()

            if len(first_exchange_messages_from_db) >= 2:
                print(f"DEBUG_AI_TITLE_AUTO: 新对话 {db_conversation.id} 完成首次问答，尝试自动生成标题。")
                messages_for_title_generation = [msg.to_dict() for msg in first_exchange_messages_from_db]

                try:
                    ai_generated_title = await ai_core.generate_conversation_title_from_llm(
                        messages=messages_for_title_generation,
                        user_llm_api_type=user_llm_api_type,
                        user_llm_api_key=user_llm_api_key,
                        user_llm_api_base_url=user_llm_api_base_url,
                        user_llm_model_id=user_llm_model_id_configured
                    )
                    if ai_generated_title and ai_generated_title != "新对话" and ai_generated_title != "无标题对话":
                        db_conversation.title = ai_generated_title
                        db.add(db_conversation)
                        print(f"DEBUG: AI对话 {db_conversation.id} 标题AI生成为 '{db_conversation.title}'。")
                    else:
                        db_conversation.title = "新对话"
                        db.add(db_conversation)
                        print(
                            f"DEBUG: LLM生成的标题不具意义 ('{ai_generated_title}')，对话 {db_conversation.id} 保持默认标题。")
                except Exception as e:
                    print(f"ERROR: AI自动生成标题失败: {e}. 对话 {db_conversation.id} 标题保持默认。")
                    db_conversation.title = "新对话"
                    db.add(db_conversation)
            else:
                db_conversation.title = "新对话"
                db.add(db_conversation)
                print(f"DEBUG_AI_TITLE_AUTO: 对话 {db_conversation.id} 消息内容不足，标题保持默认。")

        # 4. 更新对话的 last_updated 时间
        db_conversation.last_updated = func.now()
        db.add(db_conversation)

        db.commit()

        # 构造最终 AIQAResponse 对象
        response_to_client = schemas.AIQAResponse(
            answer=agent_raw_response["answer"],
            answer_mode=agent_raw_response["answer_mode"],
            llm_type_used=agent_raw_response.get("llm_type_used"),
            llm_model_used=agent_raw_response.get("llm_model_used"),
            conversation_id=db_conversation.id,
            turn_messages=final_turn_messages_for_response,
            source_articles=agent_raw_response.get("source_articles"),
            search_results=agent_raw_response.get("search_results")
        )

        print(f"DEBUG: 用户 {current_user_id} 在对话 {db_conversation.id} 中成功完成AI问答。")
        return response_to_client

    except Exception as e:
        db.rollback()
        print(f"ERROR: AI问答请求失败: {e}. 详细错误: {traceback.format_exc()}")

        if not conversation_id and db_conversation.id:  # 只有当是新创建的对话且已经有ID时才考虑

            pass

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"AI问答失败: {e}")


@app.post("/search/semantic", response_model=List[schemas.SemanticSearchResult], summary="智能语义搜索")
async def semantic_search(
        search_request: schemas.SemanticSearchRequest,
        current_user_id: int = Depends(get_current_user_id),  # 依赖注入提供用户ID
        db: Session = Depends(get_db)
):
    """
    通过语义搜索，在用户可访问的项目、课程、知识库文章和笔记中查找相关内容。
    """
    print(f"DEBUG: 用户 {current_user_id} 语义搜索: {search_request.query}，范围: {search_request.item_types}")

    # 记录搜索开始时间
    search_start_time = time.time()

    # 从数据库中加载完整的用户对象
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        # 理论上 get_current_user_id 已经验证了用户存在，但这里是安全校验
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="当前用户未找到。")

    searchable_items = []

    target_types = search_request.item_types if search_request.item_types else ["project", "course",
                                                                                "knowledge_article", "note"]
    # ... (从这里开始到 semantic_search 结束，所有内容都是更新过的，请完整替换) ...

    if "project" in target_types:
        # 获取所有项目。如果项目有权限控制，这里需要细化筛选逻辑。
        # 暂时简化为所有用户可见所有项目的文本信息。（可根据实际需求调整为只获取自己创建的或公开的项目）
        projects = db.query(Project).all()
        for p in projects:
            if p.embedding is not None:
                searchable_items.append({"obj": p, "type": "project"})

    if "course" in target_types:
        # 获取所有课程。课程通常也是公开的。
        courses = db.query(Course).all()
        for c in courses:
            if c.embedding is not None:
                searchable_items.append({"obj": c, "type": "course"})

    if "knowledge_article" in target_types:
        # 获取用户拥有或公开的知识库中的文章
        kbs = db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user_id) | (KnowledgeBase.access_type == "public")
        ).all()
        for kb in kbs:
            articles = db.query(KnowledgeArticle).filter(KnowledgeArticle.kb_id == kb.id).all()
            for article in articles:
                if article.embedding is not None:
                    searchable_items.append({"obj": article, "type": "knowledge_article"})

    if "note" in target_types:
        # 只获取当前用户自己的笔记
        notes = db.query(Note).filter(Note.owner_id == current_user_id).all()
        for note in notes:
            if note.embedding is not None:
                searchable_items.append({"obj": note, "type": "note"})

    if not searchable_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可搜索的内容或指定类型无数据。")

    # 2. 获取查询嵌入 (使用当前用户的LLM配置)
    user_llm_type = user.llm_api_type
    user_llm_base_url = user.llm_api_base_url
    user_llm_model_id = user.llm_model_id
    user_llm_api_key = None
    if user.llm_api_key_encrypted:
        try:
            user_llm_api_key = ai_core.decrypt_key(user.llm_api_key_encrypted)
        except Exception as e:
            print(f"WARNING_SEMANTIC_SEARCH: 解密用户 {current_user_id} LLM API Key失败: {e}. 语义搜索将无法使用嵌入。")
            user_llm_api_key = None  # 解密失败，不要使用

    query_embedding_list = await ai_core.get_embeddings_from_api(
        [search_request.query],
        api_key=user_llm_api_key,
        llm_type=user_llm_type,
        llm_base_url=user_llm_base_url,
        llm_model_id=user_llm_model_id
    )
    # 检查是否成功获得了非零嵌入向量。如果返回零向量，说明嵌入服务不可用或未配置。
    if not query_embedding_list or query_embedding_list[0] == ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="无法生成查询嵌入，请确保您的LLM配置正确，LLM类型为硅基流动且API密钥有效。")
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

    # 4. 精排 (Reranker) - 同样使用用户的LLM配置
    rerank_candidate_texts = [c['obj'].combined_text for c in initial_candidates]
    print(f"DEBUG_AI: 正在对 {len(rerank_candidate_texts)} 个候选搜索结果进行重排...")

    rerank_scores = await ai_core.get_rerank_scores_from_api(
        search_request.query,
        rerank_candidate_texts,
        api_key=user_llm_api_key,  # 传入用户的解密Key
        llm_type=user_llm_type,  # 传入用户的LLM Type
        llm_base_url=user_llm_base_url,  # 尽管 reranker API 不直接用 base_url，但保持参数一致性
        fallback_to_similarity=True  # 启用回退机制
    )
    # 检查返回的rerank_scores是否是零分数（表示API调用失败或未配置）
    if all(score == 0.0 for score in rerank_scores):
        print(f"WARNING_AI: 重排服务未能返回有效分数，使用嵌入相似度作为最终分数。")
        # 如果重排失败，回退到使用粗召回的相似度作为最终相关性得分
        for i, score in enumerate(rerank_scores):  # 遍历所有候选者
            initial_candidates[i]['relevance_score'] = initial_candidates[i]['similarity_stage1']
    else:
        print(f"DEBUG_AI: 重排服务返回有效分数，使用重排结果。")
        for i, score in enumerate(rerank_scores):
            initial_candidates[i]['relevance_score'] = float(score)

    initial_candidates.sort(key=lambda x: x['relevance_score'], reverse=True)

    # 5. 格式化最终结果
    final_results = []
    for item in initial_candidates[:search_request.limit]:
        obj = item['obj']
        content_snippet = ""
        # 尝试从不同的属性中提取内容摘要
        if hasattr(obj, 'content') and obj.content:
            content_snippet = obj.content[:150] + "..." if len(obj.content) > 150 else obj.content
        elif hasattr(obj, 'description') and obj.description:
            content_snippet = obj.description[:150] + "..." if len(obj.description) > 150 else obj.description
        elif hasattr(obj, 'bio') and obj.bio and item['type'] == 'student':  # 针对学生（如果语义搜索也搜索学生）
            content_snippet = obj.bio[:150] + "..." if len(obj.bio) > 150 else obj.bio

        final_results.append(schemas.SemanticSearchResult(
            id=obj.id,
            title=obj.title if hasattr(obj, 'title') else obj.name if hasattr(obj, 'name') else str(obj.id),
            # Fallback to name or ID
            type=item['type'],
            content_snippet=content_snippet,
            relevance_score=item['relevance_score']
        ))

    print(f"DEBUG_AI: 语义搜索完成，返回 {len(final_results)} 个结果。")

    # 记录搜索性能
    search_end_time = time.time()
    search_duration = search_end_time - search_start_time
    print(
        f"PERFORMANCE_AI: 语义搜索耗时 {search_duration:.2f}秒，处理了 {len(searchable_items)} 个候选项，返回 {len(final_results)} 个结果")

    return final_results


@app.get("/admin/rag/status", summary="RAG功能状态检查（管理员）")
async def get_rag_status(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    检查RAG功能的整体状态和性能指标（仅管理员可访问）
    """
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问此功能")

    try:
        from rag_utils import rag_monitor
        stats = rag_monitor.get_stats()

        # 统计系统整体数据
        total_articles = db.query(KnowledgeArticle).count()
        articles_with_embedding = db.query(KnowledgeArticle).filter(KnowledgeArticle.embedding.isnot(None)).count()
        total_documents = db.query(KnowledgeDocument).count()
        completed_documents = db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "completed").count()
        total_chunks = db.query(KnowledgeDocumentChunk).count()
        chunks_with_embedding = db.query(KnowledgeDocumentChunk).filter(
            KnowledgeDocumentChunk.embedding.isnot(None)).count()
        total_notes = db.query(Note).count()
        notes_with_embedding = db.query(Note).filter(Note.embedding.isnot(None)).count()

        return {
            "status": "ok",
            "performance_metrics": stats,
            "data_statistics": {
                "articles": {
                    "total": total_articles,
                    "with_embedding": articles_with_embedding,
                    "embedding_rate": articles_with_embedding / total_articles if total_articles > 0 else 0
                },
                "documents": {
                    "total": total_documents,
                    "completed": completed_documents,
                    "completion_rate": completed_documents / total_documents if total_documents > 0 else 0
                },
                "chunks": {
                    "total": total_chunks,
                    "with_embedding": chunks_with_embedding,
                    "embedding_rate": chunks_with_embedding / total_chunks if total_chunks > 0 else 0
                },
                "notes": {
                    "total": total_notes,
                    "with_embedding": notes_with_embedding,
                    "embedding_rate": notes_with_embedding / total_notes if total_notes > 0 else 0
                }
            }
        }
    except ImportError:
        return {
            "status": "monitoring_unavailable",
            "message": "RAG监控模块未启用"
        }


@app.get("/users/me/rag/diagnosis", summary="用户RAG功能诊断")
async def diagnose_user_rag(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    诊断当前用户的RAG功能配置和数据状态
    """
    try:
        from rag_utils import RAGDebugger
        diagnosis = RAGDebugger.validate_rag_setup(db, current_user_id)
        return diagnosis
    except ImportError:
        # 如果rag_utils不可用，提供基本诊断
        user = db.query(Student).filter(Student.id == current_user_id).first()
        issues = []
        recommendations = []

        if not user.llm_api_type or user.llm_api_type != "siliconflow":
            issues.append("未配置SiliconFlow LLM API")
            recommendations.append("在个人设置中配置SiliconFlow API以启用完整RAG功能")

        if not user.llm_api_key_encrypted:
            issues.append("未配置LLM API密钥")
            recommendations.append("添加有效的LLM API密钥")

        # 检查用户内容
        kb_count = db.query(KnowledgeBase).filter(KnowledgeBase.owner_id == current_user_id).count()
        article_count = db.query(KnowledgeArticle).filter(KnowledgeArticle.author_id == current_user_id).count()
        doc_count = db.query(KnowledgeDocument).filter(KnowledgeDocument.owner_id == current_user_id).count()
        note_count = db.query(Note).filter(Note.owner_id == current_user_id).count()

        if kb_count == 0 and article_count == 0 and doc_count == 0 and note_count == 0:
            issues.append("没有任何可搜索的内容")
            recommendations.append("创建知识库、上传文档或添加笔记")

        return {
            "issues": issues,
            "recommendations": recommendations,
            "status": "ok" if not issues else "has_issues",
            "content_summary": {
                "knowledge_bases": kb_count,
                "articles": article_count,
                "documents": doc_count,
                "notes": note_count
            }
        }


@app.get("/users/me/ai-conversations", response_model=List[schemas.AIConversationResponse],
         summary="获取当前用户的所有AI对话列表")
async def get_my_ai_conversations(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = 10,
        offset: int = 0
):
    """
    获取当前用户的所有AI对话列表，按最新更新时间排序。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的AI对话列表。")
    conversations = db.query(AIConversation).filter(AIConversation.user_id == current_user_id) \
        .order_by(AIConversation.last_updated.desc()) \
        .offset(offset).limit(limit).all()

    response_list = []
    for conv in conversations:
        # 动态计算总消息数，填充 total_messages_count
        total_messages_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == conv.id).count()
        conv_response = schemas.AIConversationResponse.model_validate(conv, from_attributes=True)
        conv_response.total_messages_count = total_messages_count
        response_list.append(conv_response)

    print(f"DEBUG: 用户 {current_user_id} 获取到 {len(response_list)} 个AI对话。")
    return response_list


@app.get("/users/me/ai-conversations/{conversation_id}", response_model=schemas.AIConversationResponse,
         summary="获取指定AI对话详情")
async def get_ai_conversation_detail(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的AI对话详情。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的AI对话 {conversation_id} 详情。")
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    # 动态计算总消息数
    total_messages_count = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == db_conversation.id).count()
    conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
    conv_response.total_messages_count = total_messages_count

    return conv_response


@app.get("/users/me/ai-conversations/{conversation_id}/messages",
         response_model=List[schemas.AIConversationMessageResponse], summary="获取指定AI对话的所有消息历史")
async def get_ai_conversation_messages(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = 50,
        offset: int = 0
):
    """
    获取指定AI对话的所有消息历史记录。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的AI对话 {conversation_id} 消息历史。")
    # 验证对话存在且属于当前用户
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    messages = db.query(AIConversationMessage).filter(AIConversationMessage.conversation_id == conversation_id) \
        .order_by(AIConversationMessage.sent_at).offset(offset).limit(limit).all()

    print(f"DEBUG: 对话 {conversation_id} 获取到 {len(messages)} 条消息。")
    # Pydantic的 from_attributes=True 会自动处理ORM对象到Schema的转换
    return messages


@app.get("/users/me/ai-conversations/{conversation_id}/retitle", response_model=schemas.AIConversationResponse,
         summary="触发AI重新生成指定AI对话的标题并返回")
async def get_ai_conversation_retitle(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    触发AI大模型根据对话内容重新生成并更新标题，然后返回该对话的详细信息（包含新标题）。
    此接口不接受用户手动提交的标题，其唯一作用是强制AI重新评估对话并生成新标题。
    """
    print(f"DEBUG: 用户 {current_user_id} 触发AI为对话 {conversation_id} 重新生成标题。")
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    # ----- 核心逻辑：强制走AI生成逻辑 -----
    print(f"DEBUG: AI将根据对话内容强制生成最新标题。")

    # 获取历史消息作为生成标题的上下文 (取所有消息，不再限制数量，让LLM更全面总结)
    raw_messages = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == db_conversation.id
    ).order_by(AIConversationMessage.sent_at).all()  # 获取所有消息

    if not raw_messages:
        # 如果对话中没有任何消息，无法生成有意义的标题
        # 将标题设置为一个明确的空状态或默认
        db_conversation.title = "空对话"
        db.add(db_conversation)  # 标记为更新
        db.commit()  # 提交更改
        db.refresh(db_conversation)  # 刷新以获取最新状态
        print(f"WARNING: AI对话 {conversation_id} 中无消息，标题设置为 '空对话'。")

        # 动态计算总消息数 for response (此处为0)
        conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
        conv_response.total_messages_count = 0
        return conv_response

    # 将消息反转，以便 ai_core 函数处理时是正序（从旧到新）
    past_messages_for_llm = [msg.to_dict() for msg in reversed(raw_messages)]  # to_dict() 确保兼容性

    # 获取用户的LLM配置
    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    user_llm_api_type: Optional[str] = None
    user_llm_api_base_url: Optional[str] = None
    user_llm_model_id_configured: Optional[str] = None
    user_llm_api_key: Optional[str] = None

    if not current_user_obj.llm_api_type or not current_user_obj.llm_api_key_encrypted:
        # 如果用户没有配置LLM，则无法生成标题，返回默认标题
        db_conversation.title = "新对话"
        db.add(db_conversation)
        db.commit()
        db.refresh(db_conversation)
        print(f"ERROR: 用户 {current_user_id} 未配置LLM API，无法生成标题，使用默认标题。")

        total_messages_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == db_conversation.id).count()
        conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
        conv_response.total_messages_count = total_messages_count
        return conv_response

    user_llm_api_type = current_user_obj.llm_api_type
    user_llm_api_base_url = current_user_obj.llm_api_base_url
    user_llm_model_id_configured = current_user_obj.llm_model_id

    try:
        user_llm_api_key = ai_core.decrypt_key(current_user_obj.llm_api_key_encrypted)
        print(f"DEBUG_LLM_TITLE_REGEN: 密钥解密成功，使用用户配置的硅基流动 API 密钥为对话生成标题。")
    except Exception as e:
        # 如果密钥解密失败，也视为无法生成标题，返回默认标题
        db_conversation.title = "新对话"
        db.add(db_conversation)
        db.commit()
        db.refresh(db_conversation)
        print(f"ERROR_LLM_TITLE_REGEN: 解密用户LLM API密钥失败: {e}. 无法生成标题，使用默认标题。")
        total_messages_count = db.query(AIConversationMessage).filter(
            AIConversationMessage.conversation_id == db_conversation.id).count()
        conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
        conv_response.total_messages_count = total_messages_count
        return conv_response

    if past_messages_for_llm:  # 确保有消息可以用来生成标题
        try:
            ai_generated_title = await ai_core.generate_conversation_title_from_llm(
                messages=past_messages_for_llm,
                user_llm_api_type=user_llm_api_type,
                user_llm_api_key=user_llm_api_key,
                user_llm_api_base_url=user_llm_api_base_url,
                user_llm_model_id=user_llm_model_id_configured
            )
            # 只有当生成的标题有效且不是默认的“新对话”或“无标题对话”时才更新
            if ai_generated_title and ai_generated_title != "新对话" and ai_generated_title != "无标题对话":
                db_conversation.title = ai_generated_title
                print(f"DEBUG: AI对话 {conversation_id} 标题由AI强制生成为 '{db_conversation.title}'。")
            else:
                db_conversation.title = "新对话"  # LLM生成不具意义或空，使用默认
                print(f"DEBUG: LLM生成的标题不具意义 ('{ai_generated_title}')，对话 {conversation_id} 保持默认标题。")
        except Exception as e:
            print(f"ERROR: AI自动生成标题失败: {e}. 将使用默认标题。")
            db_conversation.title = "新对话"  # 自动生成失败时的默认标题
    else:
        db_conversation.title = "新对话"  # 没有消息时（虽然上面已处理），以防万一
        print(f"DEBUG: AI对话 {conversation_id} 没有历史消息用于生成标题，使用默认标题 '{db_conversation.title}'。")
    # ----- 核心修改结束 -----

    db.add(db_conversation)  # 标记为更新
    db.commit()  # 提交更新

    db.refresh(db_conversation)  # 刷新以获取最新状态

    # 动态计算总消息数 for response
    total_messages_count = db.query(AIConversationMessage).filter(
        AIConversationMessage.conversation_id == db_conversation.id).count()
    conv_response = schemas.AIConversationResponse.model_validate(db_conversation, from_attributes=True)
    conv_response.total_messages_count = total_messages_count

    return conv_response


@app.delete("/users/me/ai-conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定AI对话")
async def delete_ai_conversation(
        conversation_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定AI对话及其所有消息历史。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试删除AI对话 {conversation_id}。")
    db_conversation = db.query(AIConversation).filter(
        AIConversation.id == conversation_id,
        AIConversation.user_id == current_user_id
    ).first()
    if not db_conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话未找到或无权访问。")

    db.delete(db_conversation)  # 会级联删除所有消息 (cascade="all, delete-orphan")
    db.commit()
    print(f"DEBUG: AI对话 {conversation_id} 及其所有消息已删除。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 随手记录管理接口 ---
@app.post("/daily-records/", response_model=schemas.DailyRecordResponse, summary="创建新随手记录")
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
            owner_llm_api_key = ai_core.decrypt_key(record_owner.llm_api_key_encrypted)
            owner_llm_type = record_owner.llm_api_type
            owner_llm_base_url = record_owner.llm_api_base_url
            owner_llm_model_id = record_owner.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用随手记录创建者配置的硅基流动 API 密钥为随手记录生成嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密随手记录创建者硅基流动 API 密钥失败: {e}。随手记录嵌入将使用零向量。")
            owner_llm_api_key = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 随手记录创建者未配置硅基流动 API 类型或密钥，随手记录嵌入将使用零向量或默认行为。")

    embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if combined_text:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text],
                api_key=owner_llm_api_key,
                llm_type=owner_llm_type,
                llm_base_url=owner_llm_base_url,
                llm_model_id=owner_llm_model_id
            )
            if new_embedding:
                embedding = new_embedding[0]
            # else: ai_core.get_embeddings_from_api 已经在不生成时返回零向量的List
            print(f"DEBUG: 随手记录嵌入向量已生成。")
        except Exception as e:
            print(f"ERROR: 生成随手记录嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 发生错误时，确保设置为零向量
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


@app.get("/daily-records/", response_model=List[schemas.DailyRecordResponse], summary="获取当前用户所有随手记录")
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
            owner_llm_api_key = ai_core.decrypt_key(record_owner.llm_api_key_encrypted)
            owner_llm_type = record_owner.llm_api_type
            owner_llm_base_url = record_owner.llm_api_base_url
            owner_llm_model_id = record_owner.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用随手记录创建者配置的硅基流动 API 密钥更新随手记录嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密随手记录创建者硅基流动 API 密钥失败: {e}。随手记录嵌入将使用零向量。")
            owner_llm_api_key = None  # 解密失败，不要使用
    else:
        print(f"DEBUG_EMBEDDING_KEY: 随手记录创建者未配置硅基流动 API 类型或密钥，随手记录嵌入将使用零向量或默认行为。")

    embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if db_record.combined_text:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
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
            embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING_EMBEDDING: 随手记录 combined_text 为空，嵌入向量设为零。")
        # 如果 combined_text 为空，embedding 保持为默认的零向量

    db_record.embedding = embedding_recalculated  # 赋值给DB对象

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


# --- 用户课程管理接口 ---
@app.post("/courses/{course_id}/enroll", response_model=schemas.UserCourseResponse, summary="用户报名课程")
async def enroll_course(
        course_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    允许用户报名（注册）一门课程。
    如果用户已报名，则返回已有的报名信息，不会重复创建。
    """
    print(f"DEBUG_COURSE_ENROLL: 用户 {current_user_id} 尝试报名课程 {course_id}。")

    # 1. 验证课程是否存在
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 2. 检查用户是否已报名该课程
    existing_enrollment = db.query(UserCourse).filter(
        UserCourse.student_id == current_user_id,
        UserCourse.course_id == course_id
    ).first()

    if existing_enrollment:
        print(f"DEBUG_COURSE_ENROLL: 用户 {current_user_id} 已报名课程 {course_id}，返回现有报名信息。")
        # 确保返回的UserCourseResponse包含课程标题
        if existing_enrollment.course is None:  # 如果course关系没有被加载
            existing_enrollment.course = db_course  # 暂时赋值以填充响应模型
        return existing_enrollment

    # 3. 创建新的报名记录
    new_enrollment = UserCourse(
        student_id=current_user_id,
        course_id=course_id,
        progress=0.0,
        status="registered",  # 初始状态为“已注册”
        last_accessed=func.now()
    )

    db.add(new_enrollment)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # 捕获可能的并发冲突，如果同时有多个请求尝试创建
        print(f"ERROR_DB: 报名课程时发生完整性错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="报名失败：课程已被您注册，或发生并发冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 报名课程 {course_id} 失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"报名课程失败: {e}")
    db.refresh(new_enrollment)

    # 确保返回的UserCourseResponse包含课程标题
    if new_enrollment.course is None:  # 如果course关系没有被加载
        new_enrollment.course = db_course  # 暂时赋值以填充响应模型

    print(f"DEBUG_COURSE_ENROLL: 用户 {current_user_id} 成功报名课程 {course_id}。")
    return new_enrollment


@app.put("/users/me/courses/{course_id}", response_model=schemas.UserCourseResponse,
         summary="更新当前用户课程学习进度和状态")
async def update_user_course_progress(
        course_id: int,
        update_data: Dict[str, Any],
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试更新课程 {course_id} 的进度。")

    try:
        user_course = db.query(UserCourse).filter(
            UserCourse.student_id == current_user_id,
            UserCourse.course_id == course_id
        ).first()

        if not user_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未注册该课程或课程未找到。")

        old_status = user_course.status
        new_status = update_data.get("status")

        # 更新进度和状态 (先更新到ORM对象，等待最终提交)
        if "progress" in update_data and isinstance(update_data["progress"], (int, float)):
            user_course.progress = update_data["progress"]
        if "status" in update_data and isinstance(update_data["status"], str):
            user_course.status = update_data["status"]

        user_course.last_accessed = func.now()  # 更新上次访问时间

        db.add(user_course)  # 将修改后的user_course对象添加到会话中

        # 在检查成就前，强制刷新会话，使 UserCourse 的最新状态对查询可见！
        if new_status == "completed" and old_status != "completed":
            db.flush()  # 确保 user_course 的 completed 状态已刷新到数据库会话，供 _check_and_award_achievements 查询
            print(f"DEBUG_FLUSH: 用户 {current_user_id} 课程 {course_id} 状态更新已刷新到会话。")

        # 检查课程状态是否变为“已完成”，并奖励积分
        if new_status == "completed" and old_status != "completed":
            user = db.query(Student).filter(Student.id == current_user_id).first()
            if user:
                course_completion_points = 30
                await _award_points(
                    db=db,
                    user=user,
                    amount=course_completion_points,
                    reason=f"完成课程：'{user_course.course.title if user_course.course else course_id}'",
                    transaction_type="EARN",
                    related_entity_type="course",
                    related_entity_id=course_id
                )
                await _check_and_award_achievements(db, current_user_id)
                print(
                    f"DEBUG_POINTS_ACHIEVEMENT: 用户 {current_user_id} 完成课程 {course_id}，获得 {course_completion_points} 积分并检查成就 (待提交)。")

        db.commit()  # 现在，这里是唯一也是最终的提交！

        # 填充 UserCourseResponse 中的 Course 标题，如果需要的话
        if user_course.course is None:
            user_course.course = db.query(Course).filter(Course.id == user_course.course_id).first()

        print(f"DEBUG: 用户 {current_user_id} 课程 {course_id} 进度更新成功，所有事务已提交。")
        return user_course  # 返回 user_course 才能映射到 UserCourseResponse

    except Exception as e:  # 捕获所有异常并回滚
        db.rollback()
        print(
            f"ERROR_USER_COURSE_UPDATE_GLOBAL: 用户 {current_user_id} 课程 {course_id} 更新过程中发生错误，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"课程更新失败：{e}",
        )


# --- 课程材料管理接口 ---
@app.post("/courses/{course_id}/materials/", response_model=schemas.CourseMaterialResponse,
          summary="为指定课程上传新材料（文件或链接）")
async def create_course_material(
        course_id: int,
        file: Optional[UploadFile] = File(None, description="上传课程文件，如PDF、视频等"),
        material_data: schemas.CourseMaterialCreate = Depends(),
        current_admin_user: Student = Depends(is_admin_user),  # 管理员创建材料
        db: Session = Depends(get_db)
):
    print(
        f"DEBUG_COURSE_MATERIAL: 管理员 {current_admin_user.id} 尝试为课程 {course_id} 创建材料: {material_data.title} (类型: {material_data.type})")

    # 1. 验证课程是否存在
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 2. 根据材料类型处理数据
        material_params = {
            "course_id": course_id,
            "title": material_data.title,
            "type": material_data.type,
            "content": material_data.content  # 可选，无论哪种类型都可作为补充描述
        }

        if material_data.type == "file":
            if not file:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="类型为 'file' 时，必须上传文件。")

            # 读取文件所有字节
            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            # OSS上的文件路径和名称，例如 course_materials/UUID.pdf
            current_oss_object_name = f"course_materials/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                material_params["file_path"] = await oss_utils.upload_file_to_oss(  # 存储OSS URL
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=file.content_type
                )
                material_params["original_filename"] = file.filename
                material_params["file_type"] = file.content_type
                material_params["size_bytes"] = file.size
                print(
                    f"DEBUG_COURSE_MATERIAL: 文件 '{file.filename}' 上传到OSS成功，URL: {material_params['file_path']}")
            except HTTPException as e:  # oss_utils.upload_file_to_oss will re-raise HTTPException
                print(f"ERROR_COURSE_MATERIAL: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出
            except Exception as e:
                print(f"ERROR_COURSE_MATERIAL: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=f"文件上传到云存储失败: {e}")

        elif material_data.type == "link":
            if not material_data.url:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'link' 时，'url' 字段为必填。")
            material_params["url"] = material_data.url
            material_params["original_filename"] = None;
            material_params["file_type"] = None;
            material_params["size_bytes"] = None
            material_params["file_path"] = None  # 确保明确为None
        elif material_data.type == "text":
            if not material_data.content:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'text' 时，'content' 字段为必填。")
            material_params["url"] = None;
            material_params["original_filename"] = None;
            material_params["file_type"] = None;
            material_params["size_bytes"] = None
            material_params["file_path"] = None  # 确保明确为None
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的材料类型。")

        # 3. 生成 combined_text 用于嵌入，并计算嵌入向量
        combined_text_content = ". ".join(filter(None, [
            _get_text_part(material_data.title),
            _get_text_part(material_data.content),
            _get_text_part(material_data.url),
            _get_text_part(material_data.original_filename),
            _get_text_part(material_data.file_type),
            _get_text_part(material_params.get("file_path"))  # 添加file_path (OSS URL)到combined_text
        ])).strip()
        if not combined_text_content:  # 如果组合文本为空，可能需要给个默认值
            combined_text_content = ""  # 确保是空字符串而不是None

        embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量

        # 获取管理员的LLM配置用于嵌入生成
        admin_llm_api_key = None
        admin_llm_type = current_admin_user.llm_api_type
        admin_llm_base_url = current_admin_user.llm_api_base_url
        admin_llm_model_id = current_admin_user.llm_model_id

        if current_admin_user.llm_api_key_encrypted:
            try:
                admin_llm_api_key = ai_core.decrypt_key(current_admin_user.llm_api_key_encrypted)
                admin_llm_type = current_admin_user.llm_api_type
                admin_llm_base_url = current_admin_user.llm_api_base_url
                admin_llm_model_id = current_admin_user.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用管理员配置的硅基流动 API 密钥为课程材料生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密管理员硅基流动 API 密钥失败: {e}。课程材料嵌入将使用零向量。")
                admin_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 管理员未配置硅基流动 API 类型或密钥，课程材料嵌入将使用零向量或默认行为。")

        if combined_text_content:
            try:
                new_embedding = await ai_core.get_embeddings_from_api(
                    [combined_text_content],
                    api_key=admin_llm_api_key,
                    llm_type=admin_llm_type,
                    llm_base_url=admin_llm_base_url,
                    llm_model_id=admin_llm_model_id
                )
                if new_embedding:
                    embedding = new_embedding[0]
                else:
                    embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 确保为零向量
                print(f"DEBUG_COURSE_MATERIAL: 材料嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR_COURSE_MATERIAL: 生成材料嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING_EMBEDDING: 课程材料 combined_text 为空，嵌入向量设为零。")

        material_params["combined_text"] = combined_text_content
        material_params["embedding"] = embedding

        # 4. 创建数据库记录
        db_material = CourseMaterial(**material_params)
        db.add(db_material)

        db.commit()  # 提交DB写入
        db.refresh(db_material)
        print(f"DEBUG_COURSE_MATERIAL: 课程材料 '{db_material.title}' (ID: {db_material.id}) 创建成功。")
        return db_material

    except IntegrityError as e:
        db.rollback()
        # 如果数据库提交失败，并且之前有文件上传到OSS，则尝试删除OSS文件
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_COURSE_MATERIAL: DB commit failed, attempting to delete OSS file: {oss_object_name_for_rollback}")

        print(f"ERROR_DB: 创建课程材料发生完整性约束错误: {e}")
        if "_course_material_title_uc" in str(e): raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                                                      detail="同一课程下已存在同名材料。")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建课程材料失败，可能存在数据冲突。")
    except HTTPException as e:  # Catch FastAPI's HTTPException and re-raise it
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_COURSE_MATERIAL: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:
        db.rollback()
        # 如果发生其他错误，并且之前有文件上传到OSS，则尝试删除OSS文件
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(
                f"DEBUG_COURSE_MATERIAL: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_DB: 创建课程材料发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建课程材料失败: {e}")


@app.get("/courses/{course_id}/materials/", response_model=List[schemas.CourseMaterialResponse],
         summary="获取指定课程的所有材料列表")
async def get_course_materials(
        course_id: int,
        # 课程材料通常是公开的，或者在学习课程后才能访问，这里简化为只要课程存在即可查看
        # current_user_id: int = Depends(get_current_user_id)，如果需要认证，可 uncomment
        db: Session = Depends(get_db),
        type_filter: Optional[Literal["file", "link", "text"]] = None
):
    print(f"DEBUG_COURSE_MATERIAL: 获取课程 {course_id} 的材料列表。")
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    query = db.query(CourseMaterial).filter(CourseMaterial.course_id == course_id)
    if type_filter:
        query = query.filter(CourseMaterial.type == type_filter)

    materials = query.order_by(CourseMaterial.title).all()
    print(f"DEBUG_COURSE_MATERIAL: 课程 {course_id} 获取到 {len(materials)} 个材料。")
    return materials


@app.get("/courses/{course_id}/materials/{material_id}", response_model=schemas.CourseMaterialResponse,
         summary="获取指定课程材料详情")
async def get_course_material_detail(
        course_id: int,
        material_id: int,
        # current_user_id: int = Depends(get_current_user_id), 如果需要认证，可 uncomment
        db: Session = Depends(get_db)
):
    print(f"DEBUG_COURSE_MATERIAL: 获取课程 {course_id} 材料 ID: {material_id} 的详情。")
    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id
    ).first()
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程。")
    return db_material


@app.put("/courses/{course_id}/materials/{material_id}", response_model=schemas.CourseMaterialResponse,
         summary="更新指定课程材料")
async def update_course_material(
        course_id: int,
        material_id: int,
        file: Optional[UploadFile] = File(None, description="可选：上传新文件替换旧文件"),
        material_data: schemas.CourseMaterialUpdate = Depends(),
        current_admin_user: Student = Depends(is_admin_user),  # 管理员更新
        db: Session = Depends(get_db)
):
    print(f"DEBUG_COURSE_MATERIAL: 管理员 {current_admin_user.id} 尝试更新课程 {course_id} 材料 ID: {material_id}。")

    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id
    ).first()
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程。")

    # 验证课程是否存在 (保持不变)
    db_course = db.query(Course).filter(Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

    update_dict = material_data.dict(exclude_unset=True)  # 获取所有明确传入的字段及其值

    # 获取旧的OSS对象名称，用于替换时删除
    old_oss_object_name = None
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_material.file_path and db_material.file_path.startswith(oss_base_url_parsed):
        old_oss_object_name = db_material.file_path.replace(oss_base_url_parsed, '', 1)

    new_oss_object_name = None  # 用于新的文件上传成功后，在 commit 失败时回滚删除

    # 类型转换的复杂逻辑
    # 检查是否尝试改变材料类型
    type_changed = "type" in update_dict and update_dict["type"] != db_material.type
    new_type_from_data = update_dict.get("type", db_material.type)  # 获取新的类型，如果没变就用旧的

    if type_changed:
        # 如果从 "file" 类型改为其他类型，需要删除旧的OSS文件
        if db_material.type == "file" and old_oss_object_name:
            try:
                # 异步删除旧的OSS文件，不阻塞主线程
                asyncio.create_task(oss_utils.delete_file_from_oss(old_oss_object_name))
                print(f"DEBUG_COURSE_MATERIAL: Deleted old OSS file {old_oss_object_name} due to type change.")
            except Exception as e:
                print(
                    f"ERROR_COURSE_MATERIAL: Failed to schedule deletion of old OSS file {old_oss_object_name} during type change: {e}")

        # 清除旧文件相关的数据库字段（file_path, original_filename, file_type, size_bytes）
        # 也清除 url 或 content，根据新类型而定
        if new_type_from_data in ["link", "text"]:
            db_material.file_path = None
            db_material.original_filename = None
            db_material.file_type = None
            db_material.size_bytes = None
            if new_type_from_data == "link":
                db_material.content = None  # 如果改为link，清除content
                if not update_dict.get("url") and not db_material.url:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="类型为 'link' 时，'url' 字段为必填。")
            elif new_type_from_data == "text":
                db_material.url = None  # 如果改为text，清除url
                if not update_dict.get("content") and not db_material.content:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                        detail="类型为 'text' 时，'content' 字段为必填。")

        db_material.type = new_type_from_data  # 更新类型

    # 如果上传了新文件 (无论类型是否改变，只要有文件上传就处理)
    if file:
        # 如果当前材料类型不是 "file" （且不是从 "file" 类型更新），则不允许文件上传
        if db_material.type != "file" and new_type_from_data != "file":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="只有类型为 'file' 的材料才能上传文件。如需更改材料类型，请在material_data中同时指定 type='file'。")

        # 如果旧文件存在且是文件类型，先从OSS删除旧文件
        if db_material.type == "file" and old_oss_object_name:
            try:
                # 异步删除旧的OSS文件
                asyncio.create_task(oss_utils.delete_file_from_oss(old_oss_object_name))
                print(f"DEBUG_COURSE_MATERIAL: Deleted old OSS file: {old_oss_object_name} for replacement.")
            except Exception as e:
                print(
                    f"ERROR_COURSE_MATERIAL: Failed to schedule deletion of old OSS file {old_oss_object_name} during replacement: {e}")

        # 读取新文件内容并上传到OSS
        file_bytes = await file.read()
        new_file_extension = os.path.splitext(file.filename)[1]
        new_oss_object_name = f"course_materials/{uuid.uuid4().hex}{new_file_extension}"  # OSS上的路径和文件名

        try:
            db_material.file_path = await oss_utils.upload_file_to_oss(  # 存储OSS URL
                file_bytes=file_bytes,
                object_name=new_oss_object_name,
                content_type=file.content_type
            )
            db_material.original_filename = file.filename
            db_material.file_type = file.content_type
            db_material.size_bytes = file.size

            if db_material.type != "file":  # 如果之前不是file类型，且上传了文件，则强制改为file类型
                db_material.type = "file"
                print(f"DEBUG_COURSE_MATERIAL: Material type automatically changed to 'file' due to file upload.")

            # 清除其他类型特有的字段
            db_material.url = None
            db_material.content = None

            print(f"DEBUG_COURSE_MATERIAL: New file '{file.filename}' saved to OSS: {db_material.file_path}")
        except HTTPException as e:  # oss_utils.upload_file_to_oss will re-raise HTTPException
            print(f"ERROR_COURSE_MATERIAL: 上传新文件到OSS失败: {e.detail}")
            raise e  # 直接重新抛出
        except Exception as e:
            print(f"ERROR_COURSE_MATERIAL: 上传新文件到OSS时发生未知错误: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

    # 应用 material_data 中的其他更新 (覆盖已处理的file/type字段)
    # 确保 material_data.dict(exclude_unset=True) 不会将 file, url, content, type等重新覆盖为None如果是没传的话
    # 所以要跳过已手工处理的字段
    fields_to_skip_manual_update = ["type", "url", "content", "original_filename", "file_type", "size_bytes", "file"]
    for key, value in update_dict.items():
        if key in fields_to_skip_manual_update:
            continue
        if hasattr(db_material, key):
            if key == "title":
                if value is None or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="材料标题不能为空。")
                setattr(db_material, key, value)
            else:
                setattr(db_material, key, value)

    # 重新生成 combined_text 和 embedding
    combined_text_content = ". ".join(filter(None, [
        _get_text_part(db_material.title),  # 使用 db_material 的最新属性
        _get_text_part(db_material.content),
        _get_text_part(db_material.url),
        _get_text_part(db_material.original_filename),
        _get_text_part(db_material.file_type),
        _get_text_part(db_material.file_path)  # 添加file_path (OSS URL)到combined_text
    ])).strip()

    # 获取管理员LLM配置和API密钥用于嵌入生成 (管理员对象已从依赖注入提供)
    admin_llm_api_key = None
    admin_llm_type = current_admin_user.llm_api_type
    admin_llm_base_url = current_admin_user.llm_api_base_url
    admin_llm_model_id = current_admin_user.llm_model_id

    if current_admin_user.llm_api_key_encrypted:
        try:
            admin_llm_api_key = ai_core.decrypt_key(current_admin_user.llm_api_key_encrypted)
        except Exception as e:
            print(
                f"WARNING_COURSE_MATERIAL_EMBEDDING: 解密管理员 {current_admin_user.id} LLM API密钥失败: {e}. 课程材料嵌入将使用零向量或默认行为。")

    embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if combined_text_content:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text_content],
                api_key=admin_llm_api_key,
                llm_type=admin_llm_type,
                llm_base_url=admin_llm_base_url,
                llm_model_id=admin_llm_model_id
            )
            if new_embedding:
                embedding_recalculated = new_embedding[0]
            print(f"DEBUG_COURSE_MATERIAL: 材料嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR_COURSE_MATERIAL: 更新材料嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:  # 如果 combined_text_content 为空
        print(f"WARNING: 课程材料内容为空，无法更新有效嵌入向量。")
        embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db_material.combined_text = combined_text_content
    db_material.embedding = embedding_recalculated  # 赋值给DB对象

    db.add(db_material)
    try:
        db.commit()
        db.refresh(db_material)
    except IntegrityError as e:
        db.rollback()
        # 如果数据库提交失败，尝试删除新上传的OSS文件
        if new_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_oss_object_name))
            print(
                f"DEBUG_COURSE_MATERIAL: Update DB commit failed, attempting to delete new OSS file: {new_oss_object_name}")
        print(f"ERROR_DB: Update course material integrity constraint error: {e}")
        if "_course_material_title_uc" in str(e):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="同一课程下已存在同名材料。")
        elif 'null value in column "type"' in str(e):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="材料类型不能为空。")
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新课程材料失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        # 如果发生其他错误，尝试删除新上传的OSS文件
        if new_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_oss_object_name))
            print(
                f"DEBUG_COURSE_MATERIAL: Unknown error during update, attempting to delete new OSS file: {new_oss_object_name}")
        print(f"ERROR_DB: Unknown error during course material update: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新课程材料失败: {e}")

    print(f"DEBUG_COURSE_MATERIAL: Course material ID: {material_id} updated successfully.")
    return db_material


@app.delete("/courses/{course_id}/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定课程材料")
async def delete_course_material(
        course_id: int,
        material_id: int,
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能删除课程材料
        db: Session = Depends(get_db)
):
    print(f"DEBUG_COURSE_MATERIAL: 管理员 {current_admin_user.id} 尝试删除课程 {course_id} 材料 ID: {material_id}。")

    db_material = db.query(CourseMaterial).filter(
        CourseMaterial.id == material_id,
        CourseMaterial.course_id == course_id  # 确保材料属于该课程
    ).first()
    if not db_material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程材料未找到或不属于该课程。")

    # 如果材料是 'file' 类型，从OSS删除文件
    if db_material.type == "file" and db_material.file_path:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_material.file_path.replace(oss_base_url_parsed, '', 1) if db_material.file_path.startswith(
            oss_base_url_parsed) else db_material.file_path

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_COURSE_MATERIAL: 删除了OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_COURSE_MATERIAL: 删除OSS文件 {object_name} 失败: {e}")
                # 这里不抛出异常，即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_COURSE_MATERIAL: 材料 {material_id} 的 file_path 无效或非OSS URL: {db_material.file_path}，跳过OSS文件删除。")

    db.delete(db_material)
    db.commit()
    print(f"DEBUG_COURSE_MATERIAL: 课程材料 ID: {material_id} 及其关联数据已删除。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    else:  # 如果 parent_id 没有被显式提供，获取顶级文件夹（parent_id 为 None）
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


# --- 具体收藏内容管理接口 ---
@app.post("/collections/", response_model=schemas.CollectedContentResponse, summary="创建新收藏内容")
async def create_collected_content(
        # Changed to Depends() to allow mixing body (JSON) and file (form-data)
        content_data: schemas.CollectedContentBase = Depends(),
        file: Optional[UploadFile] = File(None, description="可选：上传文件或图片作为收藏内容"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    为当前用户创建一条新收藏内容。支持直接创建文本/链接/媒体内容，
    或通过 shared_item_type 和 shared_item_id 收藏平台内部资源。
    如果上传文件，将存储到OSS并保存URL。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试创建收藏。标题: {content_data.title}, 共享类型: {content_data.shared_item_type}, 有文件: {bool(file)}")

    uploaded_file_object_name = None  # For rollback
    uploaded_file_size = None

    # Handle direct file upload to OSS first
    if file:
        if content_data.type not in ["file", "image", "video"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="当上传文件时，收藏类型 (type) 必须为 'file', 'image' 或 'video'。")

        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        content_type = file.content_type
        uploaded_file_size = file.size

        # Determine OSS path prefix based on content type
        oss_path_prefix = "collected_files"
        if content_type.startswith('image/'):
            oss_path_prefix = "collected_images"
        elif content_type.startswith('video/'):
            oss_path_prefix = "collected_videos"

        uploaded_file_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

        try:
            # Upload to OSS
            await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=uploaded_file_object_name,
                content_type=content_type
            )
            print(f"DEBUG_COLLECTED_CONTENT: File '{file.filename}' uploaded to OSS as '{uploaded_file_object_name}'.")

        except HTTPException as e:
            print(f"ERROR_COLLECTED_CONTENT: Upload to OSS failed for {file.filename}: {e.detail}")
            raise e
        except Exception as e:
            print(f"ERROR_COLLECTED_CONTENT: Unknown error during OSS upload for {file.filename}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

        # If file uploaded, the `final_url` will be set by _create_collected_content_item_internal
        # But we need to pass along original filename for _create_collected_content_item_internal to use in title/content

    # 调用内部辅助函数来处理所有业务逻辑
    # Pass uploaded file details to the internal helper
    return await _create_collected_content_item_internal(
        db=db,
        current_user_id=current_user_id,
        content_data=content_data,
        uploaded_file_bytes=file_bytes if file else None,  # Pass bytes only if file exists
        uploaded_file_object_name=uploaded_file_object_name,
        uploaded_file_content_type=file.content_type if file else None,
        uploaded_file_original_filename=file.filename if file else None,
        uploaded_file_size=uploaded_file_size
    )


@app.post("/collections/add-from-platform", response_model=schemas.CollectedContentResponse,
          summary="快速收藏平台内部内容（课程、项目、话题等）")
async def add_platform_item_to_collection(
        request_data: schemas.CollectedContentSharedItemAddRequest,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    用户可以通过这个便捷接口，将平台内的课程、项目、论坛话题、笔记、随手记录、知识库文章或聊天消息等内容，
    快速添加到自己的收藏中。后端将自动提取并填充标题、内容等信息。
    """
    print(
        f"DEBUG: 用户 {current_user_id} 尝试快速收藏平台内容。类型: {request_data.shared_item_type}, ID: {request_data.shared_item_id}")

    # 创建类型映射，将shared_item_type映射到CollectedContentBase允许的type值
    type_mapping = {
        "knowledge_document": None,  # 留空，由后端自动推断为合适的类型（document/image/video/file等）
        "course_material": None,     # 留空，由后端自动推断为合适的类型
        "project": "project",
        "course": "course", 
        "forum_topic": "forum_topic",
        "note": "note",
        "daily_record": "daily_record",
        "knowledge_article": "knowledge_article",
        "chat_message": None  # 留空，由后端自动推断为合适的类型（image/video/link/text等）
    }
    
    # 获取映射后的类型，如果映射结果为None，则让后端自动推断
    mapped_type = type_mapping.get(request_data.shared_item_type, request_data.shared_item_type)

    # 构造一个 CollectedContentBase 对象，只填充 shared_item 相关字段和用户主动提供的可选字段
    # 其他默认字段（如 title, type, url, content, tags, author等）将留空，由 _create_collected_content_item_internal 自动填充。
    collected_content_base_data = schemas.CollectedContentBase(
        title=request_data.title,  # 允许快速收藏时提供一个标题，如果不提供则由后端推断
        type=mapped_type,  # 使用映射后的类型，如果为None则由后端推断
        url=None,  # URL由后端推断
        content=None,  # content由后端推断
        tags=None,  # 标签由后端推断
        priority=None,  # 优先级使用默认
        notes=request_data.notes,  # 备注从请求中获取
        is_starred=request_data.is_starred,  # 星标从请求中获取
        thumbnail=None,  # 缩略图由后端推断
        author=None,  # 作者由后端推断
        duration=None,  # 时长由后端推断
        file_size=None,  # 文件大小由后端推断
        status=None,  # 状态由后端推断

        shared_item_type=request_data.shared_item_type,
        shared_item_id=request_data.shared_item_id,
        folder_id=request_data.folder_id
    )

    # 调用核心辅助函数进行实际的收藏创建
    return await _create_collected_content_item_internal(db, current_user_id, collected_content_base_data)


@app.get("/collections/", response_model=List[schemas.CollectedContentResponse], summary="获取当前用户所有收藏内容")
async def get_all_collected_contents(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        folder_id: Optional[int] = Query(None, description="按文件夹ID过滤。传入0表示顶级文件夹（即folder_id为NULL）"),
        type_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        is_starred: Optional[bool] = None,
        status_filter: Optional[str] = None
):
    """
    获取当前用户的所有收藏内容。
    支持通过文件夹ID、类型、标签、星标状态和内容状态进行过滤。
    如果 folder_id 为 None，则返回所有。传入0视为顶级文件夹（未指定文件夹）。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有收藏内容。文件夹ID: {folder_id}")
    query = db.query(CollectedContent).filter(CollectedContent.owner_id == current_user_id)

    if folder_id is not None:
        if folder_id == 0:  # folder_id=0 表示根目录，即 folder_id 为 None
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

    # <<< 新增：填充文件夹名称用于响应 >>>
    # 提前加载所有相关文件夹，避免N+1查询
    folder_ids_in_results = list(set([item.folder_id for item in contents if item.folder_id is not None]))
    folder_map = {f.id: f.name for f in db.query(Folder).filter(Folder.id.in_(folder_ids_in_results)).all()}

    for item in contents:
        if item.folder_id and item.folder_id in folder_map:
            item.folder_name_for_response = folder_map[item.folder_id]
        elif item.folder_id is None:
            item.folder_name_for_response = "未分类"  # 或其他表示根目录的字符串
    # <<< 新增结束 >>>

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

    # <<< 新增：填充文件夹名称用于响应 >>>
    if item.folder_id:
        folder_obj = db.query(Folder).filter(Folder.id == item.folder_id).first()
        if folder_obj:
            item.folder_name_for_response = folder_obj.name
        else:
            item.folder_name_for_response = "未知文件夹"  # 或处理错误情况
    elif item.folder_id is None:
        item.folder_name_for_response = "未分类"  # 或其他表示根目录的字符串
    # <<< 新增结束 >>>

    return item


@app.put("/collections/{content_id}", response_model=schemas.CollectedContentResponse, summary="更新指定收藏内容")
async def update_collected_content(
        content_id: int,
        content_data: schemas.CollectedContentBase = Depends(),  # 使用 Depends 处理 form-data 混合
        file: Optional[UploadFile] = File(None, description="可选：上传新文件或图片替换旧的"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定ID的收藏内容。用户只能更新自己的收藏。
    如果上传新文件，将替换旧文件。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新收藏内容 ID: {content_id}。有文件: {bool(file)}")
    db_item = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not db_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    update_dict = content_data.dict(exclude_unset=True)

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_item.url 中提取旧的 OSS object name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_item.url and db_item.url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_item.url.replace(oss_base_url_parsed, '', 1)

    # 处理类型变更逻辑
    # 如果传入的 update_dict 包含 'type' 字段，并且类型发生了变化
    type_changed = "type" in update_dict and update_dict["type"] != db_item.type
    new_type_from_data = update_dict.get("type", db_item.type)  # 如果类型没有在update_dict中，沿用旧的类型

    if type_changed:
        # 如果旧类型是文件/图片/视频，需要删除旧的OSS文件
        if db_item.type in ["file", "image", "video"] and old_media_oss_object_name:
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(f"DEBUG_COLLECTED_CONTENT: Deleted old OSS file {old_media_oss_object_name} due to type change.")
            except Exception as e:
                print(
                    f"ERROR_COLLECTED_CONTENT: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during type change: {e}")

        # 清除不适用于新类型的字段
        if new_type_from_data not in ["file", "image", "video"]:  # 如果新类型是非媒体类型
            db_item.url = None
            db_item.file_size = None
            db_item.duration = None
            db_item.thumbnail = None  # 媒体专属字段

        if new_type_from_data == "text":
            # 如果新类型是text，要求 content 字段
            if not update_dict.get('content') and not db_item.content:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'text' 时，'content' 字段为必填。")
            db_item.url = None  # Text type should not have URL

        elif new_type_from_data == "link":
            # 如果新类型是link，要求 url 字段
            if not update_dict.get('url') and not db_item.url:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="类型为 'link' 时，'url' 字段为必填。")
            # content for links is optional, but if it came from a file, clear it.
            if db_item.type in ["file", "image", "video"]: db_item.content = None

        db_item.type = new_type_from_data  # 更新类型

    # 处理文件上传（如果提供了新文件或新的类型是 file/image/video）
    if file:
        current_type_after_update_check = update_dict.get("type", db_item.type)  # 获取最新材料类型
        if current_type_after_update_check not in ["file", "image", "video"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="只有类型为 'file', 'image' 或 'video' 的收藏才能上传文件。如需更改材料类型，请在content_data中同时指定 type。")

        # 如果旧的OSS文件存在且当前类型是文件/图片/视频，先删除旧文件
        if db_item.type in ["file", "image", "video"] and old_media_oss_object_name:
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(f"DEBUG_COLLECTED_CONTENT: Deleted old OSS file: {old_media_oss_object_name} for replacement.")
            except Exception as e:
                print(
                    f"ERROR_COLLECTED_CONTENT: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during replacement: {e}")

        # 读取新文件内容并上传到OSS
        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        content_type = file.content_type
        uploaded_file_size = file.size

        oss_path_prefix = "collected_files"
        if content_type.startswith('image/'):
            oss_path_prefix = "collected_images"
        elif content_type.startswith('video/'):
            oss_path_prefix = "collected_videos"

        new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

        try:
            db_item.url = await oss_utils.upload_file_to_oss(  # 存储OSS URL
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_item.file_size = uploaded_file_size  # Update file size
            # Update type if it was not already "file" / "image" / "video" but a file was sent
            if db_item.type not in ["file", "image", "video"]:
                if content_type.startswith('image/'):
                    db_item.type = "image"
                elif content_type.startswith('video/'):
                    db_item.type = "video"
                else:
                    db_item.type = "file"
                print(
                    f"DEBUG_COLLECTED_CONTENT: Material type automatically changed to '{db_item.type}' due to file upload.")

            # Clear content if it's a text-based content before but now replaced by file
            if "content" not in update_dict:  # Only clear if content was not explicitly sent or it was a text type
                db_item.content = None

            print(f"DEBUG_COLLECTED_CONTENT: New file '{file.filename}' uploaded to OSS: {db_item.url}")
        except HTTPException as e:
            print(f"ERROR_COLLECTED_CONTENT: Upload new file to OSS failed: {e.detail}")
            raise e
        except Exception as e:
            print(f"ERROR_COLLECTED_CONTENT: Unknown error during new file upload to OSS: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

    # 验证新的文件夹 (如果folder_id被修改)
    if "folder_id" in update_dict and update_dict["folder_id"] is not None:
        new_folder_id = update_dict["folder_id"]
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
        update_dict.pop("folder_id")  # Remove already handled field
    elif "folder_id" in update_dict and update_dict["folder_id"] is None:
        setattr(db_item, "folder_id", None)
        update_dict.pop("folder_id")  # Remove already handled field

    # 应用其他 update_dict 中的字段
    # Skip fields already handled or fields that should not be updated from here if file was uploaded
    fields_to_skip_after_file_upload = ["type", "url", "file_size", "duration", "thumbnail", "file", "content_text"]
    for key, value in update_dict.items():
        if key in fields_to_skip_after_file_upload:
            continue
        if hasattr(db_item, key) and value is not None:
            setattr(db_item, key, value)
        elif hasattr(db_item,
                     key) and value is None:  # Allow clearing fields (except `title` if it's mandatory non-null)
            if key == "title":  # Title is mandatory, cannot be None or empty
                if not value or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="收藏内容标题不能为空。")
            setattr(db_item, key, value)  # Allow setting to None for optional fields

    # 重新生成 combined_text
    db_item.combined_text = ". ".join(filter(None, [
        _get_text_part(db_item.title),
        _get_text_part(db_item.content),
        _get_text_part(db_item.url),  # Now contains OSS URL for files
        _get_text_part(db_item.tags),
        _get_text_part(db_item.type),
        _get_text_part(db_item.author),
        _get_text_part(db_item.original_filename if hasattr(db_item, 'original_filename') else None),
        # For existing files
        _get_text_part(db_item.file_type if hasattr(db_item, 'file_type') else None),  # For existing files
    ])).strip()

    # 获取当前用户的LLM配置用于嵌入更新
    current_user_obj = db.query(Student).filter(Student.id == current_user_id).first()
    user_llm_api_key = None
    user_llm_type = None
    user_llm_base_url = None
    user_llm_model_id = None

    if current_user_obj and current_user_obj.llm_api_type == "siliconflow" and current_user_obj.llm_api_key_encrypted:
        try:
            user_llm_api_key = ai_core.decrypt_key(current_user_obj.llm_api_key_encrypted)
            user_llm_type = current_user_obj.llm_api_type
            user_llm_base_url = current_user_obj.llm_api_base_url
            user_llm_model_id = current_user_obj.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用收藏更新者配置的硅基流动 API 密钥更新收藏内容嵌入。")
        except Exception as e:
            print(
                f"WARNING_COLLECTED_CONTENT_EMBEDDING: 解密用户 {current_user_id} LLM API密钥失败: {e}. 收藏内容嵌入将使用零向量。")
            user_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 收藏更新者未配置硅基流动 API 类型或密钥，收藏内容嵌入将使用零向量或默认行为。")

    embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
    if db_item.combined_text:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [db_item.combined_text],
                api_key=user_llm_api_key,
                llm_type=user_llm_type,
                llm_base_url=user_llm_base_url,
                llm_model_id=user_llm_model_id
            )
            if new_embedding:
                embedding_recalculated = new_embedding[0]
            print(f"DEBUG: 收藏内容 {db_item.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新收藏内容 {db_item.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 收藏内容 combined_text 为空，嵌入向量设为零。")
        embedding_recalculated = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db_item.embedding = embedding_recalculated  # 赋值给DB对象

    db.add(db_item)
    try:
        db.commit()
        db.refresh(db_item)
    except IntegrityError as e:
        db.rollback()
        # Rollback logic for newly uploaded file if DB commit fails
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(
                f"DEBUG_COLLECTED_CONTENT: Update DB commit failed, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_DB: 更新收藏内容发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新收藏内容失败，可能存在数据冲突。")
    except Exception as e:
        db.rollback()
        # Rollback logic for newly uploaded file if any other error
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(
                f"DEBUG_COLLECTED_CONTENT: Unknown error during update, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_DB: 更新收藏内容发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新收藏内容失败: {e}")

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
    如果收藏的内容是文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    """
    print(f"DEBUG: 删除收藏内容 ID: {content_id}。")
    db_item = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == current_user_id
    ).first()
    if not db_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Collected content not found or not authorized")

    # 如果是 'file', 'image', 'video' 类型，并且有 OSS URL，则尝试删除 OSS 文件
    if db_item.type in ["file", "image", "video"] and db_item.url:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_item.url.replace(oss_base_url_parsed, '', 1) if db_item.url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_COLLECTED_CONTENT: 删除了OSS文件: {object_name} (For collected content {content_id})")
            except Exception as e:
                print(f"ERROR_COLLECTED_CONTENT: 删除OSS文件 {object_name} 失败: {e}")
                # 这里不抛出异常，即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_COLLECTED_CONTENT: 收藏内容 {content_id} 的 URL ({db_item.url}) 无效或非OSS URL，跳过OSS文件删除。")

    db.delete(db_item)
    db.commit()
    print(f"DEBUG: 收藏内容 {content_id} 删除成功。")
    return {"message": "Collected content deleted successfully"}


# --- 聊天室管理接口 ---
@app.post("/chat-rooms/", response_model=schemas.ChatRoomResponse, summary="创建新的聊天室")
async def create_chat_room(
        chat_room_data: schemas.ChatRoomCreate,
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建聊天室: {chat_room_data.name}")

    try:
        # 1. 关联项目/课程的校验
        if chat_room_data.project_id:
            project = db.query(Project).filter(Project.id == chat_room_data.project_id).first()
            if not project:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的项目不存在。")
            if project.chat_room:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="项目已有关联聊天室。")

        if chat_room_data.course_id:
            course = db.query(Course).filter(Course.id == chat_room_data.course_id).first()
            if not course:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的课程不存在。")
            if course.chat_room:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="课程已有关联聊天室。")

        # 2. 创建聊天室记录
        db_chat_room = ChatRoom(
            name=chat_room_data.name,
            type=chat_room_data.type,
            project_id=chat_room_data.project_id,
            course_id=chat_room_data.course_id,
            creator_id=current_user_id,
            color=chat_room_data.color
        )
        db.add(db_chat_room)
        db.commit()  # 首次提交以获取 db_chat_room 的 ID
        db.refresh(db_chat_room)  # 刷新以加载数据库生成的 ID 和创建时间

        db_chat_room_member = ChatRoomMember(
            room_id=db_chat_room.id,
            member_id=current_user_id,
            role="king",
            status="active"
        )
        db.add(db_chat_room_member)
        db.commit()  # 提交成员记录

        db_chat_room.members_count = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == db_chat_room.id,
            ChatRoomMember.status == "active"
        ).count()  # 获取活跃成员数量

        db_chat_room.last_message = {"sender": "系统", "content": "聊天室已创建！"}
        db_chat_room.unread_messages_count = 0
        db_chat_room.online_members_count = 0

        print(f"DEBUG: 聊天室 '{db_chat_room.name}' (ID: {db_chat_room.id}) 创建成功，创建者已添加为成员。")
        return db_chat_room

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 聊天室创建发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="聊天室创建失败，可能存在重复的数据（如项目/课程已有关联聊天室）或名称冲突。")
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建聊天室失败: {e}")


# project/main.py (聊天室管��接口部分)
@app.get("/chatrooms/", response_model=List[schemas.ChatRoomResponse], summary="获取当前用户所属的所有聊天室")
async def get_all_chat_rooms(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        room_type: Optional[str] = None  # 类型过滤
):
    """
    获取当前用户所属（创建或参与）的所有聊天室列表。
    可通过 type 过滤（例如：project_group, course_group）。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的所有聊天室，类型过滤: {room_type}")

    # 1. 构建核心权限查询：用户是创建者 OR 用户是活跃成员
    # 条件1: 用户是聊天室的创建者
    user_is_creator_condition = ChatRoom.creator_id == current_user_id

    # 条件2: 用户是该聊天室的活跃成员 (通过 exists 子查询判断)
    user_is_active_member_condition = (
        db.query(ChatRoomMember.id)
        .filter(
            ChatRoomMember.room_id == ChatRoom.id,  # 确保是当前聊天室的成员
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        )
        .exists()  # 如果存在符合条件的记录，则为 True
    )

    # 组合这两个条件
    main_filter_condition = or_(user_is_creator_condition, user_is_active_member_condition)

    # 构建基础查询
    rooms_query = db.query(ChatRoom).filter(main_filter_condition)

    # 应用类型过滤
    if room_type:
        rooms_query = rooms_query.filter(ChatRoom.type == room_type)

    # 执行查询，获取所有符合权限和过滤条件的聊天室
    rooms = rooms_query.order_by(ChatRoom.updated_at.desc()).all()

    # 2. 优化 N+1 问题 ：一次性获取所有房间的最新消息和发送者信息
    room_ids = [room.id for room in rooms]

    room_latest_messages_map = {}  # 用于存储 {room_id: last_message_info_dict}
    if room_ids:  # 只有当有房间时才执行消息查询
        ranked_messages_subquery = (
            db.query(
                ChatMessage.room_id,
                ChatMessage.sender_id,
                ChatMessage.content_text,
                ChatMessage.sent_at,
                func.row_number().over(
                    partition_by=ChatMessage.room_id,
                    order_by=ChatMessage.sent_at.desc()
                ).label('rn')
            )
            .filter(
                ChatMessage.room_id.in_(room_ids),
                ChatMessage.deleted_at.is_(None)  # 排除已删除的消息
            )
            .subquery('ranked_messages')
        )

        latest_messages_with_senders = (
            db.query(
                ranked_messages_subquery.c.room_id,
                ranked_messages_subquery.c.content_text,
                Student.name.label('sender_name')
            )
            .join(Student, Student.id == ranked_messages_subquery.c.sender_id)
            .filter(ranked_messages_subquery.c.rn == 1)
            .all()
        )

        for msg in latest_messages_with_senders:
            room_latest_messages_map[msg.room_id] = {
                "sender": msg.sender_name or "未知",
                "content": (msg.content_text[:50] + "..." if msg.content_text and len(msg.content_text) > 50 else (
                        msg.content_text or ""))
            }

    # 3. 填充动态统计字段到每个聊天室对象
    for room in rooms:
        # 动态计算成员数量 (已在 ChatRoomMember 逻辑中处理)
        room.members_count = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room.id,
            ChatRoomMember.status == "active"
        ).count()

        # 从预加载的字典中获取最新消息
        last_message_info = room_latest_messages_map.get(room.id)
        if last_message_info:
            room.last_message = last_message_info
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
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的聊天室详情。
    只有聊天室的创建者、活跃成员或系统管理员才能查看。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试获取聊天室 ID: {room_id} 的详情。")

    try:
        # 1. 获取当前用户和目标聊天室的信息
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 2. 权限检查：用户是否是群主、活跃成员或系统管理员**
        is_creator = (chat_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member or current_user.is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您无权查看该聊天室的详情。")

        # 3. 填充动态统计字段
        chat_room.members_count = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == chat_room.id,
            ChatRoomMember.status == "active"
        ).count()

        latest_message_data = (
            db.query(ChatMessage.content_text, Student.name)
            .filter(
                ChatMessage.room_id == chat_room.id,
                ChatMessage.deleted_at.is_(None)  # 排除已删除的消息
            )
            .join(Student, Student.id == ChatMessage.sender_id)
            .order_by(ChatMessage.sent_at.desc())
            .first()
        )

        if latest_message_data:
            content_text, sender_name = latest_message_data
            chat_room.last_message = {
                "sender": sender_name or "未知",
                "content": content_text[:50] + "..." if content_text and len(content_text) > 50 else (
                            content_text or "")
            }
        else:
            chat_room.last_message = {"sender": "系统", "content": "暂无消息"}

        chat_room.unread_messages_count = 0
        chat_room.online_members_count = 0

        return chat_room

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取聊天室详情失败: {e}")


# 聊天室管理接口部分
@app.get("/chatrooms/{room_id}/members", response_model=List[schemas.ChatRoomMemberResponse],
         summary="获取指定聊天室的所有成员列表")
async def get_chat_room_members(
        room_id: int,  # 目标聊天室ID
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试获取聊天室 {room_id} 的成员列表。")

    try:
        # 1. 获取当前用户和目标聊天室的信息
        # 使用转换后的 current_user_id_int 进行数据库查询
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 2. 核心权限检查：用户是否是群主、聊天室管理员或系统管理员
        is_creator = (chat_room.creator_id == current_user_id)
        is_room_admin = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,  # 查询时使用转换后的 current_user_id_int**
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_room_admin or current_user.is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该聊天室的成员列表。")

        # 3. 查询聊天室所有成员，并通过 joinedload 预加载关联的 Student 信息
        memberships = db.query(ChatRoomMember).options(
            joinedload(ChatRoomMember.member)  # 预加载成员的用户信息
        ).filter(ChatRoomMember.room_id == room_id).all()

        # 遍历成员关系，提取并填充 member_name
        response_members = []
        for member_ship in memberships:
            member_response_dict = {
                "id": member_ship.id,
                "room_id": member_ship.room_id,
                "member_id": member_ship.member_id,
                "role": member_ship.role,
                "status": member_ship.status,
                "joined_at": member_ship.joined_at,
                "member_name": member_ship.member.name if member_ship.member else "未知用户"  # 填充姓名
            }
            response_members.append(schemas.ChatRoomMemberResponse(**member_response_dict))

        print(f"DEBUG: 聊天室 {room_id} 获取到 {len(response_members)} 位成员。")
        return response_members  # 返回手动构建的响应列表

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取聊天室成员列表失败: {e}")


# 设置系统管理员权限接口 - 管理员专用
@app.put("/admin/users/{user_id}/set-admin", response_model=schemas.StudentResponse,
         summary="【管理员专用】设置系统管理员权限")
async def set_user_admin_status(
        user_id: int,  # 目标用户ID
        admin_status: schemas.UserAdminStatusUpdate,  # 包含 is_admin 值
        current_user_id: str = Depends(get_current_user_id),  # 已认证的系统管理员ID
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)  # 转换为整数

    print(f"DEBUG_ADMIN: 管理员 {current_user_id_int} 尝试设置用户 {user_id} 的管理员权限为 {admin_status.is_admin}。")

    try:
        # 1. 验证操作者是否为系统管理员
        current_admin = db.query(Student).filter(Student.id == current_user_id_int).first()
        if not current_admin or not current_admin.is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权执行此操作。只有系统管理员才能设置用户管理员权限。")

        # 2. 查找目标用户
        target_user = db.query(Student).filter(Student.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户未找到。")

        # 3. 不允许系统管理员取消自己的系统管理员权限 (防止误操作导致失去最高权限)
        if current_user_id_int == user_id and not admin_status.is_admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="系统管理员不能取消自己的管理员权限。请联系其他系统管理员协助。")

        # 4. 更新目标用户的管理员状态
        target_user.is_admin = admin_status.is_admin
        db.add(target_user)
        db.commit()
        db.refresh(target_user)

        print(f"DEBUG_ADMIN: 用户 {user_id} 的管理员权限已成功设置为 {admin_status.is_admin}。")
        return target_user

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 设置管理员权限失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"设置管理员权限失败: {e}")


# 设置成员角色接口 - 聊天室管理部分
@app.put("/chat-rooms/{room_id}/members/{member_id}/set-role", response_model=schemas.ChatRoomMemberResponse,
         summary="设置聊天室成员的角色（管理员/普通成员）")
async def set_chat_room_member_role(
        room_id: int,  # 目标聊天室ID
        member_id: int,  # 目标成员的用户ID
        role_update: schemas.ChatRoomMemberRoleUpdate,  # 包含新的角色信息
        current_user_id: str = Depends(get_current_user_id),  # 明确类型为 str
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)  # 将字符串ID转换为整数

    # 使用转换后的 current_user_id_int
    print(
        f"DEBUG: 用户 {current_user_id_int} 尝试设置聊天室 {room_id} 中用户 {member_id} 的角色为 '{role_update.role}'。")

    try:
        # 1. 验证目标角色是否合法
        if role_update.role not in ["admin", "member"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="无效的角色类型，只能为 'admin' 或 'member'。")

        # 2. 获取当前操作用户、目标聊天室和目标成员关系
        # 使用转换后的 current_user_id_int 进行数据库查询
        current_user = db.query(Student).filter(Student.id == current_user_id_int).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 获取目标成员的 ChatRoomMember 记录
        # 确保 db_member.member 关系已被加载
        db_member = db.query(ChatRoomMember).options(joinedload(ChatRoomMember.member)).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == member_id,  # member_id 已经是 int
            ChatRoomMember.status == "active"  # 确保是活跃成员
        ).first()
        if not db_member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户不是该聊天室的活跃成员。")

        # 不允许通过此接口修改群主自己 (群主身份由 creator_id 管理)
        # 使用转换后的 current_user_id_int
        if chat_room.creator_id == db_member.member_id:  # 这里的 db_member.member_id 通常是 int，所以比较的是 int == int
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="群主的角色不能通过此接口修改。群主身份由 ChatRoom.creator_id 字段定义。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM_SET_ROLE: current_user_id_int={current_user_id_int}, chat_room.creator_id={chat_room.creator_id}, current_user.is_admin={current_user.is_admin}")

        # 3. 核心操作权限检查：只有群主可以设置聊天室成员角色
        # 比较时使用转换后的 current_user_id_int
        is_creator = (chat_room.creator_id == current_user_id_int)

        print(f"DEBUG_PERM_SET_ROLE: is_creator={is_creator}")

        if not is_creator:  # 仅检查 is_creator
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权设置聊天室成员角色。只有群主可以执行此操作。")

        # 4. 特殊业务逻辑限制 (防止聊天室管理员给自己降权)
        # 比较时使用转换后的 current_user_id_int
        if current_user_id_int == member_id and db_member.role == "admin" and role_update.role == "member":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="聊天室管理员不能取消自己的管理员权限。")

        # 5. 更新目标成员的角色
        db_member.role = role_update.role

        db.add(db_member)
        db.commit()
        db.refresh(db_member)

        print(f"DEBUG: 聊天室 {room_id} 中的用户 {member_id} 的角色已更新为 '{role_update.role}'。")

        # 填充 member_name 到响应中 (确保 db_member.member 已通过 joinedload 加载)
        db_member.member_name = db_member.member.name if db_member.member else "未知用户"
        return db_member

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 设置成员角色失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"设置成员角色失败: {e}")


# 聊天室管理接口部分 - 删除成员
@app.delete("/chat-rooms/{room_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT,  # 改为 204 No Content
            summary="从聊天室移除成员（踢出或离开）")
async def remove_chat_room_member(
        room_id: int,
        member_id: int,  # 目标成员的用户ID
        current_user_id: str = Depends(get_current_user_id),  # 操作者用户ID (现在明确是 str 类型)
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)  # 将字符串ID转换为整数

    print(f"DEBUG: 用户 {current_user_id_int} 尝试从聊天室 {room_id} 移除成员 {member_id}。")

    try:
        # 1. 获取当前操作用户、目标聊天室和目��成员的 ChatRoomMember 记录
        # 使用转换后的 current_user_id_int 进行数据库查询
        acting_user = db.query(Student).filter(Student.id == current_user_id_int).first()
        if not acting_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 获取目标成员的 ChatRoomMember 记录，且必须是活跃成员才能被操作
        target_membership = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == member_id,  # member_id 已经是 int
            ChatRoomMember.status == "active"
        ).first()

        if not target_membership:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户不是该聊天室的活跃成员。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM_REMOVE: current_user_id_int={current_user_id_int}, chat_room.creator_id={chat_room.creator_id}, current_user.is_admin={acting_user.is_admin}")

        # 2. 处理用户自己离开群聊的情况
        if current_user_id_int == member_id:
            print(f"DEBUG_PERM_REMOVE: 判定为用户 {current_user_id_int} 尝试自己离开。")
            # 群主不能通过此接口离开群聊（他们应该使用解散群聊功能）
            if chat_room.creator_id == current_user_id_int:  # 使用 int 型 ID 比较
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="群主不能通过此接口离开群聊。要解散聊天室请使用解散功能。")

            # 其他活跃成员可以直接离开群聊
            target_membership.status = "left"  # 标记为“已离开”
            db.add(target_membership)
            db.commit()
            print(f"DEBUG: 用户 {current_user_id_int} 已成功离开聊天室 {room_id}。")
            return Response(status_code=status.HTTP_204_NO_CONTENT)  # 成功离开，返回 204

        # 3. 处理踢出他人成员的情况** (`member_id` != `current_user_id_int`)
        print(f"DEBUG_PERM_REMOVE: 判定为用户 {current_user_id_int} 尝试移除他人 {member_id}。")
        # 确定操作者的角色
        is_creator = (chat_room.creator_id == current_user_id_int)  # 使用 int 型 ID 比较
        is_system_admin = acting_user.is_admin

        # 如果操作者不是群主也不是系统管理员，则去查询他是否是聊天室管理员
        acting_user_membership = None
        if not is_creator and not is_system_admin:
            print(f"DEBUG_PERM_REMOVE: 操作者不是群主也不是系统管理员，检查是否是聊天室管理员。")
            acting_user_membership = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == room_id,
                ChatRoomMember.member_id == current_user_id_int,
                ChatRoomMember.status == "active"
            ).first()

        is_room_admin = (acting_user_membership and acting_user_membership.role == "admin")

        print(
            f"DEBUG_PERM_REMOVE: is_creator={is_creator}, is_system_admin={is_system_admin}, is_room_admin={is_room_admin}")

        # 确定被操作成员的角色
        target_member_is_creator = (member_id == chat_room.creator_id)
        target_member_role_in_room = target_membership.role  # 'admin' or 'member' (来自ChatRoomMember表)

        # 权限决策树 - 谁可以踢谁
        can_kick = False
        reason_detail = "无权将该用户从聊天室移除。"  # 默认的拒绝理由

        if is_system_admin:
            can_kick = True  # 系统管理员可以踢出任何人
            print(f"DEBUG_PERM_REMOVE: 系统管理员 {current_user_id_int} 允许踢出。")
        elif is_creator:
            can_kick = True  # 群主可以踢出任何人
            print(f"DEBUG_PERM_REMOVE: 群主 {current_user_id_int} 允许踢出。")
        elif is_room_admin:
            # 聊天室管理员只能在特定条件下踢人
            if target_member_is_creator:
                reason_detail = "聊天室管理员无权移除群主。"
                print(f"DEBUG_PERM_REMOVE: 聊天室管理员 {current_user_id_int} 试图移除群主，拒绝。")
            elif target_member_role_in_room == "admin":
                reason_detail = "聊天室管理员无权移除其他管理员。"
                print(f"DEBUG_PERM_REMOVE: 聊天室管理员 {current_user_id_int} 试图移除其他管理员，拒绝。")
            else:  # 目标成员是普通成员
                can_kick = True
                print(f"DEBUG_PERM_REMOVE: 聊天室管理员 {current_user_id_int} 允许踢出普通成员 {member_id}。")

        if not can_kick:
            print(f"DEBUG_PERM_REMOVE: 最终权限判定为拒绝，原因：{reason_detail}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason_detail)

        # 4. 执行移除操作：更新目标成员状态为 'banned' (被踢出)
        target_membership.status = "banned"
        # 聊天室管理员被踢出后，其角色仍然保持 'admin' 历史记录，只是状态变 'banned'。
        # 如果需要彻底降级，可以在此设置
        target_membership.role = "member"
        db.add(target_membership)
        db.commit()

        print(f"DEBUG: 成员 {member_id} 已成功从聊天室 {room_id} 移除（被踢出）。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)  # 成功踢出，返回 204

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 从聊天室移除成员失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"从聊天室移除成员失败: {e}")


@app.put("/chatrooms/{room_id}/", response_model=schemas.ChatRoomResponse, summary="更新指定聊天室")
async def update_chat_room(
        room_id: int,  # 从路径中获取聊天室ID
        room_data: schemas.ChatRoomUpdate,  # 要更新的聊天室数据
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 更新聊天室 ID: {room_id}。用户: {current_user_id}")

    try:  # 整个核心逻辑放入 try 块中
        # 核心权限检查：只有创建者才能更新聊天室
        # TODO: 未来扩展：允许特定类型的管理员或被授权的成员更新
        db_chat_room = db.query(ChatRoom).filter(
            ChatRoom.id == room_id,
            ChatRoom.creator_id == current_user_id  # 确保当前用户是该聊天室的创建者
        ).first()

        if not db_chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到或无权访问。")

        update_data = room_data.dict(exclude_unset=True)

        # 验证 project_id / course_id 关联
        if "project_id" in update_data and update_data["project_id"] is not None:
            project = db.query(Project).filter(Project.id == update_data["project_id"]).first()
            if not project:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的项目不存在。")
            # 检查项目是否已有关联聊天室，或是否是当前聊天室自己
            if project.chat_room and project.chat_room.id != room_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Project already has an associated chat room.")
            # TODO: 进一步验证 current_user_id 是否有权将聊天室关联到此项目

        if "course_id" in update_data and update_data["course_id"] is not None:
            course = db.query(Course).filter(Course.id == update_data["course_id"]).first()
            if not course:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
            # 检查课程是否已有关联聊天室，或是否是当前聊天室自己
            if course.chat_room and course.chat_room.id != room_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Course already has an associated chat room.")
            # TODO: 进一步验证 current_user_id 是否��权将聊天室关联到此课程

        # 应用更新
        for key, value in update_data.items():
            setattr(db_chat_room, key, value)

        db.add(db_chat_room)
        db.commit()  # 提交事务
        db.refresh(db_chat_room)  # 刷新以获取最新状态

        print(f"DEBUG: 聊天室 {room_id} 更新成功。")

        # 填充动态统计字段 (确保返回DTO的完整性)
        db_chat_room.members_count = 1
        latest_message_data = (
            db.query(ChatMessage.content_text, Student.name)
            .filter(
                ChatMessage.room_id == db_chat_room.id,
                ChatMessage.deleted_at.is_(None)  # 排除已删除的消息
            )
            .join(Student, Student.id == ChatMessage.sender_id)
            .order_by(ChatMessage.sent_at.desc())
            .first()
        )
        if latest_message_data:
            content_text, sender_name = latest_message_data
            db_chat_room.last_message = {
                "sender": sender_name or "未知",
                "content": content_text[:50] + "..." if content_text and len(content_text) > 50 else (
                        content_text or "")
            }
        else:
            db_chat_room.last_message = {"sender": "系统", "content": "暂无消息"}

        db_chat_room.unread_messages_count = 0
        db_chat_room.online_members_count = 0

        return db_chat_room

    except IntegrityError as e:  # 捕获数据库完整性错误
        db.rollback()  # 回滚事务
        print(f"ERROR_DB: 聊天室更新发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="更新聊天室失败，可能存在名称冲突或其他完整性约束冲突。")
    except HTTPException as e:  # 捕获前面主动抛出的 HTTPException**
        db.rollback()  # 确保回滚
        raise e  # 重新抛出已携带正确状态码和详情的 HTTPException
    except Exception as e:  # 捕获其他任何未预期错误
        db.rollback()  # 确保在异常时回滚
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新聊天室失败: {e}")


@app.delete("/chatrooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定聊天室（仅限群主或系统管理员）",
            operation_id="delete_single_chat_room_by_creator_or_admin")  # 明确且唯一的 operation_id
async def delete_chat_room(
        room_id: int,  # 从路径中获取聊天室ID
        current_user_id: str = Depends(get_current_user_id),  # 已认证的用户ID (现在明确是 str 类型)
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)  # 将字符串ID转换为整数

    print(f"DEBUG: 删除聊天室 ID: {room_id}。操作用户: {current_user_id_int}")

    try:
        # 1. 获取当前用户的信息，以便检查其是否为管理员
        # 使用转换后的 current_user_id_int 进行数据库查询
        current_user = db.query(Student).filter(Student.id == current_user_id_int).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        # 2. 获取目标聊天室
        db_chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM_DELETE_ROOM: current_user_id={current_user_id_int} (type={type(current_user_id_int)}), chat_room.creator_id={db_chat_room.creator_id} (type={type(db_chat_room.creator_id)})")
        print(f"DEBUG_PERM_DELETE_ROOM: current_user.is_admin={current_user.is_admin}")

        # 核心权限检查：只有群主或系统管理员可以删除此聊天室
        # 使用 int 型 ID 进行比较
        is_creator = (db_chat_room.creator_id == current_user_id_int)
        is_system_admin = current_user.is_admin

        print(f"DEBUG_PERM_DELETE_ROOM: is_creator={is_creator}, is_system_admin={is_system_admin}")
        print(f"DEBUG_PERM_DELETE_ROOM: Final DELETE ROOM permission: {is_creator or is_system_admin}")

        if not (is_creator or is_system_admin):
            # 如果既不是创建者也不是系统管理员，则无权删除
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权删除此聊天室。只有群主或系统管理员可以执行此操作。")

        # 执行删除操作：确保所有关联数据级联删除
        # SQLAlchemy的模型定义中，通常会使用 cascade="all, delete-orphan" 或 ON DELETE CASCADE
        # 来处理关联数据的级联删除。如果模型关系配置得当，直接删除 chat_room 即可。
        # 如果没有配置级联，需要手动删除相关联的 records (chat_messages, chat_room_members, chat_room_join_requests)

        # 假设模型已正确配置 ON DELETE CASCADE 或 cascade="all, delete-orphan"
        # 则只需删除聊天室本身
        db.delete(db_chat_room)  # 标记为删除
        db.commit()  # 提交事务

        # 如果没有配置级联，以下代码可以手动删除，但推荐通过模型配置级联
        # db.query(ChatMessage).filter(ChatMessage.room_id == room_id).delete()
        # print(f"DEBUG: 聊天室 {room_id} 的所有消息已删除。")
        # db.query(ChatRoomMember).filter(ChatRoomMember.room_id == room_id).delete()
        # print(f"DEBUG: 聊天室 {room_id} 的所有成员关联已删除。")
        # db.query(ChatRoomJoinRequest).filter(ChatRoomJoinRequest.room_id == room_id).delete()
        # print(f"DEBUG: 聊天室 {room_id} 的所有入群申请已删除。")
        # db.delete(db_chat_room)
        # db.commit()

        print(f"DEBUG: 聊天室 {room_id} 及其所有关联数据已成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)  # 成功删除，返回 204

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 聊天室删除发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="删除聊天室失败，可能存在数据关联问题。")
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除聊天室失败: {e}")


@app.post("/chat-rooms/{room_id}/join-request", response_model=schemas.ChatRoomJoinRequestResponse,
          summary="向指定聊天室发起入群申请")
async def send_join_request(
        room_id: int,  # 目标聊天室ID
        request_data: schemas.ChatRoomJoinRequestCreate,  # 申请理由等 (包含 room_id，但我们只用路径中的 room_id)
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID，即申请者
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试向聊天室 {room_id} 发起入群申请。理由: {request_data.reason}")

    if request_data.room_id != room_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请求体中的room_id与路径中的room_id不匹配。")

    try:
        # 1. 验证目标聊天室是否存在
        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 2. 验证申请者身份：不能是聊天室创建者
        if chat_room.creator_id == current_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="您已经是该聊天室的创建者，无需申请加入。")

        # 3. 验证申请者是否已经是活跃成员
        existing_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first()
        if existing_member:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="您已是该聊天室的活跃成员，无需重复申请。")

        # 4. 验证申请者是否已有待处理的申请 (通过数据库的 UniqueConstraint 实现，但也可以在这里提前检查)
        existing_pending_request = db.query(ChatRoomJoinRequest).filter(
            ChatRoomJoinRequest.room_id == room_id,
            ChatRoomJoinRequest.requester_id == current_user_id,
            ChatRoomJoinRequest.status == "pending"
        ).first()
        if existing_pending_request:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="您已有待处理的入群申请，请勿重复提交。")

        # 5. 创建入群申请记录
        db_join_request = ChatRoomJoinRequest(
            room_id=room_id,
            requester_id=current_user_id,
            reason=request_data.reason,
            status="pending"  # 默认状态为待处理
        )
        db.add(db_join_request)
        db.commit()
        db.refresh(db_join_request)

        print(f"DEBUG: 用户 {current_user_id} 向聊天室 {room_id} 发起的入群申请 (ID: {db_join_request.id}) 已提交。")
        return db_join_request

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 入群申请创建发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="入群申请提交失败，可能存在重复申请或其他数据冲突。")
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"提交入群申请失败: {e}")


# 获取入群申请列表接口 - 聊天室管理部分
@app.get("/chat-rooms/{room_id}/join-requests", response_model=List[schemas.ChatRoomJoinRequestResponse],
         summary="获取指定聊天室的入群申请列表")
async def get_join_requests_for_room(
        room_id: int,  # 目标聊天室ID
        # 允许通过 status 过滤请求 (例如 'pending', 'approved', 'rejected')
        status_filter: Optional[str] = Query("pending", description="过滤申请状态（pending, approved, rejected）"),
        current_user_id: str = Depends(get_current_user_id),  # 已认证的用户ID，现在明确是 str 类型
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)  # 将字符串ID转换为整数，用于后续比较和查询DB

    # 使用转换后的 current_user_id_int**
    print(f"DEBUG: 用户 {current_user_id_int} 尝试获取聊天室 {room_id} 的入群申请列表 (状态: {status_filter})。")

    try:
        # 1. 获取当前用户和目标聊天室的信息
        # 使用转换后的 current_user_id_int 进行数据库查询
        current_user = db.query(Student).filter(Student.id == current_user_id_int).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM: current_user_id={current_user_id_int} (type={type(current_user_id_int)}), chat_room.creator_id={chat_room.creator_id} (type={type(chat_room.creator_id)}), current_user.is_admin={current_user.is_admin}")

        # 2. 核心权限检查：用户是否是群主、聊天室管理员或系统管理员
        # 比较时使用转换后的 current_user_id_int
        is_creator = (chat_room.creator_id == current_user_id_int)
        is_room_admin = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id_int,  # 查询时使用转换后的 current_user_id_int**
            ChatRoomMember.status == "active"
        ).first() is not None  # 判断是否存在活跃的管理员成员记录

        print(f"DEBUG_PERM: is_creator={is_creator}, is_room_admin={is_room_admin}")
        print(f"DEBUG_PERM: Final combined permission: {is_creator or is_room_admin or current_user.is_admin}")

        # 只有群主、聊天室管理员或系统管理员才能查看申请
        if not (is_creator or is_room_admin or current_user.is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该聊天室的入群申请。")

        # 3. 构建查询条件
        query = db.query(ChatRoomJoinRequest).filter(ChatRoomJoinRequest.room_id == room_id)

        # 应用状态过滤
        if status_filter:
            query = query.filter(ChatRoomJoinRequest.status == status_filter)

        # 4. 执行查询并返回结果
        join_requests = query.order_by(ChatRoomJoinRequest.requested_at.asc()).all()

        print(f"DEBUG: 聊天室 {room_id} 获取到 {len(join_requests)} 条入群申请。")
        return join_requests

    except HTTPException as e:
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取入群申请失败: {e}")


# 处理入群申请接口 - 聊天室管理部分
@app.post("/chat-rooms/join-requests/{request_id}/process", response_model=schemas.ChatRoomJoinRequestResponse,
          summary="处理入群申请 (批准或拒绝)")
async def process_join_request(
        request_id: int,  # 要处理的入群申请ID
        process_data: schemas.ChatRoomJoinRequestProcess,  # 包含处理结果 (approved/rejected)
        current_user_id: str = Depends(get_current_user_id),  # 已认证的用户ID，即处理者 (现在明确是 str 类型)
        db: Session = Depends(get_db)
):
    current_user_id_int = int(current_user_id)  # 将字符串ID转换为整数，用于后续比较和查询DB

    print(f"DEBUG: 用户 {current_user_id_int} 尝试处理入群申请 ID: {request_id} 为 '{process_data.status}'。")

    try:
        # 1. 验证目标入群申请是否存在且为 pending 状态
        db_request = db.query(ChatRoomJoinRequest).filter(ChatRoomJoinRequest.id == request_id).first()
        if not db_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="入群申请未找到。")
        if db_request.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该申请已处理或状态异常，无法再次处理。")

        # 2. 获取当前用户和目标聊天室的信息，用于权限检查
        current_user = db.query(Student).filter(Student.id == current_user_id_int).first()  # **使用 int 型 ID 查询**
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == db_request.room_id).first()
        if not chat_room:
            # 理论上不会发生，因为 db_request.room_id 引用 ChatRoom
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的聊天室不存在。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM_PROCESS: current_user_id_int={current_user_id_int}, chat_room.creator_id={chat_room.creator_id}, current_user.is_admin={current_user.is_admin}")

        # 3. 核心权限检查：处理者是否是群主、聊天室管理员或系统管理员
        is_creator = (chat_room.creator_id == current_user_id_int)  # 使用 int 型 ID 比较
        is_room_admin = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == chat_room.id,
            ChatRoomMember.member_id == current_user_id_int,  # 使用 int 型 ID 比较
            ChatRoomMember.role == "admin",
            ChatRoomMember.status == "active"
        ).first() is not None

        print(f"DEBUG_PERM_PROCESS: is_creator={is_creator}, is_room_admin={is_room_admin}")
        print(f"DEBUG_PERM_PROCESS: Final combined permission: {is_creator or is_room_admin or current_user.is_admin}")

        if not (is_creator or is_room_admin or current_user.is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权处理此入群申请。")

        # 4. 验证请求的状态是否合法
        if process_data.status not in ["approved", "rejected"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="无效的申请处理状态，只能是 'approved' 或 'rejected'。")

        # 5. 更新申请状态及处理信息
        db_request.status = process_data.status
        db_request.processed_by_id = current_user_id_int  # 使用 int 型 ID 赋值
        db_request.processed_at = func.now()

        db.add(db_request)
        db.commit()  # 提交申请状态的更新
        # db.refresh(db_request) # 刷新 db_request，如果你需要获取 processed_by_id 等最新值，否则可以省略

        # 6. 如果申请被批准，则将用户添加到聊天室成员表中
        if process_data.status == "approved":
            # 检查用户是否已经以某种方式（例如之前被审批过）成为了成员
            existing_member = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == db_request.room_id,
                ChatRoomMember.member_id == db_request.requester_id
            ).first()

            if existing_member:
                # 如果已存在，更新其状态为 active (例如，从 'left' 或 'banned' 恢复)
                existing_member.status = "active"
                existing_member.role = "member"  # 批准加入时默认是普通成员
                db.add(existing_member)
                print(f"DEBUG: 用户 {db_request.requester_id} 在聊天室 {db_request.room_id} 的成员状态已激活。")
            else:
                # 创建新的成员记录
                new_member = ChatRoomMember(
                    room_id=db_request.room_id,
                    member_id=db_request.requester_id,  # requester_id 从 db_request 来，已经是 int
                    role="member",
                    status="active"
                )
                db.add(new_member)
                print(f"DEBUG: 用户 {db_request.requester_id} 已添加为聊天室 {db_request.room_id} 的成员。")

            db.commit()  # 提交成员表的更改

        print(f"DEBUG: 入群申请 ID: {request_id} 已成功处理为 '{process_data.status}'。")
        # 为 ChatRoomJoinRequestResponse 自动填充 member_name
        # 确保 db_request.requester 关系被加载
        db.refresh(db_request)  # 确保最新的db_request返回，特别是processed_by_id和processed_at
        return db_request

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 入群申请处理发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="处理入群申请失败，可能存在数据冲突。")
    except HTTPException as e:  # 捕获上面主动抛出的 HTTPException
        # 这里不需要 db.rollback() 因为 HTTPException 通常表示验证失败，而不是事务性错误
        # 并且，get_db() 的 finally 块会处理 session 关闭
        raise e  # 重新抛出已携带正确状态码和详情的 HTTPException
    except Exception as e:
        db.rollback()  # 对于其他未预期的数据库或内部错误，执行回滚
        print(f"ERROR_DB: 数据库会话使用过程中发生未知异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"处理入群申请失败: {e}")


# --- 聊天消息管理接口 ---
@app.post("/chatrooms/{room_id}/messages/", response_model=schemas.ChatMessageResponse,
          summary="在指定聊天室发送新消息")
async def send_chat_message(
        room_id: int,
        # 移除 message_data: schemas.ChatMessageCreate = Depends()，我们将手动从 Form 参数构建它
        content_text: Optional[str] = Form(None, description="消息文本内容，当message_type为'text'时为必填"),
        # 使用 From 明确接收表单字段
        message_type: Literal["text", "image", "file", "video", "system_notification"] = Form("text",
                                                                                              description="消息类型"),
        # 使用 From
        media_url: Optional[str] = Form(None, description="媒体文件OSS URL或外部链接"),  # 使用 From
        file: Optional[UploadFile] = File(None, description="上传文件、图片或视频作为消息"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    在指定聊天室中发送一条新消息。
    只有活跃成员和群主可以发送消息。
    支持发送文本、图片、文件、视频。
    """
    print(f"DEBUG: 用户 {current_user_id} 在聊天室 {room_id} 发送消息。类型: {message_type}")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 1. 验证聊天室是否存在
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found.")

        # 2. 权限检查：发送者是否是活跃成员或群主
        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="您无权在该聊天室发送消息。请先加入聊天室。")

        # 3. 验证发送者用户是否存在 (get_current_user_id 已经验证了，这里是双重检查)
        db_sender = db.query(Student).filter(Student.id == current_user_id).first()
        if not db_sender:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发送者用户未找到。")

        final_media_url = media_url  # 初始化为 Form 接收到的 media_url
        final_content_text = content_text  # 初始化为 Form 接收到的 content_text
        final_message_type = message_type  # 初始化为 Form 接收到的 message_type

        # 4. 处理文件上传（如果提供了文件）
        if file:
            # 检查 message_type 是否与文件上传一致
            if final_message_type not in ["file", "image", "video"]:  # 补充了 video 类型检查
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，message_type 必须为 'file', 'image' 或 'video'。")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type

            # 根据文件类型确定OSS存储路径前缀
            oss_path_prefix = "chat_files"  # 默认文件
            if content_type.startswith('image/'):
                oss_path_prefix = "chat_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "chat_videos"

            current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=content_type
                )
                print(f"DEBUG: 文件 '{file.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_media_url}")

                # 如果内容文本为空，将文件名或简短描述作为内容
                if not final_content_text and file.filename:
                    final_content_text = f"文件: {file.filename}"
                    if content_type.startswith('image/'):
                        final_content_text = f"图片: {file.filename}"
                    elif content_type.startswith('video/'):
                        final_content_text = f"视频: {file.filename}"

                # 确保当有文件时，message_type 确实反映文件类型
                if content_type.startswith('image/') and final_message_type != "image":
                    final_message_type = "image"
                elif content_type.startswith('video/') and final_message_type != "video":
                    final_message_type = "video"
                elif final_message_type not in ["file", "image", "video"]:
                    final_message_type = "file"


            except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
                print(f"ERROR: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出，让FastAPI处理
            except Exception as e:
                print(f"ERROR: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=f"文件上传到云存储失败: {e}")
        else:  # 没有上传文件
            # 这里的明确校验逻辑可以简化，因为 Pydantic 模型会处理
            pass

        # 5. 手动创建 ChatMessageCreate 实例，触发 Pydantic 校验
        try:
            message_data_validated = schemas.ChatMessageCreate(
                content_text=final_content_text,
                message_type=final_message_type,
                media_url=final_media_url
            )
        except ValueError as e:
            # 如果 Pydantic 校验失败，捕获并转换为 HTTPException
            print(f"ERROR_VALIDATION: 聊天消息数据校验失败: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"消息数据格式不正确: {e}")

        # 6. 使用校验后的数据创建消息记录
        db_message = ChatMessage(
            room_id=room_id,
            sender_id=current_user_id,
            content_text=message_data_validated.content_text,
            message_type=message_data_validated.message_type,
            media_url=message_data_validated.media_url
        )

        db.add(db_message)
        # 更新聊天室的 updated_at，作为最后活跃时间
        db_room.updated_at = func.now()
        db.add(db_room)
        db.flush()  # 刷新以便后续操作可以访问 db_message 的 ID

        # 触发成就检查 (例如，聊天消息发送数量类的成就)
        if db_sender:
            chat_message_points = 1  # 每发送一条聊天消息奖励1积分
            await _award_points(
                db=db,
                user=db_sender,
                amount=chat_message_points,
                reason=f"发送聊天消息：'{message_data_validated.content_text[:20]}...'",
                transaction_type="EARN",
                related_entity_type="chat_message",
                related_entity_id=db_message.id
            )
            await _check_and_award_achievements(db, current_user_id)
            print(
                f"DEBUG_POINTS_ACHIEVEMENT: 用户 {current_user_id} 发送聊天消息，获得 {chat_message_points} 积分并检查成就 (待提交)。")

        db.commit()  # 提交所有
        db.refresh(db_message)

        # 填充 sender_name
        db_message.sender_name = db_sender.name

        print(f"DEBUG: 聊天室 {room_id} 收到消息 (ID: {db_message.id})。")
        return db_message

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_DB: 发送聊天消息发生未知错误: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"发送消息失败: {e}")


@app.get("/chatrooms/{room_id}/messages/", response_model=List[schemas.ChatMessageResponse],
         summary="获取指定聊天室的历史消息")
async def get_chat_messages(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = 50,  # 限制返回消息数量
        offset: int = 0  # 偏移量，用于分页加载
):
    """
    获取指定聊天室的历史消息。
    所有活跃成员 (包括群主和管理员) 以及系统管理员都可以查看。
    """
    print(f"DEBUG: 获取聊天室 {room_id} 的历史消息，用户 {current_user_id}。")

    # 1. 获取当前用户和目标聊天室的信息
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

    db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

    # 2. 权限检查：用户是否是群主、活跃成员或系统管理员**
    is_creator = (db_room.creator_id == current_user_id)
    is_active_member = db.query(ChatRoomMember).filter(
        ChatRoomMember.room_id == room_id,
        ChatRoomMember.member_id == current_user_id,
        ChatRoomMember.status == "active"
    ).first() is not None

    if not (is_creator or is_active_member or current_user.is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您无权查看该聊天室的历史消息。")

    # 3. 查询消息（过滤掉被删除的消息）
    messages = db.query(ChatMessage).filter(
        ChatMessage.room_id == room_id,
        ChatMessage.deleted_at.is_(None)  # 只获取未删除的消息
    ).order_by(ChatMessage.sent_at.asc()) \
        .offset(offset).limit(limit).all()

    # 4. 填充 sender_name
    response_messages = []
    # 预加载所有发送者信息，以避免 N+1 查询问题
    sender_ids = list(set([msg.sender_id for msg in messages]))  # 获取所有不重复的发送者ID
    senders_map = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(sender_ids)).all()}

    for msg in messages:
        msg.sender_name = senders_map.get(msg.sender_id, "未知用户")
        response_messages.append(msg)

    print(f"DEBUG: 聊天室 {room_id} 获取到 {len(messages)} 条历史消息。")
    return response_messages


@app.delete("/chatrooms/{room_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定聊天消息（仅限消息发送者）")
async def delete_chat_message(
        room_id: int,
        message_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定聊天消息。
    只有消息的发送者可以删除自己发送的消息。
    使用软删除，消息在数据库中保留但对所有用户不可见。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试删除聊天室 {room_id} 中的消息 {message_id}。")

    try:
        # 1. 查询要删除的消息
        db_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)  # 只能删除未被删除的消息
        ).first()

        if not db_message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="消息未找到或已被删除。"
            )

        # 2. 权限检查：只有消息的发送者可以删除
        if db_message.sender_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您只能删除自己发送的消息。"
            )

        # 3. 验证用户是否还是聊天室的成员（可选检查）
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 检查用户是否是聊天室成员或群主
        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您不是该聊天室的成员，无法删除消息。"
            )

        # 4. 执行软删除
        from sqlalchemy import func
        db_message.deleted_at = func.now()
        db.add(db_message)
        db.commit()

        print(f"DEBUG: 消息 {message_id} 已被用户 {current_user_id} 成功删除。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 删除聊天消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除聊天消息失败: {e}"
        )


# --- 小论坛 - 话题管理接口 ---
@app.post("/forum/topics/", response_model=schemas.ForumTopicResponse, summary="发布新论坛话题")
async def create_forum_topic(
        topic_data: schemas.ForumTopicBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传图片、视频或文件作为话题的附件"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 话题发布者
        db: Session = Depends(get_db)
):
    """
    发布一个新论坛话题。可选择关联分享平台其他内容，或直接上传文件。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试发布话题: {topic_data.title or '(无标题)'}，有文件：{bool(file)}")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 1. 验证共享内容是否存在 (如果提供了 shared_item_type 和 shared_item_id)
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
            elif topic_data.shared_item_type == "collected_content":  # 支持引用收藏
                model = CollectedContent

            if model:
                shared_item = db.query(model).filter(model.id == topic_data.shared_item_id).first()
                if not shared_item:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                        detail=f"Shared item of type {topic_data.shared_item_type} with ID {topic_data.shared_item_id} not found.")

        # 2. 处理文件上传（如果提供了文件）
        final_media_url = topic_data.media_url
        final_media_type = topic_data.media_type
        final_original_filename = topic_data.original_filename
        final_media_size_bytes = topic_data.media_size_bytes

        if file:
            if final_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            # 根据文件类型确定OSS存储路径前缀
            oss_path_prefix = "forum_files"  # 默认文件
            if content_type.startswith('image/'):
                oss_path_prefix = "forum_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "forum_videos"

            current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=content_type
                )
                final_original_filename = file.filename
                final_media_size_bytes = file_size
                # 确保 media_type 与实际上传的文件类型一致
                if content_type.startswith('image/'):
                    final_media_type = "image"
                elif content_type.startswith('video/'):
                    final_media_type = "video"
                else:
                    final_media_type = "file"

                print(f"DEBUG: 文件 '{file.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_media_url}")

            except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
                print(f"ERROR: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出，让FastAPI处理
            except Exception as e:
                print(f"ERROR: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=f"文件上传到云存储失败: {e}")
        else:  # 没有上传文件，但可能提供了 media_url (例如用户粘贴的外部链接)
            # 验证 media_url 和 media_type 的一致性
            if final_media_url and not final_media_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="media_url 存在时，media_type 不能为空。")
            
            # 如果设置了 media_type 但没有 media_url，且没有上传文件，清空 media_type
            if final_media_type and not final_media_url:
                print(f"DEBUG: 检测到设置了 media_type='{final_media_type}' 但没有 media_url 和上传文件，自动清空 media_type")
                final_media_type = None
                final_original_filename = None
                final_media_size_bytes = None

        # 3. 组合文本用于嵌入
        combined_text = ". ".join(filter(None, [
            _get_text_part(topic_data.title),
            _get_text_part(topic_data.content),
            _get_text_part(topic_data.tags),
            _get_text_part(topic_data.shared_item_type),
            _get_text_part(final_media_url),  # 加入媒体URL
            _get_text_part(final_media_type),  # 加入媒体类型
            _get_text_part(final_original_filename),  # 加入原始文件名
        ])).strip()

        # 获取话题发布者的LLM配置用于嵌入生成
        topic_author = db.query(Student).filter(Student.id == current_user_id).first()
        author_llm_api_key = None
        author_llm_type = None
        author_llm_base_url = None
        author_llm_model_id = None

        if topic_author and topic_author.llm_api_type == "siliconflow" and topic_author.llm_api_key_encrypted:
            try:
                author_llm_api_key = ai_core.decrypt_key(topic_author.llm_api_key_encrypted)
                author_llm_type = topic_author.llm_api_type
                author_llm_base_url = topic_author.llm_api_base_url
                author_llm_model_id = topic_author.llm_model_id
                print(f"DEBUG_EMBEDDING_KEY: 使用话题发布者配置的硅基流动 API 密钥为话题生成嵌入。")
            except Exception as e:
                print(f"ERROR_EMBEDDING_KEY: 解密话题发布者硅基流动 API 密钥失败: {e}。话题嵌入将使用零向量或默认行为。")
                author_llm_api_key = None
        else:
            print(f"DEBUG_EMBEDDING_KEY: 话题发布者未配置硅基流动 API 类型或密钥，话题嵌入将使用零向量或默认行为。")

        embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR  # 默认零向量
        if combined_text:
            try:
                new_embedding = await ai_core.get_embeddings_from_api(
                    [combined_text],
                    api_key=author_llm_api_key,
                    llm_type=author_llm_type,
                    llm_base_url=author_llm_base_url,
                    llm_model_id=author_llm_model_id
                )
                if new_embedding:
                    embedding = new_embedding[0]
                print(f"DEBUG: 话题嵌入向量已生成。")
            except Exception as e:
                print(f"ERROR: 生成话题嵌入向量失败: {e}. 嵌入向量设为零。")
                embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
        else:
            print(f"WARNING: 话题 combined_text 为空，嵌入向量设为零。")

        # 4. 创建数据库记录
        db_topic = ForumTopic(
            owner_id=current_user_id,
            title=topic_data.title,
            content=topic_data.content,
            shared_item_type=topic_data.shared_item_type,
            shared_item_id=topic_data.shared_item_id,
            tags=topic_data.tags,
            media_url=final_media_url,  # 保存最终的媒体URL
            media_type=final_media_type,  # 保存最终的媒体类型
            original_filename=final_original_filename,  # 保存原始文件名
            media_size_bytes=final_media_size_bytes,  # 保存文件大小
            combined_text=combined_text,
            embedding=embedding
        )

        db.add(db_topic)
        db.flush()
        print(f"DEBUG_FLUSH: 话题 {db_topic.id} 已刷新到会话。")

        # 发布话题奖励积分
        if topic_author:
            topic_post_points = 15
            await _award_points(
                db=db,
                user=topic_author,
                amount=topic_post_points,
                reason=f"发布论坛话题：'{db_topic.title or '(无标题)'}'",
                transaction_type="EARN",
                related_entity_type="forum_topic",
                related_entity_id=db_topic.id
            )
            await _check_and_award_achievements(db, current_user_id)
            print(
                f"DEBUG_POINTS_ACHIEVEMENT: 用户 {current_user_id} 发布话题，获得 {topic_post_points} 积分并检查成就 (待提交)。")

        db.commit()
        db.refresh(db_topic)

        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
        db_topic.owner_name = owner_obj.name if owner_obj else "未知用户"
        db_topic.is_liked_by_current_user = False

        print(f"DEBUG: 话题 '{db_topic.title or '(无标题)'}' (ID: {db_topic.id}) 发布成功，所有事务已提交。")
        return db_topic

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_CREATE_TOPIC_GLOBAL: 创建论坛话题失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建论坛话题失败: {e}",
        )


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


# --- 辅助函数：获取项目列表并填充动态信息 ---
async def _get_projects_with_details(query, current_user_id: int, db: Session):
    projects = query.all()
    for project in projects:
        # 填充 creator_name
        creator_obj = db.query(Student).filter(Student.id == project.creator_id).first()
        # 直接为 ORM 对象设置一个私有属性，Pydantic 的 @property 会读取它
        project._creator_name = creator_obj.name if creator_obj else "未知用户"

        # 填充 is_liked_by_current_user
        project.is_liked_by_current_user = False
        if current_user_id:  # 只有登录用户才检查是否点赞
            like = db.query(ProjectLike).filter(
                ProjectLike.owner_id == current_user_id,
                ProjectLike.project_id == project.id
            ).first()
            if like:
                project.is_liked_by_current_user = True
    return projects


# --- 辅助函数：获取课程列表并填充动态信息 ---
async def _get_courses_with_details(query, current_user_id: int, db: Session):
    courses = query.all()
    for course in courses:
        # 填充 is_liked_by_current_user
        course.is_liked_by_current_user = False
        if current_user_id:  # 只有登录用户才检查是否点赞
            like = db.query(CourseLike).filter(
                CourseLike.owner_id == current_user_id,
                CourseLike.course_id == course.id
            ).first()
            if like:
                course.is_liked_by_current_user = True
    return courses


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


# project/main.py

# ... (前面的导入和类定义保持不变) ...

@app.put("/forum/topics/{topic_id}", response_model=schemas.ForumTopicResponse, summary="更新指定论坛话题")
async def update_forum_topic(
        topic_id: int,
        topic_data: schemas.ForumTopicBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传新图片、视频或文件替换旧的"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 只有话题发布者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的论坛话题内容。只有话题发布者能更新。
    支持替换附件文件。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新话题 ID: {topic_id}。有文件: {bool(file)}")
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id, ForumTopic.owner_id == current_user_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found or not authorized.")

    update_dict = topic_data.dict(exclude_unset=True)

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_topic.media_url 中提取旧的 OSS object name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_topic.media_url and db_topic.media_url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_topic.media_url.replace(oss_base_url_parsed, '', 1)

    # 1. 处理共享内容和直接上传媒体的互斥校验
    # 这个逻辑在 schema.py 的 model_validator 里已经处理了，但为了健壮性，这里可以再次检查或确保不覆盖。
    # 理论上如果 update_dict 中同时提供了 shared_item_type 和 media_url，会在 schema 验证阶段就抛错。
    # 所以无需再次手动检查互斥性。

    # Check if media_url or media_type are explicitly being cleared or updated to non-file type
    media_url_being_cleared = "media_url" in update_dict and update_dict["media_url"] is None
    media_type_being_cleared_or_changed_to_null = "media_type" in update_dict and update_dict["media_type"] is None

    # Check if type is changing to non-media type from existing media type
    type_changing_from_media = False
    if "media_type" in update_dict and update_dict["media_type"] != db_topic.media_type:
        if db_topic.media_type in ["image", "video", "file"] and update_dict["media_type"] is None:
            type_changing_from_media = True  # 从有媒体类型变为无媒体类型

    # If media content is being explicitly removed or type changed, delete old OSS file
    if old_media_oss_object_name and (
            media_url_being_cleared or media_type_being_cleared_or_changed_to_null or type_changing_from_media):
        try:
            asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
            print(
                f"DEBUG: Deleted old OSS file {old_media_oss_object_name} due to media content clearance/type change.")
        except Exception as e:
            print(
                f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during media content clearance: {e}")

        # 清空数据库中的相关媒体字段
        db_topic.media_url = None
        db_topic.media_type = None
        db_topic.original_filename = None
        db_topic.media_size_bytes = None

    # 2. 处理文件上传（如果提供了新文件或更新了媒体类型）
    if file:
        target_media_type = update_dict.get("media_type")
        if target_media_type not in ["file", "image", "video"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

        # If an old file existed, delete it (already handled by previous block or if new file is replacing it)
        if old_media_oss_object_name and not media_url_being_cleared and not media_type_being_cleared_or_changed_to_null:
            try:
                # If a new file replaces it, schedule old file deletion.
                # Avoids double deletion if old_media_oss_object_name was already handled by clearance logic.
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(f"DEBUG: Deleted old OSS file: {old_media_oss_object_name} for replacement.")
            except Exception as e:
                print(
                    f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during replacement: {e}")

        file_bytes = await file.read()
        file_extension = os.path.splitext(file.filename)[1]
        content_type = file.content_type
        file_size = file.size

        oss_path_prefix = "forum_files"
        if content_type.startswith('image/'):
            oss_path_prefix = "forum_images"
        elif content_type.startswith('video/'):
            oss_path_prefix = "forum_videos"

        new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

        try:
            db_topic.media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_topic.original_filename = file.filename
            db_topic.media_size_bytes = file_size
            db_topic.media_type = target_media_type  # Use the media_type from request body

            print(f"DEBUG: New file '{file.filename}' uploaded to OSS: {db_topic.media_url}")
        except HTTPException as e:
            print(f"ERROR: Upload new file to OSS failed: {e.detail}")
            raise e
        except Exception as e:
            print(f"ERROR: Unknown error during new file upload to OSS: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传到云存储失败: {e}")

    # 3. 应用其他 update_dict 中的字段
    # 清理掉已通过文件上传或手动处理的 media 字段，防止再次覆盖
    fields_to_skip_manual_update = ["media_url", "media_type", "original_filename", "media_size_bytes", "file"]
    for key, value in update_dict.items():
        if key in fields_to_skip_manual_update:
            continue
        if hasattr(db_topic, key) and value is not None:
            setattr(db_topic, key, value)
        elif hasattr(db_topic, key) and value is None:  # Allow clearing optional fields (except title)
            if key == "title":  # Title is mandatory, cannot be None or empty
                if not value or (isinstance(value, str) and not value.strip()):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="话题标题不能为空。")
            setattr(db_topic, key, value)

    # 4. 重新生成 combined_text 和 embedding
    combined_text = ". ".join(filter(None, [
        _get_text_part(db_topic.title),
        _get_text_part(db_topic.content),
        _get_text_part(db_topic.tags),
        _get_text_part(db_topic.shared_item_type),
        _get_text_part(db_topic.media_url),  # 包含新的媒体URL
        _get_text_part(db_topic.media_type),  # 包含新的媒体类型
        _get_text_part(db_topic.original_filename),  # 包含原始文件名
    ])).strip()

    topic_author = db.query(Student).filter(Student.id == current_user_id).first()
    author_llm_api_key = None
    author_llm_type = None
    author_llm_base_url = None
    author_llm_model_id = None

    if topic_author and topic_author.llm_api_type == "siliconflow" and topic_author.llm_api_key_encrypted:
        try:
            author_llm_api_key = ai_core.decrypt_key(topic_author.llm_api_key_encrypted)
            author_llm_type = topic_author.llm_api_type
            author_llm_base_url = topic_author.llm_api_base_url
            author_llm_model_id = topic_author.llm_model_id
            print(f"DEBUG_EMBEDDING_KEY: 使用话题发布者配置的硅基流动 API 密钥更新话题嵌入。")
        except Exception as e:
            print(f"ERROR_EMBEDDING_KEY: 解密话题发布者硅基流动 API 密钥失败: {e}。话题嵌入将使用零向量或默认行为。")
            author_llm_api_key = None
    else:
        print(f"DEBUG_EMBEDDING_KEY: 话题发布者未配置硅基流动 API 类型或密钥，话题嵌入将使用零向量或默认行为。")

    if combined_text:
        try:
            new_embedding = await ai_core.get_embeddings_from_api(
                [combined_text],
                api_key=author_llm_api_key,
                llm_type=author_llm_type,
                llm_base_url=author_llm_base_url,
                llm_model_id=author_llm_model_id
            )
            if new_embedding:
                db_topic.embedding = new_embedding[0]
            else:
                db_topic.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
            print(f"DEBUG: 话题 {db_topic.id} 嵌入向量已更新。")
        except Exception as e:
            print(f"ERROR: 更新话题 {db_topic.id} 嵌入向量失败: {e}. 嵌入向量设为零。")
            db_topic.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR
    else:
        print(f"WARNING: 话题 combined_text 为空，嵌入向量设为零。")
        db_topic.embedding = ai_core.GLOBAL_PLACEHOLDER_ZERO_VECTOR

    db.add(db_topic)
    try:
        db.commit()
        db.refresh(db_topic)
    except IntegrityError as e:
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: Update DB commit failed, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_DB: 更新话题发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新话题失败，可能存在数据冲突。")
    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: HTTP exception, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        raise e
    except Exception as e:
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(
                f"DEBUG: Unknown error during update, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_UPDATE_TOPIC_GLOBAL: 更新话题失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新话题失败: {e}",
        )


@app.delete("/forum/topics/{topic_id}", summary="删除指定论坛话题")
async def delete_forum_topic(
        topic_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 只有话题发布者能删除
        db: Session = Depends(get_db)
):
    """
    删除指定ID的论坛话题及其所有评论和点赞。如果话题关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    只有话题发布者能删除。
    """
    print(f"DEBUG: 删除话题 ID: {topic_id}。")
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id, ForumTopic.owner_id == current_user_id).first()
    if not db_topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found or not authorized")

    # <<< 新增：如果话题关联了文件或媒体，并且是OSS URL，则尝试从OSS删除文件 >>>
    if db_topic.media_type in ["image", "video", "file"] and db_topic.media_url:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_topic.media_url.replace(oss_base_url_parsed, '', 1) if db_topic.media_url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_FORUM: 删除了话题 {topic_id} 关联的OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_FORUM: 删除话题 {topic_id} 关联的OSS文件 {object_name} 失败: {e}")
                # 即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_FORUM: 话题 {topic_id} 的 media_url ({db_topic.media_url}) 无效或非OSS URL，跳过OSS文件删除。")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_topic)时自动处理所有评论和点赞
    db.delete(db_topic)
    db.commit()
    print(f"DEBUG: 话题 {topic_id} 及其评论点赞和关联文件删除成功。")
    return {"message": "Forum topic and its comments/likes/associated media deleted successfully"}


# --- 小论坛 - 评论管理接口 ---
@app.post("/forum/topics/{topic_id}/comments/", response_model=schemas.ForumCommentResponse,
          summary="为论坛话题添加评论")
async def add_forum_comment(
        topic_id: int,
        comment_data: schemas.ForumCommentBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传图片、视频或文件作为评论的附件"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 评论发布者
        db: Session = Depends(get_db)
):
    """
    为指定论坛话题添加评论。可选择回复某个已有评论（楼中楼），或直接上传文件作为附件。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试为话题 {topic_id} 添加评论。有文件：{bool(file)}")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    oss_object_name_for_rollback = None

    try:
        # 1. 验证话题是否存在
        db_topic = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
        if not db_topic:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")

        # 2. 验证父评论是否存在 (如果提供了 parent_comment_id)
        if comment_data.parent_comment_id:
            parent_comment = db.query(ForumComment).filter(
                ForumComment.id == comment_data.parent_comment_id,
                ForumComment.topic_id == topic_id  # 确保父评论属于同一话题
            ).first()
            if not parent_comment:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                    detail="Parent comment not found in this topic.")

        # 3. 处理文件上传（如果提供了文件）
        final_media_url = comment_data.media_url
        final_media_type = comment_data.media_type
        final_original_filename = comment_data.original_filename
        final_media_size_bytes = comment_data.media_size_bytes

        if file:
            if final_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            # 根据文件类型确定OSS存储路径前缀 (与话题的路径一致，方便管理)
            oss_path_prefix = "forum_files"
            if content_type.startswith('image/'):
                oss_path_prefix = "forum_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "forum_videos"

            current_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"
            oss_object_name_for_rollback = current_oss_object_name  # 记录用于回滚

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=current_oss_object_name,
                    content_type=content_type
                )
                final_original_filename = file.filename
                final_media_size_bytes = file_size
                # 确保 media_type 与实际上传的文件类型一致
                if content_type.startswith('image/'):
                    final_media_type = "image"
                elif content_type.startswith('video/'):
                    final_media_type = "video"
                else:
                    final_media_type = "file"

                print(f"DEBUG: 文件 '{file.filename}' (类型: {content_type}) 上传到OSS成功，URL: {final_media_url}")

            except HTTPException as e:  # oss_utils.upload_file_to_oss 会抛出 HTTPException
                print(f"ERROR: 上传文件到OSS失败: {e.detail}")
                raise e  # 直接重新抛出，让FastAPI处理
            except Exception as e:
                print(f"ERROR: 上传文件到OSS时发生未知错误: {e}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=f"文件上传到云存储失败: {e}")
        else:  # 没有上传文件，但可能提供了 media_url (例如用户粘贴的外部链接)
            # 验证 media_url 和 media_type 的一致性
            if final_media_url and not final_media_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="media_url 存在时，media_type 不能为空。")
            
            # 如果设置了 media_type 但没有 media_url，且没有上传文件，清空 media_type
            if final_media_type and not final_media_url:
                print(f"DEBUG: 检测到设置了 media_type='{final_media_type}' 但没有 media_url 和上传文件，自动清空 media_type")
                final_media_type = None
                final_original_filename = None
                final_media_size_bytes = None

        # 4. 创建评论记录
        db_comment = ForumComment(
            topic_id=topic_id,
            owner_id=current_user_id,
            content=comment_data.content,
            parent_comment_id=comment_data.parent_comment_id,
            media_url=final_media_url,  # 保存最终的媒体URL
            media_type=final_media_type,  # 保存最终的媒体类型
            original_filename=final_original_filename,  # 保存原始文件名
            media_size_bytes=final_media_size_bytes  # 保存文件大小
        )

        db.add(db_comment)
        # 更新话题的评论数 (这是一个在会话中修改的操作，等待最终提交)
        db_topic.comments_count += 1
        db.add(db_topic)  # SQLAlchemy会自动识别这是更新

        # 在检查成就前，强制刷新会话，使 db_comment 和 db_topic 对查询可见！
        db.flush()
        print(f"DEBUG_FLUSH: 评论 {db_comment.id} 和话题 {db_topic.id} 更新已刷新到会话。")

        # 发布评论奖励积分
        comment_author = db.query(Student).filter(Student.id == current_user_id).first()
        if comment_author:
            comment_post_points = 5
            await _award_points(
                db=db,
                user=comment_author,
                amount=comment_post_points,
                reason=f"发布论坛评论：'{db_comment.content[:20]}...'",
                transaction_type="EARN",
                related_entity_type="forum_comment",
                related_entity_id=db_comment.id
            )
            await _check_and_award_achievements(db, current_user_id)
            print(
                f"DEBUG_POINTS_ACHIEVEMENT: 用户 {current_user_id} 发布评论，获得 {comment_post_points} 积分并检查成就 (待提交)。")

        db.commit()  # 现在，这里是唯一也是最终的提交！
        db.refresh(db_comment)  # 提交后刷新db_comment以返回完整对象

        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
        db_comment.owner_name = owner_obj.name  # 访问私有属性以设置
        db_comment.is_liked_by_current_user = False

        print(f"DEBUG: 话题 {db_topic.id} 收到评论 (ID: {db_comment.id})，所有事务已提交。")
        return db_comment

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: HTTP exception, attempting to delete OSS file: {oss_object_name_for_rollback}")
        raise e
    except Exception as e:  # 捕获所有异常并回滚
        db.rollback()
        if oss_object_name_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(oss_object_name_for_rollback))
            print(f"DEBUG: Unknown error, attempting to delete OSS file: {oss_object_name_for_rollback}")
        print(f"ERROR_ADD_COMMENT_GLOBAL: 添加论坛评论失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"添加论坛评论失败: {e}",
        )


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
    ���取指定论坛话题的评论列表。
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
        comment_data: schemas.ForumCommentBase = Depends(),  # 使用 Depends() 允许同时接收 form-data 和 body
        file: Optional[UploadFile] = File(None, description="可选：上传新图片、视频或文件替换旧的"),  # 新增：接收上传文件
        current_user_id: int = Depends(get_current_user_id),  # 只有评论发布者能更新
        db: Session = Depends(get_db)
):
    """
    更新指定ID的论坛评论。只有评论发布者能更新。
    支持替换附件文件。更新后会重新生成 combined_text 和 embedding。
    """
    print(f"DEBUG: 更新评论 ID: {comment_id}。有文件: {bool(file)}")
    db_comment = db.query(ForumComment).filter(ForumComment.id == comment_id,
                                               ForumComment.owner_id == current_user_id).first()
    if not db_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found or not authorized.")

    update_dict = comment_data.dict(exclude_unset=True)

    old_media_oss_object_name = None  # 用于删除旧文件的OSS对象名称
    new_uploaded_oss_object_name = None  # 用于回滚时删除新上传的OSS文件

    # 从现有的 db_comment.media_url 中提取旧的 OSS object name
    oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
    if db_comment.media_url and db_comment.media_url.startswith(oss_base_url_parsed):
        old_media_oss_object_name = db_comment.media_url.replace(oss_base_url_parsed, '', 1)

    try:
        # Check if media_url or media_type are explicitly being cleared or updated to non-media type
        media_url_being_cleared = "media_url" in update_dict and update_dict["media_url"] is None
        media_type_being_set = "media_type" in update_dict
        new_media_type_from_data = update_dict.get("media_type")

        # If old media existed and it's explicitly being cleared, or type changes away from media
        should_delete_old_media_file = False
        if old_media_oss_object_name:
            if media_url_being_cleared:  # media_url is set to None
                should_delete_old_media_file = True
            elif media_type_being_set and new_media_type_from_data is None:  # media_type is set to None
                should_delete_old_media_file = True
            elif media_type_being_set and (
                    new_media_type_from_data not in ["image", "video", "file"]):  # media_type changes to non-media
                should_delete_old_media_file = True

        if should_delete_old_media_file:
            try:
                asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                print(
                    f"DEBUG: Deleted old OSS file {old_media_oss_object_name} due to media content clearance/type change.")
            except Exception as e:
                print(
                    f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during media content clearance: {e}")

            # 清空数据库中的相关媒体字段
            db_comment.media_url = None
            db_comment.media_type = None
            db_comment.original_filename = None
            db_comment.media_size_bytes = None

        # 1. 处理文件上传（如果提供了新文件）
        if file:
            target_media_type = update_dict.get("media_type")
            if target_media_type not in ["file", "image", "video"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="当上传文件时，media_type 必须为 'file', 'image' 或 'video'。")

            # 如果新文件替换了现有文件，且现有文件是OSS上的，则删除它
            if old_media_oss_object_name and not should_delete_old_media_file:  # Avoid double deletion
                try:
                    asyncio.create_task(oss_utils.delete_file_from_oss(old_media_oss_object_name))
                    print(f"DEBUG: Deleted old OSS file: {old_media_oss_object_name} for replacement.")
                except Exception as e:
                    print(
                        f"ERROR: Failed to schedule deletion of old OSS file {old_media_oss_object_name} during replacement: {e}")

            file_bytes = await file.read()
            file_extension = os.path.splitext(file.filename)[1]
            content_type = file.content_type
            file_size = file.size

            oss_path_prefix = "forum_files"
            if content_type.startswith('image/'):
                oss_path_prefix = "forum_images"
            elif content_type.startswith('video/'):
                oss_path_prefix = "forum_videos"

            new_uploaded_oss_object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_extension}"

            # Upload to OSS
            db_comment.media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=new_uploaded_oss_object_name,
                content_type=content_type
            )
            db_comment.original_filename = file.filename
            db_comment.media_size_bytes = file_size
            db_comment.media_type = target_media_type  # Use the media_type from request body

            print(f"DEBUG: New file '{file.filename}' uploaded to OSS: {db_comment.media_url}")

            # Clear text content if this is a file-only comment and content was not provided in update
            if "content" not in update_dict and db_comment.content:
                db_comment.content = None  # If updating with a file, clear existing text content if user didn't specify new text
        elif "media_url" in update_dict and update_dict[
            "media_url"] is not None and not file:  # User provided a new URL but no file
            # If new media_url is provided without a file, it's assumed to be an external URL
            db_comment.media_url = update_dict["media_url"]
            db_comment.media_type = update_dict.get("media_type")  # Should be provided via schema validator
            db_comment.original_filename = None
            db_comment.media_size_bytes = None
            # content is optional in this case

        # 2. 应用其他 update_dict 中的字段
        # 清理掉已通过文件上传或手动处理的 media 字段，防止再次覆盖
        fields_to_skip_manual_update = ["media_url", "media_type", "original_filename", "media_size_bytes", "file"]
        for key, value in update_dict.items():
            if key in fields_to_skip_manual_update:
                continue
            if hasattr(db_comment, key):
                if key == "content":  # Content is mandatory for text-based comments
                    if value is None or (isinstance(value, str) and not value.strip()):
                        # Only raise error if it's a text-based comment. For media-only, content can be null.
                        if db_comment.media_url is None:  # If no media, content must be there
                            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="评论内容不能为空。")
                        else:  # If there's media, content can be cleared
                            setattr(db_comment, key, value)
                    else:  # Content value is not None/empty
                        setattr(db_comment, key, value)
                elif key == "parent_comment_id":  # Cannot change parent_comment_id
                    if value != db_comment.parent_comment_id:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                            detail="Cannot change parent_comment_id of a comment.")
                else:  # For other fields
                    setattr(db_comment, key, value)

        db.add(db_comment)
        db.commit()
        db.refresh(db_comment)

        # 填充 owner_name
        owner_obj = db.query(Student).filter(Student.id == current_user_id).first()
        db_comment.owner_name = owner_obj.name
        db_comment.is_liked_by_current_user = False  # 更新不会像状态一样更改

        print(f"DEBUG: 评论 {db_comment.id} 更新成功。")
        return db_comment

    except HTTPException as e:  # 捕获FastAPI的异常，包括OSS上传时抛出的
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(f"DEBUG: HTTP exception, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        raise e
    except Exception as e:
        db.rollback()
        if new_uploaded_oss_object_name:
            asyncio.create_task(oss_utils.delete_file_from_oss(new_uploaded_oss_object_name))
            print(
                f"DEBUG: Unknown error during update, attempting to delete new OSS file: {new_uploaded_oss_object_name}")
        print(f"ERROR_UPDATE_COMMENT_GLOBAL: 更新评论失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新评论失败: {e}",
        )


@app.delete("/forum/comments/{comment_id}", summary="删除指定论坛评论")
async def delete_forum_comment(
        comment_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 只有评论发布者能删除
        db: Session = Depends(get_db)
):
    """
    删除指定ID的论坛评论。如果评论有子评论，则会级联删除所有回复。
    如果评论关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。
    只有评论发布者能删除。
    """
    print(f"DEBUG: 删除评论 ID: {comment_id}。")
    db_comment = db.query(ForumComment).filter(ForumComment.id == comment_id,
                                               ForumComment.owner_id == current_user_id).first()
    if not db_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found or not authorized")

    # 获取所属话题以便更新 comments_count
    db_topic = db.query(ForumTopic).filter(ForumTopic.id == db_comment.topic_id).first()
    if db_topic:
        # 评论数减少的逻辑应该在实际删除完评论后进行，并且需要考虑级联删除子评论的情况
        # 但在简单的计数器场景下，这里先进行初步减一，或者在钩子中处理会更好。
        # 这里仅为直接评论减一，子评论的删除不会反映在这里。
        db_topic.comments_count -= 1
        db.add(db_topic)

    # <<< 新增：如果评论关联了文件或媒体，并且是OSS URL，则尝试从OSS删除文件 >>>
    if db_comment.media_type in ["image", "video", "file"] and db_comment.media_url:
        oss_base_url_parsed = os.getenv("S3_BASE_URL").rstrip('/') + '/'
        # 从OSS URL中解析出 object_name
        object_name = db_comment.media_url.replace(oss_base_url_parsed, '', 1) if db_comment.media_url.startswith(
            oss_base_url_parsed) else None

        if object_name:
            try:
                await oss_utils.delete_file_from_oss(object_name)
                print(f"DEBUG_FORUM: 删除了评论 {comment_id} 关联的OSS文件: {object_name}")
            except Exception as e:
                print(f"ERROR_FORUM: 删除评论 {comment_id} 关联的OSS文件 {object_name} 失败: {e}")
                # 即使OSS文件删除失败，也应该允许数据库记录被删除
        else:
            print(
                f"WARNING_FORUM: 评论 {comment_id} 的 media_url ({db_comment.media_url}) 无效或非OSS URL，跳过OSS文件删除。")

    # SQLAlchemy的cascade="all, delete-orphan"会在db.delete(db_comment)时自动处理所有子评论和点赞
    db.delete(db_comment)
    db.commit()
    print(f"DEBUG: 评论 {comment_id} 及其子评论点赞和关联文件删除成功。")
    return {"message": "Forum comment and its children/likes/associated media deleted successfully"}


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
    点赞成功后，为被点赞的话题/评论的作者奖励积分，并检查其成就。
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试点赞。")
    try:  # 将整个接口逻辑包裹在一个 try 块中，统一提交
        topic_id = like_data.get("topic_id")
        comment_id = like_data.get("comment_id")

        if not topic_id and not comment_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Either topic_id or comment_id must be provided.")
        if topic_id and comment_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Only one of topic_id or comment_id can be provided.")

        existing_like = None
        target_item_owner_id = None
        related_entity_type = None
        related_entity_id = None

        if topic_id:
            existing_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                                       ForumLike.topic_id == topic_id).first()
            if not existing_like:
                target_item = db.query(ForumTopic).filter(ForumTopic.id == topic_id).first()
                if not target_item:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum topic not found.")
                target_item.likes_count += 1
                db.add(target_item)  # 在会话中更新点赞数
                target_item_owner_id = target_item.owner_id  # 获取话题作者ID
                related_entity_type = "forum_topic"
                related_entity_id = topic_id
        elif comment_id:
            existing_like = db.query(ForumLike).filter(ForumLike.owner_id == current_user_id,
                                                       ForumLike.comment_id == comment_id).first()
            if not existing_like:
                target_item = db.query(ForumComment).filter(ForumComment.id == comment_id).first()
                if not target_item:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forum comment not found.")
                target_item.likes_count += 1
                db.add(target_item)  # 在会话中更新点赞数
                target_item_owner_id = target_item.owner_id  # 获取评论作者ID
                related_entity_type = "forum_comment"
                related_entity_id = comment_id

        if existing_like:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already liked this item.")

        db_like = ForumLike(
            owner_id=current_user_id,
            topic_id=topic_id,
            comment_id=comment_id
        )

        db.add(db_like)  # 将点赞记录添加到会话

        # 在检查成就前，强制刷新会话，使 db_like 和 target_item 对查询可见
        db.flush()  # 确保点赞记录和被点赞项的更新已刷新到数据库会话，供 _check_and_award_achievements 查询
        print(f"DEBUG_FLUSH: 点赞记录 {db_like.id} 和被点赞项更新已刷新到会话。")

        # 为被点赞的作者奖励积分和检查成就
        if target_item_owner_id and target_item_owner_id != current_user_id:  # 奖励积分，但不能点赞自己给自己加分
            owner_user = db.query(Student).filter(Student.id == target_item_owner_id).first()
            if owner_user:
                like_points = 5
                await _award_points(
                    db=db,
                    user=owner_user,
                    amount=like_points,
                    reason=f"获得点赞：{target_item.title if topic_id else target_item.content[:20]}...",
                    transaction_type="EARN",
                    related_entity_type=related_entity_type,
                    related_entity_id=related_entity_id
                )
                await _check_and_award_achievements(db, target_item_owner_id)
                print(
                    f"DEBUG_POINTS_ACHIEVEMENT: 用户 {target_item_owner_id} 因获得点赞奖励 {like_points} 积分并检查成就 (待提交)。")

        db.commit()  # 这里是唯一也是最终的提交
        db.refresh(db_like)  # 提交后刷新db_like以返回完整对象

        print(
            f"DEBUG: 用户 {current_user_id} 点赞成功 (Topic ID: {topic_id or 'N/A'}, Comment ID: {comment_id or 'N/A'})。所有事务已提交。")
        return db_like

    except Exception as e:  # 捕获所有异常并回滚
        db.rollback()
        print(f"ERROR_LIKE_FORUM_GLOBAL: 点赞失败，事务已回滚: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"点赞失败: {e}",
        )


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


# --- Project Like/Unlike Interfaces ---
@app.post("/projects/{project_id}/like", response_model=schemas.ProjectLikeResponse, summary="点赞指定项目")
async def like_project_item(
        project_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 点赞者
        db: Session = Depends(get_db)
):
    """
    点赞一个项目。同一用户不能重复点赞同一项目。\n
    点赞成功后，为被点赞项目的创建者奖励积分。
    """
    print(f"DEBUG_LIKE: 用户 {current_user_id} 尝试点赞项目 ID: {project_id}")
    try:
        # 1. 验证项目是否存在
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if not db_project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目未找到。")

        # 2. 检查是否已点赞
        existing_like = db.query(ProjectLike).filter(
            ProjectLike.owner_id == current_user_id,
            ProjectLike.project_id == project_id
        ).first()
        if existing_like:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已点赞该项目。")

        # 3. 创建点赞记录
        db_like = ProjectLike(
            owner_id=current_user_id,
            project_id=project_id
        )
        db.add(db_like)

        # 4. 更新项目点赞计数
        db_project.likes_count += 1
        db.add(db_project)

        # 5. 奖励积分和检查成就 (请将 current_user_id 替换为被点赞项目的创建者 ID)
        project_creator_id = db_project.creator_id
        if project_creator_id and project_creator_id != current_user_id:  # 只有被点赞的不是自己才加分
            creator_user = db.query(Student).filter(Student.id == project_creator_id).first()
            if creator_user:
                like_points = 5
                await _award_points(
                    db=db,
                    user=creator_user,
                    amount=like_points,
                    reason=f"项目获得点赞：'{db_project.title}'",
                    transaction_type="EARN",
                    related_entity_type="project",
                    related_entity_id=project_id
                )
                await _check_and_award_achievements(db, project_creator_id)
                print(
                    f"DEBUG_POINTS_ACHIEVEMENT: 用户 {project_creator_id} 因项目获得点赞奖励 {like_points} 积分并检查成就 (待提交)。")

        db.commit()  # 统一提交所有操作
        db.refresh(db_like)

        print(f"DEBUG_LIKE: 用户 {current_user_id} 点赞项目 {project_id} 成功。")
        return db_like

    except Exception as e:
        db.rollback()
        print(f"ERROR_LIKE: 项目点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"项目点赞失败: {e}")


@app.delete("/projects/{project_id}/unlike", status_code=status.HTTP_204_NO_CONTENT, summary="取消点赞指定项目")
async def unlike_project_item(
        project_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 取消点赞者
        db: Session = Depends(get_db)
):
    """
    取消点赞一个项目。
    """
    print(f"DEBUG_UNLIKE: 用户 {current_user_id} 尝试取消点赞项目 ID: {project_id}")
    try:
        # 1. 查找点赞记录
        db_like = db.query(ProjectLike).filter(
            ProjectLike.owner_id == current_user_id,
            ProjectLike.project_id == project_id
        ).first()

        if not db_like:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到您对该项目的点赞记录。")

        # 2. 更新项目点赞计数
        db_project = db.query(Project).filter(Project.id == project_id).first()
        if db_project and db_project.likes_count > 0:
            db_project.likes_count -= 1
            db.add(db_project)

        # 3. 删除点赞记录
        db.delete(db_like)
        db.commit()

        print(f"DEBUG_UNLIKE: 用户 {current_user_id} 取消点赞项目 {project_id} 成功。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        db.rollback()
        print(f"ERROR_UNLIKE: 取消项目点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"取消项目点赞失败: {e}")


# --- NEW: Course Like/Unlike Interfaces ---
@app.post("/courses/{course_id}/like", response_model=schemas.CourseLikeResponse, summary="点赞指定课程")
async def like_course_item(
        course_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 点赞者
        db: Session = Depends(get_db)
):
    """
    点赞一个课程。同一用户不能重复点赞同一课程。\n
    点赞成功后，为被点赞课程的讲师奖励积分。
    """
    print(f"DEBUG_LIKE: 用户 {current_user_id} 尝试点赞课程 ID: {course_id}")
    try:
        # 1. 验证课程是否存在
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if not db_course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="课程未找到。")

        # 2. 检查是否已点赞
        existing_like = db.query(CourseLike).filter(
            CourseLike.owner_id == current_user_id,
            CourseLike.course_id == course_id
        ).first()
        if existing_like:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已点赞该课程。")

        # 3. 创建点赞记录
        db_like = CourseLike(
            owner_id=current_user_id,
            course_id=course_id
        )
        db.add(db_like)

        # 4. 更新课程点赞计数
        db_course.likes_count += 1
        db.add(db_course)

        # 5. 奖励积分和检查成就 (为课程的讲师奖励积分)
        # 暂时没有讲师的 Student ID，如果讲师不是平台用户，则无法奖励积分。
        # 如果 Instructor 是平台用户，需要额外逻辑来查找其 ID。
        # 这里假设 Instructor 只是一个名字，不直接关联到 Student 表。
        # 如果需要奖励，需要将 Instructor 也关联到 Student 表。
        # 为了简化，这里先不给课程讲师或创建者加积分，或者仅在讲师是平台注册用户时进行。
        print(f"DEBUG_POINTS_ACHIEVEMENT: 课程点赞不直接奖励积分给讲师，除非讲师是平台注册用户且有相应逻辑支持。")

        db.commit()  # 统一提交所有操作
        db.refresh(db_like)

        print(f"DEBUG_LIKE: 用户 {current_user_id} 点赞课程 {course_id} 成功。")
        return db_like

    except Exception as e:
        db.rollback()
        print(f"ERROR_LIKE: 课程点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"课程点赞失败: {e}")


@app.delete("/courses/{course_id}/unlike", status_code=status.HTTP_204_NO_CONTENT, summary="取消点赞指定课程")
async def unlike_course_item(
        course_id: int,
        current_user_id: int = Depends(get_current_user_id),  # 取消点赞者
        db: Session = Depends(get_db)
):
    """
    取消点赞一个课程。
    """
    print(f"DEBUG_UNLIKE: 用户 {current_user_id} 尝试取消点赞课程 ID: {course_id}")
    try:
        # 1. 查找点赞记录
        db_like = db.query(CourseLike).filter(
            CourseLike.owner_id == current_user_id,
            CourseLike.course_id == course_id
        ).first()

        if not db_like:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到您对该课程的点赞记录。")

        # 2. 更新课程点赞计数
        db_course = db.query(Course).filter(Course.id == course_id).first()
        if db_course and db_course.likes_count > 0:
            db_course.likes_count -= 1
            db.add(db_course)

        # 3. 删除点赞记录
        db.delete(db_like)
        db.commit()

        print(f"DEBUG_UNLIKE: 用户 {current_user_id} 取消点赞课程 {course_id} 成功。")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        db.rollback()
        print(f"ERROR_UNLIKE: 取消课程点赞失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"取消课程点赞失败: {e}")


# --- MCP服务配置管理接口 ---
@app.post("/mcp-configs/", response_model=schemas.UserMcpConfigResponse, summary="创建新的MCP配置")
async def create_mcp_config(
        config_data: schemas.UserMcpConfigCreate,
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试创建MCP配置: {config_data.name}")

    encrypted_key = None
    if config_data.api_key:
        encrypted_key = ai_core.encrypt_key(config_data.api_key)

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
        'created_at': db_config.created_at,
        'updated_at': db_config.updated_at,
        'api_key_encrypted': None  # 明确设置为None
    }

    print(f"DEBUG: 用户 {current_user_id} 的MCP配置 '{db_config.name}' (ID: {db_config.id}) 创建成功。")
    return schemas.UserMcpConfigResponse(**response_dict)


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
            'created_at': config.created_at,
            'updated_at': config.updated_at,
            'api_key_encrypted': None  # 明确设置为None，确保不泄露
        }
        result_configs.append(schemas.UserMcpConfigResponse(**config_dict))

    print(f"DEBUG: 获取到 {len(result_configs)} 条MCP配置。")
    return result_configs


# 用户MCP配置接口部分
@app.put("/mcp-configs/{config_id}", response_model=schemas.UserMcpConfigResponse, summary="更新指定MCP配置")
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
            db_config.api_key_encrypted = ai_core.encrypt_key(update_data["api_key"])
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
        'created_at': db_config.created_at,
        'updated_at': db_config.updated_at,
        'api_key_encrypted': None  # 明确设置为None
    }

    print(f"DEBUG: MCP配置 {db_config.id} 更新成功。")
    return schemas.UserMcpConfigResponse(**response_dict)


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
                output_schema={"type": "string", "description": "文本摘要��果"}
            ))

    print(f"DEBUG: 找到 {len(available_tools)} 个可用的MCP工具。")
    return available_tools


# --- WebSocket 聊天室接口 --
@app.websocket("/ws/chat/{room_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        room_id: int,
        token: str = Query(..., description="用户JWT认证令牌"),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_WS: 尝试连接房间 {room_id}。")
    current_email = None
    current_payload_sub_str = None  # 用于存储从 JWT 'sub' 出来的字符串
    current_user_db = None
    try:
        # 解码 JWT 令牌以获取用户身份
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 从 'sub' 获取的是用户ID的字符串表示
        current_payload_sub_str: str = payload.get("sub")
        if current_payload_sub_str is None:
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION,
                                      reason="Invalid authentication token (subject missing).")

        # 将字符串ID转换为整数，然后用它查询用户
        # 假设 sub 字段存储的是用户ID
        try:
            current_user_id_int = int(current_payload_sub_str)
        except ValueError:
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid user ID format in token.")

        # 从数据库中根据用户 ID 获取用户信息
        current_user_db = db.query(Student).filter(Student.id == current_user_id_int).first()
        if current_user_db is None:
            # 这通常不应该发生，除非数据库用户被删除了
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="User not found in database.")

        # 为了调试打印，获取用户的真实邮箱，虽然不用于认证
        current_email = current_user_db.email

    # 将 jwt.PyJWTError 改为 JWTError
    except (JWTError, WebSocketDisconnect) as auth_error:
        # 捕获 JWT 解析错误和主动抛出的 WebSocketDisconnect
        print(f"ERROR_WS_AUTH: WebSocket 认证失败: {type(auth_error).__name__}: {auth_error}")  # 打印错误类型
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"Authentication failed: {auth_error}")
        return
    except Exception as e:
        # 捕获其他非预期的认证异常
        print(f"ERROR_WS_AUTH: WebSocket 认证内部错误: {type(e).__name__}: {e}")  # 打印错误类型
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Authentication internal error.")
        return

    print(f"DEBUG_WS: 用户 {current_user_id_int} (邮箱: {current_email}) 尝试连接聊天室 {room_id}。")

    chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not chat_room:
        print(f"WARNING_WS: 用户 {current_user_id_int} 尝试连接不存在的聊天室 {room_id}。")
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA, reason="聊天室不存在。")
        return

    # 调试打印：查看权限相关的原始值和比较结果
    print(
        f"DEBUG_PERM_WS: current_user_id_int={current_user_id_int} (type={type(current_user_id_int)}), chat_room.creator_id={chat_room.creator_id} (type={type(chat_room.creator_id)})")

    # 核心权限：验证用户是否为该聊天室的创建者或活跃成员
    is_creator = (chat_room.creator_id == current_user_id_int)
    is_active_member = db.query(ChatRoomMember).filter(
        ChatRoomMember.room_id == room_id,
        ChatRoomMember.member_id == current_user_id_int,
        ChatRoomMember.status == "active"
    ).first() is not None

    print(f"DEBUG_PERM_WS: is_creator={is_creator}, is_active_member={is_active_member}")
    print(f"DEBUG_PERM_WS: Final WS permission: {is_creator or is_active_member}")

    if not (is_creator or is_active_member):
        print(f"WARNING_WS: 用户 {current_user_id_int} 无权连接聊天室 {room_id}。")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="您无权访问或加入此聊天室。")
        return

    try:
        await manager.connect(websocket, room_id, current_user_id_int)
        print(f"DEBUG_WS: 用户 {current_user_id_int} 已成功连接到聊天室 {room_id}。")

        # 发送欢迎消息给新连接的用户
        await manager.send_personal_message(
            json.dumps({"type": "status", "content": f"欢迎用户 {current_user_db.name} 加入聊天室 {chat_room.name}！"}),
            websocket)

        while True:
            # 接收 JSON 格式消息 (假设前端发送 {"content": "..."} 类型)
            data = await websocket.receive_json()
            message_content = data.get("content")

            if not message_content or not isinstance(message_content, str):
                await websocket.send_json({"error": "Invalid message format. 'content' (string) is required."})
                continue

            # 再次检查权限 (防止在连接期间权限被撤销)
            re_check_active_member = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == room_id,
                ChatRoomMember.member_id == current_user_id_int,
                ChatRoomMember.status == "active"
            ).first()
            re_check_creator = (chat_room.creator_id == current_user_id_int)

            if not (re_check_creator or re_check_active_member):
                print(f"WARNING_WS: 用户 {current_user_id_int} 在聊天室 {room_id} 发送消息时已失去��限。连接将被关闭。")
                await websocket.send_json(
                    {"error": "No permission to send messages. You may have been removed or left the chat."})
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="失去发送消息权限。")
                break  # 用户无权发送，断开循环

            db_message = ChatMessage(
                room_id=room_id,
                sender_id=current_user_id_int,
                content_text=message_content,
                message_type="text"  # 默认为文本
            )
            db.add(db_message)
            db.commit()  # 立即提交
            db.refresh(db_message)  # 刷新以获取ID和时间戳

            # 广播包含发送者名称和时间戳的 JSON 消息
            message_to_broadcast = {
                "type": "chat_message",
                "id": db_message.id,
                "room_id": room_id,
                "sender_id": current_user_id_int,
                "sender_name": current_user_db.name,  # 直接使用已获取的用户名
                "content": message_content,
                "sent_at": db_message.sent_at.isoformat()  # ISO 8601 格式
            }
            await manager.broadcast(json.dumps(message_to_broadcast), room_id)
            print(f"DEBUG_WS: 聊天室 {room_id} 广播消息: {current_user_db.name}: {message_content[:50]}...")

    except WebSocketDisconnect:
        # 用户正常断开连接（或服务器主动关闭）
        print(f"DEBUG_WS: 用户 {current_user_id_int} 从聊天室 {room_id} 断开连接 (WebSocketDisconnect)。")
    except Exception as e:
        # 捕获其他意外错误
        print(f"ERROR_WS: 用户 {current_user_id_int} 在聊天室 {room_id} WebSocket 处理异常: {e}")
        # 如果连接仍然开启，尝试发送错误消息并关闭
        if websocket.client_state == 1:  # WebSocketState.CONNECTED
            await websocket.send_json({"error": f"服务器内部错误: {e}"})
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason=f"服务器内部错误: {e}")
    finally:
        # 确保在任何情况下都从管理器中移除连接
        if current_user_id_int is not None:
            manager.disconnect(room_id, current_user_id_int)


# --- 成就定义管理接口 (管理员专用) ---
@app.post("/admin/achievements/definitions", response_model=AchievementResponse, summary="【管理员专用】创建新的成就定义")
async def create_achievement_definition(
        achievement_data: AchievementCreate,
        # 只有管理员才能访问此接口
        current_admin_user: Student = Depends(is_admin_user),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 尝试创建成就：{achievement_data.name}")

    # 检查成就名称是否已存在
    existing_achievement = db.query(Achievement).filter(Achievement.name == achievement_data.name).first()
    if existing_achievement:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"成就名称 '{achievement_data.name}' 已存在。")

    new_achievement = Achievement(
        name=achievement_data.name,
        description=achievement_data.description,
        criteria_type=achievement_data.criteria_type,
        criteria_value=achievement_data.criteria_value,
        badge_url=achievement_data.badge_url,
        reward_points=achievement_data.reward_points,
        is_active=achievement_data.is_active
    )

    db.add(new_achievement)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 创建成就定义发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="创建成就定义失败，可能存在名称冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 创建成就定义失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"创建成就定义失败: {e}")

    db.refresh(new_achievement)
    print(
        f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 成功创建成就：{new_achievement.name} (ID: {new_achievement.id})")
    return new_achievement


@app.get("/achievements/definitions", response_model=List[AchievementResponse],
         summary="获取所有成就定义（可供所有用户查看）")
async def get_all_achievement_definitions(
        db: Session = Depends(get_db),
        is_active: Optional[bool] = None,  # 过滤条件：只获取启用或禁用的成就
        criteria_type: Optional[str] = None  # 过滤条件：按类型过滤
):
    """
    获取平台所有成就的定义列表。非管理员用户也可访问此接口以了解成就体系。
    可选择按激活状态和条件类型过滤。
    """
    print("DEBUG_ACHIEVEMENT: 获取所有成就定义。")
    query = db.query(Achievement)

    if is_active is not None:
        query = query.filter(Achievement.is_active == is_active)
    if criteria_type:
        query = query.filter(Achievement.criteria_type == criteria_type)

    achievements = query.order_by(Achievement.name).all()
    print(f"DEBUG_ACHIEVEMENT: 获取到 {len(achievements)} 条成就定义。")
    return achievements


@app.get("/achievements/definitions/{achievement_id}", response_model=AchievementResponse,
         summary="获取指定成就定义详情")
async def get_achievement_definition_by_id(
        achievement_id: int,
        db: Session = Depends(get_db)
):
    """
    获取指定ID的成就定义详情。非管理员用户也可访问。
    """
    print(f"DEBUG_ACHIEVEMENT: 获取成就定义 ID: {achievement_id} 的详情。")
    achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成就定义未找到。")
    return achievement


@app.put("/admin/achievements/definitions/{achievement_id}", response_model=AchievementResponse,
         summary="【管理员专用】更新指定成就定义")
async def update_achievement_definition(
        achievement_id: int,
        achievement_data: AchievementUpdate,
        current_admin_user: Student = Depends(is_admin_user),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 尝试更新成就 ID: {achievement_id}")

    db_achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not db_achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成就定义未找到。")

    update_data = achievement_data.dict(exclude_unset=True)

    # 如果尝试改变名称，检查新名称是否冲突
    if "name" in update_data and update_data["name"] is not None and update_data["name"] != db_achievement.name:
        existing_name_achievement = db.query(Achievement).filter(
            Achievement.name == update_data["name"],
            Achievement.id != achievement_id
        ).first()
        if existing_name_achievement:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"成就名称 '{update_data['name']}' 已被使用。")

    for key, value in update_data.items():
        setattr(db_achievement, key, value)

    db.add(db_achievement)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 更新成就定义发生完整性约束错误: {e}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="更新成就定义失败，可能存在名称冲突。")
    except Exception as e:
        db.rollback()
        print(f"ERROR: 更新成就定义失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新成就定义失败: {e}")

    db.refresh(db_achievement)
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 成功更新成就 ID: {achievement_id}.")
    return db_achievement


@app.delete("/admin/achievements/definitions/{achievement_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="【管理员专用】删除指定成就定义")
async def delete_achievement_definition(
        achievement_id: int,
        current_admin_user: Student = Depends(is_admin_user),
        db: Session = Depends(get_db)
):
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 尝试删除成就 ID: {achievement_id}")

    db_achievement = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not db_achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成就定义未找到。")

    # 删除成就定义也将删除所有用户获得的该成就记录 (UserAchievement)
    # 如果希望保留用户获得的成就记录但禁用成就，应使用 PUT 接口将 is_active 设为 False
    db.delete(db_achievement)
    db.commit()
    print(f"DEBUG_ADMIN_ACHIEVEMENT: 管理员 {current_admin_user.id} 成功删除成就 ID: {achievement_id}。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- 用户积分和成就查询接口 ---
@app.get("/users/me/points", response_model=schemas.StudentResponse, summary="获取当前用户积分余额和上次登录时间")
async def get_my_points_and_login_status(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取当前用户总积分余额和上次登录时间。
    """
    print(f"DEBUG_POINTS_QUERY: 获取用户 {current_user_id} 的积分信息。")
    user = db.query(Student).filter(Student.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户未找到。")
    return user  # StudentResponse 会自动包含 total_points 和 last_login_at


@app.get("/users/me/points/history", response_model=List[PointTransactionResponse], summary="获取当前用户积分交易历史")
async def get_my_points_history(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        transaction_type: Optional[Literal["EARN", "CONSUME", "ADMIN_ADJUST"]] = None,
        limit: int = 20,
        offset: int = 0
):
    """
    获取当前用户的积分交易历史记录。
    可按交易类型过滤，并支持分页。
    """
    print(f"DEBUG_POINTS_QUERY: 获取用户 {current_user_id} 的积分历史。")
    query = db.query(PointTransaction).filter(PointTransaction.user_id == current_user_id)

    if transaction_type:
        query = query.filter(PointTransaction.transaction_type == transaction_type)

    transactions = query.order_by(PointTransaction.created_at.desc()).offset(offset).limit(limit).all()
    print(f"DEBUG_POINTS_QUERY: 获取到 {len(transactions)} 条积分交易记录。")
    return transactions


@app.get("/users/me/achievements", response_model=List[UserAchievementResponse], summary="获取当前用户已获得的成就列表")
async def get_my_achievements(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取当前用户已获得的成就列表，包含成就的详细元数据。
    """
    print(f"DEBUG_ACHIEVEMENT_QUERY: 获取用户 {current_user_id} 的已获得成就列表。")
    # 使用 joinedload 预加载关联的 Achievement 对象，避免 N+1 查询问题
    user_achievements = db.query(UserAchievement).options(
        joinedload(UserAchievement.achievement)  # 预加载成就定义
    ).filter(UserAchievement.user_id == current_user_id).all()

    # 填充 UserAchievementResponse 中的成就详情字段
    response_list = []
    for ua in user_achievements:
        response_data = UserAchievementResponse(
            id=ua.id,
            user_id=ua.user_id,
            achievement_id=ua.achievement_id,
            earned_at=ua.earned_at,
            is_notified=ua.is_notified,
            # 从关联的 achievement 对象中获取数据
            achievement_name=ua.achievement.name if ua.achievement else None,
            achievement_description=ua.achievement.description if ua.achievement else None,
            badge_url=ua.achievement.badge_url if ua.achievement else None,
            reward_points=ua.achievement.reward_points if ua.achievement else 0
        )
        response_list.append(response_data)

    print(f"DEBUG_ACHIEVEMENT_QUERY: 用户 {current_user_id} 获取到 {len(response_list)} 个成就。")
    return response_list


@app.post("/admin/points/reward", response_model=PointTransactionResponse,
          summary="【管理员专用】为指定用户手动发放/扣除积分")
async def admin_reward_or_deduct_points(
        reward_request: PointsRewardRequest,  # 接收积分变动请求
        current_admin_user: Student = Depends(is_admin_user),  # 只有管理员能操作
        db: Session = Depends(get_db)
):
    """
    管理员可以手动为指定用户发放或扣除积分。
    """
    print(
        f"DEBUG_ADMIN_POINTS: 管理员 {current_admin_user.id} 尝试为用户 {reward_request.user_id} 手动调整积分：{reward_request.amount}")

    target_user = db.query(Student).filter(Student.id == reward_request.user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标用户未找到。")

    # 调用积分奖励辅助函数
    await _award_points(
        db=db,
        user=target_user,
        amount=reward_request.amount,
        reason=reward_request.reason or f"管理员手动调整 (由{current_admin_user.username})",
        transaction_type=reward_request.transaction_type,
        related_entity_type=reward_request.related_entity_type,
        related_entity_id=reward_request.related_entity_id
    )
    # 刷新并获取最新的交易记录（或直接返回 _award_points 生成的 transaction 对象）
    # 这里为了返回 PointsRewardRequest 的响应类型，通常需要重新查询或构建
    # 假设 _award_points 内部会commit并生成事务对象，这里查询最新的那个
    latest_transaction = db.query(PointTransaction).filter(
        PointTransaction.user_id == target_user.id
    ).order_by(PointTransaction.created_at.desc()).first()

    print(f"DEBUG_ADMIN_POINTS: 管理员 {current_admin_user.id} 成功调整用户 {target_user.id} 积分。")
    return latest_transaction  # 返回最新的交易记录