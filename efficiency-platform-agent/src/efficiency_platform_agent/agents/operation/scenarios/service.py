"""S6 场景提交服务：只负责权威校验、计划编译和 Supervisor 委派。"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    OperationQualityReport,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    select_profiles_for_task,
)
from efficiency_platform_agent.agents.operation.contracts.scenarios import (
    compile_scenario_plan,
)
from efficiency_platform_agent.core.multi_agent import CompletionStatus
from efficiency_platform_agent.core.operation_progress import (
    report_operation_progress,
)

from .contracts import (
    ScenarioExecutionResult,
    ScenarioPackRegistry,
    ScenarioSubmission,
    ScenarioSupervisorPort,
    ScenarioSupervisorRequest,
)


class ScenarioPackService:
    """场景包的唯一生产入口，不创建 Agent 或图运行时。"""

    def __init__(
        self,
        registry: ScenarioPackRegistry,
        supervisor: ScenarioSupervisorPort,
        quality_gate=None,
    ) -> None:
        self.registry = registry
        self.supervisor = supervisor
        self.quality_gate = quality_gate

    async def run(self, submission: ScenarioSubmission) -> ScenarioExecutionResult:
        """按 Manifest→Profile→Plan→Supervisor 固定顺序执行一次。"""

        if not isinstance(submission, ScenarioSubmission):
            raise TypeError("submission必须是ScenarioSubmission")
        if (
            submission.request.request.tenant_id != submission.task_spec.tenant_id
            or submission.request.request.user_id != submission.task_spec.user_id
        ):
            raise ValueError("SCENARIO_IDENTITY_MISMATCH")
        try:
            manifest = self.registry.get(
                submission.scenario_id, submission.manifest_semantic_version
            )
        except Exception as error:
            raise ValueError("SCENARIO_NOT_FOUND") from error
        if submission.task_spec.requires_user_input:
            return ScenarioExecutionResult(
                submission.scenario_id,
                submission.manifest_semantic_version,
                CompletionStatus.WAITING_INPUT,
                None,
                None,
                submission.task_spec.missing_critical_condition_ids,
                (),
                submission.task_spec.missing_critical_condition_ids,
                frozenset({"SCENARIO_INPUT_REQUIRED"}),
                None,
            )
        try:
            context = select_profiles_for_task(
                submission.task_spec, cast(tuple, submission.profile_candidates)
            )
            plan = compile_scenario_plan(
                manifest, submission.task_spec, context, submission.plan_id
            )
        except Exception as error:
            raise ValueError("SCENARIO_PLAN_INVALID") from error
        request = ScenarioSupervisorRequest(
            "scenario-supervisor-request/1",
            submission.submission_id,
            submission.request,
            submission.task_spec,
            context,
            plan,
            submission.evidence_pack,
            submission.referenced_inputs,
        )
        result = await self.supervisor.execute_scenario(request)
        if not isinstance(result, ScenarioExecutionResult):
            raise ValueError("SCENARIO_RESULT_INVALID")  # noqa: TRY004
        if (
            result.scenario_id != submission.scenario_id
            or result.semantic_version != submission.manifest_semantic_version
        ):
            raise ValueError("SCENARIO_RESULT_MISMATCH")
        if (
            result.completion_status is CompletionStatus.COMPLETE
            and result.deliverable_bundle is None
        ):
            return ScenarioExecutionResult(
                result.scenario_id,
                result.semantic_version,
                CompletionStatus.FAILED,
                None,
                result.quality_report,
                result.missing_condition_ids,
                result.completed_scope,
                result.missing_scope,
                result.warning_codes,
                "SCENARIO_BUNDLE_INCOMPLETE",
            )
        if result.completion_status is CompletionStatus.PARTIAL and (
            (not result.completed_scope and not result.missing_scope)
            or not result.warning_codes
        ):
            return replace(
                result,
                completion_status=CompletionStatus.FAILED,
                deliverable_bundle=None,
                error_code=result.error_code or "SCENARIO_PARTIAL_INCOMPLETE",
            )
        if self.quality_gate is not None and result.deliverable_bundle is not None:
            await report_operation_progress("checking_delivery")
            report = self.quality_gate.validate(manifest, result)
            if not isinstance(report, OperationQualityReport):
                raise ValueError("SCENARIO_QUALITY_REPORT_INVALID")
            await report_operation_progress(
                "checking_delivery",
                event="quality_checked",
                payload={
                    "completed": len(result.deliverable_bundle.deliverables),
                    "target": len(result.deliverable_bundle.deliverables),
                },
            )
            bundle = replace(
                result.deliverable_bundle,
                quality_report_ids=tuple(
                    dict.fromkeys(
                        (
                            *result.deliverable_bundle.quality_report_ids,
                            report.report_id,
                        )
                    )
                ),
            )
            result = replace(result, quality_report=report, deliverable_bundle=bundle)
            if report.final_status is QualityStatus.FAILED:
                result = replace(
                    result,
                    completion_status=CompletionStatus.FAILED,
                    error_code="SCENARIO_QUALITY_FAILED",
                )
        return result


__all__ = ["ScenarioPackService"]
