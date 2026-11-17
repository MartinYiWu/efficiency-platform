"""分段摘要前置准入；不调用Provider、不激活摘要、不变更持久状态。"""

from efficiency_platform_agent.contracts.memory import ConversationScopeModel
from efficiency_platform_agent.core.context_control import TokenMeasurement
from efficiency_platform_agent.memory.summary_contracts import (
    CandidateStatus,
    RejectedOption,
    SummaryBasisEvent,
    SummaryInputSource,
    SummarySegment,
)


class SummaryPolicy:
    def validate_token_bounds(
        self,
        source_measurement: TokenMeasurement,
        output_measurement: TokenMeasurement,
        *,
        source_limit: int,
        output_limit: int,
    ) -> None:
        if any(
            type(limit) is not int or limit <= 0
            for limit in (source_limit, output_limit)
        ):
            raise ValueError("SUMMARY_TOKEN_LIMIT_INVALID")
        if not source_measurement.verified or not output_measurement.verified:
            raise ValueError("SUMMARY_TOKEN_EVIDENCE_REQUIRED")
        if source_measurement.total_upper_bound > source_limit:
            raise ValueError("SUMMARY_SOURCE_TOKEN_LIMIT")
        if output_measurement.total_upper_bound > output_limit:
            raise ValueError("SUMMARY_OUTPUT_TOKEN_LIMIT")

    def admit(
        self,
        mode: str,
        sources: tuple[SummaryInputSource, ...],
        scope: ConversationScopeModel,
        *,
        now: int,
    ) -> None:
        if mode not in {"SUMMARY", "PROPOSALS", "BOTH"}:
            raise ValueError("SUMMARY_MODE_INVALID")
        if not sources or type(sources) is not tuple or len(sources) > 128:
            raise ValueError("SUMMARY_SOURCES_INVALID")
        if type(now) is not int or now < 0:
            raise ValueError("SUMMARY_TIME_INVALID")
        refs = tuple(source.source_ref for source in sources)
        if len(set(refs)) != len(refs) or len(
            {(ref.source_type, ref.source_id) for ref in refs}
        ) != len(refs):
            raise ValueError("SUMMARY_SOURCES_DUPLICATE")
        sequences = tuple(source.sequence for source in sources)
        if sequences != tuple(range(sequences[0], sequences[0] + len(sources))):
            raise ValueError("SUMMARY_SOURCE_RANGE_INVALID")
        purposes = {"SUMMARY", "PROPOSALS"} if mode == "BOTH" else {mode}
        for source in sources:
            if source.scope != scope or scope.session_kind != "CONVERSATION":
                raise ValueError("SUMMARY_SCOPE_MISMATCH")
            if not source.completed:
                raise ValueError("SUMMARY_SOURCE_INCOMPLETE")
            if source.source_kind != "ORIGINAL":
                raise ValueError("SUMMARY_RECURSION_DENIED")
            if source.expires_at <= now:
                raise ValueError("SUMMARY_SOURCE_EXPIRED")
            if not purposes.issubset(source.allowed_purposes):
                raise ValueError("SUMMARY_PURPOSE_DENIED")
            if (
                "SUMMARY" in purposes
                and (
                    source.summary_scope_ref is None
                    or source.summary_retention_ref is None
                )
            ) or (
                "PROPOSALS" in purposes
                and (
                    source.proposals_scope_ref is None
                    or source.proposals_retention_ref is None
                )
            ):
                raise ValueError("SUMMARY_PURPOSE_DENIED")
            if mode == "BOTH" and (
                source.summary_scope_ref != source.proposals_scope_ref
                or source.summary_retention_ref != source.proposals_retention_ref
            ):
                raise ValueError("SUMMARY_PURPOSE_INCOMPATIBLE")
            members = tuple(
                item.source_ref for item in sources if item.group_id == source.group_id
            )
            if source.group_members != members:
                raise ValueError("SUMMARY_GROUP_INCOMPLETE")
            group_sequences = tuple(
                item.sequence for item in sources if item.group_id == source.group_id
            )
            if group_sequences != tuple(
                range(group_sequences[0], group_sequences[0] + len(group_sequences))
            ):
                raise ValueError("SUMMARY_GROUP_INCOMPLETE")
            if source.source_ref not in source.source_dependencies:
                raise ValueError("SUMMARY_DEPENDENCIES_INCOMPLETE")
            if any(
                not {"grant_epoch", "source_epoch", "deletion_epoch"}.issubset(
                    ref.model_fields_set
                )
                for ref in (
                    source.source_ref,
                    *source.group_members,
                    *source.source_dependencies,
                )
            ):
                raise ValueError("SUMMARY_SOURCE_EPOCHS_REQUIRED")

    def validate_segment(
        self,
        segment: SummarySegment,
        sources: tuple[SummaryInputSource, ...],
        events: tuple[SummaryBasisEvent, ...],
        *,
        now: int,
        source_revision: int,
    ) -> None:
        self.admit("SUMMARY", sources, segment.scope, now=now)
        if segment.covered_sources != tuple(source.source_ref for source in sources):
            raise ValueError("SUMMARY_COVERAGE_MISMATCH")
        if segment.watermark.source_revision != source_revision or (
            segment.watermark.first_sequence,
            segment.watermark.last_sequence,
        ) != (sources[0].sequence, sources[-1].sequence):
            raise ValueError("SUMMARY_WATERMARK_MISMATCH")
        dependencies = {dep for source in sources for dep in source.source_dependencies}
        if set(segment.source_dependencies) != dependencies:
            raise ValueError("SUMMARY_DEPENDENCIES_INCOMPLETE")
        if segment.expires_at > min(source.expires_at for source in sources):
            raise ValueError("SUMMARY_EXPIRY_EXTENDED")
        if segment.expires_at <= now:
            raise ValueError("SUMMARY_SOURCE_EXPIRED")
        by_event = {event.event_ref: event for event in events}
        if len(by_event) != len(events) or not set(by_event).issubset(dependencies):
            raise ValueError("SUMMARY_BASIS_UNKNOWN")
        entries = (
            segment.goal,
            *segment.confirmed_constraints,
            *segment.decisions,
            *segment.rejected_options,
            *segment.open_questions,
            *segment.important_refs,
            *segment.uncertainties,
        )
        claims: dict[str, tuple[str, str]] = {}
        for item in entries:
            identity = (item.content_origin, item.decision_status)
            if item.claim_ref in claims and claims[item.claim_ref] != identity:
                raise ValueError("SUMMARY_CLAIM_CONFLICT")
            claims[item.claim_ref] = identity
            if not set(item.source_refs).issubset(segment.covered_sources):
                raise ValueError("SUMMARY_SOURCE_REF_UNKNOWN")
            source_values = {
                value
                for source in sources
                if source.source_ref in item.source_refs
                for value in source.critical_values
            }
            if not set(item.critical_values).issubset(source_values):
                raise ValueError("SUMMARY_CRITICAL_SOURCE_MISMATCH")
            event = by_event.get(item.basis_event_ref) if item.basis_event_ref else None
            if item.basis_event_ref is not None and event is None:
                raise ValueError("SUMMARY_BASIS_UNKNOWN")
            item_dependencies = {
                dependency
                for source in sources
                if source.source_ref in item.source_refs
                for dependency in source.source_dependencies
            }
            if event is not None and item.basis_event_ref not in item_dependencies:
                raise ValueError("SUMMARY_BASIS_SOURCE_MISMATCH")
            if event is not None and item.claim_ref != event.claim_ref:
                raise ValueError("SUMMARY_BASIS_CLAIM_MISMATCH")
            if event is not None and item.decision_status != event.decision_status:
                raise ValueError("SUMMARY_BASIS_STATUS_MISMATCH")
            if item.content_origin in {"USER_REQUIREMENT", "BUSINESS_FACT"}:
                authority = (
                    "USER" if item.content_origin == "USER_REQUIREMENT" else "JAVA"
                )
                if (
                    event is None
                    or event.authority != authority
                    or event.content_origin != item.content_origin
                ):
                    raise ValueError("SUMMARY_AUTHORITY_REQUIRED")
            if item.decision_status in {"CONFIRMED", "REJECTED"} and (
                event is None
                or event.authority not in {"USER", "JAVA"}
                or event.decision_status != item.decision_status
            ):
                raise ValueError("SUMMARY_CONFIRMATION_REQUIRED")
            if event is not None and item.critical_values != event.critical_values:
                raise ValueError("SUMMARY_CRITICAL_VALUES_CHANGED")
            if isinstance(item, RejectedOption):
                if item.decision_status != "REJECTED":
                    raise ValueError("SUMMARY_REJECTED_STATUS_INVALID")
                if event is None or item.reason != event.rejection_reason:
                    raise ValueError("SUMMARY_REJECTION_REASON_CHANGED")
        if any(
            item.decision_status != "CONFIRMED"
            for item in segment.confirmed_constraints
        ):
            raise ValueError("SUMMARY_CONSTRAINT_UNCONFIRMED")
        if any(
            item.decision_status != "UNRESOLVED"
            for item in (*segment.open_questions, *segment.uncertainties)
        ):
            raise ValueError("SUMMARY_UNRESOLVED_STATE_CHANGED")
        for event in events:
            if event.decision_status in {"CONFIRMED", "REJECTED"} and not any(
                item.basis_event_ref == event.event_ref
                and item.decision_status == event.decision_status
                and (
                    event.decision_status != "REJECTED"
                    or isinstance(item, RejectedOption)
                )
                for item in entries
            ):
                raise ValueError("SUMMARY_REQUIRED_EVENT_MISSING")
        actual_values = {value for item in entries for value in item.critical_values}
        expected_values = {
            value for source in sources for value in source.critical_values
        }
        if actual_values != expected_values:
            raise ValueError("SUMMARY_CRITICAL_VALUES_CHANGED")

    def candidate_status(
        self,
        segment: SummarySegment,
        current_sources: tuple[SummaryInputSource, ...],
        *,
        source_revision: int,
    ) -> CandidateStatus:
        if (
            type(source_revision) is not int
            or source_revision < segment.watermark.source_revision
        ):
            return "STALE"
        selected = tuple(
            source
            for source in current_sources
            if segment.watermark.first_sequence
            <= source.sequence
            <= segment.watermark.last_sequence
        )
        if (
            tuple(source.source_ref for source in selected) != segment.covered_sources
            or any(source.scope != segment.scope for source in selected)
            or {dep for source in selected for dep in source.source_dependencies}
            != set(segment.source_dependencies)
        ):
            return "STALE"
        return "PENDING"
