# project/utils/utils.py

from datetime import datetime
from typing import Any, Optional, Literal, List, Dict
from sqlalchemy.orm import Session, Query
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from fastapi import HTTPException, status

from project.models import Student, Project, UserCourse, ForumTopic, ForumComment, ForumLike, ChatMessage, PointTransaction, Achievement, UserAchievement
from project.ai_providers.config import GLOBAL_PLACEHOLDER_ZERO_VECTOR
from project.ai_providers.embedding_provider import get_embeddings_from_api
from project.ai_providers.security_utils import decrypt_key


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
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return str(value).strip() if str(value).strip() else ""


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


# --- 通用工具函数 ---

def validate_ownership(item, current_user_id: int, field_name: str = "owner_id", error_message: str = "无权访问此资源"):
    """
    验证用户是否拥有某个资源的权限
    
    Args:
        item: 要验证的资源对象
        current_user_id: 当前用户ID
        field_name: 所有者字段名（默认为 'owner_id'，也可以是 'creator_id' 等）
        error_message: 错误提示信息
    
    Raises:
        HTTPException: 如果资源不存在或用户无权访问
    """
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源未找到")
    
    owner_id = getattr(item, field_name, None)
    if owner_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error_message)


def paginate_query(query: Query, page: int = 1, page_size: int = 10, max_page_size: int = 100):
    """
    为查询添加分页功能
    
    Args:
        query: SQLAlchemy查询对象
        page: 页码（从1开始）
        page_size: 每页大小
        max_page_size: 最大每页大小
    
    Returns:
        tuple: (分页后的查询对象, offset, limit)
    """
    # 限制每页大小
    page_size = min(page_size, max_page_size)
    page = max(1, page)  # 确保页码至少为1
    
    offset = (page - 1) * page_size
    limit = page_size
    
    return query.offset(offset).limit(limit), offset, limit


async def generate_embedding_safe(combined_text: str, user_id: int = None, provider: str = None, api_key: str = None) -> List[float]:
    """
    安全地生成嵌入向量，失败时返回零向量
    
    Args:
        combined_text: 要生成嵌入的文本
        user_id: 用户ID
        provider: 嵌入提供商
        api_key: API密钥
    
    Returns:
        List[float]: 嵌入向量或零向量
    """
    if not combined_text or not combined_text.strip():
        return GLOBAL_PLACEHOLDER_ZERO_VECTOR
    
    try:
        new_embedding = await get_embeddings_from_api(
            texts=[combined_text],
            user_id=user_id,
            provider=provider,
            api_key=api_key
        )
        
        if new_embedding and isinstance(new_embedding, list) and len(new_embedding) > 0:
            return new_embedding[0]
        else:
            return GLOBAL_PLACEHOLDER_ZERO_VECTOR
            
    except Exception as e:
        print(f"ERROR_EMBEDDING: 生成嵌入向量失败: {e}")
        return GLOBAL_PLACEHOLDER_ZERO_VECTOR


def populate_user_name(item, db: Session, field_name: str = "owner_id", target_field: str = "owner_name"):
    """
    为对象填充用户名信息
    
    Args:
        item: 要填充的对象
        db: 数据库会话
        field_name: 用户ID字段名
        target_field: 目标字段名（用于存储用户名）
    """
    user_id = getattr(item, field_name, None)
    if user_id:
        user = db.query(Student).filter(Student.id == user_id).first()
        setattr(item, target_field, user.name if user else "未知用户")
    else:
        setattr(item, target_field, "未知用户")


def populate_like_status(item, current_user_id: int, db: Session, like_model, item_id_field: str, target_field: str = "is_liked_by_current_user"):
    """
    为对象填充当前用户的点赞状态
    
    Args:
        item: 要填充的对象
        current_user_id: 当前用户ID
        db: 数据库会话
        like_model: 点赞模型类
        item_id_field: 项目ID字段名（如 'topic_id', 'project_id' 等）
        target_field: 目标字段名
    """
    setattr(item, target_field, False)
    
    if current_user_id:
        item_id = getattr(item, "id", None)
        if item_id:
            like_filter = {
                "owner_id": current_user_id,
                item_id_field: item_id
            }
            like = db.query(like_model).filter_by(**like_filter).first()
            if like:
                setattr(item, target_field, True)


def get_user_by_id_or_404(db: Session, user_id: int, error_message: str = "用户未找到") -> Student:
    """
    根据ID获取用户，如果不存在则抛出404错误
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        error_message: 错误提示信息
    
    Returns:
        Student: 用户对象
        
    Raises:
        HTTPException: 如果用户不存在
    """
    user = db.query(Student).filter(Student.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
    return user


def check_admin_permission(db: Session, current_user_id: int) -> Student:
    """
    检查用户是否具有管理员权限
    
    Args:
        db: 数据库会话
        current_user_id: 当前用户ID
    
    Returns:
        Student: 管理员用户对象
        
    Raises:
        HTTPException: 如果用户不是管理员
    """
    user = get_user_by_id_or_404(db, current_user_id, "用户未找到")
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


# --- 通用查询和错误处理函数 ---

def get_resource_or_404(db: Session, model_class, resource_id: int, error_message: str = None):
    """
    通用的资源查找函数，如果不存在则抛出404错误
    
    Args:
        db: 数据库会话
        model_class: 模型类
        resource_id: 资源ID
        error_message: 自定义错误信息
    
    Returns:
        查找到的资源对象
        
    Raises:
        HTTPException: 如果资源不存在
    """
    if error_message is None:
        error_message = f"{model_class.__name__}未找到"
    
    resource = db.query(model_class).filter(model_class.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
    return resource


def get_user_resource_or_404(db: Session, model_class, resource_id: int, user_id: int, 
                            user_field: str = "owner_id", error_message: str = None):
    """
    查找用户拥有的资源，如果不存在或不属于用户则抛出404错误
    
    Args:
        db: 数据库会话
        model_class: 模型类
        resource_id: 资源ID
        user_id: 用户ID
        user_field: 用户字段名（如 'owner_id', 'creator_id'）
        error_message: 自定义错误信息
    
    Returns:
        查找到的资源对象
        
    Raises:
        HTTPException: 如果资源不存在或无权访问
    """
    if error_message is None:
        error_message = f"{model_class.__name__}未找到或无权访问"
    
    filter_kwargs = {
        "id": resource_id,
        user_field: user_id
    }
    
    resource = db.query(model_class).filter_by(**filter_kwargs).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_message)
    return resource


def check_resource_permission(resource, current_user_id: int, admin_user: Student = None, 
                            owner_field: str = "owner_id", error_message: str = "无权访问此资源"):
    """
    检查用户是否有权限访问资源（所有者或管理员）
    
    Args:
        resource: 资源对象
        current_user_id: 当前用户ID
        admin_user: 管理员用户对象（如果已查询）
        owner_field: 所有者字段名
        error_message: 错误信息
    
    Raises:
        HTTPException: 如果无权访问
    """
    owner_id = getattr(resource, owner_field, None)
    is_owner = (owner_id == current_user_id)
    is_admin = admin_user and admin_user.is_admin if admin_user else False
    
    if not (is_owner or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error_message)


# --- 通用数据库事务处理函数 ---

def commit_or_rollback(db: Session, operation_name: str = "操作"):
    """
    安全的数据库提交，失败时回滚
    
    Args:
        db: 数据库会话
        operation_name: 操作名称，用于错误日志
    
    Raises:
        HTTPException: 如果提交失败
    """
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"ERROR_DB: {operation_name}失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"{operation_name}失败")


def create_and_add_resource(db: Session, resource, operation_name: str = "创建资源"):
    """
    创建资源并添加到数据库
    
    Args:
        db: 数据库会话
        resource: 要创建的资源对象
        operation_name: 操作名称
    
    Returns:
        创建的资源对象
    """
    db.add(resource)
    commit_or_rollback(db, operation_name)
    db.refresh(resource)
    return resource


# --- 通用列表获取和详情填充函数 ---

async def get_resources_with_details(query, current_user_id: int, db: Session, 
                                   like_model=None, like_field: str = None,
                                   user_field: str = "owner_id", user_name_field: str = "owner_name"):
    """
    通用的资源列表获取和详情填充函数
    
    Args:
        query: SQLAlchemy查询对象
        current_user_id: 当前用户ID
        db: 数据库会话
        like_model: 点赞模型类
        like_field: 点赞关联字段名
        user_field: 用户字段名
        user_name_field: 用户名字段名
    
    Returns:
        填充了详情的资源列表
    """
    resources = query.all()
    
    for resource in resources:
        # 填充用户名
        populate_user_name(resource, db, user_field, user_name_field)
        
        # 填充点赞状态
        if like_model and like_field:
            populate_like_status(resource, current_user_id, db, like_model, like_field)
    
    return resources


# --- 具体资源类型的详情填充函数 ---

async def get_projects_with_details(query, current_user_id: int, db: Session):
    """获取项目列表并填充详细信息"""
    from models import ProjectLike
    return await get_resources_with_details(
        query, current_user_id, db, 
        like_model=ProjectLike, like_field="project_id",
        user_field="creator_id", user_name_field="_creator_name"
    )


async def get_courses_with_details(query, current_user_id: int, db: Session):
    """获取课程列表并填充动态信息"""
    from models import CourseLike
    return await get_resources_with_details(
        query, current_user_id, db,
        like_model=CourseLike, like_field="course_id",
        user_field="owner_id", user_name_field="owner_name"
    )


async def get_forum_topics_with_details(query, current_user_id: int, db: Session):
    """获取论坛话题列表并填充动态信息"""
    from models import ForumLike
    return await get_resources_with_details(
        query, current_user_id, db,
        like_model=ForumLike, like_field="topic_id",
        user_field="owner_id", user_name_field="owner_name"
    )


# --- 调试日志工具函数 ---

def debug_log(message: str, **kwargs):
    """
    统一的调试日志格式
    
    Args:
        message: 日志消息
        **kwargs: 额外的键值对参数
    """
    if kwargs:
        formatted_kwargs = ", ".join([f"{k}: {v}" for k, v in kwargs.items()])
        print(f"DEBUG: {message} - {formatted_kwargs}")
    else:
        print(f"DEBUG: {message}")


def debug_operation(operation: str, user_id: int = None, resource_id: int = None, 
                   resource_type: str = None, **kwargs):
    """
    记录操作日志
    
    Args:
        operation: 操作名称
        user_id: 用户ID
        resource_id: 资源ID
        resource_type: 资源类型
        **kwargs: 其他参数
    """
    parts = []
    if user_id:
        parts.append(f"用户 {user_id}")
    parts.append(operation)
    if resource_type and resource_id:
        parts.append(f"{resource_type} ID: {resource_id}")
    
    message = " ".join(parts)
    debug_log(message, **kwargs)


# --- Skills 字段处理函数 ---

def process_skills_field(skills_data: List[Any]) -> List[Dict]:
    """
    处理技能字段数据
    
    Args:
        skills_data: 技能数据列表
    
    Returns:
        处理后的技能数据列表
    """
    if not skills_data:
        return []
    
    skills_list_for_db = []
    for skill in skills_data:
        if hasattr(skill, 'model_dump'):
            skills_list_for_db.append(skill.model_dump())
        elif isinstance(skill, dict):
            skills_list_for_db.append(skill)
        else:
            skills_list_for_db.append({"name": str(skill)})
    
    return skills_list_for_db


def skills_to_text(skills_data: List[Dict]) -> str:
    """
    将技能数据转换为文本
    
    Args:
        skills_data: 技能数据列表
    
    Returns:
        技能文本字符串
    """
    if not skills_data:
        return ""
    
    skill_names = []
    for skill in skills_data:
        if isinstance(skill, dict) and skill.get("name"):
            skill_names.append(skill["name"])
        elif isinstance(skill, str):
            skill_names.append(skill)
    
    return ", ".join(skill_names)


def parse_skills_from_json(skills_json: str) -> List[Dict]:
    """
    从JSON字符串解析技能数据
    
    Args:
        skills_json: JSON字符串
    
    Returns:
        技能数据列表
    """
    if not skills_json:
        return []
    
    try:
        import json
        return json.loads(skills_json)
    except (json.JSONDecodeError, TypeError):
        return []


# --- 嵌入向量处理函数 ---

async def update_embedding_safe(item, combined_text: str, user_id: int = None, 
                               provider: str = None, api_key: str = None):
    """
    安全地更新对象的嵌入向量
    
    Args:
        item: 要更新的对象
        combined_text: 用于生成嵌入的文本
        user_id: 用户ID
        provider: 提供商
        api_key: API密钥
    """
    if combined_text and combined_text.strip():
        embedding = await generate_embedding_safe(combined_text, user_id, provider, api_key)
        item.embedding = embedding
        debug_log(f"嵌入向量已更新", item_id=getattr(item, 'id', 'unknown'))
    else:
        item.embedding = GLOBAL_PLACEHOLDER_ZERO_VECTOR
        debug_log(f"文本为空，设置为零向量", item_id=getattr(item, 'id', 'unknown'))


def build_user_combined_text(user_data: Dict[str, Any]) -> str:
    """
    构建用户的组合文本用于嵌入向量生成
    
    Args:
        user_data: 用户数据字典
    
    Returns:
        组合的文本内容
    """
    text_fields = [
        'name', 'major', 'interests', 'bio', 'awards_competitions',
        'academic_achievements', 'soft_skills', 'portfolio_link',
        'preferred_role', 'availability', 'location'
    ]
    
    text_parts = []
    
    for field in text_fields:
        value = user_data.get(field)
        text_part = _get_text_part(value)
        if text_part:
            text_parts.append(text_part)
    
    # 处理技能字段
    skills = user_data.get('skills', [])
    if skills:
        skills_text = skills_to_text(skills if isinstance(skills, list) else parse_skills_from_json(skills))
        if skills_text:
            text_parts.append(skills_text)
    
    return ". ".join(text_parts)


# --- 唯一性检查函数 ---

def check_unique_field(db: Session, model_class, field_name: str, field_value: Any, 
                      exclude_id: int = None, error_message: str = None):
    """
    检查字段值的唯一性
    
    Args:
        db: 数据库会话
        model_class: 模型类
        field_name: 字段名
        field_value: 字段值
        exclude_id: 排除的ID（更新时使用）
        error_message: 错误信息
    
    Raises:
        HTTPException: 如果字段值已存在
    """
    if field_value is None:
        return
        
    query = db.query(model_class).filter(getattr(model_class, field_name) == field_value)
    
    if exclude_id:
        query = query.filter(model_class.id != exclude_id)
    
    existing = query.first()
    if existing:
        if error_message is None:
            error_message = f"{field_name}已被使用"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)


# --- 字段更新函数 ---

def update_fields_from_dict(item, update_data: Dict[str, Any], allowed_fields: List[str] = None,
                           exclude_fields: List[str] = None):
    """
    从字典更新对象字段
    
    Args:
        item: 要更新的对象
        update_data: 更新数据字典
        allowed_fields: 允许更新的字段列表
        exclude_fields: 排除的字段列表
    """
    exclude_fields = exclude_fields or []
    
    for key, value in update_data.items():
        if key in exclude_fields:
            continue
            
        if allowed_fields and key not in allowed_fields:
            continue
            
        if hasattr(item, key):
            setattr(item, key, value)
            debug_log(f"更新字段", field=key, value=value)
