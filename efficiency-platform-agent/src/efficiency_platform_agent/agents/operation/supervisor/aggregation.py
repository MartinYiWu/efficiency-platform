"""Supervisor 的确定性结果聚合与有限修订裁决。"""

from __future__ import annotations

from dataclasses import dataclass

from efficiency_platform_agent.core.multi_agent import (
    CompletionStatus,
    TaskExecutionStatus,
    TaskGraph,
    TaskOutcome,
)

from ..contracts.deliverables import (
    DeliverableBundle,
    OperationDeliverable,
    OperationQualityReport,
)
from ..contracts.evidence import ConclusionSupport, EvidencePack, EvidenceRecord


@dataclass(frozen=True, slots=True)
class AggregationResult:
    """一个任务图波次的结构化聚合结果。"""

    completion_status: CompletionStatus
    deliverables: tuple[OperationDeliverable, ...]
    evidence_pack: EvidencePack | None
    completed_scope: tuple[str, ...]
    missing_scope: tuple[str, ...]
    warnings: tuple[str, ...]
    failures: tuple[str, ...]
    conflicts: tuple[str, ...]
    quality_reports: tuple[OperationQualityReport, ...] = ()


@dataclass(frozen=True, slots=True)
class RevisionDecision:
    """修订是否可以进入后续计划编译的确定性裁决。"""

    allowed: bool
    reason_code: str
    next_revision: int | None

    @classmethod
    def decide(
        cls,
        *,
        revision: int,
        max_revisions: int = 2,
        remaining_budget: bool,
        reason_code: str = "QUALITY_NOT_MET",
        current_task_count: int = 0,
        requested_task_count: int = 0,
    ) -> RevisionDecision:
        """按修订次数、预算和任务数共同判断，不修改任何运行状态。"""
        if revision < 0 or max_revisions < 0:
            raise ValueError("修订次数不得为负数")
        if current_task_count < 0 or requested_task_count < 0:
            raise ValueError("任务数不得为负数")
        if current_task_count + requested_task_count > 16:
            return cls(False, "TASK_LIMIT_EXCEEDED", None)
        if revision >= max_revisions:
            return cls(False, "REVISION_LIMIT_EXCEEDED", None)
        if not remaining_budget:
            return cls(False, "BUDGET_EXHAUSTED", None)
        if reason_code not in {
            "QUALITY_NOT_MET",
            "OUTPUT_SCHEMA_INVALID",
            "SPECIALIST_PARTIAL_FAILURE",
            "RESEARCH_INSUFFICIENT",
        }:
            return cls(False, "REVISION_REASON_NOT_REPAIRABLE", None)
        return cls(True, reason_code, revision + 1)


def _append_unique(values: list[str], value: str) -> None:
    """按首次出现顺序追加字符串。"""
    if value not in values:
        values.append(value)


def _envelope_for(envelopes: tuple[object, ...], task_id: str) -> object | None:
    for envelope in envelopes:
        if getattr(envelope, "task_id", None) == task_id:
            return envelope
    return None


class ResultAggregator:
    """只收集任务结果，不执行业务判断或 S3 assembly。"""

    def aggregate(
        self,
        graph: TaskGraph,
        outcomes: tuple[TaskOutcome, ...],
        envelopes: tuple[object, ...] = (),
    ) -> AggregationResult:
        """按图拓扑顺序聚合结果、范围、警告、失败和冲突。"""
        if not isinstance(graph, TaskGraph):
            raise TypeError("graph 必须是 TaskGraph")
        if not isinstance(outcomes, tuple) or not isinstance(envelopes, tuple):
            raise TypeError("outcomes 和 envelopes 必须是不可变 tuple")
        by_id: dict[str, TaskOutcome] = {}
        for candidate in outcomes:
            if not isinstance(candidate, TaskOutcome):
                raise TypeError("outcomes 只能包含 TaskOutcome")
            if candidate.task_id in by_id:
                raise ValueError("同一任务只能有一个聚合结果")
            by_id[candidate.task_id] = candidate
        nodes = {node.task_id: node for node in graph.tasks}
        unknown_outcomes = set(by_id).difference(nodes)
        if unknown_outcomes:
            raise ValueError("结果引用了任务图外的任务")
        envelope_task_ids: set[str] = set()
        for envelope in envelopes:
            task_id = getattr(envelope, "task_id", None)
            if not isinstance(task_id, str) or not task_id:
                raise ValueError("结果封装缺少有效 task_id")
            if task_id in envelope_task_ids:
                raise ValueError("同一任务只能有一个结果封装")
            envelope_task_ids.add(task_id)
        completed: list[str] = []
        missing: list[str] = []
        warnings: list[str] = []
        failures: list[str] = []
        conflicts: list[str] = []
        deliverables: list[OperationDeliverable] = []
        quality_reports: list[OperationQualityReport] = []
        evidence_packs: list[EvidencePack] = []
        deliverable_ids: set[str] = set()
        evidence_ids: set[str] = set()
        has_optional_failure = False
        has_required_failure = False
        has_waiting_input = False
        has_cancelled = False
        successful_tasks = 0

        for task_id in graph.topological_order:
            node = nodes[task_id]
            outcome = by_id.get(task_id)
            if outcome is None:
                _append_unique(missing, task_id)
                _append_unique(failures, f"{task_id}:MISSING_OUTCOME")
                if node.required:
                    has_required_failure = True
                else:
                    has_optional_failure = True
                continue
            if outcome.status is TaskExecutionStatus.CANCELLED:
                has_cancelled = True
                for scope in outcome.missing_scope or (task_id,):
                    _append_unique(missing, scope)
                _append_unique(failures, f"{task_id}:CANCELLED")
                continue
            if outcome.status is TaskExecutionStatus.WAITING_INPUT:
                has_waiting_input = True
                for scope in outcome.missing_scope or (task_id,):
                    _append_unique(missing, scope)
                _append_unique(warnings, f"{task_id}:WAITING_INPUT")
                continue
            dependency_blocked = any(
                by_id.get(dep) is None
                or by_id[dep].status is not TaskExecutionStatus.SUCCEEDED
                for dep in node.depends_on
            )
            if (
                outcome.status is TaskExecutionStatus.SUCCEEDED
                and not dependency_blocked
            ):
                successful_tasks += 1
                for scope in outcome.completed_scope or (task_id,):
                    _append_unique(completed, scope)
            elif outcome.status is TaskExecutionStatus.SUCCEEDED and dependency_blocked:
                _append_unique(missing, task_id)
                for scope in outcome.missing_scope or (task_id,):
                    _append_unique(missing, scope)
                _append_unique(failures, f"{task_id}:DEPENDENCY_NOT_SATISFIED")
                if node.required:
                    has_required_failure = True
                else:
                    has_optional_failure = True
            else:
                for scope in outcome.missing_scope or (task_id,):
                    _append_unique(missing, scope)
                code = outcome.error_code or outcome.status.value.upper()
                _append_unique(failures, f"{task_id}:{code}")
                if node.required:
                    has_required_failure = True
                else:
                    has_optional_failure = True
            if (
                outcome.status is not TaskExecutionStatus.SUCCEEDED
                or dependency_blocked
            ):
                continue
            envelope = _envelope_for(envelopes, task_id)
            if envelope is None:
                continue
            self._collect_envelope(
                envelope,
                deliverables,
                deliverable_ids,
                evidence_packs,
                evidence_ids,
                quality_reports,
                conflicts,
                warnings,
            )

        all_succeeded = successful_tasks == len(graph.tasks)
        if has_cancelled:
            status = CompletionStatus.CANCELLED
        elif has_waiting_input:
            status = CompletionStatus.WAITING_INPUT
        elif has_required_failure:
            status = CompletionStatus.FAILED
        elif has_optional_failure or not all_succeeded:
            status = CompletionStatus.PARTIAL
        else:
            status = CompletionStatus.COMPLETE
        return AggregationResult(
            completion_status=status,
            deliverables=tuple(deliverables),
            evidence_pack=self._merge_evidence(evidence_packs, graph, conflicts),
            completed_scope=tuple(completed),
            missing_scope=tuple(missing),
            warnings=tuple(warnings),
            failures=tuple(failures),
            conflicts=tuple(conflicts),
            quality_reports=tuple(quality_reports),
        )

    @staticmethod
    def _collect_envelope(
        envelope: object,
        deliverables: list[OperationDeliverable],
        deliverable_ids: set[str],
        evidence_packs: list[EvidencePack],
        evidence_ids: set[str],
        quality_reports: list[OperationQualityReport],
        conflicts: list[str],
        warnings: list[str],
    ) -> None:
        """从已解码的结果封装收集 S3 权威对象。"""
        bundle = getattr(envelope, "deliverable_bundle", None)
        if bundle is not None:
            if not isinstance(bundle, DeliverableBundle):
                raise TypeError("deliverable_bundle 必须是 DeliverableBundle")
            for item in bundle.deliverables:
                if item.deliverable_id in deliverable_ids:
                    _append_unique(conflicts, f"deliverable:{item.deliverable_id}")
                deliverable_ids.add(item.deliverable_id)
                deliverables.append(item)
        pack = getattr(envelope, "evidence_pack", None)
        if pack is not None:
            if not isinstance(pack, EvidencePack):
                raise TypeError("evidence_pack 必须是 EvidencePack")
            for record in pack.records:
                if record.evidence_id in evidence_ids:
                    _append_unique(conflicts, f"evidence:{record.evidence_id}")
                evidence_ids.add(record.evidence_id)
            evidence_packs.append(pack)
        report = getattr(envelope, "quality_report", None)
        if report is not None:
            if not isinstance(report, OperationQualityReport):
                raise TypeError("quality_report 必须是 OperationQualityReport")
            quality_reports.append(report)
        for warning in getattr(envelope, "warnings", ()):
            if isinstance(warning, str):
                _append_unique(warnings, warning)

    @staticmethod
    def _merge_evidence(
        packs: list[EvidencePack],
        graph: TaskGraph,
        conflicts: list[str],
    ) -> EvidencePack | None:
        """保留所有证据记录和关联，不静默覆盖重复 ID。"""
        if not packs:
            return None
        records: list[EvidenceRecord] = []
        supports: list[ConclusionSupport] = []
        for pack in packs:
            records.extend(pack.records)
            supports.extend(pack.supports)
        if len(packs) == 1:
            pack_id = packs[0].pack_id
        else:
            pack_id = f"{graph.plan_id}.evidence"
            if len({pack.task_id for pack in packs}) > 1:
                _append_unique(conflicts, "evidence:task_id")
        return EvidencePack(
            contract_version="evidence-pack/1",
            pack_id=pack_id,
            task_id=packs[0].task_id,
            records=tuple(records),
            supports=tuple(supports),
        )


__all__ = ["AggregationResult", "ResultAggregator", "RevisionDecision"]
