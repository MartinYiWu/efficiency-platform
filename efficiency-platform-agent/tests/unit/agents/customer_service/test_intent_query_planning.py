"""意图与检索查询联合规划，以及旧 Prompt 回退。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.agents.customer_service import graph as graph_module
from efficiency_platform_agent.agents.customer_service.graph import CustomerServiceGraph
from efficiency_platform_agent.agents.customer_service.intent import classify_intent
from efficiency_platform_agent.agents.customer_service.retrieval import (
    CustomerServiceRetrieval,
    RetrievalTrace,
)
from efficiency_platform_agent.agents.customer_service.state import (
    AnswerMode,
    CustomerServiceAnswer,
    CustomerServiceRunRequest,
    EvidenceContractError,
    HistoryMessage,
    IntentDecision,
    IntentType,
    SufficiencyDecision,
)
from tests.unit.agents.customer_service.test_equivalence import Scenario


def request():
    return CustomerServiceRunRequest(
        contract_version="customer-service-run/1",
        request_id="query-planning",
        conversation_id=uuid4(),
        tenant_id="dev",
        user_id="u",
        agent_release_id=uuid4(),
        message="那紧急情况呢？",
        history=(
            HistoryMessage(role="user", content="请假需要提前申请吗？"),
            HistoryMessage(role="assistant", content="需要提前申请。"),
        ),
    )


def intent_value(kind=IntentType.COMPANY_QUERY):
    return {
        "intent_type": kind,
        "requires_company_knowledge": kind
        in {IntentType.COMPANY_QUERY, IntentType.MIXED_QUERY},
        "requires_general_advice": kind
        in {IntentType.GENERAL_QUERY, IntentType.MIXED_QUERY},
        "normalized_question": "紧急情况请假能事后补交证明吗？",
        "missing_field": "请假类型" if kind is IntentType.AMBIGUOUS_QUERY else None,
    }


def test_old_intent_output_defaults_to_empty_query_plan():
    assert IntentDecision(**intent_value()).retrieval_queries == ()


@pytest.mark.parametrize("query", ["", " ", "\t\n", "\u3000"])
def test_intent_rejects_empty_or_whitespace_query(query):
    with pytest.raises(ValidationError, match="retrieval_queries") as error:
        IntentDecision(**intent_value(), retrieval_queries=(query,))
    assert error.value.errors()[0]["loc"] == ("retrieval_queries", 0)


def test_intent_query_plan_maximum_is_ten():
    queries = tuple(f"问题{i}？" for i in range(10))
    assert (
        IntentDecision(**intent_value(), retrieval_queries=queries).retrieval_queries
        == queries
    )
    with pytest.raises(ValidationError, match="retrieval_queries"):
        IntentDecision(**intent_value(), retrieval_queries=(*queries, "第十一题？"))


@pytest.mark.parametrize("limit", [None, 2])
async def test_intent_planning_preserves_question_history_and_optional_limit(limit):
    inputs = []

    class Gateway:
        async def complete(self, stage, value, output_type):
            assert stage == "intent"
            inputs.append(value)
            return output_type(**intent_value())

    run_request = request()
    if limit is None:
        await classify_intent(Gateway(), run_request)
    else:
        await classify_intent(Gateway(), run_request, rewrite_query_limit=limit)
    expected = {
        "question": run_request.message,
        "history": [item.model_dump(mode="json") for item in run_request.history],
    }
    if limit is not None:
        expected["rewrite_query_limit"] = limit
    assert inputs == [expected]


async def test_planned_queries_skip_rewrite_and_keep_evidence_verification():
    scenario = Scenario()
    embedded = []
    fts_queries = []
    vector_limits = []
    original_embed = scenario.embed
    original_vector_search = scenario.vector_search

    async def embed(queries):
        embedded.append(queries)
        return await original_embed(queries)

    async def vector_search(**kwargs):
        vector_limits.append(kwargs["limit"])
        return await original_vector_search(**kwargs)

    async def fts_search(**kwargs):
        fts_queries.append((kwargs["query"], kwargs["limit"]))
        return ()

    scenario.embed = embed
    scenario.vector_search = vector_search
    scenario.fts_search = fts_search
    trace = await CustomerServiceRetrieval(scenario, scenario, scenario).search(
        tenant_id="test",
        question="如何请假？",
        gateway=scenario,
        bundle=scenario.bundle,
        planned_queries=("紧急情况请假如何补交证明？", "超出策略上限的问句？"),
    )
    assert trace.rewritten_queries == ("紧急情况请假如何补交证明？",)
    assert embedded == [trace.rewritten_queries]
    assert vector_limits == [scenario.bundle.rag_policy.vector_top_k]
    assert fts_queries == [
        (trace.rewritten_queries[0], scenario.bundle.rag_policy.fts_top_k)
    ]
    assert "rewrite" not in scenario.calls
    assert {"embed", "members", "rerank", "parents", "vectors", "equivalence"} <= set(
        scenario.calls
    )
    assert len(trace.reranked_evidence) == 2
    assert len(trace.assembly.selected) == 1


@pytest.mark.parametrize("queries", [None, ()])
async def test_missing_or_empty_plan_preserves_rewrite(queries):
    scenario = Scenario()
    trace = await CustomerServiceRetrieval(scenario, scenario, scenario).search(
        tenant_id="test",
        question="如何请假？",
        gateway=scenario,
        bundle=scenario.bundle,
        planned_queries=queries,
    )
    assert scenario.calls.count("rewrite") == 1
    assert trace.rewritten_queries == ("请假",)


async def test_planned_queries_still_reject_conflicting_index_versions():
    scenario = Scenario()
    conflicting = list(scenario.members[0])
    conflicting[2] = uuid4()
    scenario.members += (tuple(conflicting),)
    with pytest.raises(EvidenceContractError, match="INDEX_DOCUMENT_VERSION_CONFLICT"):
        await CustomerServiceRetrieval(scenario, scenario, scenario).search(
            tenant_id="test",
            question="如何请假？",
            gateway=scenario,
            bundle=scenario.bundle,
            planned_queries=("如何请假？",),
        )
    assert "rewrite" not in scenario.calls
    assert "rerank" not in scenario.calls


@pytest.mark.parametrize("kind", [IntentType.COMPANY_QUERY, IntentType.MIXED_QUERY])
@pytest.mark.parametrize("queries", [None, ("紧急情况请假如何补交证明？",)])
async def test_graph_passes_frozen_query_limit_and_only_present_plans(
    monkeypatch, kind, queries
):
    calls = []
    inputs = []

    class Retrieval:
        async def search(self, **kwargs):
            calls.append(kwargs)
            return RetrievalTrace(kwargs["question"], (), (), (), (), (), ())

    class Gateway:
        async def complete(self, stage, value, output_type):
            assert stage == "intent"
            inputs.append(value)
            value = intent_value(kind)
            if queries is not None:
                value["retrieval_queries"] = queries
            return output_type(**value)

    async def judge(*_args, **_kwargs):
        return SufficiencyDecision(
            sufficient=False,
            supported_claims=(),
            unsupported_claims=(),
            conflicts=(),
            recommended_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
        )

    async def answer(*_args, **_kwargs):
        return CustomerServiceAnswer(
            contract_version="customer-service-answer/1",
            answer_mode=AnswerMode.INSUFFICIENT_EVIDENCE,
            insufficiency_reason="没有匹配证据。",
        )

    monkeypatch.setattr(graph_module, "judge_sufficiency", judge)
    monkeypatch.setattr(graph_module, "generate_answer", answer)
    run_request = request()
    bundle = SimpleNamespace(
        contract_version="customer-service-release/1",
        rag_policy=SimpleNamespace(rewrite_query_limit=2),
    )
    await CustomerServiceGraph(Retrieval()).run(run_request, bundle, Gateway())
    assert inputs[0]["rewrite_query_limit"] == 2
    assert inputs[0]["history"] == [
        item.model_dump(mode="json") for item in run_request.history
    ]
    assert len(calls) == 1
    assert calls[0]["question"] == intent_value()["normalized_question"]
    assert calls[0]["bundle"] is bundle
    if queries:
        assert calls[0]["planned_queries"] == queries
    else:
        assert "planned_queries" not in calls[0]


@pytest.mark.parametrize("kind", [IntentType.GENERAL_QUERY, IntentType.AMBIGUOUS_QUERY])
async def test_non_company_intent_does_not_retrieve_even_with_query_plan(
    monkeypatch, kind
):
    class Gateway:
        async def complete(self, stage, _value, output_type):
            assert stage == "intent"
            return output_type(**intent_value(kind), retrieval_queries=("如何请假？",))

    async def answer(*_args, **_kwargs):
        return CustomerServiceAnswer(
            contract_version="customer-service-answer/1",
            answer_mode=AnswerMode.CLARIFY,
            clarification_question="请问是哪种请假？",
        )

    monkeypatch.setattr(graph_module, "generate_answer", answer)
    bundle = SimpleNamespace(rag_policy=SimpleNamespace(rewrite_query_limit=2))
    result = await CustomerServiceGraph(object()).run(request(), bundle, Gateway())
    assert result.retrieval_trace is None
