# S4 Task 4 Specialist 选择与安全派发实施报告

## 状态

已完成离线选择、上下文裁剪、预算约束派发和基础结果解码；未进行真实 Specialist、模型、网络、数据库、Redis、COS 或生产并发验收。

## 交付内容

- `selection.py`：
  - 通过 `AgentRegistry.match(..., kind=AgentKind.SPECIALIST)` 获取注册元数据；
  - 在 AgentFactory 创建前执行任务类型、能力、输入/输出 Schema、权限、工具和最小执行预算六项硬过滤；
  - 按额外能力、权限、工具、声明费用和 `agent_id` 稳定排序；
  - `ContextProjector` 仅投影已声明 Profile 引用和来源范围，缺失引用或范围立即失败关闭。
- `dispatch.py`：
  - 使用 `BudgetLedger.budget_for` 逐字段收紧子预算；
  - 构造 S1 `SupervisorTask` 与 S4 `TaskDispatch`，不把 Registry、Factory 或父上下文注入 Specialist；
  - `SpecialistResultDecoder` 校验版本化结果信封、不可变范围、能力请求和自报用量；自报用量只形成 `SPECIALIST_USAGE_IGNORED`，不写预算账本；
  - 对 S3 `EvidencePack` 的 `records/supports` 执行字段严格校验和无损解码。
- `tests/support/supervisor_fakes.py`：只提供合成 Specialist 注册和 TaskNode，不访问外部系统。
- `dispatch.py`：对 `DeliverableBundle`、`OperationQualityReport` 及其嵌套值对象执行结构化解码，字段不完整或类型不符时统一失败关闭。

## RED

命令：

```text
$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.agents.operation.supervisor.test_selection tests.unit.agents.operation.supervisor.test_dispatch -v
```

结果：退出码 1；初次因 `selection.py`/`dispatch.py` 不存在而导入失败。

## GREEN 与静态门禁

- `uv run python -m unittest tests.unit.agents.operation.supervisor.test_selection tests.unit.agents.operation.supervisor.test_dispatch -v`：退出码 0，4 项测试通过。
- `uv run ruff check src/efficiency_platform_agent/agents/operation/supervisor tests/unit/agents/operation/supervisor tests/support/supervisor_fakes.py`：退出码 0。
- `uv run mypy src/efficiency_platform_agent/agents/operation/supervisor tests/unit/agents/operation/supervisor tests/support/supervisor_fakes.py`：退出码 0。
- `uv run python -m compileall -q src/efficiency_platform_agent/agents/operation/supervisor`：退出码 0。
- S4 Task 1～4 联合回归：`uv run python -m unittest tests.unit.agents.operation.supervisor.test_selection tests.unit.agents.operation.supervisor.test_dispatch tests.unit.agents.operation.supervisor.test_planning tests.unit.agents.operation.supervisor.test_budget -v`，退出码 0，22 项测试通过。

## 未验证与后续边界

- 当前已实现 EvidencePack、DeliverableBundle 和 OperationQualityReport 的结构化离线解码；未执行业务质量判断或 Artifact 写入。
- 未执行候选装配失败后的切换事件、并发调度、取消、恢复、部分失败聚合和 LangGraph Builder；这些属于后续 S4 任务。
- 未连接真实注册中心、Specialist、模型、Provider、网络或持久化；不能据此宣称生产可用。
