# S4 Task 2 计划编译实施报告

记录日期：2026-09-04

## 范围

本任务把 S3 `OperationPlan` 确定性编译为 S4 `TaskGraph`。编译器只消费 S3 计划、`SupervisorLimits` 和 core 任务图契约，不查询 Registry、不创建 Specialist、不执行 Graph，也不访问真实外部系统。

## 文件级结果

- 新增 `src/efficiency_platform_agent/agents/operation/supervisor/__init__.py`
- 新增 `src/efficiency_platform_agent/agents/operation/supervisor/errors.py`
- 新增 `src/efficiency_platform_agent/agents/operation/supervisor/planning.py`
- 新增 `tests/unit/agents/operation/__init__.py`
- 新增 `tests/unit/agents/operation/supervisor/__init__.py`
- 新增 `tests/unit/agents/operation/supervisor/test_planning.py`
- 新增 `docs/superpowers/sdd/operation-supervisor-s4/task-2-snapshot.md`

## TDD 证据

- RED：`uv run python -m unittest tests.unit.agents.operation.supervisor.test_planning -v`，退出码非零，原因是目标 `supervisor.errors` 模块不存在。
- GREEN：同一命令退出码 0，8 项测试通过。
- 静态检查：`uv run mypy src/efficiency_platform_agent/agents/operation/supervisor/planning.py src/efficiency_platform_agent/agents/operation/supervisor/errors.py` 退出码 0；并行 Task3 的 `budget.py` 当前存在独立类型错误，因此不将整个 supervisor 目录声明为通过。
- 编译检查：`uv run python -m compileall -q src/efficiency_platform_agent/agents/operation/supervisor` 退出码 0。
- 目标文件 Ruff：退出码 0。对包含其他并行任务文件的目录扫描时，另有 Task3 文件的提示，不属于本任务文件。

## 已实现门禁

- 稳定 Kahn 拓扑排序，同一层按步骤 ID 字典序排列。
- 缺失依赖、循环依赖、空计划、任务数量和 DAG 深度限制。
- 每步骤预算不超过计划总预算。
- `required` 与失败行为组合校验。
- 四种 S3 `FailureBehavior` 映射到 S4 `TaskFailureMode`。
- task type、Schema、能力、权限、工具、依赖、交付物和质量引用复制到冻结 `TaskNode`。

## 未验证边界

尚未验证真实 S2/S3 适配器、Registry/Factory、调度、LangGraph、模型、网络、数据库、Redis、COS、并行执行和生产运行行为。
