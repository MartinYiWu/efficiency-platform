# S5 Task 5～6 实施报告：品牌、内容与渠道运营 Specialist

## 实施范围

本次仅实现离线固定脚本和确定性结构输出，不接入真实模型、Provider、网络、数据库、平台发布或账号操作；未修改 S1～S4 生命周期与公共契约。

## Task 5（S5B）

- 新增 `BrandOperationAgent`、`IPOperationAgent`、`ProductOperationAgent`。
- 三者分别使用唯一 S5 capability、task type、Prompt Bundle、质量策略和固定 AgentSpec；预算按 S5 计划声明。
- 输出独立 `DeliverableBundle`，分别标记 `brand_strategy`、`ip_strategy`、`product_operation_plan`；不宣称曝光、转化、留存或 ROI 实际值。
- AgentSpec 不声明写 Tool 或外部权限，结果只包含离线草稿结构。

## Task 6（S5C）

- 新增 `PlatformProfile` 与 `PlatformProfileResolver`，只展开 S3 `ChannelProfile` 的版本化规则；固定样本标记 `fixture_only=True`。
- 新增 `ContentAgent`、`ChannelContentAgent`、`CampaignOperationAgent`，分别输出平台中立 Brief、渠道独立内容和活动方案。
- 渠道执行视图要求合法规则版本和已确认事实；不自动切换平台，不执行发布、通知、交易或其他外部副作用。

## RED/GREEN 证据

RED：在目标模块尚未落盘时，聚焦命令因 Specialist/Profile 模块不存在而导入失败，确认测试针对预期缺口。

GREEN：

```powershell
$env:PYTHONPATH='src'; uv run python -m unittest tests.unit.agents.operation.specialists.test_brand_ip_product tests.unit.agents.operation.profiles.test_platform tests.unit.agents.operation.specialists.test_content_channel_campaign tests.acceptance.test_operation_brand_ip_product tests.acceptance.test_operation_content_channel_campaign -v
```

结果：退出码 0，7 项测试通过。

静态验证：

```powershell
uv run ruff check src/efficiency_platform_agent/agents/operation/specialists/_base.py src/efficiency_platform_agent/agents/operation/specialists/brand.py src/efficiency_platform_agent/agents/operation/specialists/ip.py src/efficiency_platform_agent/agents/operation/specialists/product.py src/efficiency_platform_agent/agents/operation/specialists/content.py src/efficiency_platform_agent/agents/operation/specialists/channel.py src/efficiency_platform_agent/agents/operation/specialists/campaign.py src/efficiency_platform_agent/agents/operation/profiles/platform.py tests/unit/agents/operation/specialists/test_brand_ip_product.py tests/unit/agents/operation/specialists/test_content_channel_campaign.py tests/unit/agents/operation/profiles/test_platform.py tests/acceptance/test_operation_brand_ip_product.py tests/acceptance/test_operation_content_channel_campaign.py
uv run python -m compileall -q src/efficiency_platform_agent/agents/operation tests/unit/agents/operation tests/acceptance/test_operation_brand_ip_product.py tests/acceptance/test_operation_content_channel_campaign.py
```

结果：Ruff 退出码 0；compileall 退出码 0。

## 文件清单

- `src/efficiency_platform_agent/agents/operation/specialists/_base.py`
- `src/efficiency_platform_agent/agents/operation/specialists/{brand,ip,product,content,channel,campaign}.py`
- `src/efficiency_platform_agent/agents/operation/profiles/platform.py`
- `src/efficiency_platform_agent/prompts/resources/operation/{brand_operation_v1,ip_operation_v1,product_operation_v1,content_operation_v1,channel_content_v1,campaign_operation_v1}.j2`
- `tests/fixtures/operation/{brand,ip,product,content,platform,campaign}/*.json`
- `tests/unit/agents/operation/{specialists,profiles}/*`
- `tests/acceptance/test_operation_brand_ip_product.py`
- `tests/acceptance/test_operation_content_channel_campaign.py`

## 未验证边界

- 当前 Specialist 为离线确定性草稿输出，尚未接入 S2 Prompt/Model Runtime；真实内容质量、品牌事实和平台规则未验证。
- 未连接公共搜索、真实 ChannelProfile 数据、真实模型、数据库、缓存、COS 或任何平台发布接口。
- `SpecialistResultDecoder` 对非空 `DeliverableBundle`/`OperationQualityReport` 的完整无损解码仍属于 S4 后续适配边界。
