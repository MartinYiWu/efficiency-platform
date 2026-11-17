from dataclasses import replace
from importlib import import_module

import pytest

from efficiency_platform_agent.contracts.memory import (
    ConversationScopeModel,
    SourceDependencyModel,
)
from efficiency_platform_agent.memory.summary_contracts import (
    CriticalValue,
    RejectedOption,
    SummaryBasisEvent,
    SummaryEntry,
    SummaryInputSource,
    SummarySegment,
    SummaryWatermark,
)


def fixture():
    api = import_module("efficiency_platform_agent.memory.summary_validation")
    scope = ConversationScopeModel(
        tenant_id="tenant",
        user_id="user",
        domain="hr",
        top_level_agent_id="hr",
        session_kind="CONVERSATION",
        session_id="session",
    )
    ref = SourceDependencyModel(
        source_type="MESSAGE",
        source_id="m1",
        source_version="v1",
        grant_epoch=1,
        source_epoch=2,
        deletion_epoch=3,
    )
    critical = (
        CriticalValue(field_ref="amount", kind="NUMBER", value="123.45"),
        CriticalValue(
            field_ref="date", kind="DATE", value="2026-11-17", timezone="UTC"
        ),
        CriticalValue(field_ref="constraint", kind="CONSTRAINT", value="禁止发出"),
    )
    source = SummaryInputSource(
        source_ref=ref,
        scope=scope,
        sequence=1,
        group_id="g1",
        group_members=(ref,),
        source_dependencies=(ref,),
        completed=True,
        source_kind="ORIGINAL",
        allowed_purposes=frozenset({"SUMMARY"}),
        summary_scope_ref="scope",
        proposals_scope_ref=None,
        summary_retention_ref="retention",
        proposals_retention_ref=None,
        expires_at=100,
        critical_values=critical,
    )
    rejected = RejectedOption(
        claim_ref="A",
        text="拒绝A",
        content_origin="USER_REQUIREMENT",
        decision_status="REJECTED",
        source_refs=(ref,),
        basis_event_ref=ref,
        critical_values=critical,
        reason=None,
    )
    goal = SummaryEntry(
        claim_ref="B",
        text="建议B尚未确认",
        content_origin="MODEL_SUGGESTION",
        decision_status="PROPOSED",
        source_refs=(ref,),
        basis_event_ref=None,
    )
    event = SummaryBasisEvent(
        event_ref=ref,
        claim_ref="A",
        authority="USER",
        content_origin="USER_REQUIREMENT",
        decision_status="REJECTED",
        critical_values=critical,
    )
    segment = SummarySegment(
        segment_id="seg1",
        scope=scope,
        covered_sources=(ref,),
        watermark=SummaryWatermark(
            source_revision=4, first_sequence=1, last_sequence=1
        ),
        goal=goal,
        confirmed_constraints=(),
        decisions=(),
        rejected_options=(rejected,),
        open_questions=(),
        important_refs=(),
        uncertainties=(),
        source_dependencies=(ref,),
        expires_at=90,
    )
    frozen = api.FrozenSummarySources(
        sources=(source,),
        events=(event,),
        required_entries=(goal, rejected),
        session_revision=7,
        source_revision=4,
        mode="SUMMARY",
        memory_policy_version="memory/2",
        authority_ref="trusted-projection/1",
    )
    state = api.SummaryTaskState(
        scope=scope,
        current_sources=(source,),
        session_revision=7,
        source_revision=4,
        now=10,
        original_mode="SUMMARY",
        memory_policy_version="memory/2",
        authority_ref="trusted-projection/1",
    )
    return api, segment, frozen, state


def test_validator_preserves_cas_watermark_and_critical_digest():
    api, segment, frozen, state = fixture()
    result = api.validate_summary(segment, frozen, state)
    assert result.segment == segment
    assert (result.session_revision, result.source_revision) == (7, 4)
    assert result.watermark == segment.watermark
    assert len(result.frozen_critical_digest) == 64
    assert result.source_dependencies == segment.source_dependencies
    assert result.free_text_quality == "UNVERIFIED"
    assert result.commit_status == "NOT_COMMITTED"
    assert "123.45" not in repr(result)


@pytest.mark.parametrize(
    "change",
    [
        {"source_ref": "version"},
        {"expires_at": 10},
        {"allowed_purposes": frozenset()},
        {"scope": "scope"},
        {"source_kind": "SUMMARY"},
        {"completed": False},
        {"group_members": ()},
        {"source_dependencies": ()},
    ],
)
def test_current_source_changes_or_revocation_make_candidate_stale(change):
    api, segment, frozen, state = fixture()
    source = state.current_sources[0]
    if change.get("source_ref") == "version":
        change = {
            "source_ref": source.source_ref.model_copy(update={"source_version": "v2"})
        }
    if change.get("scope") == "scope":
        change = {"scope": source.scope.model_copy(update={"session_id": "other"})}
    state = replace(
        state, current_sources=(source.model_copy(update=change),), source_revision=5
    )
    with pytest.raises(ValueError, match="SUMMARY_STALE"):
        api.validate_summary(segment, frozen, state)


def test_watermark_external_append_is_allowed_without_covering_new_message():
    api, segment, frozen, state = fixture()
    source = state.current_sources[0]
    ref = source.source_ref.model_copy(update={"source_id": "m2"})
    appended = source.model_copy(
        update={
            "source_ref": ref,
            "sequence": 2,
            "group_id": "g2",
            "group_members": (ref,),
            "source_dependencies": (ref,),
        }
    )
    result = api.validate_summary(
        segment,
        frozen,
        replace(
            state,
            current_sources=(source, appended),
            session_revision=8,
            source_revision=5,
        ),
    )
    assert result.watermark.last_sequence == 1
    assert result.session_revision == 7


@pytest.mark.parametrize(
    "mutation",
    [
        "number",
        "date",
        "constraint",
        "reason",
        "confirm",
        "origin",
        "basis",
        "omit_suggestion",
        "expiry",
    ],
)
def test_critical_state_or_basis_corruption_is_rejected(mutation):
    api, segment, frozen, state = fixture()
    rejected = segment.rejected_options[0]
    if mutation in {"number", "date", "constraint"}:
        values = list(rejected.critical_values)
        index = {"number": 0, "date": 1, "constraint": 2}[mutation]
        values[index] = values[index].model_copy(update={"value": "篡改"})
        segment = segment.model_copy(
            update={
                "rejected_options": (
                    rejected.model_copy(update={"critical_values": tuple(values)}),
                )
            }
        )
    elif mutation == "reason":
        segment = segment.model_copy(
            update={
                "rejected_options": (
                    rejected.model_copy(update={"reason": "模型编造原因"}),
                )
            }
        )
    elif mutation == "confirm":
        segment = segment.model_copy(
            update={
                "goal": segment.goal.model_copy(update={"decision_status": "CONFIRMED"})
            }
        )
    elif mutation == "origin":
        segment = segment.model_copy(
            update={
                "goal": segment.goal.model_copy(
                    update={"content_origin": "UNCONFIRMED_INFERENCE"}
                )
            }
        )
    elif mutation == "basis":
        segment = segment.model_copy(
            update={
                "goal": segment.goal.model_copy(
                    update={
                        "basis_event_ref": rejected.source_refs[0].model_copy(
                            update={"source_id": "unknown"}
                        )
                    }
                )
            }
        )
    elif mutation == "omit_suggestion":
        segment = segment.model_copy(
            update={"goal": segment.goal.model_copy(update={"claim_ref": "invented"})}
        )
    else:
        segment = segment.model_copy(update={"expires_at": 101})
    with pytest.raises(ValueError, match="SUMMARY_"):
        api.validate_summary(segment, frozen, state)


def test_original_purpose_and_authority_are_not_candidate_permissions():
    api, segment, frozen, state = fixture()
    for changed in (
        replace(state, original_mode="BOTH"),
        replace(state, authority_ref=""),
        replace(state, memory_policy_version="memory/3"),
    ):
        with pytest.raises(ValueError, match="SUMMARY_"):
            api.validate_summary(segment, frozen, changed)


def test_frozen_digest_uses_typed_fields_not_free_text_quality_scores():
    api, segment, frozen, state = fixture()
    original = api.validate_summary(segment, frozen, state)
    wording = segment.model_copy(
        update={"goal": segment.goal.model_copy(update={"text": "另一种未验叙述"})}
    )
    assert (
        api.validate_summary(wording, frozen, state).frozen_critical_digest
        == original.frozen_critical_digest
    )
    assert original.free_text_quality == "UNVERIFIED"


def test_missing_projection_authority_and_expired_candidate_are_rejected():
    api, segment, frozen, state = fixture()
    with pytest.raises(ValueError, match="SUMMARY_AUTHORITY_BINDING_INVALID"):
        api.validate_summary(
            segment,
            replace(frozen, authority_ref=" "),
            replace(state, authority_ref=" "),
        )
    with pytest.raises(ValueError, match="SUMMARY_SOURCE_EXPIRED"):
        api.validate_summary(segment, frozen, replace(state, now=95))
