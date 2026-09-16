# S6 Task 4 实施报告：24 个固定样本与 Fake

## 实施范围

在 `tests/support` 中新增 8 个场景各 3 种结果状态的固定样本与脚本化 Fake，生产代码不依赖样本、期望状态或 Fake。样本只能通过 `submission_from_sample` 去除全部 `expected_*` 字段后转换为 `ScenarioSubmission`。

## RED/GREEN 证据

GREEN 命令：

`$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.operation.scenarios.test_samples -v`

结果：退出码 0，2 项测试通过，覆盖 24 个样本、三种状态覆盖和转换字段隔离。

## 文件清单

- `tests/support/s6_scenario_samples.py`
- `tests/support/s6_scenario_fakes.py`
- `tests/unit/operation/scenarios/test_samples.py`

## 未验证边界

样本与 Fake 仅用于离线契约测试，不代表真实 Specialist、模型质量、网络检索、数据源、数据库、平台规则或外部副作用已验证。
