# project/services/security_service.py
"""
安全扫描服务 - 文件病毒扫描和敏感内容检测
从 routers/knowledge/security_scanner.py 重构而来
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
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    pattern_matched: Optional[str] = None
    confidence: float = 0.0
    recommendation: Optional[str] = None

@dataclass
class ScanResult:
    """扫描结果"""
    file_path: str
    scan_type: ScanType
    threat_level: ThreatLevel
    is_safe: bool
    threats: List[SecurityThreat]
    scan_duration: float
    file_size: int
    file_hash: str
    scanned_at: datetime

class SecurityService:
    """安全扫描服务"""
    
    def __init__(self):
        self.virus_patterns = self._load_virus_patterns()
        self.sensitive_patterns = self._load_sensitive_patterns()
        self.malware_signatures = self._load_malware_signatures()
        self.privacy_patterns = self._load_privacy_patterns()

    async def scan_file(self, file_path: str, scan_types: List[ScanType] = None) -> ScanResult:
        """扫描文件"""
        start_time = datetime.now()
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 默认扫描所有类型
        if not scan_types:
            scan_types = list(ScanType)
        
        file_size = os.path.getsize(file_path)
        file_hash = await self._calculate_file_hash(file_path)
        
        all_threats = []
        max_threat_level = ThreatLevel.SAFE
        
        for scan_type in scan_types:
            threats = await self._scan_by_type(file_path, scan_type)
            all_threats.extend(threats)
            
            # 更新最高威胁等级
            for threat in threats:
                if self._threat_level_priority(threat.threat_level) > self._threat_level_priority(max_threat_level):
                    max_threat_level = threat.threat_level
        
        scan_duration = (datetime.now() - start_time).total_seconds()
        
        return ScanResult(
            file_path=file_path,
            scan_type=ScanType.VIRUS,  # 主要扫描类型
            threat_level=max_threat_level,
            is_safe=max_threat_level == ThreatLevel.SAFE,
            threats=all_threats,
            scan_duration=scan_duration,
            file_size=file_size,
            file_hash=file_hash,
            scanned_at=start_time
        )

    async def scan_content(self, content: bytes, filename: str = "unknown", 
                          scan_types: List[ScanType] = None) -> ScanResult:
        """扫描内容"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        try:
            result = await self.scan_file(temp_path, scan_types)
            result.file_path = filename  # 使用原始文件名
            return result
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except:
                pass

    async def scan_url(self, url: str) -> ScanResult:
        """扫描URL"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                return await self.scan_content(
                    response.content, 
                    filename=os.path.basename(urlparse(url).path) or "downloaded_file"
                )
        except Exception as e:
            logger.error(f"扫描URL失败: {e}")
            raise

    async def _scan_by_type(self, file_path: str, scan_type: ScanType) -> List[SecurityThreat]:
        """根据类型扫描文件"""
        if scan_type == ScanType.VIRUS:
            return await self._scan_virus(file_path)
        elif scan_type == ScanType.MALWARE:
            return await self._scan_malware(file_path)
        elif scan_type == ScanType.SENSITIVE_CONTENT:
            return await self._scan_sensitive_content(file_path)
        elif scan_type == ScanType.SUSPICIOUS_PATTERN:
            return await self._scan_suspicious_patterns(file_path)
        elif scan_type == ScanType.PRIVACY_DATA:
            return await self._scan_privacy_data(file_path)
        else:
            return []

    async def _scan_virus(self, file_path: str) -> List[SecurityThreat]:
        """病毒扫描"""
        threats = []
        
        try:
            # 文件类型检查
            file_type = magic.from_file(file_path, mime=True)
            
            # 检查是否为可执行文件
            if self._is_executable_file(file_type):
                threats.append(SecurityThreat(
                    threat_type="executable_file",
                    threat_level=ThreatLevel.MEDIUM,
                    description="检测到可执行文件",
                    file_path=file_path,
                    confidence=0.8,
                    recommendation="请确认文件来源可靠"
                ))
            
            # 文件大小检查
            file_size = os.path.getsize(file_path)
            if file_size > 100 * 1024 * 1024:  # 100MB
                threats.append(SecurityThreat(
                    threat_type="large_file",
                    threat_level=ThreatLevel.LOW,
                    description="文件过大，可能包含恶意内容",
                    file_path=file_path,
                    confidence=0.3,
                    recommendation="建议检查文件内容"
                ))
            
            # 文件名检查
            suspicious_extensions = ['.exe', '.bat', '.cmd', '.scr', '.vbs', '.js']
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in suspicious_extensions:
                threats.append(SecurityThreat(
                    threat_type="suspicious_extension",
                    threat_level=ThreatLevel.HIGH,
                    description=f"检测到可疑文件扩展名: {file_ext}",
                    file_path=file_path,
                    confidence=0.9,
                    recommendation="请勿执行此文件"
                ))
            
        except Exception as e:
            logger.error(f"病毒扫描失败: {e}")
        
        return threats

    async def _scan_malware(self, file_path: str) -> List[SecurityThreat]:
        """恶意软件扫描"""
        threats = []
        
        try:
            # 读取文件内容进行模式匹配
            async with aiofiles.open(file_path, 'rb') as file:
                content = await file.read()
            
            # 检查恶意软件签名
            for signature, info in self.malware_signatures.items():
                if signature.encode() in content:
                    threats.append(SecurityThreat(
                        threat_type="malware_signature",
                        threat_level=ThreatLevel.CRITICAL,
                        description=f"检测到恶意软件签名: {info['name']}",
                        file_path=file_path,
                        pattern_matched=signature,
                        confidence=info['confidence'],
                        recommendation="立即删除此文件"
                    ))
            
        except Exception as e:
            logger.error(f"恶意软件扫描失败: {e}")
        
        return threats

    async def _scan_sensitive_content(self, file_path: str) -> List[SecurityThreat]:
        """敏感内容扫描"""
        threats = []
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = await file.read()
                lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                for pattern_name, pattern_info in self.sensitive_patterns.items():
                    if re.search(pattern_info['pattern'], line, re.IGNORECASE):
                        threats.append(SecurityThreat(
                            threat_type="sensitive_content",
                            threat_level=ThreatLevel.HIGH,
                            description=f"检测到敏感内容: {pattern_info['description']}",
                            file_path=file_path,
                            line_number=line_num,
                            pattern_matched=pattern_name,
                            confidence=pattern_info['confidence'],
                            recommendation="请检查并移除敏感信息"
                        ))
            
        except Exception as e:
            logger.error(f"敏感内容扫描失败: {e}")
        
        return threats

    async def _scan_suspicious_patterns(self, file_path: str) -> List[SecurityThreat]:
        """可疑模式扫描"""
        threats = []
        
        try:
            # 检查文件是否为压缩包
            if self._is_archive_file(file_path):
                archive_threats = await self._scan_archive_file(file_path)
                threats.extend(archive_threats)
            
            # 检查文件是否为图片
            if self._is_image_file(file_path):
                image_threats = await self._scan_image_file(file_path)
                threats.extend(image_threats)
            
        except Exception as e:
            logger.error(f"可疑模式扫描失败: {e}")
        
        return threats

    async def _scan_privacy_data(self, file_path: str) -> List[SecurityThreat]:
        """隐私数据扫描"""
        threats = []
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = await file.read()
                lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                for pattern_name, pattern_info in self.privacy_patterns.items():
                    matches = re.finditer(pattern_info['pattern'], line)
                    for match in matches:
                        threats.append(SecurityThreat(
                            threat_type="privacy_data",
                            threat_level=ThreatLevel.MEDIUM,
                            description=f"检测到隐私数据: {pattern_info['description']}",
                            file_path=file_path,
                            line_number=line_num,
                            pattern_matched=match.group(),
                            confidence=pattern_info['confidence'],
                            recommendation="请确认是否需要保护此隐私信息"
                        ))
            
        except Exception as e:
            logger.error(f"隐私数据扫描失败: {e}")
        
        return threats

    async def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希"""
        hash_md5 = hashlib.md5()
        async with aiofiles.open(file_path, 'rb') as file:
            while chunk := await file.read(8192):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _load_virus_patterns(self) -> Dict[str, Any]:
        """加载病毒模式"""
        return {
            "suspicious_command": {
                "pattern": r"(rm\s+-rf|del\s+/f|format\s+c:)",
                "description": "可疑系统命令",
                "confidence": 0.7
            },
            "shell_injection": {
                "pattern": r"(\$\(.*\)|`.*`|eval\s*\()",
                "description": "shell注入模式",
                "confidence": 0.8
            }
        }

    def _load_sensitive_patterns(self) -> Dict[str, Any]:
        """加载敏感内容模式"""
        return {
            "password": {
                "pattern": r"(password|pwd|passwd)\s*[:=]\s*['\"]?[\w!@#$%^&*()]+['\"]?",
                "description": "密码信息",
                "confidence": 0.9
            },
            "api_key": {
                "pattern": r"(api[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[\w-]+['\"]?",
                "description": "API密钥",
                "confidence": 0.9
            },
            "credit_card": {
                "pattern": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
                "description": "信用卡号",
                "confidence": 0.8
            }
        }

    def _load_malware_signatures(self) -> Dict[str, Any]:
        """加载恶意软件签名"""
        return {
            "evil_script": {
                "name": "恶意脚本",
                "confidence": 0.95
            },
            "trojan_horse": {
                "name": "木马程序",
                "confidence": 0.9
            }
        }

    def _load_privacy_patterns(self) -> Dict[str, Any]:
        """加载隐私数据模式"""
        return {
            "email": {
                "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                "description": "电子邮件地址",
                "confidence": 0.9
            },
            "phone": {
                "pattern": r"\b(?:\+86[-\s]?)?1[3-9]\d{9}\b",
                "description": "手机号码",
                "confidence": 0.8
            },
            "id_card": {
                "pattern": r"\b\d{17}[\dXx]\b",
                "description": "身份证号",
                "confidence": 0.95
            }
        }

    def _is_executable_file(self, file_type: str) -> bool:
        """检查是否为可执行文件"""
        executable_types = [
            'application/x-executable',
            'application/x-msdos-program',
            'application/x-msdownload'
        ]
        return file_type in executable_types

    def _is_archive_file(self, file_path: str) -> bool:
        """检查是否为压缩文件"""
        archive_extensions = ['.zip', '.rar', '.7z', '.tar', '.gz']
        return any(file_path.lower().endswith(ext) for ext in archive_extensions)

    def _is_image_file(self, file_path: str) -> bool:
        """检查是否为图片文件"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        return any(file_path.lower().endswith(ext) for ext in image_extensions)

    async def _scan_archive_file(self, file_path: str) -> List[SecurityThreat]:
        """扫描压缩文件"""
        threats = []
        
        try:
            if file_path.lower().endswith('.zip'):
                with zipfile.ZipFile(file_path, 'r') as archive:
                    file_list = archive.namelist()
            elif file_path.lower().endswith('.7z'):
                with py7zr.SevenZipFile(file_path, mode='r') as archive:
                    file_list = archive.getnames()
            else:
                return threats
            
            # 检查压缩包内的可疑文件
            for filename in file_list:
                if any(filename.lower().endswith(ext) for ext in ['.exe', '.bat', '.cmd']):
                    threats.append(SecurityThreat(
                        threat_type="suspicious_archive_content",
                        threat_level=ThreatLevel.HIGH,
                        description=f"压缩包内包含可疑文件: {filename}",
                        file_path=file_path,
                        confidence=0.8,
                        recommendation="请谨慎解压此文件"
                    ))
            
        except Exception as e:
            logger.error(f"扫描压缩文件失败: {e}")
        
        return threats

    async def _scan_image_file(self, file_path: str) -> List[SecurityThreat]:
        """扫描图片文件"""
        threats = []
        
        try:
            with Image.open(file_path) as img:
                # 检查图片尺寸是否异常
                width, height = img.size
                if width > 10000 or height > 10000:
                    threats.append(SecurityThreat(
                        threat_type="suspicious_image_size",
                        threat_level=ThreatLevel.LOW,
                        description="图片尺寸异常大",
                        file_path=file_path,
                        confidence=0.5,
                        recommendation="请检查图片是否正常"
                    ))
                
                # 检查图片是否包含EXIF数据
                if hasattr(img, '_getexif') and img._getexif():
                    threats.append(SecurityThreat(
                        threat_type="image_exif_data",
                        threat_level=ThreatLevel.LOW,
                        description="图片包含EXIF数据，可能泄露位置信息",
                        file_path=file_path,
                        confidence=0.7,
                        recommendation="建议清除EXIF数据"
                    ))
            
        except Exception as e:
            logger.error(f"扫描图片文件失败: {e}")
        
        return threats

    def _threat_level_priority(self, level: ThreatLevel) -> int:
        """威胁等级优先级"""
        return {
            ThreatLevel.SAFE: 0,
            ThreatLevel.LOW: 1,
            ThreatLevel.MEDIUM: 2,
            ThreatLevel.HIGH: 3,
            ThreatLevel.CRITICAL: 4
        }.get(level, 0)

# 创建全局实例
security_service = SecurityService()

# 便捷函数
async def scan_file_security(file_path: str, scan_types: List[ScanType] = None) -> ScanResult:
    """扫描文件安全性"""
    return await security_service.scan_file(file_path, scan_types)

async def scan_content_security(content: bytes, filename: str = "unknown", 
                               scan_types: List[ScanType] = None) -> ScanResult:
    """扫描内容安全性"""
    return await security_service.scan_content(content, filename, scan_types)

async def scan_url_security(url: str) -> ScanResult:
    """扫描URL安全性"""
    return await security_service.scan_url(url)
