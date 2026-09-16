# Task 2 Research Provider 与能力装配诊断报告

| 属性 | 内容 |
|---|---|
| 状态 | 已完成本 Task 2 范围内实现与目标验证 |
| 负责人 | Research Provider 与能力装配子任务 |
| 更新时间 | 2026-09-08 |
| 适用范围 | `deepseek_web_search.py`、`operation_agent_factory.py`、`local_real_factory.py` 及对应单元测试 |
| 非目标 | 不修改 ModelRuntime、Harness service、GraphRuntime，不读取或写入 `.env`，不执行 Git 操作 |

## 已完成证据

### Research Provider RED

命令：

```powershell
uv run pytest tests/unit/capabilities/test_research_provider.py -q
```

结果：退出码 `1`，新增测试因 `DeepSeekWebSearchProvider.__init__()` 不接受 `recorder` 参数失败。失败原因与预期一致，证明新增分类诊断行为在实现前不存在。

### Research Provider GREEN

命令：

```powershell
uv run pytest tests/unit/capabilities/test_research_provider.py -q
```

结果：退出码 `0`，`6 passed, 8 subtests passed`。

已验证行为：

- 每一次实际 `responses.create` 尝试只调用一次并生成本地 `provider_call_id`；未新增自动重试。
- 401/403、404、408/超时、429、5xx 和其他异常分类为稳定内部错误码；对上仍返回 `RESEARCH_UNAVAILABLE`。
- 客户端缺少 `responses.create` 记录 `RESEARCH_RESPONSES_UNSUPPORTED`，但不会生成伪造调用标识。
- 成功和证据不足只输出有效/拒绝来源计数；不会把 Prompt、异常正文、Key、响应体、URL、标题或发布者放入 `DiagnosticRecord`。
- 耗时使用 `time.monotonic_ns()` 计算，结果为非负毫秒。

## 组合根 RED/GREEN

RED 命令：

```powershell
uv run pytest tests/unit/harness/test_local_real_factory.py -q
```

共享的 `harness/service.py` 恢复可导入后，退出码 `1`，新增两项断言均因组合根没有调用 `log_capability()` 而失败；既有测试 `11 passed`。失败原因与预期一致。

GREEN 命令：

```powershell
uv run pytest tests/unit/capabilities/test_research_provider.py tests/unit/harness/test_local_real_factory.py -q
```

结果：退出码 `0`，`19 passed, 8 subtests passed`。

已验证行为：

- 非测试组合根只创建一个 `LocalExecutionLogger`。
- Gate 关闭时输出 `capability_disabled / RESEARCH_GATE_DISABLED`；Gate 开启并完成 Provider 装配时输出 `capability_ready`。
- 组合根把唯一 Recorder 注入 `DeepSeekWebSearchProvider`；测试模式默认使用 `NoopDiagnosticRecorder`，未把 logger 注入 ModelRuntime、GraphRuntime 或 Harness service。
- `_UnavailableResearchProvider` 在实际研究请求到达时记录 `RESEARCH_GATE_DISABLED` 或 `RESEARCH_PROVIDER_NOT_CONFIGURED`，但对上仍保留 `RESEARCH_UNAVAILABLE`。

## 本任务范围内静态验证

命令：

```powershell
uv run ruff check src/efficiency_platform_agent/capabilities/research/deepseek_web_search.py src/efficiency_platform_agent/harness/operation_agent_factory.py src/efficiency_platform_agent/harness/local_real_factory.py tests/unit/capabilities/test_research_provider.py tests/unit/harness/test_local_real_factory.py
uv run python -m compileall -q src/efficiency_platform_agent/capabilities/research/deepseek_web_search.py src/efficiency_platform_agent/harness/operation_agent_factory.py src/efficiency_platform_agent/harness/local_real_factory.py tests/unit/capabilities/test_research_provider.py tests/unit/harness/test_local_real_factory.py
```

结果：两个命令均退出码 `0`；Ruff 输出 `All checks passed!`，源码编译无输出。

## 与 Task 1 的联合目标回归

命令：

```powershell
uv run pytest tests/unit/core/test_diagnostics.py tests/unit/observability/test_local_execution_log.py tests/unit/capabilities/test_research_provider.py tests/unit/harness/test_local_real_factory.py -q
```

结果：本次追加装配后的新鲜运行退出码 `0`，`68 passed, 8 subtests passed`。组合根的日志测试替身已按 Task 1 职责补齐能力状态接口后，本 Task 2 的能力状态装配与原有本地日志契约可共同通过。

## 追加：统一 Recorder 注入

新增身份 RED 命令：

```powershell
uv run pytest tests/unit/harness/test_local_real_factory.py -q
```

结果：退出码 `1`，两项新增断言失败。真实组合根的 `ModelRuntime` 使用了独立 `NoopDiagnosticRecorder`，测试模式下 ModelRuntime、GraphRuntime 与 Harness 也各自创建 Noop 实例，证明尚未形成统一 Recorder。

最小 GREEN：组合根继续只创建一个 `execution_logger`；将该对象依次传入 `ModelRuntime`、`GraphRuntime`、`AgentRuntimeService`，并保持已有 Research Provider 注入。测试模式复用同一个 `NoopDiagnosticRecorder`，不会创建 `LocalExecutionLogger`。

GREEN 命令：

```powershell
uv run pytest tests/unit/harness/test_local_real_factory.py -q
uv run ruff check src/efficiency_platform_agent/harness/local_real_factory.py tests/unit/harness/test_local_real_factory.py
uv run python -m compileall -q src/efficiency_platform_agent/harness/local_real_factory.py tests/unit/harness/test_local_real_factory.py
```

结果：三个命令均退出码 `0`；`15 passed`，Ruff 输出 `All checks passed!`，源码编译无输出。

## 未验证边界

- 全项目回归、架构门禁、全项目 Ruff/mypy/源码编译及真实联网失败日志属于后续整合任务，尚未在本子任务中声明通过。
