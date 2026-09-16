"""运营交付物、质量报告及其离线追溯校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from efficiency_platform_agent.core.run import JsonObject

from .evidence import EvidencePack, EvidenceRecord, TimeWindow, validate_evidence_pack
from .profiles import OperationContext

if TYPE_CHECKING:
    from .planning import OperationPlan

_STABLE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")


class DeliverableKind(StrEnum):
    """运营交付物的稳定大类。"""

    REPORT = "report"
    COPY = "copy"
    PLAN = "plan"
    ANALYSIS = "analysis"
    FACT = "report"
    RESEARCH_REPORT = "report"
    ANALYSIS_REPORT = "analysis"


class QualityDimension(StrEnum):
    """质量报告检查维度。"""

    EVIDENCE = "evidence"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    SAFETY = "safety"
    FORMAT = "format"
    SOURCE = "source"


class QualityStatus(StrEnum):
    """单项检查或质量报告的结果状态。"""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    UNKNOWN = "unknown"
    PASS = "passed"
    FAIL = "failed"


def _stable_id(name: str, value: str) -> None:
    if not isinstance(value, str) or _STABLE_ID.fullmatch(value) is None:
        raise ValueError(f"{name}必须是稳定的小写标识")


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}不能为空")


def _id_tuple(name: str, values: tuple[str, ...], *, allow_empty: bool = True) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{name}必须是不可变元组")
    if not allow_empty and not values:
        raise ValueError(f"{name}不能为空")
    if len(set(values)) != len(values):
        raise ValueError(f"{name}不能重复")
    for value in values:
        _stable_id(name, value)


@dataclass(frozen=True, slots=True)
class GenerationProcessReference:
    """交付物的可追溯生成过程引用，不保存 Prompt 正文或文件。"""

    process_id: str
    process_version: str
    plan_step_ids: tuple[str, ...]
    input_reference_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _stable_id("process_id", self.process_id)
        _text("process_version", self.process_version)
        _id_tuple("plan_step_ids", self.plan_step_ids)
        _id_tuple("input_reference_ids", self.input_reference_ids)


@dataclass(frozen=True, slots=True)
class OperationDeliverable:
    """一个独立、版本化且不可变的运营交付物声明。"""

    contract_version: str
    deliverable_id: str
    kind: DeliverableKind
    semantic_version: str
    title: str
    subject_reference_ids: tuple[str, ...]
    channel_ids: tuple[str, ...]
    time_window: TimeWindow | None
    payload: JsonObject
    evidence_ids: frozenset[str]
    assumption_ids: frozenset[str]
    warning_codes: frozenset[str]
    profile_reference_ids: tuple[str, ...]
    generation_process: GenerationProcessReference
    prompt_bundle_id: str | None
    prompt_bundle_version: str | None
    plan_id: str
    quality_report_id: str | None
    artifact_reference: str | None

    def __post_init__(self) -> None:
        if self.contract_version != "operation-deliverable/1":
            raise ValueError("contract_version必须为operation-deliverable/1")
        _stable_id("deliverable_id", self.deliverable_id)
        if not isinstance(self.kind, DeliverableKind):
            raise TypeError("kind必须是DeliverableKind")
        _text("semantic_version", self.semantic_version)
        _text("title", self.title)
        _id_tuple("subject_reference_ids", self.subject_reference_ids)
        _id_tuple("channel_ids", self.channel_ids)
        if not isinstance(self.payload, JsonObject):
            raise TypeError("payload必须是JsonObject")
        for field_name, values in (
            ("evidence_ids", self.evidence_ids),
            ("assumption_ids", self.assumption_ids),
            ("warning_codes", self.warning_codes),
        ):
            if not isinstance(values, frozenset):
                raise TypeError(f"{field_name}必须是不可变集合")
            for value in values:
                _stable_id(field_name, value)
        _id_tuple("profile_reference_ids", self.profile_reference_ids)
        if not isinstance(self.generation_process, GenerationProcessReference):
            raise TypeError("generation_process必须是GenerationProcessReference")
        if (self.prompt_bundle_id is None) != (self.prompt_bundle_version is None):
            raise ValueError("Prompt ID 与版本必须同时提供")
        if self.prompt_bundle_id is not None:
            _stable_id("prompt_bundle_id", self.prompt_bundle_id)
            _text("prompt_bundle_version", self.prompt_bundle_version or "")
        _stable_id("plan_id", self.plan_id)
        if self.quality_report_id is not None:
            _stable_id("quality_report_id", self.quality_report_id)
        if self.artifact_reference is not None:
            _text("artifact_reference", self.artifact_reference)


@dataclass(frozen=True, slots=True)
class OperationQualityCheck:
    """一个结构化质量维度检查及其安全说明。"""

    dimension: QualityDimension
    status: QualityStatus
    issue_reference_ids: tuple[str, ...]
    safe_message: str


@dataclass(frozen=True, slots=True)
class OperationQualityReport:
    """交付物质量门禁结果；S3 只记录修订次数，不执行修订。"""

    contract_version: str
    report_id: str
    task_id: str
    deliverable_ids: tuple[str, ...]
    checks: tuple[OperationQualityCheck, ...]
    final_status: QualityStatus
    revision_count: int

    def __post_init__(self) -> None:
        if self.contract_version != "operation-quality-report/1":
            raise ValueError("contract_version必须为operation-quality-report/1")
        _stable_id("report_id", self.report_id)
        _stable_id("task_id", self.task_id)
        _id_tuple("deliverable_ids", self.deliverable_ids)
        if not isinstance(self.checks, tuple) or not self.checks:
            raise ValueError("checks必须是非空不可变元组")
        for check in self.checks:
            if not isinstance(check, OperationQualityCheck):
                raise TypeError("checks只能包含OperationQualityCheck")
            if not isinstance(check.dimension, QualityDimension):
                raise TypeError("质量检查必须提供合法维度")
            if not isinstance(check.status, QualityStatus):
                raise ValueError("质量检查必须提供状态")  # noqa: TRY004  # 缺失质量状态按值错误拒绝
            _id_tuple("issue_reference_ids", check.issue_reference_ids)
            _text("safe_message", check.safe_message)
        if not isinstance(self.final_status, QualityStatus):
            raise TypeError("final_status必须是QualityStatus")
        if (
            not isinstance(self.revision_count, int)
            or isinstance(self.revision_count, bool)
            or not 0 <= self.revision_count <= 2
        ):
            raise ValueError("revision_count必须在0到2之间")


@dataclass(frozen=True, slots=True)
class DeliverableBundle:
    """同一任务和计划下的交付物集合，仅含 Artifact 引用。"""

    contract_version: str
    bundle_id: str
    task_id: str
    plan_id: str
    deliverables: tuple[OperationDeliverable, ...]
    evidence_pack_id: str | None
    quality_report_ids: tuple[str, ...]
    warning_codes: frozenset[str]

    def __post_init__(self) -> None:
        if self.contract_version != "deliverable-bundle/1":
            raise ValueError("contract_version必须为deliverable-bundle/1")
        _stable_id("bundle_id", self.bundle_id)
        _stable_id("task_id", self.task_id)
        _stable_id("plan_id", self.plan_id)
        if not isinstance(self.deliverables, tuple) or not self.deliverables:
            raise ValueError("deliverables必须是非空不可变元组")
        if any(
            not isinstance(item, OperationDeliverable) for item in self.deliverables
        ):
            raise TypeError("deliverables只能包含OperationDeliverable")
        if self.evidence_pack_id is not None:
            _stable_id("evidence_pack_id", self.evidence_pack_id)
        _id_tuple("quality_report_ids", self.quality_report_ids)
        if not isinstance(self.warning_codes, frozenset):
            raise TypeError("warning_codes必须是不可变集合")
        for code in self.warning_codes:
            _stable_id("warning_codes", code)


def build_quality_report(
    *,
    checks: tuple[OperationQualityCheck, ...],
    contract_version: str = "operation-quality-report/1",
    report_id: str = "quality-report",
    task_id: str = "task-a",
    deliverable_ids: tuple[str, ...] = ("deliverable-a",),
    final_status: QualityStatus = QualityStatus.PASSED,
    revision_count: int = 0,
) -> OperationQualityReport:
    """构造并校验结构化质量报告，不执行任何修订。"""

    return OperationQualityReport(
        contract_version,
        report_id,
        task_id,
        deliverable_ids,
        checks,
        final_status,
        revision_count,
    )


def _plan_fields(plan: OperationPlan) -> tuple[str, str, tuple[object, ...]]:
    """读取计划的冻结字段，避免在交付物模块复制计划模型。"""

    for name in ("task_id", "plan_id", "steps"):
        if not hasattr(plan, name):
            raise TypeError("plan必须提供OperationPlan冻结字段")
    return plan.task_id, plan.plan_id, plan.steps


def _profile_references(plan: OperationPlan) -> dict[str, str]:
    references: dict[str, str] = {}
    _, _, steps = _plan_fields(plan)
    for step in steps:
        context = getattr(step, "context", None)
        if not isinstance(context, OperationContext):
            raise TypeError("计划步骤必须带OperationContext")
        for reference in context.profile_references:
            references[reference.profile_id] = reference.semantic_version
    return references


def _is_fact_kind(kind: DeliverableKind) -> bool:
    return kind in {
        DeliverableKind.REPORT,
        DeliverableKind.ANALYSIS,
    }


def validate_deliverable_bundle(
    bundle: DeliverableBundle,
    plan: OperationPlan,
    evidence: EvidencePack | None,
) -> None:
    """校验交付物追溯链；不保存 Artifact、不访问网络、不生成内容。"""

    if not isinstance(bundle, DeliverableBundle):
        raise TypeError("bundle必须是DeliverableBundle")
    task_id, plan_id, steps = _plan_fields(plan)
    if bundle.task_id != task_id:
        raise ValueError("交付包 task_id 与计划不一致")
    if bundle.plan_id != plan_id:
        raise ValueError("交付包 plan_id 与计划不一致")
    step_ids = {getattr(step, "step_id", None) for step in steps}
    profiles = _profile_references(plan)
    evidence_by_id: dict[str, EvidenceRecord] = {}
    if evidence is not None:
        if not isinstance(evidence, EvidencePack):
            raise TypeError("evidence必须是EvidencePack或空值")
        validate_evidence_pack(evidence)
        if bundle.evidence_pack_id != evidence.pack_id:
            raise ValueError("交付包 evidence_pack_id 与证据包不一致")
        evidence_by_id = {record.evidence_id: record for record in evidence.records}
    for deliverable in bundle.deliverables:
        if deliverable.plan_id != plan_id:
            raise ValueError("交付物 plan_id 与计划不一致")
        if not deliverable.generation_process.plan_step_ids:
            raise ValueError("生成过程必须引用计划步骤")
        if not set(deliverable.generation_process.plan_step_ids).issubset(step_ids):
            raise ValueError("生成过程引用了不存在的计划步骤")
        if (deliverable.prompt_bundle_id is None) != (
            deliverable.prompt_bundle_version is None
        ):
            raise ValueError("Prompt ID 与版本必须同时提供")
        for profile_id in deliverable.profile_reference_ids:
            if profile_id not in profiles:
                raise ValueError("Profile 引用不在计划上下文中")
        if _is_fact_kind(deliverable.kind):
            if evidence is None:
                raise ValueError("事实型交付物必须引用有效证据")
            for evidence_id in deliverable.evidence_ids:
                if evidence_id not in evidence_by_id:
                    raise ValueError("交付物引用了不存在的证据")
            referenced = set(deliverable.evidence_ids)
            supported = {
                conclusion_id
                for record in evidence.records
                if record.evidence_id in referenced
                for conclusion_id in record.supported_conclusion_ids
            }
            if not referenced or not supported:
                raise ValueError("事实型交付物必须关联有效结论证据")
            if any(
                evidence_by_id[evidence_id].quality_status.value != "valid"
                or not evidence_by_id[evidence_id].within_time_window
                for evidence_id in referenced
            ):
                raise ValueError("事实型交付物引用了无效证据")


__all__ = [name for name in globals() if not name.startswith("_")]
