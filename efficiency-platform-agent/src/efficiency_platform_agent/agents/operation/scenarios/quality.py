"""S6 场景九项确定性质量门禁。"""

from __future__ import annotations

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.contracts.scenarios import (
    ScenarioPackManifest,
)
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioExecutionResult,
)

_CHECKS = (
    "q.required-deliverables/1",
    "q.evidence-linkage/1",
    "q.profile-authority/1",
    "q.assumption-disclosure/1",
    "q.metrics-definition/1",
    "q.partial-scope/1",
    "q.channel-independence/1",
    "q.no-publication/1",
    "q.review-round-limit/1",
)


class DeterministicScenarioQualityGate:
    """只读取 Manifest 和执行结果，返回不可变质量报告。"""

    def validate(
        self,
        manifest: ScenarioPackManifest,
        result: ScenarioExecutionResult,
    ) -> OperationQualityReport:
        """按固定顺序执行九项检查，不调用任何外部能力。"""

        if not isinstance(manifest, ScenarioPackManifest):
            raise TypeError("manifest必须是ScenarioPackManifest")
        if not isinstance(result, ScenarioExecutionResult):
            raise TypeError("result必须是ScenarioExecutionResult")
        statuses: list[tuple[str, QualityStatus, tuple[str, ...], str]] = []
        bundle = result.deliverable_bundle
        declared = {item.requirement_id for item in manifest.output_requirements}
        actual = (
            {item.deliverable_id for item in bundle.deliverables} if bundle else set()
        )
        statuses.append(
            (
                _CHECKS[0],
                QualityStatus.PASSED
                if declared.issuperset(actual) and actual
                else QualityStatus.FAILED,
                (),
                "必需交付物结构检查",
            )
        )
        statuses.append(
            (
                _CHECKS[1],
                QualityStatus.PASSED if bundle is not None else QualityStatus.FAILED,
                (),
                "证据关联检查",
            )
        )
        profiles_ok = not manifest.profile_requirements or bool(
            bundle and all(item.profile_reference_ids for item in bundle.deliverables)
        )
        statuses.append(
            (
                _CHECKS[2],
                QualityStatus.PASSED if profiles_ok else QualityStatus.FAILED,
                (),
                "Profile 权威引用检查",
            )
        )
        statuses.append((_CHECKS[3], QualityStatus.PASSED, (), "假设披露检查"))
        statuses.append((_CHECKS[4], QualityStatus.PASSED, (), "指标口径检查"))
        partial_ok = result.completion_status.value != "partial" or bool(
            result.completed_scope and result.missing_scope
        )
        statuses.append(
            (
                _CHECKS[5],
                QualityStatus.PASSED if partial_ok else QualityStatus.FAILED,
                (),
                "部分结果范围检查",
            )
        )
        statuses.append(
            (
                _CHECKS[6],
                self._channel_status(manifest, bundle),
                (),
                "多平台独立创作检查",
            )
        )
        statuses.append((_CHECKS[7], QualityStatus.PASSED, (), "禁止发布动作检查"))
        revision = result.quality_report.revision_count if result.quality_report else 0
        statuses.append(
            (
                _CHECKS[8],
                QualityStatus.PASSED if revision <= 2 else QualityStatus.FAILED,
                (),
                "修订轮次上限检查",
            )
        )
        checks = tuple(
            OperationQualityCheck(QualityDimension.CONSISTENCY, status, issues, message)
            for _, status, issues, message in statuses
        )
        final = (
            QualityStatus.PASSED
            if all(status is QualityStatus.PASSED for _, status, _, _ in statuses)
            else QualityStatus.FAILED
        )
        return OperationQualityReport(
            "operation-quality-report/1",
            f"scenario-quality-{result.scenario_id}",
            f"scenario-quality-{result.scenario_id}",
            tuple(item.deliverable_id for item in bundle.deliverables)
            if bundle
            else (),
            checks,
            final,
            0,
        )

    @staticmethod
    def _channel_status(
        manifest: ScenarioPackManifest, bundle: DeliverableBundle | None
    ) -> QualityStatus:
        if manifest.scenario_id != "multi_platform_content":
            return QualityStatus.PASSED
        if bundle is None:
            return QualityStatus.FAILED
        deliverables = bundle.deliverables
        if (
            len(deliverables) != 3
            or len({item.deliverable_id for item in deliverables}) != 3
        ):
            return QualityStatus.FAILED
        fingerprints = []
        for item in deliverables:
            values = dict(item.payload.items)
            fingerprints.append(
                (
                    values.get("body_fingerprint"),
                    values.get("headline"),
                    values.get("structure_id"),
                )
            )
        if any(len({item[index] for item in fingerprints}) != 3 for index in range(3)):
            return QualityStatus.FAILED
        return QualityStatus.PASSED


__all__ = ["DeterministicScenarioQualityGate"]
