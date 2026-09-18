# R06 实施报告：事件聚合、来源独立性与排序

## 状态

**离线通过。**

R06 已完成有界事件聚类提案/裁决、来源家族解析、独立性状态、importance/heat/recency 排序和 pairwise 聚类评估。没有调用真实模型、没有启用真实来源或发起公网请求，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_evidence_v2.py`
- `src/efficiency_platform_agent/capabilities/research/v2/clustering.py`
- `src/efficiency_platform_agent/capabilities/research/v2/source_families.py`
- `src/efficiency_platform_agent/capabilities/research/v2/ranking.py`
- `src/efficiency_platform_agent/prompts/registry.py`
- `src/efficiency_platform_agent/prompts/resources/research/cluster_v2.j2`
- `tests/unit/capabilities/research_v2/test_event_clustering.py`
- `tests/unit/capabilities/research_v2/test_source_families.py`
- `tests/unit/capabilities/research_v2/test_ranking.py`
- `tests/unit/prompts/test_research_v2_templates.py`

## 已实现不变量

- EventClusterer 先按 Brief 实体命中、显式产品版本和两日邻近形成确定性桶，每次语义提案最多接收 30 个规范文档。
- 聚类端口只返回 document_id、event_type、product_version、semantic_equivalence、实体和依据；程序绑定 brief digest 与 Prompt 版本并检查未知 ID、跨桶 ID、重复分配、事件类型和产品版本。
- 陈旧 Prompt/Brief、different/uncertain 语义、事件类型冲突或产品版本冲突均不形成合并事件；相关文档保守降为 singleton uncertain。
- 每个输入文档最终且只属于一个事件；event_id 由 Brief、事件类型、版本和排序后的成员 ID 生成，不受输入顺序或模型自由文本影响。
- 代表文档优先 primary，再按最早可确认事件/首发时间和 document_id 稳定选择；事件时间不使用当前时间回填。
- SourceFamilyResolver 通过 ownership_group、同 publisher、同规范 URL 和相同正文识别同一来源族；不同域名不会自动计为独立来源，只有 primary 原始来源或已知 ownership_group 才形成 confirmed 独立家族，其他均为 unknown。
- importance 仅接受 critical/high/medium/low 与解释码；同等级按事件时间与 stable event_id 排序。
- heat 观测必须携带 platform、metric、snapshot_id 和带时区观测时间；同平台同指标只用最新可比快照，并在平台/指标内归一化后汇总，不直接相加原始 score/rank/comments。
- 热度缺失保持 `score=None/heat_unknown`，不当作 0；当前快照只标记 `platform_normalized_current_heat`，没有可比历史时不生成“上涨最快”等 trend_label。
- pairwise 评估要求预测/人工标注使用同一文档全集，输出 precision、recall、false positive pairs 和 false negative pairs，明确报告误合并与漏合并。

## 验证证据

```text
R06 定向（事件聚类/来源家族/排序/Prompt）：18 passed
Ruff（全 src/tests）：All checks passed
mypy（全 src）：Success: no issues found in 252 source files
全量回归：1372 passed, 275 subtests passed, 2 existing dependency warnings in 45.99s
```

两条警告仍来自既有 Starlette BlockingPortal 弃用提示与 Polars 未来返回类型提示，不由 R06 引入。

## 边界与后续

- EventClusterer 依赖中立 `EventClusterDecisionPort`；真实 ModelRuntime、ContextBuilder、预算租约结算和图内调用在 R09/X02 组合根接入前保持关闭。
- `confirmed_independent_count` 只表达当前证据可确认的来源家族，不宣称不同 unknown 家族彼此独立。
- 当前 heat 排序是平台内最新快照的归一化排序，不是全网热度、历史涨幅或趋势分析。
- R06 只形成事件候选；事实单元、原文字符定位、数字校验和冲突管理由 R07 实施。
