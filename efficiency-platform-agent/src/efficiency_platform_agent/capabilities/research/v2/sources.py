"""只暴露已免费准入且满足当前 Brief 的来源目录。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceDescriptorV2,
    SourceRuntimeContextV2,
)
from efficiency_platform_agent.contracts.research_v2 import ResearchBriefV2

from .source_admission import SourceAdmission


@dataclass(frozen=True, slots=True)
class SourceAvailabilityV2:
    source_id: str
    available: bool
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.available == bool(self.reason_codes):
            raise ValueError("SOURCE_AVAILABILITY_INVALID")


@dataclass(frozen=True, slots=True)
class SourceQuotaReservationV2:
    allowed: bool
    reservation_id: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.allowed and (
            self.reservation_id is None or self.reason_code is not None
        ):
            raise ValueError("SOURCE_QUOTA_RESERVATION_INVALID")
        if not self.allowed and (
            self.reservation_id is not None or self.reason_code is None
        ):
            raise ValueError("SOURCE_QUOTA_RESERVATION_INVALID")


class SourceQuotaLedger(Protocol):
    def reserve(
        self,
        *,
        source_id: str,
        tenant_id: str,
        run_id: str,
        units: int,
    ) -> str | None: ...


class VerifiedSourceRegistry:
    def __init__(
        self,
        descriptors: tuple[SourceDescriptorV2, ...],
        admission: SourceAdmission,
        *,
        registered_adapter_ids: frozenset[str],
        intended_use: str = "research",
        quota_ledger: SourceQuotaLedger | None = None,
    ) -> None:
        ids = [item.source_id for item in descriptors]
        if len(set(ids)) != len(ids):
            raise ValueError("SOURCE_ID_DUPLICATED")
        if not registered_adapter_ids or any(
            not item.strip() for item in registered_adapter_ids
        ):
            raise ValueError("SOURCE_ADAPTER_REGISTRY_INVALID")
        self._descriptors = tuple(sorted(descriptors, key=lambda item: item.source_id))
        self.admission = admission
        self.registered_adapter_ids = registered_adapter_ids
        self.intended_use = intended_use
        self.quota_ledger = quota_ledger

    def availability(
        self,
        context: SourceRuntimeContextV2,
        brief: ResearchBriefV2,
    ) -> tuple[SourceAvailabilityV2, ...]:
        return tuple(self._evaluate(item, context, brief) for item in self._descriptors)

    def list_available(
        self,
        context: SourceRuntimeContextV2,
        brief: ResearchBriefV2,
    ) -> tuple[SourceDescriptorV2, ...]:
        decisions = {item.source_id: item for item in self.availability(context, brief)}
        return tuple(
            item for item in self._descriptors if decisions[item.source_id].available
        )

    def reserve_for_call(
        self,
        source_id: str,
        context: SourceRuntimeContextV2,
        brief: ResearchBriefV2,
    ) -> SourceQuotaReservationV2:
        descriptor = next(
            (item for item in self._descriptors if item.source_id == source_id),
            None,
        )
        if descriptor is None:
            return _reservation_denied("SOURCE_UNKNOWN")
        availability = self._evaluate(descriptor, context, brief)
        if not availability.available:
            return _reservation_denied(availability.reason_codes[0])
        if descriptor.cost_policy.mode == "free":
            return SourceQuotaReservationV2(
                allowed=True,
                reservation_id=f"free:{context.run_id}:{source_id}",
            )
        if self.quota_ledger is None:
            return _reservation_denied("SOURCE_QUOTA_LEDGER_UNAVAILABLE")
        reservation_id = self.quota_ledger.reserve(
            source_id=source_id,
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            units=1,
        )
        if reservation_id is None:
            return _reservation_denied("SOURCE_QUOTA_RESERVATION_FAILED")
        return SourceQuotaReservationV2(True, reservation_id)

    def _evaluate(
        self,
        descriptor: SourceDescriptorV2,
        context: SourceRuntimeContextV2,
        brief: ResearchBriefV2,
    ) -> SourceAvailabilityV2:
        admitted = self.admission.evaluate(
            descriptor, descriptor.admission, context.now
        )
        if not admitted.allowed:
            return _unavailable(descriptor.source_id, admitted.reason_codes[0])
        if descriptor.adapter_id not in self.registered_adapter_ids:
            return _unavailable(descriptor.source_id, "SOURCE_ADAPTER_UNREGISTERED")
        if self.intended_use not in descriptor.admission.intended_uses:
            return _unavailable(descriptor.source_id, "SOURCE_USE_UNVERIFIED")
        if (
            descriptor.cost_policy.requires_authentication
            and descriptor.source_id not in context.available_credential_source_ids
        ):
            return _unavailable(descriptor.source_id, "SOURCE_CREDENTIAL_MISSING")
        if admitted.quota_reservation_required:
            remaining = context.quota_remaining_by_source.get(descriptor.source_id)
            if remaining is None:
                return _unavailable(descriptor.source_id, "SOURCE_QUOTA_UNKNOWN")
            if remaining <= 0:
                return _unavailable(descriptor.source_id, "SOURCE_QUOTA_EXHAUSTED")
        runtime_allowed = context.allowed_source_ids
        requested_allowed = brief.source_constraints.allowed_source_ids
        if runtime_allowed is not None and descriptor.source_id not in runtime_allowed:
            return _unavailable(descriptor.source_id, "SOURCE_NOT_RUNTIME_ALLOWED")
        if (
            requested_allowed is not None
            and descriptor.source_id not in requested_allowed
        ):
            return _unavailable(descriptor.source_id, "SOURCE_NOT_REQUESTED")
        if descriptor.source_id in brief.source_constraints.excluded_source_ids:
            return _unavailable(descriptor.source_id, "SOURCE_EXCLUDED")
        if brief.source_constraints.primary_only and "primary" not in descriptor.roles:
            return _unavailable(descriptor.source_id, "SOURCE_PRIMARY_REQUIRED")
        if brief.source_constraints.languages is not None and not (
            set(descriptor.languages) & set(brief.source_constraints.languages)
        ):
            return _unavailable(descriptor.source_id, "SOURCE_LANGUAGE_UNSUPPORTED")
        if brief.source_constraints.event_regions is not None and not (
            set(descriptor.regions) & set(brief.source_constraints.event_regions)
        ):
            return _unavailable(descriptor.source_id, "SOURCE_REGION_UNSUPPORTED")
        if not _history_covers(descriptor, context, brief):
            return _unavailable(descriptor.source_id, "SOURCE_HISTORY_UNSUPPORTED")
        return SourceAvailabilityV2(descriptor.source_id, True)


def _history_covers(
    descriptor: SourceDescriptorV2,
    context: SourceRuntimeContextV2,
    brief: ResearchBriefV2,
) -> bool:
    if descriptor.history_mode == "unknown":
        return False
    if descriptor.max_lookback is not None and (
        brief.time_window.start < context.now - descriptor.max_lookback
    ):
        return False
    if descriptor.history_mode == "latest_only":
        if not descriptor.admission.history_verified:
            return False
        freshness = descriptor.freshness_sla
        if freshness is None or brief.time_window.start < context.now - freshness:
            return False
    return True


def _unavailable(source_id: str, code: str) -> SourceAvailabilityV2:
    return SourceAvailabilityV2(source_id, False, (code,))


def _reservation_denied(code: str) -> SourceQuotaReservationV2:
    return SourceQuotaReservationV2(False, reason_code=code)


__all__ = [
    "SourceAvailabilityV2",
    "SourceQuotaLedger",
    "SourceQuotaReservationV2",
    "VerifiedSourceRegistry",
]
