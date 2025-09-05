# project/utils/cache.py
import redis
import json
import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ChatRoomCache:
    def __init__(self, redis_url=None):
        try:
            # 优先使用传入的redis_url，否则从环境变量获取
            redis_url = redis_url or os.getenv("REDIS_URL")
            
            # 检查是否启用Redis和是否有Redis URL配置
            enable_redis = os.getenv("ENABLE_REDIS", "true").lower() == "true"
            if not enable_redis or not redis_url:
                if not enable_redis:
                    logger.info("Redis缓存已禁用，缓存功能将被禁用")
                else:
                    logger.warning("未配置REDIS_URL环境变量，缓存功能将被禁用")
                self.redis_client = None
                self.is_available = False
                return
            
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # 测试连接
            self.redis_client.ping()
            self.is_available = True
            logger.info(f"Redis缓存连接成功: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")
        except Exception as e:
            logger.warning(f"Redis连接失败，缓存功能将被禁用: {e}")
            self.redis_client = None
            self.is_available = False
    
    async def get_room_members_count(self, room_id: int) -> Optional[int]:
        """获取缓存的房间成员数量"""
        if not self.is_available:
            return None
            
        try:
            key = f"room:{room_id}:members_count"
            count = self.redis_client.get(key)
            return int(count) if count else None
        except Exception as e:
            logger.error(f"获取房间成员数量缓存失败: {e}")
            return None
    
    async def set_room_members_count(self, room_id: int, count: int, expire: int = 300):
        """设置房间成员数量缓存"""
        if not self.is_available:
            return
            
        try:
            key = f"room:{room_id}:members_count"
            self.redis_client.setex(key, expire, count)
        except Exception as e:
            logger.error(f"设置房间成员数量缓存失败: {e}")
    
    async def get_room_info(self, room_id: int) -> Optional[Dict]:
        """获取缓存的房间信息"""
        if not self.is_available:
            return None
            
        try:
            key = f"room:{room_id}:info"
            data = self.redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"获取房间信息缓存失败: {e}")
            return None
    
    async def set_room_info(self, room_id: int, room_info: Dict, expire: int = 600):
        """设置房间信息缓存"""
        if not self.is_available:
            return
            
        try:
            key = f"room:{room_id}:info"
            # 确保datetime对象可以序列化
            serializable_info = self._make_serializable(room_info)
            self.redis_client.setex(key, expire, json.dumps(serializable_info))
        except Exception as e:
            logger.error(f"设置房间信息缓存失败: {e}")
    
    async def get_user_rooms(self, user_id: int) -> Optional[List[int]]:
        """获取用户房间列表缓存"""
        if not self.is_available:
            return None
            
        try:
            key = f"user:{user_id}:rooms"
            data = self.redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"获取用户房间列表缓存失败: {e}")
            return None
    
    async def set_user_rooms(self, user_id: int, room_ids: List[int], expire: int = 300):
        """设置用户房间列表缓存"""
        if not self.is_available:
            return
            
        try:
            key = f"user:{user_id}:rooms"
            self.redis_client.setex(key, expire, json.dumps(room_ids))
        except Exception as e:
            logger.error(f"设置用户房间列表缓存失败: {e}")
    
    async def invalidate_room_cache(self, room_id: int):
        """清除房间相关缓存"""
        if not self.is_available:
            return
            
        try:
            keys_to_delete = [
                f"room:{room_id}:info",
                f"room:{room_id}:members_count",
                f"room:{room_id}:messages_count",
                f"room:{room_id}:latest_message"
            ]
            
            for key in keys_to_delete:
                self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"清除房间缓存失败: {e}")
    
    async def invalidate_user_cache(self, user_id: int):
        """清除用户相关缓存"""
        if not self.is_available:
            return
            
        try:
            keys_to_delete = [
                f"user:{user_id}:rooms",
                f"user:{user_id}:profile"
            ]
            
            for key in keys_to_delete:
                self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"清除用户缓存失败: {e}")
    
    async def get_recent_messages(self, room_id: int, limit: int = 50) -> Optional[List[Dict]]:
        """获取最近消息缓存"""
        if not self.is_available:
            return None
            
        try:
            key = f"room:{room_id}:recent_messages"
            messages = self.redis_client.lrange(key, 0, limit - 1)
            return [json.loads(msg) for msg in messages] if messages else None
        except Exception as e:
            logger.error(f"获取最近消息缓存失败: {e}")
            return None
    
    async def add_recent_message(self, room_id: int, message: Dict, max_messages: int = 100):
        """添加最近消息到缓存"""
        if not self.is_available:
            return
            
        try:
            key = f"room:{room_id}:recent_messages"
            # 确保消息可以序列化
            serializable_message = self._make_serializable(message)
            
            # 添加到列表头部
            self.redis_client.lpush(key, json.dumps(serializable_message))
            
            # 限制列表长度
            self.redis_client.ltrim(key, 0, max_messages - 1)
            
            # 设置过期时间
            self.redis_client.expire(key, 3600)  # 1小时
        except Exception as e:
            logger.error(f"添加最近消息缓存失败: {e}")
    
    async def get_online_users(self, room_id: int) -> Optional[List[int]]:
        """获取在线用户列表"""
        if not self.is_available:
            return None
            
        try:
            key = f"room:{room_id}:online_users"
            user_ids = self.redis_client.smembers(key)
            return [int(uid) for uid in user_ids] if user_ids else None
        except Exception as e:
            logger.error(f"获取在线用户列表失败: {e}")
            return None
    
    async def add_online_user(self, room_id: int, user_id: int):
        """添加在线用户"""
        if not self.is_available:
            return
            
        try:
            key = f"room:{room_id}:online_users"
            self.redis_client.sadd(key, user_id)
            self.redis_client.expire(key, 1800)  # 30分钟
        except Exception as e:
            logger.error(f"添加在线用户失败: {e}")
    
    async def remove_online_user(self, room_id: int, user_id: int):
        """移除在线用户"""
        if not self.is_available:
            return
            
        try:
            key = f"room:{room_id}:online_users"
            self.redis_client.srem(key, user_id)
        except Exception as e:
            logger.error(f"移除在线用户失败: {e}")
    
    def _make_serializable(self, obj: Any) -> Any:
        """将对象转换为可序列化的格式"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            # 对于模型对象，提取其属性
            result = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):
                    result[key] = self._make_serializable(value)
            return result
        else:
            return obj

# 创建全局缓存实例
cache = ChatRoomCache()
