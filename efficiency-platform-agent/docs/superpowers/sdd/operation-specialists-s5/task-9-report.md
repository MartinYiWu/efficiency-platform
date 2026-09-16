# S5 Task 9 实施报告：显式注册与能力目录

## 实施内容

- `definition.py` 新增 `operation_capability_specs()`、`operation_agent_specs()` 和 `register_operation_specialists()`。
- 11 个 Specialist 使用唯一 `OperationSpecialistCapabilityId`，每个 AgentSpec 仅声明一个能力；预算、策略、任务类型、Prompt Bundle、Tool、权限、状态版本和 Checkpoint 版本按 S5 计划表固定。
- 研究 Specialist 使用 `WORKFLOW`、`synthetic_research` 和 `synthetic.read`；其余 Specialist 使用计划声明的策略及零外部权限。
- `specialists/__init__.py` 仅导出显式类，不执行注册副作用；注册函数通过显式 Builder 元组，不扫描目录、不动态导入、不按具体业务 ID 路由。
- 新增注册/能力目录集成测试，验证 11 个注册项、每项一个能力及能力唯一归属。

## RED/GREEN 证据

RED：注册函数不存在时，能力目录/注册测试无法导入目标符号；定义补齐后进入 GREEN。

GREEN：

```powershell
$env:PYTHONPATH='src'; uv run pytest tests.integration.agents.operation.test_specialist_dispatch tests.contract.agents.operation.test_specialist_contract tests.contract.agents.operation.test_s6_capability_catalog_contract -q
```

结果：退出码 0，5 项测试通过（2 项注册集成、1 项公共结果契约、2 项能力目录契约）。

静态验证：

```powershell
uv run ruff check src/efficiency_platform_agent/agents/operation/definition.py src/efficiency_platform_agent/agents/operation/specialists/__init__.py src/efficiency_platform_agent/agents/operation/specialists/_base.py tests/integration/agents/operation/test_specialist_dispatch.py
uv run ruff format --check src/efficiency_platform_agent/agents/operation/definition.py src/efficiency_platform_agent/agents/operation/specialists/__init__.py src/efficiency_platform_agent/agents/operation/specialists/_base.py tests/integration/agents/operation/test_specialist_dispatch.py
uv run python -m compileall -q src/efficiency_platform_agent/agents/operation tests/integration/agents/operation
```

结果：Ruff 检查、格式检查和 compileall 均退出码 0。

## 未验证边界

- 注册验证只使用离线 Fake 研究 Provider 和空分析 Reader，不调用真实模型、网络、数据库、缓存或平台接口。
- S4 真实调度、恢复、取消、持久化 Checkpoint、真实 Usage 和生产故障切换未验证。
- Specialist 的业务质量、真实平台规则、外部发布和业务效果不属于本任务。
