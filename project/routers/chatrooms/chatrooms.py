# project/routers/chatrooms/chatrooms.py
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query, File, UploadFile, Form, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal, Union
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, desc
from jose import JWTError, jwt
import uuid, os, asyncio, json, mimetypes, base64, hashlib
from datetime import datetime, timedelta
import io

# 可选的 magic 导入 (在 Windows 上可能有问题)
try:
    import magic
except ImportError:
    magic = None

# 导入数据库和模型
from project.database import get_db
from project.models import Student, Project, Course, ChatRoom, ChatMessage, ChatRoomMember, ChatRoomJoinRequest, Achievement, UserAchievement, PointTransaction
from project.dependencies.dependencies import get_current_user_id, SECRET_KEY, ALGORITHM
import project.schemas.schemas as schemas
import project.oss_utils as oss_utils

# 安全配置常量
class SecurityConfig:
    """安全配置类"""
    # 文件大小限制 (MB)
    MAX_FILE_SIZE_MB = {
        'image': 10,      # 图片最大10MB
        'video': 100,     # 视频最大100MB
        'audio': 50,      # 音频最大50MB
        'document': 20,   # 文档最大20MB
        'general': 20     # 通用文件最大20MB
    }
    
    # 文件过期策略 (天)
    FILE_EXPIRY_DAYS = {
        'temp_files': 7,      # 临时文件7天
        'chat_media': 365,    # 聊天媒体文件1年
        'documents': 1095,    # 文档3年
        'system_files': -1    # 系统文件永不过期
    }
    
    # 允许的文件类型
    ALLOWED_MIME_TYPES = {
        'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'],
        'video': ['video/mp4', 'video/avi', 'video/mov', 'video/wmv', 'video/flv', 'video/mkv', 'video/webm'],
        'audio': ['audio/mpeg', 'audio/wav', 'audio/m4a', 'audio/aac', 'audio/ogg', 'audio/webm'],
        'document': [
            'text/plain', 'text/markdown', 'text/html', 'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'text/x-python', 'application/javascript', 'application/json',
            'application/xml', 'text/csv', 'application/zip', 'application/x-rar-compressed'
        ]
    }
    
    # 恶意文件扫描规则
    MALICIOUS_PATTERNS = [
        b'<%eval', b'<script', b'javascript:', b'vbscript:', b'onload=', b'onerror=',
        b'<?php', b'<%', b'<jsp:', b'exec(', b'system(', b'shell_exec(',
        b'\x4d\x5a\x90\x00',  # PE executable header
        b'\x50\x4b\x03\x04',  # ZIP header (可能包含恶意脚本)
    ]
    
    # 消息分页限制
    MAX_MESSAGES_PER_PAGE = 100
    DEFAULT_MESSAGES_PER_PAGE = 50
    
    # WebSocket连接限制
    MAX_CONNECTIONS_PER_USER = 5
    HEARTBEAT_INTERVAL = 30  # 秒
    
    # 权限控制
    MESSAGE_RECALL_TIME_LIMIT = 120  # 消息撤回时间限制(秒)
    PIN_MESSAGE_LIMIT = 10           # 每个聊天室最多置顶消息数

# 创建路由器
router = APIRouter(
    tags=["聊天室管理"],
    responses={404: {"description": "Not found"}},
)

# --- 安全工具函数 ---
async def validate_file_security(file_content: bytes, filename: str, content_type: str) -> bool:
    """
    验证文件安全性，检查文件大小、类型和恶意内容
    """
    # 1. 文件大小检查
    file_size_mb = len(file_content) / (1024 * 1024)
    
    # 根据文件类型确定大小限制
    if content_type.startswith('image/'):
        max_size = SecurityConfig.MAX_FILE_SIZE_MB['image']
    elif content_type.startswith('video/'):
        max_size = SecurityConfig.MAX_FILE_SIZE_MB['video']
    elif content_type.startswith('audio/'):
        max_size = SecurityConfig.MAX_FILE_SIZE_MB['audio']
    elif content_type in SecurityConfig.ALLOWED_MIME_TYPES['document']:
        max_size = SecurityConfig.MAX_FILE_SIZE_MB['document']
    else:
        max_size = SecurityConfig.MAX_FILE_SIZE_MB['general']
    
    if file_size_mb > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件大小 {file_size_mb:.2f}MB 超过限制 {max_size}MB"
        )
    
    # 2. MIME类型验证
    allowed_types = []
    for category, types in SecurityConfig.ALLOWED_MIME_TYPES.items():
        allowed_types.extend(types)
    
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支持的文件类型: {content_type}"
        )
    
    # 3. 文件内容恶意扫描
    for pattern in SecurityConfig.MALICIOUS_PATTERNS:
        if pattern in file_content[:1024]:  # 只检查前1KB内容
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="检测到潜在恶意文件内容"
            )
    
    # 4. 文件扩展名验证
    file_ext = os.path.splitext(filename)[1].lower()
    dangerous_extensions = ['.exe', '.bat', '.cmd', '.scr', '.vbs', '.js', '.jar', '.app']
    if file_ext in dangerous_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"危险的文件扩展名: {file_ext}"
        )
    
    return True

async def generate_secure_filename(original_filename: str, user_id: int) -> str:
    """
    生成安全的文件名，防止目录遍历攻击
    """
    # 获取文件扩展名
    file_ext = os.path.splitext(original_filename)[1].lower()
    
    # 生成安全的UUID文件名
    safe_uuid = str(uuid.uuid4())
    timestamp = int(datetime.now().timestamp())
    
    # 添加用户ID和时间戳来增强唯一性
    secure_name = f"{user_id}_{timestamp}_{safe_uuid}{file_ext}"
    
    return secure_name

async def cleanup_expired_files(db: Session):
    """
    清理过期文件的后台任务
    """
    try:
        # 获取过期的聊天消息文件
        expired_threshold = datetime.now() - timedelta(days=SecurityConfig.FILE_EXPIRY_DAYS['chat_media'])
        
        expired_messages = db.query(ChatMessage).filter(
            ChatMessage.sent_at < expired_threshold,
            ChatMessage.media_url.isnot(None),
            ChatMessage.deleted_at.is_(None)
        ).all()
        
        deleted_count = 0
        for message in expired_messages:
            if message.media_url:
                # 从OSS删除文件
                try:
                    object_name = message.media_url.split('/')[-1]
                    await oss_utils.delete_file_from_oss(object_name)
                    deleted_count += 1
                except Exception as e:
                    print(f"WARNING: 删除过期文件失败: {object_name}, 错误: {e}")
                
                # 清空数据库中的URL引用
                message.media_url = None
                db.add(message)
        
        db.commit()
        print(f"INFO: 清理了 {deleted_count} 个过期文件")
        
    except Exception as e:
        print(f"ERROR: 清理过期文件时发生错误: {e}")
        db.rollback()

# --- WebSocket 连接管理：增强版本 ---
class EnhancedConnectionManager:
    def __init__(self):
        # 房间连接: {room_id: {user_id: WebSocket}}
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}
        # 用户连接计数: {user_id: connection_count}
        self.user_connection_count: Dict[int, int] = {}
        # 连接心跳记录: {(room_id, user_id): last_heartbeat}
        self.heartbeats: Dict[tuple, datetime] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user_id: int):
        # 检查用户连接数限制
        current_connections = self.user_connection_count.get(user_id, 0)
        if current_connections >= SecurityConfig.MAX_CONNECTIONS_PER_USER:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="超过最大连接数限制"
            )
            return False
        
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = {}
        
        # 如果用户已在该房间连接，关闭旧连接
        if user_id in self.active_connections[room_id]:
            old_ws = self.active_connections[room_id][user_id]
            try:
                await old_ws.close(code=status.WS_1000_NORMAL_CLOSURE, reason="新连接替换")
            except:
                pass
        
        self.active_connections[room_id][user_id] = websocket
        self.user_connection_count[user_id] = self.user_connection_count.get(user_id, 0) + 1
        self.heartbeats[(room_id, user_id)] = datetime.now()
        
        print(f"DEBUG_WS: 用户 {user_id} 连接房间 {room_id}，当前房间连接数: {len(self.active_connections[room_id])}")
        return True

    def disconnect(self, room_id: int, user_id: int):
        if room_id in self.active_connections and user_id in self.active_connections[room_id]:
            del self.active_connections[room_id][user_id]
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
            
            # 减少用户连接计数
            if user_id in self.user_connection_count:
                self.user_connection_count[user_id] -= 1
                if self.user_connection_count[user_id] <= 0:
                    del self.user_connection_count[user_id]
            
            # 移除心跳记录
            heartbeat_key = (room_id, user_id)
            if heartbeat_key in self.heartbeats:
                del self.heartbeats[heartbeat_key]
        
        print(f"DEBUG_WS: 用户 {user_id} 断开房间 {room_id}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            print(f"WARNING_WS: 发送个人消息失败: {e}")

    async def broadcast(self, message: str, room_id: int, exclude_user_id: Optional[int] = None):
        if room_id in self.active_connections:
            disconnected_users = []
            for user_id, connection in self.active_connections[room_id].items():
                if exclude_user_id and user_id == exclude_user_id:
                    continue
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"WARNING_WS: 向用户 {user_id} 广播消息失败: {e}")
                    disconnected_users.append(user_id)
            
            # 清理断开的连接
            for user_id in disconnected_users:
                self.disconnect(room_id, user_id)

    def update_heartbeat(self, room_id: int, user_id: int):
        """更新用户心跳时间"""
        self.heartbeats[(room_id, user_id)] = datetime.now()

    async def cleanup_stale_connections(self):
        """清理超时的连接"""
        current_time = datetime.now()
        stale_connections = []
        
        for (room_id, user_id), last_heartbeat in self.heartbeats.items():
            if (current_time - last_heartbeat).seconds > SecurityConfig.HEARTBEAT_INTERVAL * 2:
                stale_connections.append((room_id, user_id))
        
        for room_id, user_id in stale_connections:
            if room_id in self.active_connections and user_id in self.active_connections[room_id]:
                try:
                    await self.active_connections[room_id][user_id].close(
                        code=status.WS_1001_GOING_AWAY,
                        reason="连接超时"
                    )
                except:
                    pass
                self.disconnect(room_id, user_id)

manager = EnhancedConnectionManager()  # 创建增强版连接管理器实例

@router.post("/chat-rooms/", response_model=schemas.ChatRoomResponse, summary="创建新的聊天室")
async def create_chat_room(
        chat_room_data: schemas.ChatRoomCreate,
        background_tasks: BackgroundTasks,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    创建新的聊天室，具备完整的权限控制和安全验证
    """
    print(f"DEBUG: 用户 {current_user_id} 尝试创建聊天室: {chat_room_data.name}")

    try:
        # 1. 用户权限预检查
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效")

        # 2. 验证聊天室名称唯一性（同一用户不能创建重名聊天室）
        existing_room = db.query(ChatRoom).filter(
            ChatRoom.name == chat_room_data.name,
            ChatRoom.creator_id == current_user_id
        ).first()
        if existing_room:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="您已创建过同名的聊天室"
            )

        # 3. 关联项目/课程的安全校验
        if chat_room_data.project_id:
            project = db.query(Project).filter(Project.id == chat_room_data.project_id).first()
            if not project:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的项目不存在")
            
            # 验证用户是否有权将项目关联到聊天室
            if project.creator_id != current_user_id and not current_user.is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="您无权将此项目关联到聊天室"
                )
            
            if project.chat_room:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="项目已有关联聊天室"
                )

        if chat_room_data.course_id:
            course = db.query(Course).filter(Course.id == chat_room_data.course_id).first()
            if not course:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的课程不存在")
            
            # 验证用户是否有权将课程关联到聊天室
            if course.creator_id != current_user_id and not current_user.is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="您无权将此课程关联到聊天室"
                )
            
            if course.chat_room:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="课程已有关联聊天室"
                )

        # 4. 创建聊天室记录
        db_chat_room = ChatRoom(
            name=chat_room_data.name,
            type=chat_room_data.type,
            project_id=chat_room_data.project_id,
            course_id=chat_room_data.course_id,
            creator_id=current_user_id,
            color=chat_room_data.color or "#1976D2"  # 默认蓝色
        )
        db.add(db_chat_room)
        db.flush()  # 获取ID但不提交

        # 5. 添加创建者为群主成员
        db_chat_room_member = ChatRoomMember(
            room_id=db_chat_room.id,
            member_id=current_user_id,
            role="king",
            status="active"
        )
        db.add(db_chat_room_member)

        # 6. 创建系统欢迎消息
        welcome_message = ChatMessage(
            room_id=db_chat_room.id,
            sender_id=current_user_id,
            content_text=f"聊天室「{db_chat_room.name}」已创建！欢迎大家加入讨论。",
            message_type="system_notification"
        )
        db.add(welcome_message)

        db.commit()  # 提交所有更改
        db.refresh(db_chat_room)

        # 7. 填充响应数据
        db_chat_room.members_count = 1
        db_chat_room.last_message = {"sender": "系统", "content": "聊天室已创建！"}
        db_chat_room.unread_messages_count = 0
        db_chat_room.online_members_count = 0

        # 8. 添加后台任务进行文件清理
        background_tasks.add_task(cleanup_expired_files, db)

        print(f"DEBUG: 聊天室 '{db_chat_room.name}' (ID: {db_chat_room.id}) 创建成功")
        return db_chat_room

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR_DB: 聊天室创建发生完整性约束错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="聊天室创建失败，可能存在数据冲突"
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: 创建聊天室时发生未知异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建聊天室失败: {str(e)}"
        )


@router.get("/chatrooms/", response_model=List[schemas.ChatRoomResponse], summary="获取当前用户所属的所有聊天室")
async def get_all_chat_rooms(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        room_type: Optional[str] = Query(None, description="类型过滤"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        search: Optional[str] = Query(None, description="搜索聊天室名称"),
        sort_by: Literal["updated_at", "created_at", "name"] = Query("updated_at", description="排序字段"),
        sort_order: Literal["desc", "asc"] = Query("desc", description="排序方向")
):
    """
    获取当前用户所属（创建或参与）的所有聊天室列表。
    支持分页、搜索、排序和类型过滤。
    """
    print(f"DEBUG: 获取用户 {current_user_id} 的聊天室列表，类型: {room_type}, 页码: {page}")

    try:
        # 1. 权限查询：用户是创建者 OR 用户是活跃成员
        user_is_creator_condition = ChatRoom.creator_id == current_user_id
        user_is_active_member_condition = (
            db.query(ChatRoomMember.id)
            .filter(
                ChatRoomMember.room_id == ChatRoom.id,
                ChatRoomMember.member_id == current_user_id,
                ChatRoomMember.status == "active"
            )
            .exists()
        )
        
        main_filter_condition = or_(user_is_creator_condition, user_is_active_member_condition)

        # 2. 构建查询
        base_query = db.query(ChatRoom).filter(main_filter_condition)

        # 应用类型过滤
        if room_type:
            base_query = base_query.filter(ChatRoom.type == room_type)

        # 应用搜索过滤
        if search:
            search_pattern = f"%{search}%"
            base_query = base_query.filter(ChatRoom.name.ilike(search_pattern))

        # 应用排序
        if sort_by == "updated_at":
            order_column = ChatRoom.updated_at
        elif sort_by == "created_at":
            order_column = ChatRoom.created_at
        else:
            order_column = ChatRoom.name

        if sort_order == "desc":
            base_query = base_query.order_by(desc(order_column))
        else:
            base_query = base_query.order_by(order_column)

        # 3. 计算总数（用于分页信息）
        total_count = base_query.count()

        # 4. 应用分页
        offset = (page - 1) * page_size
        rooms = base_query.offset(offset).limit(page_size).all()

        # 5. 批量获取房间相关数据，避免N+1查询
        room_ids = [room.id for room in rooms]
        
        # 批量获取成员数量
        member_counts = {}
        if room_ids:
            member_count_query = db.query(
                ChatRoomMember.room_id,
                func.count(ChatRoomMember.id).label('count')
            ).filter(
                ChatRoomMember.room_id.in_(room_ids),
                ChatRoomMember.status == "active"
            ).group_by(ChatRoomMember.room_id).all()
            
            member_counts = {row.room_id: row.count for row in member_count_query}

        # 批量获取最新消息
        latest_messages = {}
        if room_ids:
            # 使用窗口函数获取每个房间的最新消息
            latest_msg_subquery = (
                db.query(
                    ChatMessage.room_id,
                    ChatMessage.content_text,
                    ChatMessage.sent_at,
                    Student.name.label('sender_name'),
                    func.row_number().over(
                        partition_by=ChatMessage.room_id,
                        order_by=ChatMessage.sent_at.desc()
                    ).label('rn')
                )
                .join(Student, Student.id == ChatMessage.sender_id)
                .filter(
                    ChatMessage.room_id.in_(room_ids),
                    ChatMessage.deleted_at.is_(None)
                )
                .subquery()
            )

            latest_messages_query = db.query(
                latest_msg_subquery.c.room_id,
                latest_msg_subquery.c.content_text,
                latest_msg_subquery.c.sender_name
            ).filter(latest_msg_subquery.c.rn == 1).all()

            for msg in latest_messages_query:
                content = msg.content_text or ""
                if len(content) > 50:
                    content = content[:50] + "..."
                latest_messages[msg.room_id] = {
                    "sender": msg.sender_name or "未知",
                    "content": content
                }

        # 6. 填充响应数据
        for room in rooms:
            room.members_count = member_counts.get(room.id, 0)
            room.last_message = latest_messages.get(room.id, {"sender": "系统", "content": "暂无消息"})
            
            # 获取在线成员数量（从WebSocket连接管理器）
            room.online_members_count = len(manager.active_connections.get(room.id, {}))
            
            # TODO: 实现未读消息计数功能
            room.unread_messages_count = 0

        print(f"DEBUG: 用户 {current_user_id} 获取到 {len(rooms)} 个聊天室，总计 {total_count} 个")

        # 7. 设置分页响应头
        response_data = JSONResponse(
            content=[room.__dict__ for room in rooms],
            headers={
                "X-Total-Count": str(total_count),
                "X-Page": str(page),
                "X-Page-Size": str(page_size),
                "X-Total-Pages": str((total_count + page_size - 1) // page_size)
            }
        )
        return rooms

    except Exception as e:
        print(f"ERROR: 获取聊天室列表时发生错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取聊天室列表失败，请稍后重试"
        )


@router.get("/chatrooms/{room_id}", response_model=schemas.ChatRoomResponse, summary="获取指定聊天室详情")
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


@router.put("/chatrooms/{room_id}/", response_model=schemas.ChatRoomResponse, summary="更新指定聊天室")
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
            # TODO: 进一步验证 current_user_id 是否有权将聊天室关联到此课程

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


@router.delete("/chatrooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定聊天室（仅限群主或系统管理员）",
            operation_id="delete_single_chat_room_by_creator_or_admin")  # 明确且唯一的 operation_id
async def delete_chat_room(
        room_id: int,  # 从路径中获取聊天室ID
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 删除聊天室 ID: {room_id}。操作用户: {current_user_id}")

    try:
        # 1. 获取当前用户的信息，以便检查其是否为管理员
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        # 2. 获取目标聊天室
        db_chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM_DELETE_ROOM: current_user_id={current_user_id} (type={type(current_user_id)}), chat_room.creator_id={db_chat_room.creator_id} (type={type(db_chat_room.creator_id)})")
        print(f"DEBUG_PERM_DELETE_ROOM: current_user.is_admin={current_user.is_admin}")

        # 核心权限检查：只有群主或系统管理员可以删除此聊天室
        is_creator = (db_chat_room.creator_id == current_user_id)
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


@router.get("/chatrooms/{room_id}/members", response_model=List[schemas.ChatRoomMemberResponse],
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


@router.put("/chat-rooms/{room_id}/members/{member_id}/set-role", response_model=schemas.ChatRoomMemberResponse,
         summary="设置聊天室成员的角色（管理员/普通成员）")
async def set_chat_room_member_role(
        room_id: int,  # 目标聊天室ID
        member_id: int,  # 目标成员的用户ID
        role_update: schemas.ChatRoomMemberRoleUpdate,  # 包含新的角色信息
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(
        f"DEBUG: 用户 {current_user_id} 尝试设置聊天室 {room_id} 中用户 {member_id} 的角色为 '{role_update.role}'。")

    try:
        # 1. 验证目标角色是否合法
        if role_update.role not in ["admin", "member"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="无效的角色类型，只能为 'admin' 或 'member'。")

        # 2. 获取当前操作用户、目标聊天室和目标成员关系
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
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
        if chat_room.creator_id == db_member.member_id:  # 这里的 db_member.member_id 通常是 int，所以比较的是 int == int
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="群主的角色不能通过此接口修改。群主身份由 ChatRoom.creator_id 字段定义。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM_SET_ROLE: current_user_id={current_user_id}, chat_room.creator_id={chat_room.creator_id}, current_user.is_admin={current_user.is_admin}")

        # 3. 核心操作权限检查：只有群主可以设置聊天室成员角色
        is_creator = (chat_room.creator_id == current_user_id)

        print(f"DEBUG_PERM_SET_ROLE: is_creator={is_creator}")

        if not is_creator:  # 仅检查 is_creator
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="无权设置聊天室成员角色。只有群主可以执行此操作。")

        # 4. 特殊业务逻辑限制 (防止聊天室管理员给自己降权)
        if current_user_id == member_id and db_member.role == "admin" and role_update.role == "member":
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


@router.delete("/chat-rooms/{room_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="从聊天室移除成员（踢出或离开）")
async def remove_chat_room_member(
        room_id: int,
        member_id: int,  # 目标成员的用户ID
        current_user_id: int = Depends(get_current_user_id),  # 操作者用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试从聊天室 {room_id} 移除成员 {member_id}。")

    try:
        # 1. 获取当前操作用户、目标聊天室和目标成员的 ChatRoomMember 记录
        acting_user = db.query(Student).filter(Student.id == current_user_id).first()
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
            f"DEBUG_PERM_REMOVE: current_user_id={current_user_id}, chat_room.creator_id={chat_room.creator_id}, current_user.is_admin={acting_user.is_admin}")

        # 2. 处理用户自己离开群聊的情况
        if current_user_id == member_id:
            print(f"DEBUG_PERM_REMOVE: 判定为用户 {current_user_id} 尝试自己离开。")
            # 群主不能通过此接口离开群聊（他们应该使用解散群聊功能）
            if chat_room.creator_id == current_user_id:  # 使用 int 型 ID 比较
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="群主不能通过此接口离开群聊。要解散聊天室请使用解散功能。")

            # 其他活跃成员可以直接离开群聊
            target_membership.status = "left"  # 标记为"已离开"
            db.add(target_membership)
            db.commit()
            print(f"DEBUG: 用户 {current_user_id} 已成功离开聊天室 {room_id}。")
            return Response(status_code=status.HTTP_204_NO_CONTENT)  # 成功离开，返回 204

        # 3. 处理踢出他人成员的情况** (`member_id` != `current_user_id`)
        print(f"DEBUG_PERM_REMOVE: 判定为用户 {current_user_id} 尝试移除他人 {member_id}。")
        # 确定操作者的角色
        is_creator = (chat_room.creator_id == current_user_id)  # 使用 int 型 ID 比较
        is_system_admin = acting_user.is_admin

        # 如果操作者不是群主也不是系统管理员，则去查询他是否是聊天室管理员
        acting_user_membership = None
        if not is_creator and not is_system_admin:
            print(f"DEBUG_PERM_REMOVE: 操作者不是群主也不是系统管理员，检查是否是聊天室管理员。")
            acting_user_membership = db.query(ChatRoomMember).filter(
                ChatRoomMember.room_id == room_id,
                ChatRoomMember.member_id == current_user_id,
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
            print(f"DEBUG_PERM_REMOVE: 系统管理员 {current_user_id} 允许踢出。")
        elif is_creator:
            can_kick = True  # 群主可以踢出任何人
            print(f"DEBUG_PERM_REMOVE: 群主 {current_user_id} 允许踢出。")
        elif is_room_admin:
            # 聊天室管理员只能在特定条件下踢人
            if target_member_is_creator:
                reason_detail = "聊天室管理员无权移除群主。"
                print(f"DEBUG_PERM_REMOVE: 聊天室管理员 {current_user_id} 试图移除群主，拒绝。")
            elif target_member_role_in_room == "admin":
                reason_detail = "聊天室管理员无权移除其他管理员。"
                print(f"DEBUG_PERM_REMOVE: 聊天室管理员 {current_user_id} 试图移除其他管理员，拒绝。")
            else:  # 目标成员是普通成员
                can_kick = True
                print(f"DEBUG_PERM_REMOVE: 聊天室管理员 {current_user_id} 允许踢出普通成员 {member_id}。")

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


@router.post("/chat-rooms/{room_id}/join-request", response_model=schemas.ChatRoomJoinRequestResponse,
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


@router.get("/chat-rooms/{room_id}/join-requests", response_model=List[schemas.ChatRoomJoinRequestResponse],
         summary="获取指定聊天室的入群申请列表")
async def get_join_requests_for_room(
        room_id: int,  # 目标聊天室ID
        # 允许通过 status 过滤请求 (例如 'pending', 'approved', 'rejected')
        status_filter: Optional[str] = Query("pending", description="过滤申请状态（pending, approved, rejected）"),
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试获取聊天室 {room_id} 的入群申请列表 (状态: {status_filter})。")

    try:
        # 1. 获取当前用户和目标聊天室的信息
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM: current_user_id={current_user_id} (type={type(current_user_id)}), chat_room.creator_id={chat_room.creator_id} (type={type(chat_room.creator_id)}), current_user.is_admin={current_user.is_admin}")

        # 2. 核心权限检查：用户是否是群主、聊天室管理员或系统管理员
        is_creator = (chat_room.creator_id == current_user_id)
        is_room_admin = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,  # 查询时使用转换后的 current_user_id**
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


@router.post("/chat-rooms/join-requests/{request_id}/process", response_model=schemas.ChatRoomJoinRequestResponse,
          summary="处理入群申请 (批准或拒绝)")
async def process_join_request(
        request_id: int,  # 要处理的入群申请ID
        process_data: schemas.ChatRoomJoinRequestProcess,  # 包含处理结果 (approved/rejected)
        current_user_id: int = Depends(get_current_user_id),  # 已认证的用户ID，即处理者
        db: Session = Depends(get_db)
):
    print(f"DEBUG: 用户 {current_user_id} 尝试处理入群申请 ID: {request_id} 为 '{process_data.status}'。")

    try:
        # 1. 验证目标入群申请是否存在且为 pending 状态
        db_request = db.query(ChatRoomJoinRequest).filter(ChatRoomJoinRequest.id == request_id).first()
        if not db_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="入群申请未找到。")
        if db_request.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该申请已处理或状态异常，无法再次处理。")

        # 2. 获取当前用户和目标聊天室的信息，用于权限检查
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == db_request.room_id).first()
        if not chat_room:
            # 理论上不会发生，因为 db_request.room_id 引用 ChatRoom
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="关联的聊天室不存在。")

        # 调试打印：查看权限相关的原始值和比较结果
        print(
            f"DEBUG_PERM_PROCESS: current_user_id={current_user_id}, chat_room.creator_id={chat_room.creator_id}, current_user.is_admin={current_user.is_admin}")

        # 3. 核心权限检查：处理者是否是群主、聊天室管理员或系统管理员
        is_creator = (chat_room.creator_id == current_user_id)  # 使用 int 型 ID 比较
        is_room_admin = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == chat_room.id,
            ChatRoomMember.member_id == current_user_id,  # 使用 int 型 ID 比较
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
        db_request.processed_by_id = current_user_id  # 使用 int 型 ID 赋值
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

    print(f"DEBUG_POINTS: 用户 {user.id} 积分变动：{amount}，当前总积分：{user.total_points}，原因：{reason}")


async def _check_and_award_achievements(db: Session, user_id: int):
    """
    检查用户是否达到了任何成就条件，并授予未获得的成就。
    此函数会定期或在关键事件后调用。它只添加对象到会话，不进行commit。
    """
    print(f"DEBUG_ACHIEVEMENT: 检查用户 {user_id} 的成就")
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        print(f"WARNING_ACHIEVEMENT: 用户 {user_id} 不存在")
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
    if not unearned_achievements:
        print(f"DEBUG_ACHIEVEMENT: 用户 {user_id} 没有未获得的活跃成就")
        return

    # TODO: 实现具体的成就检查逻辑
    # 例如：聊天消息数量成就、文件上传成就等


# --- 文件存储成本优化策略 ---
async def optimize_storage_costs(db: Session):
    """
    优化存储成本的策略实现
    """
    try:
        # 1. 清理重复文件
        await remove_duplicate_files(db)
        
        # 2. 压缩大型媒体文件
        await compress_large_media_files(db)
        
        # 3. 迁移冷数据到低成本存储
        await migrate_cold_data(db)
        
        # 4. 删除孤立文件
        await cleanup_orphaned_files(db)
        
        print("INFO: 存储成本优化完成")
        
    except Exception as e:
        print(f"ERROR: 存储成本优化失败: {e}")


async def remove_duplicate_files(db: Session):
    """识别并删除重复的文件"""
    # 基于文件哈希值识别重复文件
    duplicate_query = """
    SELECT media_url, COUNT(*) as count, 
           MIN(id) as keep_id,
           ARRAY_AGG(id) as all_ids
    FROM chat_messages 
    WHERE media_url IS NOT NULL 
      AND deleted_at IS NULL
    GROUP BY media_url 
    HAVING COUNT(*) > 1
    """
    
    # TODO: 实现重复文件清理逻辑


async def compress_large_media_files(db: Session):
    """压缩大型媒体文件"""
    # 查找大于一定阈值的媒体文件
    large_files = db.query(ChatMessage).filter(
        ChatMessage.file_size > 10 * 1024 * 1024,  # 大于10MB
        ChatMessage.media_url.isnot(None),
        ChatMessage.deleted_at.is_(None)
    ).all()
    
    # TODO: 实现文件压缩逻辑


async def migrate_cold_data(db: Session):
    """将冷数据迁移到低成本存储"""
    # 超过一定时间未访问的文件迁移到冷存储
    cold_threshold = datetime.now() - timedelta(days=90)
    
    cold_files = db.query(ChatMessage).filter(
        ChatMessage.sent_at < cold_threshold,
        ChatMessage.media_url.isnot(None),
        ChatMessage.deleted_at.is_(None)
    ).all()
    
    # TODO: 实现冷数据迁移逻辑


async def cleanup_orphaned_files(db: Session):
    """清理孤立的文件（数据库中已删除但OSS中仍存在）"""
    # TODO: 实现孤立文件清理逻辑
    pass


# --- 权限管理增强 ---
class PermissionManager:
    """权限管理器"""
    
    @staticmethod
    def check_file_access_permission(user_id: int, file_url: str, db: Session) -> bool:
        """检查用户是否有权限访问特定文件"""
        # 查找文件所属的聊天室
        message = db.query(ChatMessage).filter(
            ChatMessage.media_url == file_url,
            ChatMessage.deleted_at.is_(None)
        ).first()
        
        if not message:
            return False
        
        # 检查用户是否有权限访问该聊天室
        room_id = message.room_id
        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        
        if not chat_room:
            return False
        
        # 检查是否是群主或活跃成员
        is_creator = (chat_room.creator_id == user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == user_id,
            ChatRoomMember.status == "active"
        ).first() is not None
        
        return is_creator or is_active_member
    
    @staticmethod
    def get_user_storage_quota(user: Student) -> dict:
        """获取用户存储配额信息"""
        # 基础配额
        base_quota_mb = 100  # 100MB基础配额
        
        # 会员额外配额
        premium_bonus_mb = 500 if user.is_admin else 0
        
        # 积分兑换配额
        point_bonus_mb = min(user.total_points // 100, 1000)  # 每100积分兑换1MB，最多1GB
        
        total_quota_mb = base_quota_mb + premium_bonus_mb + point_bonus_mb
        
        # 计算已使用配额
        used_quota_mb = 0  # TODO: 实现已使用配额计算
        
        return {
            "total_quota_mb": total_quota_mb,
            "used_quota_mb": used_quota_mb,
            "available_quota_mb": total_quota_mb - used_quota_mb,
            "quota_percentage": (used_quota_mb / total_quota_mb) * 100 if total_quota_mb > 0 else 0
        }


# --- 文件访问权限接口 ---
@router.get("/files/{file_id}/access", summary="验证文件访问权限")
async def verify_file_access(
        file_id: str,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    验证用户是否有权限访问特定文件
    """
    try:
        # 从文件ID或URL中提取文件信息
        # TODO: 实现文件ID到URL的映射
        
        has_permission = PermissionManager.check_file_access_permission(
            current_user_id, file_id, db
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您无权访问此文件"
            )
        
        return {"access_granted": True, "file_id": file_id}
        
    except Exception as e:
        print(f"ERROR: 验证文件访问权限失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="验证文件权限失败"
        )


@router.get("/users/storage-quota", summary="获取用户存储配额信息")
async def get_user_storage_quota(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取当前用户的存储配额信息
    """
    try:
        user = db.query(Student).filter(Student.id == current_user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户未找到"
            )
        
        quota_info = PermissionManager.get_user_storage_quota(user)
        
        return quota_info
        
    except Exception as e:
        print(f"ERROR: 获取存储配额信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取存储配额信息失败"
        )


# --- 聊天室基础管理接口 ---
@router.get("/chatrooms/{room_id}", response_model=schemas.ChatRoomResponse, summary="获取指定聊天室详情（增强版）", operation_id="get_chat_room_by_id_enhanced")
async def get_chat_room_by_id_enhanced(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取指定ID的聊天室详情。
    增强特性：
    - 在线成员统计
    - 权限验证
    - 详细信息展示
    """
    try:
        # 获取当前用户和目标聊天室的信息
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        # 权限检查
        is_creator = (chat_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member or current_user.is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="您无权查看该聊天室的详情"
            )

        # 填充统计信息
        chat_room.members_count = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == chat_room.id,
            ChatRoomMember.status == "active"
        ).count()

        # 获取最新消息
        latest_message_data = (
            db.query(ChatMessage.content_text, Student.name)
            .filter(
                ChatMessage.room_id == chat_room.id,
                ChatMessage.deleted_at.is_(None)
            )
            .join(Student, Student.id == ChatMessage.sender_id)
            .order_by(ChatMessage.sent_at.desc())
            .first()
        )

        if latest_message_data:
            content_text, sender_name = latest_message_data
            chat_room.last_message = {
                "sender": sender_name or "未知",
                "content": content_text[:50] + "..." if content_text and len(content_text) > 50 else (content_text or "")
            }
        else:
            chat_room.last_message = {"sender": "系统", "content": "暂无消息"}

        # 在线成员统计
        chat_room.online_members_count = len(manager.active_connections.get(room_id, {}))
        
        # TODO: 实现未读消息统计
        chat_room.unread_messages_count = 0

        return chat_room

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: 获取聊天室详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"获取聊天室详情失败: {str(e)}"
        )


@router.put("/chatrooms/{room_id}/", response_model=schemas.ChatRoomResponse, summary="更新指定聊天室（增强版）", operation_id="update_chat_room_enhanced")
async def update_chat_room_enhanced(
        room_id: int,
        room_data: schemas.ChatRoomUpdate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新指定聊天室。
    增强特性：
    - 严格权限控制
    - 关联验证
    - 实时通知
    """
    try:
        # 权限检查：只有创建者才能更新聊天室
        db_chat_room = db.query(ChatRoom).filter(
            ChatRoom.id == room_id,
            ChatRoom.creator_id == current_user_id
        ).first()

        if not db_chat_room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="聊天室未找到或无权访问"
            )

        update_data = room_data.dict(exclude_unset=True)

        # 验证项目关联
        if "project_id" in update_data and update_data["project_id"] is not None:
            project = db.query(Project).filter(Project.id == update_data["project_id"]).first()
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="关联的项目不存在"
                )
            
            # 检查权限
            if project.creator_id != current_user_id:
                current_user = db.query(Student).filter(Student.id == current_user_id).first()
                if not current_user or not current_user.is_admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="您无权将此项目关联到聊天室"
                    )
            
            # 检查项目是否已有其他聊天室
            if project.chat_room and project.chat_room.id != room_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="项目已有关联的聊天室"
                )

        # 验证课程关联
        if "course_id" in update_data and update_data["course_id"] is not None:
            course = db.query(Course).filter(Course.id == update_data["course_id"]).first()
            if not course:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="关联的课程不存在"
                )
            
            # 检查权限
            if course.creator_id != current_user_id:
                current_user = db.query(Student).filter(Student.id == current_user_id).first()
                if not current_user or not current_user.is_admin:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="您无权将此课程关联到聊天室"
                    )
            
            # 检查课程是否已有其他聊天室
            if course.chat_room and course.chat_room.id != room_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="课程已有关联的聊天室"
                )

        # 应用更新
        for key, value in update_data.items():
            setattr(db_chat_room, key, value)

        db_chat_room.updated_at = func.now()
        db.add(db_chat_room)
        db.commit()
        db.refresh(db_chat_room)

        # 填充响应数据
        db_chat_room.members_count = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == db_chat_room.id,
            ChatRoomMember.status == "active"
        ).count()
        
        db_chat_room.online_members_count = len(manager.active_connections.get(room_id, {}))
        db_chat_room.unread_messages_count = 0
        db_chat_room.last_message = {"sender": "系统", "content": "聊天室信息已更新"}

        # WebSocket通知
        update_notification = {
            "type": "room_updated",
            "room_id": room_id,
            "updated_by": current_user_id,
            "changes": update_data,
            "timestamp": datetime.now().isoformat()
        }
        asyncio.create_task(manager.broadcast(json.dumps(update_notification), room_id))

        print(f"DEBUG: 聊天室 {room_id} 更新成功")
        return db_chat_room

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR: 聊天室更新发生完整性约束错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="更新聊天室失败，可能存在名称冲突或其他约束冲突"
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 更新聊天室失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"更新聊天室失败: {str(e)}"
        )


@router.delete("/chatrooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="删除指定聊天室（增强版）")
async def delete_chat_room(
        room_id: int,
        background_tasks: BackgroundTasks,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    删除指定聊天室。
    增强特性：
    - 严格权限控制
    - 关联文件清理
    - 级联删除
    - 实时通知
    """
    try:
        # 获取当前用户信息
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效")

        # 获取目标聊天室
        db_chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        # 权限检查：只有群主或系统管理员可以删除
        is_creator = (db_chat_room.creator_id == current_user_id)
        is_system_admin = current_user.is_admin

        if not (is_creator or is_system_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权删除此聊天室。只有群主或系统管理员可以执行此操作"
            )

        # 收集需要清理的文件
        messages_with_files = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.media_url.isnot(None)
        ).all()

        file_urls_to_delete = [msg.media_url for msg in messages_with_files if msg.media_url]

        # 先通知所有连接的用户聊天室即将删除
        deletion_notification = {
            "type": "room_deleting",
            "room_id": room_id,
            "deleted_by": current_user_id,
            "timestamp": datetime.now().isoformat(),
            "message": "聊天室即将被删除"
        }
        await manager.broadcast(json.dumps(deletion_notification), room_id)

        # 断开所有WebSocket连接
        if room_id in manager.active_connections:
            for user_id, websocket in list(manager.active_connections[room_id].items()):
                try:
                    await websocket.close(
                        code=status.WS_1001_GOING_AWAY, 
                        reason="聊天室已被删除"
                    )
                except:
                    pass
                manager.disconnect(room_id, user_id)

        # 执行数据库删除（级联删除应在模型中配置）
        db.delete(db_chat_room)
        db.commit()

        # 后台任务：清理关联文件
        background_tasks.add_task(cleanup_room_files, file_urls_to_delete)

        print(f"DEBUG: 聊天室 {room_id} 及其所有关联数据已成功删除")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR: 聊天室删除发生完整性约束错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, 
            detail="删除聊天室失败，可能存在数据关联问题"
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 删除聊天室失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"删除聊天室失败: {str(e)}"
        )


async def cleanup_room_files(file_urls: List[str]):
    """后台任务：清理聊天室相关的文件"""
    for file_url in file_urls:
        try:
            # 从URL中提取object_name
            object_name = file_url.split('/')[-1]
            await oss_utils.delete_file_from_oss(object_name)
            print(f"DEBUG: 已删除文件: {object_name}")
        except Exception as e:
            print(f"WARNING: 删除文件失败: {file_url}, 错误: {e}")


# --- 入群申请管理 ---
@router.post("/chat-rooms/{room_id}/join-request", response_model=schemas.ChatRoomJoinRequestResponse,
          summary="向指定聊天室发起入群申请（增强版）", operation_id="send_join_request_enhanced")
async def send_join_request_enhanced(
        room_id: int,
        request_data: schemas.ChatRoomJoinRequestCreate,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    向指定聊天室发起入群申请。
    增强特性：
    - 重复申请检查
    - 实时通知
    - 申请理由验证
    """
    try:
        if request_data.room_id != room_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="请求体中的room_id与路径中的room_id不匹配"
            )

        # 验证聊天室存在
        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        # 验证申请者不是创建者
        if chat_room.creator_id == current_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已经是该聊天室的创建者，无需申请加入"
            )

        # 验证申请者不是活跃成员
        existing_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first()
        if existing_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="您已是该聊天室的活跃成员，无需重复申请"
            )

        # 验证没有待处理的申请
        existing_pending_request = db.query(ChatRoomJoinRequest).filter(
            ChatRoomJoinRequest.room_id == room_id,
            ChatRoomJoinRequest.requester_id == current_user_id,
            ChatRoomJoinRequest.status == "pending"
        ).first()
        if existing_pending_request:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail="您已有待处理的入群申请，请勿重复提交"
            )

        # 创建入群申请
        db_join_request = ChatRoomJoinRequest(
            room_id=room_id,
            requester_id=current_user_id,
            reason=request_data.reason,
            status="pending"
        )
        db.add(db_join_request)
        db.commit()
        db.refresh(db_join_request)

        # 实时通知群主和管理员
        requester = db.query(Student).filter(Student.id == current_user_id).first()
        join_request_notification = {
            "type": "join_request_received",
            "room_id": room_id,
            "requester_id": current_user_id,
            "requester_name": requester.name if requester else "未知用户",
            "reason": request_data.reason,
            "request_id": db_join_request.id,
            "timestamp": datetime.now().isoformat()
        }
        
        # 通知群主
        if chat_room.creator_id in manager.active_connections.get(room_id, {}):
            creator_ws = manager.active_connections[room_id][chat_room.creator_id]
            asyncio.create_task(
                manager.send_personal_message(json.dumps(join_request_notification), creator_ws)
            )

        print(f"DEBUG: 用户 {current_user_id} 向聊天室 {room_id} 发起入群申请")
        return db_join_request

    except IntegrityError as e:
        db.rollback()
        print(f"ERROR: 入群申请创建发生完整性约束错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="入群申请提交失败，可能存在重复申请或其他数据冲突"
        )
# --- 管理员功能和系统维护 ---
@router.post("/admin/optimize-storage", summary="优化存储（管理员）")
async def optimize_storage_endpoint(
        background_tasks: BackgroundTasks,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    触发存储优化任务（仅管理员可用）
    """
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以执行此操作"
        )
    
    # 添加后台任务
    background_tasks.add_task(optimize_storage_costs, db)
    background_tasks.add_task(cleanup_expired_files, db)
    
    return {"message": "存储优化任务已启动"}


@router.post("/admin/cleanup-connections", summary="清理过期WebSocket连接（管理员）")
async def cleanup_stale_connections(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    清理过期的WebSocket连接（仅管理员可用）
    """
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以执行此操作"
        )
    
    await manager.cleanup_stale_connections()
    
    return {
        "message": "已清理过期连接",
        "active_rooms": len(manager.active_connections),
        "total_connections": sum(len(connections) for connections in manager.active_connections.values())
    }


@router.get("/admin/system-health", summary="系统健康检查（管理员）")
async def system_health_check(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    系统健康检查（仅管理员可用）
    """
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以查看系统健康状态"
        )
    
    try:
        # 数据库健康检查
        db_health = True
        try:
            db.execute("SELECT 1")
        except:
            db_health = False
        
        # WebSocket连接状态
        ws_stats = {
            "active_rooms": len(manager.active_connections),
            "total_connections": sum(len(connections) for connections in manager.active_connections.values()),
            "user_connections": len(manager.user_connection_count),
            "heartbeat_records": len(manager.heartbeats)
        }
        
        # 存储统计
        total_messages = db.query(ChatMessage).count()
        messages_with_files = db.query(ChatMessage).filter(
            ChatMessage.media_url.isnot(None)
        ).count()
        
        total_file_size = db.query(func.sum(ChatMessage.file_size)).filter(
            ChatMessage.file_size.isnot(None)
        ).scalar() or 0
        
        # 内存和性能指标
        import psutil
        memory_usage = psutil.virtual_memory().percent
        cpu_usage = psutil.cpu_percent()
        
        return {
            "system_status": "healthy" if db_health else "unhealthy",
            "database_health": db_health,
            "websocket_stats": ws_stats,
            "storage_stats": {
                "total_messages": total_messages,
                "messages_with_files": messages_with_files,
                "total_file_size_mb": round(total_file_size / (1024 * 1024), 2)
            },
            "server_stats": {
                "memory_usage_percent": memory_usage,
                "cpu_usage_percent": cpu_usage
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"ERROR: 系统健康检查失败: {e}")
        return {
            "system_status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# --- 安全检查和审计 ---
@router.post("/admin/security-scan", summary="安全扫描（管理员）")
async def security_scan(
        scan_type: Literal["files", "connections", "permissions", "all"] = Query("all"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    执行安全扫描（仅管理员可用）
    """
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以执行安全扫描"
        )
    
    scan_results = {}
    
    try:
        if scan_type in ["files", "all"]:
            # 文件安全扫描
            large_files = db.query(ChatMessage).filter(
                ChatMessage.file_size > 50 * 1024 * 1024,  # 大于50MB
                ChatMessage.media_url.isnot(None)
            ).count()
            
            scan_results["file_security"] = {
                "large_files_count": large_files,
                "status": "warning" if large_files > 10 else "ok"
            }
        
        if scan_type in ["connections", "all"]:
            # 连接安全扫描
            total_connections = sum(len(connections) for connections in manager.active_connections.values())
            max_connections_per_user = max(manager.user_connection_count.values()) if manager.user_connection_count else 0
            
            scan_results["connection_security"] = {
                "total_connections": total_connections,
                "max_connections_per_user": max_connections_per_user,
                "status": "warning" if max_connections_per_user > SecurityConfig.MAX_CONNECTIONS_PER_USER else "ok"
            }
        
        if scan_type in ["permissions", "all"]:
            # 权限安全扫描
            admin_count = db.query(Student).filter(Student.is_admin == True).count()
            
            scan_results["permission_security"] = {
                "admin_users_count": admin_count,
                "status": "warning" if admin_count > 5 else "ok"  # 警告：管理员过多
            }
        
        overall_status = "ok"
        for category in scan_results.values():
            if category.get("status") == "warning":
                overall_status = "warning"
                break
        
        return {
            "scan_type": scan_type,
            "overall_status": overall_status,
            "scan_results": scan_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"ERROR: 安全扫描失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"安全扫描失败: {str(e)}"
        )


# --- 批量操作接口 ---
@router.post("/admin/batch-cleanup", summary="批量清理操作（管理员）")
async def batch_cleanup(
        background_tasks: BackgroundTasks,
        cleanup_type: Literal["expired_files", "old_messages", "inactive_rooms", "all"] = Query("expired_files"),
        days_threshold: int = Query(30, description="清理阈值天数"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    批量清理操作（仅管理员可用）
    """
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以执行批量清理"
        )
    
    tasks_added = []
    
    if cleanup_type in ["expired_files", "all"]:
        background_tasks.add_task(cleanup_expired_files, db)
        tasks_added.append("expired_files")
    
    if cleanup_type in ["old_messages", "all"]:
        background_tasks.add_task(cleanup_old_messages, db, days_threshold)
        tasks_added.append("old_messages")
    
    if cleanup_type in ["inactive_rooms", "all"]:
        background_tasks.add_task(cleanup_inactive_rooms, db, days_threshold)
        tasks_added.append("inactive_rooms")
    
    return {
        "message": "批量清理任务已启动",
        "tasks": tasks_added,
        "days_threshold": days_threshold
    }


async def cleanup_old_messages(db: Session, days_threshold: int):
    """清理旧消息"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        
        # 查找旧消息
        old_messages = db.query(ChatMessage).filter(
            ChatMessage.sent_at < cutoff_date,
            ChatMessage.deleted_at.is_(None)
        ).all()
        
        deleted_count = 0
        for message in old_messages:
            # 软删除消息
            message.deleted_at = func.now()
            db.add(message)
            deleted_count += 1
        
        db.commit()
        print(f"INFO: 清理了 {deleted_count} 条旧消息")
        
    except Exception as e:
        print(f"ERROR: 清理旧消息失败: {e}")
        db.rollback()


async def cleanup_inactive_rooms(db: Session, days_threshold: int):
    """清理不活跃的聊天室"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        
        # 查找不活跃的聊天室
        inactive_rooms = db.query(ChatRoom).filter(
            ChatRoom.updated_at < cutoff_date,
            # 添加其他条件，比如无活跃成员
        ).all()
        
        # TODO: 实现不活跃聊天室的清理逻辑
        # 需要谨慎处理，避免误删重要聊天室
        
        print(f"INFO: 发现 {len(inactive_rooms)} 个不活跃聊天室")
        
    except Exception as e:
        print(f"ERROR: 清理不活跃聊天室失败: {e}")


# --- 实时状态监控 ---
@router.get("/admin/real-time-stats", summary="实时统计数据（管理员）")
async def get_real_time_stats(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    获取实时统计数据（仅管理员可用）
    """
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以查看实时统计"
        )
    
    try:
        # 实时消息统计
        now = datetime.now()
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)
        
        messages_last_hour = db.query(ChatMessage).filter(
            ChatMessage.sent_at >= last_hour
        ).count()
        
        messages_last_day = db.query(ChatMessage).filter(
            ChatMessage.sent_at >= last_day
        ).count()
        
        # 活跃用户统计
        active_users_last_hour = db.query(ChatMessage.sender_id).filter(
            ChatMessage.sent_at >= last_hour
        ).distinct().count()
        
        # WebSocket连接统计
        current_connections = sum(len(connections) for connections in manager.active_connections.values())
        active_rooms = len(manager.active_connections)
        
        return {
            "timestamp": now.isoformat(),
            "message_stats": {
                "last_hour": messages_last_hour,
                "last_day": messages_last_day
            },
            "user_stats": {
                "active_users_last_hour": active_users_last_hour
            },
            "connection_stats": {
                "current_connections": current_connections,
                "active_rooms": active_rooms
            }
        }
        
    except Exception as e:
        print(f"ERROR: 获取实时统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取实时统计失败: {str(e)}"
        )
@router.post("/chatrooms/{room_id}/messages/", response_model=schemas.ChatMessageResponse,
          summary="在指定聊天室发送新消息（增强版）")
async def send_chat_message(
        room_id: int,
        background_tasks: BackgroundTasks,
        content_text: Optional[str] = Form(None, description="消息文本内容"),
        message_type: Literal["text", "image", "file", "video", "audio", "system_notification"] = Form("text"),
        media_url: Optional[str] = Form(None, description="媒体文件OSS URL或外部链接"),
        file: Optional[UploadFile] = File(None, description="单个文件上传"),
        files: Optional[List[UploadFile]] = File(None, description="批量文件上传（最多9个）"),
        audio_duration: Optional[float] = Form(None, description="音频时长（秒）"),
        file_size: Optional[int] = Form(None, description="文件大小（字节）"),
        reply_to_message_id: Optional[int] = Form(None, description="回复的消息ID"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    发送消息到指定聊天室。
    
    功能特性：
    - 支持文本、图片、视频、音频、文件消息
    - 批量文件上传（最多9个）
    - 文件安全扫描和大小限制
    - 回复消息功能
    - 自动清理过期文件
    - 实时WebSocket推送
    """
    print(f"DEBUG: 用户 {current_user_id} 在聊天室 {room_id} 发送消息，类型: {message_type}")

    uploaded_files_for_rollback = []

    try:
        # 1. 基础权限验证
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您无权在该聊天室发送消息"
            )

        # 2. 验证发送者
        db_sender = db.query(Student).filter(Student.id == current_user_id).first()
        if not db_sender:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发送者用户未找到")

        # 3. 验证回复消息
        reply_message = None
        if reply_to_message_id:
            reply_message = db.query(ChatMessage).filter(
                ChatMessage.id == reply_to_message_id,
                ChatMessage.room_id == room_id,
                ChatMessage.deleted_at.is_(None)
            ).first()
            if not reply_message:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回复的消息不存在")

        # 4. 处理文件上传
        messages_to_create = []

        # 处理批量文件上传
        if files and len(files) > 0:
            if len(files) > 9:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="一次最多上传9个文件"
                )
            
            for idx, upload_file in enumerate(files):
                if not upload_file.filename:
                    continue
                
                # 读取文件内容
                file_bytes = await upload_file.read()
                content_type = upload_file.content_type or 'application/octet-stream'
                
                # 安全验证
                await validate_file_security(file_bytes, upload_file.filename, content_type)
                
                # 生成安全文件名
                secure_filename = await generate_secure_filename(upload_file.filename, current_user_id)
                
                # 确定文件类型和存储路径
                if content_type.startswith('image/'):
                    msg_type = "image"
                    oss_path = f"chat_images/{secure_filename}"
                elif content_type.startswith('video/'):
                    msg_type = "video"
                    oss_path = f"chat_videos/{secure_filename}"
                elif content_type.startswith('audio/'):
                    msg_type = "audio"
                    oss_path = f"chat_audios/{secure_filename}"
                else:
                    msg_type = "file"
                    oss_path = f"chat_files/{secure_filename}"

                uploaded_files_for_rollback.append(oss_path)
                
                try:
                    media_url = await oss_utils.upload_file_to_oss(
                        file_bytes=file_bytes,
                        object_name=oss_path,
                        content_type=content_type
                    )
                    
                    # 生成消息内容
                    if idx == 0 and content_text:
                        message_content = content_text
                    else:
                        if msg_type == "image":
                            message_content = f"[图片] {upload_file.filename}"
                        elif msg_type == "video":
                            message_content = f"[视频] {upload_file.filename}"
                        elif msg_type == "audio":
                            message_content = f"[音频] {upload_file.filename}"
                        else:
                            message_content = f"[文件] {upload_file.filename}"
                    
                    messages_to_create.append({
                        'content_text': message_content,
                        'message_type': msg_type,
                        'media_url': media_url,
                        'file_size': len(file_bytes),
                        'original_filename': upload_file.filename,
                        'audio_duration': audio_duration if msg_type == "audio" else None
                    })
                    
                except Exception as e:
                    print(f"ERROR: 上传文件 {upload_file.filename} 失败: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"文件上传失败: {upload_file.filename}"
                    )

        # 处理单文件上传
        elif file and file.filename:
            file_bytes = await file.read()
            content_type = file.content_type or 'application/octet-stream'
            
            # 安全验证
            await validate_file_security(file_bytes, file.filename, content_type)
            
            # 生成安全文件名
            secure_filename = await generate_secure_filename(file.filename, current_user_id)
            
            # 确定文件类型和存储路径
            if content_type.startswith('image/'):
                final_message_type = "image"
                oss_path = f"chat_images/{secure_filename}"
            elif content_type.startswith('video/'):
                final_message_type = "video"
                oss_path = f"chat_videos/{secure_filename}"
            elif content_type.startswith('audio/'):
                final_message_type = "audio"
                oss_path = f"chat_audios/{secure_filename}"
            else:
                final_message_type = "file"
                oss_path = f"chat_files/{secure_filename}"

            uploaded_files_for_rollback.append(oss_path)

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=oss_path,
                    content_type=content_type
                )

                # 设置消息内容
                if not content_text:
                    if final_message_type == "image":
                        final_content_text = f"[图片] {file.filename}"
                    elif final_message_type == "video":
                        final_content_text = f"[视频] {file.filename}"
                    elif final_message_type == "audio":
                        final_content_text = f"[音频] {file.filename}"
                    else:
                        final_content_text = f"[文件] {file.filename}"
                else:
                    final_content_text = content_text

                messages_to_create.append({
                    'content_text': final_content_text,
                    'message_type': final_message_type,
                    'media_url': final_media_url,
                    'file_size': len(file_bytes),
                    'original_filename': file.filename,
                    'audio_duration': audio_duration if final_message_type == "audio" else None
                })

            except Exception as e:
                print(f"ERROR: 上传文件失败: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"文件上传失败: {e}"
                )

        # 处理纯文本消息
        else:
            if message_type == "text" and not content_text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="文本消息内容不能为空"
                )
            
            messages_to_create.append({
                'content_text': content_text,
                'message_type': message_type,
                'media_url': media_url,
                'file_size': file_size,
                'original_filename': None,
                'audio_duration': audio_duration if message_type == "audio" else None
            })

        # 5. 批量创建消息记录
        created_messages = []
        for msg_data in messages_to_create:
            db_message = ChatMessage(
                room_id=room_id,
                sender_id=current_user_id,
                content_text=msg_data['content_text'],
                message_type=msg_data['message_type'],
                media_url=msg_data['media_url'],
                reply_to_message_id=reply_to_message_id,
                file_size=msg_data['file_size'],
                original_filename=msg_data['original_filename'],
                audio_duration=msg_data['audio_duration']
            )
            db.add(db_message)
            created_messages.append(db_message)

        # 更新聊天室时间
        db_room.updated_at = func.now()
        db.add(db_room)
        db.flush()

        # 6. 积分奖励
        chat_message_points = len(created_messages)
        await _award_points(
            db=db,
            user=db_sender,
            amount=chat_message_points,
            reason=f"发送{len(created_messages)}条聊天消息",
            transaction_type="EARN",
            related_entity_type="chat_message",
            related_entity_id=created_messages[0].id if created_messages else None
        )
        await _check_and_award_achievements(db, current_user_id)

        db.commit()

        # 7. 填充响应数据并WebSocket推送
        for msg in created_messages:
            db.refresh(msg)
            msg.sender_name = db_sender.name
            
            # 构建WebSocket消息
            ws_message = {
                "type": "chat_message",
                "id": msg.id,
                "room_id": room_id,
                "sender_id": current_user_id,
                "sender_name": db_sender.name,
                "content": msg.content_text,
                "message_type": msg.message_type,
                "media_url": msg.media_url,
                "sent_at": msg.sent_at.isoformat(),
                "reply_to_message_id": reply_to_message_id,
                "reply_to_message": {
                    "id": reply_message.id,
                    "content": reply_message.content_text[:50] + "..." if len(reply_message.content_text) > 50 else reply_message.content_text,
                    "sender_name": reply_message.sender.name
                } if reply_message else None
            }
            
            # 广播到WebSocket连接
            asyncio.create_task(manager.broadcast(json.dumps(ws_message), room_id))

        # 8. 添加后台任务
        background_tasks.add_task(cleanup_expired_files, db)

        print(f"DEBUG: 聊天室 {room_id} 收到 {len(created_messages)} 条消息")
        
        return created_messages[0] if created_messages else None

    except HTTPException:
        db.rollback()
        # 清理已上传的文件
        for file_key in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(file_key))
        raise
    except Exception as e:
        db.rollback()
        # 清理已上传的文件
        for file_key in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(file_key))
        print(f"ERROR: 发送聊天消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发送消息失败: {str(e)}"
        )
@router.post("/chatrooms/{room_id}/upload-audio/", response_model=schemas.ChatMessageResponse,
          summary="上传音频消息（仿微信语音）")
async def upload_audio_message(
        room_id: int,
        audio_file: UploadFile = File(..., description="音频文件（支持mp3, wav, m4a, aac, ogg, webm格式）"),
        duration: Optional[float] = Form(None, description="音频时长（秒）"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    上传音频消息，模拟微信语音功能。
    支持格式：mp3, wav, m4a, aac, ogg, webm
    """
    try:
        # 验证音频文件格式
        if not audio_file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="音频文件名不能为空")
        
        file_ext = os.path.splitext(audio_file.filename)[1].lower()
        SUPPORTED_AUDIO_FORMATS = ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.webm']
        
        if file_ext not in SUPPORTED_AUDIO_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的音频格式: {file_ext}。支持的格式: {', '.join(SUPPORTED_AUDIO_FORMATS)}"
            )

        # 验证权限
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权在该聊天室发送消息")

        # 上传音频文件
        file_bytes = await audio_file.read()
        object_name = f"chat_audios/{uuid.uuid4().hex}{file_ext}"
        
        try:
            media_url = await oss_utils.upload_file_to_oss(
                file_bytes=file_bytes,
                object_name=object_name,
                content_type=audio_file.content_type or 'audio/mpeg'
            )
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"音频上传失败: {e}")

        # 创建音频消息
        db_message = ChatMessage(
            room_id=room_id,
            sender_id=current_user_id,
            content_text=f"语音消息",
            message_type="audio",
            media_url=media_url,
            file_size=len(file_bytes),
            original_filename=audio_file.filename,
            audio_duration=duration
        )
        
        db.add(db_message)
        db_room.updated_at = func.now()
        db.add(db_room)
        db.commit()
        db.refresh(db_message)

        # 填充发送者姓名
        sender = db.query(Student).filter(Student.id == current_user_id).first()
        db_message.sender_name = sender.name if sender else "未知用户"

        return db_message

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 上传音频消息失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"上传音频消息失败: {e}")


@router.post("/chatrooms/{room_id}/upload-gallery/", response_model=List[schemas.ChatMessageResponse],
          summary="批量上传图片/视频（仿微信相册选择）")
async def upload_gallery_media(
        room_id: int,
        files: List[UploadFile] = File(..., description="图片或视频文件列表（最多9个）"),
        caption: Optional[str] = Form(None, description="图片/视频描述文字"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    批量上传图片或视频，模拟微信相册选择功能。
    最多支持一次上传9个文件。
    """
    uploaded_files_for_rollback = []
    
    try:
        if len(files) > 9:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="一次最多上传9个文件")
        
        if len(files) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少需要选择一个文件")

        # 验证权限
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权在该聊天室发送消息")

        # 验证文件格式
        SUPPORTED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        SUPPORTED_VIDEO_FORMATS = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv']
        
        created_messages = []
        
        for idx, file in enumerate(files):
            if not file.filename:
                continue
                
            file_ext = os.path.splitext(file.filename)[1].lower()
            
            # 判断文件类型
            if file_ext in SUPPORTED_IMAGE_FORMATS:
                message_type = "image"
                oss_path_prefix = "chat_images"
            elif file_ext in SUPPORTED_VIDEO_FORMATS:
                message_type = "video"
                oss_path_prefix = "chat_videos"
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(SUPPORTED_IMAGE_FORMATS + SUPPORTED_VIDEO_FORMATS)}"
                )

            # 上传文件
            file_bytes = await file.read()
            object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_ext}"
            uploaded_files_for_rollback.append(object_name)
            
            try:
                media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=object_name,
                    content_type=file.content_type or ('image/jpeg' if message_type == 'image' else 'video/mp4')
                )
            except Exception as e:
                # 如果某个文件上传失败，清理已上传的文件
                for obj_name in uploaded_files_for_rollback:
                    asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                                  detail=f"文件 {file.filename} 上传失败: {e}")

            # 创建消息
            content_text = caption if idx == 0 and caption else f"{message_type}: {file.filename}"
            
            db_message = ChatMessage(
                room_id=room_id,
                sender_id=current_user_id,
                content_text=content_text,
                message_type=message_type,
                media_url=media_url,
                file_size=len(file_bytes),
                original_filename=file.filename
            )
            
            db.add(db_message)
            created_messages.append(db_message)

        # 更新聊天室时间并提交
        db_room.updated_at = func.now()
        db.add(db_room)
        db.commit()
        
        # 刷新消息并填充发送者姓名
        sender = db.query(Student).filter(Student.id == current_user_id).first()
        sender_name = sender.name if sender else "未知用户"
        
        for msg in created_messages:
            db.refresh(msg)
            msg.sender_name = sender_name

        return created_messages

    except HTTPException:
        db.rollback()
        # 清理已上传的文件
        for obj_name in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
        raise
    except Exception as e:
        db.rollback()
        # 清理已上传的文件
        for obj_name in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
        print(f"ERROR: 批量上传媒体文件失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"批量上传失败: {e}")


@router.post("/chatrooms/{room_id}/upload-documents/", response_model=List[schemas.ChatMessageResponse],
          summary="上传文档文件（支持多种办公和代码文件格式）")
async def upload_document_files(
        room_id: int,
        files: List[UploadFile] = File(..., description="文档文件列表"),
        description: Optional[str] = Form(None, description="文件描述"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    上传文档文件，支持：
    - 文档类型：txt, md, html, pdf, docx, pptx, xlsx
    - 代码文件：py, js, json, xml, csv 等
    """
    uploaded_files_for_rollback = []
    
    try:
        if len(files) > 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="一次最多上传10个文档文件")

        # 验证权限
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权在该聊天室发送消息")

        # 支持的文档格式
        SUPPORTED_DOC_FORMATS = {
            '.txt': 'text/plain',
            '.md': 'text/markdown', 
            '.html': 'text/html',
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.py': 'text/x-python',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed'
        }
        
        created_messages = []
        
        for idx, file in enumerate(files):
            if not file.filename:
                continue
                
            file_ext = os.path.splitext(file.filename)[1].lower()
            
            if file_ext not in SUPPORTED_DOC_FORMATS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的文档格式: {file_ext}。支持的格式: {', '.join(SUPPORTED_DOC_FORMATS.keys())}"
                )

            # 上传文件
            file_bytes = await file.read()
            object_name = f"chat_files/{uuid.uuid4().hex}{file_ext}"
            uploaded_files_for_rollback.append(object_name)
            
            try:
                media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=object_name,
                    content_type=file.content_type or SUPPORTED_DOC_FORMATS[file_ext]
                )
            except Exception as e:
                # 清理已上传的文件
                for obj_name in uploaded_files_for_rollback:
                    asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                                  detail=f"文件 {file.filename} 上传失败: {e}")

            # 创建消息
            content_text = description if idx == 0 and description else f"文档: {file.filename}"
            
            db_message = ChatMessage(
                room_id=room_id,
                sender_id=current_user_id,
                content_text=content_text,
                message_type="file",
                media_url=media_url,
                file_size=len(file_bytes),
                original_filename=file.filename
            )
            
            db.add(db_message)
            created_messages.append(db_message)

        # 更新聊天室时间并提交
        db_room.updated_at = func.now()
        db.add(db_room)
        db.commit()
        
        # 刷新消息并填充发送者姓名
        sender = db.query(Student).filter(Student.id == current_user_id).first()
        sender_name = sender.name if sender else "未知用户"
        
        for msg in created_messages:
            db.refresh(msg)
            msg.sender_name = sender_name

        return created_messages

    except HTTPException:
        db.rollback()
        # 清理已上传的文件
        for obj_name in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
        raise
    except Exception as e:
        db.rollback()
        # 清理已上传的文件
        for obj_name in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(obj_name))
        print(f"ERROR: 上传文档文件失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"上传文档失败: {e}")


@router.get("/chatrooms/{room_id}/messages/", response_model=List[schemas.ChatMessageResponse],
         summary="获取指定聊天室的历史消息（增强分页版）")
async def get_chat_messages(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = Query(SecurityConfig.DEFAULT_MESSAGES_PER_PAGE, ge=1, le=SecurityConfig.MAX_MESSAGES_PER_PAGE, description="每页消息数量"),
        cursor: Optional[int] = Query(None, description="游标分页的消息ID，获取此ID之前的消息"),
        message_type: Optional[str] = Query(None, description="按消息类型过滤"),
        search: Optional[str] = Query(None, description="搜索消息内容"),
        pinned_only: bool = Query(False, description="只获取置顶消息"),
        include_deleted: bool = Query(False, description="是否包含已删除消息（仅群主可用）")
):
    """
    获取指定聊天室的历史消息。
    
    功能特性：
    - 高效分页加载（游标分页）
    - 消息类型过滤
    - 消息内容搜索
    - 置顶消息筛选
    - 懒加载机制
    - 权限控制
    """
    print(f"DEBUG: 获取聊天室 {room_id} 的历史消息，用户 {current_user_id}，游标: {cursor}")

    try:
        # 1. 权限验证
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效")

        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        # 权限检查：用户是否是群主、活跃成员或系统管理员
        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member or current_user.is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="您无权查看该聊天室的历史消息"
            )

        # 2. 构建基础查询
        query = db.query(ChatMessage).filter(ChatMessage.room_id == room_id)
        
        # 是否包含已删除消息（仅群主可见）
        if not include_deleted or not is_creator:
            query = query.filter(ChatMessage.deleted_at.is_(None))
        
        # 游标分页
        if cursor:
            query = query.filter(ChatMessage.id < cursor)
        
        # 消息类型过滤
        if message_type:
            query = query.filter(ChatMessage.message_type == message_type)
        
        # 置顶消息过滤
        if pinned_only:
            query = query.filter(ChatMessage.is_pinned == True)
        
        # 消息内容搜索
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(ChatMessage.content_text.ilike(search_pattern))

        # 预加载关联数据，避免N+1查询
        query = query.options(
            joinedload(ChatMessage.reply_to),
            joinedload(ChatMessage.sender)
        )

        # 排序和限制
        messages = query.order_by(desc(ChatMessage.sent_at)).limit(limit).all()

        # 3. 填充响应数据
        response_messages = []
        for msg in messages:
            # 填充发送者姓名
            msg.sender_name = msg.sender.name if msg.sender else "未知用户"
            
            # 填充回复消息信息
            if msg.reply_to:
                msg.reply_to.sender_name = msg.reply_to.sender.name if msg.reply_to.sender else "未知用户"
                msg.reply_to_message = msg.reply_to
            
            response_messages.append(msg)

        # 4. 返回正序消息（最旧的在前，最新的在后）
        response_messages.reverse()

        # 5. 计算下一页游标
        next_cursor = None
        if len(response_messages) == limit and response_messages:
            next_cursor = response_messages[0].id  # 最旧消息的ID

        print(f"DEBUG: 聊天室 {room_id} 获取到 {len(response_messages)} 条历史消息")

        # 6. 设置响应头
        response = JSONResponse(
            content=[msg.__dict__ for msg in response_messages] if response_messages else [],
            headers={
                "X-Next-Cursor": str(next_cursor) if next_cursor else "",
                "X-Has-More": "true" if next_cursor else "false",
                "X-Message-Count": str(len(response_messages))
            }
        )
        
        return response_messages

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: 获取聊天消息时发生错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取聊天消息失败，请稍后重试"
        )


@router.put("/chatrooms/{room_id}/messages/{message_id}/recall", 
         response_model=schemas.ChatMessageResponse,
         summary="撤回消息（仿微信撤回功能）")
async def recall_message(
        room_id: int,
        message_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    撤回消息功能，类似微信。
    只有消息发送者可以撤回，且有时间限制（2分钟内）。
    """
    try:
        # 查询要撤回的消息
        db_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)
        ).first()

        if not db_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息未找到或已被删除")

        # 权限检查：只有消息发送者可以撤回
        if db_message.sender_id != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能撤回自己发送的消息")

        # 时间限制检查：2分钟内可撤回
        from datetime import timedelta
        time_limit = timedelta(minutes=2)
        if datetime.now() - db_message.sent_at > time_limit:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息发送超过2分钟，无法撤回")

        # 更新消息为撤回状态
        db_message.content_text = "消息已撤回"
        db_message.message_type = "system_notification"
        db_message.media_url = None  # 清除媒体链接
        db_message.edited_at = func.now()
        
        db.add(db_message)
        db.commit()
        db.refresh(db_message)

        # 填充发送者姓名
        sender = db.query(Student).filter(Student.id == current_user_id).first()
        db_message.sender_name = sender.name if sender else "未知用户"

        return db_message

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 撤回消息失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"撤回消息失败: {e}")


@router.put("/chatrooms/{room_id}/messages/{message_id}/pin",
         summary="置顶/取消置顶消息")
async def toggle_pin_message(
        room_id: int,
        message_id: int,
        pin: bool = Query(..., description="true为置顶，false为取消置顶"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    置顶或取消置顶消息。
    只有群主和管理员可以执行此操作。
    """
    try:
        # 权限检查
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        is_creator = (db_room.creator_id == current_user_id)
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first()
        is_admin = member and member.role == "admin"

        if not (is_creator or is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有群主和管理员可以置顶消息")

        # 查询消息
        db_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)
        ).first()

        if not db_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息未找到")

        # 更新置顶状态
        db_message.is_pinned = pin
        db.add(db_message)
        db.commit()

        return {"message": f"消息已{'置顶' if pin else '取消置顶'}"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 置顶消息操作失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"置顶操作失败: {e}")


@router.post("/chatrooms/{room_id}/messages/{message_id}/forward",
          response_model=schemas.ChatMessageResponse,
          summary="转发消息到其他聊天室")
async def forward_message(
        room_id: int,
        message_id: int,
        target_room_id: int = Form(..., description="目标聊天室ID"),
        additional_text: Optional[str] = Form(None, description="转发时添加的额外文字"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    转发消息到其他聊天室。
    """
    try:
        # 验证源消息
        source_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)
        ).first()

        if not source_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源消息未找到")

        # 验证源聊天室权限
        source_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not source_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源聊天室未找到")

        is_source_creator = (source_room.creator_id == current_user_id)
        is_source_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_source_creator or is_source_member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问源聊天室")

        # 验证目标聊天室权限
        target_room = db.query(ChatRoom).filter(ChatRoom.id == target_room_id).first()
        if not target_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标聊天室未找到")

        is_target_creator = (target_room.creator_id == current_user_id)
        is_target_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == target_room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_target_creator or is_target_member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权在目标聊天室发送消息")

        # 创建转发消息
        forward_content = f"[转发] {source_message.content_text}"
        if additional_text:
            forward_content = f"{additional_text}\n\n{forward_content}"

        forwarded_message = ChatMessage(
            room_id=target_room_id,
            sender_id=current_user_id,
            content_text=forward_content,
            message_type=source_message.message_type,
            media_url=source_message.media_url,
            file_size=source_message.file_size,
            original_filename=source_message.original_filename,
            audio_duration=source_message.audio_duration
        )

        db.add(forwarded_message)
        target_room.updated_at = func.now()
        db.add(target_room)
        db.commit()
        db.refresh(forwarded_message)

        # 填充发送者姓名
        sender = db.query(Student).filter(Student.id == current_user_id).first()
        forwarded_message.sender_name = sender.name if sender else "未知用户"

        return forwarded_message

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 转发消息失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"转发消息失败: {e}")


@router.get("/chatrooms/{room_id}/media", response_model=List[schemas.ChatMessageResponse],
         summary="获取聊天室中的所有媒体文件")
async def get_chat_media(
        room_id: int,
        media_type: Optional[str] = Query(None, description="媒体类型过滤：image/video/audio/file"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = Query(50, description="限制返回数量"),
        offset: int = Query(0, description="偏移量")
):
    """
    获取聊天室中的所有媒体文件，用于媒体浏览。
    """
    try:
        # 权限检查
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该聊天室内容")

        # 构建查询
        query = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None),
            ChatMessage.media_url.isnot(None)  # 只获取有媒体的消息
        )

        # 按媒体类型过滤
        if media_type:
            query = query.filter(ChatMessage.message_type == media_type)

        # 执行查询
        media_messages = query.order_by(ChatMessage.sent_at.desc()) \
            .offset(offset).limit(limit).all()

        # 填充发送者姓名
        sender_ids = list(set([msg.sender_id for msg in media_messages]))
        senders_map = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(sender_ids)).all()} if sender_ids else {}

        for msg in media_messages:
            msg.sender_name = senders_map.get(msg.sender_id, "未知用户")

        return media_messages

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: 获取聊天室媒体文件失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取媒体文件失败: {e}")


@router.delete("/chatrooms/{room_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT,
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


# --- 增强版 WebSocket 聊天室接口 ---
@router.websocket("/ws_chat/{room_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        room_id: int,
        token: str = Query(..., description="用户JWT认证令牌"),
        db: Session = Depends(get_db)
):
    """
    增强版 WebSocket 聊天接口，支持：
    - 实时消息推送
    - 心跳检测
    - 连接状态管理
    - 在线用户统计
    - 输入状态提示
    - 安全连接验证
    """
    print(f"DEBUG_WS: 尝试连接房间 {room_id}")
    current_user_id = None
    current_user = None
    
    try:
        # 1. JWT令牌验证
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id_str = payload.get("sub")
            if not user_id_str:
                raise WebSocketDisconnect(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Invalid token: missing subject"
                )
            
            current_user_id = int(user_id_str)
        except (JWTError, ValueError) as e:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason=f"Authentication failed: {e}"
            )
            return

        # 2. 用户验证
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="User not found"
            )
            return

        # 3. 聊天室验证
        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            await websocket.close(
                code=status.WS_1003_UNSUPPORTED_DATA,
                reason="聊天室不存在"
            )
            return

        # 4. 权限验证
        is_creator = (chat_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member):
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="您无权访问此聊天室"
            )
            return

        # 5. 建立连接
        connection_success = await manager.connect(websocket, room_id, current_user_id)
        if not connection_success:
            return

        print(f"DEBUG_WS: 用户 {current_user_id} 成功连接聊天室 {room_id}")

        # 6. 发送欢迎消息
        welcome_message = {
            "type": "system",
            "content": f"欢迎 {current_user.name} 加入聊天室！",
            "timestamp": datetime.now().isoformat(),
            "room_info": {
                "id": chat_room.id,
                "name": chat_room.name,
                "type": chat_room.type,
                "online_members": len(manager.active_connections.get(room_id, {}))
            }
        }
        await manager.send_personal_message(json.dumps(welcome_message), websocket)

        # 7. 向其他用户广播加入通知
        join_notification = {
            "type": "user_joined",
            "user_id": current_user_id,
            "user_name": current_user.name,
            "content": f"{current_user.name} 加入了聊天室",
            "timestamp": datetime.now().isoformat(),
            "online_members_count": len(manager.active_connections.get(room_id, {}))
        }
        await manager.broadcast(json.dumps(join_notification), room_id, exclude_user_id=current_user_id)

        # 8. 心跳检测任务
        async def heartbeat_task():
            while True:
                try:
                    await asyncio.sleep(SecurityConfig.HEARTBEAT_INTERVAL)
                    heartbeat_msg = {
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat()
                    }
                    await manager.send_personal_message(json.dumps(heartbeat_msg), websocket)
                except:
                    break

        # 启动心跳任务
        heartbeat_job = asyncio.create_task(heartbeat_task())

        # 9. 消息处理循环
        try:
            while True:
                # 接收客户端消息
                data = await websocket.receive_json()
                message_type = data.get("type", "chat")
                
                # 更新心跳
                manager.update_heartbeat(room_id, current_user_id)
                
                if message_type == "chat":
                    await handle_chat_message(data, room_id, current_user_id, current_user, db)
                    
                elif message_type == "typing":
                    await handle_typing_status(data, room_id, current_user_id, current_user)
                    
                elif message_type == "heartbeat_response":
                    # 客户端心跳响应，更新心跳时间
                    manager.update_heartbeat(room_id, current_user_id)
                    
                elif message_type == "file_upload_notification":
                    await handle_file_upload_notification(data, room_id, current_user_id, current_user)
                    
                elif message_type == "message_read":
                    await handle_message_read(data, room_id, current_user_id, db)
                    
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {message_type}"
                    })

        except WebSocketDisconnect:
            print(f"DEBUG_WS: 用户 {current_user_id} 主动断开连接")
        except Exception as e:
            print(f"ERROR_WS: WebSocket连接异常: {e}")
            await websocket.send_json({
                "type": "error",
                "message": f"服务器内部错误: {str(e)}"
            })
        finally:
            # 取消心跳任务
            heartbeat_job.cancel()
            
            # 广播用户离开消息
            if current_user_id and current_user:
                leave_notification = {
                    "type": "user_left",
                    "user_id": current_user_id,
                    "user_name": current_user.name,
                    "content": f"{current_user.name} 离开了聊天室",
                    "timestamp": datetime.now().isoformat(),
                    "online_members_count": len(manager.active_connections.get(room_id, {})) - 1
                }
                await manager.broadcast(json.dumps(leave_notification), room_id)
            
            # 断开连接
            manager.disconnect(room_id, current_user_id)

    except Exception as e:
        print(f"ERROR_WS: WebSocket初始化异常: {e}")
        if websocket.client_state.name == "CONNECTED":
            await websocket.close(
                code=status.WS_1011_INTERNAL_ERROR,
                reason=f"服务器内部错误: {str(e)}"
            )


async def handle_chat_message(data: dict, room_id: int, user_id: int, user: Student, db: Session):
    """处理聊天消息"""
    message_content = data.get("content")
    reply_to_id = data.get("reply_to_message_id")

    if not message_content or not isinstance(message_content, str):
        return

    # 再次验证权限
    is_active = db.query(ChatRoomMember).filter(
        ChatRoomMember.room_id == room_id,
        ChatRoomMember.member_id == user_id,
        ChatRoomMember.status == "active"
    ).first() is not None

    if not is_active:
        return

    # 验证回复消息
    reply_message = None
    if reply_to_id:
        reply_message = db.query(ChatMessage).filter(
            ChatMessage.id == reply_to_id,
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)
        ).first()

    # 创建消息记录
    db_message = ChatMessage(
        room_id=room_id,
        sender_id=user_id,
        content_text=message_content,
        message_type="text",
        reply_to_message_id=reply_to_id if reply_message else None
    )
    db.add(db_message)
    
    # 更新聊天室活跃时间
    chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if chat_room:
        chat_room.updated_at = func.now()
        db.add(chat_room)
    
    db.commit()
    db.refresh(db_message)

    # 构建广播消息
    broadcast_message = {
        "type": "chat_message",
        "id": db_message.id,
        "room_id": room_id,
        "sender_id": user_id,
        "sender_name": user.name,
        "content": message_content,
        "message_type": "text",
        "sent_at": db_message.sent_at.isoformat(),
        "reply_to_message_id": reply_to_id,
        "reply_to_message": {
            "id": reply_message.id,
            "content": reply_message.content_text[:50] + "..." if len(reply_message.content_text) > 50 else reply_message.content_text,
            "sender_name": reply_message.sender.name
        } if reply_message else None
    }
    
    await manager.broadcast(json.dumps(broadcast_message), room_id)


async def handle_typing_status(data: dict, room_id: int, user_id: int, user: Student):
    """处理用户输入状态"""
    typing_message = {
        "type": "typing",
        "user_id": user_id,
        "user_name": user.name,
        "is_typing": data.get("is_typing", True),
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(json.dumps(typing_message), room_id, exclude_user_id=user_id)


async def handle_file_upload_notification(data: dict, room_id: int, user_id: int, user: Student):
    """处理文件上传完成通知"""
    file_info = data.get("file_info", {})
    notification_message = {
        "type": "file_uploaded",
        "user_id": user_id,
        "user_name": user.name,
        "file_info": file_info,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(json.dumps(notification_message), room_id)


async def handle_message_read(data: dict, room_id: int, user_id: int, db: Session):
    """处理消息已读状态"""
    message_id = data.get("message_id")
    if not message_id:
        return
    
    # TODO: 实现消息已读状态记录
    # 可以创建一个MessageReadStatus表来记录用户的消息已读状态
    pass


# --- 消息撤回和管理功能 ---
@router.put("/chatrooms/{room_id}/messages/{message_id}/recall", 
         response_model=schemas.ChatMessageResponse,
         summary="撤回消息（增强版）", operation_id="recall_message_enhanced")
async def recall_message_enhanced(
        room_id: int,
        message_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    撤回消息功能，类似微信。
    增强特性：
    - 时间限制检查
    - 权限验证
    - 实时通知
    """
    try:
        # 查询要撤回的消息
        db_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)
        ).first()

        if not db_message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="消息未找到或已被删除"
            )

        # 权限检查：只有消息发送者或群主可以撤回
        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        is_sender = (db_message.sender_id == current_user_id)
        is_creator = (chat_room.creator_id == current_user_id)

        if not (is_sender or is_creator):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="只能撤回自己发送的消息或群主可撤回任何消息"
            )

        # 时间限制检查：发送者2分钟内可撤回，群主无时间限制
        if is_sender and not is_creator:
            time_limit = timedelta(seconds=SecurityConfig.MESSAGE_RECALL_TIME_LIMIT)
            if datetime.now() - db_message.sent_at > time_limit:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"消息发送超过{SecurityConfig.MESSAGE_RECALL_TIME_LIMIT}秒，无法撤回"
                )

        # 执行撤回
        db_message.content_text = "此消息已被撤回"
        db_message.message_type = "system_notification"
        db_message.media_url = None  # 清除媒体链接
        db_message.edited_at = func.now()
        
        db.add(db_message)
        db.commit()
        db.refresh(db_message)

        # 填充发送者姓名
        sender = db.query(Student).filter(Student.id == db_message.sender_id).first()
        db_message.sender_name = sender.name if sender else "未知用户"

        # WebSocket实时通知
        recall_notification = {
            "type": "message_recalled",
            "message_id": message_id,
            "room_id": room_id,
            "recalled_by": current_user_id,
            "timestamp": datetime.now().isoformat()
        }
        asyncio.create_task(manager.broadcast(json.dumps(recall_notification), room_id))

        return db_message

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 撤回消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"撤回消息失败: {str(e)}"
        )


@router.put("/chatrooms/{room_id}/messages/{message_id}/pin",
         summary="置顶/取消置顶消息（增强版）", operation_id="toggle_pin_message_enhanced")
async def toggle_pin_message_enhanced(
        room_id: int,
        message_id: int,
        pin: bool = Query(..., description="true为置顶，false为取消置顶"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    置顶或取消置顶消息。
    增强特性：
    - 置顶数量限制
    - 权限控制
    - 实时通知
    """
    try:
        # 权限检查
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        is_creator = (db_room.creator_id == current_user_id)
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first()
        is_admin = member and member.role == "admin"

        if not (is_creator or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="只有群主和管理员可以置顶消息"
            )

        # 查询消息
        db_message = db.query(ChatMessage).filter(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)
        ).first()

        if not db_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息未找到")

        # 置顶数量限制检查
        if pin:
            pinned_count = db.query(ChatMessage).filter(
                ChatMessage.room_id == room_id,
                ChatMessage.is_pinned == True,
                ChatMessage.deleted_at.is_(None)
            ).count()
            
            if pinned_count >= SecurityConfig.PIN_MESSAGE_LIMIT:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"最多只能置顶{SecurityConfig.PIN_MESSAGE_LIMIT}条消息"
                )

        # 更新置顶状态
        db_message.is_pinned = pin
        db.add(db_message)
        db.commit()

        # WebSocket实时通知
        pin_notification = {
            "type": "message_pinned" if pin else "message_unpinned",
            "message_id": message_id,
            "room_id": room_id,
            "pinned_by": current_user_id,
            "timestamp": datetime.now().isoformat()
        }
        asyncio.create_task(manager.broadcast(json.dumps(pin_notification), room_id))

        return {"message": f"消息已{'置顶' if pin else '取消置顶'}"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"ERROR: 置顶消息操作失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"置顶操作失败: {str(e)}"
        )


# --- 聊天室成员管理 ---
@router.get("/chatrooms/{room_id}/members", response_model=List[schemas.ChatRoomMemberResponse],
         summary="获取指定聊天室的所有成员列表（增强版）", operation_id="get_chat_room_members_enhanced")
async def get_chat_room_members_enhanced(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        status_filter: Optional[str] = Query(None, description="按状态过滤成员"),
        role_filter: Optional[str] = Query(None, description="按角色过滤成员")
):
    """
    获取指定聊天室的所有成员列表。
    增强特性：
    - 状态和角色过滤
    - 在线状态显示
    - 权限控制
    """
    try:
        # 权限验证
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效")

        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        # 权限检查
        is_creator = (chat_room.creator_id == current_user_id)
        is_room_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_room_member or current_user.is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="无权查看该聊天室的成员列表"
            )

        # 构建查询
        query = db.query(ChatRoomMember).options(
            joinedload(ChatRoomMember.member)
        ).filter(ChatRoomMember.room_id == room_id)

        # 应用过滤
        if status_filter:
            query = query.filter(ChatRoomMember.status == status_filter)
        if role_filter:
            query = query.filter(ChatRoomMember.role == role_filter)

        memberships = query.all()

        # 构建响应
        response_members = []
        online_users = manager.active_connections.get(room_id, {})
        
        for membership in memberships:
            member_response = {
                "id": membership.id,
                "room_id": membership.room_id,
                "member_id": membership.member_id,
                "role": membership.role,
                "status": membership.status,
                "joined_at": membership.joined_at,
                "member_name": membership.member.name if membership.member else "未知用户",
                "is_online": membership.member_id in online_users
            }
            response_members.append(schemas.ChatRoomMemberResponse(**member_response))

        print(f"DEBUG: 聊天室 {room_id} 获取到 {len(response_members)} 位成员")
        return response_members

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: 获取聊天室成员列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"获取聊天室成员列表失败: {str(e)}"
        )


# --- 聊天室设置管理 ---
@router.put("/chatrooms/{room_id}/settings", summary="更新聊天室设置")
async def update_chat_room_settings(
        room_id: int,
        allow_file_upload: Optional[bool] = Query(None, description="是否允许文件上传"),
        max_file_size_mb: Optional[int] = Query(None, description="最大文件大小限制(MB)"),
        allowed_file_types: Optional[List[str]] = Query(None, description="允许的文件类型"),
        message_retention_days: Optional[int] = Query(None, description="消息保留天数"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    更新聊天室设置（仅群主可用）
    """
    try:
        # 权限检查
        chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not chat_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

        if chat_room.creator_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="只有群主可以修改聊天室设置"
            )

        # TODO: 实现聊天室设置的数据库存储
        # 这里可以添加一个ChatRoomSettings表来存储这些设置
        
        settings = {
            "allow_file_upload": allow_file_upload,
            "max_file_size_mb": max_file_size_mb,
            "allowed_file_types": allowed_file_types,
            "message_retention_days": message_retention_days
        }

        # 过滤掉None值
        settings = {k: v for k, v in settings.items() if v is not None}

        return {
            "message": "聊天室设置已更新",
            "settings": settings
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: 更新聊天室设置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"更新聊天室设置失败: {str(e)}"
        )


# --- 系统监控和统计 ---
@router.get("/admin/chatroom-stats", summary="获取聊天室统计信息（管理员）")
async def get_chatroom_statistics(
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        days: int = Query(7, description="统计天数")
):
    """
    获取聊天室统计信息（仅管理员可用）
    """
    current_user = db.query(Student).filter(Student.id == current_user_id).first()
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以查看统计信息"
        )

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # 基础统计
        total_rooms = db.query(ChatRoom).count()
        total_messages = db.query(ChatMessage).filter(
            ChatMessage.sent_at >= start_date,
            ChatMessage.deleted_at.is_(None)
        ).count()
        
        active_users = db.query(ChatMessage.sender_id).filter(
            ChatMessage.sent_at >= start_date
        ).distinct().count()

        # 存储统计
        total_file_size = db.query(func.sum(ChatMessage.file_size)).filter(
            ChatMessage.file_size.isnot(None),
            ChatMessage.deleted_at.is_(None)
        ).scalar() or 0

        # WebSocket连接统计
        active_connections = sum(len(connections) for connections in manager.active_connections.values())
        
        return {
            "period_days": days,
            "total_chatrooms": total_rooms,
            "total_messages": total_messages,
            "active_users": active_users,
            "total_file_size_mb": round(total_file_size / (1024 * 1024), 2),
            "active_websocket_connections": active_connections,
            "active_rooms_with_connections": len(manager.active_connections)
        }

    except Exception as e:
        print(f"ERROR: 获取聊天室统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )