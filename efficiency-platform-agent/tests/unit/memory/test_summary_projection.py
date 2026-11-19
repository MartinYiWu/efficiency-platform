"""v2关键反例：短引用不制造确认，固定硬上限不放宽。"""

import json
from dataclasses import replace

import pytest

from efficiency_platform_agent.core.run import ProviderMessage
from efficiency_platform_agent.memory.summary_contracts import (
    CriticalValue,
    SummaryBasisEvent,
)
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy
from efficiency_platform_agent.memory.summary_projection import (
    SUMMARY_LEGEND,
    project_model_sources,
    render_summary,
)
from tests.unit.context.test_compaction_benefit import setup
from tests.unit.memory.test_summary_contracts import entry, ref, source


def projected():
    message = ref("a" * 36, "b" * 64)
    basis = ref("c" * 36, "d" * 36).model_copy(
        update={"source_type": "USER_PREFERENCE_DECISION"}
    )
    value = CriticalValue(
        field_ref="response.language", kind="CONSTRAINT", value="zh-CN", timezone=None
    )
    src = source(
        source_ref=message,
        group_members=(message,),
        source_dependencies=(message, basis),
        critical_values=(value,),
    )
    required = entry(
        claim_ref="preference:" + "e" * 36 + ":" + "d" * 36,
        text="response.language=zh-CN",
        content_origin="USER_REQUIREMENT",
        decision_status="CONFIRMED",
        source_refs=(message,),
        basis_event_ref=basis,
        critical_values=(value,),
    )
    event = SummaryBasisEvent(
        event_ref=basis,
        claim_ref=required.claim_ref,
        authority="USER",
        content_origin="USER_REQUIREMENT",
        decision_status="CONFIRMED",
        critical_values=(value,),
    )
    return project_model_sources(
        (src,), ("original notes " * 25,), (event,), (required,), 1
    )


def test_alias_unknown_missing_required_and_confirmation_forgery_reject():
    projection = projected()
    answer = {
        "v": 2,
        "goal": {"text": "Advice", "sources": ["s0"]},
        "notes": [],
        "kept": ["r0"],
    }
    segment = projection.candidate(json.dumps(answer), "op")
    assert segment.confirmed_constraints[0] is projection.required[0]
    assert segment.goal.decision_status == "UNRESOLVED"
    assert segment.source_dependencies == projection.sources[0].source_dependencies
    for changed in (
        dict(answer, kept=[]),
        dict(answer, goal={"text": "bad", "sources": ["s99"]}),
        dict(
            answer,
            goal={"text": "bad", "sources": ["s0"], "decision_status": "CONFIRMED"},
        ),
    ):
        with pytest.raises(ValueError):
            projection.candidate(json.dumps(changed), "op")


def test_real_identifiers_fit_fixed_slots_and_legend_is_measured():
    projection = projected()
    segment = projection.candidate(
        json.dumps(
            {
                "v": 2,
                "goal": {"text": "Advice", "sources": ["s0"]},
                "notes": [],
                "kept": ["r0"],
            }
        ),
        "op",
    )
    _, baseline, _, counter = setup()
    rendered = render_summary(segment)
    source_tokens = counter.measure_messages(
        (ProviderMessage("user", projection.user_json),), baseline.capacity
    )
    summary_tokens = counter.measure_messages(
        (ProviderMessage("user", rendered.text),), baseline.capacity
    )
    assert source_tokens.verified and source_tokens.total_upper_bound <= 2000
    assert summary_tokens.total_upper_bound <= 500
    assert "a" * 36 not in rendered.text and "a" * 36 in rendered.aliases_json
    assert (
        counter.measure_messages(
            (
                ProviderMessage("system", SUMMARY_LEGEND),
                ProviderMessage("user", rendered.text),
            ),
            baseline.capacity,
        ).total_upper_bound
        > summary_tokens.total_upper_bound
    )
    with pytest.raises(ValueError, match="SUMMARY_SOURCE_TOKEN_LIMIT"):
        SummaryPolicy().validate_token_bounds(
            replace(source_tokens, total_upper_bound=2001),
            replace(summary_tokens, total_upper_bound=500),
            source_limit=2000,
            output_limit=500,
        )


def test_compaction_measures_legend_in_real_full_request():
    api, baseline, validated, counter = setup(history_length=6000)
    decision = api.propose_compaction(baseline, validated, counter)
    assert decision.status == "BENEFICIAL"
    assert any(m.content == SUMMARY_LEGEND for m in decision.request.messages)
    assert (
        decision.T_after
        == counter.measure(decision.request, baseline.capacity).total_upper_bound
    )
    assert decision.T_after < decision.T_before
