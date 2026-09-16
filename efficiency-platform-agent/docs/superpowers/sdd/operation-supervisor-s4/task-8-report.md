# S4 Task 8 实施报告：多 Agent 架构治理守卫

## 实施范围

本次落地可离线执行的架构守卫和代表性 Supervisor 验收测试，覆盖 Specialist peer-to-peer 目录边界、AgentRegistry/AgentFactory 引用方向、策略层第二运行时与 LangGraph 禁止规则、LangGraph 唯一入口、S4 生产代码外部 I/O/厂商 SDK 禁止规则，以及选择、预算、派发、有界波次调度和预计算计划拒绝闭环。未修改 S2、S3 或 S4 生产代码，未引入第三方依赖。

## RED 证据

命令：`$env:PYTHONPATH='src'; uv run python -m unittest tests.architecture.test_multi_agent_governance -v`

结果：退出码 1；初始守卫发现基础 `agents/factory.py` 对 `agents/registry.py` 的内部实现引用，测试规则未区分框架根实现与调度层引用。

## GREEN 证据

修正守卫规则后执行：

`$env:PYTHONPATH='src'; uv run python -m unittest tests.architecture.test_multi_agent_governance -v`

结果：退出码 0，5 项测试通过。

代表性离线验收：

`$env:PYTHONPATH='src'; uv run python -m unittest tests.architecture.test_multi_agent_governance tests.acceptance.test_operation_supervisor -v`

结果：退出码 0，9 项测试通过（5 项架构守卫、4 项代表性验收）。覆盖合成 Specialist 单波次成功、预计算计划载荷在 Supervisor 节点前拒绝、S3 三端口到 assembly 的 GraphRuntime 闭环，以及单一 Graph Runtime 策略边界。

全量回归（当时交付证据）：

`$env:PYTHONPATH='src'; uv run pytest -q`

结果：退出码 0，296 passed、243 个子测试通过；仅有 1 个第三方依赖弃用警告。后续阶段新增测试后的最新全量结果以 S7 G0 报告为准。

静态门禁：

- `uv run ruff check tests/architecture/test_multi_agent_governance.py`：退出码 0。
- `uv run ruff format --check tests/architecture/test_multi_agent_governance.py tests/acceptance/test_operation_supervisor.py`：退出码 0。
- `uv run mypy src/efficiency_platform_agent`：退出码 0。
- `uv run python -m compileall -q src tests`：退出码 0。

## 文件清单

- 新建 `tests/architecture/test_multi_agent_governance.py`
- 新建 `tests/acceptance/__init__.py`、`tests/acceptance/test_operation_supervisor.py`
- 新建本报告与实施前快照
- 更新 `进度账本.md` 的 Task 8 状态为“已完成（离线，真实边界待验收）”

## 未验证边界

本次验收使用 S2 GraphRuntime 的离线实现和合成 Fake；真实 S3 Specialist、LangGraph 跨进程持久检查点、生产等待恢复顺序、生产取消唤醒或外部系统仍未验收，因此不代表生产端到端验收完成。
