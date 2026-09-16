# Agent 正式启动入口与 VSCode 调试进度

## 状态

已完成代码、配置、独立审查和离线验证。该结论仅覆盖本地开发启动与调试体验，不代表生产部署或真实模型可用性验收。

## 已交付

- 包内正式入口：`efficiency_platform_agent.main:main`。
- 模块启动方式：`uv run python -m efficiency_platform_agent`。
- 兼容入口：`scripts/local_agent_server.py` 转调包内正式入口。
- VSCode 项目解释器、pytest 发现范围与 F5 调试配置。
- 真实组合根注册的本地终端运行日志；日志只输出已治理的运行标识、状态、策略、降级标记、错误码和 Token 汇总。
- 事件或状态日志监听器发生异常时，不会改变 Run 执行结果。

## 验证证据

```text
uv run pytest tests/unit/test_application_entry.py tests/unit/observability/test_local_execution_log.py tests/unit/harness/test_harness_service.py tests/governance/test_vscode_debug_configuration.py -q
16 passed

uv run pytest -m "not real_external" -q
754 passed，2 warnings，266 subtests passed

uv run ruff check src tests scripts
All checks passed

uv run mypy src
Success: no issues found in 197 source files

uv run python -m compileall -q src tests scripts
通过

uv run python -m efficiency_platform_agent --help
包含 --env-file、--host、--port
```

## 人工验收边界

- 未在本轮启动真实 Agent 服务，因此未调用 DeepSeek，也未读取或输出 `.env` 的密钥值。
- 未在 VSCode 图形界面实际按 F5；配置文件和配置治理测试已验证。人工验收时，必须以 `D:\efficiency-platform\efficiency-platform-agent` 为 VSCode 工作区根目录，选择“启动：本地真实 Agent API”。
- 启动后的运行日志应在 VSCode 集成终端显示；停止服务使用终端 `Ctrl+C` 或 VSCode 停止调试。
