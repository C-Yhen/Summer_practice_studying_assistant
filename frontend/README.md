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

演示登录信息已经预填在登录页，直接点击登录即可。演示令牌只保存在当前浏览器标签页的 `sessionStorage` 中，不作为真实用户数据源。

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

## API 与演示数据回退

- API 基地址由 `VITE_API_BASE_URL` 配置，默认使用同源 `/api/v1`；Vite 开发服务器会把 `/api` 代理到 `http://localhost:8000`。
- Axios 实例、JWT 请求拦截与统一回退逻辑位于 `src/api/client.ts`，领域请求封装位于 `src/api/services.ts`。
- 默认 `VITE_ENABLE_MOCK=true`。请求后端失败时，页面会经过一个短延迟后回退到 `src/data/mock.ts` 的演示数据，因此后端未启动也能完成前端答辩。
- 联调或生产环境应设置 `VITE_ENABLE_MOCK=false`，此时接口错误会正常抛出，不会用演示数据掩盖故障。
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
