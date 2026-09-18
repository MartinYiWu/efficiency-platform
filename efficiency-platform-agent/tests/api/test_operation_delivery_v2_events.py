"""验证运营 V2 只通过既有 SSE 协议输出用户安全阶段与单一交付。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.contracts.deliverables import (
    DeliverableSetV1,
    DeliverableSetV2,
    DeliverableV1,
    DeliverySummaryV2,
    NextActionV2,
    PlatformContentDeliverableV2,
    PlatformContentV2,
)
from efficiency_platform_agent.contracts.requests import CreateRunRequestV1
from efficiency_platform_agent.contracts.stream_events import RunStreamEventV1
from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject, JsonValue
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.service import AgentRuntimeService
from efficiency_platform_agent.orchestration.contracts import (
    CheckpointView,
    GraphExecutionResult,
)
from efficiency_platform_agent.persistence.in_memory import (
    FixedClock,
    InMemoryRunEventStore,
    InMemoryRunRepository,
    SequenceIdGenerator,
)
from efficiency_platform_agent.routing.strategy_router import StrategyRouter
from efficiency_platform_agent.runtime.event_hub import EventHub


def _json_value(value: object) -> JsonValue:
    """把已校验模型输出冻结为 Graph 边界使用的不可变 JSON。"""

    if isinstance(value, dict):
        return JsonObject(
            tuple((str(key), _json_value(item)) for key, item in value.items())
        )
    if isinstance(value, list):
        return tuple(_json_value(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("测试输出必须是严格 JSON")


def _v2_delivery(run_id: str) -> DeliverableSetV2:
    """构造包含受控后续动作的最小合法 V2 集合。"""

    deliverable = PlatformContentDeliverableV2(
        deliverable_id="deliverable-1",
        platform="wechat",
        title="AI 行业周报",
        lead="本周值得关注的行业变化。",
        content=PlatformContentV2(
            body_markdown="## 本周观察\n\n这是可直接交付的正文。",
            hashtags=["AI"],
            format_notes=["保留二级标题"],
        ),
        copy_text="AI 行业周报\n\n本周值得关注的行业变化。",
    )
    return DeliverableSetV2(
        run_id=run_id,
        intent_revision=1,
        summary=DeliverySummaryV2(
            message="已完成 1 份内容。", result_count=1, complete=True
        ),
        deliverables=[deliverable],
        next_actions=[
            NextActionV2(
                action_id="action-1",
                action_type="rewrite_for_platform",
                label="改写为小红书版本",
                target_deliverable_id="deliverable-1",
                intent_patch={"channels": ["xiaohongshu"]},
                requires_user_input=True,
            )
        ],
    )


class OperationDeliveryGraph:
    """返回 Task 4 运行时接口形状的最小运营图替身。"""

    def __init__(
        self,
        contract_version: str,
        *,
        invalid_action: bool = False,
        omit_output_version: bool = False,
        omit_set_version: bool = False,
        internal_extra: bool = False,
    ) -> None:
        self.contract_version = contract_version
        self.invalid_action = invalid_action
        self.omit_output_version = omit_output_version
        self.omit_set_version = omit_set_version
        self.internal_extra = internal_extra

    async def execute(self, _selection, state):
        if self.contract_version == "deliverable-set/2":
            result = _v2_delivery(state["run_id"])
            content = result.summary.message
        else:
            result = DeliverableSetV1(
                deliverables=[
                    DeliverableV1(platform="wechat", title="标题", body="正文")
                ],
                summary="已完成 1 份内容。",
            )
            content = result.summary
        deliverable_set = result.model_dump(mode="json")
        if self.invalid_action:
            deliverable_set["next_actions"][0]["action_type"] = "delete_records"
        if self.omit_set_version:
            deliverable_set.pop("contract_version")
        if self.internal_extra:
            deliverable_set["next_actions"][0]["hidden_reasoning"] = "private"
        output_payload = {
            "content": content,
            "deliverable_set": deliverable_set,
        }
        if not self.omit_output_version:
            output_payload["delivery_contract_version"] = result.contract_version
        output = _json_value(output_payload)
        assert isinstance(output, JsonObject)
        return GraphExecutionResult(
            UsageSnapshot(3, 5, 0, estimated=True),
            BudgetGuard().start(
                ExecutionBudget(20, 4, 100, 100, 100, 100),
                now_epoch_ms=state["budget_state"]["started_at_epoch_ms"],
            ),
            CheckpointView(state["run_id"], "s2:multi_agent:1", "cp-operation"),
            (),
            RunStatus.SUCCEEDED,
            output,
        )


def _service(
    contract_version: str = "deliverable-set/2",
    *,
    invalid_action: bool = False,
    omit_output_version: bool = False,
    omit_set_version: bool = False,
    internal_extra: bool = False,
) -> AgentRuntimeService:
    """构造只运行一个受控运营图的 Harness。"""

    return AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(frozenset({StrategyMode.MULTI_AGENT})),
        graph_runtime=OperationDeliveryGraph(
            contract_version,
            invalid_action=invalid_action,
            omit_output_version=omit_output_version,
            omit_set_version=omit_set_version,
            internal_extra=internal_extra,
        ),
        budget_guard=BudgetGuard(),
        budget=ExecutionBudget(20, 4, 100, 100, 100, 100),
        clock=FixedClock(1),
        id_generator=SequenceIdGenerator(),
        event_hub=EventHub(),
    )


def _request(request_id: str, text: str) -> CreateRunRequestV1:
    """构造运营多 Agent 请求。"""

    return CreateRunRequestV1(
        request_id=request_id,
        tenant_id="tenant-1",
        user_id="user-1",
        input_text=text,
        requested_strategy=StrategyMode.MULTI_AGENT,
        strategy_payload_schema_version="operation-strategy-payload/1",
        strategy_payload={"operation_request": {"request": {}}},
    )


async def _run_stream(
    text: str, *, contract_version: str = "deliverable-set/2"
) -> list[RunStreamEventV1]:
    """执行并回放一次完整运营事件流。"""

    service = _service(contract_version)
    queued = await service.create_and_schedule(
        _request(f"request-{contract_version}", text)
    )
    await service.wait_for_background_tasks()
    return await service.event_hub.replay(queued.run_id, 0)


@pytest.mark.asyncio
async def test_plain_graph_does_not_infer_phases_from_research_words() -> None:
    """普通图不报告进度时，Harness 不得按输入关键词伪造阶段。"""

    events = await _run_stream("收集最近 AI 行业动态并撰写公众号内容")
    phases = [item.payload["phase"] for item in events if item.event == "phase_started"]

    assert phases == []
    names = [item.event for item in events]
    assert names.count("deliverable") == 1
    assert names.count("stream_done") == 1
    assert names[-1] == "stream_done"
    deliverable = next(item for item in events if item.event == "deliverable")
    assert (
        deliverable.payload["deliverable_set"]["contract_version"]
        == "deliverable-set/2"
    )
    assert (
        deliverable.payload["deliverable_set"]["next_actions"][0]["action_id"]
        == "action-1"
    )
    assert not any("next_action" in item.event for item in events)
    assert [item.sequence for item in events] == list(range(1, len(events) + 1))
    serialized = "".join(item.model_dump_json() for item in events).lower()
    for forbidden in ("prompt", "token", "model_candidates", "tool_args", "raw_page"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_plain_graph_does_not_infer_content_phases_without_signals() -> None:
    """没有真实进度信号时，非研究请求也不得自动出现创作阶段。"""

    events = await _run_stream("为新品撰写一篇公众号内容")

    assert not any(item.event == "phase_started" for item in events)


@pytest.mark.asyncio
async def test_v2_replay_resumes_without_duplicate_delivery_or_terminal_event() -> None:
    """从游标续读时不重复唯一交付和唯一终态。"""

    service = _service()
    queued = await service.create_and_schedule(
        _request("request-replay", "收集最近 AI 动态并撰写公众号内容")
    )
    await service.wait_for_background_tasks()
    all_events = await service.event_hub.replay(queued.run_id, 0)
    delivery = next(item for item in all_events if item.event == "deliverable")
    cursor = delivery.sequence - 1
    resumed = await service.event_hub.replay(queued.run_id, cursor)

    assert all(item.sequence > cursor for item in resumed)
    assert [item.event for item in resumed].count("deliverable") == 1
    assert [item.event for item in resumed].count("stream_done") == 1


@pytest.mark.asyncio
async def test_v1_delivery_remains_compatible_with_the_existing_event_name() -> None:
    """显式 V1 Run 仍使用同一个 deliverable 事件，不引入第二套协议。"""

    events = await _run_stream(
        "为新品撰写一篇公众号内容", contract_version="deliverable-set/1"
    )

    deliveries = [item for item in events if item.event == "deliverable"]
    assert len(deliveries) == 1
    assert (
        deliveries[0].payload["deliverable_set"]["contract_version"]
        == "deliverable-set/1"
    )


@pytest.mark.asyncio
async def test_v2_stream_rejects_invalid_next_action_before_delivery() -> None:
    """SSE 发布边界必须再次拒绝绕过意图管线的非法动作。"""

    service = _service(invalid_action=True)
    queued = await service.create_and_schedule(
        _request("request-invalid-action", "为新品撰写一篇公众号内容")
    )
    await service.wait_for_background_tasks()
    events = await service.event_hub.replay(queued.run_id, 0)

    assert not any(item.event == "deliverable" for item in events)
    errors = [item for item in events if item.event == "stream_error"]
    assert len(errors) == 1
    assert errors[0].payload["code"] == "DELIVERABLE_SET_INVALID"
    assert [item.event for item in events].count("stream_done") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["invalid_action", "internal_extra"])
async def test_nested_invalid_v2_cannot_bypass_when_output_version_is_missing(
    mutation: str,
) -> None:
    """顶层版本缺失时仍按集合自带 V2 版本严格拒绝嵌套非法字段。"""

    service = _service(
        omit_output_version=True,
        invalid_action=mutation == "invalid_action",
        internal_extra=mutation == "internal_extra",
    )
    queued = await service.create_and_schedule(
        _request(f"request-{mutation}", "为新品撰写一篇公众号内容")
    )
    await service.wait_for_background_tasks()
    events = await service.event_hub.replay(queued.run_id, 0)

    assert not any(item.event == "deliverable" for item in events)
    assert [
        item.payload["code"] for item in events if item.event == "stream_error"
    ] == ["DELIVERABLE_SET_INVALID"]


@pytest.mark.asyncio
async def test_missing_both_versions_is_strictly_normalized_as_v1() -> None:
    """集合和顶层都无版本时只允许严格 V1，并补回标准版本字段。"""

    service = _service(
        "deliverable-set/1", omit_output_version=True, omit_set_version=True
    )
    queued = await service.create_and_schedule(
        _request("request-versionless-v1", "为新品撰写一篇公众号内容")
    )
    await service.wait_for_background_tasks()
    events = await service.event_hub.replay(queued.run_id, 0)

    delivery = next(item for item in events if item.event == "deliverable")
    assert (
        delivery.payload["deliverable_set"]["contract_version"] == "deliverable-set/1"
    )
