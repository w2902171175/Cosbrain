# YARA Configuration File
# 设置YARA相关的环境变量
# 注意：路径配置已移至 production_config.py 进行动态管理

# 启用YARA扫描
ENABLE_YARA_SCAN=true

# YARA规则文件路径 (生产环境会自动覆盖此设置)
# YARA_RULES_PATH=yara/rules/rules.yar

# YARA扫描日志级别
YARA_LOG_LEVEL=INFO

# YARA扫描超时时间（秒）
YARA_SCAN_TIMEOUT=30

# 扫描结果输出目录 (生产环境会自动覆盖此设置)
# YARA_OUTPUT_DIR=yara/output

# 允许扫描的文件扩展名（用逗号分隔）
YARA_ALLOWED_EXTENSIONS=.exe,.dll,.ps1,.bat,.cmd,.py,.js,.vbs,.jar,.zip,.rar

# 排除扫描的目录（用逗号分隔）
YARA_EXCLUDE_DIRS=node_modules,.git,__pycache__,.venv,venv

# 最大文件大小（MB）
YARA_MAX_FILE_SIZE=100
