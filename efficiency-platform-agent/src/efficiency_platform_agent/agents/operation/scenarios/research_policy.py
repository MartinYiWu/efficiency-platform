"""运营研究场景的版本化质量策略默认值。"""

from __future__ import annotations

from efficiency_platform_agent.contracts.research_v2 import ResearchPolicySnapshotV2


def offline_research_quality_policy() -> ResearchPolicySnapshotV2:
    """返回离线阶段固定策略；不代表任何真实来源已准入。"""

    return ResearchPolicySnapshotV2(
        quality_policy_id="research-quality-v2",
        policy_version="research-quality/2.0.0-offline",
        minimum_independent_sources=1,
        require_primary_for_key_claims=False,
        max_collection_rounds=3,
        max_no_gain_rounds=1,
    )


__all__ = ["offline_research_quality_policy"]
