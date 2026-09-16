"""渠道内容 Specialist。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class ChannelContentAgent(OperationSpecialistBase):
    """按单个 PlatformProfile 输出独立渠道成品。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.channel.content",
            capability_id=OperationSpecialistCapabilityId.CHANNEL_CONTENT.value,
            task_type="operation.channel_content",
            prompt_bundle_id="operation.channel.content/1",
            quality_policy_id="operation-channel-quality/1",
            output_title="渠道独立内容",
            output_label="channel_content",
            max_input_tokens=5_000,
        )


__all__ = ["ChannelContentAgent"]
