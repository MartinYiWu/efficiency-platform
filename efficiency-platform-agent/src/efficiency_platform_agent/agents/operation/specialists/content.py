"""内容运营 Specialist。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)

from ._base import OperationSpecialistBase


class ContentAgent(OperationSpecialistBase):
    """输出平台中立的选题、内容支柱和日历 Brief。"""

    def __init__(self) -> None:
        super().__init__(
            agent_id="operation.content.create",
            capability_id=OperationSpecialistCapabilityId.CONTENT_CREATE.value,
            task_type="operation.content_create",
            prompt_bundle_id="operation.content.create/1",
            quality_policy_id="operation-content-quality/1",
            output_title="内容创作 Brief",
            output_label="content_brief",
            max_input_tokens=6_000,
        )


__all__ = ["ContentAgent"]
