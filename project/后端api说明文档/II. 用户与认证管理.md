
### 2.1 用户认证

#### 2.1.1 用户注册

* **POST /register**
* **摘要**: 用户注册新账号。用户需提供邮箱或手机号之一，以及密码。系统将自动生成唯一的用户名，如果用户未指定。注册成功后，会为用户初始化个人资料并生成其文本内容的嵌入向量（主要为零向量，用户配置LLM后会更新）。
* **权限**: 无需认证。
* **请求体**: `application/json`
 * **schemas.StudentCreate** (继承 `schemas.StudentBase`)
 * `email` (EmailStr, optional): 用户邮箱。**邮箱和手机号至少需要提供一个。**
 * `phone_number` (str, optional): 用户手机号，例如 `13812345678`。**邮箱和手机号至少需要提供一个。**
 * `password` (str): 密码，至少6位。
 * `username` (str, optional): 用户在平台内唯一的用户名/昵称。如果未提供，系统将自动生成。
 * `school` (str, optional): 用户所属学校名称。
 * `name` (str, optional): 用户真实姓名。如果未提供，将使用 `username` 作为 `name`。
 * `major` (str, optional): 专业。
 * `skills` (List[schemas.SkillWithProficiency], optional): 用户的技能列表及熟练度。例如：
 ```json
 [
 {"name": "Python", "level": "融会贯通"},
 {"name": "FastAPI", "level": "登堂入室"}
 ]
 ```
 * `interests` (str, optional): 兴趣爱好。
 * `bio` (str, optional): 个人简介。
 * `awards_competitions` (str, optional): 获奖或参赛经历。
 * `academic_achievements` (str, optional): 学术成就。
 * `soft_skills` (str, optional): 软技能。
 * `portfolio_link` (str, optional): 个人作品集链接。
 * `preferred_role` (str, optional): 偏好角色，例如“后端开发工程师”、“项目经理”。
 * `availability` (str, optional): 可用时间或投入度，例如“每周20小时”、“暑假全职”。
 * `location` (str, optional): 所在地理位置，例如“广州大学城”、“珠海横琴”。
* **响应体**: `application/json`
 * **schemas.StudentResponse**
 * `id` (int): 用户ID。
 * `email` (EmailStr, optional): 用户邮箱。
 * `phone_number` (str, optional): 用户手机号。
 * `username` (str): 用户名/昵称。
 * `school` (str, optional): 学校名称。
 * `name` (str): 用户姓名。
 * `major` (str, optional): 专业。
 * `skills` (List[schemas.SkillWithProficiency], optional): 用户技能列表及熟练度。
 * `total_points` (int): 用户当前总积分。
 * `last_login_at` (datetime, optional): 用户上次登录时间。
 * `login_count` (int): 用户总登录天数（完成每日打卡的次数）。
 * `completed_projects_count` (int, optional): 用户创建并已完成的项目总数。
 * `completed_courses_count` (int, optional): 用户完成的课程总数。
 * `combined_text` (str, optional): 综合用户资料生成的文本内容，用于AI模型。
 * `embedding` (List[float], optional): 文本内容对应的嵌入向量。
 * `llm_api_type` (str, optional): 用户配置的LLM类型。
 * `llm_api_base_url` (str, optional): 用户配置的LLM API基础URL。
 * `llm_model_id` (str, optional): 用户配置的LLM模型ID。
 * `llm_api_key_encrypted` (str, optional): 加密后的LLM API密钥（通常不会在响应中返回明文）。
 * `created_at` (datetime): 用户创建时间 (ISO 8601 格式)。
 * `updated_at` (datetime, optional): 用户信息最后更新时间 (ISO 8601 格式)。
 * `is_admin` (bool): 是否为系统管理员。
* **常见状态码**:
 * `200 OK`: 用户注册成功。
 * `409 Conflict`: 邮箱、手机号或用户名已被注册。
 * `400 Bad Request`: 请求数据格式不正确，例如缺少必填字段（如密码、邮箱或手机号）。
 * `500 Internal Server Error`: 服务器内部错误，例如无法生成唯一的用户名。

#### 2.1.2 用户登录并获取JWT令牌

* **POST /token**
* **摘要**: 通过用户凭证（邮箱或手机号）和密码获取JWT令牌。成功登录且首次今日登录会奖励积分并检查成就。
* **权限**: 无需认证。
* **请求体**: `application/x-www-form-urlencoded`
 * `username` (str): 用户的邮箱或手机号。
 * `password` (str): 用户密码。
* **响应体**: `application/json`
 * **schemas.Token**
 * `access_token` (str): 访问令牌。
 * `token_type` (str): 令牌类型，通常为`bearer`。
 * `expires_in_minutes` (int): 令牌过期时间（分钟）。
* **常见状态码**:
 * `200 OK`: 登录成功。
 * `401 Unauthorized`: 凭证（邮箱/手机号或密码）错误。
 * `500 Internal Server Error`: 登录成功但数据保存失败（例如积分/成就更新），请指示用户重试或联系管理员。

### 2.2 个人资料管理

#### 2.2.1 获取当前登录用户详情

* **GET /users/me**
* **摘要**: 获取当前登录用户的详细信息，包括其注册时间、联系方式、个人简介、技能列表、项目和课程完成情况，以及积分和登录状态。
* **权限**: 需要认证。
* **请求体**: 无
* **响应体**: `application/json`
 * **schemas.StudentResponse** (详见 **2.1.1 用户注册** 响应体)。
* **常见状态码**:
 * `200 OK`: 成功获取用户详情。
 * `401 Unauthorized`: 未提供认证令牌或令牌无效/过期。
 * `404 Not Found`: 用户未找到（通常在认证令牌指向的用户不存在时发生）。

#### 2.2.2 更新当前登录用户详情

* **PUT /users/me**
* **摘要**: 更新当前登录用户的个人资料信息。此接口支持部分更新，仅需提供需要修改的字段。更新用户的相关文本字段（如专业、技能、兴趣、简介等）会触发个人资料嵌入向量的重新计算，以保持AI匹配的准确性。
* **权限**: 需要认证。
* **请求体**: `application/json`
 * **schemas.StudentUpdate** (所有字段均为可选)
 * `username` (str, optional): 用户在平台内唯一的用户名/昵称。
 * `phone_number` (str, optional): 用户手机号。
 * `school` (str, optional): 用户所属学校名称。
 * `name` (str, optional): 用户真实姓名。
 * `major` (str, optional): 专业。
 * `skills` (List[schemas.SkillWithProficiency], optional): 用户的技能列表及熟练度。
 * `interests` (str, optional): 兴趣爱好。
 * `bio` (str, optional): 个人简介。
 * `awards_competitions` (str, optional): 获奖或参赛经历。
 * `academic_achievements` (str, optional): 学术成就。
 * `soft_skills` (str, optional): 软技能。
 * `portfolio_link` (str, optional): 个人作品集链接。
 * `preferred_role` (str, optional): 偏好角色。
 * `availability` (str, optional): 可用时间或投入度。
 * `location` (str, optional): 所在地理位置。
* **响应体**: `application/json`
 * **schemas.StudentResponse** (详见 **2.1.1 用户注册** 响应体)。返回更新后的用户完整信息。
* **常见状态码**:
 * `200 OK`: 用户信息更新成功。
 * `401 Unauthorized`: 未提供认证令牌或令牌无效/过期。
 * `409 Conflict`: 提供的用户名或手机号已被其他用户使用。
 * `500 Internal Server Error`: 服务器内部错误，例如重新计算嵌入向量失败。

### 2.3 用户积分与成就

#### 2.3.1 获取当前用户积分余额和上次登录时间

* **GET /users/me/points**
* **摘要**: 获取当前登录用户的总积分余额和最近一次登录打卡时间，以及总登录天数。此集成在 `/users/me` 接口中已经提供。
* **权限**: 需要认证。
* **请求体**: 无
* **响应体**: `application/json`
 * **schemas.StudentResponse**
 * `total_points` (int): 用户当前的总积分。
 * `last_login_at` (datetime, optional): 用户最近一次登录的时间 (ISO 8601 格式)。
 * `login_count` (int): 用户累计登录天数（完成每日打卡的次数）。
 * **注意**: 响应中包含 `StudentResponse` 的所有其他字段，此处仅列出与积分和登录直接相关的字段。
* **常见状态码**:
 * `200 OK`: 成功获取用户积分和登录信息。
 * `401 Unauthorized`: 未提供认证令牌或令牌无效/过期。

#### 2.3.2 获取当前用户积分交易历史

* **GET /users/me/points/history**
* **摘要**: 获取当前用户的所有积分交易历史记录，包括积分获取和消耗的详情。
* **权限**: 需要认证。
* **请求参数**:
 * `transaction_type` (str, optional): 积分交易类型，用于过滤。可选值：`EARN` (获得), `CONSUME` (消耗), `ADMIN_ADJUST` (管理员调整)。
 * `limit` (int, optional): 返回的最大记录数量，默认 `20`。
 * `offset` (int, optional): 查询结果的偏移量，用于分页，默认 `0`。
* **响应体**: `application/json`
 * **List[schemas.PointTransactionResponse]**
 * `id` (int): 积分交易记录ID。
 * `user_id` (int): 发生交易的用户ID。
 * `amount` (int): 积分变动金额（正数表示获得，负数表示消耗）。
 * `reason` (str, optional): 积分变动的具体理由描述。
 * `transaction_type` (str): 积分交易类型，例如 `EARN`, `CONSUME`, `ADMIN_ADJUST`。
 * `related_entity_type` (str, optional): 关联的实体类型（例如：`project`, `course`, `forum_topic`, `achievement`）。
 * `related_entity_id` (int, optional): 关联实体的ID。
 * `created_at` (datetime): 交易发生时间 (ISO 8601 格式)。
* **常见状态码**:
 * `200 OK`: 成功获取积分交易历史。
 * `401 Unauthorized`: 未提供认证令牌或令牌无效/过期。

#### 2.3.3 获取当前用户已获得的成就列表

* **GET /users/me/achievements**
* **摘要**: 获取当前用户所有已获得的成就列表，包含每个成就的详细信息（如成就名称、描述、徽章图片URL和奖励积分）。
* **权限**: 需要认证。
* **请求参数**: 无
* **响应体**: `application/json`
 * **List[schemas.UserAchievementResponse]**
 * `id` (int): 用户成就记录ID。
 * `user_id` (int): 获得成就的用户ID。
 * `achievement_id` (int): 实际成就定义的ID。
 * `earned_at` (datetime): 获得成就的时间 (ISO 8601 格式)。
 * `is_notified` (bool): 成就是否已通知用户。
 * `achievement_name` (str, optional): 成就名称。
 * `achievement_description` (str, optional): 成就描述。
 * `badge_url` (str, optional): 勋章图片URL。
 * `reward_points` (int, optional): 获得此成就奖励的积分。
* **常见状态码**:
 * `200 OK`: 成功获取用户成就列表。
 * `401 Unauthorized`: 未提供认证令牌或令牌无效/过期。

---
