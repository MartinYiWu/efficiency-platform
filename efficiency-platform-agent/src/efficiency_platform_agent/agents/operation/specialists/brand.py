"""品牌运营 Specialist。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class BrandOperationAgent(OperationSpecialistBase):
    """输出品牌定位、价值主张和信息体系策略。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.brand.strategy",
            capability_id=OperationSpecialistCapabilityId.BRAND_STRATEGY.value,
            task_type="operation.brand_strategy",
            prompt_bundle_id="operation.brand.strategy/1",
            quality_policy_id="operation-strategy-quality/1",
            output_title="品牌运营策略",
            output_label="brand_strategy",
            max_input_tokens=6_000,
            max_output_tokens=3_000,
        )


__all__ = ["BrandOperationAgent"]
