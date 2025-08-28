# project/routers/chatrooms/chatrooms.py
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal, Union
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from jose import JWTError, jwt
import uuid, os, asyncio, json, mimetypes, base64
from datetime import datetime
import io

# 导入数据库和模型
from database import get_db
from models.models import Student, Project, Course, ChatRoom, ChatMessage, ChatRoomMember, ChatRoomJoinRequest, Achievement, UserAchievement, PointTransaction
from dependencies.dependencies import get_current_user_id, SECRET_KEY, ALGORITHM
import schemas.schemas as schemas
import oss_utils

# 创建路由器
router = APIRouter(
    tags=["聊天室管理"],
    responses={404: {"description": "Not found"}},
)

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

@router.post("/chat-rooms/", response_model=schemas.ChatRoomResponse, summary="创建新的聊天室")
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


@router.get("/chatrooms/", response_model=List[schemas.ChatRoomResponse], summary="获取当前用户所属的所有聊天室")
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

    try:
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

    except Exception as e:
        print(f"ERROR: 获取聊天室列表时发生错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取聊天室列表失败，请稍后重试。"
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


# --- 聊天消息管理接口 ---
@router.post("/chatrooms/{room_id}/messages/", response_model=schemas.ChatMessageResponse,
          summary="在指定聊天室发送新消息")
async def send_chat_message(
        room_id: int,
        content_text: Optional[str] = Form(None, description="消息文本内容，当message_type为'text'时为必填"),
        message_type: Literal["text", "image", "file", "video", "audio", "system_notification"] = Form("text", description="消息类型"),
        media_url: Optional[str] = Form(None, description="媒体文件OSS URL或外部链接"),
        file: Optional[UploadFile] = File(None, description="上传文件、图片、视频或音频"),
        # 新增：多文件上传支持（仿微信相册选择多张图片）
        files: Optional[List[UploadFile]] = File(None, description="批量上传文件（最多9个）"),
        # 新增：语音消息支持
        audio_duration: Optional[float] = Form(None, description="音频时长（秒）"),
        # 新增：文件元数据
        file_size: Optional[int] = Form(None, description="文件大小（字节）"),
        reply_to_message_id: Optional[int] = Form(None, description="回复的消息ID"),
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    """
    在指定聊天室中发送一条新消息。
    支持多种消息类型：
    - 文本消息
    - 图片/视频（单个或多个，仿微信相册）
    - 文件（支持 txt, md, html, pdf, docx, pptx, xlsx, .py 等）
    - 音频消息（仿微信按住说话）
    - 回复消息
    """
    print(f"DEBUG: 用户 {current_user_id} 在聊天室 {room_id} 发送消息。类型: {message_type}")

    # 用于在OSS上传失败或DB事务回滚时删除OSS中已上传文件的变量
    uploaded_files_for_rollback = []

    try:
        # 1. 验证聊天室是否存在
        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到")

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

        # 3. 验证发送者用户是否存在
        db_sender = db.query(Student).filter(Student.id == current_user_id).first()
        if not db_sender:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="发送者用户未找到")

        # 4. 验证回复消息是否存在（如果指定了回复）
        if reply_to_message_id:
            reply_message = db.query(ChatMessage).filter(
                ChatMessage.id == reply_to_message_id,
                ChatMessage.room_id == room_id,
                ChatMessage.deleted_at.is_(None)
            ).first()
            if not reply_message:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回复的消息不存在")

        # 定义支持的文件类型
        SUPPORTED_FILE_TYPES = {
            # 文档类型
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
            # 音频类型
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.m4a': 'audio/mp4',
            '.aac': 'audio/aac',
            '.ogg': 'audio/ogg',
            '.webm': 'audio/webm',  # 用于录音
            # 图片类型
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
            # 视频类型
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.wmv': 'video/x-ms-wmv',
            '.flv': 'video/x-flv',
            '.mkv': 'video/x-matroska'
        }

        messages_to_create = []  # 存储要创建的消息列表（支持多文件时创建多条消息）

        # 5. 处理多文件上传（批量上传，如微信相册选择多张图片）
        if files and len(files) > 0:
            if len(files) > 9:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="一次最多上传9个文件")
            
            for idx, upload_file in enumerate(files):
                if not upload_file.filename:
                    continue
                    
                file_ext = os.path.splitext(upload_file.filename)[1].lower()
                if file_ext not in SUPPORTED_FILE_TYPES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"不支持的文件类型: {file_ext}。支持的类型: {', '.join(SUPPORTED_FILE_TYPES.keys())}"
                    )

                file_bytes = await upload_file.read()
                content_type = upload_file.content_type or SUPPORTED_FILE_TYPES.get(file_ext, 'application/octet-stream')

                # 根据文件类型确定消息类型和OSS路径
                if content_type.startswith('image/'):
                    msg_type = "image"
                    oss_path_prefix = "chat_images"
                elif content_type.startswith('video/'):
                    msg_type = "video"  
                    oss_path_prefix = "chat_videos"
                elif content_type.startswith('audio/'):
                    msg_type = "audio"
                    oss_path_prefix = "chat_audios"
                else:
                    msg_type = "file"
                    oss_path_prefix = "chat_files"

                # 上传到OSS
                object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_ext}"
                uploaded_files_for_rollback.append(object_name)
                
                try:
                    media_url = await oss_utils.upload_file_to_oss(
                        file_bytes=file_bytes,
                        object_name=object_name,
                        content_type=content_type
                    )
                    print(f"DEBUG: 文件 '{upload_file.filename}' 上传成功，URL: {media_url}")
                    
                    # 创建消息数据
                    message_content = content_text if idx == 0 and content_text else f"文件: {upload_file.filename}"
                    if content_type.startswith('image/'):
                        message_content = f"图片: {upload_file.filename}"
                    elif content_type.startswith('video/'):
                        message_content = f"视频: {upload_file.filename}"
                    elif content_type.startswith('audio/'):
                        message_content = f"音频: {upload_file.filename}"
                    
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
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                                      detail=f"文件上传失败: {upload_file.filename}")

        # 6. 处理单个文件上传
        elif file and file.filename:
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in SUPPORTED_FILE_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"不支持的文件类型: {file_ext}。支持的类型: {', '.join(SUPPORTED_FILE_TYPES.keys())}"
                )

            file_bytes = await file.read()
            content_type = file.content_type or SUPPORTED_FILE_TYPES.get(file_ext, 'application/octet-stream')

            # 根据文件类型确定消息类型和OSS路径
            if content_type.startswith('image/'):
                final_message_type = "image"
                oss_path_prefix = "chat_images"
            elif content_type.startswith('video/'):
                final_message_type = "video"
                oss_path_prefix = "chat_videos" 
            elif content_type.startswith('audio/'):
                final_message_type = "audio"
                oss_path_prefix = "chat_audios"
            else:
                final_message_type = "file"
                oss_path_prefix = "chat_files"

            object_name = f"{oss_path_prefix}/{uuid.uuid4().hex}{file_ext}"
            uploaded_files_for_rollback.append(object_name)

            try:
                final_media_url = await oss_utils.upload_file_to_oss(
                    file_bytes=file_bytes,
                    object_name=object_name,
                    content_type=content_type
                )
                print(f"DEBUG: 文件 '{file.filename}' 上传成功，URL: {final_media_url}")

                # 设置消息内容
                if not content_text:
                    if content_type.startswith('image/'):
                        final_content_text = f"图片: {file.filename}"
                    elif content_type.startswith('video/'):
                        final_content_text = f"视频: {file.filename}"
                    elif content_type.startswith('audio/'):
                        final_content_text = f"音频: {file.filename}"
                    else:
                        final_content_text = f"文件: {file.filename}"
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
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件上传失败: {e}")

        # 7. 处理纯文本消息或系统通知
        else:
            if message_type == "text" and not content_text:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文本消息内容不能为空")
            
            messages_to_create.append({
                'content_text': content_text,
                'message_type': message_type,
                'media_url': media_url,
                'file_size': file_size,
                'original_filename': None,
                'audio_duration': audio_duration if message_type == "audio" else None
            })

        # 8. 批量创建消息记录
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

        # 更新聊天室的 updated_at
        db_room.updated_at = func.now()
        db.add(db_room)
        db.flush()  # 刷新以便后续操作可以访问消息的 ID

        # 9. 积分奖励和成就检查
        chat_message_points = len(created_messages)  # 每条消息1积分
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

        db.commit()  # 提交所有
        
        # 10. 填充 sender_name 并返回结果
        for msg in created_messages:
            db.refresh(msg)
            msg.sender_name = db_sender.name

        print(f"DEBUG: 聊天室 {room_id} 收到 {len(created_messages)} 条消息")
        
        # 如果是单条消息，返回消息对象；如果是多条消息，返回第一条
        return created_messages[0] if created_messages else None

    except HTTPException as e:
        db.rollback()
        # 清理已上传的文件
        for file_key in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(file_key))
        raise e
    except Exception as e:
        db.rollback()
        # 清理已上传的文件
        for file_key in uploaded_files_for_rollback:
            asyncio.create_task(oss_utils.delete_file_from_oss(file_key))
        print(f"ERROR: 发送聊天消息失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"发送消息失败: {e}")


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
         summary="获取指定聊天室的历史消息")
async def get_chat_messages(
        room_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        limit: int = Query(50, description="限制返回消息数量"),
        offset: int = Query(0, description="偏移量，用于分页加载"),
        message_type: Optional[str] = Query(None, description="按消息类型过滤")
):
    """
    获取指定聊天室的历史消息。
    支持分页加载和按类型过滤。
    """
    print(f"DEBUG: 获取聊天室 {room_id} 的历史消息，用户 {current_user_id}。")

    try:
        # 1. 获取当前用户和目标聊天室的信息
        current_user = db.query(Student).filter(Student.id == current_user_id).first()
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证用户无效。")

        db_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not db_room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="聊天室未找到。")

        # 2. 权限检查：用户是否是群主、活跃成员或系统管理员
        is_creator = (db_room.creator_id == current_user_id)
        is_active_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.room_id == room_id,
            ChatRoomMember.member_id == current_user_id,
            ChatRoomMember.status == "active"
        ).first() is not None

        if not (is_creator or is_active_member or current_user.is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您无权查看该聊天室的历史消息。")

        # 3. 构建查询（过滤掉被删除的消息）
        query = db.query(ChatMessage).filter(
            ChatMessage.room_id == room_id,
            ChatMessage.deleted_at.is_(None)  # 只获取未删除的消息
        )
        
        # 按消息类型过滤
        if message_type:
            query = query.filter(ChatMessage.message_type == message_type)
        
        # 预加载回复消息的信息
        query = query.options(joinedload(ChatMessage.reply_to))
        
        # 排序和分页
        messages = query.order_by(ChatMessage.sent_at.desc()) \
            .offset(offset).limit(limit).all()

        # 4. 填充 sender_name 和 reply_to_message
        response_messages = []
        # 预加载所有发送者信息，以避免 N+1 查询问题
        sender_ids = list(set([msg.sender_id for msg in messages if msg.sender_id]))
        if messages:
            # 包括被回复消息的发送者
            reply_sender_ids = [msg.reply_to.sender_id for msg in messages if msg.reply_to and msg.reply_to.sender_id]
            sender_ids.extend(reply_sender_ids)
            sender_ids = list(set(sender_ids))
        
        senders_map = {s.id: s.name for s in db.query(Student).filter(Student.id.in_(sender_ids)).all()} if sender_ids else {}

        for msg in messages:
            msg.sender_name = senders_map.get(msg.sender_id, "未知用户")
            
            # 填充回复消息信息
            if msg.reply_to:
                msg.reply_to.sender_name = senders_map.get(msg.reply_to.sender_id, "未知用户")
                msg.reply_to_message = msg.reply_to
            
            response_messages.append(msg)

        # 反转顺序，使最新的消息在最后（符合聊天界面习惯）
        response_messages.reverse()

        print(f"DEBUG: 聊天室 {room_id} 获取到 {len(response_messages)} 条历史消息。")
        return response_messages

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"ERROR: 获取聊天消息时发生错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取聊天消息失败，请稍后重试。"
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


# --- WebSocket 聊天室接口 ---
@router.websocket("/ws_chat/{room_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        room_id: int,
        token: str = Query(..., description="用户JWT认证令牌"),
        db: Session = Depends(get_db)
):
    """
    WebSocket 聊天接口，支持实时消息推送。
    支持的消息类型：
    - 文本消息
    - 状态消息（用户加入/离开）
    - 系统通知
    - 媒体文件消息通知
    """
    print(f"DEBUG_WS: 尝试连接房间 {room_id}。")
    current_email = None
    current_payload_sub_str = None
    current_user_db = None
    current_user_id_int = None
    
    try:
        # 解码 JWT 令牌以获取用户身份
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        current_payload_sub_str: str = payload.get("sub")
        if current_payload_sub_str is None:
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION,
                                      reason="Invalid authentication token (subject missing).")

        # 将字符串ID转换为整数
        try:
            current_user_id_int = int(current_payload_sub_str)
        except ValueError:
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid user ID format in token.")

        # 从数据库中获取用户信息
        current_user_db = db.query(Student).filter(Student.id == current_user_id_int).first()
        if current_user_db is None:
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="User not found in database.")

        current_email = current_user_db.email

    except (JWTError, WebSocketDisconnect) as auth_error:
        print(f"ERROR_WS_AUTH: WebSocket 认证失败: {type(auth_error).__name__}: {auth_error}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"Authentication failed: {auth_error}")
        return
    except Exception as e:
        print(f"ERROR_WS_AUTH: WebSocket 认证内部错误: {type(e).__name__}: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Authentication internal error.")
        return

    print(f"DEBUG_WS: 用户 {current_user_id_int} (邮箱: {current_email}) 尝试连接聊天室 {room_id}。")

    # 验证聊天室权限
    chat_room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not chat_room:
        print(f"WARNING_WS: 用户 {current_user_id_int} 尝试连接不存在的聊天室 {room_id}。")
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA, reason="聊天室不存在。")
        return

    # 权限检查
    is_creator = (chat_room.creator_id == current_user_id_int)
    is_active_member = db.query(ChatRoomMember).filter(
        ChatRoomMember.room_id == room_id,
        ChatRoomMember.member_id == current_user_id_int,
        ChatRoomMember.status == "active"
    ).first() is not None

    print(f"DEBUG_PERM_WS: is_creator={is_creator}, is_active_member={is_active_member}")

    if not (is_creator or is_active_member):
        print(f"WARNING_WS: 用户 {current_user_id_int} 无权连接聊天室 {room_id}。")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="您无权访问或加入此聊天室。")
        return

    try:
        await manager.connect(websocket, room_id, current_user_id_int)
        print(f"DEBUG_WS: 用户 {current_user_id_int} 已成功连接到聊天室 {room_id}。")

        # 发送欢迎消息给新连接的用户
        welcome_message = {
            "type": "system",
            "content": f"欢迎 {current_user_db.name} 加入聊天室 {chat_room.name}！",
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(json.dumps(welcome_message), websocket)

        # 向房间内其他用户广播用户加入消息
        join_notification = {
            "type": "user_joined",
            "user_id": current_user_id_int,
            "user_name": current_user_db.name,
            "content": f"{current_user_db.name} 加入了聊天室",
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast(json.dumps(join_notification), room_id)

        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            message_type = data.get("type", "chat")
            
            if message_type == "chat":
                # 处理聊天消息
                message_content = data.get("content")
                reply_to_id = data.get("reply_to_message_id")

                if not message_content or not isinstance(message_content, str):
                    await websocket.send_json({"error": "Invalid message format. 'content' (string) is required."})
                    continue

                # 再次检查权限
                re_check_active_member = db.query(ChatRoomMember).filter(
                    ChatRoomMember.room_id == room_id,
                    ChatRoomMember.member_id == current_user_id_int,
                    ChatRoomMember.status == "active"
                ).first()
                re_check_creator = (chat_room.creator_id == current_user_id_int)

                if not (re_check_creator or re_check_active_member):
                    print(f"WARNING_WS: 用户 {current_user_id_int} 发送消息时已失去权限。")
                    await websocket.send_json({"error": "No permission to send messages."})
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="失去发送消息权限。")
                    break

                # 验证回复消息
                reply_to_message = None
                if reply_to_id:
                    reply_to_message = db.query(ChatMessage).filter(
                        ChatMessage.id == reply_to_id,
                        ChatMessage.room_id == room_id,
                        ChatMessage.deleted_at.is_(None)
                    ).first()

                # 创建消息记录
                db_message = ChatMessage(
                    room_id=room_id,
                    sender_id=current_user_id_int,
                    content_text=message_content,
                    message_type="text",
                    reply_to_message_id=reply_to_id if reply_to_message else None
                )
                db.add(db_message)
                
                # 更新聊天室活跃时间
                chat_room.updated_at = func.now()
                db.add(chat_room)
                
                db.commit()
                db.refresh(db_message)

                # 构建广播消息
                broadcast_message = {
                    "type": "chat_message",
                    "id": db_message.id,
                    "room_id": room_id,
                    "sender_id": current_user_id_int,
                    "sender_name": current_user_db.name,
                    "content": message_content,
                    "message_type": "text",
                    "sent_at": db_message.sent_at.isoformat(),
                    "reply_to_message_id": reply_to_id,
                    "reply_to_message": {
                        "id": reply_to_message.id,
                        "content": reply_to_message.content_text[:50] + "..." if len(reply_to_message.content_text) > 50 else reply_to_message.content_text,
                        "sender_name": reply_to_message.sender.name
                    } if reply_to_message else None
                }
                
                await manager.broadcast(json.dumps(broadcast_message), room_id)
                print(f"DEBUG_WS: 聊天室 {room_id} 广播消息: {current_user_db.name}: {message_content[:50]}...")

            elif message_type == "typing":
                # 处理正在输入状态
                typing_message = {
                    "type": "typing",
                    "user_id": current_user_id_int,
                    "user_name": current_user_db.name,
                    "is_typing": data.get("is_typing", True),
                    "timestamp": datetime.now().isoformat()
                }
                # 广播给除自己外的其他用户
                for user_id, connection in manager.active_connections.get(room_id, {}).items():
                    if user_id != current_user_id_int:
                        try:
                            await connection.send_text(json.dumps(typing_message))
                        except:
                            pass

            elif message_type == "file_upload_notification":
                # 处理文件上传完成通知
                file_info = data.get("file_info", {})
                notification_message = {
                    "type": "file_uploaded",
                    "user_id": current_user_id_int,
                    "user_name": current_user_db.name,
                    "file_info": file_info,
                    "timestamp": datetime.now().isoformat()
                }
                await manager.broadcast(json.dumps(notification_message), room_id)

            elif message_type == "heartbeat":
                # 心跳检测
                await websocket.send_json({"type": "heartbeat_response", "timestamp": datetime.now().isoformat()})

            else:
                await websocket.send_json({"error": f"Unknown message type: {message_type}"})

    except WebSocketDisconnect:
        print(f"DEBUG_WS: 用户 {current_user_id_int} 从聊天室 {room_id} 断开连接。")
        
        # 广播用户离开消息
        if current_user_id_int and current_user_db:
            leave_notification = {
                "type": "user_left",
                "user_id": current_user_id_int,
                "user_name": current_user_db.name,
                "content": f"{current_user_db.name} 离开了聊天室",
                "timestamp": datetime.now().isoformat()
            }
            await manager.broadcast(json.dumps(leave_notification), room_id)
            
    except Exception as e:
        print(f"ERROR_WS: 用户 {current_user_id_int} 在聊天室 {room_id} WebSocket 处理异常: {e}")
        if websocket.client_state == 1:  # WebSocketState.CONNECTED
            await websocket.send_json({"error": f"服务器内部错误: {e}"})
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason=f"服务器内部错误: {e}")
    finally:
        # 确保从管理器中移除连接
        if current_user_id_int is not None:
            manager.disconnect(room_id, current_user_id_int)