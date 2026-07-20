# StudyPilot 前端 MVP

基于 Vue 3、TypeScript、Vite、Element Plus、Pinia、Axios、ECharts 的智能学习助手前端。项目包含附件要求的 18 个页面，并使用“数据库系统期末冲刺”作为可直接答辩的演示数据。

## 本地运行

```bash
npm install
npm run dev
```

生产构建：

```bash
npm run build
```

## 运行模式

默认为真实后端模式，Mock 不会在未配置时静默开启。复制 `.env.example` 为 `.env.local` 后可按下面两种方式配置。

真实后端模式：

```env
VITE_API_BASE_URL=/api/v1
VITE_ENABLE_MOCK=false
```

该模式需要后端、PostgreSQL 和 Redis 等服务正常运行。注册会发送 `display_name`、`email` 和 `password`；登录使用后端签发的真实 JWT，并通过 `/users/me` 在页面刷新后恢复用户信息。令牌仅保存在当前浏览器标签页的 `sessionStorage` 中。

演示模式：

```env
VITE_ENABLE_MOCK=true
```

只有值严格等于字符串 `true` 时才会开启。演示模式会使用虚拟账号、演示令牌和 Mock 业务数据，不会把注册信息写入真实后端。页面顶部会显示“演示模式”标识。

## 页面路由

| 页面 | 路由 |
| --- | --- |
| 登录 / 注册 | `/login`、`/register` |
| 学习首页 | `/dashboard` |
| 课程管理 / 课程详情 | `/courses`、`/courses/:id` |
| 资料上传 / 文档处理进度 | `/upload`、`/documents/tasks` |
| 智能问答 | `/chat` |
| 学习计划 / 今日任务 | `/plan`、`/today` |
| 推荐中心 | `/recommendations` |
| 练习答题 / 错题本 | `/practice`、`/wrong-book` |
| 知识点掌握度 / 学习统计 | `/mastery`、`/statistics` |
| 长时任务中心 | `/tasks` |
| 日历同步 | `/calendar` |
| 个人设置 | `/settings` |

## API 与演示数据

- API 基地址由 `VITE_API_BASE_URL` 配置，默认使用同源 `/api/v1`；Vite 开发服务器会把 `/api` 代理到 `http://localhost:8000`。
- Axios 实例、JWT 请求拦截、统一 Envelope 解包和 API 错误提取位于 `src/api/client.ts`，领域请求封装位于 `src/api/services.ts`。
- 真实模式下，认证请求失败会显示 401、409、422、网络错误或后端 `detail`，不会生成虚假 Token 或用户。
- 显式设置 `VITE_ENABLE_MOCK=true` 后，业务请求才可在后端失败时回退到 `src/data/mock.ts` 的演示数据。认证流程会直接走独立的虚拟账号路径。
- 长时任务 WebSocket 封装位于 `src/api/taskSocket.ts`。未配置 `VITE_WS_URL` 时，处理进度页使用可预测的本地演示进度；配置后会消费后端进度消息。

期望的统一响应结构：

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "req_xxx"
}
```

## 答辩演示建议

1. 登录并展示学习首页的任务、薄弱点、趋势和长时任务。
2. 进入“数据库系统”课程，上传资料并展示 Celery / Redis / pgvector 处理进度。
3. 在智能问答中提问“什么是第三范式”，展开右侧文档、页码、章节与匹配度引用。
4. 展示 AI 调整计划的原因和 `v2 → v3` 差异，再演示用户确认机制。
5. 完成一道练习，展示错题分析、掌握度变化和可解释推荐。
6. 在日历页预览事件，强调 MCP 只读调用可自动执行，写操作必须经用户确认且全部记录日志。

## 可见功能 E2E 验收

仓库包含桌面端与移动端 Playwright 验收套件。它会启动一个短生命周期的 SQLite 后端容器和本地 Vite 服务，不依赖 PostgreSQL、Redis 或 Celery，也不会写入日常开发数据库。

```powershell
cd frontend
powershell -ExecutionPolicy Bypass -File .\e2e\run-isolated.ps1
```

运行前需要 Docker Desktop 可用，并已安装前端依赖和系统 Chrome。测试完成后，脚本会移除临时后端容器和 Playwright 输出目录。各可见功能的实际覆盖、排除项与阻塞项记录在 `docs/VISIBLE_FUNCTION_ACCEPTANCE.md`。
