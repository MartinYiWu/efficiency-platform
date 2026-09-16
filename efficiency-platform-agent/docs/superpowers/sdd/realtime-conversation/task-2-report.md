# Task 2 实施报告：DIRECT Graph 与 Harness 端到端实时 SSE

| 项目 | 内容 |
|---|---|
| 状态 | DONE |
| 负责人 | Task 2 实施代理 |
| 适用范围 | DIRECT 通用对话的运行中 delta、SSE、取消与跨片段公开治理 |
| 更新时间 | 2026-09-08 |

## RED 证据

1. `uv run pytest tests/unit/security/test_public_response.py -q`
   - `1 failed, 9 passed`。
   - 原因：`PublicResponseGovernor` 不存在 `stream()`，跨 delta 的敏感模式前缀无法治理。
2. `uv run pytest tests/unit/agents/conversation/test_general_agent.py -q`
   - `1 failed, 16 passed`。
   - 原因：`GeneralConversationAgent.execute()` 不接受 `on_delta`，无法优先使用流式 Runtime。
3. `uv run pytest tests/orchestration/test_conversation_direct_runtime.py -q`
   - `1 failed, 9 passed`。
   - 原因：DIRECT Graph 注册入口不接受 `output_publisher`，缺少按 `run_id` 隔离的窄输出端口。
4. `uv run pytest tests/api/test_run_sse_integration.py -q`
   - `1 failed, 17 passed`。
   - 原因：Harness 不存在 `publish_assistant_delta()`，不能在 `RUNNING` 期间接收实时正文。

## 实现要点

- `PublicResponseGovernor.stream()` 以有限缓冲治理跨 delta 的助手能力否定和内部指令泄露；未形成敏感模式的正常技术讨论会继续输出。
- `GeneralConversationAgent` 在提供 `on_delta` 且 Runtime 存在 `stream_complete()` 时优先流式执行；仅当首片前明确收到 `PROVIDER_UNAVAILABLE` 时回退旧 `complete()`，保持既有 Fake Provider 兼容。
- DIRECT Graph 新增仅传递 `run_id` 与正文的 `ConversationOutputPublisher`，Agent 不依赖 EventHub 或 API 类型。
- Harness 仅在 Run 为 `RUNNING`、未取消时发布 delta，每 Run 只发布一次 `assistant_started`；已实时发布的 DIRECT 正文在成功结算时不再整段重复发送。
- 本地真实组合根移除 96 字符终态伪分片，真实模型 DIRECT 通过 Graph 窄端口调用 Harness。
- 新增端到端回归：首片在 Run 仍为 `RUNNING` 时到达 SSE；首片后的可重试 Provider 错误只保留首片、Run 失败、不得调用备用候选或拼接另一答案。

## GREEN 与验证证据

1. `uv run pytest tests/unit/agents/conversation/test_general_agent.py tests/orchestration/test_conversation_direct_runtime.py tests/api/test_run_sse_integration.py tests/unit/security/test_public_response.py -q`
   - `57 passed in 1.56s`。
2. `uv run ruff check src/efficiency_platform_agent/agents/conversation/general_agent.py src/efficiency_platform_agent/orchestration/builders/conversation_direct.py src/efficiency_platform_agent/harness/service.py src/efficiency_platform_agent/harness/local_real_factory.py src/efficiency_platform_agent/security/public_response.py tests/unit/agents/conversation/test_general_agent.py tests/orchestration/test_conversation_direct_runtime.py tests/api/test_run_sse_integration.py tests/unit/security/test_public_response.py`
   - `All checks passed!`。
3. `uv run python -m unittest tests.architecture.test_dependency_rules -v`
   - `Ran 12 tests ... OK`。

## 修改文件

- `src/efficiency_platform_agent/agents/conversation/general_agent.py`
- `src/efficiency_platform_agent/orchestration/builders/conversation_direct.py`
- `src/efficiency_platform_agent/harness/service.py`
- `src/efficiency_platform_agent/harness/local_real_factory.py`
- `src/efficiency_platform_agent/security/public_response.py`
- `tests/unit/agents/conversation/test_general_agent.py`
- `tests/orchestration/test_conversation_direct_runtime.py`
- `tests/api/test_run_sse_integration.py`
- `tests/unit/security/test_public_response.py`
- `docs/superpowers/sdd/realtime-conversation/task-2-report.md`

## 自查结论与关注点

- 已确认未读取 `.env`、未运行 Git、未启动常驻服务，也未修改 ConversationService、IntentInterpreter、场景 Manifest 或前端文件。
- 已实时发布的 delta 拼接与 DIRECT 成功终态 `output.content` 一致；会话历史仍由既有成功终态路径单次回写。
- Task 1 的 `stream_complete()` 与既有 `stream()` 在候选选择、首片后不降级、超时、取消和带 `error` 的 chunk Usage 最大快照方面已统一；该修复已由新增 RED/GREEN 回归验证。
- 本次全部为离线 Fake/ASGI 验证；未进行真实厂商网络调用或生产 SSE 客户端验收。
