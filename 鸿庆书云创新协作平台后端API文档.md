本文档详细描述了鸿庆书云创新协作平台后端API的各个接口、其请求参数和响应体结构。

## **目录**

1. **认证与用户管理**
 * 1.1 `POST /register` 用户注册
 * 1.2 `POST /token` 用户登录并获取JWT令牌
 * 1.3 `GET /users/me` 获取当前登录用户详情
 * 1.4 `PUT /users/me` 更新当前登录用户详情
 * 1.5 `GET /students/` 获取所有学生列表 (管理员专用)
 * 1.6 `GET /students/{student_id}` 获取指定学生详情 (管理员专用)
 * 1.7 `PUT /admin/users/{user_id}/set-admin` 【管理员专用】设置系统管理员权限

2. **项目管理与推荐**
 * 2.1 `POST /projects/` 创建新项目
 * 2.2 `GET /projects/` 获取所有项目列表
 * 2.3 `GET /projects/{project_id}` 获取指定项目详情
 * 2.4 `PUT /projects/{project_id}` 更新指定项目
 * 2.5 `GET /recommend/projects/{student_id}` 为指定学生推荐项目
 * 2.6 `GET /projects/{project_id}/match-students` 为指定项目推荐学生

3. **课程管理与推荐**
 * 3.1 `POST /courses/` 创建新课程 (管理员专用)
 * 3.2 `GET /courses/` 获取所有课程列表
 * 3.3 `GET /courses/{course_id}` 获取指定课程详情
 * 3.4 `PUT /courses/{course_id}` 更新指定课程 (管理员专用)
 * 3.5 `GET /recommend/courses/{student_id}` 为指定学生推荐课程

4. **课程材料管理**
 * 4.1 `POST /courses/{course_id}/materials/` 为指定课程上传新材料（文件或链接） (管理员专用)
 * 4.2 `GET /courses/{course_id}/materials/` 获取指定课程的所有材料列表
 * 4.3 `GET /courses/{course_id}/materials/{material_id}` 获取指定课程材料详情
 * 4.4 `PUT /courses/{course_id}/materials/{material_id}` 更新指定课程材料 (管理员专用)
 * 4.5 `DELETE /courses/{course_id}/materials/{material_id}` 删除指定课程材料 (管理员专用)

5. **核心AI功能**
 * 5.1 `POST /ai/qa` AI智能问答 (通用、RAG或工具调用)
 * 5.2 `POST /search/semantic` 智能语义搜索
 * 5.3 `GET /llm/available-models` 获取可配置的LLM服务商及模型列表

6. **第三方AI服务配置管理**
 * 6.1 `POST /users/me/llm-config` 更新当前用户LLM配置
 * 6.2 `POST /mcp-configs/` 创建新的MCP配置
 * 6.3 `GET /mcp-configs/` 获取当前用户所有MCP服务配置
 * 6.4 `PUT /mcp-configs/{config_id}` 更新指定MCP配置
 * 6.5 `DELETE /mcp-configs/{config_id}` 删除指定MCP服务配置
 * 6.6 `POST /mcp-configs/{config_id}/check-status` 检查指定MCP服务的连通性
 * 6.7 `GET /llm/mcp-available-tools` 获取智库聊天可用的MCP工具列表
 * 6.8 `POST /search-engine-configs/` 创建新的搜索引擎配置
 * 6.9 `GET /search-engine-configs/` 获取当前用户所有搜索引擎配置
 * 6.10 `GET /search-engine-configs/{config_id}` 获取指定搜索引擎配置详情
 * 6.11 `PUT /search-engine-configs/{config_id}` 更新指定搜索引擎配置
 * 6.12 `DELETE /search-engine-configs/{config_id}` 删除指定搜索引擎配置
 * 6.13 `POST /search-engine-configs/{config_id}/check-status` 检查指定搜索引擎的连通性
 * 6.14 `POST /users/me/tts_configs` 为当前用户创建新的TTS配置
 * 6.15 `GET /users/me/tts_configs` 获取当前用户的所有TTS配置
 * 6.16 `GET /users/me/tts_configs/{config_id}` 获取指定TTS配置详情
 * 6.17 `PUT /users/me/tts_configs/{config_id}` 更新指定TTS配置
 * 6.18 `DELETE /users/me/tts_configs/{config_id}` 删除指定TTS配置
 * 6.19 `PUT /users/me/tts_configs/{config_id}/set_active` 设置指定TTS配置为激活状态

7. **随手记录管理**
 * 7.1 `POST /daily-records/` 创建新随手记录
 * 7.2 `GET /daily-records/` 获取当前用户所有随手记录
 * 7.3 `GET /daily-records/{record_id}` 获取指定随手记录详情
 * 7.4 `PUT /daily-records/{record_id}` 更新指定随手记录
 * 7.5 `DELETE /daily-records/{record_id}` 删除指定随手记录

8. **文件夹与收藏管理**
 * 8.1 `POST /folders/` 创建新文件夹
 * 8.2 `GET /folders/` 获取当前用户所有文件夹
 * 8.3 `GET /folders/{folder_id}` 获取指定文件夹详情
 * 8.4 `PUT /folders/{folder_id}` 更新指定文件夹
 * 8.5 `DELETE /folders/{folder_id}` 删除指定文件夹
 * 8.6 `POST /collections/` 创建新收藏内容
 * 8.7 `GET /collections/` 获取当前用户所有收藏内容
 * 8.8 `GET /collections/{content_id}` 获取指定收藏内容详情
 * 8.9 `PUT /collections/{content_id}` 更新指定收藏内容
 * 8.10 `DELETE /collections/{content_id}` 删除指定收藏内容

9. **知识库与文章、文档管理**
 * 9.1 `POST /knowledge-bases/` 创建新知识库
 * 9.2 `GET /knowledge-bases/` 获取当前用户所有知识库
 * 9.3 `GET /knowledge-bases/{kb_id}` 获取指定知识库详情
 * 9.4 `PUT /knowledge-bases/{kb_id}` 更新指定知识库
 * 9.5 `DELETE /knowledge-bases/{kb_id}` 删除指定知识库
 * 9.6 `POST /knowledge-bases/{kb_id}/articles/` 在指定知识库中创建新文章
 * 9.7 `GET /knowledge-bases/{kb_id}/articles/` 获取指定知识库的所有文章
 * 9.8 `GET /articles/{article_id}` 获取指定文章详情
 * 9.9 `PUT /articles/{article_id}` 更新指定文章
 * 9.10 `DELETE /articles/{article_id}` 删除指定文章
 * 9.11 `POST /knowledge-bases/{kb_id}/documents/` 上传新知识文档到知识库
 * 9.12 `GET /knowledge-bases/{kb_id}/documents/` 获取知识库下所有知识文档
 * 9.13 `GET /knowledge-bases/{kb_id}/documents/{document_id}` 获取指定知识文档详情
 * 9.14 `DELETE /knowledge-bases/{kb_id}/documents/{document_id}` 删除指定知识文档
 * 9.15 `GET /knowledge-bases/{kb_id}/documents/{document_id}/content` 获取知识文档的原始文本内容 (DEBUG)
 * 9.16 `GET /knowledge-bases/{kb_id}/documents/{document_id}/chunks` 获取知识文档的所有文本块列表 (DEBUG)

10. **聊天室与消息、社交功能**
 * 10.1 `POST /chat-rooms/` 创建新的聊天室
 * 10.2 `GET /chatrooms/` 获取当前用户所属的所有聊天室
 * 10.3 `GET /chatrooms/{room_id}` 获取指定聊天室详情
 * 10.4 `PUT /chatrooms/{room_id}/` 更新指定聊天室
 * 10.5 `DELETE /chatrooms/{room_id}` 删除指定聊天室（仅限群主或系统管理员）
 * 10.6 `GET /chatrooms/{room_id}/members` 获取指定聊天室的所有成员列表
 * 10.7 `PUT /chat-rooms/{room_id}/members/{member_id}/set-role` 设置聊天室成员的角色（管理员/普通成员）
 * 10.8 `DELETE /chat-rooms/{room_id}/members/{member_id}` 从聊天室移除成员（踢出或离开）
 * 10.9 `POST /chat-rooms/{room_id}/join-request` 向指定聊天室发起入群申请
 * 10.10 `GET /chat-rooms/{room_id}/join-requests` 获取指定聊天室的入群申请列表
 * 10.11 `POST /chat-rooms/join-requests/{request_id}/process` 处理入群申请 (批准或拒绝)
 * 10.12 `POST /chatrooms/{room_id}/messages/` 在指定聊天室发送新消息
 * 10.13 `GET /chatrooms/{room_id}/messages/` 获取指定聊天室的历史消息
 * 10.14 `POST /forum/topics/` 发布新论坛话题
 * 10.15 `GET /forum/topics/` 获取论坛话题列表
 * 10.16 `GET /forum/topics/{topic_id}` 获取指定论坛话题详情
 * 10.17 `PUT /forum/topics/{topic_id}` 更新指定论坛话题
 * 10.18 `DELETE /forum/topics/{topic_id}` 删除指定论坛话题
 * 10.19 `POST /forum/topics/{topic_id}/comments/` 为论坛话题添加评论
 * 10.20 `GET /forum/topics/{topic_id}/comments/` 获取论坛话题的评论列表
 * 10.21 `PUT /forum/comments/{comment_id}` 更新指定论坛评论
 * 10.22 `DELETE /forum/comments/{comment_id}` 删除指定论坛评论
 * 10.23 `POST /forum/likes/` 点赞论坛话题或评论
 * 10.24 `DELETE /forum/likes/` 取消点赞论坛话题或评论
 * 10.25 `POST /forum/follow/` 关注一个用户
 * 10.26 `DELETE /forum/unfollow/` 取消关注一个用户

11. **成就与积分**
 * 11.1 `POST /admin/achievements/definitions` 【管理员专用】创建新的成就定义
 * 11.2 `GET /achievements/definitions` 获取所有成就定义（可供所有用户查看）
 * 11.3 `GET /achievements/definitions/{achievement_id}` 获取指定成就定义详情
 * 11.4 `PUT /admin/achievements/definitions/{achievement_id}` 【管理员专用】更新指定成就定义
 * 11.5 `DELETE /admin/achievements/definitions/{achievement_id}` 【管理员专用】删除指定成就定义
 * 11.6 `GET /users/me/points` 获取当前用户积分余额和上次登录时间
 * 11.7 `GET /users/me/points/history` 获取当前用户积分交易历史
 * 11.8 `GET /users/me/achievements` 获取当前用户已获得的成就列表
 * 11.9 `POST /admin/points/reward` 【管理员专用】为指定用户手动发放/扣除积分


12. **仪表盘与系统监控**
 * 12.1 `GET /dashboard/summary` 获取首页工作台概览数据
 * 12.2 `GET /dashboard/projects` 获取当前用户参与的项目卡片列表
 * 12.3 `GET /dashboard/courses` 获取当前用户学习的课程卡片列表
 * 12.4 `GET /health` 健康检查

---

## **基本概念与公共字段**

* **Pydantic 模型**: API 请求和响应体均使用 Pydantic 模型进行数据验证和序列化。
* **认证**: 大多数需要用户信息的操作都需要有效的 JWT Bearer Token。认证流程请参阅 `POST /token`。Token需放在 `Authorization` 请求头中，格式为 `Bearer <your_token_here>`。
* **权限**:
 * **认证用户**: 任何已登录用户。
 * **创建者/所有者**: 资源的创建者或拥有者。
 * **管理员**: `is_admin` 为 `True` 的系统管理员。
* **时间戳**: 通常以 ISO 8601 格式 (`YYYY-MM-DDTHH:MM:SS.ffffffZ`) 返回。
* **`Optional[Type]`**: 表示该字段是可选的。
* **`Literal[...]`**: 表示该字段的值必须是给定列表中的一个。
* `**id**`: (int) 资源的唯一标识符。
* `**created_at**`: (datetime) 资源创建时间。
* `**updated_at**`: (datetime) 资源最后更新时间。
* `**combined_text**`: (str) 用于AI嵌入的组合文本字段，包含资源的多个关键文本信息。
* `**embedding**`: (List[float]) 资源的向量嵌入，用于语义搜索和AI匹配。

### **公共基础模型**

#### **`SkillWithProficiency` (技能熟练度)**

* **`name`** (str): 技能名称。
* **`level`** (Literal["初窥门径", "登堂入室", "融会贯通", "炉火纯青"]): 技能熟练度等级。

---

## **1. 认证与用户管理**

### **1.1 `POST /register` 用户注册**

* **摘要**: 用户注册新账号。
* **权限**: 无需认证。
* **请求体**: `schemas.StudentCreate`
 * `email` (Optional[EmailStr]): 用户邮箱，与手机号至少提供一个。
 * `phone_number` (Optional[str]): 用户手机号，11位数字，与邮箱至少提供一个。
 * `password` (str): 用户密码，至少6位。
 * `username` (Optional[str]): 用户名，平台内唯一，若不提供则自动生成。
 * `school` (Optional[str]): 用户所在学校。
 * `name` (Optional[str]): 真实姓名。
 * `major` (Optional[str]): 专业。
 * `skills` (Optional[List[schemas.SkillWithProficiency]]): 技能列表。
 * `interests` (Optional[str]): 兴趣描述。
 * `bio` (Optional[str]): 个人简介。
 * `awards_competitions` (Optional[str]): 获奖与竞赛经历。
 * `academic_achievements` (Optional[str]): 学术成就。
 * `soft_skills` (Optional[str]): 软技能。
 * `portfolio_link` (Optional[str]): 个人作品集链接。
 * `preferred_role` (Optional[str]): 偏好角色。
 * `availability` (Optional[str]): 可用时间（例如：每周20小时，暑假全职）。
 * `location` (Optional[str]): 学生所在地理位置。
* **响应体**: `schemas.StudentResponse`
 * `id` (int): 用户ID。
 * `email` (Optional[EmailStr]): 用户邮箱。
 * `phone_number` (Optional[str]): 用户手机号。
 * `username` (str): 用户名。
 * `school` (Optional[str]): 学校。
 * `name` (Optional[str]): 姓名。
 * `major` (Optional[str]): 专业。
 * `skills` (List[schemas.SkillWithProficiency]): 技能列表。
 * `interests` (Optional[str]): 兴趣。
 * `bio` (Optional[str]): 简介。
 * `awards_competitions` (Optional[str]): 获奖信息。
 * `academic_achievements` (Optional[str]): 学术成就。
 * `soft_skills` (Optional[str]): 软技能。
 * `portfolio_link` (Optional[str]): 作品集链接。
 * `preferred_role` (Optional[str]): 偏好角色。
 * `availability` (Optional[str]): 可用时间。
 * `location` (Optional[str]): 学生所在地。
 * `combined_text` (Optional[str]): 用于AI的组合文本。
 * `llm_api_type` (Optional[str]): 用户配置的LLM类型。
 * `llm_api_base_url` (Optional[str]): 用户配置的LLM基础URL。
 * `llm_model_id` (Optional[str]): 用户配置的LLM模型ID。
 * `llm_api_key_encrypted` (Optional[str]): 用户加密的LLM API Key (不会返回明文)。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
 * `is_admin` (bool): 是否为管理员。
 * `total_points` (int): 用户总积分。
 * `last_login_at` (Optional[datetime]): 上次登录时间。
 * `login_count` (int): 总登录天数。
 * `completed_projects_count` (Optional[int]): 已完成项目数量（后端计算）。
 * `completed_courses_count` (Optional[int]): 已完成课程数量（后端计算）。
* **常见状态码**: `200 OK`, `409 Conflict` (邮箱/手机号/用户名已注册)

### **1.2 `POST /token` 用户登录并获取JWT令牌**

* **摘要**: 通过用户凭证和密码获取JWT令牌。成功登录且首次今日登录会奖励积分并检查成就。
* **权限**: 无需认证。
* **请求体**: `application/x-www-form-urlencoded`
 * `username` (str): 用户的邮箱或手机号。
 * `password` (str): 用户密码。
* **响应体**: `schemas.Token`
 * `access_token` (str): 访问令牌。
 * `token_type` (str): 令牌类型，通常为`bearer`。
 * `expires_in_minutes` (int): 令牌过期时间（分钟）。
* **常见状态码**: `200 OK`, `401 Unauthorized` (凭证错误), `500 Internal Server Error` (数据保存失败)

### **1.3 `GET /users/me` 获取当前登录用户详情**

* **摘要**: 获取当前登录用户的详细信息，包括其总积分、成就、创建并完成的项目数量和完成的课程数量。
* **权限**: 已认证用户。
* **响应体**: `schemas.StudentResponse` (同 `POST /register` 的响应体，但包含当前用户特定数据)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **1.4 `PUT /users/me` 更新当前登录用户详情**

* **摘要**: 更新当前登录用户的详细信息（如姓名、专业、技能等）。
* **权限**: 已认证用户。
* **请求体**: `schemas.StudentUpdate`
 * 所有字段均为 `Optional`，只更新提供的字段。
 * `username` (Optional[str]): 用户名，唯一性检查。
 * `phone_number` (Optional[str]): 手机号，唯一性检查。
 * `skills` (Optional[List[schemas.SkillWithProficiency]]): 技能列表。
 * `location` (Optional[str]): 学生所在地理位置。
 * 其他 `StudentBase` 中的用户信息字段。
* **响应体**: `schemas.StudentResponse` (同 `GET /users/me` 响应体)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `409 Conflict` (用户名/手机号已被使用)

### **1.5 `GET /students/` 获取所有学生列表**

* **摘要**: 获取平台所有学生的概要列表。
* **权限**: 已认证用户（当前版本通常任何人可以获取，但根据业务可以限制为管理员）。
* **响应体**: `List[schemas.StudentResponse]` (每个元素为 `schemas.StudentResponse`，通常不包含敏感信息如加密密钥)。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **1.6 `GET /students/{student_id}` 获取指定学生详情**

* **摘要**: 获取指定ID学生的详细信息。
* **权限**: 已认证用户（当前版本通常任何人可以获取，但根据业务可以限制为管理员）。
* **路径参数**:
 * `student_id` (int): 学生的唯一标识符。
* **响应体**: `schemas.StudentResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **1.7 `PUT /admin/users/{user_id}/set-admin` 【管理员专用】设置系统管理员权限**

* **摘要**: 设置或取消指定用户的系统管理员权限。
* **权限**: 系统管理员。
* **路径参数**:
 * `user_id` (int): 目标用户的ID。
* **请求体**: `schemas.UserAdminStatusUpdate`
 * `is_admin` (bool): `True` 表示设置为管理员，`False` 表示取消管理员权限。
* **响应体**: `schemas.StudentResponse` (更新后的用户详情)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden` (非管理员尝试操作), `404 Not Found` (用户不存在), `400 Bad Request` (管理员不能取消自己的权限)

---

## **2. 项目管理与推荐**

### **2.1 `POST /projects/` 创建新项目**

* **摘要**: 创建一个新项目。项目创建者将自动关联。
* **权限**: 已认证用户。
* **请求体**: `schemas.ProjectCreate`
 * `title` (str): 项目标题。
 * `description` (Optional[str]): 项目描述。
 * `required_skills` (Optional[List[schemas.SkillWithProficiency]]): 项目所需技能列表。
 * `required_roles` (Optional[List[str]]): 项目所需角色列表。
 * `keywords` (Optional[str]): 关键词。
 * `project_type` (Optional[str]): 项目类型。
 * `expected_deliverables` (Optional[str]): 预期交付物。
 * `contact_person_info` (Optional[str]): 联系人信息。
 * `learning_outcomes` (Optional[str]): 学习成果。
 * `team_size_preference` (Optional[str]): 团队规模偏好。
 * `project_status` (Optional[str]): 项目状态。
 * `start_date` (Optional[datetime]): 项目开始日期。
 * `end_date` (Optional[datetime]): 项目结束日期。
 * `estimated_weekly_hours` (Optional[int]): 估计每周所需投入小时数。
 * `location` (Optional[str]): 项目所在地理位置。
* **响应体**: `schemas.ProjectResponse`
 * `id` (int): 项目ID。
 * 所有 `ProjectCreate` 中的字段。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `409 Conflict` (数据冲突)

### **2.2 `GET /projects/` 获取所有项目列表**

* **摘要**: 获取平台上所有项目的概要列表。
* **权限**: 已认证用户。
* **响应体**: `List[schemas.ProjectResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **2.3 `GET /projects/{project_id}` 获取指定项目详情**

* **摘要**: 获取指定ID项目的详细信息。
* **权限**: 已认证用户。
* **路径参数**:
 * `project_id` (int): 项目的唯一标识符。
* **响应体**: `schemas.ProjectResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **2.4 `PUT /projects/{project_id}` 更新指定项目**

* **摘要**: 更新指定ID项目的详细信息。只有项目创建者或系统管理员可以修改。当项目状态变为“已完成”时，会触发项目创建者的积分奖励和成就检查。
* **权限**: 项目创建者或系统管理员。
* **路径参数**:
 * `project_id` (int): 项目ID。
* **请求体**: `schemas.ProjectUpdate`
 * 所有 `ProjectCreate` 中的字段均为 `Optional`，只更新提供的字段。
* **响应体**: `schemas.ProjectResponse` (更新后的项目详情)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **2.5 `GET /recommend/projects/{student_id}` 为指定学生推荐项目**

* **摘要**: 使用AI为指定学生推荐相关的项目，考虑文本内容相似度、技能匹配、时间匹配和地理位置。
* **权限**: 已认证用户（取决于业务，可以限制为学生本人）。
* **路径参数**:
 * `student_id` (int): 学生的唯一标识符。
* **查询参数**:
 * `initial_k` (int): 初步筛选要返回的候选数量 (默认50)。
 * `final_k` (int): 最终重排后返回的推荐数量 (默认3)。
* **响应体**: `List[schemas.MatchedProject]`
 * `project_id` (int): 推荐项目的ID。
 * `title` (str): 项目标题。
 * `description` (str): 项目描述。
 * `similarity_stage1` (float): 第一阶段（粗召回/综合匹配）的相似度得分。
 * `relevance_score` (float): 最终重排后的相关性得分（更准确）。
 * `match_rationale` (Optional[str]): AI生成的匹配理由和行动建议。
* **常见状态码**: `200 OK`, `404 Not Found` (学生或项目不存在), `500 Internal Server Error` (AI服务失败)

### **2.6 `GET /projects/{project_id}/match-students` 为指定项目推荐学生**

* **摘要**: 使用AI为指定项目推荐相关的学生，考虑文本内容相似度、技能匹配、时间匹配和地理位置。
* **权限**: 已认证用户。
* **路径参数**:
 * `project_id` (int): 项目的唯一标识符。
* **查询参数**:
 * `initial_k` (int): 初步筛选要返回的候选数量 (默认50)。
 * `final_k` (int): 最终重排后返回的推荐数量 (默认3)。
* **响应体**: `List[schemas.MatchedStudent]`
 * `student_id` (int): 推荐学生的ID。
 * `name` (str): 学生姓名。
 * `major` (str): 学生专业。
 * `skills` (Optional[List[schemas.SkillWithProficiency]]): 学生的技能列表。
 * `similarity_stage1` (float): 第一阶段（粗召回/综合匹配）的相似度得分。
 * `relevance_score` (float): 最终重排后的相关性得分（更准确）。
 * `match_rationale` (Optional[str]): AI生成的匹配理由和行动建议。
* **常见状态码**: `200 OK`, `404 Not Found` (项目或学生不存在), `500 Internal Server Error` (AI服务失败)

---

## **3. 课程管理与推荐**

### **3.1 `POST /courses/` 创建新课程**

* **摘要**: 创建一个新课程，由管理员操作。
* **权限**: 系统管理员。
* **请求体**: `schemas.CourseBase`
 * `title` (str): 课程标题。
 * `description` (Optional[str]): 课程描述。
 * `instructor` (Optional[str]): 讲师名称。
 * `category` (Optional[str]): 课程类别。
 * `total_lessons` (Optional[int]): 总课时数。
 * `avg_rating` (Optional[float]): 平均评分。
 * `cover_image_url` (Optional[str]): 课程封面图片URL。
 * `required_skills` (Optional[List[schemas.SkillWithProficiency]]): 学习该课程所需基础技能或课程教授的技能。
* **响应体**: `schemas.CourseResponse`
 * `id` (int): 课程ID。
 * 所有 `CourseBase` 中的字段。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `409 Conflict` (数据冲突)

### **3.2 `GET /courses/` 获取所有课程列表**

* **摘要**: 获取平台上所有课程的概要列表。
* **权限**: 已认证用户。
* **响应体**: `List[schemas.CourseResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **3.3 `GET /courses/{course_id}` 获取指定课程详情**

* **摘要**: 获取指定ID课程的详细信息。
* **权限**: 已认证用户。
* **路径参数**:
 * `course_id` (int): 课程的唯一标识符。
* **响应体**: `schemas.CourseResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **3.4 `PUT /courses/{course_id}` 更新指定课程**

* **摘要**: 更新指定ID课程的详细信息。只有系统管理员可以修改。
* **权限**: 系统管理员。
* **路径参数**:
 * `course_id` (int): 课程ID。
* **请求体**: `schemas.CourseUpdate`
 * 所有 `CourseBase` 中的字段均为 `Optional`，只更新提供的字段。
* **响应体**: `schemas.CourseResponse` (更新后的课程详情)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **3.5 `GET /recommend/courses/{student_id}` 为指定学生推荐课程**

* **摘要**: 使用AI为指定学生推荐相关的课程，考虑文本内容相似度、技能匹配。
* **权限**: 已认证用户（取决于业务，可以限制为学生本人）。
* **路径参数**:
 * `student_id` (int): 学生的唯一标识符。
* **查询参数**:
 * `initial_k` (int): 初步筛选要返回的候选数量 (默认50)。
 * `final_k` (int): 最终重排后返回的推荐数量 (默认3)。
* **响应体**: `List[schemas.MatchedCourse]`
 * `course_id` (int): 推荐课程的ID。
 * `title` (str): 课程标题。
 * `description` (str): 课程描述。
 * `instructor` (Optional[str]): 讲师名称。
 * `category` (Optional[str]): 课程类别。
 * `cover_image_url` (Optional[str]): 课程封面URL。
 * `similarity_stage1` (float): 第一阶段（粗召回/综合匹配）的相似度得分。
 * `relevance_score` (float): 最终重排后的相关性得分（更准确）。
 * `match_rationale` (Optional[str]): AI生成的匹配理由和行动建议。
* **常见状态码**: `200 OK`, `404 Not Found` (学生或课程不存在), `500 Internal Server Error` (AI服务失败)

---

## **4. 课程材料管理**

### **4.1 `POST /courses/{course_id}/materials/` 为指定课程上传新材料（文件或链接）**

* **摘要**: 为指定课程上传一个新的学习材料，可以是文件、外部链接或纯文本。
* **权限**: 系统管理员。
* **路径参数**:
 * `course_id` (int): 课程ID。
* **请求体**: `multipart/form-data` 或 `application/json`
 * `file` (Optional[UploadFile]): 当`type`为`"file"`时，提供上传的文件。
 * `material_data` (`schemas.CourseMaterialCreate`):
 * `title` (str): 材料标题（必填）。
 * `type` (Literal["file", "link", "text"]): 材料类型。
 * `url` (Optional[str]): 当`type`为`"link"`时，提供外部链接URL（必填）。
 * `content` (Optional[str]): 当`type`为`"text"`时，提供文本内容（必填）；也可作为其他类型的补充描述。
* **响应体**: `schemas.CourseMaterialResponse`
 * `id` (int): 材料ID。
 * `course_id` (int): 所属课程ID。
 * `title` (str): 材料标题。
 * `type` (str): 材料类型。
 * `file_path` (Optional[str]): 本地文件路径（仅`type="file"`）。
 * `original_filename` (Optional[str]): 原始文件名（仅`type="file"`）。
 * `file_type` (Optional[str]): 文件MIME类型（仅`type="file"`）。
 * `size_bytes` (Optional[int]): 文件大小（字节）（仅`type="file"`）。
 * `url` (Optional[str]): 外部链接URL（仅`type="link"`）。
 * `content` (Optional[str]): 文本内容或描述（仅`type="text"`或补充）。
 * `combined_text` (Optional[str]): 用于AI的组合文本。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `400 Bad Request` (参数不合法，如缺少必填字段), `401 Unauthorized`, `403 Forbidden`, `404 Not Found` (课程不存在), `409 Conflict` (同名材料已存在), `500 Internal Server Error`

### **4.2 `GET /courses/{course_id}/materials/` 获取指定课程的所有材料列表**

* **摘要**: 获取指定课程的所有学习材料（文件、链接、文本）的列表。
* **权限**: 已认证用户。
* **路径参数**:
 * `course_id` (int): 课程ID。
* **查询参数**:
 * `type_filter` (Optional[Literal["file", "link", "text"]]): 按材料类型过滤。
* **响应体**: `List[schemas.CourseMaterialResponse]`
* **常见状态码**: `200 OK`, `404 Not Found` (课程不存在)

### **4.3 `GET /courses/{course_id}/materials/{material_id}` 获取指定课程材料详情**

* **摘要**: 获取指定课程中的特定学习材料的详细信息。
* **权限**: 已认证用户。
* **路径参数**:
 * `course_id` (int): 课程ID。
 * `material_id` (int): 材料ID。
* **响应体**: `schemas.CourseMaterialResponse`
* **常见状态码**: `200 OK`, `404 Not Found`

### **4.4 `PUT /courses/{course_id}/materials/{material_id}` 更新指定课程材料**

* **摘要**: 更新指定课程材料的信息。可替换文件、更改链接或文本内容，甚至更改材料类型。
* **权限**: 系统管理员。
* **路径参数**:
 * `course_id` (int): 课程ID。
 * `material_id` (int): 材料ID。
* **请求体**: `multipart/form-data` 或 `application/json`
 * `file` (Optional[UploadFile]): 可选，提供新文件替换现有文件。如果材料类型不是`"file"`，需要同时在`material_data`中将`type`更新为`"file"`。
 * `material_data` (`schemas.CourseMaterialUpdate`):
 * 所有字段均为 `Optional`，只更新提供的字段。
 * `title` (Optional[str]): 材料标题，不能更新为`null`或空字符串。
 * `type` (Optional[Literal["file", "link", "text"]]): 更改材料类型（会影响其他字段的有效性）。
 * `url` (Optional[str]): 更新外部链接。
 * `content` (Optional[str]): 更新文本内容。
* **响应体**: `schemas.CourseMaterialResponse` (更新后的材料详情)。
* **常见状态码**: `200 OK`, `400 Bad Request` (参数不合法), `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict` (同名材料已存在)

### **4.5 `DELETE /courses/{course_id}/materials/{material_id}` 删除指定课程材料**

* **摘要**: 删除指定课程中的特定学习材料。如果材料是文件类型，会同时删除本地存储的文件。
* **权限**: 系统管理员。
* **路径参数**:
 * `course_id` (int): 课程ID。
 * `material_id` (int): 材料ID。
* **响应体**: `204 No Content`
* **常见状态码**: `204 No Content`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

---

## **5. 核心AI功能**

### **5.1 `POST /ai/qa` AI智能问答 (通用、RAG或工具调用)**

* **摘要**: 使用LLM进行问答。
* **权限**: 已认证用户。
* **请求体**: `schemas.AIQARequest`
 * `query` (str): 用户的问题。
 * `kb_ids` (Optional[List[int]]): 知识库ID列表，用于RAG。
 * `note_ids` (Optional[List[int]]): 笔记ID列表，用于RAG。
 * `use_tools` (Optional[bool]): 是否允许AI使用工具（如网络搜索、MCP工具），默认`False`。
 * `preferred_tools` (Optional[List[Literal["rag", "web_search", "mcp_tool"]]]): 引导AI优先使用的工具类型。
 * `llm_model_id` (Optional[str]): 指定LLM模型ID，若不提供则使用用户默认配置。
* **响应体**: `schemas.AIQAResponse`
 * `answer` (str): AI生成的答案。
 * `source_articles` (Optional[List[Dict[str, Any]]]): RAG模式下的来源文章信息。
 * `search_results` (Optional[List[Dict[str, Any]]]): 网络搜索结果摘要，如果使用了网络搜索工具。
 * `tool_calls` (Optional[List[Dict[str, Any]]]): 如果AI调用了工具，记录工具调用信息和状态。
 * `answer_mode` (str): 答案生成模式，如`"General_mode"`, `"Tool_Use_mode"`, `"RAG_mode"`。
 * `llm_type_used` (Optional[str]): 实际使用的LLM类型。
 * `llm_model_used` (Optional[str]): 实际使用的LLM模型ID。
* **常见状态码**: `200 OK`, `400 Bad Request` (LLM配置缺失), `500 Internal Server Error` (AI服务失败)

### **5.2 `POST /search/semantic` 智能语义搜索**

* **摘要**: 通过语义搜索，在用户可访问的项目、课程、知识库文章和笔记中查找相关内容。
* **权限**: 已认证用户。
* **请求体**: `schemas.SemanticSearchRequest`
 * `query` (str): 搜索查询。
 * `item_types` (Optional[List[str]]): 要搜索的项目类型列表，如`"project"`, `"course"`, `"knowledge_article"`, `"note"`。
 * `limit` (int): 返回结果的数量限制（默认10）。
* **响应体**: `List[schemas.SemanticSearchResult]`
 * `id` (int): 结果项的ID。
 * `title` (str): 结果项的标题。
 * `type` (str): 结果项的类型。
 * `content_snippet` (Optional[str]): 结果项内容的摘要片段。
 * `relevance_score` (float): 相关性得分。
* **常见状态码**: `200 OK`, `404 Not Found` (无内容可搜索), `503 Service Unavailable` (AI服务失败)

### **5.3 `GET /llm/available-models` 获取可配置的LLM服务商及模型列表**

* **摘要**: 返回所有支持的LLM服务商类型及其默认模型和可用模型列表。
* **权限**: 任何已认证用户。
* **响应体**: `Dict[str, Dict[str, Any]]`
 * 键为LLM服务商类型（如`"openai"`），值为包含`default_model`和`available_models`的字典。
* **常见状态码**: `200 OK`

---

## **6. 第三方AI服务配置管理**

### **6.1 `POST /users/me/llm-config` 更新当前用户LLM配置**

* **摘要**: 更新当前用户的LLM（大语言模型）API配置，密钥会加密存储。
* **权限**: 已认证用户。
* **请求体**: `schemas.UserLLMConfigUpdate`
 * `llm_api_type` (Optional[Literal[...]]): LLM服务商类型。
 * `llm_api_key` (Optional[str]): LLM API密钥（明文）。
 * `llm_api_base_url` (Optional[str]): LLM API基础URL。
 * `llm_model_id` (Optional[str]): LLM模型ID。
* **响应体**: `schemas.StudentResponse` (更新后的用户详情，包含加密的LLM配置字段)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **6.2 `POST /mcp-configs/` 创建新的MCP配置**

* **摘要**: 为当前用户创建新的MCP（Multi-modal Computing Platform）服务配置。
* **权限**: 已认证用户。
* **请求体**: `schemas.UserMcpConfigCreate`
 * `name` (str): 配置名称。
 * `mcp_type` (Optional[Literal["modelscope_community", "custom_mcp"]]): MCP服务类型。
 * `base_url` (str): MCP API基础URL。
 * `protocol_type` (Optional[Literal["sse", "http_rest", "websocket"]]): 协议类型，默认`http_rest`。
 * `api_key` (Optional[str]): API密钥（明文），会加密存储。
 * `is_active` (Optional[bool]): 是否激活，默认`True`。
 * `description` (Optional[str]): 描述。
* **响应体**: `schemas.UserMcpConfigResponse`
 * `id` (int): 配置ID。
 * `owner_id` (int): 拥有者ID。
 * 所有 `UserMcpConfigCreate` 中的字段 (api_key返回加密后的api_key_encrypted)。
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `409 Conflict` (同名活跃配置已存在)

### **6.3 `GET /mcp-configs/` 获取当前用户所有MCP服务配置**

* **摘要**: 获取当前用户配置的所有MCP服务列表。
* **权限**: 已认证用户。
* **查询参数**:
 * `is_active` (Optional[bool]): 按激活状态过滤。
* **响应体**: `List[schemas.UserMcpConfigResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **6.4 `PUT /mcp-configs/{config_id}` 更新指定MCP配置**

* **摘要**: 更新指定MCP服务配置。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **请求体**: `schemas.UserMcpConfigBase`
 * 所有字段为可选。
* **响应体**: `schemas.UserMcpConfigResponse`
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found`, `409 Conflict`

### **6.5 `DELETE /mcp-configs/{config_id}` 删除指定MCP服务配置**

* **摘要**: 删除指定MCP服务配置。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `{"message": "MCP config deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **6.6 `POST /mcp-configs/{config_id}/check-status` 检查指定MCP服务的连通性**

* **摘要**: 检查指定ID的MCP服务配置的API连通性。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `schemas.McpStatusResponse`
 * `status` (str): 连通性状态，如`"success"`, `"failure"`, `"timeout"`。
 * `message` (str): 状态描述。
 * `service_name` (Optional[str]): 服务名称。
 * `config_id` (Optional[int]): 配置ID。
 * `timestamp` (datetime): 检查时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `500 Internal Server Error`

### **6.7 `GET /llm/mcp-available-tools` 获取智库聊天可用的MCP工具列表**

* **摘要**: 根据用户已配置且启用的MCP服务，返回可用于智库聊天中的工具列表。
* **权限**: 已认证用户。
* **响应体**: `List[schemas.McpToolDefinition]`
 * `tool_id` (str): 工具的唯一ID。
 * `name` (str): 工具名称。
 * `description` (str): 工具描述。
 * `mcp_config_id` (int): 关联的MCP配置ID。
 * `mcp_config_name` (str): 关联的MCP配置名称。
 * `input_schema` (Dict[str, Any]): 工具输入参数的JSON Schema。
 * `output_schema` (Dict[str, Any]): 工具输出结果的JSON Schema。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **6.8 `POST /search-engine-configs/` 创建新的搜索引擎配置**

* **摘要**: 创建新的搜索引擎配置。
* **权限**: 已认证用户。
* **请求体**: `schemas.UserSearchEngineConfigCreate`
 * `name` (str): 配置名称。
 * `engine_type` (Literal["bing", "tavily", "baidu", "google_cse", "custom"]): 搜索引擎类型。
 * `api_key` (Optional[str]): API密钥（明文），会加密存储。
 * `is_active` (Optional[bool]): 是否激活，默认`True`。
 * `description` (Optional[str]): 描述。
 * `base_url` (Optional[str]): 搜索引擎API基础URL。
* **响应体**: `schemas.UserSearchEngineConfigResponse`
 * `id` (int): 配置ID。
 * `owner_id` (int): 拥有者ID。
 * 所有 `UserSearchEngineConfigCreate` 中的字段 (api_key返回加密后的api_key_encrypted)。
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `409 Conflict` (同名活跃配置已存在)

### **6.9 `GET /search-engine-configs/` 获取当前用户所有搜索引擎配置**

* **摘要**: 获取当前用户配置的所有搜索引擎列表。
* **权限**: 已认证用户。
* **查询参数**:
 * `is_active` (Optional[bool]): 按激活状态过滤。
* **响应体**: `List[schemas.UserSearchEngineConfigResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **6.10 `GET /search-engine-configs/{config_id}` 获取指定搜索引擎配置详情**

* **摘要**: 获取指定ID的搜索引擎配置详情。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `schemas.UserSearchEngineConfigResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **6.11 `PUT /search-engine-configs/{config_id}` 更新指定搜索引擎配置**

* **摘要**: 更新指定搜索引擎配置。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **请求体**: `schemas.UserSearchEngineConfigUpdate` (继承 `UserSearchEngineConfigBase` 的所有可选字段)。
* **响应体**: `schemas.UserSearchEngineConfigResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `409 Conflict`

### **6.12 `DELETE /search-engine-configs/{config_id}` 删除指定搜索引擎配置**

* **摘要**: 删除指定搜索引擎配置。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `{"message": "Search engine config deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **6.13 `POST /search-engine-configs/{config_id}/check-status` 检查指定搜索引擎的连通性**

* **摘要**: 检查指定ID的搜索引擎配置的API连通性。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `schemas.SearchEngineStatusResponse`
 * `status` (str): 连通性状态，如`"success"`, `"failure"`, `"timeout"`。
 * `message` (str): 状态描述。
 * `engine_name` (Optional[str]): 引擎名称。
 * `config_id` (Optional[int]): 配置ID。
 * `timestamp` (datetime): 检查时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `500 Internal Server Error`

### **6.14 `POST /users/me/tts_configs` 为当前用户创建新的TTS配置**

* **摘要**: 为当前用户创建新的TTS（Text-to-Speech）配置。
* **权限**: 已认证用户。
* **请求体**: `schemas.UserTTSConfigCreate`
 * `name` (str): 配置名称。
 * `tts_type` (Literal["openai", "gemini", "aliyun", "siliconflow"]): 语音提供商类型。
 * `api_key` (str): API密钥（明文），会加密存储。
 * `base_url` (Optional[str]): API基础URL。
 * `model_id` (Optional[str]): 语音模型ID。
 * `voice_name` (Optional[str]): 语音名称或ID。
 * `is_active` (Optional[bool]): 是否激活，默认`False`。
* **响应体**: `schemas.UserTTSConfigResponse`
 * `id` (int): 配置ID。
 * `owner_id` (int): 拥有者ID。
 * 所有 `UserTTSConfigCreate` 中的字段 (api_key返回加密后的api_key_encrypted)。
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `409 Conflict` (同名配置或已有激活配置)

### **6.15 `GET /users/me/tts_configs` 获取当前用户的所有TTS配置**

* **摘要**: 获取当前用户配置的所有TTS服务列表。
* **权限**: 已认证用户。
* **响应体**: `List[schemas.UserTTSConfigResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **6.16 `GET /users/me/tts_configs/{config_id}` 获取指定TTS配置详情**

* **摘要**: 获取指定ID的TTS配置详情。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `schemas.UserTTSConfigResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **6.17 `PUT /users/me/tts_configs/{config_id}` 更新指定TTS配置**

* **摘要**: 更新指定TTS配置。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **请求体**: `schemas.UserTTSConfigUpdate` (继承 `UserTTSConfigBase` 的所有可选字段)。
* **响应体**: `schemas.UserTTSConfigResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `409 Conflict`

### **6.18 `DELETE /users/me/tts_configs/{config_id}` 删除指定TTS配置**

* **摘要**: 删除指定TTS配置。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `204 No Content`
* **常见状态码**: `204 No Content`, `401 Unauthorized`, `404 Not Found`

### **6.19 `PUT /users/me/tts_configs/{config_id}/set_active` 设置指定TTS配置为激活状态**

* **摘要**: 将指定ID的TTS配置设置为激活状态，同时将其他激活配置设为非激活。
* **权限**: 配置所有者。
* **路径参数**:
 * `config_id` (int): 配置ID。
* **响应体**: `schemas.UserTTSConfigResponse` (被激活的配置详情)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `500 Internal Server Error`

---

## **7. 随手记录管理**

### **7.1 `POST /daily-records/` 创建新随手记录**

* **摘要**: 为当前用户创建一条新随手记录。
* **权限**: 已认证用户。
* **请求体**: `schemas.DailyRecordBase`
 * `content` (str): 记录内容。
 * `mood` (Optional[str]): 心情标签。
 * `tags` (Optional[str]): 其他标签，逗号分隔。
* **响应体**: `schemas.DailyRecordResponse`
 * `id` (int): 记录ID。
 * `owner_id` (int): 拥有者ID。
 * `combined_text` (Optional[str]): 用于AI的组合文本。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **7.2 `GET /daily-records/` 获取当前用户所有随手记录**

* **摘要**: 获取当前用户的所有随手记录。
* **权限**: 已认证用户。
* **查询参数**:
 * `mood` (Optional[str]):按心情过滤。
 * `tag` (Optional[str]): 按标签模糊过滤。
* **响应体**: `List[schemas.DailyRecordResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **7.3 `GET /daily-records/{record_id}` 获取指定随手记录详情**

* **摘要**: 获取指定ID的随手记录详情。
* **权限**: 记录所有者。
* **路径参数**:
 * `record_id` (int): 记录ID。
* **响应体**: `schemas.DailyRecordResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **7.4 `PUT /daily-records/{record_id}` 更新指定随手记录**

* **摘要**: 更新指定ID的随手记录内容。
* **权限**: 记录所有者。
* **路径参数**:
 * `record_id` (int): 记录ID。
* **请求体**: `schemas.DailyRecordBase` (所有字段 Optional)。
* **响应体**: `schemas.DailyRecordResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **7.5 `DELETE /daily-records/{record_id}` 删除指定随手记录**

* **摘要**: 删除指定ID的随手记录。
* **权限**: 记录所有者。
* **路径参数**:
 * `record_id` (int): 记录ID。
* **响应体**: `{"message": "Daily record deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

---

## **8. 文件夹与收藏管理**

### **8.1 `POST /folders/` 创建新文件夹**

* **摘要**: 为当前用户创建一个新文件夹。
* **权限**: 已认证用户。
* **请求体**: `schemas.FolderBase`
 * `name` (str): 文件夹名称。
 * `description` (Optional[str]): 描述。
 * `color` (Optional[str]): 颜色。
 * `icon` (Optional[str]): 图标。
 * `parent_id` (Optional[int]): 父文件夹ID，用于创建子文件夹。
 * `order` (Optional[int]): 排序。
* **响应体**: `schemas.FolderResponse`
 * `id` (int): 文件夹ID。
 * `owner_id` (int): 拥有者ID。
 * `item_count` (Optional[int]): 包含的直属内容和子文件夹数量（动态计算）。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found` (父文件夹不存在), `400 Bad Request` (循环引用)

### **8.2 `GET /folders/` 获取当前用户所有文件夹**

* **摘要**: 获取当前用户的所有文件夹。
* **权限**: 已认证用户。
* **查询参数**:
 * `parent_id` (Optional[int]): 按父文件夹ID过滤，`None`表示顶级文件夹。
* **响应体**: `List[schemas.FolderResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **8.3 `GET /folders/{folder_id}` 获取指定文件夹详情**

* **摘要**: 获取指定ID的文件夹详情。
* **权限**: 文件夹所有者。
* **路径参数**:
 * `folder_id` (int): 文件夹ID。
* **响应体**: `schemas.FolderResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **8.4 `PUT /folders/{folder_id}` 更新指定文件夹**

* **摘要**: 更新指定ID的文件夹信息。
* **权限**: 文件夹所有者。
* **路径参数**:
 * `folder_id` (int): 文件夹ID。
* **请求体**: `schemas.FolderBase` (所有字段 Optional)。
* **响应体**: `schemas.FolderResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `400 Bad Request`

### **8.5 `DELETE /folders/{folder_id}` 删除指定文件夹**

* **摘要**: 删除指定ID的文件夹及其包含的所有子文件夹和收藏内容。
* **权限**: 文件夹所有者。
* **路径参数**:
 * `folder_id` (int): 文件夹ID。
* **响应体**: `{"message": "Folder and its contents deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **8.6 `POST /collections/` 创建新收藏内容**

* **摘要**: 为当前用户创建一条新收藏内容。
* **权限**: 已认证用户。
* **请求体**: `schemas.CollectedContentBase`
 * `title` (str): 收藏标题。
 * `type` (Literal[...]): 收藏内容类型。
 * `url` (Optional[str]): 外部链接。
 * `content` (Optional[str]): 文本内容。
 * `tags` (Optional[str]): 标签。
 * `folder_id` (Optional[int]): 所属文件夹ID。
 * 其他自定义字段。
* **响应体**: `schemas.CollectedContentResponse`
 * `id` (int): 收藏ID。
 * `owner_id` (int): 拥有者ID。
 * `access_count` (int): 访问次数。
 * `combined_text` (Optional[str]): 用于AI的组合文本。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found` (文件夹不存在)

### **8.7 `GET /collections/` 获取当前用户所有收藏内容**

* **摘要**: 获取当前用户的所有收藏内容。
* **权限**: 已认证用户。
* **查询参数**:
 * `folder_id` (Optional[int]): 按文件夹过滤，`0`表示根目录，`None`表示所有。
 * `type_filter` (Optional[str]): 按类型过滤。
 * `tag_filter` (Optional[str]): 按标签模糊过滤。
 * `is_starred` (Optional[bool]): 只看星标。
 * `status_filter` (Optional[str]): 按状态过滤。
* **响应体**: `List[schemas.CollectedContentResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **8.8 `GET /collections/{content_id}` 获取指定收藏内容详情**

* **摘要**: 获取指定ID的收藏内容详情。每次访问会自动增加访问计数。
* **权限**: 收藏所有者。
* **路径参数**:
 * `content_id` (int): 收藏内容ID。
* **响应体**: `schemas.CollectedContentResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **8.9 `PUT /collections/{content_id}` 更新指定收藏内容**

* **摘要**: 更新指定ID的收藏内容。
* **权限**: 收藏所有者。
* **路径参数**:
 * `content_id` (int): 收藏内容ID。
* **请求体**: `schemas.CollectedContentBase` (所有字段 Optional)。
* **响应体**: `schemas.CollectedContentResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **8.10 `DELETE /collections/{content_id}` 删除指定收藏内容**

* **摘要**: 删除指定ID的收藏内容。
* **权限**: 收藏所有者。
* **路径参数**:
 * `content_id` (int): 收藏内容ID。
* **响应体**: `{"message": "Collected content deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

---

## **9. 知识库与文章、文档管理**

### **9.1 `POST /knowledge-bases/` 创建新知识库**

* **摘要**: 为当前用户创建一个新知识库。
* **权限**: 已认证用户。
* **请求体**: `schemas.KnowledgeBaseBase`
 * `name` (str): 知识库名称。
 * `description` (Optional[str]): 描述。
 * `access_type` (Optional[str]): 访问类型，默认`private`。
* **响应体**: `schemas.KnowledgeBaseResponse`
 * `id` (int): 知识库ID。
 * `owner_id` (int): 拥有者ID。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `409 Conflict` (名称已存在)

### **9.2 `GET /knowledge-bases/` 获取当前用户所有知识库**

* **摘要**: 获取当前用户的所有知识库列表。
* **权限**: 已认证用户。
* **响应体**: `List[schemas.KnowledgeBaseResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **9.3 `GET /knowledge-bases/{kb_id}` 获取指定知识库详情**

* **摘要**: 获取指定ID知识库的详细信息。
* **权限**: 知识库所有者或公共知识库。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
* **响应体**: `schemas.KnowledgeBaseResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.4 `PUT /knowledge-bases/{kb_id}` 更新指定知识库**

* **摘要**: 更新指定ID知识库的信息。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
* **请求体**: `schemas.KnowledgeBaseBase` (所有字段 Optional)。
* **响应体**: `schemas.KnowledgeBaseResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `409 Conflict`

### **9.5 `DELETE /knowledge-bases/{kb_id}` 删除指定知识库**

* **摘要**: 删除指定ID的知识库及其所有文章和文档。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
* **响应体**: `{"message": "Knowledge base and its articles/documents deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.6 `POST /knowledge-bases/{kb_id}/articles/` 在指定知识库中创建新文章**

* **摘要**: 在指定知识库中创建一篇新知识文章。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
* **请求体**: `schemas.KnowledgeArticleBase`
 * `title` (Optional[str]): 文章标题。
 * `content` (Optional[str]): 文章内容。
 * `version` (Optional[str]): 版本。
 * `tags` (Optional[str]): 标签。
* **响应体**: `schemas.KnowledgeArticleResponse`
 * `id` (int): 文章ID。
 * `kb_id` (int): 所属知识库ID。
 * `author_id` (int): 作者ID。
 * `combined_text` (Optional[str]): 用于AI的组合文本。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found` (知识库不存在)

### **9.7 `GET /knowledge-bases/{kb_id}/articles/` 获取指定知识库的所有文章**

* **摘要**: 获取指定知识库下的所有知识文章列表。
* **权限**: 知识库所有者或公共知识库。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
* **响应体**: `List[schemas.KnowledgeArticleResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.8 `GET /articles/{article_id}` 获取指定文章详情**

* **摘要**: 获取指定ID文章的详细信息。
* **权限**: 文章作者或其所在知识库所有者。
* **路径参数**:
 * `article_id` (int): 文章ID。
* **响应体**: `schemas.KnowledgeArticleResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.9 `PUT /articles/{article_id}` 更新指定文章**

* **摘要**: 更新指定ID文章的信息。
* **权限**: 文章作者。
* **路径参数**:
 * `article_id` (int): 文章ID。
* **请求体**: `schemas.KnowledgeArticleBase` (所有字段 Optional)。
* **响应体**: `schemas.KnowledgeArticleResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.10 `DELETE /articles/{article_id}` 删除指定文章**

* **摘要**: 删除指定ID的文章。
* **权限**: 文章作者。
* **路径参数**:
 * `article_id` (int): 文章ID。
* **响应体**: `{"message": "Knowledge article deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.11 `POST /knowledge-bases/{kb_id}/documents/` 上传新知识文档到知识库**

* **摘要**: 上传一个新的文档（PDF, DOCX, TXT）到指定知识库。文档内容将在后台异步处理，包括文本提取、分块和嵌入生成。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
* **请求体**: `multipart/form-data`
 * `file` (UploadFile): 上传的文件。
* **响应体**: `schemas.KnowledgeDocumentResponse`
 * `id` (int): 文档ID。
 * `kb_id` (int): 所属知识库ID。
 * `owner_id` (int): 拥有者ID。
 * `file_name` (str): 原始文件名。
 * `file_path` (str): 本地保存路径。
 * `file_type` (str): 文件MIME类型。
 * `status` (str): 处理状态，如`"processing"`, `"completed"`, `"failed"`。
 * `processing_message` (Optional[str]): 处理信息。
 * `total_chunks` (int): 总文本块数量。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `202 Accepted` (请求已接受，后台处理), `400 Bad Request`, `401 Unauthorized`, `404 Not Found`, `500 Internal Server Error`

### **9.12 `GET /knowledge-bases/{kb_id}/documents/` 获取知识库下所有知识文档**

* **摘要**: 获取指定知识库下所有知识文档（已上传文件）的列表。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
* **查询参数**:
 * `status_filter` (Optional[str]): 按处理状态过滤。
* **响应体**: `List[schemas.KnowledgeDocumentResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.13 `GET /knowledge-bases/{kb_id}/documents/{document_id}` 获取指定知识文档详情**

* **摘要**: 获取指定知识库下指定知识文档的详情。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
 * `document_id` (int): 文档ID。
* **响应体**: `schemas.KnowledgeDocumentResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.14 `DELETE /knowledge-bases/{kb_id}/documents/{document_id}` 删除指定知识文档**

* **摘要**: 删除指定知识库下的指定知识文档及其所有文本块和本地文件。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
 * `document_id` (int): 文档ID。
* **响应体**: `{"message": "Knowledge document deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **9.15 `GET /knowledge-bases/{kb_id}/documents/{document_id}/content` 获取知识文档的原始文本内容 (DEBUG)**

* **摘要**: 获取指定知识文档的原始文本内容 (用于调试，慎用)。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
 * `document_id` (int): 文档ID。
* **响应体**: `{"content": "..."}`
* **常见状态码**: `200 OK`, `400 Bad Request` (未完成处理), `401 Unauthorized`, `404 Not Found`

### **9.16 `GET /knowledge-bases/{kb_id}/documents/{document_id}/chunks` 获取知识文档的所有文本块列表 (DEBUG)**

* **摘要**: 获取指定知识文档的所有文本块列表 (用于调试)。
* **权限**: 知识库所有者。
* **路径参数**:
 * `kb_id` (int): 知识库ID。
 * `document_id` (int): 文档ID。
* **响应体**: `List[schemas.KnowledgeDocumentChunkResponse]`
 * `id` (int): 文本块ID。
 * `document_id` (int): 所属文档ID。
 * `owner_id` (int): 拥有者ID。
 * `kb_id` (int): 所属知识库ID。
 * `chunk_index` (int): 文本块顺序。
 * `content` (str): 文本块内容。
 * `combined_text` (Optional[str]): 组合文本。
* **常见状态码**: `200 OK`, `422 Unprocessable Entity` (文档未完成处理), `401 Unauthorized`, `404 Not Found`

---

## **10. 聊天室与消息、社交功能**

### **10.1 `POST /chat-rooms/` 创建新的聊天室**

* **摘要**: 创建一个新的聊天室。
* **权限**: 已认证用户。
* **请求体**: `schemas.ChatRoomCreate`
 * `name` (str): 聊天室名称。
 * `type` (Literal["project_group", "course_group", "private", "general"]): 聊天室类型。
 * `project_id` (Optional[int]): 关联项目ID。
 * `course_id` (Optional[int]): 关联课程ID。
 * `color` (Optional[str]): 聊天室颜色。
* **响应体**: `schemas.ChatRoomResponse`
 * `id` (int): 聊天室ID。
 * `creator_id` (int): 创建者ID。
 * `members_count` (Optional[int]): 成员数量。
 * `last_message` (Optional[Dict[str, Any]]): 最新消息概要。
 * `unread_messages_count` (Optional[int]): 未读消息数。
 * `online_members_count` (Optional[int]): 在线成员数。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found` (关联项目/课程不存在), `409 Conflict` (项目/课程已有关联聊天室)

### **10.2 `GET /chatrooms/` 获取当前用户所属的所有聊天室**

* **摘要**: 获取当前用户所属（创建或参与）的所有聊天室列表。
* **权限**: 已认证用户。
* **查询参数**:
 * `room_type` (Optional[str]): 按类型过滤（`project_group`, `course_group`等）。
* **响应体**: `List[schemas.ChatRoomResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **10.3 `GET /chatrooms/{room_id}` 获取指定聊天室详情**

* **摘要**: 获取指定ID的聊天室详情。
* **权限**: 聊天室创建者、活跃成员或系统管理员。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **响应体**: `schemas.ChatRoomResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **10.4 `PUT /chatrooms/{room_id}/` 更新指定聊天室**

* **摘要**: 更新指定聊天室的信息。
* **权限**: 聊天室创建者。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **请求体**: `schemas.ChatRoomUpdate` (所有字段 Optional)。
* **响应体**: `schemas.ChatRoomResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`

### **10.5 `DELETE /chatrooms/{room_id}` 删除指定聊天室（仅限群主或系统管理员）**

* **摘要**: 删除指定聊天室及其所有关联数据（消息、成员记录、入群申请）。
* **权限**: 聊天室创建者或系统管理员。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **响应体**: `204 No Content`
* **常见状态码**: `204 No Content`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **10.6 `GET /chatrooms/{room_id}/members` 获取指定聊天室的所有成员列表**

* **摘要**: 获取指定聊天室的所有成员列表。
* **权限**: 聊天室创建者、管理员或系统管理员。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **响应体**: `List[schemas.ChatRoomMemberResponse]`
 * `id` (int): 成员关系ID。
 * `room_id` (int): 聊天室ID。
 * `member_id` (int): 成员用户ID。
 * `role` (Literal["admin", "member"]): 成员角色。
 * `status` (Literal["active", "banned", "left"]): 成员状态。
 * `joined_at` (datetime): 加入时间。
 * `member_name` (Optional[str]): 成员姓名。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **10.7 `PUT /chat-rooms/{room_id}/members/{member_id}/set-role` 设置聊天室成员的角色（管理员/普通成员）**

* **摘要**: 设置指定聊天室成员的角色（管理员/普通成员）。
* **权限**: 聊天室创建者。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
 * `member_id` (int): 目标成员的用户ID。
* **请求体**: `schemas.ChatRoomMemberRoleUpdate`
 * `role` (Literal["admin", "member"]): 要设置的新角色。
* **响应体**: `schemas.ChatRoomMemberResponse` (更新后的成员关系详情)。
* **常见状态码**: `200 OK`, `400 Bad Request` (群主角色无法修改，管理员不能降自己), `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **10.8 `DELETE /chat-rooms/{room_id}/members/{member_id}` 从聊天室移除成员（踢出或离开）**

* **摘要**: 从聊天室移除成员。成员可以自己离开；群主或管理员可以踢出其他成员。
* **权限**: 成员本人（离开），或聊天室创建者/管理员/系统管理员（踢出）。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
 * `member_id` (int): 目标成员的用户ID。
* **响应体**: `204 No Content`
* **常见状态码**: `204 No Content`, `400 Bad Request` (群主不能自己离开), `401 Unauthorized`, `403 Forbidden` (无权移除), `404 Not Found`

### **10.9 `POST /chat-rooms/{room_id}/join-request` 向指定聊天室发起入群申请**

* **摘要**: 向指定聊天室发起入群申请。
* **权限**: 已认证用户。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **请求体**: `schemas.ChatRoomJoinRequestCreate`
 * `room_id` (int): 目标聊天室ID（需要与路径参数一致）。
 * `reason` (Optional[str]): 申请理由。
* **响应体**: `schemas.ChatRoomJoinRequestResponse`
 * `id` (int): 申请ID。
 * `room_id` (int): 聊天室ID。
 * `requester_id` (int): 申请者ID。
 * `reason` (Optional[str]): 申请理由。
 * `status` (str): 申请状态，默认`pending`。
 * `requested_at` (datetime): 申请时间。
 * `processed_by_id` (Optional[int]): 处理者ID。
 * `processed_at` (Optional[datetime]): 处理时间。
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found` (聊天室不存在), `409 Conflict` (已有待处理申请)

### **10.10 `GET /chat-rooms/{room_id}/join-requests` 获取指定聊天室的入群申请列表**

* **摘要**: 获取指定聊天室的入群申请列表。
* **权限**: 聊天室创建者、管理员或系统管理员。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **查询参数**:
 * `status_filter` (Optional[str]): 按状态过滤 (`pending`, `approved`, `rejected`)。
* **响应体**: `List[schemas.ChatRoomJoinRequestResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **10.11 `POST /chat-rooms/join-requests/{request_id}/process` 处理入群申请 (批准或拒绝)**

* **摘要**: 处理入群申请（批准或拒绝）。
* **权限**: 聊天室创建者、管理员或系统管理员。
* **路径参数**:
 * `request_id` (int): 入群申请ID。
* **请求体**: `schemas.ChatRoomJoinRequestProcess`
 * `status` (Literal["approved", "rejected"]): 处理结果。
* **响应体**: `schemas.ChatRoomJoinRequestResponse` (处理后的申请详情)。
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **10.12 `POST /chatrooms/{room_id}/messages/` 在指定聊天室发送新消息**

* **摘要**: 在指定聊天室发送一条新消息。
* **权限**: 聊天室活跃成员（包括创建者）。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **请求体**: `schemas.ChatMessageCreate`
 * `content_text` (str): 消息文本内容。
 * `message_type` (Literal["text", "image", "file", "system_notification"]): 消息类型，默认`text`。
 * `media_url` (Optional[str]): 媒体文件URL。
* **响应体**: `schemas.ChatMessageResponse`
 * `id` (int): 消息ID。
 * `room_id` (int): 聊天室ID。
 * `sender_id` (int): 发送者ID。
 * `sent_at` (datetime): 发送时间。
 * `sender_name` (Optional[str]): 发送者姓名。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.13 `GET /chatrooms/{room_id}/messages/` 获取指定聊天室的历史消息**

* **摘要**: 获取指定聊天室的历史消息。
* **权限**: 聊天室创建者（根据业务可扩展为活跃成员）。
* **路径参数**:
 * `room_id` (int): 聊天室ID。
* **查询参数**:
 * `limit` (int): 限制返回消息数量，默认50。
 * `offset` (int): 偏移量，用于分页，默认0。
* **响应体**: `List[schemas.ChatMessageResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.14 `POST /forum/topics/` 发布新论坛话题**

* **摘要**: 发布一个新论坛话题。
* **权限**: 已认证用户。
* **请求体**: `schemas.ForumTopicBase`
 * `title` (str): 话题标题。
 * `content` (str): 话题内容。
 * `shared_item_type` (Optional[Literal[...]]): 关联分享平台其他内容类型。
 * `shared_item_id` (Optional[int]): 关联内容ID。
 * `tags` (Optional[str]): 标签。
* **响应体**: `schemas.ForumTopicResponse`
 * `id` (int): 话题ID。
 * `owner_id` (int): 发布者ID。
 * `owner_name` (Optional[str]): 发布者名字。
 * `likes_count` (int): 点赞数。
 * `comments_count` (int): 评论数。
 * `views_count` (int): 浏览数。
 * `is_liked_by_current_user` (bool): 当前用户是否点赞。
 * `is_collected_by_current_user` (bool): 当前用户是否收藏。
 * `combined_text` (Optional[str]): 用于AI的组合文本。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **10.15 `GET /forum/topics/` 获取论坛话题列表**

* **摘要**: 获取论坛话题列表，支持关键词、标签和分享类型过滤。
* **权限**: 已认证用户。
* **查询参数**:
 * `query_str` (Optional[str]): 搜索关键词。
 * `tag` (Optional[str]): 标签过滤。
 * `shared_type` (Optional[str]): 分享类型过滤。
 * `limit` (int): 限制返回数量。
 * `offset` (int): 偏移量。
* **响应体**: `List[schemas.ForumTopicResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **10.16 `GET /forum/topics/{topic_id}` 获取指定论坛话题详情**

* **摘要**: 获取指定ID的论坛话题详情。每次访问会增加浏览数。
* **权限**: 已认证用户。
* **路径参数**:
 * `topic_id` (int): 话题ID。
* **响应体**: `schemas.ForumTopicResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.17 `PUT /forum/topics/{topic_id}` 更新指定论坛话题**

* **摘要**: 更新指定ID的论坛话题内容。
* **权限**: 话题发布者。
* **路径参数**:
 * `topic_id` (int): 话题ID。
* **请求体**: `schemas.ForumTopicBase` (所有字段 Optional)。
* **响应体**: `schemas.ForumTopicResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.18 `DELETE /forum/topics/{topic_id}` 删除指定论坛话题**

* **摘要**: 删除指定ID的论坛话题及其所有评论和点赞。
* **权限**: 话题发布者。
* **路径参数**:
 * `topic_id` (int): 话题ID。
* **响应体**: `{"message": "Forum topic and its comments/likes deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.19 `POST /forum/topics/{topic_id}/comments/` 为论坛话题添加评论**

* **摘要**: 为指定论坛话题添加评论。
* **权限**: 已认证用户。
* **路径参数**:
 * `topic_id` (int): 话题ID。
* **请求体**: `schemas.ForumCommentBase`
 * `content` (str): 评论内容。
 * `parent_comment_id` (Optional[int]): 父评论ID，用于楼中楼回复。
* **响应体**: `schemas.ForumCommentResponse`
 * `id` (int): 评论ID。
 * `topic_id` (int): 所属话题ID。
 * `owner_id` (int): 发布者ID。
 * `owner_name` (Optional[str]): 发布者名字。
 * `likes_count` (int): 点赞数。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (Optional[datetime]): 更新时间。
 * `is_liked_by_current_user` (bool): 当前用户是否点赞。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.20 `GET /forum/topics/{topic_id}/comments/` 获取论坛话题的评论列表**

* **摘要**: 获取指定论坛话题的评论列表。
* **权限**: 已认证用户。
* **路径参数**:
 * `topic_id` (int): 话题ID。
* **查询参数**:
 * `parent_comment_id` (Optional[int]): 按父评论ID过滤（楼中楼）。
 * `limit` (int): 限制返回数量。
 * `offset` (int): 偏移量。
* **响应体**: `List[schemas.ForumCommentResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.21 `PUT /forum/comments/{comment_id}` 更新指定论坛评论**

* **摘要**: 更新指定ID的论坛评论内容（目前只允许更新`content`）。
* **权限**: 评论发布者。
* **路径参数**:
 * `comment_id` (int): 评论ID。
* **请求体**: `schemas.ForumCommentBase` (只包含`content`，其他字段忽略)。
* **响应体**: `schemas.ForumCommentResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`, `400 Bad Request`

### **10.22 `DELETE /forum/comments/{comment_id}` 删除指定论坛评论**

* **摘要**: 删除指定ID的论坛评论。如果评论有子评论，则会级联删除所有回复。
* **权限**: 评论发布者。
* **路径参数**:
 * `comment_id` (int): 评论ID。
* **响应体**: `{"message": "Forum comment and its children/likes deleted successfully"}`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **10.23 `POST /forum/likes/` 点赞论坛话题或评论**

* **摘要**: 点赞一个论坛话题或评论。
* **权限**: 已认证用户。
* **请求体**: `Dict[str, Any]` (必须提供`topic_id`或`comment_id`其中一个，不能同时提供)。
 * `topic_id` (Optional[int]): 要点赞的话题ID。
 * `comment_id` (Optional[int]): 要点赞的评论ID。
* **响应体**: `schemas.ForumLikeResponse`
 * `id` (int): 点赞记录ID。
 * `owner_id` (int): 点赞者ID。
 * `topic_id` (Optional[int]): 所属话题ID。
 * `comment_id` (Optional[int]): 所属评论ID。
 * `created_at` (datetime): 点赞时间。
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found`, `409 Conflict` (已点赞)

### **10.24 `DELETE /forum/likes/` 取消点赞论坛话题或评论**

* **摘要**: 取消点赞一个论坛话题或评论。
* **权限**: 已认证用户。
* **请求体**: `Dict[str, Any]` (必须提供`topic_id`或`comment_id`其中一个，不能同时提供)。
 * `topic_id` (Optional[int]): 要取消点赞的话题ID。
 * `comment_id` (Optional[int]): 要取消点赞的评论ID。
* **响应体**: `{"message": "Like removed successfully"}`
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found`

### **10.25 `POST /forum/follow/` 关注一个用户**

* **摘要**: 关注另一个用户。
* **权限**: 已认证用户。
* **请求体**: `Dict[str, Any]`
 * `followed_id` (int): 被关注用户的ID。
* **响应体**: `schemas.UserFollowResponse`
 * `id` (int): 关注记录ID。
 * `follower_id` (int): 关注者ID。
 * `followed_id` (int): 被关注者ID。
 * `created_at` (datetime): 关注时间。
* **常见状态码**: `200 OK`, `400 Bad Request` (不能关注自己), `401 Unauthorized`, `404 Not Found` (用户不存在), `409 Conflict` (已关注)

### **10.26 `DELETE /forum/unfollow/` 取消关注一个用户**

* **摘要**: 取消关注另一个用户。
* **权限**: 已认证用户。
* **请求体**: `Dict[str, Any]`
 * `followed_id` (int): 要取消关注的用户的ID。
* **响应体**: `{"message": "Unfollowed successfully"}`
* **常见状态码**: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found` (未关注)

---

## **11. 成就与积分**

### **11.1 `POST /admin/achievements/definitions` 【管理员专用】创建新的成就定义**

* **摘要**: 创建一个新的成就定义。
* **权限**: 系统管理员。
* **请求体**: `schemas.AchievementCreate`
 * `name` (str): 成就名称。
 * `description` (str): 成就描述。
 * `criteria_type` (Literal[...]): 达成成就的条件类型。
 * `criteria_value` (float): 达成成就所需的数值门槛。
 * `badge_url` (Optional[str]): 勋章图片URL。
 * `reward_points` (int): 达成此成就额外奖励的积分。
 * `is_active` (bool): 成就是否启用。
* **响应体**: `schemas.AchievementResponse`
 * `id` (int): 成就ID。
 * 所有 `AchievementCreate` 中的字段。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `409 Conflict` (名称已存在)

### **11.2 `GET /achievements/definitions` 获取所有成就定义（可供所有用户查看）**

* **摘要**: 获取平台所有成就的定义列表。
* **权限**: 任何已认证用户。
* **查询参数**:
 * `is_active` (Optional[bool]): 按激活状态过滤。
 * `criteria_type` (Optional[str]): 按条件类型过滤。
* **响应体**: `List[schemas.AchievementResponse]`
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **11.3 `GET /achievements/definitions/{achievement_id}` 获取指定成就定义详情**

* **摘要**: 获取指定ID的成就定义详情。
* **权限**: 任何已认证用户。
* **路径参数**:
 * `achievement_id` (int): 成就定义ID。
* **响应体**: `schemas.AchievementResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **11.4 `PUT /admin/achievements/definitions/{achievement_id}` 【管理员专用】更新指定成就定义**

* **摘要**: 更新指定成就定义。
* **权限**: 系统管理员。
* **路径参数**:
 * `achievement_id` (int): 成就定义ID。
* **请求体**: `schemas.AchievementUpdate` (所有字段 Optional)。
* **响应体**: `schemas.AchievementResponse`
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`

### **11.5 `DELETE /admin/achievements/definitions/{achievement_id}` 【管理员专用】删除指定成就定义**

* **摘要**: 删除指定成就定义。
* **权限**: 系统管理员。
* **路径参数**:
 * `achievement_id` (int): 成就定义ID。
* **响应体**: `204 No Content`
* **常见状态码**: `204 No Content`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`

### **11.6 `GET /users/me/points` 获取当前用户积分余额和上次登录时间**

* **摘要**: 获取当前用户总积分余额和上次登录时间。
* **权限**: 已认证用户。
* **响应体**: `schemas.StudentResponse` (只包含积分、登录时间等相关字段信息)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `404 Not Found`

### **11.7 `GET /users/me/points/history` 获取当前用户积分交易历史**

* **摘要**: 获取当前用户的积分交易历史记录。
* **权限**: 已认证用户。
* **查询参数**:
 * `transaction_type` (Optional[Literal["EARN", "CONSUME", "ADMIN_ADJUST"]]):按交易类型过滤。
 * `limit` (int): 限制返回数量。
 * `offset` (int): 偏移量。
* **响应体**: `List[schemas.PointTransactionResponse]`
 * `id` (int): 交易ID。
 * `user_id` (int): 用户ID。
 * `amount` (int): 积分变动金额（正数获得，负数消耗）。
 * `reason` (Optional[str]): 积分变动理由。
 * `transaction_type` (str): 交易类型。
 * `related_entity_type` (Optional[str]): 关联实体类型。
 * `related_entity_id` (Optional[int]): 关联实体ID。
 * `created_at` (datetime): 交易时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **11.8 `GET /users/me/achievements` 获取当前用户已获得的成就列表**

* **摘要**: 获取当前用户已获得的成就列表，包含成就的详细元数据。
* **权限**: 已认证用户。
* **响应体**: `List[schemas.UserAchievementResponse]`
 * `id` (int): 用户成就记录ID。
 * `user_id` (int): 用户ID。
 * `achievement_id` (int): 成就定义ID。
 * `earned_at` (datetime): 获得时间。
 * `is_notified` (bool): 是否已通知。
 * `achievement_name` (Optional[str]): 成就名称。
 * `achievement_description` (Optional[str]): 成就描述。
 * `badge_url` (Optional[str]): 勋章图片URL。
 * `reward_points` (Optional[int]): 获得此成就奖励的积分。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **11.9 `POST /admin/points/reward` 【管理员专用】为指定用户手动发放/扣除积分**

* **摘要**: 管理员可以手动为指定用户发放或扣除积分。
* **权限**: 系统管理员。
* **请求体**: `schemas.PointsRewardRequest`
 * `user_id` (int): 目标用户ID。
 * `amount` (int): 积分变动数量，正数代表增加，负数代表减少。
 * `reason` (Optional[str]): 积分变动理由。
 * `transaction_type` (Literal["EARN", "CONSUME", "ADMIN_ADJUST"]): 交易类型，默认`ADMIN_ADJUST`。
 * `related_entity_type` (Optional[str]): 关联实体类型。
 * `related_entity_id` (Optional[int]): 关联实体ID。
* **响应体**: `schemas.PointTransactionResponse` (最新创建的积分交易记录)。
* **常见状态码**: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` (用户不存在)


## **12. 仪表盘与系统监控**

### **12.1 `GET /dashboard/summary` 获取首页工作台概览数据**

* **摘要**: 获取首页个人工作台的概览数据，包括活跃项目、完成项目、学习中课程、完成课程等。
* **权限**: 已认证用户。
* **响应体**: `schemas.DashboardSummaryResponse`
 * `active_projects_count` (int): 活跃项目数。
 * `completed_projects_count` (int): 已完成项目数。
 * `learning_courses_count` (int): 学习中课程数。
 * `completed_courses_count` (int): 已完成课程数。
 * `active_chats_count` (int): 活跃聊天室数。
 * `unread_messages_count` (int): 未读消息数 (当前模拟为0)。
 * `resume_completion_percentage` (float): 简历完成度百分比。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **12.2 `GET /dashboard/projects` 获取当前用户参与的项目卡片列表**

* **摘要**: 获取当前用户参与的项目卡片列表（简化版，目前返回所有项目卡片）。
* **权限**: 已认证用户。
* **查询参数**:
 * `status_filter` (Optional[str]): 按项目状态过滤。
* **响应体**: `List[schemas.DashboardProjectCard]`
 * `id` (int): 项目ID。
 * `title` (str): 项目标题。
 * `progress` (float): 项目进度（模拟值）。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **12.3 `GET /dashboard/courses` 获取当前用户学习的课程卡片列表**

* **摘要**: 获取当前用户学习的课程卡片列表。
* **权限**: 已认证用户。
* **查询参数**:
 * `status_filter` (Optional[str]): 按课程状态过滤。
* **响应体**: `List[schemas.DashboardCourseCard]`
 * `id` (int): 课程ID。
 * `title` (str): 课程标题。
 * `progress` (float): 学习进度。
 * `last_accessed` (Optional[datetime]): 最后访问时间。
* **常见状态码**: `200 OK`, `401 Unauthorized`

### **12.4 `GET /health` 健康检查**

* **摘要**: 检查API服务是否正常运行。
* **权限**: 无需认证。
* **响应体**: `{"status": "ok", "message": "鸿庆书云创新协作平台后端API运行正常！"}`
* **常见状态码**: `200 OK`

---