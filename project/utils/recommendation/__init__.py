# project/utils/recommendation/__init__.py
"""
推荐算法工具模块
"""

from .behavior_analyzer import BehaviorAnalyzer, UserAction, UserBehavior, UserProfile
from .content_matcher import ContentMatcher, SimilarityCalculator
from .tag_extractor import TagExtractor, KeywordExtractor

# 便捷函数导入
from .behavior_analyzer import record_user_behavior, get_user_profile, get_user_behaviors
from .content_matcher import add_document_to_index, find_similar_documents, calculate_similarity
from .tag_extractor import extract_tags_from_content, suggest_document_tags, extract_keywords_from_text

__all__ = [
    # 类
    'BehaviorAnalyzer',
    'UserAction',
    'UserBehavior', 
    'UserProfile',
    'ContentMatcher',
    'SimilarityCalculator',
    'TagExtractor',
    'KeywordExtractor',
    
    # 便捷函数
    'record_user_behavior',
    'get_user_profile',
    'get_user_behaviors',
    'add_document_to_index',
    'find_similar_documents',
    'calculate_similarity',
    'extract_tags_from_content',
    'suggest_document_tags',
    'extract_keywords_from_text'
]
