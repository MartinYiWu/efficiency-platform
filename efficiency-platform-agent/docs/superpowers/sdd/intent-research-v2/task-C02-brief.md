# C02 实施任务简报：冻结 V2 中立契约与公共测试夹具

## 目标与边界

- 仅实现总计划 C02，不提前实现 C03、I01— I07、R01—R10 或 X01—X05。
- 新增六个 `contracts/*_v2.py` 模块、两份契约测试和两份测试支持文件；仅在确有 fixture 注册需要时修改 `tests/conftest.py`。
- 不进行网络访问、真实模型调用、数据库变更、配置密钥读取、Java/UI 修改或 Git 操作。
- `contracts` 可依赖 Pydantic；不得向 `core` 引入 Pydantic，不得创建运行时实现或动态注册。

## 必须实现的文件与归属

- `contracts/intent_v2.py`：`FieldValue`、`FieldOperation`、`IntentPatchV2`、`IntentFrameV2`、`CapabilityDescriptorV2`、`CapabilityPlanV2`、`IntentDecision`，以及端口签名所需的中立输入/输出类型。
- `contracts/temporal_v2.py`：`TemporalExpression` 判别联合、`ResolvedTimeWindow`。
- `contracts/research_v2.py`：`CountPolicy`、`ResearchBriefV2`、研究策略、结果、质量、补采计划、输出决策与交付包。
- `contracts/research_sources_v2.py`：来源描述/准入/费用、发现与抓取请求、批次、候选、获取内容、抽取文档、尝试记录。
- `contracts/research_evidence_v2.py`：来源文档、事件簇、事实、`EvidenceRef`/来源位置、覆盖率与质量快照。
- `contracts/research_ports_v2.py`：总计划 14 个同步/异步 `Protocol`，签名和返回类型必须严格冻结，不用 `Any` 绕过类型。
- `tests/support/intent_v2_cases.py`、`research_v2_cases.py`：显式 case_id 映射；未知 ID 必须抛 `KeyError`，禁止默认成功。
- `tests/contracts/test_intent_v2.py`、`test_research_v2.py`：行为红灯、最小实现、完整回归。

## 强制契约规则

1. 所有边界模型统一 `extra="forbid"`、`frozen=True`，带固定 `contract_version`/`schema_version`。
2. ID 去首尾空白后非空且有长度上限；revision 非负；一个能力计划最多 8 个目标，依赖 DAG 无环且引用存在。
3. 已解析时间必须为有时区 UTC，且 `start < end`；语义表达的 unknown/null 与显式空集合严格分离。
4. `CountPolicy` 仅支持 exact/at_most/best_effort，`minimum >= 1` 且 `minimum <= target`，target 也必须有合理上限。
5. 来源位置包含消息/文档 ID、Unicode 字符索引 `[start, end)` 与原文片段；验证索引非负且 start < end。C02 只做结构校验，依赖原文的精确切片匹配留给 I01/R06。
6. `ResearchBriefV2` 不接收模型提供的 tenant/user/budget 字段；受信任身份用专门 `TrustedResearchContext` 由后续 builder 注入。额外字段必须拒绝。
7. `scope_hash`/幂等摘要使用排序键、稳定分隔符的规范 JSON；排除 diagnostics、时间耗时、临时错误等非语义字段。同一语义输入摘要稳定。
8. 研究结果明确区分 COMPLETE/PARTIAL/NO_MATCHES/FAILED，不修改既有 `RunStatus`。
9. V1 模型 schema 在 C02 前后保持不变，测试使用固定的当前 schema 快照/摘要证明，而不是修改 V1。
10. 代码注释、docstring 与配置说明使用中文；导出符号明确，无导入副作用。

## 冻结端口

严格落实总计划第 168—187 行的 14 个端口：解释器、Reducer、时间解析、Binder、决策、BriefBuilder、SourceRegistry、SourceProvider、DocumentProvider、Extractor、QualityEvaluator、CollectionPlanner、OutputVerifier、ResearchServiceV2。除 `text`/`anchor`/`timezone` 外所有入参与返回均为显式中立契约；同步/异步不得改变。

## TDD 与验收

- 先写额外字段、非法时间、负 revision、超 8 目标、未知依赖/循环、非法计数、缺失来源位置、身份/预算注入、摘要稳定、未知 fixture ID、V1 schema 未变测试并记录真实行为红灯。
- 最小实现后运行：
  - `.venv/Scripts/python.exe -m pytest tests/contracts/test_intent_v2.py tests/contracts/test_research_v2.py tests/architecture -q`
  - `.venv/Scripts/python.exe -m ruff check src/efficiency_platform_agent/contracts tests/contracts tests/support/intent_v2_cases.py tests/support/research_v2_cases.py`
  - `.venv/Scripts/python.exe -m mypy src/efficiency_platform_agent/contracts/intent_v2.py src/efficiency_platform_agent/contracts/temporal_v2.py src/efficiency_platform_agent/contracts/research_v2.py src/efficiency_platform_agent/contracts/research_sources_v2.py src/efficiency_platform_agent/contracts/research_evidence_v2.py src/efficiency_platform_agent/contracts/research_ports_v2.py`
- 将红灯、绿灯、文件清单、未实现边界和风险写入 `task-C02-report.md`；不要修改实施进度账本，账本由控制器评审后更新。
