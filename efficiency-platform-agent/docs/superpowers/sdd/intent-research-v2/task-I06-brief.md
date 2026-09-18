# I06 实施任务简报：研究需求桥接、场景投影与缓存资格

## 目标与边界

将完整、可执行的 IntentFrameV2 确定性地桥接为 ResearchBriefV2，并把多目标能力计划无损投影为显式 ScenarioProjection；定义研究证据缓存复用资格。I06 不调用模型、Agent、Tool、来源、数据库或旧 V1 Intent，不执行场景。

## 文件白名单

- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/research_bridge.py`
- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/scenario_adapter.py`
- 更新 `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- 必要扩展 `src/efficiency_platform_agent/contracts/research_v2.py`
- 新增 `tests/orchestration/intent_v2/test_research_bridge.py`
- 完成后新增 I06 report/review，并更新实施进度账本

## 冻结规则

1. Builder 只接受无阻塞歧义/未决引用且研究主题、时间、来源约束、输出要求均有效的 Frame；可信 task_id 必须匹配，身份/预算只取 TrustedResearchContextV2。
2. 时间必须经 I03 TemporalResolver 生成非空 UTC 左闭右开窗口；禁止给研究链传 None 或 unspecified。
3. 来源约束与输出目标分开保存；未知来源 ID 保留为需求，不能偷偷替换为其他来源。
4. 显式 count 生成 exact 策略且不得被默认 5 覆盖；未显式数量才使用有诊断记录的 best_effort 默认。
5. topic、时间、来源、输出、数量与显式 exclusions 分别生成稳定硬需求 ID；Brief digest 固定 intent revision 与 policy version。
6. ScenarioProjection 保留每个 Goal、能力、依赖、Frame 语义参数和 Goal 参数；不伪造 IntentEnvelopeV1，不把复合目标压成单一 task_type。
7. 不完整/不支持的计划输出 `supported=False` 和稳定 reasons，不能产生部分投影。
8. 缓存复用必须同租户、同权限快照、未过期、主题一致、缓存时间覆盖请求时间且 basis 相同，并证明实际来源满足新来源约束；仅改变输出平台可复用，改变时间不可只改标题。

## 验收

先写来源/目标分离、昨天窗口、exact3、排除项、默认记录、未就绪拒绝、多目标无损投影、缓存复用/失配红灯；实现后执行 I06 定向、I03/I05/旧场景回归、意图/契约/架构组合、Ruff、mypy 和全量测试，再完成文件级反例审查。
