# S4 Task 8 代表性验收测试草稿

记录时间：2026-09-04

## 已新增

- `tests/architecture/test_multi_agent_governance.py`：检查 LangGraph 唯一导入边界、框架中立策略层、S4 外部 I/O 禁止和 Specialist 禁止点对点依赖。
- `tests/acceptance/test_operation_supervisor.py`：使用合成 Specialist、S4 预算账本、选择器、派发器和有界调度器验证代表性单波次；验证预计算计划载荷在 Supervisor 节点前拒绝；确认 S4 计划编译器仍位于既有单 Graph Runtime 边界内。
- `tests/acceptance/__init__.py`：验收测试包声明。

## RED 结果与实际缺口

命令：

```text
$env:PYTHONPATH='src'; uv run python -m unittest tests.architecture.test_multi_agent_governance tests.acceptance.test_operation_supervisor -v
```

架构守卫 4 项通过；验收用例中有 2 项失败，均为真实接口缺口而非跳过：

1. 有效的 `operation_request` 中仍可携带预计算 `plan` 字段，当前解码节点没有在嵌套请求层拒绝该字段。
2. `BoundedScheduler` 将 `TaskDispatch` 传给 S1 `AgentPlugin.run(SupervisorTask)`，合成 Specialist 因接口类型不匹配返回 `SPECIALIST_FAILED`；应由后续 S4 任务修正派发调用边界或建立明确的适配器。

不得把当前验收草稿描述为 S4 端到端通过。后续修复上述缺口后，必须重新运行本命令，并补充等待/恢复、取消、可信用量、预算耗尽、候选切换、部分失败、EvidencePack 无损聚合及 16/4/8/1 上限验收；这些行为目前未被本草稿覆盖。

## 静态证据

- `uv run ruff check tests/architecture/test_multi_agent_governance.py tests/acceptance/test_operation_supervisor.py`：退出码 0。
- `uv run python -m compileall -q src tests/acceptance tests/architecture/test_multi_agent_governance.py`：退出码 0。

本测试只使用内存 Fake，不连接模型、Provider、网络、数据库、Redis、COS 或真实业务 Specialist。
