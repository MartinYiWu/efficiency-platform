"""Research Agent Tool Loop 与证据闭包契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResearchRequestV2(_FrozenContract):
    contract_version: Literal["research-request/2"] = "research-request/2"
    request_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    topic: str = Field(min_length=1, max_length=2_000)
    date_range: str = Field(min_length=1, max_length=256)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    language: str = Field(min_length=1, max_length=32)
    max_results: int = Field(ge=1, le=100)

    @field_validator("source_ids")
    @classmethod
    def validate_source_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(not item.strip() for item in value):
            raise ValueError("RESEARCH_SOURCE_ID_INVALID")
        return value


class EvidenceSourceV1(_FrozenContract):
    source_id: str = Field(min_length=1, max_length=128)
    tool_call_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=4_096)
    title: str = Field(min_length=1, max_length=2_000)
    published_at: datetime | None = None
    excerpt: str | None = Field(default=None, max_length=4_000)

    @field_validator("url")
    @classmethod
    def validate_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("EVIDENCE_SOURCE_URL_INVALID")
        return value


class EvidenceClaimV1(_FrozenContract):
    claim_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=64)


class EvidenceHotspotV1(_FrozenContract):
    hotspot_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=2_000)
    summary: str = Field(min_length=1, max_length=8_000)
    claim_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    published_at: datetime | None = None
    heat: float | None = Field(default=None, ge=0)


class EvidencePackV1(_FrozenContract):
    contract_version: Literal["evidence-pack/1"] = "evidence-pack/1"
    topic: str = Field(min_length=1, max_length=2_000)
    sources: tuple[EvidenceSourceV1, ...] = Field(min_length=1, max_length=1_000)
    claims: tuple[EvidenceClaimV1, ...] = Field(min_length=1, max_length=5_000)
    hotspots: tuple[EvidenceHotspotV1, ...] = Field(min_length=1, max_length=1_000)
    gaps: tuple[str, ...] = Field(default=(), max_length=128)
    partial: bool = False

    @model_validator(mode="after")
    def validate_reference_closure(self) -> EvidencePackV1:
        source_ids = [item.source_id for item in self.sources]
        claim_ids = [item.claim_id for item in self.claims]
        hotspot_ids = [item.hotspot_id for item in self.hotspots]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("EVIDENCE_SOURCE_DUPLICATE")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("EVIDENCE_CLAIM_DUPLICATE")
        if len(hotspot_ids) != len(set(hotspot_ids)):
            raise ValueError("EVIDENCE_HOTSPOT_DUPLICATE")
        known_sources = set(source_ids)
        known_claims = set(claim_ids)
        claim_sources = {item.claim_id: set(item.source_ids) for item in self.claims}
        if any(not sources <= known_sources for sources in claim_sources.values()):
            raise ValueError("EVIDENCE_CLAIM_SOURCE_OPEN")
        for hotspot in self.hotspots:
            if not set(hotspot.claim_ids) <= known_claims:
                raise ValueError("EVIDENCE_HOTSPOT_CLAIM_OPEN")
            if not set(hotspot.source_ids) <= known_sources:
                raise ValueError("EVIDENCE_HOTSPOT_SOURCE_OPEN")
            required_sources = set().union(
                *(claim_sources[item] for item in hotspot.claim_ids)
            )
            if not required_sources <= set(hotspot.source_ids):
                raise ValueError("EVIDENCE_HOTSPOT_SOURCE_INCOMPLETE")
        if self.partial and not self.gaps:
            raise ValueError("EVIDENCE_PARTIAL_GAP_REQUIRED")
        return self


class ResearchReflectionV1(_FrozenContract):
    complete: bool
    problems: tuple[str, ...] = Field(default=(), max_length=64)
    repair_instructions: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def validate_decision(self) -> ResearchReflectionV1:
        if self.complete and self.problems:
            raise ValueError("RESEARCH_REFLECTION_CONTRADICTORY")
        if not self.complete and (not self.problems or not self.repair_instructions):
            raise ValueError("RESEARCH_REFLECTION_REPAIR_REQUIRED")
        return self


__all__ = [
    "EvidenceClaimV1",
    "EvidenceHotspotV1",
    "EvidencePackV1",
    "EvidenceSourceV1",
    "ResearchReflectionV1",
    "ResearchRequestV2",
]
