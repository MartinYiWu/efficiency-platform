"""活动运营 Specialist。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class CampaignOperationAgent(OperationSpecialistBase):
    """输出活动目标、机制、节奏、物料和风险计划。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.campaign.plan",
            capability_id=OperationSpecialistCapabilityId.CAMPAIGN_PLAN.value,
            task_type="operation.campaign_plan",
            prompt_bundle_id="operation.campaign.plan/1",
            quality_policy_id="operation-strategy-quality/1",
            output_title="活动运营方案",
            output_label="campaign_plan",
            max_input_tokens=7_000,
        )


__all__ = ["CampaignOperationAgent"]
