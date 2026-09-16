# Agent 正式启动入口与 VSCode 调试设计

| 属性 | 内容 |
|---|---|
| 状态 | 已批准，待实施 |
| 负责人 | Agent 平台架构负责人 |
| 创建日期 | 2026-09-08 |
| 适用范围 | 纯 Agent 本地开发启动、VSCode 调试与终端执行日志 |
| 不在范围 | 监控平台、日志采集服务、Trace、Metric、告警、部署、Java 侧改动 |

## 1. 目标

提供与 Java `Application.main()` 等价的 Python 应用启动入口，使开发者在 VSCode 按 F5 即可启动真实本地 Agent API，并在集成终端查看安全的 Run 执行日志。

`Debug Tests` 只用于 pytest 测试函数，不承担启动真实服务的职责；真实服务必须通过“启动：本地真实 Agent API”调试配置运行。

## 2. 设计

新增 `src/efficiency_platform_agent/main.py` 作为唯一正式启动入口。它只负责解析 `--env-file`、`--host`、`--port` 参数，调用既有 `build_local_agent_application()`，再以 Uvicorn 启动 FastAPI；不得包含业务编排、模型调用逻辑或密钥输出。

新增 `src/efficiency_platform_agent/__main__.py`，仅调用 `main()`，使命令 `uv run python -m efficiency_platform_agent` 成为稳定启动方式。既有 `scripts/local_agent_server.py` 改为兼容薄包装，转调正式入口，避免已有脚本命令失效。

新增 `observability/local_execution_log.py`。该组件只使用标准库 `logging` 输出开发终端日志，接收已治理的 Run 生命周期事件和终态视图，禁止记录用户原文、Prompt、模型完整输出、Authorization、API Key、连接串或异常堆栈。输出字段限于 `run_id`、`request_id`、事件类型、Run 状态、策略、错误码、降级标记和 Token 汇总。

`AgentRuntimeService` 新增受控 Run 事件监听器注册口。事件写入既有事件仓后通知监听器；监听器异常被吞并且不得影响 Run 生命周期。真实组合根注册本地执行日志监听器，测试组合根不隐式启用。

## 3. VSCode 体验

新增 `.vscode/settings.json`，固定项目 `.venv\\Scripts\\python.exe`、启用 pytest、关闭 unittest 测试发现，并将 pytest 发现范围收敛为 `tests`。新增 `.vscode/launch.json`：

- `启动：本地真实 Agent API`：以模块方式运行 `efficiency_platform_agent`，日志输出到集成终端；
- `调试：当前 pytest 测试文件`：以 pytest 调试当前 `test_*.py` 文件；
- `调试：Agent 全量离线测试`：只运行 `-m not real_external`，不触发真实外部 Gate。

配置中不写入 `.env` 值、密钥或真实连接串；JSONC 中所有注释使用中文。

## 4. 日志边界与示例

本地终端日志采用一行一事件的可读文本，例如：

```text
INFO [AgentRun] 事件=run_created run_id=运行标识 request_id=请求标识 状态=created
INFO [AgentRun] 事件=strategy_selected run_id=运行标识 状态=queued
INFO [AgentRun] 事件=run_succeeded run_id=运行标识 状态=succeeded 策略=multi_agent 降级=false 输入Token=输入令牌数 输出Token=输出令牌数
```

日志不是 SSE 返回正文的镜像，也不是审计、指标或监控平台。失败时只输出稳定错误码，不输出异常正文和 traceback。

## 5. 验收标准

1. `uv run python -m efficiency_platform_agent --help` 正常返回帮助，且不会读取或输出密钥值。
2. `scripts/local_agent_server.py` 仍可启动同一正式入口。
3. 受控 Run 事件能够被本地日志监听器接收；监听器失败不影响 Run。
4. 日志不包含用户输入、Prompt、密钥、Bearer、`sk-`、连接串或 traceback。
5. VSCode pytest 配置可从项目根发现 `tests`；当前测试文件可断点调试。
6. VSCode F5 启动项使用 `integratedTerminal`，并能显示 Uvicorn 与 Agent Run 日志。
