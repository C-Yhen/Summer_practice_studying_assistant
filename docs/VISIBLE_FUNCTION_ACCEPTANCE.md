# Round 17 可见功能验收清单

本清单记录 2026-07-20 在真实前端、隔离 SQLite 后端、同步任务模式和离线 Provider 下的实际结果。`PASS` 仅用于 Playwright 中实际操作过的控件；后端回归不能替代浏览器结果。系统 Chrome 自动化结果为桌面 9/9、移动 9/9。内置受控浏览器运行时无可用实例，故未执行第二套人工浏览器复核。

状态仅使用：`PASS`、`FIXED_AND_PASS`、`EXCLUDED`、`BLOCKED`。

| ID | 页面/区域 | 交互控件 | 前置条件与步骤 | 期望结果 / 真实 API 或行为 | 桌面 | 移动 | 自动化用例 | 问题与修复 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| A01 | 注册 | 昵称、邮箱、密码、协议、创建账号 | 随机账号填写并提交 | `POST /auth/register` 后真实登录并进入首页 | 通过 | 通过 | `auth-shell: register...` | 无 | PASS |
| A02 | 注册 | 重复邮箱 | 注册后再次提交同邮箱 | 后端 409，不伪造成功 | 通过 | 通过 | `auth-shell: register...` | 无 | PASS |
| A03 | 登录 | 空字段、错误密码、提交按钮 | 空提交，再以错误密码提交 | 前端校验；登录 401 留在登录页 | 通过 | 通过 | `auth-shell: login validation...` | 登录 401 不触发全局登出 | PASS |
| A04 | 登录 | Enter、redirect | 输入正确凭据并按 Enter | `POST /auth/login`，返回原目标 `/settings` | 通过 | 通过 | `auth-shell: register...` | 无 | PASS |
| A05 | 登录状态 | 页面刷新 | 登录后刷新首页 | `GET /users/me` 恢复真实用户 | 通过 | 通过 | `auth-shell: register...` | 无 | PASS |
| A06 | 退出 | 用户菜单、退出登录、浏览器返回 | 点击退出并返回 | Token 清除；不能返回受保护首页 | 通过 | 通过 | `auth-shell: register...` | 无 | PASS |
| A07 | 登录 | 忘记密码展示 | 查看登录辅助区域 | 明确显示“暂未开放”，无可点击假入口 | 通过 | 通过 | 路由/认证故事 | 原来是无行为按钮，改为静态说明 | FIXED_AND_PASS |
| B01 | 应用壳 | 18 个生产路由及标题 | 逐一路由打开 | 页面内容可见，document title 与路由一致 | 通过 | 通过 | `routes: all production pages...` | 日历 eyebrow 统一 | FIXED_AND_PASS |
| B02 | 应用壳 | 桌面侧栏、移动抽屉 | 从设置页点击课程管理 | 客户端导航到课程页 | 通过 | 通过 | `courses-session: business 401...` | 无 | PASS |
| B03 | 全局搜索 | 桌面/移动入口、Ctrl+K、输入、Enter | 打开并搜索“学习日历” | 跳转 `/calendar` | 通过 | 通过 | `courses-session: create course...` | 无 | PASS |
| B04 | 全局搜索 | 方向键、长结果列表、Esc | 创建 8 门课，连续 ArrowDown 20 次 | 高亮项滚入结果容器；Esc 关闭 | 通过 | 通过 | `courses-session: quick-search...` | 增加 `scrollIntoView({block:'nearest'})` | FIXED_AND_PASS |
| B05 | 全局搜索 | 打开/关闭/用户切换 | 重开搜索、退出、401 | 查询、索引、错误、课程缓存清理 | 通过 | 通过 | 搜索、退出及 401 故事 | 集中 reset 并监听会话失效 | FIXED_AND_PASS |
| C01 | 全局会话 | 业务请求 401 | 篡改 Token 后点击课程导航 | 一次清理、提示、跳登录并保留 `/courses` | 通过 | 通过 | `courses-session: business 401...` | 新增无循环依赖 coordinator | FIXED_AND_PASS |
| C02 | 全局会话 | 重新登录 | 401 后用原账号登录 | 返回原 `/courses` | 通过 | 通过 | `courses-session: business 401...` | 无 refresh token | PASS |
| D01 | 学习首页 | 空账号首页与快捷入口 | 新账号打开 `/dashboard` | 真实空状态，无固定统计；页面可用 | 仅打开 | 仅打开 | 路由标题 smoke | 未逐一点击首页快捷卡片 | BLOCKED |
| E01 | 课程列表 | 创建课程表单 | 点击创建，填写名称/编号并提交 | `POST /courses`，进入真实详情 | 通过 | 通过 | `courses-session: create course...` | 无 | PASS |
| E02 | 课程详情 | URL 恢复与标题 | 创建后进入 `/courses/:id` | 真实课程名可见 | 通过 | 通过 | `courses-session: create course...` | 无 | PASS |
| E03 | 课程详情 | 编辑、取消、保存、归档 | 未逐项操作 | 应调用现有更新/归档 API | 未执行 | 未执行 | 无 | 后端回归不能替代可见验收 | BLOCKED |
| F01 | 资料上传 | 课程、文件选择、上传按钮 | 选择真实课程和小型 TXT | `POST /documents/upload`，跳处理 URL | 通过 | 通过 | `learning-flow: upload...` | 无 | PASS |
| F02 | 文档进度 | courseId/documentId/taskId、状态 | 上传后查看任务 | 文档名、真实 taskId、完成状态可见 | 通过 | 通过 | `learning-flow: upload...` | 同步处理、无 Redis/Celery | PASS |
| F03 | 上传异常 | 空文件、类型、大小、重复点击 | 未逐项操作 | 应显示真实校验并可恢复 | 未执行 | 未执行 | 无 | 后端文档回归通过 | BLOCKED |
| F04 | 文档进度 | 筛选、刷新、重新解析、错配 URL | 未逐项操作 | 保持课程/文档/任务归属 | 未执行 | 未执行 | 无 | 后端资源隔离回归通过 | BLOCKED |
| G01 | 智能问答 | 课程、就绪资料、问题、发送 | 上传后输入问题并点击发送 | 离线 Provider 返回持久化问答 | 通过 | 通过 | `learning-flow: upload...` | 不评价外部模型质量 | PASS |
| G02 | 智能问答 | 会话切换、历史、引用、错误重试 | 未逐项操作 | 现有真实 API 路径 | 未执行 | 未执行 | 无 | RAG 后端回归通过 | BLOCKED |
| H01 | 学习计划 | 生成候选、确认弹窗、确认生效 | 点击生成并确认 | candidate 真实变为 active | 通过 | 通过 | `learning-flow: upload...` | 无 | PASS |
| H02 | 今日任务 | 日期/课程筛选、完成、幂等 | 未逐项操作 | 创建一次学习记录并更新页面 | 未执行 | 未执行 | 无 | 后端回归通过 | BLOCKED |
| I01 | 推荐中心 | 首次失败、重试 | 拦截一次 503 后点击重试 | 保留工具栏并重新 GET 成功 | 通过 | 通过 | `routes: recommendation errors...` | 重试/刷新有 loading 与禁用 | FIXED_AND_PASS |
| I02 | 推荐中心 | 分类切换、URL | 点击“学习计划”分类 | URL 写入 `category=plan` 并真实请求 | 通过 | 通过 | `routes: recommendation errors...` | 无 | PASS |
| I03 | 推荐中心 | 反馈、主操作、历史 | 未逐项操作 | 真实写反馈并保持卡片级锁 | 未执行 | 未执行 | 无 | 推荐后端回归通过 | BLOCKED |
| J01 | 练习答题 | 课程、选项、提交、下一题 | 页面实际打开；未作答 | 真实提交与幂等 | 仅打开 | 仅打开 | 路由标题 smoke | 页面可开不等同按钮通过 | BLOCKED |
| K01 | 错题本 | 筛选、分页、详情、标记/移除 | 页面实际打开；未操作 | 真实错题 API | 仅打开 | 仅打开 | 路由标题 smoke | 后端回归不能替代可见验收 | BLOCKED |
| L01 | 掌握度 | 课程、刷新、列表 | 页面实际打开；未操作 | 只展示真实 attempts 数据 | 仅打开 | 仅打开 | 路由标题 smoke | 无控件级证据 | BLOCKED |
| M01 | 学习统计 | 7/30 天、课程、CSV | 页面实际打开；未下载 | 真实 overview/CSV | 仅打开 | 仅打开 | 路由标题 smoke | 下载未验证 | BLOCKED |
| N01 | 长时任务 | 筛选、分页、详情、取消/重试 | 页面实际打开；未操作 | 真实 async task API | 仅打开 | 仅打开 | 路由标题 smoke | 无控件级证据 | BLOCKED |
| N02 | 学习周报 | 创建、详情、Markdown | 未操作 | 同步生成并下载持久化结果 | 未执行 | 未执行 | 无 | 周报后端回归通过 | BLOCKED |
| O01 | 学习日历 | 页面标题/eyebrow | 搜索跳转并检查页面 | `学习日历 / LEARNING CALENDAR` | 通过 | 通过 | `courses-session: create course...` | 修复旧 eyebrow | FIXED_AND_PASS |
| O02 | 学习日历 | 上周/今天/下周、课程 | 页面实际打开；未逐项点击 | 更新 URL 并重载事件 | 仅打开 | 仅打开 | 路由标题 smoke | 无控件级证据 | BLOCKED |
| O03 | 学习日历 | DST 02:30 | 后端构造纽约跳变日 | 422 `INVALID_LOCAL_TIME`；上海正常 | 后端通过 | 后端通过 | `test_calendar_mcp.py` | 增加 UTC round-trip 验证 | FIXED_AND_PASS |
| O04 | 学习日历 | 同步、修改/删除、ICS | 未操作 | 真实预览/确认和下载 | 未执行 | 未执行 | 无 | 日历后端回归通过 | BLOCKED |
| O05 | 日历 MCP | 工具列表、审计 | 本轮禁止启动真实 MCP | 只保留现有元数据/API | 排除 | 排除 | 无 | 未修改 MCP | EXCLUDED |
| P01 | 个人设置 | 昵称、时区、保存、回填 | 修改带空格昵称并保存 | `PATCH /users/me`，规范化回填 | 通过 | 通过 | `learning-flow: profile...` | 桌面昵称同步；移动只显示头像 | PASS |
| P02 | 个人设置 | 学习偏好、保存 | 勾选 Markdown 并保存 | `PATCH /users/me/preferences` | 通过 | 通过 | `learning-flow: profile...` | 无 | PASS |
| P03 | 个人设置 | 模型、工具权限、修改密码 | 打开对应标签 | “后续开放”，按钮 disabled | 通过 | 通过 | `learning-flow: profile...` | 无假成功 | PASS |
| Q01 | 用户隔离 | A/B 资源与切换缓存 | 每用例使用随机独立账号，未构造完整 A/B 故事 | 用户资源不得串用 | 部分 | 部分 | 全套独立账号 | 后端隔离回归通过 | BLOCKED |
| Q02 | 下载 | CSV、ICS、Markdown | 未执行浏览器下载 | 正确文件并清理对象 URL | 未执行 | 未执行 | 无 | 产物目录已清理 | BLOCKED |
| X01 | 外部 AI/Embedding | Provider 质量 | 明确不连接外部服务 | 仅使用离线 Provider | 排除 | 排除 | `learning-flow: upload...` | 后续团队工作 | EXCLUDED |
| X02 | 认证扩展 | 忘记/修改密码、refresh token | 当前未实现 | 不显示可点击假入口 | 排除 | 排除 | 登录/设置故事 | 无新增业务 | EXCLUDED |
| X03 | 聊天扩展 | 流式、删除/重命名会话 | 当前未实现 | 不作为本轮失败 | 排除 | 排除 | 无 | 无新增入口 | EXCLUDED |
| X04 | 第三方日历 | Outlook/Google 同步 | 当前未实现 | 本地事件与 ICS 保持诚实 | 排除 | 排除 | 无 | 无第三方凭据 | EXCLUDED |
| X05 | 新导出 | PDF/DOCX/XLSX | 当前未实现 | 不新增假入口 | 排除 | 排除 | 无 | 仅现有 CSV/ICS/MD | EXCLUDED |
| X06 | 学习扩展 | 延期、专注计时、计划历史 | 当前未实现 | 不新增入口 | 排除 | 排除 | 无 | 无 | EXCLUDED |
| X07 | 系统扩展 | 通知、Webhook、WebSocket、缓存 | 当前未实现 | 不作为本轮失败 | 排除 | 排除 | 无 | 无 | EXCLUDED |

## 结果汇总

- 清单条目：47
- PASS：17
- FIXED_AND_PASS：8
- EXCLUDED：8
- BLOCKED：14
- 自动化浏览器：桌面 9/9、移动 9/9，合计 18/18。
- BLOCKED 表示该控件组没有获得本轮浏览器级实际操作证据；后端测试通过不改变该状态。
