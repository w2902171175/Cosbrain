# project/utils/file_security.py
"""
增强版文件安全验证器 - 生产环境版本
支持病毒扫描、深度内容分析、文件指纹识别、智能分类等高级功能
"""
import os
import hashlib
import mimetypes
import re
import subprocess
import tempfile
from typing import Tuple, List, Dict, Any, Optional, Union
from PIL import Image, ImageFile
from io import BytesIO
import logging
from datetime import datetime, timedelta
import threading
import time

logger = logging.getLogger(__name__)

# 可选依赖
try:
    import magic
    HAS_MAGIC = True
    logger.info("🔍 File Security - python-magic 增强检测已启用")
except ImportError:
    HAS_MAGIC = False
    logger.debug("python-magic 不可用，将使用基础文件类型检测")

try:
    import filetype
    HAS_FILETYPE = True
    logger.info("📄 File Security - filetype 验证增强已启用")
except ImportError:
    HAS_FILETYPE = False
    logger.debug("filetype 不可用，将跳过filetype检测")

# YARA检查 - 动态检测是否可用
def _check_yara_available():
    """检查YARA是否可用"""
    try:
        import yara  # type: ignore
        return True
    except ImportError:
        return False

HAS_YARA = _check_yara_available()
if HAS_YARA:
    logger.info("🛡️ File Security - YARA 恶意软件检测已启用")
else:
    logger.debug("yara-python 不可用，将跳过病毒扫描")

logger = logging.getLogger(__name__)

# 配置类
class FileSecurityConfig:
    """文件安全配置"""
    def __init__(self):
        # 基础配置
        self.max_file_size = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB
        self.enable_virus_scan = os.getenv("ENABLE_VIRUS_SCAN", "false").lower() == "true"
        self.enable_yara_scan = os.getenv("ENABLE_YARA_SCAN", "false").lower() == "true"
        self.yara_rules_path = os.getenv("YARA_RULES_PATH", "")
        self.clamav_path = os.getenv("CLAMAV_PATH", "/usr/bin/clamscan")
        self.enable_file_signature_check = os.getenv("ENABLE_FILE_SIGNATURE_CHECK", "true").lower() == "true"
        self.quarantine_path = os.getenv("QUARANTINE_PATH", "/tmp/quarantine")
        self.enable_ocr_scan = os.getenv("ENABLE_OCR_SCAN", "false").lower() == "true"
        
        # 文件类型配置
        self.allowed_extensions = self._load_allowed_extensions()
        self.file_size_limits = self._load_file_size_limits()
        self.dangerous_extensions = self._load_dangerous_extensions()
        self.allowed_mime_types = self._load_allowed_mime_types()
        
        # 安全规则
        self.max_image_pixels = int(os.getenv("MAX_IMAGE_PIXELS", str(50 * 1024 * 1024)))  # 50M像素
        self.max_filename_length = int(os.getenv("MAX_FILENAME_LENGTH", "255"))
        self.enable_content_analysis = os.getenv("ENABLE_CONTENT_ANALYSIS", "true").lower() == "true"
    
    def _load_allowed_extensions(self) -> Dict[str, set]:
        """加载允许的文件扩展名"""
        return {
            'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.ico'},
            'documents': {'.txt', '.md', '.pdf', '.docx', '.pptx', '.xlsx', '.doc', '.ppt', '.xls', '.rtf', '.odt'},
            'code': {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.css', '.html', '.json', '.xml', '.yml', '.yaml', '.go', '.rs', '.php'},
            'audio': {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma'},
            'video': {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', '.m4v', '.3gp'},
            'archives': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'},
            'ebooks': {'.epub', '.mobi', '.azw', '.azw3'}
        }
    
    def _load_file_size_limits(self) -> Dict[str, int]:
        """加载文件大小限制"""
        return {
            'images': 20 * 1024 * 1024,      # 20MB
            'documents': 100 * 1024 * 1024,  # 100MB
            'code': 10 * 1024 * 1024,        # 10MB
            'audio': 200 * 1024 * 1024,      # 200MB
            'video': 1024 * 1024 * 1024,     # 1GB
            'archives': 500 * 1024 * 1024,   # 500MB
            'ebooks': 50 * 1024 * 1024       # 50MB
        }
    
    def _load_dangerous_extensions(self) -> set:
        """加载危险文件扩展名"""
        return {
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar',
            '.app', '.deb', '.pkg', '.dmg', '.msi', '.dll', '.sys', '.drv',
            '.php', '.asp', '.aspx', '.jsp', '.cgi', '.pl', '.sh', '.ps1',
            '.psm1', '.psd1', '.vb', '.wsf', '.wsh', '.hta', '.reg'
        }
    
    def _load_allowed_mime_types(self) -> set:
        """加载允许的MIME类型"""
        return {
            # 图片
            'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp', 
            'image/svg+xml', 'image/tiff', 'image/x-icon',
            # 文档
            'text/plain', 'text/markdown', 'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/msword', 'application/vnd.ms-powerpoint', 'application/vnd.ms-excel',
            'application/rtf', 'application/vnd.oasis.opendocument.text',
            # 代码
            'text/x-python', 'application/javascript', 'text/javascript', 'application/json',
            'text/css', 'text/html', 'application/xml', 'text/xml', 'application/x-yaml',
            'text/yaml', 'text/x-go', 'text/x-rust', 'application/x-php',
            # 音频
            'audio/mpeg', 'audio/wav', 'audio/x-m4a', 'audio/aac', 'audio/ogg', 
            'audio/flac', 'audio/x-ms-wma',
            # 视频
            'video/mp4', 'video/x-msvideo', 'video/quicktime', 'video/x-ms-wmv',
            'video/x-flv', 'video/webm', 'video/x-matroska', 'video/3gpp',
            # 压缩文件
            'application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed',
            'application/x-tar', 'application/gzip', 'application/x-bzip2',
            # 电子书
            'application/epub+zip', 'application/x-mobipocket-ebook'
        }

class FileFingerprint:
    """文件指纹识别"""
    
    @staticmethod
    def calculate_hashes(file_content: bytes) -> Dict[str, str]:
        """计算多种哈希值"""
        return {
            'md5': hashlib.md5(file_content).hexdigest(),
            'sha1': hashlib.sha1(file_content).hexdigest(),
            'sha256': hashlib.sha256(file_content).hexdigest(),
            'sha512': hashlib.sha512(file_content).hexdigest()
        }
    
    @staticmethod
    def detect_file_type(file_content: bytes) -> Dict[str, Any]:
        """检测文件真实类型"""
        result = {
            'magic_type': None,
            'filetype_guess': None,
            'confidence': 0.0
        }
        
        try:
            # 使用python-magic检测（如果可用）
            if HAS_MAGIC:
                result['magic_type'] = magic.from_buffer(file_content, mime=True)
        except Exception as e:
            logger.warning(f"Magic检测失败: {e}")
        
        try:
            # 使用filetype检测（如果可用）
            if HAS_FILETYPE:
                kind = filetype.guess(file_content)
                if kind:
                    result['filetype_guess'] = kind.mime
                    result['confidence'] = 0.8  # filetype通常比较准确
        except Exception as e:
            logger.warning(f"Filetype检测失败: {e}")
        
        return result

class VirusScanner:
    """病毒扫描器"""
    
    def __init__(self, config: FileSecurityConfig):
        self.config = config
        self.yara_rules = None
        self._load_yara_rules()
    
    def _load_yara_rules(self):
        """加载YARA规则"""
        if not self.config.enable_yara_scan or not self.config.yara_rules_path or not HAS_YARA:
            return
        
        try:
            if os.path.exists(self.config.yara_rules_path):
                # 动态导入yara，避免全局导入错误
                try:
                    import yara  # type: ignore
                    self.yara_rules = yara.compile(filepath=self.config.yara_rules_path)
                    logger.info("YARA规则加载成功")
                except ImportError:
                    logger.warning("YARA不可用，跳过规则加载")
        except Exception as e:
            logger.error(f"YARA规则加载失败: {e}")
    
    def scan_with_clamav(self, file_path: str) -> Tuple[bool, str]:
        """使用ClamAV扫描文件"""
        if not self.config.enable_virus_scan:
            return True, "病毒扫描已禁用"
        
        try:
            if not os.path.exists(self.config.clamav_path):
                return True, "ClamAV未安装"
            
            result = subprocess.run(
                [self.config.clamav_path, '--quiet', '--infected', file_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, "无病毒"
            elif result.returncode == 1:
                return False, f"发现病毒: {result.stdout.strip()}"
            else:
                return True, f"扫描错误: {result.stderr.strip()}"
                
        except subprocess.TimeoutExpired:
            return False, "病毒扫描超时"
        except Exception as e:
            logger.error(f"ClamAV扫描失败: {e}")
            return True, f"扫描失败: {str(e)}"
    
    def scan_with_yara(self, file_content: bytes) -> Tuple[bool, List[str]]:
        """使用YARA规则扫描"""
        if not self.config.enable_yara_scan or not self.yara_rules:
            return True, []
        
        try:
            matches = self.yara_rules.match(data=file_content)
            if matches:
                return False, [match.rule for match in matches]
            return True, []
            
        except Exception as e:
            logger.error(f"YARA扫描失败: {e}")
            return True, []

class ContentAnalyzer:
    """内容分析器"""
    
    @staticmethod
    def analyze_text_content(content: str) -> Dict[str, Any]:
        """分析文本内容"""
        analysis = {
            'language': 'unknown',
            'encoding': 'utf-8',
            'line_count': content.count('\n'),
            'char_count': len(content),
            'suspicious_patterns': [],
            'contains_urls': bool(re.search(r'https?://\S+', content)),
            'contains_emails': bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', content))
        }
        
        # 检测可疑模式
        suspicious_patterns = [
            (r'<script[^>]*>.*?</script>', 'JavaScript代码'),
            (r'eval\s*\(', 'Eval函数'),
            (r'document\.write', 'Document.write'),
            (r'window\.location', 'Location重定向'),
            (r'base64_decode', 'Base64解码'),
            (r'shell_exec|system|exec', 'Shell执行'),
            (r'sql\s*(select|insert|update|delete)', 'SQL语句')
        ]
        
        for pattern, description in suspicious_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                analysis['suspicious_patterns'].append(description)
        
        return analysis
    
    @staticmethod
    def analyze_image_content(file_content: bytes) -> Dict[str, Any]:
        """分析图片内容"""
        analysis = {
            'format': None,
            'size': None,
            'mode': None,
            'has_exif': False,
            'exif_data': {},
            'is_animated': False,
            'frame_count': 1
        }
        
        try:
            with Image.open(BytesIO(file_content)) as img:
                analysis['format'] = img.format
                analysis['size'] = img.size
                analysis['mode'] = img.mode
                
                # EXIF数据
                if hasattr(img, '_getexif') and img._getexif():
                    analysis['has_exif'] = True
                    exif = img._getexif()
                    if exif:
                        # 只保留安全的EXIF信息
                        safe_tags = {272: 'model', 306: 'datetime', 271: 'make'}
                        analysis['exif_data'] = {
                            safe_tags.get(tag, f'tag_{tag}'): value 
                            for tag, value in exif.items() 
                            if tag in safe_tags
                        }
                
                # 动图检测
                if hasattr(img, 'is_animated'):
                    analysis['is_animated'] = img.is_animated
                    if img.is_animated:
                        analysis['frame_count'] = getattr(img, 'n_frames', 1)
        
        except Exception as e:
            logger.warning(f"图片分析失败: {e}")
        
        return analysis

class EnhancedFileSecurityValidator:
    """增强版文件安全验证器"""
    
    def __init__(self, config: Optional[FileSecurityConfig] = None):
        self.config = config or FileSecurityConfig()
        self.virus_scanner = VirusScanner(self.config)
        self.fingerprint = FileFingerprint()
        self.content_analyzer = ContentAnalyzer()
        self.scan_cache = {}  # 扫描结果缓存
        self.cache_lock = threading.Lock()
    
    def get_file_category(self, filename: str) -> Optional[str]:
        """根据文件扩展名获取文件类别"""
        ext = os.path.splitext(filename.lower())[1]
        for category, extensions in self.config.allowed_extensions.items():
            if ext in extensions:
                return category
        return None
    
    def validate_filename(self, filename: str) -> Tuple[bool, str, Dict[str, Any]]:
        """验证文件名安全性"""
        details = {
            'original_filename': filename,
            'sanitized_filename': '',
            'issues': []
        }
        
        if not filename:
            return False, "文件名不能为空", details
        
        # 长度检查
        if len(filename) > self.config.max_filename_length:
            details['issues'].append(f"文件名过长（最大{self.config.max_filename_length}字符）")
            return False, f"文件名过长（最大{self.config.max_filename_length}字符）", details
        
        # 非法字符检查
        illegal_chars = r'[<>:"/\\|?*\x00-\x1f]'
        if re.search(illegal_chars, filename):
            details['issues'].append("包含非法字符")
            return False, "文件名包含非法字符", details
        
        # 扩展名检查
        ext = os.path.splitext(filename.lower())[1]
        if ext in self.config.dangerous_extensions:
            details['issues'].append(f"危险文件类型: {ext}")
            return False, f"不允许的文件类型: {ext}", details
        
        # 白名单检查
        category = self.get_file_category(filename)
        if not category:
            details['issues'].append(f"不支持的文件类型: {ext}")
            return False, f"不支持的文件类型: {ext}", details
        
        # 生成安全文件名
        details['sanitized_filename'] = self.generate_secure_filename(filename)
        details['category'] = category
        
        return True, "文件名验证通过", details
    
    def validate_file_size(self, file_size: int, filename: str) -> Tuple[bool, str, Dict[str, Any]]:
        """验证文件大小"""
        details = {
            'file_size': file_size,
            'file_size_human': self._format_file_size(file_size),
            'category': self.get_file_category(filename),
            'limit': 0,
            'limit_human': ''
        }
        
        category = self.get_file_category(filename)
        if not category:
            return False, "无法确定文件类别", details
        
        max_size = self.config.file_size_limits.get(category, self.config.max_file_size)
        details['limit'] = max_size
        details['limit_human'] = self._format_file_size(max_size)
        
        if file_size > max_size:
            return False, f"文件过大，{category}类型文件最大允许{details['limit_human']}", details
        
        return True, "文件大小验证通过", details
    
    def validate_file_signature(self, file_content: bytes, declared_type: str) -> Tuple[bool, str, Dict[str, Any]]:
        """验证文件签名"""
        details = {
            'declared_type': declared_type,
            'detected_types': {},
            'signature_match': False,
            'confidence': 0.0
        }
        
        if not self.config.enable_file_signature_check:
            return True, "文件签名检查已禁用", details
        
        try:
            # 检测文件类型
            type_info = self.fingerprint.detect_file_type(file_content)
            details['detected_types'] = type_info
            
            # 检查类型匹配
            detected_type = type_info.get('filetype_guess') or type_info.get('magic_type')
            if detected_type:
                details['signature_match'] = self._is_compatible_mime_type(detected_type, declared_type)
                details['confidence'] = type_info.get('confidence', 0.5)
                
                if not details['signature_match']:
                    return False, f"文件签名不匹配: 声明为{declared_type}，实际为{detected_type}", details
            
            return True, "文件签名验证通过", details
            
        except Exception as e:
            logger.error(f"文件签名验证失败: {e}")
            return True, f"文件签名验证失败: {str(e)}", details
    
    def scan_for_threats(self, file_content: bytes, filename: str) -> Tuple[bool, str, Dict[str, Any]]:
        """威胁扫描"""
        details = {
            'clamav_result': {'clean': True, 'message': '未扫描'},
            'yara_result': {'clean': True, 'matches': []},
            'content_analysis': {},
            'threat_score': 0.0
        }
        
        # 检查缓存
        file_hash = hashlib.sha256(file_content).hexdigest()
        with self.cache_lock:
            if file_hash in self.scan_cache:
                cached_result = self.scan_cache[file_hash]
                if time.time() - cached_result['timestamp'] < 3600:  # 1小时缓存
                    return cached_result['result']
        
        try:
            # ClamAV扫描
            if self.config.enable_virus_scan:
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_file.write(file_content)
                    temp_file.flush()
                    
                    is_clean, message = self.virus_scanner.scan_with_clamav(temp_file.name)
                    details['clamav_result'] = {'clean': is_clean, 'message': message}
                    
                    os.unlink(temp_file.name)
                    
                    if not is_clean:
                        details['threat_score'] += 1.0
            
            # YARA扫描
            if self.config.enable_yara_scan:
                is_clean, matches = self.virus_scanner.scan_with_yara(file_content)
                details['yara_result'] = {'clean': is_clean, 'matches': matches}
                
                if not is_clean:
                    details['threat_score'] += 0.8
            
            # 内容分析
            if self.config.enable_content_analysis:
                category = self.get_file_category(filename)
                if category == 'images':
                    details['content_analysis'] = self.content_analyzer.analyze_image_content(file_content)
                elif category in ['documents', 'code']:
                    try:
                        content_text = file_content.decode('utf-8', errors='ignore')
                        details['content_analysis'] = self.content_analyzer.analyze_text_content(content_text)
                        
                        # 根据可疑模式增加威胁分数
                        suspicious_count = len(details['content_analysis'].get('suspicious_patterns', []))
                        details['threat_score'] += suspicious_count * 0.2
                    except Exception:
                        pass
            
            # 综合判断
            is_safe = details['threat_score'] < 0.5
            message = "文件安全" if is_safe else f"文件可能存在威胁，威胁分数: {details['threat_score']:.2f}"
            
            result = (is_safe, message, details)
            
            # 缓存结果
            with self.cache_lock:
                self.scan_cache[file_hash] = {
                    'result': result,
                    'timestamp': time.time()
                }
                
                # 清理过期缓存
                if len(self.scan_cache) > 1000:
                    current_time = time.time()
                    expired_keys = [k for k, v in self.scan_cache.items() 
                                  if current_time - v['timestamp'] > 3600]
                    for key in expired_keys:
                        del self.scan_cache[key]
            
            return result
            
        except Exception as e:
            logger.error(f"威胁扫描失败: {e}")
            return True, f"威胁扫描失败: {str(e)}", details
    
    def quarantine_file(self, file_content: bytes, filename: str, reason: str) -> str:
        """隔离可疑文件"""
        try:
            if not os.path.exists(self.config.quarantine_path):
                os.makedirs(self.config.quarantine_path)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_hash = hashlib.sha256(file_content).hexdigest()[:8]
            quarantine_filename = f"{timestamp}_{file_hash}_{filename}"
            quarantine_filepath = os.path.join(self.config.quarantine_path, quarantine_filename)
            
            with open(quarantine_filepath, 'wb') as f:
                f.write(file_content)
            
            # 写入隔离信息
            info_file = quarantine_filepath + ".info"
            with open(info_file, 'w') as f:
                f.write(f"Original filename: {filename}\n")
                f.write(f"Quarantine time: {datetime.now()}\n")
                f.write(f"Reason: {reason}\n")
                f.write(f"File hash: {hashlib.sha256(file_content).hexdigest()}\n")
            
            logger.warning(f"文件已隔离: {quarantine_filepath}, 原因: {reason}")
            return quarantine_filepath
            
        except Exception as e:
            logger.error(f"文件隔离失败: {e}")
            return ""
    
    def generate_secure_filename(self, original_filename: str) -> str:
        """生成安全的文件名"""
        name, ext = os.path.splitext(original_filename)
        
        # 清理文件名
        clean_name = re.sub(r'[^\w\u4e00-\u9fa5\-.]', '_', name)
        clean_name = re.sub(r'_{2,}', '_', clean_name)  # 合并多个下划线
        clean_name = clean_name.strip('_')
        
        # 限制长度
        if len(clean_name) > 200:
            clean_name = clean_name[:200]
        
        # 生成时间戳和随机数
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.md5(os.urandom(8)).hexdigest()[:6]
        
        return f"{timestamp}_{random_suffix}_{clean_name}{ext.lower()}"
    
    def _is_compatible_mime_type(self, detected: str, declared: str) -> bool:
        """检查MIME类型兼容性"""
        if detected == declared:
            return True
        
        # 兼容性映射
        compatible_mappings = {
            'text/plain': [
                'text/x-python', 'application/json', 'text/css', 
                'text/html', 'text/javascript', 'application/javascript'
            ],
            'application/octet-stream': [
                'audio/mpeg', 'video/mp4', 'application/zip'
            ],
            'image/jpeg': ['image/jpg'],
            'application/x-rar-compressed': ['application/rar']
        }
        
        return declared in compatible_mappings.get(detected, [])
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"

def validate_file_security(
    filename: str, 
    file_content: bytes, 
    content_type: str,
    config: Optional[FileSecurityConfig] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    增强版文件安全验证
    
    Returns:
        Tuple[bool, str, Dict]: (是否通过验证, 消息, 详细结果)
    """
    validator = EnhancedFileSecurityValidator(config)
    
    validation_result = {
        'filename_validation': {},
        'size_validation': {},
        'signature_validation': {},
        'threat_scan': {},
        'file_info': {},
        'processing_time': 0
    }
    
    start_time = time.time()
    
    try:
        # 1. 文件名验证
        is_valid, message, details = validator.validate_filename(filename)
        validation_result['filename_validation'] = details
        if not is_valid:
            return False, message, validation_result
        
        # 2. 文件大小验证
        is_valid, message, details = validator.validate_file_size(len(file_content), filename)
        validation_result['size_validation'] = details
        if not is_valid:
            return False, message, validation_result
        
        # 3. 文件签名验证
        is_valid, message, details = validator.validate_file_signature(file_content, content_type)
        validation_result['signature_validation'] = details
        if not is_valid:
            return False, message, validation_result
        
        # 4. 威胁扫描
        is_safe, message, details = validator.scan_for_threats(file_content, filename)
        validation_result['threat_scan'] = details
        if not is_safe:
            # 隔离文件
            quarantine_path = validator.quarantine_file(file_content, filename, message)
            validation_result['quarantine_path'] = quarantine_path
            return False, message, validation_result
        
        # 5. 生成文件信息
        hashes = validator.fingerprint.calculate_hashes(file_content)
        validation_result['file_info'] = {
            'original_filename': filename,
            'secure_filename': validator.generate_secure_filename(filename),
            'file_size': len(file_content),
            'file_size_human': validator._format_file_size(len(file_content)),
            'content_type': content_type,
            'category': validator.get_file_category(filename),
            'hashes': hashes,
            'upload_time': datetime.now().isoformat()
        }
        
        validation_result['processing_time'] = time.time() - start_time
        
        return True, "文件验证通过", validation_result
        
    except Exception as e:
        logger.error(f"文件验证异常: {e}")
        validation_result['processing_time'] = time.time() - start_time
        validation_result['error'] = str(e)
        return False, f"文件验证失败: {str(e)}", validation_result

# 配置实例
default_file_security_config = FileSecurityConfig()
