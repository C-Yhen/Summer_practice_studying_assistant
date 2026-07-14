# 11. MCP 工具设计

## 是什么与边界

MCP Server 把学习系统的能力包装成 Agent 可发现、可校验的工具。它不是绕过后端的“数据库遥控器”：所有工具都从可信认证上下文获得 `user_id`，复用服务层权限和事务，不允许调用方通过参数冒充别的用户。

每次工具调用遵循：

```text
Agent 选择工具 → MCP Schema 校验 → 身份/权限/资源归属校验
→ 若有副作用：生成预览和确认令牌 → 用户确认
→ 幂等执行 → 标准化结果 → 写 mcp_tool_calls 审计日志
```

## 统一输入和输出

MCP 传输层认证后产生以下可信上下文；它不作为模型可自由填写的普通工具参数：

```json
{
  "auth_context": {
    "user_id": 1001,
    "agent_run_id": "ar_01J...",
    "scopes": ["course:read", "plan:write", "calendar:write"]
  },
  "arguments": {},
  "meta": {
    "request_id": "req_01J...",
    "idempotency_key": "required-for-write",
    "confirmation_token": "required-after-preview"
  }
}
```

统一成功/失败外壳：

```json
{
  "ok": true,
  "data": {},
  "meta": {"tool_call_id": 8891, "request_id": "req_01J...", "cached": false}
}
```

```json
{
  "ok": false,
  "error": {
    "code": "CONFIRMATION_REQUIRED",
    "message": "请先确认将创建 7 个日历事件",
    "retryable": false,
    "details": {"preview_id": "pv_123"}
  },
  "meta": {"tool_call_id": 8891, "request_id": "req_01J..."}
}
```

## 18 个工具逐项定义

说明：所有工具都必须登录并写调用日志。“确认”指 Agent/MCP 发起副作用操作前的显式确认；用户直接在页面点击“完成任务”可视为该次操作的明确意图，但仍需权限校验和幂等。

| # | 工具与作用 | 输入参数 | 输出参数 | 权限/写入/确认 | 错误处理 | 幂等要求 |
|---:|---|---|---|---|---|---|
| 1 | `get_user_courses`：列出当前用户课程 | `status?`, `page=1`, `page_size<=100` | `items[{course_id,name,exam_date,role,progress}]`, `total` | `course:read`；只读；否 | 参数错 `VALIDATION_ERROR`；无权限的课程不返回 | 天然幂等；可短缓存 |
| 2 | `get_user_profile`：取课程级学习画像 | `course_id`, `include_preferences=false` | `level`, `weak_points`, `preferences?`, `confidence`, `updated_at` | `profile:read` 且课程成员；只读；否 | 画像未生成返回 `PROFILE_NOT_READY`，可建议初测 | 天然幂等；按画像版本缓存 |
| 3 | `get_learning_history`：查询学习记录 | `course_id`, `start_at`, `end_at`, `page`, `page_size` | 记录列表、总时长、完成率、分页 | `learning:read`；只读；否 | 日期跨度超 90 天要求缩小；资源归属校验 | 天然幂等；短 TTL |
| 4 | `get_knowledge_mastery`：查询掌握度 | `course_id`, `knowledge_point_ids?` | `items[{id,name,score,confidence,evidence_count,trend}]` | `mastery:read`；只读；否 | 无证据返回低置信度默认值，不伪造分数 | 天然幂等；按掌握度版本缓存 |
| 5 | `get_study_plan`：获取当前或指定计划版本 | `course_id`, `version?`, `date_from?`, `date_to?` | 计划元数据、任务、风险 | `plan:read`；只读；否 | 不存在 `PLAN_NOT_FOUND`；不能读取他人计划 | 天然幂等；按版本缓存 |
| 6 | `get_today_tasks`：获取当地日期的任务 | `course_id?`, `date?`（默认用户时区今天） | `items`, `total_estimated_minutes`, `completion_rate` | `task:read`；只读；否 | 时区无效回退用户设置并警告；计划未激活返回空列表 | 天然幂等；短 TTL |
| 7 | `create_study_task`：创建学习任务 | `course_id`, `plan_version_id?`, `name`, `type`, `date`, `minutes`, `knowledge_point_id?`, `priority`, `preview_only` | 预览或 `task_id`, `status`, `created_at` | `task:write`；写；**是** | 时间过载/冲突返回预览警告；令牌过期重新预览 | 必须提供幂等键；唯一约束防重复 |
| 8 | `update_task_status`：完成/跳过/恢复任务 | `task_id`, `target_status`, `actual_minutes?`, `completed_at?`, `preview_only` | 任务新状态、掌握度更新任务 ID | `task:write` 且任务归属；写；Agent 调用**是** | 非法状态转换 `TASK_STATE_CONFLICT`；版本冲突返回最新值 | 幂等键 + `expected_updated_at` 乐观锁；重复目标状态返回原结果 |
| 9 | `get_wrong_questions`：查询错题 | `course_id`, `knowledge_point_id?`, `status?`, `page` | 错题、错误次数、最近答案、解析 | `question:read`；只读；否 | 题目已下架仍可返回快照但标记不可练习 | 天然幂等；短 TTL |
| 10 | `recommend_resources`：推荐资料/章节 | `course_id`, `knowledge_point_id?`, `available_minutes?`, `limit<=20` | 资源、分数分解、理由、`recommendation_record_id` | `recommendation:read`；逻辑只读但会记曝光；否 | 候选为空返回原因；不跨课程泄露 | 同一 `request_id+item` 曝光只记一次；结果按上下文版本幂等 |
| 11 | `recommend_exercises`：推荐练习题 | `course_id`, `knowledge_point_id?`, `difficulty?`, `count<=50` | 题目摘要、预计时长、分数和理由 | `recommendation:read`；记录曝光；否 | 过滤已泄露答案的题；候选不足明确返回实际数量 | 同上；请求幂等避免重复曝光 |
| 12 | `search_course_material`：搜索课件 | `course_id`, `query`, `document_ids?`, `top_k<=20`, `strict_current_version=true` | 片段、相似度、文档、页码/章节 | `material:read` 且文档归属；只读；否 | 文档未 ready 返回 `DOCUMENT_NOT_READY`；无命中返回空 | 按查询与版本指纹天然幂等；可缓存 |
| 13 | `get_available_time`：合并偏好和日历空闲时间 | `start_at`, `end_at`, `minimum_minutes`, `calendar_account_id?` | 空闲时段、来源、时区、冲突 | `calendar:read`；只读；首次访问可能需第三方授权，不是写确认 | Token 过期返回 `CALENDAR_REAUTH_REQUIRED`；服务异常可退回用户设置并标警告 | 同一时间窗幂等；短 TTL |
| 14 | `create_calendar_event`：创建日历事件 | `account_id`, `title`, `start_at`, `end_at`, `timezone`, `task_id?`, `preview_only` | 预览或本地事件 ID、第三方事件 ID、同步状态 | `calendar:write` 且账号归属；写；**是** | 冲突返回可选时段；超时后先按幂等键查询再决定重试 | 强制幂等键；本地唯一 `(account_id, provider_event_id)` |
| 15 | `update_calendar_event`：修改日历事件 | `calendar_event_id`, `patch`, `expected_version`, `preview_only` | 前后差异、新版本、同步状态 | `calendar:write` 且事件归属；写；**是** | 第三方已删 `REMOTE_NOT_FOUND`；版本冲突返回远端快照 | 幂等键 + 版本号；重复 patch 返回当前结果 |
| 16 | `delete_calendar_event`：删除日历事件 | `calendar_event_id`, `reason?`, `preview_only` | `deleted=true`, 本地/远端状态 | `calendar:write` 且事件归属；写；**是** | 远端已不存在视为幂等成功；本地保留软删记录 | 强制幂等键；重复删除成功 |
| 17 | `reschedule_study_plan`：生成/确认重排 | `course_id`, `reason`, `constraints?`, `base_version`, `preview_only` | 调整原因、差异、风险；确认后返回新版本 | `plan:write`；写；**是** | 基础版本已变化 `PLAN_VERSION_CONFLICT`；容量不足返回风险方案 | 预览按输入哈希复用；确认需幂等键和一次性令牌 |
| 18 | `generate_weekly_report`：生成周报 | `course_id`, `week_start`, `preview_only?` | `async_task_id`，完成后报告 ID/摘要 | `report:write`（产生报告）；写；首次提交**是** | 已有同周报告则返回已有任务/报告；失败可重试 | 唯一 `(user,course,week_start,algorithm_version)`；任务幂等 |

## 权限模型

- `owner/student/teacher/admin` 只是角色，实际检查细分 scope 和资源归属；普通学生只能读写自己的画像、计划、记录和日历账号。
- 所有 ID 都先按 `user_id/tenant_id` 过滤再查询，不能先查询对象后只在前端隐藏。
- 教师可读班级数据属于第三阶段，默认接口不开放。
- MCP Server 与 FastAPI 之间使用短期服务凭证，并继续透传已验证的最终用户身份；服务凭证不能替代用户权限。

## 确认协议

1. 写工具第一次以 `preview_only=true` 调用，后端执行完整校验但不产生副作用。
2. 返回人可读差异、风险、预计写入对象数和 `preview_id`。
3. 用户在前端明确点击确认；服务端生成 5 分钟有效、绑定 `user_id + tool + normalized_args_hash + preview_id` 的一次性令牌。
4. 执行时必须同时提交确认令牌和 `Idempotency-Key`；参数变更一位也需重新确认。
5. 事务成功后消费令牌；网络重试使用同一幂等键，返回第一次结果。
6. 日历批量同步展示全部事件；部分失败时返回逐项状态，不自动反复创建。

18 个首发工具没有“删除学习任务”和“发送邮件/消息”工具：删除学习任务统一映射为受控的任务取消接口；未来若增加 `send_notification` 等工具，也必须使用同一预览/确认协议。也就是说，创建学习任务、修改计划、取消/删除任务、创建/修改/删除日历事件、发送邮件或消息都不能由 Agent 静默执行。

## 调用日志

每次调用在开始时插入 `mcp_tool_calls(status='running')`，结束时更新；记录 `user_id, agent_run_id, tool_name, arguments_json, result_json, status, error_code, error_message, is_write, confirmation_id, idempotency_key_hash, started_at, ended_at, duration_ms, request_id`。

安全要求：密码、JWT、OAuth Token、文件密钥和确认令牌不落日志；通过字段白名单/脱敏器处理。大输出只存摘要与对象存储地址。即使 Schema 校验失败也记录工具名、请求 ID 和脱敏错误。日志本身只允许本人查看摘要、管理员审计，默认保存 90～180 天。

## 统一错误分类

| 类型 | 示例 | 是否自动重试 |
|---|---|---|
| 参数/权限 | `VALIDATION_ERROR`, `FORBIDDEN` | 否 |
| 需要确认 | `CONFIRMATION_REQUIRED/EXPIRED` | 否，重新展示/确认 |
| 资源冲突 | `PLAN_VERSION_CONFLICT`, `TASK_STATE_CONFLICT` | 否，读取新状态再决定 |
| 临时外部错误 | `PROVIDER_TIMEOUT`, `RATE_LIMITED` | 只读可指数退避；写操作先查幂等结果 |
| 永久外部错误 | `CALENDAR_REAUTH_REQUIRED` | 否，引导重新授权 |
| 内部错误 | `INTERNAL_ERROR` + `request_id` | 后台记录；仅对可重入任务有限重试 |

# 12. 第三方服务设计

## 统一适配层

业务层只依赖抽象接口和内部 DTO：

```python
class LLMProvider(Protocol):
    async def chat_json(self, messages, response_schema, options) -> dict: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class CalendarProvider(Protocol):
    async def list_events(self, account, start_at, end_at) -> list[CalendarEventDTO]: ...
    async def create_event(self, account, event, idempotency_key) -> CalendarEventDTO: ...
    async def update_event(self, account, remote_id, patch, version) -> CalendarEventDTO: ...
    async def delete_event(self, account, remote_id) -> None: ...

class ObjectStorageProvider(Protocol):
    async def put(self, key, stream, content_type) -> StoredObjectDTO: ...
    async def signed_get_url(self, key, expires_seconds) -> str: ...

class NotificationProvider(Protocol):
    async def send(self, recipient, template_id, variables, idempotency_key) -> SendResult: ...

class SearchProvider(Protocol):
    async def search_learning_resources(self, query, filters, limit) -> list[SearchResultDTO]: ...
```

可实现 `OpenAICompatibleLLMProvider` 连接 DeepSeek、通义千问、智谱或其他兼容服务；日历可实现学校日历/Google/Microsoft 等 Provider；本地开发用 `LocalStorageProvider`，答辩可选 MinIO。Embedding 与 Chat Provider 可以不同，但各自模型名称和维度必须配置化、版本化。

公开学习资源搜索是可选扩展：只接入许可清晰的 API，保存来源 URL、标题、摘要、许可/抓取时间，并在推荐前做课程相关性和安全过滤；不得把搜索摘要当作用户课件证据混入“严格资料模式”。

## 调用链

```text
Service → ProviderRegistry(按配置选择) → Provider DTO 转换
        → 超时/限流/重试/熔断 → 厂商 SDK/API
        → 标准结果或 ProviderError → 业务层决定降级
```

## 稳定性策略

| 风险 | 实现方式 |
|---|---|
| API 超时 | 连接超时 3～5 秒、总超时按场景配置；LLM 30～90 秒，日历 10 秒；绝不无限等待 |
| 请求重试 | 仅对 429、网络中断、部分 5xx 指数退避并加入随机抖动；默认最多 3 次 |
| 写操作重复 | 写请求带幂等键；超时后先查询远端/本地映射，确认未创建再重试 |
| Token 过期 | 加密保存 refresh token，单账号加锁刷新；失败将账号标为 `reauth_required` |
| 权限不足 | 转为标准 `PROVIDER_PERMISSION_DENIED`，前端引导重新授权，不扩大 scope |
| 限流 | 读响应短缓存；队列削峰；尊重 `Retry-After`；按用户和 Provider 双层限额 |
| 服务不可用 | 熔断器打开后快速失败；RAG 可切备用模型或返回稍后重试，规则计划可无 LLM 运行 |
| 数据同步失败 | `calendar_events.sync_status` 记录 `pending/synced/failed/conflict`，异步补偿并可人工重试 |

## 配置和安全

- `.env` 只保存开发配置示例，真实密钥通过环境变量/密钥管理注入；日志中脱敏。
- OAuth Token 加密存储，按最小 scope 授权；注销绑定时撤销远端 Token 并软删本地账号。
- 保存 `provider`, `model`, `request_id`, token 用量、耗时和费用估计，方便切换与成本控制。
- 第三方响应先转内部 DTO 并校验；不让厂商字段渗透到核心表。

# 13. Redis 缓存设计

## 模式和原则

采用 Cache-Aside：读时先 Redis，未命中查 PostgreSQL 后写缓存；更新时先提交数据库事务，再删除相关缓存。Redis 不是权威数据源，缓存值必须携带 `schema_version/data_version/generated_at`。

## Key、TTL 与失效

| 数据 | Key | 建议 TTL | 命中条件 | 主动失效时机 |
|---|---|---:|---|---|
| 问答 | `qa:{user}:{course}:{version_fp}:{mode}:{question_hash}` | 24 小时（±10% 抖动） | 用户、范围、模式、问题、版本指纹完全一致 | 文档当前版本切换、权限变化、用户删除会话时删关联 key/版本索引 |
| RAG 检索 | `retrieval:{course}:{version_fp}:{filter_hash}:{query_hash}` | 6 小时（±10%） | Top-K、文档过滤、检索算法版本相同 | 文档更新/删除、索引重建或检索配置升级 |
| 会话状态 | `session:{user}:{session_id}` | 30 分钟滑动；最长 24 小时 | 会话归属、状态版本一致 | 登出、密码修改、会话删除 |
| 用户画像 | `profile:{user}:{course}:{profile_version}` | 30 分钟（±10%） | 画像版本一致 | 偏好、学习记录、掌握度变化后删当前别名 |
| 学习计划 | `plan:{user}:{course}:{plan_version}` | 30 分钟（±10%） | 请求的激活版本与缓存一致 | 新计划确认、任务状态/时间变化时删相关版本视图 |
| 掌握度 | `mastery:{user}:{course}:{mastery_version}` | 10 分钟（±10%） | 掌握度版本一致 | 新答题、错题状态和评测重算后删除 |
| 长任务进度 | `job:{task_id}` | 任务中 24 小时续期；结束后 7 天 | task_id 归属匹配 | 任务结束后保留短期；过期从 DB 查关键状态 |
| 可用时间 | `availability:{user}:{account}:{range_hash}` | 1～5 分钟 | 日历同步游标/账号版本一致 | 日历事件创建、修改、删除后删时间窗 |
| 空值缓存 | `null:{resource}:{owner}:{id}` | 30～60 秒 | 资源确实不存在且请求者相同 | 创建资源后删除 |
| 验证码 | `verify:{purpose}:{target_hash}` | 5 分钟 | 次数未超限 | 成功使用后立即删除 |
| 限流 | `rate:{scope}:{identity}:{window}` | 窗口 + 10 秒 | 原子计数 | 自动过期 |

`version_fp` 不是单个整数，而是本次检索允许文档的排序后 `(document_id,current_version)` 列表哈希；这样多文档任一更新都自然产生新 key。

## 读取伪代码

```python
async def get_profile(user_id, course_id):
    version = await repo.get_profile_version(user_id, course_id)
    key = f"profile:{user_id}:{course_id}:{version}"
    if value := await redis.get(key):
        return validate_cache_schema(value)

    lock = f"lock:rebuild:{key}"
    if await redis.set(lock, owner_token, nx=True, ex=10):
        try:
            value = await repo.load_profile(user_id, course_id)
            await redis.set(key, serialize(value), ex=jitter(1800))
            return value
        finally:
            await safe_unlock(lock, owner_token)  # Lua 比较 token 后删除
    return await short_wait_then_read_or_db(key)
```

## 更新与精确失效

- **文档更新**：新切块全部成功 → DB 事务切换当前版本 → 发布 `document.version.changed` → 删除文档/课程的版本别名和 key 索引。旧 key 即使未立即扫描删除，也因版本指纹不同永不命中；异步清扫回收空间。
- **计划更新**：确认新版本后删除 `plan current alias`、今日任务和可用时间相关缓存；旧版本缓存可保留供历史查询，但不能作为当前版本返回。
- **学习记录变化**：提交答题/完成任务后删除掌握度、画像、推荐候选、统计和今日任务缓存；建议用事件消费者集中处理，避免漏删。
- 为避免 Redis `KEYS` 扫描，写缓存时同时把 key 加入集合，如 `idx:doc:{document_id}:cache_keys`，或主要依靠版本化 key + 定期清理。

## 三类经典缓存问题

1. **穿透（查不存在的 ID）**：所有 ID 先校验格式和权限；对确定不存在的资源缓存短 TTL 空值；接口限流。布隆过滤器是数据量很大后的加分项。
2. **击穿（热点 key 突然过期）**：单飞锁只允许一个请求回源；其他请求短等或返回短期旧值；热点缓存可提前刷新。
3. **雪崩（大量 key 同时过期）**：TTL 增加随机抖动；分批预热；Redis 异常时限速降级；不要为所有课程使用完全相同过期时间。

## 分布式锁和热点保护

- 锁通过 `SET key random_token NX PX ttl` 获取，用 Lua “值等于 token 才删除”；业务执行可能超过 TTL 时由受控看门狗续期。
- 文档建库锁：`lock:document:{document_id}:version:{version}`；计划调整锁：`lock:plan:{user}:{course}`；Token 刷新锁：`lock:oauth:{account_id}`。
- Redis 锁只是并发优化，最终仍依赖数据库唯一约束、乐观锁和幂等表保证正确性。
- 热点问答设置每用户/课程限流、并发信号量、较长 TTL；模型服务拥塞时进入排队或明确返回 `429/503`。

## 数据保护

缓存 JSON 不放密码、OAuth Token、完整 JWT 和不必要的个人信息；Key 中对邮箱/手机号哈希。任务进度接口仍需校验 `async_tasks.user_id`，知道 task_id 不能直接读取他人进度。

# 14. Celery 长时任务设计

## 哪些任务异步化

大型 PDF/PPT/Word 解析、切块、批量 Embedding、向量索引重建、课程知识点提取、批量生成题/分析错题、长期计划/大规模重排、周报/阶段报告和批量日历同步。普通 CRUD 和单次轻量查询不应为了“技术亮点”强行异步。

## 输入、处理、输出

- 输入：`task_type`、资源 ID/版本、标准化参数、用户 ID、幂等键；大文件只传对象存储 key，不放入 Celery 消息。
- 处理：FastAPI 创建 `async_tasks`，事务提交后投递；Worker 逐阶段执行，在 Redis 高频更新进度，在 DB 低频保存关键检查点。
- 输出：立即返回 `task_id/status_url/ws_channel`；完成后 DB 保存结果引用，Redis 保留短期进度并创建站内通知。

## 状态机

```text
queued → processing → success
   │         ├──────→ waiting_for_user → processing
   │         ├──────→ retrying ────────→ processing
   │         ├──────→ failed
   └─────────┴──────→ cancelled
```

只有合法状态转换才能更新；取消采用协作式取消：API 将 `cancel_requested_at` 写 DB/Redis，Worker 在安全检查点停止。已经提交的数据库小事务不强制回滚，但未完成的新文档版本不得切换为当前版本。

## 提交流程与“事务后投递”

1. API 校验 JWT、资源归属、额度和参数。
2. 用 `(user_id, task_type, idempotency_key)` 唯一约束查重。
3. 数据库事务创建 `async_tasks(status='queued')`，必要时创建业务草稿。
4. 事务提交后投递 Celery；若投递失败，将 `dispatch_status='failed'`，由补偿扫描器重投，不能丢任务。
5. 返回 `202 Accepted`，前端通过 WebSocket 或 `GET /async-tasks/{id}` 轮询。

## 文档解析任务阶段

| 进度 | current_step | 操作 |
|---:|---|---|
| 0～5 | `validating` | 校验版本、文件存在、幂等和取消状态 |
| 5～30 | `extracting` | 解析文本、页码、章节；分页写临时结果 |
| 30～40 | `cleaning` | 清洗并计算内容哈希 |
| 40～55 | `chunking` | 生成切块和元数据 |
| 55～90 | `embedding` | 例如每批 32 条调用 Provider，批次可重试 |
| 90～97 | `persisting` | 批量 upsert 切块；唯一键防重复 |
| 97～100 | `activating` | 抽样校验，事务切当前版本，失效缓存，ready |

## 重试、超时和恢复

- Celery 软/硬超时按任务类型设置，例如解析 15/20 分钟，周报 3/5 分钟；超时保存失败阶段。
- 网络/429/可恢复 5xx 指数退避重试，默认最大 3 次；文件损坏、Schema 错误、权限不足不重试。
- 每个阶段使用确定性幂等键，如 `document_id:version:chunk_index:embedding_model_version`；数据库唯一约束和 upsert 防止重复。
- Worker 崩溃后从 `checkpoint_json/current_step` 恢复，不重新创建整个版本；任务运行前再次校验资源仍归属用户且未删除。
- 失败保留 `error_code + 脱敏 error_message + trace_id`；前端显示可理解建议，堆栈只进服务日志。

## 队列隔离和并发

- `document`：解析和切块，CPU/内存较高。
- `embedding`：外部 API、限流敏感，可按 Provider 单独限速。
- `planning`：长期计划和批量重排。
- `report`：周报/阶段报告。
- `integration`：日历和通知。

不同队列设置独立 Worker 并发和预取数，避免一个大 PDF 堵住日历同步。MVP 可运行一个 Worker，但代码仍按任务路由组织。

## 进度接口与 WebSocket

Redis `job:{task_id}` 保存 `status/progress/current_step/message/updated_at`；DB 保存关键状态。WebSocket 只推送“状态发生变化”，断线后前端先通过 REST 取最新状态再订阅。进度应单调不下降；同一用户高频更新限为每 0.5～1 秒一次。

## 典型任务结果

```json
{
  "task_id": "01J2TASK...",
  "task_type": "parse_document",
  "status": "processing",
  "progress": 68,
  "current_step": "embedding",
  "message": "已生成 136/200 个文本块向量",
  "retry_count": 1,
  "can_cancel": true,
  "created_at": "2026-07-14T09:00:00+08:00",
  "updated_at": "2026-07-14T09:02:21+08:00"
}
```
