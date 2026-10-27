from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.agents.customer_service import graph as graph_module
from efficiency_platform_agent.agents.customer_service.graph import CustomerServiceGraph
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    CustomerServiceRunRequest,
    GeneralAdvice,
    IntentDecision,
    IntentType,
    RunEventPayload,
)


def test_stage_phase_rejects_unknown_value() -> None:
    assert RunEventPayload(stage="intent", phase="STARTED").phase == "STARTED"
    with pytest.raises(ValidationError):
        RunEventPayload(stage="intent", phase="GUESSING")


async def test_general_question_emits_real_stage_boundaries(monkeypatch) -> None:
    answer_entered = asyncio.Event()
    release_answer = asyncio.Event()
    stages: list[tuple[str, str]] = []

    async def classify(_gateway, _request, *, rewrite_query_limit):
        assert rewrite_query_limit == 2
        return IntentDecision(
            intent_type=IntentType.GENERAL_QUERY,
            requires_company_knowledge=False,
            requires_general_advice=True,
            normalized_question="如何安排工作？",
        )

    async def answer(*_args, **_kwargs):
        answer_entered.set()
        await release_answer.wait()
        return CustomerServiceAnswer(
            contract_version="customer-service-answer/1",
            answer_mode=AnswerMode.GENERAL_ADVICE,
            general_advice=GeneralAdvice(paragraphs=("先列出任务。",)),
        )

    monkeypatch.setattr(graph_module, "classify_intent", classify)
    monkeypatch.setattr(graph_module, "generate_answer", answer)
    request = CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="stage-test",
        conversation_id=UUID("80000000-0000-0000-0000-000000000002"),
        tenant_id="dev",
        user_id="1",
        agent_release_id=UUID("80000000-0000-0000-0000-000000000001"),
        message="如何安排工作？",
        history=(),
    )
    task = asyncio.create_task(
        CustomerServiceGraph(object()).run(
            request,
            SimpleNamespace(rag_policy=SimpleNamespace(rewrite_query_limit=2)),
            object(),
            on_stage=lambda stage, phase: stages.append((stage, phase)),
        )
    )
    await asyncio.wait_for(answer_entered.wait(), 1)
    assert stages == [("intent", "COMPLETED"), ("answer", "STARTED")]
    release_answer.set()
    await task
    assert all(stage not in {"retrieval", "verification"} for stage, _ in stages)
