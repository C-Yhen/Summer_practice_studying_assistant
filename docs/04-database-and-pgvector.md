# 15. 数据库表设计

## 设计约定

- PostgreSQL 15+；主键默认 `BIGSERIAL`，对外不可猜测 ID（任务、运行）使用 `UUID`。
- 时间统一为 `TIMESTAMPTZ`，数据库保存 UTC，前端按用户时区显示；所有 29 张表都有 `created_at`、`updated_at`。
- JSONB 只保存变化快的快照/分数明细，能够关联、筛选和约束的核心字段必须独立成列。
- 金额/分数用 `NUMERIC`，持续时间用整数分钟/毫秒，禁止用浮点时间。
- 软删除表使用 `deleted_at TIMESTAMPTZ NULL`；所有正常查询显式带 `deleted_at IS NULL`。审计/历史流水表不软删，通过保留策略归档。
- 外键默认 `ON DELETE RESTRICT`；完全从属且无审计价值的数据才 `CASCADE`。软删除业务对象时由服务层处理关联可见性。
- `updated_at` 由统一触发器或 ORM `onupdate` 更新；不是依赖开发者手填。
- 下列“普通索引”指单列索引，“联合/唯一”列出多列索引。生产前以真实查询的 `EXPLAIN ANALYZE` 校验，避免为了数量盲目加索引。

附件列出了 28 张表。本方案新增第 6 张 `document_versions`，把逻辑文档与每次上传的物理版本分离，合计 **29 张表**；这是实现“新版本成功后再原子切换、失败仍使用旧版”的必要结构。

## 1. `users`：用户账号

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否/自增 | 主键 |
| `email` | VARCHAR(255) | 否 | 规范化为小写 |
| `password_hash` | VARCHAR(255) | 否 | Argon2/bcrypt 哈希，绝不存明文 |
| `display_name` | VARCHAR(80) | 否 | 展示名 |
| `timezone` | VARCHAR(64) | 否/`Asia/Shanghai` | IANA 时区 |
| `status` | VARCHAR(20) | 否/`active` | `active/disabled/pending`，CHECK |
| `last_login_at` | TIMESTAMPTZ | 是/NULL | 最近登录 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：`UNIQUE(email)`；普通索引 `status`、`deleted_at`；联合索引 `(status, created_at DESC)`。软删除：是。

## 2. `user_preferences`：全局学习偏好

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `foundation_level` | VARCHAR(20) | 否/`unknown` | `weak/basic/intermediate/advanced/unknown` |
| `learning_order` | VARCHAR(20) | 否/`explain_first` | `explain_first/practice_first` |
| `preferred_resource_types` | VARCHAR(30)[] | 否/`{}` | 类型数组 |
| `preferred_difficulty` | VARCHAR(20) | 否/`basic` | 难度枚举 |
| `session_minutes` | SMALLINT | 否/45 | CHECK 10～180 |
| `daily_minutes` | SMALLINT | 否/120 | CHECK 0～720 |
| `target_score` | NUMERIC(5,2) | 是/NULL | CHECK 0～100 |
| `detail_level` | VARCHAR(20) | 否/`detailed` | 讲解程度 |
| `need_exam_focus` | BOOLEAN | 否/true | 考试重点 |
| `need_common_mistakes` | BOOLEAN | 否/true | 易错点 |
| `need_derivation` | BOOLEAN | 否/false | 详细推导 |
| `unavailable_dates` | DATE[] | 否/`{}` | 临时不可学习日；复杂日历后续单独建模 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(user_id)`；普通索引 `foundation_level`；无必要联合索引。软删除：否，随用户停用但保留。

## 3. `courses`：课程

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `owner_id` | BIGINT | 否 | FK → `users.id` |
| `name` | VARCHAR(120) | 否 | 课程名 |
| `description` | TEXT | 是/NULL | 说明 |
| `exam_at` | TIMESTAMPTZ | 是/NULL | 考试时间 |
| `target_score` | NUMERIC(5,2) | 是/NULL | CHECK 0～100 |
| `status` | VARCHAR(20) | 否/`active` | `active/archived` |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：活跃记录可建部分唯一索引 `(owner_id, lower(name)) WHERE deleted_at IS NULL`；普通索引 `owner_id`、`exam_at`；联合 `(owner_id,status,exam_at)`。软删除：是。

## 4. `course_members`：课程成员与角色

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `role` | VARCHAR(20) | 否/`student` | `owner/teacher/student` |
| `joined_at` | TIMESTAMPTZ | 否/now() | 加入时间 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 移出课程 |

约束/索引：`UNIQUE(course_id,user_id)`；普通索引 `user_id`；联合 `(user_id,role,deleted_at)`、`(course_id,role)`。软删除：是；若需重新加入，更新原记录清空 `deleted_at`。

## 5. `documents`：逻辑文档

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `uploaded_by` | BIGINT | 否 | FK → `users.id` |
| `title` | VARCHAR(255) | 否 | 显示名称 |
| `document_type` | VARCHAR(20) | 否 | `pdf/ppt/pptx/doc/docx/txt/md`，CHECK |
| `current_version` | INTEGER | 是/NULL | 当前 ready 版本号 |
| `status` | VARCHAR(20) | 否/`uploaded` | `uploaded/parsing/embedding/ready/failed/deleted` |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：普通索引 `course_id`、`uploaded_by`、`status`；联合 `(course_id,status,deleted_at)`、`(course_id,updated_at DESC)`；当前版本通过 FK/触发器难以直接表达时，服务层事务保证它对应同文档的 ready 版本。软删除：是。

## 6. `document_versions`：文档物理版本（新增）

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `document_id` | BIGINT | 否 | FK → `documents.id` |
| `version_no` | INTEGER | 否 | 从 1 递增，CHECK > 0 |
| `original_filename` | VARCHAR(255) | 否 | 原文件名（清理路径） |
| `storage_key` | VARCHAR(512) | 否 | 对象存储键 |
| `mime_type` | VARCHAR(100) | 否 | 校验后的 MIME |
| `file_size` | BIGINT | 否 | CHECK > 0 |
| `sha256` | CHAR(64) | 否 | 内容校验和 |
| `status` | VARCHAR(20) | 否/`uploaded` | 文档处理状态 |
| `parser_version` | VARCHAR(50) | 是/NULL | 解析器版本 |
| `embedding_model` | VARCHAR(100) | 是/NULL | 向量模型版本 |
| `chunk_count` | INTEGER | 否/0 | CHECK >= 0 |
| `error_code` | VARCHAR(80) | 是/NULL | 标准错误码 |
| `error_message` | TEXT | 是/NULL | 脱敏错误 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：`UNIQUE(document_id,version_no)`、`UNIQUE(storage_key)`；普通索引 `sha256`、`status`；联合 `(document_id,status,created_at DESC)`。软删除：是；旧版默认保留，按保留策略清理原文件和切块。

## 7. `document_chunks`：资料文本块与向量

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `document_id` | BIGINT | 否 | FK → `documents.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id`，冗余用于先过滤 |
| `document_version` | INTEGER | 否 | 与 `document_versions.version_no` 对应 |
| `chunk_index` | INTEGER | 否 | CHECK >= 0 |
| `content` | TEXT | 否 | 原文切块 |
| `content_hash` | CHAR(64) | 否 | 清洗后内容 SHA-256 |
| `page_number` | INTEGER | 是/NULL | CHECK > 0 |
| `chapter_name` | VARCHAR(255) | 是/NULL | 章节 |
| `token_count` | INTEGER | 是/NULL | CHECK >= 0 |
| `metadata_json` | JSONB | 否/`{}` | 坐标、标题层级等扩展元数据 |
| `embedding` | VECTOR(1024) | 否 | 维度必须匹配模型 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：`UNIQUE(document_id,document_version,chunk_index)`；复合 FK `(document_id,document_version)` → `document_versions(document_id,version_no)`；普通索引 `course_id`、`document_id`、`content_hash`；联合 B-tree `(course_id,document_id,document_version,deleted_at)`；向量 HNSW 索引见第 16 节。软删除：是。

## 8. `knowledge_points`：课程知识点

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `parent_id` | BIGINT | 是/NULL | 自引用 FK → `knowledge_points.id` |
| `name` | VARCHAR(160) | 否 | 名称 |
| `description` | TEXT | 是/NULL | 定义 |
| `exam_importance` | NUMERIC(4,3) | 否/0.5 | CHECK 0～1 |
| `difficulty` | VARCHAR(20) | 否/`basic` | 难度 |
| `estimated_minutes` | SMALLINT | 否/45 | CHECK > 0 |
| `source` | VARCHAR(20) | 否/`manual` | `manual/extracted` |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：活跃知识点 `UNIQUE(course_id,lower(name)) WHERE deleted_at IS NULL`；普通索引 `parent_id`；联合 `(course_id,exam_importance DESC)`。服务层校验父节点属于同课程。软删除：是。

## 9. `knowledge_dependencies`：知识点前置关系

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `prerequisite_id` | BIGINT | 否 | FK → `knowledge_points.id` |
| `dependent_id` | BIGINT | 否 | FK → `knowledge_points.id` |
| `weight` | NUMERIC(4,3) | 否/1.0 | CHECK 0～1 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：`UNIQUE(course_id,prerequisite_id,dependent_id)`；CHECK `prerequisite_id <> dependent_id`；普通索引 `dependent_id`；联合 `(course_id,prerequisite_id)`、`(course_id,dependent_id)`。服务层拓扑检查防止间接环。软删除：是。

## 10. `resources`：可推荐学习资源

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `knowledge_point_id` | BIGINT | 是/NULL | FK → `knowledge_points.id` |
| `document_id` | BIGINT | 是/NULL | FK → `documents.id` |
| `title` | VARCHAR(255) | 否 | 标题 |
| `resource_type` | VARCHAR(30) | 否 | 文档/章节/视频/链接等 |
| `url_or_locator` | TEXT | 是/NULL | 外链或内部定位符 |
| `difficulty` | VARCHAR(20) | 否/`basic` | 难度 |
| `estimated_minutes` | SMALLINT | 是/NULL | CHECK > 0 |
| `quality_score` | NUMERIC(4,3) | 否/0.5 | CHECK 0～1 |
| `prerequisite_tags` | JSONB | 否/`[]` | 前置标签快照 |
| `audience_tags` | JSONB | 否/`[]` | 适合人群 |
| `exam_review_suitable` | BOOLEAN | 否/false | 考前复习 |
| `status` | VARCHAR(20) | 否/`active` | 可用状态 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：普通索引 `course_id`、`knowledge_point_id`、`document_id`；联合 `(course_id,knowledge_point_id,difficulty,status)`、`(course_id,quality_score DESC)`；可对 JSONB 标签建 GIN（有查询后再加）。软删除：是。

## 11. `questions`：题目

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `knowledge_point_id` | BIGINT | 是/NULL | FK → `knowledge_points.id` |
| `source_document_id` | BIGINT | 是/NULL | FK → `documents.id` |
| `question_type` | VARCHAR(30) | 否 | `single/multiple/true_false/short` |
| `stem` | TEXT | 否 | 题干 |
| `answer_json` | JSONB | 否 | 标准答案；作答接口不可提前返回 |
| `explanation` | TEXT | 是/NULL | 解析 |
| `difficulty` | VARCHAR(20) | 否/`basic` | 难度 |
| `quality_status` | VARCHAR(20) | 否/`draft` | `draft/reviewed/published/rejected` |
| `generated_by` | VARCHAR(20) | 否/`manual` | `manual/llm` |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：普通索引 `course_id`、`knowledge_point_id`；联合 `(course_id,knowledge_point_id,difficulty,quality_status)`。LLM 题必须校验/抽审后才 published。软删除：是。

## 12. `question_options`：选择题选项

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `question_id` | BIGINT | 否 | FK → `questions.id` ON DELETE CASCADE |
| `option_key` | VARCHAR(8) | 否 | A/B/C/D 等 |
| `content` | TEXT | 否 | 选项内容 |
| `is_correct` | BOOLEAN | 否/false | 仅教师/判分服务读取 |
| `sort_order` | SMALLINT | 否/0 | 展示顺序 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(question_id,option_key)`、`UNIQUE(question_id,sort_order)`；普通索引 `question_id`。软删除：否，题目版本变更时整体替换；历史作答保存答案快照。

## 13. `user_profiles`：课程级画像快照

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `profile_version` | INTEGER | 否/1 | 乐观版本 |
| `foundation_level` | VARCHAR(20) | 否/`unknown` | 课程基础 |
| `ability_score` | NUMERIC(5,4) | 是/NULL | 0～1 |
| `confidence` | NUMERIC(5,4) | 否/0 | 0～1 |
| `weak_point_ids` | BIGINT[] | 否/`{}` | 快照；权威分数仍在 mastery |
| `feature_json` | JSONB | 否/`{}` | 行为聚合特征 |
| `evidence_until` | TIMESTAMPTZ | 是/NULL | 数据截止时间 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(user_id,course_id)`；普通索引 `course_id`；联合 `(user_id,updated_at DESC)`。软删除：否；课程删除后不可见但保留分析依据。

## 14. `study_plans`：逻辑学习计划

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `name` | VARCHAR(160) | 否 | 计划名 |
| `goal` | TEXT | 否 | 计划目标 |
| `start_date` | DATE | 否 | 开始日 |
| `end_date` | DATE | 否 | 结束日，CHECK >= start_date |
| `active_version` | INTEGER | 是/NULL | 当前已确认版本号 |
| `status` | VARCHAR(20) | 否/`draft` | `draft/active/completed/cancelled` |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：同用户课程最多一个 active 的部分唯一索引 `(user_id,course_id) WHERE status='active' AND deleted_at IS NULL`；普通索引 `course_id`；联合 `(user_id,status,end_date)`。软删除：是。

## 15. `study_plan_versions`：计划版本

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `plan_id` | BIGINT | 否 | FK → `study_plans.id` |
| `version_no` | INTEGER | 否 | 从 1 递增 |
| `base_version_no` | INTEGER | 是/NULL | 调整来源 |
| `status` | VARCHAR(20) | 否/`draft` | `draft/active/superseded/rejected` |
| `algorithm_version` | VARCHAR(50) | 否 | 规则版本 |
| `input_snapshot` | JSONB | 否 | 当时约束和掌握度摘要 |
| `summary` | TEXT | 是/NULL | LLM/模板生成摘要 |
| `adjustment_reason` | TEXT | 是/NULL | 调整原因 |
| `diff_json` | JSONB | 否/`{}` | 新增/删除/推迟/时长差异 |
| `risk_json` | JSONB | 否/`[]` | 不可覆盖内容和风险 |
| `confirmed_by` | BIGINT | 是/NULL | FK → `users.id` |
| `confirmed_at` | TIMESTAMPTZ | 是/NULL | 确认时间 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(plan_id,version_no)`；每计划最多一个 active 的部分唯一索引；普通索引 `status`；联合 `(plan_id,status,created_at DESC)`。软删除：否，版本必须保留。

## 16. `study_tasks`：每日学习任务

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `plan_version_id` | BIGINT | 否 | FK → `study_plan_versions.id` |
| `stable_key` | UUID | 否/gen_random_uuid() | 跨版本识别同一逻辑任务 |
| `user_id` | BIGINT | 否 | FK → `users.id`，便于归属过滤 |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `knowledge_point_id` | BIGINT | 是/NULL | FK → `knowledge_points.id` |
| `task_date` | DATE | 否 | 任务日期 |
| `name` | VARCHAR(255) | 否 | 任务名 |
| `task_type` | VARCHAR(30) | 否 | 新知识/阅读/观看/练习/错题/测试/复习/模拟 |
| `estimated_minutes` | SMALLINT | 否 | CHECK 1～720 |
| `priority` | SMALLINT | 否/50 | CHECK 0～100 |
| `difficulty` | VARCHAR(20) | 否/`basic` | 难度 |
| `prerequisite_task_keys` | UUID[] | 否/`{}` | 同版本前置任务 stable_key |
| `resource_ids` | BIGINT[] | 否/`{}` | 推荐资源快照 |
| `question_ids` | BIGINT[] | 否/`{}` | 推荐题目快照 |
| `status` | VARCHAR(20) | 否/`pending` | `pending/in_progress/completed/skipped/cancelled` |
| `actual_minutes` | SMALLINT | 是/NULL | CHECK >= 0 |
| `completed_at` | TIMESTAMPTZ | 是/NULL | 完成时间 |
| `adjustment_reason` | TEXT | 是/NULL | 调整原因 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间/乐观锁 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 用户删除草稿任务 |

约束/索引：`UNIQUE(plan_version_id,stable_key)`；普通索引 `knowledge_point_id`、`task_date`；联合 `(user_id,task_date,status)`、`(plan_version_id,task_date,priority DESC)`、`(course_id,knowledge_point_id,status)`。软删除：是；已确认版本中的删除应在新版本标记取消而非破坏历史。

## 17. `learning_records`：学习行为与时长

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `task_id` | BIGINT | 是/NULL | FK → `study_tasks.id` |
| `knowledge_point_id` | BIGINT | 是/NULL | FK → `knowledge_points.id` |
| `record_type` | VARCHAR(30) | 否 | `study/view/click/complete/skip/favorite/rating` |
| `started_at` | TIMESTAMPTZ | 是/NULL | 开始时间 |
| `ended_at` | TIMESTAMPTZ | 是/NULL | 结束时间 |
| `duration_seconds` | INTEGER | 否/0 | CHECK >= 0；服务端校验异常时长 |
| `value_json` | JSONB | 否/`{}` | 评分、对象 ID 等事件数据 |
| `source` | VARCHAR(30) | 否/`web` | web/mcp/import |
| `idempotency_key` | VARCHAR(128) | 是/NULL | 客户端重试去重 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(user_id,idempotency_key)`（允许 NULL）；普通索引 `task_id`、`knowledge_point_id`；联合 `(user_id,course_id,created_at DESC)`、`(course_id,record_type,created_at)`。CHECK `ended_at >= started_at`。软删除：否，作为行为事实保留并按隐私策略归档。

## 18. `question_attempts`：答题记录

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `question_id` | BIGINT | 否 | FK → `questions.id` |
| `task_id` | BIGINT | 是/NULL | FK → `study_tasks.id` |
| `attempt_no` | INTEGER | 否 | 同题第几次，CHECK > 0 |
| `submitted_answer` | JSONB | 否 | 用户答案 |
| `correct_answer_snapshot` | JSONB | 否 | 作答时标准答案快照 |
| `is_correct` | BOOLEAN | 是/NULL | 主观题待批改可空 |
| `score` | NUMERIC(5,2) | 是/NULL | CHECK 0～100 |
| `duration_seconds` | INTEGER | 是/NULL | CHECK >= 0 |
| `feedback` | TEXT | 是/NULL | 受控解析 |
| `idempotency_key` | VARCHAR(128) | 否 | 防重复提交 |
| `created_at` | TIMESTAMPTZ | 否/now() | 提交时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 批改更新时间 |

约束/索引：`UNIQUE(user_id,idempotency_key)`、`UNIQUE(user_id,question_id,attempt_no)`；普通索引 `task_id`；联合 `(user_id,course_id,created_at DESC)`、`(user_id,question_id,created_at DESC)`。软删除：否。

## 19. `knowledge_mastery`：用户知识点掌握度

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `knowledge_point_id` | BIGINT | 否 | FK → `knowledge_points.id` |
| `mastery_score` | NUMERIC(5,4) | 否/0.5 | CHECK 0～1 |
| `confidence` | NUMERIC(5,4) | 否/0 | CHECK 0～1 |
| `evidence_count` | INTEGER | 否/0 | CHECK >= 0 |
| `correct_count` | INTEGER | 否/0 | CHECK >= 0 |
| `attempt_count` | INTEGER | 否/0 | CHECK >= correct_count |
| `last_studied_at` | TIMESTAMPTZ | 是/NULL | 最近学习 |
| `last_assessed_at` | TIMESTAMPTZ | 是/NULL | 最近评测 |
| `algorithm_version` | VARCHAR(50) | 否 | 更新算法版本 |
| `version` | INTEGER | 否/1 | 乐观锁/缓存版本 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(user_id,course_id,knowledge_point_id)`；普通索引 `knowledge_point_id`；联合 `(user_id,course_id,mastery_score)`、`(course_id,updated_at DESC)`。软删除：否；知识点软删后历史分数保留。

## 20. `wrong_questions`：错题本聚合

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `question_id` | BIGINT | 否 | FK → `questions.id` |
| `knowledge_point_id` | BIGINT | 是/NULL | FK → `knowledge_points.id` |
| `first_wrong_at` | TIMESTAMPTZ | 否 | 首次错误 |
| `last_wrong_at` | TIMESTAMPTZ | 否 | 最近错误 |
| `wrong_count` | INTEGER | 否/1 | CHECK > 0 |
| `last_attempt_id` | BIGINT | 否 | FK → `question_attempts.id` |
| `status` | VARCHAR(20) | 否/`active` | `active/reviewing/mastered/removed` |
| `mastered_at` | TIMESTAMPTZ | 是/NULL | 掌握时间 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 用户从错题本移除 |

约束/索引：`UNIQUE(user_id,question_id)`；普通索引 `knowledge_point_id`；联合 `(user_id,course_id,status,last_wrong_at DESC)`。软删除：是；再次答错时可恢复原记录。

## 21. `recommendation_records`：推荐曝光与反馈

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `item_type` | VARCHAR(30) | 否 | resource/question/task/knowledge_point |
| `item_id` | BIGINT | 否 | 多态对象 ID，服务层校验归属 |
| `request_id` | UUID | 否 | 一次推荐列表 |
| `algorithm_version` | VARCHAR(50) | 否 | 权重/候选算法版本 |
| `rank_position` | SMALLINT | 否 | CHECK > 0 |
| `score` | NUMERIC(7,4) | 否 | 0～100 |
| `score_breakdown` | JSONB | 否 | 六项分数及修正项 |
| `reason_facts` | JSONB | 否 | 可验证事实 |
| `reason_text` | TEXT | 否 | 展示理由 |
| `context_snapshot` | JSONB | 否 | 当时薄弱度/时长等，不含敏感信息 |
| `clicked_at` | TIMESTAMPTZ | 是/NULL | 点击 |
| `completed_at` | TIMESTAMPTZ | 是/NULL | 完成 |
| `skipped_at` | TIMESTAMPTZ | 是/NULL | 跳过 |
| `rating` | SMALLINT | 是/NULL | CHECK 1～5 |
| `mastery_delta` | NUMERIC(6,5) | 是/NULL | 后续效果，仅相关性指标 |
| `created_at` | TIMESTAMPTZ | 否/now() | 曝光时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 反馈更新时间 |

约束/索引：`UNIQUE(request_id,item_type,item_id)`；普通索引 `item_id`、`algorithm_version`；联合 `(user_id,course_id,created_at DESC)`、`(course_id,item_type,created_at)`。软删除：否，评价推荐效果所需。

## 22. `chat_sessions`：问答会话

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | UUID PK | 否/gen_random_uuid() | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `course_id` | BIGINT | 否 | FK → `courses.id` |
| `title` | VARCHAR(160) | 否/`新会话` | 标题 |
| `mode` | VARCHAR(20) | 否/`basic` | basic/exam/strict/teacher |
| `document_scope` | JSONB | 否/`{}` | 允许文档 ID；每次仍重新鉴权 |
| `last_message_at` | TIMESTAMPTZ | 是/NULL | 最近消息 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：普通索引 `course_id`；联合 `(user_id,course_id,last_message_at DESC)`、`(user_id,deleted_at)`。软删除：是。

## 23. `chat_messages`：聊天消息与引用快照

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | UUID PK | 否/gen_random_uuid() | 主键 |
| `session_id` | UUID | 否 | FK → `chat_sessions.id` |
| `role` | VARCHAR(20) | 否 | `user/assistant/system/tool` |
| `content` | TEXT | 否 | 消息正文 |
| `structured_content` | JSONB | 是/NULL | 模型结构化原结果 |
| `retrieval_query` | TEXT | 是/NULL | 改写后的查询 |
| `citations_json` | JSONB | 否/`[]` | chunk/document/version/page/quote 快照 |
| `model_name` | VARCHAR(100) | 是/NULL | 模型 |
| `prompt_version` | VARCHAR(50) | 是/NULL | 提示词版本 |
| `token_usage_json` | JSONB | 否/`{}` | token 用量 |
| `latency_ms` | INTEGER | 是/NULL | CHECK >= 0 |
| `request_id` | UUID | 否 | 追踪/幂等 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 单条软删（一般随会话隐藏） |

约束/索引：`UNIQUE(session_id,request_id,role)`（同请求各角色一次）；普通索引 `request_id`；联合 `(session_id,created_at)`。软删除：是。

## 24. `agent_runs`：Agent 一次运行

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | UUID PK | 否/gen_random_uuid() | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `session_id` | UUID | 是/NULL | FK → `chat_sessions.id` |
| `goal` | TEXT | 否 | 用户目标摘要 |
| `status` | VARCHAR(20) | 否/`running` | running/waiting_confirmation/success/failed/cancelled |
| `model_name` | VARCHAR(100) | 是/NULL | 模型 |
| `input_json` | JSONB | 否 | 脱敏输入 |
| `output_json` | JSONB | 是/NULL | 最终结果 |
| `error_code` | VARCHAR(80) | 是/NULL | 错误码 |
| `started_at` | TIMESTAMPTZ | 否/now() | 开始 |
| `ended_at` | TIMESTAMPTZ | 是/NULL | 结束 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：普通索引 `session_id`、`status`；联合 `(user_id,created_at DESC)`、`(status,started_at)`。软删除：否，按保留期归档。

## 25. `mcp_tool_calls`：MCP 工具审计

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `agent_run_id` | UUID | 是/NULL | FK → `agent_runs.id` |
| `tool_name` | VARCHAR(100) | 否 | 工具名 |
| `arguments_json` | JSONB | 否 | 脱敏参数 |
| `result_json` | JSONB | 是/NULL | 脱敏/截断结果 |
| `status` | VARCHAR(20) | 否/`running` | running/success/failed/denied |
| `is_write` | BOOLEAN | 否/false | 是否副作用 |
| `confirmation_id` | UUID | 是/NULL | 确认记录/预览 ID |
| `idempotency_key_hash` | CHAR(64) | 是/NULL | 不存明文键 |
| `error_code` | VARCHAR(80) | 是/NULL | 标准错误码 |
| `error_message` | TEXT | 是/NULL | 脱敏错误 |
| `request_id` | UUID | 否 | 全链路跟踪 |
| `started_at` | TIMESTAMPTZ | 否/now() | 开始 |
| `ended_at` | TIMESTAMPTZ | 是/NULL | 结束 |
| `duration_ms` | INTEGER | 是/NULL | CHECK >= 0 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(request_id)`；写操作成功时可建部分唯一 `(user_id,tool_name,idempotency_key_hash) WHERE is_write AND status='success'`；普通索引 `agent_run_id`、`tool_name`；联合 `(user_id,created_at DESC)`、`(status,started_at)`。软删除：否，按审计保留期归档。

## 26. `async_tasks`：长时任务

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | UUID PK | 否/gen_random_uuid() | task_id |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `task_type` | VARCHAR(80) | 否 | 任务类型 |
| `resource_type` | VARCHAR(50) | 是/NULL | document/plan/report 等 |
| `resource_id` | VARCHAR(80) | 是/NULL | 关联对象 ID（不同类型） |
| `status` | VARCHAR(30) | 否/`queued` | 七种任务状态 |
| `dispatch_status` | VARCHAR(20) | 否/`pending` | pending/sent/failed |
| `progress` | SMALLINT | 否/0 | CHECK 0～100 |
| `current_step` | VARCHAR(100) | 是/NULL | 当前阶段 |
| `input_data` | JSONB | 否 | 脱敏输入 |
| `result_data` | JSONB | 是/NULL | 结果摘要/地址 |
| `checkpoint_json` | JSONB | 否/`{}` | 恢复点 |
| `error_code` | VARCHAR(80) | 是/NULL | 错误码 |
| `error_message` | TEXT | 是/NULL | 脱敏错误 |
| `retry_count` | SMALLINT | 否/0 | CHECK >= 0 |
| `max_retries` | SMALLINT | 否/3 | CHECK 0～10 |
| `idempotency_key` | VARCHAR(128) | 否 | 用户任务去重 |
| `cancel_requested_at` | TIMESTAMPTZ | 是/NULL | 协作取消 |
| `started_at` | TIMESTAMPTZ | 是/NULL | 开始 |
| `finished_at` | TIMESTAMPTZ | 是/NULL | 完成 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |

约束/索引：`UNIQUE(user_id,task_type,idempotency_key)`；普通索引 `resource_id`；联合 `(user_id,status,created_at DESC)`、`(dispatch_status,created_at)`、`(status,updated_at)`。软删除：否，历史用于恢复和审计。

## 27. `notifications`：站内/邮件/消息通知

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `channel` | VARCHAR(20) | 否/`in_app` | in_app/email/message |
| `type` | VARCHAR(50) | 否 | task_done/reminder/report 等 |
| `title` | VARCHAR(200) | 否 | 标题 |
| `content` | TEXT | 否 | 正文 |
| `data_json` | JSONB | 否/`{}` | 跳转对象等 |
| `status` | VARCHAR(20) | 否/`pending` | pending/sent/failed/read |
| `idempotency_key` | VARCHAR(128) | 否 | 防重复发送 |
| `scheduled_at` | TIMESTAMPTZ | 是/NULL | 计划发送 |
| `sent_at` | TIMESTAMPTZ | 是/NULL | 已发送 |
| `read_at` | TIMESTAMPTZ | 是/NULL | 已读 |
| `error_message` | TEXT | 是/NULL | 脱敏错误 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 用户删除通知 |

约束/索引：`UNIQUE(user_id,channel,idempotency_key)`；普通索引 `status`；联合 `(user_id,status,created_at DESC)`、`(status,scheduled_at)`。软删除：是。

## 28. `calendar_accounts`：第三方日历授权

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `user_id` | BIGINT | 否 | FK → `users.id` |
| `provider` | VARCHAR(40) | 否 | google/microsoft/other |
| `provider_account_id` | VARCHAR(255) | 否 | 远端账户标识 |
| `display_name` | VARCHAR(120) | 是/NULL | 展示名 |
| `encrypted_access_token` | BYTEA | 否 | 应用级加密 |
| `encrypted_refresh_token` | BYTEA | 是/NULL | 应用级加密 |
| `token_expires_at` | TIMESTAMPTZ | 是/NULL | 过期时间 |
| `scopes` | TEXT[] | 否/`{}` | 授权范围 |
| `status` | VARCHAR(30) | 否/`active` | active/expired/reauth_required/revoked |
| `sync_cursor` | TEXT | 是/NULL | 增量同步游标 |
| `last_synced_at` | TIMESTAMPTZ | 是/NULL | 最近同步 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 解绑软删 |

约束/索引：`UNIQUE(user_id,provider,provider_account_id)`；普通索引 `status`；联合 `(user_id,status)`、`(status,token_expires_at)`。软删除：是；解绑同时撤销远端 Token。

## 29. `calendar_events`：本地任务与远端日历映射

| 字段 | 类型 | 可空/默认 | 关系或说明 |
|---|---|---|---|
| `id` | BIGSERIAL PK | 否 | 主键 |
| `calendar_account_id` | BIGINT | 否 | FK → `calendar_accounts.id` |
| `user_id` | BIGINT | 否 | FK → `users.id`，归属过滤 |
| `study_task_id` | BIGINT | 是/NULL | FK → `study_tasks.id` |
| `provider_event_id` | VARCHAR(255) | 是/NULL | 远端事件 ID |
| `title` | VARCHAR(255) | 否 | 事件标题 |
| `description` | TEXT | 是/NULL | 说明 |
| `start_at` | TIMESTAMPTZ | 否 | 开始 |
| `end_at` | TIMESTAMPTZ | 否 | CHECK end > start |
| `timezone` | VARCHAR(64) | 否 | IANA 时区 |
| `remote_version` | VARCHAR(255) | 是/NULL | etag/version，乐观并发 |
| `sync_status` | VARCHAR(30) | 否/`pending` | pending/synced/failed/conflict/deleted |
| `idempotency_key` | VARCHAR(128) | 否 | 防重复创建 |
| `last_synced_at` | TIMESTAMPTZ | 是/NULL | 最近同步 |
| `error_message` | TEXT | 是/NULL | 脱敏错误 |
| `created_at` | TIMESTAMPTZ | 否/now() | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否/now() | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是/NULL | 软删除 |

约束/索引：`UNIQUE(calendar_account_id,provider_event_id)`（NULL 可重复）、`UNIQUE(calendar_account_id,idempotency_key)`；普通索引 `study_task_id`；联合 `(user_id,start_at,end_at)`、`(calendar_account_id,sync_status,updated_at)`。软删除：是，远端已删仍保留审计映射。

## 跨表一致性与删除策略

- 创建课程时同事务写 `courses` 和 owner 的 `course_members`。
- 上传新版本先写 `document_versions`；解析全部成功后同事务更新 `documents.current_version/status`，失败不改变当前 ready 版本。
- 确认计划时锁定 `study_plans` 行并检查基础版本；同事务切换版本状态与 `active_version`。
- 提交答案时同事务写 `question_attempts`、upsert `wrong_questions`，再以事件/任务更新 `knowledge_mastery`；重复幂等键不得重复计数。
- 用户/课程删除以软删为主；异步清理对象存储和向量块。聊天、行为、Agent/MCP/任务日志按隐私与审计保留期脱敏归档。
- 多态字段（推荐 `item_id`、异步 `resource_id`）无法由普通 FK 完整约束，必须在 Service 中校验类型、存在性和归属；MVP 后数据模型稳定可拆为显式关联表。

# 16. pgvector 向量检索设计

## 扩展、字段与索引

下面 SQL 以 1024 维余弦距离为例；切换 Embedding 模型前必须迁移维度并重建向量，不能把不同模型向量混在同一索引中。

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- 关键字段示意；完整字段见 document_chunks 表设计。
CREATE TABLE document_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    document_version INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    page_number INTEGER,
    chapter_name VARCHAR(255),
    token_count INTEGER,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    UNIQUE (document_id, document_version, chunk_index),
    FOREIGN KEY (document_id, document_version)
      REFERENCES document_versions(document_id, version_no)
);

CREATE INDEX idx_chunks_filter
    ON document_chunks(course_id, document_id, document_version)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_chunks_embedding_hnsw
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE deleted_at IS NULL;
```

HNSW 查询快、无需训练，适合持续上传；它占内存较多。实训早期切块少时可先做精确查询，数据增长后再建 HNSW。若使用 IVFFlat，必须在有代表性数据后建索引并执行 `ANALYZE`。

## 只查当前版本的相似度 SQL

```sql
SELECT
    dc.id AS chunk_id,
    dc.document_id,
    d.title AS document_name,
    dc.document_version,
    dc.content,
    dc.page_number,
    dc.chapter_name,
    1 - (dc.embedding <=> CAST(:query_embedding AS vector)) AS similarity
FROM document_chunks AS dc
JOIN documents AS d ON d.id = dc.document_id
JOIN course_members AS cm
  ON cm.course_id = dc.course_id
 AND cm.user_id = :user_id
 AND cm.deleted_at IS NULL
WHERE dc.course_id = :course_id
  AND dc.deleted_at IS NULL
  AND d.deleted_at IS NULL
  AND d.status = 'ready'
  AND dc.document_version = d.current_version
  AND (:document_ids_is_null OR dc.document_id = ANY(:document_ids))
ORDER BY dc.embedding <=> CAST(:query_embedding AS vector)
LIMIT :top_k;
```

注意：不能只过滤 `document_version = 1`，因为不同文档的当前版本可能不同；必须逐文档与 `documents.current_version` 对比。指定 `document_ids` 前仍要验证都属于该课程。

## 带阈值的查询

```sql
WITH candidates AS (
    SELECT dc.*,
           dc.embedding <=> CAST(:query_embedding AS vector) AS distance
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id
    WHERE dc.course_id = :course_id
      AND dc.document_version = d.current_version
      AND dc.deleted_at IS NULL
      AND d.deleted_at IS NULL
      AND d.status = 'ready'
    ORDER BY dc.embedding <=> CAST(:query_embedding AS vector)
    LIMIT :candidate_k
)
SELECT id, document_id, content, page_number, chapter_name,
       1 - distance AS similarity
FROM candidates
WHERE 1 - distance >= :min_similarity
ORDER BY distance
LIMIT :top_k;
```

余弦“距离”越小越相似，`similarity = 1 - distance` 越大越相似。阈值不能拍脑袋固定，应以课程问答集调参；不同模型的分数分布不同。

## 可选关键词 + 向量混合检索

MVP 可先只做向量。第二阶段给 `content` 增加中文分词/全文检索配置，从向量与关键词各取 Top-N，再在应用层用 RRF：

```text
rrf_score(document) = Σ 1 / (60 + rank_in_each_list)
```

随后按 `rrf_score` 取 20 个候选交给 reranker。不要直接相加未经归一化的余弦分和全文检索分。

## 性能与正确性检查

1. 批量写入向量（如 32～128 块/批），完成后 `ANALYZE document_chunks`。
2. HNSW 过滤后可能候选不足；先调大候选范围/`hnsw.ef_search`，新版 pgvector 可评估 iterative scan，再考虑按大课程分区。
3. 使用 `EXPLAIN (ANALYZE, BUFFERS)` 检查是否使用向量索引与 B-tree 过滤索引。
4. 抽样验证 `chunk_id → 文档版本 → 页码 → 原文` 一致；页码引用错误比回答慢更影响可信度。
5. 删除文档先软删并停止检索，之后异步物理清理旧切块；重建索引在低峰期执行。
6. Embedding 模型/维度/预处理变更时创建新版本或新列，双写验证后切换，不能静默覆盖。

