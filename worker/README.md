# Celery Worker

长时任务的定义与业务服务放在 `backend/app/tasks/`，以确保 API 与 Worker 共用同一套权限、幂等和状态更新逻辑。该目录保留部署说明与后续独立拆分入口；当前 `docker-compose.yml` 使用后端同一镜像启动 Celery Worker。

任务执行必须遵循：

1. API 先写入 `async_tasks` 并返回 `task_id`；
2. Worker 用幂等锁把状态改为 `processing`；
3. 每个阶段同时更新 PostgreSQL 关键状态和 Redis 进度；
4. 成功、失败、取消都落库；
5. 重试不能重复生成文档块、计划版本或第三方日历事件。
