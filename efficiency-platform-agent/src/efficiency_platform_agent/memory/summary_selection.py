"""可信Java已提交投影的CPU选择；不验证签名、不签发权限、不读取Java表。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
)
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    SourceDependency,
    require_bool,
    require_count,
    require_dependencies,
    require_id,
)
from efficiency_platform_agent.core.run import ProviderMessage
from efficiency_platform_agent.memory.summary_contracts import (
    SummaryBasisEvent,
    SummaryInputSource,
    SummarySegment,
)
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy
from efficiency_platform_agent.memory.summary_projection import (
    SUMMARY_LEGEND,
    render_summary,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)


@runtime_checkable
class OriginalContextPiece(Protocol):
    @property
    def piece_id(self) -> str: ...
    @property
    def scope(self) -> ExecutionScope: ...
    @property
    def messages(self) -> tuple[ProviderMessage, ...]: ...
    @property
    def safety_dependencies(self) -> tuple[SourceDependency, ...]: ...
    @property
    def required(self) -> bool: ...
    @property
    def kind(self) -> str: ...
    @property
    def covered_message_ids(self) -> tuple[str, ...]: ...
    @property
    def is_required(self) -> bool: ...


class SummarySelectionPolicy(Protocol):
    @property
    def scope(self) -> ExecutionScope: ...
    @property
    def authorized_dependencies(self) -> tuple[SourceDependency, ...]: ...
    @property
    def allowed_message_ids(self) -> frozenset[str]: ...
    @property
    def max_pieces(self) -> int: ...
    @property
    def max_history_messages(self) -> int: ...
    @property
    def summary_token_limit(self) -> int: ...


@dataclass(frozen=True, slots=True)
class SelectedSummaryPiece:
    """中立注入DTO；由context组合边界转为ContextPiece，memory不反向依赖context。"""

    piece_id: str
    scope: ExecutionScope
    messages: tuple[ProviderMessage, ...] = field(repr=False)
    safety_dependencies: tuple[SourceDependency, ...]
    covered_message_ids: tuple[str, ...]
    kind: Literal["summary"] = field(default="summary", init=False)
    required: bool = field(default=False, init=False)
    is_required: bool = field(default=False, init=False)
    projection_aliases: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CommittedSummary:
    """仅供已验签Java端口构造；普通HTTP/模型的COMMITTED字段不构成权威。

    current_dependencies来自当前权限/来源状态复核，必须包含摘要自身与全部原源；
    covered_message_ids来自真实MESSAGE目录，不能把既有source UUID改名为消息ID。
    """

    segment: SummarySegment = field(repr=False)
    sources: tuple[SummaryInputSource, ...] = field(repr=False)
    basis_events: tuple[SummaryBasisEvent, ...] = field(repr=False)
    source_revision: int
    authority_ref: str = field(repr=False)
    commit_ref: str = field(repr=False)
    status: Literal["COMMITTED", "STALE", "REVOKED"]
    authorized: bool
    current_dependencies: tuple[SourceDependency, ...] = field(repr=False)
    retention_ref: str = field(repr=False)
    expires_at: int
    summary_dependency: SourceDependency
    covered_message_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for ref in (self.authority_ref, self.commit_ref, self.retention_ref):
            require_id(ref)
        require_count(self.source_revision)
        require_count(self.expires_at)
        require_bool(self.authorized)
        require_dependencies(self.current_dependencies)
        if (
            type(self.segment) is not SummarySegment
            or type(self.summary_dependency) is not SourceDependency
            or type(self.sources) is not tuple
            or any(type(source) is not SummaryInputSource for source in self.sources)
            or type(self.basis_events) is not tuple
            or any(type(event) is not SummaryBasisEvent for event in self.basis_events)
            or type(self.covered_message_ids) is not tuple
            or self.status not in {"COMMITTED", "STALE", "REVOKED"}
        ):
            raise ValueError("SUMMARY_METADATA_INVALID")
        for identifier in self.covered_message_ids:
            require_id(identifier)


@dataclass(frozen=True, slots=True)
class SummaryOmission:
    reason: str
    source_refs: tuple[SourceDependency, ...] = ()


@dataclass(frozen=True, slots=True)
class SummarySelection:
    pieces: tuple[OriginalContextPiece, ...] = field(repr=False)
    selected_segments: tuple[str, ...]
    omissions: tuple[SummaryOmission, ...]
    summary_tokens: int


@dataclass(frozen=True, slots=True)
class SelectedSummaryLegend:
    piece_id: str
    scope: ExecutionScope
    messages: tuple[ProviderMessage, ...]
    safety_dependencies: tuple[SourceDependency, ...] = ()
    covered_message_ids: tuple[str, ...] = ()
    kind: str = "system"
    required: bool = True
    is_required: bool = True
    projection_aliases: tuple[tuple[str, str], ...] = ()


def _replaceable(piece: OriginalContextPiece) -> bool:
    return piece.kind == "history" and not (
        piece.is_required
        and (
            piece.required
            or any(m.role in {"system", "developer"} for m in piece.messages)
            or not any(m.tool_calls for m in piece.messages)
        )
    )


def select_committed_summaries(
    pieces: tuple[OriginalContextPiece, ...],
    committed_segments: tuple[CommittedSummary, ...],
    policy: SummarySelectionPolicy,
    capacity: ModelCapacity,
    counter: ConservativeRequestTokenCounter,
    *,
    now: int,
) -> SummarySelection:
    """保近期完整原文组，按新到旧选至多三段；完整请求最终仍须原Controller计窗。"""

    require_count(now)
    if (
        type(counter) is not ConservativeRequestTokenCounter
        or not capacity.verified
        or type(pieces) is not tuple
        or type(committed_segments) is not tuple
        or any(
            not isinstance(p, OriginalContextPiece) or p.scope != policy.scope
            for p in pieces
        )
        or any(type(item) is not CommittedSummary for item in committed_segments)
    ):
        raise ValueError("SUMMARY_SELECTION_INPUT_INVALID")
    if len(pieces) > policy.max_pieces or len(committed_segments) > policy.max_pieces:
        raise ValueError("CONTEXT_SOURCE_LIMIT")
    omissions: list[SummaryOmission] = []
    # 传入的旧摘要正文无权直接复用；每次只从可信提交投影重建。
    originals = tuple(p for p in pieces if p.kind != "summary")
    omissions.extend(
        SummaryOmission("UNVERIFIED_EXISTING_SUMMARY")
        for p in pieces
        if p.kind == "summary"
    )
    recent: set[str] = set()
    count = 0
    for piece in reversed(originals):
        if piece.kind != "history":
            continue
        if count < policy.max_history_messages:
            recent.update(piece.covered_message_ids)
            count += len(piece.messages)
    protected = recent | {
        identifier
        for p in originals
        if not _replaceable(p)
        for identifier in p.covered_message_ids
    }
    selected: list[tuple[CommittedSummary, SelectedSummaryPiece]] = []
    covered: set[str] = set()
    replaced: set[str] = set()
    tokens = 0
    blocked = {
        item.segment.segment_id
        for item in committed_segments
        if item.status != "COMMITTED"
    }
    for item in sorted(
        committed_segments,
        key=lambda s: s.segment.watermark.last_sequence,
        reverse=True,
    ):
        segment = item.segment
        dependencies = tuple(
            dict.fromkeys(
                (
                    *(r.to_core() for r in segment.source_dependencies),
                    item.summary_dependency,
                )
            )
        )
        coverage = tuple(ref.source_id for ref in segment.covered_sources)
        # 无权限/过期/撤销对象只返回常量原因，不泄露其segment/source身份。
        if (
            policy.scope.conversation.session_kind != "CONVERSATION"
            or segment.scope.to_core() != policy.scope.conversation
            or item.authorized is not True
            or item.status != "COMMITTED"
            or segment.segment_id in blocked
            or item.expires_at <= now
            or segment.expires_at <= now
            or item.expires_at > segment.expires_at
            or not set(dependencies).issubset(policy.authorized_dependencies)
            or not set(dependencies).issubset(item.current_dependencies)
            or not set(coverage).issubset(policy.allowed_message_ids)
        ):
            omissions.append(SummaryOmission("SUMMARY_NOT_CURRENT_OR_AUTHORIZED"))
            continue
        try:
            for ref in (item.authority_ref, item.commit_ref, item.retention_ref):
                require_id(ref)
            require_count(item.source_revision)
            require_count(item.expires_at)
            if (
                item.summary_dependency.source_type != "SUMMARY"
                or item.summary_dependency.source_id != segment.segment_id
                or coverage != item.covered_message_ids
                or any(ref.source_type != "MESSAGE" for ref in segment.covered_sources)
            ):
                raise ValueError("SUMMARY_COVERAGE_MISMATCH")
            SummaryPolicy().validate_segment(
                segment,
                item.sources,
                item.basis_events,
                now=now,
                source_revision=item.source_revision,
            )
        except (ValueError, TypeError):
            omissions.append(SummaryOmission("SUMMARY_METADATA_INVALID"))
            continue
        reason = None
        overlapping = tuple(
            p for p in originals if set(p.covered_message_ids).intersection(coverage)
        )
        if protected.intersection(coverage):
            reason = "RECENT_OR_REQUIRED_ORIGINAL"
        elif any(
            not _replaceable(p) or not set(p.covered_message_ids).issubset(coverage)
            for p in overlapping
        ):
            reason = "SUMMARY_GROUP_INCOMPLETE"
        elif covered.intersection(coverage):
            reason = "DUPLICATE_COVERAGE"
        elif len(selected) >= 3:
            reason = "SUMMARY_SEGMENT_LIMIT"
        elif (
            len(originals) - len(replaced) - len(overlapping) + len(selected) + 1
            > policy.max_pieces
        ):
            reason = "CONTEXT_SOURCE_LIMIT"
        if reason:
            omissions.append(SummaryOmission(reason, dependencies))
            continue
        rendered = render_summary(segment)
        summary = SelectedSummaryPiece(
            "summary:" + segment.segment_id,
            policy.scope,
            (ProviderMessage("user", rendered.text),),
            dependencies,
            covered_message_ids=coverage,
            projection_aliases=((segment.segment_id, rendered.aliases_json),),
        )
        measured = counter.measure_messages(summary.messages, capacity)
        if (
            type(measured) is not TokenMeasurement
            or not measured.verified
            or measured.method != "conservative-utf8-fragment/1"
        ):
            raise ValueError("CONTEXT_CAPACITY_UNVERIFIED")
        size = measured.total_upper_bound
        # 片段上界相加仍是保守上界，避免对相同正文重复计数。
        if size > 500 or tokens + size > min(1000, policy.summary_token_limit):
            omissions.append(SummaryOmission("SUMMARY_SLOT_LIMIT", dependencies))
            continue
        tokens += size
        selected.append((item, summary))
        covered.update(coverage)
        replaced.update(p.piece_id for p in overlapping)
    selected.sort(key=lambda pair: pair[0].segment.watermark.first_sequence)
    remaining = tuple(p for p in originals if p.piece_id not in replaced)
    summaries = tuple(piece for _, piece in selected)
    position = next(
        (
            i
            for i, p in enumerate(remaining)
            if p.kind in {"history", "current_request"}
        ),
        len(remaining),
    )
    legend: tuple[SelectedSummaryLegend, ...] = ()
    if summaries and not any(
        p.piece_id == "summary-legend/2"
        and p.messages == (ProviderMessage("system", SUMMARY_LEGEND),)
        for p in remaining
    ):
        legend = (
            SelectedSummaryLegend(
                "summary-legend/2",
                policy.scope,
                (ProviderMessage("system", SUMMARY_LEGEND),),
            ),
        )
    result = (*remaining[:position], *legend, *summaries, *remaining[position:])
    return SummarySelection(
        result,
        tuple(item.segment.segment_id for item, _ in selected),
        tuple(omissions),
        tokens,
    )
