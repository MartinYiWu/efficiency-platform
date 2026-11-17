import json
from dataclasses import replace
from importlib import import_module

import pytest

from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.context.selection import select_context
from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderToolCall,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from tests.unit.memory.test_summary_validation import fixture


def setup(history_length=6000, schema_size=0, full_candidate=False):
    validation, segment, frozen, state = fixture()
    if not full_candidate:
        goal = segment.goal.model_copy(update={"text": "B"})
        source = frozen.sources[0].model_copy(update={"critical_values": ()})
        frozen = replace(frozen, sources=(source,), events=(), required_entries=(goal,))
        state = replace(state, current_sources=(source,))
        segment = segment.model_copy(update={"goal": goal, "rejected_options": ()})
    api = import_module("efficiency_platform_agent.context.compaction")
    scope = ExecutionScope(
        state.scope.to_core(), "task", "execution", "subtask", "ANSWER", "hr"
    )
    dependency = frozen.sources[0].source_ref.to_core()
    pieces = (
        ContextPiece(
            "system",
            scope,
            (ProviderMessage("developer", "保留系统合同"),),
            kind="system",
        ),
        ContextPiece(
            "history",
            scope,
            (ProviderMessage("user", "原始历史" * history_length),),
            safety_dependencies=(dependency,),
            kind="history",
            covered_message_ids=("m1",),
        ),
        ContextPiece(
            "facts",
            scope,
            (ProviderMessage("user", "权威HR事实123；评分配置5；asOf=2026-11-17"),),
            kind="business_evidence",
        ),
        ContextPiece(
            "current",
            scope,
            (ProviderMessage("user", "当前用户请求"),),
            kind="current_request",
        ),
    )
    capacity = ModelCapacity(
        "deepseek",
        "deepseek-chat",
        "v1",
        200000,
        190000,
        8192,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "local-evidence",
    )
    limits = WindowLimits(200000, 190000, 1000, 100, 190000)
    request = ProviderRequest(
        "provider/1",
        tuple(m for p in pieces for m in p.messages),
        JsonObject(
            (
                (
                    "tools",
                    (JsonObject((("description", "工具Schema" * schema_size),)),),
                ),
                ("response_format", JsonObject((("type", "json_object"),))),
            )
        ),
        1000,
    )
    counter = ConservativeRequestTokenCounter()
    policy = ContextPolicy(
        "node",
        "window/7",
        scope,
        (dependency,),
        frozenset({"m1"}),
        history_token_limit=150000,
    )
    view = select_context(
        scope,
        policy,
        pieces,
        limits,
        counter=counter,
        capacity=capacity,
        request_template=request,
    )
    baseline = api.CompactionBaseline(
        view, capacity, limits, "window/7", "memory/2", policy
    )
    validated = validation.validate_summary(segment, frozen, state)
    return api, baseline, validated, counter


def rebuild(baseline, counter, *, policy=None, pieces=None):
    policy = policy if policy is not None else baseline.window_policy
    pieces = pieces if pieces is not None else baseline.view.pieces
    request = replace(
        baseline.view.request,
        messages=tuple(message for piece in pieces for message in piece.messages),
    )
    view = select_context(
        policy.scope,
        policy,
        tuple(pieces),
        baseline.limits,
        counter=counter,
        capacity=baseline.capacity,
        request_template=request,
    )
    return replace(baseline, window_policy=policy, view=view)


@pytest.mark.parametrize("role", ["system", "developer"])
def test_historical_system_or_developer_contract_is_not_replaced(role):
    api, baseline, candidate, counter = setup()
    pieces = list(baseline.view.pieces)
    message = ProviderMessage(role, "trusted contract to retain " * 6000)
    pieces[1] = replace(pieces[1], messages=(message,))
    baseline = rebuild(baseline, counter, pieces=pieces)
    assert pieces[1].is_required
    assert pieces[1] in baseline.view.pieces
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.status == "REJECTED"
    assert result.reason == "SUMMARY_COVERAGE_MISMATCH"
    assert result.request is None
    assert message in baseline.view.request.messages


def test_original_zero_summary_slot_rejects_despite_full_request_benefit():
    api, baseline, candidate, counter = setup()
    policy = replace(baseline.window_policy, summary_token_limit=0)
    baseline = rebuild(baseline, counter, policy=policy)
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.status == "REJECTED"
    assert result.reason == "SUMMARY_SLOT_LIMIT"
    assert result.request is None


def test_summary_single_fragment_limit_is_independent_of_full_request_window():
    api, baseline, candidate, counter = setup(full_candidate=True)
    policy = replace(baseline.window_policy, summary_token_limit=10000)
    baseline = rebuild(baseline, counter, policy=policy)
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.status == "REJECTED"
    assert result.reason == "SUMMARY_SLOT_LIMIT"
    assert result.request is None


@pytest.mark.parametrize("summary_limit", [700, 1000])
def test_retained_and_new_summaries_share_original_total_slot(summary_limit):
    api, baseline, candidate, counter = setup()
    history = baseline.view.pieces[1]
    dependency = replace(history.safety_dependencies[0], source_id="m3")
    existing = ContextPiece(
        "existing",
        history.scope,
        (ProviderMessage("user", "existing summary"),),
        (dependency,),
        kind="summary",
        covered_message_ids=("m3",),
    )
    policy = replace(
        baseline.window_policy,
        summary_token_limit=summary_limit,
        authorized_dependencies=baseline.window_policy.authorized_dependencies
        + (dependency,),
        allowed_message_ids=frozenset({"m1", "m3"}),
    )
    pieces = baseline.view.pieces[:2] + (existing,) + baseline.view.pieces[2:]
    baseline = rebuild(baseline, counter, policy=policy, pieces=pieces)
    assert existing in baseline.view.pieces
    result = api.propose_compaction(baseline, candidate, counter)
    if summary_limit == 700:
        assert result.reason == "SUMMARY_SLOT_LIMIT"
        assert result.status == "REJECTED"
        assert result.request is None
    else:
        assert result.status == "BENEFICIAL"
        assert result.request.messages[2] is existing.messages[0]
        summaries = (result.request.messages[1], result.request.messages[2])
        assert all(
            counter.measure_messages((m,), baseline.capacity).total_upper_bound <= 500
            for m in summaries
        )
        assert (
            counter.measure_messages(summaries, baseline.capacity).total_upper_bound
            <= summary_limit
        )


def test_wide_policy_cannot_raise_hard_summary_total_above_1000():
    api, baseline, candidate, counter = setup()
    legal = api.propose_compaction(baseline, candidate, counter)
    assert legal.status == "BENEFICIAL"
    history = baseline.view.pieces[1]
    retained = tuple(
        ContextPiece(
            "existing-" + identifier,
            history.scope,
            (ProviderMessage("user", "existing summary"),),
            (replace(history.safety_dependencies[0], source_id=identifier),),
            kind="summary",
            covered_message_ids=(identifier,),
        )
        for identifier in ("m3", "m4")
    )
    policy = replace(
        baseline.window_policy,
        summary_token_limit=2000,
        authorized_dependencies=baseline.window_policy.authorized_dependencies
        + tuple(piece.safety_dependencies[0] for piece in retained),
        allowed_message_ids=frozenset({"m1", "m3", "m4"}),
    )
    baseline = rebuild(
        baseline,
        counter,
        policy=policy,
        pieces=baseline.view.pieces[:2] + retained + baseline.view.pieces[2:],
    )
    assert all(piece in baseline.view.pieces for piece in retained)
    summaries = (legal.request.messages[1], *(piece.messages[0] for piece in retained))
    assert tuple(
        counter.measure_messages((message,), baseline.capacity).total_upper_bound
        for message in summaries
    ) == (497, 302, 302)
    assert (
        counter.measure_messages(summaries, baseline.capacity).total_upper_bound == 1099
    )
    original = baseline.view.request
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.status == "REJECTED"
    assert result.reason == "SUMMARY_SLOT_LIMIT"
    assert result.request is None
    assert result.T_after < result.T_before
    assert baseline.view.request is original
    assert all(piece.messages[0] in original.messages for piece in retained)


def test_compact_projection_preserves_all_fields_and_is_measured_before_slot_rejection(
    monkeypatch,
):
    api, baseline, candidate, counter = setup(full_candidate=True)
    captured = []
    original = ConservativeRequestTokenCounter.measure_messages

    def measure(self, messages, capacity):
        captured.extend(messages)
        return original(self, messages, capacity)

    monkeypatch.setattr(ConservativeRequestTokenCounter, "measure_messages", measure)
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.reason == "SUMMARY_SLOT_LIMIT"
    payload = json.loads(captured[0].content)
    assert payload["version"] == 1
    assert payload["refs"] == [{"type": "MESSAGE", "id": "m1", "version": "v1"}]
    original_goal = candidate.segment.goal
    assert payload["goal"] == {
        "claim": original_goal.claim_ref,
        "text": original_goal.text,
        "origin": original_goal.content_origin,
        "status": original_goal.decision_status,
        "sources": [0],
        "basis": None,
    }
    original_rejected = candidate.segment.rejected_options[0]
    assert payload["rejected_options"] == [
        {
            "claim": original_rejected.claim_ref,
            "text": original_rejected.text,
            "origin": original_rejected.content_origin,
            "status": original_rejected.decision_status,
            "sources": [0],
            "basis": 0,
            "reason": None,
            "critical": [
                value.model_dump(mode="json")
                for value in original_rejected.critical_values
            ],
        }
    ]
    assert "confirmed_constraints" not in payload


@pytest.mark.parametrize("fragment_tokens", [500, 501])
def test_single_summary_exact_fragment_boundary_uses_actual_counter(fragment_tokens):
    api, baseline, candidate, counter = setup()
    validation = import_module("efficiency_platform_agent.memory.summary_validation")
    goal = candidate.segment.goal.model_copy(
        update={"text": "B" * (fragment_tokens - 496)}
    )
    checked = validation.validate_summary(
        candidate.segment.model_copy(update={"goal": goal}),
        replace(candidate.frozen_sources, required_entries=(goal,)),
        candidate.task_state,
    )
    result = api.propose_compaction(baseline, checked, counter)
    if fragment_tokens == 500:
        assert result.status == "BENEFICIAL"
        assert (
            counter.measure_messages(
                (result.request.messages[1],), baseline.capacity
            ).total_upper_bound
            == 500
        )
    else:
        assert result.status == "REJECTED"
        assert result.reason == "SUMMARY_SLOT_LIMIT"
        assert result.T_after < result.T_before


@pytest.mark.parametrize("mutation", ["verified", "method"])
def test_fragment_measurement_must_be_verified_with_known_serialization(
    monkeypatch, mutation
):
    api, baseline, candidate, counter = setup()
    original = ConservativeRequestTokenCounter.measure_messages

    def measure(self, messages, capacity):
        value = original(self, messages, capacity)
        return (
            replace(value, verified=False)
            if mutation == "verified"
            else replace(value, method="unknown")
        )

    monkeypatch.setattr(ConservativeRequestTokenCounter, "measure_messages", measure)
    assert (
        api.propose_compaction(baseline, candidate, counter).reason
        == "CONTEXT_CAPACITY_UNVERIFIED"
    )


def test_legal_summary_reduces_full_serialized_request_and_baseline_is_immutable():
    api, baseline, candidate, counter = setup(schema_size=100)
    original = baseline.view.request
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.status == "BENEFICIAL"
    assert result.T_after < result.T_before
    assert (
        result.T_before
        == counter.measure(original, baseline.capacity).total_upper_bound
    )
    assert (
        result.T_after
        == counter.measure(result.request, baseline.capacity).total_upper_bound
    )
    assert result.request.options is original.options
    assert result.request.messages[0] is original.messages[0]
    assert result.request.messages[-2:] == original.messages[-2:]
    assert result.safety_dependencies == baseline.view.selected_safety_dependencies
    assert baseline.view.request is original
    assert result.commit_status == "NOT_COMMITTED"
    assert (
        counter.measure_messages(
            (result.request.messages[1],), baseline.capacity
        ).total_upper_bound
        <= 500
    )
    assert (
        counter.measure_messages(
            (result.request.messages[1],), baseline.capacity
        ).total_upper_bound
        <= baseline.window_policy.summary_token_limit
    )


def test_short_text_but_larger_summary_wrapper_is_not_a_benefit():
    api, baseline, candidate, counter = setup(history_length=5, schema_size=1000)
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.status == "REJECTED"
    assert result.reason == "SUMMARY_NOT_BENEFICIAL"
    assert result.T_after >= result.T_before
    assert result.request is None


def test_mutated_authoritative_fact_in_request_cannot_manufacture_benefit():
    api, baseline, candidate, counter = setup()
    changed = replace(
        baseline.view.request,
        messages=baseline.view.request.messages[:-2]
        + (
            ProviderMessage("user", "改写事实"),
            baseline.view.request.messages[-1],
        ),
    )
    baseline = replace(baseline, view=replace(baseline.view, request=changed))
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.reason == "SUMMARY_BASELINE_MISMATCH"


def test_unknown_counter_and_unverified_measurement_or_capacity_fail_closed(
    monkeypatch,
):
    api, baseline, candidate, counter = setup()

    class UnknownCounter:
        def measure(self, request, capacity):
            raise AssertionError("未知计数器不能运行")

    assert (
        api.propose_compaction(baseline, candidate, UnknownCounter()).reason
        == "CONTEXT_CAPACITY_UNVERIFIED"
    )
    assert (
        api.propose_compaction(
            replace(baseline, capacity=replace(baseline.capacity, verified=False)),
            candidate,
            counter,
        ).reason
        == "CONTEXT_CAPACITY_UNVERIFIED"
    )
    monkeypatch.setattr(
        ConservativeRequestTokenCounter,
        "measure",
        lambda *args: TokenMeasurement(1, (), "conservative-utf8/1", False),
    )
    assert (
        api.propose_compaction(baseline, candidate, counter).reason
        == "CONTEXT_CAPACITY_UNVERIFIED"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "window",
        "window_policy",
        "memory_policy",
        "required",
        "coverage",
        "dependencies",
    ],
)
def test_window_versions_required_content_and_source_closure_are_not_relaxed(mutation):
    api, baseline, candidate, counter = setup()
    if mutation == "window":
        baseline = replace(baseline, limits=WindowLimits(200000, 100, 1000, 100, 100))
    elif mutation == "memory_policy":
        baseline = replace(baseline, memory_policy_version="memory/3")
    elif mutation == "window_policy":
        baseline = replace(baseline, window_policy_version="window/8")
    else:
        pieces = list(baseline.view.pieces)
        history = pieces[1]
        if mutation == "required":
            pieces[1] = replace(history, required=True)
        elif mutation == "coverage":
            pieces[1] = replace(history, covered_message_ids=("m1", "extra"))
        else:
            pieces[1] = replace(history, safety_dependencies=())
        baseline = replace(baseline, view=replace(baseline.view, pieces=tuple(pieces)))
    result = api.propose_compaction(baseline, candidate, counter)
    assert result.status == "REJECTED"
    assert result.request is None


def test_dependency_from_actual_input_remains_when_entry_display_refs_are_smaller():
    api, baseline, candidate, counter = setup()
    validation = import_module("efficiency_platform_agent.memory.summary_validation")
    source = candidate.frozen_sources.sources[0]
    hidden = source.source_ref.model_copy(
        update={"source_type": "MEMORY_ITEM", "source_id": "hidden"}
    )
    changed = source.model_copy(
        update={"source_dependencies": (source.source_ref, hidden)}
    )
    frozen = replace(candidate.frozen_sources, sources=(changed,))
    state = replace(candidate.task_state, current_sources=(changed,))
    segment = candidate.segment.model_copy(
        update={"source_dependencies": (source.source_ref, hidden)}
    )
    checked = validation.validate_summary(segment, frozen, state)
    pieces = list(baseline.view.pieces)
    pieces[1] = replace(
        pieces[1], safety_dependencies=(source.source_ref.to_core(), hidden.to_core())
    )
    view = replace(
        baseline.view,
        pieces=tuple(pieces),
        selected_safety_dependencies=pieces[1].safety_dependencies,
    )
    policy = replace(
        baseline.window_policy, authorized_dependencies=pieces[1].safety_dependencies
    )
    result = api.propose_compaction(
        replace(baseline, view=view, window_policy=policy), checked, counter
    )
    assert result.status == "BENEFICIAL"
    assert hidden.to_core() in result.safety_dependencies
    assert result.request is not None
    assert hidden in checked.source_dependencies
    payload = json.loads(result.request.messages[1].content)
    assert all(ref["id"] != "hidden" for ref in payload["refs"])


def test_baseline_policy_authority_cannot_be_widened_by_candidate():
    api, baseline, candidate, counter = setup()
    baseline = replace(
        baseline,
        window_policy=replace(baseline.window_policy, authorized_dependencies=()),
    )
    assert (
        api.propose_compaction(baseline, candidate, counter).reason
        == "SUMMARY_BASELINE_MISMATCH"
    )


def test_complete_historical_tool_group_is_replaced_atomically():
    api, baseline, candidate, counter = setup()
    validation = import_module("efficiency_platform_agent.memory.summary_validation")
    first = candidate.frozen_sources.sources[0]
    second_ref = first.source_ref.model_copy(update={"source_id": "m2"})
    members = (first.source_ref, second_ref)
    sources = (
        first.model_copy(update={"group_members": members}),
        first.model_copy(
            update={
                "source_ref": second_ref,
                "sequence": 2,
                "group_members": members,
                "source_dependencies": (second_ref,),
                "critical_values": (),
            }
        ),
    )
    segment = candidate.segment.model_copy(
        update={
            "covered_sources": members,
            "source_dependencies": members,
            "watermark": candidate.watermark.model_copy(update={"last_sequence": 2}),
        }
    )
    checked = validation.validate_summary(
        segment,
        replace(candidate.frozen_sources, sources=sources),
        replace(candidate.task_state, current_sources=sources),
    )
    pieces = list(baseline.view.pieces)
    group = (
        ProviderMessage(
            "assistant",
            None,
            tool_calls=(ProviderToolCall("call", "readonly", JsonObject()),),
        ),
        ProviderMessage("tool", "历史只读结果" * 6000, tool_call_id="call"),
    )
    deps = tuple(ref.to_core() for ref in members)
    pieces[1] = replace(
        pieces[1],
        messages=group,
        covered_message_ids=("m1", "m2"),
        safety_dependencies=deps,
    )
    request = replace(
        baseline.view.request, messages=tuple(m for p in pieces for m in p.messages)
    )
    view = replace(
        baseline.view,
        pieces=tuple(pieces),
        request=request,
        messages=request.messages,
        selected_safety_dependencies=deps,
    )
    policy = replace(
        baseline.window_policy,
        authorized_dependencies=deps,
        allowed_message_ids=frozenset({"m1", "m2"}),
    )
    result = api.propose_compaction(
        replace(baseline, view=view, window_policy=policy), checked, counter
    )
    assert result.status == "BENEFICIAL"
    assert result.request is not None
    assert all(
        message.role != "tool" and not message.tool_calls
        for message in result.request.messages
    )
    with pytest.raises(ValueError, match="SUMMARY_GROUP_INCOMPLETE"):
        validation.validate_summary(
            candidate.segment,
            replace(candidate.frozen_sources, sources=(sources[0],)),
            replace(candidate.task_state, current_sources=(sources[0],)),
        )
