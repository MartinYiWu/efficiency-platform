"""离线完整请求压缩收益提案；不启用摘要、不更新基线、不执行Java CAS。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from efficiency_platform_agent.context.policy import (
    ContextPiece,
    ContextPolicy,
    render_context_messages,
)
from efficiency_platform_agent.context.selection import ContextView
from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenCounter,
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.memory import SourceDependency
from efficiency_platform_agent.core.run import ProviderMessage, ProviderRequest
from efficiency_platform_agent.memory.summary_projection import (
    SUMMARY_LEGEND,
    render_summary,
)
from efficiency_platform_agent.memory.summary_validation import (
    ValidatedSummary,
    validate_summary,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)


@dataclass(frozen=True, slots=True)
class CompactionBaseline:
    view: ContextView = field(repr=False)
    capacity: ModelCapacity
    limits: WindowLimits
    window_policy_version: str
    memory_policy_version: str
    window_policy: ContextPolicy


@dataclass(frozen=True, slots=True)
class CompactionDecision:
    status: str
    reason: str
    T_before: int | None = None
    T_after: int | None = None
    request: ProviderRequest | None = field(default=None, repr=False)
    safety_dependencies: tuple[SourceDependency, ...] = ()
    commit_status: str = field(default="NOT_COMMITTED", init=False)


def propose_compaction(
    baseline_view: CompactionBaseline,
    candidate: ValidatedSummary,
    counter: TokenCounter,
) -> CompactionDecision:
    baseline = baseline_view
    if (
        type(baseline) is not CompactionBaseline
        or type(candidate) is not ValidatedSummary
    ):
        return CompactionDecision("REJECTED", "SUMMARY_VALIDATION_REQUIRED")
    capacity, limits, view = baseline.capacity, baseline.limits, baseline.view
    if (
        type(counter) is not ConservativeRequestTokenCounter
        or not capacity.verified
        or limits.context_window_tokens > capacity.context_window_tokens
        or limits.output_reserve_tokens > capacity.max_output_tokens
        or (
            capacity.max_input_tokens is not None
            and limits.input_cap() > capacity.max_input_tokens
        )
    ):
        return CompactionDecision("REJECTED", "CONTEXT_CAPACITY_UNVERIFIED")
    if (
        not baseline.window_policy_version
        or baseline.window_policy_version != baseline.window_policy.version
        or baseline.memory_policy_version != candidate.memory_policy_version
    ):
        return CompactionDecision("REJECTED", "SUMMARY_POLICY_MISMATCH")
    try:
        checked = validate_summary(
            candidate.segment, candidate.frozen_sources, candidate.task_state
        )
    except ValueError:
        return CompactionDecision("REJECTED", "SUMMARY_VALIDATION_FAILED")
    if checked != candidate:
        return CompactionDecision("REJECTED", "SUMMARY_VALIDATION_FAILED")
    pieces = view.pieces
    if (
        render_context_messages(baseline.window_policy,pieces)
        != view.request.messages
        or view.messages != view.request.messages
        or tuple(dict.fromkeys(dep for p in pieces for dep in p.safety_dependencies))
        != view.selected_safety_dependencies
        or any(p.scope != baseline.window_policy.scope for p in pieces)
        or any(
            not set(p.safety_dependencies).issubset(
                baseline.window_policy.authorized_dependencies
            )
            or not set(p.covered_message_ids).issubset(
                baseline.window_policy.allowed_message_ids
            )
            for p in pieces
        )
    ):
        return CompactionDecision("REJECTED", "SUMMARY_BASELINE_MISMATCH")
    segment = candidate.segment
    coverage = tuple(ref.source_id for ref in segment.covered_sources)
    if any(ref.source_type != "MESSAGE" for ref in segment.covered_sources):
        return CompactionDecision("REJECTED", "SUMMARY_COVERAGE_MISMATCH")
    removed = tuple(
        p for p in pieces if set(p.covered_message_ids).intersection(coverage)
    )
    if (
        not removed
        or tuple(identifier for p in removed for identifier in p.covered_message_ids)
        != coverage
        or any(
            p.kind != "history"
            or (
                p.is_required
                and (
                    p.required
                    or any(m.role in {"system", "developer"} for m in p.messages)
                    or not any(m.tool_calls for m in p.messages)
                )
            )
            or p.scope.conversation != segment.scope.to_core()
            for p in removed
        )
        or any(
            p.kind == "summary" and set(p.covered_message_ids).intersection(coverage)
            for p in pieces
        )
    ):
        return CompactionDecision("REJECTED", "SUMMARY_COVERAGE_MISMATCH")
    dependencies = tuple(ref.to_core() for ref in segment.source_dependencies)
    if set(dependencies) != {dep for p in removed for dep in p.safety_dependencies}:
        return CompactionDecision("REJECTED", "SUMMARY_DEPENDENCIES_INCOMPLETE")
    rendered = render_summary(segment)
    summary = ContextPiece(
        "compaction:" + segment.segment_id,
        removed[0].scope,
        (ProviderMessage("user", rendered.text),),
        dependencies,
        kind="summary",
        covered_message_ids=coverage,
        projection_aliases=((segment.segment_id, rendered.aliases_json),),
    )
    proposed: list[ContextPiece] = []
    for piece in pieces:
        if piece is removed[0]:
            if not any(
                p.piece_id == "summary-legend/2"
                and p.messages == (ProviderMessage("system", SUMMARY_LEGEND),)
                for p in pieces
            ):
                proposed.append(
                    ContextPiece(
                        "summary-legend/2",
                        removed[0].scope,
                        (ProviderMessage("system", SUMMARY_LEGEND),),
                        required=True,
                        kind="system",
                    )
                )
            proposed.append(summary)
        if piece not in removed:
            proposed.append(piece)
    request = replace(
        view.request, messages=render_context_messages(baseline.window_policy,tuple(proposed))
    )
    after_dependencies = tuple(
        dict.fromkeys(dep for p in proposed for dep in p.safety_dependencies)
    )
    if set(after_dependencies) != set(view.selected_safety_dependencies):
        return CompactionDecision("REJECTED", "SUMMARY_DEPENDENCIES_INCOMPLETE")
    try:
        before = counter.measure(view.request, capacity)
        after = counter.measure(request, capacity)
    except ValueError:
        return CompactionDecision("REJECTED", "CONTEXT_CAPACITY_UNVERIFIED")
    if any(
        not isinstance(value, TokenMeasurement)
        or not value.verified
        or value.method != capacity.tokenizer_ref
        for value in (before, after)
    ):
        return CompactionDecision("REJECTED", "CONTEXT_CAPACITY_UNVERIFIED")
    t_before, t_after = before.total_upper_bound, after.total_upper_bound
    summaries = tuple(piece for piece in proposed if piece.kind == "summary")
    for messages, slot_limit in (
        *((piece.messages, 500) for piece in summaries),
        (
            tuple(message for piece in summaries for message in piece.messages),
            min(1000, baseline.window_policy.summary_token_limit),
        ),
    ):
        try:
            measurement = counter.measure_messages(messages, capacity)
        except ValueError:
            return CompactionDecision("REJECTED", "CONTEXT_CAPACITY_UNVERIFIED")
        if (
            not isinstance(measurement, TokenMeasurement)
            or not measurement.verified
            or measurement.method != "conservative-utf8-fragment/1"
        ):
            return CompactionDecision("REJECTED", "CONTEXT_CAPACITY_UNVERIFIED")
        if measurement.total_upper_bound > slot_limit:
            return CompactionDecision(
                "REJECTED", "SUMMARY_SLOT_LIMIT", t_before, t_after
            )
    if t_after >= t_before:
        return CompactionDecision(
            "REJECTED", "SUMMARY_NOT_BENEFICIAL", t_before, t_after
        )
    if t_after > limits.input_cap():
        return CompactionDecision(
            "REJECTED", "CONTEXT_REQUIRED_INPUT_TOO_LARGE", t_before, t_after
        )
    return CompactionDecision(
        "BENEFICIAL",
        "SUMMARY_BENEFIT_VERIFIED",
        t_before,
        t_after,
        request,
        view.selected_safety_dependencies,
    )
