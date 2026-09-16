# S6 Task 8 实施报告：后四个场景服务级回归

## 实施范围

补充 `campaign_plan`、`content_calendar`、`growth_experiment`、`operation_review` 四个场景的 `ScenarioPackService.run()` 服务级离线回归。测试通过固定 Manifest、S3 计划替身和脚本化 Supervisor，覆盖完整、等待、部分、数据不可用、平台 Profile 缺失、实验基线未验证、归因假设和无触达约束；未调用网络、模型、数据库、发送或交易接口。

## GREEN 证据

命令：

`$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.operation.scenarios.test_campaign_and_calendar tests.unit.operation.scenarios.test_growth_and_review -v`

结果：退出码 0，9 项测试通过。覆盖活动完整交付物（排期、任务板、风险、指标）、活动无触达、日历 Profile 缺失与等待、增长实验无数据部分结果、复盘不可读数据失败、复盘归因假设和等待，以及不完整 PARTIAL 结果的失败关闭。

静态检查：

- `uv run ruff format --check tests/unit/operation/scenarios/test_campaign_and_calendar.py tests/unit/operation/scenarios/test_growth_and_review.py`：通过。
- `uv run ruff check tests/unit/operation/scenarios/test_campaign_and_calendar.py tests/unit/operation/scenarios/test_growth_and_review.py`：通过。
- `uv run mypy src/efficiency_platform_agent/agents/operation/scenarios/service.py`：通过。

## 文件清单

- `tests/unit/operation/scenarios/test_campaign_and_calendar.py`
- `tests/unit/operation/scenarios/test_growth_and_review.py`
- `src/efficiency_platform_agent/agents/operation/scenarios/service.py`（补充 PARTIAL 缺少范围或告警时的失败关闭）
- `docs/superpowers/sdd/operation-scenarios-s6/task-8-report.md`

## 未验证边界

本次只验证 ScenarioPackService 的 Manifest→Profile→Plan→Supervisor 委派顺序和结构化状态边界，不宣称真实 S4 调度、真实 Specialist、数据分析质量、平台规则或外部平台效果。真实模型、网络、数据库、Redis、COS、文件和发布动作仍未验证。
