"""IP 运营 Specialist。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class IPOperationAgent(OperationSpecialistBase):
    """输出人设边界、内容支柱和成长计划。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.ip.strategy",
            capability_id=OperationSpecialistCapabilityId.IP_STRATEGY.value,
            task_type="operation.ip_strategy",
            prompt_bundle_id="operation.ip.strategy/1",
            quality_policy_id="operation-strategy-quality/1",
            output_title="IP 运营策略",
            output_label="ip_strategy",
            max_input_tokens=6_000,
            max_output_tokens=3_000,
        )


__all__ = ["IPOperationAgent"]
