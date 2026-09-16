# Task 1：诊断契约、上下文与本地格式化报告

| 属性 | 内容 |
|---|---|
| 状态 | 已完成（仅 Task 1） |
| 负责人 | Agent 侧实施任务执行者 |
| 更新日期 | 2026-09-08 |
| 适用范围 | 诊断契约、Run ContextVar 与本地固定格式日志 |
| 不适用范围 | Research Provider、ModelRuntime、Graph、Harness 注入和真实外部请求 |
| 关联设计 | [Agent 关键执行与错误日志设计](../../specs/2026-09-08-Agent关键执行与错误日志-设计.md) |

## RED 证据

1. 命令：`uv run pytest tests/unit/core/test_diagnostics.py -q`
   - 结果：退出码 1；收集阶段报 `ModuleNotFoundError: No module named 'efficiency_platform_agent.core.diagnostics'`。
   - 结论：新增诊断上下文与不可变契约测试在实现前有效失败。
2. 命令：`uv run pytest tests/unit/observability/test_local_execution_log.py -q`
   - 结果：退出码 1；收集阶段报同一 `core.diagnostics` 缺失错误。
   - 结论：本地日志测试依赖尚未存在的受控诊断契约，未发生误通过。

## GREEN 与质量证据

1. 命令：`uv run pytest tests/unit/core/test_diagnostics.py tests/unit/observability/test_local_execution_log.py -q`
   - 结果：退出码 0，`22 passed in 2.19s`。
2. 命令：`uv run ruff check src/efficiency_platform_agent/core/diagnostics.py src/efficiency_platform_agent/observability/local_execution_log.py tests/unit/core/test_diagnostics.py tests/unit/observability/test_local_execution_log.py`
   - 结果：退出码 0，`All checks passed!`。
3. 命令：`uv run python -m compileall -q src/efficiency_platform_agent/core/diagnostics.py src/efficiency_platform_agent/observability/local_execution_log.py tests/unit/core/test_diagnostics.py tests/unit/observability/test_local_execution_log.py`
   - 结果：退出码 0，无输出。
4. 命令：`uv run pytest tests/architecture -q`
   - 结果：退出码 0，`43 passed, 124 subtests passed in 2.80s`。

## 真实诊断结论

- `DiagnosticRecord` 是冻结、slots 化的显式白名单契约，不接受 `payload`、`message` 或任意映射字段。
- 契约包含已批准的能力、稳定原因、规则版本、受限本地 `provider_call_id` 与证据计数字段；所有数值字段必须为非 `bool` 的 `int`，HTTP 状态限于 100 至 599，其余计数不得为负数。
- `bind_diagnostic_context()` 基于 `ContextVar` 支持嵌套恢复和 asyncio 并发任务隔离，避免 Run 上下文串线。
- `LocalExecutionLogger` 只按显式字段和固定组件前缀输出，能够关联当前 Run 上下文；底层 Logger 写入失败被隔离，`record()` 入口以 `TypeError` 拒绝自由 `message` 和 `payload` 参数。
- 能力日志仅由 `enabled` 推导 `capability_ready` 或 `capability_disabled`，不接收自由事件字段。

## 未验证项

- Task 2 尚未向 Research Provider 或组合根注入 Recorder，未验证真实 Provider 失败阶段、HTTP 分类与能力装配日志。
- Task 3 尚未为 ModelRuntime、Graph、Harness 绑定上下文或记录异常诊断。
- 未执行任何真实外部请求，未读取、打印、修改或校验 `.env`。

## 审查修复补充证据

1. RED 命令：`uv run pytest tests/unit/core/test_diagnostics.py -q`
   - 结果：退出码 1，`19 failed, 19 passed`。
   - 结论：新增测试证实 `duration_ms`、`attempt`、Token 与证据计数的浮点和 `NaN` 会绕过原有范围比较；字符串会产生非预期的 `TypeError`。
2. 补充 RED 命令：`uv run pytest tests/unit/core/test_diagnostics.py -q -k rejects_fractional_http_status_in_valid_range`
   - 结果：退出码 1，`1 failed, 38 deselected`；断言 `http_status=200.5` 必须被拒绝时得到 `DID NOT RAISE ValueError`。
   - 结论：在测试验证中还原旧的纯范围比较后，精确证明范围内的小数 HTTP 状态会被错误接受；随后立即恢复整数类型校验。
3. GREEN 命令：`uv run pytest tests/unit/core/test_diagnostics.py tests/unit/observability/test_local_execution_log.py -q`
   - 结果：退出码 0，`47 passed in 1.89s`。
   - 结论：所有数值字段已验证拒绝浮点、字符串和 `NaN`，其中包含 `http_status=200.5`；并发 ContextVar 隔离、自由 `message` 字段拒绝及 Logger 抛错隔离均受单元测试覆盖。
4. 质量命令：`uv run ruff check src/efficiency_platform_agent/core/diagnostics.py src/efficiency_platform_agent/observability/local_execution_log.py tests/unit/core/test_diagnostics.py tests/unit/observability/test_local_execution_log.py`
   - 结果：退出码 0，`All checks passed!`。

## Task 2 组合根兼容性证据

1. RED 命令：`uv run pytest tests/unit/observability/test_local_execution_log.py -q`
   - 结果：退出码 1，`1 failed, 7 passed`。
   - 结论：组合根开始调用同一 Logger 的 `log_capability()` 后，测试替身缺少该方法，抛出 `AttributeError`。
2. GREEN 命令：`uv run pytest tests/unit/observability/test_local_execution_log.py -q`
   - 结果：退出码 0，`8 passed in 5.04s`。
   - 结论：测试替身已实现 `record()` 和 `log_capability()` 的受控记录，并验证 Gate 关闭时的 `deepseek_web_search` 固定能力状态。
3. 质量命令：`uv run ruff check tests/unit/observability/test_local_execution_log.py`
   - 结果：退出码 0，`All checks passed!`。
