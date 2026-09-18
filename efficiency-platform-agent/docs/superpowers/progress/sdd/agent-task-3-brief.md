### Task 3: 注册 V2 Prompt 并让模型 Specialist 生成类型化内容

**Files:**
- Create: `src/efficiency_platform_agent/prompts/resources/operation/deliverable_generation_v2.j2`
- Modify: `src/efficiency_platform_agent/harness/operation_agent_factory.py`
- Modify: `src/efficiency_platform_agent/agents/operation/specialists/model_backed.py`
- Create: `tests/unit/agents/operation/specialists/test_model_backed_v2.py`
- Modify: `tests/unit/prompts/test_prompt_runtime.py`

**Interfaces:**
- Consumes: `deliverable_kind_for()`、Task 1 V2 Schema、Task 2 验证器。
- Produces: `ModelBackedOperationSpecialist` 构造器新增 `deliverable_contract_version="deliverable/2"` 参数，并返回带 V2 payload 的既有 `SpecialistExecutionResult`。

- [ ] **Step 1: 写 V2 Prompt 注册与 Schema 请求失败测试**

```python
def test_operation_factory_registers_v2_prompt() -> None:
    registry = build_operation_prompt_registry()
    spec = registry.get("operation.deliverable.generation/2")
    assert spec.output_schema_version == "deliverable/2"


@pytest.mark.asyncio
async def test_model_specialist_requests_ranked_digest_schema_for_research() -> None:
    model = RecordingModel(result=ranked_digest_model_output())
    specialist = specialist_for("operation.research.insight", model)
    result = await specialist.run(research_task())
    assert decode_payload(result).get("contract_version") == "deliverable/2"
    assert model.requests[0].json_schema_name == "operation_ranked_digest"
```

- [ ] **Step 2: 运行测试并确认红灯**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/prompts/test_prompt_runtime.py -q
```

Expected: FAIL，V2 Prompt 和构造参数尚不存在。

- [ ] **Step 3: 新增 V2 Prompt 模板**

模板必须完整规定：

```text
你是受中央 Supervisor 管理的运营专家。当前能力为 {{ capability }}，本轮交付类型为 {{ deliverable_kind }}。
只能输出 deliverable/2 对应的严格 JSON；不得输出 Markdown 围栏、解释或隐藏推理。
研究事实只能引用输入 citations 的 citation_id 和 URL；不得生成新来源或宣称系统已核验。
ranked_digest 每条必须包含事实摘要、运营价值、连续排名与 source_refs；没有真实热度时不得写“全网热度排序”。
只有 Research Quality Gate 接纳的事件可进入正式榜单；低置信度单源线索必须排除或明确进入待核实区域，冲突来源不得改写成确定性结论。
platform_content 只生成当前平台独立正文，事实不得超出 evidence；Markdown 禁止 HTML。
小红书、公众号和今日头条必须分别遵守短段落/分节长文/信息价值优先的结构，不得直接复制同一正文。
action_plan 必须包含目标、受众、阶段、行动、指标与透明假设。
diagnosis 必须把证据、判断、优先级、建议与数据缺口分开。
retrospective 必须区分目标、结果、差距、原因和下一步；缺少数据不得伪造指标。
copy_text 固定输出空字符串，由运行时确定性生成；warnings 固定输出空数组。
```

- [ ] **Step 4: 显式注册 V1/V2 Prompt**

在 factory 中提取 `build_operation_prompt_registry()`，保留 V1 注册并增加：

```python
PromptBundleSpec(
    "operation.deliverable.generation/2",
    "1.0.0",
    "operation",
    "operation/deliverable_generation_v2.j2",
    "operation-prompt/2",
    frozenset({"capability", "deliverable_kind"}),
    "deliverable/2",
    frozenset({"balanced"}),
    30_000,
)
```

- [ ] **Step 5: 修改 ModelBackedOperationSpecialist 的版本分派**

构造器增加固定 `deliverable_contract_version`，默认由组合根传入 `deliverable/2`。`run()` 中先调用 `deliverable_kind_for(self.spec.agent_id, raw["platform"], bool(raw["research"]))`，再选择 V1 或对应 V2 子模型的 JSON Schema。V2 校验后必须：

1. 在 `model_backed.py` 内定义私有 Model Draft Schema：业务字段与五类正式内容模型一致，但运行时所有字段固定为 `citations=[]`、`copy_text=""`、`warnings=[]`；模型先通过 Draft Schema，运行时再构造正式非空 `OperationDeliverableV2`，不得放宽正式契约；
2. 用输入来源构造 `CitationV2`，不接受模型新 URL。优先使用 `EvidenceRecord.evidence_id` 作为 `citation_id`；没有 EvidencePack 时使用规范 HTTPS URL 的 SHA-256 前 20 位生成 `citation-{digest20}`。由于现有 EvidencePack 只证明离线字段质量，所有旧来源保守映射为 `source_type="public_page"`、`source_tier="secondary"`、`verification_status="unverified"`；`published_at` 只从已有 epoch 转 UTC ISO，`independent_source_group` 取小写 hostname，禁止根据标题或 publisher 猜 official/API/RSS/verified；
3. 模型内容中的 `source_refs` 只能引用运行时输入的 `citation_id`；排名条目引用完成后，运行时反向计算每条 Citation 的 `supports_item_ids`，非排名内容保持空数组；
4. 用 Task 2 验证器重算 `copy_text`；
5. 将运行时 warnings 转为 `WarningV2`；
6. 继续封装为既有 `OperationDeliverable.payload`，不改变 Supervisor 结果外壳；既有 `DeliverableAssembler.assess()` 需要 V1 时，只对已完成的正式 V2 做确定性 V1 投影用于质量报告，payload 仍保存 V2。

结构校验失败只允许沿用现有剩余预算生成一次修复 Prompt；引用、版本和权限错误不进入修复。若唯一修复响应被 Provider 明确标记为 `PROVIDER_RESPONSE_TRUNCATED`，保留既有相同修复请求的一次传输级重试，因为截断响应没有形成第二次结构修复。Task 3 只增加显式 V2 opt-in，组合根默认仍为 V1；Task 4 聚合链完成后才把新 Run 默认切到 V2。

- [ ] **Step 6: 运行 Specialist、Prompt 与既有引用回归**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/agents/operation/specialists/test_model_backed_citations.py tests/unit/prompts/test_prompt_runtime.py -q
```

Expected: PASS；既有 V1 测试使用显式 `deliverable_contract_version="deliverable/1"`。

- [ ] **Step 7: 更新进度账本并保存文件快照清单**

记录 Prompt ID、Schema 名称、修复边界和测试结果。
