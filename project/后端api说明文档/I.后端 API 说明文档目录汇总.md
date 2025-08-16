### 前言
* 欢迎。
* API 约定
 * 认证机制 (JWT Token)
 * 错误码说明
 * 数据类型约定 (请求体, 响应体)
 * 分页、过滤、排序规范

### I. 系统基础服务

* **1.1 健康检查**
 * 1.1.1 检查API服务状态 (GET /health)

### II. 用户与认证管理

* **2.1 用户认证**
 * 2.1.1 用户注册 (POST /register)
 * 2.1.2 用户登录并获取JWT令牌 (POST /token)
* **2.2 个人资料管理**
 * 2.2.1 获取当前登录用户详情 (GET /users/me)
 * 2.2.2 更新当前登录用户详情 (PUT /users/me)
* **2.3 用户积分与成就**
 * 2.3.1 获取当前用户积分余额和上次登录时间 (GET /users/me/points)
 * 2.3.2 获取当前用户积分交易历史 (GET /users/me/points/history)
 * 2.3.3 获取当前用户已获得的成就列表 (GET /users/me/achievements)

### III. 项目与课程管理

* **3.1 项目管理**
 * 3.1.1 创建新项目 (POST /projects/)
 * 3.1.2 获取所有项目列表 (GET /projects/)
 * 3.1.3 获取指定项目详情 (GET /projects/{project_id})
 * 3.1.4 更新指定项目 (PUT /projects/{project_id})
* **3.2 项目成员与申请**
 * 3.2.1 学生申请加入项目 (POST /projects/{project_id}/apply)
 * 3.2.2 获取项目所有申请列表 (GET /projects/{project_id}/applications)
 * 3.2.3 处理项目申请 (POST /projects/applications/{application_id}/process)
 * 3.2.4 获取项目成员列表 (GET /projects/{project_id}/members)
* **3.3 课程管理**
 * 3.3.1 创建新课程 (POST /courses/)
 * 3.3.2 获取所有课程列表 (GET /courses/)
 * 3.3.3 获取指定课程详情 (GET /courses/{course_id})
 * 3.3.4 更新指定课程 (PUT /courses/{course_id})
* **3.4 课程参与与材料**
 * 3.4.1 用户报名课程 (POST /courses/{course_id}/enroll)
 * 3.4.2 更新当前用户课程学习进度和状态 (PUT /users/me/courses/{course_id})
 * 3.4.3 为指定课程上传新材料（文件或链接） (POST /courses/{course_id}/materials/)
 * 3.4.4 获取指定课程的所有材料列表 (GET /courses/{course_id}/materials/)
 * 3.4.5 获取指定课程材料详情 (GET /courses/{course_id}/materials/{material_id})
 * 3.4.6 更新指定课程材料 (PUT /courses/{course_id}/materials/{material_id})
 * 3.4.7 删除指定课程材料 (DELETE /courses/{course_id}/materials/{material_id})

### IV. 个人知识与协作工具

* **4.1 仪表盘 / 个人工作台**
 * 4.1.1 获取首页工作台概览数据 (GET /dashboard/summary)
 * 4.1.2 获取当前用户参与的项目卡片列表 (GET /dashboard/projects)
 * 4.1.3 获取当前用户学习的课程卡片列表 (GET /dashboard/courses)
* **4.2 笔记管理**
 * 4.2.1 创建新笔记 (POST /notes/)
 * 4.2.2 获取当前用户所有笔记 (GET /notes/)
 * 4.2.3 获取指定笔记详情 (GET /notes/{note_id})
 * 4.2.4 更新指定笔记 (PUT /notes/{note_id})
 * 4.2.5 删除指定笔记 (DELETE /notes/{note_id})
* **4.3 随手记录**
 * 4.3.1 创建新随手记录 (POST /daily-records/)
 * 4.3.2 获取当前用户所有随手记录 (GET /daily-records/)
 * 4.3.3 获取指定随手记录详情 (GET /daily-records/{record_id})
 * 4.3.4 更新指定随手记录 (PUT /daily-records/{record_id})
 * 4.3.5 删除指定随手记录 (DELETE /daily-records/{record_id})
* **4.4 文件夹与收藏管理**
 * 4.4.1 创建新文件夹 (POST /folders/)
 * 4.4.2 获取当前用户所有文件夹 (GET /folders/)
 * 4.4.3 获取指定文件夹详情 (GET /folders/{folder_id})
 * 4.4.4 更新指定文件夹 (PUT /folders/{folder_id})
 * 4.4.5 删除指定文件夹 (DELETE /folders/{folder_id})
 * 4.4.6 创建新收藏内容 (POST /collections/)
 * 4.4.7 快速收藏平台内部内容 (POST /collections/add-from-platform)
 * 4.4.8 获取当前用户所有收藏内容 (GET /collections/)
 * 4.4.9 获取指定收藏内容详情 (GET /collections/{content_id})
 * 4.4.10 更新指定收藏内容 (PUT /collections/{content_id})
 * 4.4.11 删除指定收藏内容 (DELETE /collections/{content_id})
* **4.5 知识库管理**
 * 4.5.1 创建新知识库 (POST /knowledge-bases/)
 * 4.5.2 获取当前用户所有知识库 (GET /knowledge-bases/)
 * 4.5.3 获取指定知识库详情 (GET /knowledge-bases/{kb_id})
 * 4.5.4 更新指定知识库 (PUT /knowledge-bases/{kb_id})
 * 4.5.5 删除指定知识库 (DELETE /knowledge-bases/{kb_id})
 * 4.5.6 在指定知识库中创建新文件夹 (POST /knowledge-bases/{kb_id}/folders/)
 * 4.5.7 获取指定知识库下所有文件夹和软链接内容 (GET /knowledge-bases/{kb_id}/folders/)
 * 4.5.8 获取指定知识库文件夹详情及其内容 (GET /knowledge-bases/{kb_id}/folders/{kb_folder_id})
 * 4.5.9 更新指定知识库文件夹 (PUT /knowledge-bases/{kb_id}/folders/{kb_folder_id})
 * 4.5.10 删除指定知识库文件夹 (DELETE /knowledge-bases/{kb_id}/folders/{kb_folder_id})
 * 4.5.11 在指定知识库中创建新文章 (POST /knowledge-bases/{kb_id}/articles/)
 * 4.5.12 获取指定知识库的所有文章 (GET /knowledge-bases/{kb_id}/articles/)
 * 4.5.13 获取指定文章详情 (GET /articles/{article_id})
 * 4.5.14 更新指定知识文章 (PUT /knowledge-bases/{kb_id}/articles/{article_id})
 * 4.5.15 删除指定文章 (DELETE /articles/{article_id})
 * 4.5.16 上传新知识文档到知识库 (POST /knowledge-bases/{kb_id}/documents/)
 * 4.5.17 获取知识库下所有知识文档 (GET /knowledge-bases/{kb_id}/documents/)
 * 4.5.18 获取指定知识文档详情 (GET /knowledge-bases/{kb_id}/documents/{document_id})
 * 4.5.19 删除指定知识文档 (DELETE /knowledge-bases/{kb_id}/documents/{document_id})
 * 4.5.20 获取知识文档的原始文本内容 (DEBUG) (GET /knowledge-bases/{kb_id}/documents/{document_id}/content)
 * 4.5.21 获取知识文档文本块列表 (DEBUG) (GET /knowledge-bases/{kb_id}/documents/{document_id}/chunks)
* **4.6 聊天与群组协作**
 * 4.6.1 创建新的聊天室 (POST /chat-rooms/)
 * 4.6.2 获取当前用户所属的所有聊天室 (GET /chatrooms/)
 * 4.6.3 获取指定聊天室详情 (GET /chatrooms/{room_id})
 * 4.6.4 更新指定聊天室 (PUT /chatrooms/{room_id}/)
 * 4.6.5 删除指定聊天室 (DELETE /chatrooms/{room_id})
 * 4.6.6 获取指定聊天室的所有成员列表 (GET /chatrooms/{room_id}/members)
 * 4.6.7 设置聊天室成员的角色 (PUT /chat-rooms/{room_id}/members/{member_id}/set-role)
 * 4.6.8 从聊天室移除成员 (DELETE /chat-rooms/{room_id}/members/{member_id})
 * 4.6.9 向指定聊天室发起入群申请 (POST /chat-rooms/{room_id}/join-request)
 * 4.6.10 获取指定聊天室的入群申请列表 (GET /chat-rooms/{room_id}/join-requests)
 * 4.6.11 处理入群申请 (POST /chat-rooms/join-requests/{request_id}/process)
 * 4.6.12 在指定聊天室发送新消息 (POST /chatrooms/{room_id}/messages/)
 * 4.6.13 获取指定聊天室的历史消息 (GET /chatrooms/{room_id}/messages/)
 * 4.6.14 WebSocket 聊天室接口 (WS /ws/chat/{room_id})
* **4.7 论坛与社区互动**
 * 4.7.1 发布新论坛话题 (POST /forum/topics/)
 * 4.7.2 获取论坛话题列表 (GET /forum/topics/)
 * 4.7.3 获取指定论坛话题详情 (GET /forum/topics/{topic_id})
 * 4.7.4 更新指定论坛话题 (PUT /forum/topics/{topic_id})
 * 4.7.5 删除指定论坛话题 (DELETE /forum/topics/{topic_id})
 * 4.7.6 为论坛话题添加评论 (POST /forum/topics/{topic_id}/comments/)
 * 4.7.7 获取论坛话题的评论列表 (GET /forum/topics/{topic_id}/comments/)
 * 4.7.8 更新指定论坛评论 (PUT /forum/comments/{comment_id})
 * 4.7.9 删除指定论坛评论 (DELETE /forum/comments/{comment_id})
 * 4.7.10 点赞论坛话题或评论 (POST /forum/likes/)
 * 4.7.11 取消点赞论坛话题或评论 (DELETE /forum/likes/)
 * 4.7.12 关注一个用户 (POST /forum/follow/)
 * 4.7.13 取消关注一个用户 (DELETE /forum/unfollow/)

### V. 人工智能服务与配置

* **5.1 AI智能问答与搜索**
 * 5.1.1 AI智能问答 (通用、RAG或工具调用) (POST /ai/qa)
 * 5.1.2 智能语义搜索 (POST /search/semantic)
 * 5.1.3 获取当前用户的所有AI对话列表 (GET /users/me/ai-conversations)
 * 5.1.4 获取指定AI对话详情 (GET /users/me/ai-conversations/{conversation_id})
 * 5.1.5 获取指定AI对话的所有消息历史 (GET /users/me/ai-conversations/{conversation_id}/messages)
 * 5.1.6 更新指定AI对话的标题 (PUT /users/me/ai-conversations/{conversation_id})
 * 5.1.7 删除指定AI对话 (DELETE /users/me/ai-conversations/{conversation_id})
* **5.2 AI智能匹配**
 * 5.2.1 为指定学生推荐项目 (GET /recommend/projects/{student_id})
 * 5.2.2 为指定学生推荐课程 (GET /recommend/courses/{student_id})
 * 5.2.3 为指定项目推荐学生 (GET /projects/{project_id}/match-students)
* **5.3 用户AI服务配置**
 * 5.3.1 更新当前用户LLM配置 (PUT /users/me/llm-config)
 * 5.3.2 获取可配置的LLM服务商及模型列表 (GET /llm/available-models)
 * 5.3.3 创建新的MCP配置 (POST /mcp-configs/)
 * 5.3.4 获取当前用户所有MCP服务配置 (GET /mcp-configs/)
 * 5.3.5 更新指定MCP配置 (PUT /mcp-configs/{config_id})
 * 5.3.6 删除指定MCP服务配置 (DELETE /mcp-configs/{config_id})
 * 5.3.7 检查指定MCP服务的连通性 (POST /mcp-configs/{config_id}/check-status)
 * 5.3.8 获取智库聊天可用的MCP工具列表 (GET /llm/mcp-available-tools)
 * 5.3.9 创建新的搜索引擎配置 (POST /search-engine-configs/)
 * 5.3.10 获取当前用户所有搜索引擎配置 (GET /search-engine-configs/)
 * 5.3.11 获取指定搜索引擎配置详情 (GET /search-engine-configs/{config_id})
 * 5.3.12 更新指定搜索引擎配置 (PUT /search-engine-configs/{config_id})
 * 5.3.13 删除指定搜索引擎配置 (DELETE /search-engine-configs/{config_id})
 * 5.3.14 检查指定搜索引擎的连通性 (POST /search-engine-configs/{config_id}/check-status)
 * 5.3.15 执行一次网络搜索 (POST /ai/web-search)
 * 5.3.16 为当前用户创建新的TTS配置 (POST /users/me/tts_configs)
 * 5.3.17 获取当前用户的所有TTS配置 (GET /users/me/tts_configs)
 * 5.3.18 获取指定TTS配置详情 (GET /users/me/tts_configs/{config_id})
 * 5.3.19 更新指定TTS配置 (PUT /users/me/tts_configs/{config_id})
 * 5.3.20 删除指定TTS配置 (DELETE /users/me/tts_configs/{config_id})
 * 5.3.21 设置指定TTS配置为激活状态 (PUT /users/me/tts_configs/{config_id}/set_active)

### VI. 管理员与系统维护

* **6.1 用户管理 (管理员)**
 * 6.1.1 获取所有学生列表 (GET /students/)
 * 6.1.2 获取指定学生详情 (GET /students/{student_id})
 * 6.1.3 设置系统管理员权限 (PUT /admin/users/{user_id}/set-admin)
* **6.2 成就与积分管理 (管理员)**
 * 6.2.1 创建新的成就定义 (POST /admin/achievements/definitions)
 * 6.2.2 获取所有成就定义（可供所有用户查看） (GET /achievements/definitions)
 * 6.2.3 获取指定成就定义详情 (GET /achievements/definitions/{achievement_id})
 * 6.2.4 更新指定成就定义 (PUT /admin/achievements/definitions/{achievement_id})
 * 6.2.5 删除指定成就定义 (DELETE /admin/achievements/definitions/{achievement_id})
 * 6.2.6 手动发放/扣除积分 (POST /admin/points/reward)

---
