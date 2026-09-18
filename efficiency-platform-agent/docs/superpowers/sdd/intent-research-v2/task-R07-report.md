# R07 实施报告：Claim 提取、原文定位与冲突管理

## 状态

**离线通过。**

R07 已完成规范正文 EvidenceRef 构建/校验、Claim 模型提案的确定性门禁、数值/单位/归属检查、来源家族支持计数、冲突保留和人工事实召回评估。没有调用真实模型、没有启用真实来源或发起公网请求，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_evidence_v2.py`
- `src/efficiency_platform_agent/capabilities/research/v2/evidence.py`
- `src/efficiency_platform_agent/capabilities/research/v2/claims.py`
- `src/efficiency_platform_agent/prompts/registry.py`
- `src/efficiency_platform_agent/prompts/resources/research/claims_v2.j2`
- `tests/unit/capabilities/research_v2/test_evidence_refs.py`
- `tests/unit/capabilities/research_v2/test_claims.py`
- `tests/unit/capabilities/research_v2/test_conflicts.py`
- `tests/unit/prompts/test_research_v2_templates.py`

## 已实现不变量

- `build_evidence_ref` 只从已保存的 `SourceDocument.text` 生成 Unicode 字符区间、逐字 excerpt、正文 hash、paragraph_index 和稳定 evidence_id；不使用 HTML 字节偏移。
- `EvidenceValidator` 交叉校验 document_id、content_hash、范围、逐字 excerpt、paragraph_index 和 acquisition_method；URL 存在但无已保存正文时返回 `EVIDENCE_DOCUMENT_NOT_STORED`。
- Claim 模型端口只能提出既有 event_id 与 evidence_id；程序拒绝未知证据、事件外证据、陈旧 Brief/Prompt、无效证据、缺失主体和重复提案。
- 数值 Claim 必须同时保存 `value_text/numeric_value/unit/claim_time`；数值必须同时出现在规范摘录、Claim 文本和值文本中，单位必须同时受原文与 Claim 文本支持。
- Claim 类型冻结为 announcement、reported_fact、measured_result、opinion、inference；announcement/opinion 必须 attributed，inference 必须显式 inference。
- 客观 Claim 至少需要一个 confirmed 独立来源家族；若证据全是主体自己的 primary 原文，则至少两个 confirmed 家族，否则要求改为归属式陈述。
- 多篇同文转载通过 source family 折叠为一个家族；unknown 家族不计入 independent_support_count，转载数量不能投票提升事实等级。
- ClaimRecord 保留原子 `claim_key`，冲突仅在同事件、同 claim key、主体、单位与时间下比较；不同原子指标不会因单位相同被误判冲突。
- 不同值形成 unresolved ConflictGroup，双方 Claim 与证据都保留；冲突 objective Claim 不进入 certain_fact，attributed Claim 只进入明确归属争议集合。
- `evaluate_claim_recall` 对人工冻结的 expected claim keys 报告 recall、missing 和 unexpected，明确程序引用覆盖率不能替代事实完整性评估。

## 验证证据

```text
R07 定向（Claim/Evidence/Conflict/Prompt）：17 passed
Ruff（全 src/tests）：All checks passed
mypy（全 src）：Success: no issues found in 254 source files
全量回归：1386 passed, 275 subtests passed, 2 existing dependency warnings in 45.45s
```

两条警告仍来自既有 Starlette BlockingPortal 弃用提示与 Polars 未来返回类型提示，不由 R07 引入。

## 边界与后续

- ClaimExtractor 依赖中立 `ClaimDecisionPort`；真实 ModelRuntime、ContextBuilder、模型预算租约和图内调用在 R09/X02 接入前保持关闭。
- `certain_fact_claim_ids` 是本层证据与冲突门禁结果，不等于最终交付合格；时间/相关性/来源允许、事件非重复和集合覆盖还需 R08 质量门槛。
- 当前单位同义词表仅覆盖百分比、秒、毫秒、USD、CNY；未知单位采用原词逐字匹配，后续只能版本化扩展，不能静默换算。
- 真实来源仍全部保持 disabled/UNVERIFIED；本阶段未验证任何公网正文或模型事实召回质量。
