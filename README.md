# StudyPilot 智能学习助手

StudyPilot 是面向课程学习场景的全栈学习辅助平台。用户可围绕一门课程上传资料、建立可追溯的资料问答、生成和确认学习计划、完成每日任务、进行练习与错题复习，并从掌握度、统计、推荐、周报和本地日历中查看学习进展。

系统以课程资料为学习上下文：已处理的资料用于问答引用、知识点提取与练习；确认后的计划产生今日任务；完成任务和练习结果会反馈到掌握度、统计与学习建议。AI 增强是后台可选能力，基础业务流程仍依赖真实课程、资料和学习记录。

## 主要功能

- 用户注册、登录、退出与会话恢复；
- 课程创建、编辑、切换和归档；
- PDF、TXT、Markdown（`.md`/`.markdown`）资料上传与异步处理；
- 基于课程资料的智能问答与引用来源；
- 学习计划预览、确认、今日任务和学习记录；
- 练习、答案解析、错题本与知识点掌握度；
- 基于真实知识点、任务和记录的学习建议；
- 学习统计、CSV 导出、周报 Markdown 下载；
- 本地学习日历、ICS 导出和长时任务中心。

## 技术结构

- 前端：Vue 3、TypeScript、Element Plus；
- 后端：FastAPI；
- 数据：PostgreSQL 16 + pgvector；
- 任务与缓存：Redis、Celery Worker；
- 部署：Docker Compose。

## 目录结构

| 目录 | 用途 |
|---|---|
| `frontend` | Vue 前端页面、路由和接口调用 |
| `backend` | FastAPI 接口、业务服务、RAG 与数据模型 |
| `worker` | Celery 后台任务入口 |
| `mcp-server` | 独立 MCP 工具服务 |
| `docs` | 部署、状态和设计说明 |
| `scripts` | 开发与健康检查脚本 |
| `tests` | 后端与端到端测试 |
| `docker` | 前后端镜像构建与数据库初始化文件 |

## 最快启动

1. 安装并启动 Docker Desktop。
2. 若当前电脑已经有项目作者配置好的本机 `.env`，直接保留并使用它；`start.bat` 不会覆盖该文件。老师或其他人员首次取得源码时，源码包不包含 `.env` 与真实密钥，应复制模板：

   ```powershell
   Copy-Item .env.example .env
   ```

3. 运行 `start.bat`，或执行：

   ```powershell
   docker compose up -d --build
   ```

4. 打开 <http://localhost:8080>。

首次使用建议先注册账号、创建课程并上传一份课程资料，等待资料状态为 `ready` 后再使用问答、计划和练习。

`.env.example` 仅保留 Qwen 配置模板，不含真实 Key。使用真实 Qwen 时在自己的本机 `.env` 填写 `LLM_API_KEY`；没有 Qwen Key 时，将 `LLM_PROVIDER` 改为 `mock` 进行离线演示。无需、也不得要求项目作者提供或提交个人 API Key。

## 文档导航

- [项目部署说明](./项目部署说明.md)
- [项目使用说明](./项目使用说明.md)
- [快速启动指南](./快速启动指南.md)
- [详细 Docker 教程](./docs/07-docker-setup.md)
- [项目当前状态](./docs/PROJECT_STATUS.md)

## 测试与版本信息

- 本次文档整理基线：`eb71a9ba53ba77d6238cbd11674efc76ea37e553`；
- 最近完整 SQLite 后端测试：`161 passed, 3 skipped`；
- 最近前端构建：`npm run build` 通过（仅有既有的 chunk 体积警告）；
- Docker Compose 服务为 `frontend`、`backend`、`worker`、`postgres`、`redis`；
- 已以受控请求验证过 Qwen 知识点提取；远程 AI 的响应速度和输出质量仍会受网络与模型服务影响；
- 真实聊天页 KaTeX 的人工可视化验收尚未执行，不能视为已验证。

## 安全说明

不要提交 `.env`、真实 API Key、JWT 密钥、数据库密码、用户上传资料、数据库卷、`node_modules` 或本地虚拟环境。`.env.example` 仅提供配置项示例。
