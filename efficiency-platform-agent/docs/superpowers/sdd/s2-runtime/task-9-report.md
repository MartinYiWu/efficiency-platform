# S2 任务 9：唯一 LangGraph Runtime、Direct 与固定 Workflow

## 状态

已完成（离线 Graph 单元 GREEN，待阶段级复核）。

## 实际文件

- `src/efficiency_platform_agent/orchestration/state.py`
- `src/efficiency_platform_agent/orchestration/contracts.py`
- `src/efficiency_platform_agent/orchestration/registry.py`
- `src/efficiency_platform_agent/orchestration/cancellation.py`
- `src/efficiency_platform_agent/orchestration/checkpoint.py`
- `src/efficiency_platform_agent/orchestration/runtime.py`
- `src/efficiency_platform_agent/orchestration/builders/direct.py`
- `src/efficiency_platform_agent/orchestration/builders/workflow.py`
- `tests/unit/orchestration/test_graph_runtime.py`
- `tests/unit/orchestration/test_cancellation.py`
- `tests/architecture/test_s2_runtime_boundaries.py`

## RED/GREEN

任务开始阶段因 Graph Runtime 模块及核心类型缺失而无法收集测试；修正契约导入后完成最小实现。当前聚焦验证：

```text
uv run pytest tests/unit/orchestration/test_graph_runtime.py tests/unit/orchestration/test_cancellation.py tests/architecture/test_s2_runtime_boundaries.py -q
6 passed

uv run ruff check src/efficiency_platform_agent/orchestration tests/unit/orchestration tests/architecture/test_s2_runtime_boundaries.py
All checks passed

uv run mypy src/efficiency_platform_agent/orchestration
Success: no issues found
```

另行验证 Direct 与 Workflow 均可在 LangGraph InMemorySaver 下执行并返回结构化 `JsonObject` 输出；LangGraph 导入仅存在于 `orchestration/**`。

2026-09-04 补充验证：`GraphRuntime` 的 Checkpoint 适配同时兼容同步与异步存储端口，并在执行、恢复、读取及失败路径传递 `tenant_id`；内存适配器按租户分区，异步存储路径和跨租户无命中聚焦测试通过。该兼容性仅证明运行时适配行为，不代表真实 PostgreSQL 跨进程持久化已验收。

## 已实现边界

- 显式 GraphRegistry，按策略唯一注册并拒绝重复；
- Direct 与固定 Workflow 使用同一个 GraphRuntime；
- 唯一 `execute(self, selection, initial_state)` 生命周期；
- CheckpointView、进程内取消信号和 payload 白名单基础校验；
- 非法图结果归一化为安全失败，不回显内部异常。
- `FAILED/TIMED_OUT` 携带成功输出或缺少合法错误码时统一丢弃输出并失败关闭，避免把非法状态组合交给 Harness。

## 未验证边界

- 尚未接入 Harness、API/SSE、真实 Provider 或真实 Tool；
- 尚未完成完整预算前后节点治理、恢复语义和六组端到端 acceptance；
- Checkpoint 仍为进程内测试适配器，未验证跨进程、并发和生产持久化。
