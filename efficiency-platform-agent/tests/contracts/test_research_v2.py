"""研究 V2 契约的冻结行为测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.research_evidence_v2 import EvidenceRefV2
from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceAdmissionRecordV2,
    SourceCostPolicyV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    ResearchBriefV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from tests.support.research_v2_cases import research_v2_case


def test_count_policy_rejects_unbounded_or_inverted_count() -> None:
    with pytest.raises(ValidationError):
        CountPolicy(mode="exact", target=0, minimum=1)
    with pytest.raises(ValidationError):
        CountPolicy(mode="exact", target=3, minimum=4)
    assert CountPolicy(mode="exact", target=5, minimum=1).target == 5


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime.fromisoformat("2026-09-16"), datetime.fromisoformat("2026-09-17")),
        (
            datetime(2026, 9, 17, tzinfo=UTC),
            datetime(2026, 9, 16, tzinfo=UTC),
        ),
        (
            datetime(2026, 9, 16, tzinfo=timezone(timedelta(hours=8))),
            datetime(2026, 9, 17, tzinfo=timezone(timedelta(hours=8))),
        ),
    ],
)
def test_resolved_window_requires_ordered_aware_utc_bounds(
    start: datetime, end: datetime
) -> None:
    with pytest.raises(ValidationError):
        ResolvedTimeWindow(
            start=start,
            end=end,
            timezone="Asia/Shanghai",
            precision="day",
            anchor=datetime(2026, 9, 16, tzinfo=UTC),
        )


def test_source_admission_rejects_verified_record_without_evidence() -> None:
    with pytest.raises(ValidationError):
        SourceAdmissionRecordV2(
            admission_record_id="admission-1",
            status="VERIFIED",
            approved_by="reviewer",
            last_verified_at=datetime(2026, 9, 16, tzinfo=UTC),
            permission_verified=False,
            schema_verified=True,
        )


def test_free_quota_requires_hard_stop_and_evidence() -> None:
    with pytest.raises(ValidationError):
        SourceCostPolicyV2(
            mode="free_quota",
            evidence_url="https://example.test/pricing",
            verified_at=datetime(2026, 9, 16, tzinfo=UTC),
            requires_authentication=False,
            overage_behavior="unknown",
        )


def test_evidence_ref_requires_nonempty_unicode_span() -> None:
    with pytest.raises(ValidationError):
        EvidenceRefV2(
            evidence_id="e-1",
            document_id="d-1",
            content_hash="0123456789abcdef",
            char_start=0,
            char_end=2,
            excerpt="闻",
            acquisition_method="rss",
        )


def test_unknown_research_case_id_does_not_default_to_success() -> None:
    with pytest.raises(KeyError):
        research_v2_case("missing-case")


def test_brief_rejects_model_identity_or_budget_fields_and_digest_ignores_diagnostics() -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    common = {
        "trusted_context": TrustedResearchContextV2(
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            budget_lease_id="lease-1",
        ),
        "intent_revision": 1,
        "topic": "AI",
        "time_window": ResolvedTimeWindow(
            start=now,
            end=datetime(2026, 9, 17, tzinfo=UTC),
            timezone="Asia/Shanghai",
            precision="day",
            anchor=now,
        ),
        "source_constraints": {},
        "count_policy": CountPolicy(mode="best_effort", target=5, minimum=1),
        "output_requirements": {"output_types": ("digest",), "language": "zh-CN"},
        "quality_policy_id": "quality-v2",
        "policy_version": "2026-09-16",
    }
    first = ResearchBriefV2(**common, diagnostics=())
    second = ResearchBriefV2(**common, diagnostics=("temporary-note",))
    assert first.canonical_digest() == second.canonical_digest()
    with pytest.raises(ValidationError):
        ResearchBriefV2(**common, tenant_id="model-tenant")
    with pytest.raises(ValidationError):
        ResearchBriefV2(**common, budget_lease_id="model-lease")
