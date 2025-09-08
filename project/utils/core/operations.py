# project/utils/core/operations.py
"""通用操作工具模块"""

from typing import Optional, List, Dict, Any, Type, TypeVar
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime

from project.models import Project, User
from .common_utils import debug_operation
from .error_handler import not_found, validation_failed

T = TypeVar('T')


class QueryBuilder:
    def __init__(self, session: Session, model: Type[T]):
        self.session = session
        self.model = model
        self.query = session.query(model)
        self._filters = []
        self._orders = []
    
    def filter_by_id(self, id_value: int) -> 'QueryBuilder':
        if id_value:
            self._filters.append(self.model.id == id_value)
        return self
    
    def filter_by_user(self, user_id: int, field_name: str = 'creator_id') -> 'QueryBuilder':
        if user_id:
            field = getattr(self.model, field_name, None)
            if field:
                self._filters.append(field == user_id)
        return self
    
    def filter_by_status(self, status_value: Any, field_name: str = 'status') -> 'QueryBuilder':
        if status_value is not None:
            field = getattr(self.model, field_name, None)
            if field:
                self._filters.append(field == status_value)
        return self
    
    def filter_by_date_range(self, start_date: datetime = None, end_date: datetime = None,
                           field_name: str = 'created_at') -> 'QueryBuilder':
        field = getattr(self.model, field_name, None)
        if field:
            if start_date:
                self._filters.append(field >= start_date)
            if end_date:
                self._filters.append(field <= end_date)
        return self
    
    def search_text(self, text: str, fields: List[str] = None) -> 'QueryBuilder':
        if text and fields:
            conditions = []
            for field_name in fields:
                field = getattr(self.model, field_name, None)
                if field:
                    conditions.append(field.like(f'%{text}%'))
            if conditions:
                self._filters.append(or_(*conditions))
        return self
    
    def order_by(self, field_name: str, desc: bool = False) -> 'QueryBuilder':
        field = getattr(self.model, field_name, None)
        if field:
            self._orders.append(field.desc() if desc else field.asc())
        return self
    
    def paginate(self, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        if self._filters:
            self.query = self.query.filter(and_(*self._filters))
        if self._orders:
            self.query = self.query.order_by(*self._orders)
        
        total = self.query.count()
        offset = (page - 1) * per_page
        items = self.query.offset(offset).limit(per_page).all()
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
            "has_prev": page > 1,
            "has_next": page * per_page < total
        }
    
    def first_or_404(self, error_message: str = "资源未找到") -> T:
        if self._filters:
            self.query = self.query.filter(and_(*self._filters))
        
        result = self.query.first()
        if not result:
            not_found(error_message)
        return result
    
    def all(self) -> List[T]:
        if self._filters:
            self.query = self.query.filter(and_(*self._filters))
        if self._orders:
            self.query = self.query.order_by(*self._orders)
        return self.query.all()


class DbOps:
    @staticmethod
    def get_or_404(db: Session, model: Type[T], id_value: int, error_message: str = None) -> T:
        obj = db.query(model).filter(model.id == id_value).first()
        if not obj:
            error_msg = error_message or f"{model.__name__}未找到"
            not_found(error_msg, id_value)
        return obj
    
    @staticmethod
    def soft_delete(db: Session, obj: Any, commit: bool = True) -> None:
        if hasattr(obj, 'is_deleted'):
            obj.is_deleted = True
        elif hasattr(obj, 'deleted_at'):
            obj.deleted_at = datetime.utcnow()
        elif hasattr(obj, 'status'):
            obj.status = 'deleted'
        else:
            db.delete(obj)
        
        if commit:
            db.commit()
    
    @staticmethod
    def batch_update(db: Session, model: Type[T], filters: Dict[str, Any],
                    updates: Dict[str, Any], commit: bool = True) -> int:
        query = db.query(model)
        for field, value in filters.items():
            if hasattr(model, field):
                query = query.filter(getattr(model, field) == value)
        
        count = query.update(updates)
        if commit:
            db.commit()
        
        debug_operation("批量更新", model=model.__name__, count=count)
        return count
    
    @staticmethod
    def get_related_count(db: Session, obj: Any, relation_name: str) -> int:
        if hasattr(obj, relation_name):
            relation = getattr(obj, relation_name)
            if hasattr(relation, 'count'):
                return relation.count()
        return 0


class Validator:
    @staticmethod
    def required_fields(data: Dict[str, Any], *fields: str) -> None:
        for field in fields:
            if field not in data or data[field] is None:
                validation_failed(field, "此字段为必填项")
            if isinstance(data[field], str) and not data[field].strip():
                validation_failed(field, "此字段不能为空")
    
    @staticmethod
    def string_length(value: str, field_name: str, min_length: int = None, max_length: int = None) -> None:
        if not isinstance(value, str):
            return
        
        length = len(value.strip())
        if min_length and length < min_length:
            validation_failed(field_name, f"最少需要{min_length}个字符")
        if max_length and length > max_length:
            validation_failed(field_name, f"最多允许{max_length}个字符")
    
    @staticmethod
    def email(email: str, field_name: str = "邮箱") -> None:
        import re
        if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            validation_failed(field_name, "邮箱格式不正确")
    
    @staticmethod
    def choice(value: Any, choices: List[Any], field_name: str, allow_none: bool = False) -> None:
        if value is None and allow_none:
            return
        if value not in choices:
            validation_failed(field_name, f"必须是以下值之一: {', '.join(map(str, choices))}")


class UserOps:
    @staticmethod
    def get_name(db: Session, user_id: int) -> str:
        user = db.query(User).filter(User.id == user_id).first()
        return user.username if user else "未知用户"
    
    @staticmethod
    def fill_names(db: Session, items: List[Any], user_field: str = 'creator_id') -> None:
        if not items:
            return
        
        user_ids = {getattr(item, user_field, None) for item in items if getattr(item, user_field, None)}
        if not user_ids:
            return
        
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {user.id: user.username for user in users}
        
        for item in items:
            user_id = getattr(item, user_field, None)
            if user_id:
                name_field = user_field.replace('_id', '_name')
                setattr(item, name_field, user_map.get(user_id, "未知用户"))
    
    @staticmethod
    def has_permission(db: Session, user_id: int, resource_id: int, resource_type: str,
                      permission: str = "read") -> bool:
        if resource_type == "project":
            project = db.query(Project).filter(Project.id == resource_id).first()
            if not project:
                return False
            if project.creator_id == user_id:
                return True
        return False


class ProjectOps:
    @staticmethod
    def get_with_creator(db: Session, project_id: int) -> Project:
        project = DbOps.get_or_404(db, Project, project_id, "项目")
        if project.creator_id:
            project.creator_name = UserOps.get_name(db, project.creator_id)
        return project
    
    @staticmethod
    def has_permission(db: Session, project_id: int, user_id: int, action: str = "view") -> bool:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return False
        
        if project.creator_id == user_id:
            return True
        
        if action == "view":
            return getattr(project, 'is_public', True)
        elif action in ["edit", "delete"]:
            return project.creator_id == user_id
        
        return False
    
    @staticmethod
    def update_stats(db: Session, project_id: int) -> None:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            debug_operation("更新项目统计", project_id=project_id)


# 便捷函数
def build_query(db: Session, model: Type[T]) -> QueryBuilder:
    return QueryBuilder(db, model)


def get_or_404(db: Session, model: Type[T], id_value: int, error_message: str = None) -> T:
    return DbOps.get_or_404(db, model, id_value, error_message)


def required(*fields: str):
    def validate_data(data: Dict[str, Any]) -> None:
        Validator.required_fields(data, *fields)
    return validate_data


def fill_user_names(db: Session, items: List[Any], user_field: str = 'creator_id') -> None:
    UserOps.fill_names(db, items, user_field)


# 向后兼容的别名
create_query_builder = build_query
validate_required = lambda data, *fields: Validator.required_fields(data, *fields)
DatabaseOperations = DbOps
ValidationUtils = Validator
UserOperations = UserOps
ProjectOperations = ProjectOps
