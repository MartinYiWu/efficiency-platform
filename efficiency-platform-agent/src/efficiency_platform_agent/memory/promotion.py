"""案例晋升的CPU门禁；只能由Java有权人工证明推进，不修改Prompt。"""

from dataclasses import dataclass

from efficiency_platform_agent.core.memory import (
    SourceDependency,
    require_dependencies,
    require_id,
)


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    episode_id: str
    candidate_digest: str
    source_dependencies: tuple[SourceDependency, ...]
    current_dependencies: tuple[SourceDependency, ...]
    owner_confirmed: bool
    sharing_approved: bool
    deidentification_approved: bool
    regression_suite: str
    regression_version: str
    report_sha256: str
    cases: int
    passed: int
    required_cases: int
    reviewed_by: str
    source_owner_id: str


def validate_promotion(evidence: PromotionEvidence) -> None:
    if type(evidence) is not PromotionEvidence:
        raise ValueError("MEMORY_PROMOTION_EVIDENCE_REQUIRED")
    for value in (
        evidence.episode_id,
        evidence.regression_suite,
        evidence.regression_version,
        evidence.reviewed_by,
        evidence.source_owner_id,
    ):
        require_id(value)
    for digest in (evidence.candidate_digest, evidence.report_sha256):
        if len(digest) != 64 or any(
            value not in "0123456789abcdef" for value in digest
        ):
            raise ValueError("MEMORY_PROMOTION_PROOF_INVALID")
    require_dependencies(evidence.source_dependencies)
    require_dependencies(evidence.current_dependencies)
    if not evidence.source_dependencies or not set(
        evidence.source_dependencies
    ).issubset(evidence.current_dependencies):
        raise ValueError("MEMORY_PROMOTION_SOURCE_REVOKED")
    if any(
        flag is not True
        for flag in (
            evidence.owner_confirmed,
            evidence.sharing_approved,
            evidence.deidentification_approved,
        )
    ):
        raise ValueError("MEMORY_PROMOTION_APPROVAL_REQUIRED")
    if evidence.reviewed_by == evidence.source_owner_id:
        raise ValueError("MEMORY_PROMOTION_INDEPENDENT_REVIEW_REQUIRED")
    if (
        any(
            type(value) is not int
            for value in (evidence.cases, evidence.passed, evidence.required_cases)
        )
        or evidence.required_cases < 1
        or evidence.cases < evidence.required_cases
        or evidence.passed != evidence.cases
    ):
        raise ValueError("MEMORY_PROMOTION_REGRESSION_REQUIRED")
