"""免费来源的确定性准入门禁。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceAdmissionRecordV2,
    SourceDescriptorV2,
)


@dataclass(frozen=True, slots=True)
class AdmissionDecisionV2:
    allowed: bool
    reason_codes: tuple[str, ...] = ()
    quota_reservation_required: bool = False

    def __post_init__(self) -> None:
        if self.allowed == bool(self.reason_codes):
            raise ValueError("SOURCE_ADMISSION_DECISION_INVALID")


class SourceAdmission:
    def __init__(
        self,
        *,
        admission_ttl: timedelta = timedelta(days=30),
        cost_evidence_ttl: timedelta = timedelta(days=30),
    ) -> None:
        if admission_ttl <= timedelta(0) or cost_evidence_ttl <= timedelta(0):
            raise ValueError("SOURCE_ADMISSION_TTL_INVALID")
        self.admission_ttl = admission_ttl
        self.cost_evidence_ttl = cost_evidence_ttl

    def evaluate(
        self,
        descriptor: SourceDescriptorV2,
        record: SourceAdmissionRecordV2,
        now: datetime,
    ) -> AdmissionDecisionV2:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("SOURCE_ADMISSION_NOW_NAIVE")
        if not descriptor.enabled:
            return _deny("SOURCE_DISABLED")
        if descriptor.admission != record:
            return _deny("SOURCE_ADMISSION_STALE")
        if record.status != "VERIFIED":
            return _deny("SOURCE_UNVERIFIED")
        if not record.schema_verified:
            return _deny("SOURCE_SCHEMA_UNVERIFIED")
        if not record.permission_verified:
            return _deny("SOURCE_PERMISSION_UNVERIFIED")
        if record.last_verified_at is None or record.last_verified_at > now:
            return _deny("SOURCE_ADMISSION_TIME_INVALID")
        if now - record.last_verified_at > self.admission_ttl:
            return _deny("SOURCE_ADMISSION_EXPIRED")
        cost = descriptor.cost_policy
        if cost.mode == "unknown":
            return _deny("SOURCE_COST_UNVERIFIED")
        if cost.mode == "paid" or cost.overage_behavior == "charge":
            return _deny("SOURCE_PAID_FORBIDDEN")
        if not cost.evidence_url.strip():
            return _deny("SOURCE_COST_EVIDENCE_MISSING")
        if cost.verified_at.tzinfo is None or cost.verified_at.utcoffset() is None:
            return _deny("SOURCE_COST_TIME_INVALID")
        if cost.verified_at > now:
            return _deny("SOURCE_COST_TIME_INVALID")
        if now - cost.verified_at > self.cost_evidence_ttl:
            return _deny("SOURCE_COST_EVIDENCE_EXPIRED")
        return AdmissionDecisionV2(
            allowed=True,
            quota_reservation_required=cost.mode == "free_quota",
        )


def _deny(code: str) -> AdmissionDecisionV2:
    return AdmissionDecisionV2(allowed=False, reason_codes=(code,))


__all__ = ["AdmissionDecisionV2", "SourceAdmission"]
