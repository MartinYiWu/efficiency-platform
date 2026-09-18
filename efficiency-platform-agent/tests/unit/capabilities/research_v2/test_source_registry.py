"""R01 来源 Registry 硬筛选测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from efficiency_platform_agent.capabilities.research.v2.source_admission import (
    SourceAdmission,
)
from efficiency_platform_agent.capabilities.research.v2.sources import (
    VerifiedSourceRegistry,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    OutputRequirementsV2,
    SourceConstraintsV2,
)
from efficiency_platform_agent.contracts.research_sources_v2 import (
    SourceRuntimeContextV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    CountPolicy,
    ResearchBriefV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from tests.unit.capabilities.research_v2.test_source_admission import descriptor

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def brief(*, source_ids=("source-1",), start_days=1):
    return ResearchBriefV2(
        trusted_context=TrustedResearchContextV2(
            tenant_id="tenant-1",
            run_id="run-1",
            task_id="task-1",
            budget_lease_id="lease-1",
        ),
        intent_revision=1,
        topic="AI",
        time_window=ResolvedTimeWindow(
            start=NOW - timedelta(days=start_days),
            end=NOW,
            timezone="Asia/Shanghai",
            precision="day",
            anchor=NOW,
        ),
        source_constraints=SourceConstraintsV2(
            allowed_source_ids=source_ids,
            languages=("zh",),
            event_regions=("cn",),
            primary_only=True,
        ),
        count_policy=CountPolicy(mode="exact", target=3, minimum=3),
        output_requirements=OutputRequirementsV2(
            output_types=("digest",), language="zh-CN"
        ),
        quality_policy_id="quality-1",
        policy_version="policy-1",
    )


def context(**updates):
    base = SourceRuntimeContextV2(
        tenant_id="tenant-1",
        run_id="run-1",
        now=NOW,
        allowed_source_ids=("source-1",),
        available_credential_source_ids=("source-1",),
        quota_remaining_by_source={"source-1": 1},
    )
    return base.model_copy(update=updates)


def registry(source=None, *, adapters=frozenset({"rss_atom"})):
    return VerifiedSourceRegistry(
        (source or descriptor(),),
        SourceAdmission(),
        registered_adapter_ids=adapters,
    )


class _QuotaLedger:
    def __init__(self, reservation_id=None):
        self.reservation_id = reservation_id
        self.calls = []

    def reserve(self, **request):
        self.calls.append(request)
        return self.reservation_id


def test_verified_free_source_is_available_after_all_filters() -> None:
    assert registry().list_available(context(), brief())[0].source_id == "source-1"


def test_unknown_adapter_user_scope_and_history_are_rejected_before_provider() -> None:
    assert (
        registry(adapters=frozenset({"other"})).list_available(context(), brief()) == ()
    )
    assert (
        registry().list_available(context(allowed_source_ids=("other",)), brief()) == ()
    )
    assert registry().list_available(context(), brief(start_days=31)) == ()


def test_authenticated_quota_source_requires_credential_and_real_remaining_snapshot() -> (
    None
):
    quota_source = descriptor(mode="free_quota")
    source_registry = registry(quota_source)

    decisions = source_registry.availability(
        context(available_credential_source_ids=(), quota_remaining_by_source={}),
        brief(),
    )
    assert decisions[0].reason_codes == ("SOURCE_CREDENTIAL_MISSING",)

    decisions = source_registry.availability(
        context(quota_remaining_by_source={}), brief()
    )
    assert decisions[0].reason_codes == ("SOURCE_QUOTA_UNKNOWN",)

    decisions = source_registry.availability(
        context(quota_remaining_by_source={"source-1": 0}), brief()
    )
    assert decisions[0].reason_codes == ("SOURCE_QUOTA_EXHAUSTED",)


def test_free_quota_requires_atomic_account_reservation_before_call() -> None:
    quota_source = descriptor(mode="free_quota")
    without_ledger = registry(quota_source).reserve_for_call(
        "source-1", context(), brief()
    )
    assert without_ledger.allowed is False
    assert without_ledger.reason_code == "SOURCE_QUOTA_LEDGER_UNAVAILABLE"

    ledger = _QuotaLedger("reservation-1")
    source_registry = VerifiedSourceRegistry(
        (quota_source,),
        SourceAdmission(),
        registered_adapter_ids=frozenset({"rss_atom"}),
        quota_ledger=ledger,
    )
    reserved = source_registry.reserve_for_call("source-1", context(), brief())
    assert reserved.allowed is True
    assert reserved.reservation_id == "reservation-1"
    assert ledger.calls == [
        {
            "source_id": "source-1",
            "tenant_id": "tenant-1",
            "run_id": "run-1",
            "units": 1,
        }
    ]


def test_disabled_fixture_configuration_never_becomes_available() -> None:
    disabled = descriptor(enabled=False)
    decision = registry(disabled).availability(context(), brief())[0]
    assert decision.available is False
    assert decision.reason_codes == ("SOURCE_DISABLED",)
