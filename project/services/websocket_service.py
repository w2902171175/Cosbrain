# project/services/websocket_service.py
import logging
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from websockets.exceptions import ConnectionClosed
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from datetime import datetime

from project.database import get_db
from project.utils import get_current_user_id
from project.models import ChatRoom, ChatRoomMember, ChatMessage, User
from project.services.message_service import MessageService
from project.utils.security.permissions import check_room_access
from project.utils.async_cache.cache import cache
from jose import JWTError, jwt
from project.utils import SECRET_KEY, ALGORITHM

logger = logging.getLogger(__name__)
router = APIRouter()

class EnhancedConnectionManager:
    """增强的WebSocket连接管理器"""
    
    def __init__(self):
        # 房间连接：room_id -> {user_id: websocket}
        self.room_connections: Dict[int, Dict[int, WebSocket]] = {}
        # 用户连接：user_id -> {room_id: websocket}
        self.user_connections: Dict[int, Dict[int, WebSocket]] = {}
        # 连接元数据
        self.connection_metadata: Dict[str, Dict] = {}
    
    async def connect(self, websocket: WebSocket, room_id: int, user_id: int):
        """建立WebSocket连接"""
        await websocket.accept()
        
        # 初始化房间连接
        if room_id not in self.room_connections:
            self.room_connections[room_id] = {}
        
        # 初始化用户连接
        if user_id not in self.user_connections:
            self.user_connections[user_id] = {}
        
        # 存储连接
        self.room_connections[room_id][user_id] = websocket
        self.user_connections[user_id][room_id] = websocket
        
        # 存储连接元数据
        connection_id = f"{room_id}_{user_id}"
        self.connection_metadata[connection_id] = {
            "room_id": room_id,
            "user_id": user_id,
            "connected_at": datetime.now(),
            "last_activity": datetime.now()
        }
        
        # 添加到在线用户缓存
        await cache.add_online_user(room_id, user_id)
        
        logger.info(f"用户 {user_id} 连接到聊天室 {room_id}")
    
    async def disconnect(self, room_id: int, user_id: int):
        """断开WebSocket连接"""
        # 移除房间连接
        if room_id in self.room_connections:
            self.room_connections[room_id].pop(user_id, None)
            if not self.room_connections[room_id]:
                del self.room_connections[room_id]
        
        # 移除用户连接
        if user_id in self.user_connections:
            self.user_connections[user_id].pop(room_id, None)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        # 移除连接元数据
        connection_id = f"{room_id}_{user_id}"
        self.connection_metadata.pop(connection_id, None)
        
        # 从在线用户缓存中移除
        await cache.remove_online_user(room_id, user_id)
        
        logger.info(f"用户 {user_id} 从聊天室 {room_id} 断开连接")
    
    async def send_personal_message(self, message: str, user_id: int, room_id: int):
        """发送个人消息"""
        if room_id in self.room_connections and user_id in self.room_connections[room_id]:
            websocket = self.room_connections[room_id][user_id]
            try:
                await websocket.send_text(message)
                # 更新活动时间
                connection_id = f"{room_id}_{user_id}"
                if connection_id in self.connection_metadata:
                    self.connection_metadata[connection_id]["last_activity"] = datetime.now()
            except Exception as e:
                logger.error(f"发送个人消息失败: {e}")
                await self.disconnect(room_id, user_id)
    
    async def broadcast_to_room(self, message: str, room_id: int, exclude_user: Optional[int] = None):
        """向房间广播消息 - 优化版本"""
        if room_id not in self.room_connections:
            return
        
        # 使用asyncio.gather进行并发发送
        import asyncio
        
        async def send_to_user(user_id: int, websocket: WebSocket):
            if exclude_user and user_id == exclude_user:
                return True
            
            try:
                await websocket.send_text(message)
                # 更新活动时间
                connection_id = f"{room_id}_{user_id}"
                if connection_id in self.connection_metadata:
                    self.connection_metadata[connection_id]["last_activity"] = datetime.now()
                return True
            except Exception as e:
                logger.error(f"广播消息失败 (用户 {user_id}): {e}")
                return False
        
        # 并发发送消息
        tasks = [
            send_to_user(user_id, websocket) 
            for user_id, websocket in self.room_connections[room_id].items()
        ]
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 清理断开的连接
            failed_users = [
                user_id for i, (user_id, _) in enumerate(self.room_connections[room_id].items())
                if not results[i] or isinstance(results[i], Exception)
            ]
            
            for user_id in failed_users:
                await self.disconnect(room_id, user_id)
    
    async def get_room_online_users(self, room_id: int) -> List[int]:
        """获取房间在线用户列表"""
        if room_id in self.room_connections:
            return list(self.room_connections[room_id].keys())
        return []
    
    async def get_user_active_rooms(self, user_id: int) -> List[int]:
        """获取用户活跃的房间列表"""
        if user_id in self.user_connections:
            return list(self.user_connections[user_id].keys())
        return []
    
    async def cleanup_expired_connections(self, max_idle_minutes: int = 30):
        """清理过期连接"""
        current_time = datetime.now()
        expired_connections = []
        
        for connection_id, metadata in self.connection_metadata.items():
            idle_time = current_time - metadata["last_activity"]
            if idle_time.total_seconds() > (max_idle_minutes * 60):
                expired_connections.append((metadata["room_id"], metadata["user_id"]))
        
        for room_id, user_id in expired_connections:
            await self.disconnect(room_id, user_id)
        
        logger.info(f"清理了 {len(expired_connections)} 个过期连接")
    
    def get_connection_stats(self) -> Dict:
        """获取连接统计信息"""
        total_connections = sum(len(users) for users in self.room_connections.values())
        active_rooms = len(self.room_connections)
        active_users = len(self.user_connections)
        
        return {
            "total_connections": total_connections,
            "active_rooms": active_rooms,
            "active_users": active_users,
            "rooms_detail": {
                room_id: len(users) 
                for room_id, users in self.room_connections.items()
            }
        }

# 全局连接管理器实例
manager = EnhancedConnectionManager()

async def get_user_from_token(token: str, db: Session) -> Optional[int]:
    """从token获取用户ID"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            return None
        
        # 验证用户是否存在
        user = db.query(User).filter(User.id == user_id).first()
        return user.id if user else None
    except JWTError:
        return None

@router.websocket("/ws_chat/{room_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket, 
    room_id: int,
    token: str,
    db: Session = Depends(get_db)
):
    """WebSocket聊天端点"""
    current_user_id = None
    
    try:
        # 验证token
        current_user_id = await get_user_from_token(token, db)
        if not current_user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="无效的认证信息")
            return
        
        # 检查房间访问权限
        try:
            check_room_access(db, room_id, current_user_id)
        except HTTPException:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="没有访问权限")
            return
        
        # 建立连接
        await manager.connect(websocket, room_id, current_user_id)
        
        # 发送连接成功消息
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_established",
                "room_id": room_id,
                "user_id": current_user_id,
                "timestamp": datetime.now().isoformat()
            }),
            current_user_id,
            room_id
        )
        
        # 通知其他用户有新用户加入
        online_users = await manager.get_room_online_users(room_id)
        await manager.broadcast_to_room(
            json.dumps({
                "type": "user_joined",
                "user_id": current_user_id,
                "online_users": online_users,
                "timestamp": datetime.now().isoformat()
            }),
            room_id,
            exclude_user=current_user_id
        )
        
        # 监听消息
        while True:
            try:
                # 接收消息
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # 处理不同类型的消息
                await handle_websocket_message(
                    message_data, room_id, current_user_id, db, websocket
                )
                
            except WebSocketDisconnect:
                logger.info(f"用户 {current_user_id} 主动断开WebSocket连接")
                break
            except ConnectionClosed:
                logger.info(f"用户 {current_user_id} 的WebSocket连接已关闭")
                break
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps({
                        "type": "error",
                        "message": "无效的JSON格式"
                    }),
                    current_user_id,
                    room_id
                )
            except Exception as e:
                logger.error(f"处理WebSocket消息时出错: {e}")
                await manager.send_personal_message(
                    json.dumps({
                        "type": "error",
                        "message": "处理消息时出错"
                    }),
                    current_user_id,
                    room_id
                )
    
    except Exception as e:
        logger.error(f"WebSocket连接异常: {e}")
    
    finally:
        # 清理连接
        if current_user_id:
            await manager.disconnect(room_id, current_user_id)
            
            # 通知其他用户有用户离开
            online_users = await manager.get_room_online_users(room_id)
            await manager.broadcast_to_room(
                json.dumps({
                    "type": "user_left",
                    "user_id": current_user_id,
                    "online_users": online_users,
                    "timestamp": datetime.now().isoformat()
                }),
                room_id
            )

async def handle_websocket_message(
    message_data: Dict, 
    room_id: int, 
    user_id: int, 
    db: Session,
    websocket: WebSocket
):
    """处理WebSocket消息"""
    message_type = message_data.get("type")
    
    if message_type == "chat_message":
        await handle_chat_message(message_data, room_id, user_id, db)
    elif message_type == "typing":
        await handle_typing_indicator(message_data, room_id, user_id)
    elif message_type == "ping":
        await handle_ping(room_id, user_id)
    elif message_type == "get_online_users":
        await handle_get_online_users(room_id, user_id)
    else:
        await manager.send_personal_message(
            json.dumps({
                "type": "error",
                "message": f"未知的消息类型: {message_type}"
            }),
            user_id,
            room_id
        )

async def handle_chat_message(message_data: Dict, room_id: int, user_id: int, db: Session):
    """处理聊天消息"""
    try:
        content = message_data.get("content", "").strip()
        reply_to_id = message_data.get("reply_to_id")
        
        if not content:
            return
        
        # 创建消息记录
        db_message = await MessageService.create_message_async(
            db=db,
            room_id=room_id,
            sender_id=user_id,
            content=content,
            message_type="text",
            reply_to_id=reply_to_id
        )
        
        # 添加到缓存
        await cache.add_recent_message(room_id, db_message.__dict__)
        
        # 获取发送者信息
        sender = db.query(User).filter(User.id == user_id).first()
        
        # 构建广播消息
        broadcast_message = {
            "type": "new_message",
            "message_id": db_message.id,
            "room_id": room_id,
            "sender_id": user_id,
            "sender_name": sender.name if sender else "未知用户",
            "content": content,
            "message_type": "text",
            "reply_to_id": reply_to_id,
            "created_at": db_message.created_at.isoformat(),
            "timestamp": datetime.now().isoformat()
        }
        
        # 广播消息到房间
        await manager.broadcast_to_room(
            json.dumps(broadcast_message),
            room_id
        )
        
    except Exception as e:
        logger.error(f"处理聊天消息失败: {e}")
        await manager.send_personal_message(
            json.dumps({
                "type": "error",
                "message": "发送消息失败"
            }),
            user_id,
            room_id
        )

async def handle_typing_indicator(message_data: Dict, room_id: int, user_id: int):
    """处理打字指示器"""
    is_typing = message_data.get("is_typing", False)
    
    # 广播打字状态
    await manager.broadcast_to_room(
        json.dumps({
            "type": "typing_indicator",
            "user_id": user_id,
            "is_typing": is_typing,
            "timestamp": datetime.now().isoformat()
        }),
        room_id,
        exclude_user=user_id
    )

async def handle_ping(room_id: int, user_id: int):
    """处理心跳包"""
    await manager.send_personal_message(
        json.dumps({
            "type": "pong",
            "timestamp": datetime.now().isoformat()
        }),
        user_id,
        room_id
    )

async def handle_get_online_users(room_id: int, user_id: int):
    """处理获取在线用户请求"""
    online_users = await manager.get_room_online_users(room_id)
    
    await manager.send_personal_message(
        json.dumps({
            "type": "online_users",
            "room_id": room_id,
            "users": online_users,
            "count": len(online_users),
            "timestamp": datetime.now().isoformat()
        }),
        user_id,
        room_id
    )

# 定期清理过期连接的后台任务
async def cleanup_connections_task():
    """清理过期连接的后台任务"""
    while True:
        try:
            await manager.cleanup_expired_connections()
            await asyncio.sleep(300)  # 每5分钟清理一次
        except Exception as e:
            logger.error(f"清理连接任务出错: {e}")
            await asyncio.sleep(60)  # 出错后等待1分钟再重试

# 启动清理任务 - 只在异步环境中启动
def start_cleanup_task():
    """启动清理任务（仅在有事件循环时）"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(cleanup_connections_task())
    except RuntimeError:
        # 没有运行中的事件循环，跳过启动任务
        logger.info("没有运行中的事件循环，跳过启动清理任务")

# 延迟启动清理任务，避免在导入时出错
def init_background_tasks():
    """初始化后台任务"""
    try:
        import asyncio
        start_cleanup_task()
    except Exception as e:
        logger.warning(f"初始化后台任务失败: {e}")
