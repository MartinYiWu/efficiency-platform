"""社群运营 Specialist，仅生成栏目、互动和 SOP。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class CommunityAgent(OperationSpecialistBase):
    """生成社群定位、栏目、互动激励和运营 SOP，不发送消息。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.community.plan",
            capability_id=OperationSpecialistCapabilityId.COMMUNITY_PLAN.value,
            task_type="operation.community_plan",
            prompt_bundle_id="operation.community.plan/1",
            quality_policy_id="operation-strategy-quality/1",
            output_title="社群运营计划",
            output_label="community_plan",
            max_input_tokens=6_000,
            max_output_tokens=3_000,
        )


__all__ = ["CommunityAgent"]
