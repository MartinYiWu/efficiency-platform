"""有证据的案例候选校验；点赞不构成测量结果或共享许可。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.core.memory import (
    ConversationScope,
    SourceDependency,
    require_dependencies,
)

Text = Annotated[str, Field(min_length=1, max_length=2048, pattern=r"\S")]


class EpisodeContent(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )
    category: Literal["USER_PREFERENCE", "MEASURED_RESULT", "TECHNICAL_EXPERIENCE"]
    scenario: Text = Field(repr=False)
    preconditions: tuple[Text, ...] = Field(max_length=16, repr=False)
    actions: tuple[Text, ...] = Field(min_length=1, max_length=16, repr=False)
    observed_results: Text = Field(repr=False)
    denominator: int | None = Field(default=None, gt=0)
    observed_from: datetime | None = None
    observed_until: datetime | None = None
    evidence_refs: tuple[Annotated[str, Field(min_length=1, max_length=128)], ...] = (
        Field(min_length=1, max_length=128)
    )
    applicable_version: Annotated[str, Field(min_length=1, max_length=128)]
    disallowed_conditions: tuple[Text, ...] = Field(max_length=16, repr=False)

    @model_validator(mode="after")
    def measured_evidence(self) -> Self:
        if self.category == "MEASURED_RESULT" and (
            self.denominator is None
            or self.observed_from is None
            or self.observed_until is None
        ):
            raise ValueError("MEMORY_EPISODE_MEASUREMENT_REQUIRED")
        if (self.observed_from is None) != (self.observed_until is None):
            raise ValueError("MEMORY_EPISODE_TIME_INVALID")
        if (
            self.observed_from is not None
            and self.observed_until is not None
            and (
                self.observed_from.tzinfo is None
                or self.observed_until.tzinfo is None
                or self.observed_until < self.observed_from
            )
        ):
            raise ValueError("MEMORY_EPISODE_TIME_INVALID")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("MEMORY_EPISODE_EVIDENCE_DUPLICATE")
        return self


@dataclass(frozen=True, slots=True)
class EpisodeEvidence:
    """原Java当前源码快照；technical_only/测量ref均不取模型输出。"""

    scope: ConversationScope
    dependencies: tuple[SourceDependency, ...]
    authorized_evidence_refs: frozenset[str]
    measured_evidence_refs: frozenset[str]
    technical_only: bool = False


@dataclass(frozen=True, slots=True)
class EpisodeCandidate:
    content: EpisodeContent = field(repr=False)
    source_dependencies: tuple[SourceDependency, ...]
    status: Literal["CANDIDATE"] = field(default="CANDIDATE", init=False)
    free_text_quality: Literal["UNVERIFIED"] = field(default="UNVERIFIED", init=False)


def validate_episode(
    content: EpisodeContent, evidence: EpisodeEvidence
) -> EpisodeCandidate:
    if type(content) is not EpisodeContent or type(evidence) is not EpisodeEvidence:
        raise ValueError("MEMORY_EPISODE_EVIDENCE_REQUIRED")
    require_dependencies(evidence.dependencies)
    if not evidence.dependencies or not set(content.evidence_refs).issubset(
        evidence.authorized_evidence_refs
    ):
        raise ValueError("MEMORY_EPISODE_SOURCE_DENIED")
    if content.category == "MEASURED_RESULT" and not set(
        content.evidence_refs
    ).intersection(evidence.measured_evidence_refs):
        raise ValueError("MEMORY_EPISODE_MEASUREMENT_REQUIRED")
    if evidence.scope.domain == "hr" and (
        content.category != "TECHNICAL_EXPERIENCE"
        or evidence.technical_only is not True
    ):
        raise ValueError("MEMORY_EPISODE_HR_PROFILE_DENIED")
    return EpisodeCandidate(content, evidence.dependencies)
