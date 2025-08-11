# 鸿庆书云创新协作平台API接口文档

## 目录
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
- [聊天室管理](#聊天室管理)
- [收藏夹管理](#收藏夹管理)
- [随手记录](#随手记录)
- [仪表板接口](#仪表板接口)
- [积分与成就系统](#积分与成就系统)
- [统计接口](#统计接口)

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

### 1. 用户注册
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

### 2. 用户登录
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

### 3. 获取当前用户信息
**接口：** `GET /users/me`

**摘要：** 获取当前登录用户的详细信息

**认证：** 需要Bearer Token

**响应体：**
```json
{
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

### 4. 更新用户信息
**接口：** `PUT /users/me`

**摘要：** 更新当前用户的个人信息

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "张三",
  "major": "软件工程",
  "skills": [
    {
      "name": "Python",
      "level": "炉火纯青"
    }
  ],
  "bio": "热爱编程的学生",
  "location": "珠海横琴"
}
```

**字段说明：**
- `skills`: 技能列表，level可选值：`初窥门径`、`登堂入室`、`融会贯通`、`炉火纯青`
- 所有字段均为可选

---

## 项目管理

### 1. 创建项目
**接口：** `POST /projects/`

**摘要：** 创建新项目

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "智能学习助手开发",
  "description": "基于AI的个性化学习助手系统",
  "required_skills": [
    {
      "name": "Python",
      "level": "融会贯通"
    },
    {
      "name": "机器学习",
      "level": "登堂入室"
    }
  ],
  "required_roles": ["前端开发", "后端开发", "AI工程师"],
  "keywords": "AI,教育,个性化",
  "project_type": "技术创新",
  "expected_deliverables": "完整的学习助手系统",
  "team_size_preference": "3-5人",
  "project_status": "招募中",
  "start_date": "2024-02-01T00:00:00",
  "end_date": "2024-06-01T00:00:00",
  "estimated_weekly_hours": 10,
  "location": "广州大学城"
}
```

**字段说明：**
- `title`: 项目标题（必填）
- `description`: 项目描述
- `required_skills`: 所需技能列表
- `required_roles`: 所需角色列表
- `project_status`: 项目状态（招募中、进行中、已完成等）
- `location`: 项目地理位置

**响应体：**
```json
{
  "id": 1,
  "title": "智能学习助手开发",
  "description": "基于AI的个性化学习助手系统",
  "required_skills": ["..."],
  "required_roles": ["前端开发", "后端开发", "AI工程师"],
  "project_status": "招募中",
  "location": "广州大学城",
  "created_at": "2024-01-01T10:00:00"
}
```

### 2. 获取所有项目
**接口：** `GET /projects/`

**摘要：** 获取所有项目列表

**响应体：**
```json
[
  {
    "id": 1,
    "title": "智能学习助手开发",
    "description": "基于AI的个性化学习助手系统",
    "project_status": "招募中",
    "location": "广州大学城",
    "created_at": "2024-01-01T10:00:00"
  }
]
```

### 3. 获取项目详情
**接口：** `GET /projects/{project_id}`

**摘要：** 获取指定项目的详细信息

**路径参数：**
- `project_id`: 项目ID

### 4. 更新项目
**接口：** `PUT /projects/{project_id}`

**摘要：** 更新项目信息（仅项目创建者或管理员）

**认证：** 需要Bearer Token

**请求体：** 与创建项目相同，所有字段可选

### 5. 项目推荐
**接口：** `GET /recommend/projects/{student_id}`

**摘要：** 为指定学生推荐匹配的项目

**路径参数：**
- `student_id`: 学生ID

**查询参数：**
- `initial_k`: 初始候选数量（默认50）
- `final_k`: 最终推荐数量（默认10）

**响应体：**
```json
[
  {
    "project": {
      "id": 1,
      "title": "智能学习助手开发",
      "description": "基于AI的个性化学习助手系统"
    },
    "similarity_score": 0.85,
    "relevance_score": 0.90,
    "match_reasons": ["技能匹配度高", "项目类型符合兴趣"]
  }
]
```

### 6. 学生推荐
**接口：** `GET /projects/{project_id}/match-students`

**摘要：** 为指定项目推荐匹配的学生

**路径参数：**
- `project_id`: 项目ID

---

## 课程管理

### 1. 创建课程
**接口：** `POST /courses/`

**摘要：** 创建新课程（仅管理员）

**认证：** 需要管理员权限

**请求体：**
```json
{
  "title": "Python程序设计",
  "description": "从零开始学习Python编程",
  "instructor": "李教授",
  "category": "编程语言",
  "total_lessons": 20,
  "avg_rating": 4.5,
  "cover_image_url": "https://example.com/cover.jpg",
  "required_skills": [
    {
      "name": "计算机基础",
      "level": "初窥门径"
    }
  ]
}
```

**字段说明：**
- `title`: 课程标题（必填）
- `instructor`: 讲师姓名
- `category`: 课程分类
- `total_lessons`: 总课时数
- `avg_rating`: 平均评分
- `required_skills`: 先修技能要求

### 2. 获取课程详情
**接口：** `GET /courses/{course_id}`

**摘要：** 获取指定课程的详细信息

### 3. 更新课程
**接口：** `PUT /courses/{course_id}`

**摘要：** 更新课程信息（仅管理员）

### 4. 课程推荐
**接口：** `GET /recommend/courses/{student_id}`

**摘要：** 为指定学生推荐相关课程

### 5. 更新学习进度
**接口：** `PUT /users/me/courses/{course_id}`

**摘要：** 更新当前用户的课程学习进度

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "progress": 0.8,
  "status": "completed"
}
```

**字段说明：**
- `progress`: 学习进度（0.0-1.0）
- `status`: 学习状态（in_progress、completed、paused）

### 6. 课程材料管理

#### 6.1 上传课程材料
**接口：** `POST /courses/{course_id}/materials/`

**摘要：** 为指定课程上传材料（仅管理员）

**认证：** 需要管理员权限

**请求体（文件上传）：**
```form-data
file: [文件]
title: "第一章课件"
type: "file"
content: "课程介绍材料"
```

**请求体（链接）：**
```json
{
  "title": "参考资料",
  "type": "link",
  "url": "https://example.com/reference",
  "content": "补充学习资料"
}
```

#### 6.2 获取课程材料
**接口：** `GET /courses/{course_id}/materials/`

**摘要：** 获取指定课程的所有材料

**查询参数：**
- `type_filter`: 按类型过滤（file、link、text）

---

## 知识库管理

### 1. 创建知识库
**接口：** `POST /knowledge-bases/`

**摘要：** 创建新知识库

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "AI学习笔记",
  "description": "人工智能相关学习资料整理",
  "access_type": "private"
}
```

**字段说明：**
- `name`: 知识库名称（必填）
- `description`: 描述信息
- `access_type`: 访问类型（private、public）

### 2. 获取知识库列表
**接口：** `GET /knowledge-bases/`

**摘要：** 获取当前用户的所有知识库

### 3. 上传知识文档
**接口：** `POST /knowledge-bases/{kb_id}/documents/`

**摘要：** 上传文档到知识库（支持PDF、DOCX、TXT）

**认证：** 需要Bearer Token

**请求体：**
```form-data
file: [文件]
```

**响应体：**
```json
{
  "id": 1,
  "kb_id": 1,
  "file_name": "AI基础教程.pdf",
  "status": "processing",
  "processing_message": "文件已上传，等待处理...",
  "created_at": "2024-01-01T10:00:00"
}
```

### 4. 知识文章管理

#### 4.1 创建知识文章
**接口：** `POST /knowledge-bases/{kb_id}/articles/`

**摘要：** 在知识库中创建文章

**请求体：**
```json
{
  "title": "机器学习入门",
  "content": "机器学习是人工智能的一个重要分支...",
  "version": "1.0",
  "tags": "机器学习,AI,入门"
}
```

#### 4.2 获取知识文章
**接口：** `GET /knowledge-bases/{kb_id}/articles/`

**摘要：** 获取知识库中的所有文章

---

## 笔记管理

### 1. 创建笔记
**接口：** `POST /notes/`

**摘要：** 创建新笔记

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "Python学习笔记",
  "content": "今天学习了Python的基础语法...",
  "note_type": "study",
  "course_id": 1,
  "tags": "Python,编程,学习"
}
```

**字段说明：**
- `title`: 笔记标题
- `content`: 笔记内容
- `note_type`: 笔记类型（general、study、project）
- `course_id`: 关联课程ID（可选）
- `tags`: 标签

### 2. 获取笔记列表
**接口：** `GET /notes/`

**摘要：** 获取当前用户的所有笔记

**查询参数：**
- `note_type`: 按类型过滤

### 3. 更新笔记
**接口：** `PUT /notes/{note_id}`

**摘要：** 更新指定笔记

### 4. 删除笔记
**接口：** `DELETE /notes/{note_id}`

**摘要：** 删除指定笔记

---

## AI智能服务

### 1. AI问答
**接口：** `POST /ai/qa`

**摘要：** AI智能问答服务，支持通用问答和工具调用

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "query": "请帮我解释什么是机器学习？",
  "use_tools": true,
  "preferred_tools": ["rag", "web_search"],
  "kb_ids": [1, 2],
  "note_ids": [10, 20],
  "llm_model_id": "gpt-3.5-turbo"
}
```

**字段说明：**
- `query`: 用户问题（必填）
- `use_tools`: 是否使用AI工具（默认false）
- `preferred_tools`: 偏好工具列表（rag、web_search、mcp_tools）
- `kb_ids`: 知识库ID列表（用于RAG检索）
- `note_ids`: 笔记ID列表（用于RAG检索）
- `llm_model_id`: 指定LLM模型

**响应体：**
```json
{
  "answer": "机器学习是人工智能的一个分支...",
  "answer_mode": "RAG_mode",
  "llm_type_used": "openai",
  "llm_model_used": "gpt-3.5-turbo",
  "sources_used": [
    {
      "type": "knowledge_article",
      "title": "机器学习基础",
      "relevance_score": 0.95
    }
  ],
  "tools_used": ["rag"],
  "processing_time": 2.5
}
```

### 2. 网络搜索
**接口：** `POST /ai/web-search`

**摘要：** 执行网络搜索

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "query": "最新的AI技术发展",
  "search_engine_config_id": 1,
  "max_results": 10
}
```

### 3. 语义搜索
**接口：** `POST /search/semantic`

**摘要：** 智能语义搜索

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "query": "Python机器学习教程",
  "item_types": ["project", "course", "knowledge_article", "note"],
  "limit": 10
}
```

**响应体：**
```json
[
  {
    "id": 1,
    "title": "Python机器学习实战项目",
    "type": "project",
    "content_snippet": "基于Python的机器学习项目...",
    "relevance_score": 0.92
  }
]
```

---

## 搜索引擎配置

### 1. 创建搜索引擎配置
**接口：** `POST /search-engine-configs/`

**摘要：** 创建搜索引擎配置

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "我的Google搜索",
  "engine_type": "google",
  "api_key": "your_api_key",
  "search_engine_id": "your_search_engine_id",
  "is_active": true
}
```

### 2. 获取搜索引擎配置
**接口：** `GET /search-engine-configs/`

**摘要：** 获取当前用户的所有搜索引擎配置

---

## TTS语音配置

### 1. 创建TTS配置
**接口：** `POST /users/me/tts_configs`

**摘要：** 创建文字转语音配置

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "name": "我的语音配置",
  "provider": "azure",
  "api_key": "your_tts_api_key",
  "region": "eastus",
  "voice_name": "zh-CN-XiaoxiaoNeural",
  "is_active": true
}
```

### 2. 获取TTS配置
**接口：** `GET /users/me/tts_configs`

**摘要：** 获取当前用户的所有TTS配置

### 3. 设置活跃配置
**接口：** `PUT /users/me/tts_configs/{config_id}/set_active`

**摘要：** 设置指定TTS配置为激活状态

---

## 随手记录

### 1. 创建随手记录
**接口：** `POST /daily-records/`

**摘要：** 创建新的随手记录

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "content": "今天学习了Vue.js的基础知识，感觉很有趣！",
  "mood": "开心",
  "tags": "学习,Vue.js,前端"
}
```

### 2. 获取随手记录
**接口：** `GET /daily-records/`

**摘要：** 获取当前用户的所有随手记录

**查询参数：**
- `mood`: 按心情过滤
- `tag`: 按标签过滤

---

## 仪表板接口

### 1. 获取仪表板概览
**接口：** `GET /dashboard/summary`

**摘要：** 获取用户工作台概览数据

**认证：** 需要Bearer Token

**响应体：**
```json
{
  "active_projects_count": 3,
  "completed_projects_count": 2,
  "learning_courses_count": 5,
  "completed_courses_count": 8,
  "active_chats_count": 2,
  "unread_messages_count": 0,
  "resume_completion_percentage": 75.5
}
```

### 2. 获取项目卡片
**接口：** `GET /dashboard/projects`

**摘要：** 获取用户参与的项目卡片列表

**查询参数：**
- `status_filter`: 按状态过滤

### 3. 获取课程卡片
**接口：** `GET /dashboard/courses`

**摘要：** 获取用户学习的课程卡片列表

**查询参数：**
- `status_filter`: 按状态过滤

---

## 积分与成就系统

### 1. 积分奖励规则
- 注册成功：+100积分
- 完成项目：+50积分
- 完成课程：+30积分
- 每日登录：+5积分

### 2. 成就系统
系统自动检测用户行为并授予相应成就：
- 首次登录
- 完成首个项目
- 完成多个课程
- 积分里程碑

---

## 统计接口

### 1. 获取用户完成项目数
**接口：** `GET /users/{user_id}/completed-projects-count`

**摘要：** 获取指定用户完成的项目总数

**认证：** 需要Bearer Token（本人或管理员）

**响应体：**
```json
{
  "count": 5,
  "description": "由用户 1 创建并完成的项目总数"
}
```

### 2. 获取用户完成课程数
**接口：** `GET /users/{user_id}/completed-courses-count`

**摘要：** 获取指定用户完成的课程总数

### 3. 获取课程全球完成数
**接口：** `GET /courses/{course_id}/completed-by-count`

**摘要：** 获取指定课程被多少学生完成

---

## 健康检查

### 1. 健康检查
**接口：** `GET /health`

**摘要：** API服务健康状态检查

**响应体：**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T10:00:00",
  "version": "0.1.0"
}
```

---

## 错误处理

API使用标准HTTP状态码：

- `200 OK`: 请求成功
- `201 Created`: 资源创建成功
- `204 No Content`: 请求成功但无返回内容
- `400 Bad Request`: 请求参数错误
- `401 Unauthorized`: 未授权，需要登录
- `403 Forbidden`: 禁止访问，权限不足
- `404 Not Found`: 资源未找到
- `409 Conflict`: 资源冲突（如重复创建）
- `422 Unprocessable Entity`: 请求格式正确但业务逻辑错误
- `500 Internal Server Error`: 服务器内部错误

**错误响应格式：**
```json
{
  "detail": "错误详细信息"
}
```

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
