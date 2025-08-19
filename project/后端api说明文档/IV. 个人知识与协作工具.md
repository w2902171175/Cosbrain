
#### 4.1 仪表盘 / 个人工作台

**4.1.1 获取首页工作台概览数据**

* **GET /dashboard/summary**
* **摘要**: 获取当前登录用户工作台的概览数据，包括活跃项目数、已完成项目数、学习中课程数、已完成课程数、活跃聊天室数、未读消息数和简历完成度百分比。
* **权限**: 需认证 (用户)。
* **请求体**: 无
* **响应体**: schemas.DashboardSummaryResponse
 * `active_projects_count` (int): 用户当前参与的活跃项目数量。
 * `completed_projects_count` (int): 用户完成的项目数量。
 * `learning_courses_count` (int): 用户正在学习中的课程数量。
 * `completed_courses_count` (int): 用户已完成的课程数量。
 * `active_chats_count` (int): 用户活跃聊天室的数量 (当前默认为创建的聊天室数量)。
 * `unread_messages_count` (int): 用户未读消息的数量 (当前默认为 0，待实现)。
 * `resume_completion_percentage` (float): 用户简历（个人资料）的完成度百分比。
* **常见状态码**:
 * `200 OK`: 成功获取概览数据。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 用户未找到 (理论上认证通过不会发生)。

**4.1.2 获取当前用户参与的项目卡片列表**

* **GET /dashboard/projects**
* **摘要**: 获取当前登录用户参与的（或模拟所有）项目列表，以卡片形式展示概览信息，如项目标题、进度等。
* **权限**: 需认证 (用户)。
* **请求参数**:
 * `status_filter` (str, Optional): 按项目状态过滤，例如："进行中", "已完成"。
* **响应体**: List[schemas.DashboardProjectCard]
 * 列表项:
 * `id` (int): 项目ID。
 * `title` (str): 项目标题。
 * `progress` (float): 项目进度百分比 (0.0 - 1.0)。
* **常见状态码**:
 * `200 OK`: 成功获取项目卡片列表。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。

**4.1.3 获取当前用户学习的课程卡片列表**

* **GET /dashboard/courses**
* **摘要**: 获取当前登录用户学习的课程列表，以卡片形式展示概览信息，如课程标题、学习进度、上次访问时间等。
* **权限**: 需认证 (用户)。
* **请求参数**:
 * `status_filter` (str, Optional): 按课程学习状态过滤，例如："in_progress" (学习中), "completed" (已完成)。
* **响应体**: List[schemas.DashboardCourseCard]
 * 列表项:
 * `id` (int): 课程ID。
 * `title` (str): 课程标题。
 * `progress` (float): 课程学习进度百分比 (0.0 - 1.0)。
 * `last_accessed` (datetime, Optional): 上次访问该课程的时间 (ISO 8601 格式)。
* **常见状态码**:
 * `200 OK`: 成功获取课程卡片列表。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。

#### 4.2 笔记管理

**4.2.1 创建新笔记**

* **POST /notes/**
* **摘要**: 为当前登录用户创建一条新笔记。支持上传文件作为附件，并可关联课程章节或用户自定义文件夹。后端会根据笔记内容和附件信息生成组合文本和嵌入向量。
* **权限**: 需认证 (用户)。
* **请求体**: `multipart/form-data`
 * `title` (str, Optional): 笔记标题。
 * `content` (str, Optional): 笔记文本内容。
 * `note_type` (str, Optional): 笔记类型，默认为 "general"。
 * `course_id` (int, Optional): 关联的课程ID。
 * `tags` (str, Optional): 笔记标签，多个标签可使用逗号分隔。
 * `chapter` (str, Optional): 课程章节信息，例如："第一章 - AI概述"。
 * `media_url` (str, Optional): 笔记中嵌入的媒体（图片、视频、文件）的外部链接URL。仅当未上传 `file` 时使用。
 * `media_type` (Literal["image", "video", "file"], Optional): 媒体类型，当 `media_url` 或 `file` 存在时必填。
 * `original_filename` (str, Optional): 原始上传文件名，当上传 `file` 或提供 `media_url` 且类型是文件时建议提供。
 * `media_size_bytes` (int, Optional): 媒体文件大小（字节）。
 * `folder_id` (int, Optional): 关联的用户自定义文件夹ID。传入 `0` (零) 将在后端被视为 `null`，表示笔记未放入特定文件夹。如果同时提供了 `course_id` 或 `chapter`，将返回错误。
 * `file` (file, Optional): 上传的附件文件（图片、视频或任何文件），将存储到OSS并生成URL。如果提供此参数，将优先使用此文件。
* **响应体**: schemas.NoteResponse (注意：响应体中的 `folder_name` 和 `course_title` 字段是动态附加的，可能未在 Schema 中直接定义，但会通过属性暴露)
 * `id` (int): 笔记ID。
 * `owner_id` (int): 笔记所有者ID。
 * `title` (str, Optional): 笔记标题。
 * `content` (str, Optional): 笔记文本内容。
 * `note_type` (str, Optional): 笔记类型。
 * `course_id` (int, Optional): 关联的课程ID。
 * `tags` (str, Optional): 笔记标签。
 * `chapter` (str, Optional): 课程章节信息。
 * `media_url` (str, Optional): 媒体文件URL。
 * `media_type` (str, Optional): 媒体类型。
 * `original_filename` (str, Optional): 原始文件名。
 * `media_size_bytes` (int, Optional): 文件大小（字节）。
 * `folder_id` (int, Optional): 关联的文件夹ID。
 * `combined_text` (str, Optional): 用于AI模型嵌入的组合文本。
 * `created_at` (datetime): 创建时间 (ISO 8601 格式)。
 * `updated_at` (datetime, Optional): 更新时间 (ISO 8601 格式)。
 * `folder_name` (str, Optional): 关联的文件夹名称 (动态属性)。
 * `course_title` (str, Optional): 关联的课程标题 (动态属性)。
* **常见状态码**:
 * `200 OK`: 笔记创建成功。
 * `400 Bad Request`: 请求参数不正确，例如文件类型不匹配、内容与媒体URL冲突、同时关联课程和文件夹、章节信息缺失课程ID等。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 关联的课程或目标文件夹未找到。
 * `500 Internal Server Error`: 服务器内部错误，例如文件上传到云存储失败。

**4.2.2 获取当前用户所有笔记**

* **GET /notes/**
* **摘要**: 获取当前登录用户的所有笔记列表。支持按类型、课程ID、章节、文件夹ID和标签进行过滤，并支持分页。
* **权限**: 需认证 (用户)。
* **请求参数**:
 * `note_type` (str, Optional): 笔记类型过滤。
 * `course_id` (int, Optional): 按关联课程ID过滤。
 * `chapter` (str, Optional): 按课程章节名称过滤。**注意：如果提供此参数，`course_id` 也必须提供。**
 * `folder_id` (int, Optional): 按自定义文件夹ID过滤。传入 `0` (零) 表示过滤出所有未放入任何文件夹的顶级笔记 (`folder_id` 为 NULL 的笔记)。
 * `tags` (str, Optional): 按标签过滤，支持模糊匹配。
 * `limit` (int, Optional): 返回的最大笔记数量，默认为 `100`。
 * `offset` (int, Optional): 查询的偏移量，默认为 `0`。
* **响应体**: List[schemas.NoteResponse]
 * 列表项同 `创建新笔记` 的响应体。
* **常见状态码**:
 * `200 OK`: 成功获取笔记列表。
 * `400 Bad Request`: 请求参数冲突，例如同时按课程/章节和文件夹ID过滤。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 指定的文件夹或课程未找到 (如果过滤条件涉及到特定ID)。

**4.2.3 获取指定笔记详情**

* **GET /notes/{note_id}**
* **摘要**: 获取指定ID的笔记详细信息。用户只能获取自己的笔记。
* **权限**: 需认证 (用户)。
* **路径参数**:
 * `note_id` (int): 笔记的唯一标识符ID。
* **请求体**: 无
* **响应体**: schemas.NoteResponse (字段说明同 `创建新笔记` 的响应体)
* **常见状态码**:
 * `200 OK`: 成功获取笔记详情。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 指定ID的笔记未找到或不属于当前用户。

**4.2.4 更新指定笔记**

* **PUT /notes/{note_id}**
* **摘要**: 更新指定ID的笔记内容。用户只能更新自己的笔记。支持替换附件文件和修改所属的课程章节或自定义文件夹。更新后会重新生成组合文本和嵌入向量。
* **权限**: 需认证 (用户)。
* **路径参数**:
 * `note_id` (int): 笔记的唯一标识符ID。
* **请求体**: `multipart/form-data`
 * 以下字段均为可选，只更新提供的内容：
 * `title` (str, Optional): 笔记标题。
 * `content` (str, Optional): 笔记文本内容。如果更新为仅包含媒体的笔记，可以传入空字符串或 None，但如果 `media_url` 也为空，`content` 则不能为空。
 * `note_type` (str, Optional): 笔记类型。
 * `course_id` (int, Optional): 关联的课程ID。
 * `tags` (str, Optional): 笔记标签。
 * `chapter` (str, Optional): 课程章节信息。**注意：如果提供此参数，`course_id` 也必须提供。**
 * `media_url` (str, Optional): 笔记中嵌入的媒体（图片、视频、文件）的外部链接URL。可以传入空字符串或 None 来清除当前媒体URL。
 * `media_type` (Literal["image", "video", "file"], Optional): 媒体类型。
 * `original_filename` (str, Optional): 原始上传文件名。
 * `media_size_bytes` (int, Optional): 媒体文件大小（字节）。
 * `folder_id` (int, Optional): 关联的用户自定义文件夹ID。传入 `0` (零) 将在后端被视为 `null`，表示笔记未放入特定文件夹。
 * `file` (file, Optional): 上传的新附件文件，将替换原有附件并删除旧文件。如果提供此参数，将优先更新媒体URL和类型。
* **响应体**: schemas.NoteResponse (字段说明同 `创建新笔记` 的响应体)
* **常见状态码**:
 * `200 OK`: 笔记更新成功。
 * `400 Bad Request`: 请求参数不正确，例如文件类型不匹配、内容与媒体URL冲突、同时关联课程和文件夹、章节信息缺失课程ID、清空了所有内容。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 指定ID的笔记未找到或不属于当前用户，或关联的课程/目标文件夹未找到。
 * `500 Internal Server Error`: 服务器内部错误，例如文件上传到云存储失败。

**4.2.5 删除指定笔记**

* **DELETE /notes/{note_id}**
* **摘要**: 删除指定ID的笔记。用户只能删除自己的笔记。如果笔记关联了文件或媒体（指向OSS），将同时删除云存储中的文件。
* **权限**: 需认证 (用户)。
* **路径参数**:
 * `note_id` (int): 笔记的唯一标识符ID。
* **请求体**: 无
* **响应体**:
 * `message` (str): 删除成功消息。
* **常见状态码**:
 * `200 OK`: 笔记及其关联数据删除成功。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 指定ID的笔记未找到或不属于当前用户。
 * `500 Internal Server Error`: 服务器内部错误，例如删除OSS文件失败（但数据库记录仍会被删除）。

#### 4.3 随手记录

**4.3.1 创建新随手记录**

* **POST /daily-records/**
* **摘要**: 为当前登录用户创建一条新的随手记录。记录内容将用于AI智能分析和搜索，生成组合文本和嵌入向量。
* **权限**: 需认证 (用户)。
* **请求体**: `application/json`
 * `content` (str): 记录的文本内容，必填。
 * `mood` (str, Optional): 记录时的心情描述。
 * `tags` (str, Optional): 记录的标签，多个标签可使用逗号分隔。
* **响应体**: schemas.DailyRecordResponse
 * `id` (int): 随手记录ID。
 * `owner_id` (int): 记录所有者ID。
 * `content` (str): 记录文本内容。
 * `mood` (str, Optional): 心情。
 * `tags` (str, Optional): 标签。
 * `combined_text` (str, Optional): 用于AI模型嵌入的组合文本。
 * `created_at` (datetime): 创建时间 (ISO 8601 格式)。
 * `updated_at` (datetime, Optional): 更新时间 (ISO 8601 格式)。
* **常见状态码**:
 * `200 OK`: 随手记录创建成功。
 * `400 Bad Request`: 请求参数不正确，例如 `content` 为空。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `500 Internal Server Error`: 服务器内部错误。

**4.3.2 获取当前用户所有随手记录**

* **GET /daily-records/**
* **摘要**: 获取当前登录用户的所有随手记录列表。支持按心情（mood）或标签（tag）进行过滤。
* **权限**: 需认证 (用户)。
* **请求参数**:
 * `mood` (str, Optional): 按心情过滤。
 * `tag` (str, Optional): 按标签过滤，支持模糊匹配。
* **响应体**: List[schemas.DailyRecordResponse]
 * 列表项同 `创建新随手记录` 的响应体。
* **常见状态码**:
 * `200 OK`: 成功获取随手记录列表。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。

**4.3.3 获取指定随手记录详情**

* **GET /daily-records/{record_id}**
* **摘要**: 获取指定ID的随手记录详细信息。用户只能获取自己的记录。
* **权限**: 需认证 (用户)。
* **路径参数**:
 * `record_id` (int): 随手记录的唯一标识符ID。
* **请求体**: 无
* **响应体**: schemas.DailyRecordResponse (字段说明同 `创建新随手记录` 的响应体)
* **常见状态码**:
 * `200 OK`: 成功获取随手记录详情。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 指定ID的随手记录未找到或不属于当前用户。

**4.3.4 更新指定随手记录**

* **PUT /daily-records/{record_id}**
* **摘要**: 更新指定ID的随手记录内容。用户只能更新自己的记录。更新后会重新生成组合文本和嵌入向量。
* **权限**: 需认证 (用户)。
* **路径参数**:
 * `record_id` (int): 随手记录的唯一标识符ID。
* **请求体**: `application/json`
 * 以下字段均为可选，只更新提供的内容：
 * `content` (str, Optional): 记录的文本内容。如果提供，内容不能为空。
 * `mood` (str, Optional): 记录时的心情描述。
 * `tags` (str, Optional): 记录的标签。
* **响应体**: schemas.DailyRecordResponse (字段说明同 `创建新随手记录` 的响应体)
* **常见状态码**:
 * `200 OK`: 随手记录更新成功。
 * `400 Bad Request`: 请求参数不正确，例如 `content` 尝试更新为空。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 指定ID的随手记录未找到或不属于当前用户。
 * `500 Internal Server Error`: 服务器内部错误。

**4.3.5 删除指定随手记录**

* **DELETE /daily-records/{record_id}**
* **摘要**: 删除指定ID的随手记录。用户只能删除自己的记录。
* **权限**: 需认证 (用户)。
* **路径参数**:
 * `record_id` (int): 随手记录的唯一标识符ID。
* **请求体**: 无
* **响应体**:
 * `message` (str): 删除成功消息。
* **常见状态码**:
 * `200 OK`: 随手记录删除成功。
 * `401 Unauthorized`: 未提供认证令牌或认证失败。
 * `404 Not Found`: 指定ID的随手记录未找到或不属于当前用户。



#### 4.4 文件夹与收藏管理

**4.4.1 创建新文件夹**
* **Endpoint**: `POST /folders/`
* **摘要**: 为当前用户创建一个新文件夹。文件夹支持嵌套，可指定父文件夹。
* **权限**: 认证用户
* **请求体**: `application/json`
 * `schemas.FolderBase`
 * `name` (str): 文件夹名称，必填。
 * `description` (Optional[str]): 文件夹描述。
 * `color` (Optional[str]): 文件夹颜色，例如 `#FF0000`。
 * `icon` (Optional[str]): 文件夹图标名称。
 * `parent_id` (Optional[int]): 父文件夹ID。如果为 `None` (或传入 `null`)，则表示在根目录下创建。
 * `order` (Optional[int]): 排序优先级，数字越小越靠前 (默认0)。
* **响应体**: `schemas.FolderResponse`
 * `id` (int): 文件夹ID。
 * `owner_id` (int): 文件夹所有者（用户）ID。
 * `name` (str): 文件夹名称。
 * `description` (Optional[str]): 文件夹描述。
 * `color` (Optional[str]): 文件夹颜色。
 * `icon` (Optional[str]): 文件夹图标。
 * `parent_id` (Optional[int]): 父文件夹ID。
 * `order` (Optional[int]): 排序优先级。
 * `item_count` (Optional[int]): （动态计算）文件夹下直属内容（收藏内容和子文件夹）的数量。
 * `created_at` (datetime): 创建时间 (ISO 8601 格式)。
 * `updated_at` (Optional[datetime]): 更新时间 (ISO 8601 格式)。
* **常见状态码**:
 * `200 OK`: 文件夹创建成功。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 指定的父文件夹未找到或不属于当前用户。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.2 获取当前用户所有文件夹**
* **Endpoint**: `GET /folders/`
* **摘要**: 获取当前用户创建的所有文件夹列表。默认返回顶级文件夹。
* **权限**: 认证用户
* **查询参数**:
 * `parent_id` (Optional[int]):
 * 按父文件夹ID过滤，返回该父文件夹下的所有子文件夹。
 * 如果为 `None` (或不传此参数)，则返回所有顶级文件夹（即 `parent_id` 为 `NULL` 的文件夹）。
* **响应体**: `List[schemas.FolderResponse]`
 * 列表中的每个元素都是 `schemas.FolderResponse` 对象，字段同上。
* **常见状态码**:
 * `200 OK`: 文件夹列表获取成功。
 * `401 Unauthorized`: 用户未认证。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.3 获取指定文件夹详情**
* **Endpoint**: `GET /folders/{folder_id}`
* **摘要**: 获取指定ID的文件夹的详细信息。
* **权限**: 认证用户 (只能获取自己的文件夹)
* **路径参数**:
 * `folder_id` (int): 文件夹的唯一标识ID。
* **响应体**: `schemas.FolderResponse`
 * 字段同上。
* **常见状态码**:
 * `200 OK`: 文件夹详情获取成功。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 指定文件夹未找到或不属于当前用户。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.4 更新指定文件夹**
* **Endpoint**: `PUT /folders/{folder_id}`
* **摘要**: 更新指定ID文件夹的名称、描述、颜色、图标、父文件夹或排序。
* **权限**: 认证用户 (只能更新自己的文件夹)
* **路径参数**:
 * `folder_id` (int): 要更新的文件夹的唯一标识ID。
* **请求体**: `application/json`
 * `schemas.FolderBase` (所有字段均为可选，只更新提供的字段):
 * `name` (Optional[str]): 文件夹名称。
 * `description` (Optional[str]): 文件夹描述。
 * `color` (Optional[str]): 文件夹颜色。
 * `icon` (Optional[str]): 文件夹图标。
 * `parent_id` (Optional[int]): 新的父文件夹ID。如果设置为 `None` (或 `null`)，表示将文件夹移动到根目录。
 * `order` (Optional[int]): 新的排序优先级。
* **响应体**: `schemas.FolderResponse`
 * 字段同上，显示更新后的文件夹信息。
* **常见状态码**:
 * `200 OK`: 文件夹更新成功。
 * `400 Bad Request`: 请求参数无效 (例如，尝试将文件夹设置为其自身的子文件夹导致循环引用)。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 要更新的文件夹或指定的新父文件夹未找到或不属于当前用户。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.5 删除指定文件夹**
* **Endpoint**: `DELETE /folders/{folder_id}`
* **摘要**: 删除指定ID的文件夹。该操作会级联删除其下所有子文件夹和所有关联的收藏内容和笔记。
* **权限**: 认证用户 (只能删除自己的文件夹)
* **路径参数**:
 * `folder_id` (int): 要删除的文件夹的唯一标识ID。
* **响应体**: `application/json`
 * `message` (str): "Folder and its contents deleted successfully" 表示删除成功。
* **常见状态码**:
 * `200 OK`: 文件夹及其内容（包括子文件夹、收藏内容、笔记）删除成功。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 指定文件夹未找到或不属于当前用户。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.6 创建新收藏内容**
* **Endpoint**: `POST /collections/`
* **摘要**: 为当前用户创建一个新的收藏内容，支持直接创建文本、链接或上传文件/图片/视频。
* **权限**: 认证用户
* **请求体**: `multipart/form-data`
 * `content_data` (JSON, representing `schemas.CollectedContentBase`):
 * `title` (str): 收藏内容的标题，必填。
 * `type` (Literal): 内容类型，必填，可选值包括 `"document"`, `"video"`, `"note"`, `"link"`, `"file"`, `"image"`, `"forum_topic"`, `"course"`, `"project"`, `"knowledge_article"`, `"daily_record"`。
 * `url` (Optional[str]): 当 `type` 为 `"link"` 或媒体文件类型 (`"file"`, `"image"`, `"video"`) 时，此字段为外部链接URL或OSS文件URL。
 * `content` (Optional[str]): 文本内容或简要描述。当 `type` 为 `"text"` 时通常为必填。
 * `tags` (Optional[str]): 标签，使用逗号分隔的字符串，例如 `"AI,学习方法"`。
 * `folder_id` (Optional[int]): 相关联的用户自定义文件夹ID。如果为 `None` (或 `null`)，表示未放入特定文件夹。
 * `priority` (Optional[int]): 收藏内容的优先级 (默认3)。
 * `notes` (Optional[str]): 用户对该收藏的个人备注。
 * `is_starred` (Optional[bool]): 是否为星标收藏 (默认 `false`)。
 * `thumbnail` (Optional[str]): 缩略图URL。
 * `author` (Optional[str]): 作者名称。
 * `duration` (Optional[str]): 媒体时长，例如 `"1h30m"`。
 * `file_size` (Optional[int]): 文件大小（字节）。
 * `status` (Optional[Literal["active", "archived", "deleted"]]): 收藏内容的状态。
 * `file` (Optional[UploadFile]): 可选。用于上传图片、视频或文档文件作为收藏内容。如果提供此参数，`content_data.type` 必须为 `"file"`, `"image"`, 或 `"video"`。
* **响应体**: `schemas.CollectedContentResponse`
 * `id` (int): 收藏内容ID。
 * `owner_id` (int): 内容所有者（用户）ID。
 * `title` (str): 收藏内容的标题。
 * `type` (Literal): 内容类型。
 * `url` (Optional[str]): 外部链接或OSS文件URL。
 * `content` (Optional[str]): 文本内容或简要描述。
 * `tags` (Optional[str]): 标签。
 * `folder_id` (Optional[int]): 所属文件夹ID。
 * `priority` (Optional[int]): 优先级。
 * `notes` (Optional[str]): 备注。
 * `access_count` (Optional[int]): 访问次数。
 * `is_starred` (Optional[bool]): 是否星标。
 * `thumbnail` (Optional[str]): 缩略图URL。
 * `author` (Optional[str]): 作者。
 * `duration` (Optional[str]): 时长。
 * `file_size` (Optional[int]): 文件大小（字节）。
 * `status` (Optional[Literal]): 状态。
 * `shared_item_type` (Optional[Literal]): 如果是分享平台内部内容，记录其类型。
 * `shared_item_id` (Optional[int]): 如果是分享平台内部内容，记录其ID。
 * `combined_text` (Optional[str]): 用于AI模型嵌入的组合文本。
 * `created_at` (datetime): 创建时间 (ISO 8601 格式)。
 * `updated_at` (Optional[datetime]): 更新时间 (ISO 8601 格式)。
 * `folder_name` (Optional[str]): （动态填充）所属文件夹名称。
* **常见状态码**:
 * `200 OK`: 收藏内容创建成功。
 * `400 Bad Request`: 请求参数无效（例如缺少必填字段、`type` 与 `url` 不匹配、文件类型不符等）。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 指定的文件夹未找到或不属于当前用户。
 * `409 Conflict`: 收藏内容已存在（例如已收藏同一内部资源），或数据库唯一性约束冲突。
 * `500 Internal Server Error`: 文件上传失败或服务器内部错误。

**4.4.7 快速收藏平台内部内容**
* **Endpoint**: `POST /collections/add-from-platform`
* **摘要**: 用户可以通过此接口快速收藏平台内部的现有内容（如课程、项目、论坛话题、笔记、随手记录、知识库文章或聊天消息）到自己的收藏。
* **权限**: 认证用户
* **请求体**: `application/json`
 * `schemas.CollectedContentSharedItemAddRequest`
 * `shared_item_type` (Literal): 要收藏的平台内部内容的类型，必填。可选值包括 `"project"`, `"course"`, `"forum_topic"`, `"note"`, `"daily_record"`, `"knowledge_article"`, `"chat_message"`, `"knowledge_document"`。
 * `shared_item_id` (int): 要收藏的平台内部内容的ID，必填。
 * `folder_id` (Optional[int]): 要收藏到的文件夹ID。
 * `notes` (Optional[str]): 收藏时添加的个人备注。
 * `is_starred` (Optional[bool]): 是否立即为该收藏添加星标 (默认 `false`)。
 * `title` (Optional[str]): 收藏项的自定义标题。如果为空，后端将自动从共享项中提取（例如：项目标题、笔记标题等）。
* **响应体**: `schemas.CollectedContentResponse`
 * 字段同上。
* **常见状态码**:
 * `200 OK`: 平台内部内容成功收藏。
 * `400 Bad Request`: 请求参数无效 (例如，不支持的 `shared_item_type`)。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 共享项或指定文件夹未找到或无权访问。
 * `409 Conflict`: 该内容已被当前用户收藏。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.8 获取当前用户所有收藏内容**
* **Endpoint**: `GET /collections/`
* **摘要**: 获取当前用户的所有收藏内容列表。支持多种筛选条件。
* **权限**: 认证用户
* **查询参数**:
 * `folder_id` (Optional[int]): 按文件夹ID过滤。
 * 如果为 `None` (或不传此参数)，则返回用户所有收藏内容，无论是否在文件夹内。
 * 如果传入 `0`，则返回所有**不在任何文件夹内**（即 `folder_id` 为 `NULL`）的收藏内容。
 * 如果传入特定文件夹ID，则返回该文件夹下的所有直属收藏内容。
 * `type_filter` (Optional[str]): 按内容类型过滤，例如 `"document"`, `"video"`, `"link"` 等。
 * `tag_filter` (Optional[str]): 按标签过滤，支持模糊匹配（例如，`tag_filter` 为 `"AI"`，可匹配带有 `"AI,机器学习"` 的收藏）。
 * `is_starred` (Optional[bool]): 按星标状态过滤 (`true` 只返回星标，`false` 只返回非星标)。
 * `status_filter` (Optional[str]): 按内容状态过滤，例如 `"active"`, `"archived"`, `"deleted"`。
* **响应体**: `List[schemas.CollectedContentResponse]`
 * 列表中的每个元素都是 `schemas.CollectedContentResponse` 对象，字段同上。
* **常见状态码**:
 * `200 OK`: 收藏内容列表获取成功。
 * `401 Unauthorized`: 用户未认证。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.9 获取指定收藏内容详情**
* **Endpoint**: `GET /collections/{content_id}`
* **摘要**: 获取指定ID的收藏内容的详细信息。每次访问此接口会增加该收藏的访问计数。
* **权限**: 认证用户 (只能获取自己的收藏)
* **路径参数**:
 * `content_id` (int): 收藏内容的唯一标识ID。
* **响应体**: `schemas.CollectedContentResponse`
 * 字段同上，显示收藏内容的详细信息，包括更新后的 `access_count`。
* **常见状态码**:
 * `200 OK`: 收藏内容详情获取成功。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 指定收藏内容未找到或不属于当前用户。
 * `500 Internal Server Error`: 其他服务器内部错误。

**4.4.10 更新指定收藏内容**
* **Endpoint**: `PUT /collections/{content_id}`
* **摘要**: 更新指定ID的收藏内容信息。支持修改标题、类型、URL、内容、标签等。如果上传新文件，将替换旧的媒体文件。
* **权限**: 认证用户 (只能更新自己的收藏)
* **路径参数**:
 * `content_id` (int): 要更新的收藏内容的唯一标识ID。
* **请求体**: `multipart/form-data`
 * `content_data` (JSON, representing `schemas.CollectedContentBase`):
 * `title` (Optional[str]): 收藏内容的标题。
 * `type` (Optional[Literal]): 内容类型。
 * `url` (Optional[str]): 外部链接或OSS文件URL。
 * `content` (Optional[str]): 文本内容或简要描述。
 * `tags` (Optional[str]): 标签。
 * `folder_id` (Optional[int]): 新的关联文件夹ID。传入 `None` 或 `null` 表示清除关联。
 * `priority` (Optional[int]): 优先级。
 * `notes` (Optional[str]): 个人备注。
 * `is_starred` (Optional[bool]): 是否星标。
 * `thumbnail` (Optional[str]): 缩略图URL。
 * `author` (Optional[str]): 作者。
 * `duration` (Optional[str]): 时长。
 * `file_size` (Optional[int]): 文件大小（字节）。
 * `status` (Optional[Literal]): 内容状态。
 * `file` (Optional[UploadFile]): 可选。上传新的文件、图片或视频来替换现有媒体内容。如果提供此参数，`content_data.type` 必须是 `"file"`, `"image"`, 或 `"video"`。
* **响应体**: `schemas.CollectedContentResponse`
 * 字段同上，显示更新后的收藏内容信息。
* **常见状态码**:
 * `200 OK`: 收藏内容更新成功。
 * `400 Bad Request`: 请求参数无效（例如：标题为空、`type` 与 `url` 不匹配、文件类型不符等）。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 收藏内容或指定的新文件夹未找到或不属于当前用户。
 * `409 Conflict`: 数据冲突（例如，尝试将内部共享内容类型改为普通文件类型等）。
 * `500 Internal Server Error`: 文件上传失败或服务器内部错误。

**4.4.11 删除指定收藏内容**
* **Endpoint**: `DELETE /collections/{content_id}`
* **摘要**: 删除指定ID的收藏内容。如果收藏内容是文件或媒体（通过URL指向OSS）且位于OSS上，将同时删除OSS上的文件。
* **权限**: 认证用户 (只能删除自己的收藏)
* **路径参数**:
 * `content_id` (int): 要删除的收藏内容的唯一标识ID。
* **响应体**: `application/json`
 * `message` (str): "Collected content deleted successfully" 表示删除成功。
* **常见状态码**:
 * `200 OK`: 收藏内容删除成功。
 * `401 Unauthorized`: 用户未认证。
 * `404 Not Found`: 指定收藏内容未找到或不属于当前用户。
 * `500 Internal Server Error`: 关联的OSS文件删除失败或内部服务器错误。

---

#### 4.5 知识库管理

##### 4.5.1 创建新知识库

* **POST** `/knowledge-bases/`
* **摘要**: 创建一个新的知识库。每个用户可以拥有多个知识库。
* **权限**: 需要认证 (JWT Token)。
* **请求体**: `application/json`
 * `name` (str): 知识库名称。
 * `description` (Optional[str]): 知识库描述。
 * `access_type` (Optional[str]): 访问类型，如 `"private"` (私有) 或 `"public"` (公开)，默认为 `"private"`。
* **响应体**: `schemas.KnowledgeBaseResponse`
 * `id` (int): 知识库唯一ID。
 * `owner_id` (int): 知识库创建者的用户ID。
 * `name` (str): 知识库名称。
 * `description` (Optional[str]): 知识库描述。
 * `access_type` (Optional[str]): 访问类型。
 * `created_at` (datetime): 创建时间 (ISO 8601 格式)。
 * `updated_at` (Optional[datetime]): 最后更新时间 (ISO 8601 格式)。
* **常见状态码**:
 * `200 OK`: 知识库创建成功。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `409 Conflict`: 知识库名称已存在（在当前用户下）。
 * `500 Internal Server Error`: 服务器内部错误，例如数据库操作失败。

---

##### 4.5.2 获取当前用户所有知识库

* **GET** `/knowledge-bases/`
* **摘要**: 获取当前登录用户创建的所有知识库的列表。
* **权限**: 需要认证 (JWT Token)。
* **请求参数**: 无。
* **查询参数**: 无。
* **响应体**: `List[schemas.KnowledgeBaseResponse]`
 * 列表项结构与 `schemas.KnowledgeBaseResponse` 相同，详见 4.5.1。
* **常见状态码**:
 * `200 OK`: 成功获取知识库列表，即使列表为空。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。

---

##### 4.5.3 获取指定知识库详情

* **GET** `/knowledge-bases/{kb_id}`
* **摘要**: 获取指定ID的知识库的详细信息。
* **权限**: 需要认证 (JWT Token)。用户只能获取自己拥有的知识库详情。
* **路径参数**:
 * `kb_id` (int): 目标知识库的唯一ID。
* **请求参数**: 无。
* **响应体**: `schemas.KnowledgeBaseResponse`
 * 结构与 `schemas.KnowledgeBaseResponse` 相同，详见 4.5.1。
* **常见状态码**:
 * `200 OK`: 成功获取知识库详情。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的知识库未找到，或者当前用户无权访问该知识库。

---

##### 4.5.4 更新指定知识库

* **PUT** `/knowledge-bases/{kb_id}`
* **摘要**: 更新指定ID的知识库的信息（如名称、描述、访问类型）。
* **权限**: 需要认证 (JWT Token)。只有知识库的所有者才能更新。
* **路径参数**:
 * `kb_id` (int): 目标知识库的唯一ID。
* **请求体**: `application/json`
 * `name` (Optional[str]): 新的知识库名称。
 * `description` (Optional[str]): 新的知识库描述。
 * `access_type` (Optional[str]): 新的访问类型。
* **响应体**: `schemas.KnowledgeBaseResponse`
 * 结构与 `schemas.KnowledgeBaseResponse` 相同，详见 4.5.1。
* **常见状态码**:
 * `200 OK`: 知识库更新成功。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的知识库未找到，或者当前用户无权更新该知识库。
 * `409 Conflict`: 更新后的知识库名称已存在（在当前用户下）。
 * `500 Internal Server Error`: 服务器内部错误，例如数据库操作失败。

---

##### 4.5.5 删除指定知识库

* **DELETE** `/knowledge-bases/{kb_id}`
* **摘要**: 删除指定ID的知识库。删除知识库将同时级联删除其下的所有文件夹、文章和文档。
* **权限**: 需要认证 (JWT Token)。只有知识库的所有者才能删除。
* **路径参数**:
 * `kb_id` (int): 目标知识库的唯一ID。
* **请求参数**: 无。
* **响应体**: `application/json`
 * `message` (str): success message string, e.g., "Knowledge base and its articles/documents deleted successfully"。
* **常见状态码**:
 * `200 OK`: 知识库及其所有关联内容删除成功。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的知识库未找到，或者当前用户无权删除该知识库。

---

##### 4.5.6 在指定知识库中创建新文件夹

* **POST** `/knowledge-bases/{kb_id}/folders/`
* **摘要**: 在指定知识库中为当前用户创建一个新文件夹。
* **描述**: 支持创建普通文件夹和软链接文件夹。普通文件夹可嵌套，软链接文件夹可以链接到用户的笔记文件夹或收藏文件夹，从而实现内容的复用和统一管理。软链接文件夹必须是顶级文件夹，且不允许链接包含非外部URL视频的文件。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 所属知识库的ID。
* **请求体**: `application/json`
 * `name` (str): 文件夹名称。
 * `description` (Optional[str]): 文件夹描述。
 * `parent_id` (Optional[int]): 父文件夹ID。如果为 `None` 或 `0`，则表示在知识库的根目录下创建。
 * `order` (Optional[int]): 排序值，用于控制文件夹在同级列表中的显示顺序。
 * `linked_folder_type` (Optional[`"note_folder"` | `"collected_content_folder"`]): 如果要创建软链接文件夹，指定链接的外部文件夹类型。
 * `"note_folder"`: 链接到用户在笔记模块创建的文件夹。
 * `"collected_content_folder"`: 链接到用户在收藏模块创建的文件夹。
 * `linked_folder_id` (Optional[int]): 如果是软链接文件夹，指定要链接的外部文件夹的ID。
* **响应体**: `schemas.KnowledgeBaseFolderResponse`
 * `id` (int): 知识库文件夹唯一ID。
 * `kb_id` (int): 所属知识库的ID。
 * `owner_id` (int): 文件夹创建者的用户ID。
 * `name` (str): 文件夹名称。
 * `description` (Optional[str]): 文件夹描述。
 * `parent_id` (Optional[int]): 父文件夹ID。
 * `order` (Optional[int]): 排序值。
 * `linked_folder_type` (Optional[str]): 链接的外部文件夹类型。
 * `linked_folder_id` (Optional[int]): 链接的外部文件夹ID。
 * `item_count` (Optional[int]): 文件夹下直属文章/文档/子文件夹或软链接内容的总数。
 * `parent_folder_name` (Optional[str]): 父文件夹的名称（动态填充，无父文件夹则为 `None`）。
 * `knowledge_base_name` (Optional[str]): 所属知识库的名称（动态填充）。
 * `linked_object_names` (Optional[List[str]]): 如果是软链接文件夹，此字段包含其链接的外部文件夹所含内容的名称列表（动态填充）。
* **常见状态码**:
 * `200 OK`: 文件夹创建成功。
 * `400 Bad Request`: 请求参数无效（例如，软链接文件夹指定了父文件夹，或链接目标包含不支持的媒体类型，或非软链接文件夹未提供名称）。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 所属知识库或指定的父文件夹/链接目标未找到，或当前用户无权访问。
 * `409 Conflict`: 在当前知识库的相同层级下已存在同名文件夹，或该外部文件夹已被链接到此知识库。
 * `500 Internal Server Error`: 服务器内部错误。

---

##### 4.5.7 获取指定知识库下所有文件夹和软链接内容

* **GET** `/knowledge-bases/{kb_id}/folders/`
* **摘要**: 获取指定知识库下当前用户创建的所有文件夹列表。
* **描述**: 返回的文件夹列表，无论是普通文件夹还是软链接文件夹，都会包含其下内容的统计信息。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 所属知识库的ID。
* **查询参数**:
 * `parent_id` (Optional[int]): 按父文件夹ID过滤。如果为 `None` (未提供)，则默认返回知识库根目录下的所有顶级文件夹。传入 `0` 表示专门查询根目录下的文件夹（其 `parent_id` 为 `NULL`）。
* **响应体**: `List[schemas.KnowledgeBaseFolderResponse]`
 * 列表项结构与 `schemas.KnowledgeBaseFolderResponse` 相同，详见 4.5.6。
* **常见状态码**:
 * `200 OK`: 成功获取文件夹列表，即使列表为空。
 * `400 Bad Request`: 提供的 `parent_id` 无效（例如，指定了一个不存在的父文件夹ID）。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 所属知识库或指定的父文件夹未找到，或当前用户无权访问。

---

##### 4.5.8 获取指定知识库文件夹详情及其内容

* **GET** `/knowledge-bases/{kb_id}/folders/{kb_folder_id}`
* **摘要**: 获取指定知识库文件夹的详细信息及其包含的直接内容列表。
* **描述**: 用户只能获取自己知识库下的文件夹详情。如果文件夹是软链接文件夹，并且请求中包含 `include_contents=True`，则响应中会额外包含其链接的实际内容列表（例如笔记或收藏项的概要信息）。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 所属知识库的ID。
 * `kb_folder_id` (int): 目标知识库文件夹的唯一ID。
* **查询参数**:
 * `include_contents` (Optional[bool]): 默认为 `False`。如果设置为 `True`，且目标文件夹是软链接类型，则会在响应中包含其链接的实际内容列表（`contents` 字段）。对于普通文件夹，如果设置为 `True`，也会返回其直属的文章和文档。
* **响应体**: `schemas.KnowledgeBaseFolderContentResponse`
 * `id` (int): 知识库文件夹唯一ID。
 * `kb_id` (int): 所属知识库的ID。
 * `owner_id` (int): 文件夹所有者ID。
 * `name` (str): 文件夹名称。
 * `description` (Optional[str]): 文件夹描述。
 * `parent_id` (Optional[int]): 父文件夹ID。
 * `order` (Optional[int]): 排序值。
 * `linked_folder_type` (Optional[str]): 链接的外部文件夹类型。
 * `linked_folder_id` (Optional[int]): 链接的外部文件夹ID。
 * `item_count` (Optional[int]): 文件夹下直属文章/文档/子文件夹或软链接内容的总数。
 * `parent_folder_name` (Optional[str]): 父文件夹的名称（动态填充）。
 * `knowledge_base_name` (Optional[str]): 所属知识库的名称（动态填充）。
 * `linked_object_names` (Optional[List[str]]): 如果是软链接文件夹，此字段包含其链接的外部文件夹所含内容的名称列表（动态填充）。
 * `contents` (Optional[List[Any]]): 软链接文件夹内实际包含的内容列表（例如 `schemas.NoteResponse` 或 `schemas.CollectedContentResponse`）或普通文件夹下的直属文章和文档（`schemas.KnowledgeArticleResponse` 或 `schemas.KnowledgeDocumentResponse`）。仅当 `include_contents` 为 `True` 时返回。
* **常见状态码**:
 * `200 OK`: 成功获取文件夹详情和可选的内容。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的知识库文件夹未找到，或不属于该知识库，或当前用户无权访问。

---

##### 4.5.9 更新指定知识库文件夹

* **PUT** `/knowledge-bases/{kb_id}/folders/{kb_folder_id}`
* **摘要**: 更新指定ID的知识库文件夹的信息（例如名称、描述、所属父文件夹、排序或软链接目标）。
* **描述**: 用户只能更新自己知识库下的文件夹。更新时对普通文件夹和软链接文件夹有不同限制：普通文件夹不能转换为软链接，软链接文件夹不能转换为普通文件夹（需删除重链），且软链接文件夹始终为顶级。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 所属知识库的ID。
 * `kb_folder_id` (int): 目标知识库文件夹的唯一ID。
* **请求体**: `application/json`
 * `name` (Optional[str]): 新的文件夹名称。
 * `description` (Optional[str]): 新的文件夹描述。
 * `parent_id` (Optional[int]): 新的父文件夹ID。如果为 `None` 或 `0`，则表示设置为顶级文件夹。
 * `order` (Optional[int]): 新的排序值。
 * `linked_folder_type` (Optional[`"note_folder"` | `"collected_content_folder"`]): 如果要更新（或首次设置）软链接类型。
 * `linked_folder_id` (Optional[int]): 如果要更新（或首次设置）软链接ID。
* **响应体**: `schemas.KnowledgeBaseFolderResponse`
 * 结构与 `schemas.KnowledgeBaseFolderResponse` 相同，详见 4.5.6。
* **常见状态码**:
 * `200 OK`: 文件夹更新成功。
 * `400 Bad Request`: 请求参数无效（例如，将自己设为父文件夹，或在普通文件夹中指定软链接字段，或尝试将包含内容的普通文件夹转换为软链接，或软链接文件夹包含禁用媒体类型）。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 知识库文件夹未找到，或不属于该知识库，或当前用户无权访问，或新的父文件夹/链接目标未找到/无权访问。
 * `409 Conflict`: 在当前知识库的相同层级下已存在同名文件夹，或该外部文件夹已被链接到此知识库。
 * `500 Internal Server Error`: 服务器内部错误。

---

##### 4.5.10 删除指定知识库文件夹

* **DELETE** `/knowledge-bases/{kb_id}/folders/{kb_folder_id}`
* **摘要**: 删除指定ID的知识库文件夹。
* **描述**: 用户只能删除自己知识库下的文件夹。
 * **普通文件夹**: 删除普通文件夹将级联删除其下所有的直属文章、文档和子文件夹。
 * **软链接文件夹**: 删除软链接文件夹只会删除该链接记录本身，不会影响被链接的原始笔记文件夹或收藏文件夹中的内容。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 所属知识库的ID。
 * `kb_folder_id` (int): 目标知识库文件夹的唯一ID。
* **请求参数**: 无。
* **响应体**: 无内容 (HTTP 204 No Content)。
* **常见状态码**:
 * `204 No Content`: 文件夹及其关联内容（如果适用）删除成功。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的知识库文件夹未找到，或不属于该知识库，或当前用户无权访问。

---

##### 4.5.11 在指定知识库中创建新文章

* **POST** `/knowledge-bases/{kb_id}/articles/`
* **摘要**: 在指定知识库中创建一篇新的文本知识文章。
* **描述**: 文章内容将被处理并生成嵌入向量，用于后续的智能搜索和问答功能。文章可选择归属某个知识库文件夹。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 文章所属知识库的ID。
* **请求体**: `application/json`
 * `title` (str): 文章标题。
 * `content` (str): 文章的文本内容。
 * `version` (Optional[str]): 文章版本，默认为 `"1.0"`。
 * `tags` (Optional[str]): 文章的标签，以逗号分隔的字符串。
 * `kb_folder_id` (Optional[int]): 文章所属知识库文件夹的ID。如果为 `None` 或 `0`，则表示文章在知识库的根目录下。
* **响应体**: `schemas.KnowledgeArticleResponse`
 * `id` (int): 文章唯一ID。
 * `kb_id` (int): 所属知识库ID。
 * `author_id` (int): 文章作者的用户ID。
 * `title` (str): 文章标题。
 * `content` (str): 文章内容。
 * `version` (Optional[str]): 文章版本。
 * `tags` (Optional[str]): 文章标签。
 * `kb_folder_id` (Optional[int]): 所属知识库文件夹ID。
 * `combined_text` (Optional[str]): 用于AI嵌入的组合文本。
 * `created_at` (datetime): 创建时间 (ISO 8601 格式)。
 * `updated_at` (Optional[datetime]): 最后更新时间 (ISO 8601 格式)。
 * `kb_folder_name` (Optional[str]): 所属知识库文件夹的名称（动态填充，无文件夹则为“未分类”）。
* **常见状态码**:
 * `200 OK`: 文章创建成功。
 * `400 Bad Request`: 请求参数无效（例如，缺少标题或内容，或指定了无效的文件夹ID）。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 所属知识库或指定的知识库文件夹未找到，或当前用户无权访问。
 * `409 Conflict`: 数据冲突，例如可能存在同名文章（取决于具体业务规则）。
 * `500 Internal Server Error`: 服务器内部错误。

---

##### 4.5.12 获取指定知识库的所有文章

* **GET** `/knowledge-bases/{kb_id}/articles/`
* **摘要**: 获取指定知识库下所有知识文章的列表。
* **描述**: 支持按知识库文件夹、文章标题/内容关键词、标签进行过滤，并支持分页。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 知识库的ID。
* **查询参数**:
 * `kb_folder_id` (Optional[int]): 按知识库文件夹ID过滤。如果为 `None` (未提供)，则获取所有文章。传入 `0` 表示专门查询根目录下的文章（其 `kb_folder_id` 为 `NULL`）。
 * `query_str` (Optional[str]): 搜索关键词，将根据文章标题或内容进行模糊匹配。
 * `tag_filter` (Optional[str]): 标签过滤，将对文章的标签进行模糊匹配。
 * `page` (int): 页码，从1开始，默认为 `1`。
 * `page_size` (int): 每页返回的文章数量，默认为 `20` (最大 `100`)。
* **响应体**: `List[schemas.KnowledgeArticleResponse]`
 * 列表项结构与 `schemas.KnowledgeArticleResponse` 相同，详见 4.5.11。
* **常见状态码**:
 * `200 OK`: 成功获取文章列表，即使列表为空。
 * `400 Bad Request`: 提供的文件夹ID或分页参数无效。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 所属知识库或指定的知识库文件夹未找到，或当前用户无权访问。

---

##### 4.5.13 获取指定文章详情

* **GET** `/articles/{article_id}`
* **摘要**: 获取指定ID的知识文章的详细信息。
* **权限**: 需要认证 (JWT Token)。用户只能获取自己拥有的文章详情。
* **路径参数**:
 * `article_id` (int): 目标知识文章的唯一ID。
* **请求参数**: 无。
* **响应体**: `schemas.KnowledgeArticleResponse`
 * 结构与 `schemas.KnowledgeArticleResponse` 相同，详见 4.5.11。
* **常见状态码**:
 * `200 OK`: 成功获取文章详情。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的文章未找到，或者当前用户无权访问该文章。

---

##### 4.5.14 更新指定知识文章

* **PUT** `/knowledge-bases/{kb_id}/articles/{article_id}`
* **摘要**: 更新指定ID的知识文章内容。
* **描述**: 只有文章作者可以更新其文章。更新操作会重新生成文章的组合文本和嵌入向量。支持更改文章所属的知识库文件夹。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 文章所属知识库的ID。
 * `article_id` (int): 目标知识文章的唯一ID。
* **请求体**: `application/json`
 * `title` (Optional[str]): 新的文章标题。
 * `content` (Optional[str]): 新的文章内容。
 * `version` (Optional[str]): 新的文章版本。
 * `tags` (Optional[str]): 新的文章标签。
 * `kb_folder_id` (Optional[int]): 文章所属知识库文件夹的新ID。如果为 `None` 或 `0`，则表示将文章移至知识库的根目录。
* **响应体**: `schemas.KnowledgeArticleResponse`
 * 结构与 `schemas.KnowledgeArticleResponse` 相同，详见 4.5.11。
* **常见状态码**:
 * `200 OK`: 文章更新成功。
 * `400 Bad Request`: 请求参数无效（例如，标题或内容为空，或指定了无效的文件夹ID）。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的文章未找到，或不属于该知识库，或当前用户无权更新该文章；或指定的知识库文件夹未找到/无权访问。
 * `409 Conflict`: 数据冲突。
 * `500 Internal Server Error`: 服务器内部错误。

---

##### 4.5.15 删除指定文章

* **DELETE** `/articles/{article_id}`
* **摘要**: 删除指定ID的知识文章。
* **描述**: 用户只能删除自己拥有的知识文章。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `article_id` (int): 目标知识文章的唯一ID。
* **请求参数**: 无。
* **响应体**: `application/json`
 * `message` (str): success message string, e.g., "Knowledge article deleted successfully"。
* **常见状态码**:
 * `200 OK`: 文章删除成功。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的文章未找到，或者当前用户无权删除该文章。

---

##### 4.5.16 上传新知识文档到知识库

* **POST** `/knowledge-bases/{kb_id}/documents/`
* **摘要**: 上传一个新文档（例如 PDF, DOCX, TXT, 图片文件）到指定知识库。
* **描述**: 本接口不支持直接上传视频文件到知识库。上传成功后，文档内容将进入后台队列进行异步处理（文本提取、分块和嵌入生成）。处理状态可在文档详情中查询。文档可选择归属某个知识库文件夹，但不能上传到软链接文件夹。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 文档所属知识库的ID。
* **请求体**: `multipart/form-data`
 * `file` (File): 要上传的文档文件。支持的 MIME 类型包括：`text/plain` (.txt), `text/markdown` (.md), `application/pdf` (.pdf), `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (.docx), `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `image/bmp`。
 * `kb_folder_id` (Optional[int]): (Form Field) 文档所属知识库文件夹的ID。如果为 `None` 或 `0`，则表示文档在知识库的根目录下。
* **响应体**: `schemas.KnowledgeDocumentResponse`
 * `id` (int): 文档唯一ID。
 * `kb_id` (int): 所属知识库ID。
 * `owner_id` (int): 文件上传者的用户ID。
 * `file_name` (str): 原始文件名。
 * `file_path` (str): 文件在对象存储 (OSS) 中的 URL。
 * `file_type` (Optional[str]): 文件的MIME类型。
 * `status` (Optional[str]): 文档处理状态：`"pending"` (待处理), `"processing"` (处理中), `"completed"` (已完成), `"failed"` (失败)。默认为 `"processing"`。
 * `processing_message` (Optional[str]): 详细的处理状态或错误信息。
 * `total_chunks` (Optional[int]): 文档被分块后的总分块数。
 * `kb_folder_id` (Optional[int]): 所属知识库文件夹ID。
 * `created_at` (datetime): 创建时间 (ISO 8601 格式)。
 * `updated_at` (Optional[datetime]): 最后更新时间 (ISO 8601 格式)。
 * `kb_folder_name` (Optional[str]): 所属知识库文件夹的名称（动态填充，无文件夹则为“未分类”）。
* **常见状态码**:
 * `202 Accepted`: 文件已成功上传到云存储并进入后台处理队列。
 * `400 Bad Request`: 文件类型不支持，或上传了视频文件，或指定了无效/软链接知识库文件夹。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 所属知识库或指定的知识库文件夹未找到，或当前用户无权访问。
 * `500 Internal Server Error`: 文件上传到云存储失败或服务器内部错误。

---

##### 4.5.17 获取知识库下所有知识文档

* **GET** `/knowledge-bases/{kb_id}/documents/`
* **摘要**: 获取指定知识库下所有已上传的知识文档列表。
* **描述**: 支持按知识库文件夹、文档处理状态和文件名关键词进行过滤，并支持分页。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 知识库的ID。
* **查询参数**:
 * `kb_folder_id` (Optional[int]): 按知识库文件夹ID过滤。如果为 `None` (未提供)，则获取所有文档。传入 `0` 表示专门查询根目录下的文档（其 `kb_folder_id` 为 `NULL`）。
 * `status_filter` (Optional[str]): 按处理状态过滤（例如：`"processing"`, `"completed"`, `"failed"`）。
 * `query_str` (Optional[str]): 按关键词搜索文件名进行模糊匹配。
 * `page` (int): 页码，从1开始，默认为 `1`。
 * `page_size` (int): 每页返回的文档数量，默认为 `20` (最大 `100`)。
* **响应体**: `List[schemas.KnowledgeDocumentResponse]`
 * 列表项结构与 `schemas.KnowledgeDocumentResponse` 相同，详见 4.5.16。
* **常见状态码**:
 * `200 OK`: 成功获取文档列表，即使列表为空。
 * `400 Bad Request`: 提供的文件夹ID或分页参数无效。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 所属知识库或指定的知识库文件夹未找到，或当前用户无权访问。

---

##### 4.5.18 获取指定知识文档详情

* **GET** `/knowledge-bases/{kb_id}/documents/{document_id}`
* **摘要**: 获取指定知识库下指定文档的详细信息。
* **权限**: 需要认证 (JWT Token)。用户只能获取自己拥有知识库下的文档详情。
* **路径参数**:
 * `kb_id` (int): 文档所属知识库的ID。
 * `document_id` (int): 目标知识文档的唯一ID。
* **请求参数**: 无。
* **响应体**: `schemas.KnowledgeDocumentResponse`
 * 结构与 `schemas.KnowledgeDocumentResponse` 相同，详见 4.5.16。
* **常见状态码**:
 * `200 OK`: 成功获取文档详情。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的文档未找到，或不属于该知识库，或当前用户无权访问该文档。

---

##### 4.5.19 删除指定知识文档

* **DELETE** `/knowledge-bases/{kb_id}/documents/{document_id}`
* **摘要**: 删除指定知识库下的指定知识文档。
* **描述**: 删除文档将同时级联删除该文档的所有文本块（chunk）数据，并从对象存储 (OSS) 中删除相关联的文件。
* **权限**: 需要认证 (JWT Token)。用户只能删除自己拥有知识库下的文档。
* **路径参数**:
 * `kb_id` (int): 文档所属知识库的ID。
 * `document_id` (int): 目标知识文档的唯一ID。
* **请求参数**: 无。
* **响应体**: `application/json`
 * `message` (str): success message string, e.g., "Knowledge document deleted successfully"。
* **常见状态码**:
 * `200 OK`: 文档及其所有关联内容删除成功。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的文档未找到，或不属于该知识库，或当前用户无权删除该文档。

---

##### 4.5.20 获取知识文档的原始文本内容 (DEBUG)

* **GET** `/knowledge-bases/{kb_id}/documents/{document_id}/content`
* **摘要**: 获取指定知识文档的完整文本内容（仅供调试）。
* **描述**: 该接口用于在文档处理完成后，查看从文档中提取出的原始文本。由于可能返回大量文本，请谨慎使用。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 文档所属知识库的ID。
 * `document_id` (int): 目标知识文档的唯一ID。
* **请求参数**: 无。
* **响应体**: `application/json`
 * `content` (str): 从文档中提取的完整文本内容。
* **常见状态码**:
 * `200 OK`: 成功获取文档文本内容。
 * `400 Bad Request`: 文档处理尚未完成或已失败，暂无内容可返回。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的文档未找到，或不属于该知识库，或当前用户无权访问该文档。

---

##### 4.5.21 获取知识文档文本块列表 (DEBUG)

* **GET** `/knowledge-bases/{kb_id}/documents/{document_id}/chunks`
* **摘要**: 获取指定知识文档的所有文本块列表（仅供调试）。
* **描述**: 该接口用于查看文档被AI模型分块后的具体文本块内容。这些文本块通常用于RAG (Retrieval-Augmented Generation) 等AI应用。只有当文档处理状态为 `"completed"` 时，才能获取文本块。
* **权限**: 需要认证 (JWT Token)。
* **路径参数**:
 * `kb_id` (int): 文档所属知识库的ID。
 * `document_id` (int): 目标知识文档的唯一ID。
* **请求参数**: 无。
* **响应体**: `List[schemas.KnowledgeDocumentChunkResponse]`
 * `id` (int): 文本块唯一ID。
 * `document_id` (int): 所属文档的ID。
 * `owner_id` (int): 文本块所有者的用户ID。
 * `kb_id` (int): 所属知识库的ID。
 * `chunk_index` (int): 文本块在原文档中的顺序索引。
 * `content` (str): 文本块的实际内容。
 * `combined_text` (Optional[str]): 组合文本（如果存在于模型中）。
* **常见状态码**:
 * `200 OK`: 成功获取文本块列表，即使列表为空。
 * `401 Unauthorized`: 未提供或提供了无效的认证凭据。
 * `404 Not Found`: 指定ID的文档未找到，或不属于该知识库，或当前用户无权访问该文档。
 * `422 Unprocessable Entity`: 文档仍在处理中，文本块暂不可用。

---


---

#### 4.6 聊天与群组协作

**4.6.1 创建新的聊天室**

* **API Endpoint:** `POST /chat-rooms/`
* **摘要:** 创建一个新的聊天室。房间创建者将自动成为该聊天室的群主和首位成员。聊天室可以关联到特定的项目或课程。
* **权限:** 需要认证 (JWT Token)。
* **请求体:** `application/json`
 ```json
 {
 "name": "string", // 聊天室名称，必填
 "type": "general", // 聊天室类型，可选值: "project_group", "course_group", "private", "general"，默认为 "general"
 "project_id": null, // 关联的项目ID，可选。如果提供，表示这是一个项目群组，且该项目不能已有关联聊天室
 "course_id": null, // 关联的课程ID，可选。如果提供，表示这是一个课程群组，且该课程不能已有关联聊天室
 "color": null // 聊天室颜色（用于UI显示），可选，例如 "#RRGGBB"
 }
 ```
 * **name** (`str`): 聊天室的名称，最长100字符，必填。
 * **type** (`Literal`): 聊天室的类型。可选值包括: `project_group` (项目群组), `course_group` (课程群组), `private` (私人聊天), `general` (普通群组)。默认为 `general`。
 * **project_id** (`int`, 可选): 如果聊天室是项目群组，则指定关联的项目ID。如果项目已经关联了其他聊天室，将会报错。
 * **course_id** (`int`, 可选): 如果聊天室是课程群组，则指定关联的课程ID。如果课程已经关联了其他聊天室，将会报错。
 * **color** (`str`, 可选): 聊天室在UI上显示的颜色标识，例如十六进制颜色码。
* **响应体:** `schemas.ChatRoomResponse`
 ```json
 {
 "name": "string",
 "type": "general",
 "project_id": null,
 "course_id": null,
 "color": null,
 "id": 0,
 "creator_id": 0,
 "members_count": 0,
 "last_message": {
 "sender": "string",
 "content": "string"
 },
 "unread_messages_count": 0,
 "online_members_count": 0,
 "created_at": "2023-10-27T10:00:00Z",
 "updated_at": "2023-10-27T10:00:00Z"
 }
 ```
 * **id** (`int`): 聊天室的唯一ID。
 * **creator_id** (`int`): 创建者的用户ID。
 * **members_count** (`int`): 当前活跃成员的数量。
 * **last_message** (`Dict[str, Any]`, 可选): 聊天室的最后一条消息概要，包含 `sender` (发送者姓名) 和 `content` (消息内容片段)。
 * **unread_messages_count** (`int`): 当前用户在该聊天室的未读消息数量 (当前为模拟值)。
 * **online_members_count** (`int`): 当前在线成员数量 (当前为模拟值)。
 * **created_at** (`datetime`): 聊天室创建时间 (ISO 8601 格式)。
 * **updated_at** (`datetime`, 可选): 聊天室最后更新时间 (ISO 8601 格式)。
 * (其他字段同请求体中的定义)
* **常见状态码:**
 * `200 OK`: 聊天室创建成功。
 * `400 Bad Request`: 请求参数无效 (例如，关联的项目/课程已存在聊天室)。
 * `401 Unauthorized`: 未认证用户。
 * `409 Conflict`: 聊天室名称冲突或者关联的项目/课程ID已经与另一个聊天室关联。
 * `500 Internal Server Error`: 服务器内部错误。

---

**4.6.2 获取当前用户所属的所有聊天室**

* **API Endpoint:** `GET /chatrooms/`
* **摘要:** 获取当前用户作为创建者或活跃成员所参与的所有聊天室列表。
* **权限:** 需要认证 (JWT Token)。
* **请求参数:**
 * **room_type** (`str`, 可选): 按聊天室类型过滤。可选值与 `/chat-rooms/` API 的 `type` 字段一致。
* **响应体:** `List[schemas.ChatRoomResponse]` (参见 `4.6.1` 的响应体结构)
* **常见状态码:**
 * `200 OK`: 成功获取聊天室列表。
 * `401 Unauthorized`: 未认证用户。

---

**4.6.3 获取指定聊天室详情**

* **API Endpoint:** `GET /chatrooms/{room_id}`
* **摘要:** 获取指定 ID 的聊天室的详细信息。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主、活跃成员或系统管理员才能查看。
* **请求参数:**
 * **room_id** (`int`): 要查询的聊天室的唯一 ID。
* **响应体:** `schemas.ChatRoomResponse` (参见 `4.6.1` 的响应体结构)
* **常见状态码:**
 * `200 OK`: 成功获取聊天室详情。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权查看该聊天室。
 * `404 Not Found`: 聊天室不存在。

---

**4.6.4 更新指定聊天室**

* **API Endpoint:** `PUT /chatrooms/{room_id}/`
* **摘要:** 更新指定 ID 聊天室的名称、类型、关联项目/课程或颜色。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主才能更新。
* **请求参数:**
 * **room_id** (`int`): 要更新的聊天室的唯一 ID。
* **请求体:** `application/json`
 ```json
 {
 "name": "string", // 聊天室名称，可选
 "type": "general", // 聊天室类型，可选
 "project_id": null, // 关联的项目ID，可选
 "course_id": null, // 关联的课程ID，可选
 "color": "#RRGGBB" // 聊天室颜色，可选
 }
 ```
 * **name** (`str`, 可选): 聊天室的新名称。
 * **type** (`Literal`, 可选): 聊天室的新类型。可选值同创建时。
 * **project_id** (`int`, 可选): 重新关联的项目 ID。如果提供，会检查项目是否已有关联且不是当前聊天室，否则报错。
 * **course_id** (`int`, 可选): 重新关联的课程 ID。如果提供，会检查课程是否已有关联且不是当前聊天室，否则报错。
 * **color** (`str`, 可选): 聊天室的新颜色。
* **响应体:** `schemas.ChatRoomResponse` (参见 `4.6.1` 的响应体结构)
* **常见状态码:**
 * `200 OK`: 聊天室更新成功。
 * `400 Bad Request`: 请求参数无效。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权更新该聊天室。
 * `404 Not Found`: 聊天室不存在。
 * `409 Conflict`: 聊天室名称冲突或关联的项目/课程已与另一个聊天室关联。
 * `500 Internal Server Error`: 服务器内部错误。

---

**4.6.5 删除指定聊天室**

* **API Endpoint:** `DELETE /chatrooms/{room_id}`
* **摘要:** 删除指定 ID 的聊天室。此操作会级联删除所有关联的聊天消息、成员记录和入群申请。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主或系统管理员才能删除。
* **请求参数:**
 * **room_id** (`int`): 要删除的聊天室的唯一 ID。
* **响应体:** `No Content` (无响应体)
* **常见状态码:**
 * `204 No Content`: 聊天室删除成功。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权删除该聊天室。
 * `404 Not Found`: 聊天室不存在。
 * `409 Conflict`: 删除失败，可能存在数据关联问题。

---

**4.6.6 获取指定聊天室的所有成员列表**

* **API Endpoint:** `GET /chatrooms/{room_id}/members`
* **摘要:** 获取指定 ID 聊天室的所有成员的列表，包含成员的姓名和角色。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主、聊天室管理员或系统管理员才能查看。
* **请求参数:**
 * **room_id** (`int`): 要查询成员的聊天室的唯一 ID。
* **响应体:** `List[schemas.ChatRoomMemberResponse]`
 ```json
 [
 {
 "room_id": 0,
 "member_id": 0,
 "role": "member",
 "status": "active",
 "last_read_at": null,
 "id": 0,
 "joined_at": "2023-10-27T10:00:00Z",
 "member_name": "string"
 }
 ]
 ```
 * **id** (`int`): 成员记录的唯一 ID。
 * **room_id** (`int`): 所属聊天室的 ID。
 * **member_id** (`int`): 成员的用户 ID。
 * **role** (`Literal`): 成员在聊天室中的角色。可选值: `admin` (管理员), `member` (普通成员), `king` (群主)。
 * **status** (`Literal`): 成员状态。可选值: `active` (活跃), `banned` (被踢出/禁用), `left` (已离开)。
 * **last_read_at** (`datetime`, 可选): 成员最后阅读消息的时间 (ISO 8601 格式)。
 * **joined_at** (`datetime`): 成员加入聊天室的时间 (ISO 8601 格式)。
 * **member_name** (`str`, 可选): 成员的用户姓名。
* **常见状态码:**
 * `200 OK`: 成功获取成员列表。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权查看该聊天室的成员列表。
 * `404 Not Found`: 聊天室不存在。

---

**4.6.7 设置聊天室成员的角色**

* **API Endpoint:** `PUT /chat-rooms/{room_id}/members/{member_id}/set-role`
* **摘要:** 设置指定聊天室中某个成员的角色 (例如提升为管理员或降级为普通成员)。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主可以执行此操作。
* **请求参数:**
 * **room_id** (`int`): 目标聊天室的唯一 ID。
 * **member_id** (`int`): 要设置角色的成员的用户 ID。
* **请求体:** `application/json`
 ```json
 {
 "role": "admin" // 或 "member"
 }
 ```
 * **role** (`Literal`): 要设置的新角色。可选值: `admin` (管理员) 或 `member` (普通成员)。
* **响应体:** `schemas.ChatRoomMemberResponse` (参见 `4.6.6` 的响应体结构)
* **常见状态码:**
 * `200 OK`: 成员角色更新成功。
 * `400 Bad Request`: 请求参数无效 (例如，尝试设置无效的角色类型，或群主尝试修改自己的角色)。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权设置成员角色。
 * `404 Not Found`: 聊天室或目标成员不存在。
 * `500 Internal Server Error`: 服务器内部错误。

---

**4.6.8 从聊天室移除成员**

* **API Endpoint:** `DELETE /chat-rooms/{room_id}/members/{member_id}`
* **摘要:** 从指定聊天室中移除一个成员 (可以是用户自己离开，或群主/管理员踢出)。
* **权限:** 需要认证 (JWT Token)。
 * 用户可以移除自己 (除了群主)。
 * 群主可以移除任何成员。
 * 聊天室管理员可以移除普通成员 (不能移除群主或其他管理员)。
 * 系统管理员可以移除任何成员。
* **请求参数:**
 * **room_id** (`int`): 目标聊天室的唯一 ID。
 * **member_id** (`int`): 要移除的成员的用户 ID。
* **响应体:** `No Content` (无响应体)
* **常见状态码:**
 * `204 No Content`: 成员移除成功。
 * `400 Bad Request`: 请求无效 (例如，群主尝试自己离开群聊)。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权移除该成员。
 * `404 Not Found`: 聊天室或成员不存在/不是活跃成员。

---

**4.6.9 向指定聊天室发起入群申请**

* **API Endpoint:** `POST /chat-rooms/{room_id}/join-request`
* **摘要:** 当前用户向指定 ID 的聊天室发起入群申请。
* **权限:** 需要认证 (JWT Token)。
* **请求参数:**
 * **room_id** (`int`): 目标聊天室的唯一 ID。
* **请求体:** `application/json`
 ```json
 {
 "room_id": 0, // 必须与路径中的 room_id 匹配
 "reason": "string" // 入群申请理由，可选
 }
 ```
 * **room_id** (`int`): 目标聊天室的 ID (必须与路径参数 `room_id` 匹配)。
 * **reason** (`str`, 可选): 用户提交的入群理由。
* **响应体:** `schemas.ChatRoomJoinRequestResponse`
 ```json
 {
 "id": 0,
 "room_id": 0,
 "requester_id": 0,
 "reason": "string",
 "status": "pending",
 "requested_at": "2023-10-27T10:00:00Z",
 "processed_by_id": null,
 "processed_at": null
 }
 ```
 * **id** (`int`): 申请记录的唯一 ID。
 * **room_id** (`int`): 目标聊天室的 ID。
 * **requester_id** (`int`): 申请者的用户 ID。
 * **reason** (`str`, 可选): 入群申请理由。
 * **status** (`str`): 申请状态，默认为 `pending` (待处理)。
 * **requested_at** (`datetime`): 申请提交时间 (ISO 8601 格式)。
 * **processed_by_id** (`int`, 可选): 处理该申请的用户 ID。
 * **processed_at** (`datetime`, 可选): 申请处理时间 (ISO 8601 格式)。
* **常见状态码:**
 * `200 OK`: 申请提交成功。
 * `400 Bad Request`: 请求参数无效 (例如，请求体中的 `room_id` 不匹配，或用户已经是创建者/成员)。
 * `401 Unauthorized`: 未认证用户。
 * `404 Not Found`: 聊天室不存在。
 * `409 Conflict`: 用户已存在待处理的申请。
 * `500 Internal Server Error`: 服务器内部错误。

---

**4.6.10 获取指定聊天室的入群申请列表**

* **API Endpoint:** `GET /chat-rooms/{room_id}/join-requests`
* **摘要:** 获取指定 ID 聊天室的入群申请列表。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主、聊天室管理员或系统管理员才能查看。
* **请求参数:**
 * **room_id** (`int`): 目标聊天室的唯一 ID。
 * **status_filter** (`str`, 可选): 按申请状态过滤。可选值: `pending` (待处理，默认), `approved` (已批准), `rejected` (已拒绝)。
* **响应体:** `List[schemas.ChatRoomJoinRequestResponse]` (参见 `4.6.9` 的响应体结构)
* **常见状态码:**
 * `200 OK`: 成功获取入群申请列表。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权查看该聊天室的入群申请。
 * `404 Not Found`: 聊天室不存在。

---

**4.6.11 处理入群申请**

* **API Endpoint:** `POST /chat-rooms/join-requests/{request_id}/process`
* **摘要:** 处理指定 ID 的入群申请 (批准或拒绝)。如果申请被批准，申请者将成为聊天室的活跃成员。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主、聊天室管理员或系统管理员才能处理。
* **请求参数:**
 * **request_id** (`int`): 要处理的入群申请的唯一 ID。
* **请求体:** `application/json`
 ```json
 {
 "status": "approved", // 或 "rejected"
 "process_message": "string" // 审批附言，可选
 }
 ```
 * **status** (`Literal`): 处理结果状态。可选值: `approved` (批准) 或 `rejected` (拒绝)。
 * **process_message** (`str`, 可选): 审批时的附言，例如拒绝理由。
* **响应体:** `schemas.ChatRoomJoinRequestResponse` (参见 `4.6.9` 的响应体结构)
* **常见状态码:**
 * `200 OK`: 申请处理成功。
 * `400 Bad Request`: 请求参数无效 (例如，申请已处理或状态异常)。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权处理该申请。
 * `404 Not Found`: 入群申请不存在。
 * `409 Conflict`: 处理申请时发生数据冲突。
 * `500 Internal Server Error`: 服务器内部错误。

---

**4.6.12 在指定聊天室发送新消息**

* **API Endpoint:** `POST /chatrooms/{room_id}/messages/`
* **摘要:** 在指定 ID 的聊天室发送一条新的聊天消息。支持发送文本、图片、文件和视频等多种类型消息。成功发送消息会奖励积分并检查成就。
* **权限:** 需要认证 (JWT Token)。只有聊天室的群主或活跃成员才能发送消息。
* **请求参数:**
 * **room_id** (`int`): 目标聊天室的唯一 ID。
* **请求体:** `multipart/form-data`
 * **content_text** (`str`, 可选): 消息的文本内容。当 `message_type` 为 `text` 时 **必填**。
 * **message_type** (`Literal`): 消息类型。可选值包括: `text` (文本，默认), `image` (图片), `file` (文件), `video` (视频), `system_notification` (系统通知)。
 * **media_url** (`str`, 可选): 媒体文件的 OSS URL 或外部链接。当 `message_type` 为 `image`, `file`, `video` 时 **必填**。
 * **file** (`file`, 可选): 上传文件、图片或视频文件。如果提供此字段，后端将处理文件上传到 OSS，并覆盖 `media_url` 和推断 `message_type`。
* **响应体:** `schemas.ChatMessageResponse`
 ```json
 {
 "content_text": "string",
 "message_type": "text",
 "media_url": null,
 "id": 0,
 "room_id": 0,
 "sender_id": 0,
 "sent_at": "2023-10-27T10:00:00Z",
 "sender_name": "string"
 }
 ```
 * **id** (`int`): 消息的唯一 ID。
 * **room_id** (`int`): 消息所属聊天室的 ID。
 * **sender_id** (`int`): 消息发送者的用户 ID。
 * **sent_at** (`datetime`): 消息发送时间 (ISO 8601 格式)。
 * **sender_name** (`str`, 可选): 消息发送者的姓名。
 * (其他字段同请求体中的定义)
* **常见状态码:**
 * `200 OK`: 消息发送成功。
 * `400 Bad Request`: 请求参数无效 (例如，消息内容或媒体URL不符合类型要求)。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权在该聊天室发送消息 (例如，不是活跃成员)。
 * `404 Not Found`: 聊天室不存在。
 * `500 Internal Server Error`: 服务器内部错误 (例如，文件上传到云存储失败)。

---

**4.6.13 获取指定聊天室的历史消息**

* **API Endpoint:** `GET /chatrooms/{room_id}/messages/`
* **摘要:** 获取指定 ID 聊天室的所有历史消息列表。
* **权限:** 需要认证 (JWT Token)。所有活跃成员 (包括群主和管理员) 以及系统管理员都可以查看。
* **请求参数:**
 * **room_id** (`int`): 目标聊天室的唯一 ID。
 * **limit** (`int`, 可选): 返回的最大消息数量，默认为 50。
 * **offset** (`int`, 可选): 查询的偏移量，用于分页，默认为 0。
* **响应体:** `List[schemas.ChatMessageResponse]` (参见 `4.6.12` 的响应体结构)
* **常见状态码:**
 * `200 OK`: 成功获取历史消息列表。
 * `401 Unauthorized`: 未认证用户。
 * `403 Forbidden`: 用户无权查看该聊天室的历史消息。
 * `404 Not Found`: 聊天室不存在。

---

**4.6.14 WebSocket 聊天室接口**

* **API Endpoint:** `WS /ws/chat/{room_id}`
* **摘要:** 用于实时聊天通信的 WebSocket 连接接口。客户端通过此连接发送和接收聊天消息。
* **权限:** 需要认证 (JWT Token)。认证令牌通过 URL 查询参数 `token` 传递。只有聊天室的群主或活跃成员才能连接。
* **连接参数:**
 * **room_id** (`int`): 要连接的聊天室的唯一 ID (作为路径参数)。
 * **token** (`str`): 用户的 JWT 认证令牌 (作为查询参数)。
* **消息格式 (客户端发送):** `JSON`
 ```json
 {
 "content": "string" // 消息文本内容
 }
 ```
* **消息格式 (服务器发送):** `JSON` (示例，具体内容可能更丰富)
 ```json
 {
 "type": "chat_message",
 "id": 0,
 "room_id": 0,
 "sender_id": 0,
 "sender_name": "string",
 "content": "string",
 "sent_at": "2023-10-27T10:00:00Z"
 }
 ```
 * **type** (`str`): 消息类型，例如 "chat_message"。
 * **id** (`int`): 消息的唯一 ID。
 * **room_id** (`int`): 消息所属聊天室的 ID。
 * **sender_id** (`int`): 消息发送者的用户 ID。
 * **sender_name** (`str`): 消息发送者的姓名。
 * **content** (`str`): 消息的文本内容。
 * **sent_at** (`datetime`): 消息发送时间 (ISO 8601 格式)。
* **常见连接/错误码:**
 * `101 Switching Protocols`: 成功建立 WebSocket 连接。
 * `1008 Policy Violation`: 认证失败 (JWT无效、过期或用户无权访问)。
 * `1003 Unsupported Data`: 聊天室不存在。
 * `1011 Internal Error`: 服务器内部错误导致连接中断。

---


#### 4.7 论坛与社区互动

**4.7.1 发布新论坛话题 (POST /forum/topics/)**
**摘要**: 发布一个新论坛话题。可选择关联分享平台其他内容（如笔记、课程等），或直接上传文件作为附件。
**权限**: 需要认证 (JWT Token)。
**请求体**: `multipart/form-data`
* **title** (str, 可选): 话题标题。
* **content** (str): 话题内容。
* **shared_item_type** (str, 可选): 如果分享平台内部内容，记录其类型。可选值：`note`, `daily_record`, `course`, `project`, `knowledge_article`, `knowledge_base`, `collected_content`。
* **shared_item_id** (int, 可选): 如果分享平台内部内容，记录其ID。
* **tags** (str, 可选): 话题标签，多个标签以逗号分隔，例如："学习,AI,讨论"。
* **media_url** (str, 可选): 附件的外部链接URL。如果上传 `file`，此字段将由后端填充。
* **media_type** (str, 可选): 附件媒体类型。当上传 `file` 或提供 `media_url` 时为必填。可选值：`image`, `video`, `file`。
* **file** (file, 可选): 要上传的文件、图片或视频。当 `media_type` 为 `image`, `video`, `file` 且无 `media_url` 时，可上传此文件。

**请求体注意事项**:
* `content` 不能为空。
* `shared_item_type` 和 `shared_item_id` 必须同时提供或同时为空。
* `shared_item_type/id` 和 `media_url` / `file` 不能同时提供，即不能同时分享内部内容和直接上传/链接外部媒体/文件。
* 如果提供 `media_url` 但不上传 `file`，则 `media_type` 必须与提供的 `media_url` 类型语义匹配。
* 如果上传 `file`，则 `media_type` 必须为 `image`、`video` 或 `file`。`original_filename` 和 `media_size_bytes` 将由后端根据上传文件自动填充。

**响应体**: `schemas.ForumTopicResponse`
* **id** (int): 话题ID。
* **owner_id** (int): 发布者用户ID。
* **title** (str): 话题标题。
* **content** (str): 话题内容。
* **shared_item_type** (str, 可选): 分享内容类型。
* **shared_item_id** (int, 可选): 分享内容ID。
* **tags** (str, 可选): 话题标签。
* **media_url** (str, 可选): 附件URL。
* **media_type** (str, 可选): 附件媒体类型。
* **original_filename** (str, 可选): 原始上传文件名。
* **media_size_bytes** (int, 可选): 媒体文件大小。
* **likes_count** (int): 点赞数。
* **comments_count** (int): 评论数。
* **views_count** (int): 浏览数。
* **combined_text** (str, 可选): 用于AI模型嵌入的组合文本。
* **created_at** (datetime): 创建时间 (ISO 8601 格式)。
* **updated_at** (datetime, 可选): 最后更新时间 (ISO 8601 格式)。
* **owner_name** (str, 可选): 发布者姓名。
* **is_liked_by_current_user** (bool, 可选): 当前用户是否已点赞该话题。

**常见状态码**:
* `200 OK` (发布成功)
* `400 Bad Request` (请求数据校验失败，例如内容或媒体类型错误，或共享项与媒体同时提供)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (关联的共享项不存在)
* `409 Conflict` (可能存在数据冲突，例如并发创建)
* `500 Internal Server Error` (文件上传到OSS失败，或数据库操作异常)

---

**4.7.2 获取论坛话题列表 (GET /forum/topics/)**
**摘要**: 获取论坛话题列表，支持关键词、标签和分享类型过滤。
**权限**: 需要认证 (JWT Token)。

**请求参数**:
* **query_str** (str, 可选): 搜索关键词，将匹配话题标题或内容。
* **tag** (str, 可选): 话题标签，支持模糊匹配。
* **shared_type** (str, 可选): 分享类型过滤。可选值同 `POST /forum/topics/` 中的 `shared_item_type`。
* **limit** (int, 可选): 返回的最大话题数量，默认为10。
* **offset** (int, 可选): 查询的偏移量，默认为0，用于分页。

**响应体**: `List[schemas.ForumTopicResponse]`
(详细字段同 **4.7.1 发布新论坛话题** 的响应体 `schemas.ForumTopicResponse`，但为列表形式)。

**常见状态码**:
* `200 OK` (成功获取话题列表)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `500 Internal Server Error` (数据库操作异常)

---

**4.7.3 获取指定论坛话题详情 (GET /forum/topics/{topic_id})**
**摘要**: 获取指定ID的论坛话题详情。每次访问会增加话题的浏览数。
**权限**: 需要认证 (JWT Token)。

**请求参数**:
* **topic_id** (int, 路径参数): 要获取详情的话题ID。

**响应体**: `schemas.ForumTopicResponse`
(详细字段同 **4.7.1 发布新论坛话题** 的响应体 `schemas.ForumTopicResponse`)。

**常见状态码**:
* `200 OK` (成功获取话题详情)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (指定话题ID不存在)
* `500 Internal Server Error` (数据库操作异常)

---

**4.7.4 更新指定论坛话题 (PUT /forum/topics/{topic_id})**
**摘要**: 更新指定ID的论坛话题内容。只有话题发布者能更新。支持替换附件文件。更新后会重新生成 `combined_text` 和 `embedding`。
**权限**: 需要认证 (JWT Token)。只有话题发布者可以更新。

**请求参数**:
* **topic_id** (int, 路径参数): 要更新的话题ID。

**请求体**: `multipart/form-data`
* **title** (str, 可选): 话题标题。
* **content** (str, 可选): 话题内容。
* **shared_item_type** (str, 可选): 如果分享平台内部内容，记录其类型。可选值同 `POST /forum/topics/` 中的 `shared_item_type`。
* **shared_item_id** (int, 可选): 如果分享平台内部内容，记录其ID。
* **tags** (str, 可选): 话题标签，多个标签以逗号分隔。
* **media_url** (str, 可选): 新的附件外部链接URL。如果上传 `file`，此字段将被忽略。传入 `null` 可清除现有媒体URL。
* **media_type** (str, 可选): 新的附件媒体类型。当上传 `file` 或提供新的 `media_url` 时为必填且必须与文件类型一致。传入 `null` 可清除现有媒体类型。可选值：`image`, `video`, `file`。
* **file** (file, 可选): 要上传的新文件、图片或视频，将替换当前话题的任何现有附件。

**请求体注意事项**:
* 如果 `media_url`、`media_type` 或 `file` 中有参数被设置，将覆盖旧的附件信息。如果 `media_url` 或 `media_type` 传入 `null`，将清除话题的附件。
* 如果上传 `file`，它将替换所有旧的附件，并且 `media_url`, `media_type`, `original_filename`, `media_size_bytes` 将根据上传的文件类型和其OSS URL重新设置。
* `title` 不能为空。`content` 不能为空，除非话题包含媒体附件且 `content` 字段被显式设置为 `null`。
* `shared_item_type` 和 `shared_item_id` 必须同时提供或同时为空。不能同时指定 `shared_item_type/id` 和 `media_url`/`file`。
* `parent_comment_id` 不允许修改。

**响应体**: `schemas.ForumTopicResponse`
(详细字段同 **4.7.1 发布新论坛话题** 的响应体 `schemas.ForumTopicResponse`)。

**常见状态码**:
* `200 OK` (更新成功)
* `400 Bad Request` (请求数据校验失败，例如 `title` 为空，或媒体类型与文件冲突)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `403 Forbidden` (用户不是话题发布者，无权操作)
* `404 Not Found` (指定话题ID不存在)
* `409 Conflict` (可能存在数据冲突，例如并发更新)
* `500 Internal Server Error` (文件上传到OSS失败，或数据库操作异常)

---

**4.7.5 删除指定论坛话题 (DELETE /forum/topics/{topic_id})**
**摘要**: 删除指定ID的论坛话题及其所有评论和点赞。如果话题关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。只有话题发布者能删除。
**权限**: 需要认证 (JWT Token)。只有话题发布者可以删除。

**请求参数**:
* **topic_id** (int, 路径参数): 要删除的话题ID。

**响应体**: `application/json`
* **message** (str): 删除成功消息。

**常见状态码**:
* `200 OK` (删除成功)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `403 Forbidden` (用户不是话题发布者，无权删除)
* `404 Not Found` (指定话题ID不存在)
* `500 Internal Server Error` (OSS文件删除失败或数据库操作异常)

---

**4.7.6 为论坛话题添加评论 (POST /forum/topics/{topic_id}/comments/)**
**摘要**: 为指定论坛话题添加评论。可选择回复某个已有评论（楼中楼），或直接上传文件作为附件。
**权限**: 需要认证 (JWT Token)。
**请求体**: `multipart/form-data`
* **content** (str): 评论文本内容。
* **parent_comment_id** (int, 可选): 如果是回复某个评论，则为该评论的ID（实现楼中楼）。
* **media_url** (str, 可选): 附件的外部链接URL。如果上传 `file`，此字段将由后端填充。
* **media_type** (str, 可选): 附件媒体类型。当上传 `file` 或提供 `media_url` 时为必填。可选值：`image`, `video`, `file`。
* **file** (file, 可选): 要上传的文件、图片或视频。当 `media_type` 为 `image`, `video`, `file` 且无 `media_url` 时，可上传此文件。

**请求体注意事项**:
* `content` 和 `media_url` （或 `file`）至少需要提供一个。
* 如果提供 `media_url` 但不上传 `file`，则 `media_type` 必须与提供的 `media_url` 类型语义匹配。
* 如果上传 `file`，则 `media_type` 必须为 `image`、`video` 或 `file`。`original_filename` 和 `media_size_bytes` 将由后端根据上传文件自动填充。

**响应体**: `schemas.ForumCommentResponse`
* **id** (int): 评论ID。
* **topic_id** (int): 所属话题ID。
* **owner_id** (int): 发布者用户ID。
* **content** (str): 评论文本内容。
* **parent_comment_id** (int, 可选): 父评论ID。
* **media_url** (str, 可选): 附件URL。
* **media_type** (str, 可选): 附件媒体类型。
* **original_filename** (str, 可选): 原始上传文件名。
* **media_size_bytes** (int, 可选): 媒体文件大小。
* **likes_count** (int): 点赞数。
* **created_at** (datetime): 创建时间 (ISO 8601 格式)。
* **updated_at** (datetime, 可选): 最后更新时间 (ISO 8601 格式)。
* **owner_name** (str, 可选): 发布者姓名。
* **is_liked_by_current_user** (bool, 可选): 当前用户是否已点赞该评论。

**常见状态码**:
* `200 OK` (评论发布成功)
* `400 Bad Request` (请求数据校验失败，例如内容或媒体类型错误)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (指定话题ID或父评论ID不存在)
* `500 Internal Server Error` (文件上传到OSS失败，或数据库操作异常)

---

**4.7.7 获取论坛话题的评论列表 (GET /forum/topics/{topic_id}/comments/)**
**摘要**: 获取指定论坛话题的评论列表。可过滤以获取特定评论的回复（楼中楼）。
**权限**: 需要认证 (JWT Token)。

**请求参数**:
* **topic_id** (int, 路径参数): 要获取评论的话题ID。
* **parent_comment_id** (int, 可选): 如果指定，只返回该父评论下的子评论 (即楼中楼)。如果为空，则返回所有一级评论。
* **limit** (int, 可选): 返回的最大评论数量，默认为50。
* **offset** (int, 可选): 查询的偏移量，默认为0，用于分页。

**响应体**: `List[schemas.ForumCommentResponse]`
(详细字段同 **4.7.6 为论坛话题添加评论** 的响应体 `schemas.ForumCommentResponse`，但为列表形式)。

**常见状态码**:
* `200 OK` (成功获取评论列表)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (指定话题ID不存在)
* `500 Internal Server Error` (数据库操作异常)

---

**4.7.8 更新指定论坛评论 (PUT /forum/comments/{comment_id})**
**摘要**: 更新指定ID的论坛评论。只有评论发布者能更新。支持替换附件文件。
**权限**: 需要认证 (JWT Token)。只有评论发布者可以更新。

**请求参数**:
* **comment_id** (int, 路径参数): 要更新的评论ID。

**请求体**: `multipart/form-data`
* **content** (str, 可选): 评论文本内容。传入 `null` 可清除文本内容（如果存在媒体附件）。
* **media_url** (str, 可选): 新的附件外部链接URL。如果上传 `file`，此字段将被忽略。传入 `null` 可清除现有媒体URL。
* **media_type** (str, 可选): 新的附件媒体类型。当上传 `file` 或提供新的 `media_url` 时为必填且必须与文件类型一致。传入 `null` 可清除现有媒体类型。可选值：`image`, `video`, `file`。
* **file** (file, 可选): 要上传的新文件、图片或视频，将替换当前评论的任何现有附件。

**请求体注意事项**:
* `content` 和 `media_url` （或 `file`）至少需要提供一个有效值。如果 `content` 设置为 `null`，则必须有媒体附件。
* 如果 `media_url`、`media_type` 或 `file` 中有参数被设置，将覆盖旧的附件信息。如果 `media_url` 或 `media_type` 传入 `null`，将清除评论的附件。
* 父评论 `parent_comment_id` 不允许修改。

**响应体**: `schemas.ForumCommentResponse`
(详细字段同 **4.7.6 为论坛话题添加评论** 的响应体 `schemas.ForumCommentResponse`)。

**常见状态码**:
* `200 OK` (更新成功)
* `400 Bad Request` (请求数据校验失败，例如 `content` 为空且无媒体，或媒体类型与文件冲突)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `403 Forbidden` (用户不是评论发布者，无权操作)
* `404 Not Found` (指定评论ID不存在)
* `500 Internal Server Error` (文件上传到OSS失败，或数据库操作异常)

---

**4.7.9 删除指定论坛评论 (DELETE /forum/comments/{comment_id})**
**摘要**: 删除指定ID的论坛评论。如果评论有子评论，则会级联删除所有回复。如果评论关联了文件或媒体（通过URL指向OSS），将同时删除OSS上的文件。只有评论发布者能删除。
**权限**: 需要认证 (JWT Token)。只有评论发布者可以删除。

**请求参数**:
* **comment_id** (int, 路径参数): 要删除的评论ID。

**响应体**: `application/json`
* **message** (str): 删除成功消息。

**常见状态码**:
* `200 OK` (删除成功)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `403 Forbidden` (用户不是评论发布者，无权删除)
* `404 Not Found` (指定评论ID不存在)
* `500 Internal Server Error` (OSS文件删除失败或数据库操作异常)

---

**4.7.10 点赞论坛话题或评论 (POST /forum/likes/)**
**摘要**: 点赞一个论坛话题或评论。必须提供 `topic_id` 或 `comment_id` 中的一个。同一用户不能重复点赞同一项。点赞成功后，为被点赞的话题/评论的作者奖励积分，并检查其成就。
**权限**: 需要认证 (JWT Token)。
**请求体**: `application/json`
```json
{
  "topic_id": 123,  // 点赞话题，提供话题ID
  "comment_id": 456 // 点赞评论，提供评论ID
}
```
**请求体注意事项**:
* `topic_id` 和 `comment_id` 中必须且只能提供一个。

**响应体**: `schemas.ForumLikeResponse`
* **id** (int): 点赞记录ID。
* **owner_id** (int): 点赞者用户ID。
* **topic_id** (int, 可选): 如果是话题点赞，为话题ID。
* **comment_id** (int, 可选): 如果是评论点赞，为评论ID。
* **created_at** (datetime): 点赞时间 (ISO 8601 格式)。

**常见状态码**:
* `200 OK` (点赞成功)
* `400 Bad Request` (请求参数错误，例如同时提供 `topic_id` 和 `comment_id`)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (话题或评论不存在)
* `409 Conflict` (已点赞该项)
* `500 Internal Server Error` (数据库操作异常)

---

**4.7.11 取消点赞论坛话题或评论 (DELETE /forum/likes/)**
**摘要**: 取消点赞一个论坛话题或评论。必须提供 `topic_id` 或 `comment_id` 中的一个。
**权限**: 需要认证 (JWT Token)。
**请求体**: `application/json`
```json
{
  "topic_id": 123,  // 取消点赞话题，提供话题ID
  "comment_id": 456 // 取消点赞评论，提供评论ID
}
```
**请求体注意事项**:
* `topic_id` 和 `comment_id` 中必须且只能提供一个。

**响应体**: `application/json`
* **message** (str): 取消点赞成功消息。

**常见状态码**:
* `200 OK` (取消点赞成功)
* `400 Bad Request` (请求参数错误)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (未找到该用户对该项的点赞记录)
* `500 Internal Server Error` (数据库操作异常)

---

**4.7.12 关注一个用户 (POST /forum/follow/)**
**摘要**: 允许当前用户关注另一个用户。
**权限**: 需要认证 (JWT Token)。
**请求体**: `application/json`
```json
{
  "followed_id": 789 // 要关注的用户ID
}
```
**请求体注意事项**:
* 不能关注自己。

**响应体**: `schemas.UserFollowResponse`
* **id** (int): 关注关系ID。
* **follower_id** (int): 关注者用户ID。
* **followed_id** (int): 被关注者用户ID。
* **created_at** (datetime): 关注时间 (ISO 8601 格式)。

**常见状态码**:
* `200 OK` (关注成功)
* `400 Bad Request` (请求参数错误，例如关注自己)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (被关注用户不存在)
* `409 Conflict` (已关注该用户)
* `500 Internal Server Error` (数据库操作异常)

---

**4.7.13 取消关注一个用户 (DELETE /forum/unfollow/)**
**摘要**: 允许当前用户取消关注另一个用户。
**权限**: 需要认证 (JWT Token)。
**请求体**: `application/json`
```json
{
  "followed_id": 789 // 要取消关注的用户ID
}
```

**响应体**: `application/json`
* **message** (str): 取消关注成功消息。

**常见状态码**:
* `200 OK` (取消关注成功)
* `400 Bad Request` (请求参数错误)
* `401 Unauthorized` (未提供或无效的JWT令牌)
* `404 Not Found` (未找到该用户对该用户的关注记录)
* `500 Internal Server Error` (数据库操作异常)

---
