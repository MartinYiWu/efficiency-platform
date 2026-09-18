"""R01 免费来源准入门禁测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from efficiency_platform_agent.capabilities.research.v2.source_admission import (
    SourceAdmission,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceAdmissionRecordV2,
    SourceContentPolicyV2,
    SourceCostPolicyV2,
    SourceDescriptorV2,
    SourceRatePolicyV2,
)

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def descriptor(*, mode="free", enabled=True, verified_at=NOW, status="VERIFIED"):
    admission = SourceAdmissionRecordV2(
        admission_record_id="admission-1",
        status=status,
        last_verified_at=NOW if status == "VERIFIED" else None,
        approved_by="reviewer" if status == "VERIFIED" else None,
        intended_uses=("research",),
        schema_verified=status == "VERIFIED",
        history_verified=True,
        permission_verified=status == "VERIFIED",
    )
    return SourceDescriptorV2(
        source_id="source-1",
        adapter_id="rss_atom",
        config_version="1",
        roles=("primary",),
        languages=("zh",),
        regions=("cn",),
        publisher_id="publisher-1",
        allowed_hosts=("example.test",),
        access_mode="rss",
        history_mode="archive",
        max_lookback=timedelta(days=30),
        pagination=False,
        rate_policy=SourceRatePolicyV2(requests=10, period_seconds=60),
        content_policy=SourceContentPolicyV2(
            storage_mode="excerpt_only", retention_days=7, citation_allowed=True
        ),
        cost_policy=SourceCostPolicyV2(
            mode=mode,
            evidence_url="https://example.test/cost",
            verified_at=verified_at,
            quota_limit=100 if mode == "free_quota" else None,
            quota_period="day" if mode == "free_quota" else None,
            requires_authentication=mode == "free_quota",
            overage_behavior=(
                "hard_stop" if mode in {"free", "free_quota"} else "charge"
            ),
        ),
        admission=admission,
        enabled=enabled,
    )


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        (descriptor(mode="paid"), "SOURCE_PAID_FORBIDDEN"),
        (descriptor(mode="unknown"), "SOURCE_COST_UNVERIFIED"),
        (descriptor(enabled=False), "SOURCE_DISABLED"),
        (descriptor(status="UNVERIFIED"), "SOURCE_UNVERIFIED"),
        (
            descriptor(verified_at=NOW - timedelta(days=31)),
            "SOURCE_COST_EVIDENCE_EXPIRED",
        ),
    ],
)
def test_non_free_unverified_or_expired_source_is_denied(source, reason) -> None:
    decision = SourceAdmission().evaluate(source, source.admission, NOW)

    assert decision.allowed is False
    assert decision.reason_codes == (reason,)


def test_free_quota_is_allowed_only_as_reservation_required() -> None:
    source = descriptor(mode="free_quota")
    decision = SourceAdmission().evaluate(source, source.admission, NOW)

    assert decision.allowed is True
    assert decision.quota_reservation_required is True


def test_stale_external_record_is_denied() -> None:
    source = descriptor()
    stale = source.admission.model_copy(update={"admission_record_id": "other"})

    assert SourceAdmission().evaluate(source, stale, NOW).reason_codes == (
        "SOURCE_ADMISSION_STALE",
    )
