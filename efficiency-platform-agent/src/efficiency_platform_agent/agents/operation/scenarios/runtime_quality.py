"""面向真实成品结构的场景质量门，保留 S6 权威质量标识。"""

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    QUALITY_CHECKS,
)
from efficiency_platform_agent.capabilities.quality.deliverable_assembler import (
    DeliverableAssembler,
)
from efficiency_platform_agent.capabilities.quality.deliverable_v2 import (
    project_set_v2_to_v1,
)
from efficiency_platform_agent.contracts.deliverables import (
    DeliverableSetV2,
    DeliverySummaryV2,
)
from efficiency_platform_agent.core.run import JsonObject


def _plain(value):
    """解码领域交付物 JSON，不依赖任何专家实现。"""
    if isinstance(value, JsonObject):
        return {key: _plain(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class RuntimeScenarioQualityGate:
    """合并专家报告并实际检查成品结构、来源、范围与平台独立性。"""

    def __init__(self, deliverable_contract_version: str = "deliverable/1") -> None:
        self.deliverable_contract_version = deliverable_contract_version

    def validate(self, manifest, result) -> OperationQualityReport:
        """原始质量 ID 保存在检查说明，report_id 独立遵守稳定 ID 契约。"""
        bundle = result.deliverable_bundle
        items = tuple(bundle.deliverables) if bundle else ()
        declared = {item.requirement_id for item in manifest.output_requirements}
        actual = {item.deliverable_id for item in items}
        valid = bool(items) and len(actual) == len(items) and actual.issubset(declared)
        inherited = result.quality_report
        statuses = {
            check_id: QualityStatus.PASSED for check_id in manifest.quality_check_ids
        }
        statuses["q.required-deliverables/1"] = (
            QualityStatus.PASSED if valid else QualityStatus.FAILED
        )
        if manifest.profile_requirements and any(
            not item.profile_reference_ids for item in items
        ):
            statuses["q.profile-authority/1"] = QualityStatus.WARNING
        if manifest.scenario_id == "operation_review":
            statuses["q.metrics-definition/1"] = QualityStatus.WARNING
        if result.completion_status.value == "partial" and not (
            result.completed_scope and result.missing_scope
        ):
            statuses["q.partial-scope/1"] = QualityStatus.FAILED
        if inherited and inherited.revision_count > 2:
            statuses["q.review-round-limit/1"] = QualityStatus.FAILED
        payloads = [_plain(item.payload) for item in items]
        if self.deliverable_contract_version == "deliverable/2":
            view = DeliverableSetV2(
                run_id="quality-view",
                intent_revision=0,
                summary=DeliverySummaryV2(
                    message="场景质量视图", result_count=len(payloads), complete=True
                ),
                deliverables=payloads,
            )
            payloads = [
                item.model_dump(mode="json")
                for item in project_set_v2_to_v1(view).deliverables
            ]
        format_report = DeliverableAssembler().assess(
            payloads,
            task_id=bundle.task_id if bundle else "scenario-task",
            report_id=f"scenario-format-{result.scenario_id}",
            deliverable_ids=tuple(item.deliverable_id for item in items),
        )
        for check in format_report.checks:
            if check.dimension is QualityDimension.EVIDENCE:
                statuses["q.evidence-linkage/1"] = check.status
            if check.dimension is QualityDimension.CONSISTENCY:
                statuses["q.channel-independence/1"] = check.status
        if not manifest.quality_check_ids.issubset(QUALITY_CHECKS):
            raise ValueError("SCENARIO_QUALITY_CHECK_UNKNOWN")
        checks = tuple(
            OperationQualityCheck(
                QualityDimension.CONSISTENCY,
                statuses[check_id],
                (),
                f"{check_id}：场景确定性质量检查",
            )
            for check_id in sorted(manifest.quality_check_ids)
        )
        checks += format_report.checks
        if inherited:
            checks += inherited.checks
        final = (
            QualityStatus.FAILED
            if any(check.status is QualityStatus.FAILED for check in checks)
            else QualityStatus.WARNING
            if any(
                check.status in {QualityStatus.WARNING, QualityStatus.UNKNOWN}
                for check in checks
            )
            else QualityStatus.PASSED
        )
        return OperationQualityReport(
            "operation-quality-report/1",
            f"scenario-quality-{result.scenario_id}",
            bundle.task_id if bundle else "scenario-task",
            tuple(item.deliverable_id for item in items),
            checks,
            final,
            inherited.revision_count if inherited else 0,
        )
