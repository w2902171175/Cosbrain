# 鸿庆书云创新协作平台API接口文档

 本文档详细描述了鸿庆书云创新协作平台的API接口，提供学生项目匹配、智能推荐、知识管理、课程学习和协作功能。

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
  "timestamp": "2025-01-12T10:00:00Z"
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

### 5. 更新用户信息
**接口：** `PUT /users/me`

**摘要：** 更新当前登录用户的信息

**认证：** 需要Bearer Token

### 6. 更新用户LLM配置
**接口：** `PUT /users/me/llm-config`

**摘要：** 更新当前用户的LLM（大语言模型）配置

**认证：** 需要Bearer Token

### 7. 获取可用LLM模型
**接口：** `GET /llm/available-models`

**摘要：** 获取可配置的LLM服务商及模型列表

### 8. 获取所有学生列表
**接口：** `GET /students/`

**摘要：** 获取所有学生用户列表

### 9. 获取指定学生详情
**接口：** `GET /students/{student_id}`

**摘要：** 获取指定学生的详细信息

---

## 项目管理

### 1. 创建新项目
**接口：** `POST /projects/`

**摘要：** 创建新的项目

**认证：** 需要Bearer Token

### 2. 获取所有项目列表
**接口：** `GET /projects/`

**摘要：** 获取所有项目列表

### 3. 获取指定项目详情
**接口：** `GET /projects/{project_id}`

**摘要：** 获取指定项目的详细信息

### 4. 更新指定项目
**接口：** `PUT /projects/{project_id}`

**摘要：** 更新指定项目信息（仅项目创建者或管理员可操作）

**认证：** 需要Bearer Token

### 5. 为学生推荐项目
**接口：** `GET /recommend/projects/{student_id}`

**摘要：** 为指定学生推荐匹配的项目

### 6. 为项目匹配学生
**接口：** `GET /projects/{project_id}/match-students`

**摘要：** 为指定项目匹配合适的学生

---

## 课程管理

### 1. 创建新课程
**接口：** `POST /courses/`

**摘要：** 创建新的课程（仅管理员可操作）

**认证：** 需要Bearer Token（管理员权限）

### 2. 获取指定课程详情
**接口：** `GET /courses/{course_id}`

**摘要：** 获取指定课程的详细信息

### 3. 更新指定课程
**接口：** `PUT /courses/{course_id}`

**摘要：** 更新指定课程信息（仅管理员可操作）

### 4. 为学生推荐课程
**接口：** `GET /recommend/courses/{student_id}`

**摘要：** 为指定学生推荐匹配的课程

### 5. 更新用户课程关系
**接口：** `PUT /users/me/courses/{course_id}`

**摘要：** 更新当前用户与指定课程的关联关系

### 6. 创建课程材料
**接口：** `POST /courses/{course_id}/materials/`

**摘要：** 为指定课程创建新的学习材料

### 7. 获取课程材料列表
**接口：** `GET /courses/{course_id}/materials/`

**摘要：** 获取指定课程的所有学习材料

### 8. 获取指定课程材料
**接口：** `GET /courses/{course_id}/materials/{material_id}`

**摘要：** 获取指定课程材料的详细信息

### 9. 更新课程材料
**接口：** `PUT /courses/{course_id}/materials/{material_id}`

**摘要：** 更新指定课程材料

### 10. 删除课程材料
**接口：** `DELETE /courses/{course_id}/materials/{material_id}`

**摘要：** 删除指定课程材料

---

## 知识库管理

### 1. 创建新知识库
**接口：** `POST /knowledge-bases/`

**摘要：** 创建新的知识库

**认证：** 需要Bearer Token

### 2. 获取所有知识库
**接口：** `GET /knowledge-bases/`

**摘要：** 获取当前用户所有知识库

### 3. 获取指定知识库详情
**接口：** `GET /knowledge-bases/{kb_id}`

**摘要：** 获取指定知识库的详细信息

### 4. 更新指定知识库
**接口：** `PUT /knowledge-bases/{kb_id}`

**摘要：** 更新指定知识库信息

### 5. 删除指定知识库
**接口：** `DELETE /knowledge-bases/{kb_id}`

**摘要：** 删除指定知识库

### 6. 创建知识库文章
**接口：** `POST /knowledge-bases/{kb_id}/articles/`

**摘要：** 在指定知识库中创建新文章

### 7. 获取知识库文章列表
**接口：** `GET /knowledge-bases/{kb_id}/articles/`

**摘要：** 获取指定知识库的所有文章

### 8. 获取指定文章详情
**接口：** `GET /articles/{article_id}`

**摘要：** 获取指定文章的详细信息

### 9. 更新指定文章
**接口：** `PUT /articles/{article_id}`

**摘要：** 更新指定文章内容

### 10. 删除指定文章
**接口：** `DELETE /articles/{article_id}`

**摘要：** 删除指定文章

### 11. 上传知识文档
**接口：** `POST /knowledge-bases/{kb_id}/documents/`

**摘要：** 上传文档到指定知识库

**认证：** 需要Bearer Token

**请求体：** `multipart/form-data`
```
file: [文件] （支持PDF、DOCX、TXT格式）
```

**响应状态：** `202 Accepted`（文档将在后台异步处理）

### 12. 获取知识文档列表
**接口：** `GET /knowledge-bases/{kb_id}/documents/`

**摘要：** 获取指定知识库的所有文档

**查询参数：**
- `status_filter`: 按状态过滤（processing/completed/failed）

### 13. 获取指定知识文档
**接口：** `GET /knowledge-bases/{kb_id}/documents/{document_id}`

**摘要：** 获取指定知识文档的详细信息

### 14. 删除知识文档
**接口：** `DELETE /knowledge-bases/{kb_id}/documents/{document_id}`

**摘要：** 删除指定知识文档

### 15. 获取文档内容
**接口：** `GET /knowledge-bases/{kb_id}/documents/{document_id}/content`

**摘要：** 获取知识文档的原始文本内容（调试用）

### 16. 获取文档分块
**接口：** `GET /knowledge-bases/{kb_id}/documents/{document_id}/chunks`

**摘要：** 获取知识文档的分块信息

---

## 笔记管理

### 1. 创建新笔记
**接口：** `POST /notes/`

**摘要：** 创建新的个人笔记

**认证：** 需要Bearer Token

### 2. 获取所有笔记
**接口：** `GET /notes/`

**摘要：** 获取当前用户所有笔记

### 3. 获取指定笔记详情
**接口：** `GET /notes/{note_id}`

**摘要：** 获取指定笔记的详细信息

### 4. 更新指定笔记
**接口：** `PUT /notes/{note_id}`

**摘要：** 更新指定笔记内容

### 5. 删除指定笔记
**接口：** `DELETE /notes/{note_id}`

**摘要：** 删除指定笔记

---

## AI智能服务

### 1. AI智能问答
**接口：** `POST /ai/qa`

**摘要：** AI智能问答（支持通用问答、RAG检索问答或工具调用）

**认证：** 需要Bearer Token

### 2. 智能语义搜索
**接口：** `POST /search/semantic`

**摘要：** 基于向量嵌入的智能语义搜索

### 3. 网络搜索
**接口：** `POST /ai/web-search`

**摘要：** 执行一次网络搜索

---

## 搜索引擎配置

### 1. 创建搜索引擎配置
**接口：** `POST /search-engine-configs/`

**摘要：** 创建新的搜索引擎配置

### 2. 获取搜索引擎配置列表
**接口：** `GET /search-engine-configs/`

**摘要：** 获取当前用户的所有搜索引擎配置

### 3. 获取指定搜索引擎配置
**接口：** `GET /search-engine-configs/{config_id}`

**摘要：** 获取指定搜索引擎配置的详细信息

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

### 2. 获取TTS配置列表
**接口：** `GET /users/me/tts_configs`

**摘要：** 获取当前用户的所有TTS配置

### 3. 获取指定TTS配置
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

## 聊天室管理

### 1. 创建聊天室
**接口：** `POST /chat-rooms/`

**摘要：** 创建新的聊天室

### 2. 获取聊天室列表
**接口：** `GET /chatrooms/`

**摘要：** 获取当前用户所属的所有聊天室

### 3. 获取指定聊天室详情
**接口：** `GET /chatrooms/{room_id}`

**摘要：** 获取指定聊天室详情

### 4. 获取聊天室成员
**接口：** `GET /chatrooms/{room_id}/members`

**摘要：** 获取指定聊天室的所有成员

### 5. 设置成员角色
**接口：** `PUT /chat-rooms/{room_id}/members/{member_id}/set-role`

**摘要：** 设置聊天室成员的角色

### 6. 移除聊天室成员
**接口：** `DELETE /chat-rooms/{room_id}/members/{member_id}`

**摘要：** 从聊天室中移除指定成员

### 7. 更新聊天室信息
**接口：** `PUT /chatrooms/{room_id}/`

**摘要：** 更新指定聊天室信息

### 8. 删除聊天室
**接口：** `DELETE /chatrooms/{room_id}`

**摘要：** 删除指定聊天室

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

### 13. 获取聊天消息
**接口：** `GET /chatrooms/{room_id}/messages/`

**摘要：** 获取指定聊天室的历史消息

---

## 收藏夹管理

### 1. 创建文件夹
**接口：** `POST /folders/`

**摘要：** 创建新文件夹

### 2. 获取文件夹列表
**接口：** `GET /folders/`

**摘要：** 获取当前用户所有文件夹

### 3. 获取指定文件夹详情
**接口：** `GET /folders/{folder_id}`

**摘要：** 获取指定文件夹详情

### 4. 更新指定文件夹
**接口：** `PUT /folders/{folder_id}`

**摘要：** 更新指定文件夹

### 5. 删除指定文件夹
**接口：** `DELETE /folders/{folder_id}`

**摘要：** 删除指定文件夹

### 6. 创建收藏内容
**接口：** `POST /collections/`

**摘要：** 创建新收藏内容

### 7. 获取收藏内容列表
**接口：** `GET /collections/`

**摘要：** 获取当前用户所有收藏内容

### 8. 获取指定收藏内容
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

### 2. 获取随手记录列表
**接口：** `GET /daily-records/`

**摘要：** 获取当前用户所有随手记录

### 3. 获取指定随手记录
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

### 2. 获取项目卡片
**接口：** `GET /dashboard/projects`

**摘要：** 获取仪表板项目卡片数据

### 3. 获取课程卡片
**接口：** `GET /dashboard/courses`

**摘要：** 获取仪表板课程卡片数据

---

## 论坛功能

### 1. 发布论坛话题
**接口：** `POST /forum/topics/`

**摘要：** 发布新论坛话题

### 2. 获取论坛话题列表
**接口：** `GET /forum/topics/`

**摘要：** 获取论坛话题列表

---

## AI对话系统

### 1. 获取AI对话列表
**接口：** `GET /users/me/ai-conversations`

**摘要：** 获取当前用户的所有AI对话会话

### 2. 获取指定AI对话
**接口：** `GET /users/me/ai-conversations/{conversation_id}`

**摘要：** 获取指定AI对话会话的详细信息

### 3. 获取对话消息
**接口：** `GET /users/me/ai-conversations/{conversation_id}/messages`

**摘要：** 获取指定AI对话的所有消息

### 4. 更新对话标题
**接口：** `PUT /users/me/ai-conversations/{conversation_id}`

**摘要：** 更新指定AI对话的标题

### 5. 删除AI对话
**接口：** `DELETE /users/me/ai-conversations/{conversation_id}`

**摘要：** 删除指定AI对话会话

---

## 系统管理

### 1. 设置用户管理员权限
**接口：** `PUT /admin/users/{user_id}/set-admin`

**摘要：** 设置或取消用户的管理员权限（需要管理员权限）

---

## 响应状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 201 | 创建成功 |
| 204 | 删除成功（无内容） |
| 400 | 请求参数错误 |
| 401 | 未授权（需要登录） |
| 403 | 禁止访问（权限不足） |
| 404 | 资源不存在 |
| 422 | 请求参数验证失败 |
| 500 | 服务器内部错误 |

---

## 错误响应格式

```json
{
  "detail": "错误详细信息"
}
```

---

**文档更新时间：** 2025年1月12日

**API版本：** v0.1.0
