# Agent 关键执行与错误日志：Task 3 实施报告

| 属性 | 内容 |
| --- | --- |
| 状态 | 已完成（Task 3 范围） |
| 负责人 | Agent 实施任务 3 |
| 更新时间 | 2026-09-08 |
| 适用范围 | ModelRuntime、Harness、GraphRuntime 的受控诊断 |
| 关联设计 | `docs/superpowers/specs/2026-09-08-Agent关键执行与错误日志-设计.md` 第 4、5.3、5.5 节 |
| 关联计划 | `docs/superpowers/plans/2026-09-08-Agent关键执行与错误日志-实施计划.md` Task 3 |

## 实施结果

- 三个构造器均新增可选关键字参数 `diagnostic_recorder`；未提供时使用 `NoopDiagnosticRecorder`，原有公开业务方法签名和行为保持不变。
- `ModelRuntime.complete()` 与 `stream_complete()` 在候选调用边界记录开始、成功、失败及降级选择；记录仅含 Provider、逻辑模型、attempt、稳定错误码、异常类型、安全位置、可重试性、非负耗时和明确返回的输入/输出 Token。
- Harness 在后台 Pipeline 和排队 Graph 路径绑定 `run_id`、`request_id`；策略确定后嵌套绑定 `strategy`。Pipeline、后台和图执行吞异常边界先记录白名单事实，再沿用原有安全归一化结果。
- `GraphRuntime.execute()` 与 `resume()` 对未处理异常记录 `graph_execution_failed`，保留原有安全失败结果。
- Recorder 调用本身被隔离；不读取、记录或渲染消息、options、模型输出、异常字符串或配置值。

## RED 证据

执行命令：

```powershell
uv run pytest tests/unit/capabilities/test_model_runtime.py tests/unit/harness/test_harness_service.py tests/unit/orchestration/test_graph_runtime.py -q
```

结果：`3 failed, 16 passed`，三项新增测试均因三个构造器尚不接受 `diagnostic_recorder` 失败：

- `ModelRuntime.__init__()`：unexpected keyword argument `diagnostic_recorder`；
- `AgentRuntimeService.__init__()`：unexpected keyword argument `diagnostic_recorder`；
- `GraphRuntime.__init__()`：unexpected keyword argument `diagnostic_recorder`。

失败原因符合预期：诊断注入和对应记录尚未实现，而非测试拼写或环境故障。

## GREEN 与验证证据

执行命令：

```powershell
uv run pytest tests/unit/capabilities/test_model_runtime.py tests/unit/harness/test_harness_service.py tests/unit/orchestration/test_graph_runtime.py -q
uv run ruff check src/efficiency_platform_agent/capabilities/model/runtime.py src/efficiency_platform_agent/harness/service.py src/efficiency_platform_agent/orchestration/runtime.py tests/unit/capabilities/test_model_runtime.py tests/unit/harness/test_harness_service.py tests/unit/orchestration/test_graph_runtime.py
uv run mypy src/efficiency_platform_agent/capabilities/model/runtime.py src/efficiency_platform_agent/harness/service.py src/efficiency_platform_agent/orchestration/runtime.py
uv run python -m compileall -q src/efficiency_platform_agent/capabilities/model/runtime.py src/efficiency_platform_agent/harness/service.py src/efficiency_platform_agent/orchestration/runtime.py tests/unit/capabilities/test_model_runtime.py tests/unit/harness/test_harness_service.py tests/unit/orchestration/test_graph_runtime.py
```

结果：

- `19 passed in 0.45s`；
- Ruff：`All checks passed!`；
- Mypy：`Success: no issues found in 3 source files`；
- `compileall`：退出码 0、无输出。

新增测试覆盖模型首次候选失败后的降级与成功用量、请求正文和 options 脱敏、后台 Pipeline 异常的 Run 关联与上下文恢复、Graph 未处理异常的安全位置与安全终态。

## 未验证边界

- 未运行 Task 4 的全项目回归、架构/文档治理门禁或真实联网研究验证；这些不属于 Task 3 文件所有权。
- 未改动 `local_real_factory.py`、Research Provider、`.env` 或任何 Git 状态。
