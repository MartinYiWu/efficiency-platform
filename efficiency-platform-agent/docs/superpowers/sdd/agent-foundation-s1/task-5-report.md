# S1 Task 5 契约测试任务报告

| 属性 | 内容 |
|---|---|
| 状态 | 已完成（离线契约测试已实现；全量测试存在既有环境失败） |
| 适用范围 | S1 AgentSpec、AgentPlugin、Registry、Factory 与 SupervisorTask 的准入契约 |
| 更新时间 | 2026-09-03 |
| 外部依赖 | 零：仅使用 Python 标准库、项目源码和合成测试数据 |

## 实际变更文件

- `tests/contract/__init__.py`
- `tests/contract/agents/__init__.py`
- `tests/contract/agents/test_agent_plugin_contract.py`
- `docs/superpowers/sdd/agent-foundation-s1/task-5-report.md`

契约测试覆盖显式注册、能力匹配、Factory 装配、结构化 `SupervisorTask` 输入、异步插件执行和结构化 `RunResult` 输出。测试使用 `tests.support.agent_fakes` 的确定性合成 Specialist，不包含真实账号、URL、连接串、Prompt 或业务数据。

## 测试证据

### 新增契约测试

命令：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest tests.contract.agents.test_agent_plugin_contract -v
```

结果：`Ran 1 test in 0.036s`，`OK`；PowerShell 实测总耗时约 `0.375s`。

按任务简报原始命令（未设置源码路径）运行时因当前仓库未安装 `src` 包而出现 `ModuleNotFoundError`；这不是契约失败。使用仅指向本地源码的 `PYTHONPATH=src` 后通过，未安装或访问任何外部服务。

### 全量测试

命令：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest discover -s tests -p "test_*.py" -v
```

结果：共 `75` 项，新增契约测试通过；`74` 项通过，`1` 项失败，耗时约 `0.883s`（PowerShell 实测约 `1.303s`）。唯一失败为既有 `config.test_llm_configuration_template.LlmConfigurationTemplateTest.test_local_env_deepseek_public_state_matches_when_present`，原因是本机 `.env` 的 DeepSeek 公开状态不符合该既有测试预期；本任务未修改 `.env` 或生产实现。

### 源码编译与外部依赖自检

命令：

```powershell
uv run python -m compileall -q src tests
```

结果：`COMPILE_EXIT=0`。

对新增契约测试及其合成 Fake 的导入扫描结果：`CONTRACT_SUPPORT_EXTERNAL_IMPORTS=NONE`。测试执行路径未初始化网络、数据库、Redis、COS、模型客户端或真实配置连接。

## 自检与顾虑

- 未改动 `src/` 生产实现；Factory 边界保持既有只归一化 `AgentDefinitionError` 的约定。
- 新增包文件和测试代码中的注释、Docstring 使用中文；测试结果使用标准库 `unittest.IsolatedAsyncioTestCase`。
- 当前全量测试不能宣称全绿，需由维护者另行处理本机 `.env` 状态与既有配置测试的环境一致性。
- 本报告只证明 S1 离线契约，不证明业务 Agent、真实 Provider、基础设施连接或生产可用性。

## 审查修复：RunResult 类型准入

审查指出原测试只访问 `status`、`run_id` 和 `output` 属性，未证明插件返回值确为结构化 `RunResult`。本次仅修改 `tests/contract/agents/test_agent_plugin_contract.py`：导入 `RunResult` 与 `StrategyMode`，新增 `assertIsInstance(result, RunResult)`，并断言策略为 `StrategyMode.MULTI_AGENT`；未修改生产实现。

### RED

为验证类型断言确实具备捕获能力，先临时加入刻意错误的 `assertIsInstance(result, str)`，运行：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest tests.contract.agents.test_agent_plugin_contract -v
```

结果：`Ran 1 test in 0.043s`，失败；实际返回值显示为 `RunResult(...)`，并报告其不是 `str`。该临时错误断言随后已替换，不保留在最终文件中。

### GREEN

替换为 `assertIsInstance(result, RunResult)` 并加入策略断言后，运行同一命令：`Ran 1 test in 0.035s`，`OK`（PowerShell 实测约 `0.371s`）。

结论：契约测试现在同时验证结构化结果的运行时类型、成功状态、关联 Run ID、Multi-Agent 策略和结构化输出；仍保持零外部依赖和纯合成数据边界。
