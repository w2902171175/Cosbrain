# project/routers/chatrooms.py
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any, Literal
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from jose import JWTError, jwt
import uuid, os, asyncio, json

# 导入数据库和模型
from database import get_db
from models import Student, Project, Course, ChatRoom, ChatMessage, ChatRoomMember, ChatRoomJoinRequest, Achievement, UserAchievement, PointTransaction
from dependencies import get_current_user_id, SECRET_KEY, ALGORITHM
import schemas
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


@router.get("/chatrooms/{room_id}/messages/", response_model=List[schemas.ChatMessageResponse],
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

    try:
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

    except HTTPException as e:
        # 重新抛出HTTP异常
        raise e
    except Exception as e:
        print(f"ERROR: 获取聊天消息时发生错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取聊天消息失败，请稍后重试。"
        )


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
                print(f"WARNING_WS: 用户 {current_user_id_int} 在聊天室 {room_id} 发送消息时已失去权限。连接将被关闭。")
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
