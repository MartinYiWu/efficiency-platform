# P1 Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 原生 CPython 3.13 环境中交付纯 Agent 侧 P1 运行闭环，使 Run 能被可靠创建、投递、执行、持久化、流式观察、暂停恢复和协作取消，并为未来 Supervisor 多 Agent 子图保留统一治理边界。

**Architecture:** 使用自研薄 Harness 包裹唯一的 LangGraph `StateGraph` Runtime；PostgreSQL 保存 Run、事件、用量、Outbox 和 Checkpoint 等权威事实，Taskiq `RedisStreamBroker` 负责异步执行，Redis Streams 负责短期 Run Event/SSE 交付。所有外部框架停留在 Adapter 或组合根，核心状态与端口保持 Python 标准库中立。

**Tech Stack:** CPython 3.13、uv、FastAPI、Pydantic v2、LangGraph、langgraph-checkpoint-postgres、Taskiq、taskiq-redis、redis-py、PostgreSQL、Psycopg 3、SQLAlchemy 2 async、Alembic、structlog、pytest、Ruff、mypy

> **执行冻结：** P1～P5 的全部技术组件尚未完成讨论与总体评审。本文当前只作为规划参考，任何任务、命令、依赖安装、代码修改、基础设施连接、PoC 和 DDL 均不得执行。只有 P1～P5 全部选型完成、跨阶段依赖复核通过且项目负责人再次明确授权实施后，本文才可进入评审和执行。

## Global Constraints

- 全局实施门禁优先于本文全部任务：P1～P5 技术组件选型、边界和最终裁决和跨阶段一致性评审未全部完成前，必须保持零实施。
- 项目解释器固定为 `>=3.13,<3.14`，执行命令统一使用项目根目录中的 `uv run`。
- Windows 原生运行是准入硬约束；Taskiq 在 PyPI 标注 Alpha，必须先通过 Windows + Python 3.13 PoC。
- LangGraph 原生 `StateGraph` 是唯一 Graph Runtime；禁止引入 full `langchain` Agent Runtime、Deep Agents、AutoGen、CrewAI、LlamaIndex Workflow 或第二生命周期。
- Graph State 使用 `TypedDict` 与标准类型；Pydantic 只用于 API、任务、事件、配置和持久化 DTO 边界。
- PostgreSQL 是纯 Agent 侧唯一关系型技术事实库；MySQL Driver、`asyncpg` 和 `psycopg2` 不得进入 P1 依赖。
- Agent 自有表使用 SQLAlchemy 2 async + Alembic；Checkpoint 使用独立 Psycopg async pool + `AsyncPostgresSaver`。
- Redis 只承担 Taskiq Broker、短期 Run Event、取消快信号、缓存和锁，不得作为权威状态。
- P1 不安装 OpenTelemetry、OTLP、Prometheus、Grafana、Collector 或 LangSmith，不建设 Dashboard、告警和监控平台。
- P1 不接入业务 Agent、LLM、RAG、OCR、MCP、业务 Tool、业务数据库、ASR、TTS、视频、内容审核或付费热点数据源。
- Checkpoint 只使用 msgpack 兼容值，禁止 pickle fallback；`InMemorySaver` 只允许测试使用。
- 任何共享 PostgreSQL DDL 执行前必须展示目标、脚本、影响、只读预检与回滚，并取得本次目标的明确授权。
- 当前目录不是 Git 仓库。执行每个 Git checkpoint 前先运行 `git rev-parse --is-inside-work-tree`；结果不是 `true` 时跳过提交，并在交付报告记录文件清单和验证证据，禁止声称已提交。
- 每个实现任务执行 RED 测试、最小实现、GREEN 测试和相关回归；不得把导入成功当成行为验证。

## Plan Metadata

| 属性 | 内容 |
|---|---|
| 标题 | P1 Agent Runtime 实施计划 |
| 状态 | 草案 |
| 作者/负责人 | Agent 平台架构负责人 |
| 创建日期 | 2026-09-02 |
| 最后更新日期 | 2026-09-02 |
| 评审人/批准人 | 评审人：尚未指定；批准人：尚未批准 |
| 关联 ADR/设计/计划 | [P1 Agent Runtime 技术组件选型设计](../specs/2026-09-02-P1-Agent-Runtime技术组件选型-设计.md)、[Agent 侧技术组件选型](../../architecture/Agent侧技术组件选型.md)、[数据库与 SQL 规范](../../standards/05-数据库与SQL规范.md) |
| 替代关系 | 无 |
| 适用范围 | P1 运行时实现与隔离 PoC；不授权共享 DDL、部署或业务能力接入 |
| 执行状态 | 已冻结、不可执行；解除条件为 P1～P5 全部组件选型完成、总体评审通过且项目负责人再次明确授权 |

## File Structure

计划完成后新增或实质修改的文件职责如下：

```text
pyproject.toml / uv.lock                         # P0/P1 直接依赖与精确解析结果
docs/adr/ADR-0001-LangGraph作为唯一运行时.md      # Graph Runtime 与 Harness 裁决
docs/adr/ADR-0002-PostgreSQL作为运行事实库.md     # 权威状态、双逻辑 DSN 与迁移边界
docs/adr/ADR-0003-Taskiq与Outbox可靠投递.md       # Windows 队列、至少一次投递与防重

src/efficiency_platform_agent/
├─ contracts/
│  ├─ events.py                                 # Pydantic RunEvent 契约
│  ├─ requests.py                               # 创建、恢复、取消请求契约
│  └─ tasks.py                                  # 最小任务消息契约
├─ core/
│  ├─ runtime.py                                # 框架中立 Run/Outbox/Event/Usage 值对象
│  └─ runtime_ports.py                          # Repository/EventBus/Cancel/Clock 端口
├─ observability/
│  ├─ logging.py                                # structlog 初始化与 contextvars 绑定
│  └─ redaction.py                              # 日志/事件集中脱敏
├─ persistence/
│  ├─ database.py                               # SQLAlchemy async engine/session 生命周期
│  ├─ models.py                                 # Agent 自有 Runtime 表映射
│  ├─ repositories.py                           # Run/Event/Outbox/Usage Repository
│  └─ checkpoint.py                             # AsyncPostgresSaver 独立连接池
├─ providers/cache/
│  ├─ run_events.py                             # Redis per-run Streams
│  └─ cancellation.py                           # Redis 取消快信号
├─ tasks/
│  ├─ broker.py                                 # Taskiq RedisStreamBroker 配置
│  ├─ dispatcher.py                             # PostgreSQL Outbox Dispatcher
│  └─ worker.py                                 # Run 认领、租约、执行与 ACK 边界
├─ orchestration/
│  ├─ state.py                                  # TypedDict Graph State
│  ├─ events.py                                 # LangGraph 事件归一化
│  ├─ checkpoint.py                             # thread_id/checkpoint_ns 配置
│  └─ runtime.py                                # 五种策略的 StateGraph 构建与执行入口
├─ routing/router.py                            # 结构化 StrategyMode 选择
├─ harness/
│  ├─ settings.py                               # 组合根使用的 Pydantic Settings
│  ├─ service.py                                # Create/Execute/Resume/Cancel/Query 用例
│  └─ factory.py                                # API/Worker 共用组合根
└─ api/
   ├─ app.py                                    # FastAPI 生命周期与路由注册
   ├─ routes.py                                 # Run API、Resume、Cancel、Query
   └─ sse.py                                    # Last-Event-ID 与 SSE 序列化

alembic.ini / migrations/                       # Agent 自有 Runtime 表迁移入口
sql/bootstrap/agent_database_bootstrap_v1/      # Agent schema/迁移账本引导包
sql/changes/20260902_001_P1运行时事实表/          # precheck/up/verify/rollback 受审 SQL
tests/unit/                                     # 纯端口、契约、日志、Graph 单测
tests/integration/                              # PostgreSQL/Redis/Taskiq 隔离集成测试
tests/acceptance/                               # API→Outbox→Worker→Graph→SSE 端到端验收
scripts/p1_poc.ps1                              # Windows P1 准入命令
```

---

### Task 1: 建立 ADR、依赖准入测试与锁文件

**Files:**
- Create: `docs/adr/ADR-0001-LangGraph作为唯一运行时.md`
- Create: `docs/adr/ADR-0002-PostgreSQL作为运行事实库.md`
- Create: `docs/adr/ADR-0003-Taskiq与Outbox可靠投递.md`
- Create: `tests/admission/__init__.py`
- Create: `tests/admission/test_p1_dependencies.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `docs/architecture/Agent侧技术组件选型.md`

**Interfaces:**
- Consumes: 已批准的 P1 设计、Python `>=3.13,<3.14`、uv 0.12.9
- Produces: 可审计 ADR、P0/P1 直接依赖、禁止依赖门禁、Windows 可导入基线

- [ ] **Step 1: 编写三个 ADR 并保持实施未授权边界**

每个 ADR 使用 `docs/templates/ADR决策记录模板.md` 的元数据，并写入以下不可变裁决：

```text
ADR-0001: StateGraph 是唯一运行时；薄 Harness 在其外层；五种策略共享 Run 生命周期。
ADR-0002: PostgreSQL 是权威事实库；Runtime/Vector 使用不同逻辑 DSN；Redis 仅临时；MySQL 不进入底座。
ADR-0003: Taskiq RedisStreamBroker 负责 Windows 异步执行；PostgreSQL Outbox 至少一次投递；Worker CAS/租约防重。
```

ADR 状态先写 `评审中`，不得因设计已批准而伪造 ADR 批准。三个 ADR 都要列出 Celery、双写无 Outbox、Redis 权威状态等否决方案及退出条件。

- [ ] **Gate: 完成三个 ADR 的独立批准**

将三个 ADR 的完整正文交给项目负责人评审。只有收到对三个 ADR 的明确批准后，才把状态、批准人、批准日期、批准范围和证据写入 ADR，并继续 Step 2 安装准备。任一 ADR 仍为 `评审中` 时，本任务必须停止在此处。

- [ ] **Step 2: 写依赖准入 RED 测试**

`tests/admission/test_p1_dependencies.py` 写入：

```python
from importlib.metadata import PackageNotFoundError, version

import pytest


REQUIRED = (
    "fastapi",
    "pydantic",
    "langgraph",
    "langgraph-checkpoint-postgres",
    "taskiq",
    "taskiq-redis",
    "redis",
    "psycopg",
    "sqlalchemy",
    "alembic",
    "structlog",
)
FORBIDDEN = (
    "celery",
    "langchain",
    "asyncpg",
    "psycopg2",
    "psycopg2-binary",
    "aiomysql",
    "opentelemetry-sdk",
    "prometheus-client",
)


@pytest.mark.parametrize("distribution", REQUIRED)
def test_required_distribution_is_installed(distribution: str) -> None:
    try:
        installed = version(distribution)
    except PackageNotFoundError as error:
        raise AssertionError(f"missing required distribution: {distribution}") from error
    assert installed


@pytest.mark.parametrize("distribution", FORBIDDEN)
def test_forbidden_distribution_is_absent(distribution: str) -> None:
    with pytest.raises(PackageNotFoundError):
        version(distribution)
```

- [ ] **Step 3: 运行测试并确认依赖缺失**

Run:

```powershell
uv run python -m pytest tests/admission/test_p1_dependencies.py -q
```

Expected: FAIL，首先报告 `pytest` 或 P1 distribution 尚未安装；失败原因必须是依赖缺失，而不是测试语法错误。

- [ ] **Step 4: 安装 P0/P1 直接依赖并生成锁文件**

Run:

```powershell
uv add "fastapi>=0.135,<1" uvicorn pydantic pydantic-settings httpx
uv add langgraph langgraph-checkpoint-postgres taskiq taskiq-redis redis "psycopg[binary,pool]" "sqlalchemy[asyncio]>=2,<3" alembic structlog
uv add --dev pytest pytest-asyncio pytest-cov respx ruff mypy
uv lock
uv sync --locked
```

Expected: 所有命令退出码为 0，`pyproject.toml` 只有批准的直接依赖，`uv.lock` 记录完整精确版本。

- [ ] **Step 5: 验证依赖准入与 Windows 导入**

Run:

```powershell
uv run python -m pytest tests/admission/test_p1_dependencies.py -q
uv run python -c "import langgraph, taskiq, taskiq_redis, redis, psycopg, sqlalchemy, alembic, structlog; print('p1-import-ok')"
uv tree
```

Expected: 准入测试 PASS，导入命令输出 `p1-import-ok`；`uv tree` 不出现禁止 distribution。`langchain-core` 作为 LangGraph 底层依赖允许存在，名为 `langchain` 的完整包不得存在。

- [ ] **Step 6: 执行条件 Git checkpoint**

```powershell
$inside = git rev-parse --is-inside-work-tree 2>$null
if ($inside -eq 'true') {
  git add -- pyproject.toml uv.lock tests/admission docs/adr docs/architecture/Agent侧技术组件选型.md
  git commit -m "build: establish p1 runtime dependencies"
} else {
  Write-Output 'git-checkpoint-skipped:not-a-repository'
}
```

Expected: Git 仓库中生成一个仅含白名单文件的提交；当前无 Git 场景输出明确跳过信息。

---

### Task 2: 定义 Run、任务、事件、用量与端口契约

**Files:**
- Create: `src/efficiency_platform_agent/core/runtime.py`
- Create: `src/efficiency_platform_agent/core/runtime_ports.py`
- Modify: `src/efficiency_platform_agent/core/run.py`
- Create: `src/efficiency_platform_agent/contracts/events.py`
- Create: `src/efficiency_platform_agent/contracts/requests.py`
- Create: `src/efficiency_platform_agent/contracts/tasks.py`
- Modify: `src/efficiency_platform_agent/core/__init__.py`
- Modify: `src/efficiency_platform_agent/contracts/__init__.py`
- Create: `tests/unit/core/test_runtime_contracts.py`
- Create: `tests/unit/contracts/test_boundary_contracts.py`
- Modify: `tests/architecture/test_core_contracts.py`

**Interfaces:**
- Consumes: `RunStatus`、`StrategyMode`、不可变 `JsonObject`
- Produces: `RunRecord`、`RunEventRecord`、`DispatchRecord`、`UsageRecord`、`RunRepository`、`RunEventBus`、`CancellationSignal`、`ExecuteRunTask`、`RunEvent`

- [ ] **Step 1: 写核心契约 RED 测试**

测试必须覆盖：初始 Run 只能是 `QUEUED`、版本必须为正整数、Token 不允许负值、任务消息不允许携带 Prompt/文档字段、`CANCEL_REQUESTED` 是事件而不是 `RunStatus`、事件 payload 必须可 JSON 序列化。

```python
def test_cancel_request_is_event_not_run_status() -> None:
    from efficiency_platform_agent.contracts.events import RunEventType
    from efficiency_platform_agent.core.enums import RunStatus

    assert RunEventType.CANCEL_REQUESTED.value == "cancel_requested"
    assert "cancel_requested" not in {item.value for item in RunStatus}
```

Run:

```powershell
uv run pytest tests/unit/core/test_runtime_contracts.py tests/unit/contracts/test_boundary_contracts.py -q
```

Expected: FAIL，原因是新模块或类型不存在。

- [ ] **Step 2: 实现框架中立 Runtime 值对象**

先按 ADR-0001 将现有 `RunContext.trace_id` 迁移为必填 `task_id` 与 `correlation_id`，同步现有架构测试。当前没有已接入外部消费者，因此不保留含义错误的 `trace_id` 兼容别名；若执行前发现真实消费者，必须停止并补充兼容 ADR。

`core/runtime.py` 至少定义以下不可变类型和校验：

```python
@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    task_id: str
    correlation_id: str
    tenant_id: str
    status: RunStatus
    strategy: StrategyMode
    state_version: int
    execution_attempt: int
    worker_id: str | None
    lease_until_epoch_ms: int | None


@dataclass(frozen=True, slots=True)
class UsageRecord:
    run_id: str
    step_id: str
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    duration_ms: int
    measurement_source: str
```

同文件定义 `RunEventRecord` 和 `DispatchRecord`；所有 ID 非空，计数非负，时间使用 UTC epoch millisecond 或 timezone-aware datetime 且全文件保持一种表示。

- [ ] **Step 3: 定义 Repository 与基础设施端口**

`core/runtime_ports.py` 的签名固定为：

```python
class RunRepository(Protocol):
    async def create_queued(self, run: RunRecord, event: RunEventRecord, dispatch: DispatchRecord) -> None:
        raise NotImplementedError

    async def get(self, run_id: str) -> RunRecord | None:
        raise NotImplementedError

    async def claim(self, run_id: str, expected_version: int, worker_id: str, lease_until_epoch_ms: int) -> RunRecord | None:
        raise NotImplementedError

    async def renew_lease(self, run_id: str, state_version: int, worker_id: str, lease_until_epoch_ms: int) -> bool:
        raise NotImplementedError

    async def transition(self, run_id: str, expected_version: int, target: RunStatus, event: RunEventRecord) -> RunRecord:
        raise NotImplementedError

    async def request_cancel(self, run_id: str, event: RunEventRecord) -> bool:
        raise NotImplementedError


class RunEventBus(Protocol):
    async def publish(self, event: RunEventRecord) -> str:
        raise NotImplementedError

    async def read(self, run_id: str, after_id: str, block_ms: int, count: int) -> Sequence[tuple[str, RunEventRecord]]:
        raise NotImplementedError


class CancellationSignal(Protocol):
    async def request(self, run_id: str, ttl_seconds: int) -> None:
        raise NotImplementedError

    async def is_requested(self, run_id: str) -> bool:
        raise NotImplementedError
```

实际文件使用 `raise NotImplementedError` 作为 Protocol 方法体，避免在受治理文档中复制省略占位写法。

- [ ] **Step 4: 实现 Pydantic 边界契约**

`contracts/events.py` 定义有限 `RunEventType`、`RunEventV1` 和 `from_domain()`/`to_domain()`；`contracts/tasks.py` 定义只含以下字段的 `ExecuteRunTaskV1`：

```python
class ExecuteRunTaskV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["1.0"] = "1.0"
    run_id: str
    task_id: str
    correlation_id: str
    expected_state_version: int = Field(ge=1)
```

`requests.py` 定义 `CreateRunRequestV1`、`ResumeRunRequestV1`、`CancelRunRequestV1` 和 `RunViewV1`。Resume payload 使用有大小上限的 JSON 值，禁止任意 Python 对象。

- [ ] **Step 5: 运行契约测试和架构守卫**

```powershell
uv run pytest tests/unit/core/test_runtime_contracts.py tests/unit/contracts/test_boundary_contracts.py -q
uv run python -m unittest tests.architecture.test_dependency_rules -v
```

Expected: 两组测试均 PASS；`core` 不导入 Pydantic、LangGraph、SQLAlchemy、Redis 或 Taskiq。

- [ ] **Step 6: 执行条件 Git checkpoint**

使用 Task 1 的条件脚本，仅暂存本任务列出的 `src` 与 `tests` 文件，提交信息使用 `feat: define p1 runtime contracts`。

---

### Task 3: 实现结构化日志、上下文传播与脱敏

**Files:**
- Create: `src/efficiency_platform_agent/observability/logging.py`
- Create: `src/efficiency_platform_agent/observability/redaction.py`
- Modify: `src/efficiency_platform_agent/observability/__init__.py`
- Create: `tests/unit/observability/test_logging.py`
- Create: `tests/unit/observability/test_redaction.py`

**Interfaces:**
- Consumes: `run_id`、`task_id`、`correlation_id` 和受控事件字段
- Produces: `configure_logging(environment: str)`、`bind_run_context(run_id: str, task_id: str, correlation_id: str)`、`clear_run_context()`、`redact_mapping(value: Mapping[str, object])`

- [ ] **Step 1: 写日志 RED 测试**

测试必须证明：本地渲染可读、非本地输出 JSON、三个关联 ID 自动绑定、清理后不串 Run、`authorization`/`cookie`/`password`/`dsn`/`prompt` 值被替换为 `[REDACTED]`、异常日志不含原始 Secret。

```python
def test_context_is_cleared_between_runs(capsys: pytest.CaptureFixture[str]) -> None:
    bind_run_context(run_id="run-a", task_id="task-a", correlation_id="corr-a")
    get_logger().info("first")
    clear_run_context()
    get_logger().info("second")
    lines = capsys.readouterr().out.splitlines()
    assert "run-a" in lines[0]
    assert "run-a" not in lines[1]
```

- [ ] **Step 2: 实现集中脱敏**

`redaction.py` 使用大小写不敏感的精确 Key 集合和递归深度/集合长度上限。禁止将任意包含 `id` 的字段全部脱敏；`run_id`、`task_id`、`correlation_id` 必须保留。

- [ ] **Step 3: 配置 structlog 与 contextvars**

`logging.py` 必须调用 `structlog.contextvars.merge_contextvars`，本地使用 `ConsoleRenderer`，其他环境使用 `JSONRenderer(serializer=json.dumps)`；公共字段固定为 `timestamp`、`level`、`event` 和已绑定上下文。不要引入 OpenTelemetry processor。

- [ ] **Step 4: 验证日志行为**

```powershell
uv run pytest tests/unit/observability -q
uv run ruff check src/efficiency_platform_agent/observability tests/unit/observability
uv run mypy src/efficiency_platform_agent/observability
```

Expected: 全部 PASS；输出中无测试 Secret 明文。

- [ ] **Step 5: 执行条件 Git checkpoint**

仅暂存本任务文件，提交信息使用 `feat: add structured runtime logging`。

---

### Task 4: 建立 PostgreSQL Runtime 事实层与受审迁移包

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/20260902_001_p1_runtime_facts.py`
- Create: `src/efficiency_platform_agent/persistence/database.py`
- Create: `src/efficiency_platform_agent/persistence/models.py`
- Create: `src/efficiency_platform_agent/persistence/repositories.py`
- Create: `sql/bootstrap/agent_database_bootstrap_v1/00-变更说明.md`
- Create: `sql/bootstrap/agent_database_bootstrap_v1/01-precheck.sql`
- Create: `sql/bootstrap/agent_database_bootstrap_v1/02-up.sql`
- Create: `sql/bootstrap/agent_database_bootstrap_v1/03-verify.sql`
- Create: `sql/bootstrap/agent_database_bootstrap_v1/04-rollback.sql`
- Create: `sql/changes/20260902_001_P1运行时事实表/00-变更说明.md`
- Create: `sql/changes/20260902_001_P1运行时事实表/01-precheck.sql`
- Create: `sql/changes/20260902_001_P1运行时事实表/02-up.sql`
- Create: `sql/changes/20260902_001_P1运行时事实表/03-verify.sql`
- Create: `sql/changes/20260902_001_P1运行时事实表/04-rollback.sql`
- Create: `tests/unit/persistence/test_models.py`
- Create: `tests/unit/persistence/test_repository_contract.py`
- Create: `tests/integration/persistence/test_postgres_repository.py`

**Interfaces:**
- Consumes: `RunRepository`、`RunRecord`、`RunEventRecord`、`DispatchRecord`、Runtime PostgreSQL DSN
- Produces: `create_engine_and_session_factory(dsn)`、`SqlAlchemyRunRepository`、Alembic revision 与同源 SQL 变更包

- [ ] **Step 1: 写模型与 Repository RED 测试**

单元测试检查表名、必填租户字段、UTC 时间、状态/版本约束、Outbox 唯一键和索引；Repository 契约测试以 fake session 验证 `create_queued()` 只提交一次事务，`claim()` 必须包含状态、版本和租约条件。

```python
def test_runtime_tables_are_explicit() -> None:
    assert set(Base.metadata.tables) >= {
        "agent_runtime.agent_run",
        "agent_runtime.agent_run_state_event",
        "agent_runtime.agent_step_invocation",
        "agent_runtime.agent_usage",
        "agent_runtime.agent_dispatch_outbox",
    }
```

- [ ] **Step 2: 实现 SQLAlchemy 模型**

模型最低字段如下；所有时间为 `TIMESTAMP WITH TIME ZONE`，所有租户数据包含 `tenant_id`：

```text
agent_run: run_id, task_id, correlation_id, tenant_id, status, strategy,
           state_version, execution_attempt, worker_id, lease_until,
           cancel_requested_at, created_at, started_at, finished_at, updated_at
agent_run_state_event: event_id, run_id, tenant_id, event_type, from_status,
                       to_status, state_version, payload_json, occurred_at
agent_step_invocation: invocation_id, run_id, tenant_id, step_id, graph, node,
                       attempt, status, started_at, finished_at, duration_ms, error_code
agent_usage: usage_id, run_id, tenant_id, invocation_id, provider, model,
             input_tokens, output_tokens, cached_tokens, duration_ms,
             measurement_source, occurred_at
agent_dispatch_outbox: outbox_id, run_id, task_id, contract_version, payload_json,
                       status, attempts, next_attempt_at, claimed_by,
                       claim_until, published_at, created_at, updated_at
```

`payload_json` 只存经 Schema 校验的受控 JSON；核心过滤字段不得藏入 JSONB。

- [ ] **Step 3: 实现 Repository 的事务与 CAS**

`create_queued()` 在同一 transaction 写 Run、QUEUED 状态事件和 PENDING Outbox。`claim()` 执行单条条件更新：QUEUED + expected version 可首次认领；RUNNING 只有租约过期才可恢复认领。每次成功更新 `state_version + 1` 和 `execution_attempt + 1` 并返回新记录；影响零行返回 `None`。

- [ ] **Step 4: 生成 Alembic 与 SQL 评审包，但不执行 DDL**

Bootstrap 只能创建 `agent_runtime` schema 与规范要求的迁移权威账本，并使用固定 advisory lock `7887332933888385649`。普通变更包创建五张 P1 表及约束/索引，Alembic revision 选择 `alembic_embedded` 并引用 `change_id=20260902_001_P1运行时事实表`。

Run only read-only/file checks:

```powershell
uv run python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; script = ScriptDirectory.from_config(Config('alembic.ini')); assert len(script.get_heads()) == 1; print(script.get_current_head())"
uv run python -m compileall -q migrations src
Get-FileHash -Algorithm SHA256 'sql/changes/20260902_001_P1运行时事实表/02-up.sql'
```

Expected: migration graph 可加载、Python 编译通过、输出稳定 SHA-256。不得运行 `alembic upgrade`、`stamp`、`current` 或任意 SQL 写入。

- [ ] **Step 5: 获取 DDL 授权后才运行隔离 PostgreSQL 集成测试**

执行者必须先展示两个 SQL 包、目标脱敏标识、只读 precheck、预计对象、事务与回滚。只有用户对该隔离目标明确授权后，才运行：

```powershell
if ([string]::IsNullOrWhiteSpace($env:AGENT_RUNTIME_TEST_DSN)) {
  throw 'AGENT_RUNTIME_TEST_DSN must be injected by the approved secret source'
}
uv run pytest tests/integration/persistence/test_postgres_repository.py -q
```

Expected: 创建/查询、并发 claim 单胜者、租约过期恢复、非法状态失败关闭、Outbox 与 Run 原子性全部 PASS。命令中的示例 DSN 必须由受控 Secret 注入替换，真实值不得写入文档或日志。

- [ ] **Step 6: 执行条件 Git checkpoint**

仅暂存本任务文件，提交信息使用 `feat: add postgres runtime facts`；无 Git 时记录 SQL 文件哈希与测试状态。

---

### Task 5: 接入 AsyncPostgresSaver 与 Checkpoint 生命周期

**Files:**
- Create: `src/efficiency_platform_agent/persistence/checkpoint.py`
- Create: `src/efficiency_platform_agent/orchestration/checkpoint.py`
- Create: `tests/unit/orchestration/test_checkpoint_config.py`
- Create: `tests/integration/orchestration/test_postgres_checkpoint.py`
- Create: `scripts/setup_checkpoint.py`

**Interfaces:**
- Consumes: Runtime PostgreSQL Checkpoint DSN、`run_id`、strategy/subgraph namespace
- Produces: `CheckpointResources` async context manager、`graph_config(run_id, checkpoint_ns)`、显式 setup 命令

- [ ] **Step 1: 写 Checkpoint RED 测试**

单元测试检查 `thread_id == run_id`、namespace 非空且格式稳定、生产工厂拒绝 `InMemorySaver`、serializer 配置不允许 pickle。集成测试检查进程 A 写入后进程 B 能以同一 thread/namespace 读取。

- [ ] **Step 2: 实现独立 Psycopg async pool**

`persistence/checkpoint.py` 必须使用：

```python
AsyncConnectionPool(
    conninfo=dsn,
    open=False,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    },
)
```

生命周期明确 `await pool.open()`、构造 `AsyncPostgresSaver(pool)`、关闭时 `await pool.close()`。不得复用 SQLAlchemy engine pool。

- [ ] **Step 3: 实现稳定 Graph config**

`graph_config()` 返回：

```python
{
    "configurable": {
        "thread_id": run_id,
        "checkpoint_ns": checkpoint_ns,
    }
}
```

namespace 由 `strategy/<mode>`、`supervisor`、`specialist/<registered-name>` 构成，只允许注册表安全字符。

- [ ] **Step 4: 将 setup 与应用启动分离**

`scripts/setup_checkpoint.py` 只接受受控环境 DSN，调用一次 `AsyncPostgresSaver.setup()` 后退出。FastAPI lifespan、Worker startup 和 Repository 初始化均不得调用 `setup()`。

- [ ] **Step 5: 获得目标 DDL 授权后验证跨进程恢复**

```powershell
uv run python scripts/setup_checkpoint.py
uv run pytest tests/integration/orchestration/test_postgres_checkpoint.py -q
```

Expected: setup 与测试退出码 0；等待态 Checkpoint 在新的 Python 进程可恢复；错误 namespace 读不到其他子图状态。未获授权时本步骤必须保持未执行并明确报告。

- [ ] **Step 6: 执行条件 Git checkpoint**

仅暂存本任务文件，提交信息使用 `feat: add postgres graph checkpoints`。

---

### Task 6: 实现 Redis Run Event Bus、SSE 游标与取消快信号

**Files:**
- Create: `src/efficiency_platform_agent/providers/cache/run_events.py`
- Create: `src/efficiency_platform_agent/providers/cache/cancellation.py`
- Create: `src/efficiency_platform_agent/api/sse.py`
- Create: `tests/unit/providers/cache/test_run_event_codec.py`
- Create: `tests/unit/api/test_sse.py`
- Create: `tests/integration/cache/test_redis_run_events.py`

**Interfaces:**
- Consumes: `RunEventBus`、`CancellationSignal`、`RunEventRecord`
- Produces: `RedisRunEventBus`、`RedisCancellationSignal`、`encode_sse_event(event_id: str, event: RunEventV1)`

- [ ] **Step 1: 写 Redis/SSE RED 测试**

覆盖：Key 固定为 `agent:run:{run_id}:events`、Broker 与 Event Key 前缀不同、XADD 返回 ID、XREAD 从 `Last-Event-ID` 后读取、多观察者互不消费、终态后保留 TTL、payload 超限拒绝、Token 小片段聚合、取消信号 TTL。

```python
def test_event_stream_key_is_per_run() -> None:
    assert run_event_key("run-123") == "agent:run:run-123:events"
```

- [ ] **Step 2: 实现受控事件编码与 Redis Streams Adapter**

事件使用 `RunEventV1.model_dump_json()` 编码，读取后严格反序列化；`publish()` 设置近似 `MAXLEN` 和 TTL。配置必须显式包含 `max_stream_length`、`stream_ttl_seconds`、`terminal_ttl_seconds`、`read_block_ms` 和 `read_count`，且全部为正数。

- [ ] **Step 3: 实现 SSE 序列化**

`api/sse.py` 只负责把 Harness 返回的事件信封编码为 SSE：Redis Stream ID 写为 `id`，内部 event type 写为 `event`，JSON 写为 `data`。该模块不得导入 Redis Adapter。`Last-Event-ID` 的校验和读取由 Harness 事件流用例协调；游标格式不合法返回稳定 400 错误，不直接传入 Redis 命令。

- [ ] **Step 4: 运行单元与隔离 Redis 集成测试**

```powershell
uv run pytest tests/unit/providers/cache tests/unit/api/test_sse.py -q
uv run pytest tests/integration/cache/test_redis_run_events.py -q
```

Expected: 单元测试 PASS；在提供隔离 `AGENT_REDIS_TEST_URL` 时集成测试 PASS。没有隔离 Redis 时只允许显式 skip，不得宣称集成链路已验证。

- [ ] **Step 5: 执行条件 Git checkpoint**

仅暂存本任务文件，提交信息使用 `feat: add redis run event streaming`。

---

### Task 7: 实现 Taskiq Broker、Outbox Dispatcher 与 Worker 防重恢复

**Files:**
- Create: `src/efficiency_platform_agent/tasks/broker.py`
- Create: `src/efficiency_platform_agent/tasks/dispatcher.py`
- Create: `src/efficiency_platform_agent/tasks/worker.py`
- Create: `tests/unit/tasks/test_dispatcher.py`
- Create: `tests/unit/tasks/test_worker_claim.py`
- Create: `tests/integration/tasks/test_taskiq_redis_stream.py`
- Create: `tests/integration/tasks/test_duplicate_and_crash_recovery.py`

**Interfaces:**
- Consumes: `ExecuteRunTaskV1`、Outbox Repository、Run Repository、Harness execute port、RedisStreamBroker URL
- Produces: `broker`、`dispatch_pending(limit: int)`、Taskiq task `execute_run_task(run_id: str, task_id: str, correlation_id: str, expected_state_version: int)`

- [ ] **Step 1: 写 Dispatcher 和 Worker RED 测试**

测试用 fake Repository/Fake Broker 证明：成功发布后才标记 SENT；发布异常只递增尝试并设置受控 next-at；发布成功但标记前崩溃会重复发布；重复消息在有效租约期间只有一个 Worker 执行；租约过期后允许新 Worker 从同一 Run 恢复。

- [ ] **Step 2: 配置 RedisStreamBroker**

`tasks/broker.py` 从受控 Settings 读取独立 Broker 前缀和 URL，构造 `RedisStreamBroker`。Broker Key 前缀不得等于 `agent:run:`；关闭函数必须释放连接。不得配置 Taskiq 结果为权威 Run 结果。

- [ ] **Step 3: 实现 Outbox Dispatcher**

`dispatch_pending(limit)` 必须：原子 claim 一批到期 PENDING 记录、逐条校验 `ExecuteRunTaskV1`、调用 Taskiq `.kiq()`、成功后条件更新 SENT、失败后记录稳定错误码和指数退避。退避上限、claim lease 和 batch size 均从 Settings 读取并验证为正数。

- [ ] **Step 4: 实现 Worker 生命周期**

Worker 收到原始参数后先构造 `ExecuteRunTaskV1`，显式绑定日志上下文，再调用 `RunRepository.claim()`。claim 返回 `None` 时记录 `duplicate_or_active_lease` 并安全返回；成功时启动有限频率 lease renewal，执行 Harness，终态写 PostgreSQL 后再返回。异常必须归一化为稳定错误事件，不能将 Taskiq return value 当最终事实。

- [ ] **Step 5: Windows 原生 Taskiq PoC**

在 PowerShell 启动 Worker：

```powershell
uv run taskiq worker efficiency_platform_agent.tasks.broker:broker efficiency_platform_agent.tasks.worker
```

另一个 PowerShell 运行集成测试：

```powershell
uv run pytest tests/integration/tasks/test_taskiq_redis_stream.py -q
uv run pytest tests/integration/tasks/test_duplicate_and_crash_recovery.py -q
```

Expected: publish/consume/ACK、Worker 强制终止后的重投递、重复消息单次有效执行全部 PASS；测试结束后 Worker 进程退出，测试 Redis Key 按测试前缀清理。

- [ ] **Step 6: 执行条件 Git checkpoint**

仅暂存本任务文件，提交信息使用 `feat: add reliable taskiq dispatch`。

---

### Task 8: 实现 LangGraph 五策略骨架、Router 与薄 Harness

**Files:**
- Create: `src/efficiency_platform_agent/orchestration/state.py`
- Create: `src/efficiency_platform_agent/orchestration/events.py`
- Create: `src/efficiency_platform_agent/orchestration/runtime.py`
- Create: `src/efficiency_platform_agent/routing/router.py`
- Create: `src/efficiency_platform_agent/harness/service.py`
- Create: `tests/unit/orchestration/test_graph_state.py`
- Create: `tests/unit/orchestration/test_runtime.py`
- Create: `tests/unit/routing/test_router.py`
- Create: `tests/unit/harness/test_service.py`
- Create: `tests/integration/orchestration/test_interrupt_resume.py`

**Interfaces:**
- Consumes: `RunRepository`、`RunEventBus`、`CancellationSignal`、Checkpointer、`StrategyMode`
- Produces: `AgentGraphState`、`GraphRuntime.execute/resume`、`StrategyRouter.select`、`AgentRuntimeService`

- [ ] **Step 1: 写五策略与 Harness RED 测试**

测试必须证明五个 `StrategyMode` 都映射到 `StateGraph` builder；所有入口都经过 Harness；ReAct 有最大步数终止；Plan-and-Execute 的计划在 State 中；Multi-Agent 只有 Supervisor 能调 Specialist subgraph；Specialist 不能直接调另一 Specialist；LangGraph 原始事件不会穿透 API 契约。

- [ ] **Step 2: 定义 TypedDict Graph State**

`orchestration/state.py` 使用：

```python
class AgentGraphState(TypedDict):
    run_id: str
    task_id: str
    correlation_id: str
    strategy: str
    input_data: dict[str, JsonValue]
    plan: list[dict[str, JsonValue]]
    step_count: int
    max_steps: int
    specialist_results: dict[str, dict[str, JsonValue]]
    output: JsonValue
    error_code: str | None
```

状态中不得放 Session、Redis client、SQLAlchemy model、Taskiq message、Pydantic model 或厂商对象。

- [ ] **Step 3: 实现五种技术骨架 Graph**

使用 `StateGraph(AgentGraphState)` 分别构建 Direct、Workflow、bounded ReAct、Plan-and-Execute 和 Supervisor/Subgraph。节点只做确定性技术回显、计数、计划拆分和结构化合并，不接模型或业务逻辑。每个循环都有 `max_steps` 条件边和稳定失败码 `STEP_BUDGET_EXHAUSTED`。

- [ ] **Step 4: 实现规则型 Strategy Router**

P1 Router 输入是显式 `requested_mode`；值缺失默认 Direct，非法值失败关闭。P1 不用 LLM 猜路由。返回值包含 `mode`、`rule_version="1.0"` 和受控 reason code。

- [ ] **Step 5: 实现 Harness 用例服务**

`AgentRuntimeService` 方法固定为：

```python
async def create_run(self, request: CreateRunRequestV1) -> RunViewV1:
    raise NotImplementedError

async def execute_run(self, message: ExecuteRunTaskV1, worker_id: str) -> RunViewV1:
    raise NotImplementedError

async def resume_run(self, run_id: str, request: ResumeRunRequestV1) -> RunViewV1:
    raise NotImplementedError

async def cancel_run(self, run_id: str, request: CancelRunRequestV1) -> RunViewV1:
    raise NotImplementedError

async def get_run(self, run_id: str, tenant_id: str) -> RunViewV1:
    raise NotImplementedError

def stream_run_events(self, run_id: str, tenant_id: str, last_event_id: str | None) -> AsyncIterator[tuple[str, RunEventV1]]:
    raise NotImplementedError
```

实际代码使用显式实现，不使用省略方法体。每个方法验证租户/状态/版本，长期事件先提交 PostgreSQL，再尽力发布 Redis；Redis 发布失败记录安全日志但不回滚权威状态。`stream_run_events()` 是 API 获取实时事件的唯一入口，API 不得直接依赖 Redis client 或 `RedisRunEventBus`。

- [ ] **Step 6: 验证 Graph、暂停恢复与架构依赖**

```powershell
uv run pytest tests/unit/orchestration tests/unit/routing tests/unit/harness -q
uv run pytest tests/integration/orchestration/test_interrupt_resume.py -q
uv run python -m unittest tests.architecture.test_dependency_rules -v
```

Expected: 五策略、步数终止、Supervisor 隔离、`interrupt()`/`Command(resume=resume_value)` 同 Run 恢复均 PASS；没有第二 Graph Runtime。

- [ ] **Step 7: 执行条件 Git checkpoint**

仅暂存本任务文件，提交信息使用 `feat: add governed langgraph runtime`。

---

### Task 9: 实现 FastAPI Run API、SSE、恢复与协作取消

**Files:**
- Create: `src/efficiency_platform_agent/harness/settings.py`
- Create: `src/efficiency_platform_agent/harness/factory.py`
- Create: `src/efficiency_platform_agent/api/routes.py`
- Create: `src/efficiency_platform_agent/api/app.py`
- Modify: `src/efficiency_platform_agent/api/__init__.py`
- Create: `tests/unit/harness/test_settings.py`
- Create: `tests/unit/api/test_routes.py`
- Create: `tests/acceptance/test_run_lifecycle.py`
- Create: `tests/acceptance/test_sse_reconnect.py`
- Create: `tests/acceptance/test_cooperative_cancel.py`

**Interfaces:**
- Consumes: `AgentRuntimeService`、Settings、已完成的 Worker/Graph/Persistence Adapter
- Produces: FastAPI `app` 与稳定 `/v1/runs` 生命周期 API

- [ ] **Step 1: 写 API RED 测试**

路由固定为：

```text
POST /v1/runs
GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/events
POST /v1/runs/{run_id}/resume
POST /v1/runs/{run_id}/cancel
GET  /health/live
GET  /health/ready
```

测试覆盖 201/200、Schema 422、安全 404、防跨租户、非法状态 409、SSE `Last-Event-ID`、取消幂等和错误正文不泄露配置。

- [ ] **Step 2: 实现 Settings 与组合根**

Settings 使用 `pydantic-settings`，配置键分为 `AGENT_RUNTIME_DATABASE_URL`、`AGENT_CHECKPOINT_DATABASE_URL`、`AGENT_VECTOR_DATABASE_URL`、`AGENT_TASK_BROKER_URL`、`AGENT_RUN_EVENT_REDIS_URL`。P1 启动只要求 Runtime/Checkpoint/Broker/Event 四项；Vector DSN 可以为空，因为 P2 才使用。`repr` 和校验错误不得输出 Secret 值。

`harness/factory.py` 是 API/Worker 共用组合根，创建 SQLAlchemy engine、独立 Checkpoint pool、Redis Adapter、Repository、Graph Runtime 和 Service；业务方法不得自行读取环境变量。API 只获得 `AgentRuntimeService`，不得从组合根取出数据库或 Redis Adapter 直接使用。

- [ ] **Step 3: 实现 API 与 lifespan**

FastAPI lifespan 按顺序打开连接、构造服务、注册到 `app.state`，关闭时反向释放。lifespan 禁止调用 Alembic、Checkpoint `setup()` 或任何 DDL。readiness 只检查已配置依赖的轻量连接状态，不创建表。

- [ ] **Step 4: 实现协作式取消**

Cancel API 先写 PostgreSQL `CANCEL_REQUESTED` 事件/`cancel_requested_at`，再设置 Redis TTL Key。Worker 在节点前后、事件 flush 前和可取消 I/O 边界检查；安全退出后用 CAS 转为 `CANCELLED`。对 `SUCCEEDED`/`FAILED`/`CANCELLED`/`TIMED_OUT` 请求取消返回幂等终态视图，不反转终态。

- [ ] **Step 5: 运行 API 与验收测试**

```powershell
uv run pytest tests/unit/api tests/unit/harness/test_settings.py -q
uv run pytest tests/acceptance/test_run_lifecycle.py tests/acceptance/test_sse_reconnect.py tests/acceptance/test_cooperative_cancel.py -q
```

Expected: Create→QUEUED→RUNNING→SUCCEEDED、断线续读、等待恢复和取消路径全部 PASS；Redis 过期时 API 仍能从 PostgreSQL 返回最终状态和长期事件。

- [ ] **Step 6: 执行条件 Git checkpoint**

仅暂存本任务文件，提交信息使用 `feat: expose p1 run lifecycle api`。

---

### Task 10: 固化 Windows PoC、全量质量门禁与交付证据

**Files:**
- Create: `scripts/p1_poc.ps1`
- Create: `docs/reports/2026-09-02-P1-Agent-Runtime兼容性-评审报告.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/architecture/Agent侧技术组件选型.md`
- Modify: `docs/superpowers/plans/2026-09-02-P1-Agent-Runtime实施计划.md`

**Interfaces:**
- Consumes: Tasks 1～9 的全部实现和隔离 PostgreSQL/Redis
- Produces: 一键 Windows PoC、真实版本/命令/结果证据、清晰完成边界

- [ ] **Step 1: 编写 PowerShell PoC 脚本**

`scripts/p1_poc.ps1` 必须使用 `$ErrorActionPreference = 'Stop'`，按顺序检查 Python 3.13、锁文件同步、禁止依赖、单元测试、架构守卫、隔离 PostgreSQL、Checkpoint、Redis Streams、Taskiq ACK/重投递、重复执行、interrupt/resume、取消、SSE reconnect、Ruff、mypy 和 compileall。脚本不得回显任何 `*_URL` 值。

核心命令顺序：

```powershell
uv sync --locked
uv run python --version
uv run pytest tests/unit tests/admission -q
uv run python -m unittest discover -s tests/architecture -v
uv run pytest tests/integration -q
uv run pytest tests/acceptance -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run python -m compileall -q src migrations
```

- [ ] **Step 2: 运行完整 PoC 并保存脱敏输出**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/p1_poc.ps1 *> p1-poc-output.log
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: 退出码 0。输出必须先经过 Secret 扫描；评审报告只摘录版本、测试数量、耗时和稳定错误码，不提交包含环境地址的原始日志。

- [ ] **Step 3: 人工演练 Worker 崩溃与 SSE 重连**

启动一个测试 Run，在节点中断点终止 Worker，等待 Broker 重投递与租约过期，再启动新 Worker；确认同一 `run_id/thread_id` 继续且外部有效执行只有一次。断开 SSE 后携带最后一个 Redis Stream ID 重连，确认没有重复已确认事件，Stream 过期时明确回查 PostgreSQL。

- [ ] **Step 4: 写兼容性评审报告**

报告必须逐项记录：

```text
Python/uv/Windows 版本
所有直接依赖与 uv.lock 版本
Taskiq worker 启停、ACK、重投递
重复投递单有效执行
PostgreSQL CAS/Outbox
AsyncPostgresSaver 跨进程恢复
interrupt/resume 与协作取消
Redis Streams SSE reconnect
测试/Ruff/mypy/compileall 结果
DDL 授权目标与执行证据，或明确未执行
未覆盖的部署、业务 Agent、模型、RAG、OCR、监控平台范围
```

- [ ] **Step 5: 更新开发命令和技术状态**

README 与 CONTRIBUTING 只写实际通过的命令。只有 Taskiq Windows PoC、PostgreSQL/Redis 集成和全量门禁均通过时，技术选型文档才可把 P1 标为“已验证”；依赖已安装但外部集成未跑时必须标为“部分实现、集成未验证”。

- [ ] **Step 6: 最终文件与依赖审计**

```powershell
rg -n "Celery|OpenTelemetry|Prometheus|Grafana|LangSmith|asyncpg|psycopg2|aiomysql" pyproject.toml uv.lock src tests
rg -n "password|authorization|cookie|secret|database_url" p1-poc-output.log
uv run python -m unittest discover -s tests -v
```

Expected: 第一条仅允许测试中的禁止依赖断言，不允许实际安装或导入；第二条不得输出凭据值；完整测试退出码为 0。

- [ ] **Step 7: 执行条件 Git checkpoint 与交付**

Git 存在时仅按文件白名单提交，提交信息使用 `docs: record p1 runtime acceptance`。无 Git 时输出：变更文件清单、`uv.lock` 哈希、SQL 变更包哈希、PoC 命令与结果、未执行项、回滚方式；禁止写“已合并”或“已推送”。

## Self-Review Checklist

- [x] 已批准设计第 1～16 节都能映射到 Task 1～10 的具体交付物。
- [x] 所有新类型和方法在首次被后续任务引用前已有定义任务。
- [x] 没有把 Redis、Taskiq return value 或 Checkpoint 当作 Run/Usage 权威事实。
- [x] `CANCEL_REQUESTED` 明确是事件/标记，不是新增 `RunStatus`。
- [x] SQLAlchemy pool 与 Checkpoint Psycopg pool 明确分离。
- [x] DDL 生成、只读审查、授权执行和运行验证没有混为同一步。
- [x] Windows + Python 3.13、Taskiq Alpha 风险和崩溃恢复均有强制 PoC。
- [x] 监控平台、业务 Agent、模型、RAG、OCR 和部署没有进入 P1 实施范围。
- [x] 每个代码任务都有 RED、最小实现、GREEN 与回归命令。
- [x] 无 Git 场景不会伪造 commit、merge 或 push 状态。

## Rollback Boundary

- 依赖准入失败：使用 `uv remove` 移除失败组件并重新锁定；保留 ADR、失败证据和稳定端口，不改用未经评审框架。
- Taskiq PoC 失败：停止 P1 队列实施，保留 `ExecuteRunTaskV1`、Outbox 和 Worker claim 契约，回到 ADR-0003 比较 Windows 兼容替代方案。
- PostgreSQL Repository 失败：不执行共享 DDL，不让 Redis 接管权威状态；修正模型/事务后在隔离库重新验证。
- Checkpoint 失败：不降级生产态内存 Saver；等待态 Run 必须失败关闭并报告不可恢复。
- Redis Event Bus 失败：权威 Run 与长期事件保持 PostgreSQL 已提交状态，SSE 返回可重连错误并允许状态查询。
- 任何共享 DDL 已执行后的回滚：只使用已批准变更包的 `04-rollback.sql`，先核对影响和数据保留；不得手工删除未解析对象。

## Completion Definition

只有以下事实同时成立才可声明 P1 Runtime 已验证：

1. ADR 已按治理流程批准；
2. `uv.lock` 固定实际通过 PoC 的依赖版本；
3. Windows + Python 3.13 下 Taskiq ACK、重投递、停止与恢复通过；
4. PostgreSQL Run/Outbox/CAS 与 AsyncPostgresSaver 在获授权隔离目标通过；
5. Redis Streams SSE reconnect、TTL 与取消信号通过；
6. 五策略 StateGraph 骨架、Supervisor 子图隔离、interrupt/resume 和协作取消通过；
7. 单元、集成、验收、架构守卫、Ruff、mypy 和 compileall 全部退出码为 0；
8. 报告明确区分已验证与部署、业务、模型、RAG、OCR、监控平台等未进入范围的能力。

若数据库 DDL 未获授权或外部服务集成测试未执行，允许交付代码与文档，但状态必须是“P1 已实现、外部集成未验证”，不得声明 Runtime 已验证或可发布。
