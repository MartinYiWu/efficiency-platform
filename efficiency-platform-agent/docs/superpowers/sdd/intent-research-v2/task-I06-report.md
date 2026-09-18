# I06 实施报告：研究需求桥接、场景投影与缓存资格

## 状态

**离线通过。**

本任务只实现 Agent 侧确定性 ResearchBrief 桥接、不可执行场景投影和证据缓存复用资格；未调用模型、Agent、Tool、网络、来源或数据库，未创建 V1 Intent，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_v2.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/research_bridge.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/scenario_adapter.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- `tests/orchestration/intent_v2/test_research_bridge.py`
- `docs/superpowers/sdd/intent-research-v2/task-I06-brief.md`
- 本报告与规格/质量审查记录

## 已实现边界

- `ResearchBriefBuilderV2` 只接受可信 task 匹配、revision>=1、无阻塞歧义/未决引用且唯一明确选择研究能力的 Frame；身份、Run 和预算租约仅取 `TrustedResearchContextV2`。
- 时间表达必须由 I03 `TemporalResolver` 解析为非空 UTC 左闭右开窗口；缺失/unspecified/歧义/非法时间失败关闭。
- 来源 `allowed_source_ids` 与输出 `target_platforms` 分开保存；未知来源 ID 原样保留，不替换成其他来源。
- 显式 count 形成 `exact(target=minimum=count)`；未给数量才形成 `best_effort(5,1)`，并记录 `DEFAULT_COUNT_POLICY` 诊断。
- topic、时间、来源、输出、数量及非空 exclusions 生成稳定 `ResearchRequirementV2`；契约重新计算并拒绝被篡改的 ID/digest。
- Brief 固定 `intent_revision`、`intent_scope_hash`、质量策略 ID/版本；默认字段和默认叶级策略写入 diagnostics，但 diagnostics 不进入 canonical digest。
- 为兼容 C02 旧 V2 快照，缺少 `hard_requirements` 的旧 Brief 仍可读取；I06 Builder 产出的可执行 Brief 始终带完整硬需求集合，不把旧快照冒充新 Bridge 产物。
- `ScenarioInputAdapter` 保留每个 Goal、能力、依赖、Frame 语义字段和 Goal 参数，不合并复合目标、不生成 `IntentEnvelopeV1`。
- 未就绪 Frame、不完整/不一致计划、未知能力、能力或依赖不匹配均返回空步骤和稳定 reason，不泄漏部分投影。
- 缓存复用要求同租户、同权限快照、未过期、主题/实体/排除项一致、basis 相同且时间全覆盖，并证明实际来源、语言、区域和 primary 属性满足新约束；只改输出平台可复用，改变时间或事实范围不可复用。

## 红灯与修正证据

首次新增 I06 测试后执行得到：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2.research_bridge'
```

首轮实现后 14 项新测试通过，静态检查暴露 3 个泛型写法和 14 个类型问题，均改为 Python 3.13 类型参数及类型安全字段投影。组合回归随后发现 C02 旧 Brief 缺新增硬需求字段而失败；最终采用“旧快照可读、I06 产物强校验”的兼容策略，并增加 digest 篡改、候选歧义、零 revision、未知能力、依赖丢失和实体范围缓存失效回归。

## 绿灯与回归证据

```text
I06 新增测试 + ResearchBrief 契约：26 passed

I03/I05/场景组合：86 passed

意图 V2 + contracts + architecture：
265 passed, 124 subtests passed

Ruff：All checks passed

mypy：Success: no issues found in 10 source files

全量回归：
1210 passed, 275 subtests passed, 2 existing dependency warnings in 38.69s
```

两条全量警告来自既有 Starlette 与 Polars 依赖，不由 I06 引入。

## 未宣称事项

- I06 不证明真实模型意图精度，也不验证来源实际可用；真实模型验收属于 X04，来源准入与采集属于 R01—R10。
- Builder 通过完整性不变量保守判断可桥接 Frame；READY 决策与 Builder 的顺序接线由 I07 负责。
- ScenarioProjection 只是 V2 Supervisor/旧场景协调层的不可执行输入，不等于已创建 `OperationTaskSpec` 或运行 Specialist。
- 缓存资格只定义可信元数据判定；缓存持久化、TTL 清理、证据读取和并发隔离属于后续研究/集成任务。
