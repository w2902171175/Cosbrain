# project/routers/course_notes/utils.py
"""
课程笔记路由的工具函数模块
提取重复逻辑，提高代码复用性和可维护性
"""

from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from typing import List, Optional
import json
import logging
import time
from functools import wraps

from project.models import Note, Folder, Course
import project.schemas as schemas

logger = logging.getLogger(__name__)


def parse_note_data_from_request(
    note_data: Optional[schemas.NoteBase],
    note_data_json: Optional[str],
    file: Optional[UploadFile]
) -> schemas.NoteBase:
    """
    解析笔记数据，支持JSON和multipart格式
    
    Args:
        note_data: JSON格式请求时的笔记数据
        note_data_json: multipart格式请求时的JSON字符串
        file: 上传的文件
        
    Returns:
        解析后的笔记数据
        
    Raises:
        HTTPException: 数据格式错误或验证失败
    """
    if note_data_json is not None:
        # multipart/form-data 请求
        try:
            note_data_dict = json.loads(note_data_json)
            parsed_note_data = schemas.NoteBase(**note_data_dict)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的JSON格式: {e}"
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"数据验证失败: {e}"
            )
    elif note_data is not None:
        # application/json 请求
        if file is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON请求不支持文件上传，请使用 multipart/form-data 格式"
            )
        parsed_note_data = note_data
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须提供笔记数据：JSON请求使用 note_data，表单请求使用 note_data_json"
        )
    
    return parsed_note_data


def validate_folder_access(
    folder_id: Optional[int], 
    user_id: int, 
    db: Session,
    allow_none: bool = True
) -> Optional[Folder]:
    """
    验证文件夹访问权限
    
    Args:
        folder_id: 文件夹ID，None表示根目录
        user_id: 用户ID
        db: 数据库会话
        allow_none: 是否允许None值（根目录）
        
    Returns:
        文件夹对象或None（根目录）
        
    Raises:
        HTTPException: 文件夹不存在或无权访问
    """
    if folder_id is None:
        if allow_none:
            return None
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="必须指定文件夹ID"
            )
    
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == user_id
    ).first()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在或无权访问"
        )
    
    return folder


def populate_note_relations(notes: List[Note], db: Session) -> None:
    """
    批量填充笔记的关联信息（文件夹名、课程标题）
    使用优化的查询减少数据库访问次数
    
    Args:
        notes: 笔记列表
        db: 数据库会话
    """
    if not notes:
        return
    
    # 收集需要查询的ID
    folder_ids = {note.folder_id for note in notes if note.folder_id is not None}
    course_ids = {note.course_id for note in notes if note.course_id is not None}
    
    # 批量查询文件夹信息
    folders_map = {}
    if folder_ids:
        folders = db.query(Folder).filter(Folder.id.in_(folder_ids)).all()
        folders_map = {folder.id: folder for folder in folders}
    
    # 批量查询课程信息
    courses_map = {}
    if course_ids:
        courses = db.query(Course).filter(Course.id.in_(course_ids)).all()
        courses_map = {course.id: course for course in courses}
    
    # 填充关联信息
    for note in notes:
        if note.folder_id and note.folder_id in folders_map:
            note.folder_name_for_response = folders_map[note.folder_id].name
        
        if note.course_id and note.course_id in courses_map:
            note.course_title_for_response = courses_map[note.course_id].title


def get_notes_with_relations(
    base_query,
    db: Session,
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "created_at",
    sort_order: str = "desc"
) -> List[Note]:
    """
    获取带关联信息的笔记列表，优化数据库查询
    
    Args:
        base_query: 基础查询对象
        db: 数据库会话
        limit: 限制数量
        offset: 偏移量
        sort_by: 排序字段
        sort_order: 排序方向
        
    Returns:
        笔记列表
    """
    # 应用排序
    if sort_by == "title":
        order_field = Note.title
    elif sort_by == "updated_at":
        order_field = Note.updated_at
    else:
        order_field = Note.created_at
    
    if sort_order == "asc":
        base_query = base_query.order_by(order_field.asc())
    else:
        base_query = base_query.order_by(order_field.desc())
    
    # 使用joinedload预加载关联数据，避免N+1查询
    notes = base_query.options(
        joinedload(Note.folder),
        joinedload(Note.course)
    ).offset(offset).limit(limit).all()
    
    # 填充响应字段
    for note in notes:
        if note.folder:
            note.folder_name_for_response = note.folder.name
        if note.course:
            note.course_title_for_response = note.course.title
    
    return notes


def validate_note_access(note_id: int, user_id: int, db: Session) -> Note:
    """
    验证笔记访问权限
    
    Args:
        note_id: 笔记ID
        user_id: 用户ID
        db: 数据库会话
        
    Returns:
        笔记对象
        
    Raises:
        HTTPException: 笔记不存在或无权访问
    """
    note = db.query(Note).filter(
        Note.id == note_id,
        Note.owner_id == user_id
    ).first()
    
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="笔记不存在或无权访问"
        )
    
    return note


def validate_batch_operation_limit(items_count: int, max_limit: int = 100) -> None:
    """
    验证批量操作的数量限制
    
    Args:
        items_count: 要操作的项目数量
        max_limit: 最大允许数量
        
    Raises:
        HTTPException: 超出数量限制
    """
    if items_count > max_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"单次最多只能操作{max_limit}个项目，当前尝试操作{items_count}个"
        )


def process_folder_id(folder_id: int) -> Optional[int]:
    """
    处理文件夹ID，将0转换为None（根目录）
    
    Args:
        folder_id: 原始文件夹ID
        
    Returns:
        处理后的文件夹ID
    """
    return None if folder_id == 0 else folder_id


def log_operation(operation: str, user_id: int, details: str = ""):
    """
    统一的操作日志记录
    
    Args:
        operation: 操作类型
        user_id: 用户ID
        details: 详细信息
    """
    logger.info(f"用户 {user_id} 执行操作: {operation}. {details}")


def check_folder_name_duplicate(
    db: Session,
    user_id: int,
    name: str,
    parent_id: Optional[int],
    exclude_folder_id: Optional[int] = None
) -> bool:
    """
    检查文件夹名称是否重复
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        name: 文件夹名称
        parent_id: 父文件夹ID
        exclude_folder_id: 要排除的文件夹ID（用于更新时排除自身）
        
    Returns:
        是否存在重复名称
    """
    query = db.query(Folder).filter(
        Folder.owner_id == user_id,
        Folder.name == name,
        Folder.parent_id == parent_id
    )
    
    if exclude_folder_id is not None:
        query = query.filter(Folder.id != exclude_folder_id)
    
    return query.first() is not None


async def check_cycle_reference(folder_id: int, new_parent_id: int, db: Session) -> bool:
    """
    检查设置新父文件夹是否会创建循环引用
    
    Args:
        folder_id: 要移动的文件夹ID
        new_parent_id: 新的父文件夹ID
        db: 数据库会话
        
    Returns:
        是否会形成循环引用
    """
    current_id = new_parent_id
    visited = set()
    
    while current_id is not None:
        if current_id == folder_id:
            return True
        if current_id in visited:
            break
        visited.add(current_id)
        
        parent_folder = db.query(Folder).filter(Folder.id == current_id).first()
        current_id = parent_folder.parent_id if parent_folder else None
    
    return False


from typing import Tuple

def get_folder_content_counts(db: Session, folder_id: int) -> Tuple[int, int]:
    """
    获取文件夹内容统计（笔记数和子文件夹数）
    
    Args:
        db: 数据库会话
        folder_id: 文件夹ID
        
    Returns:
        (notes_count, subfolders_count)
    """
    notes_count = db.query(Note).filter(Note.folder_id == folder_id).count()
    subfolders_count = db.query(Folder).filter(Folder.parent_id == folder_id).count()
    return notes_count, subfolders_count


def build_search_conditions(
    search_title: bool = True,
    search_content: bool = True, 
    search_tags: bool = True,
    query: str = ""
) -> list:
    """
    构建搜索条件列表
    
    Args:
        search_title: 是否搜索标题
        search_content: 是否搜索内容
        search_tags: 是否搜索标签
        query: 搜索关键词
        
    Returns:
        搜索条件列表
    """
    search_conditions = []
    search_pattern = f"%{query}%"
    
    if search_title:
        search_conditions.append(Note.title.ilike(search_pattern))
    if search_content:
        search_conditions.append(Note.content.ilike(search_pattern))
    if search_tags:
        search_conditions.append(Note.tags.ilike(search_pattern))
    
    return search_conditions


def optimize_folder_id_filter(folder_ids: Optional[List[int]], query):
    """
    优化文件夹ID过滤逻辑
    
    Args:
        folder_ids: 文件夹ID列表
        query: 查询对象
        
    Returns:
        优化后的查询对象
    """
    if folder_ids is None:
        return query
    
    # 处理0值（根目录）
    processed_folder_ids = []
    include_root = False
    
    for fid in folder_ids:
        if fid == 0:
            include_root = True
        else:
            processed_folder_ids.append(fid)
    
    if include_root and processed_folder_ids:
        query = query.filter(
            or_(
                Note.folder_id.in_(processed_folder_ids),
                Note.folder_id.is_(None)
            )
        )
    elif include_root:
        query = query.filter(Note.folder_id.is_(None))
    elif processed_folder_ids:
        query = query.filter(Note.folder_id.in_(processed_folder_ids))
    
    return query


def validate_search_query(query: str) -> str:
    """
    验证和清理搜索查询字符串
    
    Args:
        query: 原始查询字符串
        
    Returns:
        清理后的查询字符串
        
    Raises:
        HTTPException: 查询字符串无效
    """
    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="搜索关键词不能为空"
        )
    
    # 清理查询字符串
    cleaned_query = query.strip()
    
    # 检查长度限制
    if len(cleaned_query) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="搜索关键词过长，最大长度为100个字符"
        )
    
    # 防止SQL注入的基本检查
    dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "xp_", "sp_"]
    for char in dangerous_chars:
        if char in cleaned_query.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="搜索关键词包含非法字符"
            )
    
    return cleaned_query


def validate_pagination_params(limit: int, offset: int) -> Tuple[int, int]:
    """
    验证分页参数
    
    Args:
        limit: 限制数量
        offset: 偏移量
        
    Returns:
        验证后的(limit, offset)
        
    Raises:
        HTTPException: 参数无效
    """
    if limit <= 0 or limit > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit参数必须在1-1000之间"
        )
    
    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="offset参数不能为负数"
        )
    
    return limit, offset


def sanitize_folder_name(name: str) -> str:
    """
    清理文件夹名称
    
    Args:
        name: 原始文件夹名称
        
    Returns:
        清理后的文件夹名称
        
    Raises:
        HTTPException: 名称无效
    """
    if not name or not name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件夹名称不能为空"
        )
    
    cleaned_name = name.strip()
    
    # 检查长度
    if len(cleaned_name) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件夹名称过长，最大长度为50个字符"
        )
    
    # 检查非法字符
    illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in illegal_chars:
        if char in cleaned_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件夹名称不能包含字符: {char}"
            )
    
    return cleaned_name


def performance_monitor(operation_name: str):
    """
    性能监控装饰器
    
    Args:
        operation_name: 操作名称
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(f"{operation_name} 执行完成，耗时: {execution_time:.3f}秒")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"{operation_name} 执行失败，耗时: {execution_time:.3f}秒，错误: {e}")
                raise
        return wrapper
    return decorator


class DatabaseQueryOptimizer:
    """
    数据库查询优化器
    """
    
    @staticmethod
    def batch_load_related_data(notes: List, db: Session) -> None:
        """
        批量加载关联数据，避免N+1查询
        
        Args:
            notes: 笔记列表
            db: 数据库会话
        """
        if not notes:
            return
        
        # 批量加载文件夹信息
        folder_ids = {note.folder_id for note in notes if note.folder_id is not None}
        folders_map = {}
        if folder_ids:
            folders = db.query(Folder).filter(Folder.id.in_(folder_ids)).all()
            folders_map = {folder.id: folder for folder in folders}
        
        # 批量加载课程信息  
        course_ids = {note.course_id for note in notes if note.course_id is not None}
        courses_map = {}
        if course_ids:
            courses = db.query(Course).filter(Course.id.in_(course_ids)).all()
            courses_map = {course.id: course for course in courses}
        
        # 填充关联信息
        for note in notes:
            if note.folder_id and note.folder_id in folders_map:
                note.folder_name_for_response = folders_map[note.folder_id].name
            if note.course_id and note.course_id in courses_map:
                note.course_title_for_response = courses_map[note.course_id].title
    
    @staticmethod
    def optimize_count_queries(db: Session, user_id: int) -> dict:
        """
        优化统计查询
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            统计信息字典
        """
        # 使用子查询优化统计
        stats = {}
        
        # 总文件夹数
        stats['total_folders'] = db.query(Folder).filter(Folder.owner_id == user_id).count()
        
        # 总笔记数
        stats['total_notes'] = db.query(Note).filter(Note.owner_id == user_id).count()
        
        # 按类型统计笔记（一次查询）
        note_type_stats = db.query(
            Note.note_type,
            func.count(Note.id)
        ).filter(
            Note.owner_id == user_id
        ).group_by(Note.note_type).all()
        
        stats['content_by_type'] = {note_type: count for note_type, count in note_type_stats}
        
        return stats
