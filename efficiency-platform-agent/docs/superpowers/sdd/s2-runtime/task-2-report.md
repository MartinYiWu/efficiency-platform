# S2 任务 2 实施报告：Run、事件、预算与异步端口核心契约

## 1. 范围与状态

- 状态：已修复（核心契约 GREEN，待独立复核）。
- 目标：按计划 2.2 建立框架中立的五维预算、运行事实、事件安全边界和异步存储端口。
- 非目标：不实现任务 3～12 的 Harness、路由、Graph、Provider、Tool、API/SSE 或 Fake acceptance runtime。
- 既有 RED 证据保持原样：`task-2-core-red.txt`、`task-2-acceptance-red.txt` 未重写或删除；修正后的导入路径与目标模块缺失证据见 `task-2-core-red-corrected.txt`，修复过程和限制见 `task-2-fix-report.md`。

## 2. 实现内容

### 2.1 预算守卫

`core/budget.py` 提供冻结、带 `slots` 的 `BudgetCharge`、`BudgetState`、`RemainingBudget`，以及 `BudgetGuard` 和统一 `BudgetExhaustedError`。预算按迭代、Tool 次数、输入 Token、输出 Token、费用五维计算；`start()` 固定绝对 deadline，调用前检查与调用后记账均保持单调消费，并在到达 deadline 或任一维度超限时失败关闭。

### 2.2 Run 与事件事实

`core/runtime.py` 提供 `UsageSnapshot`、`StrategyPayload`、`RunFailure`、`RunRecord`、`RunEventRecord`、`ExecutionFact`。所有值对象均冻结并带 `slots`；`RunRecord.__post_init__` 与 `transition()` 共同约束终态输出/失败载荷，并拒绝预算消费倒退或重写起始时间、绝对 deadline。事件类型使用固定白名单，`strategy_event` 使用固定信封字段，敏感正文键递归拒绝（包括嵌套 `JsonObject`/tuple/Mapping）。

### 2.3 异步端口与架构守卫

`core/runtime_ports.py` 提供 `RunRepository`、`RunEventStore`、`Clock`、`IdGenerator` 异步/可替换端口。架构测试增加 S2 核心文件的上层与框架依赖扫描，确保只依赖标准库和 `core` 内部契约。

## 3. 新鲜验证证据

以下命令均在 `D:\efficiency-platform\efficiency-platform-agent` 执行，未连接网络或真实基础设施：

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/unit/core/test_budget_guard.py tests/unit/core/test_runtime_contracts.py tests/contract/runtime/test_event_contract.py -q` | 33 passed，退出码 0 |
| `uv run pytest tests/architecture/test_core_contracts.py tests/unit/core tests/contract/runtime/test_event_contract.py -q` | 49 passed，31 subtests passed，退出码 0 |
| `uv run python -m unittest tests.architecture.test_core_contracts tests.unit.agents.test_agent_spec -v` | 18/18 通过，退出码 0 |
| `uv run ruff check src/efficiency_platform_agent/core/budget.py src/efficiency_platform_agent/core/runtime.py src/efficiency_platform_agent/core/runtime_ports.py tests/architecture/test_core_contracts.py` | All checks passed，退出码 0 |
| `uv run mypy src/efficiency_platform_agent/core/budget.py src/efficiency_platform_agent/core/runtime.py src/efficiency_platform_agent/core/runtime_ports.py` | Success，退出码 0 |

## 4. 未验证与已知边界

- `uv run pytest -q` 仍会收集历史快照目录并触发同名测试导入冲突，同时 acceptance 测试依赖尚未创建的 `support.runtime_fakes`；这些属于任务 3～12 范围，不在本任务实现。
- 修正后的核心 RED 无法在已存在生产实现的工作树上重放，已使用等价隔离快照记录目标模块缺失证据，未伪造原始时间或结果。
- 尚未接入 LangGraph 唯一 Graph Runtime、Harness、真实或跨进程持久化、PostgreSQL `AsyncPostgresSaver`、Redis、Provider/Tool 网络调用、API/SSE、取消唤醒和生产部署。
- 当前 GREEN 仅证明核心数据类、预算规则、事件白名单、状态转换和端口形状；不等价于端到端或生产验收完成。
