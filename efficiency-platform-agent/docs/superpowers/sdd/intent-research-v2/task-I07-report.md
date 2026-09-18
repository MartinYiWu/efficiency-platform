# I07 实施报告：会话协调、CAS 生命周期与离线评测

## 状态

**离线通过。**

本任务完成 Agent 侧 Intent V2 离线协调器、租户隔离 InMemory CAS 仓储、现有会话服务可选注入点和 240 例离线标注资产；未接真实 PostgreSQL、真实模型、真实来源或 Tool，未替换 V1 生产路径，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/orchestration/intent_v2/pipeline.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/binding.py`（研究必填 Frame 维度闭合）
- `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- `src/efficiency_platform_agent/conversation/service.py`（可选 V2 coordinator 注入点）
- `src/efficiency_platform_agent/evaluation/__init__.py`
- `src/efficiency_platform_agent/evaluation/intent_v2.py`
- `tests/conversation/test_intent_v2_flow.py`
- `tests/evaluation/test_intent_v2_dataset.py`
- `tests/fixtures/intent_v2/development.jsonl`（120）
- `tests/fixtures/intent_v2/regression.jsonl`（60）
- `tests/fixtures/intent_v2/frozen.jsonl`（60）
- `tests/fixtures/intent_v2/manifest.json`
- `docs/superpowers/sdd/intent-research-v2/task-I07-brief.md`
- 本报告与规格/质量审查记录

## 已实现边界

- `IntentPipelineV2` 固定执行读取/幂等→解释→Patch Validator→Reducer→TemporalResolver→Binder/Decision→Brief/ScenarioProjection→CAS commit；不增加关键词 fast path。
- 只有仓储 CAS 成功后才返回 `committed=True`；只有已提交、非重放、READY 且生命周期为 START_NEW_RUN/RESUME_RUN 时 `dispatch_allowed=True`。
- InMemory 仓储用 `(tenant_id, task_id)` 和 `(tenant_id, task_id, message_id)` 复合键隔离；真实数据库实现仍归 X01。
- 相同消息 ID+正文直接重放已提交结果且不再次调用模型/派发；相同 ID 不同正文稳定失败；不同并发消息基于同 revision 时仅一个 CAS 成功。
- WAITING_INPUT 补齐后复用原 Run 且 Brief 绑定原 Run；终态/新任务使用拟建 Run；运行中 refine 提交新 revision，但只返回 `SUPERSEDE_AT_SAFE_BOUNDARY` 和 replacement Run，不直接取消、不并发派发。
- cancel 只返回 `CANCEL_EXISTING`，供既有取消入口处理；不旁路写终态。chat、CLARIFY、UNSUPPORTED、FAILED 和重放均不派发。
- 澄清已达两轮时稳定 `CLARIFICATION_LIMIT_EXCEEDED`，不再提交第三轮；Provider 技术故障保留 usage/provider_calls 并不转用户澄清。
- ConversationService 新增可选 `IntentV2ConversationCoordinator`；存在 V1 pending intent 时永远跳过 V2，保证任务版本不降格/静默升级；coordinator 返回 None 时完整沿用原 V1 路径。
- 240 例数据严格为 development/regression/frozen=120/60/60；类别为单轮60、多轮60、日期40、复合30、攻击30、故障20；语义族不跨 split，文件 SHA-256、数量、来源、标注方式、时区和冻结集禁止调参均写入 manifest。
- 评测器检查 hash、计数、语义族隔离、密钥模式和预测覆盖，输出 case/field/decision/capability 的正确数与总数及逐字段错误；未声明的额外字段除显式 allowed_defaults 外计为错误。

## 红灯与修正证据

首次新增会话流测试时执行得到：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2.pipeline'
```

实现后的安全审查发现并修复三项重要问题：仓储最初仅按 task_id 键控；CAS 候选在原子提交前标记 committed；恢复 WAITING_INPUT 时 Brief 绑定拟新 Run。最终改为租户复合键、仓储内原子生成 committed 结果、生命周期判定后绑定真实目标 Run，并增加跨租户、同 ID 冲突、Provider 故障、澄清上限与取消回归。

## 绿灯与回归证据

```text
I07 会话流 + 数据集定向：15 passed

I07 + orchestration + conversation + architecture：
323 passed, 124 subtests passed

contracts + 场景 Registry + 会话 API：98 passed

Ruff：All checks passed

mypy：Success: no issues found in 18 source files

全量回归：
1225 passed, 275 subtests passed, 2 existing dependency warnings in 36.15s
```

两条全量警告来自既有 Starlette 与 Polars 依赖，不由 I07 引入。

## 未宣称事项

- InMemory 仓储只证明 CAS/幂等/隔离语义，不能替代 X01 PostgreSQL 迁移、恢复、索引和事务验收。
- ConversationService 仅有可选注入点，没有默认开启 V2 或修改生产配置；真实组合根、开关、回滚和灰度属于 X03/X05。
- 240 例是设计规格驱动的离线标注资产，当前只用静态 oracle 验证数据/指标管线；不代表真实模型达到任何精度阈值。真实冻结集模型评测属于 X04。
- `SUPERSEDE_AT_SAFE_BOUNDARY` 和 `CANCEL_EXISTING` 是提交给既有生命周期的动作意图，本任务未旁路调用取消或写 Run 终态。
