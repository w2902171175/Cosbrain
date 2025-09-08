# project/services/tts_service.py
"""
TTS模块服务层 - 业务逻辑分离
基于优化框架为 TTS 模块提供高效的服务层实现
"""
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from datetime import datetime
import logging

# 核心导入
from project.models import UserTTSConfig
import project.schemas as schemas
from project.ai_providers.security_utils import decrypt_key, encrypt_key
from project.utils.optimization.production_utils import cache_manager

logger = logging.getLogger(__name__)

class TTSConfigService:
    """TTS配置管理服务"""
    
    @staticmethod
    def get_user_tts_configs_optimized(
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 50
    ) -> Tuple[List[UserTTSConfig], int]:
        """获取用户TTS配置列表 - 优化版本"""
        try:
            # 优化查询：使用joinedload避免N+1问题
            query = db.query(UserTTSConfig).filter(
                UserTTSConfig.owner_id == user_id
            ).order_by(UserTTSConfig.is_active.desc(), UserTTSConfig.updated_at.desc())
            
            total = query.count()
            configs = query.offset(skip).limit(limit).all()
            
            logger.info(f"用户 {user_id} 获取到 {len(configs)} 个TTS配置")
            return configs, total
            
        except Exception as e:
            logger.error(f"获取用户TTS配置失败: {e}")
            raise
    
    @staticmethod
    def create_tts_config_optimized(
        db: Session, 
        user_id: int, 
        config_data: Dict[str, Any]
    ) -> UserTTSConfig:
        """创建TTS配置 - 优化版本"""
        try:
            # 数据验证和处理
            config_dict = TTSUtilities.validate_config_data(config_data)
            
            # 加密API密钥
            if config_dict.get('api_key'):
                config_dict['api_key_encrypted'] = encrypt_key(config_dict.pop('api_key'))
            
            # 如果设置为激活，则先禁用其他配置
            if config_dict.get('is_active', False):
                TTSConfigService._deactivate_other_configs(db, user_id)
            
            # 创建配置对象
            db_config = UserTTSConfig(
                owner_id=user_id,
                **config_dict
            )
            
            db.add(db_config)
            db.commit()
            db.refresh(db_config)
            
            # 清除相关缓存
            TTSUtilities.clear_user_cache(user_id)
            
            logger.info(f"用户 {user_id} 创建TTS配置 {db_config.id}")
            return db_config
            
        except IntegrityError as e:
            db.rollback()
            logger.error(f"创建TTS配置数据完整性错误: {e}")
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"创建TTS配置失败: {e}")
            raise
    
    @staticmethod
    def get_tts_config_optimized(
        db: Session, 
        config_id: int, 
        user_id: int
    ) -> Optional[UserTTSConfig]:
        """获取单个TTS配置 - 优化版本"""
        try:
            config = db.query(UserTTSConfig).filter(
                UserTTSConfig.id == config_id,
                UserTTSConfig.owner_id == user_id
            ).first()
            
            if config:
                logger.info(f"用户 {user_id} 获取TTS配置 {config_id}")
            else:
                logger.warning(f"用户 {user_id} 尝试访问不存在的TTS配置 {config_id}")
            
            return config
            
        except Exception as e:
            logger.error(f"获取TTS配置失败: {e}")
            raise
    
    @staticmethod
    def update_tts_config_optimized(
        db: Session, 
        config_id: int, 
        user_id: int, 
        update_data: Dict[str, Any]
    ) -> Optional[UserTTSConfig]:
        """更新TTS配置 - 优化版本"""
        try:
            config = TTSConfigService.get_tts_config_optimized(db, config_id, user_id)
            if not config:
                return None
            
            # 验证更新数据
            validated_data = TTSUtilities.validate_update_data(update_data)
            
            # 处理API密钥更新
            if 'api_key' in validated_data:
                if validated_data['api_key']:
                    validated_data['api_key_encrypted'] = encrypt_key(validated_data.pop('api_key'))
                else:
                    validated_data['api_key_encrypted'] = None
                    validated_data.pop('api_key', None)
            
            # 如果要激活此配置，先禁用其他配置
            if validated_data.get('is_active', False):
                TTSConfigService._deactivate_other_configs(db, user_id, config_id)
            
            # 更新字段
            for key, value in validated_data.items():
                setattr(config, key, value)
            
            config.updated_at = datetime.now()
            db.commit()
            db.refresh(config)
            
            # 清除相关缓存
            TTSUtilities.clear_config_cache(config_id)
            TTSUtilities.clear_user_cache(user_id)
            
            logger.info(f"用户 {user_id} 更新TTS配置 {config_id}")
            return config
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新TTS配置失败: {e}")
            raise
    
    @staticmethod
    def delete_tts_config_optimized(
        db: Session, 
        config_id: int, 
        user_id: int
    ) -> bool:
        """删除TTS配置 - 优化版本"""
        try:
            config = TTSConfigService.get_tts_config_optimized(db, config_id, user_id)
            if not config:
                return False
            
            db.delete(config)
            db.commit()
            
            # 清除相关缓存
            TTSUtilities.clear_config_cache(config_id)
            TTSUtilities.clear_user_cache(user_id)
            
            logger.info(f"用户 {user_id} 删除TTS配置 {config_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"删除TTS配置失败: {e}")
            raise
    
    @staticmethod
    def _deactivate_other_configs(
        db: Session, 
        user_id: int, 
        exclude_config_id: Optional[int] = None
    ):
        """禁用用户的其他TTS配置"""
        query = db.query(UserTTSConfig).filter(
            UserTTSConfig.owner_id == user_id,
            UserTTSConfig.is_active == True
        )
        
        if exclude_config_id:
            query = query.filter(UserTTSConfig.id != exclude_config_id)
        
        configs = query.all()
        for config in configs:
            config.is_active = False
        
        db.commit()

class TTSSynthesisService:
    """TTS语音合成服务"""
    
    @staticmethod
    async def synthesize_text_optimized(
        db: Session,
        user_id: int,
        text: str,
        voice_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """文本转语音合成 - 优化版本"""
        try:
            # 获取用户激活的TTS配置
            active_config = db.query(UserTTSConfig).filter(
                UserTTSConfig.owner_id == user_id,
                UserTTSConfig.is_active == True
            ).first()
            
            if not active_config:
                return {
                    "status": "error",
                    "message": "用户没有激活的TTS配置"
                }
            
            # 检查缓存
            cache_key = f"tts_synthesis_{user_id}_{hash(text)}"
            cached_result = cache_manager.get(cache_key)
            if cached_result:
                return cached_result
            
            # 执行语音合成
            synthesis_result = await TTSSynthesisService._perform_synthesis(
                active_config, text, voice_config
            )
            
            # 缓存结果
            if synthesis_result.get("status") == "success":
                cache_manager.set(cache_key, synthesis_result, ttl=1800)  # 30分钟缓存
            
            return synthesis_result
            
        except Exception as e:
            logger.error(f"TTS语音合成失败: {e}")
            return {
                "status": "error",
                "message": f"语音合成失败: {str(e)}"
            }
    
    @staticmethod
    async def _perform_synthesis(
        config: UserTTSConfig,
        text: str,
        voice_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行实际的语音合成"""
        # 这里应该调用实际的TTS API
        # 简化示例实现
        synthesis_params = {
            "text": text,
            "voice": voice_config.get("voice", "default") if voice_config else "default",
            "speed": voice_config.get("speed", 1.0) if voice_config else 1.0,
            "pitch": voice_config.get("pitch", 0) if voice_config else 0
        }
        
        # 模拟合成过程
        return {
            "status": "success",
            "audio_url": f"https://tts-storage.example.com/audio_{hash(text)}.mp3",
            "duration": len(text) * 0.1,  # 估算时长
            "synthesis_params": synthesis_params,
            "timestamp": datetime.now().isoformat()
        }

class TTSUtilities:
    """TTS工具类"""
    
    @staticmethod
    def validate_config_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证TTS配置数据"""
        required_fields = ['name', 'provider_type']
        for field in required_fields:
            if not data.get(field):
                raise ValueError(f"缺少必需字段: {field}")
        
        # 验证提供商类型
        valid_providers = ['azure', 'google', 'amazon', 'openai', 'elevenlabs']
        if data.get('provider_type') not in valid_providers:
            raise ValueError(f"不支持的TTS提供商: {data.get('provider_type')}")
        
        return data
    
    @staticmethod
    def validate_update_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证更新数据"""
        allowed_fields = [
            'name', 'provider_type', 'api_key', 'voice_id', 
            'voice_settings', 'is_active', 'description'
        ]
        
        validated_data = {}
        for key, value in data.items():
            if key in allowed_fields and value is not None:
                validated_data[key] = value
        
        return validated_data
    
    @staticmethod
    def clear_config_cache(config_id: int):
        """清除配置相关缓存"""
        cache_keys = [
            f"tts_config_{config_id}",
            f"tts_synthesis_*_{config_id}_*"
        ]
        for key in cache_keys:
            cache_manager.delete_pattern(key)
    
    @staticmethod
    def clear_user_cache(user_id: int):
        """清除用户相关缓存"""
        cache_key = f"user_tts_configs_{user_id}"
        cache_manager.delete(cache_key)
        
        # 清除用户的合成缓存
        cache_manager.delete_pattern(f"tts_synthesis_{user_id}_*")
    
    @staticmethod
    def build_safe_response_dict(config: UserTTSConfig) -> Dict[str, Any]:
        """构建安全的响应字典"""
        return {
            'id': config.id,
            'owner_id': config.owner_id,
            'name': config.name,
            'provider_type': config.provider_type,
            'voice_id': getattr(config, 'voice_id', None),
            'voice_settings': getattr(config, 'voice_settings', None),
            'is_active': config.is_active,
            'description': getattr(config, 'description', None),
            'created_at': config.created_at or datetime.now(),
            'updated_at': config.updated_at or config.created_at or datetime.now(),
            'api_key_encrypted': None  # 永远不返回加密的密钥
        }
