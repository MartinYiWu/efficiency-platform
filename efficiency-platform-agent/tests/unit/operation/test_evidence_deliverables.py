"""运营证据、交付物与质量报告离线契约测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
    validate_deliverable_bundle,
)
from efficiency_platform_agent.agents.operation.contracts.evidence import (
    ConclusionSupport,
    EvidenceDuplicateStatus,
    EvidencePack,
    EvidenceQualityStatus,
    EvidenceRecord,
    validate_evidence_pack,
)
from efficiency_platform_agent.agents.operation.contracts.planning import (
    OperationPlan,
    OperationPlanStep,
)
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
    ProfileKind,
    ProfileReference,
)
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject


def _member(enum_type: type, name: str):
    """按名称取得枚举成员；测试在枚举扩展时仍保持语义明确。"""

    try:
        return enum_type[name]
    except KeyError:
        return next(iter(enum_type))


def _budget() -> ExecutionBudget:
    return ExecutionBudget(
        max_iterations=4,
        max_tool_calls=4,
        max_input_tokens=400,
        max_output_tokens=400,
        timeout_ms=5_000,
        max_cost_microunits=100,
    )


def _context() -> OperationContext:
    profile = ProfileReference(
        profile_id="profile.brand",
        kind=_member(ProfileKind, "BRAND"),
        semantic_version="1.0.0",
        fact_ids=("fact.brand",),
    )
    return OperationContext(
        contract_version="operation-context/1",
        context_id="context-a",
        tenant_id="tenant-a",
        task_id="task-a",
        profile_references=(profile,),
        source_scope_ids=frozenset(),
    )


def _plan() -> OperationPlan:
    context = _context()
    step = OperationPlanStep(
        step_id="research",
        task_type="operation.research",
        depends_on_step_ids=(),
        required_capabilities=CapabilityRequirement(
            all_of=frozenset({"operation.research"})
        ),
        input_schema_version="operation-research-input/1",
        output_schema_version="operation-research-output/1",
        input_reference_ids=(),
        context=context,
        allowed_tools=frozenset(),
        required_permissions=frozenset(),
        budget=_budget(),
        expected_deliverable_ids=("deliverable-a",),
        quality_check_ids=frozenset({"evidence"}),
        required=True,
        failure_behavior=_member(
            __import__(
                "efficiency_platform_agent.agents.operation.contracts.planning",
                fromlist=["FailureBehavior"],
            ).FailureBehavior,
            "FAIL",
        ),
    )
    return OperationPlan(
        contract_version="operation-plan/1",
        plan_id="plan-a",
        task_id="task-a",
        strategy=StrategyMode.DIRECT,
        source_template_id=None,
        source_template_version=None,
        success_conditions=("deliverable_ready",),
        steps=(step,),
        total_budget=_budget(),
        termination_conditions=frozenset({"complete"}),
    )


def _record(
    evidence_id: str,
    url: str,
    duplicate_status: EvidenceDuplicateStatus,
    conclusion_ids: frozenset[str] = frozenset({"claim-1"}),
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        title="公开资料",
        publisher="公开来源",
        source_url=url,
        published_at_epoch_ms=1,
        retrieved_at_epoch_ms=2,
        source_scope=next(
            iter(
                __import__(
                    "efficiency_platform_agent.agents.operation.contracts.task",
                    fromlist=["SourceScope"],
                ).SourceScope
            )
        ),
        supported_conclusion_ids=conclusion_ids,
        within_time_window=True,
        duplicate_status=duplicate_status,
        quality_status=_member(EvidenceQualityStatus, "VALID"),
    )


def _pack(records: tuple[EvidenceRecord, ...]) -> EvidencePack:
    evidence_ids = frozenset(record.evidence_id for record in records)
    return EvidencePack(
        contract_version="evidence-pack/1",
        pack_id="pack-a",
        task_id="task-a",
        records=records,
        supports=(ConclusionSupport("claim-1", evidence_ids),),
    )


def _process(
    *, plan_step_ids: tuple[str, ...] = ("research",)
) -> GenerationProcessReference:
    return GenerationProcessReference(
        process_id="process-a",
        process_version="1.0.0",
        plan_step_ids=plan_step_ids,
        input_reference_ids=(),
    )


def _deliverable(
    *,
    kind: DeliverableKind | None = None,
    evidence_ids: frozenset[str] = frozenset({"evidence-a"}),
    process: GenerationProcessReference | None = None,
    prompt_bundle_id: str | None = None,
    prompt_bundle_version: str | None = None,
    profile_reference_ids: tuple[str, ...] = ("profile.brand",),
) -> OperationDeliverable:
    return OperationDeliverable(
        contract_version="operation-deliverable/1",
        deliverable_id="deliverable-a",
        kind=kind or _member(DeliverableKind, "FACT"),
        semantic_version="1.0.0",
        title="资料结论",
        subject_reference_ids=(),
        channel_ids=(),
        time_window=None,
        payload=JsonObject((("content", "内容"),)),
        evidence_ids=evidence_ids,
        assumption_ids=frozenset(),
        warning_codes=frozenset(),
        profile_reference_ids=profile_reference_ids,
        generation_process=process or _process(),
        prompt_bundle_id=prompt_bundle_id,
        prompt_bundle_version=prompt_bundle_version,
        plan_id="plan-a",
        quality_report_id=None,
        artifact_reference=None,
    )


def _bundle(
    deliverable: OperationDeliverable,
    *,
    evidence_pack_id: str | None = "pack-a",
) -> DeliverableBundle:
    return DeliverableBundle(
        contract_version="deliverable-bundle/1",
        bundle_id="bundle-a",
        task_id="task-a",
        plan_id="plan-a",
        deliverables=(deliverable,),
        evidence_pack_id=evidence_pack_id,
        quality_report_ids=(),
        warning_codes=frozenset(),
    )


def test_evidence_pack_requires_truthful_duplicate_status_for_normalized_url() -> None:
    first = _record("evidence-a", "https://a.example/x", EvidenceDuplicateStatus.UNIQUE)
    wrong = _record(
        "evidence-b", "https://a.example/x/", EvidenceDuplicateStatus.UNIQUE
    )
    with pytest.raises(ValueError, match="重复状态与规范 URL 分组不一致"):
        validate_evidence_pack(_pack((first, wrong)))

    duplicate = _record(
        "evidence-b", "https://a.example/x/", EvidenceDuplicateStatus.DUPLICATE
    )
    validate_evidence_pack(_pack((first, duplicate)))


def test_evidence_pack_rejects_orphan_conclusion() -> None:
    record = _record(
        "evidence-a", "https://a.example/x", EvidenceDuplicateStatus.UNIQUE
    )
    pack = EvidencePack(
        contract_version="evidence-pack/1",
        pack_id="pack-a",
        task_id="task-a",
        records=(record,),
        supports=(ConclusionSupport("claim-1", frozenset({"evidence-missing"})),),
    )
    with pytest.raises(ValueError):
        validate_evidence_pack(pack)


def test_fact_deliverable_rejects_unbacked_claim_but_plan_deliverable_allows_no_evidence() -> (
    None
):
    plan = _plan()
    fact_bundle = _bundle(_deliverable(evidence_ids=frozenset()), evidence_pack_id=None)
    with pytest.raises(ValueError):
        validate_deliverable_bundle(fact_bundle, plan, None)

    plan_kind = _member(DeliverableKind, "PLAN")
    plan_bundle = _bundle(
        _deliverable(kind=plan_kind, evidence_ids=frozenset()), evidence_pack_id=None
    )
    validate_deliverable_bundle(plan_bundle, plan, None)


def test_quality_report_requires_dimension_status_and_issue_reference() -> None:
    quality_check = OperationQualityCheck(
        _member(QualityDimension, "EVIDENCE"),
        None,
        (),
        "",
    )
    with pytest.raises(ValueError):
        OperationQualityReport(
            contract_version="operation-quality-report/1",
            report_id="report-a",
            task_id="task-a",
            deliverable_ids=("deliverable-a",),
            checks=(quality_check,),
            final_status=_member(QualityStatus, "PASSED"),
            revision_count=0,
        )


def test_deliverable_requires_generation_process_and_complete_prompt_version_pair() -> (
    None
):
    plan = _plan()
    with pytest.raises(ValueError, match="生成过程必须引用计划步骤"):
        validate_deliverable_bundle(
            _bundle(
                _deliverable(process=_process(plan_step_ids=())), evidence_pack_id=None
            ),
            plan,
            None,
        )
    with pytest.raises(ValueError, match="Prompt ID 与版本必须同时提供"):
        validate_deliverable_bundle(
            _bundle(
                _deliverable(
                    prompt_bundle_id="operation.compose", prompt_bundle_version=None
                ),
                evidence_pack_id=None,
            ),
            plan,
            None,
        )


def test_deliverable_profile_reference_must_resolve_with_version_from_plan_context() -> (
    None
):
    with pytest.raises(ValueError, match="Profile 引用不在计划上下文中"):
        validate_deliverable_bundle(
            _bundle(
                _deliverable(profile_reference_ids=("profile.unknown",)),
                evidence_pack_id=None,
            ),
            _plan(),
            None,
        )
