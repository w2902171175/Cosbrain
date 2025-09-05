# project/services/mcp_service.py
"""
MCP模块服务层 - 业务逻辑分离
基于优化框架为 MCP 模块提供高效的服务层实现
"""
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from datetime import datetime
import logging
import httpx
import asyncio
import time

# 核心导入
from project.models import UserMcpConfig
import project.schemas as schemas
from project.ai_providers.security_utils import decrypt_key, encrypt_key
from project.utils.optimization.production_utils import cache_manager

# MCP专用模块导入
try:
    from project.config.mcp_config import mcp_config, get_provider_headers
    from project.utils.async_cache.mcp_cache_manager import mcp_cache_manager
    from project.utils.monitoring.mcp_performance_monitor import mcp_performance_monitor
except ImportError:
    # 如果模块不存在，使用默认值
    mcp_config = None
    mcp_cache_manager = cache_manager
    mcp_performance_monitor = None

logger = logging.getLogger(__name__)

class MCPConfigService:
    """MCP配置管理服务"""
    
    @staticmethod
    def get_user_configs_optimized(
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 50
    ) -> Tuple[List[UserMcpConfig], int]:
        """获取用户MCP配置列表 - 优化版本"""
        try:
            # 优化查询：使用joinedload避免N+1问题
            query = db.query(UserMcpConfig).filter(
                UserMcpConfig.owner_id == user_id
            ).order_by(UserMcpConfig.updated_at.desc())
            
            total = query.count()
            configs = query.offset(skip).limit(limit).all()
            
            logger.info(f"用户 {user_id} 获取到 {len(configs)} 个MCP配置")
            return configs, total
            
        except Exception as e:
            logger.error(f"获取用户MCP配置失败: {e}")
            raise
    
    @staticmethod
    def create_mcp_config_optimized(
        db: Session, 
        user_id: int, 
        config_data: Dict[str, Any]
    ) -> UserMcpConfig:
        """创建MCP配置 - 优化版本"""
        try:
            # 数据验证和处理
            config_dict = MCPUtilities.validate_config_data(config_data)
            
            # 加密API密钥（如果提供）
            if config_dict.get('api_key'):
                config_dict['api_key_encrypted'] = encrypt_key(config_dict.pop('api_key'))
            
            # 创建配置对象
            db_config = UserMcpConfig(
                owner_id=user_id,
                **config_dict
            )
            
            db.add(db_config)
            db.commit()
            db.refresh(db_config)
            
            # 清除相关缓存
            MCPUtilities.clear_user_cache(user_id)
            
            logger.info(f"用户 {user_id} 创建MCP配置 {db_config.id}")
            return db_config
            
        except IntegrityError as e:
            db.rollback()
            logger.error(f"创建MCP配置数据完整性错误: {e}")
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"创建MCP配置失败: {e}")
            raise
    
    @staticmethod
    def get_mcp_config_optimized(
        db: Session, 
        config_id: int, 
        user_id: int
    ) -> Optional[UserMcpConfig]:
        """获取单个MCP配置 - 优化版本"""
        try:
            config = db.query(UserMcpConfig).filter(
                UserMcpConfig.id == config_id,
                UserMcpConfig.owner_id == user_id
            ).first()
            
            if config:
                logger.info(f"用户 {user_id} 获取MCP配置 {config_id}")
            else:
                logger.warning(f"用户 {user_id} 尝试访问不存在的MCP配置 {config_id}")
            
            return config
            
        except Exception as e:
            logger.error(f"获取MCP配置失败: {e}")
            raise
    
    @staticmethod
    def update_mcp_config_optimized(
        db: Session, 
        config_id: int, 
        user_id: int, 
        update_data: Dict[str, Any]
    ) -> Optional[UserMcpConfig]:
        """更新MCP配置 - 优化版本"""
        try:
            config = MCPConfigService.get_mcp_config_optimized(db, config_id, user_id)
            if not config:
                return None
            
            # 验证更新数据
            validated_data = MCPUtilities.validate_update_data(update_data)
            
            # 处理API密钥更新
            if 'api_key' in validated_data:
                if validated_data['api_key']:
                    validated_data['api_key_encrypted'] = encrypt_key(validated_data.pop('api_key'))
                else:
                    validated_data['api_key_encrypted'] = None
                    validated_data.pop('api_key', None)
            
            # 更新字段
            for key, value in validated_data.items():
                setattr(config, key, value)
            
            config.updated_at = datetime.now()
            db.commit()
            db.refresh(config)
            
            # 清除相关缓存
            MCPUtilities.clear_config_cache(config_id)
            MCPUtilities.clear_user_cache(user_id)
            
            logger.info(f"用户 {user_id} 更新MCP配置 {config_id}")
            return config
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新MCP配置失败: {e}")
            raise
    
    @staticmethod
    def delete_mcp_config_optimized(
        db: Session, 
        config_id: int, 
        user_id: int
    ) -> bool:
        """删除MCP配置 - 优化版本"""
        try:
            config = MCPConfigService.get_mcp_config_optimized(db, config_id, user_id)
            if not config:
                return False
            
            db.delete(config)
            db.commit()
            
            # 清除相关缓存
            MCPUtilities.clear_config_cache(config_id)
            MCPUtilities.clear_user_cache(user_id)
            
            logger.info(f"用户 {user_id} 删除MCP配置 {config_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"删除MCP配置失败: {e}")
            raise

class MCPConnectionService:
    """MCP连接管理服务"""
    
    @staticmethod
    async def test_mcp_connection_optimized(
        db: Session, 
        config_id: int, 
        user_id: int
    ) -> Dict[str, Any]:
        """测试MCP连接 - 优化版本"""
        try:
            config = MCPConfigService.get_mcp_config_optimized(db, config_id, user_id)
            if not config:
                return {"status": "error", "message": "MCP配置未找到"}
            
            # 检查缓存的连接状态
            cache_key = f"mcp_connection_status_{config_id}"
            cached_status = mcp_cache_manager.get(cache_key)
            if cached_status:
                return cached_status
            
            # 解密API密钥
            api_key = None
            if config.api_key_encrypted:
                api_key = decrypt_key(config.api_key_encrypted)
            
            # 构建请求头
            headers = MCPUtilities.get_provider_headers(config.service_type, api_key)
            
            # 测试连接
            test_url = f"{config.api_endpoint}/health" if config.api_endpoint else None
            if not test_url:
                return {"status": "error", "message": "MCP配置缺少有效的端点URL"}
            
            start_time = time.time()
            status_result = await MCPConnectionService._perform_connection_test(
                test_url, headers, config_id, start_time
            )
            
            # 缓存结果
            cache_ttl = 300 if status_result["status"] == "success" else 60
            mcp_cache_manager.set(cache_key, status_result, ttl=cache_ttl)
            
            return status_result
            
        except Exception as e:
            logger.error(f"测试MCP连接失败: {e}")
            return {"status": "error", "message": f"连接测试失败: {str(e)}"}
    
    @staticmethod
    async def _perform_connection_test(
        test_url: str, 
        headers: Dict[str, str], 
        config_id: int, 
        start_time: float
    ) -> Dict[str, Any]:
        """执行连接测试"""
        max_retries = 3
        retry_delay = 1.0
        
        async with httpx.AsyncClient() as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.get(
                        test_url, 
                        headers=headers, 
                        timeout=30.0
                    )
                    
                    if response.status_code < 400:
                        response_time = time.time() - start_time
                        
                        # 记录性能指标
                        if mcp_performance_monitor:
                            mcp_performance_monitor.record_request(
                                config_id=config_id,
                                response_time=response_time,
                                status_code=response.status_code,
                                success=True
                            )
                        
                        return {
                            "status": "success",
                            "message": f"成功连接到MCP服务: {test_url}",
                            "response_time": response_time,
                            "timestamp": datetime.now().isoformat()
                        }
                    
                except httpx.RequestError as e:
                    logger.warning(f"MCP连接测试重试 {attempt + 1}/{max_retries + 1}: {e}")
                    if attempt < max_retries:
                        await asyncio.sleep(retry_delay)
                    continue
        
        return {
            "status": "error",
            "message": f"连接测试失败，已重试 {max_retries} 次",
            "timestamp": datetime.now().isoformat()
        }

class MCPToolsService:
    """MCP工具管理服务"""
    
    @staticmethod
    async def get_mcp_tools_optimized(
        db: Session, 
        config_id: int, 
        user_id: int
    ) -> List[Dict[str, Any]]:
        """获取MCP工具列表 - 优化版本"""
        try:
            config = MCPConfigService.get_mcp_config_optimized(db, config_id, user_id)
            if not config:
                return []
            
            # 检查缓存
            cache_key = f"mcp_tools_{config_id}"
            cached_tools = mcp_cache_manager.get(cache_key)
            if cached_tools:
                return cached_tools
            
            # 解密API密钥
            api_key = None
            if config.api_key_encrypted:
                api_key = decrypt_key(config.api_key_encrypted)
            
            headers = MCPUtilities.get_provider_headers(config.service_type, api_key)
            tools_url = f"{config.api_endpoint}/tools"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    tools_url,
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    tools_data = response.json()
                    tools_list = tools_data.get('tools', [])
                    
                    # 缓存结果
                    mcp_cache_manager.set(cache_key, tools_list, ttl=3600)  # 1小时缓存
                    
                    logger.info(f"获取到 {len(tools_list)} 个MCP工具 (配置ID: {config_id})")
                    return tools_list
                else:
                    logger.error(f"获取MCP工具失败: HTTP {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"获取MCP工具列表失败: {e}")
            return []

class MCPUtilities:
    """MCP工具类"""
    
    @staticmethod
    def validate_config_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置数据"""
        required_fields = ['name', 'service_type', 'api_endpoint']
        for field in required_fields:
            if not data.get(field):
                raise ValueError(f"缺少必需字段: {field}")
        
        # 验证URL格式
        api_endpoint = data.get('api_endpoint')
        if api_endpoint and not api_endpoint.startswith(('http://', 'https://')):
            raise ValueError("API端点必须是有效的HTTP/HTTPS URL")
        
        return data
    
    @staticmethod
    def validate_update_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证更新数据"""
        allowed_fields = [
            'name', 'service_type', 'api_endpoint', 'protocol_type', 
            'is_active', 'description', 'api_key'
        ]
        
        validated_data = {}
        for key, value in data.items():
            if key in allowed_fields and value is not None:
                validated_data[key] = value
        
        return validated_data
    
    @staticmethod
    def get_provider_headers(service_type: str, api_key: Optional[str] = None) -> Dict[str, str]:
        """获取服务提供商请求头"""
        if mcp_config and hasattr(mcp_config, 'get_provider_headers'):
            return get_provider_headers(service_type, api_key)
        
        # 默认请求头
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers
    
    @staticmethod
    def clear_config_cache(config_id: int):
        """清除配置相关缓存"""
        cache_keys = [
            f"mcp_connection_status_{config_id}",
            f"mcp_tools_{config_id}",
            f"mcp_config_{config_id}"
        ]
        for key in cache_keys:
            mcp_cache_manager.delete(key)
    
    @staticmethod
    def clear_user_cache(user_id: int):
        """清除用户相关缓存"""
        cache_key = f"user_mcp_configs_{user_id}"
        mcp_cache_manager.delete(cache_key)
    
    @staticmethod
    def build_safe_response_dict(config: UserMcpConfig) -> Dict[str, Any]:
        """构建安全的响应字典"""
        return {
            'id': config.id,
            'owner_id': config.owner_id,
            'name': config.name,
            'service_type': getattr(config, 'service_type', None),
            'api_endpoint': getattr(config, 'api_endpoint', None),
            'protocol_type': config.protocol_type,
            'is_active': config.is_active,
            'description': config.description,
            'created_at': config.created_at or datetime.now(),
            'updated_at': config.updated_at or config.created_at or datetime.now(),
            'api_key_encrypted': None  # 永远不返回加密的密钥
        }
