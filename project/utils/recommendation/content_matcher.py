# project/utils/recommendation/content_matcher.py
"""
内容相似度计算工具
基于文本内容进行相似度计算和推荐
"""

import re
import math
from typing import Dict, List, Optional, Any, Tuple
import logging
import jieba
import jieba.analyse
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict

logger = logging.getLogger(__name__)

class ContentMatcher:
    """内容匹配器"""
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words=None,
            ngram_range=(1, 2)
        )
        self.document_vectors = {}
        self.document_texts = {}
    
    def preprocess_text(self, text: str) -> str:
        """预处理文本"""
        try:
            # 清理文本
            text = re.sub(r'[^\w\s]', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            
            # 中文分词
            words = jieba.cut(text)
            processed_text = ' '.join(words)
            
            return processed_text.lower().strip()
            
        except Exception as e:
            logger.error(f"文本预处理失败: {e}")
            return text
    
    def add_document(self, doc_id: int, content: str, metadata: Dict[str, Any] = None):
        """添加文档到索引"""
        try:
            processed_content = self.preprocess_text(content)
            self.document_texts[doc_id] = {
                'content': processed_content,
                'metadata': metadata or {}
            }
            
            # 重新构建向量索引
            self._rebuild_vectors()
            
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
    
    def find_similar_documents(self, doc_id: int, 
                             threshold: float = 0.5, 
                             limit: int = 10) -> List[Tuple[int, float]]:
        """查找相似文档"""
        try:
            if doc_id not in self.document_vectors:
                return []
            
            target_vector = self.document_vectors[doc_id]
            similarities = []
            
            for other_id, other_vector in self.document_vectors.items():
                if other_id != doc_id:
                    similarity = cosine_similarity([target_vector], [other_vector])[0][0]
                    if similarity >= threshold:
                        similarities.append((other_id, similarity))
            
            # 按相似度排序
            similarities.sort(key=lambda x: x[1], reverse=True)
            return similarities[:limit]
            
        except Exception as e:
            logger.error(f"查找相似文档失败: {e}")
            return []
    
    def find_similar_by_content(self, content: str, 
                               threshold: float = 0.5, 
                               limit: int = 10) -> List[Tuple[int, float]]:
        """根据内容查找相似文档"""
        try:
            processed_content = self.preprocess_text(content)
            
            if not self.document_texts:
                return []
            
            # 计算输入内容的向量
            all_texts = [processed_content] + [
                doc['content'] for doc in self.document_texts.values()
            ]
            
            vectors = self.vectorizer.fit_transform(all_texts)
            input_vector = vectors[0]
            doc_vectors = vectors[1:]
            
            similarities = []
            doc_ids = list(self.document_texts.keys())
            
            for i, doc_id in enumerate(doc_ids):
                similarity = cosine_similarity(input_vector, doc_vectors[i])[0][0]
                if similarity >= threshold:
                    similarities.append((doc_id, similarity))
            
            # 按相似度排序
            similarities.sort(key=lambda x: x[1], reverse=True)
            return similarities[:limit]
            
        except Exception as e:
            logger.error(f"根据内容查找相似文档失败: {e}")
            return []
    
    def get_content_features(self, content: str) -> Dict[str, Any]:
        """提取内容特征"""
        try:
            processed_content = self.preprocess_text(content)
            
            # 提取关键词
            keywords = jieba.analyse.extract_tags(content, topK=10, withWeight=True)
            
            # 计算基本统计
            features = {
                'length': len(content),
                'word_count': len(processed_content.split()),
                'keywords': dict(keywords),
                'language': self._detect_language(content),
                'readability': self._calculate_readability(content)
            }
            
            return features
            
        except Exception as e:
            logger.error(f"提取内容特征失败: {e}")
            return {}
    
    def _rebuild_vectors(self):
        """重建向量索引"""
        try:
            if not self.document_texts:
                return
            
            texts = [doc['content'] for doc in self.document_texts.values()]
            doc_ids = list(self.document_texts.keys())
            
            vectors = self.vectorizer.fit_transform(texts)
            
            self.document_vectors = {}
            for i, doc_id in enumerate(doc_ids):
                self.document_vectors[doc_id] = vectors[i].toarray()[0]
                
        except Exception as e:
            logger.error(f"重建向量索引失败: {e}")
    
    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        # 简单的中英文检测
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        if chinese_chars > english_chars:
            return 'zh'
        elif english_chars > chinese_chars:
            return 'en'
        else:
            return 'mixed'
    
    def _calculate_readability(self, text: str) -> float:
        """计算文本可读性评分"""
        try:
            sentences = re.split(r'[.!?。！？]', text)
            words = self.preprocess_text(text).split()
            
            if not sentences or not words:
                return 0.0
            
            avg_sentence_length = len(words) / len(sentences)
            
            # 简化的可读性评分
            if avg_sentence_length <= 10:
                return 1.0
            elif avg_sentence_length <= 20:
                return 0.8
            elif avg_sentence_length <= 30:
                return 0.6
            else:
                return 0.4
                
        except Exception as e:
            logger.error(f"计算可读性失败: {e}")
            return 0.5

class SimilarityCalculator:
    """相似度计算器"""
    
    @staticmethod
    def jaccard_similarity(set1: set, set2: set) -> float:
        """计算Jaccard相似度"""
        if not set1 and not set2:
            return 1.0
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def cosine_similarity_vectors(vec1: List[float], vec2: List[float]) -> float:
        """计算向量余弦相似度"""
        try:
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return dot_product / (norm1 * norm2)
            
        except Exception as e:
            logger.error(f"计算余弦相似度失败: {e}")
            return 0.0
    
    @staticmethod
    def semantic_similarity(text1: str, text2: str) -> float:
        """计算语义相似度"""
        try:
            # 提取关键词
            keywords1 = set(word for word, weight in jieba.analyse.extract_tags(text1, topK=20, withWeight=True))
            keywords2 = set(word for word, weight in jieba.analyse.extract_tags(text2, topK=20, withWeight=True))
            
            return SimilarityCalculator.jaccard_similarity(keywords1, keywords2)
            
        except Exception as e:
            logger.error(f"计算语义相似度失败: {e}")
            return 0.0
    
    @staticmethod
    def combined_similarity(text1: str, text2: str, 
                          weights: Dict[str, float] = None) -> float:
        """计算综合相似度"""
        if weights is None:
            weights = {
                'semantic': 0.6,
                'lexical': 0.4
            }
        
        try:
            # 语义相似度
            semantic_sim = SimilarityCalculator.semantic_similarity(text1, text2)
            
            # 词汇相似度（简单的词汇重叠）
            words1 = set(jieba.cut(text1))
            words2 = set(jieba.cut(text2))
            lexical_sim = SimilarityCalculator.jaccard_similarity(words1, words2)
            
            # 加权平均
            combined_sim = (
                semantic_sim * weights.get('semantic', 0.6) +
                lexical_sim * weights.get('lexical', 0.4)
            )
            
            return combined_sim
            
        except Exception as e:
            logger.error(f"计算综合相似度失败: {e}")
            return 0.0

# 创建全局实例
content_matcher = ContentMatcher()
similarity_calculator = SimilarityCalculator()

# 便捷函数
def add_document_to_index(doc_id: int, content: str, metadata: Dict[str, Any] = None):
    """添加文档到索引"""
    content_matcher.add_document(doc_id, content, metadata)

def find_similar_documents(doc_id: int, threshold: float = 0.5, limit: int = 10) -> List[Tuple[int, float]]:
    """查找相似文档"""
    return content_matcher.find_similar_documents(doc_id, threshold, limit)

def calculate_similarity(text1: str, text2: str) -> float:
    """计算文本相似度"""
    return similarity_calculator.combined_similarity(text1, text2)
