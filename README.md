# 🎓鸿庆书云创新协作平台

>  一个为师生提供智能匹配、知识管理、课程学习和协作支持的综合性教育平台
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-blue.svg)](https://postgresql.org)
[![pgvector](https://img.shields.io/badge/pgvector-0.5+-purple.svg)](https://github.com/pgvector/pgvector)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📖 项目简介

鸿庆书云创新协作平台是一个基于AI技术的现代化教育协作系统，旨在为学生、教师和学习者提供一个集成化的学习环境。平台通过智能匹配算法帮助用户找到合适的学习伙伴，提供强大的知识管理工具，支持实时协作和交流。

## ✨ 核心特色

### 🤖 AI智能功能
- **智能学生匹配**: 基于向量嵌入技术，分析用户技能、兴趣和学习目标，智能推荐最匹配的学习伙伴
- **智能文档解析**: 支持Word、PDF、Excel等多种格式文档的智能解析和内容提取
- **语义搜索**: 基于pgvector的向量数据库实现高精度的语义搜索
- **AI助手集成**: 支持OpenAI GPT、本地模型等多种AI模型配置
- **文本转语音(TTS)**: 集成多种TTS服务提供商，支持个性化语音配置

### 📚 知识管理系统
- **个人知识库**: 创建和管理个人知识体系，支持分类标签和智能检索
- **文档上传处理**: 自动解析和索引上传的文档内容，支持RAG检索
- **知识文章编写**: 富文本编辑器支持，markdown语法兼容
- **智能推荐**: 基于用户行为和内容相似性的知识推荐
- **文档分块处理**: 智能文档分块和向量化，提升检索精度

### 💬 实时协作系统
- **WebSocket聊天**: 低延迟的实时消息传输
- **多人聊天室**: 支持项目组、学习小组等多人协作场景
- **聊天室管理**: 完整的成员管理、权限控制和加入申请流程
- **在线状态显示**: 实时显示用户在线状态和活跃度

### 🎯 学习管理
- **课程体系**: 完整的课程创建、管理和学习进度跟踪
- **学习记录**: 详细的学习轨迹和成绩分析
- **个人收藏**: 分文件夹管理收藏内容，支持星标和优先级
- **每日记录**: 学习日志和心情记录，支持标签分类

### 🌐 社区论坛
- **话题讨论**: 学术话题发布和深度讨论
- **评论互动**: 支持多级嵌套评论和回复
- **点赞关注**: 社交化的互动机制
- **用户关系**: 好友关注和粉丝系统

### 🏆 积分成就系统
- **积分机制**: 通过学习、分享、互动等行为获得积分
- **成就系统**: 多样化的成就挑战和奖励机制
- **排行榜**: 激励性的积分排行和成就展示
- **每日打卡**: 培养学习习惯的签到奖励系统

### ⚙️ 个性化配置
- **多模型配置**: 支持配置多个LLM、TTS、搜索引擎
- **MCP协议集成**: 支持Model Context Protocol标准
- **API密钥管理**: 安全的加密存储和管理机制

## 🛠️ 技术架构

### 后端核心
- **FastAPI**: 高性能异步Web框架，自动生成API文档
- **SQLAlchemy 2.0**: 现代化ORM，支持异步操作
- **PostgreSQL + pgvector**: 关系型数据库 + 向量数据��扩展
- **WebSocket**: 实时双向通信协议
- **Pydantic**: 数据验证和序列化
- **Alembic**: 数据库迁移管理

### AI/ML技术栈
- **Sentence Transformers**: 文本向量化模型
- **scikit-learn**: 机器学习算法库
- **PyTorch**: 深度学习框架
- **OpenAI API**: 大语言模型服务
- **gTTS**: 文本转语音功能
- **Transformers**: HuggingFace模型库

### 文件处理
- **python-docx**: Microsoft Word文档处理
- **PyPDF2**: PDF文档解析
- **openpyxl**: Excel文件读写
- **python-pptx**: PowerPoint文档处理

### 安全与认证
- **PassLib + BCrypt**: 密码加密和验证
- **cryptography**: 对称加密算法
- **JWT**: JSON Web Token令牌管理

## 🏗️ 项目结构详解

```
Create/
├── README.md                      # 项目说明文档
├── requirements.txt               # Python依赖包列表
├── run.py                        # 应用启动脚本
├── alembic/                      # 数据库迁移工具
│   └── env.py                    # Alembic环境配置
└── project/                      # 主要代码目录
    ├── main.py                   # FastAPI应用入口和路由定义
    ├── models.py                 # SQLAlchemy数据模型定义(29个表)
    ├── schemas.py                # Pydantic数据验证模式
    ├── database.py               # 数据库连接和会话管理
    ├── base.py                   # SQLAlchemy基类定义
    ├── dependencies.py           # FastAPI依赖注入
    ├── ai_core.py                # AI功能核心模块
    ├── ai_core_MiniLM.py         # MiniLM模型集成
    ├── import_data.py            # 数据导入和初始化脚本
    ├── reset_sequences.py        # 数据库序列重置工具
    ├── fix_data_serialization.py # 数据序列化修复工具
    ├── routers/                  # API路由模块
    │   ├── __init__.py          # 路由包初始化
    │   ├── auth.py              # 用户认证相关
    ├── export_tools/             # 数据导出工具
    │   ├── export_data.py       # 导出脚本
    │   └── data/                # 导出的CSV数据
    │       ├── projects.csv     # 项目数据导出
    │       └── students.csv     # 学生数据导出
    ├── uploaded_files/           # 用户上传文件存储
    │   └── *.{docx,pdf,xlsx,txt} # 各类型上传文件
    ├── temp_audio/               # 临时音频文件存储
    │   └── *.mp3                # TTS生成的音频文件
    └── __pycache__/             # Python字节码缓存
```

## 📦 快速开始

### 🔧 环境准备

**系统要求:**
- Python 3.8 或更高版本
- PostgreSQL 14+ (需安装pgvector扩展)
- Git版本控制工具
- 至少4GB内存和5GB磁盘空间

**PostgreSQL pgvector扩展安装:**
```sql
-- 连接到PostgreSQL数据库
CREATE EXTENSION IF NOT EXISTS vector;
```

### 🚀 安装步骤

1. **克隆项目并进入目录**
```bash
git clone <repository-url>
cd Create
```

2. **创建并激活虚拟环境**
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
```

3. **安装项目依赖**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **环境变量配置**

创建 `.env` 文件：
```env
# 数据库配置
DATABASE_URL=postgresql://username:password@localhost:5432/hongqing_platform

# 安全配置
SECRET_KEY=your-super-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# AI服务配置
OPENAI_API_KEY=your-openai-api-key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# 文件上传配置
UPLOAD_DIR=./project/uploaded_files
TEMP_AUDIO_DIR=./project/temp_audio
MAX_FILE_SIZE=10485760  # 10MB

# 开发配置
DEBUG=True
LOG_LEVEL=INFO
```

5. **数据库初始化**
```bash
cd project
python -c "from database import init_db; init_db()"
```

6. **导入示例数据（可选）**
```bash
python import_data.py
```

7. **启动开发服务器**
```bash
# 方式1：直接启动
python run.py

# 方式2：使用uvicorn
uvicorn project.main:app --reload --host 0.0.0.0 --port 8000
```

## 📊 数据库结构

平台采用PostgreSQL数据库，共包含29个核��数据表：

### 核心表组
- **用户和项目**: `students`, `projects`
- **聊天系统**: `chat_rooms`, `chat_messages`, `chat_room_members`, `chat_room_join_requests`
- **论坛社区**: `forum_topics`, `forum_comments`, `forum_likes`, `user_follows`
- **知识管理**: `knowledge_bases`, `knowledge_articles`, `knowledge_documents`
- **学习���理**: `notes`, `daily_records`, `folders`, `collected_contents`
- **课程系统**: `courses`, `course_materials`, `user_courses`
- **积分成就**: `achievements`, `user_achievements`, `point_transactions`
- **系统配置**: `user_mcp_configs`, `user_search_engine_configs`, `user_tts_configs`




## 🚀 部署指南

### Docker部署（推荐）

1. **构建Docker镜像**
```bash
docker build -t hongqing-platform .
```

2. **使用Docker Compose**
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/hongqing
    depends_on:
      - db
  
  db:
    image: pgvector/pgvector:pg14
    environment:
      POSTGRES_DB: hongqing
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

3. **启动服务**
```bash
docker-compose up -d
```

### 生产环境部署

1. **使用Gunicorn**
```bash
pip install gunicorn
gunicorn project.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

2. **Nginx配置示例**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # Cosbrain
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;

    你可以用容器（推荐）或裸机方式部署。

    ### 方案A：Docker（推荐，最省事）

    1) 准备环境变量

    复制 `.env.example` 为 `.env`，按需调整值（尤其是 SECRET_KEY、DATABASE_URL）。

    2) 一键启动

    在项目根目录运行：

    ```
    docker compose up -d --build
    ```

    这会启动 Postgres 和 API。默认 API 监听 8000 端口。

    3) 反向代理（可选）

    将 `deploy/nginx.conf.example` 配置到你的 Nginx，并将域名指向服务器。

    ### 方案B：裸机/服务器直跑（Windows/Linux）

    1) Python 环境

    - Python 3.11+，建议使用虚拟环境

    2) 安装依赖

    在项目根目录执行：

    ```
    pip install -r requirements.txt
    ```

    3) 配置环境变量

    复制 `.env.example` 为 `.env`，设置 `DATABASE_URL` 指向你的 PostgreSQL。

    4) 运行服务

    ```
    uvicorn project.main:app --host 0.0.0.0 --port 8000 --workers 2
    ```

    5) 生产守护

    - Linux 可参考 `deploy/cosbrain.service.example` 创建 systemd 服务
    - Windows 可使用 NSSM 或任务计划程序把 uvicorn 作为服务常驻

    ### 数据库

    默认使用 PostgreSQL。生产建议开启自动备份并限制公网访问，仅通过内网或隧道访问。

    ### 配置项

    可通过环境变量控制：

    - `DATABASE_URL`：PostgreSQL 连接串
    - `SECRET_KEY`：JWT 密钥
    - `SQL_ECHO`：是否打印 SQL（true/false）
    - 连接池：`SQL_POOL_SIZE`、`SQL_MAX_OVERFLOW`、`SQL_POOL_TIMEOUT`、`SQL_POOL_RECYCLE`
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 🧪 测试

### 运行测试
```bash
# 安装测试依赖
pip install pytest pytest-asyncio

# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_auth.py

# 生成覆盖率报告
pytest --cov=project tests/
```

### 测试数据库
```bash
# 创建测试数据库
createdb hongqing_test

# 运行测试时使用测试数据库
TEST_DATABASE_URL=postgresql://user:password@localhost/hongqing_test pytest
```

## 🐛 故障排除

### 常见问题

1. **数据库连接问题**
```bash
# 检查PostgreSQL服务状态
sudo systemctl status postgresql

# 检查pgvector扩展
psql -d your_database -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

2. **依赖安装问题**
```bash
# 清理pip缓存
pip cache purge

# 重新安装依赖
pip install --no-cache-dir -r requirements.txt
```

3. **文件上传问题**
```bash
# 检查上传目录权限
chmod 755 project/uploaded_files/
```

### 日志调试
```bash
# 启用详细日志
export LOG_LEVEL=DEBUG
python run.py
```

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 开发流程

1. **Fork项目**
2. **创建功能分支**
```bash
git checkout -b feature/your-feature-name
```

3. **提交代码**
```bash
git commit -m "Add: 新功能描述"
```

4. **推送分支**
```bash
git push origin feature/your-feature-name
```

5. **创建Pull Request**

### 代码规范

- **Python代码**: 遵循PEP 8规范
- **提交信息**: 使用约定式提交格式
- **文档**: 重要功能需要编写文档
- **测试**: 新功能需要编写对应测试

### 提交类型
- `feat:` 新功能
- `fix:` 问题修复
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 其他变更

## 📝 版本历史

### v1.0.0 (Current)
- ✅ 基础用户认证系统
- ✅ 智能学生匹配功能
- ✅ 实时聊天系统
- ✅ 知识管理系统
- ✅ 文档上传和解析
- ✅ AI对话集成
- ✅ 论坛社区功能
- ✅ 积分成就系统
- ✅ 多模型配置支持

### 计划功能
- 🔄 移动端适配
- 🔄 多语言支持
- 🔄 高级数据分析
- 🔄 视频会议集成
- 🔄 更多AI模型支持

## 📄 许可证

本项目采用 [MIT License](LICENSE) 许可证。

## 📞 联系我们

- **项目主页**: [GitHub Repository]
- **问题反馈**: [Issues]
- **文档**: [Wiki]
- **邮箱**: wxh1331@foxmail.com


⭐ 如果这个项目对你有帮助，请给我们一个star！
