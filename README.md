# 🎓 鸿庆书云创新协作平台 (Cosbrain)

<div align="center">

![Logo](https://img.shields.io/badge/🎓-鸿庆书云-blue?style=for-the-badge)

**云聚书，书载鸿，鸿成庆**

*基于AI技术的现代化智慧教育协作平台*


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

#### 🔍 性能优化

- **索引策略**: 为高频查询字段建立复合索引，优化关联查询性能
- **向量索引**: pgvector扩展的HNSW索引，支持高效的相似度搜索
- **分区表**: 对大数据量表（如消息、日志）进行时间分区
- **连接池**: SQLAlchemy连接池配置，支持高并发访问

### 🔌 API架构

基于FastAPI的现代化RESTful API设计，具有自动文档生成、类型验证和异步处理能力。

#### 🔧 API特性

- **📖 自动文档**: OpenAPI 3.0标准，实时生成API文档
- **✅ 数据验证**: Pydantic模型自动验证请求参数
- **⚡ 异步处理**: 全异步架构，支持高并发请求
- **🔒 安全机制**: JWT认证、CORS配置、请求限流
- **📊 监控日志**: 请求追踪、性能监控、错误报告

#### � API 文档

平台提供完整的RESTful API接口，支持自动文档生成和交互式测试。

##### 🔗 文档访问

| 文档类型 | 访问地址 | 特点 |
|----------|----------|------|
| **Swagger UI** | http://localhost:8000/docs | 交互式API测试，支持在线调用 |
| **ReDoc** | http://localhost:8000/redoc | 美观的文档展示，适合阅读 |
| **OpenAPI JSON** | http://localhost:8000/openapi.json | 机器可读的API规范 |

##### 🚀 API 模块概览

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


## 🏗️ 项目结构

```
Cosbrain/                                    # 项目根目录
├── 📄 README.md                             # 项目说明文档
├── 📋 requirements.txt                      # Python依赖包列表(60个包)
├── 📜 LICENSE                               # 自定义开源许可证
├── 🔧 alembic/                             # 数据库迁移工具
│   └── env.py                              # Alembic环境配置
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

```


### 🗃️ 数据文件

平台包含完整的示例数据和导出功能：
- **📈 业务数据**: 34个表的完整数据导出
- **📋 表结构**: 每个表的schema文档
- **🧪 测试数据**: projects.csv和students.csv等示例数据
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


####  7️⃣启动服务

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

#### 8️⃣ 验证部署

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
