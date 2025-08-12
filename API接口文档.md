# 鸿庆书云创新协作平台API接口文档

本文档详细描述了鸿庆书云创新协作平台的数据库表结构，共包含 **28个数据表**。
- [项目概述](#项目概述)
- [认证方式](#认证方式)
- [用户认证与管理](#用户认证与管理)
- [项目管理](#项目管理)
- [课程管理](#课程管理)
- [知识库管理](#知识库管理)
- [笔记管理](#笔记管理)
- [AI智能服务](#ai智能服务)
- [搜索引擎配置](#搜索引擎配置)
- [TTS语音配置](#tts语音配置)
8. [AI对话系统表](#8-ai对话系统表)
9. [系统配置表](#9-系统配置表)
- [聊天室管理](#聊天室管理)
- [收藏夹管理](#收藏夹管理)
- [随手记录](#随手记录)
- [仪表板接口](#仪表板接口)
- [论坛功能](#论坛功能)
- [积分与成就系统](#积分与成就系统)
- [AI对话系统](#ai对话系统)
- [统计接口](#统计接口)
- [WebSocket实时通信](#websocket实时通信)
- [系统管理](#系统管理)

---

## 项目概述

本API为"鸿庆书云创新协作平台"提供后端服务，支持学生项目匹配、智能推荐、知识管理、课程学习和协作功能。

**基础信息：**
- API版本：v0.1.0
- 基础URL：`http://localhost:8000`（开发环境）
- 数据格式：JSON
- 认证方式：JWT Bearer Token

---

## 认证方式

所有需要认证的接口都使用JWT Bearer Token认证。

**请求头格式：**
```
Authorization: Bearer <your_jwt_token>
```

---

## 用户认证与管理

### 1. 健康检查
**接口：** `GET /health`

**摘要：** API服务健康检查

**响应体：**
```json
{
  "status": "healthy",
  "message": "鸿庆书云创新协作平台API正常运行",
  "timestamp": "2024-01-01T10:00:00Z"
}
```

### 2. 用户注册
**接口：** `POST /register`

**摘要：** 新用户注册账号

**请求体：**
```json
{
  "username": "张三",
  "email": "zhangsan@example.com",
  "phone_number": "13800138000",
  "password": "password123",
  "name": "张三",
  "school": "广州大学",
  "major": "计算机科学与技术",
  "location": "广州大学城"
}
```

**字段说明：**
- `username`: 用户名/昵称（必填，1-50字符）
- `email`: 邮箱地址（与phone_number二选一）
- `phone_number`: 手机号（与email二选一，11位）
- `password`: 密码（必填，至少6位）
- `name`: 真实姓名（可选）
- `school`: 学校名称（可选，最大100字符）
- `major`: 专业（可选）
- `location`: 地理位置（可选）

**响应体：**
```json
{
  "id": 1,
  "username": "张三",
  "email": "zhangsan@example.com",
  "name": "张三",
  "school": "广州大学",
  "major": "计算机科学与技术",
  "location": "广州大学城",
  "created_at": "2024-01-01T10:00:00",
  "is_admin": false,
  "total_points": 100,
  "login_count": 0
}
```

### 3. 用户登录
**接口：** `POST /token`

**摘要：** 用户登录获取JWT令牌

**请求体：**
```json
{
  "username": "zhangsan@example.com",
  "password": "password123"
}
```

**字段说明：**
- `username`: 邮箱地址或手机号
- `password`: 密码

**响应体：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 43200
}
```

### 4. 获取当前用户信息
**接口：** `GET /users/me`

**摘要：** 获取当前登录用户的详细信息

**认证：** 需要Bearer Token

**响应体：**
```json
{
**特殊约束：** 确保一个用户在一个聊天室中最多只有一个 'pending' 状态的申请

  "id": 1,
  "username": "张三",
  "email": "zhangsan@example.com",
  "name": "张三",
  "school": "广州大学",
  "major": "计算机科学与技术",
  "skills": [
    {
      "name": "Python",
      "level": "融会贯通"
    }
  ],
  "location": "广州大学城",
  "total_points": 100,
  "is_admin": false,
  "created_at": "2024-01-01T10:00:00"
}
```

### 5. 更新用户信息
**接口：** `PUT /users/me`

**摘要：** 更新当前登录用户的信息

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "username": "新用户名",
  "name": "新姓名",
  "school": "新学校",
  "major": "新专业",
  "location": "新位置",
  "skills": [
    {
      "name": "Python",
      "level": "精通"
    }
  ]
}
```

### 6. 更新用户LLM配置
**接口：** `PUT /users/me/llm-config`

**摘要：** 更新当前用户的LLM（大语言模型）配置

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "llm_api_type": "openai",
  "llm_model_id": "gpt-4",
  "llm_api_key": "your_api_key",
  "llm_api_base_url": "https://api.openai.com/v1"
}
```

### 7. 获取可用LLM模型
**接口：** `GET /llm/available-models`

**摘要：** 获取可配置的LLM服务商及模型列表

**响应体：**
```json
{
  "providers": {
    "openai": {
      "models": ["gpt-4", "gpt-3.5-turbo"],
      "default_api_base": "https://api.openai.com/v1"
    },
    "anthropic": {
      "models": ["claude-3-opus", "claude-3-sonnet"],
      "default_api_base": "https://api.anthropic.com"
    },
    "siliconflow": {
      "models": ["deepseek-chat", "qwen-turbo"],
      "default_api_base": "https://api.siliconflow.cn/v1"
    }
  }
}
```

### 8. 获取所有学生列表
**接口：** `GET /students/`

**摘要：** 获取所有学生用户列表

**响应体：**
```json
[
  {
    "id": 1,
    "username": "张三",
    "name": "张三",
    "school": "广州大学",
    "major": "计算机科学",
    "created_at": "2024-01-01T10:00:00"
  }
]
```

### 9. 获取指定学生详情
**接口：** `GET /students/{student_id}`

**摘要：** 获取指定学生的详细信息

**路径参数：**
- `student_id`: 学生ID

---

## 项目管理

### 1. 创建新项目
**接口：** `POST /projects/`

**摘要：** 创建新的项目

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "智能学习管理系统",
  "description": "基于AI的个性化学习平台",
  "required_skills": [
    {
      "name": "Python",
      "level": "精通"
    },
    {
      "name": "React",
      "level": "熟练"
    }
  ],
  "required_roles": ["后端开发", "前端开发", "UI设计"],
  "keywords": "AI, 学习, 管理系统",
  "project_type": "Web应用",
  "expected_deliverables": "完整的学习管理系统",
  "contact_person_info": "张三 - zhangsan@example.com",
  "learning_outcomes": "掌握全栈开发技能",
  "team_size_preference": "3-5人",
  "project_status": "招募中",
  "start_date": "2024-02-01",
  "end_date": "2024-06-01",
  "estimated_weekly_hours": 20,
  "location": "广州"
}
```

### 2. 获取所有项目列表
**接口：** `GET /projects/`

**摘要：** 获取所有项目列表

### 3. 获取指定项目详情
**接口：** `GET /projects/{project_id}`

**摘要：** 获取指定项目的详细信息

**路径参数：**
- `project_id`: 项目ID

### 4. 更新指定项目
**接口：** `PUT /projects/{project_id}`

**摘要：** 更新指定项目信息（仅项目创建者或管理员可操作）

**认证：** 需要Bearer Token

### 5. 为学生推荐项目
**接口：** `GET /recommend/projects/{student_id}`

**摘要：** 为指定学生推荐匹配的项目

**路径参数：**
- `student_id`: 学生ID

**查询参数：**
- `initial_k`: 初始候选数量（默认20）
- `final_k`: 最终推荐数量（默认5）

### 6. 为项目匹配学生
**接口：** `GET /projects/{project_id}/match-students`

**摘要：** 为指定项目匹配合适的学生

**路径参数：**
- `project_id`: 项目ID

**查询参数：**
- `initial_k`: 初始候选数量（默认20）
- `final_k`: 最终推荐数量（默认5）

---

## 课程管理

### 1. 创建新课程
**接口：** `POST /courses/`

**摘要：** 创建新的课程（仅管理员可操作）

**认证：** 需要Bearer Token（管理员权限）

**请求体：**
```json
{
  "title": "Python编程基础",
  "description": "从零开始学习Python编程",
  "instructor": "李老师",
  "category": "编程语言",
### 5.5 collection_items (收藏项目表)

旧的收藏系统表（将来可能重构或删除）。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | Integer | PRIMARY KEY, INDEX | 收藏项目唯一标识符 |
| user_id | Integer | FOREIGN KEY(students.id) | 用户ID |
| item_type | String | | 项目类型 |
| item_id | Integer | | 项目ID |
| created_at | DateTime | SERVER_DEFAULT=func.now() | 创建时间 |

  "total_lessons": 40,
  "avg_rating": 4.8,
  "cover_image_url": "https://example.com/python-course.jpg",
  "required_skills": [
    {
      "name": "计算机基础",
      "level": "了解"
    }
  ]
}
```

### 2. 获取指定课程详情
**接口：** `GET /courses/{course_id}`

**摘要：** 获取指定课程的详细信息

### 3. 更新指定课程
**接口：** `PUT /courses/{course_id}`
| combined_text | Text | | 合并文本（用于搜索） |
| embedding | Vector(1024) | | 向量嵌入 |
| created_at | DateTime | SERVER_DEFAULT=func.now() | 创建时间 |
| updated_at | DateTime | ONUPDATE=func.now() | 更新时间 |

### 6.2 user_courses (用户课程关联表)

管理用户与课程的关联关系。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| student_id | Integer | FOREIGN KEY(students.id), PRIMARY KEY | 学生ID |
| course_id | Integer | FOREIGN KEY(courses.id), PRIMARY KEY | 课程ID |
| progress | Float | DEFAULT=0.0 | 学习进度 |
| status | String | DEFAULT="in_progress" | 学习状态 |
| last_accessed | DateTime | SERVER_DEFAULT=func.now(), ONUPDATE=func.now() | 最后访问时间 |
| created_at | DateTime | SERVER_DEFAULT=func.now() | 创建时间 |

### 6.3 course_materials (课程材料表)

存储课程相关的学习材料。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | Integer | PRIMARY KEY, INDEX | 材料唯一标识符 |
| course_id | Integer | FOREIGN KEY(courses.id), NOT NULL, INDEX | 课程ID |
| title | String | NOT NULL | 材料标题 |
| type | String | NOT NULL | 材料类型（file/link/text） |
| file_path | String | NULLABLE | 本地文件存储路径 |
| original_filename | String | NULLABLE | 原始上传文件名 |
| file_type | String | NULLABLE | 文件MIME类型 |
| size_bytes | Integer | NULLABLE | 文件大小（字节） |
| url | String | NULLABLE | 外部链接URL |
| content | Text | NULLABLE | 文本内容或描述 |
| combined_text | Text | NULLABLE | 合并文本（用于搜索） |
| embedding | Vector(1024) | NULLABLE | 向量嵌入 |
| created_at | DateTime | SERVER_DEFAULT=func.now() | 创建时间 |
| updated_at | DateTime | ONUPDATE=func.now() | 更新时间 |

**约束：** 
- UNIQUE(course_id, title) - 同一课程下材料标题唯一
- UNIQUE(file_path) - 文件路径唯一
### 7.1 achievements (成就表)

定义系统中可获得的成就。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | Integer | PRIMARY KEY, INDEX | 成就唯一标识符 |
| name | String | UNIQUE, NOT NULL | 成就名称 |
| description | Text | NOT NULL | 成就描述 |
| criteria_type | String | NOT NULL | 达成条件类型 |
| criteria_value | Float | NOT NULL | 达成所需数值门槛 |
| badge_url | String | NULLABLE | 勋章图片URL |
| reward_points | Integer | DEFAULT=0, NOT NULL | 奖励积分 |
| is_active | Boolean | DEFAULT=True, NOT NULL | 是否启用 |
| created_at | DateTime | SERVER_DEFAULT=func.now() | 创建时间 |
| updated_at | DateTime | ONUPDATE=func.now() | 更新时间 |

### 7.2 user_achievements (用户成就表)
| is_notified | Boolean | DEFAULT=False, NOT NULL | 是否已通知 |
**约束：** UNIQUE(user_id, achievement_id) - 确保一个用户不会重复获得同一个成就

### 7.3 point_transactions (积分交易表)
| amount | Integer | NOT NULL | 积分变化量（正数为获得，负数为消耗） |
| reason | String | NULLABLE | 变动理由描述 |
| related_entity_type | String | NULLABLE | 关联实体类型 |
| related_entity_id | Integer | NULLABLE | 关联实体ID |
## 8. AI对话系统表

### 8.1 ai_conversations (AI对话表)

存储用户与AI的对话会话。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | Integer | PRIMARY KEY, INDEX | 对话唯一标识符 |
| user_id | Integer | FOREIGN KEY(students.id), NOT NULL, INDEX | 对话所属用户ID |
| title | String | NULLABLE | 对话标题 |
| created_at | DateTime | SERVER_DEFAULT=func.now(), NOT NULL | 对话创建时间 |
| last_updated | DateTime | SERVER_DEFAULT=func.now(), ONUPDATE=func.now(), NOT NULL | 最后更新时间 |

### 8.2 ai_conversation_messages (AI对话消息表)

存储AI对话中的具体消息。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | Integer | PRIMARY KEY, INDEX | 消息唯一标识符 |
| conversation_id | Integer | FOREIGN KEY(ai_conversations.id), NOT NULL, INDEX | 所属对话ID |
| role | String | NOT NULL | 消息角色（user/assistant/tool_call/tool_output） |
| content | Text | NOT NULL | 消息内容 |
| tool_calls_json | JSONB | NULLABLE | 工具调用JSON数据 |
| tool_output_json | JSONB | NULLABLE | 工具输出JSON数据 |
| llm_type_used | String | NULLABLE | 使用的LLM类型 |
| llm_model_used | String | NULLABLE | 使用的LLM模型ID |
| sent_at | DateTime | SERVER_DEFAULT=func.now(), NOT NULL | 消息发送时间 |

---
## 9. 系统配置表

### 9.1 user_mcp_configs (用户MCP配置表)
### 9.2 user_search_engine_configs (用户搜索引擎配置表)
### 9.3 user_tts_configs (用户TTS配置表)
   - `knowledge_bases.owner_id` → `students.id`
   - `forum_topics.owner_id` → `students.id`
   - `ai_conversations.user_id` → `students.id`
   - `course_materials.course_id` → `courses.id`

   - `knowledge_document_chunks.kb_id` → `knowledge_bases.id`
   - `forum_comments.topic_id` → `forum_topics.id`
   - `forum_comments.parent_comment_id` → `forum_comments.id` (自引用)
   - `forum_likes.topic_id` → `forum_topics.id`
   - `forum_likes.comment_id` → `forum_comments.id`


7. **积分和成就**：
   - `user_achievements.user_id` → `students.id`
   - `user_achievements.achievement_id` → `achievements.id`
   - `point_transactions.user_id` → `students.id`

8. **AI对话**：
   - `ai_conversation_messages.conversation_id` → `ai_conversations.id`


   - 同一课程下材料标题唯一
   - 用户不能重复获得同一个成就

   - 删除用户时，相关的成就、积分记录、AI对话等会被级联删除
   - 删除AI对话时，相关的消息会被级联删除



2. **JSONB字段**：skills、required_skills、required_roles、tool_calls_json、tool_output_json 等使用JSONB存储复杂数据
6. **嵌套结构支持**：文件夹和评论支持嵌套结构
1. 修正了数据库表总数为28个
2. 新增了AI对话系统相关表格（ai_conversations, ai_conversation_messages）
4. 补充了积分系统和成就系统的完整字段说明
5. 修正了所有表的字段名称和约束信息，确保与当前模型完全同步
6. 新增了collection_items表的说明
7. 完善了所有外键关系和约束条件的描述
8. 更新了技术特性说明，包括向量搜索和JSONB字段的使用
**接口：** `POST /courses/{course_id}/materials/`

**摘要：** 为指定课程上传学习材料

**认证：** 需要Bearer Token

**请求体：** `multipart/form-data`
```
file: [文件]
title: "材料标题"
description: "材料描述"
material_type: "document"
```

#### 5.2 获取课程材料列表
**接口：** `GET /courses/{course_id}/materials/`

**摘要：** 获取指定课程的所有学习材料

#### 5.3 获取课程材料详情
**接口：** `GET /courses/{course_id}/materials/{material_id}`

**摘要：** 获取指定课程材料的详细信息

#### 5.4 更新课程材料
**接口：** `PUT /courses/{course_id}/materials/{material_id}`

**摘要：** 更新指定课程材料信息

#### 5.5 删除课程材料
**接口：** `DELETE /courses/{course_id}/materials/{material_id}`

**摘要：** 删除指定课程材料

---

## 知识库管理

### 1. 创建新知识库
**接口：** `POST /knowledge-bases/`

**摘要：** 创建新的知识库

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "Python学习笔记",
  "description": "记录Python学习过程中的知识点",
  "access_type": "private"
}
```

### 2. 获取知识库列表
**接口：** `GET /knowledge-bases/`

**摘要：** 获取当前用户所有知识库

### 3. 获取知识库详情
**接口：** `GET /knowledge-bases/{kb_id}`

**摘要：** 获取指定知识库详情

### 4. 更新知识库
**接口：** `PUT /knowledge-bases/{kb_id}`

**摘要：** 更新指定知识库信息

### 5. 删除知识库
**接口：** `DELETE /knowledge-bases/{kb_id}`

**摘要：** 删除指定知识库

### 6. 知识库文章管理

#### 6.1 创建知识库文章
**接口：** `POST /knowledge-bases/{kb_id}/articles/`

**摘要：** 在指定知识库中创建新文章

**请求体：**
```json
{
  "title": "Python函数详解",
  "content": "函数是Python中的重要概念...",
  "version": "1.0",
  "tags": "Python, 函数, 编程"
}
```

#### 6.2 获取知识库文章列表
**接口：** `GET /knowledge-bases/{kb_id}/articles/`

**摘要：** 获取指定知识库的所有文章

#### 6.3 获取文章详情
**接口：** `GET /articles/{article_id}`

**摘要：** 获取指定文章详情

#### 6.4 更新文章
**接口：** `PUT /articles/{article_id}`

**摘要：** 更新指定文章内容

#### 6.5 删除文章
**接口：** `DELETE /articles/{article_id}`

**摘要：** 删除指定文章

### 7. 知识库文档管理

#### 7.1 上传知识文档
**接口：** `POST /knowledge-bases/{kb_id}/documents/`

**摘要：** 向知识库上传文档并进行向量化处理

**认证：** 需要Bearer Token

**请求体：** `multipart/form-data`
```
file: [文件] （支持PDF、DOCX、TXT格式）
```

**响应状态：** `202 Accepted`（文档将在后台异步处理）

#### 7.2 获取知识文档列表
**接口：** `GET /knowledge-bases/{kb_id}/documents/`

**摘要：** 获取指定知识库的所有文档

**查询参数：**
- `status_filter`: 按状态过滤（processing/completed/failed）

#### 7.3 获取知识文档详情
**接口：** `GET /knowledge-bases/{kb_id}/documents/{document_id}`

**摘要：** 获取指定知识文档详情

#### 7.4 删除知识文档
**接口：** `DELETE /knowledge-bases/{kb_id}/documents/{document_id}`

**摘要：** 删除指定知识文档

#### 7.5 获取文档原始内容
**接口：** `GET /knowledge-bases/{kb_id}/documents/{document_id}/content`

**摘要：** 获取知识文档的原始文本内容（调试用）

#### 7.6 获取文档向量块
**接口：** `GET /knowledge-bases/{kb_id}/documents/{document_id}/chunks`

**摘要：** 获取知识文档的向量化分块信息

---

## 笔记管理

### 1. 创建新笔记
**接口：** `POST /notes/`

**摘要：** 创建新的学习笔记

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "今日学习总结",
  "content": "今天学习了Python的面向对象编程...",
  "note_type": "学习笔记",
  "course_id": 1,
  "tags": "学习, Python, 总结"
}
```

### 2. 获取笔记列表
**接口：** `GET /notes/`

**摘要：** 获取当前用户所有笔记

**查询参数：**
- `note_type`: 按笔记类型过滤

### 3. 获取笔记详情
**接口：** `GET /notes/{note_id}`

**摘要：** 获取指定笔记详情

### 4. 更新笔记
**接口：** `PUT /notes/{note_id}`

**摘要：** 更新指定笔记内容

### 5. 删除笔记
**接口：** `DELETE /notes/{note_id}`

**摘要：** 删除指定笔记

---

## AI智能服务

### 1. AI智能问答
**接口：** `POST /ai/qa`

**摘要：** AI智能问答服务，支持通用问答、RAG知识库问答和工具调用

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "query": "Python中如何定义类？",
  "use_tools": true,
  "preferred_tools": ["rag", "web_search"],
  "knowledge_base_ids": [1, 2],
  "conversation_id": "conv_123",
  "llm_model_id": "gpt-4"
}
```

**字段说明：**
- `query`: 用户问题（必填）
- `use_tools`: 是否启用工具调用（可选，默认false）
- `preferred_tools`: 偏好工具列表（可选）
- `knowledge_base_ids`: 指定知识库ID列表（可选）
- `conversation_id`: 对话ID（可选，用于上下文记忆）
- `llm_model_id`: 指定LLM模型（可选）

**响应体：**
```json
{
  "answer": "在Python中定义类使用class关键字...",
  "sources": [
    {
      "source_type": "knowledge_base",
      "title": "Python基础教程",
      "content": "相关内容片段",
      "similarity_score": 0.95
    }
  ],
  "tool_calls": [],
  "conversation_id": "conv_123",
  "llm_model_used": "gpt-4"
}
```

### 2. 网络搜索
**接口：** `POST /ai/web-search`

**摘要：** 执行一次网络搜索

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "query": "最新的Python框架",
  "search_engine_config_id": 1,
  "max_results": 10
}
```

### 3. 语义搜索
**接口：** `POST /search/semantic`

**摘要：** 智能语义搜索，在知识库中搜索相关内容

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "query": "机器学习算法",
  "knowledge_base_ids": [1, 2],
  "limit": 10,
  "similarity_threshold": 0.7
}
```

---

## 搜索引擎配置

### 1. 创建搜索引擎配置
**接口：** `POST /search-engine-configs/`

**摘要：** 创建新的搜索引擎配置

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "我的Google搜索",
  "engine_type": "google",
  "api_key": "your_api_key",
  "base_url": "https://www.googleapis.com/customsearch/v1",
  "description": "Google自定义搜索配置",
  "is_active": true
}
```

### 2. 获取搜索引擎配置列表
**接口：** `GET /search-engine-configs/`

**摘要：** 获取当前用户所有搜索引擎配置

### 3. 获取搜索引擎配置详情
**接口：** `GET /search-engine-configs/{config_id}`

**摘要：** 获取指定搜索引擎配置详情

### 4. 更新搜索引擎配置
**接口：** `PUT /search-engine-configs/{config_id}`

**摘要：** 更新指定搜索引擎配置

### 5. 删除搜索引擎配置
**接口：** `DELETE /search-engine-configs/{config_id}`

**摘要：** 删除指定搜索引擎配置

### 6. 检查搜索引擎状态
**接口：** `POST /search-engine-configs/{config_id}/check-status`

**摘要：** 检查指定搜索引擎配置的连接状态

---

## TTS语音配置

### 1. 创建TTS配置
**接口：** `POST /users/me/tts_configs`

**摘要：** 为当前用户创建新的TTS配置

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "我的语音配置",
  "tts_type": "openai",
  "api_key": "your_api_key",
  "base_url": "https://api.openai.com/v1",
  "model_id": "tts-1",
  "voice_name": "alloy",
  "is_active": true
}
```

### 2. 获取TTS配置列表
**接口：** `GET /users/me/tts_configs`

**摘要：** 获取当前用户的所有TTS配置

### 3. 获取TTS配置详情
**接口：** `GET /users/me/tts_configs/{config_id}`

**摘要：** 获取指定TTS配置详情

### 4. 更新TTS配置
**接口：** `PUT /users/me/tts_configs/{config_id}`

**摘要：** 更新指定TTS配置

### 5. 删除TTS配置
**接口：** `DELETE /users/me/tts_configs/{config_id}`

**摘要：** 删除指定TTS配置

### 6. 设置活跃TTS配置
**接口：** `PUT /users/me/tts_configs/{config_id}/set_active`

**摘要：** 设置指定TTS配置为激活状态

---

## MCP服务配置

### 1. 创建MCP配置
**接口：** `POST /mcp-configs/`

**摘要：** 创建新的MCP服务配置

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "文件系统MCP",
  "mcp_type": "filesystem",
  "base_url": "mcp://filesystem",
  "protocol_type": "stdio",
  "description": "文件系统访问MCP服务",
  "is_active": true
}
```

### 2. 获取MCP配置列表
**接口：** `GET /mcp-configs/`

**摘要：** 获取当前用户所有MCP服务配置

### 3. 更新MCP配置
**接口：** `PUT /mcp-configs/{config_id}`

**摘要：** 更新指定MCP配置

### 4. 删除MCP配置
**接口：** `DELETE /mcp-configs/{config_id}`

**摘要：** 删除指定MCP服务配置

### 5. 检查MCP状态
**接口：** `POST /mcp-configs/{config_id}/check-status`

**摘要：** 检查指定MCP服务的连接状态

### 6. 获取可用MCP工具
**接口：** `GET /llm/mcp-available-tools`

**摘要：** 获取当前用户所有活跃MCP服务提供的工具列表

---

## 聊天室管理

### 1. 创建聊天室
**接口：** `POST /chat-rooms/`

**摘要：** 创建新的聊天室

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "Python学习讨论组",
  "type": "general",
  "project_id": null,
  "course_id": null,
  "color": "#3498db"
}
```

### 2. 获取聊天室列表
**接口：** `GET /chatrooms/`

**摘要：** 获取当前用户所属的所有聊天室

### 3. 获取聊天室详情
**接口：** `GET /chatrooms/{room_id}`

**摘要：** 获取指定聊天室详情

### 4. 获取聊天室成员
**接口：** `GET /chatrooms/{room_id}/members`

**摘要：** 获取指定聊天室的所有成员

### 5. 更新聊天室
**接口：** `PUT /chatrooms/{room_id}/`

**摘要：** 更新指定聊天室信息

### 6. 删除聊天室
**接口：** `DELETE /chatrooms/{room_id}`

**摘要：** 删除指定聊天室

### 7. 设置成员角色
**接口：** `PUT /chat-rooms/{room_id}/members/{member_id}/set-role`

**摘要：** 设置聊天室成员的角色

### 8. 移除聊天室成员
**接口：** `DELETE /chat-rooms/{room_id}/members/{member_id}`

**摘要：** 从聊天室中移除指定成员

### 9. 申请加入聊天室
**接口：** `POST /chat-rooms/{room_id}/join-request`

**摘要：** 申请加入指定聊天室

### 10. 获取加入申请列表
**接口：** `GET /chat-rooms/{room_id}/join-requests`

**摘要：** 获取指定聊天室的所有加入申请

### 11. 处理加入申请
**接口：** `POST /chat-rooms/join-requests/{request_id}/process`

**摘要：** 处理聊天室加入申请（同意或拒绝）

### 12. 发送聊天消息
**接口：** `POST /chatrooms/{room_id}/messages/`

**摘要：** 在指定聊天室发送消息

**请求体：**
```json
{
  "content_text": "大家好，我是新成员！",
  "message_type": "text",
  "media_url": null
}
```

### 13. 获取聊天消息
**接口：** `GET /chatrooms/{room_id}/messages/`

**摘要：** 获取指定聊天室的消息历史

**查询参数：**
- `limit`: 消息数量限制
- `offset`: 偏移量

---

## 收藏夹管理

### 1. 创建收藏夹
**接口：** `POST /folders/`

**摘要：** 创建新文件夹

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "Python资源",
  "description": "收集Python学习相关的资源",
  "color": "#2ecc71",
  "icon": "folder",
  "parent_id": null,
  "order": 0
}
```

### 2. 获取文件夹列表
**接口：** `GET /folders/`

**摘要：** 获取当前用户所有文件夹

### 3. 获取文件夹详情
**接口：** `GET /folders/{folder_id}`

**摘要：** 获取指定文件夹详情

### 4. 更新文件夹
**接口：** `PUT /folders/{folder_id}`

**摘要：** 更新指定文件夹信息

### 5. 删除文件夹
**接口：** `DELETE /folders/{folder_id}`

**摘要：** 删除指定文件夹

### 6. 创建收藏内容
**接口：** `POST /collections/`

**摘要：** 创建新收藏内容

**请求体：**
```json
{
  "title": "Python官方文档",
  "type": "link",
  "url": "https://docs.python.org/",
  "content": "Python官方文档链接",
  "folder_id": 1,
  "tags": "Python, 文档, 官方",
  "priority": 5,
  "notes": "重要参考资料",
  "is_starred": true
}
```

### 7. 获取收藏内容列表
**接口：** `GET /collections/`

**摘要：** 获取当前用户所有收藏内容

### 8. 获取收藏内容详情
**接口：** `GET /collections/{content_id}`

**摘要：** 获取指定收藏内容详情

### 9. 更新收藏内容
**接口：** `PUT /collections/{content_id}`

**摘要：** 更新指定收藏内容

### 10. 删除收藏内容
**接口：** `DELETE /collections/{content_id}`

**摘要：** 删除指定收藏内容

---

## 随手记录

### 1. 创建随手记录
**接口：** `POST /daily-records/`

**摘要：** 创建新随手记录

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "content": "今天学习了装饰器，感觉很有趣...",
  "mood": "开心",
  "tags": "学习, 装饰器, Python"
}
```

### 2. 获取随手记录列表
**接口：** `GET /daily-records/`

**摘要：** 获取当前用户所有随手记录

### 3. 获取随手记录详情
**接口：** `GET /daily-records/{record_id}`

**摘要：** 获取指定随手记录详情

### 4. 更新随手记录
**接口：** `PUT /daily-records/{record_id}`

**摘要：** 更新指定随手记录

### 5. 删除随手记录
**接口：** `DELETE /daily-records/{record_id}`

**摘要：** 删除指定随手记录

---

## 仪表板接口

### 1. 获取工作台概览
**接口：** `GET /dashboard/summary`

**摘要：** 获取首页工作台概览数据

**认证：** 需要Bearer Token

**响应体：**
```json
{
  "active_projects_count": 3,
  "completed_projects_count": 5,
  "learning_courses_count": 2,
  "completed_courses_count": 8,
  "active_chats_count": 4,
  "unread_messages_count": 12,
  "resume_completion_percentage": 85.5
}
```

### 2. 获取仪表板项目列表
**接口：** `GET /dashboard/projects`

**摘要：** 获取当前用户参与的项目卡片列表

**认证：** 需要Bearer Token

**查询参数：**
- `status_filter`: 按状态过滤项目

**响应体：**
```json
[
  {
    "id": 1,
    "title": "智能学习管理系统",
    "progress": 0.65
  }
]
```

### 3. 获取仪表板课程列表
**接口：** `GET /dashboard/courses`

**摘要：** 获取当前用户学习的课程卡片列表

**认证：** 需要Bearer Token

**查询参数：**
- `status_filter`: 按状态过滤课程

**响应体：**
```json
[
  {
    "id": 1,
    "title": "Python编程基础",
    "progress": 75.5,
    "last_accessed": "2024-01-01T10:00:00"
  }
]
```

---

## AI对话系统

### 1. 获取AI对话列表
**接口：** `GET /ai/conversations`

**摘要：** 获取当前用户的所有AI对话

**认证：** 需要Bearer Token

### 2. 获取AI对话详情
**接口：** `GET /ai/conversations/{conversation_id}`

**摘要：** 获取指定AI对话的详细信息和消息历史

**认证：** 需要Bearer Token

### 3. 创建新AI对话
**接口：** `POST /ai/conversations`

**摘要：** 创建新的AI对话会话

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "Python学习讨论"
}
```

### 4. 更新AI对话标题
**接口：** `PUT /ai/conversations/{conversation_id}`

**摘要：** 更新AI对话的标题

**认证：** 需要Bearer Token

### 5. 删除AI对话
**接口：** `DELETE /ai/conversations/{conversation_id}`

**摘要：** 删除指定的AI对话及其所有消息

**认证：** 需要Bearer Token

---

## 论坛功能

### 1. 发布论坛话题
**接口：** `POST /forum/topics`

**摘要：** 发布新的论坛话题

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "Python学习心得分享",
  "content": "分享一些Python学习的心得体会...",
  "tags": "Python, 学习, 心得",
  "shared_item_type": "project",
  "shared_item_id": 1
}
```

### 2. 获取论坛话题列表
**接口：** `GET /forum/topics`

**摘要：** 获取论坛话题列表

**查询参数：**
- `limit`: 每页数量
- `offset`: 偏移量
- `tag`: 按标签筛选

### 3. 获取论坛话题详情
**接口：** `GET /forum/topics/{topic_id}`

**摘要：** 获取指定论坛话题的详细信息

### 4. 更新论坛话题
**接口：** `PUT /forum/topics/{topic_id}`

**摘要：** 更新论坛话题（仅作者可操作）

**认证：** 需要Bearer Token

### 5. 删除论坛话题
**接口：** `DELETE /forum/topics/{topic_id}`

**摘要：** 删除论坛话题（仅作者可操作）

**认证：** 需要Bearer Token

### 6. 评论管理

#### 6.1 添加评论
**接口：** `POST /forum/topics/{topic_id}/comments`

**摘要：** 对论坛话题添加评论

**认证：** 需要Bearer Token

#### 6.2 获取评论列表
**接口：** `GET /forum/topics/{topic_id}/comments`

**摘要：** 获取指定话题的所有评论

#### 6.3 删除评论
**接口：** `DELETE /forum/comments/{comment_id}`

**摘要：** 删除指定评论（仅作者可操作）

**认证：** 需要Bearer Token

### 7. 点赞功能

#### 7.1 点赞话题
**接口：** `POST /forum/topics/{topic_id}/like`

**摘要：** 对论坛话题点赞

**认证：** 需要Bearer Token

#### 7.2 取消点赞
**接口：** `DELETE /forum/topics/{topic_id}/like`

**摘要：** 取消对论坛话题的点赞

**认证：** 需要Bearer Token

### 8. 关注功能

#### 8.1 关注用户
**接口：** `POST /users/{user_id}/follow`

**摘要：** 关注指定用户

**认证：** 需要Bearer Token

#### 8.2 取消关注
**接口：** `DELETE /users/{user_id}/follow`

**摘要：** 取消关注指定用户

**认证：** 需要Bearer Token

#### 8.3 获取关注列表
**接口：** `GET /users/me/following`

**摘要：** 获取当前用户的关注列表

**认证：** 需要Bearer Token

#### 8.4 获取粉丝列表
**接口：** `GET /users/me/followers`

**摘要：** 获取当前用户的粉丝列表

**认证：** 需要Bearer Token

---

## 积分与成就系统

### 1. 获取用户积分信息
**接口：** `GET /users/me/points`

**摘要：** 获取当前用户的积分信息

**认证：** 需要Bearer Token

**响应体：**
```json
{
  "total_points": 1250,
  "recent_transactions": [
    {
      "id": 1,
      "amount": 50,
      "reason": "完成项目：智能学习系统",
      "transaction_type": "EARN",
      "created_at": "2024-01-01T10:00:00"
    }
  ]
}
```

### 2. 获取积分交易历史
**接口：** `GET /users/me/point-transactions`

**摘要：** 获取当前用户的积分交易历史

**认证：** 需要Bearer Token

**查询参数：**
- `limit`: 每页数量
- `offset`: 偏移量
- `transaction_type`: 交易类型过滤

### 3. 管理员奖励积分
**接口：** `POST /admin/users/{user_id}/reward-points`

**摘要：** 管理员为指定用户奖励积分

**认证：** 需要Bearer Token（管理员权限）

**请求体：**
```json
{
  "amount": 100,
  "reason": "优秀项目表现"
}
```

### 4. 获取成就列表
**接口：** `GET /achievements`

**摘要：** 获取所有可获得的成就列表

### 5. 获取用户成就
**接口：** `GET /users/me/achievements`

**摘要：** 获取当前用户已获得的成就

**认证：** 需要Bearer Token

### 6. 管理员成就管理

#### 6.1 创建成就
**接口：** `POST /admin/achievements`

**摘要：** 创建新的成就（仅管理员）

**认证：** 需要Bearer Token（管理员权限）

#### 6.2 更新成就
**接口：** `PUT /admin/achievements/{achievement_id}`

**摘要：** 更新成就信息（仅管理员）

**认证：** 需要Bearer Token（管理员权限）

#### 6.3 删除成就
**接口：** `DELETE /admin/achievements/{achievement_id}`

**摘要：** 删除成就（仅管理员）

**认证：** 需要Bearer Token（管理员权限）

---

## 统计接口

### 1. 获取平台统计信息
**接口：** `GET /stats/platform`

**摘要：** 获取平台整体统计信息

**响应体：**
```json
{
  "total_users": 1250,
  "total_projects": 340,
  "total_courses": 45,
  "total_knowledge_bases": 180,
  "total_notes": 8650,
  "active_users_today": 156
}
```

### 2. 获取用户统计信息
**接口：** `GET /stats/users/me`

**摘要：** 获取当前用户的个人统计信息

**认证：** 需要Bearer Token

---

## WebSocket实时通信

### 1. 聊天室WebSocket连接
**接口：** `WebSocket /ws/chat/{room_id}`

**摘要：** 建立与指定聊天室的WebSocket连接，用于实时聊天

**认证：** 需要在查询参数中提供token

**连接URL示例：**
```
ws://localhost:8000/ws/chat/1?token=your_jwt_token
```

**消息格式：**
```json
{
  "type": "message",
  "content": "Hello, world!",
  "timestamp": "2024-01-01T10:00:00Z"
}
```

### 2. 系统通知WebSocket连接
**接口：** `WebSocket /ws/notifications`

**摘要：** 建立系统通知的WebSocket连接

**认证：** 需要在查询参数中提供token

---

## 系统管理

### 1. 系统健康检查
**接口：** `GET /admin/health`

**摘要：** 系统健康状态检查（管理员专用）

**认证：** 需要Bearer Token（管理员权限）

### 2. 数据库状态检查
**接口：** `GET /admin/db-status`

**摘要：** 检查数据库连接状态

**认证：** 需要Bearer Token（管理员权限）

### 3. 清理临时文件
**接口：** `POST /admin/cleanup-temp-files`

**摘要：** 清理系统临时文件

**认证：** 需要Bearer Token（管理员权限）

### 4. 用户管理

#### 4.1 获取所有用户
**接口：** `GET /admin/users`

**摘要：** 获取所有用户列表（管理员专用）

**认证：** 需要Bearer Token（管理员权限）

#### 4.2 封禁用户
**接口：** `PUT /admin/users/{user_id}/ban`

**摘要：** 封禁指定用户

**认证：** 需要Bearer Token（管理员权限）

#### 4.3 解封用户
**接口：** `PUT /admin/users/{user_id}/unban`

**摘要：** 解封指定用户

**认证：** 需要Bearer Token（管理员权限）

---

## 错误响应格式

所有API接口的错误响应都遵循统一格式：

```json
{
  "detail": "错误描述信息"
}
```

**常见HTTP状态码：**
- `200 OK`: 请求成功
- `201 Created`: 资源创建成功
- `202 Accepted`: 请求已接受，正在处理
- `204 No Content`: 请求成功，无返回内容
- `400 Bad Request`: 请求参数错误
- `401 Unauthorized`: 未认证或认证失败
- `403 Forbidden`: 权限不足
- `404 Not Found`: 资源未找到
- `409 Conflict`: 资源冲突
- `422 Unprocessable Entity`: 请求格式正确但语义错误
- `500 Internal Server Error`: 服务器内部错误

---

## 注意事项

1. **认证令牌**：所有需要认证的接口都必须在请求头中包含有效的JWT令牌
2. **文件上传**：上传文件时使用`multipart/form-data`格式
3. **日期格式**：所有日期时间使用ISO 8601格式（如：`2024-01-01T10:00:00`）
4. **分页**：部分列表接口支持分页参数（`page`、`size`）
5. **权限控制**：管理员权限接口需要`is_admin=true`的用户
6. **API限制**：部分AI服务接口可能有调用频率限制

---

## 更新日志

- **v0.1.0** (2024-01-01): 初始版本发布
  - 完成用户认证系统
  - 实现项目管理功能
  - 添加课程学习模块
  - 集成AI智能服务
  - 支持知识库管理
  - 实现实时聊天功能
  - 添加积分与成就系统
  - 完整的API文档
