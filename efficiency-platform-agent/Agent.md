# Agent 侧开发总纲

## 1. 使命与边界

本工程采用 **Harnessed Hybrid Multi-Agent Architecture（受控混合多 Agent 架构）**，为纯 Agent 侧提供可治理、可恢复、可观测的运行底座。它 MUST NOT 承担 Java 侧工程、业务系统架构或部署拓扑；当前已具备离线契约级运营 Specialist 与 Scenario Pack，但 MUST NOT 在未完成真实验收前宣称生产业务可用，也不得接入 ASR、TTS、语音视频、内容审核或付费商业热点数据源。

## 2. 总体架构范式

每次请求 MUST 经过 Inbound API、Contracts、Agent Harness、Strategy Router、统一 Graph Runtime、Context/Tool/Memory/Capability、Provider 与 Persistence。Harness MUST 统一身份、权限、预算、超时、取消、Checkpoint、审计边界、关联标识与错误映射；所有策略 MUST 共享该治理边界。LangGraph 是唯一 Graph Runtime，MUST NOT 并存第二套编排内核。完整 Trace、Metric 与监控平台属于后置专项，不是 P1 依赖。

## 3. 执行策略

Strategy Router MUST 按意图、风险、复杂度、工具需要、延迟与成本选择策略，而不是自行编排专家：

- **Direct**：单轮、低风险、无需工具；MUST NOT 无意义进入循环。
- **Workflow**：步骤固定或强审计；路径 SHOULD 保持确定。
- **ReAct**：需要少量动态 Tool 调用；MUST 限制工具白名单、步数、Token 与时间预算。
- **Plan-and-Execute**：长任务、可分解且可能重规划；Planner、Executor 与 Replanner MUST 使用可持久化计划。
- **Multi-Agent**：跨专业能力、并行或汇总需要；MUST 交由 Supervisor 受控调度。

## 4. 多 Agent 协作拓扑

Multi-Agent MUST 由 **Supervisor** Graph 接收路由结果，分配结构化子任务和裁剪上下文，控制并发、预算、权限与终止条件，并合并结构化结果、证据与错误。**Specialist Subgraph** 只能接收 Supervisor 分配的子任务，MUST NOT 与用户或其他专家自由对话，MUST NOT 直接调用其他专家；其输出 MUST 为可审计的结构化结果、证据、引用或错误。

Strategy Router 的职责是选择 Direct、Workflow、ReAct、Plan-and-Execute 或 Multi-Agent 执行模式；Supervisor 的职责仅在 Multi-Agent 模式内编排已选专家。二者 MUST NOT 相互替代或绕过统一 Harness。

## 5. 统一运行状态

Run MUST 采用 `CREATED → QUEUED → RUNNING → SUCCEEDED` 主路径。`CREATED` 只可进入 `QUEUED` 或 `CANCELLED`；`QUEUED` 可进入 `RUNNING`、`FAILED`、`CANCELLED`、`TIMED_OUT`；`RUNNING` 可进入三类 `WAITING` 或四个终态。`WAITING_TOOL`、`WAITING_INPUT`、`WAITING_APPROVAL` 必须先恢复到 `RUNNING`，或进入 `FAILED`、`CANCELLED`、`TIMED_OUT`，不得直接宣告成功。`SUCCEEDED`、`FAILED`、`CANCELLED`、`TIMED_OUT` 是不可逆终态；同状态重复事件按幂等事件允许，不产生新转换。非法跳转必须失败关闭。

暂停、恢复、补充输入与取消 MUST 通过同一 `run_id + checkpoint` 生命周期处理，而非建立旁路执行链；生产态持久化边界固定为 PostgreSQL `AsyncPostgresSaver`，当前尚未接入，MUST NOT 把标准库状态表测试描述为持久化恢复已验证。

## 6. 核心层职责

`core/contracts` MUST 保存稳定契约；`harness` 负责单次 Run 治理；`routing` 负责策略和模型选择；`orchestration` 负责图、状态机和 Checkpoint；`context` 负责唯一 Context Builder 与预算；`tools/runtime` 负责 Tool 治理；`providers` 负责厂商适配；`persistence` 负责权威状态；`observability/security/evaluation` 提供横切治理。内部层 MUST NOT 依赖 `api`，Provider 与 Persistence MUST NOT 反向依赖 Harness、Routing、Orchestration、Strategies、Agents 或 Workflows。

## 7. 扩展准入规则

新增 Agent、Strategy、Workflow、Tool、Provider、Prompt 或 Capability MUST 声明归属、输入输出 Schema、权限/预算、超时、失败处理、可观测字段和测试。Agent 与 Strategy MUST 通过注册机制接入；Tool MUST 经 Tool Runtime；Provider MUST 隔离厂商 SDK、响应、异常和配置键；Capability MAY 组合技术能力，但 MUST NOT 隐藏业务部门流程判断。新增跨层依赖、第二运行时或架构裁决变更 MUST 先有 ADR。

## 8. 上下文、工具与记忆

Context Builder MUST 是唯一上下文装配与预算入口，包含租户、用户、会话、历史与证据，并对外部内容作不可信标记。Memory MUST 区分短期、长期与情景记忆，检索结果 SHOULD 保留来源与引用。Tool MUST 声明 Schema、权限、幂等性、超时、重试、外部副作用与结果大小；MCP MAY 用于协议互操作，但 MUST NOT 绕过 Tool Runtime。

## 9. Provider 与技术能力

Provider MUST 通过稳定端口封装 LLM、Embedding、Rerank、OCR、数据库/向量、缓存、对象存储与公开搜索；上层 MUST NOT 感知厂商对象、异常或配置键。模型输出 MUST 先经 Schema 校验再进入 Graph State。当前 MUST NOT 引入 Text2SQL、模型生成 SQL 或面向业务数据库的直接分析；Agent 自有查询 MUST 使用受控 Repository 与参数化语句。能力可复用既有 PostgreSQL、pgvector、Redis、COS 与模型配置，但 MUST 使用 Agent 独立命名空间，MUST NOT 与 Java 表混写。Agent Runtime 与 Agent Vector 使用独立逻辑 PostgreSQL 数据源；MySQL MUST NOT 作为 Agent 运行状态、用量、统计或 Checkpoint 的基础依赖。

## 10. 禁止事项

MUST NOT 新增第二 Graph Runtime、去中心化 Swarm 或专家自由互聊；MUST NOT 绕过 Harness、Context Builder、Tool Runtime 或 Provider；MUST NOT 提交 Secret、记录原始敏感文档或把未校验模型文本当控制指令；MUST NOT 将 Redis、Taskiq Broker 或任务结果当权威状态；MUST NOT 执行未授权共享 DDL；MUST NOT 将内容审核未建设误解为可忽略基础安全控制。

## 11. 必读规范

实现前 MUST 阅读[纯 Agent 侧总体架构](docs/architecture/纯Agent侧总体架构.md)、[Agent 侧技术组件选型](docs/architecture/Agent侧技术组件选型.md)、[扩展开发约定](docs/architecture/扩展开发约定.md)及[工程规范索引](docs/standards/00-规范索引.md)。详细实现、质量和安全规则以索引及其链接文档为准。
