from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.memory import (
    ConversationScopeModel,
    SourceDependencyModel,
)
from efficiency_platform_agent.core.context_control import TokenMeasurement
from efficiency_platform_agent.memory.summary_contracts import (
    CriticalValue,
    RejectedOption,
    SummaryBasisEvent,
    SummaryEntry,
    SummaryInputSource,
    SummarySegment,
    SummaryWatermark,
)
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy


def ref(name: str = "m1", version: str = "1") -> SourceDependencyModel:
    return SourceDependencyModel(
        source_type="MESSAGE",
        source_id=name,
        source_version=version,
        grant_epoch=2,
        source_epoch=3,
        deletion_epoch=4,
    )


def source(**changes: object) -> SummaryInputSource:
    data: dict[str, object] = {
        "source_ref": ref(),
        "scope": scope(),
        "sequence": 1,
        "group_id": "g1",
        "group_members": (ref(),),
        "source_dependencies": (ref(),),
        "completed": True,
        "source_kind": "ORIGINAL",
        "allowed_purposes": frozenset({"SUMMARY", "PROPOSALS"}),
        "summary_scope_ref": "scope",
        "proposals_scope_ref": "scope",
        "summary_retention_ref": "retention",
        "proposals_retention_ref": "retention",
        "expires_at": 100,
        "critical_values": (),
    }
    data.update(changes)
    return SummaryInputSource.model_validate(data)


def scope() -> ConversationScopeModel:
    return ConversationScopeModel(
        tenant_id="tenant",
        user_id="user",
        domain="operations",
        top_level_agent_id="operations",
        session_kind="CONVERSATION",
        session_id="s1",
    )


def entry(**changes: object) -> SummaryEntry:
    data: dict[str, object] = {
        "text": "建议方案A",
        "claim_ref": "option-A",
        "content_origin": "MODEL_SUGGESTION",
        "decision_status": "PROPOSED",
        "source_refs": (ref(),),
        "basis_event_ref": None,
        "critical_values": (),
    }
    data.update(changes)
    return SummaryEntry.model_validate(data)


def segment(**changes: object) -> SummarySegment:
    data: dict[str, object] = {
        "segment_id": "seg1",
        "scope": scope(),
        "covered_sources": (ref(),),
        "watermark": SummaryWatermark(
            source_revision=1, first_sequence=1, last_sequence=1
        ),
        "goal": entry(claim_ref="goal"),
        "confirmed_constraints": (),
        "decisions": (),
        "rejected_options": (),
        "open_questions": (),
        "important_refs": (),
        "uncertainties": (),
        "source_dependencies": (ref(),),
        "expires_at": 100,
    }
    data.update(changes)
    return SummarySegment.model_validate(data)


def validate(
    value: SummarySegment,
    sources: tuple[SummaryInputSource, ...] | None = None,
    events: tuple[SummaryBasisEvent, ...] = (),
) -> None:
    SummaryPolicy().validate_segment(
        value, sources or (source(),), events, now=10, source_revision=1
    )


@pytest.mark.parametrize("mode", ["PROPOSALS", "BOTH"])
def test_sensitive_summary_only_source_denies_before_provider(mode: str) -> None:
    with pytest.raises(ValueError, match="SUMMARY_PURPOSE_DENIED"):
        SummaryPolicy().admit(
            mode, (source(allowed_purposes=frozenset({"SUMMARY"})),), scope(), now=10
        )


def test_summary_only_and_both_compatible_input_are_admitted() -> None:
    policy = SummaryPolicy()
    policy.admit(
        "SUMMARY", (source(allowed_purposes=frozenset({"SUMMARY"})),), scope(), now=10
    )
    policy.admit("BOTH", (source(),), scope(), now=10)
    validate(segment())


@pytest.mark.parametrize(
    "changes",
    [
        {"proposals_scope_ref": "different"},
        {"proposals_retention_ref": "different"},
    ],
)
def test_both_requires_scope_and_retention_compatibility(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="SUMMARY_PURPOSE_INCOMPATIBLE"):
        SummaryPolicy().admit("BOTH", (source(**changes),), scope(), now=10)


def test_model_suggestion_cannot_confirm_itself() -> None:
    with pytest.raises(ValueError, match="SUMMARY_CONFIRMATION_REQUIRED"):
        validate(segment(decisions=(entry(decision_status="CONFIRMED"),)))


def test_unknown_basis_is_rejected_even_for_unconfirmed_inference() -> None:
    with pytest.raises(ValueError, match="SUMMARY_BASIS_UNKNOWN"):
        validate(
            segment(
                uncertainties=(
                    entry(
                        content_origin="UNCONFIRMED_INFERENCE",
                        decision_status="UNRESOLVED",
                        basis_event_ref=ref("unknown"),
                    ),
                )
            )
        )


def test_user_confirmation_can_confirm_suggestion_with_traceable_event() -> None:
    event = SummaryBasisEvent(
        event_ref=ref(),
        claim_ref="option-A",
        authority="USER",
        content_origin="USER_REQUIREMENT",
        decision_status="CONFIRMED",
    )
    validate(
        segment(decisions=(entry(decision_status="CONFIRMED", basis_event_ref=ref()),)),
        events=(event,),
    )


@pytest.mark.parametrize(
    "origin,authority", [("USER_REQUIREMENT", "USER"), ("BUSINESS_FACT", "JAVA")]
)
def test_authoritative_constraint_values_preserved_independently(
    origin: str, authority: str
) -> None:
    values = (
        CriticalValue(field_ref="amount", kind="NUMBER", value="123.45"),
        CriticalValue(
            field_ref="date", kind="DATE", value="2026-11-17", timezone="Asia/Shanghai"
        ),
        CriticalValue(field_ref="constraint", kind="CONSTRAINT", value="不得使用方案B"),
    )
    event = SummaryBasisEvent.model_validate(
        {
            "event_ref": ref(),
            "claim_ref": "option-A",
            "authority": authority,
            "content_origin": origin,
            "decision_status": "CONFIRMED",
            "critical_values": values,
        }
    )
    item = entry(
        content_origin=origin,
        decision_status="CONFIRMED",
        basis_event_ref=ref(),
        critical_values=values,
    )
    inputs = (source(critical_values=values),)
    validate(segment(goal=item, confirmed_constraints=(item,)), inputs, (event,))
    with pytest.raises(ValueError, match="SUMMARY_CRITICAL_VALUES_CHANGED"):
        validate(
            segment(
                goal=item,
                confirmed_constraints=(
                    item.model_copy(update={"critical_values": ()}),
                ),
            ),
            inputs,
            (event,),
        )


def test_business_fact_cannot_be_confirmed_by_model_event() -> None:
    event = SummaryBasisEvent(
        event_ref=ref(),
        claim_ref="option-A",
        authority="MODEL",
        content_origin="MODEL_SUGGESTION",
        decision_status="PROPOSED",
    )
    with pytest.raises(ValueError, match="SUMMARY_AUTHORITY_REQUIRED"):
        validate(
            segment(
                important_refs=(
                    entry(content_origin="BUSINESS_FACT", basis_event_ref=ref()),
                )
            ),
            events=(event,),
        )


@pytest.mark.parametrize("reason", [None, "成本已超限"])
def test_rejected_option_keeps_only_recorded_reason(reason: str | None) -> None:
    event = SummaryBasisEvent(
        event_ref=ref(),
        claim_ref="option-A",
        authority="USER",
        content_origin="USER_REQUIREMENT",
        decision_status="REJECTED",
        rejection_reason=reason,
    )
    item = RejectedOption(
        **entry(decision_status="REJECTED", basis_event_ref=ref()).model_dump(),
        reason=reason,
    )
    validate(segment(goal=item, rejected_options=(item,)), events=(event,))
    with pytest.raises(ValueError, match="SUMMARY_REJECTION_REASON_CHANGED"):
        validate(
            segment(rejected_options=(item.model_copy(update={"reason": "编造理由"}),)),
            events=(event,),
        )
    with pytest.raises(ValueError, match="SUMMARY_REQUIRED_EVENT_MISSING"):
        validate(segment(), events=(event,))


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"covered_sources": (ref("foreign"),)}, "SUMMARY_COVERAGE_MISMATCH"),
        ({"source_dependencies": ()}, "SUMMARY_DEPENDENCIES_INCOMPLETE"),
        ({"expires_at": 101}, "SUMMARY_EXPIRY_EXTENDED"),
        (
            {
                "watermark": SummaryWatermark(
                    source_revision=1, first_sequence=1, last_sequence=2
                )
            },
            "SUMMARY_WATERMARK_MISMATCH",
        ),
    ],
)
def test_segment_metadata_cannot_expand_input(
    changes: dict[str, object], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        validate(segment(**changes))


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"completed": False}, "SUMMARY_SOURCE_INCOMPLETE"),
        ({"source_kind": "SUMMARY"}, "SUMMARY_RECURSION_DENIED"),
        ({"group_members": (ref(), ref("tool-result"))}, "SUMMARY_GROUP_INCOMPLETE"),
        ({"expires_at": 10}, "SUMMARY_SOURCE_EXPIRED"),
        (
            {"scope": scope().model_copy(update={"user_id": "other"})},
            "SUMMARY_SCOPE_MISMATCH",
        ),
    ],
)
def test_invalid_source_is_rejected_before_generation(
    changes: dict[str, object], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        SummaryPolicy().admit("SUMMARY", (source(**changes),), scope(), now=10)


def test_whole_tool_group_and_transitive_dependencies_are_required() -> None:
    dependencies = (ref(), ref("m2"), ref("business"))
    members = (ref(), ref("m2"))
    sources = (
        source(group_members=members, source_dependencies=dependencies),
        source(
            source_ref=ref("m2"),
            sequence=2,
            group_members=members,
            source_dependencies=(ref("m2"),),
        ),
    )
    value = segment(
        covered_sources=members,
        source_dependencies=dependencies,
        watermark=SummaryWatermark(
            source_revision=1, first_sequence=1, last_sequence=2
        ),
    )
    validate(value, sources)
    with pytest.raises(ValueError, match="SUMMARY_DEPENDENCIES_INCOMPLETE"):
        validate(value.model_copy(update={"source_dependencies": members}), sources)


def test_epochs_and_revision_correction_mark_candidate_stale_but_append_does_not() -> (
    None
):
    policy = SummaryPolicy()
    assert (
        policy.candidate_status(segment(), (source(),), source_revision=1) == "PENDING"
    )
    assert (
        policy.candidate_status(
            segment(),
            (
                source(
                    source_ref=ref(version="2"),
                    group_members=(ref(version="2"),),
                    source_dependencies=(ref(version="2"),),
                ),
            ),
            source_revision=2,
        )
        == "STALE"
    )
    changed = ref().model_copy(update={"source_epoch": 5})
    assert (
        policy.candidate_status(
            segment(),
            (
                source(
                    source_ref=changed,
                    group_members=(changed,),
                    source_dependencies=(changed,),
                ),
            ),
            source_revision=2,
        )
        == "STALE"
    )
    assert (
        policy.candidate_status(
            segment(),
            (
                source(),
                source(
                    source_ref=ref("later"),
                    sequence=2,
                    group_id="g2",
                    group_members=(ref("later"),),
                    source_dependencies=(ref("later"),),
                ),
            ),
            source_revision=2,
        )
        == "PENDING"
    )


def test_contract_is_strict_frozen_bounded_and_sensitive_repr_hidden() -> None:
    value = segment(goal=entry(text="敏感测试正文"))
    assert "敏感测试正文" not in repr(value)
    with pytest.raises(ValidationError):
        value.expires_at = 123
    invalid: tuple[Callable[[], object], ...] = (
        lambda: entry(text="x" * 2049),
        lambda: segment(unknown="正文"),
        lambda: segment(expires_at=True),
        lambda: segment(decisions=[entry()]),
    )
    for call in invalid:
        with pytest.raises(ValidationError):
            call()


def test_confirmation_for_another_claim_cannot_confirm_this_suggestion() -> None:
    event = SummaryBasisEvent(
        event_ref=ref(),
        claim_ref="option-A",
        authority="USER",
        content_origin="USER_REQUIREMENT",
        decision_status="CONFIRMED",
    )
    event = event.model_copy(update={"claim_ref": "option-B"})
    with pytest.raises(ValueError, match="SUMMARY_BASIS_CLAIM_MISMATCH"):
        validate(
            segment(
                decisions=(entry(decision_status="CONFIRMED", basis_event_ref=ref()),)
            ),
            events=(event,),
        )


def test_wrong_source_revision_cannot_validate_watermark() -> None:
    with pytest.raises(ValueError, match="SUMMARY_WATERMARK_MISMATCH"):
        validate(
            segment(
                watermark=SummaryWatermark(
                    source_revision=2, first_sequence=1, last_sequence=1
                )
            )
        )


def test_complete_epochs_are_required_not_defaulted_from_omitted_fields() -> None:
    partial = SourceDependencyModel(
        source_type="MESSAGE", source_id="m1", source_version="1"
    )
    with pytest.raises(ValueError, match="SUMMARY_SOURCE_EPOCHS_REQUIRED"):
        SummaryPolicy().admit(
            "SUMMARY",
            (
                source(
                    source_ref=partial,
                    group_members=(partial,),
                    source_dependencies=(partial,),
                ),
            ),
            scope(),
            now=10,
        )


def test_noncontiguous_tool_group_cannot_cross_another_interaction() -> None:
    members = (ref(), ref("m3"))
    sources = (
        source(group_members=members),
        source(
            source_ref=ref("m2"),
            sequence=2,
            group_id="g2",
            group_members=(ref("m2"),),
            source_dependencies=(ref("m2"),),
        ),
        source(
            source_ref=ref("m3"),
            sequence=3,
            group_members=members,
            source_dependencies=(ref("m3"),),
        ),
    )
    with pytest.raises(ValueError, match="SUMMARY_GROUP_INCOMPLETE"):
        SummaryPolicy().admit("SUMMARY", sources, scope(), now=10)


def test_invalid_date_timezone_is_rejected_by_contract() -> None:
    with pytest.raises(ValidationError):
        CriticalValue(
            field_ref="date",
            kind="DATE",
            value="2026-11-17",
            timezone="invented/timezone",
        )


def test_same_claim_cannot_have_conflicting_decision_statuses() -> None:
    value = segment(
        decisions=(entry(),), uncertainties=(entry(decision_status="UNRESOLVED"),)
    )
    with pytest.raises(ValueError, match="SUMMARY_CLAIM_CONFLICT"):
        validate(value)


def test_critical_value_cannot_be_attached_to_another_source() -> None:
    value = CriticalValue(field_ref="amount", kind="NUMBER", value="123.45")
    inputs = (
        source(critical_values=(value,)),
        source(
            source_ref=ref("m2"),
            sequence=2,
            group_id="g2",
            group_members=(ref("m2"),),
            source_dependencies=(ref("m2"),),
        ),
    )
    candidate = segment(
        covered_sources=(ref(), ref("m2")),
        source_dependencies=(ref(), ref("m2")),
        watermark=SummaryWatermark(
            source_revision=1, first_sequence=1, last_sequence=2
        ),
        decisions=(entry(source_refs=(ref("m2"),), critical_values=(value,)),),
    )
    with pytest.raises(ValueError, match="SUMMARY_CRITICAL_SOURCE_MISMATCH"):
        validate(candidate, inputs)


def test_critical_value_field_identity_is_required() -> None:
    with pytest.raises(ValidationError):
        CriticalValue(kind="NUMBER", value="123.45")


@pytest.mark.parametrize(
    "tokens,verified,error",
    [
        (2001, True, "SUMMARY_SOURCE_TOKEN_LIMIT"),
        (100, False, "SUMMARY_TOKEN_EVIDENCE_REQUIRED"),
    ],
)
def test_only_explicit_verified_token_bounds_are_accepted(
    tokens: int,
    verified: bool,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        SummaryPolicy().validate_token_bounds(
            TokenMeasurement(tokens, (), "tokenizer-v1", verified),
            TokenMeasurement(500, (), "tokenizer-v1", True),
            source_limit=2000,
            output_limit=500,
        )


def test_output_count_includes_explicit_published_bound() -> None:
    policy = SummaryPolicy()
    policy.validate_token_bounds(
        TokenMeasurement(2000, (), "tokenizer-v1", True),
        TokenMeasurement(500, (), "tokenizer-v1", True),
        source_limit=2000,
        output_limit=500,
    )
    with pytest.raises(ValueError, match="SUMMARY_OUTPUT_TOKEN_LIMIT"):
        policy.validate_token_bounds(
            TokenMeasurement(2000, (), "tokenizer-v1", True),
            TokenMeasurement(501, (), "tokenizer-v1", True),
            source_limit=2000,
            output_limit=500,
        )


def test_confirmation_cannot_be_borrowed_from_an_independent_source() -> None:
    sources = (
        source(),
        source(
            source_ref=ref("m2"),
            sequence=2,
            group_id="g2",
            group_members=(ref("m2"),),
            source_dependencies=(ref("m2"),),
        ),
    )
    event = SummaryBasisEvent(
        event_ref=ref(),
        claim_ref="option-A",
        authority="USER",
        content_origin="USER_REQUIREMENT",
        decision_status="CONFIRMED",
    )
    candidate = segment(
        covered_sources=(ref(), ref("m2")),
        source_dependencies=(ref(), ref("m2")),
        watermark=SummaryWatermark(
            source_revision=1, first_sequence=1, last_sequence=2
        ),
        decisions=(
            entry(
                source_refs=(ref("m2"),),
                basis_event_ref=ref(),
                decision_status="CONFIRMED",
            ),
        ),
    )
    with pytest.raises(ValueError, match="SUMMARY_BASIS_SOURCE_MISMATCH"):
        validate(candidate, sources, (event,))


def test_confirmation_from_a_real_transitive_source_dependency_is_allowed() -> None:
    event_ref = ref("confirmation")
    sources = (source(source_dependencies=(ref(), event_ref)),)
    event = SummaryBasisEvent(
        event_ref=event_ref,
        claim_ref="option-A",
        authority="USER",
        content_origin="USER_REQUIREMENT",
        decision_status="CONFIRMED",
    )
    validate(
        segment(
            source_dependencies=(ref(), event_ref),
            decisions=(entry(basis_event_ref=event_ref, decision_status="CONFIRMED"),),
        ),
        sources,
        (event,),
    )


@pytest.mark.parametrize(
    "item_status,event_status",
    [
        ("PROPOSED", "UNRESOLVED"),
        ("UNRESOLVED", "PROPOSED"),
    ],
)
def test_declared_basis_must_match_even_unconfirmed_decision_status(
    item_status: str,
    event_status: str,
) -> None:
    event = SummaryBasisEvent.model_validate(
        {
            "event_ref": ref(),
            "claim_ref": "option-A",
            "authority": "MODEL",
            "content_origin": "MODEL_SUGGESTION",
            "decision_status": event_status,
        }
    )
    with pytest.raises(ValueError, match="SUMMARY_BASIS_STATUS_MISMATCH"):
        validate(
            segment(
                decisions=(entry(decision_status=item_status, basis_event_ref=ref()),)
            ),
            events=(event,),
        )


@pytest.mark.parametrize("status", ["PROPOSED", "UNRESOLVED"])
def test_matching_unconfirmed_basis_and_no_basis_are_allowed(status: str) -> None:
    event = SummaryBasisEvent.model_validate(
        {
            "event_ref": ref(),
            "claim_ref": "option-A",
            "authority": "MODEL",
            "content_origin": "MODEL_SUGGESTION",
            "decision_status": status,
        }
    )
    validate(
        segment(decisions=(entry(decision_status=status, basis_event_ref=ref()),)),
        events=(event,),
    )
    validate(segment(decisions=(entry(decision_status=status),)))
