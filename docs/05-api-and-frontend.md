# 17. API 接口设计

## 通用约定

- Base URL：`/api/v1`；JSON 使用 `snake_case`；时间为带时区 ISO 8601；分页为 `page/page_size`（最大 100）。
- 除注册、登录、健康检查外，使用 `Authorization: Bearer <JWT>`。JWT 只表示身份，接口仍必须检查课程/文档/计划/任务归属。
- 所有写接口接收 `Idempotency-Key`；更新接口可带 `If-Match`/`expected_updated_at` 做乐观锁。
- 创建任务、计划调整确认、破坏性删除和日历写操作使用“预览 → 一次性确认令牌 → 执行”。确认令牌绑定用户、动作、参数哈希，5 分钟过期。
- 长时任务返回 HTTP `202` 和 `async_task_id`；不能返回假完成。缓存命中可在 `meta.cached` 标记。
- 响应统一：`{"data": ..., "meta": {"request_id":"..."}}`；错误统一：

```json
{
  "error": {
    "code": "DOCUMENT_NOT_READY",
    "message": "文档仍在解析中",
    "details": {"document_id": 21, "status": "embedding"}
  },
  "meta": {"request_id": "req_01J..."}
}
```

常用 HTTP/业务错误：`400 VALIDATION_ERROR`、`401 AUTH_INVALID`、`403 FORBIDDEN`、`404 *_NOT_FOUND`、`409 VERSION_CONFLICT/STATE_CONFLICT`、`422 LLM_SCHEMA_INVALID`、`429 RATE_LIMITED`、`503 PROVIDER_UNAVAILABLE`、`500 INTERNAL_ERROR`。下表只列接口特有错误。

## REST API 总表

表中“Redis/长任务/确认”依次表示是否读取或失效 Redis、是否返回异步任务、是否需要确认令牌；`—` 表示无请求体。

### 用户

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON（`data` 内） | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /auth/register` | `{"email":"u@example.com","password":"***","display_name":"小夏"}` | `{"user":{"id":1001,"email":"u@example.com"},"access_token":"...","refresh_token":"..."}` | `EMAIL_EXISTS`, `WEAK_PASSWORD` | 否 | 否/否/否 |
| `POST /auth/login` | `{"email":"u@example.com","password":"***"}` | `{"access_token":"...","refresh_token":"...","expires_in":1800,"user":{"id":1001}}` | `CREDENTIALS_INVALID`, `USER_DISABLED` | 否 | 会话/否/否 |
| `GET /users/me` | — | `{"id":1001,"display_name":"小夏","timezone":"Asia/Shanghai","preferences":{...}}` | `USER_NOT_FOUND` | 是 | 画像/否/否 |
| `PATCH /users/me/preferences` | `{"foundation_level":"basic","daily_minutes":120,"session_minutes":45,"learning_order":"explain_first"}` | `{"preference_version":3,"updated_at":"..."}` | `PREFERENCE_INVALID` | 是 | 失效画像/否/否 |
| `GET /users/me/statistics` | Query `course_id?,start_date?,end_date?` | `{"study_minutes":620,"task_completion_rate":0.78,"accuracy":0.71,"trend":[...]}` | `DATE_RANGE_TOO_LARGE` | 是 | 是/否/否 |

### 课程

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /courses` | `{"name":"数据库系统","description":"...","exam_at":"2026-07-21T09:00:00+08:00","target_score":85}` | `{"id":12,"name":"数据库系统","role":"owner","status":"active"}` | `COURSE_NAME_EXISTS` | 是 | 失效课程/否/否 |
| `GET /courses` | Query `status?,page,page_size` | `{"items":[{"id":12,"name":"数据库系统","progress":0.32}],"total":1}` | — | 是 | 是/否/否 |
| `GET /courses/{course_id}` | Path `course_id` | `{"id":12,"exam_at":"...","target_score":85,"document_count":2,"weak_points":[...]}` | `COURSE_NOT_FOUND` | 是 | 是/否/否 |
| `PATCH /courses/{course_id}` | `{"name":"数据库原理","target_score":90}` | `{"id":12,"name":"数据库原理","updated_at":"..."}` | `COURSE_VERSION_CONFLICT` | 是 | 失效课程/否/否 |
| `DELETE /courses/{course_id}` | `{"preview_only":false,"reason":"不再学习"}` + 确认头 | `{"id":12,"status":"deleted","cleanup_task_id":"..."}` | `COURSE_HAS_ACTIVE_TASKS`, `CONFIRMATION_REQUIRED` | 是 | 失效/可能/是 |
| `PUT /courses/{course_id}/exam-date` | `{"exam_at":"2026-07-21T09:00:00+08:00","timezone":"Asia/Shanghai"}` | `{"exam_at":"...","plan_adjustment_suggested":true}` | `EXAM_DATE_INVALID` | 是 | 失效计划/否/否 |

### 文档

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /courses/{course_id}/documents` | `multipart/form-data`: `file`, `title?`; 无 JSON | `{"document_id":21,"version":1,"status":"uploaded","async_task_id":"..."}` | `FILE_TYPE_UNSUPPORTED`, `FILE_TOO_LARGE`, `MIME_MISMATCH` | 是 | 否/是/否 |
| `GET /courses/{course_id}/documents` | Query `status?,type?,page,page_size` | `{"items":[{"id":21,"title":"第3章.pdf","current_version":1,"status":"ready"}],"total":1}` | `COURSE_NOT_FOUND` | 是 | 是/否/否 |
| `GET /documents/{document_id}` | — | `{"id":21,"status":"embedding","current_version":null,"versions":[...]}` | `DOCUMENT_NOT_FOUND` | 是 | 是/否/否 |
| `DELETE /documents/{document_id}` | `{"preview_only":false}` + 确认头 | `{"id":21,"status":"deleted","cleanup_task_id":"..."}` | `CONFIRMATION_REQUIRED` | 是 | 清 QA/检索/是/是 |
| `POST /documents/{document_id}/reparse` | `{"version":1,"parser_options":{},"preview_only":false}` | `{"async_task_id":"...","status":"queued"}` | `DOCUMENT_BUSY`, `VERSION_NOT_FOUND` | 是 | 完成后清理/是/是 |
| `GET /documents/{document_id}/tasks/latest` | — | `{"task_id":"...","status":"processing","progress":68,"current_step":"embedding"}` | `TASK_NOT_FOUND` | 是 | 进度/否/否 |

### RAG 问答

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /courses/{course_id}/chat-sessions` | `{"title":"范式复习","mode":"strict","document_ids":[21]}` | `{"session_id":"...","mode":"strict"}` | `DOCUMENT_SCOPE_INVALID` | 是 | 会话/否/否 |
| `POST /chat-sessions/{session_id}/messages` | `{"question":"什么是第三范式？","mode":"strict","document_ids":[21],"top_k":6}` | `{"message_id":"...","answer":"...","sufficient_evidence":true,"citations":[{"source_id":"S2","document_id":21,"document_name":"第3章.pdf","version":1,"page_number":18,"chapter_name":"3NF","quote":"..."}]}` | `DOCUMENT_NOT_READY`, `NO_RETRIEVABLE_DOCUMENT`, `LLM_SCHEMA_INVALID` | 是 | QA+检索/否/否 |
| `GET /chat-sessions/{session_id}/messages` | Query `cursor?,limit<=100` | `{"items":[{"id":"...","role":"user","content":"..."}],"next_cursor":null}` | `SESSION_NOT_FOUND` | 是 | 会话/否/否 |
| `GET /chat-messages/{message_id}/citations` | — | `{"items":[{"chunk_id":301,"document_name":"第3章.pdf","page_number":18,"quote":"...","version_valid":true}]}` | `MESSAGE_NOT_FOUND` | 是 | 是/否/否 |
| `DELETE /chat-sessions/{session_id}` | `{"preview_only":false}` + 确认头 | `{"session_id":"...","deleted":true}` | `CONFIRMATION_REQUIRED` | 是 | 清会话/否/是 |

### 学习计划与任务

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /courses/{course_id}/study-plans/generate` | `{"start_date":"2026-07-15","end_date":"2026-07-21","daily_availability":{"default_minutes":120},"unavailable_dates":[],"session_minutes":45,"goal":"达到85分"}` | `{"async_task_id":"...","status":"queued"}` | `INSUFFICIENT_INPUT`, `EXAM_DATE_INVALID` | 是 | 完成后写/是/否（只生成草案） |
| `GET /courses/{course_id}/study-plans/current` | Query `date_from?,date_to?` | `{"plan_id":41,"version":2,"status":"active","tasks":[...],"risks":[]}` | `PLAN_NOT_FOUND` | 是 | 计划/否/否 |
| `POST /study-plans/{plan_id}/adjustments` | `{"reason":"每天只能学习60分钟","constraints":{"daily_minutes":60},"base_version":2}` | `{"async_task_id":"...","candidate_version":3}` | `PLAN_VERSION_CONFLICT` | 是 | 是/可能/否（只生成草案） |
| `POST /study-plans/{plan_id}/versions/{version}/confirm` | `{"preview_id":"pv_123","expected_base_version":2}` + 确认头 | `{"plan_id":41,"active_version":3,"previous_version":2,"calendar_sync_required":true}` | `CONFIRMATION_REQUIRED`, `PLAN_VERSION_CONFLICT` | 是 | 失效/否/是 |
| `GET /study-plans/{plan_id}/versions` | Query `page,page_size` | `{"items":[{"version":3,"status":"active","reason":"..."},{"version":2,"status":"superseded"}],"total":3}` | `PLAN_NOT_FOUND` | 是 | 是/否/否 |
| `GET /study-plans/{plan_id}/versions/{version}/diff` | Query `compare_to?` | `{"added":[...],"removed":[...],"rescheduled":[...],"minutes_change":-120,"risks":[...]}` | `VERSION_NOT_FOUND` | 是 | 是/否/否 |
| `POST /study-tasks/{task_id}/complete` | `{"actual_minutes":48,"completed_at":"2026-07-15T20:48:00+08:00"}` | `{"task_id":801,"status":"completed","mastery_update_task_id":"..."}` | `TASK_STATE_CONFLICT` | 是 | 失效掌握度/否/否（点击即意图） |
| `POST /study-tasks/{task_id}/delay` | `{"to_date":"2026-07-17","reason":"临时有课","expected_updated_at":"..."}` | `{"task_id":801,"old_date":"2026-07-16","new_date":"2026-07-17","overload_warning":false}` | `DATE_OVERLOADED`, `TASK_VERSION_CONFLICT` | 是 | 失效计划/否/否 |
| `POST /study-tasks/{task_id}/cancel` | `{"reason":"内容已掌握","preview_only":false}` + 确认头 | `{"task_id":801,"status":"cancelled"}` | `CONFIRMATION_REQUIRED`, `TASK_STATE_CONFLICT` | 是 | 失效计划/否/是 |

### 推荐系统

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `GET /courses/{course_id}/recommendations/resources` | Query `knowledge_point_id?,available_minutes?,limit<=20` | `{"items":[{"record_id":991,"resource_id":91,"score":86.5,"reason":"...","score_breakdown":{...}}]}` | `NO_CANDIDATE`（也可 200 空列表） | 是 | 画像/否/否 |
| `GET /courses/{course_id}/recommendations/exercises` | Query `knowledge_point_id?,difficulty?,count<=50` | `{"items":[{"record_id":992,"question_id":501,"difficulty":"basic","reason":"..."}]}` | — | 是 | 画像/否/否 |
| `POST /recommendations/{record_id}/feedback` | `{"action":"clicked","rating":null,"occurred_at":"..."}` | `{"record_id":991,"accepted":true}` | `FEEDBACK_INVALID` | 是 | 失效推荐/否/否 |
| `GET /recommendations/{record_id}/reason` | — | `{"reason":"...","facts":[...],"score_breakdown":{...},"algorithm_version":"rule-v1"}` | `RECOMMENDATION_NOT_FOUND` | 是 | 是/否/否 |
| `GET /courses/{course_id}/recommendations/history` | Query `item_type?,start_at?,end_at?,page` | `{"items":[...],"total":25,"metrics":{"ctr":0.32,"completion_rate":0.18}}` | `DATE_RANGE_TOO_LARGE` | 是 | 是/否/否 |

### 题目和错题

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `GET /courses/{course_id}/questions` | Query `knowledge_point_id?,difficulty?,type?,limit` | `{"items":[{"id":501,"stem":"...","options":[...]}]}`（不返回答案） | — | 是 | 是/否/否 |
| `POST /questions/{question_id}/attempts` | `{"answer":{"selected":["B"]},"duration_seconds":90,"task_id":801}` | `{"attempt_id":7001,"is_correct":false,"score":0,"correct_answer":{"selected":["A"]},"explanation":"...","mastery_update_task_id":"..."}` | `QUESTION_NOT_PUBLISHED`, `DUPLICATE_ATTEMPT` | 是 | 失效掌握度/否/否 |
| `GET /question-attempts/{attempt_id}` | — | `{"id":7001,"question":{...},"submitted_answer":{...},"is_correct":false,"explanation":"..."}` | `ATTEMPT_NOT_FOUND` | 是 | 是/否/否 |
| `GET /courses/{course_id}/wrong-questions` | Query `knowledge_point_id?,status?,page` | `{"items":[{"wrong_id":71,"question":{...},"wrong_count":2,"status":"active"}],"total":8}` | — | 是 | 是/否/否 |
| `DELETE /wrong-questions/{wrong_id}` | `{"preview_only":false}` + 确认头 | `{"wrong_id":71,"removed":true}` | `CONFIRMATION_REQUIRED` | 是 | 失效错题/否/是 |
| `POST /wrong-questions/{wrong_id}/master` | `{"evidence_attempt_id":7002}` | `{"wrong_id":71,"status":"mastered","mastered_at":"..."}` | `MASTERY_EVIDENCE_REQUIRED` | 是 | 失效掌握度/否/否 |

### 学习记录

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /learning-sessions/start` | `{"course_id":12,"task_id":801,"knowledge_point_id":31}` | `{"learning_session_id":"ls_...","started_at":"..."}` | `SESSION_ALREADY_ACTIVE` | 是 | 会话/否/否 |
| `POST /learning-sessions/{id}/end` | `{"ended_at":"...","completed":true}` | `{"record_id":8011,"duration_seconds":2880,"accepted_seconds":2880}` | `LEARNING_SESSION_NOT_FOUND` | 是 | 失效画像/否/否 |
| `POST /learning-records` | `{"course_id":12,"task_id":801,"duration_seconds":1800,"record_type":"study","occurred_at":"..."}` | `{"record_id":8012,"accepted":true}` | `DURATION_SUSPICIOUS` | 是 | 失效画像/否/否 |
| `GET /courses/{course_id}/learning-records` | Query `start_at?,end_at?,type?,page` | `{"items":[...],"total":20,"summary":{"minutes":620}}` | `DATE_RANGE_TOO_LARGE` | 是 | 是/否/否 |
| `GET /courses/{course_id}/knowledge-mastery` | Query `knowledge_point_ids?` | `{"items":[{"knowledge_point_id":31,"score":0.48,"confidence":0.72,"trend":"up"}]}` | — | 是 | 掌握度/否/否 |

### 长时任务

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /async-tasks` | `{"task_type":"weekly_report","resource_type":"course","resource_id":"12","input_data":{"week_start":"2026-07-13"}}` | `{"task_id":"...","status":"queued","status_url":"/api/v1/async-tasks/..."}` | `TASK_TYPE_NOT_ALLOWED` | 是 | 进度/是/依任务类型 |
| `GET /async-tasks/{task_id}` | — | `{"task_id":"...","status":"processing","progress":68,"current_step":"embedding","can_cancel":true}` | `TASK_NOT_FOUND` | 是 | 进度/否/否 |
| `GET /async-tasks/{task_id}/progress` | — | `{"progress":68,"message":"136/200","updated_at":"..."}` | `TASK_NOT_FOUND` | 是 | 进度/否/否 |
| `POST /async-tasks/{task_id}/cancel` | `{"reason":"用户取消"}` | `{"task_id":"...","status":"processing","cancel_requested":true}` | `TASK_NOT_CANCELLABLE` | 是 | 进度/否/否（点击即意图） |
| `POST /async-tasks/{task_id}/retry` | `{"from_checkpoint":true}` | `{"task_id":"new-or-same-id","status":"queued","retry_count":2}` | `TASK_NOT_RETRYABLE`, `MAX_RETRIES_REACHED` | 是 | 进度/是/否 |

### MCP

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `GET /mcp/tools` | Query `scope?` | `{"items":[{"name":"get_today_tasks","description":"...","input_schema":{},"is_write":false,"requires_confirmation":false}]}` | — | 是 | 短缓存/否/否 |
| `POST /mcp/tools/{tool_name}/execute` | `{"arguments":{"course_id":12},"agent_run_id":"..."}` | `{"tool_call_id":8891,"result":{"items":[...]}}` | `TOOL_NOT_FOUND`, `TOOL_PERMISSION_DENIED` | 是 | 依工具/依工具/只允许只读 |
| `POST /mcp/tools/{tool_name}/preview` | `{"arguments":{...},"agent_run_id":"..."}` | `{"preview_id":"pv_123","summary":"将创建7个事件","changes":[...],"risks":[],"expires_at":"..."}` | `TOOL_NOT_WRITABLE`, `PREVIEW_INVALID` | 是 | 依工具/否/否 |
| `POST /mcp/tools/{tool_name}/confirm` | `{"preview_id":"pv_123","confirmation_token":"...","arguments":{...},"agent_run_id":"..."}` | `{"tool_call_id":8892,"result":{...},"idempotent_replay":false}` | `CONFIRMATION_REQUIRED/EXPIRED`, `ARGUMENTS_CHANGED` | 是 | 依工具/依工具/是 |
| `GET /mcp/tool-calls` | Query `agent_run_id?,tool_name?,status?,page` | `{"items":[{"id":8891,"tool_name":"...","status":"success","duration_ms":42}],"total":12}` | — | 是 | 否/否/否 |

### 日历

| 方法与 URL | 参数 / 请求 JSON | 响应 JSON | 特有错误 | JWT | Redis/长任务/确认 |
|---|---|---|---|:---:|---|
| `POST /calendar/accounts` | `{"provider":"microsoft","redirect_uri":"https://.../callback"}` | `{"authorization_url":"https://...","state":"opaque","expires_in":600}` | `PROVIDER_UNSUPPORTED` | 是 | OAuth state/否/否 |
| `GET /calendar/oauth/callback` | Query `code,state`；无 JSON | `{"account_id":61,"provider":"microsoft","status":"active"}` | `OAUTH_STATE_INVALID`, `OAUTH_CODE_EXPIRED` | 是（同一浏览器会话） | 清 OAuth state/否/否 |
| `GET /calendar/availability` | Query `start_at,end_at,minimum_minutes,account_id?` | `{"timezone":"Asia/Shanghai","slots":[{"start_at":"...","end_at":"...","source":"calendar"}]}` | `CALENDAR_REAUTH_REQUIRED` | 是 | 1～5 分钟/否/否 |
| `POST /study-plans/{plan_id}/calendar-sync/preview` | `{"version":3,"account_id":61}` | `{"preview_id":"pv_cal","events":[...],"conflicts":[...],"expires_at":"..."}` | `PLAN_VERSION_CONFLICT` | 是 | 是/可能/否 |
| `POST /study-plans/{plan_id}/calendar-sync/confirm` | `{"preview_id":"pv_cal","confirmation_token":"..."}` | `{"async_task_id":"...","event_count":7,"status":"queued"}` | `CONFIRMATION_EXPIRED`, `ARGUMENTS_CHANGED` | 是 | 失效可用时间/是/是 |
| `PATCH /calendar/events/{event_id}` | `{"start_at":"...","end_at":"...","expected_version":"etag","preview_only":false}` + 确认头 | `{"event_id":71,"sync_status":"synced","remote_version":"etag2"}` | `CALENDAR_CONFLICT`, `REMOTE_NOT_FOUND` | 是 | 失效可用时间/可能/是 |
| `DELETE /calendar/events/{event_id}` | `{"preview_only":false}` + 确认头 | `{"event_id":71,"deleted":true,"sync_status":"deleted"}` | `CONFIRMATION_REQUIRED` | 是 | 失效可用时间/可能/是 |

## 关键请求/响应完整示例

### 文档上传（异步）

```http
POST /api/v1/courses/12/documents
Authorization: Bearer <token>
Idempotency-Key: upload-20260714-db-ch3
Content-Type: multipart/form-data

file=@chapter3.pdf&title=数据库第三章
```

```json
{
  "data": {
    "document_id": 21,
    "version": 1,
    "status": "uploaded",
    "async_task_id": "0190ef7e-8b30-7d31-a8bc-3e2e1ef0a111",
    "status_url": "/api/v1/async-tasks/0190ef7e-8b30-7d31-a8bc-3e2e1ef0a111"
  },
  "meta": {"request_id": "req_upload_01"}
}
```

### 严格资料问答

```json
{
  "question": "什么是第三范式？",
  "mode": "strict",
  "document_ids": [21],
  "top_k": 6
}
```

```json
{
  "data": {
    "message_id": "0190f001-1111-7777-8888-abcdef123456",
    "answer": "第三范式要求关系先满足第二范式，并且非主属性不传递依赖于候选键。",
    "sufficient_evidence": true,
    "citations": [
      {
        "source_id": "S2",
        "document_id": 21,
        "document_name": "数据库第三章",
        "document_version": 1,
        "chunk_id": 301,
        "page_number": 18,
        "chapter_name": "3.4 第三范式",
        "quote": "……非主属性不传递函数依赖于候选键……"
      }
    ]
  },
  "meta": {"request_id": "req_chat_01", "cached": false, "latency_ms": 1840}
}
```

### 计划确认（版本冲突安全）

```json
{
  "preview_id": "pv_plan_003",
  "expected_base_version": 2
}
```

请求头还需 `X-Confirmation-Token` 与 `Idempotency-Key`。成功响应：

```json
{
  "data": {
    "plan_id": 41,
    "active_version": 3,
    "previous_version": 2,
    "activated_at": "2026-07-14T15:30:00+08:00",
    "cache_invalidated": true,
    "calendar_sync_required": true
  },
  "meta": {"request_id": "req_plan_confirm_03", "idempotent_replay": false}
}
```

### MCP 日历创建的预览与确认

预览响应只展示待执行动作：

```json
{
  "data": {
    "preview_id": "pv_cal_123",
    "tool_name": "create_calendar_event",
    "summary": "将在学习日历创建 1 个事件",
    "changes": [
      {"title":"复习函数依赖","start_at":"2026-07-15T19:00:00+08:00","end_at":"2026-07-15T19:45:00+08:00"}
    ],
    "conflicts": [],
    "requires_confirmation": true,
    "expires_at": "2026-07-14T15:35:00+08:00"
  }
}
```

确认成功后才返回本地和第三方 ID：

```json
{
  "data": {
    "tool_call_id": 8892,
    "result": {
      "calendar_event_id": 71,
      "provider_event_id": "AAMkAG...",
      "sync_status": "synced"
    }
  },
  "meta": {"request_id": "req_mcp_02", "idempotent_replay": false}
}
```

## WebSocket 任务进度

连接：`GET /api/v1/ws/async-tasks?token=<短期ws票据>`，订阅消息 `{"action":"subscribe","task_ids":["..."]}`。服务端推送：

```json
{
  "type": "async_task.progress",
  "data": {
    "task_id": "0190ef7e-...",
    "status": "processing",
    "progress": 68,
    "current_step": "embedding",
    "message": "已处理 136/200 个文本块",
    "updated_at": "2026-07-14T09:02:21+08:00"
  }
}
```

短期票据必须由已登录 REST 接口签发，且只能订阅属于自己的 task_id。断线重连先用 REST 取最终状态，防止漏掉消息。

# 18. 前端页面设计

## 前端结构与共同状态

Vue Router 管路由；Pinia 分为 `auth/course/document/chat/plan/task/recommendation/job/calendar` store；Axios 拦截器注入 JWT、请求 ID 和幂等键，并统一处理 401；WebSocket store 负责断线重连。每页都必须设计加载、空数据、错误、无权限和移动端/窄屏基本布局。

| # | 页面/路由 | 主要输入 | 页面处理与交互 | 主要输出/组件 |
|---:|---|---|---|---|
| 1 | 登录 `/login` | 邮箱、密码 | 表单校验、登录、保存短期访问状态；刷新 Token 建议 HttpOnly Cookie | 登录成功跳首页；错误不区分“邮箱存在” |
| 2 | 注册 `/register` | 邮箱、密码、确认密码、昵称 | 密码强度、协议确认、注册 | 账号与初始设置入口 |
| 3 | 学习首页 `/dashboard` | 当前课程、日期 | 并行加载今日任务/统计/推荐/任务进度；卡片可跳详情 | 今日任务、学习进度、考试倒计时、计划完成率、薄弱点、推荐资料/题目、最近建议/长任务、ECharts 趋势图 |
| 4 | 课程管理 `/courses` | 搜索、状态、课程表单 | 新建/编辑/归档/删除预览与确认 | 课程卡片、考试日、目标分、进度 |
| 5 | 课程详情 `/courses/:id` | 课程 ID | 聚合资料、知识点、计划、薄弱点；Tab 懒加载 | 课程概况、资料列表、知识树、计划入口 |
| 6 | 资料上传 `/courses/:id/upload` | 拖拽文件、标题 | 前端扩展名/大小预校验、上传进度、重复提示；服务端仍复验 | document_id、异步任务卡片 |
| 7 | 文档处理进度 `/documents/:id/progress` | document_id/task_id | REST 初始状态 + WebSocket 更新；失败展示错误和重试预览 | 步骤条、百分比、切块数、版本、重试按钮 |
| 8 | 智能问答 `/courses/:id/chat/:sessionId?` | 问题、模式、文档范围 | 流式/非流式展示；引用 source_id 映射；点击打开原文；资料不足提示 | 回答、资料名、页码/章节、原文抽屉、历史会话 |
| 9 | 学习计划 `/courses/:id/plan` | 版本、周/月视图 | 展示规则计划；比较版本；调整草案；确认前差异/风险弹窗 | 日历/列表、任务依赖、版本时间线、负载条 |
| 10 | 今日任务 `/tasks/today` | 日期、课程筛选 | 开始、完成、延迟、取消；计时器；状态乐观更新失败回滚 | 今日总时长、完成率、任务卡片 |
| 11 | 推荐中心 `/courses/:id/recommendations` | 类型、知识点、可用时长 | 获取资源/题目；点击、跳过、收藏、评分反馈 | 分数、标签、预计时长、“为什么推荐”抽屉 |
| 12 | 练习答题 `/courses/:id/practice` | 题集、答案、耗时 | 未提交前不请求答案；提交后显示解析；支持下一题 | 得分、正确答案、解析、掌握度变化提示 |
| 13 | 错题本 `/courses/:id/wrong-questions` | 知识点/状态筛选 | 重做、标记掌握（需证据）、删除确认 | 错误次数、最近答案、解析、复习入口 |
| 14 | 掌握度 `/courses/:id/mastery` | 课程、知识点 | ECharts 雷达/柱形/趋势；显示置信度和证据数 | 薄弱排序、趋势、最近评测、推荐入口 |
| 15 | 学习统计 `/statistics` | 课程、日期范围 | 聚合时长、完成率、正确率、推荐效果；图表空值处理 | 趋势图、热力图、指标卡、导出（扩展） |
| 16 | 长时任务中心 `/jobs` | 状态/类型筛选 | 轮询或 WS；取消、重试；权限与最终状态复查 | 队列/处理中/成功/失败、进度、结果链接 |
| 17 | 日历同步 `/calendar` | 日历账号、计划版本 | OAuth 绑定；空闲时间；同步预览；冲突处理；确认后异步同步 | 周视图、待创建/修改/删除事件、逐项同步结果 |
| 18 | 个人设置 `/settings` | 个人资料、学习偏好、时区、日历授权 | 修改偏好并失效画像；解绑日历二次确认 | 保存状态、重新授权提示、账号安全入口 |

## 学习首页布局建议

```text
┌ 课程选择 ─ 考试倒计时 ─ 今日可用 120 分钟 ┐
├ 今日任务(主区域) ───────┬ 计划完成率/学习进度 ┤
├ 薄弱知识点 ─ 推荐资料 ──┼ 推荐题目             ┤
├ 学习趋势图(7/30 天) ────┼ 最近学习建议         ┤
└ 最近长时任务及进度 ─────┴ 快捷上传/提问/练习   ┘
```

首页请求应聚合或并行，避免 10 个卡片串行等待。骨架屏先显示布局；某个推荐接口失败不应让今日任务一起白屏。

## 智能问答引用交互

- 正文中的 `[S1]` 可点击；右侧抽屉显示资料名、版本、页码/章节和原文片段。
- `version_valid=false` 时标记“该资料已有新版本，这是历史回答引用”，不能悄悄改引用。
- 严格资料模式资料不足时使用明确空态，不展示模型猜测。
- 切换课程或资料范围需创建新上下文/确认清空当前上下文，避免跨课程串话。

## 计划确认交互

1. 调整请求完成后，先显示触发证据和“调整前/后”并排差异。
2. 用颜色区分新增、删除、推迟和时长变化；同时列出未安排内容和风险。
3. “确认新版本”和“同步到日历”是两个独立动作；各自生成确认令牌。
4. 若确认时返回版本冲突，刷新最新版本并要求重新比较，不能覆盖别处修改。

## 状态管理注意点

- Token 不长期放明文 localStorage；优先短期内存 access token + 安全 Cookie refresh token。
- Store 保存服务端对象时带 `updated_at/version`；更新冲突时回滚乐观 UI。
- `job` Store 按 task_id 去重 WebSocket 消息，进度只单调增长；最终状态以后不再被旧消息改回 processing。
- ECharts 组件在 Tab 显示和窗口变化时 `resize()`；无数据时展示说明而非一条假 0 线。
