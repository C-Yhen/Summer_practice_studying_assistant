# Round 17 可见功能验收清单

本清单记录 2026-07-20 在真实 Vite 前端、短生命周期隔离 SQLite 后端、同步任务模式、离线 Provider 和系统 Chrome 下的可见交互结果。复杂前置数据可由 API helper 或仅位于 E2E 目录的 fixture 准备，但被验收的按钮、表单、筛选、确认和下载均由 Playwright 在浏览器中真实操作。后端测试不能替代浏览器证据，显式 Mock 结果不作为真实功能通过依据。

状态仅允许 `PASS`、`FIXED_AND_PASS`、`EXCLUDED`、`BLOCKED`。外部模型未接入不影响 AI 产品定位；回答质量不在本轮评价范围。

| ID | 页面/区域 | 控件 | 前置条件 | 操作 | 期望结果 | 桌面结果 | 移动结果 | 自动化测试 | 发现问题 | 修复文件 | 最终状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A01 | 注册 | 协议、密码显隐、提交 | 随机新账号 | 未勾选提交，再勾选并双击 | 未勾选不发 POST；勾选只发一次并成功 | 通过 | 通过 | `auth-shell: register agreement...` | 协议曾默认勾选，缺少确认密码和显隐验收 | `RegisterView.vue` | FIXED_AND_PASS |
| A02 | 注册 | 重复邮箱与重试 | API 预建账号 | 浏览器提交重复邮箱，再改邮箱 | 显示 409 文案、保留表单、解除 loading、可重试 | 通过 | 通过 | `auth-shell: duplicate email...` | 无 | — | PASS |
| A03 | 登录 | 校验和错误密码 | 已注册账号 | 空提交、错误密码提交 | 前端校验；401 留在登录页且不触发全局失效 | 通过 | 通过 | `auth-shell: login validation...` | 无 | — | PASS |
| A04 | 登录 | Enter 与 redirect | 带 redirect 打开登录页 | 正确凭据按 Enter | 登录一次并回到原目标 | 通过 | 通过 | `auth-shell: register agreement...` | 无 | — | PASS |
| A05 | 会话恢复 | 页面刷新 | 已登录 | 刷新受保护页面 | `/users/me` 恢复真实用户 | 通过 | 通过 | `auth-shell: register agreement...` | 无 | — | PASS |
| A06 | 退出 | 用户菜单、返回 | 已登录 | 点击退出并浏览器返回 | Token、用户及缓存清空，不能返回保护页 | 通过 | 通过 | `auth-shell: register agreement...` | 无 | — | PASS |
| A07 | 登录辅助 | 尚未开放入口 | 未登录 | 检查辅助区 | 静态说明，不提供无行为按钮 | 通过 | 通过 | `auth-shell` | 曾显示无行为可点击入口 | `LoginView.vue` | FIXED_AND_PASS |
| B01 | 应用壳 | 18 条生产路由和标题 | API 创建动态课程 | 逐路由打开 | title、主容器、导航名一致，无 404/空白 | 通过 | 通过 | `routes: all 18 production routes...` | 日历标题曾不一致 | `router/index.ts`、`CalendarView.vue` | FIXED_AND_PASS |
| B02 | 应用壳 | 桌面侧栏与移动抽屉 | 已登录 | 点击课程管理 | 正确进入 `/courses` | 通过 | 通过 | `courses-session: business 401...` | 无 | — | PASS |
| B03 | 全局搜索 | 桌面点击、Ctrl/Cmd+K、移动图标 | 已登录 | 三种入口打开并搜索日历 | 入口可用并进入 `/calendar` | 通过 | 通过 | `courses-session: global search...` | 无 | — | PASS |
| B04 | 全局搜索 | 方向键、Enter、Esc、滚动、焦点 | API 创建多门课程 | 键盘遍历长列表并关闭 | 高亮项滚入视区，Enter 跳转，Esc 恢复焦点 | 通过 | 通过 | `courses-session: quick-search...` | 高亮项曾不自动滚动 | `QuickSearch.vue` | FIXED_AND_PASS |
| B05 | 全局搜索 | 用户切换后的课程缓存 | 同一浏览器 A/B/A | 搜索 A、退出切 B、再回 A | 只显示当前用户真实课程 | 通过 | 通过 | `isolation-downloads: A/B/A...` | 用户缓存曾跨会话保留 | `QuickSearch.vue`、`auth.ts` | FIXED_AND_PASS |
| C01 | 全局会话 | 并发业务 401 | 已登录且拦截多个业务请求 | 并发触发 401 | 只清理、提示、跳转一次；后续抑制 | 通过 | 单次通过 | `courses-session: concurrent business 401...` | 单 Promise 与手动退出竞态需加固 | `session-expiry.ts`、`client.ts`、`auth.ts` | FIXED_AND_PASS |
| C02 | 全局会话 | 重新登录及旧请求 | 401 后或手动退出 | 重新登录；让旧请求迟到 401 | 登录重置协调器；旧 401 不误提示 | 通过 | 通过 | `courses-session: stale 401...` | 无 Refresh Token，本轮未新增 | `session-expiry.ts`、`client.ts` | PASS |
| D01 | 学习首页 | 快捷入口、空状态、重试 | 空账号及有数据账号 | 逐个点击课程、上传、计划、今日、推荐、掌握度、统计；拦截一次失败后重试 | 跳到真实路由；无固定指标；重试发真实请求 | 通过 | 通过 | `course-document-dashboard: dashboard shortcuts...` | 展示区曾含无来源固定动态数字 | `AuthShowcase.vue` | FIXED_AND_PASS |
| E01 | 课程列表 | 创建课程 | 已登录 | 填写名称和编号并双击提交 | 只创建一次并进入真实详情 | 通过 | 通过 | `courses-session: create course...` | 无 | — | PASS |
| E02 | 课程详情 | URL 恢复与标题 | 已创建课程 | 直接打开详情 URL | 显示真实课程且刷新保持 | 通过 | 通过 | `course-document-dashboard: edit archive...` | 无 | — | PASS |
| E03 | 课程详情 | 编辑、取消、保存、归档 | 已创建课程 | 取消编辑；再保存；取消归档；再确认 | 取消恢复原值，规范化保存持久化，归档后列表/搜索/直链均不可用 | 通过 | 通过 | `course-document-dashboard: edit archive...` | 无新增生产问题 | — | PASS |
| F01 | 资料上传 | 课程、文件、上传 | 已有课程 | 选择合法 TXT 并点击上传 | 一次真实上传并进入处理页 | 通过 | 通过 | `learning-flow: upload...` | 无 | — | PASS |
| F02 | 文档进度 | 文档和任务详情 | 合法上传完成 | 查看处理页 | 文档名、真实 taskId、完成状态可见 | 通过 | 通过 | `learning-flow: upload...` | 无 | — | PASS |
| F03 | 上传异常 | 空选择、空 TXT、扩展名、大小、双击、恢复 | 已有课程 | 依次提交异常文件，再提交合法 TXT | 显示真实校验；错误可恢复；合法上传只发一次 POST | 通过 | 通过 | `course-document-dashboard: upload validation...` | 无新增生产问题 | — | PASS |
| F04 | 文档任务 | 课程/状态筛选、任务、刷新、轮询、重解析、错配 URL | 准备成功和失败任务 | 操作所有控件并替换 ID | 资源链一致；失败可恢复；重解析防重复；切课清旧详情 | 通过 | 通过 | `course-document-dashboard: document task...` | 无新增生产问题 | — | PASS |
| G01 | 智能问答 | 发送和持久化 | 已有 ready 文档 | 发送后刷新、离开再返回 | 同会话问题和离线回答保留且不重复发送 | 通过 | 通过 | `chat-settings: chat persistence...` | 不评价回答质量 | — | PASS |
| G02 | 智能问答 | 双会话、资料、引用、键盘、错误重试、移动会话区 | 已有课程和资料 | 切换会话；Shift+Enter；Enter；拦截一次失败再重发 | 历史恢复；引用/无引用诚实；失败后同输入可恢复；切课清旧会话 | 通过 | 通过 | `chat-settings: chat persistence...` | 移动端曾完全隐藏引用区域 | `ChatView.vue` | FIXED_AND_PASS |
| H01 | 学习计划 | 生成、确认 | 已有课程 | 生成 candidate 并确认 | candidate 真实变为 active | 通过 | 通过 | `learning-flow: plan...` | 无 | — | PASS |
| H02 | 今日任务 | 日期/课程/taskId、分钟、完成、幂等、重试 | active 与 candidate 版本并存 | URL 恢复；非法分钟；双击完成；刷新与重复完成 | 只完成一次并持久化；candidate/旧版本不出现；失败可重试 | 通过 | 通过 | `learning-recommendations: today task...` | 日期和 taskId 曾不能完整 URL 恢复 | `TodayTasksView.vue` | FIXED_AND_PASS |
| I01 | 推荐中心 | 加载失败与重试 | 已有课程 | 拦截 503 后点击重试 | 保留工具栏并重新 GET 成功 | 通过 | 通过 | `routes-recommendations: recommendation errors...` | 重试/刷新锁曾不完整 | `RecommendationsView.vue` | FIXED_AND_PASS |
| I02 | 推荐中心 | 分类和 URL | 已有多类候选 | 切换分类并刷新 | URL 恢复且分类 GET 只读 | 通过 | 通过 | `routes-recommendations: category URL...` | 无 | — | PASS |
| I03 | 推荐中心 | 两卡并发反馈、主操作、历史 | 已有多条推荐 | A/B 同时反馈；跨卡片连续触发主操作；打开/刷新历史 | 反馈卡片锁独立；主操作全局单锁；每动作一次写入和一次跳转；历史请求防重复 | 通过 | 通过 | `learning-recommendations: recommendation feedback locks...` | 反馈曾使用单一 busy；主操作 busy key 曾可被另一卡片覆盖 | `RecommendationsView.vue` | FIXED_AND_PASS |
| J01 | 练习答题 | 课程、答案、提交、失败重试、下一题 | 已有题目 | 改答案；双击；中断一次网络并以相同 submission 重试 | 单次有效提交；结果/解析正确；切课清未提交状态 | 通过 | 通过 | `learning-recommendations: practice...` | 移动端长选项文本曾覆盖“下一题”点击区域 | `PracticeView.vue` | FIXED_AND_PASS |
| K01 | 错题本 | 筛选、分页、详情、标记、移出、再次练习 | 已有错误作答 | 操作现有控件并刷新 | summary 与列表一致，锁有效，持久化且切课不残留 | 通过 | 通过 | `learning-recommendations: practice...` | 无新增生产问题 | — | PASS |
| L01 | 掌握度 | 课程、刷新、筛选、排序、空状态 | 有尝试和 attempts=0 数据 | 操作现有控件并切课 | 只把真实尝试作为掌握记录；空状态和错误可恢复 | 通过 | 通过 | `learning-recommendations: practice...` | 无新增生产问题 | — | PASS |
| M01 | 学习统计 | 7/30 天、课程、URL、图表、CSV | 有跨日学习和练习数据 | 切范围和课程；下载；拦截一次导出失败 | 指标/比较/daily/分布/49日热图/洞察真实；CSV 页面下载正确 | 通过 | 通过 | `statistics-tasks-calendar: statistics CSV...` | 无新增生产问题 | — | PASS |
| N01 | 长时任务 | 筛选、分页、详情、刷新、取消、重试 | fixture 准备 queued/failed | 浏览器确认取消与重试，含双击 | URL/详情/自动刷新正确；写操作各一次；移动详情和横向滚动可用 | 通过 | 通过 | `statistics-tasks-calendar: task center...` | 无新增生产问题 | — | PASS |
| N02 | 学习周报 | 创建校验、详情、Markdown、旧 schema | 准备学习数据和旧任务 | 校验日期；双击创建；查看章节；下载；拦截导出失败 | 周报真实持久化；新旧 schema 可读；Markdown 内容和文件名正确 | 通过 | 通过 | `statistics-tasks-calendar: reports Markdown...` | 无新增生产问题 | — | PASS |
| O01 | 学习日历 | 页面标题/eyebrow | 已登录 | 搜索跳转并查看 | `学习日历 / LEARNING CALENDAR` | 通过 | 通过 | `routes: all 18 production routes...` | 标题曾写成“日程日历” | `CalendarView.vue` | FIXED_AND_PASS |
| O02 | 学习日历 | 上周/今天/下周、课程、前进后退 | 已有日历数据 | 点击周导航、切课程、刷新、浏览器前后退 | URL 可恢复；周一至周日；按用户时区；切范围清旧事件 | 通过 | 通过 | `statistics-tasks-calendar: calendar navigation...` | `replace` 曾无法形成浏览器历史 | `CalendarView.vue` | FIXED_AND_PASS |
| O03 | 日历 DST | 春季不存在与秋季重复时间 | America/New_York | 预览 2026-03-08 02:30 和 2026-11-01 01:30 | 春季 422；秋季明确 fold=0，稳定为 05:30Z | 后端通过 | 后端通过 | `test_calendar_mcp.py` 两个 DST 专项 | 秋季曾依赖未声明的 Python 默认 fold | `calendar.py`、`test_calendar_mcp.py` | FIXED_AND_PASS |
| O04 | 学习日历 | 计划同步、修改、删除、ICS、eventId | active 任务和日历事件 | 预览各状态；双击确认；编辑；取消/确认删除；下载两次 ICS | 幂等且任务保留；直链事件隔离；删除事件不再导出；MCP 面板失败不影响本地功能 | 通过 | 通过 | `statistics-tasks-calendar: calendar sync ICS...` | 直链 eventId 缺少恢复和隔离提示 | `CalendarView.vue` | FIXED_AND_PASS |
| O05 | 日历 MCP | 真实 MCP Server 与第三方账户 | 本轮禁止启动 | 不执行外部联调 | 仅验证页面现有工具元数据和隔离审计空状态 | 排除 | 排除 | `statistics-tasks-calendar: calendar sync ICS...` | MCP Server 未启动 | — | EXCLUDED |
| P01 | 个人设置 | 昵称、时区、回填 | 已登录 | 上海改纽约，刷新，再改回上海；保存带空格昵称 | 服务端规范化；timezone 持久化并回填 | 通过 | 通过 | `chat-settings: settings persist...` | 无 | — | PASS |
| P02 | 个人设置 | 学习偏好 | 已登录 | 修改 Markdown 等偏好并保存刷新 | PATCH 持久化，不覆盖其他字段 | 通过 | 通过 | `chat-settings: settings persist...` | 无 | — | PASS |
| P03 | 个人设置 | 模型、工具权限、修改密码 | 打开各标签 | 检查控件 | 明确“后续开放”且禁用，无假成功 | 通过 | 通过 | `chat-settings: settings persist...` | 无 | — | PASS |
| Q01 | 用户隔离 | 同浏览器完整 A/B/A 故事 | A 有课程、文档、计划、任务、练习、错题、反馈、周报、事件 | A 验证后退出；B 查各页和直链；再回 A | B 看不到 A 资源；搜索隔离；A 关键数据仍在 | 通过 | 通过 | `isolation-downloads: complete A/B/A...` | 持久化注入 Token 的旧 helper 会污染用户切换；零课程非法推荐 URL 错误曾被空状态遮挡 | `api.ts`、`RecommendationsView.vue` | FIXED_AND_PASS |
| Q02 | 浏览器下载 | CSV、ICS、Markdown | 准备三类真实数据 | 仅通过页面按钮捕获 download | 校验文件名、BOM/表头、日历结构、中文 Markdown，并清理临时目录 | 通过 | 通过 | `statistics-tasks-calendar` 两个下载用例 | 无新增生产问题 | — | PASS |
| X01 | 外部 AI/Embedding | 外部 Provider 质量 | 本轮禁止连接 | 不执行 | 保留 AI 品牌；离线 Provider 只验交互，不评价质量 | 排除 | 排除 | 问答 E2E 仅覆盖离线路径 | 外部 Provider 未接入 | — | EXCLUDED |
| X02 | 认证扩展 | 忘记/修改密码、Refresh Token | 尚未实现 | 不执行 | 不显示可点击假入口 | 排除 | 排除 | 认证 E2E | 明确未来能力 | — | EXCLUDED |
| X03 | 聊天扩展 | 流式、删除、重命名 | 尚未实现 | 不执行 | 不作为本轮失败 | 排除 | 排除 | — | 明确未来能力 | — | EXCLUDED |
| X04 | 第三方日历 | Outlook/Google 自动同步 | 尚未实现 | 不执行 | 本地事件和 ICS 保持真实 | 排除 | 排除 | — | 明确未来能力 | — | EXCLUDED |
| X05 | 新导出 | PDF/DOCX/XLSX | 尚未实现 | 不执行 | 不新增假入口 | 排除 | 排除 | — | 仅验收现有 CSV/ICS/Markdown | — | EXCLUDED |
| X06 | 学习扩展 | 延期、专注计时、计划历史 | 尚未实现 | 不执行 | 不新增入口 | 排除 | 排除 | — | 明确未来能力 | — | EXCLUDED |
| X07 | 系统扩展 | 通知、Webhook、WebSocket、缓存 | 尚未实现或本轮禁用 | 不执行 | 不作为本轮失败 | 排除 | 排除 | — | 明确未来能力 | — | EXCLUDED |

## 结果汇总

- 清单条目：52
- PASS：27
- FIXED_AND_PASS：17
- EXCLUDED：8
- BLOCKED：0
- 测试函数：27
- Playwright 项目矩阵：desktop 27，mobile 27，共 54 个项目执行项；其中并发 401 用例按设计仅在 desktop 执行，mobile 记为 1 个 skipped。
- 唯一一次完整矩阵原始结果：desktop 27/27；mobile 21 passed、1 skipped、5 failed。5 个移动失败修复后均通过对应 targeted spec；最终 53 个可执行项目都有通过证据，另 1 个为设计内 skipped。
- 浏览器控件证据均来自隔离 Playwright；DST 同时由后端专项覆盖。

## 问题严重度台账

| 问题 ID | 严重度 | 失败场景 | 修复文件 | 自动化用例 | 最终结果 |
|---|---|---|---|---|---|
| R17-P1-01 | P1 | 并发 401 可能重复清理、提示或导航，手动退出后的旧 401 可能误提示 | `session-expiry.ts`、`client.ts`、`auth.ts` | `concurrent business 401`、`stale 401 after logout` | FIXED_AND_PASS |
| R17-P1-02 | P1 | 单一推荐 busy 状态不能安全支持两卡并发，先完成请求可能解除另一卡锁 | `RecommendationsView.vue` | `independent feedback locks` | FIXED_AND_PASS |
| R17-P1-03 | P1 | A 卡片主操作等待反馈时 B 仍可点击并覆盖 busy key，导致跨卡片重复写入或导航 | `RecommendationsView.vue` | `recommendation feedback locks...` 定向 desktop/mobile | FIXED_AND_PASS |
| R17-P2-01 | P2 | 注册协议默认勾选且确认密码/显隐证据不足 | `RegisterView.vue` | `register agreement` | FIXED_AND_PASS |
| R17-P2-02 | P2 | AI 展示区固定动态指标没有真实数据来源 | `AuthShowcase.vue` | `dashboard shortcuts` | FIXED_AND_PASS |
| R17-P2-03 | P2 | 日历周导航没有浏览器历史，eventId 直链不能完整恢复 | `CalendarView.vue` | `calendar navigation`、`calendar sync ICS` | FIXED_AND_PASS |
| R17-P2-04 | P2 | 今日任务日期和 taskId 不能完整 URL 恢复 | `TodayTasksView.vue` | `today task URL` | FIXED_AND_PASS |
| R17-P2-05 | P2 | 当前用户零课程时，非法推荐 courseId 错误会被空状态遮挡 | `RecommendationsView.vue` | `complete A/B/A isolation` | FIXED_AND_PASS |
| R17-P2-06 | P2 | 浏览器请求缺失 favicon 产生未声明控制台资源错误 | `index.html` | 全局 console fixture | FIXED_AND_PASS |
| R17-P2-07 | P2 | E2E helper 持久注入旧 Token，破坏同页 A/B 切换证据 | `e2e/helpers/api.ts` | `complete A/B/A isolation` | FIXED_AND_PASS |
| R17-P2-08 | P2 | 全局搜索长列表高亮项不会自动滚入视区 | `QuickSearch.vue` | `quick-search keyboard scroll` | FIXED_AND_PASS |
| R17-P2-09 | P2 | 推荐失败后的刷新/重试可能重复请求 | `RecommendationsView.vue` | `recommendation errors recover` | FIXED_AND_PASS |
| R17-P2-10 | P2 | 日历导航名和页面 eyebrow 不一致 | `CalendarView.vue`、路由元数据 | `all 18 production routes` | FIXED_AND_PASS |
| R17-P2-11 | P2 | 登录页曾存在无行为的辅助按钮 | `LoginView.vue` | `auth-shell` | FIXED_AND_PASS |
| R17-P2-12 | P2 | DST 春季不存在本地时间可能被静默归一化 | `calendar.py`、`test_calendar_mcp.py` | `nonexistent_dst_local_time` | FIXED_AND_PASS |
| R17-P2-13 | P2 | 移动问答页隐藏引用区域，无法查看引用或无引用状态 | `ChatView.vue` | `chat persistence` mobile | FIXED_AND_PASS |
| R17-P2-14 | P2 | 移动练习长选项换行后覆盖“下一题”触摸区域 | `PracticeView.vue` | `practice retries...` mobile | FIXED_AND_PASS |
| R17-P2-15 | P2 | 移动日历周导航溢出，dialog 子控件在触摸仿真下命中父 overlay | `CalendarView.vue`、`e2e/helpers/ui.ts` | `calendar navigation...` mobile | FIXED_AND_PASS |
| R17-P2-16 | P2 | 移动周报日期 popper 遮挡创建按钮，E2E 未等待面板关闭 | `statistics-tasks-calendar.spec.ts` | `async task filters...` mobile | FIXED_AND_PASS |

严重度统计：P0 = 0，P1 = 3，P2 = 16。每项均有修复文件、自动化用例和最终结果；没有以删除可见功能规避验收。
