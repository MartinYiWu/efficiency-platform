# C03 实施任务简报：共享原子预算租约、来源配额与并发执行事实

## 目标与边界

实现 Agent 侧的中立预算租约与离线 Fake Repository，确保跨调用的原子预留/结算/释放事实；不接生产数据库、不改共享 DDL、不启用网络或真实模型费用。现有 `BudgetGuard`、`ToolRuntime`、`ModelRuntime` 先保持兼容，只有通过适配器显式接入新父账本。

## 文件白名单

- 新增 `src/efficiency_platform_agent/core/budget_lease.py`：仅标准库和 core 内已有中立类型；不得导入 Pydantic、tools、capabilities、providers。
- 新增 `src/efficiency_platform_agent/contracts/research_execution_v2.py`：Pydantic 边界契约、预算租约端口和状态结构。
- 新增 `src/efficiency_platform_agent/capabilities/research/v2/__init__.py` 与 `budget.py`：Fake/内存租约实现和模型/来源用量事实转换；不得双重扣费。
- 新增 `tests/unit/core/test_budget_lease.py`、`tests/unit/tools/test_research_budget_adapter.py`。
- 如需补充测试支持，只能新增 `tests/support/budget_v2_cases.py`；不改现有 Runtime 主流程，除非先证明现有签名兼容且保持回归。

## 冻结规则

1. `BudgetScope` 至少包含 tenant、run、stage 和 quota dimension；租户使用记录隔离，来源免费配额按共享 source/account bucket 计数，不能按 tenant 重置供应商桶。
2. `BudgetLeasePort.reserve(scope, invocation_id, charge, expected_version) -> Reservation`、`settle(reservation_id, actual, outcome) -> LedgerSnapshot`、`release(reservation_id) -> LedgerSnapshot` 均为 async；实现必须以 CAS/版本事实保证多协程并发，不依赖单个业务锁作为正确性证明。
3. 原子不变量：`used + reserved + new <= limit`；同一 invocation_id 的 reserve/settle/release 重放幂等，冲突返回稳定错误，不静默覆盖。
4. charge/actual 使用非负整数；unknown/estimated 结果必须保留占用或按保守最大值结算，不能把未知调用释放成零费用。
5. 预留失败不得 dispatch；已知零费用的确定性步骤可以不消耗模型预算（适配器只转换真实事实，不替父账本重复扣费）。
6. 取消/迟到结果保留审计事实；迟到成功不得自动形成可交付成功结果。
7. 所有 Pydantic 边界 `extra=forbid,frozen=True`；core dataclass 使用 `frozen=True,slots=True`；中文 docstring；不使用 `Any` 绕过签名。

## TDD 验收

先写行为红灯：同一 run 剩余 1 次的两个并发申请恰有一个成功；超限不派发；version 冲突；幂等 settle；unknown 结果不释放；source/account 与 tenant 隔离；取消后的迟到结果保留审计。

执行：

```text
.venv/Scripts/python.exe -m pytest tests/unit/core/test_budget_lease.py tests/unit/tools/test_research_budget_adapter.py tests/unit/tools/test_tool_runtime.py tests/unit/capabilities/test_model_runtime.py -q
.venv/Scripts/python.exe -m ruff check src/efficiency_platform_agent/core/budget_lease.py src/efficiency_platform_agent/contracts/research_execution_v2.py src/efficiency_platform_agent/capabilities/research/v2 tests/unit/core/test_budget_lease.py tests/unit/tools/test_research_budget_adapter.py
.venv/Scripts/python.exe -m mypy src/efficiency_platform_agent/core/budget_lease.py src/efficiency_platform_agent/contracts/research_execution_v2.py src/efficiency_platform_agent/capabilities/research/v2/budget.py
```

将红灯/绿灯、并发证据、未接生产边界写入 `task-C03-report.md`，审查通过后由控制器更新进度账本。
