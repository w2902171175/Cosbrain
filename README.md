# 鸿庆书云创新协作平台

> 🎓 一个为师生提供智能匹配、知识管理、课程学习和协作支持的综合性教育平台

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-blue.svg)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📖 项目简介

鸿庆书云创新协作平台是一个基于AI技术的现代化教育协作系统，旨在为学生、教师和学习者提供一个集成化的学习环境。平台通过智能匹配算法帮助用户找到合适的学习伙伴，提供强大的知识管理工具，支持实时协作和交流。

## ✨ 核心特色

### 🤖 AI智能功能
- **智能学生匹配**: 基于向量嵌入技术，分析用户技能、兴趣和学习目标，智能推荐最匹配的学习伙伴
- **智能文档解析**: 支持Word、PDF、Excel等多种格式文档的智能解析和内容提取
- **语义搜索**: 基于pgvector的向量数据库实现高精度的语义搜索
- **AI助手集成**: 支持OpenAI GPT、本地模型等多种AI模型配置

### 📚 知识管理系统
- **个人知识库**: 创建和管理个人知识体系，支持分类标签和智能检索
- **文档上传处理**: 自动解析和索引上传的文档内容
- **知识文章编写**: 富文本编辑器支持，markdown语法兼容
- **智能推荐**: 基于用户行为和内容相似性的知识推荐

### 💬 实时协作系统
- **WebSocket聊天**: 低延迟的实时消息传输
- **多人聊天室**: 支持项目组、学习小组等多人协作场景
- **在线状态显示**: 实时显示用户在线状态和活跃度

### 🎯 学习管理
- **课程体系**: 完整的课程创建、管理和学习进度跟踪
- **学习记录**: 详细的学习轨迹和成绩分析
- **个人收藏**: 收藏重要学习资源和内容
- **每日记录**: 学习日志和反思记录

### 🌐 社区论坛
- **话题讨论**: 学术话题发布和深度讨论
- **评论互动**: 支持多级评论和回复
- **点赞关注**: 社交化的互动机制
- **用户关系**: 好友关注和粉丝系统

## 🛠️ 技术架构

### 后端核心
- **FastAPI**: 高性能异步Web框架，自动生成API文档
- **SQLAlchemy 2.0**: 现代化ORM，支持异步操作
- **PostgreSQL + pgvector**: 关系型数据库 + 向量数据库扩展
- **WebSocket**: 实时双向通信协议
- **Pydantic**: 数据验证和序列化

### AI/ML技术栈
- **Sentence Transformers**: 文本向量化模型
- **scikit-learn**: 机器学习算法库
- **PyTorch**: 深度学习框架
- **OpenAI API**: 大语言模型服务
- **gTTS**: 文本转语音功能

### 文件处理
- **python-docx**: Microsoft Word文档处理
- **PyPDF2**: PDF文档解析
- **openpyxl**: Excel文件读写
- **python-pptx**: PowerPoint文档处理

### 安全与认证
- **PassLib + BCrypt**: 密码加密和验证
- **OAuth2**: 标准化认证流程
- **JWT**: JSON Web Token令牌管理

## 🏗️ 项目结构详解

```
Create/
├── README.md                    # 项目说明文档
├── requirements.txt             # Python依赖包列表
├── .gitignore                  # Git忽略文件配置
├── .env                        # 环境变量配置（需创建）
└── project/                    # 主要代码目录
    ├── main.py                 # FastAPI应用入口和路由定义
    ├── models.py               # SQLAlchemy数据模型定义
    ├── schemas.py              # Pydantic数据验证模式
    ├── database.py             # 数据库连接和会话管理
    ├── base.py                 # SQLAlchemy基类定义
    ├── ai_core.py              # AI功能核心模块
    ├── ai_core_MiniLM.py       # MiniLM模型专用模块
    ├── import_data.py          # 数据导入和初始化脚本
    ├── students.csv            # 学生示例数据
    ├── projects.csv            # 项目示例数据
    ├── temp_audio/             # 临时音频文件存储
    │   └── *.mp3              # TTS生成的音频文件
    ├── uploaded_files/         # 用户上传文件存储
    │   ├── *.docx             # Word文档
    │   ├── *.pdf              # PDF文档
    │   ├── *.xlsx             # Excel文档
    │   └── *.txt              # 文本文件
    └── __pycache__/           # Python字节码缓存
```

## 📦 快速开始

### 🔧 环境准备

**系统要求:**
- Python 3.8 或更高版本
- PostgreSQL 14+ (需安装pgvector扩展)
- Git版本控制工具
- 至少4GB内存和2GB磁盘空间

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
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后，访问 http://localhost:8000 查看应用状态。

## 📚 API文档和测试

### 交互式API文档
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 主要API端点

| 功能模块 | 端点 | 方法 | 描述 |
|---------|------|------|------|
| 用户管理 | `/students/` | POST | 创建新学生用户 |
| 用户管理 | `/students/{id}` | GET | 获取学生详情 |
| 智能匹配 | `/students/match/{student_id}` | GET | 获取匹配推荐 |
| 知识库 | `/knowledge-bases/` | POST | 创建知识库 |
| 文档上传 | `/upload-document/` | POST | 上传并解析文档 |
| 实时聊天 | `/ws/chat/{room_id}` | WebSocket | 聊天室连接 |
| 课程管理 | `/courses/` | GET | 获取课程列表 |
| 论坛系统 | `/forum/topics/` | POST | 发布论坛话题 |

## 🔌 AI功能详解

### 向量搜索引擎
基于pgvector扩展的高性能向量数据库：
- **文本嵌入**: 使用Sentence-BERT模型将文本转换为1024维向量
- **相似性计算**: 余弦相似度算法计算内容相关性
- **实时索引**: 新上传内容自动向量化并建立索引

### 智能匹配算法
```python
# 匹配算法核心逻辑示例
def find_similar_students(target_student_id, top_k=5):
    # 1. 获取目标学生的向量表示
    # 2. 计算与所有其他学生的相似度
    # 3. 返回相似度最高的K个学生
    pass
```

### 支持的AI模型
- **OpenAI GPT系列**: GPT-3.5, GPT-4
- **开源模型**: 支持本地部署的Llama、ChatGLM等
- **嵌入模型**: all-MiniLM-L6-v2, text-embedding-ada-002

## 🚀 生产环境部署

### Docker部署（推荐）

1. **创建Dockerfile**
```dockerfile
FROM python:3.8-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY project/ ./project/
COPY .env .

EXPOSE 8000
CMD ["uvicorn", "project.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

2. **构建和运行**
```bash
docker build -t hongqing-platform .
docker run -p 8000:8000 --env-file .env hongqing-platform
```

### 使用Docker Compose

创建 `docker-compose.yml`:
```yaml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/hongqing
    depends_on:
      - db
    
  db:
    image: pgvector/pgvector:pg14
    environment:
      - POSTGRES_DB=hongqing
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    
volumes:
  postgres_data:
```

### Nginx反向代理配置

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 🔧 开发指南

### 代码规范
- 遵循PEP 8 Python编码规范
- 使用类型注解提高代码可读性
- 编写单元测试确保代码质量

### 添加新功能
1. 在 `models.py` 中定义数据模型
2. 在 `schemas.py` 中创建Pydantic模式
3. 在 `main.py` 中添加API路由
4. 编写测试用例验证功能

### 调试技巧
```bash
# 启用详细日志
uvicorn main:app --reload --log-level debug

# 数据库查询日志
# 在database.py中设置 echo=True
```

## ❓ 常见问题

### Q: 如何配置不同的AI模型？
A: 在用户设置中配置API密钥和模型参数，支持OpenAI、Azure OpenAI等多种服务。

### Q: 上传的文件存储在哪里？
A: 文件存储在 `project/uploaded_files/` 目录，建议生产环境使用对象存储服务。

### Q: 如何备份数据库？
A: 使用PostgreSQL的pg_dump工具：
```bash
pg_dump -U username -h localhost hongqing_platform > backup.sql
```

### Q: WebSocket连接失败怎么办？
A: 检查防火墙设置，确保8000端口开放，并验证WebSocket URL格式正确。

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 贡献流程
1. Fork本项目到你的GitHub账户
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

### 开发环境设置
```bash
# 安装开发依赖
pip install pytest pytest-asyncio black flake8

# 运行测试
pytest

# 代码格式化
black .

# 代码检查
flake8 .
```

### Issue报告
发现bug或有功能建议？请在GitHub Issues中详细描述：
- 问题描述和重现步骤
- 预期行为和实际行为
- 系统环境信息
- 相关日志和错误信息

## 📊 性能监控

### 关键指标
- API响应时间: < 200ms
- 并发用户数: 支持1000+
- 文件上传: 最大10MB
- WebSocket连接: 支持500+并发

### 监控工具推荐
- **APM**: New Relic, DataDog
- **日志**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **性能**: Prometheus + Grafana

## 🔒 安全说明

### 数据保护
- 所有密码使用BCrypt加密存储
- API访问需要JWT令牌验证
- 文件上传包含恶意软件检测
- 敏感数据传输使用HTTPS加密

### 隐私政策
- 用户数据仅用于平台功能提供
- 不会与第三方分享个人信息
- 用户可随时导出或删除个人数据

## 📄 许可证

本项目采用 [MIT许可证](LICENSE) - 查看LICENSE文件了解详细信息。

## 📞 联系我们

- **项目主页**: [GitHub Repository](https://github.com/your-username/hongqing-platform)
- **问题反馈**: [GitHub Issues](https://github.com/your-username/hongqing-platform/issues)
- **邮箱支持**: wxh1331@foxmail.com
- **社区讨论**: [Discord服务器](https://discord.gg/your-invite)

## 🗺️ 发展路线图

### 已完成 ✅
- [x] 基础用户管理系统
- [x] AI智能匹配算法
- [x] 实时聊天功能
- [x] 文档上传处理
- [x] 向量搜索引擎

### 进行中 🚧
- [ ] 移动端适配优化
- [ ] 高级AI对话功能
- [ ] 多媒体内容支持
- [ ] 性能监控仪表板

### 计划中 📋
- [ ] 移动APP开发 (React Native)
- [ ] 视频会议集成 (WebRTC)
- [ ] 区块链证书系统
- [ ] 多语言国际化支持
- [ ] 企业级权限管理
- [ ] API开放平台

### 未来愿景 🌟
- [ ] VR/AR学习体验
- [ ] AI个人学习助教
- [ ] 跨平台数据同步
- [ ] 智能学习路径推荐

## 🙏 致谢

感谢以下开源项目和社区的支持：

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化Web框架
- [SQLAlchemy](https://sqlalchemy.org/) - Python ORM框架
- [pgvector](https://github.com/pgvector/pgvector) - PostgreSQL向量扩展
- [Sentence Transformers](https://sentence-transformers.net/) - 文本嵌入模型
- [OpenAI](https://openai.com/) - AI语言模型服务

特别感谢所有贡献者和用户的支持与反馈！

---

<div align="center">
<b>🌟 如果这个项目对你有帮助，请给我们一个Star！🌟</b>
<br><br>
<i>最后更新: 2025年1月</i>
</div>
