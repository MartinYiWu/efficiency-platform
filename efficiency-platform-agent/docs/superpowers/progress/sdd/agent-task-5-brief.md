### Task 5: 输出安全阶段、交付事件和后续动作

**Files:**
- Modify: `src/efficiency_platform_agent/harness/service.py`
- Modify: `src/efficiency_platform_agent/contracts/stream_events.py`
- Create: `src/efficiency_platform_agent/runtime/operation_progress.py`
- Create: `src/efficiency_platform_agent/core/operation_progress.py`
- Modify: `src/efficiency_platform_agent/orchestration/builders/operation_runtime.py`
- Modify: `src/efficiency_platform_agent/orchestration/supervisor.py`
- Modify: `src/efficiency_platform_agent/agents/operation/scenarios/service.py`
- Modify: `src/efficiency_platform_agent/runtime/event_hub.py`
- Create: `tests/api/test_operation_delivery_v2_events.py`
- Modify: `tests/contracts/test_stream_event_contracts.py`
- Modify: `tests/runtime/test_event_hub.py`
- Modify: focused Operation Runtime/Supervisor/Scenario service tests required for real node signals.

**Interfaces:**
- Consumes: Run 输出中的 V2 集合和既有 `phase_started`、`deliverable`、`stream_done`。
- Produces: 安全的 `phase_started.payload.phase` 值与单一交付事件；事件名称仍为 V1 协议允许值。

- [ ] **Step 1: 写阶段顺序与敏感信息不泄漏失败测试**

```python
@pytest.mark.asyncio
async def test_v2_stream_exposes_safe_phases_before_delivery() -> None:
    events = await run_operation_v2_stream()
    phases = [item.payload["phase"] for item in events if item.event == "phase_started"]
    assert phases == [
        "understanding_request",
        "collecting_sources",
        "checking_evidence",
        "creating_content",
        "checking_delivery",
    ]
    deliverable = next(item for item in events if item.event == "deliverable")
    assert deliverable.payload["deliverable_set"]["contract_version"] == "deliverable-set/2"
    serialized = "".join(item.model_dump_json() for item in events)
    assert "prompt" not in serialized.lower()
    assert "token" not in serialized.lower()
```

- [ ] **Step 2: 运行测试并确认红灯**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/api/test_operation_delivery_v2_events.py -q
```

Expected: FAIL，当前只有 `scenario_execution` 等内部阶段值。

- [ ] **Step 3: 增加阶段允许清单和安全投影**

在 `stream_events.py` 增加：

```python
OperationVisiblePhase = Literal[
    "understanding_request",
    "collecting_sources",
    "checking_evidence",
    "creating_content",
    "checking_delivery",
]
```

`harness/service.py` 只根据既有执行节点和是否需要研究投影以上值。无研究请求跳过 `collecting_sources` 与 `checking_evidence`，不得为了动画伪造阶段。每个阶段最多发布一次，最终仍只有一个 `stream_done`。

独立复核修订要求：

- 删除所有按用户文本关键词判断研究阶段的逻辑，也不得在 `graph_runtime.execute()` 完整返回后补发伪“开始”阶段。
- Harness 只绑定当前 Run 的异步进度发布上下文；`understanding_request` 来自成功解析的 Submission，研究与创作阶段来自实际 Supervisor 任务/研究调用边界，`checking_delivery` 来自真实质量门禁。某阶段无法获得可靠信号时省略；普通测试图不主动报告就不得出现阶段。
- 阶段报告必须按 Run 隔离、去重，并保持现有单调序号、回放和唯一终态语义。
- ContextVar/窄端口的低层定义放在 `core/operation_progress.py`；`agents`、`orchestration` 只能依赖 core。`runtime/operation_progress.py` 如保留，仅作 Harness/API 兼容重导出，不得修改依赖矩阵绕过架构门禁。

- [ ] **Step 4: 校验后续动作只存在于交付集合**

保持 `next_actions` 在 `DeliverableSetV2` 内，不新增可绕过意图管线的执行事件。SSE 只透传严格校验后的集合；无效动作在 Task 2 已失败关闭。

补充失败关闭要求：

- 顶层版本缺失时读取集合自己的 `contract_version`；集合也缺版本时严格按 V1 校验，禁止 `dict(...)` 原样透传。
- EventHub 递归拒绝嵌套 `model_candidates`、`tool_args`、`raw_page`、`hidden_reasoning`，错误不得回显敏感值；正常业务正文中的普通 `token` 单词必须放行。
- `completed`、`target` 的类型/范围/相互关系必须独立于 `phase` 校验；`phase_started` 缺少 `phase` 必须拒绝。

- [ ] **Step 5: 运行 API、SSE 和重放回归**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/api/test_operation_delivery_v2_events.py tests/api/test_operation_phase_events.py tests/api/test_run_sse_integration.py tests/contracts/test_stream_event_contracts.py -q
```

Expected: PASS；事件序列单调、重放不重复、终态唯一。

- [ ] **Step 6: 更新进度账本并保存文件快照清单**

记录实际阶段序列和跳过规则。
