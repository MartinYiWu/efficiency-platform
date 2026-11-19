from dataclasses import replace

from efficiency_platform_agent.context.policy import ContextPiece
from efficiency_platform_agent.core.memory import SourceDependency
from efficiency_platform_agent.core.run import ProviderMessage
from efficiency_platform_agent.memory.summary_selection import (
    CommittedSummary,
    select_committed_summaries,
)
from tests.unit.context.test_compaction_benefit import setup


def fixture():
    _, baseline, candidate, counter = setup()
    segment = candidate.segment
    summary_ref = SourceDependency("SUMMARY", "seg1", "1", 1, 2, 3)
    deps = (*baseline.window_policy.authorized_dependencies, summary_ref)
    policy = replace(baseline.window_policy, authorized_dependencies=deps)
    record = CommittedSummary(
        segment=segment,
        sources=candidate.frozen_sources.sources,
        basis_events=candidate.frozen_sources.events,
        source_revision=segment.watermark.source_revision,
        authority_ref="java-verified/1",
        commit_ref="commit/1",
        status="COMMITTED",
        authorized=True,
        current_dependencies=deps,
        retention_ref="retention/1",
        expires_at=90,
        summary_dependency=summary_ref,
        covered_message_ids=("m1",),
    )
    # 此处旧原文已不在近期窗口，摘要可独立补入；所有事实原文继续保留。
    pieces = tuple(p for p in baseline.view.pieces if p.kind != "history")
    return baseline, counter, policy, record, pieces


def select(records, *, pieces=None, policy=None, now=10):
    baseline, counter, default_policy, _, defaults = fixture()
    return select_committed_summaries(
        defaults if pieces is None else pieces,
        records,
        default_policy if policy is None else policy,
        baseline.capacity,
        counter,
        now=now,
    )


def test_committed_segment_is_bounded_and_required_originals_survive():
    _, _, _, record, pieces = fixture()
    result = select((record,))
    assert result.selected_segments == ("seg1",)
    assert all(piece in result.pieces for piece in pieces)
    summary = next(p for p in result.pieces if p.kind == "summary")
    assert summary.covered_message_ids == ("m1",)
    assert record.summary_dependency in summary.safety_dependencies


def test_recent_complete_original_group_wins_over_summary():
    baseline, _, _, record, _ = fixture()
    result = select((record,), pieces=baseline.view.pieces)
    assert result.selected_segments == ()
    assert result.pieces == baseline.view.pieces
    assert result.omissions[0].reason == "RECENT_OR_REQUIRED_ORIGINAL"


def test_revoked_expired_foreign_scope_and_epoch_changes_do_not_reuse_body():
    _, _, _, record, pieces = fixture()
    stale_body = ContextPiece(
        "old-summary",
        pieces[0].scope,
        (ProviderMessage("user", "旧摘要不得回流"),),
        (record.summary_dependency,),
        kind="summary",
        covered_message_ids=("m1",),
    )
    for changed in (
        replace(record, status="REVOKED"),
        replace(record, authorized=False),
        replace(record, expires_at=5),
        replace(record, current_dependencies=()),
        replace(
            record,
            segment=record.segment.model_copy(
                update={
                    "scope": record.segment.scope.model_copy(
                        update={"user_id": "another"}
                    )
                }
            ),
        ),
    ):
        result = select((changed,), pieces=(*pieces, stale_body))
        assert result.selected_segments == ()
        assert not any(p.kind == "summary" for p in result.pieces)
        assert all(not omission.source_refs for omission in result.omissions)


def test_message_identity_and_recursive_sources_fail_closed():
    _, _, _, record, _ = fixture()
    for changed in (
        replace(record, covered_message_ids=("java-source-uuid",)),
        replace(
            record,
            sources=(record.sources[0].model_copy(update={"source_kind": "SUMMARY"}),),
        ),
    ):
        result = select((changed,))
        assert result.selected_segments == ()


def test_task_only_scope_disables_session_summaries():
    _, _, policy, record, pieces = fixture()
    conversation = replace(
        policy.scope.conversation, session_kind="TASK_ONLY", session_id=None
    )
    scope = replace(policy.scope, conversation=conversation)
    result = select(
        (record,),
        policy=replace(policy, scope=scope),
        pieces=tuple(replace(p, scope=scope) for p in pieces),
    )
    assert result.selected_segments == ()
    assert all(
        p.messages == old.messages for p, old in zip(result.pieces, pieces, strict=True)
    )


def test_three_segments_limit_total_budget_and_oversized_segment():
    baseline, counter, policy, original, pieces = fixture()
    from efficiency_platform_agent.memory.summary_projection import render_summary

    def with_fragment_tokens(record, tokens):
        goal = record.segment.goal.model_copy(update={"text": "B"})
        segment = record.segment.model_copy(update={"goal": goal})
        minimum = counter.measure_messages(
            (ProviderMessage("user", render_summary(segment).text),), baseline.capacity
        ).total_upper_bound
        assert tokens >= minimum
        goal = goal.model_copy(update={"text": "B" * (tokens - minimum + 1)})
        segment = segment.model_copy(update={"goal": goal})
        assert counter.measure_messages(
            (ProviderMessage("user", render_summary(segment).text),), baseline.capacity
        ).total_upper_bound == tokens
        return replace(record, segment=segment)
    records = []
    dependencies = []
    for sequence in range(1, 5):
        ref = original.segment.covered_sources[0].model_copy(
            update={"source_id": f"m{sequence}"}
        )
        source = original.sources[0].model_copy(
            update={
                "source_ref": ref,
                "sequence": sequence,
                "group_id": f"g{sequence}",
                "group_members": (ref,),
                "source_dependencies": (ref,),
            }
        )
        segment = original.segment.model_copy(
            update={
                "segment_id": f"seg{sequence}",
                "covered_sources": (ref,),
                "source_dependencies": (ref,),
                "goal": original.segment.goal.model_copy(
                    update={"source_refs": (ref,)}
                ),
                "watermark": original.segment.watermark.model_copy(
                    update={
                        "first_sequence": sequence,
                        "last_sequence": sequence,
                    }
                ),
            }
        )
        summary_ref = replace(original.summary_dependency, source_id=segment.segment_id)
        deps = (ref.to_core(), summary_ref)
        dependencies.extend(deps)
        records.append(
            replace(
                original,
                segment=segment,
                sources=(source,),
                summary_dependency=summary_ref,
                covered_message_ids=(ref.source_id,),
                current_dependencies=deps,
            )
        )
    policy = replace(
        policy,
        authorized_dependencies=tuple(dependencies),
        allowed_message_ids=frozenset(f"m{i}" for i in range(1, 5)),
    )
    result = select(tuple(records), policy=policy)
    # v2短正文可放入三段，第四段仍受固定段数上限约束。
    assert result.selected_segments == ("seg2", "seg3", "seg4")
    assert result.summary_tokens <= 1000
    assert result.omissions[0].reason == "SUMMARY_SEGMENT_LIMIT"
    assert all(piece in result.pieces for piece in pieces)
    # 三个实际450-token片段超过总1000，较旧段必须省略；单段仍小于500。
    records = [with_fragment_tokens(record, 450) for record in records]
    assert sum(counter.measure_messages(
        (ProviderMessage("user", render_summary(record.segment).text),), baseline.capacity
    ).total_upper_bound for record in records[-3:]) == 1350
    result = select(tuple(records), policy=policy)
    assert result.selected_segments == ("seg3", "seg4")
    assert result.summary_tokens == 900
    assert result.omissions[0].reason == "SUMMARY_SLOT_LIMIT"
    assert result.omissions[0].source_refs
    assert all(piece in result.pieces for piece in pieces)
    limited = select(tuple(records), policy=replace(policy, summary_token_limit=500))
    assert limited.summary_tokens == 450 and limited.selected_segments == ("seg4",)
    large = with_fragment_tokens(records[0], 501)
    oversized = select((large,), policy=policy)
    assert not oversized.selected_segments and oversized.summary_tokens == 0
    assert oversized.omissions[0].reason == "SUMMARY_SLOT_LIMIT"
    assert all(piece in oversized.pieces for piece in pieces)


def test_partial_old_tool_group_and_required_fact_cannot_be_replaced():
    _, _, policy, record, pieces = fixture()
    group = ContextPiece(
        "old-group",
        policy.scope,
        (ProviderMessage("user", "完整旧原文组"),),
        (record.sources[0].source_ref.to_core(),),
        kind="history",
        covered_message_ids=("m1", "m2"),
    )
    result = select(
        (record,),
        pieces=(*pieces, group),
        policy=replace(policy, max_history_messages=0),
    )
    assert result.selected_segments == () and group in result.pieces
    assert result.omissions[0].reason == "SUMMARY_GROUP_INCOMPLETE"
    fact = replace(group, kind="business_evidence", covered_message_ids=("m1",))
    result = select((record,), pieces=(*pieces, fact))
    assert fact in result.pieces and not result.selected_segments
