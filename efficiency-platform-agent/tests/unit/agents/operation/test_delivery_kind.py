"""运营 Specialist 到 V2 交付类型的稳定映射测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.agents.operation.delivery_kind import (
    deliverable_kind_for,
)


def test_specialist_capability_maps_to_stable_delivery_kind() -> None:
    assert (
        deliverable_kind_for("operation.research.insight", "research", True)
        == "ranked_digest"
    )
    assert (
        deliverable_kind_for("operation.channel.content", "xiaohongshu", False)
        == "platform_content"
    )
    assert (
        deliverable_kind_for("operation.campaign.plan", "活动策划", False)
        == "action_plan"
    )
    assert (
        deliverable_kind_for("operation.quality.review", "内容诊断", False)
        == "diagnosis"
    )
    assert (
        deliverable_kind_for("operation.analytics.review", "运营复盘", False)
        == "retrospective"
    )


def test_delivery_kind_accepts_the_canonical_capability_enum() -> None:
    assert (
        deliverable_kind_for(
            OperationSpecialistCapabilityId.CONTENT_CREATE,
            "wechat",
            False,
        )
        == "platform_content"
    )


def test_unknown_capability_fails_closed() -> None:
    with pytest.raises(ValueError, match="^DELIVERABLE_KIND_UNSUPPORTED$"):
        deliverable_kind_for("operation.unknown", "unknown", False)
