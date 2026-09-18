"""正式输出消费同 Run 研究事实；网络和模型仅使用离线边界样本。"""

import asyncio
from importlib import import_module, util

import pytest

from efficiency_platform_agent.orchestration.research_v2.graph import _terminal_patch
from tests.orchestration.research_v2.test_live_stage_runner import (
    advance,
    body_response,
    rss_response,
    semantic_model,
    setup,
)


def materializer_type():
    name = "efficiency_platform_agent.orchestration.research_v2.materializer"
    assert util.find_spec(name) is not None, "LOCAL_LIVE_MATERIALIZER_MISSING"
    return import_module(name).LocalLiveResearchOutcomeMaterializer


async def researched(*, target=1, generator=None):
    cls = materializer_type()
    case = await setup(
        responses=[rss_response(), body_response()],
        model_output=semantic_model,
        target=target,
    )
    runner, state, store, key, _, _, signal = case
    output = cls(
        key=key,
        store=store,
        brief=runner.brief,
        binding=runner.binding,
        deadline_monotonic=runner.context.deadline_monotonic,
        cancellation_signal=signal,
        draft_generator=generator,
    )
    runner.output_stages = output
    for stage in (
        "validate",
        "plan",
        "discover",
        "acquire",
        "normalize",
        "filter",
        "deduplicate",
        "cluster",
        "claims",
        "quality",
    ):
        await advance(runner, state, stage)
    state["refill_rounds"] = state["max_refill_rounds"]
    return case, output


async def delivered(case, output):
    runner, state, *_ = case
    for stage in ("compose", "verify", "render"):
        await advance(runner, state, stage)
    state.update(_terminal_patch(state))
    return await output.materialize(runner.brief, state)


async def test_materializer_preserves_server_evidence_and_verified_content_scope():
    case, output = await researched(target=5)
    runner, state, store, key, connector, model, _ = case
    before = (
        len(connector.calls),
        len(model.calls),
        await runner.binding.port.snapshot(runner.binding.scope),
    )
    outcome = await delivered(case, output)
    assert outcome.outcome == "PARTIAL"
    assert outcome.stop_reason == state["stop_reason"] == "ROUND_LIMIT"
    assert outcome.usable_event_ids == tuple(state["qualified_event_ids"])
    pack = outcome.delivery
    assert pack.requested_count == 5 and pack.delivered_event_count == 1
    assert pack.output_verified and pack.quality_report_id == state["quality_report_id"]
    assert pack.gap_codes == ("COUNT_EXACT_UNMET",)
    source = pack.events[0].citations[0]
    facts = await store.get(key)
    assert source.url == facts.documents[source.document_id].canonical_url
    assert source.content_scope == "full"
    assert source.verification_status == "verified"
    assert source.content_hash == facts.evidence[source.evidence_id].content_hash
    assert (
        source.independent_source_group
        in facts.claims[pack.events[0].claim_ids[0]].source_family_ids
    )
    assert set(pack.evidence_ids) == set(outcome.evidence_ids)
    assert "全文" in pack.content and "核验" in pack.content
    assert any("未生成重要性或热度评分" in item for item in pack.limitations)
    assert (
        len(connector.calls),
        len(model.calls),
        await runner.binding.port.snapshot(runner.binding.scope),
    ) == before


@pytest.mark.parametrize(
    "field,value", [("topic", "different"), ("intent_revision", 2)]
)
async def test_materializer_rejects_wrong_brief(field, value):
    case, output = await researched()
    await delivered(case, output)
    with pytest.raises(ValueError, match="RESEARCH_OUTCOME_BRIEF_MISMATCH"):
        await output.materialize(
            case[0].brief.model_copy(update={field: value}), case[1]
        )


@pytest.mark.parametrize("field", ["qualified_event_ids", "claim_ids", "evidence_ids"])
@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown"])
async def test_materializer_rejects_broken_state_closure(field, mode):
    case, output = await researched()
    await delivered(case, output)
    state = case[1]
    values = state[field]
    state[field] = (
        []
        if mode == "missing"
        else [*values, values[0] if mode == "duplicate" else "unknown"]
    )
    with pytest.raises(
        ValueError, match="RESEARCH_OUTCOME_.*MISMATCH|RESEARCH_OUTPUT_.*INVALID"
    ):
        await output.materialize(case[0].brief, state)


@pytest.mark.parametrize("field", ["user_id", "tenant_id", "run_id", "conversation_id"])
async def test_materializer_cannot_read_foreign_identity(field):
    case, _ = await researched()
    runner, state, store, key, _, _, signal = case
    foreign = key.model_copy(update={field: "foreign"})
    with pytest.raises((KeyError, ValueError)):
        output = materializer_type()(
            key=foreign,
            store=store,
            brief=runner.brief,
            binding=runner.binding,
            cancellation_signal=signal,
            deadline_monotonic=runner.context.deadline_monotonic,
        )
        await output.materialize(runner.brief, state)


@pytest.mark.parametrize("corruption", ["summary", "number", "excerpt", "alias"])
async def test_materializer_rechecks_content_not_only_quality_flag(corruption):
    case, output = await researched()
    _, state, store, key, *_ = case
    facts = await store.get(key)
    docs, claims, evidence = (
        dict(facts.documents),
        dict(facts.claims),
        dict(facts.evidence),
    )
    doc_id, claim_id, ref_id = (
        next(iter(docs)),
        next(iter(claims)),
        next(iter(evidence)),
    )
    if corruption == "summary":
        docs[doc_id] = docs[doc_id].model_copy(update={"content_scope": "summary"})
    elif corruption == "number":
        claims[claim_id] = claims[claim_id].model_copy(
            update={"text": "Acme announced an AI release with 99 improvements."}
        )
    elif corruption == "excerpt":
        ref = evidence[ref_id]
        evidence[ref_id] = ref.model_copy(update={"excerpt": "X" * len(ref.excerpt)})
    else:
        docs[doc_id] = docs[doc_id].model_copy(update={"document_id": "alien"})
    await store.put(
        key,
        facts.model_copy(
            update={"documents": docs, "claims": claims, "evidence": evidence}
        ),
    )
    with pytest.raises(ValueError, match="RESEARCH_OUTPUT_.*INVALID"):
        await output.run_stage("compose", state)


async def test_materializer_rejects_unverified_or_tampered_delivery():
    case, output = await researched()
    await delivered(case, output)
    runner, state, store, key, *_ = case
    state["output_verified"] = False
    with pytest.raises(ValueError, match="RESEARCH_OUTCOME_OUTPUT_UNVERIFIED"):
        await output.materialize(runner.brief, state)
    state["output_verified"] = True
    facts = await store.get(key)
    pack = facts.deliveries[state["output_artifact_id"]]
    await store.put(
        key,
        facts.model_copy(
            update={
                "deliveries": {
                    pack.delivery_id: pack.model_copy(
                        update={"content": "invented output"}
                    )
                }
            }
        ),
    )
    with pytest.raises(ValueError, match="RESEARCH_OUTCOME_DELIVERY_MISMATCH"):
        await output.materialize(runner.brief, state)


async def test_quality_failure_without_gap_cannot_be_escalated_to_complete():
    case, output = await researched()
    _, state, store, key, *_ = case
    facts = await store.get(key)
    report = facts.quality_reports[state["quality_report_id"]]
    await store.put(
        key,
        facts.model_copy(
            update={
                "quality_reports": {
                    report.report_id: report.model_copy(
                        update={"hard_gates_passed": False}
                    )
                },
            }
        ),
    )
    with pytest.raises(ValueError, match="RESEARCH_OUTCOME_QUALITY_MISMATCH"):
        await output.run_stage("compose", state)


@pytest.mark.parametrize(
    "stop,error",
    [("cancelled", asyncio.CancelledError), ("hard_deadline_reached", TimeoutError)],
)
async def test_cancel_or_hard_timeout_never_becomes_domain_success(stop, error):
    case, output = await researched()
    await delivered(case, output)
    case[1][stop] = True
    case[1].update(_terminal_patch(case[1]))
    with pytest.raises(error):
        await output.materialize(case[0].brief, case[1])


async def test_generation_failure_falls_back_without_claiming_complete():
    async def failed_generation(brief, pack):
        raise ValueError("synthetic generation failure")

    case, output = await researched(generator=failed_generation)
    outcome = await delivered(case, output)
    assert outcome.outcome == "PARTIAL"
    assert outcome.delivery.display_status == "degraded_succeeded"
    assert "OUTPUT_GENERATION_FAILED" in outcome.delivery.gap_codes
    assert outcome.delivery.delivered_event_count == 1
    assert case[1]["output_degraded"]


@pytest.mark.parametrize(
    "tampering", ["draft", "decision", "stop_reason", "domain_status"]
)
async def test_materialization_requires_current_verified_draft_and_graph_terminal(
    tampering,
):
    case, output = await researched()
    await delivered(case, output)
    runner, state, store, key, *_ = case
    facts = await store.get(key)
    if tampering == "draft":
        draft_id = facts.stage_artifact_ids["compose"][0]
        draft = facts.drafts[draft_id].model_copy(
            update={"content": "Acme invented 99 improvements."}
        )
        await store.put(key, facts.model_copy(update={"drafts": {draft_id: draft}}))
    elif tampering == "decision":
        await store.put(key, facts.model_copy(update={"output_decisions": {}}))
    else:
        state[tampering] = "PARTIAL" if tampering == "domain_status" else "BUDGET_LIMIT"
    with pytest.raises(ValueError, match="RESEARCH_OUTCOME_.*|RESEARCH_OUTPUT_.*"):
        await output.materialize(runner.brief, state)


async def graph_case(*, count, target):
    from efficiency_platform_agent.orchestration.research_v2.graph import (
        ResearchGraphDependencies,
        build_research_graph,
    )
    from efficiency_platform_agent.providers.research.transport import PinnedResponse

    items = "".join(
        f"<item><title>Acme AI {i}</title><link>https://blog.google/{path}</link><guid>{i}</guid><pubDate>Tue, 15 Sep 2026 00:00:00 GMT</pubDate><description>summary</description></item>"
        for i, path in enumerate(("article", "second", "third")[:count])
    )
    feed = PinnedResponse(
        200,
        {"content-type": "application/rss+xml"},
        (
            f'<rss version="2.0"><channel><title>Google</title><link>https://blog.google/</link><description>feed</description>{items}</channel></rss>'.encode(),
        ),
    )
    bodies = [
        PinnedResponse(
            200,
            {"content-type": "text/plain"},
            (f"Acme announced an AI release for {name}.".encode(),),
        )
        for name in ("Alpha", "Beta", "Gamma")[:count]
    ]
    case = await setup(
        responses=[feed, *bodies, feed],
        model_output=semantic_model,
        target=target,
        three=True,
    )
    runner, state, store, key, _, _, signal = case
    output = materializer_type()(
        key=key,
        store=store,
        brief=runner.brief,
        binding=runner.binding,
        cancellation_signal=signal,
        deadline_monotonic=runner.context.deadline_monotonic,
    )
    runner.output_stages = output
    result = await build_research_graph(ResearchGraphDependencies(runner)).ainvoke(
        state,
        config={"configurable": {"thread_id": "materialized"}, "recursion_limit": 100},
    )
    return case, result, await output.materialize(runner.brief, result)


async def test_formal_graph_materializes_three_actual_of_five_without_expanding_window():
    case, state, outcome = await graph_case(count=3, target=5)
    runner, _, store, key, connector, *_ = case
    facts = await store.get(key)
    assert state["domain_status"] == outcome.outcome == "PARTIAL"
    assert outcome.delivery.delivered_event_count == 3
    assert outcome.delivery.requested_count == 5
    assert len(outcome.delivery.events) == 3
    assert len(connector.calls) == 5
    assert all(
        action.time_window == runner.brief.time_window
        for plan in facts.plans.values()
        for action in plan.actions
    )


async def test_formal_graph_empty_unknown_history_stays_failed():
    _, state, outcome = await graph_case(count=0, target=5)
    assert state["domain_status"] == outcome.outcome == "FAILED"
    assert outcome.delivery is None


async def test_verified_no_matches_routes_through_formal_output_stages():
    from efficiency_platform_agent.orchestration.research_v2.graph import (
        _route_after_quality,
    )

    case, output = await researched()
    _, state, store, key, *_ = case
    facts = await store.get(key)
    report = facts.quality_reports[state["quality_report_id"]].model_copy(
        update={
            "usable_event_ids": (),
            "gaps": (),
            "hard_gates_passed": False,
        }
    )
    artifacts = dict(facts.stage_artifact_ids)
    for name in ("qualified_events", "qualified_claims", "qualified_evidence"):
        artifacts[name] = ()
    await store.put(
        key,
        facts.model_copy(
            update={
                "events": {},
                "claims": {},
                "evidence": {},
                "documents": {},
                "quality_reports": {report.report_id: report},
                "stage_artifact_ids": artifacts,
            }
        ),
    )
    for field in (
        "event_ids",
        "qualified_event_ids",
        "claim_ids",
        "evidence_ids",
        "hard_gap_ids",
    ):
        state[field] = []
    state["complete_empty_plan"] = True
    assert _route_after_quality(state) == "compose"
    outcome = await delivered(case, output)
    assert outcome.outcome == "NO_MATCHES"
    assert outcome.delivery.events == () and outcome.delivery.output_verified
