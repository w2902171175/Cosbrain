# project/utils/config_router_base.py
"""
配置路由基类 - 消除配置管理路由中的重复代码
提供标准化的CRUD操作模式
"""

from typing import Type, List, Optional, Any, Dict
from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel

from project.utils import get_current_user_id, get_db
from project.ai_providers.security_utils import encrypt_key, decrypt_key


class BaseConfigRouter:
    """配置路由基类，提供通用的CRUD操作"""
    
    def __init__(
        self,
        model_class: Type,
        create_schema: Type[BaseModel],
        response_schema: Type[BaseModel],
        update_schema: Type[BaseModel],
        config_type_name: str,  # 如 "TTS配置"、"搜索引擎配置"
        require_api_key: bool = True
    ):
        self.model_class = model_class
        self.create_schema = create_schema
        self.response_schema = response_schema
        self.update_schema = update_schema
        self.config_type_name = config_type_name
        self.require_api_key = require_api_key
    
    def validate_config_data(self, config_data: BaseModel) -> None:
        """验证配置数据"""
        if self.require_api_key and hasattr(config_data, 'api_key'):
            if not config_data.api_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="API 密钥不能为空"
                )
    
    def check_name_conflict(
        self, 
        db: Session, 
        owner_id: int, 
        name: str, 
        exclude_id: Optional[int] = None
    ) -> None:
        """检查配置名称冲突"""
        query = db.query(self.model_class).filter(
            and_(
                self.model_class.owner_id == owner_id,
                self.model_class.name == name,
                self.model_class.is_active == True
            )
        )
        
        if exclude_id:
            query = query.filter(self.model_class.id != exclude_id)
        
        existing_config = query.first()
        if existing_config:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"已存在同名且活跃的{self.config_type_name}。请选择其他名称或停用旧配置。"
            )
    
    def prepare_config_data(self, config_data: BaseModel) -> Dict[str, Any]:
        """准备配置数据，包括加密敏感信息"""
        config_dict = config_data.model_dump(exclude_unset=True)
        
        # 加密API密钥
        if 'api_key' in config_dict and config_dict['api_key']:
            config_dict['api_key_encrypted'] = encrypt_key(config_dict['api_key'])
            del config_dict['api_key']  # 移除明文密钥
        
        return config_dict
    
    async def create_config(
        self,
        config_data: BaseModel,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        """创建配置的通用方法"""
        # 验证配置数据
        self.validate_config_data(config_data)
        
        # 检查名称冲突
        self.check_name_conflict(db, current_user_id, config_data.name)
        
        # 准备配置数据
        config_dict = self.prepare_config_data(config_data)
        config_dict['owner_id'] = current_user_id
        
        # 创建数据库记录
        db_config = self.model_class(**config_dict)
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        
        return db_config
    
    async def get_configs_list(
        self,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        include_inactive: bool = False
    ) -> List:
        """获取配置列表的通用方法"""
        query = db.query(self.model_class).filter(
            self.model_class.owner_id == current_user_id
        )
        
        if not include_inactive:
            query = query.filter(self.model_class.is_active == True)
        
        return query.order_by(self.model_class.created_at.desc()).all()
    
    async def get_config_by_id(
        self,
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        """根据ID获取配置的通用方法"""
        config = db.query(self.model_class).filter(
            and_(
                self.model_class.id == config_id,
                self.model_class.owner_id == current_user_id
            )
        ).first()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到指定的{self.config_type_name}"
            )
        
        return config
    
    async def update_config(
        self,
        config_id: int,
        update_data: BaseModel,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        """更新配置的通用方法"""
        # 获取现有配置
        config = await self.get_config_by_id(config_id, current_user_id, db)
        
        # 验证更新数据
        if hasattr(update_data, 'name') and update_data.name:
            self.check_name_conflict(db, current_user_id, update_data.name, config_id)
        
        # 准备更新数据
        update_dict = self.prepare_config_data(update_data)
        
        # 更新配置
        for field, value in update_dict.items():
            if value is not None:
                setattr(config, field, value)
        
        db.commit()
        db.refresh(config)
        
        return config
    
    async def delete_config(
        self,
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db),
        soft_delete: bool = True
    ):
        """删除配置的通用方法"""
        config = await self.get_config_by_id(config_id, current_user_id, db)
        
        if soft_delete:
            # 软删除：标记为非活跃
            config.is_active = False
            db.commit()
        else:
            # 硬删除：从数据库中移除
            db.delete(config)
            db.commit()


def create_config_endpoints(
    router,
    base_router: BaseConfigRouter,
    route_prefix: str = ""
):
    """为配置路由创建标准端点的工厂函数"""
    
    @router.post(f"{route_prefix}/")
    async def create_config(
        config_data: Any,  # 使用Any避免类型注解问题
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        return await base_router.create_config(config_data, current_user_id, db)
    
    @router.get(f"{route_prefix}/")
    async def list_configs(
        include_inactive: bool = False,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        return await base_router.get_configs_list(current_user_id, db, include_inactive)
    
    @router.get(f"{route_prefix}/{{config_id}}")
    async def get_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        return await base_router.get_config_by_id(config_id, current_user_id, db)
    
    @router.put(f"{route_prefix}/{{config_id}}")
    async def update_config(
        config_id: int,
        update_data: Any,  # 使用Any避免类型注解问题
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        return await base_router.update_config(config_id, update_data, current_user_id, db)
    
    @router.delete(f"{route_prefix}/{{config_id}}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_config(
        config_id: int,
        current_user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
    ):
        await base_router.delete_config(config_id, current_user_id, db)
