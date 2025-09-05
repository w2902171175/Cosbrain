# project/utils/recommendation/tag_extractor.py
"""
标签提取和关键词分析工具
提供智能标签建议和关键词提取功能
"""

import re
import math
from typing import Dict, List, Optional, Any, Tuple
import logging
import jieba
import jieba.analyse
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

class TagExtractor:
    """标签提取器"""
    
    def __init__(self):
        # 预定义的类别标签
        self.category_keywords = {
            '技术': ['技术', '编程', '开发', '代码', '算法', '系统', '软件', '硬件', '网络'],
            '教育': ['教育', '学习', '课程', '教学', '培训', '知识', '技能', '学校'],
            '商业': ['商业', '营销', '管理', '经济', '金融', '投资', '创业', '市场'],
            '科学': ['科学', '研究', '实验', '理论', '数据', '分析', '方法', '发现'],
            '艺术': ['艺术', '设计', '创意', '美术', '音乐', '文学', '创作', '审美'],
            '健康': ['健康', '医疗', '治疗', '保健', '运动', '营养', '心理', '康复'],
            '生活': ['生活', '日常', '家庭', '社交', '娱乐', '旅游', '美食', '时尚']
        }
        
        # 技术相关的子类别
        self.tech_subcategories = {
            'python': ['python', 'django', 'flask', 'pandas', 'numpy'],
            'javascript': ['javascript', 'js', 'node', 'react', 'vue', 'angular'],
            'java': ['java', 'spring', 'maven', 'gradle', 'android'],
            'web': ['html', 'css', 'http', 'api', 'rest', 'graphql'],
            'database': ['mysql', 'postgresql', 'mongodb', 'redis', 'sql'],
            'ai': ['ai', '人工智能', '机器学习', '深度学习', 'tensorflow', 'pytorch'],
            'cloud': ['cloud', '云计算', 'aws', 'azure', 'docker', 'kubernetes']
        }
    
    def extract_tags(self, content: str, max_tags: int = 10, 
                    min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """提取标签"""
        try:
            tags = []
            
            # 1. 基于TF-IDF的关键词提取
            tfidf_tags = self._extract_tfidf_tags(content, max_tags)
            
            # 2. 基于类别匹配的标签
            category_tags = self._extract_category_tags(content)
            
            # 3. 基于技术关键词的标签
            tech_tags = self._extract_tech_tags(content)
            
            # 4. 基于实体识别的标签
            entity_tags = self._extract_entity_tags(content)
            
            # 合并和排序标签
            all_tags = {}
            
            # 添加TF-IDF标签
            for tag, weight in tfidf_tags:
                all_tags[tag] = all_tags.get(tag, 0) + weight * 0.4
            
            # 添加类别标签
            for tag, confidence in category_tags:
                all_tags[tag] = all_tags.get(tag, 0) + confidence * 0.3
            
            # 添加技术标签
            for tag, confidence in tech_tags:
                all_tags[tag] = all_tags.get(tag, 0) + confidence * 0.2
            
            # 添加实体标签
            for tag, confidence in entity_tags:
                all_tags[tag] = all_tags.get(tag, 0) + confidence * 0.1
            
            # 过滤和排序
            filtered_tags = [
                {
                    'tag': tag,
                    'confidence': confidence,
                    'type': self._get_tag_type(tag)
                }
                for tag, confidence in all_tags.items()
                if confidence >= min_confidence
            ]
            
            # 按置信度排序
            filtered_tags.sort(key=lambda x: x['confidence'], reverse=True)
            
            return filtered_tags[:max_tags]
            
        except Exception as e:
            logger.error(f"标签提取失败: {e}")
            return []
    
    def suggest_tags_for_document(self, title: str, content: str, 
                                 existing_tags: List[str] = None) -> List[str]:
        """为文档建议标签"""
        try:
            existing_tags = existing_tags or []
            
            # 合并标题和内容
            full_text = f"{title} {content}"
            
            # 提取标签
            extracted_tags = self.extract_tags(full_text, max_tags=15, min_confidence=0.3)
            
            # 过滤已存在的标签
            suggested_tags = []
            for tag_info in extracted_tags:
                tag = tag_info['tag']
                if tag not in existing_tags and tag not in suggested_tags:
                    suggested_tags.append(tag)
            
            return suggested_tags[:10]  # 返回前10个建议
            
        except Exception as e:
            logger.error(f"标签建议失败: {e}")
            return []
    
    def _extract_tfidf_tags(self, content: str, max_tags: int) -> List[Tuple[str, float]]:
        """使用TF-IDF提取关键词"""
        try:
            # 使用jieba的TF-IDF
            keywords = jieba.analyse.extract_tags(
                content, 
                topK=max_tags * 2, 
                withWeight=True
            )
            
            # 过滤短词和无意义的词
            filtered_keywords = []
            for word, weight in keywords:
                if len(word) >= 2 and self._is_meaningful_word(word):
                    filtered_keywords.append((word, weight))
            
            return filtered_keywords[:max_tags]
            
        except Exception as e:
            logger.error(f"TF-IDF提取失败: {e}")
            return []
    
    def _extract_category_tags(self, content: str) -> List[Tuple[str, float]]:
        """提取类别标签"""
        category_scores = defaultdict(float)
        
        content_lower = content.lower()
        
        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                count = content_lower.count(keyword)
                if count > 0:
                    category_scores[category] += count * 0.1
        
        # 归一化评分
        max_score = max(category_scores.values()) if category_scores else 1
        
        return [
            (category, score / max_score)
            for category, score in category_scores.items()
            if score > 0
        ]
    
    def _extract_tech_tags(self, content: str) -> List[Tuple[str, float]]:
        """提取技术相关标签"""
        tech_scores = defaultdict(float)
        
        content_lower = content.lower()
        
        for category, keywords in self.tech_subcategories.items():
            for keyword in keywords:
                count = content_lower.count(keyword)
                if count > 0:
                    tech_scores[keyword] += count * 0.15
                    tech_scores[category] += count * 0.1
        
        # 归一化评分
        max_score = max(tech_scores.values()) if tech_scores else 1
        
        return [
            (tech, score / max_score)
            for tech, score in tech_scores.items()
            if score > 0
        ]
    
    def _extract_entity_tags(self, content: str) -> List[Tuple[str, float]]:
        """提取实体标签（简化版本）"""
        entities = []
        
        # 提取可能的产品名、公司名等
        # 大写字母开头的词组
        patterns = [
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',  # 专有名词
            r'\b[A-Z]{2,}\b',  # 缩写
            r'\b\d+\.\d+\b',   # 版本号
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if len(match) >= 3 and self._is_meaningful_entity(match):
                    entities.append((match.lower(), 0.5))
        
        return entities
    
    def _is_meaningful_word(self, word: str) -> bool:
        """判断词汇是否有意义"""
        # 过滤停用词和无意义的词
        stop_words = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
            '这', '那', '这个', '那个', '什么', '如何', '怎么', '为什么'
        }
        
        return (
            word not in stop_words and
            not word.isdigit() and
            len(word) >= 2 and
            not re.match(r'^[^\w\s]+$', word)
        )
    
    def _is_meaningful_entity(self, entity: str) -> bool:
        """判断实体是否有意义"""
        # 过滤一些常见的无意义实体
        meaningless_entities = {
            'THAT', 'THIS', 'WHAT', 'WHERE', 'WHEN', 'HOW', 'WHY',
            'THE', 'AND', 'OR', 'BUT', 'IF', 'THEN'
        }
        
        return entity.upper() not in meaningless_entities
    
    def _get_tag_type(self, tag: str) -> str:
        """获取标签类型"""
        if tag in self.category_keywords:
            return 'category'
        
        for category, keywords in self.tech_subcategories.items():
            if tag in keywords:
                return 'technology'
        
        if tag in [kw for kws in self.category_keywords.values() for kw in kws]:
            return 'keyword'
        
        return 'general'

class KeywordExtractor:
    """关键词提取器"""
    
    @staticmethod
    def extract_keywords(text: str, num_keywords: int = 10) -> List[Dict[str, Any]]:
        """提取关键词"""
        try:
            # 使用jieba的TextRank算法
            textrank_keywords = jieba.analyse.textrank(
                text, 
                topK=num_keywords, 
                withWeight=True
            )
            
            # 使用TF-IDF算法
            tfidf_keywords = jieba.analyse.extract_tags(
                text, 
                topK=num_keywords, 
                withWeight=True
            )
            
            # 合并结果
            combined_keywords = {}
            
            for keyword, weight in textrank_keywords:
                combined_keywords[keyword] = {
                    'textrank_weight': weight,
                    'tfidf_weight': 0
                }
            
            for keyword, weight in tfidf_keywords:
                if keyword in combined_keywords:
                    combined_keywords[keyword]['tfidf_weight'] = weight
                else:
                    combined_keywords[keyword] = {
                        'textrank_weight': 0,
                        'tfidf_weight': weight
                    }
            
            # 计算综合权重
            keywords = []
            for keyword, weights in combined_keywords.items():
                combined_weight = (
                    weights['textrank_weight'] * 0.6 + 
                    weights['tfidf_weight'] * 0.4
                )
                
                keywords.append({
                    'keyword': keyword,
                    'weight': combined_weight,
                    'textrank_weight': weights['textrank_weight'],
                    'tfidf_weight': weights['tfidf_weight']
                })
            
            # 按权重排序
            keywords.sort(key=lambda x: x['weight'], reverse=True)
            
            return keywords[:num_keywords]
            
        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            return []
    
    @staticmethod
    def extract_keyphrases(text: str, num_phrases: int = 5) -> List[str]:
        """提取关键短语"""
        try:
            # 分句
            sentences = re.split(r'[.!?。！？]', text)
            
            # 提取名词短语
            keyphrases = []
            
            for sentence in sentences:
                # 简单的名词短语模式
                patterns = [
                    r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',  # 专有名词短语
                    r'\b(?:的|地)\s*[\u4e00-\u9fff]+',       # 中文形容词短语
                    r'\b[\u4e00-\u9fff]{2,4}(?:系统|方法|技术|模式|框架)\b'  # 技术术语
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, sentence)
                    keyphrases.extend(matches)
            
            # 去重并按长度排序
            unique_phrases = list(set(keyphrases))
            unique_phrases.sort(key=len, reverse=True)
            
            return unique_phrases[:num_phrases]
            
        except Exception as e:
            logger.error(f"关键短语提取失败: {e}")
            return []

# 创建全局实例
tag_extractor = TagExtractor()
keyword_extractor = KeywordExtractor()

# 便捷函数
def extract_tags_from_content(content: str, max_tags: int = 10) -> List[Dict[str, Any]]:
    """从内容中提取标签"""
    return tag_extractor.extract_tags(content, max_tags)

def suggest_document_tags(title: str, content: str, existing_tags: List[str] = None) -> List[str]:
    """为文档建议标签"""
    return tag_extractor.suggest_tags_for_document(title, content, existing_tags)

def extract_keywords_from_text(text: str, num_keywords: int = 10) -> List[Dict[str, Any]]:
    """从文本中提取关键词"""
    return keyword_extractor.extract_keywords(text, num_keywords)
