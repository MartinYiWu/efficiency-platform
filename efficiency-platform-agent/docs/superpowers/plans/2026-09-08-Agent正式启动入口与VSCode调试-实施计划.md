# Agent 正式启动入口与 VSCode 调试实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供标准 Python Agent 启动入口、VSCode F5 调试体验和安全的本地 Run 执行日志。

**Architecture:** 正式入口位于包内，既有脚本只作兼容转发；Harness 通过受控监听口发布已治理 Run 事件，本地组合根注册终端日志监听器。VSCode 仅负责解释器、pytest 发现和启动参数，不持有任何敏感配置。

**Tech Stack:** Python 3.13、uv、FastAPI、Uvicorn、标准库 logging、pytest、VSCode Python/Debugpy。

## 全局约束

- 项目永久非 Git；不得执行或要求 Git 操作。
- 所有新增 Python 注释、Docstring 与 JSONC 配置注释使用中文。
- 日志不得输出用户正文、Prompt、模型完整输出、密钥、Authorization、连接串、异常正文或 traceback。
- 不引入监控平台、日志采集 SDK、Trace、Metric 或外部基础设施。
- 真实外部 Gate 默认关闭；测试不得调用真实模型。

---

### Task 1：正式应用入口与兼容脚本

**Files:**
- Create: `src/efficiency_platform_agent/main.py`
- Create: `src/efficiency_platform_agent/__main__.py`
- Modify: `scripts/local_agent_server.py`
- Test: `tests/unit/test_application_entry.py`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> None`
- Produces: `parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace`
- Consumes: `build_local_agent_application(env_file: str | Path) -> LocalAgentApplication`

- [x] **Step 1: 编写失败测试。** 断言参数默认值为 `.env`、`127.0.0.1`、`8080`；断言 `main()` 用解析后的参数调用组合根和 `uvicorn.run`，不读取 `.env` 内容。

- [x] **Step 2: 运行失败测试。**

Run: `uv run pytest tests/unit/test_application_entry.py -q`

Expected: 因 `efficiency_platform_agent.main` 不存在而失败。

- [x] **Step 3: 最小实现。** 创建包内 `main.py` 和 `__main__.py`，让脚本入口只转调 `main()`。

- [x] **Step 4: 运行通过测试。**

Run: `uv run pytest tests/unit/test_application_entry.py -q`

Expected: PASS。

### Task 2：受控本地执行日志

**Files:**
- Create: `src/efficiency_platform_agent/observability/local_execution_log.py`
- Modify: `src/efficiency_platform_agent/harness/service.py`
- Modify: `src/efficiency_platform_agent/harness/local_real_factory.py`
- Test: `tests/unit/observability/test_local_execution_log.py`
- Test: `tests/unit/harness/test_harness_service.py`

**Interfaces:**
- Produces: `LocalExecutionLogger.on_run_event(event: RunEventRecord) -> Awaitable[None]`
- Produces: `LocalExecutionLogger.on_run_state(view: RunViewV1) -> Awaitable[None]`
- Produces: `AgentRuntimeService.add_run_event_listener(listener) -> None`

- [x] **Step 1: 编写失败测试。** 断言监听器按写入顺序收到 Run 事件；断言终态日志含 Run 标识、状态、策略、降级标记和 Token 汇总；断言敏感文本不进入日志；断言监听器抛错不改变 Run 结果。

- [x] **Step 2: 运行失败测试。**

Run: `uv run pytest tests/unit/observability/test_local_execution_log.py tests/unit/harness/test_harness_service.py -q`

Expected: 因监听器与日志实现不存在而失败。

- [x] **Step 3: 最小实现。** 在 Harness 事件落库后通知监听器；真实组合根注册 `LocalExecutionLogger`；日志使用 `logging` 输出集成终端。

- [x] **Step 4: 运行通过测试。**

Run: `uv run pytest tests/unit/observability/test_local_execution_log.py tests/unit/harness/test_harness_service.py -q`

Expected: PASS。

### Task 3：VSCode 测试与 F5 调试配置

**Files:**
- Create: `.vscode/settings.json`
- Create: `.vscode/launch.json`
- Modify: `README.md`
- Test: `tests/governance/test_vscode_debug_configuration.py`

**Interfaces:**
- Produces: VSCode pytest 发现范围 `tests`
- Produces: VSCode F5 模块启动配置 `efficiency_platform_agent`

- [x] **Step 1: 编写失败测试。** 断言 settings 启用 pytest、关闭 unittest、指定 `tests`，且 launch 配置包含 Agent 启动与当前 pytest 文件调试项，并使用 `integratedTerminal`。

- [x] **Step 2: 运行失败测试。**

Run: `uv run pytest tests/governance/test_vscode_debug_configuration.py -q`

Expected: 因 `.vscode` 配置不存在而失败。

- [x] **Step 3: 最小实现。** 创建不含密钥的 JSONC 配置，README 增加 VSCode 启动、测试调试和停止方法。

- [x] **Step 4: 运行通过测试。**

Run: `uv run pytest tests/governance/test_vscode_debug_configuration.py -q`

Expected: PASS。

### Task 4：整体验证与交付记录

**Files:**
- Modify: `docs/superpowers/plans/2026-09-08-Agent正式启动入口与VSCode调试-实施计划.md`
- Modify: `docs/superpowers/progress/2026-09-08-Agent正式启动入口与VSCode调试-进度.md`

- [x] **Step 1: 运行聚焦回归。**

Run: `uv run pytest tests/unit/test_application_entry.py tests/unit/observability/test_local_execution_log.py tests/unit/harness/test_harness_service.py tests/governance/test_vscode_debug_configuration.py -q`

Expected: PASS。

- [x] **Step 2: 运行静态门禁。**

Run: `uv run ruff check src tests scripts && uv run mypy src && uv run python -m compileall -q src tests scripts`

Expected: 全部通过。

- [x] **Step 3: 运行应用入口帮助验证。**

Run: `uv run python -m efficiency_platform_agent --help`

Expected: 输出 `--env-file`、`--host`、`--port`，不包含 `.env` 值。

- [x] **Step 4: 更新进度记录。** 记录命令、结果、未验证的真实模型调用和 VSCode 人工 F5 验收边界。
