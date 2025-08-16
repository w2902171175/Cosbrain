
### 3.1 项目管理

#### 3.1.1 创建新项目

* **HTTP 方法与路径:** `POST /projects/`
* **摘要:** 创建一个新的项目。项目创建者将根据项目信息（包括标题、描述、所需技能、角色、地理位置等）生成或更新AI嵌入向量，用于智能匹配。
* **权限:** 需要认证 (JWT Token)。
* **请求体:** `application/json`
 * **Schema:** `schemas.ProjectCreate`
 * **字段:**
 * `title` (string, **必填**): 项目标题。
 * `description` (string, 可选): 项目详细描述。
 * `required_skills` (List of `SkillWithProficiency`, 可选): 项目所需的技能列表，每个技能包含 `name` (string) 和 `level` (Literal["初窥门径", "登堂入室", "融会贯通", "炉火纯青"])。
 * `required_roles` (List of string, 可选): 项目所需角色的列表，例如 `["前端开发", "后端开发", "UI/UX 设计师"]`。
 * `keywords` (string, 可选): 项目关键词，用于搜索。
 * `project_type` (string, 可选): 项目类型，例如 "科研项目", "毕业设计", "创新创业项目"。
 * `expected_deliverables` (string, 可选): 预期交付物描述。
 * `contact_person_info` (string, 可选): 联系人信息，例如姓名、联系方式。
 * `learning_outcomes` (string, 可选): 学生参与项目可获得的学习成果。
 * `team_size_preference` (string, 可选): 团队规模偏好，例如 "3-5人", "不限"。
 * `project_status` (string, 可选): 项目当前状态，例如 "招募中", "进行中", "已完成"。
 * `start_date` (datetime, 可选): 项目开始日期，ISO 8601 格式，例如 `"2023-01-01T00:00:00Z"`。
 * `end_date` (datetime, 可选): 项目结束日期，ISO 8601 格式。
 * `estimated_weekly_hours` (integer, 可选): 项目估计每周所需投入小时数。
 * `location` (string, 可选): 项目所在地理位置，例如 `"广州大学城"`, `"珠海横琴新区"`, `"琶洲"`, `"线上"`。
* **响应体:** `application/json`
 * **Schema:** `schemas.ProjectResponse`
 * **字段:**
 * `id` (integer): 新创建项目的唯一ID。
 * `title` (string): 项目标题。
 * `description` (string): 项目详细描述。
 * `required_skills` (List of `SkillWithProficiency`): 项目所需的技能列表。
 * `required_roles` (List of string): 项目所需角色的列表。
 * `keywords` (string): 项目关键词。
 * `project_type` (string): 项目类型。
 * `expected_deliverables` (string): 预期交付物描述。
 * `contact_person_info` (string): 联系人信息。
 * `learning_outcomes` (string): 学习成果。
 * `team_size_preference` (string): 团队规模偏好。
 * `project_status` (string): 项目当前状态。
 * `start_date` (datetime): 项目开始日期。
 * `end_date` (datetime): 项目结束日期。
 * `estimated_weekly_hours` (integer): 项目估计每周所需投入小时数。
 * `location` (string): 项目所在地理位置。
 * `combined_text` (string): 用于AI模型嵌入的组合文本。
 * `created_at` (datetime): 项目创建时间。
 * `updated_at` (datetime, 可选): 项目最后更新时间。
* **常见状态码:**
 * `200 OK`: 项目创建成功。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `409 Conflict`: 项目创建失败，可能存在数据冲突（例如，将来如果项目标题要求唯一）。
 * `500 Internal Server Error`: 服务器内部错误，例如AI嵌入生成失败。

#### 3.1.2 获取所有项目列表

* **HTTP 方法与路径:** `GET /projects/`
* **摘要:** 获取平台中所有项目的概要列表。
* **权限:** 无需认证（当前实现）。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `List[schemas.ProjectResponse]`
 * **字段:** 返回一个项目列表，每个项目结构同 `schemas.ProjectResponse`。
* **常见状态码:**
 * `200 OK`: 成功获取项目列表。

#### 3.1.3 获取指定项目详情

* **HTTP 方法与路径:** `GET /projects/{project_id}`
* **摘要:** 获取指定ID的项目的详细信息。
* **权限:** 无需认证（当前实现）。
* **路径参数:**
 * `project_id` (integer, **必填**): 要获取的项目ID。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `schemas.ProjectResponse`
 * **字段:** 见 `3.1.1 创建新项目` 的响应体。
* **常见状态码:**
 * `200 OK`: 成功获取项目详情。
 * `404 Not Found`: 指定ID的项目未找到。

#### 3.1.4 更新指定项目

* **HTTP 方法与路径:** `PUT /projects/{project_id}`
* **摘要:** 更新指定ID的项目的详细信息。只有项目创建者或系统管理员能够更新项目信息。当项目状态更新为“已完成”时，项目创建者会获得相应的积分奖励，并触发成就检查。更新后，项目内容将重新生成AI嵌入向量。
* **权限:** 需要认证 (JWT Token)。仅限项目创建者或系统管理员。
* **路径参数:**
 * `project_id` (integer, **必填**): 要更新的项目ID。
* **请求体:** `application/json`
 * **Schema:** `schemas.ProjectUpdate`
 * **字段:** 所有字段均为可选，仅更新传入的字段。字段定义同 `schemas.ProjectCreate`，但均为可选。
* **响应体:** `application/json`
 * **Schema:** `schemas.ProjectResponse`
 * **字段:** 见 `3.1.1 创建新项目` 的响应体。
* **常见状态码:**
 * `200 OK`: 项目更新成功。
 * `400 Bad Request`: 请求数据无效，例如格式错误或尝试不合法操作。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `403 Forbidden`: 当前用户无权更新此项目。
 * `404 Not Found`: 指定ID的项目未找到。
 * `409 Conflict`: 更新失败，可能存在数据冲突。
 * `500 Internal Server Error`: 服务器内部错误，例如数据库操作失败或AI嵌入生成失败。

### 3.2 项目成员与申请

#### 3.2.1 学生申请加入项目

* **HTTP 方法与路径:** `POST /projects/{project_id}/apply`
* **摘要:** 允许学生向指定项目提交加入申请。如果学生已经是项目成员或已提交待处理的申请，则无法重复申请。
* **权限:** 需要认证 (JWT Token)。
* **路径参数:**
 * `project_id` (integer, **必填**): 目标项目ID。
* **请求体:** `application/json`
 * **Schema:** `schemas.ProjectApplicationCreate`
 * **字段:**
 * `message` (string, 可选): 申请留言，说明为什么想加入项目。
* **响应体:** `application/json`
 * **Schema:** `schemas.ProjectApplicationResponse`
 * **字段:**
 * `id` (integer): 申请记录的唯一ID。
 * `project_id` (integer): 所申请的项目ID。
 * `student_id` (integer): 申请学生的ID。
 * `status` (Literal["pending", "approved", "rejected"]): 申请状态，默认 `pending`。
 * `message` (string, 可选): 申请留言。
 * `applied_at` (datetime): 申请提交时间。
 * `processed_at` (datetime, 可选): 申请处理时间。
 * `processed_by_id` (integer, 可选): 审批者（学生）的ID。
 * `applicant_name` (string, 可选): 申请者的姓名（由后端填充）。
 * `applicant_email` (string, 可选): 申请者的邮箱（由后端填充）。
 * `processor_name` (string, 可选): 审批者（学生）的姓名（由后端填充）。
* **常见状态码:**
 * `200 OK`: 申请提交成功。
 * `400 Bad Request`: 已是项目成员或请求数据无效。
 * `401 Unauthorized`: 未认证。
 * `404 Not Found`: 项目未找到。
 * `409 Conflict`: 已有待处理的申请或已被拒绝的申请（防止重复提交）。
 * `500 Internal Server Error`: 服务器内部错误。

#### 3.2.2 获取项目所有申请列表

* **HTTP 方法与路径:** `GET /projects/{project_id}/applications`
* **摘要:** 获取指定项目的所有加入申请列表。只有项目创建者或系统管理员能够查看。
* **权限:** 需要认证 (JWT Token)。仅限项目创建者或系统管理员。
* **路径参数:**
 * `project_id` (integer, **必填**): 目标项目ID。
* **查询参数:**
 * `status_filter` (Literal["pending", "approved", "rejected"], 可选): 筛选申请状态。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `List[schemas.ProjectApplicationResponse]`
 * **字段:** 返回一个申请列表，每个申请结构同 `schemas.ProjectApplicationResponse`。
* **常见状态码:**
 * `200 OK`: 成功获取申请列表。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权查看此项目的申请。
 * `404 Not Found`: 项目未找到。

#### 3.2.3 处理项目申请

* **HTTP 方法与路径:** `POST /projects/applications/{application_id}/process`
* **摘要:** 项目创建者或系统管理员可以批准或拒绝一个项目加入申请。如果申请被批准，申请者将成为项目成员。
* **权限:** 需要认证 (JWT Token)。仅限项目创建者或系统管理员。
* **路径参数:**
 * `application_id` (integer, **必填**): 要处理的申请ID。
* **请求体:** `application/json`
 * **Schema:** `schemas.ProjectApplicationProcess`
 * **字段:**
 * `status` (Literal["approved", "rejected"], **必填**): 处理结果，`approved`（批准）或 `rejected`（拒绝）。
 * `process_message` (string, 可选): 审批附言，例如拒绝原因。
* **响应体:** `application/json`
 * **Schema:** `schemas.ProjectApplicationResponse`
 * **字段:** 见 `3.2.1 学生申请加入项目` 的响应体。
* **常见状态码:**
 * `200 OK`: 申请处理成功。
 * `400 Bad Request`: 申请状态异常（例如已处理过）或请求数据无效。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权处理此申请。
 * `404 Not Found`: 申请未找到或关联项目不存在。
 * `409 Conflict`: 处理失败，可能存在数据冲突（例如，用户已是成员）。
 * `500 Internal Server Error`: 服务器内部错误。

#### 3.2.4 获取项目成员列表

* **HTTP 方法与路径:** `GET /projects/{project_id}/members`
* **摘要:** 获取指定项目的所有活跃成员列表。项目创建者、项目活跃成员或系统管理员可以查看。
* **权限:** 需要认证 (JWT Token)。仅限项目创建者、项目活跃成员或系统管理员。
* **路径参数:**
 * `project_id` (integer, **必填**): 目标项目ID。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `List[schemas.ProjectMemberResponse]`
 * **字段:**
 * `id` (integer): 成员关系的唯一ID。
 * `project_id` (integer): 所属项目ID。
 * `student_id` (integer): 成员学生的ID。
 * `role` (Literal["admin", "member"]): 成员角色，`admin`（项目管理员）或 `member`（普通成员）。
 * `status` (Literal["active", "banned", "left"]): 成员状态，`active`（活跃）。
 * `joined_at` (datetime): 成员加入时间。
 * `member_name` (string, 可选): 成员的姓名（由后端填充）。
 * `member_email` (string, 可选): 成员的邮箱（由后端填充）。
* **常见状态码:**
 * `200 OK`: 成功获取成员列表。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权查看此项目的成员。
 * `404 Not Found`: 项目未找到。

### 3.3 课程管理

#### 3.3.1 创建新课程

* **HTTP 方法与路径:** `POST /courses/`
* **摘要:** 创建一个新的课程。课程信息（包括标题、描述、讲师、分类、所需技能等）将用于AI智能匹配。
* **权限:** 需要认证 (JWT Token)。仅限系统管理员。
* **请求体:** `application/json`
 * **Schema:** `schemas.CourseCreate`
 * **字段:**
 * `title` (string, **必填**): 课程标题。
 * `description` (string, 可选): 课程详细描述。
 * `instructor` (string, 可选): 讲师姓名。
 * `category` (string, 可选): 课程分类。
 * `total_lessons` (integer, 可选): 总课时数，默认0。
 * `avg_rating` (float, 可选): 平均评分，默认0.0。
 * `cover_image_url` (string, 可选): 课程封面图片的URL链接。
 * `required_skills` (List of `SkillWithProficiency`, 可选): 学习该课程所需基础技能列表及熟练度，或课程教授的技能。
* **响应体:** `application/json`
 * **Schema:** `schemas.CourseResponse`
 * **字段:**
 * `id` (integer): 新创建课程的唯一ID。
 * `title` (string): 课程标题。
 * `description` (string): 课程详细描述。
 * `instructor` (string): 讲师姓名。
 * `category` (string): 课程分类。
 * `total_lessons` (integer): 总课时数。
 * `avg_rating` (float): 平均评分。
 * `cover_image_url` (string): 课程封面图片的URL链接。
 * `required_skills` (List of `SkillWithProficiency`): 课程所需/教授技能。
 * `combined_text` (string): 用于AI模型嵌入的组合文本。
 * `created_at` (datetime): 课程创建时间。
 * `updated_at` (datetime, 可选): 课程最后更新时间。
* **常见状态码:**
 * `200 OK`: 课程创建成功。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权创建课程（非管理员）。
 * `409 Conflict`: 课程创建失败，可能存在数据冲突（例如，课程标题可能需要唯一）。
 * `500 Internal Server Error`: 服务器内部错误。

#### 3.3.2 获取所有课程列表

* **HTTP 方法与路径:** `GET /courses/`
* **摘要:** 获取平台上所有课程的概要列表。
* **权限:** 无需认证。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `List[schemas.CourseResponse]`
 * **字段:** 返回一个课程列表，每个课程结构同 `schemas.CourseResponse`。
* **常见状态码:**
 * `200 OK`: 成功获取课程列表。

#### 3.3.3 获取指定课程详情

* **HTTP 方法与路径:** `GET /courses/{course_id}`
* **摘要:** 获取指定ID的课程的详细信息。
* **权限:** 无需认证。
* **路径参数:**
 * `course_id` (integer, **必填**): 要获取的课程ID。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `schemas.CourseResponse`
 * **字段:** 见 `3.3.1 创建新课程` 的响应体。
* **常见状态码:**
 * `200 OK`: 成功获取课程详情。
 * `404 Not Found`: 指定ID的课程未找到。

#### 3.3.4 更新指定课程

* **HTTP 方法与路径:** `PUT /courses/{course_id}`
* **摘要:** 更新指定ID的课程的详细信息。只有系统管理员能够更新课程信息。更新后，课程内容将重新生成AI嵌入向量。
* **权限:** 需要认证 (JWT Token)。仅限系统管理员。
* **路径参数:**
 * `course_id` (integer, **必填**): 要更新的课程ID。
* **请求体:** `application/json`
 * **Schema:** `schemas.CourseUpdate`
 * **字段:** 所有字段均为可选，仅更新传入的字段。字段定义同 `schemas.CourseBase`，但均为可选。
* **响应体:** `application/json`
 * **Schema:** `schemas.CourseResponse`
 * **字段:** 见 `3.3.1 创建新课程` 的响应体。
* **常见状态码:**
 * `200 OK`: 课程更新成功。
 * `400 Bad Request`: 请求数据无效。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权更新此课程。
 * `404 Not Found`: 指定ID的课程未找到。
 * `409 Conflict`: 更新失败，可能存在数据冲突。
 * `500 Internal Server Error`: 服务器内部错误。

### 3.4 课程参与与材料

#### 3.4.1 用户报名课程

* **HTTP 方法与路径:** `POST /courses/{course_id}/enroll`
* **摘要:** 允许当前认证用户报名（注册）一门课程。如果用户已经报名，则返回已有的报名信息，不会重复创建。
* **权限:** 需要认证 (JWT Token)。
* **路径参数:**
 * `course_id` (integer, **必填**): 要报名的课程ID。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `schemas.UserCourseResponse`
 * **字段:**
 * `student_id` (integer): 报名的学生ID。
 * `course_id` (integer): 报名的课程ID。
 * `progress` (float): 当前学习进度，默认 0.0。
 * `status` (string): 学习状态，默认 `"registered"`。
 * `last_accessed` (datetime): 最后访问时间。
 * `created_at` (datetime): 报名创建时间。
* **常见状态码:**
 * `200 OK`: 课程报名成功或已报名，返回现有报名信息。
 * `401 Unauthorized`: 未认证。
 * `404 Not Found`: 课程未找到。
 * `409 Conflict`: 报名失败，可能存在并发冲突。
 * `500 Internal Server Error`: 服务器内部错误。

#### 3.4.2 更新当前用户课程学习进度和状态

* **HTTP 方法与路径:** `PUT /users/me/courses/{course_id}`
* **摘要:** 更新当前登录用户指定课程的学习进度和状态。当课程状态更新为“已完成”时，用户会获得相应的积分奖励，并触发成就检查。
* **权限:** 需要认证 (JWT Token)。
* **路径参数:**
 * `course_id` (integer, **必填**): 要更新进度的课程ID。
* **请求体:** `application/json`
 * **Schema:** `Dict[str, Any]` (动态字典，包含以下可选字段)
 * **字段:**
 * `progress` (float, 可选): 学习进度，例如 `0.5` 代表 50%。
 * `status` (string, 可选): 学习状态，例如 `"in_progress"`, `"completed"`。
* **响应体:** `application/json`
 * **Schema:** `schemas.UserCourseResponse`
 * **字段:** 见 `3.4.1 用户报名课程` 的响应体。
* **常见状态码:**
 * `200 OK`: 课程进度和状态更新成功。
 * `400 Bad Request`: 请求数据无效。
 * `401 Unauthorized`: 未认证。
 * `404 Not Found`: 用户未注册该课程或课程未找到。
 * `500 Internal Server Error`: 服务器内部错误。

#### 3.4.3 为指定课程上传新材料（文件或链接）

* **HTTP 方法与路径:** `POST /courses/{course_id}/materials/`
* **摘要:** 为指定课程上传新的材料。支持上传文件（如PDF、文档、图片、视频）或提供外部链接或纯文本内容。
* **权限:** 需要认证 (JWT Token)。仅限系统管理员。
* **路径参数:**
 * `course_id` (integer, **必填**): 目标课程ID。
* **请求体:** `multipart/form-data`
 * **Schema:** 组合了文件 (`file`) 和 JSON 字符串 (`material_data`)
 * **字段:**
 * `file` (file, 可选): 要上传的文件。如果 `material_data.type` 为 `"file"`, `"image"`, `"video"`，则此处应上传文件。支持的文件类型包括常见文档（如TXT, PDF, DOCX）和图片、视频。
 * `material_data` (application/json **string**, **必填**): 一个JSON字符串，包含 `schemas.CourseMaterialCreate` 模型的字段。
 * `title` (string, **必填**): 材料标题。
 * `type` (Literal["file", "link", "text", "video", "image"], **必填**): 材料类型。
 * 如果 `type` 为 `"file"`, `"image"`, `"video"`，则必须同时提供 `file` 参数。
 * 如果 `type` 为 `"link"`，则 `url` 字段必填。
 * 如果 `type` 为 `"text"`，则 `content` 字段必填。
 * `url` (string, 可选): 外部链接URL。当 `type` 为 `"link"` 时必填。当 `type` 为 `"file"`, `"image"`, `"video"` 时，此字段可由后端填充为OSS URL。
 * `content` (string, 可选): 文本内容。当 `type` 为 `"text"` 时必填，否则可作为补充描述。
 * `original_filename` (string, 可选): （仅用于 `file` 类型）原始上传文件名。
 * `file_type` (string, 可选): （仅用于 `file` 类型）文件MIME类型。
 * `size_bytes` (integer, 可选): （仅用于 `file` 类型）文件大小（字节）。
* **响应体:** `application/json`
 * **Schema:** `schemas.CourseMaterialResponse`
 * **字段:**
 * `id` (integer): 材料唯一ID。
 * `course_id` (integer): 所属课程ID。
 * `title` (string): 材料标题。
 * `type` (Literal["file", "link", "text", "video", "image"]): 材料类型。
 * `file_path` (string, 可选): OSS文件URL（如果类型是 `"file"`, `"image"`, `"video"`）。
 * `original_filename` (string, 可选): 原始上传文件名。
 * `file_type` (string, 可选): 文件MIME类型。
 * `size_bytes` (integer, 可选): 文件大小（字节）。
 * `url` (string, 可选): 外部链接URL（如果类型是 `"link"`）。
 * `content` (string, 可选): 文本内容或描述。
 * `combined_text` (string, 可选): 用于AI模型嵌入的组合文本。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (datetime, 可选): 更新时间。
* **常见状态码:**
 * `200 OK`: 材料创建成功。
 * `400 Bad Request`: 请求数据无效，例如缺少必填字段或文件类型不匹配。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权操作（非管理员）。
 * `404 Not Found`: 课程未找到。
 * `409 Conflict`: 课程下已存在同名材料。
 * `500 Internal Server Error`: 服务器内部错误，例如OSS上传失败或AI嵌入生成失败。

#### 3.4.4 获取指定课程的所有材料列表

* **HTTP 方法与路径:** `GET /courses/{course_id}/materials/`
* **摘要:** 获取指定课程的所有材料列表。
* **权限:** 无需认证（当前实现，未来可根据课程访问权限调整）。
* **路径参数:**
 * `course_id` (integer, **必填**): 目标课程ID。
* **查询参数:**
 * `type_filter` (Literal["file", "link", "text"], 可选): 筛选材料类型。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `List[schemas.CourseMaterialResponse]`
 * **字段:** 返回一个材料列表，每个材料结构同 `schemas.CourseMaterialResponse`。
* **常见状态码:**
 * `200 OK`: 成功获取材料列表。
 * `404 Not Found`: 课程未找到。

#### 3.4.5 获取指定课程材料详情

* **HTTP 方法与路径:** `GET /courses/{course_id}/materials/{material_id}`
* **摘要:** 获取指定课程下指定ID的材料的详细信息。
* **权限:** 无需认证（当前实现，未来可根据课程访问权限调整）。
* **路径参数:**
 * `course_id` (integer, **必填**): 材料所属的课程ID。
 * `material_id` (integer, **必填**): 要获取的材料ID。
* **请求体:** 无。
* **响应体:** `application/json`
 * **Schema:** `schemas.CourseMaterialResponse`
 * **字段:** 见 `3.4.3 为指定课程上传新材料` 的响应体。
* **常见状态码:**
 * `200 OK`: 成功获取材料详情。
 * `404 Not Found`: 材料未找到或不属于该课程。

#### 3.4.6 更新指定课程材料

* **HTTP 方法与路径:** `PUT /courses/{course_id}/materials/{material_id}`
* **摘要:** 更新指定课程下指定ID的材料信息。只有系统管理员能够更新。支持替换文件、更改内容或更改材料类型。更新后会重新生成用于AI嵌入的组合文本和嵌入向量。
* **权限:** 需要认证 (JWT Token)。仅限系统管理员。
* **路径参数:**
 * `course_id` (integer, **必填**): 材料所属的课程ID。
 * `material_id` (integer, **必填**): 要更新的材料ID。
* **请求体:** `multipart/form-data`
 * **Schema:** 组合了文件 (`file`) 和 JSON 字符串 (`material_data`)
 * **字段:**
 * `file` (file, 可选): 可选，上传新文件以替换旧的文件。如果提供新文件，`material_data` 中 `type` 最好指定为 `"file"`, `"image"`, `"video"`。
 * `material_data` (application/json **string**, **必填**): 一个JSON字符串，包含 `schemas.CourseMaterialUpdate` 模型的字段。
 * `title` (string, 可选): 材料标题。
 * `type` (Literal["file", "link", "text", "video", "image"], 可选): 材料类型。更改类型会清除不适用字段。
 * `url` (string, 可选): 外部链接URL。如果提供新链接且 `type` 为 `"link"`，则更新。
 * `content` (string, 可选): 文本内容。如果提供新文本且 `type` 为 `"text"`，则更新。
 * `original_filename` (string, 可选): （仅用于 `file` 类型）原始上传文件名。
 * `file_type` (string, 可选): （仅用于 `file` 类型）文件MIME类型。
 * `size_bytes` (integer, 可选): （仅用于 `file` 类型）文件大小（字节）。
* **响应体:** `application/json`
 * **Schema:** `schemas.CourseMaterialResponse`
 * **字段:** 见 `3.4.3 为指定课程上传新材料` 的响应体。
* **常见状态码:**
 * `200 OK`: 材料更新成功。
 * `400 Bad Request`: 请求数据无效，例如类型转换冲突，或缺少必填字段（如类型为“link”但未提供URL）。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权操作（非管理员）。
 * `404 Not Found`: 材料未找到或不属于该课程。
 * `409 Conflict`: 材料更新失败，例如同一课程下材料标题冲突。
 * `500 Internal Server Error`: 服务器内部错误，例如OSS文件操作失败或AI嵌入生成失败。

#### 3.4.7 删除指定课程材料

* **HTTP 方法与路径:** `DELETE /courses/{course_id}/materials/{material_id}`
* **摘要:** 删除指定课程下指定ID的材料。如果材料是文件类型且存储在OSS上，将同时删除OSS上的文件。
* **权限:** 需要认证 (JWT Token)。仅限系统管理员。
* **路径参数:**
 * `course_id` (integer, **必填**): 材料所属的课程ID。
 * `material_id` (integer, **必填**): 要删除的材料ID。
* **请求体:** 无。
* **响应体:** 无。
* **常见状态码:**
 * `204 No Content`: 材料已成功删除。
 * `401 Unauthorized`: 未认证。
 * `403 Forbidden`: 当前用户无权操作（非管理员）。
 * `404 Not Found`: 材料未找到或不属于该课程。
 * `500 Internal Server Error`: 服务器内部错误，例如OSS文件删除失败。

---
