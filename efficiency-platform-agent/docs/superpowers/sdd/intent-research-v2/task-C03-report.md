# C03 实施报告：共享原子预算租约与执行事实

## 状态

**离线通过。** C03 已完成实现、定向反例、全量回归和独立文件级审查；没有接生产数据库、共享 DDL、真实来源或真实模型费用。生产权威存储仍归 X01。

## 交付文件

- `src/efficiency_platform_agent/core/budget_lease.py`
- `src/efficiency_platform_agent/contracts/research_execution_v2.py`
- `src/efficiency_platform_agent/capabilities/research/v2/__init__.py`
- `src/efficiency_platform_agent/capabilities/research/v2/budget.py`
- `src/efficiency_platform_agent/tools/runtime/service.py`
- `src/efficiency_platform_agent/capabilities/model/runtime.py`
- `tests/unit/core/test_budget_lease.py`
- `tests/unit/tools/test_research_budget_adapter.py`
- `tests/unit/tools/test_tool_runtime.py`
- `tests/unit/capabilities/test_model_runtime.py`
- `tests/unit/capabilities/model/test_runtime.py`

## 已实现不变量

- `reserve -> mark_dispatched -> settle` 是唯一外部调用生命周期；预留失败不派发，dispatch 后不得 release。
- reserve 与 dispatch 之间若进入取消终态或截止时间，原子释放预留并拒绝派发。
- CAS 冲突刷新权威 snapshot/version 后有界重试；额度充足的共享父账本并发不会被误判为耗尽。
- source/account 免费额度跨 tenant 共享真实桶；tenant/run 使用事实与 invocation 幂等键仍隔离，不泄露首个租户 scope。
- unknown 结果按预留与已知实际逐维保守结算；已派发调用实际超额时完整记录 observed actual，标记 `over_limit=True`、`delivery_allowed=False`，关闭 reservation 并禁止后续调用。
- deadline、取消终态及超额的成功结果只保留用量和审计，不形成可交付成功。
- Tool、Model complete、stream、stream_complete 均可显式使用父 BudgetLeaseContext；旧预算与租约不能双开。
- 租约治理的流式模型先完成结算和交付判定，再释放缓存增量；无租约旧入口保持既有实时流式行为。
- 旧构造器预算路径用锁保护并把最新 BudgetState 写回实例；显式 per-call context 仍可并发隔离。
- `model_invocation_started` 只在 Provider 已解析且租约 reserve+dispatch 成功后记录。
- core 仅使用标准库 dataclass/Protocol；Pydantic 只位于 contracts 边界。

## 关键反例闭环

独立审查先后发现并验证修复：共享实例预算串账、共享来源租户泄露、reserve 与 dispatch 混淆、取消不算迟到、契约长度漂移、父账本未接 Runtime、流式提前交付、构造器预算不累计、终态与 dispatch 竞争、旧 remaining 早退遗留、CAS 误拒绝、started 事件提前、overrun 丢失实际用量、错误结果 usage 归零。

最终最小反例事实：Provider 实际 cost=5 且超过预留时，返回 `BUDGET_EXHAUSTED`，正文不交付，`ProviderResult.usage=5`、`ModelExecutionResult.usage=5`、ledger used=5、audit actual=5、`over_limit=True`、reserved=0。

## 验证证据

```text
.venv/Scripts/python.exe -m pytest tests/architecture/test_core_contracts.py tests/architecture/test_dependency_rules.py tests/unit/core/test_budget_lease.py tests/unit/tools/test_research_budget_adapter.py tests/unit/tools/test_tool_runtime.py tests/unit/capabilities/test_model_runtime.py tests/unit/capabilities/model/test_runtime.py -q
93 passed, 78 subtests passed

.venv/Scripts/python.exe -m ruff check <C03 source and tests>
All checks passed!

.venv/Scripts/python.exe -m mypy <C03 source modules>
Success: no issues found
```

最终独立审查结论为 PASS，无 Critical、Important 或 Minor。最终全量仓库回归为 1025 passed、275 subtests passed，仅保留 2 条既有第三方弃用/未来行为警告。

## 边界与残余风险

- `InMemoryBudgetLeaseRepository` 仅是离线 Fake；生产正确性不得依赖进程内锁。X01 必须用数据库 CAS、唯一约束和独立连接并发测试实现同一端口。
- over-limit 表示已经发生的外部事实，不是允许事前超支；新 reserve 会因 used 已超限继续失败关闭。
- 180 秒、35 秒、25% 等策略值未硬编码，必须由批准后的策略快照提供。
