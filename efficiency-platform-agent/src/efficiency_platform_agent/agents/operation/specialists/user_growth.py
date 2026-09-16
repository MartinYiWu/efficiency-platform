"""用户增长运营 Specialist，仅生成分析和实验计划。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class UserGrowthAgent(OperationSpecialistBase):
    """生成用户分层、生命周期、漏斗和实验计划，不执行触达。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.user_growth.plan",
            capability_id=OperationSpecialistCapabilityId.USER_GROWTH_PLAN.value,
            task_type="operation.user_growth_plan",
            prompt_bundle_id="operation.user_growth.plan/1",
            quality_policy_id="operation-strategy-quality/1",
            output_title="用户增长计划",
            output_label="user_growth_plan",
            max_input_tokens=6_000,
            max_output_tokens=3_000,
        )


__all__ = ["UserGrowthAgent"]
