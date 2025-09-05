# project/utils/recommendation/behavior_analyzer.py
"""
用户行为分析工具
从 routers/knowledge/intelligent_recommendation.py 提取的核心算法
"""

import json
import time
import math
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
import logging
import redis
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

class UserAction(str, Enum):
    """用户行为类型"""
    VIEW = "view"
    DOWNLOAD = "download"
    SEARCH = "search"
    BOOKMARK = "bookmark"
    SHARE = "share"
    COMMENT = "comment"
    RATE = "rate"
    EDIT = "edit"
    DELETE = "delete"
    UPLOAD = "upload"
    TAG = "tag"

@dataclass
class UserBehavior:
    """用户行为记录"""
    user_id: int
    action: UserAction
    document_id: int
    kb_id: int
    timestamp: datetime
    session_id: str
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'action': self.action,
            'document_id': self.document_id,
            'kb_id': self.kb_id,
            'timestamp': self.timestamp.isoformat(),
            'session_id': self.session_id,
            'metadata': self.metadata or {}
        }

@dataclass
class UserProfile:
    """用户画像"""
    user_id: int
    interests: Dict[str, float]        # 兴趣标签及权重
    categories: Dict[str, float]       # 内容类别偏好
    activity_level: float              # 活跃度
    preferred_formats: List[str]       # 偏好格式
    interaction_patterns: Dict[str, Any]  # 交互模式
    last_updated: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class BehaviorAnalyzer:
    """用户行为分析器"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.behavior_weights = {
            UserAction.VIEW: 1.0,
            UserAction.DOWNLOAD: 3.0,
            UserAction.SEARCH: 1.5,
            UserAction.BOOKMARK: 4.0,
            UserAction.SHARE: 5.0,
            UserAction.COMMENT: 3.5,
            UserAction.RATE: 4.5,
            UserAction.EDIT: 2.0,
            UserAction.DELETE: -1.0,
            UserAction.UPLOAD: 2.5,
            UserAction.TAG: 2.0
        }
    
    async def record_behavior(self, behavior: UserBehavior):
        """记录用户行为"""
        try:
            # 存储到Redis
            if self.redis_client:
                behavior_key = f"user_behavior:{behavior.user_id}"
                await self.redis_client.lpush(behavior_key, json.dumps(behavior.to_dict()))
                await self.redis_client.ltrim(behavior_key, 0, 999)  # 保留最近1000条记录
            
            # 更新用户画像
            await self._update_user_profile(behavior)
            
        except Exception as e:
            logger.error(f"记录用户行为失败: {e}")
    
    async def get_user_behaviors(self, user_id: int, 
                               time_range: timedelta = None) -> List[UserBehavior]:
        """获取用户行为历史"""
        if not self.redis_client:
            return []
        
        try:
            behavior_key = f"user_behavior:{user_id}"
            raw_behaviors = await self.redis_client.lrange(behavior_key, 0, -1)
            
            behaviors = []
            cutoff_time = datetime.now() - (time_range or timedelta(days=30))
            
            for raw_behavior in raw_behaviors:
                behavior_data = json.loads(raw_behavior)
                behavior_time = datetime.fromisoformat(behavior_data['timestamp'])
                
                if behavior_time >= cutoff_time:
                    behavior = UserBehavior(
                        user_id=behavior_data['user_id'],
                        action=UserAction(behavior_data['action']),
                        document_id=behavior_data['document_id'],
                        kb_id=behavior_data['kb_id'],
                        timestamp=behavior_time,
                        session_id=behavior_data['session_id'],
                        metadata=behavior_data.get('metadata', {})
                    )
                    behaviors.append(behavior)
            
            return behaviors
            
        except Exception as e:
            logger.error(f"获取用户行为失败: {e}")
            return []
    
    async def build_user_profile(self, user_id: int) -> UserProfile:
        """构建用户画像"""
        try:
            behaviors = await self.get_user_behaviors(user_id, timedelta(days=30))
            
            if not behaviors:
                return self._create_empty_profile(user_id)
            
            # 分析兴趣标签
            interests = self._analyze_interests(behaviors)
            
            # 分析内容类别偏好
            categories = self._analyze_categories(behaviors)
            
            # 计算活跃度
            activity_level = self._calculate_activity_level(behaviors)
            
            # 分析偏好格式
            preferred_formats = self._analyze_preferred_formats(behaviors)
            
            # 分析交互模式
            interaction_patterns = self._analyze_interaction_patterns(behaviors)
            
            profile = UserProfile(
                user_id=user_id,
                interests=interests,
                categories=categories,
                activity_level=activity_level,
                preferred_formats=preferred_formats,
                interaction_patterns=interaction_patterns,
                last_updated=datetime.now()
            )
            
            # 缓存用户画像
            if self.redis_client:
                profile_key = f"user_profile:{user_id}"
                await self.redis_client.setex(
                    profile_key, 
                    3600,  # 1小时缓存
                    json.dumps(profile.to_dict())
                )
            
            return profile
            
        except Exception as e:
            logger.error(f"构建用户画像失败: {e}")
            return self._create_empty_profile(user_id)
    
    async def get_user_profile(self, user_id: int) -> UserProfile:
        """获取用户画像（优先从缓存）"""
        try:
            # 先从缓存获取
            if self.redis_client:
                profile_key = f"user_profile:{user_id}"
                cached_profile = await self.redis_client.get(profile_key)
                
                if cached_profile:
                    profile_data = json.loads(cached_profile)
                    profile_data['last_updated'] = datetime.fromisoformat(profile_data['last_updated'])
                    return UserProfile(**profile_data)
            
            # 缓存未命中，重新构建
            return await self.build_user_profile(user_id)
            
        except Exception as e:
            logger.error(f"获取用户画像失败: {e}")
            return self._create_empty_profile(user_id)
    
    def _analyze_interests(self, behaviors: List[UserBehavior]) -> Dict[str, float]:
        """分析用户兴趣标签"""
        interest_scores = defaultdict(float)
        
        for behavior in behaviors:
            weight = self.behavior_weights.get(behavior.action, 1.0)
            
            # 从元数据中提取标签
            tags = behavior.metadata.get('tags', []) if behavior.metadata else []
            for tag in tags:
                interest_scores[tag] += weight
            
            # 时间衰减
            days_ago = (datetime.now() - behavior.timestamp).days
            decay_factor = math.exp(-days_ago / 30.0)  # 30天半衰期
            
            for tag in tags:
                interest_scores[tag] *= decay_factor
        
        # 归一化
        total_score = sum(interest_scores.values())
        if total_score > 0:
            return {tag: score / total_score for tag, score in interest_scores.items()}
        
        return {}
    
    def _analyze_categories(self, behaviors: List[UserBehavior]) -> Dict[str, float]:
        """分析内容类别偏好"""
        category_scores = defaultdict(float)
        
        for behavior in behaviors:
            weight = self.behavior_weights.get(behavior.action, 1.0)
            category = behavior.metadata.get('category', 'unknown') if behavior.metadata else 'unknown'
            category_scores[category] += weight
        
        # 归一化
        total_score = sum(category_scores.values())
        if total_score > 0:
            return {cat: score / total_score for cat, score in category_scores.items()}
        
        return {}
    
    def _calculate_activity_level(self, behaviors: List[UserBehavior]) -> float:
        """计算用户活跃度"""
        if not behaviors:
            return 0.0
        
        # 按天分组计算活跃度
        daily_activities = defaultdict(float)
        
        for behavior in behaviors:
            date_key = behavior.timestamp.date()
            weight = self.behavior_weights.get(behavior.action, 1.0)
            daily_activities[date_key] += weight
        
        # 计算平均活跃度
        total_days = (datetime.now().date() - min(daily_activities.keys())).days + 1
        avg_activity = sum(daily_activities.values()) / total_days
        
        # 归一化到0-1范围
        return min(avg_activity / 10.0, 1.0)
    
    def _analyze_preferred_formats(self, behaviors: List[UserBehavior]) -> List[str]:
        """分析偏好格式"""
        format_counts = defaultdict(int)
        
        for behavior in behaviors:
            if behavior.action in [UserAction.VIEW, UserAction.DOWNLOAD]:
                file_format = behavior.metadata.get('format', 'unknown') if behavior.metadata else 'unknown'
                format_counts[file_format] += 1
        
        # 返回使用频率最高的格式
        sorted_formats = sorted(format_counts.items(), key=lambda x: x[1], reverse=True)
        return [fmt for fmt, count in sorted_formats[:5]]  # 返回前5种格式
    
    def _analyze_interaction_patterns(self, behaviors: List[UserBehavior]) -> Dict[str, Any]:
        """分析交互模式"""
        patterns = {
            'most_active_hours': [],
            'session_duration_avg': 0.0,
            'preferred_actions': [],
            'weekly_pattern': defaultdict(int)
        }
        
        # 分析活跃时间段
        hour_counts = defaultdict(int)
        for behavior in behaviors:
            hour_counts[behavior.timestamp.hour] += 1
        
        sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
        patterns['most_active_hours'] = [hour for hour, count in sorted_hours[:3]]
        
        # 分析行为偏好
        action_counts = defaultdict(int)
        for behavior in behaviors:
            action_counts[behavior.action] += 1
        
        sorted_actions = sorted(action_counts.items(), key=lambda x: x[1], reverse=True)
        patterns['preferred_actions'] = [action for action, count in sorted_actions[:3]]
        
        # 分析周模式
        for behavior in behaviors:
            patterns['weekly_pattern'][behavior.timestamp.weekday()] += 1
        
        return patterns
    
    def _create_empty_profile(self, user_id: int) -> UserProfile:
        """创建空的用户画像"""
        return UserProfile(
            user_id=user_id,
            interests={},
            categories={},
            activity_level=0.0,
            preferred_formats=[],
            interaction_patterns={},
            last_updated=datetime.now()
        )
    
    async def _update_user_profile(self, behavior: UserBehavior):
        """更新用户画像（增量更新）"""
        try:
            # 获取当前画像
            profile = await self.get_user_profile(behavior.user_id)
            
            # 增量更新兴趣标签
            tags = behavior.metadata.get('tags', []) if behavior.metadata else []
            weight = self.behavior_weights.get(behavior.action, 1.0)
            
            for tag in tags:
                profile.interests[tag] = profile.interests.get(tag, 0.0) + weight * 0.1
            
            # 更新类别偏好
            category = behavior.metadata.get('category', 'unknown') if behavior.metadata else 'unknown'
            profile.categories[category] = profile.categories.get(category, 0.0) + weight * 0.1
            
            # 更新时间戳
            profile.last_updated = datetime.now()
            
            # 重新缓存
            if self.redis_client:
                profile_key = f"user_profile:{behavior.user_id}"
                await self.redis_client.setex(
                    profile_key,
                    3600,
                    json.dumps(profile.to_dict())
                )
                
        except Exception as e:
            logger.error(f"更新用户画像失败: {e}")

# 创建全局实例
behavior_analyzer = BehaviorAnalyzer()

# 便捷函数
async def record_user_behavior(behavior: UserBehavior):
    """记录用户行为"""
    return await behavior_analyzer.record_behavior(behavior)

async def get_user_profile(user_id: int) -> UserProfile:
    """获取用户画像"""
    return await behavior_analyzer.get_user_profile(user_id)

async def get_user_behaviors(user_id: int, time_range: timedelta = None) -> List[UserBehavior]:
    """获取用户行为历史"""
    return await behavior_analyzer.get_user_behaviors(user_id, time_range)
