"""研究证据的确定性门禁，不访问来源 URL。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidencePack,
    validate_evidence_pack,
)


@dataclass(frozen=True, slots=True)
class EvidenceGatePolicy:
    """Evidence Gate 的最小来源、发布者和时间窗策略。"""

    policy_id: str
    minimum_valid_source_count: int
    minimum_distinct_publisher_count: int
    require_all_factual_conclusions_supported: bool
    require_within_time_window: bool

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("EVIDENCE_POLICY_INVALID:policy_id")
        if (
            self.minimum_valid_source_count < 0
            or self.minimum_distinct_publisher_count < 0
        ):
            raise ValueError("EVIDENCE_POLICY_INVALID:minimum_count")


@dataclass(frozen=True, slots=True)
class EvidenceGateDecision:
    """证据门禁结果；原文核验始终为 False。"""

    accepted: bool
    valid_evidence_ids: tuple[str, ...]
    rejected_evidence_ids: tuple[str, ...]
    unsupported_conclusion_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    source_content_verified: Literal[False] = False


class EvidenceGate:
    """先执行 S3 结构校验，再执行来源和结论关联门禁。"""

    def evaluate(
        self,
        pack: EvidencePack,
        factual_conclusion_ids: frozenset[str],
        policy: EvidenceGatePolicy,
    ) -> EvidenceGateDecision:
        """返回稳定原因码，不打开 URL，也不补写事实。"""

        if not isinstance(factual_conclusion_ids, frozenset):
            raise TypeError("factual_conclusion_ids必须是frozenset")
        try:
            validate_evidence_pack(pack)
        except (TypeError, ValueError):
            return EvidenceGateDecision(
                False,
                (),
                tuple(record.evidence_id for record in getattr(pack, "records", ())),
                tuple(sorted(factual_conclusion_ids)),
                ("EVIDENCE_INVALID",),
            )

        records = pack.records
        valid = tuple(
            record
            for record in records
            if record.quality_status.value in {"valid", "unverified"}
            and (not policy.require_within_time_window or record.within_time_window)
        )
        valid_ids = tuple(record.evidence_id for record in valid)
        rejected_ids = tuple(
            record.evidence_id
            for record in records
            if record.evidence_id not in valid_ids
        )
        publishers = {record.publisher for record in valid}
        supported = {
            conclusion_id
            for record in valid
            for conclusion_id in record.supported_conclusion_ids
        }
        unsupported = tuple(sorted(factual_conclusion_ids - supported))
        reasons: list[str] = []
        if len(valid) < policy.minimum_valid_source_count:
            reasons.append("RESEARCH_INSUFFICIENT")
        if len(publishers) < policy.minimum_distinct_publisher_count:
            reasons.append("RESEARCH_INSUFFICIENT")
        if policy.require_all_factual_conclusions_supported and unsupported:
            reasons.append("EVIDENCE_INVALID")
        unique_reasons = tuple(dict.fromkeys(reasons))
        return EvidenceGateDecision(
            not unique_reasons,
            valid_ids,
            rejected_ids,
            unsupported,
            unique_reasons,
        )


__all__ = ["EvidenceGate", "EvidenceGateDecision", "EvidenceGatePolicy"]
