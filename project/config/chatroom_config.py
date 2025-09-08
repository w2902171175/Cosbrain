# project/config/chatroom_config.py
"""
聊天室配置文件 - 统一配置管理
"""

# 缓存配置
CACHE_CONFIG = {
    "default_ttl": 3600,  # 1小时
    "message_cache_size": 100,  # 每个房间缓存的消息数量
    "user_rooms_cache_ttl": 1800,  # 用户房间列表缓存时间（30分钟）
    "room_info_cache_ttl": 900,   # 房间信息缓存时间（15分钟）
}

# 文件上传配置
FILE_UPLOAD_CONFIG = {
    "max_file_size": {
        "image": 10 * 1024 * 1024,    # 10MB
        "audio": 50 * 1024 * 1024,    # 50MB
        "video": 100 * 1024 * 1024,   # 100MB
        "document": 20 * 1024 * 1024, # 20MB
    },
    "allowed_extensions": {
        "image": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
        "audio": [".mp3", ".wav", ".m4a", ".ogg"],
        "video": [".mp4", ".avi", ".mov", ".wmv"],
        "document": [".pdf", ".doc", ".docx", ".txt", ".md"],
    },
    "storage_quota": {
        "max_files_per_user_per_room": 100,
        "max_total_size_per_user": 500 * 1024 * 1024,  # 500MB
    }
}

# WebSocket配置
WEBSOCKET_CONFIG = {
    "max_idle_minutes": 30,        # 最大空闲时间（分钟）
    "cleanup_interval": 300,       # 清理间隔（秒）
    "max_connections_per_room": 100,
    "heartbeat_interval": 30,      # 心跳间隔（秒）
}

# 消息配置
MESSAGE_CONFIG = {
    "max_content_length": 2000,    # 最大消息长度
    "max_messages_per_minute": 60, # 每分钟最大消息数
    "pin_message_limit": 5,        # 每个房间最大置顶消息数
    "recall_time_limit": 120,      # 撤回时间限制（秒）
}

# 房间配置
ROOM_CONFIG = {
    "max_members": 500,            # 最大成员数
    "max_rooms_per_user": 50,      # 每个用户最大创建房间数
    "inactive_room_days": 30,      # 非活跃房间天数
}

# 积分奖励配置
POINTS_CONFIG = {
    "create_room": 10,
    "send_message": 1,
    "upload_image": 2,
    "upload_audio": 2,
    "upload_document": 3,
    "upload_video": 5,
    "daily_limit": 100,            # 每日最大获得积分
}

# 安全配置
SECURITY_CONFIG = {
    "max_failed_attempts": 5,      # 最大失败尝试次数
    "lockout_duration": 300,       # 锁定时间（秒）
    "rate_limit": {
        "messages": {"count": 60, "window": 60},      # 每分钟60条消息
        "uploads": {"count": 10, "window": 300},      # 每5分钟10个文件
        "join_requests": {"count": 5, "window": 3600}, # 每小时5个加入请求
    }
}
