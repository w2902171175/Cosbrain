# project/config/projects_config.py
"""
项目模块配置文件 - 统一配置管理
"""

# OSS路径前缀
OSS_PROJECT_COVERS_PREFIX = "project_covers"
OSS_PROJECT_ATTACHMENTS_PREFIX = "project_attachments"
OSS_PROJECT_FILES_PREFIX = "project_files"

# 文件类型限制
FORBIDDEN_FILE_TYPES = ['image/', 'video/']
ALLOWED_COVER_IMAGE_TYPES = ['image/']

# 项目成员角色
PROJECT_MEMBER_ROLES = {
    'ADMIN': 'admin',
    'MEMBER': 'member'
}

# 项目成员状态
PROJECT_MEMBER_STATUS = {
    'ACTIVE': 'active',
    'INACTIVE': 'inactive'
}

# 申请状态
APPLICATION_STATUS = {
    'PENDING': 'pending',
    'APPROVED': 'approved',
    'REJECTED': 'rejected'
}

# 文件访问类型
FILE_ACCESS_TYPES = {
    'PUBLIC': 'public',
    'MEMBER_ONLY': 'member_only'
}

# 积分奖励
POINTS_REWARDS = {
    'PROJECT_LIKED': 5,  # 项目被点赞奖励积分
}

# 权限级别
PERMISSION_LEVELS = {
    'CREATOR': 'creator',
    'ADMIN': 'admin',
    'PROJECT_ADMIN': 'project_admin',
    'MEMBER': 'member'
}

# 事务类型
TRANSACTION_TYPES = {
    'EARN': 'EARN',
    'SPEND': 'SPEND'
}

# 实体类型
ENTITY_TYPES = {
    'PROJECT': 'project',
    'USER': 'user',
    'FILE': 'file'
}

# 错误消息
ERROR_MESSAGES = {
    'PROJECT_NOT_FOUND': '项目未找到。',
    'PROJECT_FILE_NOT_FOUND': '项目文件未找到。',
    'APPLICATION_NOT_FOUND': '项目申请未找到。',
    'USER_NOT_FOUND': '认证用户无效。',
    'ALREADY_MEMBER': '您已经是该项目的成员，无需申请加入。',
    'PENDING_APPLICATION_EXISTS': '您已有待处理的项目申请，请勿重复提交。',
    'REJECTED_APPLICATION_EXISTS': '您有此项目已被拒绝的申请，请联系项目创建者。',
    'APPLICATION_ALREADY_PROCESSED': '该申请已处理或状态异常，无法再次处理。',
    'ALREADY_LIKED': '已点赞该项目。',
    'LIKE_NOT_FOUND': '未找到您对该项目的点赞记录。',
    'UNSUPPORTED_COVER_TYPE': '项目封面只接受图片文件。',
    'UNSUPPORTED_ATTACHMENT_TYPE': '项目附件不支持图片或视频文件。请使用项目封面上传或在聊天室上传。',
    'METADATA_MISMATCH': '项目附件文件数量与提供的元数据数量不匹配，或缺失附件元数据。',
    'METADATA_WITHOUT_FILES': '提供了项目附件元数据但未上传任何文件。',
    'INVALID_JSON_FORMAT': '项目数据格式错误',
    'METADATA_JSON_INVALID': '项目附件元数据 JSON 格式不正确或验证失败',
    'FILE_NOT_BELONG_TO_PROJECT': '项目文件不属于该项目。',
    'NO_PERMISSION_VIEW_APPLICATIONS': '无权查看该项目的申请列表。只有项目创建者、项目管理员或系统管理员可以。',
    'NO_PERMISSION_PROCESS_APPLICATION': '无权处理该项目申请。只有项目创建者、项目管理员或系统管理员可以。',
    'NO_PERMISSION_UPDATE_PROJECT': '无权更新此项目。只有项目创建者或系统管理员可以修改。',
    'NO_PERMISSION_DELETE_PROJECT': '无权删除此项目。只有项目创建者或系统管理员可以执行此操作。',
    'NO_PERMISSION_DELETE_FILE': '无权删除此文件。',
    'NO_PERMISSION_UPLOAD_FILE': '无权为该项目上传文件。',
    'COVER_UPLOAD_FAILED': '封面文件上传到云存储失败',
    'PROJECT_CREATE_FAILED': '创建项目失败',
    'PROJECT_DELETE_FAILED': '删除项目文件失败',
    'PROJECT_UPDATE_FAILED': '更新项目失败',
    'FILE_UPLOAD_FAILED': '项目文件上传失败',
    'FILE_DELETE_FAILED': '删除项目文件失败'
}

# 成功消息
SUCCESS_MESSAGES = {
    'PROJECT_CREATED': '项目创建成功',
    'PROJECT_UPDATED': '项目更新成功',
    'PROJECT_DELETED': '项目删除成功',
    'APPLICATION_SUBMITTED': '项目申请提交成功',
    'APPLICATION_PROCESSED': '项目申请处理成功',
    'FILE_UPLOADED': '项目文件上传成功',
    'FILE_DELETED': '项目文件删除成功',
    'PROJECT_LIKED': '项目点赞成功',
    'PROJECT_UNLIKED': '取消点赞成功'
}

# 日志消息模板
LOG_TEMPLATES = {
    'RECEIVE_PROJECT_DATA': 'DEBUG_RECEIVE_PROJECT: 接收到 project_data_json: {data}',
    'RECEIVE_COVER_IMAGE': 'DEBUG_RECEIVE_COVER: 接收到 cover_image: {filename}',
    'RECEIVE_FILES_META': 'DEBUG_RECEIVE_FILES_META: 接收到 project_files_meta_json: {meta}',
    'RECEIVE_FILES_COUNT': 'DEBUG_RECEIVE_FILES: 接收到 project_files count: {count}',
    'COVER_UPLOAD_SUCCESS': 'DEBUG: 封面文件 {filename} (类型: {content_type}) 上传到OSS成功，URL: {url}',
    'PROJECT_FILE_UPLOADED': 'DEBUG: 项目附件文件 {filename} 已上传并准备添加到数据库。',
    'CREATOR_ADDED_AS_MEMBER': 'DEBUG: 准备将创建者 {user_id} 自动添加为项目 {project_id} 的成员。',
    'EMBEDDING_GENERATED': 'DEBUG: 项目嵌入向量已生成。',
    'PROJECT_CREATED_SUCCESS': 'DEBUG: 项目 {title} (ID: {project_id}) 创建成功。',
    'APPLICATION_SUBMITTED_LOG': 'DEBUG_PROJECT_APP: 用户 {user_id} 成功向项目 {project_id} 提交了申请 (ID: {application_id})。',
    'APPLICATION_APPROVED': 'DEBUG_PROJECT_APP: 用户 {student_id} 已添加为项目 {project_id} 的新成员。',
    'APPLICATION_REACTIVATED': 'DEBUG_PROJECT_APP: 用户 {student_id} 已再次激活为项目 {project_id} 的成员。',
    'DELETE_OSS_FILE': 'DEBUG: 尝试删除OSS文件: {filename}',
    'INVALID_COVER_FILE': 'WARNING: 接收到一个空封面文件或文件名为空的封面文件。跳过封面处理。',
    'FILENAME_MISMATCH': 'WARNING: 附件元数据中的文件名 {meta_filename} 与实际上传文件名 {actual_filename} 不匹配，将使用实际文件名。'
}
