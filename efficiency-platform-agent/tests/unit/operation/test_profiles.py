"""Profile 权威性和最小上下文的离线契约测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.profiles import (
    AudienceProfile,
    BrandProfile,
    CampaignProfile,
    ChannelProfile,
    IPProfile,
    MetricProfile,
    OperationContext,
    ProductProfile,
    ProfileFact,
    ProfileFactState,
    ProfileKind,
    ProfileReference,
    select_profiles_for_task,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    OperationDomain,
    OperationIntent,
    OperationTaskSpec,
    SourceScope,
)
from efficiency_platform_agent.core.run import JsonObject


def _fact(
    fact_id: str = "fact-brand",
    *,
    state: ProfileFactState = ProfileFactState.CONFIRMED,
    confirmed_at_epoch_ms: int | None = 1,
    expires_at_epoch_ms: int | None = None,
) -> ProfileFact:
    return ProfileFact(
        fact_id=fact_id,
        field_name="定位",
        value=JsonObject(),
        source_kind=SourceScope.PROFILE,
        source_reference="profile:brand",
        state=state,
        confirmed_at_epoch_ms=confirmed_at_epoch_ms,
        expires_at_epoch_ms=expires_at_epoch_ms,
    )


def _task(
    *,
    tenant_id: str = "tenant-a",
    task_id: str = "task-a",
    domains: frozenset[OperationDomain] = frozenset({OperationDomain.BRAND}),
) -> OperationTaskSpec:
    return OperationTaskSpec(
        contract_version="operation-task/1",
        task_id=task_id,
        tenant_id=tenant_id,
        user_id="user-a",
        session_id="session-a",
        parent_task_id=None,
        operation_id="operation-a",
        intent=OperationIntent.CREATE,
        domains=domains,
        goals=(),
        objects=(),
        key_conditions=(),
        assumptions=(),
        source_scopes=frozenset({SourceScope.PROFILE}),
        deliverable_requirements=(),
        missing_critical_condition_ids=(),
        requires_user_input=False,
    )


def _brand(
    *, tenant_id: str = "tenant-a", fact: ProfileFact | None = None
) -> BrandProfile:
    return BrandProfile(
        contract_version="profile/1",
        profile_id="brand-main",
        tenant_id=tenant_id,
        semantic_version="1.0.0",
        facts=(fact or _fact(),),
    )


class ProfileContractTests(unittest.TestCase):
    """验证 Profile 的事实状态、租户边界和上下文裁剪。"""

    def test_channel_profile_requires_versioned_rules(self) -> None:
        with self.assertRaises(ValueError):
            ChannelProfile(
                contract_version="profile/1",
                profile_id="channel-xhs",
                tenant_id="tenant-a",
                channel_id="xiaohongshu",
                rules_version="",
                rules=JsonObject(),
                facts=(_fact("fact-channel"),),
                semantic_version="1.0.0",
            )

    def test_candidate_brand_fact_cannot_be_marked_confirmed(self) -> None:
        with self.assertRaises(ValueError):
            _fact(
                state=ProfileFactState.CANDIDATE,
                confirmed_at_epoch_ms=1,
            )

    def test_context_rejects_cross_tenant_profile_and_unrequested_profile(self) -> None:
        with self.assertRaises(ValueError):
            select_profiles_for_task(_task(), (_brand(tenant_id="tenant-b"),))
        with self.assertRaises(ValueError):
            select_profiles_for_task(
                _task(domains=frozenset({OperationDomain.PRODUCT})),
                (_brand(),),
            )

    def test_context_selects_only_requested_profile_and_preserves_version(self) -> None:
        context = select_profiles_for_task(_task(), (_brand(),))
        self.assertIsInstance(context, OperationContext)
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.task_id, "task-a")
        self.assertEqual(context.profile_references[0].kind, ProfileKind.BRAND)
        self.assertEqual(context.profile_references[0].semantic_version, "1.0.0")
        self.assertEqual(context.profiles, context.profile_references)

    def test_expired_confirmed_fact_is_rejected(self) -> None:
        expired = _brand(
            fact=_fact(
                expires_at_epoch_ms=2,
            )
        )
        with self.assertRaises(ValueError):
            select_profiles_for_task(_task(), (expired,))

    def test_metric_profile_has_definition_and_target_but_no_actual_value(self) -> None:
        metric = MetricProfile(
            contract_version="profile/1",
            profile_id="metric-awareness",
            tenant_id="tenant-a",
            semantic_version="1.0.0",
            facts=(_fact("fact-metric"),),
            metric_id="awareness",
            definition="有效曝光次数",
            target_value=JsonObject(),
            period="2026-Q3",
        )
        self.assertFalse(hasattr(metric, "actual_value"))

    def test_all_profile_variants_share_immutable_fact_skeleton(self) -> None:
        profiles = (
            _brand(),
            IPProfile(
                "profile/1",
                "ip-main",
                "tenant-a",
                "1.0.0",
                (_fact("fact-ip"),),
                "confirmed",
            ),
            ProductProfile(
                "profile/1",
                "product-main",
                "tenant-a",
                "1.0.0",
                (_fact("fact-product"),),
                "product-a",
            ),
            AudienceProfile(
                "profile/1",
                "audience-main",
                "tenant-a",
                "1.0.0",
                (_fact("fact-audience"),),
                "segment-a",
            ),
            MetricProfile(
                "profile/1",
                "metric-main",
                "tenant-a",
                "1.0.0",
                (_fact("fact-metric-2"),),
                "metric-a",
                "口径",
                None,
                "月",
            ),
            ChannelProfile(
                "profile/1",
                "channel-main",
                "tenant-a",
                "wechat",
                "2026.1",
                JsonObject(),
                (_fact("fact-channel-2"),),
                "1.0.0",
            ),
            CampaignProfile(
                "profile/1",
                "campaign-main",
                "tenant-a",
                "1.0.0",
                (_fact("fact-campaign"),),
                "campaign-a",
            ),
        )
        for profile in profiles:
            with self.subTest(profile=type(profile).__name__):
                self.assertIsInstance(profile.facts, tuple)
                self.assertEqual(profile.contract_version, "profile/1")

    def test_profile_reference_rejects_duplicate_fact_ids(self) -> None:
        with self.assertRaises(ValueError):
            ProfileReference(
                "brand-main", ProfileKind.BRAND, "1.0.0", ("fact-a", "fact-a")
            )


if __name__ == "__main__":
    unittest.main()
