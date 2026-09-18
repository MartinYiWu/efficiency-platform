"""将 V1 搜索结果降级为未核验 V2 候选，绝不升级内容可信度。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.capabilities.research.contracts import ResearchResult
from efficiency_platform_agent.contracts.research_sources_v2 import CandidateRecordV2


class LegacyCandidateBatchV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=128)
    candidates: tuple[CandidateRecordV2, ...] = Field(default=(), max_length=500)
    content_verified: bool = False
    coverage: str = "unknown"


class LegacyResearchAdapter:
    def to_candidates(self, result: ResearchResult) -> LegacyCandidateBatchV2:
        candidates: list[CandidateRecordV2] = []
        for observation in result.observations:
            digest = hashlib.sha256(
                (result.request_id + "\x00" + observation.observation_id).encode()
            ).hexdigest()[:32]
            raw_published = (
                datetime.fromtimestamp(
                    observation.published_at_epoch_ms / 1000, tz=UTC
                ).isoformat()
                if observation.published_at_epoch_ms is not None
                else None
            )
            candidates.append(
                CandidateRecordV2(
                    candidate_id=f"candidate-v1-{digest}",
                    source_id="legacy.v1",
                    source_item_id=observation.observation_id,
                    url=observation.source_url,
                    title=observation.title,
                    raw_published_at=raw_published,
                    timestamp_semantics=(
                        "published" if raw_published is not None else "unknown"
                    ),
                    discovered_via="api",
                    content_scope="none",
                    labels=("legacy_candidate", "content_unverified"),
                )
            )
        return LegacyCandidateBatchV2(
            request_id=result.request_id,
            candidates=tuple(candidates),
            content_verified=False,
            coverage="unknown",
        )


__all__ = ["LegacyCandidateBatchV2", "LegacyResearchAdapter"]
