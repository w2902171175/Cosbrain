
#### **6.1 用户管理 (管理员)**

**6.1.1 获取所有学生列表**
* **方法**: `GET`
* **路径**: `/students/`
* **摘要**: 获取平台上所有学生的完整列表。
* **权限**: **无直接认证要求** （**警告**: 根据当前代码实现，此接口没有显式认证或权限检查。若此功能仅限管理员，则此处存在安全隐患，需要额外添加`Depends(is_admin_user)`）。
* **请求参数**: 无
* **响应体**: `List[schemas.StudentResponse]`
 * **id** (int): 学生的唯一ID。
 * **username** (str): 用户在平台内唯一的用户名/昵称。
 * **email** (Optional[EmailStr]): 用户邮箱。
 * **phone_number** (Optional[str]): 用户手机号。
 * **school** (Optional[str]): 用户所属学校名称。
 * **name** (Optional[str]): 用户真实姓名。
 * **major** (Optional[str]): 主修专业。
 * **skills** (Optional[List[schemas.SkillWithProficiency]]): 用户技能列表及熟练度。
 * **interests** (Optional[str]): 兴趣爱好。
 * **bio** (Optional[str]): 个人简介。
 * **awards_competitions** (Optional[str]): 获奖与竞赛经历。
 * **academic_achievements** (Optional[str]): 学术成就。
 * **soft_skills** (Optional[str]): 软技能。
 * **portfolio_link** (Optional[str]): 作品集链接。
 * **preferred_role** (Optional[str]): 偏好角色。
 * **availability** (Optional[str]): 可用时间。
 * **location** (Optional[str]): 学生所在地理位置。
 * **combined_text** (Optional[str]): 用于AI模型嵌入的组合文本。
 * **embedding** (Optional[List[float]]): 文本内容的嵌入向量。
 * **llm_api_type** (Optional[Literal]): 用户配置的LLM类型。
 * **llm_api_base_url** (Optional[str]): 用户自定义LLM的API基础URL。
 * **llm_model_id** (Optional[str]): 用户选定的LLM模型ID。
 * **llm_api_key_encrypted** (Optional[str]): 加密后的LLM API密钥（不会返回明文）。
 * **created_at** (datetime): 用户创建时间。
 * **updated_at** (Optional[datetime]): 最后更新时间。
 * **is_admin** (bool): 是否为系统管理员。
 * **total_points** (int): 用户当前总积分。
 * **last_login_at** (Optional[datetime]): 用户上次登录时间。
 * **login_count** (int): 用户总登录天数。
 * **completed_projects_count** (Optional[int]): 用户创建并已完成的项目总数。
 * **completed_courses_count** (Optional[int]): 用户完成的课程总数。
* **常见状态码**:
 * `200 OK`: 成功获取学生列表。

**6.1.2 获取指定学生详情**
* **方法**: `GET`
* **路径**: `/students/{student_id}`
* **摘要**: 获取指定ID学生的所有详细信息。
* **权限**: **无直接认证要求** （**警告**: 根据当前代码实现，此接口没有显式认证或权限检查。若此功能仅限管理员，则此处存在安全隐患，需要额外添加`Depends(is_admin_user)`）。
* **路径参数**:
 * **student_id** (int): 要查询的学生的唯一ID。
* **请求参数**: 无
* **响应体**: `schemas.StudentResponse`
 * 结构同 `6.1.1 获取所有学生列表` 的响应体。
* **常见状态码**:
 * `200 OK`: 成功获取学生详情。
 * `404 Not Found`: 学生未找到。

**6.1.3 设置系统管理员权限**
* **方法**: `PUT`
* **路径**: `/admin/users/{user_id}/set-admin`
* **摘要**: 设置或取消指定用户的系统管理员权限。
* **权限**: 仅限 `系统管理员`。
* **路径参数**:
 * **user_id** (int): 目标用户的唯一ID。
* **请求体**: `application/json`
 * **is_admin** (bool): 是否设置为系统管理员 (`True`) 或取消管理员权限 (`False`)。
* **响应体**: `schemas.StudentResponse`
 * 结构同 `6.1.1 获取所有学生列表` 的响应体，其中`is_admin`字段会反映更新后的状态。
* **常见状态码**:
 * `200 OK`: 成功设置用户管理员权限。
 * `400 Bad Request`: 客户端请求参数不合法，例如系统管理员尝试取消自己的管理员权限。
 * `403 Forbidden`: 当前用户无权执行此操作（不是系统管理员）。
 * `404 Not Found`: 目标用户未找到。
 * `500 Internal Server Error`: 服务器内部错误，例如数据保存失败。

---

#### **6.2 成就与积分管理 (管理员)**

**6.2.1 创建新的成就定义**
* **方法**: `POST`
* **路径**: `/admin/achievements/definitions`
* **摘要**: 系统管理员创建新的成就定义。
* **权限**: 仅限 `系统管理员`。
* **请求体**: `application/json`
 * **name** (str): 成就名称，在平台内须唯一。
 * **description** (str): 成就的详细描述。
 * **criteria_type** (Literal["PROJECT_COMPLETED_COUNT", "COURSE_COMPLETED_COUNT", "FORUM_LIKES_RECEIVED", "DAILY_LOGIN_STREAK", "FORUM_POSTS_COUNT", "CHAT_MESSAGES_SENT_COUNT", "LOGIN_COUNT"]): 达成成就的条件类型。
 * **criteria_value** (float): 达成成就所需的数值门槛（例如，完成项目数、获得点赞数）。
 * **badge_url** (Optional[str]): 勋章图片或图标的URL。
 * **reward_points** (int): 达成此成就额外奖励的积分数量 (默认0分)。
 * **is_active** (bool): 该成就定义是否启用 (默认`True`)。
* **响应体**: `schemas.AchievementResponse`
 * **id** (int): 成就定义的唯一ID。
 * **name** (str): 成就名称。
 * **description** (str): 成就描述。
 * **criteria_type** (str): 达成成就的条件类型。
 * **criteria_value** (float): 达成成就所需的数值门槛。
 * **badge_url** (Optional[str]): 勋章图片或图标URL。
 * **reward_points** (int): 达成此成就额外奖励的积分。
 * **is_active** (bool): 该成就是否启用。
 * **created_at** (datetime): 成就创建时间。
 * **updated_at** (Optional[datetime]): 最后更新时间。
* **常见状态码**:
 * `200 OK`: 成功创建成就定义。
 * `403 Forbidden`: 当前用户无权执行此操作。
 * `409 Conflict`: 成就名称已存在。
 * `500 Internal Server Error`: 服务器内部错误。

**6.2.2 获取所有成就定义（可供所有用户查看）**
* **方法**: `GET`
* **路径**: `/achievements/definitions`
* **摘要**: 获取平台所有可用的成就定义列表。此接口对所有用户开放，以便用户了解平台有哪些成就可供追求。
* **权限**: 无需认证。
* **请求参数 (Query)**:
 * **is_active** (Optional[bool]): 过滤条件，只获取启用 (`True`) 或禁用 (`False`) 的成就定义。
 * **criteria_type** (Optional[str]): 过滤条件，按成就的条件类型进行筛选。
* **响应体**: `List[schemas.AchievementResponse]`
 * 列表中的每个元素结构同 `6.2.1 创建新的成就定义` 的响应体。
* **常见状态码**:
 * `200 OK`: 成功获取成就定义列表。

**6.2.3 获取指定成就定义详情**
* **方法**: `GET`
* **路径**: `/achievements/definitions/{achievement_id}`
* **摘要**: 获取指定ID的成就定义详情。此接口对所有用户开放。
* **权限**: 无需认证。
* **路径参数**:
 * **achievement_id** (int): 要查询的成就定义的唯一ID。
* **请求参数**: 无
* **响应体**: `schemas.AchievementResponse`
 * 结构同 `6.2.1 创建新的成就定义` 的响应体。
* **常见状态码**:
 * `200 OK`: 成功获取成就定义详情。
 * `404 Not Found`: 成就定义未找到。

**6.2.4 更新指定成就定义**
* **方法**: `PUT`
* **路径**: `/admin/achievements/definitions/{achievement_id}`
* **摘要**: 系统管理员更新指定成就定义的信息。
* **权限**: 仅限 `系统管理员`。
* **路径参数**:
 * **achievement_id** (int): 要更新的成就定义的唯一ID。
* **请求体**: `application/json`
 * **name** (Optional[str]): 成就名称。
 * **description** (Optional[str]): 成就的详细描述。
 * **criteria_type** (Optional[Literal]): 达成成就的条件类型。
 * **criteria_value** (Optional[float]): 达成成就所需的数值门槛。
 * **badge_url** (Optional[str]): 勋章图片或图标的URL。
 * **reward_points** (Optional[int]): 达成此成就额外奖励的积分数量。
 * **is_active** (Optional[bool]): 该成就定义是否启用。
* **响应体**: `schemas.AchievementResponse`
 * 结构同 `6.2.1 创建新的成就定义` 的响应体，反映更新后的状态。
* **常见状态码**:
 * `200 OK`: 成功更新成就定义。
 * `403 Forbidden`: 当前用户无权执行此操作。
 * `404 Not Found`: 成就定义未找到。
 * `409 Conflict`: 更新后的成就名称已存在。
 * `500 Internal Server Error`: 服务器内部错误。

**6.2.5 删除指定成就定义**
* **方法**: `DELETE`
* **路径**: `/admin/achievements/definitions/{achievement_id}`
* **摘要**: 系统管理员删除指定成就定义。此操作将同时删除所有用户已获得的该成就记录。
* **权限**: 仅限 `系统管理员`。
* **路径参数**:
 * **achievement_id** (int): 要删除的成就定义的唯一ID。
* **请求参数**: 无
* **响应体**: `HTTP 204 No Content`
 * 表示删除成功，无返回内容。
* **常见状态码**:
 * `204 No Content`: 成功删除成就定义。
 * `403 Forbidden`: 当前用户无权执行此操作。
 * `404 Not Found`: 成就定义未找到。

**6.2.6 手动发放/扣除积分**
* **方法**: `POST`
* **路径**: `/admin/points/reward`
* **摘要**: 系统管理员可以手动为指定用户发放或扣除积分。
* **权限**: 仅限 `系统管理员`。
* **请求体**: `application/json`
 * **user_id** (int): 目标用户的唯一ID。
 * **amount** (int): 积分变动数量，正数代码增加积分，负数代表扣除积分。
 * **reason** (Optional[str]): 积分变动的具体理由（例如：`"活动奖励", "作弊惩罚"`）。
 * **transaction_type** (Literal["EARN", "CONSUME", "ADMIN_ADJUST"]): 积分交易类型，`ADMIN_ADJUST`为管理员手动调整。
 * **related_entity_type** (Optional[str]): 关联的实体类型，例如`"project", "course", "forum_topic"`。
 * **related_entity_id** (Optional[int]): 关联实体的唯一ID。
* **响应体**: `schemas.PointTransactionResponse`
 * **id** (int): 积分交易记录的唯一ID。
 * **user_id** (int): 发生交易的用户ID。
 * **amount** (int): 积分变动金额。
 * **reason** (Optional[str]): 积分变动理由描述。
 * **transaction_type** (str): 积分交易类型。
 * **related_entity_type** (Optional[str]): 关联的实体类型。
 * **related_entity_id** (Optional[int]): 关联实体的ID。
 * **created_at** (datetime): 交易记录创建时间。
* **常见状态码**:
 * `200 OK`: 成功调整用户积分。
 * `403 Forbidden`: 当前用户无权执行此操作。
 * `404 Not Found`: 目标用户未找到。
 * `500 Internal Server Error`: 服务器内部错误。
