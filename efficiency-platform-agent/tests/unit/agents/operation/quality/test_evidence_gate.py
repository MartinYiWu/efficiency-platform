"""Evidence Gate 的确定性离线校验测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    ConclusionSupport,
    EvidenceDuplicateStatus,
    EvidencePack,
    EvidenceQualityStatus,
    EvidenceRecord,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.agents.operation.quality.evidence_gate import (
    EvidenceGate,
    EvidenceGatePolicy,
)


def _record(
    evidence_id: str,
    url: str,
    claims: frozenset[str],
    duplicate: EvidenceDuplicateStatus = EvidenceDuplicateStatus.UNIQUE,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id,
        f"标题-{evidence_id}",
        f"发布者-{evidence_id}",
        url,
        1780000000000,
        1780003600000,
        SourceScope.EXTERNAL_REFERENCE,
        claims,
        True,
        duplicate,
        EvidenceQualityStatus.VALID,
    )


class EvidenceGateTests(unittest.TestCase):
    """验证重复来源与未支撑结论的失败关闭。"""

    def _policy(self) -> EvidenceGatePolicy:
        return EvidenceGatePolicy("strict-v1", 2, 2, True, True)

    def test_rejects_duplicate_and_unsupported_claims(self) -> None:
        pack = EvidencePack(
            "evidence-pack/1",
            "pack-a",
            "task-a",
            (
                _record("evidence-1", "https://example.com/a", frozenset({"claim-1"})),
                _record("evidence-2", "https://example.com/a", frozenset({"claim-1"})),
            ),
            (ConclusionSupport("claim-1", frozenset({"evidence-1", "evidence-2"})),),
        )
        decision = EvidenceGate().evaluate(
            pack, frozenset({"claim-1", "claim-2"}), self._policy()
        )
        self.assertFalse(decision.accepted)
        self.assertIn("EVIDENCE_INVALID", decision.reason_codes)
        self.assertFalse(decision.source_content_verified)

    def test_accepts_two_distinct_publishers_and_linked_claims(self) -> None:
        first = _record("evidence-1", "https://example.com/a", frozenset({"claim-1"}))
        second = _record("evidence-2", "https://example.com/b", frozenset({"claim-2"}))
        pack = EvidencePack(
            "evidence-pack/1",
            "pack-a",
            "task-a",
            (first, second),
            (
                ConclusionSupport("claim-1", frozenset({"evidence-1"})),
                ConclusionSupport("claim-2", frozenset({"evidence-2"})),
            ),
        )
        decision = EvidenceGate().evaluate(
            pack, frozenset({"claim-1", "claim-2"}), self._policy()
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(
            tuple(decision.valid_evidence_ids), ("evidence-1", "evidence-2")
        )


if __name__ == "__main__":
    unittest.main()
