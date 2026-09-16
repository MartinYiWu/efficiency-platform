# Task 2 任务简报：DIRECT Graph 与 Harness 端到端实时 SSE

## 目标

把 Task 1 的 `ModelRuntime.stream_complete(..., on_delta=...)` 接入通用对话，使安全正文 delta 在模型尚未完成、Run 仍为 `RUNNING` 时到达 SSE，并保持最终正文、预算、取消、终态和历史一致。

## 已有接口

- `ModelRuntime.stream_complete(demand, request, *, remaining_budget, on_delta) -> ModelExecutionResult`
- `PublicResponseGovernor.govern(content) -> str`
- 本地固定回复继续走结果发布；真实模型 DIRECT 必须走运行中增量发布。

## 文件所有权

- 可修改：`src/efficiency_platform_agent/agents/conversation/general_agent.py`
- 可修改：`src/efficiency_platform_agent/orchestration/builders/conversation_direct.py`
- 可修改：`src/efficiency_platform_agent/harness/service.py`
- 可修改：`src/efficiency_platform_agent/harness/local_real_factory.py`
- 可修改：`src/efficiency_platform_agent/security/public_response.py`（仅增加流式跨片段治理）
- 可修改对应 Agent、Graph、Harness、API SSE、输出治理测试。
- 不得修改 ConversationService、IntentInterpreter、场景 Manifest 或前端文件。

## 必须满足

- 严格 TDD，先实际运行有效 RED，再写最小生产实现并运行 GREEN。
- `GeneralConversationAgent` 兼容现有测试 Fake：支持流式运行时优先，必要时为仅有 `complete()` 的旧窄端口保留兼容路径，但本地真实组合根必须走真实流式。
- Graph 通过按 `run_id` 隔离的窄输出端口发布，不把 EventHub/API 类型注入 Agent。
- Harness 只在 Run 为 `RUNNING` 且未取消/未终态时接受 delta；`assistant_started` 每 Run 至多一次。
- 已实时发布的 DIRECT 正文在成功结算时不得再次整段发布；本地固定回复和多 Agent 质量门后成品仍能正常发布。
- SSE delta 拼接必须严格等于最终 `output.content`，会话历史只回写一次。
- 流式正文必须经过有界跨片段治理；敏感模式跨 delta 时不得把内部能力限制或系统指令前缀提前交付。用户正常技术讨论不得误拦。
- 首个可见 delta 前允许 ModelRuntime 降级；首片后失败或取消不得拼接备用模型答案。
- 取消后无迟到 delta；不同 Run 的取消和增量互不影响。
- 移除/停用 DIRECT 完整结果后的 96 字符伪分片，但不得破坏非 DIRECT 结果呈现。
- 不新增事件类型；前端依旧消费 `assistant_started`、`assistant_delta`、`stream_done`。
- 所有新增注释/Docstring 中文；不读取 `.env`，不运行 Git，不启动常驻服务。

## 验证

至少运行：

```powershell
uv run pytest tests/unit/agents/conversation/test_general_agent.py tests/orchestration/test_conversation_direct_runtime.py tests/api/test_run_sse_integration.py tests/unit/security/test_public_response.py -q
uv run ruff check src/efficiency_platform_agent/agents/conversation/general_agent.py src/efficiency_platform_agent/orchestration/builders/conversation_direct.py src/efficiency_platform_agent/harness/service.py src/efficiency_platform_agent/harness/local_real_factory.py src/efficiency_platform_agent/security/public_response.py tests/unit/agents/conversation/test_general_agent.py tests/orchestration/test_conversation_direct_runtime.py tests/api/test_run_sse_integration.py tests/unit/security/test_public_response.py
uv run python -m unittest tests.architecture.test_dependency_rules -v
```

把 RED 命令/失败原因、GREEN 命令/结果、修改文件和自查结论写入 `task-2-report.md`。
