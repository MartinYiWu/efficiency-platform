# S6 Task 3 实施报告：显式场景 Manifest Registry

## 实施范围

新增八个 `scenario-pack/1`、`1.0.0` 场景 Manifest、S3 模板步骤声明和内存 Registry。每个步骤的能力均从 S5 `OperationSpecialistCapabilityId` 枚举读取；没有 Agent 类名、发布 Tool、Provider 参数、网络地址或执行逻辑。

## RED/GREEN 证据

初始 RED：Registry、Manifest 模块和测试文件不存在，目标测试无法导入。

GREEN 命令：

`$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.operation.scenarios.test_registry -v`

结果：退出码 0，4 项测试通过，覆盖八个版本、稳定排序、S5 capability 目录一致性、重复注册拒绝、显式版本查找和多平台三步骤独立输出。

静态检查：本次相关源码和测试 Ruff、format、mypy、compileall 通过（S6 其他既有文件未纳入本次格式化范围）。

## 文件清单

- `src/efficiency_platform_agent/agents/operation/scenarios/__init__.py`
- `src/efficiency_platform_agent/agents/operation/scenarios/registry.py`
- `src/efficiency_platform_agent/agents/operation/scenarios/manifests.py`
- `tests/unit/operation/scenarios/__init__.py`
- `tests/unit/operation/scenarios/test_registry.py`

## 契约修正与未验证边界

S6 计划固定的质量检查 ID 使用 `q.xxx/1` 版本后缀，而 S3 原校验仅支持无斜杠稳定 ID。已做最小兼容修正：只对 `quality_check_ids` 放行稳定标识加数字主版本后缀，其他 ID 校验保持原规则；八个 Manifest 现与计划固定 ID 完全一致。尚未实现 ScenarioSubmission 服务、Supervisor 真实调度或外部系统验收。
