from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidencePack,
    EvidenceQualityStatus,
    EvidenceRecord,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.agents.operation.specialists.model_backed import (
    evidence_citations,
)


def test_evidence_citation_title_contains_published_day() -> None:
    pack = EvidencePack(
        "evidence-pack/1",
        "pack-1",
        "task-1",
        (
            EvidenceRecord(
                "evidence-1",
                "官方模型发布",
                "官方博客",
                "https://official.example/release",
                1_789_520_400_000,
                1_789_610_400_000,
                SourceScope.EXTERNAL_REFERENCE,
                frozenset({"goal"}),
                True,
                EvidenceDuplicateStatus.UNIQUE,
                EvidenceQualityStatus.VALID,
            ),
        ),
        (),
    )

    citations = evidence_citations(pack)

    assert citations[0]["title"] == "官方模型发布（发布日期：2026-09-16）"
