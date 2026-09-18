### Task 4: 聚合 DeliverableSetV2 并固定 Run 版本

**Files:**
- Modify: `src/efficiency_platform_agent/agents/operation/execution.py`
- Modify: `src/efficiency_platform_agent/agents/operation/operation_agent.py`
- Modify: `src/efficiency_platform_agent/harness/operation_agent_factory.py`
- Modify: `src/efficiency_platform_agent/harness/local_real_factory.py` only to expose and pass through `deliverable_set_contract_version`; do not change service lifecycle.
- Modify: `src/efficiency_platform_agent/harness/research_v2_adapter.py`
- Modify: `src/efficiency_platform_agent/agents/operation/specialists/model_backed_research.py`
- Modify: `src/efficiency_platform_agent/agents/operation/scenarios/runtime_quality.py`
- Modify: `src/efficiency_platform_agent/agents/operation/scenarios/service.py`
- Modify: `src/efficiency_platform_agent/orchestration/builders/operation_runtime.py`
- Create: `tests/integration/test_operation_deliverable_v2.py`
- Modify: `tests/integration/test_operation_agent_runtime.py` and other existing tests only where a legacy V1 fake must explicitly request `deliverable-set/1`; do not rewrite their expected V1 semantics.
- Modify: `tests/unit/harness/test_research_v2_provider_adapter.py`
- Modify: `tests/unit/harness/test_local_real_factory.py` only to make legacy V1 fakes explicit and verify version pass-through.
- Modify: `tests/unit/operation/scenarios/test_quality.py`
- Modify: `tests/unit/operation/scenarios/test_service.py`
- Modify: `tests/acceptance/test_research_v2_closed_loop.py` only to add V2 delivery assertions to existing bounded-collection cases; do not replace existing Research V2 expectations.

**Interfaces:**
- Consumes: Specialist V2 payload、`assemble_set_v2()`、`project_set_v2_to_v1()`。
- Produces: `OperationExecution.deliverables: DeliverableSetV1 | DeliverableSetV2 | None`，Run 输出中的 `deliverable_set` 与 `delivery_contract_version`。

- [ ] **Step 1: 写 V2 聚合、部分结果和 V1 回退失败测试**

```python
@pytest.mark.asyncio
async def test_operation_agent_returns_v2_and_preserves_partial_results() -> None:
    agent = build_test_agent(deliverable_set_contract_version="deliverable-set/2")
    result = await agent.execute(partial_submission())
    assert result.deliverables.contract_version == "deliverable-set/2"
    assert result.deliverables.degraded is True
    assert result.deliverables.deliverables


@pytest.mark.asyncio
async def test_operation_agent_projects_v2_to_v1_only_when_configured() -> None:
    agent = build_test_agent(deliverable_set_contract_version="deliverable-set/1")
    result = await agent.execute(success_submission())
    assert result.deliverables.contract_version == "deliverable-set/1"


@pytest.mark.asyncio
async def test_partial_research_preserves_accepted_items_and_exact_gap() -> None:
    agent = build_test_agent(deliverable_set_contract_version="deliverable-set/2")
    result = await agent.execute(partial_research_submission())
    assert result.status is CompletionStatus.PARTIAL
    assert result.deliverables.degraded is True
    assert result.deliverables.deliverables[0].content.items
    assert [warning.code for warning in result.deliverables.warnings] == [
        "RESEARCH_TARGET_NOT_REACHED"
    ]


@pytest.mark.asyncio
async def test_no_matches_does_not_use_model_knowledge_as_realtime_evidence() -> None:
    agent = build_test_agent(deliverable_set_contract_version="deliverable-set/2")
    result = await agent.execute(no_matches_submission())
    assert result.status is CompletionStatus.COMPLETE
    assert result.deliverables.deliverables == []
    assert result.deliverables.provenance.source_count == 0
```

- [ ] **Step 2: 运行测试并确认红灯**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py -q
```

Expected: FAIL，OperationAgent 仍固定组装 V1。

- [ ] **Step 3: 修改执行和 Agent 聚合类型**

```python
DeliverableSet = DeliverableSetV1 | DeliverableSetV2

@dataclass(frozen=True)
class OperationExecution:
    deliverables: DeliverableSet | None
    status: CompletionStatus
    usage: UsageSnapshot
    # 其余字段保持不变
```

`OperationAgent.__init__` 增加 `deliverable_set_contract_version`，仅接受两个集合版本。V2 路径将 bundle payload 校验为 `OperationDeliverableV2`，调用 `assemble_set_v2()`；显式 V1 Run 继续由 `deliverable/1` Specialist 和既有 V1 assembler 生成，不根据 V2 字段猜测。`project_set_v2_to_v1()` 只作为“已完成 V2 → 旧客户端视图”的显式投影接口，不把同一执行 Run 内部混成两个生成版本。

Research V2 领域结果必须确定性映射：`COMPLETE` 生成完整集合；`PARTIAL` 保留已接纳条目、设置 `degraded=true` 并写入具体缺口 warning；`NO_MATCHES` 返回空交付物和明确完成说明；`FAILED` 不调用模型补事实。`provenance` 直接取已治理的采集时间窗、有效来源数和排序口径。不得由模型设置领域状态或扩大补采预算。

为保留既有边界，允许以下窄改：`ResearchV2ProviderAdapter` 将 `PARTIAL` 投影为带稳定 `RESEARCH_OUTCOME_PARTIAL`/gap warnings 的成功观察，将 `NO_MATCHES` 投影为 `ResearchStatus.EMPTY`，不再误报 FAILED；`ModelBackedResearchSpecialist` 显式接收交付版本，V2 的 EMPTY 不调用模型而返回成功无 bundle 的受控结果；`ScenarioPackService` 仅在 `industry_digest` 且存在确定性 `RESEARCH_NO_MATCHES` warning 时允许 COMPLETE+无 bundle；`OperationAgent` 将其组装为空的 V2 集合。`RuntimeScenarioQualityGate` 对 V2 payload 先做 Task 2 的确定性 V1 质量视图投影再复用既有检查，正式 payload 保持 V2。不得新建第二个研究编排器或在 OperationAgent 旁路调用 Research Service。

- [ ] **Step 4: 在组合根固定版本并透传到 Run 输出**

`build_operation_agent()` 增加：

```python
deliverable_set_contract_version: Literal["deliverable-set/1", "deliverable-set/2"] = "deliverable-set/2"
```

并由该集合版本确定性派生 Specialist 的 `deliverable/1` 或 `deliverable/2`，把两者分别传给 Specialist 与 `OperationAgent`。`operation_runtime.py` 输出增加：

```python
"delivery_contract_version": result.contract_version,
"content": result.summary.message,
"deliverable_set": result.model_dump(mode="json"),
```

该值只用于诊断和前端版本分派，不新增另一种 SSE 事件。

- [ ] **Step 5: 运行集成与既有 OperationAgent 回归**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py tests/integration/test_operation_agent_runtime.py tests/acceptance/test_operation_supervisor.py -q
```

Expected: PASS；V1 测试显式请求 V1，新默认 Run 输出 V2。并运行已有有限补采回归，确认“尚有准入来源和预算才补采”“无新增有效事件立即停止”“达到轮次/时间/预算上限返回 PARTIAL”：

```powershell
.venv\Scripts\python.exe -m pytest tests/acceptance/test_research_v2_closed_loop.py tests/orchestration/research_v2/test_planner.py tests/orchestration/research_v2/test_termination.py -q
```

- [ ] **Step 6: 更新进度账本并保存文件快照清单**

记录默认版本、回退方式、部分结果和集成测试结果。
