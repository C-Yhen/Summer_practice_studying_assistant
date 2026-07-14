# 智能学习助手设计文档导航

> 项目：《基于 MCP、RAG 与个性化推荐的智能学习助手》  
> 文档状态：**实施前设计方案**。本文档描述建议的目标架构、接口和实现顺序，不代表仓库中已经完成这些功能。  
> 适用团队：3～5 人、8 周暑期实训；默认按 4 人分工。  
> 阅读方式：请严格按下列 1～27 顺序阅读。每个模块尽量采用“是什么 → 为什么 → 怎么做 → 输入/处理/输出”的结构。

## 严格输出顺序

| 序号 | 主题 | 文档 |
|---:|---|---|
| 1 | 项目简介 | [01-overview-and-architecture.md](./01-overview-and-architecture.md#1-项目简介) |
| 2 | 项目解决的问题 | [01-overview-and-architecture.md](./01-overview-and-architecture.md#2-项目解决的问题) |
| 3 | 目标用户 | [01-overview-and-architecture.md](./01-overview-and-architecture.md#3-目标用户) |
| 4 | 系统功能模块 | [01-overview-and-architecture.md](./01-overview-and-architecture.md#4-系统功能模块) |
| 5 | 系统总体架构 | [01-overview-and-architecture.md](./01-overview-and-architecture.md#5-系统总体架构) |
| 6 | PostgreSQL、pgvector 和 Redis 的职责划分 | [01-overview-and-architecture.md](./01-overview-and-architecture.md#6-postgresqlpgvector-和-redis-的职责划分) |
| 7 | RAG 实现流程 | [02-intelligence-design.md](./02-intelligence-design.md#7-rag-实现流程) |
| 8 | 学习计划算法 | [02-intelligence-design.md](./02-intelligence-design.md#8-学习计划算法) |
| 9 | 动态计划调整算法 | [02-intelligence-design.md](./02-intelligence-design.md#9-动态计划调整算法) |
| 10 | 推荐系统设计 | [02-intelligence-design.md](./02-intelligence-design.md#10-推荐系统设计) |
| 11 | MCP 工具设计 | [03-mcp-and-infrastructure.md](./03-mcp-and-infrastructure.md#11-mcp-工具设计) |
| 12 | 第三方服务设计 | [03-mcp-and-infrastructure.md](./03-mcp-and-infrastructure.md#12-第三方服务设计) |
| 13 | Redis 缓存设计 | [03-mcp-and-infrastructure.md](./03-mcp-and-infrastructure.md#13-redis-缓存设计) |
| 14 | Celery 长时任务设计 | [03-mcp-and-infrastructure.md](./03-mcp-and-infrastructure.md#14-celery-长时任务设计) |
| 15 | 数据库表设计（29 张） | [04-database-and-pgvector.md](./04-database-and-pgvector.md#15-数据库表设计) |
| 16 | pgvector 向量检索设计 | [04-database-and-pgvector.md](./04-database-and-pgvector.md#16-pgvector-向量检索设计) |
| 17 | API 接口设计 | [05-api-and-frontend.md](./05-api-and-frontend.md#17-api-接口设计) |
| 18 | 前端页面设计 | [05-api-and-frontend.md](./05-api-and-frontend.md#18-前端页面设计) |
| 19 | 项目目录结构 | [06-delivery-plan.md](./06-delivery-plan.md#19-项目目录结构) |
| 20 | 核心代码示例 | [06-delivery-plan.md](./06-delivery-plan.md#20-核心代码示例) |
| 21 | 团队分工 | [06-delivery-plan.md](./06-delivery-plan.md#21-团队分工) |
| 22 | 开发时间安排 | [06-delivery-plan.md](./06-delivery-plan.md#22-开发时间安排) |
| 23 | 测试方案 | [06-delivery-plan.md](./06-delivery-plan.md#23-测试方案) |
| 24 | 项目创新点 | [06-delivery-plan.md](./06-delivery-plan.md#24-项目创新点) |
| 25 | 项目风险 | [06-delivery-plan.md](./06-delivery-plan.md#25-项目风险) |
| 26 | 答辩演示流程 | [06-delivery-plan.md](./06-delivery-plan.md#26-答辩演示流程) |
| 27 | 最小可用版本实现顺序 | [06-delivery-plan.md](./06-delivery-plan.md#27-最小可用版本实现顺序) |

## 全局设计原则

1. 数据负责判断，规则负责约束，大模型负责表达。
2. 大模型只返回经过 Pydantic 校验的结构化 JSON，不直接连接或修改数据库。
3. 所有写操作经过后端服务层；重要写操作校验 JWT、资源归属和权限。
4. 创建任务、调整计划、写日历等副作用操作，必须先生成预览并取得一次性确认令牌。
5. 文档与学习计划都保留版本；新请求只使用当前有效版本。
6. 推荐必须保存分数分解和自然语言理由，不能只返回一个资源 ID。
7. 长时任务必须有持久化状态、幂等键、进度查询、超时、重试和取消能力。
8. 第一目标是“稳定可演示的闭环”，扩展功能不能挤占 MVP 的联调和测试时间。

