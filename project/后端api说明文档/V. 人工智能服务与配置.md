
#### 5.1 AI智能问答与搜索

**5.1.1 AI智能问答 (通用、RAG或工具调用)**

* **POST `/ai/qa`**

 * **摘要**: 使用LLM进行问答，并支持对话历史记录。支持上传文件或图片作为临时上下文对AI进行提问。如果启用 `use_tools`，LLM将尝试智能选择并调用工具 (RAG、网络搜索、MCP工具)。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **请求体**: `multipart/form-data`
 * `query` (string): 用户的问题文本。
 * `conversation_id` (integer, 可选): 要继续的对话 Session ID。如果为空，则开始新的对话。
 * `kb_ids` (List[integer], 可选, 作为 JSON 字符串提交): 要检索的知识库ID列表。
 * `note_ids` (List[integer], 可选, 作为 JSON 字符串提交): 要检索的笔记ID列表。
 * `use_tools` (boolean, 可选, 默认为 `false`): 是否启用AI智能工具调用（例如网络搜索、RAG等）。
 * `preferred_tools` (List[string], 可选, 作为 JSON 字符串提交): AI在工具模式下偏好使用的工具类型列表，可选值包括 `"rag"`、`"web_search"`、`"mcp_tool"`。
 * `llm_model_id` (string, 可选): 本次会话使用的特定LLM模型ID。如果未提供，则使用用户默认配置的模型。
 * `uploaded_file` (file, 可选): 用户上传的文件（图片或文档，支持TXT, MD, PDF, DOCX, 常见图片格式）作为AI提问的临时上下文。

 * **响应体**: `schemas.AIQAResponse`
 * `answer` (string): AI生成的回答。
 * `answer_mode` (string): 回答模式，例如："General_mode" (通用回答), "Tool_Use_mode" (工具调用模式), "Tool_Use_Failed_Answer" (工具调用但AI未能生成清晰答案), "Failed_General_mode" (通用模式失败)。
 * `llm_type_used` (string, 可选): 本次消息生成时实际使用的LLM类型。
 * `llm_model_used` (string, 可选): 本次消息生成时实际使用的LLM模型ID。
 * `conversation_id` (integer): 当前问答所关联的对话 Session ID。
 * `turn_messages` (List[`schemas.AIConversationMessageResponse`]): 当前轮次（包括用户问题和AI回复）产生的完整消息序列。
 * `id` (integer): 消息ID。
 * `conversation_id` (integer): 所属对话ID。
 * `role` (string): 消息角色 ("user", "assistant", "tool_call", "tool_output")。
 * `content` (string): 消息内容（文本）。
 * `tool_calls_json` (object, 可选): 如果角色是 "tool_call"，存储工具调用的 JSON 数据。
 * `tool_output_json` (object, 可选): 如果角色是 "tool_output"，存储工具输出的 JSON 数据。
 * `llm_type_used` (string, 可选): 本次消息使用的LLM类型。
 * `llm_model_used` (string, 可选): 本次消息使用的LLM模型ID。
 * `sent_at` (datetime): 消息发送时间 (ISO 8601 格式)。
 * `source_articles` (List[object], 可选): 如果使用了RAG工具，返回RAG检索到的相关文档来源信息（包括ID, 标题, 类型）。
 * `search_results` (List[object], 可选): 如果使用了网络搜索工具，返回网络搜索结果（包含标题, 摘要, 链接）。

 * **常见状态码**:
 * `200 OK`: AI问答成功。
 * `400 Bad Request`: 参数校验失败（例如，用户未配置LLM API，或提供的文件类型不支持，或消息数据格式不正确）。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 指定的对话 ID 不存在或无权访问。
 * `500 Internal Server Error`: 服务器内部错误（例如，API密钥解密失败，处理上传文件失败）。
 * `503 Service Unavailable`: AI服务调用失败（例如，LLM API不可用）。

**5.1.2 智能语义搜索**

* **POST `/search/semantic`**

 * **摘要**: 通过语义搜索，在用户可访问的项目、课程、知识库文章和笔记中查找相关内容。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **请求体**: `application/json`
 * `query` (string): 用于语义搜索的查询文本。
 * `item_types` (List[string], 可选): 要搜索的内容类型列表，可选值包括 `"project"`、`"course"`、`"knowledge_article"`、`"note"`。如果为空，则默认搜索所有类型。
 * `limit` (integer, 默认为 10): 返回的最大搜索结果数量。

 * **响应体**: `List[schemas.SemanticSearchResult]`
 * `id` (integer): 搜索结果的实体ID。
 * `title` (string): 搜索结果的标题。
 * `type` (string): 搜索结果的实体类型（例如："project", "course", "knowledge_article", "note"）。
 * `content_snippet` (string, 可选): 搜索结果内容的摘要片段。
 * `relevance_score` (float): 搜索结果与查询的相关性得分，越高表示越相关。

 * **常见状态码**:
 * `200 OK`: 语义搜索成功。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 未找到可搜索的内容或指定类型无数据，或未找到与查询相关的初步结果。
 * `500 Internal Server Error`: 服务器内部错误。
 * `503 Service Unavailable`: 无法生成查询嵌入（例如，LLM配置不正确或API密钥无效）。

**5.1.3 获取当前用户的所有AI对话列表**

* **GET `/users/me/ai-conversations`**

 * **摘要**: 获取当前用户的所有AI对话列表，按最新更新时间降序排序。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **查询参数**:
 * `limit` (integer, 默认为 10): 返回对话的最大数量。
 * `offset` (integer, 默认为 0): 查询结果的偏移量，用于分页。

 * **响应体**: `List[schemas.AIConversationResponse]`
 * `id` (integer): 对话ID。
 * `user_id` (integer): 对话所属用户ID。
 * `title` (string, 可选): 对话标题（可由AI生成或用户自定义）。
 * `created_at` (datetime): 对话创建时间 (ISO 8601 格式)。
 * `last_updated` (datetime): 对话最后更新时间 (ISO 8601 格式)。
 * `total_messages_count` (integer, 可选): 对话中的总消息数量。

 * **常见状态码**:
 * `200 OK`: 成功获取对话列表。
 * `401 Unauthorized`: 未提供或无效的认证令牌。

**5.1.4 获取指定AI对话详情**

* **GET `/users/me/ai-conversations/{conversation_id}`**

 * **摘要**: 获取指定ID的AI对话详情。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **路径参数**:
 * `conversation_id` (integer): 要获取详情的对话ID。

 * **响应体**: `schemas.AIConversationResponse`
 * `id` (integer): 对话ID。
 * `user_id` (integer): 对话所属用户ID。
 * `title` (string, 可选): 对话标题。
 * `created_at` (datetime): 对话创建时间 (ISO 8601 格式)。
 * `last_updated` (datetime): 对话最后更新时间 (ISO 8601 格式)。
 * `total_messages_count` (integer, 可选): 对话中的总消息数量。

 * **常见状态码**:
 * `200 OK`: 成功获取对话详情。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 对话未找到或无权访问。

**5.1.5 获取指定AI对话的所有消息历史**

* **GET `/users/me/ai-conversations/{conversation_id}/messages`**

 * **摘要**: 获取指定AI对话的所有消息历史记录。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **路径参数**:
 * `conversation_id` (integer): 要获取消息历史的对话ID。

 * **查询参数**:
 * `limit` (integer, 默认为 50): 返回消息的最大数量。
 * `offset` (integer, 默认为 0): 查询结果的偏移量，用于分页。

 * **响应体**: `List[schemas.AIConversationMessageResponse]`
 * `id` (integer): 消息ID。
 * `conversation_id` (integer): 所属对话ID。
 * `role` (string): 消息角色 ("user", "assistant", "tool_call", "tool_output")。
 * `content` (string): 消息内容（文本）。
 * `tool_calls_json` (object, 可选): 如果角色是 "tool_call"，存储工具调用的 JSON 数据。
 * `tool_output_json` (object, 可选): 如果角色是 "tool_output"，存储工具输出的 JSON 数据。
 * `llm_type_used` (string, 可选): 本次消息使用的LLM类型。
 * `llm_model_used` (string, 可选): 本次消息使用的LLM模型ID。
 * `sent_at` (datetime): 消息发送时间 (ISO 8601 格式)。

 * **常见状态码**:
 * `200 OK`: 成功获取消息历史。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 对话未找到或无权访问。

**5.1.6 更新指定AI对话的标题**

* **PUT `/users/me/ai-conversations/{conversation_id}`**

 * **摘要**: 更新指定AI对话的标题。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **路径参数**:
 * `conversation_id` (integer): 要更新标题的对话ID。

 * **请求体**: `application/json`
 * `title` (string, 可选): 对话的新标题。

 * **响应体**: `schemas.AIConversationResponse`
 * `id` (integer): 对话ID。
 * `user_id` (integer): 对话所属用户ID。
 * `title` (string, 可选): 对话标题。
 * `created_at` (datetime): 对话创建时间 (ISO 8601 格式)。
 * `last_updated` (datetime): 对话最后更新时间 (ISO 8601 格式)。
 * `total_messages_count` (integer, 可选): 对话中的总消息数量。

 * **常见状态码**:
 * `200 OK`: 成功更新对话标题。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 对话未找到或无权访问。

**5.1.7 删除指定AI对话**

* **DELETE `/users/me/ai-conversations/{conversation_id}`**

 * **摘要**: 删除指定AI对话及其所有消息历史。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **路径参数**:
 * `conversation_id` (integer): 要删除的对话ID。

 * **响应体**: `204 No Content`

 * **常见状态码**:
 * `204 No Content`: 成功删除对话。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 对话未找到或无权访问。

---

#### 5.2 AI智能匹配

**5.2.1 为指定学生推荐项目**

* **GET `/recommend/projects/{student_id}`**

 * **摘要**: 为指定学生推荐相关项目，综合考虑内容相关性、技能熟练度、时间投入和地理位置等多种匹配因素。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **路径参数**:
 * `student_id` (integer): 要为其推荐项目的学生ID。

 * **查询参数**:
 * `initial_k` (integer, 默认为 50): 初步筛选的候选项目数量。
 * `final_k` (integer, 默认为 3): 最终返回的推荐项目数量。

 * **响应体**: `List[schemas.MatchedProject]`
 * `project_id` (integer): 推荐的项目ID。
 * `title` (string): 项目标题。
 * `description` (string): 项目描述。
 * `similarity_stage1` (float): 第一阶段（嵌入相似度）的综合匹配得分。
 * `relevance_score` (float): 经过重排（Rerank）后的最终相关性得分。
 * `match_rationale` (string, 可选): AI生成的学生与项目匹配理由及建议。

 * **常见状态码**:
 * `200 OK`: 成功获取推荐项目列表（可能为空列表）。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 指定的学生不存在，或没有项目可供推荐（例如数据库中无项目或所有项目嵌入无效）。
 * `500 Internal Server Error`: 服务器内部错误（例如，AI服务调用失败）。

**5.2.2 为指定学生推荐课程**

* **GET `/recommend/courses/{student_id}`**

 * **摘要**: 为指定学生推荐相关课程，综合考虑内容相关性、技能熟练度、时间投入和地理位置等多种匹配因素。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **路径参数**:
 * `student_id` (integer): 要为其推荐课程的学生ID。

 * **查询参数**:
 * `initial_k` (integer, 默认为 50): 初步筛选的候选课程数量。
 * `final_k` (integer, 默认为 3): 最终返回的推荐课程数量。

 * **响应体**: `List[schemas.MatchedCourse]`
 * `course_id` (integer): 推荐的课程ID。
 * `title` (string): 课程标题。
 * `description` (string, 可选): 课程描述。
 * `instructor` (string, 可选): 课程讲师。
 * `category` (string, 可选): 课程类别。
 * `cover_image_url` (string, 可选): 课程封面图片URL。
 * `similarity_stage1` (float): 第一阶段（嵌入相似度）的综合匹配得分。
 * `relevance_score` (float): 经过重排（Rerank）后的最终相关性得分。
 * `match_rationale` (string, 可选): AI生成的学生与课程匹配理由及建议。

 * **常见状态码**:
 * `200 OK`: 成功获取推荐课程列表（可能为空列表）。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 指定的学生不存在，或没有课程可供推荐（例如数据库中无课程或所有课程嵌入无效）。
 * `500 Internal Server Error`: 服务器内部错误（例如，AI服务调用失败）。

**5.2.3 为指定项目推荐学生**

* **GET `/projects/{project_id}/match-students`**

 * **摘要**: 为指定项目推荐合适的学生，综合考虑内容相关性、技能熟练度、时间投入和地理位置等多种匹配因素。
 * **权限**: 需要认证 (通过 JWT Token)。

 * **路径参数**:
 * `project_id` (integer): 要为其推荐学生的项目ID。

 * **查询参数**:
 * `initial_k` (integer, 默认为 50): 初步筛选的候选学生数量。
 * `final_k` (integer, 默认为 3): 最终返回的推荐学生数量。

 * **响应体**: `List[schemas.MatchedStudent]`
 * `student_id` (integer): 推荐的学生ID。
 * `name` (string): 学生姓名。
 * `major` (string): 学生专业。
 * `skills` (List[`schemas.SkillWithProficiency`], 可选): 学生的技能列表及熟练度详情。
 * `similarity_stage1` (float): 第一阶段（嵌入相似度）的综合匹配得分。
 * `relevance_score` (float): 经过重排（Rerank）后的最终相关性得分。
 * `match_rationale` (string, 可选): AI生成的项目与学生匹配理由及建议。

 * **常见状态码**:
 * `200 OK`: 成功获取推荐学生列表（可能为空列表）。
 * `401 Unauthorized`: 未提供或无效的认证令牌。
 * `404 Not Found`: 指定的项目不存在，或没有学生可供推荐（例如数据库中无学生或所有学生嵌入无效）。
 * `500 Internal Server Error`: 服务器内部错误（例如，AI服务调用失败）。

---
#### 5.3 用户AI服务配置

 **5.3.1 更新当前用户LLM配置 (PUT /users/me/llm-config)**
 * 摘要: 更新当前用户的LLM（大语言模型）API配置，密钥会加密存储。成功更新配置后，会尝试重新计算用户个人资料的嵌入向量。
 * 权限: 需要认证 (JWT Token)。
 * 请求体: `application/json`
 * `schemas.UserLLMConfigUpdate`
 * `llm_api_type` (str, 可选): LLM 服务商类型，可选值：`"openai"`, `"zhipu"`, `"siliconflow"`, `"huoshanengine"`, `"kimi"`, `"deepseek"`, `"custom_openai"`。
 * `llm_api_key` (str, 可选): LLM 服务的 API 密钥。如果提供，将被加密存储。传入 `null` 或空字符串表示清空现有密钥。
 * `llm_api_base_url` (str, 可选): LLM 服务的 API 基础 URL。
 * `llm_model_id` (str, 可选): LLM 服务的模型 ID。
 * 响应体: `schemas.StudentResponse`
 * `id` (int): 用户ID。
 * `email` (str, optional): 用户邮箱。
 * `phone_number` (str, optional): 用户手机号。
 * `username` (str): 用户名。
 * `school` (str, optional): 用户学校。
 * `name` (str, optional): 用户姓名。
 * `major` (str, optional): 用户专业。
 * `skills` (List[`schemas.SkillWithProficiency`], optional): 用户技能列表及熟练度。
 * `interests` (str, optional): 用户兴趣。
 * `bio` (str, optional): 用户简介。
 * `awards_competitions` (str, optional): 获奖和竞赛信息。
 * `academic_achievements` (str, optional): 学术成就。
 * `soft_skills` (str, optional): 软技能。
 * `portfolio_link` (str, optional): 个人作品集链接。
 * `preferred_role` (str, optional): 偏好角色。
 * `availability` (str, optional): 可用时间。
 * `location` (str, optional): 地理位置。
 * `combined_text` (str, optional): 用于AI模型嵌入的组合文本。
 * `embedding` (List[float], optional): 文本内容的嵌入向量。
 * `llm_api_type` (str, optional): 用户配置的LLM类型。
 * `llm_api_base_url` (str, optional): 用户配置的LLM基础URL。
 * `llm_model_id` (str, optional): 用户配置的LLM模型ID。
 * `llm_api_key_encrypted` (str, optional): LLM API密钥 (加密后)。**注意: 此字段不会包含明文密钥。**
 * `created_at` (datetime): 用户创建时间。
 * `updated_at` (datetime, optional): 最后更新时间。
 * `is_admin` (bool): 是否为管理员。
 * `total_points` (int): 用户总积分。
 * `last_login_at` (datetime, optional): 上次登录时间。
 * `login_count` (int): 登录次数。
 * `completed_projects_count` (int, optional): 用户创建并已完成的项目总数。
 * `completed_courses_count` (int, optional): 用户完成的课程总数。
 * 常见状态码: 200 OK (更新成功), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (用户未找到), 500 Internal Server Error (加密失败或内部错误)。

 **5.3.2 获取可配置的LLM服务商及模型列表 (GET /llm/available-models)**
 * 摘要: 返回所有支持的LLM服务商类型及其默认模型和可用模型列表。
 * 权限: 无需认证。
 * 请求体: 无
 * 响应体: `application/json` (字典类型)
 * `openai` (Dict):
 * `default_model` (str): 默认模型ID。
 * `available_models` (List[str]): 可用模型ID列表。
 * `notes` (str): 获取API密钥的说明。
 * `zhipu` (Dict): (类似 openai 的结构)
 * `siliconflow` (Dict): (类似 openai 的结构)
 * `huoshanengine` (Dict): (类似 openai 的结构)
 * `kimi` (Dict): (类似 openai 的结构)
 * `deepseek` (Dict): (类似 openai 的结构)
 * `custom_openai` (Dict): 自定义OpenAI兼容服务配置模板。
 * `default_model` (None): 无默认模型。
 * `available_models` (List[str]): 占位符，表示可使用任意模型ID。
 * `notes` (str): 说明需要用户提供完整API基础URL、密钥和模型ID。
 * 常见状态码: 200 OK (成功获取)。

 **5.3.3 创建新的MCP配置 (POST /mcp-configs/)**
 * 摘要: 为当前用户创建一条新的MCP (Multi-Cloud Platform) 服务配置，用于AI智能工具调用。
 * 权限: 需要认证 (JWT Token)。
 * 请求体: `application/json`
 * `schemas.UserMcpConfigCreate`
 * `name` (str): MCP 配置的唯一名称。
 * `mcp_type` (str, 可选): MCP 服务商类型，可选值：`"modelscope_community"` (阿里魔搭社区), `"custom_mcp"` (自定义MCP)。
 * `base_url` (str): MCP 服务的 API 基础 URL。
 * `protocol_type` (str, 可选): MCP 服务的协议类型，可选值：`"sse"` (Server-Sent Events), `"http_rest"` (HTTP RESTful API), `"websocket"`。 默认为 `"http_rest"`。
 * `api_key` (str, 可选): MCP 服务的 API 密钥。如果提供，将被加密存储。
 * `is_active` (bool, 可选): 配置是否激活。默认为 `True`。
 * `description` (str, 可选): 配置描述。
 * 响应体: `schemas.UserMcpConfigResponse`
 * `id` (int): 配置ID。
 * `owner_id` (int): 配置所有者ID。
 * `name` (str): 配置名称。
 * `mcp_type` (str, optional): MCP 服务商类型。
 * `base_url` (str): API 基础 URL。
 * `protocol_type` (str, optional): 协议类型。
 * `api_key_encrypted` (str, optional): 加密后的API密钥 (不返回明文)。
 * `is_active` (bool): 是否活跃。
 * `description` (str, optional): 描述。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (datetime, optional): 更新时间。
 * 常见状态码: 200 OK (创建成功), 400 Bad Request (缺少API密钥或参数校验失败), 401 Unauthorized (未认证), 409 Conflict (已存在同名且活跃的配置), 500 Internal Server Error (加密失败或内部错误)。

 **5.3.4 获取当前用户所有MCP服务配置 (GET /mcp-configs/)**
 * 摘要: 获取当前用户配置的所有MCP服务列表。
 * 权限: 需要认证 (JWT Token)。
 * 请求参数:
 * `is_active` (boolean, 可选): 过滤条件，如果为 `true` 则只返回活跃的配置，`false` 返回非活跃的，不传则返回所有。
 * 请求体: 无
 * 响应体: List[`schemas.UserMcpConfigResponse`]
 * 列表内容同 `schemas.UserMcpConfigResponse`，但 `api_key_encrypted` 字段通常不会返回敏感信息（会被设置为 `None`）。
 * 常见状态码: 200 OK (成功获取), 401 Unauthorized (未认证)。

 **5.3.5 更新指定MCP配置 (PUT /mcp-configs/{config_id})**
 * 摘要: 更新指定ID的MCP服务配置。用户只能更新自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要更新的MCP配置ID。
 * 请求体: `application/json`
 * `schemas.UserMcpConfigBase` (所有字段均为可选)
 * `name` (str, 可选): MCP 配置名称。
 * `mcp_type` (str, 可选): MCP 服务商类型。
 * `base_url` (str, 可选): API 基础 URL。
 * `protocol_type` (str, 可选): 协议类型。
 * `api_key` (str, 可选): MCP 服务的 API 密钥。如果提供，将被加密存储。传入 `null` 或空字符串表示清空现有密钥。
 * `is_active` (bool, 可选): 配置是否激活。
 * `description` (str, 可选): 配置描述。
 * 响应体: `schemas.UserMcpConfigResponse` (同创建响应)
 * 常见状态码: 200 OK (更新成功), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (配置未找到或无权访问), 409 Conflict (新名称已存在或参数校验失败)。

 **5.3.6 删除指定MCP服务配置 (DELETE /mcp-configs/{config_id})**
 * 摘要: 删除指定ID的MCP服务配置。用户只能删除自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要删除的MCP配置ID。
 * 请求体: 无
 * 响应体: `application/json`
 * `message` (str): 操作结果消息，例如 "MCP config deleted successfully"。
 * 常见状态码: 204 No Content (删除成功), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (配置未找到或无权访问)。

 **5.3.7 检查指定MCP服务的连通性 (POST /mcp-configs/{config_id}/check-status)**
 * 摘要: 检查指定ID的MCP服务配置的API连通性。该操作会尝试向MCP服务发送请求以验证其可用性。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要检查连通性的MCP配置ID。
 * 请求体: 无
 * 响应体: `schemas.McpStatusResponse`
 * `status` (str): 连通性状态，可选值：`"success"` (成功), `"failure"` (失败), `"timeout"` (超时)。
 * `message` (str): 详细的连通性检查结果或错误信息。
 * `service_name` (str, optional): 对应MCP服务的名称。
 * `config_id` (int, optional): 对应的MCP配置ID。
 * `timestamp` (datetime): 检查时间戳。
 * 常见状态码: 200 OK (检查完成，状态在响应体中), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (配置未找到或无权访问), 500 Internal Server Error (解密失败或内部错误)。

 **5.3.8 获取智库聊天可用的MCP工具列表 (GET /llm/mcp-available-tools)**
 * 摘要: 根据用户已配置且启用的MCP服务，返回可用于智库聊天中的工具列表，供LLM进行函数调用。
 * 权限: 需要认证 (JWT Token)。
 * 请求体: 无
 * 响应体: List[`schemas.McpToolDefinition`]
 * `tool_id` (str): 工具的唯一标识符。
 * `name` (str): 工具的显示名称。
 * `description` (str): 工具的功能描述，供LLM理解。
 * `mcp_config_id` (int): 关联的MCP配置ID。
 * `mcp_config_name` (str): 关联的MCP配置名称。
 * `input_schema` (Dict): 工具输入的JSON Schema，定义了调用该工具所需的参数。
 * `output_schema` (Dict): 工具输出的JSON Schema，定义了工具返回结果的结构。
 * 常见状态码: 200 OK (成功获取), 401 Unauthorized (未认证)。

 **5.3.9 创建新的搜索引擎配置 (POST /search-engine-configs/)**
 * 摘要: 为当前用户创建一条新的搜索引擎配置，用于AI智能工具（如网络搜索）调用。
 * 权限: 需要认证 (JWT Token)。
 * 请求体: `application/json`
 * `schemas.UserSearchEngineConfigCreate`
 * `name` (str): 搜索引擎配置的唯一名称。
 * `engine_type` (str): 搜索引擎类型，可选值：`"bing"`, `"tavily"`, `"baidu"`, `"google_cse"`, `"custom"`。
 * `api_key` (str): 搜索引擎的 API 密钥。不能为空。
 * `is_active` (bool, 可选): 配置是否激活。默认为 `True`。
 * `description` (str, 可选): 配置描述。
 * `base_url` (str, 可选): 搜索引擎API的基础URL。
 * 响应体: `schemas.UserSearchEngineConfigResponse`
 * `id` (int): 配置ID。
 * `owner_id` (int): 配置所有者ID。
 * `name` (str): 配置名称。
 * `engine_type` (str): 搜索引擎类型。
 * `api_key_encrypted` (str, optional): 加密后的API密钥 (不返回明文)。
 * `is_active` (bool): 是否活跃。
 * `description` (str, optional): 描述。
 * `base_url` (str, optional): 基础URL。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (datetime, optional): 更新时间。
 * 常见状态码: 200 OK (创建成功), 400 Bad Request (API密钥不能为空或参数校验失败), 401 Unauthorized (未认证), 409 Conflict (已存在同名且活跃的配置), 500 Internal Server Error (加密失败或内部错误)。

 **5.3.10 获取当前用户所有搜索引擎配置 (GET /search-engine-configs/)**
 * 摘要: 获取当前用户配置的所有搜索引擎列表。
 * 权限: 需要认证 (JWT Token)。
 * 请求参数:
 * `is_active` (boolean, 可选): 过滤条件，如果为 `true` 则只返回活跃的配置，`false` 返回非活跃的，不传则返回所有。
 * 请求体: 无
 * 响应体: List[`schemas.UserSearchEngineConfigResponse`]
 * 列表内容同 `schemas.UserSearchEngineConfigResponse`，但 `api_key_encrypted` 字段通常不会返回敏感信息（会被设置为 `None`）。
 * 常见状态码: 200 OK (成功获取), 401 Unauthorized (未认证)。

 **5.3.11 获取指定搜索引擎配置详情 (GET /search-engine-configs/{config_id})**
 * 摘要: 获取指定ID的搜索引擎配置详情。用户只能获取自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要获取的搜索引擎配置ID。
 * 请求体: 无
 * 响应体: `schemas.UserSearchEngineConfigResponse` (同创建响应)
 * 常见状态码: 200 OK (成功获取), 401 Unauthorized (未认证), 404 Not Found (配置未找到或无权访问)。

 **5.3.12 更新指定搜索引擎配置 (PUT /search-engine-configs/{config_id})**
 * 摘要: 更新指定ID的搜索引擎配置。用户只能更新自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要更新的搜索引擎配置ID。
 * 请求体: `application/json`
 * `schemas.UserSearchEngineConfigBase` (所有字段均为可选)
 * `name` (str, 可选): 搜索引擎配置名称。
 * `engine_type` (str, 可选): 搜索引擎类型。
 * `api_key` (str, 可选): 搜索引擎的 API 密钥。如果提供，将被加密存储。传入 `null` 或空字符串表示清空现有密钥。
 * `is_active` (bool, 可选): 配置是否激活。
 * `description` (str, 可选): 配置描述。
 * `base_url` (str, 可选): 搜索引擎API的基础URL。
 * 响应体: `schemas.UserSearchEngineConfigResponse` (同创建响应)
 * 常见状态码: 200 OK (更新成功), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (配置未找到或无权访问), 409 Conflict (新名称已存在或参数校验失败)。

 **5.3.13 删除指定搜索引擎配置 (DELETE /search-engine-configs/{config_id})**
 * 摘要: 删除指定ID的搜索引擎配置。用户只能删除自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要删除的搜索引擎配置ID。
 * 请求体: 无
 * 响应体: `application/json`
 * `message` (str): 操作结果消息，例如 "Search engine config deleted successfully"。
 * 常见状态码: 204 No Content (删除成功), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (配置未找到或无权访问)。

 **5.3.14 检查指定搜索引擎的连通性 (POST /search-engine-configs/{config_id}/check-status)**
 * 摘要: 检查指定ID的搜索引擎配置的API连通性。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要检查连通性的搜索引擎配置ID。
 * 请求体: 无
 * 响应体: `schemas.SearchEngineStatusResponse`
 * `status` (str): 连通性状态，可选值：`"success"` (成功), `"failure"` (失败), `"timeout"` (超时)。
 * `message` (str): 详细的连通性检查结果或错误信息。
 * `engine_name` (str, optional): 对应搜索引擎的名称。
 * `config_id` (int, optional): 对应的搜索引擎配置ID。
 * `timestamp` (datetime): 检查时间戳。
 * 常见状态码: 200 OK (检查完成，状态在响应体中), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (配置未找到或无权访问), 500 Internal Server Error (解密失败或内部错误)。

 **5.3.15 执行一次网络搜索 (POST /ai/web-search)**
 * 摘要: 使用用户配置的搜索引擎执行网络搜索。可以指定使用的搜索引擎配置ID。
 * 权限: 需要认证 (JWT Token)。
 * 请求体: `application/json`
 * `schemas.WebSearchRequest`
 * `query` (str): 搜索查询关键词。
 * `engine_config_id` (int): 要使用的搜索引擎配置ID。
 * `limit` (int, 可选): 返回结果数量限制，默认为5。
 * 响应体: `schemas.WebSearchResponse`
 * `query` (str): 原始查询关键词。
 * `engine_used` (str): 实际使用的搜索引擎名称。
 * `results` (List[`schemas.WebSearchResult`]): 搜索结果列表。
 * `title` (str): 搜索结果标题。
 * `url` (str): 搜索结果链接。
 * `snippet` (str): 搜索结果摘要。
 * `total_results` (int, optional): 总结果数量 (如果搜索引擎提供)。
 * `search_time` (float, optional): 搜索耗时（秒）。
 * `message` (str, optional): 额外信息。
 * 常见状态码: 200 OK (搜索成功), 400 Bad Request (缺少搜索引擎配置ID或参数错误), 401 Unauthorized (未认证), 404 Not Found (指定的搜索引擎配置不存在、未启用或无权访问), 500 Internal Server Error (解密失败), 503 Service Unavailable (搜索引擎服务调用失败)。

 **5.3.16 为当前用户创建新的TTS配置 (POST /users/me/tts_configs)**
 * 摘要: 为当前用户创建一条新的文本转语音 (TTS) 配置。
 * 权限: 需要认证 (JWT Token)。
 * 请求体: `application/json`
 * `schemas.UserTTSConfigCreate`
 * `name` (str): TTS 配置名称，例如：`"我的OpenAI语音"`。
 * `tts_type` (str): 语音提供商类型，可选值：`"openai"`, `"gemini"`, `"aliyun"`, `"siliconflow"`。
 * `api_key` (str): API 密钥（未加密）。
 * `base_url` (str, 可选): API 基础 URL，如有自定义需求。
 * `model_id` (str, 可选): 语音模型 ID，例如：`"tts-1"`, `"gemini-pro"`。
 * `voice_name` (str, 可选): 语音名称或 ID，例如：`"alloy"`, `"f_cn_zh_anqi_a_f"`。
 * `is_active` (bool, 可选): 是否当前激活的TTS配置。默认为 `False`。如果设为 `True`，系统会自动将用户原有的激活配置设为非激活。
 * 响应体: `schemas.UserTTSConfigResponse`
 * `id` (int): 配置ID。
 * `owner_id` (int): 配置所有者ID。
 * `name` (str): 配置名称。
 * `tts_type` (str): 语音提供商类型。
 * `api_key_encrypted` (str): 加密后的API密钥 (不返回明文)。
 * `base_url` (str, optional): API 基础 URL。
 * `model_id` (str, optional): 语音模型 ID。
 * `voice_name` (str, optional): 语音名称或 ID。
 * `is_active` (bool): 是否激活。
 * `created_at` (datetime): 创建时间。
 * `updated_at` (datetime, optional): 更新时间。
 * 常见状态码: 200 OK (创建成功), 400 Bad Request (参数校验失败，例如缺少必填字段), 401 Unauthorized (未认证), 409 Conflict (已存在同名配置或由于唯一激活限制冲突), 500 Internal Server Error (加密失败或数据库错误)。

 **5.3.17 获取当前用户的所有TTS配置 (GET /users/me/tts_configs)**
 * 摘要: 获取当前用户配置的所有文本转语音 (TTS) 服务列表。
 * 权限: 需要认证 (JWT Token)。
 * 请求体: 无
 * 响应体: List[`schemas.UserTTSConfigResponse`]
 * 列表内容同 `schemas.UserTTSConfigResponse`，但 `api_key_encrypted` 字段通常不会返回敏感信息（会被设置为 `None`）。
 * 常见状态码: 200 OK (成功获取), 401 Unauthorized (未认证)。

 **5.3.18 获取指定TTS配置详情 (GET /users/me/tts_configs/{config_id})**
 * 摘要: 获取指定ID的TTS配置详情。用户只能获取自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要获取的TTS配置ID。
 * 请求体: 无
 * 响应体: `schemas.UserTTSConfigResponse` (同创建响应)
 * 常见状态码: 200 OK (成功获取), 401 Unauthorized (未认证), 404 Not Found (配置未找到或无权访问)。

 **5.3.19 更新指定TTS配置 (PUT /users/me/tts_configs/{config_id})**
 * 摘要: 更新指定ID的TTS配置。用户只能更新自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要更新的TTS配置ID。
 * 请求体: `application/json`
 * `schemas.UserTTSConfigUpdate` (所有字段均为可选)
 * `name` (str, 可选): TTS 配置名称。
 * `tts_type` (str, 可选): 语音提供商类型。
 * `api_key` (str, 可选): API 密钥（未加密）。如果提供，将被加密存储。传入 `null` 或空字符串表示清空现有密钥。
 * `base_url` (str, 可选): API 基础 URL。
 * `model_id` (str, 可选): 语音模型 ID。
 * `voice_name` (str, 可选): 语音名称或 ID。
 * `is_active` (bool, 可选): 是否激活。如果设为 `True`，系统会自动将用户原有的激活配置设为非激活。
 * 响应体: `schemas.UserTTSConfigResponse` (同创建响应)
 * 常见状态码: 200 OK (更新成功), 400 Bad Request (参数校验失败), 401 Unauthorized (未认证), 404 Not Found (配置未找到或无权访问), 409 Conflict (新名称已存在或由于唯一激活限制冲突), 500 Internal Server Error (加密失败或数据库错误)。

 **5.3.20 删除指定TTS配置 (DELETE /users/me/tts_configs/{config_id})**
 * 摘要: 删除指定ID的TTS配置。用户只能删除自己的配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要删除的TTS配置ID。
 * 请求体: 无
 * 响应体: 无 (204 No Content)
 * 常见状态码: 204 No Content (删除成功), 401 Unauthorized (未认证), 403 Forbidden (无权操作), 404 Not Found (配置未找到或无权访问)。

 **5.3.21 设置指定TTS配置为激活状态 (PUT /users/me/tts_configs/{config_id}/set_active)**
 * 摘要: 将指定ID的TTS配置设为当前用户的激活状态。此操作会自动取消用户其他TTS配置的激活状态，确保每个用户只有一个激活的TTS配置。
 * 权限: 需要认证 (JWT Token)。
 * 路径参数:
 * `config_id` (int): 要激活的TTS配置ID。
 * 请求体: 无
 * 响应体: `schemas.UserTTSConfigResponse` (同创建响应)
 * 常见状态码: 200 OK (设置成功), 401 Unauthorized (未认证), 404 Not Found (配置未找到或无权访问), 500 Internal Server Error (数据库错误)。

---
