"""产品运营 Specialist。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class ProductOperationAgent(OperationSpecialistBase):
    """输出产品发布、教育和冷启动计划。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.product.plan",
            capability_id=OperationSpecialistCapabilityId.PRODUCT_PLAN.value,
            task_type="operation.product_plan",
            prompt_bundle_id="operation.product.plan/1",
            quality_policy_id="operation-strategy-quality/1",
            output_title="产品运营计划",
            output_label="product_operation_plan",
            max_input_tokens=6_000,
            max_output_tokens=3_000,
        )


__all__ = ["ProductOperationAgent"]
