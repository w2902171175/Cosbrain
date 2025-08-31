# Docker 一键部署

本项目提供 Docker 化部署，包含：
- 应用服务 (FastAPI + Uvicorn)
- PostgreSQL (带 pgvector 扩展)
- Redis
- 可选 MinIO（本地 S3 兼容对象存储，用于 OSS 开发联调）

## 1. 准备环境
- 安装 Docker Desktop 24+
- Windows PowerShell 或 WSL 均可

## 2. 配置环境变量
复制示例环境文件：

```powershell
Copy-Item .env.example .env
```

按需修改 `.env` 中的变量（特别是 SECRET_KEY、数据库密码等）。

## 3. 一键启动

```powershell
# 构建并启动（首次时间较长）
docker compose up -d --build

# 查看日志
docker compose logs -f app
```

或使用一键脚本（PowerShell）：

```powershell
python docker/oneclick_docker.py            # 构建并启动
python docker/oneclick_docker.py --no-build # 跳过构建直接启动
python docker/oneclick_docker.py --logs     # 启动后跟随日志
```

应用启动后访问：
- API: http://localhost:8001
- Swagger: http://localhost:8001/docs

## 4. 首次初始化数据库（可选，危险操作）
`project/database.py:init_db()` 会 DROP ALL TABLES 再重建，谨慎使用。

方式一（推荐，一次性 job）：
```powershell
docker compose --profile init up --build db-init
```
完成后只需启动/重启应用：
```powershell
docker compose up -d app
```

方式二（不建议长期开启）：设置 `.env` 后启动应用会在容器入口尝试 init（同样危险）：
```
RUN_DB_INIT=true
```
完成初始化后务必改回：
```
RUN_DB_INIT=false
```

## 5. 数据持久化与挂载
- PostgreSQL 数据卷：`pgdata`（容器卷）
- 应用日志：`./logs` 挂载到容器 `/app/logs`
- 上传文件：`./uploaded_files` -> `/app/uploaded_files`
- YARA 扫描输出：`./yara/output` -> `/app/yara/output`

## 6. OSS/MinIO 配置（可选）
compose 中包含 `minio` 与 `minio-setup` 服务用于本地对象存储测试：
- 控制台: http://localhost:9001 （默认账密 `minioadmin/minioadmin`）
- S3 端点: http://localhost:9000

在 `.env` 中启用如下变量对接 MinIO：
- S3_ENDPOINT_URL=http://minio:9000
- S3_BUCKET_NAME=cosbrain
- S3_ACCESS_KEY_ID=minioadmin
- S3_SECRET_ACCESS_KEY=minioadmin
- S3_REGION=us-east-1（或留空）
- S3_VERIFY_SSL=false
- S3_ADDRESSING_STYLE=path
- S3_BASE_URL=http://localhost:9000/cosbrain （用于生成可访问链接）

## 7. 常见问题
- 端口冲突：确保 5432、6379、8001 未被占用；或修改 compose 暴露端口。
- 构建很慢/失败：首次安装 `torch` 体积较大，耐心等待。也可在 requirements.txt 中改为 CPU 友好版本。
- 连接数据库失败：检查 `.env` 是否正确，容器网络下数据库主机应为 `db`。
- Windows 路径权限：挂载目录需要存在；确保没有被占用锁定。

## 8. 生产建议
- 将数据库和 Redis 迁移为托管服务；只保留 `app` 容器。
- 使用反向代理与 HTTPS（如 Nginx + certbot 或云厂商 LB）。
- 设置强随机的 SECRET_KEY、数据库密码，并限制外部端口暴露。

---
如需帮助，可在 README 或 Issue 中反馈。