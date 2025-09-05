# project/routers/knowledge/security_scanner.py
"""
安全扫描模块 - 文件病毒扫描和敏感内容检测
提供多层次安全防护，保护系统和用户数据安全
"""

import asyncio
import hashlib
import re
import os
import tempfile
import subprocess
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
import aiofiles
import httpx
import magic
from urllib.parse import urlparse
import yara
import zipfile
import py7zr
import rarfile
from PIL import Image
import io

logger = logging.getLogger(__name__)

class ThreatLevel(str, Enum):
    """威胁等级"""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ScanType(str, Enum):
    """扫描类型"""
    VIRUS = "virus"
    MALWARE = "malware"
    SENSITIVE_CONTENT = "sensitive_content"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    PRIVACY_DATA = "privacy_data"

@dataclass
class SecurityThreat:
    """安全威胁信息"""
    threat_type: str
    threat_level: ThreatLevel
    description: str
    details: Dict[str, Any]
    confidence: float  # 置信度 0-1
    location: str      # 威胁位置
    timestamp: datetime
    
class VirusScanner:
    """病毒扫描器"""
    
    def __init__(self):
        self.clamav_available = self._check_clamav()
        self.signatures_updated = datetime.now()
        self.quarantine_dir = "/tmp/quarantine"
        os.makedirs(self.quarantine_dir, exist_ok=True)
        
    def _check_clamav(self) -> bool:
        """检查ClamAV是否可用"""
        try:
            result = subprocess.run(['clamscan', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
            
    async def scan_file(self, file_path: str) -> Dict[str, Any]:
        """扫描文件病毒"""
        threats = []
        
        # 1. 文件哈希检查
        file_hash = await self._calculate_file_hash(file_path)
        hash_threat = await self._check_hash_reputation(file_hash)
        if hash_threat:
            threats.append(hash_threat)
            
        # 2. ClamAV扫描
        if self.clamav_available:
            clamav_threat = await self._scan_with_clamav(file_path)
            if clamav_threat:
                threats.append(clamav_threat)
                
        # 3. YARA规则扫描
        yara_threats = await self._scan_with_yara(file_path)
        threats.extend(yara_threats)
        
        # 4. 文件类型验证
        type_threat = await self._validate_file_type(file_path)
        if type_threat:
            threats.append(type_threat)
            
        # 5. 压缩文件扫描
        if await self._is_archive_file(file_path):
            archive_threats = await self._scan_archive(file_path)
            threats.extend(archive_threats)
            
        return {
            "file_path": file_path,
            "file_hash": file_hash,
            "threats": [threat.__dict__ for threat in threats],
            "threat_level": self._get_max_threat_level(threats),
            "scan_time": datetime.now().isoformat(),
            "is_safe": len(threats) == 0
        }
        
    async def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希"""
        hash_sha256 = hashlib.sha256()
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(8192):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
        
    async def _check_hash_reputation(self, file_hash: str) -> Optional[SecurityThreat]:
        """检查文件哈希声誉"""
        # 这里可以集成VirusTotal API或其他威胁情报平台
        # 示例实现
        known_malicious_hashes = {
            # 示例恶意文件哈希
            "d41d8cd98f00b204e9800998ecf8427e": "空文件测试",
        }
        
        if file_hash in known_malicious_hashes:
            return SecurityThreat(
                threat_type=ScanType.MALWARE,
                threat_level=ThreatLevel.HIGH,
                description="已知恶意文件哈希",
                details={"hash": file_hash, "source": "threat_intelligence"},
                confidence=0.95,
                location="file_hash",
                timestamp=datetime.now()
            )
        return None
        
    async def _scan_with_clamav(self, file_path: str) -> Optional[SecurityThreat]:
        """使用ClamAV扫描"""
        try:
            process = await asyncio.create_subprocess_exec(
                'clamscan', '--no-summary', file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            output = stdout.decode('utf-8')
            
            if "FOUND" in output:
                virus_name = output.split(":")[1].strip().replace(" FOUND", "")
                return SecurityThreat(
                    threat_type=ScanType.VIRUS,
                    threat_level=ThreatLevel.CRITICAL,
                    description=f"病毒检测: {virus_name}",
                    details={"virus_name": virus_name, "scanner": "clamav"},
                    confidence=0.9,
                    location="file_content",
                    timestamp=datetime.now()
                )
                
        except Exception as e:
            logger.error(f"ClamAV扫描失败: {e}")
            
        return None
        
    async def _scan_with_yara(self, file_path: str) -> List[SecurityThreat]:
        """使用YARA规则扫描"""
        threats = []
        
        try:
            # 加载YARA规则
            rules_dir = os.path.join(os.path.dirname(__file__), "../../yara/rules")
            if not os.path.exists(rules_dir):
                return threats
                
            for rule_file in os.listdir(rules_dir):
                if rule_file.endswith('.yar') or rule_file.endswith('.yara'):
                    rule_path = os.path.join(rules_dir, rule_file)
                    try:
                        rules = yara.compile(rule_path)
                        matches = rules.match(file_path)
                        
                        for match in matches:
                            threat = SecurityThreat(
                                threat_type=ScanType.MALWARE,
                                threat_level=self._get_yara_threat_level(match.rule),
                                description=f"YARA规则匹配: {match.rule}",
                                details={
                                    "rule": match.rule,
                                    "tags": match.tags,
                                    "strings": [str(s) for s in match.strings]
                                },
                                confidence=0.8,
                                location="file_content",
                                timestamp=datetime.now()
                            )
                            threats.append(threat)
                            
                    except Exception as e:
                        logger.warning(f"YARA规则 {rule_file} 加载失败: {e}")
                        
        except Exception as e:
            logger.error(f"YARA扫描失败: {e}")
            
        return threats
        
    def _get_yara_threat_level(self, rule_name: str) -> ThreatLevel:
        """根据YARA规则名称确定威胁等级"""
        rule_lower = rule_name.lower()
        
        if any(keyword in rule_lower for keyword in ['ransomware', 'trojan', 'backdoor']):
            return ThreatLevel.CRITICAL
        elif any(keyword in rule_lower for keyword in ['malware', 'virus', 'worm']):
            return ThreatLevel.HIGH
        elif any(keyword in rule_lower for keyword in ['suspicious', 'packer', 'obfuscated']):
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW
            
    async def _validate_file_type(self, file_path: str) -> Optional[SecurityThreat]:
        """验证文件类型"""
        try:
            # 使用python-magic检测真实文件类型
            file_mime = magic.from_file(file_path, mime=True)
            file_extension = os.path.splitext(file_path)[1].lower()
            
            # 检查文件类型伪装
            expected_mimes = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.mp4': 'video/mp4',
                '.avi': 'video/x-msvideo',
                '.exe': 'application/x-executable',
                '.zip': 'application/zip'
            }
            
            expected_mime = expected_mimes.get(file_extension)
            if expected_mime and not file_mime.startswith(expected_mime.split('/')[0]):
                return SecurityThreat(
                    threat_type=ScanType.SUSPICIOUS_PATTERN,
                    threat_level=ThreatLevel.MEDIUM,
                    description="文件类型伪装",
                    details={
                        "expected_mime": expected_mime,
                        "actual_mime": file_mime,
                        "extension": file_extension
                    },
                    confidence=0.7,
                    location="file_header",
                    timestamp=datetime.now()
                )
                
        except Exception as e:
            logger.error(f"文件类型验证失败: {e}")
            
        return None
        
    async def _is_archive_file(self, file_path: str) -> bool:
        """检查是否为压缩文件"""
        extensions = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2']
        return any(file_path.lower().endswith(ext) for ext in extensions)
        
    async def _scan_archive(self, file_path: str) -> List[SecurityThreat]:
        """扫描压缩文件"""
        threats = []
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 解压文件
                if file_path.lower().endswith('.zip'):
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)
                elif file_path.lower().endswith('.7z'):
                    with py7zr.SevenZipFile(file_path, mode='r') as z:
                        z.extractall(temp_dir)
                elif file_path.lower().endswith('.rar'):
                    with rarfile.RarFile(file_path) as rar_ref:
                        rar_ref.extractall(temp_dir)
                        
                # 递归扫描解压后的文件
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_full_path = os.path.join(root, file)
                        scan_result = await self.scan_file(file_full_path)
                        
                        if not scan_result['is_safe']:
                            for threat_data in scan_result['threats']:
                                threat = SecurityThreat(**threat_data)
                                threat.location = f"archive:{os.path.relpath(file_full_path, temp_dir)}"
                                threats.append(threat)
                                
        except Exception as e:
            logger.error(f"压缩文件扫描失败: {e}")
            threat = SecurityThreat(
                threat_type=ScanType.SUSPICIOUS_PATTERN,
                threat_level=ThreatLevel.MEDIUM,
                description="压缩文件解析失败",
                details={"error": str(e)},
                confidence=0.6,
                location="archive_structure",
                timestamp=datetime.now()
            )
            threats.append(threat)
            
        return threats
        
    def _get_max_threat_level(self, threats: List[SecurityThreat]) -> ThreatLevel:
        """获取最高威胁等级"""
        if not threats:
            return ThreatLevel.SAFE
            
        level_order = [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM, 
                      ThreatLevel.HIGH, ThreatLevel.CRITICAL]
        
        max_level = ThreatLevel.SAFE
        for threat in threats:
            if level_order.index(threat.threat_level) > level_order.index(max_level):
                max_level = threat.threat_level
                
        return max_level
        
    async def quarantine_file(self, file_path: str, threat_info: Dict[str, Any]) -> str:
        """隔离威胁文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.basename(file_path)
        quarantine_path = os.path.join(
            self.quarantine_dir, 
            f"{timestamp}_{filename}.quarantine"
        )
        
        # 移动文件到隔离目录
        os.rename(file_path, quarantine_path)
        
        # 记录隔离信息
        info_path = quarantine_path + ".info"
        async with aiofiles.open(info_path, 'w') as f:
            await f.write(str(threat_info))
            
        logger.warning(f"文件已隔离: {file_path} -> {quarantine_path}")
        return quarantine_path

class ContentScanner:
    """内容安全扫描器"""
    
    def __init__(self):
        self.sensitive_patterns = self._load_sensitive_patterns()
        self.privacy_patterns = self._load_privacy_patterns()
        
    def _load_sensitive_patterns(self) -> Dict[str, List[re.Pattern]]:
        """加载敏感内容模式"""
        return {
            "政治敏感": [
                re.compile(r'政治敏感词1|政治敏感词2', re.IGNORECASE),
                # 添加更多政治敏感词模式
            ],
            "暴力内容": [
                re.compile(r'暴力|恐怖|血腥', re.IGNORECASE),
                re.compile(r'杀害|伤害|攻击', re.IGNORECASE),
            ],
            "色情内容": [
                re.compile(r'色情|淫秽|性行为', re.IGNORECASE),
                # 添加更多色情内容模式
            ],
            "违法内容": [
                re.compile(r'毒品|赌博|洗钱', re.IGNORECASE),
                re.compile(r'诈骗|欺诈|非法', re.IGNORECASE),
            ]
        }
        
    def _load_privacy_patterns(self) -> Dict[str, re.Pattern]:
        """加载隐私数据模式"""
        return {
            "身份证号": re.compile(r'\b\d{15}|\d{18}\b'),
            "手机号": re.compile(r'\b1[3-9]\d{9}\b'),
            "邮箱": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            "银行卡号": re.compile(r'\b\d{16}|\d{19}\b'),
            "信用卡号": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
            "IP地址": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
            "社会保障号": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        }
        
    async def scan_text_content(self, text: str, filename: str = "") -> Dict[str, Any]:
        """扫描文本内容"""
        threats = []
        
        # 1. 敏感内容检测
        for category, patterns in self.sensitive_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    threat = SecurityThreat(
                        threat_type=ScanType.SENSITIVE_CONTENT,
                        threat_level=ThreatLevel.HIGH,
                        description=f"检测到{category}内容",
                        details={
                            "category": category,
                            "matches": matches[:5],  # 只记录前5个匹配
                            "count": len(matches)
                        },
                        confidence=0.8,
                        location="text_content",
                        timestamp=datetime.now()
                    )
                    threats.append(threat)
                    
        # 2. 隐私数据检测
        privacy_data = {}
        for data_type, pattern in self.privacy_patterns.items():
            matches = pattern.findall(text)
            if matches:
                privacy_data[data_type] = len(matches)
                
                threat = SecurityThreat(
                    threat_type=ScanType.PRIVACY_DATA,
                    threat_level=ThreatLevel.MEDIUM,
                    description=f"检测到{data_type}",
                    details={
                        "data_type": data_type,
                        "count": len(matches)
                    },
                    confidence=0.7,
                    location="text_content",
                    timestamp=datetime.now()
                )
                threats.append(threat)
                
        # 3. 可疑链接检测
        url_threats = await self._scan_urls_in_text(text)
        threats.extend(url_threats)
        
        return {
            "filename": filename,
            "threats": [threat.__dict__ for threat in threats],
            "privacy_data": privacy_data,
            "threat_level": self._get_max_threat_level(threats),
            "scan_time": datetime.now().isoformat(),
            "is_safe": len(threats) == 0
        }
        
    async def _scan_urls_in_text(self, text: str) -> List[SecurityThreat]:
        """扫描文本中的可疑URL"""
        threats = []
        
        # URL模式
        url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        )
        
        urls = url_pattern.findall(text)
        
        for url in urls:
            # 检查域名黑名单
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            # 可疑域名特征
            suspicious_patterns = [
                r'\.tk$',  # 免费域名
                r'\.ml$',  # 免费域名
                r'\d+\.\d+\.\d+\.\d+',  # IP地址
                r'[a-z]{20,}',  # 过长随机字符串
                r'bit\.ly|tinyurl|t\.co',  # 短链接服务
            ]
            
            for pattern in suspicious_patterns:
                if re.search(pattern, domain):
                    threat = SecurityThreat(
                        threat_type=ScanType.SUSPICIOUS_PATTERN,
                        threat_level=ThreatLevel.MEDIUM,
                        description="可疑URL链接",
                        details={
                            "url": url,
                            "domain": domain,
                            "pattern": pattern
                        },
                        confidence=0.6,
                        location="text_content",
                        timestamp=datetime.now()
                    )
                    threats.append(threat)
                    break
                    
        return threats
        
    def _get_max_threat_level(self, threats: List[SecurityThreat]) -> ThreatLevel:
        """获取最高威胁等级"""
        if not threats:
            return ThreatLevel.SAFE
            
        level_order = [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM, 
                      ThreatLevel.HIGH, ThreatLevel.CRITICAL]
        
        max_level = ThreatLevel.SAFE
        for threat in threats:
            if level_order.index(threat.threat_level) > level_order.index(max_level):
                max_level = threat.threat_level
                
        return max_level

class ImageScanner:
    """图像内容扫描器"""
    
    def __init__(self):
        self.nsfw_model_available = self._check_nsfw_model()
        
    def _check_nsfw_model(self) -> bool:
        """检查NSFW检测模型是否可用"""
        try:
            import tensorflow as tf
            # 这里可以加载预训练的NSFW检测模型
            return True
        except ImportError:
            return False
            
    async def scan_image(self, image_path: str) -> Dict[str, Any]:
        """扫描图像内容"""
        threats = []
        
        try:
            with Image.open(image_path) as img:
                # 1. 基础图像信息检查
                basic_threats = await self._check_basic_image_info(img, image_path)
                threats.extend(basic_threats)
                
                # 2. NSFW内容检测
                if self.nsfw_model_available:
                    nsfw_threat = await self._detect_nsfw_content(img)
                    if nsfw_threat:
                        threats.append(nsfw_threat)
                        
                # 3. 隐藏内容检测（隐写术）
                steganography_threat = await self._detect_steganography(img)
                if steganography_threat:
                    threats.append(steganography_threat)
                    
        except Exception as e:
            threat = SecurityThreat(
                threat_type=ScanType.SUSPICIOUS_PATTERN,
                threat_level=ThreatLevel.LOW,
                description="图像文件损坏或格式错误",
                details={"error": str(e)},
                confidence=0.5,
                location="image_file",
                timestamp=datetime.now()
            )
            threats.append(threat)
            
        return {
            "image_path": image_path,
            "threats": [threat.__dict__ for threat in threats],
            "threat_level": self._get_max_threat_level(threats),
            "scan_time": datetime.now().isoformat(),
            "is_safe": len(threats) == 0
        }
        
    async def _check_basic_image_info(self, img: Image.Image, image_path: str) -> List[SecurityThreat]:
        """检查基础图像信息"""
        threats = []
        
        # 检查图像尺寸
        width, height = img.size
        if width > 10000 or height > 10000:
            threat = SecurityThreat(
                threat_type=ScanType.SUSPICIOUS_PATTERN,
                threat_level=ThreatLevel.LOW,
                description="异常大尺寸图像",
                details={"width": width, "height": height},
                confidence=0.6,
                location="image_metadata",
                timestamp=datetime.now()
            )
            threats.append(threat)
            
        # 检查EXIF数据
        if hasattr(img, '_getexif') and img._getexif():
            exif_data = img._getexif()
            # 检查是否包含GPS信息
            if any(tag in exif_data for tag in [34853, 'GPSInfo']):
                threat = SecurityThreat(
                    threat_type=ScanType.PRIVACY_DATA,
                    threat_level=ThreatLevel.MEDIUM,
                    description="图像包含GPS位置信息",
                    details={"has_gps": True},
                    confidence=0.9,
                    location="image_exif",
                    timestamp=datetime.now()
                )
                threats.append(threat)
                
        return threats
        
    async def _detect_nsfw_content(self, img: Image.Image) -> Optional[SecurityThreat]:
        """检测NSFW内容"""
        # 这里可以集成NSFW检测模型
        # 示例实现
        try:
            # 简单的像素分析示例
            # 实际应用中应该使用专门的NSFW检测模型
            img_array = list(img.getdata())
            
            # 这里只是示例，实际需要更复杂的算法
            # 可以集成开源的NSFW检测模型如：
            # - Yahoo's open_nsfw
            # - NSFW JS
            # - 百度、腾讯的内容审核API
            
            return None  # 暂不实现具体检测逻辑
            
        except Exception as e:
            logger.error(f"NSFW检测失败: {e}")
            return None
            
    async def _detect_steganography(self, img: Image.Image) -> Optional[SecurityThreat]:
        """检测隐写术"""
        try:
            # 简单的LSB隐写检测
            # 检查最低位是否有规律
            if img.mode == 'RGB':
                pixels = list(img.getdata())
                lsb_data = []
                
                for pixel in pixels[:1000]:  # 只检查前1000个像素
                    for channel in pixel:
                        lsb_data.append(channel & 1)
                        
                # 简单的熵分析
                if len(set(lsb_data)) > 1:
                    # 计算0和1的分布
                    ones = sum(lsb_data)
                    zeros = len(lsb_data) - ones
                    ratio = ones / zeros if zeros > 0 else float('inf')
                    
                    # 如果分布过于均匀，可能包含隐藏数据
                    if 0.4 < ratio < 2.5:
                        return SecurityThreat(
                            threat_type=ScanType.SUSPICIOUS_PATTERN,
                            threat_level=ThreatLevel.MEDIUM,
                            description="可能包含隐写内容",
                            details={"lsb_ratio": ratio},
                            confidence=0.5,
                            location="image_pixels",
                            timestamp=datetime.now()
                        )
                        
        except Exception as e:
            logger.error(f"隐写检测失败: {e}")
            
        return None
        
    def _get_max_threat_level(self, threats: List[SecurityThreat]) -> ThreatLevel:
        """获取最高威胁等级"""
        if not threats:
            return ThreatLevel.SAFE
            
        level_order = [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM, 
                      ThreatLevel.HIGH, ThreatLevel.CRITICAL]
        
        max_level = ThreatLevel.SAFE
        for threat in threats:
            if level_order.index(threat.threat_level) > level_order.index(max_level):
                max_level = threat.threat_level
                
        return max_level

class ComprehensiveSecurityScanner:
    """综合安全扫描器"""
    
    def __init__(self):
        self.virus_scanner = VirusScanner()
        self.content_scanner = ContentScanner()
        self.image_scanner = ImageScanner()
        self.scan_history = {}
        
    async def scan_file_comprehensive(self, file_path: str, content: bytes = None) -> Dict[str, Any]:
        """综合扫描文件"""
        scan_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        results = {
            "scan_id": scan_id,
            "file_path": file_path,
            "scan_start": start_time.isoformat(),
            "virus_scan": None,
            "content_scan": None,
            "image_scan": None,
            "overall_threat_level": ThreatLevel.SAFE,
            "is_safe": True,
            "recommendations": []
        }
        
        try:
            # 1. 病毒扫描
            results["virus_scan"] = await self.virus_scanner.scan_file(file_path)
            
            # 2. 内容扫描（如果是文本文件）
            if self._is_text_file(file_path):
                if content:
                    text_content = content.decode('utf-8', errors='ignore')
                else:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        text_content = await f.read()
                        
                results["content_scan"] = await self.content_scanner.scan_text_content(
                    text_content, os.path.basename(file_path)
                )
                
            # 3. 图像扫描（如果是图像文件）
            if self._is_image_file(file_path):
                results["image_scan"] = await self.image_scanner.scan_image(file_path)
                
            # 4. 综合评估
            all_threats = []
            
            if results["virus_scan"] and not results["virus_scan"]["is_safe"]:
                all_threats.extend([SecurityThreat(**t) for t in results["virus_scan"]["threats"]])
                
            if results["content_scan"] and not results["content_scan"]["is_safe"]:
                all_threats.extend([SecurityThreat(**t) for t in results["content_scan"]["threats"]])
                
            if results["image_scan"] and not results["image_scan"]["is_safe"]:
                all_threats.extend([SecurityThreat(**t) for t in results["image_scan"]["threats"]])
                
            # 确定整体威胁等级
            if all_threats:
                results["overall_threat_level"] = self._get_max_threat_level(all_threats)
                results["is_safe"] = False
                
                # 生成建议
                results["recommendations"] = self._generate_recommendations(all_threats)
                
                # 如果威胁等级过高，自动隔离
                if results["overall_threat_level"] in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
                    quarantine_path = await self.virus_scanner.quarantine_file(
                        file_path, results
                    )
                    results["quarantined"] = True
                    results["quarantine_path"] = quarantine_path
                    
        except Exception as e:
            logger.error(f"安全扫描失败: {e}")
            results["error"] = str(e)
            
        finally:
            results["scan_duration"] = (datetime.now() - start_time).total_seconds()
            results["scan_end"] = datetime.now().isoformat()
            
            # 保存扫描历史
            self.scan_history[scan_id] = results
            
        return results
        
    def _is_text_file(self, file_path: str) -> bool:
        """判断是否为文本文件"""
        text_extensions = ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv']
        return any(file_path.lower().endswith(ext) for ext in text_extensions)
        
    def _is_image_file(self, file_path: str) -> bool:
        """判断是否为图像文件"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
        return any(file_path.lower().endswith(ext) for ext in image_extensions)
        
    def _get_max_threat_level(self, threats: List[SecurityThreat]) -> ThreatLevel:
        """获取最高威胁等级"""
        if not threats:
            return ThreatLevel.SAFE
            
        level_order = [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM, 
                      ThreatLevel.HIGH, ThreatLevel.CRITICAL]
        
        max_level = ThreatLevel.SAFE
        for threat in threats:
            if level_order.index(threat.threat_level) > level_order.index(max_level):
                max_level = threat.threat_level
                
        return max_level
        
    def _generate_recommendations(self, threats: List[SecurityThreat]) -> List[str]:
        """生成安全建议"""
        recommendations = []
        
        threat_types = set(threat.threat_type for threat in threats)
        
        if ScanType.VIRUS in threat_types or ScanType.MALWARE in threat_types:
            recommendations.append("立即删除或隔离该文件，运行全系统病毒扫描")
            
        if ScanType.SENSITIVE_CONTENT in threat_types:
            recommendations.append("审查文件内容，删除敏感信息")
            
        if ScanType.PRIVACY_DATA in threat_types:
            recommendations.append("清除个人隐私数据，或限制文件访问权限")
            
        if ScanType.SUSPICIOUS_PATTERN in threat_types:
            recommendations.append("进一步检查文件来源和内容，谨慎处理")
            
        return recommendations
        
    async def get_scan_history(self, scan_id: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """获取扫描历史"""
        if scan_id:
            return self.scan_history.get(scan_id)
        else:
            return list(self.scan_history.values())

# 全局安全扫描器实例
security_scanner = None

def get_security_scanner() -> ComprehensiveSecurityScanner:
    """获取安全扫描器实例"""
    global security_scanner
    if security_scanner is None:
        security_scanner = ComprehensiveSecurityScanner()
    return security_scanner
