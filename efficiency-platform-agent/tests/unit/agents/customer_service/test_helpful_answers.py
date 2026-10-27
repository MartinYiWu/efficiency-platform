"""公司证据不足时的有边界帮助与硬守卫。"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_answer_modes import CHUNK_ID, Gateway, decision, evidence

from efficiency_platform_agent.agents.customer_service.answer import generate_answer
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    StructuredModelError,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    GeneralAdvice,
    IntentType,
    SufficiencyDecision,
)
from efficiency_platform_agent.agents.customer_service.sufficiency import (
    judge_sufficiency,
)


def helpful_decision(**changes) -> SufficiencyDecision:
    values = {
        "sufficient": False,
        "supported_claims": (),
        "unsupported_claims": ("未确认公司的报销入口和审批人",),
        "conflicts": (),
        "recommended_mode": AnswerMode.GENERAL_ADVICE,
        "evidence_status": "NO_RELEVANT_EVIDENCE",
        "general_advice_allowed": True,
        "general_advice_scope": ("一般报销材料准备和信息确认方法",),
        "company_specific_unknowns": ("公司报销入口", "审批人"),
    }
    return SufficiencyDecision.model_validate(values | changes)


def general_answer() -> CustomerServiceAnswer:
    return CustomerServiceAnswer(
        contract_version="customer-service-answer/1",
        answer_mode=AnswerMode.GENERAL_ADVICE,
        knowledge_gap="现有资料未确认公司的报销入口和审批人。",
        general_advice=GeneralAdvice(paragraphs=("可以先准备发票和费用用途说明。",)),
    )


async def test_no_hits_use_existing_judge_and_pass_intent() -> None:
    class RecordingGateway(Gateway):
        async def complete(self, stage_key, input_value, output_type):
            assert input_value["evidence"] == []
            assert input_value["intent"]["intent_type"] == "COMPANY_QUERY"
            return await super().complete(stage_key, input_value, output_type)

    expected = helpful_decision()
    gateway = RecordingGateway([expected])
    result = await judge_sufficiency(
        gateway, "公司报销如何申请？", (), intent=decision(IntentType.COMPANY_QUERY)
    )
    assert result == expected
    assert gateway.stages == ["sufficiency"]


async def test_company_question_can_receive_bounded_general_answer_without_citations() -> (
    None
):
    answer = general_answer()
    gateway = Gateway([answer])
    result = await generate_answer(
        gateway,
        question="公司报销如何申请？",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=(),
        sufficiency=helpful_decision(),
    )
    assert result == answer
    assert result.company_sections == ()
    assert gateway.stages == ["answer_general"]


@pytest.mark.parametrize(
    "changes",
    [
        {"general_advice_allowed": False},
        {"general_advice_scope": ()},
        {"evidence_status": None},
        {"evidence_status": "CONFLICT"},
        {"conflicts": ("资料冲突",)},
    ],
)
async def test_general_fallback_requires_explicit_permission_and_unblocked_status(
    changes,
) -> None:
    result = await generate_answer(
        Gateway([]),
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=(),
        sufficiency=helpful_decision(**changes),
    )
    assert result.answer_mode is AnswerMode.INSUFFICIENT_EVIDENCE


async def test_partial_evidence_uses_mixed_mode_and_only_supported_claim_chunks() -> (
    None
):
    unrelated = evidence()[0].model_copy(
        update={"chunk_id": uuid4(), "content": "另一个主题"}
    )
    expected = CustomerServiceAnswer(
        contract_version="customer-service-answer/1",
        answer_mode=AnswerMode.MIXED,
        knowledge_gap="未找到公司审批人的资料。",
        company_sections=(
            {
                "title": "已有公司依据",
                "paragraphs": (
                    {
                        "text": "年假按制度执行。",
                        "supporting_chunk_ids": (CHUNK_ID,),
                    },
                ),
            },
        ),
        general_advice=GeneralAdvice(paragraphs=("可提前整理申请信息。",)),
    )

    class RestrictedGateway(Gateway):
        async def complete(self, stage_key, input_value, output_type):
            assert {item["chunk_id"] for item in input_value["evidence"]} == {
                str(CHUNK_ID)
            }
            return await super().complete(stage_key, input_value, output_type)

    gateway = RestrictedGateway([expected])
    result = await generate_answer(
        gateway,
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=(*evidence(), unrelated),
        sufficiency=helpful_decision(
            evidence_status="PARTIAL",
            recommended_mode=AnswerMode.MIXED,
            supported_claims=(
                {"claim": "年假按制度执行", "supporting_chunk_ids": (CHUNK_ID,)},
            ),
        ),
    )
    assert result == expected
    assert gateway.stages == ["answer_mixed"]


async def test_bad_sufficiency_reference_cannot_enable_general_fallback() -> None:
    result = await judge_sufficiency(
        Gateway(
            [
                helpful_decision(
                    evidence_status="PARTIAL",
                    supported_claims=(
                        {
                            "claim": "公司事实",
                            "supporting_chunk_ids": (uuid4(),),
                        },
                    ),
                )
            ]
        ),
        "问题",
        evidence(),
    )
    assert not result.general_advice_allowed
    answer = await generate_answer(
        Gateway([]),
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=evidence(),
        sufficiency=result,
    )
    assert answer.answer_mode is AnswerMode.INSUFFICIENT_EVIDENCE


async def test_general_generation_calls_real_stream_before_completion() -> None:
    answer = general_answer()
    blocks = []

    class StreamingGateway:
        async def complete(self, *args):
            raise AssertionError("必须使用真正流式模型调用")

        async def stream_complete(self, stage, value, output_type, feed):
            assert stage == "answer_general"
            content = answer.model_dump_json()
            end = content.index('],"') if '],"' in content else len(content) - 1
            feed(content[: end + 1])
            assert blocks, "模型尚未返回时应已输出完整知识缺口"
            feed(content)
            return answer

    result = await generate_answer(
        StreamingGateway(),
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=(),
        sufficiency=helpful_decision(),
        on_block=lambda block, mode: blocks.append((block, mode)),
    )
    assert result == answer
    assert all(mode is AnswerMode.GENERAL_ADVICE for _, mode in blocks)


async def test_service_error_does_not_become_no_hit_or_general_answer() -> None:
    class FailingGateway:
        async def complete(self, *args):
            raise StructuredModelError("PROVIDER_UNAVAILABLE", "模型调用失败")

    with pytest.raises(StructuredModelError, match="模型调用失败"):
        await judge_sufficiency(FailingGateway(), "问题", ())


async def test_nonstream_provider_does_not_emit_fake_incremental_blocks() -> None:
    answer = general_answer()
    blocks = []

    class Gateway:
        async def stream_complete(self, stage, value, output_type, feed):
            return answer

    assert (
        await generate_answer(
            Gateway(),
            question="问题",
            intent=decision(IntentType.GENERAL_QUERY),
            evidence=(),
            sufficiency=None,
            on_block=lambda *block: blocks.append(block),
        )
        == answer
    )
    assert blocks == []


async def test_budget_excluded_empty_pack_is_not_treated_as_no_hit() -> None:
    from test_evidence_pack import build

    pack = await build()
    blocked = pack.model_copy(
        update={
            "entries": (),
            "blocked": True,
            "block_reasons": ("PROTECTED_PARENT_TOO_LARGE",),
            "conflict_screen": None,
        }
    )
    result = await judge_sufficiency(Gateway([]), "问题", blocked)
    assert result.evidence_status != "NO_RELEVANT_EVIDENCE"
    assert not result.conflicts
    assert "预算" in "".join(result.unsupported_claims)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"conflicts": ("资料冲突",)}, "冲突"),
        ({"general_advice_allowed": False}, "未确认"),
        (
            {
                "general_advice_allowed": False,
                "unsupported_claims": ("完整模型输入超过预算",),
            },
            "预算",
        ),
        (
            {
                "general_advice_allowed": False,
                "unsupported_claims": ("充分性判断引用了未入选的证据",),
            },
            "引用",
        ),
    ],
)
async def test_insufficient_reason_preserves_actual_cause(changes, reason) -> None:
    result = await generate_answer(
        Gateway([]),
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=(),
        sufficiency=helpful_decision(**changes),
    )
    assert reason in result.insufficiency_reason


async def test_pack_guards_are_checked_even_when_mode_is_insufficient() -> None:
    from test_evidence_pack import build

    pack = await build()
    result = await generate_answer(
        Gateway([]),
        question="问题",
        intent=decision(IntentType.COMPANY_QUERY),
        evidence=pack.model_copy(
            update={"blocked": True, "block_reasons": ("PROTECTED_PARENT_TOO_LARGE",)}
        ),
        sufficiency=None,
    )
    assert "预算" in result.insufficiency_reason


async def test_streaming_service_publishes_one_snapshot_before_completion() -> None:
    from efficiency_platform_agent.agents.customer_service.graph import GraphResult
    from efficiency_platform_agent.agents.customer_service.renderer import (
        answer_deltas,
        render_answer,
    )
    from efficiency_platform_agent.agents.customer_service.retrieval import (
        RetrievalTrace,
    )
    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
        _Run,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        CustomerServiceRunRequest,
        RunStatus,
        RunView,
    )

    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="snapshot-stream",
        conversation_id=uuid4(),
        tenant_id="dev",
        user_id="1",
        agent_release_id=uuid4(),
        message="报销？",
        history=(),
    )
    run = _Run(
        request,
        RunView(
            run_id=uuid4(), request_id=request.request_id, status=RunStatus.RUNNING
        ),
    )
    service = CustomerServiceRunService(None, None, lambda _: None)
    answer = general_answer()
    rendered = render_answer(answer, ())
    result = GraphResult(
        rendered=rendered,
        stage_summaries=(),
        retrieval_trace=RetrievalTrace("问题", (), (), (), (), (), ()),
        sufficiency=helpful_decision(),
    )
    service._stream_stage(run, "answer_general_fallback", "STARTED")
    for block in answer_deltas(rendered):
        service._stream_answer_block(run, block, answer.answer_mode)
    service._publish_result(run, result)
    snapshots = [
        event for event in run.events if event.event_type == "retrieval.snapshot"
    ]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.payload.stage == "retrieval_snapshot"
    assert snapshot.payload.phase is None
    assert (
        snapshot.payload.retrieval_facts["sufficiency"]["general_advice_allowed"]
        is True
    )
    assert snapshot.sequence < run.events[-1].sequence
    assert run.events[-1].event_type == "answer.completed"
    assert tuple(
        event.payload.delta
        for event in run.events
        if event.event_type == "answer.delta"
    ) == answer_deltas(rendered)


async def test_snapshot_records_actual_mode_and_knowledge_gap() -> None:
    import json

    from test_retrieval_snapshot_repository import RecordingEngine

    from efficiency_platform_agent.agents.customer_service.renderer import render_answer
    from efficiency_platform_agent.agents.customer_service.retrieval import (
        RetrievalTrace,
    )
    from efficiency_platform_agent.agents.customer_service.retrieval_snapshot_repository import (
        MySqlRetrievalSnapshotRepository,
    )

    answer = general_answer()
    engine = RecordingEngine()
    result = SimpleNamespace(
        retrieval_trace=RetrievalTrace("问题", (), (), (), (), (), ()),
        sufficiency=helpful_decision(),
        rendered=render_answer(answer, ()),
    )
    await MySqlRetrievalSnapshotRepository(engine).save(uuid4(), result)
    saved = json.loads(engine.calls[0][1]["sufficiency"])
    assert saved["actual_answer_mode"] == "GENERAL_ADVICE"
    assert saved["knowledge_gap"] == answer.knowledge_gap
    assert saved["company_specific_unknowns"] == ["公司报销入口", "审批人"]


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_real_graph_service_streams_before_model_finishes_and_preserves_outcome(
    outcome,
) -> None:
    import asyncio

    from efficiency_platform_agent.agents.customer_service.graph import (
        CustomerServiceGraph,
    )
    from efficiency_platform_agent.agents.customer_service.retrieval import (
        RetrievalTrace,
    )
    from efficiency_platform_agent.agents.customer_service.service import (
        CustomerServiceRunService,
    )
    from efficiency_platform_agent.agents.customer_service.state import (
        CustomerServiceRunRequest,
        RunStatus,
    )

    entered = asyncio.Event()
    release = asyncio.Event()
    answer = general_answer()
    calls = []
    bundle = SimpleNamespace(
        contract_version="customer-service-release/1",
        rag_policy=SimpleNamespace(rewrite_query_limit=2),
    )

    class Releases:
        async def get(self, _release_id):
            return bundle

    class Retrieval:
        async def search(self, **kwargs):
            return RetrievalTrace("问题", (), (), (), (), (), ())

    class StreamingGateway:
        async def complete(self, stage, value, output_type):
            calls.append(stage)
            if stage == "intent":
                return decision(IntentType.COMPANY_QUERY)
            assert stage == "sufficiency"
            assert value["evidence"] == []
            return helpful_decision()

        async def stream_complete(self, stage, value, output_type, feed):
            calls.append(stage)
            content = answer.model_dump_json()
            feed(content[: content.index('"general_advice"')])
            entered.set()
            await release.wait()
            if outcome == "failure":
                raise StructuredModelError("PROVIDER_UNAVAILABLE", "模型服务中断")
            feed(content)
            return answer

    service = CustomerServiceRunService(
        CustomerServiceGraph(Retrieval()),
        Releases(),
        lambda _: StreamingGateway(),
    )
    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="live-stream-outcome",
        conversation_id=uuid4(),
        tenant_id="dev",
        user_id="1",
        agent_release_id=uuid4(),
        message="报销？",
        history=(),
    )
    view = await service.submit(request)
    await asyncio.wait_for(entered.wait(), 1)
    run = service._runs[view.run_id]
    assert any(event.event_type == "answer.delta" for event in run.events)
    assert not any(event.event_type == "answer.completed" for event in run.events)
    if outcome == "cancel":
        await service.cancel(view.run_id)
    else:
        release.set()
    events = [event async for event in service.events(view.run_id)]
    assert calls == ["intent", "sufficiency", "answer_general"]
    if outcome == "success":
        assert events[-1].event_type == "answer.completed"
        assert events[-1].status is RunStatus.SUCCEEDED
        snapshots = [
            event for event in events if event.event_type == "retrieval.snapshot"
        ]
        assert len(snapshots) == 1
        assert (
            snapshots[0].payload.retrieval_facts["sufficiency"]["evidence_status"]
            == "NO_RELEVANT_EVIDENCE"
        )
    else:
        assert events[-1].status is (
            RunStatus.CANCELLED if outcome == "cancel" else RunStatus.FAILED
        )
        assert not any(event.event_type == "answer.completed" for event in events)
    assert any(
        event.payload.stage == "answer"
        and "通用建议" in (event.payload.public_summary or "")
        for event in events
    )
