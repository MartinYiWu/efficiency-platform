# ADR-0005：Agent 运行态使用 MySQL

- 状态：已接受
- 日期：2026-10-15
- 决策范围：运营助手 MVP 及其 Agent 运行态持久化
- 替代范围：替代既有文档中“Agent Runtime 关系事实只使用 PostgreSQL”的部分；向量存储决策不变

## 背景

开发环境已经提供 Agent 独立 MySQL 数据库 `ai_efficiency_platform_agent`，向量数据库为 PostgreSQL + pgvector。现有 Agent 真实工厂仍使用内存 Run/Event/取消实现，服务重启会丢失运行状态，不能满足运营助手真实联调和失败审计。

## 决策

1. `ai_efficiency_platform_agent` 保存 Run、Run Event、幂等请求和运行恢复所需的结构化状态。
2. PostgreSQL + pgvector 继续保存 Document、Chunk、Embedding 和向量索引；不迁移到 MySQL。
3. Redis 只承担短期事件转发、取消信号和有 TTL 的幂等缓存，不作为长期权威事实。
4. Agent 通过 SQLAlchemy 2 async 和 MySQL 异步驱动实现既有 `RunRepository`、`RunEventStore` 协议；领域层不依赖数据库实现。
5. Run 更新使用 `run_id + version` 乐观锁；事件使用 `(run_id, sequence_no)` 唯一键；请求使用 `(tenant_id, request_id)` 唯一键。
6. 运行数据库配置缺失或不可连接时，真实运行模式启动失败，不自动回退内存实现。
7. LangGraph Checkpoint 暂不随本 ADR 迁移。MVP 先持久化对外可观察的 Run/Event 和恢复输入；需要图级断点恢复时另立决策并执行真实恢复验收。

## 后果

Agent 增加 MySQL 驱动、DDL 和适配器；原 PostgreSQL Runtime 实验代码不再是运营助手真实工厂的默认实现。向量检索代码和连接保持不变。数据库口令允许存在于用户批准的开发配置中，但日志、验收报告和接口响应不得输出凭证。

## 验证

验收必须启动真实 Agent，提交真实消息，确认同一 `runId` 的 Run/Event 出现在 MySQL，并在 Java/Agent 日志中没有未处理数据库错误。仅通过 repository 单元测试不算完成。
