# I05 实施任务简报：语义能力目录、绑定、DAG 与澄清

## 目标与边界

从现有运营 Specialist 能力声明、AgentSpec 和场景 Manifest 生成只读语义目录；实现确定性 Binder 与 DecisionPolicy，校验能力存在、权限、参数 Schema、必填槽位和 DAG，并只输出 READY / CLARIFY / UNSUPPORTED / FAILED。I05 不注册新执行能力、不调用 Agent/Tool/模型、不写库。

## 文件白名单

- 新增 `src/efficiency_platform_agent/agents/operation/scenarios/semantic_catalog.py`
- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/binding.py`
- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/decision.py`
- 更新必要 `__init__.py`
- 新增 `tests/orchestration/intent_v2/test_binding.py`
- 新增 `tests/orchestration/intent_v2/test_decision.py`
- 新增 `tests/unit/operation/scenarios/test_semantic_catalog.py`
- 完成后新增 I05 report/review，并更新实施进度账本

## 冻结规则

1. 语义目录是现有 `CapabilitySpec / AgentSpec / ScenarioPackManifest` 的确定性投影，不是第二个可执行注册表；能力 ID 必须与 `OperationSpecialistCapabilityId` 一一对应。
2. 描述、正反例属于语义元数据；版本、权限、输入 Schema、输出和依赖必须从真实注册/Manifest 导出。目录版本由规范内容哈希生成。
3. Goal 引用任何未知能力立即返回 `CAPABILITY_UNKNOWN`，不能忽略未知项后回退到第一个已知能力。
4. 选择只在 Goal 显式候选顺序中进行；权限以 `PermissionSnapshotV2.allowed_capability_ids` 为硬边界。
5. 参数必须通过 descriptor 引用的显式 Schema：未知 Schema 技术失败，未知参数/错误严格类型不执行，缺少关键 Frame 字段进入澄清。
6. 任一 Goal 失败时不返回可执行部分计划；成功计划按原 Goal 顺序稳定拓扑排序，依赖保持原样。
7. Decision 固定优先级：技术错误 FAILED → 能力不存在/未授权/非法参数 UNSUPPORTED → 关键目标/引用/时间/来源/输出缺失或歧义 CLARIFY → 全部满足 READY。
8. 每次 CLARIFY 只返回一个最高优先字段：目标/对象 → 时间 → 来源 → 必需输出。澄清轮数生命周期由 I07 管理。
9. chat/cancel 可以无业务 Goal READY；其他执行型 dialog act 没有 Goal 必须澄清，不能依赖 confidence 放行。

## 验收

先写真实目录一一对应、未知能力、未授权、非法参数、必填字段、稳定 DAG、循环/超限契约、决策优先级和单字段澄清红灯；实现后执行 I05 定向、场景 Registry 回归、意图/契约/架构组合、Ruff、mypy 和全量测试，再完成文件级反例审查。
