# 鸿庆书云创新协作平台

一个为学生提供智能匹配、知识管理、课程学习和协作支持的综合性教育平台。

## 🚀 项目特色

- **智能学生匹配**: 基于AI向量嵌入技术，智能匹配具有相似技能和兴趣的学生
- **知识管理系统**: 个人知识库管理，支持文档上传、分类和智能检索
- **实时协作**: WebSocket实时聊天室，支持多人在线协作
- **课程管理**: 完整的课程体系，包括学习进度跟踪和成绩管理
- **论坛社区**: 学术讨论区，支持话题发布、评论和点赞功能
- **个人收藏**: 支持收藏学习资源和重要内容
- **AI助手集成**: 支持多种大语言模型API配置

## 🛠️ 技术栈

### 后端
- **FastAPI**: 现代、高性能的Python Web框架
- **SQLAlchemy**: Python SQL工具包和对象关系映射
- **PostgreSQL**: 主数据库，支持向量扩展(pgvector)
- **WebSocket**: 实时通信支持
- **PassLib**: 密码加密和验证

### AI/ML
- **Sentence Transformers**: 文本向量化
- **OpenAI API**: 大语言模型集成
- **pgvector**: PostgreSQL向量数据库扩展

### 文件处理
- **python-docx**: Word文档处理
- **openpyxl**: Excel文档处理
- **PyPDF2**: PDF文档处理

## 📦 安装与部署

### 环境要求
- Python 3.8+
- PostgreSQL 14+ (带pgvector扩展)
- 虚拟环境管理工具

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd Create
```

2. **创建虚拟环境**
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **环境配置**
创建 `.env` 文件并配置以下环境变量：
```env
DATABASE_URL=postgresql://username:password@localhost/dbname
SECRET_KEY=your-secret-key
OPENAI_API_KEY=your-openai-api-key
```

5. **数据库初始化**
```bash
python -c "from database import init_db; init_db()"
```

6. **导入初始数据（可选）**
```bash
python import_data.py
```

7. **启动服务**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 📚 API文档

启动服务后，访问以下地址查看API文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🏗️ 项目结构

```
project/
├── main.py              # FastAPI应用主入口
├── models.py            # SQLAlchemy数据模型
├── schemas.py           # Pydantic数据模式
├── database.py          # 数据库连接和配置
├── ai_core.py           # AI核心功能模块
├── ai_core_MiniLM.py    # MiniLM模型支持
├── base.py              # 数据库基类
├── import_data.py       # 数据导入脚本
├── students.csv         # 学生数据
├── projects.csv         # 项目数据
├── temp_audio/          # 临时音频文件
└── uploaded_files/      # 用户上传文件
```

## 🔧 核心功能模块

### 1. 学生管理系统
- 用户注册和认证
- 个人资料管理
- 技能和兴趣标签
- 智能匹配推荐

### 2. 知识管理系统
- 个人知识库创建
- 文档上传和解析
- 知识文章编写
- 智能检索和推荐

### 3. 实时协作系统
- 聊天室创建和管理
- WebSocket实时消息
- 多人在线状态

### 4. 课程学习系统
- 课程创建和管理
- 学习进度跟踪
- 成绩记录和分析

### 5. 社区论坛系统
- 话题发布和讨论
- 评论和回复功能
- 点赞和关注机制

## 🔌 AI功能集成

### 支持的AI模型
- OpenAI GPT系列
- 本地部署的开源模型
- 自定义API端点

### 向量数据库
使用pgvector扩展实现：
- 文本语义搜索
- 相似性匹配
- 智能推荐算法

## 🚀 部署指南

### Docker部署（推荐）
```bash
# 构建镜像
docker build -t hongqing-platform .

# 运行容器
docker run -p 8000:8000 --env-file .env hongqing-platform
```

### 生产环境部署
- 使用Gunicorn作为WSGI服务器
- Nginx作为反向代理
- 配置SSL证书
- 设置日志和监控

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 📝 许可证

本项目采用 [MIT许可证](LICENSE)

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 项目Issues: [GitHub Issues](repository-url/issues)
- 邮箱: your-email@example.com

## 🎯 路线图

- [ ] 移动端APP开发
- [ ] 更多AI模型集成
- [ ] 视频会议功能
- [ ] 机器学习推荐算法优化
- [ ] 多语言国际化支持

---

*最后更新: 2025年8月*
