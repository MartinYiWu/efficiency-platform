"""质量审校后的有限修订决策。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    OperationQualityReport,
    QualityStatus,
)


class RevisionAction(StrEnum):
    """修订门禁允许的稳定动作。"""

    ACCEPT = "accept"
    REVISE = "revise"
    PARTIAL = "partial"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class RevisionRequest:
    """只描述修订范围，不携带新事实或证据正文。"""

    request_id: str
    report_id: str
    target_deliverable_ids: tuple[str, ...]
    issue_reference_ids: tuple[str, ...]
    immutable_evidence_ids: frozenset[str]
    immutable_fact_ids: frozenset[str]
    next_revision: int


@dataclass(frozen=True, slots=True)
class RevisionDecision:
    """有限修订决策及可选请求。"""

    action: RevisionAction
    request: RevisionRequest | None
    error_code: str | None


def decide_revision(
    report: OperationQualityReport,
    *,
    current_revision: int,
    max_revisions: int,
    revision_budget_available: bool,
) -> RevisionDecision:
    """根据质量报告和 S4 预算返回一次性修订决策。"""

    if not isinstance(report, OperationQualityReport):
        raise TypeError("report必须是OperationQualityReport")
    if (
        not isinstance(current_revision, int)
        or isinstance(current_revision, bool)
        or current_revision < 0
    ):
        raise ValueError("REVISION_INVALID:current_revision")
    if max_revisions < 0 or max_revisions > 2:
        raise ValueError("REVISION_INVALID:max_revisions")
    if current_revision > max_revisions:
        raise ValueError("REVISION_INVALID:current_revision")
    if report.final_status is QualityStatus.PASSED:
        return RevisionDecision(RevisionAction.ACCEPT, None, None)
    if current_revision >= max_revisions:
        return RevisionDecision(RevisionAction.FAIL, None, "QUALITY_NOT_MET")
    if not revision_budget_available:
        action = (
            RevisionAction.PARTIAL if report.deliverable_ids else RevisionAction.FAIL
        )
        return RevisionDecision(action, None, "REVISION_BUDGET_EXHAUSTED")

    issue_ids = tuple(
        dict.fromkeys(
            issue_id
            for check in report.checks
            for issue_id in check.issue_reference_ids
        )
    )
    request = RevisionRequest(
        request_id=f"{report.report_id}-revision-{current_revision + 1}",
        report_id=report.report_id,
        target_deliverable_ids=report.deliverable_ids,
        issue_reference_ids=issue_ids,
        immutable_evidence_ids=frozenset(),
        immutable_fact_ids=frozenset(),
        next_revision=current_revision + 1,
    )
    return RevisionDecision(RevisionAction.REVISE, request, None)


__all__ = [
    "RevisionAction",
    "RevisionDecision",
    "RevisionRequest",
    "decide_revision",
]
