# 纯 Agent 侧总体架构

| 属性 | 内容 |
|---|---|
| 标题 | 纯 Agent 侧总体架构 |
| 状态 | 已批准 |
| 作者/负责人 | Agent 平台架构负责人 |
| 创建日期 | 2026-09-01 |
| 最后更新日期 | 2026-09-02 |
| 评审人/批准人 | 项目负责人（用户）；批准日期：2026-09-02；批准范围：纯 Agent 侧 P0～P5 总体架构；评审结论：架构骨架及跨阶段边界通过；证据：本次任务完成逐项确认并明确回复“确认” |
| 关联 ADR/设计/计划 | [Agent 侧 P0～P5 总体技术架构设计](../superpowers/specs/2026-09-02-Agent侧P0-P5总体技术架构-设计.md)、[Agent 侧架构骨架实施计划](../superpowers/plans/2026-09-01-Agent侧架构骨架-实施计划.md)、[Agent 侧技术组件选型](Agent侧技术组件选型.md)、[P1 Agent Runtime 技术组件选型设计](../superpowers/specs/2026-09-02-P1-Agent-Runtime技术组件选型-设计.md)、[扩展开发约定](扩展开发约定.md) |
| 替代关系 | 无 |
| 适用范围 | 纯 Agent 侧已批准架构基线与标准库骨架；不适用于 Java、部署或真实运行时接入 |

## 1. 当前架构最终基线

当前最终基线采用 **Harnessed Hybrid Multi-Agent Architecture（受控混合多 Agent 架构）**。P0～P5 技术架构和组件选型已经批准；批准不表示依赖已安装、代码已实现、PoC 已执行或系统可生产使用。

这不是在 ReAct、Plan-and-Execute 和 Multi-Agent 中三选一，而是：

1. 用 Agent Harness 统一治理每一次运行；
2. 用 Strategy Router 按任务特征选择执行策略；
3. 用同一个 Graph Runtime 承载 Direct、Workflow、ReAct、Plan-and-Execute 和 Multi-Agent；
4. 多 Agent 使用中央 Supervisor 调度专家 Agent 子图，禁止无治理的点对点自由聊天；
5. 所有策略共用上下文、工具、记忆、持久化、安全、观测和评测能力。

## 2. 完整逻辑架构

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Pure Agent Service Boundary                         │
│                                                                             │
│  ┌──────────────────────── Inbound Agent API ────────────────────────────┐  │
│  │ Run API │ Stream API │ Resume/Input API │ Cancel API │ Health/Meta API│  │
│  └──────────────────────────────────┬─────────────────────────────────────┘  │
│                                     │ normalized contracts                  │
│  ┌──────────────────────────── Agent Harness ─────────────────────────────┐  │
│  │ identity/context │ auth policy │ idempotency │ budget │ timeout/cancel │  │
│  │ guardrails       │ checkpoint  │ audit boundary │ correlation/log │ errors │  │
│  └──────────────────────────────────┬─────────────────────────────────────┘  │
│                                     │                                       │
│  ┌──────────────────────────── Strategy Router ───────────────────────────┐  │
│  │ intent/risk/complexity/tool need/latency/cost → execution mode         │  │
│  └───────┬──────────┬──────────┬──────────────────┬───────────────────────┘  │
│          │          │          │                  │                          │
│      Direct    Workflow     ReAct       Plan-and-Execute      Multi-Agent    │
│                                                            ┌─────────────┐  │
│                                                            │ Supervisor  │  │
│                                                            └──┬──┬──┬────┘  │
│                                                               │  │  │       │
│                                                       Specialist Agent      │
│                                                       Subgraphs / Plugins   │
│          └──────────┴──────────┴──────────────────┴─────────────┬─────────┘  │
│                                                                │            │
│  ┌──────────────────────── Unified Graph Runtime ───────────────┴─────────┐  │
│  │ graph/node/edge │ run state machine │ task lifecycle │ retry/fallback  │  │
│  │ pause/resume    │ checkpoint        │ human approval │ event streaming │  │
│  └───────────┬──────────────────────┬───────────────────────────┬──────────┘  │
│              │                      │                           │             │
│  ┌───────────▼──────────┐ ┌─────────▼──────────┐ ┌─────────────▼─────────┐  │
│  │ Unified Context      │ │ Governed Tool      │ │ Four-layer Memory     │  │
│  │ builder/budget       │ │ Runtime            │ │ working/short-term    │  │
│  │ tenant/user/session  │ │ schema/auth/timeout│ │ episodic/semantic     │  │
│  │ history/evidence     │ │ retry/MCP/audit    │ │ source/retention      │  │
│  └───────────┬──────────┘ └─────────┬──────────┘ └─────────────┬─────────┘  │
│              │                      │                           │             │
│  ┌───────────▼──────────────────────▼───────────────────────────▼─────────┐  │
│  │                         Technical Capabilities                         │  │
│  │ Model │ Retrieval/RAG │ Document │ OCR │ Public Research │ Analytics  │  │
│  │ Citation │ Artifact │ Prompt │ Structured Output │ Model Routing      │  │
│  └──────────────────────────────────┬─────────────────────────────────────┘  │
│                                     │ stable provider ports                 │
│  ┌──────────────────────────── Provider Adapters ─────────────────────────┐  │
│  │ LLM(+web_search) │ Embedding │ Rerank │ OCR │ DB/Vector │ Cache │ COS │  │
│  └──────────────────────────────────┬─────────────────────────────────────┘  │
│                                     │                                       │
│  ┌──────────────────── Persistence & Async Execution ─────────────────────┐  │
│  │ PostgreSQL truth │ Taskiq/Redis │ outbox │ checkpoint │ events/memory │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────── Cross-cutting Governance ──────────────────────┐  │
│  │ Security │ Structured Log │ Runtime Event │ Audit │ Quota │ Config       │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 3. 代码骨架

```text
efficiency-platform-agent/
├─ pyproject.toml
├─ README.md
├─ docs/
│  ├─ architecture/
│  │  ├─ 纯Agent侧总体架构.md
│  │  ├─ 扩展开发约定.md
│  │  └─ Agent侧技术组件选型.md
│  └─ superpowers/plans/
├─ src/efficiency_platform_agent/
│  ├─ api/                       # 纯 Agent 入站协议、流式事件和恢复入口
│  ├─ contracts/                 # 请求、响应、事件、错误与 Schema
│  ├─ harness/                   # 每次 Run 的统一治理外壳
│  ├─ routing/                   # 意图、策略、风险与模型路由
│  ├─ orchestration/             # 统一图运行时、状态机与 Checkpoint
│  ├─ strategies/
│  │  ├─ direct/                 # 直接回答
│  │  ├─ workflow/               # 确定性流程
│  │  ├─ react/                  # 受控思考-行动循环
│  │  ├─ plan_execute/           # 规划、执行、重规划
│  │  └─ multi_agent/            # Supervisor 与专家子图
│  ├─ agents/                    # 未来业务/专家 Agent 插件注册槽
│  ├─ workflows/                 # 可复用确定性工作流
│  ├─ context/                   # 唯一 Context Builder 和预算管理
│  ├─ memory/                    # 工作、短期、情景、语义四层记忆
│  ├─ prompts/                   # Prompt 模板、版本和渲染
│  ├─ tools/
│  │  ├─ runtime/                # Schema、权限、超时、重试、审计
│  │  ├─ internal/               # Agent 内建工具
│  │  ├─ external/               # 外部系统适配工具
│  │  └─ mcp/                    # MCP Client 适配；不建设 MCP Server
│  ├─ capabilities/
│  │  ├─ model/                  # 模型调用、降级、结构化输出
│  │  ├─ retrieval/              # 索引、混检、融合、重排
│  │  ├─ document/               # 文档解析和表格抽取
│  │  ├─ ocr/                    # 本地 OCR；云 OCR 仅保留关闭的可选端口
│  │  ├─ research/               # LLM 服务端公共信息研究
│  │  ├─ analytics/              # 表格读取、清洗、聚合与统计
│  │  ├─ citation/               # 证据、来源和引用
│  │  └─ artifact/               # 产物生命周期
│  ├─ providers/
│  │  ├─ llm/                    # LLM 适配器
│  │  ├─ embedding/              # Embedding 适配器
│  │  ├─ rerank/                 # Rerank 适配器
│  │  ├─ ocr/                    # OCR Provider
│  │  ├─ storage/                # COS/对象存储适配器
│  │  ├─ database/               # PostgreSQL/pgvector 适配器
│  │  ├─ cache/                  # Redis 适配器
│  │  └─ search/                 # 预留槽；P4 当前不启用独立搜索源
│  ├─ persistence/               # Run、Checkpoint、四层 Memory、Artifact 持久化
│  ├─ tasks/                     # 异步任务边界；周期调度后置
│  ├─ observability/             # P1 结构化日志/关联接口；Trace、Metric 后置
│  ├─ evaluation/                # 确定性离线评测和回归集
│  ├─ security/                  # 输入、工具、资源、输出安全边界
│  └─ core/                      # 标准库实现的稳定领域契约
└─ tests/
   └─ architecture/              # 结构与依赖方向自动守卫
```

## 4. 一次请求的执行链

```text
Inbound API
  → Contracts 归一化
  → Agent Harness 建立 RunContext、预算、权限、关联标识、Checkpoint
  → Strategy Router 选择执行模式
  → Unified Graph Runtime 执行对应策略或 Supervisor 子图
  → Context / Tool / Memory / Capability 协作
  → Provider Adapter 调用外部技术组件
  → 持久化状态与事件
  → 统一结果、引用、产物和流式事件返回
```

恢复、审批和补充输入不是新建另一套执行链，而是通过 `run_id + checkpoint` 回到同一条 Graph Run。

## 5. 策略选择原则

| 模式 | 使用条件 | 核心约束 |
|---|---|---|
| Direct | 单轮、低风险、无需工具 | 禁止无意义进入 Agent 循环 |
| Workflow | 步骤固定、审计要求高 | 路径确定，模型只处理指定节点 |
| ReAct | 需要少量动态工具调用 | 限制最大步数、工具范围和预算 |
| Plan-and-Execute | 长任务、可分解、可能重规划 | Planner 与 Executor 分离，计划可持久化 |
| Multi-Agent | 跨专业能力、需要并行或汇总 | 中央 Supervisor 调度，专家之间不自由互聊 |

## 6. 多 Agent 拓扑

```text
Strategy Router
      │
      ▼
Supervisor Agent / Graph
  ├─ 选择专家 Agent
  ├─ 分配子任务与上下文切片
  ├─ 控制并发、预算、权限和终止条件
  ├─ 收集结构化结果与证据
  └─ 冲突处理、重试、合并和最终交付
          │
          ├─ Specialist Agent Plugin A
          ├─ Specialist Agent Plugin B
          └─ Specialist Agent Plugin N
```

未来人事、行政、运营、智能数据和客服等都只作为 Specialist Agent Plugin 或受控 Workflow 接入，不改变底层骨架。

## 7. 四层记忆

四层记忆是一个受治理 Memory 子系统内的数据语义分层，不是四套数据库：

| 记忆层 | 内容 | 技术落点 |
|---|---|---|
| 工作记忆 | 当前 Run 的 Graph State、步骤和中间结果 | LangGraph State + AsyncPostgresSaver |
| 短期记忆 | 当前会话最近消息、补充输入和连续上下文 | PostgreSQL 权威存储；Redis 仅作热点缓存 |
| 情景记忆 | 历史任务、关键决策、结果、失败经验、时间和来源 | PostgreSQL 结构化记录；按需进入 pgvector |
| 语义记忆 | 稳定知识、制度、文档、事实、概念和规则 | PostgreSQL 元数据 + pgvector + PostgreSQL FTS |

所有访问统一经过 Memory Port，并执行租户、用户、Agent、权限、来源和保留期限隔离。Run Event 和会话原文不能未经筛选、脱敏与结构化就自动提升为长期记忆。当前不引入 Mem0、Zep、Letta 或独立记忆服务。

## 8. 统一运行状态

```text
CREATED → QUEUED → RUNNING ───────────────→ SUCCEEDED
                        ├─→ WAITING_TOOL ──┤
                        ├─→ WAITING_INPUT ─┤
                        ├─→ WAITING_APPROVAL
                        ├─→ FAILED
                        ├─→ CANCELLED
                        └─→ TIMED_OUT
```

`CREATED` 不得跳过 `QUEUED` 直接运行；三类 `WAITING` 只能恢复到 `RUNNING` 或进入 `FAILED` / `CANCELLED` / `TIMED_OUT`；四个终态不可逆。同状态重复事件按幂等允许。不可变转换表与校验函数已在 `core` 形成框架中立代码契约，但真实 Checkpoint、恢复和 Graph Runtime 尚未接入。

## 9. 依赖方向

```text
API → Harness → Routing / Orchestration → Strategies / Agents / Workflows
                                            ↓
                   Context / Memory / Tools / Capabilities
                                            ↓
                         Providers / Persistence
                                            ↓
                              Core / Contracts
```

`core` 不依赖任何上层；内部层不得引用 `api`；Provider 和 Persistence 不得反向依赖执行策略。上述约束由 AST 架构测试自动检查。

## 10. 当前明确不进入骨架的内容

- Java 侧接口、领域、网关、权限和数据架构；
- 具体业务 Agent、业务 Workflow 和业务 Prompt；
- 容器、集群、服务发现、弹性伸缩等部署设计；
- ASR、TTS、语音与视频输入输出；
- 内容审核；
- 任何付费商业热点数据源；
- 去中心化 Swarm 和 Agent 间自由聊天；
- MCP Server、Text2SQL、在线评测、周期调度、性能压测和监控平台。
