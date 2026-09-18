# R08 检查点 1：质量门槛与覆盖状态

## 当前状态

**进行中，不是 R08 完成报告。**

本检查点只完成质量裁决内核与离线场景策略：H1–H6、集合数量/维度覆盖、成功空/失败空/历史未知状态已经实现并通过回归。arXiv、GDELT Provider 契约和 100 文档/30 事件固定回放清单尚未完成。

## 已完成

- `capabilities/research/v2/quality.py`：从 FilterResult、SourceDocument、EventCluster、Claim、EvidenceRef、ConflictSet 和 SourcePolicyDecision 聚合事件硬门禁。
- `agents/operation/scenarios/research_policy.py`：冻结离线质量策略，不声明真实来源已准入。
- H1 条件、H2 Claim 实际支持文档内容范围、H3 引用/独立来源/primary 策略、H4 重复成员、H5 unresolved objective、H6 来源允许均由程序裁决。
- exact 不足为 PARTIAL；best_effort 达 minimum 且无其他硬缺口时少于 target 仍可 COMPLETE。
- NO_MATCHES 仅在无事件、计划完整、有实际尝试、无关键失败/截断且历史 complete 时产生；全失败、截断或历史 unknown 为 FAILED。
- 单一失败可作为 warning 保留，不在已有充分合格事件时自动覆盖 COMPLETE。

## 当前验证

```text
R08 质量/覆盖定向：7 passed
Ruff（全 src/tests）：All checks passed
mypy（全 src）：Success: no issues found in 256 source files
全量回归：1393 passed, 275 subtests passed, 2 existing dependency warnings in 43.83s
```

## 未完成

- arXiv 显式时间/分类/分页/submitted-updated/摘要范围契约。
- GDELT 显式窗口/Schema/错误/历史限制/URL 线索契约。
- 两来源配置继续 disabled/UNVERIFIED 的治理用例。
- 100 文档/30 事件固定回放清单及每个 H 门槛正反例矩阵。
- R08 最终规格审查、质量审查和离线通过状态。
