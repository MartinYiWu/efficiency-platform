"""研究 Provider 的唯一、框架中立契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
    TimeWindow,
    normalize_evidence_url,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.core.runtime import UsageSnapshot

_EMPTY_USAGE = UsageSnapshot()


class ResearchStatus(StrEnum):
    """研究请求的稳定结果状态。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ResearchRequest:
    """带租户、时间窗和结论约束的研究请求。"""

    contract_version: Literal["research-request/1"]
    request_id: str
    task_id: str
    tenant_id: str
    goal: str
    time_window: TimeWindow | None
    max_sources: int
    expected_conclusion_ids: tuple[str, ...]
    result_schema_version: Literal["research-result/1"]
    max_output_tokens: int = 2_000

    def __post_init__(self) -> None:
        if self.contract_version != "research-request/1":
            raise ValueError("RESEARCH_REQUEST_INVALID:contract_version")
        for name, value in (
            ("request_id", self.request_id),
            ("task_id", self.task_id),
            ("tenant_id", self.tenant_id),
            ("goal", self.goal),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"RESEARCH_REQUEST_INVALID:{name}")
        if self.result_schema_version != "research-result/1":
            raise ValueError("RESEARCH_REQUEST_INVALID:result_schema_version")
        if (
            not isinstance(self.max_sources, int)
            or isinstance(self.max_sources, bool)
            or self.max_sources < 1
        ):
            raise ValueError("RESEARCH_REQUEST_INVALID:max_sources")
        if not isinstance(self.expected_conclusion_ids, tuple):
            raise TypeError("RESEARCH_REQUEST_INVALID:expected_conclusion_ids")
        if len(set(self.expected_conclusion_ids)) != len(self.expected_conclusion_ids):
            raise ValueError("RESEARCH_REQUEST_INVALID:expected_conclusion_ids")
        if not isinstance(self.max_output_tokens, int) or self.max_output_tokens < 1:
            raise ValueError("RESEARCH_REQUEST_INVALID:max_output_tokens")


@dataclass(frozen=True, slots=True)
class ResearchObservation:
    """研究来源的声明性观察，不包含网页正文。"""

    observation_id: str
    title: str
    publisher: str
    source_url: str
    published_at_epoch_ms: int | None
    retrieved_at_epoch_ms: int
    source_scope: SourceScope
    supported_conclusion_ids: frozenset[str]
    within_time_window: bool
    duplicate_status: EvidenceDuplicateStatus
    quality_status: EvidenceQualityStatus

    def __post_init__(self) -> None:
        for name, value in (
            ("observation_id", self.observation_id),
            ("title", self.title),
            ("publisher", self.publisher),
            ("source_url", self.source_url),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"RESEARCH_OBSERVATION_INVALID:{name}")
        try:
            normalize_evidence_url(self.source_url)
        except (TypeError, ValueError) as error:
            raise ValueError("RESEARCH_OBSERVATION_INVALID:source_url") from error
        if (
            not isinstance(self.supported_conclusion_ids, frozenset)
            or not self.supported_conclusion_ids
        ):
            raise ValueError("RESEARCH_OBSERVATION_INVALID:supported_conclusion_ids")
        if not isinstance(self.source_scope, SourceScope):
            raise TypeError("RESEARCH_OBSERVATION_INVALID:source_scope")
        if not isinstance(self.duplicate_status, EvidenceDuplicateStatus):
            raise TypeError("RESEARCH_OBSERVATION_INVALID:duplicate_status")
        if not isinstance(self.quality_status, EvidenceQualityStatus):
            raise TypeError("RESEARCH_OBSERVATION_INVALID:quality_status")
        for field_name, field_value in (
            ("published_at_epoch_ms", self.published_at_epoch_ms),
            ("retrieved_at_epoch_ms", self.retrieved_at_epoch_ms),
        ):
            if field_value is not None and (
                not isinstance(field_value, int)
                or isinstance(field_value, bool)
                or field_value < 0
            ):
                raise ValueError(f"RESEARCH_OBSERVATION_INVALID:{field_name}")
        if not isinstance(self.within_time_window, bool):
            raise TypeError("RESEARCH_OBSERVATION_INVALID:within_time_window")


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """研究 Provider 的结构化结果，禁止暴露原始 SDK 响应。"""

    contract_version: Literal["research-result/1"]
    request_id: str
    task_id: str
    tenant_id: str
    status: ResearchStatus
    observations: tuple[ResearchObservation, ...]
    warnings: tuple[str, ...]
    error_code: str | None
    usage: UsageSnapshot = _EMPTY_USAGE

    def __post_init__(self) -> None:
        if self.contract_version != "research-result/1":
            raise ValueError("RESEARCH_RESULT_INVALID:contract_version")
        for name, value in (
            ("request_id", self.request_id),
            ("task_id", self.task_id),
            ("tenant_id", self.tenant_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"RESEARCH_RESULT_INVALID:{name}")
        if not isinstance(self.status, ResearchStatus):
            raise TypeError("RESEARCH_RESULT_INVALID:status")
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, ResearchObservation) for item in self.observations
        ):
            raise TypeError("RESEARCH_RESULT_INVALID:observations")
        if not isinstance(self.warnings, tuple) or any(
            not isinstance(item, str) for item in self.warnings
        ):
            raise TypeError("RESEARCH_RESULT_INVALID:warnings")
        if self.status is ResearchStatus.SUCCEEDED:
            if not self.observations or self.error_code is not None:
                raise ValueError("RESEARCH_RESULT_INVALID:success")
        elif self.error_code not in {
            "RESEARCH_UNAVAILABLE",
            "RESEARCH_INSUFFICIENT",
            "EVIDENCE_INVALID",
        }:
            raise ValueError("RESEARCH_RESULT_INVALID:error_code")
        if self.status is ResearchStatus.FAILED and self.observations:
            raise ValueError("RESEARCH_RESULT_INVALID:failed_observations")


@runtime_checkable
class ResearchProviderPort(Protocol):
    """研究 Provider 的窄异步端口。"""

    async def research(self, request: ResearchRequest) -> ResearchResult:
        """根据一个版本化请求返回结构化研究结果。"""

        raise NotImplementedError("研究 Provider 端口只定义签名")


__all__ = [
    "ResearchObservation",
    "ResearchProviderPort",
    "ResearchRequest",
    "ResearchResult",
    "ResearchStatus",
]
