# Task 4：阶段事件与用户级错误实施报告

## 状态

DONE_WITH_CONCERNS

本任务已完成阶段事件契约、运营运行阶段摘要、用户级错误脱敏和 SSE 回放兼容验证。阶段事件由 Harness 在统一 Run 生命周期中发布，避免把内部 Prompt、工具参数、模型原文或隐藏推理放入图状态和用户事件。

## TDD 证据

先新增 `tests/api/test_operation_phase_events.py`，运行：

```text
uv run pytest tests/api/test_operation_phase_events.py -q
```

结果：`1 failed, 1 passed`。失败原因为预期的 `research_started` 尚未发布，证明测试覆盖了新增行为而不是既有行为。

实现阶段事件后运行同一命令，结果：`2 passed`。

目标回归：

```text
uv run pytest tests/api/test_operation_phase_events.py tests/api/test_run_sse_integration.py tests/acceptance/test_sse_replay.py -q
```

结果：`23 passed`。

静态检查：

```text
uv run ruff check src/efficiency_platform_agent/contracts/stream_events.py src/efficiency_platform_agent/harness/service.py src/efficiency_platform_agent/orchestration/builders/operation_runtime.py tests/api/test_operation_phase_events.py
```

结果：`All checks passed!`

```text
uv run mypy src/efficiency_platform_agent/contracts/stream_events.py src/efficiency_platform_agent/harness/service.py src/efficiency_platform_agent/orchestration/builders/operation_runtime.py
```

结果：`Success: no issues found in 3 source files`。

## 已实现内容

### 1. 阶段事件契约

在 `StreamEventName` 中增加：

- `research_started`
- `research_completed`
- `content_generation_started`
- `content_generation_completed`
- `quality_checked`

保留原有 `phase_started`、`deliverable`、`stream_error` 和 `stream_done`，因此既有 SSE 客户端和回放协议保持兼容。

### 2. 运营阶段摘要

对于 MULTI_AGENT Run，Harness 根据用户可见请求识别明确的研究标记，并发布以下安全事件序列：

```text
phase_started
research_started
research_completed
content_generation_started
content_generation_completed
quality_checked
deliverable
stream_done
```

不需要研究时跳过研究阶段，直接进入内容生成阶段。每个阶段事件最多包含 `phase`、`count`、`duration_ms`、`degraded` 和可选固定 `error_code`，不包含 Prompt、工具参数或模型原文。

### 3. 用户级错误

图执行异常继续统一映射为固定错误码和安全提示。测试使用包含 `rendered_prompt` 和模型原始响应字样的异常，验证事件中不包含这些内部信息。

## 变更文件

- `src/efficiency_platform_agent/contracts/stream_events.py`
- `src/efficiency_platform_agent/harness/service.py`
- `tests/api/test_operation_phase_events.py`
- `docs/superpowers/sdd/operation-hybrid-upgrade/task-4-report.md`

`src/efficiency_platform_agent/orchestration/builders/operation_runtime.py` 本次未修改。阶段事件属于统一 Harness 运行生命周期，集中在 Harness 发布可以覆盖真实 Graph 和测试 Graph，并避免在 Graph 状态中注入不可序列化的事件总线对象。

## 风险与后续建议

- 当前研究阶段判断使用用户输入中的有限研究词表。Task 2/Task 3 完成后，可优先读取已落地的 `requires_research` 任务标志；词表只作为兼容兜底。
- 阶段耗时目前覆盖统一 Graph 执行窗口，不能细分 Supervisor 内部每个 Specialist 的精确耗时；如后续需要精确子阶段耗时，应由 Supervisor 通过受控事件端口发布摘要，仍不得暴露内部数据。
- 本报告只覆盖离线 SSE 和错误脱敏验证，真实 DeepSeek Web Search 验收属于 Task 5，不在本任务内宣称完成。
