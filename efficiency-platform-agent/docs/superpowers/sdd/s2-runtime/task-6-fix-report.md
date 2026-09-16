# S2 任务 6 复核修复报告：Tool Runtime 治理闭环

## 状态

已修复（离线 Tool Runtime 回归 GREEN）；真实外部 Tool、MCP、Provider、网络、数据库、Redis、跨进程恢复和生产部署仍未验证。

## 修复范围

- `ToolRuntime` 为重试尝试在首次调用时建立共享绝对 deadline；每次尝试使用该 deadline 的剩余时间，不再重置完整 timeout。
- `ToolError` 结果先经过 contract、结果 Schema、输出大小治理，再归一化为固定安全错误；错误携带的 output 不再泄露给上层。
- 增加可选的 `BudgetGuard`、`ExecutionBudget`、`BudgetState` 与时钟注入，调用前真实执行 `check_before_node()`，调用后真实执行 `record_after_node()`；更新后的 `BudgetState` 通过 `ToolRuntime.budget_state` 暴露，原有 `invoke()` 返回二元组契约保持不变。未注入预算上下文时保留既有 `RemainingBudget` 调用兼容路径。

## TDD 证据

先新增三条回归测试并运行：

`.venv\\Scripts\\python.exe -m pytest tests/unit/tools/test_tool_runtime.py -q`

结果：13 项中 10 项通过、3 项失败，失败分别复现绝对 deadline 重置、ToolError output/安全消息绕过和缺少 BudgetGuard 注入接口。

完成最小实现后运行：

| 命令 | 结果 |
|---|---|
| `.venv\\Scripts\\python.exe -m pytest tests/unit/tools/test_tool_runtime.py tests/contract/runtime/test_tool_contract.py -q` | 15 passed |
| `.venv\\Scripts\\ruff.exe check src/efficiency_platform_agent/tools/runtime tests/unit/tools/test_tool_runtime.py` | All checks passed |
| `.venv\\Scripts\\python.exe -m mypy src/efficiency_platform_agent/tools/runtime` | Success: no issues found |
| `.venv\\Scripts\\python.exe -m pytest tests/architecture/test_dependency_rules.py -q` | 10 passed，36 subtests passed |
| `.venv\\Scripts\\python.exe -m compileall -q src tests` | 通过 |

## 未验证与边界

全量 `pytest -q` 未作为通过证据：仓库既有文档快照测试的同名模块导入冲突，以及 acceptance 测试引用尚未提供的 `tests.support.runtime_fakes` 工厂导致收集失败；本修复未扩大范围处理这些既有问题。未执行 Git、网络或外部 Tool。
