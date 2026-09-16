# S6 Task 7 实施报告：前四个运营场景包回归

## 实施范围

本任务为 `industry_digest`、`multi_platform_content`、`brand_operation_plan`、`ip_operation_plan` 增加离线场景回归测试。测试消费 S6 `ScenarioPackService`、S3 Manifest 和测试专属 Sample/Fake；通过注入内存 Supervisor 与 S2 合成装配器产生结构化交付物，不访问网络、文件、数据库、模型、平台账号或发布接口。

覆盖范围如下：

- 行业动态：完整报告、时间窗缺失等待、研究证据不足部分结果。
- 多平台内容：三个独立平台范围完整交付、平台集合缺失等待、头条失败但保留其他两个平台的部分结果。
- 品牌运营：完整品牌策略、品牌研究不可用的非完整结果、目标缺失等待。
- IP 运营：完整定位、渠道不可用但保留定位与孵化路径的部分结果、受众缺失等待。

## RED/GREEN 证据

RED：Task 7 场景测试文件和回归断言尚不存在；新增测试前无法执行目标测试集合。

GREEN：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.operation.scenarios.test_industry_digest tests.unit.operation.scenarios.test_multi_platform_content tests.unit.operation.scenarios.test_brand_and_ip_operation -v
```

结果：退出码 0，12 项测试通过。

样本与契约联合回归：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.operation.scenarios.test_samples tests.unit.operation.scenarios.test_industry_digest tests.unit.operation.scenarios.test_multi_platform_content tests.unit.operation.scenarios.test_brand_and_ip_operation -v
```

结果：退出码 0，14 项测试通过。静态检查 `ruff check` 与 `ruff format --check` 对本任务新增测试及 S6 Sample 文件通过。

## 文件清单

- `tests/unit/operation/scenarios/test_industry_digest.py`
- `tests/unit/operation/scenarios/test_multi_platform_content.py`
- `tests/unit/operation/scenarios/test_brand_and_ip_operation.py`
- `tests/support/s6_scenario_samples.py`：将 expected 状态固定为 S4 `CompletionStatus` 枚举。

## 未验证边界

- Supervisor、Provider、Tool 和 Profile 选择均为注入的内存替身，未证明真实 Specialist、模型池、搜索源或渠道规则可用。
- 测试验证结果状态、完成/缺失范围和告警保留，不代表实际行业研究质量、内容质量、品牌事实或 IP 效果。
- 当前回归通过显式 Patch 固定 S3 选择/计划编译结果；真实 S3 数据与业务输入校验仍留给 S7。
