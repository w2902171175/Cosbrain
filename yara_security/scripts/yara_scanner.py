#!/usr/bin/env python3
"""
YARA File Security Scanner
YARA文件安全扫描器，集成到现有项目中
"""

import os
import sys
import json
import yara
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from dotenv import load_dotenv

# 导入生产环境配置
try:
    from .production_config import production_config, initialize_yara_for_production
except ImportError:
    try:
        from production_config import production_config, initialize_yara_for_production
    except ImportError:
        # 如果无法导入生产配置，使用默认配置
        production_config = None
        initialize_yara_for_production = lambda: True


@dataclass
class ScanResult:
    """扫描结果数据类"""
    file_path: str
    file_size: int
    file_hash: str
    scan_time: str
    threat_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    matches: List[Dict[str, Any]]
    is_safe: bool


class YARAFileScanner:
    """YARA文件安全扫描器"""
    
    def __init__(self, config_file: str = "yara_security/config/.env.yara"):
        """
        初始化扫描器
        
        Args:
            config_file: 配置文件路径
        """
        # 初始化生产环境配置
        if production_config:
            initialize_yara_for_production()
        
        # 加载配置文件（如果存在）
        if os.path.exists(config_file):
            load_dotenv(config_file)
        
        self.enabled = os.getenv('ENABLE_YARA_SCAN', 'false').lower() == 'true'
        
        # 使用智能路径检测，确保在任何环境下都能正确工作
        self.rules_path = os.getenv('YARA_RULES_PATH')
        if not self.rules_path or not os.path.exists(self.rules_path):
            # 如果环境变量中的路径不存在，使用相对路径
            fallback_rules = Path.cwd() / 'yara_security' / 'rules' / 'rules.yar'
            self.rules_path = str(fallback_rules)
        
        self.output_dir = os.getenv('YARA_OUTPUT_DIR')
        if not self.output_dir:
            # 如果环境变量中没有输出目录，使用相对路径
            fallback_output = Path.cwd() / 'yara_security' / 'output'
            self.output_dir = str(fallback_output)
            
        self.log_level = os.getenv('YARA_LOG_LEVEL', 'INFO')
        self.scan_timeout = int(os.getenv('YARA_SCAN_TIMEOUT', '30'))
        self.max_file_size = int(os.getenv('YARA_MAX_FILE_SIZE', '100')) * 1024 * 1024  # 转换为字节
        
        # 解析允许的扩展名和排除目录
        allowed_ext = os.getenv('YARA_ALLOWED_EXTENSIONS', '')
        self.allowed_extensions = set(ext.strip() for ext in allowed_ext.split(',') if ext.strip())
        
        exclude_dirs = os.getenv('YARA_EXCLUDE_DIRS', '')
        self.exclude_dirs = set(dir.strip() for dir in exclude_dirs.split(',') if dir.strip())
        
        # 初始化
        self.rules = None
        
        # 创建输出目录
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        self.logger = self._setup_logger()
        
        if self.enabled:
            self.load_rules()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('YARAFileScanner')
        
        # 设置日志级别
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        logger.setLevel(level)
        
        # 创建文件处理器
        log_file = os.path.join(self.output_dir, 'yara_scan.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        if not logger.handlers:
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            
        return logger
    
    def load_rules(self) -> bool:
        """加载YARA规则"""
        if not self.enabled:
            self.logger.info("YARA扫描已禁用")
            return False
            
        try:
            if not os.path.exists(self.rules_path):
                self.logger.error(f"YARA规则文件不存在: {self.rules_path}")
                return False
                
            self.rules = yara.compile(filepath=self.rules_path)
            self.logger.info(f"成功加载YARA规则: {self.rules_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"加载YARA规则失败: {e}")
            return False
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('YARAFileScanner')
        
        # 设置日志级别
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        logger.setLevel(level)
        
        # 创建文件处理器
        log_file = os.path.join(self.output_dir, 'yara_scan.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        if not logger.handlers:
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            
        return logger
    
    def load_rules(self) -> bool:
        """加载YARA规则"""
        if not self.enabled:
            self.logger.info("YARA扫描已禁用")
            return False
            
        try:
            if not os.path.exists(self.rules_path):
                self.logger.error(f"YARA规则文件不存在: {self.rules_path}")
                return False
                
            self.rules = yara.compile(filepath=self.rules_path)
            self.logger.info(f"成功加载YARA规则: {self.rules_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"加载YARA规则失败: {e}")
            return False
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件SHA256哈希值"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception:
            return ""
    
    def _should_scan_file(self, file_path: str) -> bool:
        """判断是否应该扫描该文件"""
        if not os.path.isfile(file_path):
            return False
            
        # 检查文件大小
        try:
            file_size = os.path.getsize(file_path)
            if file_size > self.max_file_size:
                self.logger.debug(f"文件太大，跳过扫描: {file_path} ({file_size} bytes)")
                return False
        except Exception:
            return False
        
        # 检查扩展名
        if self.allowed_extensions:
            file_ext = Path(file_path).suffix.lower()
            if file_ext not in self.allowed_extensions:
                return False
        
        # 检查是否在排除目录中
        path_parts = Path(file_path).parts
        for exclude_dir in self.exclude_dirs:
            if exclude_dir in path_parts:
                return False
                
        return True
    
    def _determine_threat_level(self, matches: List[Dict[str, Any]]) -> str:
        """根据匹配结果确定威胁级别"""
        if not matches:
            return "SAFE"
            
        # 威胁级别规则
        high_threat_rules = {'Malware_Signatures', 'Executable_File'}
        medium_threat_rules = {'Suspicious_Script', 'Encrypted_File'}
        low_threat_rules = {'Network_Activity'}
        
        for match in matches:
            rule_name = match.get('rule', '')
            if rule_name in high_threat_rules:
                return "HIGH"
        
        for match in matches:
            rule_name = match.get('rule', '')
            if rule_name in medium_threat_rules:
                return "MEDIUM"
                
        return "LOW"
    
    def scan_file(self, file_path: str) -> Optional[ScanResult]:
        """
        扫描单个文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            ScanResult: 扫描结果，如果跳过扫描则返回None
        """
        if not self.enabled or not self.rules:
            return None
            
        if not self._should_scan_file(file_path):
            return None
        
        try:
            file_size = os.path.getsize(file_path)
            file_hash = self._calculate_file_hash(file_path)
            scan_time = datetime.now(timezone.utc).isoformat()
            
            # 执行YARA扫描
            matches = self.rules.match(file_path, timeout=self.scan_timeout)
            
            # 处理匹配结果
            match_results = []
            for match in matches:
                match_data = {
                    'rule': match.rule,
                    'meta': dict(match.meta),
                    'strings': []
                }
                
                # 收集匹配的字符串
                for string in match.strings:
                    string_data = {
                        'identifier': string.identifier,
                        'instances': []
                    }
                    
                    for instance in string.instances:
                        instance_data = {
                            'offset': instance.offset,
                            'matched_length': instance.matched_length,
                            'matched_data': instance.matched_data.decode('utf-8', errors='ignore')[:100]  # 限制长度
                        }
                        string_data['instances'].append(instance_data)
                    
                    match_data['strings'].append(string_data)
                
                match_results.append(match_data)
            
            # 确定威胁级别
            threat_level = self._determine_threat_level(match_results)
            is_safe = threat_level == "SAFE"
            
            result = ScanResult(
                file_path=file_path,
                file_size=file_size,
                file_hash=file_hash,
                scan_time=scan_time,
                threat_level=threat_level,
                matches=match_results,
                is_safe=is_safe
            )
            
            # 记录日志
            if not is_safe:
                self.logger.warning(f"发现威胁 [{threat_level}]: {file_path}")
            else:
                self.logger.debug(f"文件安全: {file_path}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"扫描文件失败 {file_path}: {e}")
            return None
    
    def scan_directory(self, directory_path: str, recursive: bool = True) -> List[ScanResult]:
        """
        扫描目录
        
        Args:
            directory_path: 目录路径
            recursive: 是否递归扫描
            
        Returns:
            List[ScanResult]: 扫描结果列表
        """
        if not self.enabled:
            self.logger.info("YARA扫描已禁用")
            return []
            
        results = []
        scanned_count = 0
        threat_count = 0
        
        try:
            if recursive:
                for root, dirs, files in os.walk(directory_path):
                    # 过滤排除的目录
                    dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
                    
                    for file in files:
                        file_path = os.path.join(root, file)
                        result = self.scan_file(file_path)
                        if result:
                            results.append(result)
                            scanned_count += 1
                            if not result.is_safe:
                                threat_count += 1
            else:
                for item in os.listdir(directory_path):
                    item_path = os.path.join(directory_path, item)
                    if os.path.isfile(item_path):
                        result = self.scan_file(item_path)
                        if result:
                            results.append(result)
                            scanned_count += 1
                            if not result.is_safe:
                                threat_count += 1
        
        except Exception as e:
            self.logger.error(f"扫描目录失败 {directory_path}: {e}")
        
        self.logger.info(f"扫描完成 - 总计: {scanned_count} 文件, 威胁: {threat_count} 文件")
        return results
    
    def save_scan_report(self, results: List[ScanResult], output_file: str = None) -> str:
        """
        保存扫描报告
        
        Args:
            results: 扫描结果列表
            output_file: 输出文件路径
            
        Returns:
            str: 报告文件路径
        """
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(self.output_dir, f"yara_scan_report_{timestamp}.json")
        
        # 准备报告数据
        report_data = {
            'scan_info': {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'total_files': len(results),
                'safe_files': sum(1 for r in results if r.is_safe),
                'threat_files': sum(1 for r in results if not r.is_safe),
                'rules_file': self.rules_path
            },
            'results': [asdict(result) for result in results]
        }
        
        # 保存报告
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"扫描报告已保存: {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"保存扫描报告失败: {e}")
            return ""
    
    def get_threats_summary(self, results: List[ScanResult]) -> Dict[str, Any]:
        """
        获取威胁摘要
        
        Args:
            results: 扫描结果列表
            
        Returns:
            Dict: 威胁摘要
        """
        threat_results = [r for r in results if not r.is_safe]
        
        # 按威胁级别分组
        threat_by_level = {}
        for result in threat_results:
            level = result.threat_level
            if level not in threat_by_level:
                threat_by_level[level] = []
            threat_by_level[level].append(result)
        
        # 按规则分组
        threat_by_rule = {}
        for result in threat_results:
            for match in result.matches:
                rule = match['rule']
                if rule not in threat_by_rule:
                    threat_by_rule[rule] = []
                threat_by_rule[rule].append(result.file_path)
        
        return {
            'total_threats': len(threat_results),
            'threats_by_level': {level: len(files) for level, files in threat_by_level.items()},
            'threats_by_rule': {rule: len(files) for rule, files in threat_by_rule.items()},
            'high_risk_files': [r.file_path for r in threat_results if r.threat_level == 'HIGH']
        }


def main():
    """主函数 - 演示使用"""
    import logging
    
    # 配置控制台日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("🛡️ YARA文件安全扫描器")
    logger.info("=" * 50)
    
    # 创建扫描器
    scanner = YARAFileScanner()
    
    if not scanner.enabled:
        logger.warning("❌ YARA扫描功能已禁用")
        logger.info("请在.env.yara文件中设置 ENABLE_YARA_SCAN=true")
        return
    
    # 扫描当前目录
    logger.info("🔍 扫描当前项目目录...")
    results = scanner.scan_directory(".", recursive=True)
    
    if not results:
        logger.info("✅ 没有找到需要扫描的文件")
        return
    
    # 获取威胁摘要
    summary = scanner.get_threats_summary(results)
    
    logger.info(f"\n📊 扫描摘要:")
    logger.info(f"  总文件数: {len(results)}")
    logger.info(f"  威胁文件数: {summary['total_threats']}")
    logger.info(f"  安全文件数: {len(results) - summary['total_threats']}")
    
    if summary['total_threats'] > 0:
        logger.warning(f"\n🚨 威胁分布:")
        for level, count in summary['threats_by_level'].items():
            logger.warning(f"  {level}: {count} 文件")
        
        logger.warning(f"\n🎯 威胁规则:")
        for rule, count in summary['threats_by_rule'].items():
            logger.warning(f"  {rule}: {count} 文件")
        
        if summary['high_risk_files']:
            logger.error(f"\n⚠️ 高风险文件:")
            for file_path in summary['high_risk_files'][:5]:  # 只显示前5个
                logger.error(f"  - {file_path}")
    
    # 保存报告
    report_file = scanner.save_scan_report(results)
    if report_file:
        logger.info(f"\n📄 详细报告已保存至: {report_file}")
    
    logger.info("\n✅ 扫描完成！")


if __name__ == "__main__":
    main()
