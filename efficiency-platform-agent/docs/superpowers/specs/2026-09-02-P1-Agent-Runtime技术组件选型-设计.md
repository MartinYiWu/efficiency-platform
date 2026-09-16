# P1 Agent Runtime 技术组件选型设计

| 属性 | 内容 |
|---|---|
| 标题 | P1 Agent Runtime 技术组件选型设计 |
| 状态 | 已批准 |
| 作者/负责人 | Agent 平台架构负责人 |
| 创建日期 | 2026-09-02 |
| 最后更新日期 | 2026-09-02 |
| 评审人/批准人 | 评审人/批准人：项目负责人（用户）；批准日期：2026-09-02；批准范围：本文第 1～16 节 P1 技术基线；证据：本次任务中对书面设计的明确“确认”回复 |
| 关联 ADR/设计/计划 | [纯 Agent 侧总体架构](../../architecture/纯Agent侧总体架构.md)、[Agent 侧技术组件选型](../../architecture/Agent侧技术组件选型.md)、[P1 Agent Runtime 实施计划](../plans/2026-09-02-P1-Agent-Runtime实施计划.md)、[Agent 侧工程规范体系设计](2026-09-01-Agent侧工程规范体系-设计.md) |
| 替代关系 | 无 |
| 适用范围 | 纯 Agent 侧 P1 运行时、异步执行、状态持久化、运行事件和结构化日志；不适用于业务 Agent、Java 侧、部署拓扑和监控平台建设 |

> 本文记录已批准的 P1 局部技术方向。P0～P5 总体技术架构现已完成并批准，但这仍不授权依赖安装、代码实施、基础设施连接、PoC、数据库 DDL 或生产变更，也不构成生产可用证明。

## 1. 目标与边界

P1 建设的是支持未来多 Agent 协作的公共执行底座，而不是任何人事、行政、运营、数据或客服业务能力。P1 必须形成以下最小闭环：

```text
创建 Run → 可靠投递 → Worker 认领 → LangGraph 执行
          → Checkpoint → 事件流 → 暂停/恢复/取消 → 终态落库
```

硬约束如下：

- 必须在 Windows 原生环境和 CPython 3.13 上运行；
- LangGraph 是唯一 Graph Runtime，底层必须可承载 Direct、Workflow、ReAct、Plan-and-Execute 和 Supervisor + Specialist Subgraphs；
- PostgreSQL 是纯 Agent 侧唯一关系型技术事实库；MySQL 不作为 Agent Runtime 基础依赖；
- Redis 只保存可重建的临时队列、运行事件、取消信号、缓存和锁，不承担权威状态；
- 本阶段不建设 OpenTelemetry、Prometheus、Grafana、LangSmith、Collector、Dashboard、告警或完整监控平台；
- 本阶段不接业务 Agent、LLM、RAG、OCR、MCP、业务 Tool 或业务数据库；
- 本阶段不设计部署拓扑，也不执行任何未经明确授权的共享数据库 DDL。

## 2. 最终组件基线

| 技术域 | P1 选型 | 责任边界 | 当前状态 |
|---|---|---|---|
| Graph Runtime | `langgraph` 原生 `StateGraph` Graph API | 图、节点、边、子图、中断与恢复；不使用第二编排内核 | 已确认，未安装 |
| Checkpoint | `langgraph-checkpoint-postgres` 的 `AsyncPostgresSaver` | LangGraph 状态快照、恢复和 human-in-the-loop 持久化 | 已确认，未安装 |
| 异步任务 | `taskiq` + `taskiq-redis` 的 `RedisStreamBroker` | API 与 Worker 解耦、消息 ACK、重投递 | 已确认，待强制 PoC |
| Redis Client | `redis` 的 asyncio API | Run Event Stream、取消快信号、短期缓存和锁 | 已确认，未安装 |
| Agent 数据访问 | `SQLAlchemy 2.x` async | Agent 自有 Run、Step、Usage、Event、Outbox 等关系数据 | 已确认，未安装 |
| PostgreSQL Driver | `psycopg[binary,pool]` | SQLAlchemy PostgreSQL 驱动及独立 Checkpoint 连接池 | 已确认，未安装 |
| Schema Migration | `Alembic` | 只管理 Agent 自有关系表；不得接管 LangGraph 官方表 | 已确认，未安装 |
| 结构化日志 | `structlog` + stdlib `logging` | 进程内上下文、统一事件字段、脱敏和 stdout 输出 | 已确认，未安装 |
| 边界契约 | Pydantic v2 | API、任务消息、Run Event、持久化 DTO 的输入输出校验 | P0 已选，未安装 |
| 内部状态 | `TypedDict` + Python 标准类型 | Graph State，避免把 Pydantic 模型贯穿运行内核 | 已确认，未实现 |
| JSON | Python stdlib `json` | API、事件、持久化 JSON 字段；P1 不引入 `orjson` | 已确认 |

P1 运行依赖组计划新增：

```text
langgraph
langgraph-checkpoint-postgres
taskiq
taskiq-redis
redis
psycopg[binary,pool]
sqlalchemy[asyncio]
alembic
structlog
```

这些名称只描述直接依赖边界，不构成安装指令。补丁版本、传递依赖和哈希由 PoC 后的 `uv.lock` 固定。

## 3. 完整逻辑架构

```text
┌──────────────────────────── Pure Agent Runtime Boundary ────────────────────────────┐
│                                                                                     │
│  ┌────────────── FastAPI / Contracts ──────────────┐                                │
│  │ Create Run │ SSE │ Resume/Input │ Cancel │ Query │                                │
│  └──────────────────────────┬───────────────────────┘                                │
│                             │ DB transaction                                         │
│             ┌───────────────▼────────────────┐                                       │
│             │ Agent Runtime PostgreSQL        │                                       │
│             │ Run / State Event / Outbox      │◄──────────────┐                       │
│             │ Step / Invocation / Usage       │               │ durable truth         │
│             └───────────────┬────────────────┘               │                       │
│                             │ outbox publish                   │                       │
│  ┌──────────────────────────▼──────────────────────────────┐   │                       │
│  │ Redis                                                    │   │                       │
│  │ Taskiq RedisStreamBroker │ per-run Event Streams         │   │                       │
│  │ cancel signal/cache/lock │ bounded TTL transient data    │   │                       │
│  └───────────────┬───────────────────────────────┬──────────┘   │                       │
│                  │ task ACK/redelivery            │ XREAD/SSE    │                       │
│          ┌───────▼────────────────────┐     ┌────▼──────────┐   │                       │
│          │ Taskiq Worker              │     │ FastAPI SSE   │   │                       │
│          │ claim / heartbeat / cancel │     │ Last-Event-ID │   │                       │
│          └──────────────┬─────────────┘     └───────────────┘   │                       │
│                         │                                       │                       │
│  ┌──────────────────────▼──────── Thin Agent Harness ───────────┴──────────────────┐  │
│  │ identity │ authorization │ idempotency │ budget │ timeout │ cancellation        │  │
│  │ checkpoint │ audit boundary │ correlation IDs │ redaction │ error normalization │  │
│  └──────────────────────────────┬───────────────────────────────────────────────────┘  │
│                                 │                                                      │
│  ┌────────────────────── Strategy Router + LangGraph StateGraph ───────────────────┐  │
│  │ Direct │ Workflow │ bounded ReAct │ Plan-and-Execute │ Supervisor/Subgraphs     │  │
│  │ thread_id = run_id │ checkpoint_ns isolation │ normalized Run Events           │  │
│  └──────────────────────────┬───────────────────────────────────────────────────────┘  │
│                             │ AsyncPostgresSaver                                      │
│             ┌───────────────▼──────────────────────────────┐                          │
│             │ Dedicated Checkpoint Psycopg Async Pool       │                          │
│             │ autocommit=True │ prepare_threshold=0         │                          │
│             │ row_factory=dict_row                          │                          │
│             └───────────────┬───────────────────────────────┘                          │
│                             ▼                                                          │
│                   Agent Runtime PostgreSQL                                             │
│                                                                                       │
│  Cross-cutting in P1: structlog + stdlib logging, run_id/task_id/correlation_id,      │
│  runtime events, observability port with no-op implementation                          │
└───────────────────────────────────────────────────────────────────────────────────────┘

Separate logical data boundary (not exercised by P1 Graph PoC):
Agent Vector PostgreSQL → document / chunk / embedding / pgvector index
```

## 4. 架构职责

### 4.1 Thin Agent Harness

Harness 位于入站契约与 LangGraph 之间，负责一次 Run 的统一治理。它必须负责身份与授权上下文、幂等、预算、超时、取消、Checkpoint 策略、错误归一化、审计边界、日志关联和脱敏，不得包含具体业务 Agent、模型厂商 SDK 或某种策略的内部步骤。

P1 只建立可观测扩展端口及 no-op 实现。完整 Trace、Metric、Exporter 和监控平台不是 Harness 在 P1 的实现范围。

### 4.2 Strategy Router 与 Graph Runtime

Strategy Router 只返回结构化执行模式，不调度专家。所有模式必须由原生 `StateGraph` 承载：

| 模式 | P1 骨架要求 |
|---|---|
| Direct | 单节点或最小 Graph，仍经过 Harness |
| Workflow | 确定性节点与边，状态可持久化 |
| ReAct | 有界循环，预留步数、工具和预算终止条件 |
| Plan-and-Execute | Planner、Executor、Replanner 分离，计划进入 Graph State |
| Multi-Agent | Supervisor Graph 调度 Specialist Subgraphs；专家之间不得自由互聊 |

不得使用 `langchain.create_agent`、预构建 `create_react_agent`、Deep Agents 或 LangSmith Agent Server 作为底层总框架。可在后续业务阶段按需使用不引入第二生命周期的独立工具包，但不得绕过统一 Harness 和 StateGraph。

Graph State 使用 `TypedDict` 和标准类型；Pydantic 只用于网络、任务消息、事件和持久化 DTO 等边界。LangGraph 原生事件必须先转换为内部版本化 `RunEvent`，API 不得直接向调用方暴露框架事件对象。

### 4.3 Checkpoint

生产态 Checkpointer 固定为 `AsyncPostgresSaver`：

- `thread_id` 固定等于 `run_id`；
- `checkpoint_ns` 用于隔离执行策略、Supervisor 和 Specialist Subgraph；
- Checkpoint 只允许官方 msgpack 序列化，不允许 pickle fallback；
- `InMemorySaver` 仅允许在单元测试和确定性 Graph 测试中使用；
- 不使用 `ShallowPostgresSaver`，因为它不满足完整历史和恢复证据要求；
- Checkpoint 使用独立 Psycopg async pool，不能复用 SQLAlchemy 的连接池对象；
- 连接池必须配置 `autocommit=True`、`prepare_threshold=0`、`row_factory=dict_row`；
- `AsyncPostgresSaver.setup()` 只能由显式初始化/迁移命令执行，禁止在应用启动时自动执行。

官方 Checkpoint 表由 `setup()` 管理，Agent 自有表由 Alembic 管理，两者不得交叉接管。任何共享环境 DDL 必须先展示脚本、影响范围和只读预检，并取得明确授权。

## 5. 异步任务与可靠投递

### 5.1 Taskiq 边界

`taskiq + taskiq-redis` 负责“某个 Run 何时由哪个 Worker 执行”；LangGraph 负责“该 Run 内部如何执行与从哪里恢复”。任务消息只携带最小标识和安全关联信息，例如 `run_id`、`task_id`、`correlation_id`、契约版本，不携带 Prompt、文档、Secret 或大对象。

选择 `RedisStreamBroker` 是为了获得 Redis Streams 的消息确认和重投递语义。Taskiq 当前仍标注 Alpha，因此 Windows + Python 3.13 PoC 是准入硬门禁；未通过不得进入正式实现，也不得以“可安装”推断生产可用。

Celery 不进入本项目基线，因为其官方文档明确不支持 Microsoft Windows。P1 也不引入定时调度器；周期任务在真实需求出现后单独选型。

### 5.2 PostgreSQL Outbox

Run 创建不得直接采用“先写 PostgreSQL，再盲发 Redis”的双写方式。可靠投递流程固定为：

```text
同一 PostgreSQL 事务：
  INSERT Run
  INSERT RunStateEvent(CREATED → QUEUED)
  INSERT DispatchOutbox(run_id, contract_version, status=PENDING)
        ↓ commit
Outbox Dispatcher 读取并发布到 Taskiq RedisStreamBroker
        ↓
发布成功后标记 Outbox SENT；失败按受控退避重试
```

Outbox 允许至少一次投递。Worker 必须用 `run_id + state_version` 做条件认领/CAS，只有一个 Worker 能把已排队 Run 转为 `RUNNING`；重复消息必须安全 ACK，不能产生第二次执行。Outbox 记录、Run 状态和长期事件以 PostgreSQL 为权威事实。

## 6. Run Event Bus 与 SSE

Worker 到 FastAPI SSE 的实时桥接复用 Redis Streams，但与 Taskiq Broker 使用不同 Key 空间：

```text
Task Broker：由 taskiq-redis 管理的独立前缀
Run Event：agent:run:{run_id}:events
```

事件链路为：

```text
LangGraph/Worker → normalize RunEvent → XADD per-run stream
FastAPI SSE      → XREAD BLOCK → SSE id = Redis Stream ID
Client reconnect → Last-Event-ID → 从对应 Stream ID 继续读取
```

SSE 读取不使用 Consumer Group，因为同一 Run 可能有多个观察者，每个连接都需要自己的游标。Stream 必须限制最大长度并设置 TTL；终态事件写入后延迟清理，不能在终态到达时立即删除。状态变化和需要长期保留的 Run Event 必须先提交 PostgreSQL，再尽力发布 Redis Stream；Redis 发布失败不得回滚已提交的权威状态，可由状态查询或事件补发恢复。Redis Stream 是短期交付通道，长期事件记录仍以 PostgreSQL 为准。

`RunEvent` 必须是版本化 Pydantic 契约，至少包含事件类型、时间、`run_id`、`task_id`、`correlation_id`、状态/步骤和受控 payload。事件不得包含 Secret、原始敏感 Prompt、完整文档或无限增长对象；Token 事件必须批量合并，不能逐 Token 无界写 Redis。

## 7. 暂停、恢复与取消

暂停和恢复使用 LangGraph 原生中断语义：

```text
interrupt() → Checkpoint 持久化 → Run 进入 WAITING_INPUT/WAITING_APPROVAL/WAITING_TOOL
resume API  → 校验身份/权限/版本 → Command(resume=resume_value) → 原 run_id/thread_id 继续
```

恢复不得新建 Run 冒充恢复。恢复前必须校验调用主体、状态版本、Checkpoint 存在性、输入契约和副作用幂等状态。

取消采用协作式取消：API 先在 PostgreSQL 写入 `CANCEL_REQUESTED` 取消请求事件/时间标记，再写 Redis 快速取消信号；`CANCEL_REQUESTED` 不是新的 `RunStatus`，Run 在 Worker 安全停止前保持原 `QUEUED`、`RUNNING` 或 `WAITING_*` 状态。Worker 在节点边界、流式输出边界和可取消 I/O 前后检查，清理完成后进入既有 `CANCELLED` 终态。取消不能承诺撤销已经发生的外部副作用；后续所有副作用 Tool 都必须提供幂等键、状态核对或明确补偿边界。

## 8. 持久化与数据语义

### 8.1 数据边界

Agent 侧使用两个逻辑 PostgreSQL DSN，逻辑隔离先于物理部署决策：

| 逻辑数据源 | 数据范围 | 访问方式 |
|---|---|---|
| Agent Runtime PostgreSQL | Run、状态事件、Step/Invocation、Usage、长期 Run Event、Dispatch Outbox、LangGraph Checkpoint | Agent 自有表走 SQLAlchemy async；Checkpoint 走独立 Psycopg pool |
| Agent Vector PostgreSQL | Document、Chunk、Embedding 元数据、向量和索引 | P2 通过 SQLAlchemy/Psycopg/pgvector 适配 |

它们可以在后续资源规划中映射为同一实例的不同 database/schema，也可以是不同实例；P1 不裁决部署形式。任何情况下都必须具有独立配置键、最小权限和 Agent 命名空间。

MySQL 不保存 Agent Run、Checkpoint、Usage、统计或事件。未来需要业务数据时，通过受治理 API/Tool 访问业务系统；确有只读直连需求时必须另行设计、授权和选型，不能把 MySQL Driver 预装进底座。

### 8.2 Runtime 数据不是业务数据

P1 所称数据是 Agent 自身执行事实，不是人事、行政、运营、客服等业务实体。最低语义如下：

| 事实 | 作用 |
|---|---|
| Run | 一次请求的生命周期、策略、状态、起止时间和汇总 |
| Step/Invocation | Graph 节点、模型或 Tool 调用的执行尝试与结果分类 |
| Usage | Provider、模型、输入/输出/缓存 Token、耗时、状态和计量来源 |
| Run Event | 状态变化和可恢复的长期事件记录 |
| Checkpoint | LangGraph 执行状态快照，不替代 Run/Usage 事实 |
| Dispatch Outbox | PostgreSQL 到任务 Broker 的可靠投递事实 |

P1 尚未接模型，不能伪造 Token 数。P1 只记录队列等待、Run、Graph、Node 和 Checkpoint 等真实可得耗时，并预留 Usage 契约。P2 接入 Provider 后，再按调用记录精确 Token。日 Token、平均耗时、P95、成功率和费用等统计由原始事实派生，不与原始事实混为一层，也不要求 P1 建设监控平台。

## 9. 结构化日志

P1 采用 `structlog + stdlib logging`：

- 本地控制台使用可读格式，非本地环境输出 JSON；
- 日志只写 stdout/stderr，不由应用自行切分或轮转文件；
- 进程内使用 `contextvars` 绑定上下文；
- Taskiq 消息显式传递并在 Worker 重新绑定 `run_id`、`task_id`、`correlation_id`，不能假设 contextvars 跨进程传播；
- 标准字段为 `timestamp`、`level`、`event`、`run_id`、`task_id`、`correlation_id`、`graph`、`node`、`strategy`、`worker_id`、`duration_ms`、`error_code`；
- 所有日志和事件共享集中式脱敏处理，禁止记录 Secret、连接串、认证头、原始敏感 Prompt/响应、完整文件、完整 SQL 或未经脱敏个人数据。

P1 的 `correlation_id` 是跨 API、Outbox、Taskiq、Worker、Graph、PostgreSQL 和 Redis 的诊断关联键，不等同于 OpenTelemetry `trace_id`。后续引入 Trace 时可以建立映射，但不得提前声称 Trace 已实现。

## 10. 一致性与故障处理

| 故障场景 | 必须行为 | 权威依据 |
|---|---|---|
| Run 事务失败 | 不发布任务，不产生可执行 Run | PostgreSQL transaction |
| Outbox 发布失败 | 保持 PENDING/失败次数并受控重试 | Dispatch Outbox |
| 重复任务消息 | CAS 认领失败后安全 ACK，不重复执行 | Run state/version |
| Worker 在 ACK 前崩溃 | Broker 重投递，恢复时重新认领或从 Checkpoint 继续 | Redis Stream + PostgreSQL |
| Redis Run Event 丢失/过期 | SSE 实时历史可能不完整，查询 PostgreSQL 长期事件与最终状态 | PostgreSQL Run Event |
| Checkpoint 写入失败 | 不得宣告已暂停/可恢复，Run 进入明确失败或受控重试 | PostgreSQL Checkpoint |
| SSE 客户端断线 | 使用 Last-Event-ID 从 Redis Stream ID 续读；过期则回查权威状态 | Redis + PostgreSQL |
| 收到取消 | PostgreSQL 先写取消请求事件/标记；停止产生新步骤，安全清理后写 CANCELLED | PostgreSQL state/event + Redis signal |
| 日志写入异常 | 不得改变权威 Run 结果；使用 stdlib 安全降级且不得泄密 | PostgreSQL state |

## 11. 安全与序列化边界

- 外部请求、任务消息、Run Event 和 Resume 输入必须经过版本化 Schema 校验；
- Graph 控制字段不能直接使用未经校验的模型自由文本；
- Checkpoint 严禁 pickle 或任意对象反序列化；
- Redis Key 必须有 Agent 前缀、用途隔离和有限 TTL；
- 数据库账号按 Runtime 自有表、Checkpoint、Vector 数据分别授予最小权限；
- SQLAlchemy Repository、Checkpoint Saver、Redis Broker 和 Event Bus 必须通过端口注入，Graph/Strategy 不得直接实例化基础设施客户端；
- Secret 只通过受控配置引用注入，不进入代码、文档、任务消息、日志、事件或 Checkpoint payload。

## 12. Windows + Python 3.13 准入 PoC

P1 实施前必须先通过隔离环境 PoC，至少覆盖：

1. Windows 原生启动与优雅停止 Taskiq Worker；
2. `RedisStreamBroker` 发布、消费、ACK 和失败重投递；
3. Worker 崩溃后 Run 可再次认领并从 Checkpoint 恢复；
4. 同一 `run_id` 重复投递只产生一次有效执行；
5. 最小 `StateGraph` 能执行并输出规范化 Run Event；
6. `AsyncPostgresSaver` 跨进程保存和恢复 Checkpoint；
7. `interrupt()` 与 `Command(resume=resume_value)` 使用同一 `run_id/thread_id` 恢复；
8. 协作式取消在节点和流式边界生效并落正确终态；
9. Redis Streams 支持 SSE `Last-Event-ID` 断线续读与过期回查；
10. SQLAlchemy async 与独立 Psycopg Checkpoint pool 可并存且无连接生命周期冲突；
11. structlog 关联字段能从 API 显式传播到 Worker，敏感字段被脱敏；
12. Python 3.13 下现有测试、P1 新增测试、架构守卫、Ruff 和 mypy 全部通过。

PoC 只能使用隔离测试数据库/schema，或在获得共享环境 DDL 明确授权后执行。PoC 通过条件必须有命令、版本、输出和证据路径；任何单项失败都必须先分析根因并重新裁决，不能用降级到 Celery、内存 Checkpoint 或第二 Graph Runtime 绕过。

## 13. 明确不选与后置项

| 项目 | 裁决 |
|---|---|
| Celery | 不选；Windows 不受官方支持 |
| full LangChain agent runtime / Deep Agents | 不作为底层框架，避免第二套或黑盒生命周期 |
| AutoGen / CrewAI / LlamaIndex Workflow / Swarm | 不选；禁止并存第二 Graph Runtime |
| MySQL Driver | P1 不引入；Agent 技术事实统一存 PostgreSQL |
| `asyncpg` / `psycopg2` | 不引入；统一 Psycopg 3 |
| `orjson` | 不引入；无真实性能证据时使用 stdlib JSON |
| `InMemorySaver` 生产使用 | 禁止；仅测试使用 |
| `ShallowPostgresSaver` | 不选；不满足完整恢复历史要求 |
| OpenTelemetry / OTLP / Prometheus / Grafana / LangSmith | 后置，不属于 P1，也不建设监控平台 |
| Hypothesis | 后续按状态机性质测试需要单独评估，不是 P1 必选依赖 |
| 定时调度 | 无当前需求，后续单独选型；不因 Taskiq 引入而默认建设 |

## 14. 退出与替换边界

- Taskiq 只能存在于 `tasks` 基础设施适配层；若 PoC 不通过，保持任务消息契约和 Outbox 不变，重新比较支持 Windows 的 Broker/Worker 方案；
- LangGraph 只存在于 `orchestration` 适配层和图定义，稳定 Run/事件/错误契约不得暴露框架对象；
- SQLAlchemy 只存在于 Persistence Adapter，核心层只依赖 Repository Protocol；
- Redis Event Bus 只承载短期交付，替换时以版本化 `RunEvent` 为迁移契约；
- Checkpoint 数据不等于业务结果。更换 Checkpointer 必须定义兼容窗口、旧 Run 恢复策略和迁移验证，不得静默丢弃等待态 Run。

## 15. 实施前置与完成声明

本文批准后只允许形成 P1 实施规划参考。P0～P5 选型与总体评审已经完成，但实施计划仍保持冻结；解除冻结必须由项目负责人再次明确授权具体实施范围。届时还必须：

1. 对 Graph Runtime、权威数据边界和可靠投递形成所需 ADR；
2. 明确 PoC 使用的隔离 Redis/PostgreSQL 资源；
3. 如涉及共享 DDL，单独展示脚本、影响和只读预检并获得授权；
4. 按任务拆分测试先行的实施步骤和回滚边界。

完成声明必须区分：局部设计已批准、总体组件选型已完成、实施已授权、依赖已锁定、PoC 已通过、代码已实现、DDL 已授权并执行、运行验证已通过。当前只能声明“P1 局部书面设计及 P0～P5 总体选型已批准，实施仍被冻结”。

## 16. 官方依据

- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)
- [langgraph-checkpoint-postgres README](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/README.md)
- [Taskiq PyPI](https://pypi.org/project/taskiq/)
- [taskiq-redis PyPI](https://pypi.org/project/taskiq-redis/)
- [Celery 官方平台支持说明](https://docs.celeryq.dev/en/stable/getting-started/introduction.html)
- [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [SQLAlchemy AsyncIO](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy Psycopg Dialect](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html)
- [Alembic Asyncio Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)
- [structlog contextvars](https://www.structlog.org/en/stable/contextvars.html)

## 17. 版本历史

| 日期 | 作者/负责人 | 变更摘要 |
|---|---|---|
| 2026-09-02 | Agent 平台架构负责人 | 记录 P1 Graph、Checkpoint、Taskiq、Redis Streams、PostgreSQL、数据访问和日志的逐项确认结果，进入书面评审 |
| 2026-09-02 | Agent 平台架构负责人 | 记录项目负责人对书面设计的明确确认，将状态更新为已批准；批准范围不包含实施与 DDL |
| 2026-09-02 | Agent 平台架构负责人 | 根据项目负责人补充裁决，明确 P1～P5 总体选型完成前禁止一切实施，P1 计划仅作为冻结的规划参考 |
