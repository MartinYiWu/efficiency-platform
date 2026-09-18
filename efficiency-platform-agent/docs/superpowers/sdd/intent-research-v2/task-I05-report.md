# I05 实施报告：语义能力目录、确定性绑定与决策

## 状态

**离线通过。**

本任务只实现 Agent 侧只读语义目录、Intent 阶段参数 Schema、能力 Binder、稳定 DAG 排序和单字段决策策略；未注册第二套执行能力，未调用模型、Agent、Tool、网络或数据库，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/agents/operation/scenarios/semantic_catalog.py`
- `src/efficiency_platform_agent/agents/operation/scenarios/__init__.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/binding.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/decision.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- `tests/unit/operation/scenarios/test_semantic_catalog.py`
- `tests/orchestration/intent_v2/test_binding.py`
- `tests/orchestration/intent_v2/test_decision.py`
- `docs/superpowers/sdd/intent-research-v2/task-I05-brief.md`
- 本报告与规格/质量审查记录

## 已实现边界

- 从真实 `CapabilitySpec`、`AgentSpec` 和 `ScenarioPackManifest` 构造不可执行的 `CapabilityCatalogSnapshot`；11 个能力 ID 必须与 `OperationSpecialistCapabilityId` 精确一一对应，漂移、重复或缺 Agent 均失败关闭。
- 描述和正反例作为语义元数据维护；能力版本和权限来自真实 `CapabilitySpec`，支持输出优先来自生产 Manifest 的清单级交付要求，依赖来自场景步骤 DAG；目录版本对规范化快照做 SHA-256 摘要。
- Manifest 只在单能力场景下把清单级交付要求归属给能力；多能力场景保留步骤输出契约版本，避免把测试期望字段当生产能力事实。
- Binder 只在 Goal 显式候选顺序内选择，任何未知候选立即 `CAPABILITY_UNKNOWN`；权限以可信层预先计算的 `allowed_capability_ids` 为硬边界，不自行伪造身份或权限。
- Intent 参数使用每个能力显式引用的封闭 Schema；未知参数、严格类型错误、缺 Schema 均不执行。该 Schema 是 I05 的意图阶段投影，不替代后续 `SpecialistExecutionInput` 和 I06 场景投影校验。
- 任一 Goal 失败时返回空步骤，不泄漏可执行部分计划；成功计划按输入 Goal 顺序做稳定拓扑排序并保留依赖。
- Decision 固定执行：技术错误 `FAILED`，未知/未授权/非法参数 `UNSUPPORTED`，缺失或阻塞歧义 `CLARIFY`，完整计划 `READY`；不使用模型 confidence。
- 每次只返回一个最高优先澄清字段；目标/对象优先于时间、来源和输出。普通 chat/cancel 可无业务 Goal，其余无 Goal 必须澄清。
- `tenant_id` 等非语义字段若被伪装为阻塞歧义或缺失字段，稳定返回 `INTENT_AMBIGUITY_FIELD_UNKNOWN`，不会向用户追问可信身份字段。

## 红灯与修正证据

首次加入测试时三个实现模块均不存在，定向执行得到：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.agents.operation.scenarios.semantic_catalog'
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2.binding'
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2.decision'
```

实现后对抗审查补充两项回归：后续非法 Goal 必须清空之前的合法 Goal；未知澄清字段必须技术失败。首次全量回归另发现场景架构守卫禁止生产目录读取测试期望交付字段：当时 1192 项通过、1 项失败。随后改为从清单级生产交付要求和步骤输出契约投影，守卫与全量测试恢复通过。

## 绿灯与回归证据

```text
I05 目录/绑定/决策定向：17 passed

I05 + 场景 Registry：22 passed

意图 V2 + contracts + architecture：
248 passed, 124 subtests passed

场景架构守卫修复复验：19 passed

Ruff：All checks passed

mypy：Success: no issues found in 8 source files

全量回归：
1193 passed, 275 subtests passed, 2 existing dependency warnings in 30.02s
```

两条全量警告来自既有 Starlette `BlockingPortal` 弃用提示和 Polars `read_excel` 未来返回类型变化，不由 I05 引入。

## 未宣称事项

- I05 只证明确定性目录、绑定和准入边界，不代表真实模型能稳定生成正确 Goal/参数；真实模型冻结集验收属于 X04。
- `PermissionSnapshotV2.allowed_capability_ids` 是可信授权层生成的能力级快照；真实身份/租户/权限策略接线属于 I07/X01，本任务没有实现授权系统。
- Intent 阶段参数 Schema 不等同 Specialist 最终执行输入；Frame 到 `ResearchBriefV2`/场景输入的无损投影和下游契约复验属于 I06。
- I05 不执行能力、不产生工具调用；澄清最多两轮及 Run 生命周期限制由 I07 协调器负责。
