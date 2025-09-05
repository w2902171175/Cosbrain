# project/routers/knowledge/intelligent_recommendation.py
"""
智能推荐模块 - 基于用户行为的智能推荐系统
提供个性化内容推荐、相关文档发现、智能标签建议等功能
"""

import asyncio
import json
import uuid
import time
import math
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
import logging
from collections import defaultdict, Counter
import redis
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import jieba
import jieba.analyse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_

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

class RecommendationType(str, Enum):
    """推荐类型"""
    CONTENT_BASED = "content_based"      # 基于内容
    COLLABORATIVE = "collaborative"      # 协同过滤
    BEHAVIOR_BASED = "behavior_based"   # 基于行为
    HYBRID = "hybrid"                   # 混合推荐
    TRENDING = "trending"               # 热门推荐
    SIMILAR_USERS = "similar_users"     # 相似用户

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

@dataclass
class Recommendation:
    """推荐结果"""
    document_id: int
    score: float
    reason: str
    rec_type: RecommendationType
    metadata: Dict[str, Any] = None

class BehaviorAnalyzer:
    """用户行为分析器"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.behavior_weights = {
            UserAction.VIEW: 1.0,
            UserAction.DOWNLOAD: 3.0,
            UserAction.SEARCH: 0.5,
            UserAction.BOOKMARK: 2.5,
            UserAction.SHARE: 2.0,
            UserAction.COMMENT: 1.5,
            UserAction.RATE: 2.0,
            UserAction.EDIT: 1.0,
            UserAction.DELETE: -1.0,
            UserAction.UPLOAD: 1.0,
            UserAction.TAG: 1.0
        }
        
    async def record_behavior(self, behavior: UserBehavior):
        """记录用户行为"""
        # 保存到Redis
        behavior_key = f"behavior:{behavior.user_id}:{behavior.timestamp.strftime('%Y%m%d')}"
        
        await self.redis_client.lpush(
            behavior_key,
            json.dumps(behavior.to_dict())
        )
        
        # 设置过期时间（保留90天）
        await self.redis_client.expire(behavior_key, 90 * 24 * 3600)
        
        # 更新实时行为统计
        await self._update_realtime_stats(behavior)
        
    async def _update_realtime_stats(self, behavior: UserBehavior):
        """更新实时行为统计"""
        today = datetime.now().strftime('%Y%m%d')
        
        # 用户今日行为计数
        user_stats_key = f"stats:user:{behavior.user_id}:{today}"
        await self.redis_client.hincrby(user_stats_key, behavior.action, 1)
        await self.redis_client.expire(user_stats_key, 24 * 3600)
        
        # 文档今日访问计数
        doc_stats_key = f"stats:doc:{behavior.document_id}:{today}"
        await self.redis_client.hincrby(doc_stats_key, behavior.action, 1)
        await self.redis_client.expire(doc_stats_key, 24 * 3600)
        
        # 全局热门统计
        if behavior.action in [UserAction.VIEW, UserAction.DOWNLOAD]:
            await self.redis_client.zincrby(
                f"trending:{today}",
                self.behavior_weights[behavior.action],
                behavior.document_id
            )
            await self.redis_client.expire(f"trending:{today}", 24 * 3600)
            
    async def get_user_behaviors(self, user_id: int, days: int = 30) -> List[UserBehavior]:
        """获取用户行为历史"""
        behaviors = []
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
            behavior_key = f"behavior:{user_id}:{date}"
            
            behavior_data = await self.redis_client.lrange(behavior_key, 0, -1)
            
            for data in behavior_data:
                try:
                    behavior_dict = json.loads(data)
                    behavior_dict['timestamp'] = datetime.fromisoformat(behavior_dict['timestamp'])
                    behaviors.append(UserBehavior(**behavior_dict))
                except Exception as e:
                    logger.error(f"解析行为数据失败: {e}")
                    
        return sorted(behaviors, key=lambda x: x.timestamp, reverse=True)
        
    async def analyze_user_interests(self, user_id: int, db: Session) -> Dict[str, float]:
        """分析用户兴趣"""
        behaviors = await self.get_user_behaviors(user_id)
        
        if not behaviors:
            return {}
            
        # 获取用户访问的文档信息
        doc_ids = list(set(b.document_id for b in behaviors))
        
        # 这里需要从数据库获取文档信息，包括标签、类别等
        # 简化示例
        interest_scores = defaultdict(float)
        
        for behavior in behaviors:
            weight = self.behavior_weights.get(behavior.action, 1.0)
            
            # 根据时间衰减
            days_ago = (datetime.now() - behavior.timestamp).days
            time_decay = math.exp(-days_ago / 30.0)  # 30天衰减因子
            
            score = weight * time_decay
            
            # 这里应该基于文档的实际标签和类别来更新兴趣分数
            # 简化示例：基于文档ID推断类别
            category = f"category_{behavior.document_id % 10}"
            interest_scores[category] += score
            
        # 归一化分数
        if interest_scores:
            max_score = max(interest_scores.values())
            interest_scores = {k: v / max_score for k, v in interest_scores.items()}
            
        return dict(interest_scores)

class ContentAnalyzer:
    """内容分析器"""
    
    def __init__(self):
        self.tfidf_vectorizer = None
        self.doc_vectors = None
        self.doc_ids = []
        
    async def analyze_document_content(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析文档内容"""
        if not documents:
            return {}
            
        # 提取文档文本
        texts = []
        doc_ids = []
        
        for doc in documents:
            text = doc.get('content', '') or doc.get('title', '')
            if text:
                # 中文分词
                words = jieba.cut(text)
                processed_text = ' '.join(words)
                texts.append(processed_text)
                doc_ids.append(doc['id'])
                
        if not texts:
            return {}
            
        # TF-IDF向量化
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words=['的', '是', '在', '有', '和', '就', '不', '了', '也', '我'],
            ngram_range=(1, 2)
        )
        
        self.doc_vectors = self.tfidf_vectorizer.fit_transform(texts)
        self.doc_ids = doc_ids
        
        # 提取关键词
        keywords = {}
        for i, text in enumerate(texts):
            doc_keywords = jieba.analyse.extract_tags(text, topK=10, withWeight=True)
            keywords[doc_ids[i]] = dict(doc_keywords)
            
        # 文档聚类
        if len(texts) > 5:
            clusters = self._cluster_documents(self.doc_vectors)
            cluster_info = dict(zip(doc_ids, clusters))
        else:
            cluster_info = {}
            
        return {
            'keywords': keywords,
            'clusters': cluster_info,
            'vectorizer_vocabulary': len(self.tfidf_vectorizer.vocabulary_) if self.tfidf_vectorizer else 0
        }
        
    def _cluster_documents(self, vectors, n_clusters: int = None) -> List[int]:
        """文档聚类"""
        if n_clusters is None:
            n_clusters = min(5, max(2, vectors.shape[0] // 10))
            
        try:
            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            clusters = kmeans.fit_predict(vectors.toarray())
            return clusters.tolist()
        except Exception as e:
            logger.error(f"文档聚类失败: {e}")
            return [0] * vectors.shape[0]
            
    def calculate_content_similarity(self, doc_id1: int, doc_id2: int) -> float:
        """计算文档内容相似度"""
        if not self.doc_vectors or not self.doc_ids:
            return 0.0
            
        try:
            idx1 = self.doc_ids.index(doc_id1)
            idx2 = self.doc_ids.index(doc_id2)
            
            vec1 = self.doc_vectors[idx1]
            vec2 = self.doc_vectors[idx2]
            
            similarity = cosine_similarity(vec1, vec2)[0][0]
            return float(similarity)
            
        except (ValueError, IndexError):
            return 0.0
            
    def find_similar_documents(self, doc_id: int, top_k: int = 5) -> List[Tuple[int, float]]:
        """查找相似文档"""
        if not self.doc_vectors or not self.doc_ids:
            return []
            
        try:
            idx = self.doc_ids.index(doc_id)
            target_vector = self.doc_vectors[idx]
            
            similarities = cosine_similarity(target_vector, self.doc_vectors)[0]
            
            # 排除自身
            similarities[idx] = -1
            
            # 获取最相似的文档
            similar_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for i in similar_indices:
                if similarities[i] > 0:
                    results.append((self.doc_ids[i], float(similarities[i])))
                    
            return results
            
        except (ValueError, IndexError):
            return []

class RecommendationEngine:
    """推荐引擎"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.behavior_analyzer = BehaviorAnalyzer(redis_client)
        self.content_analyzer = ContentAnalyzer()
        
    async def generate_recommendations(self, user_id: int, kb_id: int, db: Session,
                                     limit: int = 10) -> List[Recommendation]:
        """生成推荐"""
        recommendations = []
        
        # 1. 基于内容的推荐
        content_recs = await self._content_based_recommendations(user_id, kb_id, db, limit // 2)
        recommendations.extend(content_recs)
        
        # 2. 基于行为的推荐
        behavior_recs = await self._behavior_based_recommendations(user_id, kb_id, db, limit // 4)
        recommendations.extend(behavior_recs)
        
        # 3. 热门推荐
        trending_recs = await self._trending_recommendations(kb_id, db, limit // 4)
        recommendations.extend(trending_recs)
        
        # 4. 去重和排序
        unique_recs = {}
        for rec in recommendations:
            if rec.document_id not in unique_recs:
                unique_recs[rec.document_id] = rec
            elif rec.score > unique_recs[rec.document_id].score:
                unique_recs[rec.document_id] = rec
                
        # 按分数排序
        final_recs = sorted(unique_recs.values(), key=lambda x: x.score, reverse=True)
        
        return final_recs[:limit]
        
    async def _content_based_recommendations(self, user_id: int, kb_id: int, 
                                           db: Session, limit: int) -> List[Recommendation]:
        """基于内容的推荐"""
        recommendations = []
        
        try:
            # 获取用户最近浏览的文档
            recent_behaviors = await self.behavior_analyzer.get_user_behaviors(user_id, days=7)
            recent_docs = [b.document_id for b in recent_behaviors if b.action in [UserAction.VIEW, UserAction.DOWNLOAD]]
            
            if not recent_docs:
                return recommendations
                
            # 获取所有文档信息（这里需要实际的数据库查询）
            # 简化示例
            all_documents = []  # 这里应该从数据库获取kb_id下的所有文档
            
            if not all_documents:
                return recommendations
                
            # 分析文档内容
            await self.content_analyzer.analyze_document_content(all_documents)
            
            # 为每个最近浏览的文档找相似文档
            similar_docs = set()
            for doc_id in recent_docs[-5:]:  # 只考虑最近5个文档
                similar = self.content_analyzer.find_similar_documents(doc_id, 3)
                for sim_doc_id, similarity in similar:
                    if sim_doc_id not in recent_docs:  # 排除已浏览的
                        similar_docs.add((sim_doc_id, similarity))
                        
            # 转换为推荐结果
            for doc_id, similarity in list(similar_docs)[:limit]:
                rec = Recommendation(
                    document_id=doc_id,
                    score=similarity,
                    reason=f"与您浏览过的文档相似（相似度: {similarity:.2f}）",
                    rec_type=RecommendationType.CONTENT_BASED,
                    metadata={'similarity': similarity}
                )
                recommendations.append(rec)
                
        except Exception as e:
            logger.error(f"基于内容的推荐失败: {e}")
            
        return recommendations
        
    async def _behavior_based_recommendations(self, user_id: int, kb_id: int,
                                            db: Session, limit: int) -> List[Recommendation]:
        """基于行为的推荐"""
        recommendations = []
        
        try:
            # 分析用户兴趣
            interests = await self.behavior_analyzer.analyze_user_interests(user_id, db)
            
            if not interests:
                return recommendations
                
            # 基于兴趣推荐文档（这里需要实际的数据库查询逻辑）
            # 简化示例
            for category, score in sorted(interests.items(), key=lambda x: x[1], reverse=True)[:3]:
                # 这里应该查询该类别下的热门文档
                # 简化示例：假设有一些文档ID
                doc_ids = [100 + i for i in range(limit // 3)]  # 示例文档ID
                
                for doc_id in doc_ids:
                    rec = Recommendation(
                        document_id=doc_id,
                        score=score * 0.8,  # 行为推荐权重
                        reason=f"基于您的兴趣偏好: {category}",
                        rec_type=RecommendationType.BEHAVIOR_BASED,
                        metadata={'category': category, 'interest_score': score}
                    )
                    recommendations.append(rec)
                    
        except Exception as e:
            logger.error(f"基于行为的推荐失败: {e}")
            
        return recommendations
        
    async def _trending_recommendations(self, kb_id: int, db: Session, limit: int) -> List[Recommendation]:
        """热门推荐"""
        recommendations = []
        
        try:
            # 获取今日热门文档
            today = datetime.now().strftime('%Y%m%d')
            trending_docs = await self.redis_client.zrevrange(f"trending:{today}", 0, limit - 1, withscores=True)
            
            for doc_id, score in trending_docs:
                rec = Recommendation(
                    document_id=int(doc_id),
                    score=float(score) * 0.6,  # 热门推荐权重
                    reason=f"今日热门文档（热度: {score:.1f}）",
                    rec_type=RecommendationType.TRENDING,
                    metadata={'trending_score': float(score)}
                )
                recommendations.append(rec)
                
        except Exception as e:
            logger.error(f"热门推荐失败: {e}")
            
        return recommendations
        
    async def get_user_profile(self, user_id: int, db: Session) -> UserProfile:
        """获取用户画像"""
        try:
            # 分析用户兴趣
            interests = await self.behavior_analyzer.analyze_user_interests(user_id, db)
            
            # 分析用户行为模式
            behaviors = await self.behavior_analyzer.get_user_behaviors(user_id, 30)
            
            # 计算活跃度
            activity_level = len(behaviors) / 30.0  # 平均每天行为数
            
            # 分析偏好格式
            format_counter = Counter()
            for behavior in behaviors:
                # 这里需要根据document_id获取文档格式
                # 简化示例
                format_counter['pdf'] += 1
                
            preferred_formats = [fmt for fmt, _ in format_counter.most_common(3)]
            
            # 分析交互模式
            action_counter = Counter(b.action for b in behaviors)
            interaction_patterns = {
                'total_actions': len(behaviors),
                'action_distribution': dict(action_counter),
                'avg_daily_actions': activity_level,
                'most_active_hour': self._analyze_active_hours(behaviors),
                'session_duration': self._analyze_session_duration(behaviors)
            }
            
            # 分析内容类别偏好
            categories = {}
            for behavior in behaviors:
                # 这里需要根据document_id获取文档类别
                # 简化示例
                category = f"category_{behavior.document_id % 5}"
                categories[category] = categories.get(category, 0) + 1
                
            # 归一化类别权重
            if categories:
                max_count = max(categories.values())
                categories = {k: v / max_count for k, v in categories.items()}
                
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
            await self.redis_client.setex(
                f"profile:{user_id}",
                24 * 3600,  # 24小时过期
                json.dumps(profile.to_dict(), default=str)
            )
            
            return profile
            
        except Exception as e:
            logger.error(f"获取用户画像失败: {e}")
            return UserProfile(
                user_id=user_id,
                interests={},
                categories={},
                activity_level=0.0,
                preferred_formats=[],
                interaction_patterns={},
                last_updated=datetime.now()
            )
            
    def _analyze_active_hours(self, behaviors: List[UserBehavior]) -> int:
        """分析最活跃时间"""
        if not behaviors:
            return 0
            
        hour_counter = Counter(b.timestamp.hour for b in behaviors)
        return hour_counter.most_common(1)[0][0] if hour_counter else 0
        
    def _analyze_session_duration(self, behaviors: List[UserBehavior]) -> float:
        """分析平均会话时长"""
        if not behaviors:
            return 0.0
            
        sessions = defaultdict(list)
        for behavior in behaviors:
            sessions[behavior.session_id].append(behavior.timestamp)
            
        durations = []
        for session_times in sessions.values():
            if len(session_times) > 1:
                session_times.sort()
                duration = (session_times[-1] - session_times[0]).total_seconds() / 60.0  # 分钟
                durations.append(duration)
                
        return sum(durations) / len(durations) if durations else 0.0

class SmartTagSuggester:
    """智能标签建议器"""
    
    def __init__(self):
        self.tag_frequency = defaultdict(int)
        self.tag_cooccurrence = defaultdict(lambda: defaultdict(int))
        
    async def analyze_document_for_tags(self, content: str, existing_tags: List[str] = None) -> List[Dict[str, Any]]:
        """分析文档内容建议标签"""
        suggestions = []
        
        try:
            # 1. 关键词提取
            keywords = jieba.analyse.extract_tags(content, topK=20, withWeight=True)
            
            for keyword, weight in keywords:
                if len(keyword) > 1:  # 过滤单字词
                    suggestions.append({
                        'tag': keyword,
                        'confidence': weight,
                        'reason': '关键词提取',
                        'type': 'keyword'
                    })
                    
            # 2. 基于现有标签的相关标签建议
            if existing_tags:
                related_tags = await self._suggest_related_tags(existing_tags)
                for tag, score in related_tags:
                    suggestions.append({
                        'tag': tag,
                        'confidence': score,
                        'reason': f'与标签 "{", ".join(existing_tags)}" 相关',
                        'type': 'related'
                    })
                    
            # 3. 实体识别（简化版本）
            entities = self._extract_entities(content)
            for entity, entity_type in entities:
                suggestions.append({
                    'tag': entity,
                    'confidence': 0.7,
                    'reason': f'{entity_type}实体',
                    'type': 'entity'
                })
                
            # 4. 去重和排序
            unique_suggestions = {}
            for suggestion in suggestions:
                tag = suggestion['tag']
                if tag not in unique_suggestions or suggestion['confidence'] > unique_suggestions[tag]['confidence']:
                    unique_suggestions[tag] = suggestion
                    
            # 按置信度排序
            final_suggestions = sorted(unique_suggestions.values(), 
                                     key=lambda x: x['confidence'], reverse=True)
            
            return final_suggestions[:10]  # 返回前10个建议
            
        except Exception as e:
            logger.error(f"标签建议失败: {e}")
            return []
            
    def _extract_entities(self, text: str) -> List[Tuple[str, str]]:
        """提取实体（简化版本）"""
        entities = []
        
        # 简单的正则表达式匹配
        patterns = {
            '时间': r'\d{4}年|\d{1,2}月|\d{1,2}日',
            '数字': r'\d+(?:\.\d+)?%|\d+(?:\.\d+)?万|\d+(?:\.\d+)?亿',
            '组织': r'公司|企业|机构|部门|学校|大学',
            '地点': r'北京|上海|广州|深圳|杭州|南京|武汉|成都|重庆|西安'
        }
        
        for entity_type, pattern in patterns.items():
            matches = re.findall(pattern, text)
            for match in matches:
                entities.append((match, entity_type))
                
        return entities
        
    async def _suggest_related_tags(self, existing_tags: List[str]) -> List[Tuple[str, float]]:
        """基于共现关系建议相关标签"""
        related_tags = defaultdict(float)
        
        for tag in existing_tags:
            # 这里应该从历史数据中获取标签共现关系
            # 简化示例
            if tag in ['技术', '开发']:
                related_tags['编程'] += 0.8
                related_tags['软件'] += 0.7
            elif tag in ['管理', '项目']:
                related_tags['团队'] += 0.8
                related_tags['计划'] += 0.6
                
        return list(related_tags.items())
        
    async def update_tag_statistics(self, document_tags: List[str]):
        """更新标签统计信息"""
        # 更新标签频率
        for tag in document_tags:
            self.tag_frequency[tag] += 1
            
        # 更新标签共现关系
        for i, tag1 in enumerate(document_tags):
            for tag2 in document_tags[i+1:]:
                self.tag_cooccurrence[tag1][tag2] += 1
                self.tag_cooccurrence[tag2][tag1] += 1

class PersonalizedSearch:
    """个性化搜索"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        
    async def personalized_search(self, user_id: int, query: str, kb_id: int,
                                db: Session, limit: int = 20) -> List[Dict[str, Any]]:
        """个性化搜索"""
        try:
            # 1. 获取用户画像
            profile_data = await self.redis_client.get(f"profile:{user_id}")
            if profile_data:
                profile = json.loads(profile_data)
                user_interests = profile.get('interests', {})
            else:
                user_interests = {}
                
            # 2. 查询扩展
            expanded_query = await self._expand_query(query, user_interests)
            
            # 3. 执行基础搜索（这里需要调用实际的搜索函数）
            # 简化示例
            base_results = []  # 这里应该是实际的搜索结果
            
            # 4. 个性化重排序
            personalized_results = await self._rerank_results(
                base_results, user_interests, user_id
            )
            
            # 5. 记录搜索行为
            await self._record_search_behavior(user_id, query, kb_id)
            
            return personalized_results[:limit]
            
        except Exception as e:
            logger.error(f"个性化搜索失败: {e}")
            return []
            
    async def _expand_query(self, query: str, user_interests: Dict[str, float]) -> str:
        """查询扩展"""
        expanded_terms = [query]
        
        # 基于用户兴趣添加相关词汇
        query_words = set(jieba.cut(query))
        
        for interest, weight in user_interests.items():
            if weight > 0.5:  # 只考虑高权重兴趣
                # 这里可以添加同义词词典或词向量模型来扩展查询
                expanded_terms.append(interest)
                
        return ' '.join(expanded_terms)
        
    async def _rerank_results(self, results: List[Dict[str, Any]], 
                            user_interests: Dict[str, float], user_id: int) -> List[Dict[str, Any]]:
        """个性化重排序"""
        if not results or not user_interests:
            return results
            
        # 为每个结果计算个性化分数
        for result in results:
            base_score = result.get('score', 0.0)
            
            # 基于用户兴趣调整分数
            interest_boost = 0.0
            doc_categories = result.get('categories', [])
            
            for category in doc_categories:
                if category in user_interests:
                    interest_boost += user_interests[category] * 0.3
                    
            # 基于用户历史行为调整分数
            behavior_boost = await self._calculate_behavior_boost(user_id, result['id'])
            
            # 计算最终分数
            result['personalized_score'] = base_score + interest_boost + behavior_boost
            
        # 按个性化分数重新排序
        return sorted(results, key=lambda x: x.get('personalized_score', 0), reverse=True)
        
    async def _calculate_behavior_boost(self, user_id: int, doc_id: int) -> float:
        """计算基于历史行为的分数提升"""
        boost = 0.0
        
        try:
            # 检查用户是否浏览过相似文档
            behavior_key = f"user_docs:{user_id}"
            viewed_docs = await self.redis_client.smembers(behavior_key)
            
            if str(doc_id) in viewed_docs:
                boost -= 0.2  # 已浏览过的文档降权
            else:
                # 检查是否浏览过相似类型的文档
                # 这里需要更复杂的相似度计算
                boost += 0.1  # 新文档轻微加权
                
        except Exception as e:
            logger.error(f"计算行为加权失败: {e}")
            
        return boost
        
    async def _record_search_behavior(self, user_id: int, query: str, kb_id: int):
        """记录搜索行为"""
        search_log = {
            'user_id': user_id,
            'query': query,
            'kb_id': kb_id,
            'timestamp': datetime.now().isoformat()
        }
        
        # 保存到搜索历史
        await self.redis_client.lpush(
            f"search_history:{user_id}",
            json.dumps(search_log)
        )
        
        # 限制搜索历史长度
        await self.redis_client.ltrim(f"search_history:{user_id}", 0, 99)

# 全局推荐引擎实例
recommendation_engine = None
tag_suggester = None
personalized_search = None

def init_recommendation_system(redis_client) -> Tuple[RecommendationEngine, SmartTagSuggester, PersonalizedSearch]:
    """初始化推荐系统"""
    global recommendation_engine, tag_suggester, personalized_search
    
    recommendation_engine = RecommendationEngine(redis_client)
    tag_suggester = SmartTagSuggester()
    personalized_search = PersonalizedSearch(redis_client)
    
    logger.info("🎯 Recommendation - 智能推荐系统已初始化")
    return recommendation_engine, tag_suggester, personalized_search

def get_recommendation_engine() -> Optional[RecommendationEngine]:
    """获取推荐引擎实例"""
    return recommendation_engine

def get_tag_suggester() -> Optional[SmartTagSuggester]:
    """获取标签建议器实例"""
    return tag_suggester

def get_personalized_search() -> Optional[PersonalizedSearch]:
    """获取个性化搜索实例"""
    return personalized_search
