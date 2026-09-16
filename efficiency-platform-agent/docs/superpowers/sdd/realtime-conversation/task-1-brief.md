# Task 1 任务简报：真实模型流式执行结果

## 目标

在不改变 Provider 稳定端口和既有 `complete()` 行为的前提下，为 `ModelRuntime` 提供一个“实时交付 delta，结束后返回完整 `ModelExecutionResult`”的入口。

## 文件所有权

- 可修改：`src/efficiency_platform_agent/capabilities/model/runtime.py`
- 仅确有必要才修改：`src/efficiency_platform_agent/core/model.py`
- 可修改测试：`tests/unit/capabilities/model/test_runtime.py`、`tests/acceptance/test_model_degradation.py`
- 不得修改 `general_agent.py`、Harness、ConversationService 或前端文件。

## 必须满足

- 先写失败测试并实际确认按预期失败，再写生产代码。
- 调用方在 Provider 尚未完成时即可收到首个非空 delta。
- 流结束后返回完整正文、Usage、attempts 和 degraded。
- 首个可见 delta 前的可重试错误允许降级；首个可见 delta 后禁止切换候选拼接另一答案。
- 取消后不再交付 delta，也不调用新候选。
- Usage 使用最终快照/每候选最大值，不按 chunk 重复累计。
- 所有新注释和 Docstring 使用中文。
- 不读取 `.env`，不运行 Git，不启动常驻服务。

## 验证

至少运行：

```powershell
uv run pytest tests/unit/capabilities/model/test_runtime.py tests/acceptance/test_model_degradation.py -q
uv run ruff check src/efficiency_platform_agent/capabilities/model/runtime.py tests/unit/capabilities/model/test_runtime.py tests/acceptance/test_model_degradation.py
```

把 RED 命令/失败原因、GREEN 命令/结果、修改文件、自查结论写入 `task-1-report.md`。
