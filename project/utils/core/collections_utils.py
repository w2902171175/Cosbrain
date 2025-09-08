# project/utils/core/collections_utils.py
"""
收藏系统公共工具函数

提供收藏系统相关的通用工具函数，包括：
- 权限验证：文件夹和内容的访问权限检查
- 收藏文件夹管理
- 收藏状态检查
- 收藏项目创建和删除
- 点赞逻辑处理
- 批量操作支持

设计原则：
1. 单一职责：每个函数只负责一个明确的功能
2. 高内聚：相关的配置和逻辑集中管理
3. 低耦合：减少对外部模块的依赖
4. 易测试：函数设计便于单元测试
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, text
from fastapi import HTTPException, status
import logging
from datetime import datetime, timezone

from project.models import (
    Project, Course, CollectedContent, Folder, 
    ProjectLike, CourseLike, ChatMessage, ForumTopic, Note
)

# 导入配置
from project.config.collections_config import (
    COLLECTION_CONFIGS, FOLDER_COLOR_MAPPING, FOLDER_ICON_MAPPING,
    CONTENT_TYPE_FOLDER_MAPPING, TAG_KEYWORD_MAPPING, FILE_TYPE_TAG_MAPPING,
    DEFAULT_FOLDER_COLOR, DEFAULT_FOLDER_ICON, DEFAULT_FOLDER_NAME, MAX_AUTO_TAGS
)

# 配置常量
logger = logging.getLogger(__name__)


# ================== 权限验证函数 ==================

def validate_folder_permission(db: Session, folder_id: int, user_id: int) -> bool:
    """验证用户对文件夹的访问权限"""
    folder = db.query(Folder).filter(
        Folder.id == folder_id,
        Folder.owner_id == user_id
    ).first()
    
    return folder is not None


def validate_content_permission(db: Session, content_id: int, user_id: int) -> bool:
    """验证用户对收藏内容的访问权限"""
    content = db.query(CollectedContent).filter(
        CollectedContent.id == content_id,
        CollectedContent.owner_id == user_id
    ).first()
    
    return content is not None


def check_folder_access(db: Session, folder_id: int, user_id: int):
    """检查文件夹访问权限，如果无权限则抛出异常"""
    if not validate_folder_permission(db, folder_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在或无权访问"
        )


def check_content_access(db: Session, content_id: int, user_id: int):
    """检查收藏内容访问权限，如果无权限则抛出异常"""
    if not validate_content_permission(db, content_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="收藏内容不存在或无权访问"
        )


# ================== 核心工具函数 ==================

def validate_item_type(item_type: str) -> None:
    """
    验证收藏类型是否有效
    
    Args:
        item_type: 收藏类型
        
    Raises:
        ValueError: 如果类型无效
    """
    if item_type not in COLLECTION_CONFIGS:
        valid_types = ", ".join(COLLECTION_CONFIGS.keys())
        raise ValueError(f"不支持的收藏类型: {item_type}。支持的类型: {valid_types}")


async def get_or_create_collection_folder(
    db: Session, 
    user_id: int, 
    item_type: str
) -> Folder:
    """
    获取或创建指定类型的收藏文件夹
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        item_type: 收藏类型 ("project" 或 "course")
    
    Returns:
        文件夹对象
        
    Raises:
        ValueError: 如果收藏类型无效
    """
    validate_item_type(item_type)
    config = COLLECTION_CONFIGS[item_type]
    
    # 查找现有文件夹
    folder = db.query(Folder).filter(
        and_(
            Folder.owner_id == user_id,
            Folder.name == config["folder_name"]
        )
    ).first()
    
    # 如果不存在则创建
    if not folder:
        folder = Folder(
            owner_id=user_id,
            name=config["folder_name"],
            description=f"自动创建的{config['display_name']}收藏文件夹",
            color=config["color"],
            icon=config["icon"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(folder)
        db.flush()  # 获取文件夹ID
        logger.info(f"为用户 {user_id} 创建了 {item_type} 收藏文件夹: {folder.id}")
    
    return folder

async def check_item_exists(db: Session, item_type: str, item_id: int) -> Any:
    """
    检查项目/课程/知识库文件夹/笔记文件夹是否存在
    
    Args:
        db: 数据库会话
        item_type: 类型
        item_id: ID
    
    Returns:
        项目/课程/文件夹对象
        
    Raises:
        HTTPException: 如果类型无效或项目不存在
    """
    try:
        validate_item_type(item_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    config = COLLECTION_CONFIGS[item_type]
    model = config["model"]
    
    # 对于知识库文件夹和笔记文件夹，需要检查是否公开
    if item_type in ["knowledge_folder", "note_folder"]:
        item = db.query(model).filter(
            and_(
                model.id == item_id,
                model.is_public == True  # 只能收藏公开的文件夹
            )
        ).first()
    else:
        item = db.query(model).filter(model.id == item_id).first()
    
    if not item:
        display_name = config["display_name"]
        if item_type in ["knowledge_folder", "note_folder"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"公开的{display_name}未找到 (ID: {item_id})，可能不存在或未公开"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{display_name}未找到 (ID: {item_id})"
            )
    
    return item

async def check_already_collected(
    db: Session, 
    user_id: int, 
    item_type: str, 
    item_id: int
) -> bool:
    """
    检查是否已经收藏过
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        item_type: 类型
        item_id: ID
    
    Returns:
        是否已收藏
    """
    existing = db.query(CollectedContent).filter(
        and_(
            CollectedContent.owner_id == user_id,
            CollectedContent.shared_item_type == item_type,
            CollectedContent.shared_item_id == item_id,
            CollectedContent.status == "active"
        )
    ).first()
    
    return existing is not None

async def create_collection_item(
    db: Session,
    user_id: int,
    folder: Folder,
    item: Any,
    item_type: str,
    item_id: int
) -> CollectedContent:
    """
    创建收藏记录
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        folder: 文件夹对象
        item: 项目/课程/文件夹对象
        item_type: 类型
        item_id: ID
    
    Returns:
        收藏内容对象
    """
    # 获取标题字段
    if item_type in ["project", "course"]:
        title = getattr(item, "title", "")
        description = getattr(item, "description", "")
    elif item_type in ["knowledge_base", "note_folder"]:
        # 知识库使用title字段，笔记文件夹使用name字段
        if item_type == "knowledge_base":
            title = getattr(item, "title", "")
        else:  # note_folder
            title = getattr(item, "name", "")
        description = getattr(item, "description", "")
    else:
        title = getattr(item, "title", "") or getattr(item, "name", "")
        description = getattr(item, "description", "")
    
    # 获取作者信息
    author = "未知"
    try:
        if hasattr(item, 'instructor') and item.instructor:
            author = item.instructor
        elif hasattr(item, 'creator') and item.creator:
            author = item.creator.name
        elif hasattr(item, 'author') and item.author:
            author = item.author
        elif hasattr(item, 'owner') and item.owner:
            author = item.owner.name if hasattr(item.owner, 'name') else str(item.owner)
        elif hasattr(item, 'owner_id') and item.owner_id:
            author = f"用户 {item.owner_id}"
    except Exception as e:
        logger.warning(f"获取作者信息失败: {e}")
    
    # 创建收藏记录
    collection_item = CollectedContent(
        owner_id=user_id,
        folder_id=folder.id,
        title=title,
        type=item_type,
        shared_item_type=item_type,
        shared_item_id=item_id,
        content=description or "",
        excerpt=(description[:200] + "...") if description and len(description) > 200 else (description or ""),
        author=author,
        is_starred=True,
        status="active",
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(collection_item)
    logger.info(f"用户 {user_id} 收藏了 {item_type} {item_id}: {title}")
    return collection_item

async def handle_like_logic(
    db: Session,
    user_id: int,
    item: Any,
    item_type: str,
    item_id: int
) -> bool:
    """
    处理点赞逻辑（如果尚未点赞则自动点赞）
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        item: 项目/课程/文件夹对象
        item_type: 类型
        item_id: ID
    
    Returns:
        是否新增了点赞
    """
    config = COLLECTION_CONFIGS[item_type]
    like_model = config["like_model"]
    like_field = config["like_field"]
    
    # 如果不支持点赞功能，直接返回False
    if not like_model or not like_field:
        return False
    
    # 检查是否已点赞
    filter_kwargs = {
        "owner_id": user_id,
        like_field: item_id
    }
    
    existing_like = db.query(like_model).filter(
        and_(*[getattr(like_model, k) == v for k, v in filter_kwargs.items()])
    ).first()
    
    if not existing_like:
        # 创建点赞记录
        like_record = like_model(**filter_kwargs)
        db.add(like_record)
        
        # 增加点赞数
        item.likes_count = (item.likes_count or 0) + 1
        db.add(item)
        
        return True
    
    return False

async def get_collection_status(
    db: Session,
    user_id: int,
    item_type: str,
    item_id: int
) -> Dict[str, Any]:
    """
    获取收藏和点赞状态（优化版本）
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        item_type: 类型
        item_id: ID
    
    Returns:
        状态信息字典
    """
    config = COLLECTION_CONFIGS[item_type]
    like_model = config["like_model"]
    like_field = config["like_field"]
    
    # 使用一次查询同时检查收藏和点赞状态
    collection_query = db.query(CollectedContent).filter(
        and_(
            CollectedContent.owner_id == user_id,
            CollectedContent.shared_item_type == item_type,
            CollectedContent.shared_item_id == item_id,
            CollectedContent.status == "active"
        )
    )
    
    like_query = db.query(like_model).filter(
        and_(
            getattr(like_model, "owner_id") == user_id,
            getattr(like_model, like_field) == item_id
        )
    )
    
    # 并行执行查询
    is_starred = collection_query.first() is not None
    is_liked = like_query.first() is not None
    
    # 统计总收藏数
    total_stars = db.query(CollectedContent).filter(
        and_(
            CollectedContent.shared_item_type == item_type,
            CollectedContent.shared_item_id == item_id,
            CollectedContent.status == "active"
        )
    ).count()
    
    return {
        "is_starred": is_starred,
        "is_liked": is_liked,
        "total_stars": total_stars
    }

async def unstar_item(
    db: Session,
    user_id: int,
    item_type: str,
    item_id: int
) -> bool:
    """
    取消收藏项目
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        item_type: 类型
        item_id: ID
    
    Returns:
        是否成功取消收藏
        
    Raises:
        HTTPException: 如果未找到收藏记录
    """
    collection_item = db.query(CollectedContent).filter(
        and_(
            CollectedContent.owner_id == user_id,
            CollectedContent.shared_item_type == item_type,
            CollectedContent.shared_item_id == item_id,
            CollectedContent.status == "active"
        )
    ).first()
    
    if not collection_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到该{item_type}的收藏记录"
        )
    
    # 软删除收藏记录
    collection_item.status = "deleted"
    db.add(collection_item)
    
    return True

def format_star_response(
    collection_item: CollectedContent,
    item: Any,
    folder: Folder,
    item_type: str,
    item_id: int,
    also_liked: bool = False
) -> Dict[str, Any]:
    """
    格式化收藏成功响应
    
    Args:
        collection_item: 收藏记录
        item: 项目/课程对象
        folder: 文件夹对象
        item_type: 类型
        item_id: ID
        also_liked: 是否同时进行了点赞
    
    Returns:
        响应字典
    """
    config = COLLECTION_CONFIGS.get(item_type, {})
    display_name = config.get("display_name", item_type)
    
    return {
        "message": f"{display_name}收藏成功",
        "collection_id": collection_item.id,
        f"{item_type}_id": item_id,
        f"{item_type}_title": item.title,
        "folder_id": folder.id,
        "folder_name": folder.name,
        "also_liked": also_liked,
        "created_at": collection_item.created_at.isoformat() if collection_item.created_at else None
    }


def get_supported_types() -> List[str]:
    """
    获取支持的收藏类型列表
    
    Returns:
        支持的类型列表
    """
    return list(COLLECTION_CONFIGS.keys())


def get_type_display_name(item_type: str) -> str:
    """
    获取类型的显示名称
    
    Args:
        item_type: 类型代码
        
    Returns:
        显示名称
    """
    return COLLECTION_CONFIGS.get(item_type, {}).get("display_name", item_type)


# ================== 文件夹辅助函数 ==================

def suggest_folder_color(name: str) -> str:
    """根据文件夹名称智能建议颜色"""
    name_lower = name.lower()
    for keyword, color in FOLDER_COLOR_MAPPING.items():
        if keyword in name_lower:
            return color
    
    # 默认颜色
    return DEFAULT_FOLDER_COLOR


def suggest_folder_icon(name: str) -> str:
    """根据文件夹名称智能建议图标"""
    name_lower = name.lower()
    for keyword, icon in FOLDER_ICON_MAPPING.items():
        if keyword in name_lower:
            return icon
    
    # 默认图标
    return DEFAULT_FOLDER_ICON


async def calculate_folder_depth(db: Session, folder_id: int) -> int:
    """计算文件夹深度"""
    
    depth = 0
    current_id = folder_id
    
    while current_id:
        folder = db.query(Folder).filter(Folder.id == current_id).first()
        if folder and folder.parent_id:
            depth += 1
            current_id = folder.parent_id
        else:
            break
    
    return depth


async def get_folder_path(db: Session, folder_id: int, user_id: int) -> List[Dict[str, Any]]:
    """获取文件夹路径"""
    
    path = []
    current_id = folder_id
    
    while current_id:
        folder = db.query(Folder).filter(
            Folder.id == current_id,
            Folder.owner_id == user_id
        ).first()
        
        if folder:
            path.insert(0, {
                "id": folder.id,
                "name": folder.name,
                "icon": folder.icon,
                "color": folder.color
            })
            current_id = folder.parent_id
        else:
            break
    
    return path


async def would_create_cycle(db: Session, folder_id: int, new_parent_id: int, user_id: int) -> bool:
    """检查移动文件夹是否会创建循环引用"""
    
    current_id = new_parent_id
    visited = set()
    
    while current_id and current_id not in visited:
        if current_id == folder_id:
            return True
        
        visited.add(current_id)
        parent_folder = db.query(Folder).filter(
            Folder.id == current_id,
            Folder.owner_id == user_id
        ).first()
        
        current_id = parent_folder.parent_id if parent_folder else None
    
    return False


async def get_all_subfolder_ids(db: Session, folder_id: int, user_id: int) -> List[int]:
    """递归获取所有子文件夹ID"""
    
    subfolder_ids = []
    
    direct_subfolders = db.query(Folder).filter(
        Folder.parent_id == folder_id,
        Folder.owner_id == user_id
    ).all()
    
    for subfolder in direct_subfolders:
        subfolder_ids.append(subfolder.id)
        # 递归获取子文件夹的子文件夹
        nested_ids = await get_all_subfolder_ids(db, subfolder.id, user_id)
        subfolder_ids.extend(nested_ids)
    
    return subfolder_ids


# ================== 内容处理辅助函数 ==================

async def determine_target_folder(
    db: Session, 
    user_id: int, 
    specified_folder_id: Optional[int],
    folder_name: Optional[str],
    shared_item_type: Optional[str],
    url: Optional[str],
    file=None
) -> int:
    """智能确定目标文件夹"""
    
    # 如果明确指定了文件夹
    if specified_folder_id:
        folder = db.query(Folder).filter(
            Folder.id == specified_folder_id,
            Folder.owner_id == user_id
        ).first()
        if folder:
            return specified_folder_id
    
    # 如果指定了文件夹名称，查找或创建
    if folder_name:
        folder = db.query(Folder).filter(
            Folder.owner_id == user_id,
            Folder.name == folder_name,
            Folder.parent_id.is_(None)
        ).first()
        
        if folder:
            return folder.id
        else:
            # 创建新文件夹
            new_folder = Folder(
                owner_id=user_id,
                name=folder_name,
                description=f"自动创建的{folder_name}文件夹",
                color=suggest_folder_color(folder_name),
                icon=suggest_folder_icon(folder_name),
                parent_id=None,
                order=0
            )
            db.add(new_folder)
            db.flush()
            return new_folder.id
    
    # 基于内容类型智能选择文件夹
    auto_folder_name = None
    
    if shared_item_type:
        auto_folder_name = CONTENT_TYPE_FOLDER_MAPPING.get(shared_item_type, "其他收藏")
    elif file:
        if hasattr(file, 'content_type'):
            if file.content_type.startswith("image/"):
                auto_folder_name = "图片收藏"
            elif file.content_type.startswith("video/"):
                auto_folder_name = "视频收藏"
            elif file.content_type.startswith("audio/"):
                auto_folder_name = "音频收藏"
            else:
                auto_folder_name = "文件收藏"
        else:
            auto_folder_name = "文件收藏"
    elif url:
        auto_folder_name = "链接收藏"
    else:
        auto_folder_name = DEFAULT_FOLDER_NAME
    
    # 查找或创建自动分类文件夹
    auto_folder = db.query(Folder).filter(
        Folder.owner_id == user_id,
        Folder.name == auto_folder_name,
        Folder.parent_id.is_(None)
    ).first()
    
    if auto_folder:
        return auto_folder.id
    else:
        # 创建自动分类文件夹
        new_auto_folder = Folder(
            owner_id=user_id,
            name=auto_folder_name,
            description=f"自动创建的{auto_folder_name}文件夹",
            color=suggest_folder_color(auto_folder_name),
            icon=suggest_folder_icon(auto_folder_name),
            parent_id=None,
            order=0
        )
        db.add(new_auto_folder)
        db.flush()
        return new_auto_folder.id


def generate_auto_tags(title: str, content: str, content_type: str) -> str:
    """
    自动生成标签
    
    Args:
        title: 标题
        content: 内容
        content_type: 内容类型
        
    Returns:
        逗号分隔的标签字符串
    """
    tags = []
    
    # 基于类型的标签
    if content_type in FILE_TYPE_TAG_MAPPING:
        tags.extend(FILE_TYPE_TAG_MAPPING[content_type])
    
    # 基于关键词的标签
    text_content = f"{title or ''} {content or ''}".lower()
    
    for tag, keywords in TAG_KEYWORD_MAPPING.items():
        if any(keyword in text_content for keyword in keywords):
            tags.append(tag)
    
    # 去重并限制数量
    unique_tags = list(dict.fromkeys(tags))  # 保持顺序的去重
    return ",".join(unique_tags[:MAX_AUTO_TAGS])  # 限制标签数量


async def extract_shared_item_info(db: Session, item_type: str, item_id: int) -> Dict[str, Any]:
    """从共享项中提取信息"""
    
    model_map = {
        "project": Project,
        "course": Course,
        "forum_topic": ForumTopic,
        "note": Note,
        "chat_message": ChatMessage
    }
    
    source_model = model_map.get(item_type)
    if not source_model:
        return {}
    
    source_item = db.get(source_model, item_id)
    if not source_item:
        return {}
    
    # 提取通用信息
    info = {}
    
    # 标题
    info["title"] = (
        getattr(source_item, 'title', None) or 
        getattr(source_item, 'name', None) or
        f"{item_type} #{item_id}"
    )
    
    # 内容
    info["content"] = (
        getattr(source_item, 'description', None) or
        getattr(source_item, 'content', None) or
        getattr(source_item, 'content_text', None)
    )
    
    # URL
    if hasattr(source_item, 'url') and source_item.url:
        info["url"] = source_item.url
    elif hasattr(source_item, 'media_url') and source_item.media_url:
        info["url"] = source_item.media_url
    elif hasattr(source_item, 'file_path') and source_item.file_path:
        info["url"] = source_item.file_path
    
    # 作者
    if hasattr(source_item, 'owner') and source_item.owner:
        info["author"] = source_item.owner.name
    elif hasattr(source_item, 'creator') and source_item.creator:
        info["author"] = source_item.creator.name
    elif hasattr(source_item, 'sender') and source_item.sender:
        info["author"] = source_item.sender.name
    
    # 标签
    info["tags"] = getattr(source_item, 'tags', None)
    
    # 缩略图
    info["thumbnail"] = (
        getattr(source_item, 'thumbnail', None) or
        getattr(source_item, 'cover_image_url', None)
    )
    
    return info


async def extract_url_info(url: str) -> Dict[str, Any]:
    """提取URL的基本信息"""
    import httpx
    import re
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            if response.status_code == 200:
                content = response.text
                
                # 简单的HTML解析提取标题
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else None
                
                # 提取description meta标签
                desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', content, re.IGNORECASE)
                description = desc_match.group(1).strip() if desc_match else None
                
                return {
                    "title": title,
                    "description": description,
                    "thumbnail": None,
                    "author": None
                }
    except (httpx.TimeoutException, httpx.HTTPError, ValueError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to extract URL info from {url}: {e}")
    
    return {}


# ================== 优化的权限验证 ==================

class PermissionValidator:
    """统一的权限验证器 - 避免与基础函数名称冲突"""
    
    @staticmethod
    def validate_folder_permission(db: Session, folder_id: int, user_id: int) -> Optional[Folder]:
        """验证文件夹权限，返回文件夹对象或None"""
        if validate_folder_permission(db, folder_id, user_id):
            return db.query(Folder).filter(
                Folder.id == folder_id,
                Folder.owner_id == user_id
            ).first()
        return None
    
    @staticmethod
    def validate_content_permission(db: Session, content_id: int, user_id: int) -> Optional[CollectedContent]:
        """验证收藏内容权限，返回内容对象或None"""
        if validate_content_permission(db, content_id, user_id):
            return db.query(CollectedContent).filter(
                CollectedContent.id == content_id,
                CollectedContent.owner_id == user_id
            ).first()
        return None
    
    @staticmethod
    def get_folder_or_403(db: Session, folder_id: int, user_id: int) -> Folder:
        """获取文件夹，无权限则抛异常 - 重命名避免递归"""
        # 使用模块级基础函数
        check_folder_access(db, folder_id, user_id)
        return db.query(Folder).filter(
            Folder.id == folder_id,
            Folder.owner_id == user_id
        ).first()
    
    @staticmethod
    def get_content_or_403(db: Session, content_id: int, user_id: int) -> CollectedContent:
        """获取收藏内容，无权限则抛异常 - 重命名避免递归"""
        # 使用模块级基础函数
        check_content_access(db, content_id, user_id)
        return db.query(CollectedContent).filter(
            CollectedContent.id == content_id,
            CollectedContent.owner_id == user_id
        ).first()


# ================== 优化的数据库查询 ==================

class OptimizedQueries:
    """优化的数据库查询类"""
    
    @staticmethod
    def get_folder_tree_recursive(db: Session, user_id: int, parent_id: Optional[int] = None) -> List[Dict]:
        """
        使用CTE递归查询获取完整文件夹树，避免N+1问题
        """
        # PostgreSQL CTE递归查询
        cte_query = text("""
            WITH RECURSIVE folder_tree AS (
                -- 基础查询：获取根级或指定父级的文件夹
                SELECT 
                    f.id, f.name, f.description, f.color, f.icon, 
                    f.parent_id, f.order, f.created_at, f.updated_at,
                    0 as depth,
                    ARRAY[f.id] as path_ids,
                    f.name as path_names
                FROM folders f
                WHERE f.owner_id = :user_id 
                    AND f.parent_id IS NOT DISTINCT FROM :parent_id
                
                UNION ALL
                
                -- 递归查询：获取子文件夹
                SELECT 
                    f.id, f.name, f.description, f.color, f.icon,
                    f.parent_id, f.order, f.created_at, f.updated_at,
                    ft.depth + 1,
                    ft.path_ids || f.id,
                    ft.path_names || ' > ' || f.name
                FROM folders f
                INNER JOIN folder_tree ft ON f.parent_id = ft.id
                WHERE f.owner_id = :user_id
            )
            SELECT 
                ft.*,
                COALESCE(stats.content_count, 0) as content_count,
                COALESCE(stats.subfolder_count, 0) as subfolder_count,
                COALESCE(stats.total_size, 0) as total_size
            FROM folder_tree ft
            LEFT JOIN (
                SELECT 
                    cc.folder_id,
                    COUNT(cc.id) as content_count,
                    SUM(COALESCE(cc.file_size, 0)) as total_size
                FROM collected_contents cc 
                WHERE cc.owner_id = :user_id AND cc.status != 'deleted'
                GROUP BY cc.folder_id
            ) stats ON ft.id = stats.folder_id
            LEFT JOIN (
                SELECT 
                    parent_id,
                    COUNT(*) as subfolder_count
                FROM folders 
                WHERE owner_id = :user_id
                GROUP BY parent_id
            ) sub_stats ON ft.id = sub_stats.parent_id
            ORDER BY ft.depth, ft.order, ft.name
        """)
        
        result = db.execute(cte_query, {
            'user_id': user_id,
            'parent_id': parent_id
        }).fetchall()
        
        return [dict(row) for row in result]
    
    @staticmethod
    def batch_check_collected_status(db: Session, user_id: int, items: List[Dict[str, Any]]) -> Dict[str, bool]:
        """
        批量检查收藏状态，避免多次单独查询
        
        Args:
            items: [{"type": "project", "id": 1}, {"type": "course", "id": 2}]
        
        Returns:
            {"project_1": True, "course_2": False}
        """
        if not items:
            return {}
        
        # 按类型分组
        items_by_type = {}
        for item in items:
            item_type = item["type"]
            if item_type not in items_by_type:
                items_by_type[item_type] = []
            items_by_type[item_type].append(item["id"])
        
        result = {}
        
        # 批量查询每种类型
        for item_type, item_ids in items_by_type.items():
            if item_type not in COLLECTION_CONFIGS:
                continue
                
            collected_items = db.query(CollectedContent.shared_item_id).filter(
                CollectedContent.owner_id == user_id,
                CollectedContent.shared_item_type == item_type,
                CollectedContent.shared_item_id.in_(item_ids),
                CollectedContent.status != "deleted"
            ).all()
            
            collected_ids = {item.shared_item_id for item in collected_items}
            
            for item_id in item_ids:
                key = f"{item_type}_{item_id}"
                result[key] = item_id in collected_ids
        
        return result


# ================== 优化的业务逻辑 ==================

class CollectionManager:
    """收藏管理器 - 集中处理收藏相关业务逻辑"""
    
    def __init__(self, db: Session):
        self.db = db
        self.permission_validator = PermissionValidator()
        self.queries = OptimizedQueries()
    
    async def get_or_create_collection_folder(self, user_id: int, item_type: str) -> Folder:
        """获取或创建收藏文件夹 - 优化版本，使用基础验证函数"""
        validate_item_type(item_type)  # 使用基础函数
        
        config = COLLECTION_CONFIGS[item_type]
        
        # 首先尝试查找现有文件夹
        folder = self.db.query(Folder).filter(
            Folder.owner_id == user_id,
            Folder.name == config["folder_name"]
        ).first()
        
        if folder:
            return folder
        
        # 创建新文件夹 - 使用基础函数提供的颜色和图标建议
        folder = Folder(
            owner_id=user_id,
            name=config["folder_name"],
            description=f"系统自动创建的{config['display_name']}收藏夹",
            color=suggest_folder_color(config["folder_name"]),  # 使用基础函数
            icon=suggest_folder_icon(config["folder_name"]),    # 使用基础函数
            parent_id=None,
            order=0
        )
        
        self.db.add(folder)
        self.db.commit()
        self.db.refresh(folder)
        
        logger.info(f"为用户 {user_id} 创建了新的{item_type}收藏文件夹")
        return folder
    
    def validate_item_type(self, item_type: str) -> None:
        """验证收藏类型 - 使用基础函数"""
        validate_item_type(item_type)
    
    async def check_item_exists(self, item_type: str, item_id: int) -> Any:
        """检查项目/课程是否存在 - 优化版本，使用基础验证"""
        validate_item_type(item_type)  # 使用基础函数
        
        config = COLLECTION_CONFIGS[item_type]
        model = config["model"]
        
        item = self.db.query(model).filter(model.id == item_id).first()
        
        if not item:
            display_name = get_type_display_name(item_type)  # 使用基础函数
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{display_name}未找到 (ID: {item_id})"
            )
        
        return item
    
    async def batch_add_to_collection(self, user_id: int, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量添加到收藏 - 新增功能
        
        Args:
            items: [{"type": "project", "id": 1}, {"type": "course", "id": 2}]
            
        Returns:
            {"success_count": 2, "failed_items": [], "created_folders": ["项目", "课程"]}
        """
        if not items:
            return {"success_count": 0, "failed_items": [], "created_folders": []}
        
        # 验证所有项目类型
        for item in items:
            validate_item_type(item["type"])  # 使用基础函数
        
        # 批量检查现有收藏状态
        collected_status = self.queries.batch_check_collected_status(self.db, user_id, items)
        
        success_count = 0
        failed_items = []
        created_folders = []
        
        # 按类型分组处理
        items_by_type = {}
        for item in items:
            item_type = item["type"]
            if item_type not in items_by_type:
                items_by_type[item_type] = []
            items_by_type[item_type].append(item)
        
        for item_type, type_items in items_by_type.items():
            try:
                # 获取或创建文件夹
                folder = await self.get_or_create_collection_folder(user_id, item_type)
                config = COLLECTION_CONFIGS[item_type]
                
                if get_type_display_name(item_type) not in created_folders:  # 使用基础函数
                    created_folders.append(get_type_display_name(item_type))  # 使用基础函数
                
                # 批量创建收藏记录
                new_collections = []
                for item in type_items:
                    item_id = item["id"]
                    key = f"{item_type}_{item_id}"
                    
                    # 跳过已收藏的项目
                    if collected_status.get(key, False):
                        failed_items.append({
                            "item": item,
                            "reason": "已经收藏过"
                        })
                        continue
                    
                    # 验证项目存在性
                    try:
                        existing_item = await self.check_item_exists(item_type, item_id)
                    except HTTPException as e:
                        failed_items.append({
                            "item": item,
                            "reason": str(e.detail)
                        })
                        continue
                    
                    # 获取正确的标题字段
                    if item_type in ["project", "course", "knowledge_base"]:
                        title = getattr(existing_item, 'title', f'{get_type_display_name(item_type)}收藏')
                    else:  # note_folder
                        title = getattr(existing_item, 'name', f'{get_type_display_name(item_type)}收藏')
                    
                    # 创建收藏记录
                    collection_item = CollectedContent(
                        owner_id=user_id,
                        folder_id=folder.id,
                        type=item_type,
                        title=title,
                        shared_item_type=item_type,
                        shared_item_id=item_id,
                        status="active",
                        embedding=None  # 可以后续异步生成
                    )
                    new_collections.append(collection_item)
                    success_count += 1
                
                # 批量插入
                if new_collections:
                    self.db.add_all(new_collections)
            
            except Exception as e:
                logger.error(f"批量添加{item_type}收藏失败: {str(e)}")
                for item in type_items:
                    failed_items.append({
                        "item": item,
                        "reason": f"系统错误: {str(e)}"
                    })
        
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量收藏提交失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"批量收藏失败: {str(e)}"
            )
        
        return {
            "success_count": success_count,
            "failed_items": failed_items,
            "created_folders": created_folders
        }
