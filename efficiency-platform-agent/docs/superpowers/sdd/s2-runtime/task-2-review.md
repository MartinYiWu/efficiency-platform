# S2 任务 2 独立复核：Run、事件、预算与异步端口核心契约

## 复核范围与结论

复核了实施计划任务 2 及第 2.2 节、`task-2-report.md`、S2 进度账本、RED/GREEN 证据、`core/budget.py`、`core/runtime.py`、`core/runtime_ports.py`、核心单元/事件契约测试及架构守卫。未修改生产代码或测试。

结论：**需修复，当前不批准任务 2 的“已完成”结论。** 核心实现的聚焦 GREEN 可复现，但前置 TDD RED 证据不满足计划规定的“失败只能来自目标模块缺失”，且事件敏感字段保护存在可绕过路径。除这两项外，BudgetGuard 五维计算、绝对 deadline 边界、状态转换的主要路径、异步端口形状、core 依赖方向均通过复核。未发现任务 3 及以后生产实现被提前写入。

## 规范符合性

### Critical

1. **TDD 核心 RED 证据不真实/不纯净，阻断批准。** 计划要求核心 RED 的错误只能是 `core.budget`、`core.runtime` 或 `core.runtime_ports` 尚不存在。`task-2-core-red.txt:23-32` 显示事件测试当时执行的是 `from efficiency_platform_agent.core.run import JsonObject, RunEventRecord`，并因 `core.run` 没有 `RunEventRecord` 而失败；这不是目标生产模块缺失导致的失败。当前测试已改为从 `core.runtime` 导入（`tests/contract/runtime/test_event_contract.py:7-10`），但没有对应的、在生产实现前运行的修正后 RED 证据。因此报告/账本将该文件作为有效 RED 的结论不能成立。需要在可审计的干净快照上用修正后的测试重新生成 RED，并明确命令和时间；不能把实现后的 GREEN 反推为初始 RED。

### Important

1. **事件敏感字段检查只检查顶层键，可通过嵌套 `JsonObject` 泄露正文。** `core/runtime.py:213-217` 仅对 `self.payload.items` 的第一层键与 `_SENSITIVE_EVENT_KEYS` 求交集。实际复核中，`payload=JsonObject((("meta", JsonObject((("prompt", "secret"),))),))` 可成功构造 `RunEventRecord`，因此嵌套 prompt/arguments/exception 等正文不会被拒绝。这违反事件安全边界；应递归扫描所有 `JsonObject`/tuple，或把每类事件 payload 约束为只含稳定 ID、计数和安全原因码的结构化白名单，并补充嵌套泄露回归测试。

2. **`RunRecord` 的状态不变量只在 `transition()` 路径生效，直接构造/反序列化可得到非法权威快照。** `core/runtime.py:93-115` 没有校验状态与 `output`/`failure` 的对应关系；例如可直接构造 `status=SUCCEEDED, output=None, failure=None`，或 `status=FAILED, failure=None` 的记录。`transition()`（`117-146`）本身对变更路径的终态/非终态载荷、预算消费倒退和起始时间/deadline 改写检查是正确的，但 Repository 将来若从存储恢复或直接装配 `RunRecord`，这些不变量可被绕过。建议在 `__post_init__` 增加与状态一致的快照校验（同时保留 CREATED 等初始态的合法空载荷），并增加直接构造非法终态的测试。

## 代码质量与验证结果

### 通过项

- `BudgetGuard` 按五维分别计算 `limit - consumed`；消费为负时不钳制而抛出对应 `BudgetExhaustedError.reason_code`（`core/budget.py:100-131`）。`now == deadline` 及超过 deadline 均按 `absolute_timeout` 失败（`111-112`）；`record_after_node()` 保留原 started/deadline 并在实际消费后再次检查（`156-179`）。
- `RunRecord.transition()` 使用 `validate_run_status_transition`、版本递增及消费单调检查（`core/runtime.py:117-158`）；聚焦路径覆盖 CREATED→QUEUED→RUNNING→SUCCEEDED、非法跳转和终态载荷。
- `RunRepository`/`RunEventStore` 的持久化边界保持 `async def`，`Clock`/`IdGenerator` 为同步时钟/ID 端口；四个 Protocol 均带 `@runtime_checkable`（`core/runtime_ports.py:11-52`）。独立反射检查确认异步签名形状。
- 依赖守卫和直接 AST 复核均未发现 `pydantic`、LangGraph、FastAPI、Jinja2 或 harness/routing/orchestration 上层导入；当前新增生产文件仅为任务 2 指定的三个 core 文件。
- 新鲜聚焦验证：`uv run pytest tests/unit/core/test_budget_guard.py tests/unit/core/test_runtime_contracts.py tests/contract/runtime/test_event_contract.py -q` 为 **18 passed**；架构及核心回归为 **34 passed，31 subtests passed**；Ruff 和 mypy 均通过。未运行依赖任务 3 `support.runtime_fakes` 的 acceptance 全量。

### Minor

1. 核心测试虽覆盖五维“调用前超一单位”和 deadline 恰好边界，但没有直接断言 `remaining()` 在已消费超限时返回负值而不被钳零，也没有覆盖节点后超限时业务输出被丢弃/零后继调用的运行时行为；后者属于后续 Harness/Graph 接线，但应在相应 acceptance 中补齐。
2. RED/GREEN 文本只保存 pytest 输出，未在文件内记录命令行和时间戳；在已有错误导入的情况下，单靠文件系统时间不足以证明 TDD 顺序。重新生成证据时应把命令、时间、退出码和失败原因写入证据文件。

## 待修复后复核门槛

1. 重新生成“修正测试导入后的、生产实现前”的核心 RED，并将其与 acceptance RED 分开记录。
2. 递归/结构化收紧事件 payload 敏感字段边界，增加嵌套 `prompt`、`arguments`、`exception` 等拒绝测试。
3. 决定并实现 `RunRecord` 直接构造时的状态载荷不变量，再复跑核心 GREEN、架构守卫和 S1 回归。

