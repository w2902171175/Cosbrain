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
- [MCP服务配置](#mcp服务配置)
- [聊天室管理](#聊天室管理)
- [收藏夹管理](#收藏夹管理)
- [随手记录](#随手记录)
- [仪表板接口](#仪表板接口)
- [论坛功能](#论坛功能)
- [积分与成就系统](#积分与成就系统)
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

### 5. 更新用户LLM配置
**接口：** `PUT /users/me/llm-config`

**摘要：** 更新当前用户的LLM（大语言模型）配置

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "llm_provider": "openai",
  "llm_model": "gpt-4",
  "llm_api_key": "your_api_key",
  "llm_api_base": "https://api.openai.com/v1"
}
```

### 6. 获取可用LLM模型
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
    }
  }
}
```

### 7. 获取所有学生列表
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

### 8. 获取指定学生详情
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
  "required_skills": ["Python", "React", "机器学习"],
  "team_size": 5,
  "duration_weeks": 12,
  "difficulty_level": "中等",
  "is_recruiting": true
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

**摘要：** 更新指定项目信息

**认证：** 需要Bearer Token

### 5. 为学生推荐项目
**接口：** `GET /recommend/projects/{student_id}`

**摘要：** 为指定学生推荐匹配的项目

**路径参数：**
- `student_id`: 学生ID

### 6. 为项目匹配学生
**接口：** `GET /projects/{project_id}/match-students`

**摘要：** 为指定项目匹配合适的学生

**路径参数：**
- `project_id`: 项目ID

---

## 课程管理

### 1. 创建新课程
**接口：** `POST /courses/`

**摘要：** 创建新的课程

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "Python编程基础",
  "description": "从零开始学习Python编程",
  "instructor": "李老师",
  "difficulty_level": "初级",
  "estimated_hours": 40,
  "tags": ["编程", "Python", "基础"]
}
```

### 2. 获取指定课程详情
**接口：** `GET /courses/{course_id}`

**摘要：** 获取指定课程的详细信息

### 3. 更新指定课程
**接口：** `PUT /courses/{course_id}`

**摘要：** 更新指定课程信息

### 4. 为学生推荐课程
**接口：** `GET /recommend/courses/{student_id}`

**摘要：** 为指定学生推荐匹配的课程

### 5. 加入/更新课程学习状态
**接口：** `PUT /users/me/courses/{course_id}`

**摘要：** 加入课程或更新学习进度

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "progress": 75.5,
  "status": "in_progress",
  "notes": "已完成前三章学习"
}
```

### 6. 课程材料管理

#### 6.1 上传课程材料
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

#### 6.2 获取课程材料列表
**接口：** `GET /courses/{course_id}/materials/`

**摘要：** 获取指定课程的所有学习材料

#### 6.3 获取课程材料详情
**接口：** `GET /courses/{course_id}/materials/{material_id}`

**摘要：** 获取指定课程材料的详细信息

#### 6.4 更新课程材料
**接口：** `PUT /courses/{course_id}/materials/{material_id}`

**摘要：** 更新指定课程材料信息

#### 6.5 删除课程材料
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
  "is_public": false
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
  "tags": ["Python", "函数", "编程"]
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
file: [文件]
title: "文档标题"
description: "文档描述"
```

#### 7.2 获取知识文档列表
**接口：** `GET /knowledge-bases/{kb_id}/documents/`

**摘要：** 获取指定知识库的所有文档

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
  "tags": ["学习", "Python", "总结"],
  "is_public": false
}
```

### 2. 获取笔记列表
**接口：** `GET /notes/`

**摘要：** 获取当前用户所有笔记

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
  "question": "Python中如何定义类？",
  "knowledge_base_id": 1,
  "use_tools": true,
  "conversation_id": "conv_123"
}
```

**字段说明：**
- `question`: 用户问题（必填）
- `knowledge_base_id`: 知识库ID（可选，指定后将使用RAG）
- `use_tools`: 是否启用工具调用（可选）
- `conversation_id`: 对话ID（可选，用于上下文记忆）

**响应体：**
```json
{
  "answer": "在Python中定义类使用class关键字...",
  "sources": [
    {
      "document_title": "Python基础教程",
      "chunk_content": "相关内容片段",
      "similarity_score": 0.95
    }
  ],
  "tool_calls": [],
  "conversation_id": "conv_123"
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
  "provider": "google",
  "api_key": "your_api_key",
  "search_engine_id": "your_search_engine_id",
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
  "provider": "azure",
  "api_key": "your_api_key",
  "region": "eastus",
  "voice": "zh-CN-XiaoxiaoNeural",
  "speed": 1.0,
  "pitch": 0,
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
  "server_name": "filesystem",
  "command": ["python", "-m", "mcp_server_filesystem"],
  "args": ["/path/to/allowed/directory"],
  "env_vars": {},
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
  "description": "专门讨论Python编程的聊天室",
  "room_type": "public",
  "max_members": 50
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
  "content": "大家好，我是新成员！",
  "message_type": "text"
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
  "parent_folder_id": null
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
  "url": "https://docs.python.org/",
  "content_type": "link",
  "description": "Python官方文档链接",
  "folder_id": 1,
  "tags": ["Python", "文档", "官方"]
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
  "title": "今日学习心得",
  "content": "今天学习了装饰器，感觉很有趣...",
  "record_type": "学习心得",
  "tags": ["学习", "装饰器", "Python"]
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
  "total_projects": 15,
  "total_courses": 8,
  "total_notes": 42,
  "total_knowledge_bases": 3,
  "recent_activities": [
    {
      "type": "note_created",
      "title": "新建笔记：Python装饰器",
      "timestamp": "2024-01-01T10:00:00"
    }
  ]
}
```

### 2. 获取项目卡片
**接口：** `GET /dashboard/projects`

**摘要：** 获取仪表板项目卡片数据

**查询参数：**
- `limit`: 限制返回数量
- `status`: 项目状态筛选

### 3. 获取课程卡片
**接口：** `GET /dashboard/courses`

**摘要：** 获取仪表板课程卡片数据

**查询参数：**
- `limit`: 限制返回数量
- `status`: 学习状态筛选

---

## 论坛功能

### 1. 发布论坛话题
**接口：** `POST /forum/topics/`

**摘要：** 发布新论坛话题

**认证：** 需要Bearer Token

**请求体：**
```json
{
  "title": "关于Python性能优化的讨论",
  "content": "最近在学习Python性能优化，想和大家交流一下经验...",
  "category": "技术讨论",
  "tags": ["Python", "性能优化", "讨论"]
}
```

### 2. 获取论坛话题列表
**接口：** `GET /forum/topics/`

**摘要：** 获取论坛话题列表

**查询参数：**
- `category`: 分类筛选
- `limit`: 限制返回数量
- `offset`: 偏移量

### 3. 获取论坛话题详情
**接口：** `GET /forum/topics/{topic_id}`

**摘要：** 获取指定论坛话题详情

### 4. 更新论坛话题
**接口：** `PUT /forum/topics/{topic_id}`

**摘要：** 更新指定论坛话题

### 5. 删除论坛话题
**接口：** `DELETE /forum/topics/{topic_id}`

**摘要：** 删除指定论坛话题

### 6. 发表论坛评论
**接口：** `POST /forum/topics/{topic_id}/comments/`

**摘要：** 对指定话题发表评论

**请求体：**
```json
{
  "content": "我觉得使用Cython是一个不错的优化选择",
  "parent_comment_id": null
}
```

### 7. 获取论坛评论列表
**接口：** `GET /forum/topics/{topic_id}/comments/`

**摘要：** 获取指定话题的所有评论

### 8. 更新论坛评论
**接口：** `PUT /forum/comments/{comment_id}`

**摘要：** 更新指定论坛评论

### 9. 删除论坛评论
**接口：** `DELETE /forum/comments/{comment_id}`

**摘要：** 删除指定论坛评论

### 10. 点赞论坛内容
**接口：** `POST /forum/likes/`

**摘要：** 点赞论坛话题或评论

**请求体：**
```json
{
  "topic_id": 1,
  "comment_id": null
}
```

### 11. 取消点赞
**接口：** `DELETE /forum/likes/`

**摘要：** 取消点赞论坛话题或评论

### 12. 关注用户
**接口：** `POST /forum/follow/`

**摘要：** 关注一个用户

**请求体：**
```json
{
  "followed_user_id": 2
}
```

### 13. 取消关注用户
**接口：** `DELETE /forum/unfollow/`

**摘要：** 取消关注一个用户

---

## 积分与成就系统

### 1. 创建成就定义（管理员）
**接口：** `POST /admin/achievements/definitions`

**摘要：** 【管理员专用】创建新的成就定义

**认证：** 需要管理员权限

**请求体：**
```json
{
  "name": "初次登录",
  "description": "完成首次登录",
  "icon": "login",
  "points_reward": 10,
  "achievement_type": "milestone",
  "conditions": {"login_count": 1}
}
```

### 2. 获取成就定义列表
**接口：** `GET /achievements/definitions`

**摘要：** 获取所有可获得的成就定义

### 3. 获取成就定义详情
**接口：** `GET /achievements/definitions/{achievement_id}`

**摘要：** 获取指定成就定义详情

### 4. 更新成就定义（管理员）
**接口：** `PUT /admin/achievements/definitions/{achievement_id}`

**摘要：** 【管理员专用】更新指定成就定义

### 5. 删除成就定义（管理员）
**接口：** `DELETE /admin/achievements/definitions/{achievement_id}`

**摘要：** 【管理员专用】删除指定成就定义

### 6. 获取用户积分余额
**接口：** `GET /users/me/points`

**摘要：** 获取当前用户积分余额和上次登录时间

**响应体：**
```json
{
  "id": 1,
  "total_points": 150,
  "last_login": "2024-01-01T10:00:00"
}
```

### 7. 获取积分交易历史
**接口：** `GET /users/me/points/history`

**摘要：** 获取当前用户积分交易历史

### 8. 获取用户成就列表
**接口：** `GET /users/me/achievements`

**摘要：** 获取当前用户已获得的成就列表

### 9. 积分奖励（管理员）
**接口：** `POST /admin/points/reward`

**摘要：** 【管理员专用】为用户奖励积分

**请求体：**
```json
{
  "user_id": 1,
  "points": 50,
  "reason": "完成项目里程碑"
}
```

---

## WebSocket实时通信

### 1. 聊天室WebSocket连接
**接口：** `WebSocket /ws/chat/{room_id}`

**摘要：** 建立聊天室的WebSocket连接，用于实时消息传输

**认证：** 需要在WebSocket握手时提供token参数

**连接URL示例：**
```
ws://localhost:8000/ws/chat/1?token=your_jwt_token
```

**消息格式：**
```json
{
  "type": "message",
  "content": "Hello, everyone!",
  "sender_id": 1,
  "sender_name": "张三",
  "timestamp": "2024-01-01T10:00:00"
}
```

---

## 系统管理

### 1. 健康检查
**接口：** `GET /health`

**摘要：** 健康检查，返回API服务状态

**响应体：**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T10:00:00",
  "version": "0.1.0"
}
```

### 2. 设置用户管理员权限
**接口：** `PUT /admin/users/{user_id}/set-admin`

**摘要：** 【超级管理员专用】设置指定用户的管理员权限

**认证：** 需要超级管理员权限

**请求体：**
```json
{
  "is_admin": true
}
```

---

## 错误码说明

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 204 | 删除成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 422 | 请求参数验证失败 |
| 500 | 服务器内部错误 |

---

## 更新日志

### v0.1.0 (2024-12-08)
- 初版API文档发布
- 包含用户认证、项目管理、课程管理等核心功能
- 新增AI智能服务、搜索引擎配置等高级功能
- 支持TTS语音配置和MCP服务配置
- 实现聊天室、论坛、积分成就等社交功能
- 添加WebSocket实时通信支持

---

*本文档持续更新中，如有疑问请联系开发团队。*
