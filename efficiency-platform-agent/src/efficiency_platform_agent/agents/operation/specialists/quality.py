"""QualityReviewAgent 的确定性结构检查与有限修订入口。"""

from __future__ import annotations

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.agents.operation.quality.revision import (
    RevisionDecision,
    decide_revision,
)

from ._base import OperationSpecialistBase


class QualityReviewAgent(OperationSpecialistBase):
    """审校交付物并只输出结构化质量报告，不自行重调 Specialist。"""

    def __init__(self, model: object | None = None) -> None:
        super().__init__(
            agent_id="operation.quality.review",
            capability_id=OperationSpecialistCapabilityId.QUALITY_REVIEW.value,
            task_type="operation.quality_review",
            prompt_bundle_id="operation.quality.review/1",
            quality_policy_id="operation-quality-review/1",
            output_title="运营交付物质量审校",
            output_label="quality_review",
            max_input_tokens=6_000,
            max_output_tokens=2_000,
        )
        self._model = model

    def review(
        self,
        bundle: DeliverableBundle,
        *,
        task_id: str | None = None,
        current_revision: int = 0,
        max_revisions: int = 2,
        revision_budget_available: bool = True,
    ) -> tuple[OperationQualityReport, RevisionDecision]:
        """执行确定性检查并计算一次有限修订决策。"""

        if not isinstance(bundle, DeliverableBundle):
            raise TypeError("bundle必须是DeliverableBundle")
        actual_task_id = task_id or bundle.task_id
        ids = tuple(item.deliverable_id for item in bundle.deliverables)
        issue_ids: tuple[str, ...] = ()
        status = QualityStatus.PASSED
        message = "交付物结构完整且未发现跨交付物冲突"
        channels: dict[str, str] = {}
        for item in bundle.deliverables:
            for channel in item.channel_ids:
                previous = channels.get(channel)
                if previous is not None and previous != item.deliverable_id:
                    issue_ids = (previous, item.deliverable_id)
                    status = QualityStatus.FAILED
                    message = "同一渠道存在多个交付物，需要复核排版策略"
                channels[channel] = item.deliverable_id
        report = OperationQualityReport(
            "operation-quality-report/1",
            f"quality-report-{actual_task_id}",
            actual_task_id,
            ids,
            (
                OperationQualityCheck(
                    QualityDimension.CONSISTENCY,
                    status,
                    issue_ids,
                    message,
                ),
            ),
            status,
            current_revision,
        )
        decision = decide_revision(
            report,
            current_revision=current_revision,
            max_revisions=max_revisions,
            revision_budget_available=revision_budget_available,
        )
        return report, decision


__all__ = ["QualityReviewAgent"]
