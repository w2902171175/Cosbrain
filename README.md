# 🎓 鸿庆书云创新协作平台 (Cosbrain)

<div align="center">

![Logo](https://img.shields.io/badge/🎓-鸿庆书云-blue?style=for-the-badge)

**基于AI技术的现代化智慧教育协作平台**

*为师生提供智能匹配、知识管理、课程学习和实时协作的一站式教育解决方案*

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg?style=flat-square)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-blue.svg?style=flat-square)](https://postgresql.org)
[![pgvector](https://img.shields.io/badge/pgvector-0.2+-purple.svg?style=flat-square)](https://github.com/pgvector/pgvector)
[![License](https://img.shields.io/badge/License-Custom-yellow.svg?style=flat-square)](LICENSE)

[![GitHub last commit](https://img.shields.io/github/last-commit/w2902171175/Cosbrain?style=flat-square)](https://github.com/w2902171175/Cosbrain)
[![GitHub code size](https://img.shields.io/github/languages/code-size/w2902171175/Cosbrain?style=flat-square)](https://github.com/w2902171175/Cosbrain)
[![Lines of code](https://img.shields.io/tokei/lines/github/w2902171175/Cosbrain?style=flat-square)](https://github.com/w2902171175/Cosbrain)

[功能特性](#-核心特性) • [快速开始](#-快速开始) • [API文档](#-api-文档) • [部署指南](#-生产部署) • [贡献指南](#-贡献指南)

</div>

---

## 📖 项目简介

**鸿庆书云创新协作平台 (Cosbrain)** 是一个面向现代教育的智能化协作平台，致力于为学生、教师和研究者构建一个高效、智能、协作的学习生态系统。

### 🎯 项目愿景

> **"让每一个学习者都能在智能化的环境中，找到最适合的学习伙伴、最优质的学习资源，实现个性化的学习成长"**

### 🌟 平台核心价值

- **🤖 AI驱动**: 基于先进的向量嵌入技术和大语言模型，提供智能匹配、语义搜索和个性化推荐
- **📚 知识中心**: 构建结构化的知识管理体系，支持多格式文档解析和智能检索
- **🤝 协作优先**: 实时聊天、项目协作、学习小组等多维度的协作支持
- **🎓 教育专注**: 专为教育场景设计的功能模块，从课程管理到学习评估的全流程覆盖
- **🔧 高度定制**: 灵活的配置系统，支持个性化的AI模型、搜索引擎和服务集成

### 📊 平台规模

- **🗃️ 数据模型**: 29个核心数据表，覆盖用户、项目、知识、课程、社交等全业务域
- **🔗 API接口**: 12,000+ 行代码实现的RESTful API，支持完整的业务功能
- **🧠 AI集成**: 支持OpenAI GPT、Sentence Transformers等多种AI模型
- **📁 文件支持**: Word、PDF、Excel、PPT等多格式文档的智能解析

## ✨ 核心特性

<table>
<tr>
<td width="50%">

### 🤖 AI智能引擎
- **🎯 智能匹配算法**: 基于pgvector向量数据库，使用sentence-transformers模型进行语义分析，实现学生-项目-课程的精准匹配
- **🧠 多模型集成**: 支持OpenAI GPT-3.5/4、本地Transformer模型等，提供灵活的AI服务切换
- **📄 智能文档解析**: 自动解析Word、PDF、Excel、PPT等格式，提取结构化信息并向量化存储
- **🔍 向量化搜索**: 基于语义相似度的高精度搜索，支持跨语言和模糊匹配
- **💬 AI对话助手**: 集成多种LLM模型，支持RAG检索增强生成，提供专业的学术对话

### 📚 知识管理系统
- **🏗️ 分层架构**: 知识库→文件夹→文章的三级管理结构，支持无限层级嵌套
- **⚡ 智能处理**: 文档自动分块、向量化存储、元数据提取，支持RAG检索
- **📎 格式支持**: Word(.docx)、PDF、Excel(.xlsx)、PowerPoint(.pptx)的完整解析
- **🧭 知识图谱**: 基于内容相似性构建知识关联网络，智能推荐相关内容
- **⭐ 收藏系统**: 个人收藏夹，支持分类标签和批量管理

### 💬 实时协作系统
- **⚡ WebSocket通信**: 低延迟实时消息传输，支持在线状态同步
- **👥 多人聊天室**: 项目组、学习小组、临时讨论组等多场景协作支持
- **🔐 权限管理**: 完整的聊天室成员管理、加入申请和权限控制
- **📁 文件共享**: 聊天中的文件上传、云存储集成和版本管理
- **🟢 在线状态**: 实时显示用户在线状态、活跃度和最后活动时间

</td>
<td width="50%">

### 🎯 学习管理
- **📖 课程体系**: 完整的课程创建、发布、学习进度跟踪和成绩管理
- **📚 材料管理**: 课程资料上传下载、版本控制和权限管理
- **📊 学习分析**: 详细的学习轨迹、时间统计和成绩可视化分析
- **🏷️ 技能标签**: 基于技能树的课程推荐和个性化学习路径规划
- **⭐ 互动评价**: 课程评分、评论反馈和学习心得分享

### 🌐 社区论坛
- **✍️ 话题发布**: 支持富文本编辑、图片插入、附件上传的话题发布
- **💬 多级评论**: 支持无限层级的嵌套回复和讨论串
- **❤️ 社交互动**: 点赞、关注、粉丝系统，构建学习社交网络
- **🔍 内容管理**: 话题分类、标签系统和高级搜索功能

### 🏆 激励系统
- **💰 积分机制**: 多维度积分获取（学习、分享、协作）和消费系统
- **🥇 成就系统**: 丰富的成就挑战、徽章收集和奖励机制
- **📈 排行榜**: 学习积分、活跃度、贡献度等多维度排名
- **📅 每日任务**: 签到打卡、学习目标、习惯养成的任务系统

### ⚙️ 个性化配置
- **🔧 多模型配置**: LLM、TTS、搜索引擎的个性化配置和API管理
- **🔌 MCP协议**: 支持Model Context Protocol标准，扩展AI模型能力
- **🔑 安全管理**: API密钥的加密存储、权限控制和使用监控
- **🎛️ 偏好设置**: 个人学习偏好、推荐算法参数和界面定制

</td>
</tr>
</table>

## 🛠️ 技术架构

### 🏗️ 整体架构图

```mermaid
graph TB
    subgraph "前端层"
        FE[Web前端] --> API[FastAPI后端]
        MOB[移动端] --> API
    end
    
    subgraph "应用层"
        API --> AUTH[认证中心]
        API --> BIZ[业务逻辑层]
        BIZ --> MATCH[智能匹配]
        BIZ --> KNOW[知识管理]
        BIZ --> CHAT[实时通信]
        BIZ --> COURSE[课程管理]
    end
    
    subgraph "AI服务层"
        MATCH --> AI[AI核心引擎]
        KNOW --> AI
        AI --> LLM[大语言模型]
        AI --> EMB[嵌入模型]
        AI --> SEARCH[搜索引擎]
    end
    
    subgraph "数据层"
        BIZ --> ORM[SQLAlchemy ORM]
        ORM --> PG[(PostgreSQL)]
        PG --> VECTOR[pgvector扩展]
        API --> STORAGE[对象存储]
    end
```

### � 后端技术栈

<table>
<tr>
<td width="25%"><b>🌐 Web框架</b></td>
<td width="75%">

```python
FastAPI 0.111.0          # 现代异步Web框架，自动生成OpenAPI文档
Uvicorn                  # 高性能ASGI服务器
Python-multipart        # 文件上传和表单处理支持
```

</td>
</tr>
<tr>
<td><b>�️ 数据库层</b></td>
<td>

```python
PostgreSQL 14+          # 主数据库，支持复杂查询和事务
pgvector 0.2+           # 向量数据库扩展，支持AI嵌入搜索
SQLAlchemy 2.0.32       # 现代化ORM，支持异步和类型提示
Alembic 1.13.2          # 数据库版本管理和迁移工具
```

</td>
</tr>
<tr>
<td><b>🤖 AI/ML引擎</b></td>
<td>

```python
Sentence-Transformers   # 文本语义嵌入和相似度计算
Transformers 4.38.2     # HuggingFace模型库，支持多种预训练模型
Scikit-learn 1.5.0      # 经典机器学习算法库
PyTorch 2.2.1           # 深度学习框架，模型训练和推理
OpenAI 1.12.0           # GPT API集成，支持最新模型
```

</td>
</tr>
<tr>
<td><b>� 认证安全</b></td>
<td>

```python
PassLib + BCrypt        # 密码安全哈希和验证
Python-JOSE             # JWT令牌生成和验证
Cryptography            # 高级加密算法支持
```

</td>
</tr>
<tr>
<td><b>� 文件处理</b></td>
<td>

```python
python-docx             # Word文档(.docx)解析和生成
PyPDF2                  # PDF文档内容提取
openpyxl                # Excel文件(.xlsx)操作
python-pptx             # PowerPoint(.pptx)处理
```

</td>
</tr>
<tr>
<td><b>☁️ 云服务集成</b></td>
<td>

```python
HTTPX                   # 现代异步HTTP客户端
gTTS                    # Google文本转语音服务
Boto3风格API            # S3兼容对象存储接口
```

</td>
</tr>
</table>

### 🗄️ 数据库设计

平台采用PostgreSQL作为主数据库，集成pgvector扩展支持向量存储和语义搜索。数据库设计遵循标准化原则，确保数据一致性和查询性能。

#### 📊 核心数据表（29个主要表）

<details>
<summary><b>👤 用户与权限系统</b></summary>

- **`students`** - 用户基础信息、个人配置和学习档案
- **`user_follows`** - 用户关注关系和社交网络
- **`user_achievements`** - 用户成就记录和进度跟踪
- **`point_transactions`** - 积分交易流水和余额管理

</details>

<details>
<summary><b>🚀 项目协作系统</b></summary>

- **`projects`** - 项目基本信息、状态和元数据
- **`project_applications`** - 项目申请记录和审批流程
- **`project_members`** - 项目成员关系和角色权限
- **`project_files`** - 项目文件管理和版本控制
- **`project_likes`** - 项目点赞和热度统计

</details>

<details>
<summary><b>📚 知识管理系统</b></summary>

- **`knowledge_bases`** - 知识库结构和权限配置
- **`knowledge_articles`** - 知识文章内容和元数据
- **`knowledge_documents`** - 文档管理和解析状态
- **`knowledge_document_chunks`** - 文档分块和向量存储
- **`folders`** - 文件夹层级结构管理

</details>

<details>
<summary><b>🎓 课程学习系统</b></summary>

- **`courses`** - 课程信息、大纲和配置
- **`course_materials`** - 课程资料和下载管理
- **`user_courses`** - 学习记录和进度跟踪
- **`course_likes`** - 课程评价和推荐统计

</details>

<details>
<summary><b>💬 实时通信系统</b></summary>

- **`chat_rooms`** - 聊天室配置和状态管理
- **`chat_messages`** - 消息内容和传输记录
- **`chat_room_members`** - 成员关系和权限管理
- **`chat_room_join_requests`** - 加入申请和审批流程

</details>

<details>
<summary><b>🌐 社区论坛系统</b></summary>

- **`forum_topics`** - 论坛话题和讨论内容
- **`forum_comments`** - 评论回复和嵌套结构
- **`forum_likes`** - 点赞互动和热度统计

</details>

<details>
<summary><b>🤖 AI对话系统</b></summary>

- **`ai_conversations`** - AI对话会话管理
- **`ai_conversation_messages`** - 对话消息和上下文
- **`ai_conversation_temporary_files`** - 临时文件和附件

</details>

<details>
<summary><b>⚙️ 个人管理系统</b></summary>

- **`notes`** - 个人笔记和备忘录
- **`daily_records`** - 每日学习记录和总结
- **`collected_contents`** - 收藏内容和分类管理
- **`achievements`** - 成就定义和奖励规则

</details>

<details>
<summary><b>🔧 配置管理系统</b></summary>

- **`user_mcp_configs`** - MCP协议配置和模型管理
- **`user_search_engine_configs`** - 搜索引擎个性化配置
- **`user_tts_configs`** - 文本转语音服务配置

</details>

#### 🔍 性能优化

- **索引策略**: 为高频查询字段建立复合索引，优化关联查询性能
- **向量索引**: pgvector扩展的HNSW索引，支持高效的相似度搜索
- **分区表**: 对大数据量表（如消息、日志）进行时间分区
- **连接池**: SQLAlchemy连接池配置，支持高并发访问

### 🔌 API架构

基于FastAPI的现代化RESTful API设计，具有自动文档生成、类型验证和异步处理能力。

#### 📋 API模块结构

<details>
<summary><b>🔐 认证授权模块</b></summary>

```python
# JWT令牌认证和权限控制
POST /token                    # 用户登录，获取访问令牌
POST /register                 # 用户注册
GET  /me                       # 获取当前用户信息
PUT  /me                       # 更新用户信息
POST /refresh-token            # 刷新访问令牌
```

</details>

<details>
<summary><b>🎯 智能匹配模块</b></summary>

```python
# 基于向量相似度的智能推荐
GET  /match/students           # 匹配相似学生
GET  /match/projects          # 匹配适合项目
GET  /match/courses           # 推荐相关课程
POST /match/custom            # 自定义匹配查询
```

</details>

<details>
<summary><b>📚 知识管理模块</b></summary>

```python
# 知识库和文档管理
GET    /knowledge-bases        # 获取知识库列表
POST   /knowledge-bases        # 创建知识库
GET    /knowledge-bases/{id}/articles  # 获取文章列表
POST   /documents/upload       # 上传并解析文档
GET    /documents/{id}/chunks  # 获取文档分块
POST   /knowledge/search       # 语义搜索知识内容
```

</details>

<details>
<summary><b>💬 实时通信模块</b></summary>

```python
# WebSocket和聊天室管理
WebSocket /ws/chat/{room_id}   # 实时聊天连接
GET    /chat-rooms             # 获取聊天室列表
POST   /chat-rooms             # 创建聊天室
POST   /chat-rooms/{id}/join   # 申请加入聊天室
GET    /chat-rooms/{id}/messages  # 获取历史消息
POST   /chat-rooms/{id}/upload # 上传聊天文件
```

</details>

<details>
<summary><b>🎓 课程管理模块</b></summary>

```python
# 课程和学习管理
GET    /courses                # 获取课程列表
POST   /courses                # 创建新课程
GET    /courses/{id}           # 获取课程详情
POST   /courses/{id}/enroll    # 报名参加课程
GET    /courses/{id}/materials # 获取课程资料
POST   /courses/{id}/progress  # 更新学习进度
```

</details>

<details>
<summary><b>🚀 项目协作模块</b></summary>

```python
# 项目管理和团队协作
GET    /projects               # 获取项目列表
POST   /projects               # 创建新项目
POST   /projects/{id}/apply    # 申请加入项目
GET    /projects/{id}/members  # 获取项目成员
POST   /projects/{id}/files    # 上传项目文件
GET    /projects/{id}/applications  # 管理项目申请
```

</details>

<details>
<summary><b>🌐 社区论坛模块</b></summary>

```python
# 论坛话题和社交互动
GET    /forum/topics           # 获取话题列表
POST   /forum/topics           # 发布新话题
GET    /forum/topics/{id}      # 获取话题详情
POST   /forum/topics/{id}/comments  # 发表评论
POST   /forum/topics/{id}/like # 点赞话题
GET    /forum/comments/{id}/replies  # 获取回复列表
```

</details>

<details>
<summary><b>🤖 AI服务模块</b></summary>

```python
# AI对话和智能服务
POST   /ai/chat                # AI对话接口
GET    /ai/conversations       # 获取对话历史
POST   /ai/conversations/{id}/continue  # 继续对话
POST   /ai/tts                 # 文本转语音
POST   /ai/search              # AI增强搜索
GET    /ai/models              # 获取可用模型列表
```

</details>

#### 🔧 API特性

- **📖 自动文档**: OpenAPI 3.0标准，实时生成API文档
- **✅ 数据验证**: Pydantic模型自动验证请求参数
- **⚡ 异步处理**: 全异步架构，支持高并发请求
- **🔒 安全机制**: JWT认证、CORS配置、请求限流
- **📊 监控日志**: 请求追踪、性能监控、错误报告

## 🏗️ 项目结构

```
Cosbrain/                                    # 项目根目录
├── 📄 README.md                             # 项目说明文档
├── 📋 requirements.txt                      # Python依赖包列表(60个包)
├── 📜 LICENSE                               # 自定义开源许可证
├── 🔧 alembic/                             # 数据库迁移工具
│   └── env.py                              # Alembic环境配置
├── 📊 migrations/                          # SQL迁移脚本集合
│   ├── add_chat_message_deleted_at.sql     # 聊天消息软删除功能
│   ├── add_vector_indexes.sql              # 向量索引优化
│   ├── check_indexes.sql                   # 索引健康检查
│   ├── make_forum_topics_title_nullable.sql # 论坛标题字段优化
│   └── migrate_llm_model_id_to_multiple.sql # LLM模型多选支持
└── 🚀 project/                             # 主要代码目录
    ├── 🎯 main.py                          # FastAPI应用入口(12,824行)
    ├── 🗄️ models.py                        # SQLAlchemy数据模型(29个表)
    ├── 📋 schemas.py                       # Pydantic数据验证模式
    ├── 🔌 database.py                      # 数据库连接和会话管理
    ├── ⚙️ dependencies.py                  # FastAPI依赖注入配置
    ├── 🧠 ai_core.py                       # AI功能核心模块
    ├── ☁️ oss_utils.py                     # 对象存储服务工具
    ├── 📥 import_data.py                   # 数据导入和初始化脚本
    ├── 🔄 reset_sequences.py               # 数据库序列重置工具
    ├── 🔧 fix_data_serialization.py        # 数据序列化修复工具
    ├── 📂 data/                            # 数据文件目录
    │   ├── projects.csv                    # 项目示例数据
    │   ├── students.csv                    # 学生示例数据
    │   └── export/                         # 数据导出目录
    │       ├── achievements_schema.csv     # 成就系统表结构
    │       ├── achievements.csv            # 成就数据
    │       ├── ai_conversation_*.csv       # AI对话相关数据
    │       ├── chat_*.csv                  # 聊天系统数据
    │       ├── course_*.csv                # 课程系统数据
    │       ├── knowledge_*.csv             # 知识管理数据
    │       └── ...                         # 其他业务数据文件
    ├── 📚 后端api说明文档/                  # API文档目录(待完善)
    └── 🗂️ __pycache__/                     # Python字节码缓存
        ├── __init__.cpython-311.pyc        # Python 3.11编译缓存
        ├── __init__.cpython-38.pyc         # Python 3.8编译缓存
        ├── ai_core.cpython-*.pyc           # AI模块编译缓存
        ├── database.cpython-*.pyc          # 数据库模块编译缓存
        ├── main.cpython-*.pyc              # 主程序编译缓存
        ├── models.cpython-*.pyc            # 数据模型编译缓存
        └── ...                             # 其他模块编译缓存
```

### 📊 代码统计

| 模块 | 文件 | 代码行数 | 主要功能 |
|------|------|----------|----------|
| **main.py** | 1 | 12,824行 | API路由、业务逻辑、WebSocket处理 |
| **models.py** | 1 | 1,076行 | 29个数据表模型定义 |
| **schemas.py** | 1 | ~800行 | Pydantic数据验证模式 |
| **ai_core.py** | 1 | ~500行 | AI模型集成和向量处理 |
| **database.py** | 1 | ~200行 | 数据库连接和会话管理 |
| **总计** | 5+ | 15,000+行 | 完整的后端API系统 |

### 🗃️ 数据文件

平台包含完整的示例数据和导出功能：
- **📈 业务数据**: 29个表的完整数据导出
- **📋 表结构**: 每个表的schema文档
- **🧪 测试数据**: projects.csv和students.csv示例数据
- **🔄 迁移脚本**: 数据库版本升级的SQL脚本

## 📦 快速开始

### 🔧 环境要求

<table>
<tr>
<td width="50%">

**🖥️ 系统要求**
- **操作系统**: Windows 10+, Ubuntu 18.04+, macOS 10.15+
- **Python版本**: 3.8+ (推荐 3.11+)
- **内存**: 至少 4GB RAM (推荐 8GB+)
- **存储**: 5GB+ 可用空间
- **网络**: 稳定的互联网连接

</td>
<td width="50%">

**🗄️ 数据库要求**
- **PostgreSQL**: 14+ 版本
- **pgvector扩展**: 0.2+ 版本
- **数据库权限**: 创建数据库和扩展的权限
- **连接数**: 建议配置100+连接数

</td>
</tr>
</table>

### 🚀 安装部署

#### 1️⃣ 克隆项目

```bash
# 克隆代码仓库
git clone https://github.com/w2902171175/Cosbrain.git
cd Cosbrain

# 查看项目结构
ls -la
```

#### 2️⃣ 创建虚拟环境

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 验证环境
python --version
pip --version
```

</details>

<details>
<summary><b>Linux/macOS (Bash)</b></summary>

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 验证环境
python --version
pip --version
```

</details>

#### 3️⃣ 安装依赖

```bash
# 升级pip到最新版本
pip install --upgrade pip

# 安装项目依赖(60个包)
pip install -r requirements.txt

# 验证关键包安装
python -c "import fastapi, sqlalchemy, pgvector, torch; print('✅ 核心依赖安装成功')"
```

#### 4️⃣ 数据库配置

<details>
<summary><b>🐘 PostgreSQL安装与配置</b></summary>

**Ubuntu/Debian:**
```bash
# 安装PostgreSQL和pgvector
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo apt install postgresql-14-pgvector

# 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Windows:**
```powershell
# 使用Chocolatey安装
choco install postgresql
# 或下载官方安装包: https://www.postgresql.org/download/windows/
```

**创建数据库和扩展:**
```sql
-- 以postgres用户连接
sudo -u postgres psql

-- 创建数据库
CREATE DATABASE hongqing_platform;

-- 创建用户
CREATE USER hongqing_user WITH PASSWORD 'your_secure_password';

-- 授权
GRANT ALL PRIVILEGES ON DATABASE hongqing_platform TO hongqing_user;

-- 连接到项目数据库
\c hongqing_platform;

-- 安装pgvector扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 验证扩展
SELECT * FROM pg_extension WHERE extname = 'vector';
```

</details>

#### 5️⃣ 环境配置

创建 `.env` 配置文件：

```bash
# 复制示例配置
cp .env.example .env
# 或手动创建
touch .env
```

**完整配置示例:**

```env
# ==================== 数据库配置 ====================
DATABASE_URL=postgresql://hongqing_user:your_secure_password@localhost:5432/hongqing_platform

# ==================== 安全配置 ====================
SECRET_KEY=your-super-secret-key-change-in-production-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ==================== AI服务配置 ====================
# OpenAI GPT服务 (可选)
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# 其他AI服务 (可选)
ANTHROPIC_API_KEY=your-anthropic-key
GOOGLE_API_KEY=your-google-api-key

# ==================== 对象存储配置 ====================
# S3兼容存储 (可选)
S3_ACCESS_KEY_ID=your-access-key-id
S3_SECRET_ACCESS_KEY=your-secret-access-key
S3_ENDPOINT_URL=https://your-s3-endpoint.com
S3_BUCKET_NAME=hongqing-platform-files
S3_BASE_URL=https://your-cdn-domain.com
S3_REGION=us-east-1

# ==================== 文件上传配置 ====================
UPLOAD_DIR=./project/uploaded_files
TEMP_AUDIO_DIR=./project/temp_audio
MAX_FILE_SIZE=10485760          # 10MB
ALLOWED_EXTENSIONS=.pdf,.docx,.xlsx,.pptx,.txt,.md

# ==================== 开发配置 ====================
DEBUG=true
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
ENABLE_DOCS=true
```

#### 6️⃣ 初始化数据库

```bash
# 进入项目目录
cd project

# 初始化数据库表结构
python -c "
from database import init_db
print('🔄 正在初始化数据库...')
init_db()
print('✅ 数据库初始化完成')
"

# 检查表是否创建成功
python -c "
from database import SessionLocal
from sqlalchemy import text
with SessionLocal() as db:
    result = db.execute(text('SELECT count(*) FROM information_schema.tables WHERE table_schema = \\'public\\''))
    count = result.scalar()
    print(f'✅ 成功创建 {count} 个数据表')
"
```

#### 7️⃣ 导入示例数据 (可选)

```bash
# 导入预设的示例数据
python import_data.py

# 验证数据导入
python -c "
from database import SessionLocal
from models import Student, Project
with SessionLocal() as db:
    students = db.query(Student).count()
    projects = db.query(Project).count()
    print(f'✅ 导入数据: {students} 个用户, {projects} 个项目')
"
```

#### 8️⃣ 启动服务

<details>
<summary><b>🏃‍♂️ 开发模式启动</b></summary>

```bash
# 进入项目目录
cd project

# 启动开发服务器
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 或使用详细日志模式
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 --log-level debug
```

</details>

<details>
<summary><b>🚀 生产模式启动</b></summary>

```bash
# 安装生产服务器
pip install gunicorn

# 启动生产服务器
gunicorn project.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

</details>

#### 9️⃣ 验证部署

服务启动后，访问以下地址验证部署：

| 服务 | 地址 | 说明 |
|------|------|------|
| **🏠 主页** | http://localhost:8000/ | API根路径和状态检查 |
| **📚 API文档** | http://localhost:8000/docs | Swagger UI交互式文档 |
| **📖 ReDoc文档** | http://localhost:8000/redoc | ReDoc风格的API文档 |
| **🔌 健康检查** | http://localhost:8000/health | 服务健康状态监控 |

**✅ 成功标志:**
- API文档正常显示
- 数据库连接成功
- 29个数据表正确创建
- AI模型加载无错误（如果配置了AI服务）

## � API 文档

平台提供完整的RESTful API接口，支持自动文档生成和交互式测试。

### 🔗 文档访问

| 文档类型 | 访问地址 | 特点 |
|----------|----------|------|
| **Swagger UI** | http://localhost:8000/docs | 交互式API测试，支持在线调用 |
| **ReDoc** | http://localhost:8000/redoc | 美观的文档展示，适合阅读 |
| **OpenAPI JSON** | http://localhost:8000/openapi.json | 机器可读的API规范 |

### 🚀 API 模块概览

<details>
<summary><b>🔐 认证授权 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/token` | 用户登录，获取JWT访问令牌 |
| `POST` | `/register` | 用户注册，创建新账户 |
| `GET` | `/me` | 获取当前用户详细信息 |
| `PUT` | `/me` | 更新用户个人信息 |
| `POST` | `/refresh-token` | 刷新过期的访问令牌 |

</details>

<details>
<summary><b>🎯 智能匹配 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/match/students` | 基于技能和兴趣匹配相似学生 |
| `GET` | `/match/projects` | 推荐适合的项目机会 |
| `GET` | `/match/courses` | 个性化课程推荐 |
| `POST` | `/match/custom` | 自定义匹配条件查询 |
| `GET` | `/match/similar-users/{user_id}` | 查找相似用户 |

</details>

<details>
<summary><b>📚 知识管理 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/knowledge-bases` | 获取所有知识库列表 |
| `POST` | `/knowledge-bases` | 创建新的知识库 |
| `GET` | `/knowledge-bases/{id}/articles` | 获取知识库下的文章 |
| `POST` | `/knowledge-bases/{id}/articles` | 在知识库中创建文章 |
| `POST` | `/documents/upload` | 上传并智能解析文档 |
| `GET` | `/documents/{id}/chunks` | 获取文档分块内容 |
| `POST` | `/knowledge/search` | 语义搜索知识内容 |
| `GET` | `/knowledge/similar/{article_id}` | 查找相似文章 |

</details>

<details>
<summary><b>💬 实时通信 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `WebSocket` | `/ws/chat/{room_id}` | 实时聊天WebSocket连接 |
| `GET` | `/chat-rooms` | 获取用户的聊天室列表 |
| `POST` | `/chat-rooms` | 创建新的聊天室 |
| `POST` | `/chat-rooms/{id}/join` | 申请加入聊天室 |
| `GET` | `/chat-rooms/{id}/messages` | 获取聊天历史消息 |
| `POST` | `/chat-rooms/{id}/upload` | 上传聊天文件 |
| `PUT` | `/chat-rooms/{id}/settings` | 更新聊天室设置 |

</details>

<details>
<summary><b>🎓 课程管理 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/courses` | 获取课程列表，支持分页和筛选 |
| `POST` | `/courses` | 创建新课程 |
| `GET` | `/courses/{id}` | 获取课程详细信息 |
| `POST` | `/courses/{id}/enroll` | 报名参加课程 |
| `GET` | `/courses/{id}/materials` | 获取课程学习资料 |
| `POST` | `/courses/{id}/materials` | 上传课程资料 |
| `POST` | `/courses/{id}/progress` | 更新学习进度 |
| `GET` | `/courses/{id}/students` | 获取课程学员列表 |

</details>

<details>
<summary><b>🚀 项目协作 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/projects` | 获取项目列表 |
| `POST` | `/projects` | 创建新项目 |
| `GET` | `/projects/{id}` | 获取项目详情 |
| `POST` | `/projects/{id}/apply` | 申请加入项目团队 |
| `GET` | `/projects/{id}/members` | 获取项目成员列表 |
| `POST` | `/projects/{id}/members` | 添加项目成员 |
| `POST` | `/projects/{id}/files` | 上传项目文件 |
| `GET` | `/projects/{id}/applications` | 管理项目申请 |

</details>

<details>
<summary><b>🌐 社区论坛 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/forum/topics` | 获取论坛话题列表 |
| `POST` | `/forum/topics` | 发布新话题 |
| `GET` | `/forum/topics/{id}` | 获取话题详细内容 |
| `POST` | `/forum/topics/{id}/comments` | 发表话题评论 |
| `POST` | `/forum/topics/{id}/like` | 点赞/取消点赞话题 |
| `GET` | `/forum/comments/{id}/replies` | 获取评论的回复列表 |
| `POST` | `/forum/comments/{id}/reply` | 回复评论 |

</details>

<details>
<summary><b>🤖 AI服务 API</b></summary>

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/ai/chat` | AI对话接口，支持多轮对话 |
| `GET` | `/ai/conversations` | 获取AI对话历史 |
| `POST` | `/ai/conversations/{id}/continue` | 继续指定对话 |
| `POST` | `/ai/tts` | 文本转语音服务 |
| `POST` | `/ai/search` | AI增强的智能搜索 |
| `GET` | `/ai/models` | 获取可用的AI模型列表 |
| `POST` | `/ai/embeddings` | 生成文本向量嵌入 |

</details>

### 🔧 API 使用示例

#### 认证流程
```bash
# 1. 用户登录
curl -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123"

# 2. 使用令牌访问受保护的API
curl -X GET "http://localhost:8000/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 智能匹配示例
```bash
# 获取相似学生推荐
curl -X GET "http://localhost:8000/match/students?limit=5" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 项目推荐
curl -X GET "http://localhost:8000/match/projects?skills=Python,AI&limit=10" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### 文件上传示例
```bash
# 上传文档到知识库
curl -X POST "http://localhost:8000/documents/upload" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@document.pdf" \
  -F "knowledge_base_id=1"
```

#### WebSocket 连接示例
```javascript
// 连接聊天室WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/chat/1?token=YOUR_ACCESS_TOKEN');

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    console.log('收到消息:', message);
};

ws.send(JSON.stringify({
    type: 'message',
    content: 'Hello, World!',
    room_id: 1
}));
```

## ⚙️ 配置说明

### 🔧 环境变量配置

<details>
<summary><b>📊 完整配置参数表</b></summary>

| 变量名 | 描述 | 必需 | 默认值 | 示例 |
|--------|------|------|--------|------|
| **数据库配置** | | | | |
| `DATABASE_URL` | PostgreSQL连接字符串 | ✅ | - | `postgresql://user:pass@localhost/db` |
| **安全配置** | | | | |
| `SECRET_KEY` | JWT签名密钥(至少32字符) | ✅ | - | `your-super-secret-32-char-key-here` |
| `ALGORITHM` | JWT算法 | ❌ | `HS256` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 令牌过期时间(分钟) | ❌ | `30` | `1440` |
| **AI服务配置** | | | | |
| `OPENAI_API_KEY` | OpenAI API密钥 | ❌ | - | `sk-...` |
| `OPENAI_API_BASE` | OpenAI API基础URL | ❌ | OpenAI官方 | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 默认OpenAI模型 | ❌ | `gpt-3.5-turbo` | `gpt-4` |
| **对象存储配置** | | | | |
| `S3_ACCESS_KEY_ID` | S3访问密钥ID | ❌ | - | `AKIAIOSFODNN7EXAMPLE` |
| `S3_SECRET_ACCESS_KEY` | S3密钥 | ❌ | - | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `S3_ENDPOINT_URL` | S3端点URL | ❌ | - | `https://s3.amazonaws.com` |
| `S3_BUCKET_NAME` | S3存储桶名称 | ❌ | - | `hongqing-files` |
| `S3_BASE_URL` | CDN基础URL | ❌ | - | `https://cdn.example.com` |
| **文件上传配置** | | | | |
| `UPLOAD_DIR` | 本地文件上传目录 | ❌ | `./uploaded_files` | `./project/uploads` |
| `TEMP_AUDIO_DIR` | 临时音频文件目录 | ❌ | `./temp_audio` | `./project/temp_audio` |
| `MAX_FILE_SIZE` | 最大文件大小(字节) | ❌ | `10485760` | `52428800` (50MB) |
| `ALLOWED_EXTENSIONS` | 允许的文件扩展名 | ❌ | 常见格式 | `.pdf,.docx,.xlsx,.pptx` |
| **应用配置** | | | | |
| `DEBUG` | 调试模式 | ❌ | `false` | `true` |
| `LOG_LEVEL` | 日志级别 | ❌ | `INFO` | `DEBUG` |
| `CORS_ORIGINS` | 跨域允许的源 | ❌ | `*` | `http://localhost:3000` |
| `ENABLE_DOCS` | 启用API文档 | ❌ | `true` | `false` |

</details>

### 🤖 AI模型配置详解

平台支持多种AI服务的灵活配置，用户可以根据需求选择不同的模型和服务提供商。

#### 🧠 大语言模型 (LLM)

<details>
<summary><b>OpenAI GPT系列</b></summary>

```env
# OpenAI官方API
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4  # 或 gpt-3.5-turbo, gpt-4-turbo

# 支持的模型列表
# - gpt-3.5-turbo: 快速、经济的选择
# - gpt-4: 更强的推理能力
# - gpt-4-turbo: 更长的上下文窗口
# - gpt-4o: 多模态支持
```

</details>

<details>
<summary><b>本地模型配置</b></summary>

```python
# 通过Transformers库加载本地模型
LOCAL_MODEL_PATH=/path/to/your/model
LOCAL_MODEL_TYPE=huggingface  # 或 onnx, tensorrt

# 支持的本地模型示例
# - microsoft/DialoGPT-medium
# - microsoft/DialoGPT-large
# - facebook/blenderbot-400M-distill
# - 中文模型: THUDM/chatglm-6b
```

</details>

#### 🔍 搜索引擎配置

<details>
<summary><b>支持的搜索引擎</b></summary>

```env
# Bing Search API
BING_SEARCH_API_KEY=your-bing-api-key
BING_SEARCH_ENDPOINT=https://api.cognitive.microsoft.com

# Google Custom Search
GOOGLE_API_KEY=your-google-api-key
GOOGLE_SEARCH_ENGINE_ID=your-search-engine-id

# Tavily AI Search
TAVILY_API_KEY=your-tavily-api-key

# DuckDuckGo (无需API密钥)
# 自动支持，无需配置
```

</details>

#### 🎙️ 文本转语音 (TTS)

<details>
<summary><b>TTS服务配置</b></summary>

```env
# Google TTS (gTTS)
# 无需API密钥，但需要网络连接

# Azure Cognitive Services
AZURE_SPEECH_KEY=your-azure-speech-key
AZURE_SPEECH_REGION=eastus

# Amazon Polly
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1

# 支持的语言和语音
# - 中文: zh-CN, zh-TW
# - 英文: en-US, en-GB
# - 多种其他语言
```

</details>

### 🔌 MCP协议支持

平台支持Model Context Protocol (MCP)标准，允许扩展AI模型的能力。

```python
# MCP配置示例
MCP_ENABLED=true
MCP_SERVERS_CONFIG={
    "file_server": {
        "command": "npx",
        "args": ["@modelcontextprotocol/server-filesystem", "/path/to/files"],
        "env": {}
    },
    "web_server": {
        "command": "npx",
        "args": ["@modelcontextprotocol/server-web"],
        "env": {}
    }
}
```

### 🛡️ 安全最佳实践

1. **密钥管理**:
   - 使用强随机密钥 (至少32字符)
   - 定期轮换API密钥
   - 不要在代码中硬编码密钥

2. **数据库安全**:
   - 使用专用数据库用户
   - 限制数据库权限
   - 启用SSL连接

3. **文件安全**:
   - 限制文件上传大小和类型
   - 扫描上传文件的恶意内容
   - 使用沙箱环境处理文件

4. **API安全**:
   - 启用CORS保护
   - 实施请求速率限制
   - 记录和监控API访问

## 🚀 生产部署

### 🐳 Docker 部署 (推荐)

Docker部署是最简单、最可靠的生产部署方式，提供了环境隔离和一致性保证。

#### 📋 创建 Dockerfile

```dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p project/uploaded_files project/temp_audio

# 设置权限
RUN chmod -R 755 project/

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["gunicorn", "project.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

#### 📝 创建 Docker Compose 文件

<details>
<summary><b>完整的 docker-compose.yml</b></summary>

```yaml
version: '3.8'

services:
  # 应用服务
  app:
    build: 
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://hongqing_user:${DB_PASSWORD}@db:5432/hongqing_platform
      - SECRET_KEY=${SECRET_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - S3_ACCESS_KEY_ID=${S3_ACCESS_KEY_ID}
      - S3_SECRET_ACCESS_KEY=${S3_SECRET_ACCESS_KEY}
      - DEBUG=false
      - LOG_LEVEL=INFO
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - uploaded_files:/app/project/uploaded_files
      - temp_audio:/app/project/temp_audio
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # 数据库服务
  db:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: hongqing_platform
      POSTGRES_USER: hongqing_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hongqing_user -d hongqing_platform"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis缓存 (可选)
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  # Nginx反向代理
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
      - static_files:/var/www/static
    depends_on:
      - app
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  uploaded_files:
  temp_audio:
  static_files:
```

</details>

#### 🔧 环境变量配置

创建 `.env.production` 文件：

```env
# 数据库密码
DB_PASSWORD=your_super_secure_database_password_here

# 应用密钥
SECRET_KEY=your-production-secret-key-32-chars-minimum

# AI服务
OPENAI_API_KEY=sk-your-production-openai-key

# 对象存储
S3_ACCESS_KEY_ID=your-production-s3-access-key
S3_SECRET_ACCESS_KEY=your-production-s3-secret-key
S3_BUCKET_NAME=hongqing-platform-prod
S3_ENDPOINT_URL=https://your-s3-endpoint.com

# 其他生产配置
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
```

#### 🚀 启动部署

```bash
# 1. 克隆代码到生产服务器
git clone https://github.com/w2902171175/Cosbrain.git
cd Cosbrain

# 2. 配置环境变量
cp .env.production .env

# 3. 构建并启动服务
docker-compose up -d --build

# 4. 检查服务状态
docker-compose ps
docker-compose logs app

# 5. 初始化数据库（首次部署）
docker-compose exec app python -c "from project.database import init_db; init_db()"

# 6. 验证部署
curl http://localhost:8000/health
```

### 🖥️ 传统服务器部署

适用于需要更精细控制的生产环境。

#### 1️⃣ 系统准备

```bash
# Ubuntu/Debian 服务器准备
sudo apt update && sudo apt upgrade -y

# 安装必要软件
sudo apt install -y python3.11 python3.11-venv python3-pip \
                    postgresql-15 postgresql-contrib \
                    nginx supervisor git curl

# 安装pgvector扩展
sudo apt install -y postgresql-15-pgvector
```

#### 2️⃣ 应用部署

```bash
# 1. 创建应用用户
sudo adduser --system --group hongqing
sudo mkdir -p /opt/hongqing
sudo chown hongqing:hongqing /opt/hongqing

# 2. 切换到应用用户
sudo -u hongqing -i

# 3. 部署代码
cd /opt/hongqing
git clone https://github.com/w2902171175/Cosbrain.git app
cd app

# 4. 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. 安装生产服务器
pip install gunicorn

# 6. 配置环境变量
cp .env.example .env.production
# 编辑 .env.production 文件

# 7. 初始化数据库
cd project
python -c "from database import init_db; init_db()"
```

#### 3️⃣ Gunicorn 配置

创建 `gunicorn_config.py`：

```python
# Gunicorn 生产配置
bind = "127.0.0.1:8000"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 60
keepalive = 2
preload_app = True

# 日志配置
accesslog = "/var/log/hongqing/access.log"
errorlog = "/var/log/hongqing/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程配置
user = "hongqing"
group = "hongqing"
tmp_upload_dir = "/tmp"

# 安全配置
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
```

#### 4️⃣ Supervisor 进程管理

创建 `/etc/supervisor/conf.d/hongqing.conf`：

```ini
[program:hongqing]
command=/opt/hongqing/app/venv/bin/gunicorn project.main:app -c gunicorn_config.py
directory=/opt/hongqing/app
user=hongqing
group=hongqing
autostart=true
autorestart=true
startsecs=10
startretries=3
redirect_stderr=true
stdout_logfile=/var/log/hongqing/app.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=5
environment=PATH="/opt/hongqing/app/venv/bin"
```

启动服务：

```bash
# 创建日志目录
sudo mkdir -p /var/log/hongqing
sudo chown hongqing:hongqing /var/log/hongqing

# 启动Supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start hongqing

# 检查状态
sudo supervisorctl status hongqing
```

#### 5️⃣ Nginx 反向代理

创建 `/etc/nginx/sites-available/hongqing`：

<details>
<summary><b>完整 Nginx 配置</b></summary>

```nginx
# upstream配置
upstream hongqing_app {
    server 127.0.0.1:8000 fail_timeout=0;
}

# HTTP to HTTPS重定向
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS主配置
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL证书配置
    ssl_certificate /path/to/your/cert.pem;
    ssl_certificate_key /path/to/your/private.key;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;

    # 现代SSL配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # 安全头
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # 日志配置
    access_log /var/log/nginx/hongqing_access.log;
    error_log /var/log/nginx/hongqing_error.log;

    # 客户端配置
    client_max_body_size 50M;
    client_body_timeout 60s;
    client_header_timeout 60s;

    # Gzip压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;

    # 静态文件
    location /static/ {
        alias /opt/hongqing/app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # 上传文件
    location /uploads/ {
        alias /opt/hongqing/app/project/uploaded_files/;
        expires 1M;
        add_header Cache-Control "public";
    }

    # WebSocket连接
    location /ws/ {
        proxy_pass http://hongqing_app;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # API接口
    location / {
        proxy_pass http://hongqing_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # 健康检查
    location /health {
        access_log off;
        proxy_pass http://hongqing_app;
    }
}
```

</details>

启用配置：

```bash
# 启用站点
sudo ln -s /etc/nginx/sites-available/hongqing /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载Nginx
sudo systemctl reload nginx
```

### 📊 生产监控

#### 🔍 日志监控

```bash
# 实时查看应用日志
sudo tail -f /var/log/hongqing/app.log

# 查看Nginx访问日志
sudo tail -f /var/log/nginx/hongqing_access.log

# 查看错误日志
sudo tail -f /var/log/hongqing/error.log
```

#### 📈 性能监控

使用Prometheus + Grafana进行监控：

```yaml
# prometheus.yml 配置片段
scrape_configs:
  - job_name: 'hongqing-platform'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

#### 🚨 健康检查

```bash
# 创建健康检查脚本
cat > /opt/hongqing/health_check.sh << 'EOF'
#!/bin/bash
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ $response -eq 200 ]; then
    echo "✅ Service is healthy"
    exit 0
else
    echo "❌ Service is unhealthy (HTTP $response)"
    exit 1
fi
EOF

chmod +x /opt/hongqing/health_check.sh

# 添加到crontab进行定期检查
echo "*/5 * * * * /opt/hongqing/health_check.sh" | sudo crontab -
```

## 🧪 开发与测试

### � 测试框架

平台采用pytest作为主要测试框架，提供完整的单元测试、集成测试和端到端测试支持。

#### 📝 安装测试依赖

```bash
# 安装测试相关包
pip install pytest pytest-asyncio pytest-cov pytest-mock httpx

# 安装代码质量工具
pip install black isort mypy flake8
```

#### 🧪 运行测试

```bash
# 运行所有测试
pytest

# 运行特定模块测试
pytest tests/test_auth.py
pytest tests/test_ai_core.py

# 生成覆盖率报告
pytest --cov=project tests/ --cov-report=html

# 并行运行测试（更快）
pytest -n auto

# 详细输出模式
pytest -v -s
```

#### 📊 测试覆盖率

```bash
# 生成详细覆盖率报告
pytest --cov=project --cov-report=html --cov-report=term-missing

# 查看覆盖率报告
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

### 🛠️ 开发工具配置

#### 🎨 代码格式化

<details>
<summary><b>Black 配置 (pyproject.toml)</b></summary>

```toml
[tool.black]
line-length = 100
target-version = ['py38', 'py39', 'py310', 'py311']
include = '\.pyi?$'
extend-exclude = '''
/(
    \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | _build
  | buck-out
  | build
  | dist
  | migrations
)/
'''
```

</details>

<details>
<summary><b>isort 配置</b></summary>

```toml
[tool.isort]
profile = "black"
multi_line_output = 3
line_length = 100
known_first_party = ["project", "models", "schemas", "database"]
known_third_party = ["fastapi", "sqlalchemy", "pydantic", "numpy"]
```

</details>

<details>
<summary><b>mypy 配置</b></summary>

```toml
[tool.mypy]
python_version = "3.8"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true

[[tool.mypy.overrides]]
module = [
    "pgvector.*",
    "sentence_transformers.*",
    "transformers.*"
]
ignore_missing_imports = true
```

</details>

#### 🔧 开发脚本

创建 `scripts/dev.py` 开发助手脚本：

```python
#!/usr/bin/env python3
"""开发助手脚本"""
import subprocess
import sys
from pathlib import Path

def format_code():
    """格式化代码"""
    print("🎨 格式化代码...")
    subprocess.run(["black", "project/"], check=True)
    subprocess.run(["isort", "project/"], check=True)
    print("✅ 代码格式化完成")

def lint_code():
    """代码检查"""
    print("🔍 进行代码检查...")
    subprocess.run(["flake8", "project/"], check=True)
    subprocess.run(["mypy", "project/"], check=True)
    print("✅ 代码检查通过")

def run_tests():
    """运行测试"""
    print("🧪 运行测试...")
    subprocess.run([
        "pytest", 
        "--cov=project", 
        "--cov-report=term-missing",
        "-v"
    ], check=True)
    print("✅ 测试完成")

def start_dev_server():
    """启动开发服务器"""
    print("🚀 启动开发服务器...")
    subprocess.run([
        "python", "-m", "uvicorn", 
        "project.main:app", 
        "--reload", 
        "--host", "0.0.0.0", 
        "--port", "8000",
        "--log-level", "debug"
    ])

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    commands = {
        "format": format_code,
        "lint": lint_code,
        "test": run_tests,
        "serve": start_dev_server,
    }
    
    if command in commands:
        commands[command]()
    else:
        print("可用命令: format, lint, test, serve")
```

### 🔄 数据库迁移

#### Alembic 迁移管理

```bash
# 生成新的迁移文件
alembic revision --autogenerate -m "Add new feature"

# 应用迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1

# 查看迁移历史
alembic history

# 查看当前版本
alembic current
```

#### 自定义迁移脚本

```python
# migrations/add_vector_indexes.py
"""添加向量索引优化"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    # 为向量字段创建HNSW索引
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw 
        ON knowledge_document_chunks 
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    
    # 为文本搜索创建GIN索引
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_knowledge_chunks_content_gin 
        ON knowledge_document_chunks 
        USING gin (to_tsvector('english', content));
    """)

def downgrade():
    op.drop_index('idx_knowledge_chunks_embedding_hnsw')
    op.drop_index('idx_knowledge_chunks_content_gin')
```

### 🐛 调试工具

#### 日志配置

```python
# project/logging_config.py
import logging
import sys
from pathlib import Path

def setup_logging(level: str = "INFO"):
    """设置日志配置"""
    
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 配置格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # 文件处理器
    file_handler = logging.FileHandler(log_dir / "app.log")
    file_handler.setFormatter(formatter)
    
    # 错误文件处理器
    error_handler = logging.FileHandler(log_dir / "error.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # 根日志器配置
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
```

#### 性能分析

```python
# 使用装饰器进行性能分析
import time
import functools
import logging

def timer(func):
    """计时装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logging.info(f"{func.__name__} 执行时间: {end - start:.4f}秒")
        return result
    return wrapper

# 在API端点中使用
@app.get("/api/example")
@timer
async def example_endpoint():
    # 业务逻辑
    pass
```

### 📋 Git 工作流

#### 提交前检查脚本

```bash
#!/bin/bash
# scripts/pre-commit.sh

echo "🔍 运行提交前检查..."

# 代码格式化
echo "📝 格式化代码..."
black project/
isort project/

# 代码检查
echo "🔍 代码检查..."
flake8 project/ || exit 1
mypy project/ || exit 1

# 运行测试
echo "🧪 运行测试..."
pytest --cov=project tests/ || exit 1

echo "✅ 所有检查通过，可以提交代码"
```

#### Git Hooks 设置

```bash
# 设置 pre-commit hook
cp scripts/pre-commit.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### 🔧 IDE 配置

#### VS Code 配置

<details>
<summary><b>.vscode/settings.json</b></summary>

```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    }
}
```

</details>

#### PyCharm 配置

1. **解释器设置**: 选择项目虚拟环境
2. **代码风格**: 配置Black格式化器
3. **运行配置**: 创建FastAPI运行配置
4. **数据库工具**: 连接PostgreSQL数据库

## 🐛 故障排除

### 🔍 常见问题诊断

#### 🗄️ 数据库相关问题

<details>
<summary><b>❌ 数据库连接失败</b></summary>

**问题症状:**
- `connection to server at "localhost" (127.0.0.1), port 5432 failed`
- `FATAL: database "hongqing_platform" does not exist`

**解决方案:**
```bash
# 1. 检查PostgreSQL服务状态
sudo systemctl status postgresql
sudo systemctl start postgresql  # 如果未启动

# 2. 验证数据库和用户
sudo -u postgres psql
\l  # 列出所有数据库
\du  # 列出所有用户

# 3. 创建数据库和用户（如果不存在）
CREATE DATABASE hongqing_platform;
CREATE USER hongqing_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE hongqing_platform TO hongqing_user;

# 4. 验证pgvector扩展
\c hongqing_platform;
CREATE EXTENSION IF NOT EXISTS vector;
SELECT * FROM pg_extension WHERE extname = 'vector';
```

</details>

<details>
<summary><b>❌ pgvector扩展问题</b></summary>

**问题症状:**
- `extension "vector" does not exist`
- `could not access file "$libdir/vector"`

**解决方案:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql-15-pgvector

# CentOS/RHEL
sudo yum install pgvector

# 从源码编译安装
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

</details>

#### 📦 依赖安装问题

<details>
<summary><b>❌ Python包安装失败</b></summary>

**问题症状:**
- `ERROR: Failed building wheel for XXX`
- `Microsoft Visual C++ 14.0 is required` (Windows)

**解决方案:**
```bash
# 1. 升级pip和setuptools
pip install --upgrade pip setuptools wheel

# 2. 清理缓存
pip cache purge

# 3. 使用预编译包
pip install --only-binary=all -r requirements.txt

# 4. Windows特定问题
# 安装Microsoft C++ Build Tools
# 或安装Visual Studio Community

# 5. macOS特定问题
xcode-select --install  # 安装Xcode命令行工具
```

</details>

<details>
<summary><b>❌ PyTorch安装问题</b></summary>

**问题症状:**
- PyTorch安装缓慢或失败
- CUDA版本不匹配

**解决方案:**
```bash
# CPU版本（推荐用于开发）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# GPU版本（需要CUDA）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 验证安装
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

</details>

#### 📁 文件操作问题

<details>
<summary><b>❌ 文件上传失败</b></summary>

**问题症状:**
- `Permission denied`
- `No such file or directory`
- `File size exceeds limit`

**解决方案:**
```bash
# 1. 创建必要目录
mkdir -p project/uploaded_files project/temp_audio

# 2. 设置正确权限
chmod 755 project/uploaded_files project/temp_audio
chown $(whoami):$(whoami) project/uploaded_files project/temp_audio

# 3. 检查磁盘空间
df -h .

# 4. 调整文件大小限制
# 在.env中设置
MAX_FILE_SIZE=52428800  # 50MB

# 5. 检查Nginx配置（如果使用）
# client_max_body_size 50M;
```

</details>

#### 🤖 AI功能问题

<details>
<summary><b>❌ OpenAI API调用失败</b></summary>

**问题症状:**
- `Invalid API key`
- `Rate limit exceeded`
- `Connection timeout`

**解决方案:**
```bash
# 1. 验证API密钥
export OPENAI_API_KEY="sk-your-api-key"
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     https://api.openai.com/v1/models

# 2. 检查网络连接
ping api.openai.com
nslookup api.openai.com

# 3. 配置代理（如果需要）
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080

# 4. 使用API代理服务
OPENAI_API_BASE=https://your-proxy-service.com/v1
```

</details>

<details>
<summary><b>❌ 向量搜索性能问题</b></summary>

**问题症状:**
- 搜索速度慢
- 内存占用高

**解决方案:**
```sql
-- 1. 创建向量索引
CREATE INDEX CONCURRENTLY idx_embeddings_hnsw 
ON knowledge_document_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 2. 调整PostgreSQL配置
-- shared_buffers = 1GB
-- effective_cache_size = 3GB
-- random_page_cost = 1.1

-- 3. 优化查询
-- 使用适当的ef_search参数
SET hnsw.ef_search = 100;
```

</details>

### 🔧 调试工具

#### 📊 性能监控

```python
# 添加到main.py中
import time
from fastapi import Request
import logging

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} "
        f"took {process_time:.4f}s "
        f"status={response.status_code}"
    )
    return response
```

#### 🔍 日志调试

<details>
<summary><b>启用详细日志</b></summary>

```bash
# 1. 环境变量配置
export LOG_LEVEL=DEBUG
export PYTHONPATH=$PWD/project

# 2. 启动时启用详细日志
python -m uvicorn project.main:app \
    --reload \
    --log-level debug \
    --access-log

# 3. 查看实时日志
tail -f logs/app.log
tail -f logs/error.log

# 4. 过滤特定模块日志
export PYTHONASYNCIODEBUG=1  # 异步调试
```

</details>

#### 🩺 健康检查

创建健康检查端点 `/health`：

```python
@app.get("/health")
async def health_check():
    """系统健康检查"""
    try:
        # 检查数据库连接
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # 检查AI服务
    ai_status = "healthy" if ai_core.check_models() else "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" and ai_status == "healthy" else "unhealthy",
        "database": db_status,
        "ai_services": ai_status,
        "timestamp": datetime.utcnow().isoformat()
    }
```

### 🔧 开发环境重置

如果遇到严重问题，可以重置开发环境：

```bash
#!/bin/bash
# scripts/reset_dev_env.sh

echo "🔄 重置开发环境..."

# 1. 停止所有服务
pkill -f uvicorn
pkill -f gunicorn

# 2. 清理Python缓存
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name "*.pyc" -delete

# 3. 重建虚拟环境
deactivate || true
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate

# 4. 重新安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 5. 重置数据库
cd project
python -c "
from database import engine, init_db
from sqlalchemy import text
with engine.begin() as conn:
    conn.execute(text('DROP SCHEMA public CASCADE'))
    conn.execute(text('CREATE SCHEMA public'))
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
init_db()
print('✅ 数据库重置完成')
"

# 6. 清理上传文件
rm -rf project/uploaded_files/*
rm -rf project/temp_audio/*

echo "✅ 开发环境重置完成"
```

### 📞 获取帮助

如果问题仍无法解决：

1. **检查日志**: 查看详细的错误日志信息
2. **搜索Issues**: 在GitHub Issues中搜索类似问题
3. **提交Issue**: 提供详细的错误信息和环境配置
4. **社区讨论**: 在GitHub Discussions中寻求帮助
5. **联系开发者**: 发送邮件至 wxh1331@foxmail.com

## 🤝 贡献指南

我们热烈欢迎社区的贡献！无论是报告bug、提出新功能建议、改进文档还是提交代码，每一份贡献都让这个项目变得更好。

### 🌟 贡献方式

<table>
<tr>
<td width="50%">

**🐛 问题报告**
- 发现bug并提交issue
- 提供详细的复现步骤
- 包含环境信息和错误日志

**💡 功能建议**
- 提出新功能想法
- 描述使用场景和预期效果
- 参与功能设计讨论

</td>
<td width="50%">

**📝 文档改进**
- 修正文档错误
- 添加使用示例
- 翻译文档到其他语言

**💻 代码贡献**
- 修复bug和实现新功能
- 性能优化和重构
- 测试用例编写

</td>
</tr>
</table>

### 🔄 开发流程

#### 1️⃣ 准备开发环境

```bash
# 1. Fork项目到您的GitHub账户
# 在GitHub上点击Fork按钮

# 2. 克隆您的Fork
git clone https://github.com/YOUR_USERNAME/Cosbrain.git
cd Cosbrain

# 3. 添加上游仓库
git remote add upstream https://github.com/w2902171175/Cosbrain.git

# 4. 设置开发环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2️⃣ 创建功能分支

```bash
# 1. 同步最新代码
git fetch upstream
git checkout main
git merge upstream/main

# 2. 创建功能分支
git checkout -b feature/your-awesome-feature
# 或修复bug分支
git checkout -b fix/issue-123

# 3. 开始开发
# ... 进行您的修改 ...
```

#### 3️⃣ 代码开发规范

<details>
<summary><b>🎨 代码风格规范</b></summary>

**Python代码规范:**
- 遵循 **PEP 8** 标准
- 使用 **Black** 进行代码格式化
- 使用 **isort** 组织导入语句
- 行长度限制为 **100** 字符

```bash
# 格式化代码
black project/
isort project/

# 检查代码风格
flake8 project/
mypy project/
```

**命名规范:**
- 变量和函数: `snake_case`
- 类名: `PascalCase`
- 常量: `UPPER_SNAKE_CASE`
- 私有变量: `_leading_underscore`

</details>

<details>
<summary><b>📝 注释和文档</b></summary>

**函数文档字符串:**
```python
def match_students_by_skills(
    skills: List[str], 
    limit: int = 10,
    similarity_threshold: float = 0.7
) -> List[StudentMatch]:
    """
    根据技能匹配相似学生
    
    Args:
        skills: 技能关键词列表
        limit: 返回结果数量限制
        similarity_threshold: 相似度阈值 (0-1)
    
    Returns:
        StudentMatch对象列表，按相似度降序排列
        
    Raises:
        ValueError: 当技能列表为空时抛出
        
    Example:
        >>> matches = match_students_by_skills(["Python", "AI"], limit=5)
        >>> print(len(matches))
        5
    """
```

**API端点文档:**
```python
@app.post("/api/projects", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate,
    current_user: Student = Depends(get_current_user)
):
    """
    创建新项目
    
    - **name**: 项目名称 (必需)
    - **description**: 项目描述
    - **skills**: 所需技能列表
    - **max_members**: 最大成员数量
    
    返回创建的项目详细信息
    """
```

</details>

<details>
<summary><b>🧪 测试规范</b></summary>

**测试文件组织:**
```
tests/
├── test_auth.py          # 认证模块测试
├── test_ai_core.py       # AI功能测试
├── test_matching.py      # 匹配算法测试
├── test_api/             # API测试
│   ├── test_projects.py
│   ├── test_courses.py
│   └── test_chat.py
└── conftest.py           # 测试配置和fixtures
```

**测试编写示例:**
```python
import pytest
from fastapi.testclient import TestClient
from project.main import app

client = TestClient(app)

def test_create_project():
    """测试项目创建功能"""
    project_data = {
        "name": "测试项目",
        "description": "这是一个测试项目",
        "skills": ["Python", "FastAPI"]
    }
    
    response = client.post("/api/projects", json=project_data)
    
    assert response.status_code == 201
    assert response.json()["name"] == "测试项目"
    assert "id" in response.json()

@pytest.mark.asyncio
async def test_ai_matching():
    """测试AI匹配功能"""
    from project.ai_core import match_students_by_vector
    
    # 准备测试数据
    query_vector = [0.1, 0.2, 0.3]  # 示例向量
    
    # 执行匹配
    results = await match_students_by_vector(query_vector, limit=5)
    
    # 验证结果
    assert isinstance(results, list)
    assert len(results) <= 5
    assert all(hasattr(r, 'similarity') for r in results)
```

</details>

#### 4️⃣ 提交代码

<details>
<summary><b>📝 提交信息规范</b></summary>

**提交格式:**
```
<类型>(<范围>): <简短描述>

<详细描述>

<相关Issue>
```

**类型标识:**
- `feat`: 新功能
- `fix`: bug修复
- `docs`: 文档更新
- `style`: 代码格式化
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建、工具等

**示例:**
```bash
# 好的提交信息
git commit -m "feat(matching): 添加基于技能的学生匹配算法

- 实现向量相似度计算
- 添加匹配结果缓存机制
- 支持自定义相似度阈值

Closes #123"

# 不好的提交信息
git commit -m "修复bug"  # 太简略
git commit -m "update code"  # 不清楚
```

</details>

```bash
# 1. 运行测试确保代码质量
pytest --cov=project tests/
black project/
isort project/
flake8 project/
mypy project/

# 2. 提交代码
git add .
git commit -m "feat(matching): 添加基于技能的学生匹配算法"

# 3. 推送到您的Fork
git push origin feature/your-awesome-feature
```

#### 5️⃣ 创建Pull Request

1. **访问GitHub页面**，点击 "Compare & pull request"

2. **填写PR信息**:
   ```markdown
   ## 📝 变更概述
   简要描述此PR的目的和实现的功能
   
   ## 🔄 变更详情
   - [ ] 添加新功能X
   - [ ] 修复问题Y
   - [ ] 优化性能Z
   
   ## 🧪 测试情况
   - [ ] 单元测试通过
   - [ ] 集成测试通过
   - [ ] 手动测试验证
   
   ## 📸 截图/演示
   （如果适用，添加截图或GIF演示）
   
   ## 🔗 相关Issue
   Closes #123
   Related to #456
   ```

3. **请求代码审查**，等待维护者反馈

### 🔍 代码审查

#### 审查清单

**功能性:**
- [ ] 功能是否按预期工作
- [ ] 是否处理了边界情况
- [ ] 错误处理是否完善

**代码质量:**
- [ ] 代码风格符合规范
- [ ] 变量命名清晰易懂
- [ ] 函数职责单一明确

**性能:**
- [ ] 是否存在性能问题
- [ ] 数据库查询是否优化
- [ ] 内存使用是否合理

**安全性:**
- [ ] 是否存在安全漏洞
- [ ] 输入验证是否充分
- [ ] 权限检查是否正确

### 🏆 贡献者认可

我们将在以下方式认可贡献者：

- **Contributors 列表**: 在README中展示
- **Release Notes**: 在版本发布中提及
- **特殊徽章**: 为活跃贡献者提供特殊标识
- **社区感谢**: 在社区中公开感谢

### 📋 贡献者协议

通过提交代码，您同意：
1. 您拥有提交代码的合法权利
2. 您的贡献将按照项目许可证发布
3. 您同意项目维护者对代码进行必要修改

### 🎯 特殊贡献机会

#### 🌟 优先级高的贡献

- **性能优化**: 数据库查询优化、算法改进
- **AI功能增强**: 新的模型集成、算法优化
- **国际化**: 多语言支持和本地化
- **移动端适配**: 响应式设计改进
- **文档完善**: API文档、使用指南

#### 🎨 设计贡献

- **UI/UX设计**: 界面设计稿和用户体验改进
- **Logo设计**: 项目标识和品牌设计
- **动画效果**: 交互动画和视觉效果

#### 📚 文档贡献

- **教程编写**: 入门指南、高级教程
- **API文档**: 接口说明和示例代码
- **最佳实践**: 使用技巧和经验分享

### ❓ 获取帮助

如果您在贡献过程中遇到问题：

1. **查看文档**: 先查阅现有文档和FAQ
2. **搜索Issues**: 查找是否有类似问题
3. **提问讨论**: 在GitHub Discussions中提问
4. **联系维护者**: 发送邮件至 wxh1331@foxmail.com

---

**再次感谢您的贡献！** 🙏 每一份贡献都让这个项目变得更好，也让整个社区受益。

## � 性能与扩展

### ⚡ 性能优化策略

#### 🗄️ 数据库层优化

<details>
<summary><b>索引优化策略</b></summary>

```sql
-- 向量搜索优化
CREATE INDEX CONCURRENTLY idx_knowledge_chunks_embedding_hnsw 
ON knowledge_document_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 文本搜索优化  
CREATE INDEX CONCURRENTLY idx_content_gin 
ON knowledge_document_chunks 
USING gin (to_tsvector('english', content));

-- 复合索引优化
CREATE INDEX CONCURRENTLY idx_projects_skills_status 
ON projects (skills, status, created_at DESC);

-- 外键关联优化
CREATE INDEX CONCURRENTLY idx_chat_messages_room_time 
ON chat_messages (room_id, created_at DESC);
```

</details>

<details>
<summary><b>查询优化</b></summary>

```python
# 使用查询预热和批量操作
async def get_user_projects_optimized(user_id: int, db: Session):
    """优化的用户项目查询"""
    return db.query(Project)\
        .options(
            selectinload(Project.members),  # 预加载关联数据
            selectinload(Project.applications)
        )\
        .filter(Project.creator_id == user_id)\
        .order_by(Project.updated_at.desc())\
        .limit(20)\
        .all()

# 使用原生SQL进行复杂查询
async def get_popular_courses():
    """获取热门课程的优化查询"""
    query = """
    SELECT c.*, COUNT(uc.user_id) as enrollment_count
    FROM courses c
    LEFT JOIN user_courses uc ON c.id = uc.course_id
    WHERE c.status = 'published'
    GROUP BY c.id
    ORDER BY enrollment_count DESC, c.created_at DESC
    LIMIT 10
    """
    return db.execute(text(query)).fetchall()
```

</details>

<details>
<summary><b>连接池配置</b></summary>

```python
# database.py 优化配置
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,          # 连接池大小
    max_overflow=30,       # 最大溢出连接数
    pool_timeout=30,       # 获取连接超时时间
    pool_recycle=3600,     # 连接回收时间(秒)
    pool_pre_ping=True,    # 连接前检查
    echo=False,            # 生产环境关闭SQL日志
    future=True
)
```

</details>

#### 🚀 应用层优化

<details>
<summary><b>异步处理优化</b></summary>

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# 异步文件处理
async def process_document_async(file_path: str):
    """异步文档处理"""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        # CPU密集型任务放到线程池
        content = await loop.run_in_executor(
            executor, extract_document_content, file_path
        )
        # 向量化也是CPU密集型
        embeddings = await loop.run_in_executor(
            executor, generate_embeddings, content
        )
    return content, embeddings

# 批量异步操作
async def process_multiple_documents(file_paths: List[str]):
    """批量处理文档"""
    tasks = [process_document_async(path) for path in file_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

</details>

<details>
<summary><b>缓存策略</b></summary>

```python
import redis
from functools import wraps
import json
import pickle

# Redis配置
redis_client = redis.Redis(
    host='localhost', 
    port=6379, 
    db=0,
    decode_responses=True,
    socket_keepalive=True,
    socket_keepalive_options={}
)

# 缓存装饰器
def cache_result(expire_time: int = 3600):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # 尝试从缓存获取
            cached = redis_client.get(cache_key)
            if cached:
                return pickle.loads(cached)
            
            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            redis_client.setex(
                cache_key, 
                expire_time, 
                pickle.dumps(result)
            )
            return result
        return wrapper
    return decorator

# 使用示例
@cache_result(expire_time=1800)  # 缓存30分钟
async def get_popular_courses():
    """获取热门课程(带缓存)"""
    # 业务逻辑...
    pass
```

</details>

<details>
<summary><b>API响应优化</b></summary>

```python
from fastapi import BackgroundTasks
from fastapi.responses import StreamingResponse
import orjson  # 更快的JSON序列化

# 使用更快的JSON响应
class ORJSONResponse(Response):
    media_type = "application/json"
    
    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)

app = FastAPI(default_response_class=ORJSONResponse)

# 后台任务处理
@app.post("/documents/upload")
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks
):
    # 立即响应用户
    file_id = save_file_metadata(file)
    
    # 后台处理文档解析
    background_tasks.add_task(
        process_document_background, 
        file_id, 
        file.filename
    )
    
    return {"file_id": file_id, "status": "processing"}

# 流式响应
@app.get("/api/export/data")
async def export_large_dataset():
    """大数据集流式导出"""
    def generate_data():
        for chunk in get_data_chunks():
            yield orjson.dumps(chunk) + b'\n'
    
    return StreamingResponse(
        generate_data(),
        media_type="application/json"
    )
```

</details>

### 📈 扩展架构

#### 🏗️ 微服务化架构

<details>
<summary><b>服务拆分策略</b></summary>

```yaml
# docker-compose.microservices.yml
version: '3.8'
services:
  # 用户认证服务
  auth-service:
    build: ./services/auth
    ports: ["8001:8000"]
    environment:
      - DATABASE_URL=postgresql://auth_db
      
  # 知识管理服务  
  knowledge-service:
    build: ./services/knowledge
    ports: ["8002:8000"]
    depends_on: [vector-db, redis]
    
  # AI服务
  ai-service:
    build: ./services/ai
    ports: ["8003:8000"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
              
  # 聊天服务
  chat-service:
    build: ./services/chat
    ports: ["8004:8000"]
    depends_on: [redis, message-queue]
    
  # API网关
  api-gateway:
    image: nginx:alpine
    ports: ["80:80"]
    volumes:
      - ./nginx/gateway.conf:/etc/nginx/nginx.conf
    depends_on:
      - auth-service
      - knowledge-service
      - ai-service
      - chat-service
```

</details>

<details>
<summary><b>API网关配置</b></summary>

```nginx
# nginx/gateway.conf
upstream auth_service {
    server auth-service:8000;
}

upstream knowledge_service {
    server knowledge-service:8000;
}

upstream ai_service {
    server ai-service:8000;
}

upstream chat_service {
    server chat-service:8000;
}

server {
    listen 80;
    
    # 认证服务
    location /api/auth/ {
        proxy_pass http://auth_service/;
    }
    
    # 知识管理服务
    location /api/knowledge/ {
        proxy_pass http://knowledge_service/;
    }
    
    # AI服务
    location /api/ai/ {
        proxy_pass http://ai_service/;
    }
    
    # 聊天服务
    location /api/chat/ {
        proxy_pass http://chat_service/;
    }
    
    # WebSocket代理
    location /ws/ {
        proxy_pass http://chat_service;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

</details>

#### ⚖️ 负载均衡与高可用

<details>
<summary><b>Nginx负载均衡</b></summary>

```nginx
# 应用服务器集群
upstream app_servers {
    least_conn;  # 最少连接算法
    server app1.hongqing.com:8000 weight=3 max_fails=2 fail_timeout=30s;
    server app2.hongqing.com:8000 weight=3 max_fails=2 fail_timeout=30s;
    server app3.hongqing.com:8000 weight=2 max_fails=2 fail_timeout=30s;
    keepalive 32;
}

# 数据库读写分离
upstream db_read_servers {
    server db-read1.hongqing.com:5432;
    server db-read2.hongqing.com:5432;
    server db-read3.hongqing.com:5432;
}

# AI服务负载均衡
upstream ai_servers {
    server ai1.hongqing.com:8000 weight=1;
    server ai2.hongqing.com:8000 weight=1;
    server ai3.hongqing.com:8000 weight=2;  # GPU服务器权重更高
}
```

</details>

<details>
<summary><b>数据库集群</b></summary>

```yaml
# PostgreSQL主从复制配置
version: '3.8'
services:
  # 主数据库
  postgres-master:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_REPLICATION_USER: replica
      POSTGRES_REPLICATION_PASSWORD: replica_password
    volumes:
      - master_data:/var/lib/postgresql/data
      - ./postgresql.conf:/etc/postgresql/postgresql.conf
    command: >
      postgres -c config_file=/etc/postgresql/postgresql.conf
      
  # 从数据库1
  postgres-slave1:
    image: pgvector/pgvector:pg15
    environment:
      PGUSER: postgres
      POSTGRES_MASTER_SERVICE: postgres-master
      POSTGRES_REPLICATION_USER: replica
      POSTGRES_REPLICATION_PASSWORD: replica_password
    volumes:
      - slave1_data:/var/lib/postgresql/data
    depends_on:
      - postgres-master
      
  # 从数据库2  
  postgres-slave2:
    image: pgvector/pgvector:pg15
    environment:
      PGUSER: postgres
      POSTGRES_MASTER_SERVICE: postgres-master
      POSTGRES_REPLICATION_USER: replica
      POSTGRES_REPLICATION_PASSWORD: replica_password
    volumes:
      - slave2_data:/var/lib/postgresql/data
    depends_on:
      - postgres-master
```

</details>

#### 📊 监控与告警

<details>
<summary><b>Prometheus监控配置</b></summary>

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

scrape_configs:
  # 应用监控
  - job_name: 'hongqing-app'
    static_configs:
      - targets: ['app1:8000', 'app2:8000', 'app3:8000']
    metrics_path: '/metrics'
    
  # 数据库监控
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
      
  # Redis监控
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
      
  # 系统监控
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

</details>

<details>
<summary><b>Grafana仪表板</b></summary>

```json
{
  "dashboard": {
    "title": "鸿庆书云平台监控",
    "panels": [
      {
        "title": "API请求量",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "响应时间",
        "type": "graph", 
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "title": "数据库连接数",
        "type": "stat",
        "targets": [
          {
            "expr": "pg_stat_activity_count",
            "legendFormat": "活跃连接"
          }
        ]
      }
    ]
  }
}
```

</details>

### 🚀 性能基准测试

#### 📊 压力测试

```bash
# 使用wrk进行API压力测试
wrk -t12 -c400 -d30s --latency http://localhost:8000/api/health

# 使用locust进行业务场景测试
pip install locust

# locustfile.py
from locust import HttpUser, task, between

class PlatformUser(HttpUser):
    wait_time = between(1, 5)
    
    def on_start(self):
        # 用户登录
        response = self.client.post("/token", data={
            "username": "test@example.com",
            "password": "test123"
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(3)
    def search_knowledge(self):
        self.client.post("/knowledge/search", 
                        json={"query": "Python教程"},
                        headers=self.headers)
    
    @task(2) 
    def get_projects(self):
        self.client.get("/projects", headers=self.headers)
    
    @task(1)
    def ai_chat(self):
        self.client.post("/ai/chat",
                        json={"message": "你好，请介绍一下Python"},
                        headers=self.headers)

# 运行测试
locust -f locustfile.py --host=http://localhost:8000
```

#### 📈 性能基准

| 指标 | 目标值 | 当前值 | 优化建议 |
|------|--------|--------|----------|
| **API响应时间** | < 200ms | 150ms | ✅ 达标 |
| **并发用户数** | 1000+ | 800 | 需要优化 |
| **数据库查询** | < 50ms | 30ms | ✅ 达标 |
| **AI推理时间** | < 2s | 1.5s | ✅ 达标 |
| **内存使用率** | < 80% | 65% | ✅ 达标 |
| **CPU使用率** | < 70% | 45% | ✅ 达标 |

### 🔮 未来扩展计划

1. **容器化部署**: 完整的Kubernetes部署方案
2. **边缘计算**: AI模型边缘部署，降低延迟
3. **实时数据**: WebRTC支持，实现实时音视频通话
4. **智能推荐**: 基于用户行为的深度学习推荐系统
5. **多云部署**: 支持AWS、Azure、阿里云等多云环境

## � 许可证

本项目采用自定义开源许可证，支持个人和教育用途，详情请查看 [LICENSE](LICENSE) 文件。

### 📜 许可证摘要

- ✅ **免费使用**: 个人、教育机构和非营利组织可免费使用
- ✅ **开源透明**: 源代码完全开放，支持学习和研究
- ✅ **修改权限**: 允许修改和定制以满足特定需求
- ✅ **分发权限**: 可以分发原始或修改版本（需保持开源）
- ❌ **商业限制**: 禁止直接商业销售或集成到商业产品
- ❌ **闭源禁止**: 任何衍生作品必须保持开源

### 🤝 商业合作

如需商业使用或定制开发服务，请联系：
- 📧 **邮箱**: wxh1331@foxmail.com
- 💼 **商务合作**: 提供企业级部署、定制开发、技术支持等服务

## 📞 联系我们

<div align="center">

### 🌐 项目链接

[![GitHub](https://img.shields.io/badge/GitHub-Cosbrain-181717?style=for-the-badge&logo=github)](https://github.com/w2902171175/Cosbrain)
[![Issues](https://img.shields.io/badge/Issues-问题反馈-red?style=for-the-badge&logo=github)](https://github.com/w2902171175/Cosbrain/issues)
[![Discussions](https://img.shields.io/badge/Discussions-讨论交流-blue?style=for-the-badge&logo=github)](https://github.com/w2902171175/Cosbrain/discussions)

### 📬 联系方式

| 联系方式 | 地址/账号 | 用途 |
|----------|-----------|------|
| 📧 **邮箱** | wxh1331@foxmail.com | 技术支持、商务合作、问题反馈 |
| 🐛 **Bug报告** | [GitHub Issues](https://github.com/w2902171175/Cosbrain/issues) | 提交bug、功能请求 |
| 💬 **社区讨论** | [GitHub Discussions](https://github.com/w2902171175/Cosbrain/discussions) | 技术交流、使用问题 |
| 📚 **文档问题** | [文档Issues](https://github.com/w2902171175/Cosbrain/issues?q=label%3Adocumentation) | 文档改进建议 |

</div>

### 🤝 社区支持

- **🔍 问题反馈**: 发现bug或有改进建议，请在GitHub Issues中提交
- **💡 功能建议**: 有新的功能想法，欢迎在Discussions中分享
- **🤝 技术交流**: 加入我们的技术讨论，分享使用经验
- **📖 文档贡献**: 帮助改进文档，让更多人能够轻松使用平台

### 📋 常见问题

<details>
<summary><b>❓ 如何快速开始使用？</b></summary>

1. 查看[快速开始](#-快速开始)部分
2. 确保满足环境要求
3. 按步骤安装部署
4. 访问API文档进行测试

</details>

<details>
<summary><b>❓ 部署遇到问题怎么办？</b></summary>

1. 首先查看[故障排除](#-故障排除)部分
2. 检查日志文件定位具体错误
3. 在GitHub Issues中搜索类似问题
4. 如果仍无法解决，请提交新的Issue

</details>

<details>
<summary><b>❓ 如何贡献代码？</b></summary>

1. 阅读[贡献指南](#-贡献指南)
2. Fork项目到您的GitHub
3. 创建功能分支进行开发
4. 提交Pull Request

</details>

<details>
<summary><b>❓ 商业使用如何授权？</b></summary>

- 当前许可证禁止直接商业使用
- 如需商业授权，请发邮件至 wxh1331@foxmail.com
- 我们提供企业级定制服务和技术支持

</details>

## 🙏 致谢

### 🌟 开源技术栈

感谢以下优秀的开源项目，让这个平台得以实现：

<table>
<tr>
<td width="50%">

**🚀 核心框架**
- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能Web框架
- [PostgreSQL](https://www.postgresql.org/) - 强大的开源关系数据库
- [SQLAlchemy](https://sqlalchemy.org/) - Python SQL工具包和ORM
- [Pydantic](https://pydantic-docs.helpmanual.io/) - 数据验证和设置管理

</td>
<td width="50%">

**🤖 AI/ML生态**
- [pgvector](https://github.com/pgvector/pgvector) - PostgreSQL向量扩展
- [Sentence Transformers](https://www.sbert.net/) - 语义文本嵌入
- [Transformers](https://huggingface.co/transformers/) - 预训练模型库
- [PyTorch](https://pytorch.org/) - 深度学习框架

</td>
</tr>
<tr>
<td>

**🛠️ 开发工具**
- [Uvicorn](https://www.uvicorn.org/) - ASGI服务器
- [Alembic](https://alembic.sqlalchemy.org/) - 数据库迁移工具
- [pytest](https://pytest.org/) - 测试框架
- [Black](https://black.readthedocs.io/) - 代码格式化工具

</td>
<td>

**📚 文档处理**
- [python-docx](https://python-docx.readthedocs.io/) - Word文档处理
- [PyPDF2](https://pypdf2.readthedocs.io/) - PDF文档解析
- [openpyxl](https://openpyxl.readthedocs.io/) - Excel文件操作
- [python-pptx](https://python-pptx.readthedocs.io/) - PowerPoint处理

</td>
</tr>
</table>

### 👥 特别感谢

- **教育工作者**: 为平台功能设计提供宝贵建议
- **开发者社区**: 在技术选型和架构设计中给予的帮助
- **早期用户**: 测试和反馈，帮助改进用户体验
- **开源贡献者**: 每一个Pull Request和Issue都让项目变得更好

### 🏫 学术支持

感谢相关院校和研究机构在以下方面的支持：
- 算法研究和优化建议
- 用户体验和界面设计指导
- 教育场景的需求分析
- 技术验证和测试支持

---

<div align="center">

## ⭐ 如果这个项目对您有帮助，请给我们一个 Star！

[![GitHub stars](https://img.shields.io/github/stars/w2902171175/Cosbrain?style=social)](https://github.com/w2902171175/Cosbrain/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/w2902171175/Cosbrain?style=social)](https://github.com/w2902171175/Cosbrain/network/members)
[![GitHub watchers](https://img.shields.io/github/watchers/w2902171175/Cosbrain?style=social)](https://github.com/w2902171175/Cosbrain/watchers)

### 🚀 让我们一起打造更智能的教育协作平台！

**📱 关注项目动态** • **🤝 参与社区讨论** • **💡 分享使用心得** • **🔧 贡献代码改进**

---

*Made with ❤️ by the Cosbrain Team*

*© 2025 鸿庆书云创新协作平台. All rights reserved.*

</div>
