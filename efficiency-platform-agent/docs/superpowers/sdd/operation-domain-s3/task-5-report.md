# S3 Task 5 实施报告

## 范围

本任务仅建立声明性的 Scenario Pack Manifest、PlanTemplate/ScenarioStep、S2 三个窄 Protocol 和离线确定性 Fake。没有新增业务执行、Agent 调度、Graph、Provider、网络、数据库、文件或对象存储访问。

## 实施前快照

- `docs/superpowers/sdd/operation-domain-s3/task-5-snapshot.md`
- 快照确认四个目标文件在实施前均不存在。

## RED 证据

命令：`$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.operation.test_scenarios -v`

结果：退出码 1；测试模块因 `ClarificationPolicy` 尚未从 contracts 导出而导入失败，符合源码尚未实现时的预期失败。

## GREEN 证据

命令：`$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.operation.test_scenarios -v`

结果：退出码 0；6 项测试通过，覆盖不可变字段和版本校验、必需触发条件、未声明步骤输出、多步骤能力与依赖的一对一编译以及三个 Fake 端口。

静态检查：

- `uv run ruff check src/efficiency_platform_agent/agents/operation/contracts/scenarios.py src/efficiency_platform_agent/agents/operation/contracts/ports.py tests/unit/operation/test_scenarios.py tests/support/s2_operation_fakes.py`：退出码 0。
- `uv run mypy src/efficiency_platform_agent/agents/operation/contracts/scenarios.py src/efficiency_platform_agent/agents/operation/contracts/ports.py`：退出码 0。

## 文件清单

- 新建 `src/efficiency_platform_agent/agents/operation/contracts/scenarios.py`：版本化场景清单、模板、步骤、校验和确定性编译。
- 新建 `src/efficiency_platform_agent/agents/operation/contracts/ports.py`：三个 S2 `Protocol`，不提供生产实现。
- 新建 `tests/support/s2_operation_fakes.py`：只供测试使用的 S2 假端口与固定契约对象。
- 新建 `tests/unit/operation/test_scenarios.py`：Task 5 单元测试。
- 修改 `src/efficiency_platform_agent/agents/operation/contracts/__init__.py`：导出 Task 5 公开类型和端口。

## 未验证边界

Fake 不代表真实 S2 主链；场景编译不查询 Registry、不选择 Agent、不运行步骤。真实 LangGraph、模型、搜索、数据库、Artifact、业务 Specialist 和平台发布均未接入，留待后续阶段。
