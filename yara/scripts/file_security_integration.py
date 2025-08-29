#!/usr/bin/env python3
"""
文件安全验证模块 - 集成YARA扫描
为现有项目添加文件上传安全检查功能
"""

import os
import tempfile
from typing import Dict, Any, Optional, List
from fastapi import UploadFile, HTTPException
from yara_scanner import YARAFileScanner, ScanResult
import logging


class FileSecurityValidator:
    """文件安全验证器"""
    
    def __init__(self):
        """初始化文件安全验证器"""
        self.yara_scanner = YARAFileScanner()
        self.logger = logging.getLogger(__name__)
        
        # 安全配置
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.allowed_mime_types = {
            'image/jpeg', 'image/png', 'image/gif', 'image/webp',
            'application/pdf', 'text/plain', 'application/json',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        }
        
        # 危险文件扩展名
        self.dangerous_extensions = {
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js',
            '.jar', '.class', '.msi', '.dll', '.sys', '.ps1', '.sh'
        }
    
    async def validate_upload_file(self, 
                                 file: UploadFile, 
                                 strict_mode: bool = True) -> Dict[str, Any]:
        """
        验证上传文件的安全性
        
        Args:
            file: FastAPI上传文件对象
            strict_mode: 严格模式，是否进行深度YARA扫描
            
        Returns:
            Dict: 验证结果
            
        Raises:
            HTTPException: 如果文件不安全
        """
        result = {
            'is_safe': False,
            'filename': file.filename,
            'size': 0,
            'mime_type': file.content_type,
            'checks': {
                'size_check': False,
                'extension_check': False,
                'mime_type_check': False,
                'yara_scan': False
            },
            'yara_result': None,
            'threats': [],
            'warnings': []
        }
        
        try:
            # 读取文件内容
            content = await file.read()
            result['size'] = len(content)
            
            # 重置文件指针
            await file.seek(0)
            
            # 1. 检查文件大小
            if len(content) > self.max_file_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件大小超过限制 ({self.max_file_size} bytes)"
                )
            result['checks']['size_check'] = True
            
            # 2. 检查文件扩展名
            if file.filename:
                file_ext = os.path.splitext(file.filename.lower())[1]
                if file_ext in self.dangerous_extensions:
                    raise HTTPException(
                        status_code=400,
                        detail=f"不允许的文件类型: {file_ext}"
                    )
            result['checks']['extension_check'] = True
            
            # 3. 检查MIME类型
            if strict_mode and file.content_type:
                if file.content_type not in self.allowed_mime_types:
                    result['warnings'].append(f"未知的MIME类型: {file.content_type}")
            result['checks']['mime_type_check'] = True
            
            # 4. YARA扫描（如果启用）
            if self.yara_scanner.enabled and strict_mode:
                yara_result = await self._scan_file_content(content, file.filename)
                result['yara_result'] = yara_result
                
                if yara_result and not yara_result.is_safe:
                    # 根据威胁级别决定是否拒绝
                    if yara_result.threat_level in ['HIGH', 'CRITICAL']:
                        raise HTTPException(
                            status_code=400,
                            detail=f"文件包含恶意内容 (威胁级别: {yara_result.threat_level})"
                        )
                    elif yara_result.threat_level == 'MEDIUM':
                        result['warnings'].append(f"文件可能包含可疑内容 (威胁级别: {yara_result.threat_level})")
                    
                    # 收集威胁信息
                    for match in yara_result.matches:
                        result['threats'].append({
                            'rule': match['rule'],
                            'description': match['meta'].get('description', ''),
                            'threat_level': yara_result.threat_level
                        })
                        
            result['checks']['yara_scan'] = True
            result['is_safe'] = True
            
            self.logger.info(f"文件验证通过: {file.filename}")
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"文件验证失败: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"文件验证过程中发生错误: {str(e)}"
            )
    
    async def _scan_file_content(self, content: bytes, filename: str) -> Optional[ScanResult]:
        """
        扫描文件内容
        
        Args:
            content: 文件内容
            filename: 文件名
            
        Returns:
            ScanResult: YARA扫描结果
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            try:
                # 使用YARA扫描临时文件
                result = self.yara_scanner.scan_file(temp_file_path)
                return result
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                    
        except Exception as e:
            self.logger.error(f"YARA扫描失败: {e}")
            return None
    
    def get_file_risk_assessment(self, scan_result: ScanResult) -> Dict[str, Any]:
        """
        获取文件风险评估
        
        Args:
            scan_result: YARA扫描结果
            
        Returns:
            Dict: 风险评估报告
        """
        if not scan_result or scan_result.is_safe:
            return {
                'risk_level': 'LOW',
                'risk_score': 0,
                'recommendations': ['文件看起来是安全的'],
                'allow_upload': True
            }
        
        risk_score = 0
        recommendations = []
        
        # 根据威胁级别计算风险分数
        threat_scores = {
            'LOW': 1,
            'MEDIUM': 3,
            'HIGH': 7,
            'CRITICAL': 10
        }
        
        risk_score = threat_scores.get(scan_result.threat_level, 0)
        
        # 根据匹配的规则添加建议
        for match in scan_result.matches:
            rule = match['rule']
            if rule == 'Malware_Signatures':
                recommendations.append('文件包含已知恶意软件特征，建议拒绝上传')
            elif rule == 'Suspicious_Script':
                recommendations.append('文件包含可疑脚本代码，建议人工审核')
            elif rule == 'Executable_File':
                recommendations.append('文件是可执行文件，建议额外验证')
            elif rule == 'Network_Activity':
                recommendations.append('文件包含网络活动代码，建议监控')
        
        # 确定是否允许上传
        allow_upload = risk_score < 7  # 高风险以上不允许上传
        
        return {
            'risk_level': scan_result.threat_level,
            'risk_score': risk_score,
            'recommendations': recommendations or ['建议进行进一步安全检查'],
            'allow_upload': allow_upload,
            'detected_threats': [match['rule'] for match in scan_result.matches]
        }


# 用于FastAPI集成的依赖函数
def get_file_security_validator() -> FileSecurityValidator:
    """获取文件安全验证器实例"""
    return FileSecurityValidator()


# 示例用法 - FastAPI路由
"""
from fastapi import FastAPI, UploadFile, File, Depends
from file_security_integration import FileSecurityValidator, get_file_security_validator

app = FastAPI()

@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    validator: FileSecurityValidator = Depends(get_file_security_validator)
):
    # 验证文件安全性
    validation_result = await validator.validate_upload_file(file, strict_mode=True)
    
    if validation_result['is_safe']:
        # 如果有YARA扫描结果，进行风险评估
        if validation_result['yara_result']:
            risk_assessment = validator.get_file_risk_assessment(validation_result['yara_result'])
            validation_result['risk_assessment'] = risk_assessment
        
        # 处理文件上传逻辑...
        return {
            "message": "文件上传成功",
            "filename": file.filename,
            "validation": validation_result
        }
    else:
        return {
            "message": "文件验证失败",
            "validation": validation_result
        }
"""
