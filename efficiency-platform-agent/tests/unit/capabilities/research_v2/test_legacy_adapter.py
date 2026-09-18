"""R10 V1 结果只能成为未核验候选。"""

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchResult,
    ResearchStatus,
)
from efficiency_platform_agent.capabilities.research.v2.legacy_adapter import (
    LegacyResearchAdapter,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot


def test_v1_valid_observation_is_not_promoted_to_verified_content() -> None:
    observation = ResearchObservation(
        observation_id="obs-1",
        title="News",
        publisher="Publisher",
        source_url="https://example.com/news",
        published_at_epoch_ms=1_789_430_400_000,
        retrieved_at_epoch_ms=1_789_430_500_000,
        source_scope=SourceScope.EXTERNAL_REFERENCE,
        supported_conclusion_ids=frozenset({"c1"}),
        within_time_window=True,
        duplicate_status=EvidenceDuplicateStatus.UNIQUE,
        quality_status=EvidenceQualityStatus.VALID,
    )
    result = ResearchResult(
        contract_version="research-result/1",
        request_id="request-1",
        task_id="task-1",
        tenant_id="tenant-1",
        status=ResearchStatus.SUCCEEDED,
        observations=(observation,),
        warnings=(),
        error_code=None,
        usage=UsageSnapshot(),
    )
    batch = LegacyResearchAdapter().to_candidates(result)
    candidate = batch.candidates[0]
    assert batch.content_verified is False
    assert batch.coverage == "unknown"
    assert candidate.content_scope == "none"
    assert candidate.inline_content is None
    assert "content_unverified" in candidate.labels
