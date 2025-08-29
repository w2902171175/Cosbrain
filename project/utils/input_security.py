# project/utils/input_security.py
"""
增强版输入安全验证器 - 生产环境版本
支持AI内容检测、多语言处理、高级XSS防护、智能过滤等功能
"""
import re
import html
import bleach
import hashlib
import time
import os
from typing import List, Dict, Set, Optional, Tuple, Any, Union
import logging
import threading
from datetime import datetime, timedelta
import asyncio
from urllib.parse import urlparse
import base64
import json

logger = logging.getLogger(__name__)

# 尝试导入可选依赖
try:
    import langdetect
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    logger.warning("langdetect未安装，语言检测功能不可用")

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    logger.warning("textblob未安装，情感分析功能不可用")

class InputSecurityConfig:
    """输入安全配置"""
    def __init__(self):
        # 基础配置
        self.max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", "50000"))
        self.max_title_length = int(os.getenv("MAX_TITLE_LENGTH", "200"))
        self.min_title_length = int(os.getenv("MIN_TITLE_LENGTH", "5"))
        self.max_username_length = int(os.getenv("MAX_USERNAME_LENGTH", "20"))
        self.min_username_length = int(os.getenv("MIN_USERNAME_LENGTH", "2"))
        
        # 安全配置
        self.enable_ai_detection = os.getenv("ENABLE_AI_DETECTION", "false").lower() == "true"
        self.enable_language_detection = os.getenv("ENABLE_LANGUAGE_DETECTION", "true").lower() == "true"
        self.enable_sentiment_analysis = os.getenv("ENABLE_SENTIMENT_ANALYSIS", "false").lower() == "true"
        self.enable_advanced_xss_protection = os.getenv("ENABLE_ADVANCED_XSS", "true").lower() == "true"
        self.enable_unicode_normalization = os.getenv("ENABLE_UNICODE_NORM", "true").lower() == "true"
        
        # 内容过滤
        self.max_urls_per_content = int(os.getenv("MAX_URLS_PER_CONTENT", "3"))
        self.max_mentions_per_content = int(os.getenv("MAX_MENTIONS_PER_CONTENT", "10"))
        self.min_words_per_content = int(os.getenv("MIN_WORDS_PER_CONTENT", "3"))
        
        # 加载规则
        self.load_security_rules()
    
    def load_security_rules(self):
        """加载安全规则"""
        # XSS防护
        self.allowed_tags = {
            'p', 'br', 'strong', 'em', 'u', 's', 'del', 'ins', 'sub', 'sup',
            'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'thead', 'tbody',
            'tr', 'th', 'td', 'a', 'img', 'hr', 'div', 'span'
        }
        
        self.allowed_attributes = {
            'a': ['href', 'title', 'rel'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'div': ['class'],
            'span': ['class'],
            'code': ['class'],
            'pre': ['class'],
            '*': ['id', 'class']
        }
        
        self.allowed_protocols = ['http', 'https', 'mailto', 'ftp']
        
        # SQL注入模式
        self.sql_injection_patterns = [
            r'\b(union|select|insert|update|delete|drop|create|alter|exec|execute)\s+',
            r'[\'";]',
            r'--\s',
            r'/\*.*?\*/',
            r'\bor\s+\d+\s*=\s*\d+\b',
            r'\band\s+\d+\s*=\s*\d+\b',
            r'\b(having|group\s+by|order\s+by)\s+',
            r'\b(information_schema|sysobjects|msysaccessobjects)\b'
        ]
        
        # XSS模式
        self.xss_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript\s*:',
            r'vbscript\s*:',
            r'on\w+\s*=',
            r'<iframe[^>]*>.*?</iframe>',
            r'<object[^>]*>.*?</object>',
            r'<embed[^>]*>.*?</embed>',
            r'<link[^>]*>',
            r'<meta[^>]*>',
            r'<style[^>]*>.*?</style>',
            r'expression\s*\(',
            r'@import',
            r'binding\s*:',
            r'behavior\s*:'
        ]
        
        # 敏感词库
        self.sensitive_words = {
            'spam': ['垃圾信息', '广告', '推广', '代理', '刷单', '兼职'],
            'illegal': ['违法', '犯罪', '毒品', '枪支', '爆炸', '恐怖'],
            'violence': ['暴力', '杀害', '伤害', '血腥', '残忍'],
            'adult': ['色情', '成人', '性交', '裸体', '黄色'],
            'political': ['政治敏感词需要根据具体情况配置'],
            'abuse': ['骗子', '垃圾', '死去', '滚开', '白痴']
        }
        
        # 用户名规则
        self.username_patterns = {
            'valid': r'^[a-zA-Z0-9_\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]{2,20}$',
            'reserved': {
                'admin', 'administrator', 'root', 'system', 'null', 'undefined',
                'test', 'demo', 'guest', 'anonymous', 'bot', 'api', 'www',
                '管理员', '系统', '测试', '演示', '访客', '匿名'
            }
        }

class AdvancedContentFilter:
    """高级内容过滤器"""
    
    def __init__(self, config: InputSecurityConfig):
        self.config = config
        self.filter_cache = {}
        self.cache_lock = threading.Lock()
    
    def detect_language(self, text: str) -> Dict[str, Any]:
        """检测文本语言"""
        result = {
            'language': 'unknown',
            'confidence': 0.0,
            'supported': True
        }
        
        if not LANGDETECT_AVAILABLE or not self.config.enable_language_detection:
            return result
        
        try:
            language = langdetect.detect(text)
            # langdetect没有置信度，我们根据文本长度估算
            confidence = min(0.9, len(text) / 100)
            
            result.update({
                'language': language,
                'confidence': confidence,
                'supported': language in ['zh-cn', 'en', 'ja', 'ko']
            })
        except Exception as e:
            logger.warning(f"语言检测失败: {e}")
        
        return result
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """情感分析"""
        result = {
            'polarity': 0.0,
            'subjectivity': 0.0,
            'sentiment': 'neutral',
            'confidence': 0.0
        }
        
        if not TEXTBLOB_AVAILABLE or not self.config.enable_sentiment_analysis:
            return result
        
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            subjectivity = blob.sentiment.subjectivity
            
            # 判断情感倾向
            if polarity > 0.1:
                sentiment = 'positive'
            elif polarity < -0.1:
                sentiment = 'negative'
            else:
                sentiment = 'neutral'
            
            result.update({
                'polarity': polarity,
                'subjectivity': subjectivity,
                'sentiment': sentiment,
                'confidence': abs(polarity)
            })
        except Exception as e:
            logger.warning(f"情感分析失败: {e}")
        
        return result
    
    def detect_ai_generated(self, text: str) -> Dict[str, Any]:
        """检测AI生成内容"""
        result = {
            'is_ai_generated': False,
            'confidence': 0.0,
            'indicators': []
        }
        
        if not self.config.enable_ai_detection:
            return result
        
        # 简单的AI检测指标
        ai_indicators = []
        
        # 1. 过于完美的语法
        sentences = text.split('。')
        if len(sentences) > 3:
            avg_length = sum(len(s) for s in sentences) / len(sentences)
            if 20 <= avg_length <= 50:  # AI倾向于生成中等长度的句子
                ai_indicators.append('均匀句长')
        
        # 2. 缺乏个人化表达
        personal_indicators = ['我觉得', '我认为', '我的看法', '个人感受', '亲身经历']
        if not any(indicator in text for indicator in personal_indicators):
            if len(text) > 200:
                ai_indicators.append('缺乏个人化表达')
        
        # 3. 过度使用转折词
        transition_words = ['然而', '但是', '不过', '另外', '此外', '因此', '所以']
        transition_count = sum(text.count(word) for word in transition_words)
        if transition_count > len(text) / 100:
            ai_indicators.append('转折词过多')
        
        # 4. 结构过于完整
        if ('首先' in text or '第一' in text) and ('最后' in text or '总之' in text):
            ai_indicators.append('结构过于完整')
        
        confidence = len(ai_indicators) * 0.2
        result.update({
            'is_ai_generated': confidence > 0.6,
            'confidence': min(confidence, 1.0),
            'indicators': ai_indicators
        })
        
        return result
    
    def normalize_unicode(self, text: str) -> str:
        """Unicode标准化"""
        if not self.config.enable_unicode_normalization:
            return text
        
        try:
            import unicodedata
            # 标准化Unicode字符
            normalized = unicodedata.normalize('NFKC', text)
            
            # 移除零宽字符
            zero_width_chars = ['\u200b', '\u200c', '\u200d', '\ufeff', '\u2060']
            for char in zero_width_chars:
                normalized = normalized.replace(char, '')
            
            return normalized
        except Exception as e:
            logger.warning(f"Unicode标准化失败: {e}")
            return text

class EnhancedInputSecurityValidator:
    """增强版输入安全验证器"""
    
    def __init__(self, config: Optional[InputSecurityConfig] = None):
        self.config = config or InputSecurityConfig()
        self.content_filter = AdvancedContentFilter(self.config)
        self.validation_cache = {}
        self.cache_lock = threading.Lock()
    
    def sanitize_html_advanced(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """高级HTML清理"""
        sanitization_info = {
            'original_length': len(content),
            'removed_tags': [],
            'removed_attributes': [],
            'modified': False
        }
        
        if not content:
            return "", sanitization_info
        
        try:
            # Unicode标准化
            content = self.content_filter.normalize_unicode(content)
            
            # 预处理：记录移除的内容
            original_content = content
            
            if self.config.enable_advanced_xss_protection:
                # 高级XSS检测
                for pattern in self.config.xss_patterns:
                    if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                        sanitization_info['removed_tags'].append(pattern)
                        sanitization_info['modified'] = True
            
            # 使用bleach清理
            cleaned_content = bleach.clean(
                content,
                tags=self.config.allowed_tags,
                attributes=self.config.allowed_attributes,
                protocols=self.config.allowed_protocols,
                strip=True
            )
            
            # 额外的安全处理
            cleaned_content = self._additional_security_cleaning(cleaned_content)
            
            sanitization_info.update({
                'cleaned_length': len(cleaned_content),
                'modified': original_content != cleaned_content
            })
            
            return cleaned_content, sanitization_info
            
        except Exception as e:
            logger.error(f"HTML清理失败: {e}")
            # 失败时返回完全转义的内容
            escaped_content = html.escape(content)
            sanitization_info['modified'] = True
            sanitization_info['cleaned_length'] = len(escaped_content)
            return escaped_content, sanitization_info
    
    def _additional_security_cleaning(self, content: str) -> str:
        """额外的安全清理"""
        # 移除潜在的脚本注入
        dangerous_patterns = [
            r'javascript\s*:',
            r'data\s*:.*base64',
            r'vbscript\s*:',
            r'expression\s*\(',
            r'@import\s+',
            r'binding\s*:',
            r'behavior\s*:'
        ]
        
        for pattern in dangerous_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        return content
    
    def validate_username_advanced(self, username: str) -> Tuple[bool, str, Dict[str, Any]]:
        """高级用户名验证"""
        validation_info = {
            'original': username,
            'normalized': '',
            'length': len(username) if username else 0,
            'issues': [],
            'suggestions': []
        }
        
        if not username:
            validation_info['issues'].append('用户名不能为空')
            return False, "用户名不能为空", validation_info
        
        # Unicode标准化
        normalized_username = self.content_filter.normalize_unicode(username)
        validation_info['normalized'] = normalized_username
        
        # 长度检查
        if len(normalized_username) < self.config.min_username_length:
            validation_info['issues'].append(f'用户名过短（最少{self.config.min_username_length}个字符）')
            return False, f"用户名过短（最少{self.config.min_username_length}个字符）", validation_info
        
        if len(normalized_username) > self.config.max_username_length:
            validation_info['issues'].append(f'用户名过长（最多{self.config.max_username_length}个字符）')
            return False, f"用户名过长（最多{self.config.max_username_length}个字符）", validation_info
        
        # 格式检查
        if not re.match(self.config.username_patterns['valid'], normalized_username):
            validation_info['issues'].append('用户名只能包含字母、数字、下划线和中日韩文字符')
            return False, "用户名只能包含字母、数字、下划线和中日韩文字符", validation_info
        
        # 保留词检查
        if normalized_username.lower() in self.config.username_patterns['reserved']:
            validation_info['issues'].append('用户名不能使用保留词')
            validation_info['suggestions'].append(f'尝试在用户名后添加数字：{normalized_username}123')
            return False, "用户名不能使用保留词", validation_info
        
        # 敏感词检查
        if self._contains_sensitive_words(normalized_username):
            validation_info['issues'].append('用户名包含敏感词汇')
            return False, "用户名包含敏感词汇", validation_info
        
        return True, "用户名验证通过", validation_info
    
    def detect_injection_attacks(self, text: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """检测注入攻击"""
        attacks_detected = []
        
        if not text:
            return False, attacks_detected
        
        # SQL注入检测
        for pattern in self.config.sql_injection_patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            for match in matches:
                attacks_detected.append({
                    'type': 'sql_injection',
                    'pattern': pattern,
                    'match': match.group(),
                    'position': match.span(),
                    'risk_level': 'high'
                })
        
        # XSS攻击检测
        for pattern in self.config.xss_patterns:
            matches = list(re.finditer(pattern, text, re.IGNORECASE | re.DOTALL))
            for match in matches:
                attacks_detected.append({
                    'type': 'xss',
                    'pattern': pattern,
                    'match': match.group()[:100],  # 限制匹配内容长度
                    'position': match.span(),
                    'risk_level': 'high'
                })
        
        # LDAP注入检测
        ldap_patterns = [r'\*\)', r'\|\|', r'&\(&']
        for pattern in ldap_patterns:
            if re.search(pattern, text):
                attacks_detected.append({
                    'type': 'ldap_injection',
                    'pattern': pattern,
                    'risk_level': 'medium'
                })
        
        # 命令注入检测
        command_patterns = [r'[;&|`]', r'\$\(', r'>\s*/']
        for pattern in command_patterns:
            if re.search(pattern, text):
                attacks_detected.append({
                    'type': 'command_injection',
                    'pattern': pattern,
                    'risk_level': 'high'
                })
        
        return len(attacks_detected) > 0, attacks_detected
    
    def extract_and_validate_entities(self, content: str) -> Dict[str, Any]:
        """提取和验证实体"""
        entities = {
            'mentions': [],
            'urls': [],
            'emails': [],
            'hashtags': [],
            'phone_numbers': [],
            'invalid_entities': []
        }
        
        if not content:
            return entities
        
        # 提取@用户名
        mention_pattern = r'@([a-zA-Z0-9_\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+)'
        mentions = re.findall(mention_pattern, content)
        
        for mention in mentions:
            is_valid, _, _ = self.validate_username_advanced(mention)
            if is_valid:
                entities['mentions'].append(mention)
            else:
                entities['invalid_entities'].append(('mention', mention))
        
        # 提取URL
        url_pattern = r'https?://[^\s<>"\'`]+|www\.[^\s<>"\'`]+'
        urls = re.findall(url_pattern, content, re.IGNORECASE)
        
        for url in urls:
            if self._validate_url(url):
                entities['urls'].append(url)
            else:
                entities['invalid_entities'].append(('url', url))
        
        # 提取邮箱
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, content)
        entities['emails'] = emails
        
        # 提取话题标签
        hashtag_pattern = r'#([a-zA-Z0-9_\u4e00-\u9fa5]+)'
        hashtags = re.findall(hashtag_pattern, content)
        entities['hashtags'] = hashtags
        
        # 提取电话号码
        phone_pattern = r'1[3-9]\d{9}|\d{3}-\d{4}-\d{4}|\d{3}\s\d{4}\s\d{4}'
        phones = re.findall(phone_pattern, content)
        entities['phone_numbers'] = phones
        
        return entities
    
    def _validate_url(self, url: str) -> bool:
        """验证URL"""
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            
            parsed = urlparse(url)
            
            # 检查域名
            if not parsed.netloc:
                return False
            
            # 检查是否为恶意域名（需要维护黑名单）
            malicious_domains = ['example-malicious.com']  # 示例
            if any(domain in parsed.netloc for domain in malicious_domains):
                return False
            
            return True
        except Exception:
            return False
    
    def _contains_sensitive_words(self, text: str) -> bool:
        """检查敏感词"""
        text_lower = text.lower()
        
        for category, words in self.config.sensitive_words.items():
            for word in words:
                if word.lower() in text_lower:
                    return True
        
        return False
    
    def validate_content_length_and_quality(self, content: str) -> Tuple[bool, str, Dict[str, Any]]:
        """验证内容长度和质量"""
        quality_info = {
            'char_count': len(content),
            'word_count': 0,
            'sentence_count': 0,
            'paragraph_count': 0,
            'repetition_ratio': 0.0,
            'language_info': {},
            'sentiment_info': {},
            'ai_detection': {}
        }
        
        if not content:
            return False, "内容不能为空", quality_info
        
        # 基础统计
        words = re.findall(r'\b\w+\b', content)
        quality_info['word_count'] = len(words)
        quality_info['sentence_count'] = len(re.findall(r'[.!?。！？]+', content))
        quality_info['paragraph_count'] = len([p for p in content.split('\n\n') if p.strip()])
        
        # 长度检查
        if len(content) > self.config.max_content_length:
            return False, f"内容过长，最大允许{self.config.max_content_length}个字符", quality_info
        
        if quality_info['word_count'] < self.config.min_words_per_content:
            return False, f"内容过短，至少需要{self.config.min_words_per_content}个词", quality_info
        
        # 重复内容检查
        if words:
            unique_words = set(words)
            quality_info['repetition_ratio'] = 1 - (len(unique_words) / len(words))
            
            if quality_info['repetition_ratio'] > 0.7:
                return False, "内容重复度过高", quality_info
        
        # 高级分析
        quality_info['language_info'] = self.content_filter.detect_language(content)
        quality_info['sentiment_info'] = self.content_filter.analyze_sentiment(content)
        quality_info['ai_detection'] = self.content_filter.detect_ai_generated(content)
        
        return True, "内容质量验证通过", quality_info

class SmartRateLimiter:
    """智能速率限制器"""
    
    def __init__(self):
        self.limits = {
            "post_topic": {"count": 10, "window": 3600, "burst": 3},
            "post_comment": {"count": 50, "window": 3600, "burst": 10},
            "upload_file": {"count": 20, "window": 3600, "burst": 5},
            "mention_user": {"count": 100, "window": 3600, "burst": 20},
            "search": {"count": 200, "window": 3600, "burst": 50}
        }
        self.user_behavior = {}  # 用户行为分析
        self.lock = threading.Lock()
    
    def check_rate_limit_smart(self, user_id: int, action: str, cache_manager, 
                              context: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any]]:
        """智能速率检查"""
        if action not in self.limits:
            return True, {}
        
        limit_config = self.limits[action].copy()
        
        # 根据用户行为调整限制
        with self.lock:
            if user_id in self.user_behavior:
                behavior = self.user_behavior[user_id]
                
                # 信誉良好的用户放松限制
                if behavior.get('reputation_score', 0) > 0.8:
                    limit_config['count'] = int(limit_config['count'] * 1.5)
                    limit_config['burst'] = int(limit_config['burst'] * 1.2)
                
                # 可疑用户收紧限制
                elif behavior.get('reputation_score', 0) < 0.3:
                    limit_config['count'] = int(limit_config['count'] * 0.5)
                    limit_config['burst'] = int(limit_config['burst'] * 0.5)
        
        # 检查突发限制
        burst_key = f"rate_limit:burst:{action}:{user_id}"
        burst_count = cache_manager.get(burst_key) or 0
        
        if burst_count >= limit_config['burst']:
            # 检查是否在冷却期
            cooldown_key = f"rate_limit:cooldown:{action}:{user_id}"
            if cache_manager.exists(cooldown_key):
                return False, {
                    "action": action,
                    "reason": "超过突发限制，正在冷却",
                    "cooldown_remaining": cache_manager.ttl(cooldown_key)
                }
        
        # 检查常规限制
        cache_key = f"rate_limit:{action}:{user_id}"
        current_count = cache_manager.get(cache_key) or 0
        
        if current_count >= limit_config["count"]:
            return False, {
                "action": action,
                "limit": limit_config["count"],
                "window": limit_config["window"],
                "current": current_count,
                "reason": "超过速率限制"
            }
        
        # 更新计数器
        cache_manager.set(cache_key, current_count + 1, limit_config["window"])
        cache_manager.set(burst_key, burst_count + 1, 300)  # 5分钟突发窗口
        
        # 如果达到突发限制，设置冷却期
        if burst_count + 1 >= limit_config['burst']:
            cache_manager.set(cooldown_key, True, 600)  # 10分钟冷却
        
        return True, {
            "action": action,
            "limit": limit_config["count"],
            "window": limit_config["window"],
            "current": current_count + 1,
            "burst_current": burst_count + 1,
            "burst_limit": limit_config["burst"]
        }
    
    def update_user_reputation(self, user_id: int, action: str, success: bool):
        """更新用户信誉"""
        with self.lock:
            if user_id not in self.user_behavior:
                self.user_behavior[user_id] = {
                    'reputation_score': 0.5,
                    'action_count': 0,
                    'success_count': 0,
                    'last_activity': time.time()
                }
            
            behavior = self.user_behavior[user_id]
            behavior['action_count'] += 1
            behavior['last_activity'] = time.time()
            
            if success:
                behavior['success_count'] += 1
            
            # 计算新的信誉分数
            success_rate = behavior['success_count'] / behavior['action_count']
            behavior['reputation_score'] = (behavior['reputation_score'] * 0.9) + (success_rate * 0.1)

def validate_forum_input(
    title: str, 
    content: str, 
    user_id: int,
    cache_manager=None,
    config: Optional[InputSecurityConfig] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """增强版论坛输入验证"""
    
    validator = EnhancedInputSecurityValidator(config)
    rate_limiter = SmartRateLimiter()
    
    validation_result = {
        'title_validation': {},
        'content_validation': {},
        'security_checks': {},
        'entity_extraction': {},
        'rate_limit_check': {},
        'processing_time': 0,
        'cleaned_data': {}
    }
    
    start_time = time.time()
    
    try:
        # 1. 基础验证
        if not title or not title.strip():
            return False, "标题不能为空", validation_result
        
        if not content or not content.strip():
            return False, "内容不能为空", validation_result
        
        # 2. 内容质量验证
        is_valid, message, quality_info = validator.validate_content_length_and_quality(content)
        validation_result['content_validation'] = quality_info
        if not is_valid:
            return False, message, validation_result
        
        # 3. 安全检查
        has_injection, injection_details = validator.detect_injection_attacks(title + " " + content)
        validation_result['security_checks']['injection_attacks'] = injection_details
        if has_injection:
            return False, "输入包含潜在的安全威胁", validation_result
        
        # 4. HTML清理
        cleaned_content, sanitization_info = validator.sanitize_html_advanced(content)
        validation_result['security_checks']['sanitization'] = sanitization_info
        validation_result['cleaned_data']['content'] = cleaned_content
        validation_result['cleaned_data']['title'] = html.escape(title.strip())
        
        # 5. 实体提取和验证
        entities = validator.extract_and_validate_entities(content)
        validation_result['entity_extraction'] = entities
        
        # 检查URL数量限制
        if len(entities['urls']) > validator.config.max_urls_per_content:
            return False, f"内容包含过多链接（最多{validator.config.max_urls_per_content}个）", validation_result
        
        # 检查提及数量限制
        if len(entities['mentions']) > validator.config.max_mentions_per_content:
            return False, f"内容包含过多@用户（最多{validator.config.max_mentions_per_content}个）", validation_result
        
        # 6. 速率限制检查
        if cache_manager:
            is_allowed, rate_info = rate_limiter.check_rate_limit_smart(
                user_id, "post_topic", cache_manager
            )
            validation_result['rate_limit_check'] = rate_info
            if not is_allowed:
                return False, rate_info.get('reason', '操作过于频繁'), validation_result
        
        # 7. AI内容检测警告
        ai_detection = validation_result['content_validation'].get('ai_detection', {})
        if ai_detection.get('is_ai_generated', False) and ai_detection.get('confidence', 0) > 0.8:
            validation_result['warnings'] = ['内容可能由AI生成']
        
        validation_result['processing_time'] = time.time() - start_time
        
        return True, "输入验证通过", validation_result
        
    except Exception as e:
        logger.error(f"输入验证异常: {e}")
        validation_result['processing_time'] = time.time() - start_time
        validation_result['error'] = str(e)
        return False, f"输入验证失败: {str(e)}", validation_result

# 全局实例
default_input_security_config = InputSecurityConfig()
input_validator = EnhancedInputSecurityValidator()
smart_rate_limiter = SmartRateLimiter()
