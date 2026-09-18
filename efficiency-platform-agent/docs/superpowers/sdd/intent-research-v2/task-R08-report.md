# R08 实施报告：质量门槛、覆盖矩阵与可查询免费来源

## 状态

**离线通过。**

R08 已完成 H1–H6 事件质量门禁、集合数量/维度覆盖、领域结果状态、arXiv/GDELT 离线 HTTP 契约、候选来源禁用配置和 100 文档/30 事件固定回放清单。没有启用真实来源或发起公网请求，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/capabilities/research/v2/quality.py`
- `src/efficiency_platform_agent/agents/operation/scenarios/research_policy.py`
- `src/efficiency_platform_agent/providers/research/arxiv.py`
- `src/efficiency_platform_agent/providers/research/gdelt.py`
- `src/efficiency_platform_agent/contracts/research_sources_v2.py`
- `src/efficiency_platform_agent/contracts/research_evidence_v2.py`
- `src/efficiency_platform_agent/capabilities/research/v2/normalization.py`
- `src/efficiency_platform_agent/configuration/research.py`
- `config/research_sources.toml`
- `tests/fixtures/research_v2/corpus_manifest.json`
- `tests/unit/capabilities/research_v2/test_quality.py`
- `tests/unit/capabilities/research_v2/test_coverage.py`
- `tests/unit/capabilities/research_v2/test_corpus_manifest.py`
- `tests/contract/providers/research_v2/test_arxiv.py`
- `tests/contract/providers/research_v2/test_gdelt.py`

## 已实现不变量

- 质量评价只消费已验证 FilterResult、SourceDocument、EventCluster、Claim、EvidenceRef、ConflictSet 和来源策略事实；模型不能直接写 accepted 或 COMPLETE。
- H1 要求事件全部成员已通过条件/时间/语义过滤；H2 要求每个 Claim 至少有 full/platform_text 支持文档；H3 重验 evidence 定位、独立来源数和 key Claim primary 策略。
- H4 拦截跨事件重复成员；H5 阻止 unresolved objective Claim 作为确定事实；H6 要求每个成员来源均有明确 allowed 策略，缺失即失败关闭。
- `exact` 不足形成可补采 gap；`at_most`/`best_effort` 达 minimum 即满足数量门槛；best_effort 少于 target 本身不自动 PARTIAL。
- required facets 由可用事件中已接受 Claim 的 claim_key 覆盖，不用固定行业子类、媒体数量或关键词替代。
- NO_MATCHES 只在无事件、计划完整、至少一次真实来源尝试、无关键失败/截断且历史 coverage=complete 时产生；全失败、截断或历史 unknown 为 FAILED。
- 致命安全/租户完整性失败优先于已有事件，不能被覆盖成 COMPLETE；非致命单源警告在其他证据已满足硬要求时不自动降级。
- arXiv 请求显式提交时间窗、主题/分类、分页和排序；逐条区分 published/updated，仅保存 landing URL、元数据与 abstract summary，不下载 PDF，标记 `abstract_only`。
- GDELT 请求显式 start/end；`seendate` 只保存为 first_seen，不冒充 published；返回 URL 标记 `requires_content_fetch`，不能直接成为内容证据。
- GDELT 无总量证明时 coverage/completeness 保持 unknown；历史早于配置能力时在发请求前返回 SOURCE_HISTORY_UNSUPPORTED。
- arXiv/GDELT 配置均为 `enabled=false`、`admission_status=UNVERIFIED`、`cost_mode=unknown`；离线契约通过不计入真实可用来源。
- 固定 manifest 确认 100 个连续唯一文档、30 个唯一事件，并为 H1–H6 各冻结一组 pass/fail 用例。

## 验证证据

```text
R08 定向（质量/覆盖/回放/arXiv/GDELT/禁用配置）：18 passed
Ruff（全 src/tests）：All checks passed
mypy（全 src）：Success: no issues found in 258 source files
全量回归：1401 passed, 275 subtests passed, 2 existing dependency warnings in 42.62s
```

两条警告仍来自既有 Starlette BlockingPortal 弃用提示与 Polars 未来返回类型提示，不由 R08 引入。

## 边界与后续

- 固定回放 manifest 是规模与门禁治理清单，不代表 100 篇真实公网文章已抓取或人工标注完成；真实模型/来源验收仍属于 X04/X05。
- GDELT 当前没有分页总量证明，因此不能单独支持 NO_MATCHES；arXiv abstract 只支持摘要范围主张。
- R08 生成 QualityEvaluation/QualityReport，但正式 COMPLETE 仍需 R09 图终止门禁和 R10 输出核验，不能从质量函数直接发送成功终态。
