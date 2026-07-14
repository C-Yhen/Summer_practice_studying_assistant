# 19. 项目目录结构

## 建议目录

```text
project-root/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/                 # FastAPI 路由；只做鉴权、参数转换和响应
│   │   ├── core/                   # 配置、JWT、权限、错误码、日志、幂等
│   │   ├── models/                 # SQLAlchemy 29 张表模型
│   │   ├── schemas/                # Pydantic 请求/响应/LLM JSON Schema
│   │   ├── services/               # 业务用例与事务编排
│   │   ├── repositories/           # PostgreSQL 查询和持久化
│   │   ├── rag/                    # 解析、切块、检索、重排、提示词、引用校验
│   │   ├── recommendation/         # 候选、特征、规则打分、理由
│   │   ├── planning/               # 优先级、拓扑排序、排程、调整、差异
│   │   ├── agents/                 # Agent 编排与结构化工具选择
│   │   ├── mcp/                    # MCP 客户端、确认协议、工具 DTO
│   │   ├── tasks/                  # Celery 任务定义、检查点和任务路由
│   │   ├── cache/                  # Redis key、TTL、Cache-Aside、锁
│   │   ├── providers/              # LLM/Embedding/Calendar/Storage/Notification 适配
│   │   ├── utils/                  # 小型无业务依赖工具
│   │   └── main.py                 # FastAPI 应用入口
│   ├── alembic/
│   │   └── versions/               # 可审查、可回滚的数据库迁移
│   ├── pyproject.toml
│   └── alembic.ini
├── frontend/
│   ├── src/
│   │   ├── api/                    # Axios 客户端及类型
│   │   ├── assets/
│   │   ├── components/             # 通用 UI、引用卡、任务卡、确认弹窗
│   │   ├── composables/            # WebSocket、分页、请求状态
│   │   ├── layouts/
│   │   ├── router/
│   │   ├── stores/                 # Pinia 状态
│   │   ├── types/                  # 与 OpenAPI 生成类型对齐
│   │   ├── views/                  # 18 个页面
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts
├── mcp-server/
│   ├── app/
│   │   ├── tools/                  # 18 个工具；一工具一模块或按域分组
│   │   ├── auth/                   # 用户上下文、scope、服务认证
│   │   ├── confirmation/           # 预览/令牌/幂等
│   │   ├── audit/                  # mcp_tool_calls 记录和脱敏
│   │   └── server.py
│   ├── tests/
│   └── pyproject.toml
├── worker/
│   ├── celery_app.py               # Celery 配置和路由
│   └── tasks/                      # 可选：若不放 backend/app/tasks
├── docker/
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   ├── mcp.Dockerfile
│   └── nginx.conf
├── scripts/
│   ├── seed_demo_data.py           # 幂等生成答辩数据
│   ├── evaluate_rag.py             # 固定问答集评测
│   └── wait_for_services.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── api/
│   ├── rag/
│   ├── recommendation/
│   ├── mcp/
│   ├── e2e/
│   └── fixtures/                   # 小型合法测试资料和期望结果
├── docs/                           # 本设计、接口约定、演示脚本
├── docker-compose.yml
├── .env.example                    # 只列变量名和安全示例，不放真实密钥
├── .gitignore
└── README.md                       # 启动、迁移、测试、演示入口
```

## 为什么这样拆

- `api → services → repositories` 单向依赖，防止路由里混入 SQL 和大模型调用。
- `rag/recommendation/planning` 是可独立测试的算法模块，输入输出使用 schemas 中的 DTO。
- `providers` 隔离外部厂商；业务模块不能直接 import 某厂商 SDK。
- `mcp-server` 是独立进程，但共享 OpenAPI/DTO 契约；MCP 工具通过受控服务接口访问业务能力。
- `worker` 与 API 可使用同一业务包，避免复制规则；部署上是不同进程。

依赖方向建议：

```text
api / mcp / celery entrypoint
          ↓
       services
   ↙       ↓        ↘
algorithms  repositories  providers
                  ↓
          PostgreSQL / Redis
```

# 20. 核心代码示例

以下均为**实现指导伪代码/接口草图**，不是已在仓库运行的代码。落地时需补充异常类型、日志、事务和测试。

## 七条关键业务流程

### 流程一：首次使用

```text
注册 → 创建课程 → 设置考试日期/每日时间/目标成绩
→ 完成初始测试 → 写答题记录 → 计算掌握度与画像
→ 规则算法生成第一周计划草案 → 推荐资料
→ 展示任务/风险/理由 → 用户确认 → 激活版本
```

输入是账号、课程目标、可用时间和初测答案；处理包括判分、掌握度、冷启动画像、排程和推荐；输出是已确认的第一周结构化计划。任一步失败都保留可恢复状态，不把未确认草案当当前计划。

### 流程二：文档上传与 RAG 建库

```text
上传/校验 → documents + document_versions → async_tasks
→ Celery 解析页码/章节 → 清洗 → 切块 → 批量 Embedding
→ document_chunks → 抽样校验 → 原子切当前版本
→ 清 QA/检索缓存 → WebSocket 通知 ready
```

新版本失败时旧版本继续服务；只有当前版本切换成功后，新的检索才会使用它。

### 流程三：资料问答

```text
问题 → JWT/课程/文档权限 → 带版本缓存
→ 向量化 → pgvector 当前版本过滤 → 可选重排
→ 来源编号 → LLM 结构化输出 → 引用白名单验证
→ 保存消息/引用快照 → 写缓存 → 返回答案
```

资料不足或引用验证失败时明确拒答/降级，不能把模型猜测伪装成课件内容。

### 流程四：每日学习

```text
首页今日任务 → 阅读推荐资料 → 做题并提交
→ question_attempts/learning_records → 更新错题与掌握度
→ 画像/缓存失效 → 规则建议 → 判断调整触发器
```

输出包括判题结果、更新后的掌握度、今日建议和（可能的）计划调整提示；触发提示不等于自动覆盖计划。

### 流程五：动态调整计划

```text
触发证据 → 读取当前版本/剩余时间/薄弱点
→ 冻结完成任务 → 重算优先级和容量 → 新草案
→ 计算新增/删除/推迟/时长/风险差异 → 用户确认
→ 新版本 active、旧版 superseded → 清计划缓存
→ 单独预览并确认日历变更
```

### 流程六：MCP 日历同步

```text
Agent get_study_plan → get_available_time → 检查冲突
→ 生成事件预览 → 用户确认 → create_calendar_event（幂等）
→ 保存 provider_event_id/sync_status → mcp_tool_calls → 返回逐项结果
```

输入参数由 MCP Schema 校验；输出包括本地/远端 ID、同步状态和审计调用 ID。部分失败时不把整批标成成功。

### 流程七：长时任务

```text
请求 → 权限/幂等检查 → async_tasks queued → 事务后投递
→ Worker 分阶段执行/检查取消 → Redis 高频进度 + DB 检查点
→ success/failed/cancelled → 结果持久化 → 通知前端
```

## 统一 LLM Provider

```python
from typing import Protocol, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class LLMProvider(Protocol):
    async def chat_json(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        *,
        temperature: float = 0.1,
    ) -> T: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class ProviderRegistry:
    def llm(self, purpose: str) -> LLMProvider:
        # 根据配置选择 deepseek/qwen/zhipu/openai-compatible
        ...
```

`purpose` 可为 `rag_answer/plan_wording/report`，便于不同任务选择成本与能力不同的模型。Provider 内部负责超时、重试、JSON 解析和用量记录，Service 仍负责业务校验。

## RAG 回答与引用校验

```python
async def answer_question(ctx, request):
    assert await permission.can_read_course(ctx.user_id, request.course_id)
    scope = await documents.resolve_current_scope(request.course_id, request.document_ids)
    cache_key = qa_key(ctx.user_id, request, scope.version_fingerprint)
    if cached := await cache.get(cache_key):
        return cached

    standalone_query = await rewrite_if_needed(request.question, request.history)
    query_vector = (await embedding_provider.embed([standalone_query]))[0]
    chunks = await chunk_repo.search_current_versions(
        user_id=ctx.user_id,
        course_id=request.course_id,
        document_ids=scope.document_ids,
        vector=query_vector,
        top_k=request.top_k,
    )
    evidence = assign_server_source_ids(chunks)  # S1..Sn
    if not evidence_is_sufficient(evidence) and request.mode == "strict":
        result = strict_no_evidence_response()
    else:
        model_result = await llm.chat_json(
            build_grounded_messages(request, evidence), RagAnswerSchema
        )
        result = validate_citations(model_result, allowed_ids=evidence.keys())

    await chat_service.save_messages_and_citations(ctx, request, result, evidence)
    await cache.set(cache_key, result, ttl=jitter(hours=24))
    return result
```

## 掌握度更新（简单可解释版）

```python
def update_mastery(old, attempt):
    difficulty_weight = {"basic": 0.8, "medium": 1.0, "hard": 1.2}[attempt.difficulty]
    evidence = 1.0 if attempt.is_correct else 0.0
    alpha = min(0.30, 0.08 * difficulty_weight + 1 / (old.evidence_count + 10))
    new_score = clamp((1 - alpha) * old.score + alpha * evidence, 0, 1)
    new_confidence = min(1.0, old.confidence + 0.05 * difficulty_weight)
    return MasteryUpdate(score=new_score, confidence=new_confidence)
```

这只是 MVP 可解释算法；正确率需按知识点关联分摊，主观题未批改不能更新。算法版本必须入库，防止之后改公式无法解释旧结果。

## 推荐打分与理由

```python
WEIGHTS = {
    "knowledge_match": 0.30,
    "weakness": 0.25,
    "difficulty_match": 0.20,
    "preference_match": 0.10,
    "resource_quality": 0.10,
    "time_match": 0.05,
}

def rank_candidate(candidate, context):
    features = compute_normalized_features(candidate, context)
    score = 100 * sum(WEIGHTS[k] * features[k] for k in WEIGHTS)
    facts = build_reason_facts(candidate, context, features)
    return Recommendation(
        item_id=candidate.id,
        score=round(score, 2),
        score_breakdown=features,
        reason_facts=facts,
        reason=render_reason_template(facts),
    )
```

## 计划确认事务

```python
async def confirm_plan(user_id, plan_id, candidate_version, base_version, token, idem_key):
    verify_confirmation(token, user_id, "confirm_plan", normalized_args_hash(...))
    async with db.transaction():
        plan = await plan_repo.lock_for_update(plan_id)
        assert plan.user_id == user_id
        if plan.active_version != base_version:
            raise PlanVersionConflict(current=plan.active_version)
        if previous := await idem_repo.find(user_id, "confirm_plan", idem_key):
            return previous.result
        await plan_repo.supersede_active(plan.id)
        await plan_repo.activate_version(plan.id, candidate_version)
        result = await idem_repo.record_success(...)
    await cache_events.publish("plan.version.changed", {"plan_id": plan_id})
    consume_confirmation(token)
    return result
```

## Celery 可重入任务

```python
@celery_app.task(bind=True, autoretry_for=(TemporaryProviderError,), max_retries=3)
def embed_document_version(self, async_task_id, document_id, version):
    task = tasks.require_owned_and_runnable(async_task_id, document_id)
    with distributed_lock(f"document:{document_id}:v{version}"):
        for batch in chunks.pending_batches(document_id, version, size=32):
            if tasks.cancel_requested(async_task_id):
                return tasks.mark_cancelled(async_task_id)
            vectors = embedding.embed([item.content for item in batch])
            chunks.upsert_vectors(batch, vectors)  # 唯一键保证重复执行安全
            tasks.update_progress_monotonic(async_task_id, batch.progress)
        documents.activate_version_if_complete(document_id, version)
        tasks.mark_success(async_task_id)
```

## Cache-Aside 更新顺序

```python
async def complete_task(user_id, task_id, payload, idem_key):
    async with db.transaction():
        task = await task_repo.get_owned_for_update(user_id, task_id)
        result = await task_service.apply_completion_once(task, payload, idem_key)
        await outbox.add("learning.record.changed", result.cache_dimensions)
    # 事务提交后由事件消费者删除 mastery/profile/plan/recommendation 缓存
    return result
```

若时间不足以实现通用 Outbox，MVP 可在事务提交后同步删缓存，并用版本化 key 兜底；文档必须明确这是折中。

# 21. 团队分工

## 4 人主责与交叉备份

| 成员 | 主责 | 交付物 | 交叉备份/接口 |
|---|---|---|---|
| A 前端 | Vue 3、18 页骨架、Axios/Pinia、问答引用、任务进度、ECharts | 可演示页面、API 类型、E2E 用例 | 与 B 确认 OpenAPI；与 D 联调 WebSocket/任务状态 |
| B 后端业务 | FastAPI、JWT/权限、课程/文档元数据、计划/任务/学习/题目 API、Alembic | 业务接口、29 表迁移、统一错误与幂等 | 审查所有写事务；为 C/D 提供 Service 契约 |
| C RAG/Agent/MCP | 文档切块策略、pgvector 检索、提示词/引用校验、18 个 MCP 工具 | RAG 评测集、MCP Schema/审计、模型 Provider | 与 B 共建权限；与 D 共建解析/Embedding Celery 任务 |
| D 推荐/Redis/Celery/部署 | 推荐与理由、掌握度、缓存、锁、任务队列、Docker Compose、监控 | 推荐模块、任务中心、缓存测试、可一键启动环境 | 与 A 联调进度；为 C 提供 Provider 限流/队列 |

主责不等于“各写各的”。每个模块至少有一名非主责成员审查；A 也要参与契约和 E2E，B/C/D 也要能启动并验证前端闭环。

## 必须共同冻结的数据契约

第 1 周结束前共同确认：

1. ID、时间、分页、错误响应和幂等头规范。
2. 文档六种状态与异步七种状态；计划/任务状态机。
3. RAG `answer/citations`、任务 `status/progress/current_step`、推荐 `score_breakdown/reason` JSON。
4. 课程成员权限矩阵和确认令牌协议。
5. Embedding 模型、维度、切块元数据和文档版本指纹。

契约以 OpenAPI + Pydantic 为事实来源，前端类型由 OpenAPI 生成或人工同步检查；不能只在群里发截图。

## 联调方式

- 每个接口先提交 OpenAPI 示例和 Mock；前端可先用 Mock 数据开发。
- 每天下午合并到开发分支前运行 `lint + unit + migration + API smoke`。
- 每周至少两次全链路联调：上传 → 进度 → 问答；初测 → 计划 → 任务 → 掌握度 → 推荐。
- Bug 必须带复现步骤、请求 ID、期望/实际结果和最小数据，不以口头描述替代。

## Git 与代码审查

- 推荐分支：`main` 始终可演示；`develop` 集成；短分支 `feat/rag-citations`、`fix/plan-version-conflict`、`docs/api-contract`。
- 禁止长期“个人总分支”；每个 PR 尽量小于 400 行有效变更，大迁移拆成模型/服务/API。
- PR 至少 1 人审查；数据库迁移、权限、确认、MCP 写工具需 2 人（B + 对应负责人）审查。
- 合并条件：关联任务、说明输入/输出、测试通过、无密钥、迁移可升级、接口示例同步。
- `main` 只通过 PR 合并并打演示标签；答辩前一周进入功能冻结，修 Bug 不追加高风险功能。

# 22. 开发时间安排

## 8 周计划

| 周 | 目标 | 各端主要工作 | 周末验收门槛 |
|---:|---|---|---|
| 1 | 契约与可运行骨架 | 需求裁剪、架构/ER/OpenAPI、Compose、FastAPI/Vue、PostgreSQL/Redis/pgvector、CI | 一条健康检查；迁移成功；四人可本地启动；接口状态和 JSON 冻结 |
| 2 | 用户、课程、上传底座 | JWT/权限、课程 CRUD、PDF 上传/对象存储、documents/version/async_tasks、页面骨架 | 用户只能访问自己的课程；PDF 可入库并看到 queued 状态 |
| 3 | PDF 建库与 RAG MVP | PDF 页码解析、切块、Embedding、pgvector、问答、引用校验；Redis 检索/QA 缓存 | 固定 20 题中能命中资料；引用页可人工核对；无答案严格模式拒答 |
| 4 | 计划与每日任务 | 知识点、初测、掌握度基础算法、规则排程、计划/任务页面、确认与版本 | 7 天计划不过载、依赖顺序正确；确认后旧版可查 |
| 5 | 推荐与学习闭环 | 答题/错题/学习记录、基础推荐/理由、统计/图表、缓存失效 | 完成任务/答题后掌握度和推荐理由可解释地变化 |
| 6 | 核心亮点 | Celery 分队列/进度、WebSocket、动态调整草案、自研 MCP 只读工具与日志 | 长任务可取消/重试；调整显示差异；所有 MCP 调用可审计 |
| 7 | 日历与写工具 | MCP 写工具确认/幂等、日历 Provider/冲突/同步、周报；完整接口/权限/并发测试 | 未确认不能写；重复确认不重复创建；第三方失败可恢复/降级 |
| 8 | 稳定与答辩 | 功能冻结、性能/异常测试、种子数据、演示脚本、录屏备份、部署文档 | 新环境一键启动；22 步演示彩排 3 次；断网/模型失败有备用方案 |

## 范围闸门

- 第 3 周 RAG 闭环未稳定：暂停 PPT/Word，继续只支持 PDF。
- 第 5 周核心闭环未完成：日历只保留一个 Provider/模拟 Provider，周报使用模板。
- 第 6 周后不启动多 Agent、知识图谱、协同过滤和语音功能。
- 第 7 周功能冻结后只修复 P0/P1 问题和演示阻塞问题。

# 23. 测试方案

## 测试分层

| 类型 | 重点用例 | 工具/做法 | 通过标准（建议） |
|---|---|---|---|
| 单元测试 | 优先级、拓扑、时间装箱、掌握度、推荐分、缓存 key、状态机、引用白名单 | pytest；外部 Provider 使用 Fake | 核心纯函数分支覆盖；边界和非法输入都有用例 |
| API 测试 | 所有 REST 正常/错误响应、分页、幂等、乐观锁、确认 | FastAPI TestClient/httpx + 测试 DB | OpenAPI Schema 一致；错误码稳定；重复写不重复 |
| 数据库测试 | 29 表 FK/唯一/CHECK、迁移、事务回滚、软删过滤 | 临时 PostgreSQL + Alembic upgrade | 空库可升级；约束拦截脏数据；关键事务原子 |
| RAG 检索 | 正确文档/页码、Top-K、切块、严格拒答、版本隔离、跨用户隔离 | 固定 PDF + 标注问答集 | 见下方 RAG 指标 |
| LLM 格式 | 合法 JSON、缺字段、错误引用、超长文本、提示注入 | Fake/录制响应 + Pydantic | 非法输出不能入库；可控重试后明确失败 |
| 推荐 | 分数分解、过滤、冷启动、多样性、理由事实 | 固定画像/资源数据集 | 排序符合规则；每项有可核验理由；无越权候选 |
| Redis | 命中/未命中、TTL、版本失效、穿透/击穿/雪崩、锁 token | 真 Redis 集成测试 | DB 更新后旧版本不作为当前结果；锁不误删 |
| Celery | queued→processing→终态、重试、超时、取消、崩溃恢复、重复投递 | eager 单测 + 独立 Worker 集成 | 进度单调；重复任务不重复写；最终 DB 状态可查 |
| MCP | 18 个 Schema、scope、确认、幂等、日志脱敏、外部失败 | MCP 客户端 + Fake Calendar | 每次调用有日志；写操作未确认 0 次副作用 |
| 权限 | IDOR、跨课程/跨用户、普通用户读审计、WebSocket task_id | 两用户两课程矩阵 | 所有越权均 403/404 且不泄露对象存在性 |
| 异常 | 文件损坏、模型超时、Redis/日历不可用、Token 过期、容量不足 | 故障注入/Fake Provider | 明确错误/降级，无假成功、无半成品切当前版本 |
| 并发 | 同文档重复解析、计划双确认、答题双提交、日历超时重试 | pytest 并发 + k6/Locust | 唯一约束/锁/幂等生效；无双 active 计划 |
| 用户确认 | 过期、参数篡改、重复确认、他人令牌、版本变化 | API 集成 | 全部拒绝或幂等返回；参数变化必须重确认 |
| 前端 E2E | 登录、上传、问答引用、计划确认、答题、调整、日历预览 | Playwright/Cypress | 核心演示路径在干净环境自动跑通 |

## RAG 专项评测

建立 30～50 个小型标注问题：有答案、跨页答案、相似概念、指定文档、多文档、无答案各占一定比例。每题标注正确文档、页码/章节、支持片段和应拒答标志。

| 指标 | 计算 | 建议 MVP 目标 |
|---|---|---:|
| 检索 Recall@5 | 正确支持块是否在前 5 | ≥ 80%（小型固定集） |
| 引用页准确率 | 返回页码是否包含支持原文 | ≥ 90% |
| 资料忠实率 | 关键结论是否都被引用支持，人工双人抽评 | ≥ 85% |
| 无答案拒答率 | 无答案题中正确拒答比例 | ≥ 90% |
| 越权泄露 | 另一用户/课程片段被返回 | 必须 0 |
| 缓存收益 | 同问题冷/热 P50 延迟对比 | 热缓存明显低于冷请求；记录数据而非预设夸张数值 |

实验矩阵：切块 300/500/700 字，重叠 50/100；Top-K 3/5/8；有/无关键词召回；有/无 reranker。只改变一个变量，保存命中率、页码准确率、延迟和上下文 token 数，选综合最好而非只看命中率。

## 推荐专项评测

- 离线规则测试：构造弱基础/临考/时间少/无历史四类画像，断言首屏难度、知识点、用时和前置关系合理。
- 在线/试用指标：曝光去重后的 CTR、完成率、推荐后 7 天正确率/掌握度变化、跳过率、理由认可评分。
- 冷启动：新用户完成初测前后对比推荐相关性；没有行为数据时理由必须坦诚，不能声称“你最近正确率为 52%”。
- 实训样本很小时，指标只用于演示和趋势，不声称具有统计显著性或因果效果。

## 性能与安全基线

- 用 20～50 并发用户压测课程列表、今日任务、RAG（限制模型并发）和任务进度；记录 P50/P95、错误率和数据库连接数。
- 上传限制大小/MIME/文件头，文件名不能形成路径穿越；文档解析进程限制 CPU/内存/超时。
- 密码哈希、JWT 失效、OAuth Token 加密、日志脱敏、SQL 注入、提示注入、XSS/Markdown 渲染均需安全测试。

# 24. 项目创新点

创新点控制为三个能演示、能用数据证明的方向：

1. **基于学习行为和掌握度的动态计划**：不是让大模型随意改计划，而是以未完成、正确率、用时和考试剩余时间触发规则，生成可比较、可确认、可回溯的新版本。
2. **使用 MCP 安全连接学习任务与日历**：18 个工具具备 Schema、权限、确认、幂等和日志，演示 Agent 不只“回答”，还能在用户控制下完成外部操作。
3. **RAG + 画像 + 掌握度的可解释推荐**：候选来自有权限的课程内容，分数保留六项分解，每条推荐给出可核验的事实理由。

工程亮点是 PostgreSQL 与 pgvector 一体化过滤、Redis 版本化缓存、Celery 可恢复长任务、文档/计划双版本、RAG 引用白名单和第三方 Provider 适配。答辩时应展示日志、版本差异和失败恢复，而不只展示 UI。

# 25. 项目风险

## 风险清单

| 风险 | 概率/影响 | 早期信号 | 预防与缓解 | 答辩降级方案 |
|---|---|---|---|---|
| PDF 页码/公式解析不稳定 | 高/高 | 引用页错、乱码、扫描 PDF 无文本 | 第 2 周用真实课件验收；保留页级元数据；扫描 OCR 设为扩展 | 选可解析的演示 PDF；明确 OCR 不在 MVP |
| 多格式解析范围过大 | 高/中 | 第 3 周 PDF 仍未稳定却开发 PPT/Word | MVP 只承诺 PDF，解析器接口预留其他格式 | 展示格式设计，不演示未完成格式 |
| 模型输出不合法或幻觉 | 中/高 | JSON 解析失败、引用不存在 | Pydantic + 引用白名单 + 严格拒答 + 低温度 + Fake 回归 | 使用预先验证模型配置；规则/模板降级 |
| Embedding 维度/模型切换 | 中/高 | 入库维度错误、相似度突变 | 固定模型版本和维度；启动检查；新模型走新索引/迁移 | 锁定答辩模型，不临时切换 |
| 计划算法过于理想化 | 中/高 | 任务超载、依赖错、时间不足仍排满 | 规则先行、容量/拓扑断言、输出未安排风险 | 演示固定 7 天场景；LLM 仅润色 |
| 第三方日历 OAuth/审核 | **高/高，最易延期** | 回调失败、scope 未批准、账号地区限制 | 第 1 周确认 Provider；第 5 周前打通最小沙箱；保留 Mock Provider | 用本地/Mock 日历完整演示确认和幂等 |
| 写操作重复/误操作 | 中/高 | 日历重复事件、双 active 计划 | 预览确认、幂等键、DB 唯一、乐观锁、审计 | 展示重复请求返回同一结果 |
| Redis/Celery 状态丢失 | 中/中 | 页面进度卡住、DB 状态不一致 | DB 保关键状态；进度可重建；补偿投递；监控停滞任务 | 改用 REST 查 DB 最终状态，关闭实时推送 |
| 团队接口无法整合 | 中/高 | 各模块用不同状态/字段 | 第 1 周冻结 OpenAPI/状态机；小 PR；每周两次全链路 | 功能冻结，集中修核心演示路径 |
| 数据量太少无法证明推荐效果 | 高/中 | CTR/掌握度变化无意义 | 使用规则可解释和离线场景测试，不夸大统计结论 | 展示分数分解、冷启动与行为变化模拟 |
| 隐私/越权 | 低～中/极高 | 用改 ID 可读他人资料/任务 | 所有查询按 user/course 过滤；两用户权限矩阵；日志脱敏 | 未通过权限测试不得答辩上线 |
| 演示依赖网络/外部 API | 中/高 | 模型/日历限流或校园网不稳 | 本地 Compose、预热、预算/余额检查、录屏和 Fake Provider | 切备用模型或使用合规缓存/录屏解释 |

## 最容易延期的模块

从高到低：**真实第三方日历 OAuth 与双向同步**、多格式高质量解析、动态计划重排的所有边界、多 Agent/LangGraph、协同过滤/知识图谱。前三项必须尽早做技术验证；后三项在 MVP 稳定前不启动。不要为了“看起来高级”牺牲引用准确、权限和计划版本。

# 26. 答辩演示流程

## 演示前准备

- 使用幂等种子脚本准备一份经过授权的数据库课件、知识点和题目；演示账号不放真实个人信息。
- 清楚标记哪些请求是实时模型结果，哪些是降级/Fake Provider；不要把预置结果称为实时生成。
- 提前确认 Compose、模型额度、日历测试账号、时区、考试日期相对当天仍合理。
- 准备 5 分钟短流程、10～15 分钟完整流程和离线录屏；任何外部失败都能切本地 Mock。

## 22 步完整演示

1. 注册并登录，说明 JWT 与用户数据隔离。
2. 创建“数据库系统”课程。
3. 设置七天后考试。
4. 设置每天学习两小时、目标 85 分和基础模式。
5. 上传数据库课程 PDF，展示创建的文档版本。
6. 进入任务中心，看解析/切块/Embedding 进度。
7. 文档 ready 后展示切块数量和 pgvector 已入库（不直接暴露向量值）。
8. 问“什么是第三范式”。
9. 展示课件回答、资料名、版本、页码/章节和可点击原文；追加一个资料外问题演示严格拒答。
10. 完成短初始测试。
11. 展示函数依赖和事务调度较弱，并说明分数和证据数来自答题。
12. 生成七天计划草案，展示每日容量、前置顺序和机动时间。
13. 展示课件章节和练习题推荐。
14. 展开推荐理由和六项分数，说明事实来自正确率、难度和预计用时。
15. 完成一个任务并做一组练习。
16. 展示答题记录、错题本和掌握度更新。
17. 模拟第二天任务未完成（演示环境通过受控数据/时间开关，不篡改生产逻辑）。
18. 系统生成调整版本，展示新增、推迟、删除、时长和风险。
19. 用户确认调整，展示旧版本仍可查看；重复确认不产生第二个 active 版本。
20. 预览待写入日历事件，用户确认后 MCP 同步，展示第三方事件 ID 和工具日志。
21. 提交周报长任务，展示进度和最终报告。
22. 对比一次问答冷/热缓存耗时，并展示任务重试/日志脱敏等工程效果。

## 讲解主线

答辩不要逐页点功能，始终围绕一个闭环讲：**资料成为证据 → 行为成为数据 → 数据驱动计划和推荐 → 用户确认后执行 → 新行为继续改进后续计划**。每个亮点都给可验证证据：引用页、分数明细、版本差异、MCP 日志、缓存命中或任务进度。

# 27. 最小可用版本实现顺序

## 按依赖实施，而不是按页面数量实施

1. **固定 MVP 范围与契约**：只承诺 PDF、一个 Embedding 模型、一个聊天模型、规则计划、规则推荐；冻结状态机、错误 JSON、权限矩阵。
2. **搭环境**：Docker Compose 启动 PostgreSQL+pgvector、Redis、FastAPI、Vue；建立 Alembic 和健康检查。
3. **建最小表**：先完成 users/preferences/courses/members/documents/document_versions/chunks/async_tasks，再按功能增计划、题目、记录和推荐表；迁移测试必须通过。
4. **用户与课程**：注册、登录、JWT、课程 CRUD、成员归属；先完成两用户越权测试。
5. **PDF 上传与版本**：文件校验、原件保存、文档/版本记录、状态页；此时解析可先同步验证，再接 Celery。
6. **PDF 解析/切块/Embedding**：保存页码和章节，批量写 pgvector；固定小课件逐块抽验。
7. **RAG 最小闭环**：当前版本过滤、向量 Top-K、严格资料提示词、结构化答案、后端引用校验、聊天持久化。
8. **引用前端与 RAG 评测**：能点击资料名/页码/原文；有答案和无答案固定集过门槛。未通过前不开发复杂 Agent。
9. **Redis Cache-Aside**：QA/检索缓存带文档版本指纹；验证上传新版后旧缓存不命中。
10. **知识点、初测和掌握度**：题目/作答/错题、简单可解释掌握度，形成真实计划输入。
11. **规则学习计划**：时间预算、拓扑依赖、优先级、不过载、机动时间；保存草案/版本/每日任务并实现确认。
12. **每日学习闭环**：今日任务、完成/延迟、学习记录、答题后掌握度更新和基础统计。
13. **基础推荐**：按六项规则打分，保存曝光和分项理由；实现冷启动和反馈。
14. **Celery 正式异步化**：把解析/Embedding/长期计划迁入任务队列，DB 保存状态，Redis 报进度，支持重试/取消；前端轮询先跑通，再加 WebSocket。
15. **回归与一键演示**：完成上传 → 问答引用 → 初测 → 计划 → 任务 → 掌握度 → 推荐的核心链路，准备种子数据和错误降级。
16. **第二阶段亮点（MVP 稳定后）**：动态调整差异/确认 → 18 个 MCP（先只读后写）→ 日历适配 → 周报。
17. **加分功能（还有时间才做）**：混合检索、reranker、多模型切换；多 Agent/LangGraph、协同过滤、知识图谱、语音、教师端最后考虑。

## 每一步的完成定义

一个步骤只有同时满足“接口可调用、前端或测试可验证、权限正确、错误态明确、数据库状态可检查、至少一个自动测试”才算完成。只有界面截图、只有模型 Prompt、只有数据库表或只在某位同学电脑运行，都不算完成。

## 最终优先级

```text
P0：登录/权限 + PDF 当前版本建库 + RAG 引用/拒答 + 结构化计划/任务 + 学习记录
P1：基础掌握度/推荐理由 + Redis + Celery 进度 + 基础统计
P2：动态调整确认 + MCP 日志/幂等 + 一个日历 Provider + 周报
P3：多格式、混合检索、重排、多 Agent、协同过滤、知识图谱等扩展
```

如果进度落后，先删除 P3，再将日历换 Mock Provider、周报换规则模板；**不能删除权限、引用校验、版本保留、确认和幂等这些正确性保障**。

