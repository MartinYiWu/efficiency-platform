"""运营 Specialist 能力到 V2 交付类型的稳定映射。"""

from __future__ import annotations

from typing import Literal

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

DeliverableKindV2 = Literal[
    "ranked_digest",
    "platform_content",
    "action_plan",
    "diagnosis",
    "retrospective",
]

_KIND_BY_CAPABILITY: dict[OperationSpecialistCapabilityId, DeliverableKindV2] = {
    OperationSpecialistCapabilityId.RESEARCH_INSIGHT: "ranked_digest",
    OperationSpecialistCapabilityId.CONTENT_CREATE: "platform_content",
    OperationSpecialistCapabilityId.CHANNEL_CONTENT: "platform_content",
    OperationSpecialistCapabilityId.BRAND_STRATEGY: "action_plan",
    OperationSpecialistCapabilityId.IP_STRATEGY: "action_plan",
    OperationSpecialistCapabilityId.PRODUCT_PLAN: "action_plan",
    OperationSpecialistCapabilityId.CAMPAIGN_PLAN: "action_plan",
    OperationSpecialistCapabilityId.USER_GROWTH_PLAN: "action_plan",
    OperationSpecialistCapabilityId.COMMUNITY_PLAN: "action_plan",
    OperationSpecialistCapabilityId.QUALITY_REVIEW: "diagnosis",
    OperationSpecialistCapabilityId.ANALYTICS_REVIEW: "retrospective",
}


def deliverable_kind_for(
    capability_id: OperationSpecialistCapabilityId | str,
    platform: str,
    research: bool,
) -> DeliverableKindV2:
    """返回能力对应的交付类型，未知能力失败关闭。"""

    if research and platform == "research":
        return "ranked_digest"
    try:
        normalized_capability_id = OperationSpecialistCapabilityId(capability_id)
        return _KIND_BY_CAPABILITY[normalized_capability_id]
    except (KeyError, ValueError) as exc:
        raise ValueError("DELIVERABLE_KIND_UNSUPPORTED") from exc


__all__ = ["DeliverableKindV2", "deliverable_kind_for"]
