# Docker 安装、配置与项目启动教程

本文面向 Windows 10/11 开发环境，说明如何安装和配置 Docker Desktop，并用 Docker Compose 启动智能学习助手完整技术栈。Docker Desktop 安装在 C 盘或 D 盘都可以，不影响项目运行。

## 1. Docker 中运行的服务

| 服务 | 容器职责 | 主机端口 | 持久化数据 |
|---|---|---:|---|
| `frontend` | Nginx 托管 Vue 生产构建，并反向代理 API/WebSocket | `8080` | 无 |
| `backend` | FastAPI、JWT、RAG、计划与推荐接口 | `8000` | `uploads` |
| `worker` | Celery 文档解析和长任务 Worker | 无 | `uploads` |
| `postgres` | PostgreSQL 16、pgvector、业务事实数据 | `5432` | `postgres_data` |
| `redis` | Celery Broker/Result Backend 和任务进度缓存 | `6379` | `redis_data` |

默认使用离线 Mock LLM 和 Mock Embedding，不需要 API Key 即可完成演示。生产前端强制关闭 Mock 回退，接口错误不会被假数据掩盖。

## 2. Windows 前置条件

建议配置：

- Windows 10 22H2 或 Windows 11 64 位；
- BIOS/UEFI 已启用 CPU 虚拟化；
- WSL2；
- 至少 8 GB 内存、20 GB 可用磁盘；
- Git 和 PowerShell。

以管理员身份打开 PowerShell，启用 WSL2：

```powershell
wsl --install
wsl --update
wsl --set-default-version 2
```

如果系统要求重启，应先重启，再继续安装 Docker Desktop。可用下面的命令检查 WSL：

```powershell
wsl --version
wsl -l -v
```

发行版的 `VERSION` 应为 `2`。Docker Desktop 启动后，列表中还会出现 `docker-desktop`。

## 3. 安装 Docker Desktop

### 3.1 使用 Chocolatey

管理员 PowerShell：

```powershell
choco install docker-desktop -y
```

也可以从 Docker 官网下载 MSI/安装程序。安装到 D 盘时，例如选择 `D:\Docker`，程序目录通常是：

```text
D:\Docker\Docker\Docker Desktop.exe
D:\Docker\Docker\resources\bin\docker.exe
```

首次启动 Docker Desktop 后，确认：

1. 接受 Docker Desktop 使用条款；
2. 使用 WSL2 Engine；
3. 等待界面显示 Engine running。

重新打开一个 PowerShell，执行：

```powershell
docker --version
docker compose version
docker info
```

`docker info` 同时出现 `Client` 和 `Server` 信息，才表示 Engine 已就绪。只有 `Client` 或出现 pipe/daemon 错误，说明 Docker Desktop 尚未启动完成。

### 3.2 D 盘安装后的 PATH 修复

若 `docker.exe` 位于 D 盘但命令行提示找不到 `docker`，将其目录加入用户 PATH：

```powershell
$dockerBin = 'D:\Docker\Docker\resources\bin'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $dockerBin) {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$dockerBin", 'User')
}
```

关闭并重新打开 PowerShell。也可在当前窗口临时生效：

```powershell
$env:Path = 'D:\Docker\Docker\resources\bin;' + $env:Path
```

这一步也会解决以下构建错误，因为 `docker-credential-desktop.exe` 与 `docker.exe` 位于同一目录：

```text
docker-credential-desktop: executable file not found in %PATH%
```

### 3.3 将 Docker 数据放到 D 盘（可选）

安装目录和镜像数据目录不是同一概念。若希望镜像、容器和卷也存放到 D 盘，在 Docker Desktop 中打开：

```text
Settings → Resources → Advanced → Disk image location
```

选择 D 盘目录并应用。移动前应先停止本项目容器，并确认重要数据库已有备份。

## 4. 项目环境配置

进入项目根目录：

```powershell
cd D:\SumMer_practice
```

首次运行复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

至少修改 `.env` 中的 `JWT_SECRET` 和数据库密码。生成随机 JWT Secret：

```powershell
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes)
```

将输出写入 `.env`：

```dotenv
JWT_SECRET=替换为上一步生成的随机字符串
POSTGRES_PASSWORD=替换为本机开发密码
LLM_PROVIDER=mock
```

`.env` 已被 Git 忽略，不应提交真实密码或 API Key。

## 5. 构建并启动完整技术栈

在项目根目录执行：

```powershell
docker compose config --quiet
docker compose build --parallel
docker compose up -d
```

也可以使用项目脚本以前台方式启动并查看实时日志：

```powershell
.\scripts\dev.ps1
```

首次构建需要下载基础镜像和 Python/Node 依赖，后续构建会复用缓存。项目已配置 `.dockerignore`，不会把 `.venv`、`node_modules`、日志和数据库发送进构建上下文。

检查容器：

```powershell
docker compose ps
```

预期结果：`postgres`、`redis`、`backend` 显示 `healthy`，`worker` 和 `frontend` 显示 `Up`。

## 6. 访问地址与首次使用

- 前端：<http://localhost:8080>
- 后端健康检查：<http://localhost:8000/health>
- Swagger API 文档：<http://localhost:8000/docs>
- OpenAPI JSON：<http://localhost:8000/openapi.json>

打开前端后先注册账号，再创建课程和上传 TXT、Markdown 或 PDF。Docker 模式的 `VITE_ENABLE_MOCK=false`，因此页面使用的是真实后端数据。

快速健康检查：

```powershell
Invoke-RestMethod http://localhost:8000/health
(Invoke-WebRequest http://localhost:8080 -UseBasicParsing).StatusCode
.\scripts\smoke-test.ps1
```

## 7. 验证 PostgreSQL、pgvector、Redis 和 Worker

检查数据库扩展：

```powershell
docker compose exec -T postgres psql `
  -U smart_learning -d smart_learning `
  -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm') ORDER BY extname;"
```

检查 HNSW 向量索引：

```powershell
docker compose exec -T postgres psql `
  -U smart_learning -d smart_learning `
  -c "SELECT indexname FROM pg_indexes WHERE indexname='ix_document_chunks_embedding_hnsw';"
```

检查 Redis：

```powershell
docker compose exec -T redis redis-cli ping
```

输出应为 `PONG`。

检查 Celery Worker：

```powershell
docker compose logs --tail=100 worker
```

日志应包含连接 `redis://redis:6379/1` 和 `ready`。上传文档后还会看到 `process_document_job` 被接收并成功完成。

## 8. 常用维护命令

查看所有日志：

```powershell
docker compose logs -f
```

只看后端和 Worker：

```powershell
docker compose logs -f backend worker
```

重启单个服务：

```powershell
docker compose restart backend
```

修改代码后重建：

```powershell
docker compose up -d --build backend worker frontend
```

停止服务但保留数据库、Redis 和上传文件：

```powershell
docker compose down
```

重新启动：

```powershell
docker compose up -d
```

查看磁盘占用：

```powershell
docker system df
docker volume ls
```

## 9. 数据备份与重置

备份 PostgreSQL：

```powershell
docker compose exec postgres pg_dump `
  -U smart_learning -d smart_learning `
  -Fc -f /tmp/smart_learning_backup.dump
docker compose cp postgres:/tmp/smart_learning_backup.dump .\smart_learning_backup.dump
docker compose exec postgres rm /tmp/smart_learning_backup.dump
```

上述命令生成 PostgreSQL Custom Format 备份，避免 PowerShell 管道改变 SQL 文件编码。恢复前应先确认目标数据库和备份文件，示例：

```powershell
docker compose cp .\smart_learning_backup.dump postgres:/tmp/smart_learning_backup.dump
docker compose exec postgres pg_restore `
  -U smart_learning -d smart_learning --clean --if-exists `
  /tmp/smart_learning_backup.dump
```

`docker compose down` 不会删除命名卷。以下命令会永久删除数据库、Redis 和上传资料，只能在确认不需要数据时使用：

```powershell
docker compose down -v
```

重新执行 `docker compose up -d` 会创建全新的数据卷，并重新安装 `vector` 与 `pg_trgm` 扩展。

## 10. 接入 OpenAI 兼容模型（可选）

保持离线演示时不需要修改：

```dotenv
LLM_PROVIDER=mock
```

接入兼容 `/chat/completions` 和 `/embeddings` 的服务时，在 `.env` 中配置：

```dotenv
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=https://你的服务地址/v1
LLM_API_KEY=你的密钥
LLM_CHAT_MODEL=聊天模型名称
LLM_EMBEDDING_MODEL=向量模型名称
```

当前数据库向量维度为 1024。真实 Embedding 模型必须输出 1024 维向量；如果要更换维度，需要同步修改后端模型、数据库索引并重建相关向量数据。

应用配置：

```powershell
docker compose up -d --force-recreate backend worker
```

## 11. 常见故障排查

### 11.1 `docker` 不是可识别的命令

重新打开终端；D 盘安装则按第 3.2 节添加 `resources\bin` 到 PATH。不要因为找不到 CLI 就重复安装 Docker Desktop。

### 11.2 无法连接 Docker daemon

执行：

```powershell
docker info
wsl -l -v
```

确认 Docker Desktop 已启动、`docker-desktop` 为 Running、Context 为 `desktop-linux`。

### 11.3 Docker Hub 超时或错误 IPv6

本项目为国内网络环境使用以下镜像地址：

- Python、Node、Nginx、Redis：AWS Public ECR；
- PostgreSQL + pgvector：DaoCloud 对官方 pgvector 镜像的代理。

因此一般不需要直接访问 Docker Hub。如果下载出现 `unexpected EOF` 或 `short read`，直接重试，Docker 会复用已完成的镜像层：

```powershell
docker compose pull
docker compose build --parallel
```

### 11.4 端口已被占用

查看占用进程：

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 5432,6379,8000,8080 |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

停止冲突的本地开发服务，或修改 `docker-compose.yml` 左侧的主机端口。

### 11.5 后端一直 unhealthy

```powershell
docker compose ps
docker compose logs --tail=200 backend postgres redis
```

常见原因是数据库密码与已有 `postgres_data` 卷不一致。开发环境确认数据可删除后，可使用 `docker compose down -v` 重建；有数据时应恢复原密码或先做备份。

### 11.6 文档一直处于 queued/processing

```powershell
docker compose ps worker redis
docker compose logs --tail=200 worker redis
```

确认 Worker 日志包含 `ready`，Redis 返回 `PONG`，并确认 `backend` 与 `worker` 都挂载了同一个 `uploads` 卷。

### 11.7 前端显示接口错误

Docker 生产构建不会回退到 Mock。依次检查：

```powershell
Invoke-RestMethod http://localhost:8000/health
docker compose logs --tail=100 frontend backend
```

浏览器访问前端应使用 `http://localhost:8080`，不要使用已经停止的 Vite 开发端口 `5173`。

## 12. 生产部署前注意事项

当前 Compose 面向本地开发与答辩演示。正式部署前至少需要：

1. 使用强随机 JWT Secret、数据库密码和独立密钥管理；
2. 关闭 PostgreSQL、Redis、后端不必要的公网端口，仅由反向代理暴露 HTTPS；
3. 使用 Alembic 迁移代替自动建表；
4. 让 Celery Worker 使用非 root 用户；
5. 配置数据库和上传资料的自动备份；
6. 配置域名、TLS、监控、日志轮转和资源限制；
7. 将真实 API Key 只放入部署平台 Secret，不写入镜像或 Git。
