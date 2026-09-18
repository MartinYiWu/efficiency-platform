## Task 6：安全、兼容和全量 Agent 门禁

### 允许范围

- Modify: `src/efficiency_platform_agent/capabilities/quality/deliverable_v2.py`
- Create: `tests/security/test_deliverable_v2_safety.py`
- Modify: `tests/unit/capabilities/quality/test_deliverable_v2.py`
- Modify: `tests/governance/test_operation_chat_acceptance.py`
- Modify: `tests/fixtures/s7/operation_cases_v1.jsonl` only if an explicit V1 version flag is necessary; do not rewrite V1 semantics.
- Modify: `tests/unit/capabilities/research_v2/_delivery_support.py` only if the shared fictional source title itself contains a literal script tag; replace it with safe fixture text without changing research behavior or removing dedicated malicious-content tests.
- Modify: `tests/unit/capabilities/research_v2/test_delivery.py` only to align the one literal shared-title assertion with safe fixture text and add a direct malicious-source-title renderer assertion proving HTML/Markdown escaping; do not weaken escaping or malicious-content coverage.
- Modify: `docs/superpowers/progress/2026-09-17-运营Agent专业化交付与质量闭环-进度.md`

### 目标与不变量

1. `DeliveryPresentationValidator`/`assemble_set_v2` 对 V2 的引用与用户可见文本失败关闭：拒绝非 HTTPS、缺 hostname、带用户名/密码的 URL；拒绝 `<script`、`javascript:`、`system prompt`、`hidden reasoning` 等明确主动内容或内部提示标记。
2. 检查覆盖标题、导语、Markdown、可见纯文案和后续动作标签；不得用宽泛中文关键词误杀普通业务内容。引用闭包、V1 原生投影与受控动作语义不回退。
3. 先增加恶意 URL、内部标记、跨引用与安全正文的 RED 测试，再做最小实现。`tests/security/test_deliverable_v2_safety.py` 必须是可独立运行的安全边界测试。
4. 所有 V1 fixture 语义保持不变；只有必要时增加显式版本字段。
5. 在正式进度账本内给出经 `DeliverableSetV2.model_validate()` 验证的完整离线 JSON 样例：9 条热点、2 条 `example.test` 来源、一个 `rewrite_for_platform` 动作、provenance、空 warnings。禁止真实令牌、用户数据和伪造真实新闻。
6. 运行 ruff format/check、mypy src、compileall、指定安全/治理/Task 1-5 回归及完整 pytest；当前已知 LiveAcceptance 失败不得掩盖，必须复现并以调用链判定是否仍属无关基线问题。不得运行 Git。

### 独立复核重点

- 纯 URL 规则是否涵盖 credentials、scheme、hostname、大小写/空白边界；
- 文本检查是否递归覆盖所有公开字段且不会扫描或修改结构化内部运行态；
- V2 错误、引用越权和版本错误不会作为 V1 成功；
- 冻结样例能真实经模型校验且符合计数和 URL 约束；
- 全量失败的归因与实际执行证据明确分离。
