# S2 任务 6 独立复核：Tool Runtime 与合成 Tool

## 复核结论

结论：**部分通过，不能按当前实现批准为规范完整 GREEN**。

本次聚焦测试与架构依赖门禁均通过，但发现一个会导致绝对 deadline 被重试突破的高优先级问题，以及一个结果治理绕过问题。现有证据足以证明进程内离线的基本注册、拒绝、Schema、取消、超时、重试和大小限制路径；不足以证明第 2.3 节要求的绝对超时、调用后完整结果治理和生产安全边界。

## 新鲜验证

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/unit/tools/test_tool_runtime.py tests/contract/runtime/test_tool_contract.py -q` | `12 passed`，无失败/错误/跳过 |
| `uv run python -m unittest tests.architecture.test_dependency_rules -v` | `10 tests`，全部 `OK` |

另以合成计数 Tool 做只读探测：初始 `remaining_budget.timeout_ms=100`，两次可重试调用各延迟约 60ms；Runtime 实际耗时约 `0.131s`，执行了 2 次并返回可重试错误。该结果说明每次重试重新开启了完整 timeout，而不是遵守同一个绝对 deadline。

## 覆盖确认

- 注册存在、白名单、权限、副作用和参数键拒绝路径均在调用前返回，计数型 Fake 保持零调用。
- `ToolSpec` 的 Pydantic 参数/结果模型、版本和最大输出字节数有契约测试；合成 `SyntheticLookupTool` 只返回固定结果，源码未引入网络、文件、数据库、Redis 或 Provider I/O。
- Runtime 对工具异常、超时、取消统一为固定安全错误码；测试确认输入文本不出现在超时安全消息中。
- 可重试且无副作用的错误最多尝试两次；不可重试错误只尝试一次；结果 Usage 的 output token/cost 会影响本次调用内的剩余快照。
- 未扩展或声称验证 MCP、外部 Tool、Provider、网络、数据库、Redis、跨进程恢复、写 Tool 或生产部署。

## 发现的问题

### [P1] 重试不遵守绝对 timeout

`src/efficiency_platform_agent/tools/runtime/service.py` 的 `invoke()` 只接收一个 `RemainingBudget` 快照；`_invoke_bounded()` 对每次尝试单独执行 `asyncio.timeout(timeout_ms / 1000)`。每次调用结束后 `_consume()` 不扣减 `timeout_ms`，下一次循环仍使用原 timeout。因此第一次调用已经消耗的墙钟时间不会从第二次调用的 deadline 中扣除，重试可以超过 S2 计划要求的“首次确定的 absolute timeout”。

影响：重试场景可能超出 Run 的绝对截止时间，进而违反计划中的“在调用中受绝对超时控制”和预算单调性；也可能让取消/超时事件晚于父级生命周期。修复方向应是传入可计算 deadline/时钟或由 `BudgetGuard` 在每次尝试前重新计算 remaining timeout，并确保重试前再次执行同一绝对 deadline 检查。

### [P1] ToolError 分支绕过结果 Schema 与大小治理

服务在 `result.error is not None` 分支直接返回 `result`，该分支位于结果版本、结果模型和 `max_output_bytes` 检查之前。`ToolResult` 契约允许同时携带 `error` 与 `output`，因此不可信 Tool 可以返回带错误的超大或结构非法 output，Runtime 仍会把原对象交给上层；同时 Tool 自带的 `safe_message` 也未经 Runtime 脱敏/长度治理。

这不符合第 2.3 节“调用后执行结果 Schema、大小、脱敏和审计治理”的完整要求，尤其未来 MCP/外部 Tool 接入时会扩大不可信输入面。应先统一校验/丢弃 error 结果中的 output，执行大小和错误安全消息治理，再按固定错误模型返回。

### [P2] 当前实现未真正调用 BudgetGuard 的调用后记账端口

计划明确要求 `BudgetGuard.check_before_node()` 与 `BudgetGuard.record_after_node()`；当前 Runtime 仅接收 `RemainingBudget` 并在内存中用 `_consume()`/`_consume_tool_call()` 维护局部快照，无法更新父级 `BudgetState`，也不扣减 iterations、input_tokens 或实际 timeout。该接口设计可作为离线最小实现，但不能证明 Run 级预算账本已经完成调用后权威记账；需要在后续统一 Harness/Runtime 集成时补齐并增加跨调用测试。

## 规范与代码质量判断

- 规范符合：Tool Runtime 是显式唯一入口；ToolRegistry 不做动态发现；拒绝路径零副作用；合成 Tool 无外部 I/O；未越界到 MCP/外部 Tool。
- 代码质量：结构清楚、错误码固定、异常不回显原文，且已有测试命名与范围基本匹配；但绝对 deadline 的状态建模不足，结果错误分支的治理顺序存在安全漏洞。
- 交付状态建议：保留“离线基本能力已验证”，将任务 6 标为“部分完成/待修复”，关闭上述 P1 后再声称 Tool Runtime 规范完整 GREEN。当前不应宣称生产就绪或真实 Tool/MCP 已验收。

