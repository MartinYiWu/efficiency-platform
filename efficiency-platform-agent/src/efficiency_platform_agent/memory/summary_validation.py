"""独立摘要候选校验；可信来源投影由组合边界提供，不签发授权或提交数据库。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from efficiency_platform_agent.contracts.memory import (
    ConversationScopeModel,
    SourceDependencyModel,
)
from efficiency_platform_agent.core.memory import require_id
from efficiency_platform_agent.memory.summary_contracts import (
    DeriveMode,
    RejectedOption,
    SummaryBasisEvent,
    SummaryEntry,
    SummaryInputSource,
    SummarySegment,
    SummaryWatermark,
)
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy


@dataclass(frozen=True, slots=True)
class FrozenSummarySources:
    """只能由原调用的可信来源/事件投影提供，不能由候选自报保留清单。"""

    sources: tuple[SummaryInputSource, ...] = field(repr=False)
    events: tuple[SummaryBasisEvent, ...] = field(repr=False)
    required_entries: tuple[SummaryEntry, ...] = field(repr=False)
    session_revision: int
    source_revision: int
    mode: DeriveMode
    memory_policy_version: str
    authority_ref: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SummaryTaskState:
    """可信当前只读快照；不是新的运行状态或模型可写权限。"""

    scope: ConversationScopeModel
    current_sources: tuple[SummaryInputSource, ...] = field(repr=False)
    session_revision: int
    source_revision: int
    now: int
    original_mode: DeriveMode
    memory_policy_version: str
    authority_ref: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ValidatedSummary:
    segment: SummarySegment = field(repr=False)
    session_revision: int
    source_revision: int
    watermark: SummaryWatermark
    frozen_critical_digest: str = field(repr=False)
    source_dependencies: tuple[SourceDependencyModel, ...]
    expires_at: int
    memory_policy_version: str
    frozen_sources: FrozenSummarySources = field(repr=False)
    task_state: SummaryTaskState = field(repr=False)
    free_text_quality: Literal["UNVERIFIED"] = field(default="UNVERIFIED", init=False)
    commit_status: Literal["NOT_COMMITTED"] = field(default="NOT_COMMITTED", init=False)


def _entry_structure(entry: SummaryEntry) -> dict[str, object]:
    # 只声称结构化关键状态保真；叙述文本没有模型语义质量分数。
    return entry.model_dump(mode="json", exclude={"text"})


def validate_summary(
    candidate: SummarySegment,
    frozen_sources: FrozenSummarySources,
    task_state: SummaryTaskState,
) -> ValidatedSummary:
    if (
        type(candidate) is not SummarySegment
        or type(frozen_sources) is not FrozenSummarySources
        or type(task_state) is not SummaryTaskState
    ):
        raise ValueError("SUMMARY_VALIDATION_INPUT_INVALID")
    frozen, current = frozen_sources, task_state
    try:
        for identifier in (
            frozen.authority_ref,
            current.authority_ref,
            frozen.memory_policy_version,
            current.memory_policy_version,
        ):
            require_id(identifier)
    except ValueError:
        raise ValueError("SUMMARY_AUTHORITY_BINDING_INVALID") from None
    if (
        not frozen.authority_ref
        or current.authority_ref != frozen.authority_ref
        or not frozen.memory_policy_version
        or current.memory_policy_version != frozen.memory_policy_version
        or current.original_mode != frozen.mode
        or frozen.mode not in {"SUMMARY", "BOTH"}
    ):
        raise ValueError("SUMMARY_AUTHORITY_BINDING_INVALID")
    for value in (
        frozen.session_revision,
        frozen.source_revision,
        current.session_revision,
        current.source_revision,
        current.now,
    ):
        if type(value) is not int or value < 0:
            raise ValueError("SUMMARY_REVISION_INVALID")
    if (
        type(frozen.sources) is not tuple
        or type(frozen.events) is not tuple
        or type(frozen.required_entries) is not tuple
        or type(current.current_sources) is not tuple
        or not frozen.sources
        or not frozen.required_entries
        or len(frozen.required_entries) > 897
    ):
        raise ValueError("SUMMARY_SOURCE_PROJECTION_REQUIRED")
    if candidate.scope != current.scope:
        raise ValueError("SUMMARY_SCOPE_MISMATCH")
    if (
        current.session_revision < frozen.session_revision
        or current.source_revision < frozen.source_revision
        or candidate.watermark.source_revision != frozen.source_revision
    ):
        raise ValueError("SUMMARY_STALE")
    selected = tuple(
        source
        for source in current.current_sources
        if candidate.watermark.first_sequence
        <= source.sequence
        <= candidate.watermark.last_sequence
    )
    if selected != frozen.sources:
        raise ValueError("SUMMARY_STALE")
    policy = SummaryPolicy()
    policy.admit(frozen.mode, frozen.sources, current.scope, now=current.now)
    policy.validate_segment(
        candidate,
        frozen.sources,
        frozen.events,
        now=current.now,
        source_revision=frozen.source_revision,
    )
    entries = (
        candidate.goal,
        *candidate.confirmed_constraints,
        *candidate.decisions,
        *candidate.rejected_options,
        *candidate.open_questions,
        *candidate.important_refs,
        *candidate.uncertainties,
    )
    required = [_entry_structure(entry) for entry in frozen.required_entries]
    actual = [_entry_structure(entry) for entry in entries]
    if any(item not in actual for item in required):
        raise ValueError("SUMMARY_REQUIRED_STATE_CHANGED")
    for event in frozen.events:
        if not any(
            item.basis_event_ref == event.event_ref
            and item.claim_ref == event.claim_ref
            and item.decision_status == event.decision_status
            and item.critical_values == event.critical_values
            and (
                event.decision_status != "REJECTED" or isinstance(item, RejectedOption)
            )
            for item in entries
        ):
            raise ValueError("SUMMARY_REQUIRED_EVENT_MISSING")
    critical = {
        "scope": current.scope.model_dump(mode="json"),
        "session_revision": frozen.session_revision,
        "source_revision": frozen.source_revision,
        "watermark": candidate.watermark.model_dump(mode="json"),
        "mode": frozen.mode,
        "memory_policy_version": frozen.memory_policy_version,
        "sources": [
            {
                **source.model_dump(mode="json"),
                "allowed_purposes": sorted(source.allowed_purposes),
            }
            for source in frozen.sources
        ],
        "events": [event.model_dump(mode="json") for event in frozen.events],
        "required_entries": required,
    }
    digest = hashlib.sha256(
        json.dumps(
            critical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return ValidatedSummary(
        candidate,
        frozen.session_revision,
        frozen.source_revision,
        candidate.watermark,
        digest,
        candidate.source_dependencies,
        candidate.expires_at,
        frozen.memory_policy_version,
        frozen,
        current,
    )
