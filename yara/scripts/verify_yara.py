#!/usr/bin/env python3
"""
YARA 安装验证脚本
验证YARA Python是否正确安装和配置
"""

import os
import sys

def main():
    import logging
    
    # 配置控制台日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("🔍 YARA Python 安装验证")
    logger.info("=" * 40)
    
    # 1. 检查YARA模块
    try:
        import yara
        logger.info(f"✅ YARA模块导入成功")
        logger.info(f"   版本: {yara.__version__}")
    except ImportError as e:
        logger.error(f"❌ YARA模块导入失败: {e}")
        return False
    
    # 2. 检查环境变量
    logger.info(f"\n📋 环境变量检查:")
    env_vars = [
        'ENABLE_YARA_SCAN',
        'YARA_RULES_PATH', 
        'YARA_LOG_LEVEL',
        'YARA_OUTPUT_DIR'
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"   ✅ {var} = {value}")
        else:
            print(f"   ❌ {var} = 未设置")
    
    # 3. 检查规则文件
    rules_path = os.getenv('YARA_RULES_PATH', 'yara_rules/rules.yar')
    print(f"\n📄 规则文件检查:")
    if os.path.exists(rules_path):
        print(f"   ✅ 规则文件存在: {rules_path}")
        
        # 尝试编译规则
        try:
            rules = yara.compile(filepath=rules_path)
            print(f"   ✅ 规则编译成功")
        except Exception as e:
            print(f"   ❌ 规则编译失败: {e}")
            return False
    else:
        print(f"   ❌ 规则文件不存在: {rules_path}")
        return False
    
    # 4. 检查输出目录
    output_dir = os.getenv('YARA_OUTPUT_DIR', 'yara_output')
    print(f"\n📂 输出目录检查:")
    if os.path.exists(output_dir):
        print(f"   ✅ 输出目录存在: {output_dir}")
    else:
        print(f"   ❌ 输出目录不存在: {output_dir}")
    
    # 5. 快速扫描测试
    print(f"\n🧪 快速扫描测试:")
    try:
        # 创建测试数据
        test_data = b"This is a test file with powershell content"
        matches = rules.match(data=test_data)
        
        if matches:
            print(f"   ✅ 扫描功能正常，检测到 {len(matches)} 个匹配")
            for match in matches:
                print(f"      - 规则: {match.rule}")
        else:
            print(f"   ✅ 扫描功能正常，未检测到威胁")
    except Exception as e:
        print(f"   ❌ 扫描测试失败: {e}")
        return False
    
    print(f"\n✅ YARA Python 安装和配置验证通过！")
    return True

if __name__ == "__main__":
    if main():
        sys.exit(0)
    else:
        sys.exit(1)
