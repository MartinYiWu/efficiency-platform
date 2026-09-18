"""默认关闭的研究来源与策略 TOML 配置。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResearchSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=128)
    adapter_id: Literal["rss_atom", "github_releases", "hacker_news", "arxiv", "gdelt"]
    enabled: bool = False
    cost_mode: Literal["free", "free_quota", "paid", "unknown"] = "unknown"
    admission_status: Literal["VERIFIED", "UNVERIFIED", "BLOCKED"] = "UNVERIFIED"
    credential_source_id: str | None = Field(default=None, min_length=1, max_length=128)


class ResearchSourceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    config_version: str = Field(min_length=1, max_length=128)
    sources: tuple[ResearchSourceConfig, ...] = Field(default=(), max_length=256)

    @field_validator("sources")
    @classmethod
    def validate_unique_sources(
        cls, value: tuple[ResearchSourceConfig, ...]
    ) -> tuple[ResearchSourceConfig, ...]:
        identifiers = [item.source_id for item in value]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("RESEARCH_SOURCE_CONFIG_DUPLICATED")
        return value

    @classmethod
    def load(cls, path: Path) -> ResearchSourceSettings:
        with path.open("rb") as stream:
            return cls.model_validate(tomllib.load(stream))


class ResearchPolicySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = Field(min_length=1, max_length=128)
    admission_ttl_days: int = Field(default=30, ge=1, le=365)
    cost_evidence_ttl_days: int = Field(default=30, ge=1, le=365)
    max_collection_rounds: int = Field(default=3, ge=1, le=20)
    max_no_gain_rounds: int = Field(default=1, ge=1, le=5)

    @classmethod
    def load(cls, path: Path) -> ResearchPolicySettings:
        with path.open("rb") as stream:
            return cls.model_validate(tomllib.load(stream))


class ResearchPipelineSettings(BaseModel):
    """X02 无敏感开关；默认保持 V1 且不声明生产就绪。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_pipeline_version: Literal["intent-v1", "intent-v2"] = "intent-v1"
    research_pipeline_version: Literal["research-v1", "research-v2"] = "research-v1"
    runtime_mode: Literal["local_live", "production"] = "production"
    research_replan_enabled: bool = False
    research_source_allowlist: tuple[str, ...] = ()
    research_policy_version: str = Field(
        default="research-policy/disabled", min_length=1, max_length=128
    )
    state_backend: Literal["memory", "postgres"] = "memory"
    rollout_mode: Literal["all", "tenant_allowlist"] = "all"
    rollout_tenant_allowlist: tuple[str, ...] = ()

    @field_validator("research_source_allowlist")
    @classmethod
    def validate_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("RESEARCH_PIPELINE_ALLOWLIST_INVALID")
        return value

    @field_validator("rollout_tenant_allowlist")
    @classmethod
    def validate_tenant_allowlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(set(value)) != len(value):
            raise ValueError("RESEARCH_ROLLOUT_TENANT_ALLOWLIST_INVALID")
        return value

    @model_validator(mode="after")
    def validate_rollout_scope(self) -> ResearchPipelineSettings:
        if (
            self.v2_enabled
            and self.rollout_mode == "tenant_allowlist"
            and not self.rollout_tenant_allowlist
        ):
            raise ValueError("RESEARCH_ROLLOUT_TENANT_ALLOWLIST_REQUIRED")
        if self.runtime_mode == "local_live":
            if not self.v2_enabled:
                raise ValueError("RESEARCH_LOCAL_LIVE_V2_REQUIRED")
            if self.state_backend != "memory":
                raise ValueError("RESEARCH_LOCAL_LIVE_MEMORY_REQUIRED")
            if not self.research_source_allowlist:
                raise ValueError("RESEARCH_LOCAL_LIVE_SOURCE_ALLOWLIST_REQUIRED")
            if (
                self.rollout_mode != "tenant_allowlist"
                or not self.rollout_tenant_allowlist
            ):
                raise ValueError("RESEARCH_LOCAL_LIVE_TENANT_ALLOWLIST_REQUIRED")
        return self

    @property
    def v2_enabled(self) -> bool:
        return (
            self.intent_pipeline_version == "intent-v2"
            and self.research_pipeline_version == "research-v2"
        )

    @property
    def production_ready(self) -> bool:
        return (
            self.runtime_mode == "production"
            and self.v2_enabled
            and self.state_backend == "postgres"
            and self.rollout_mode == "tenant_allowlist"
            and bool(self.rollout_tenant_allowlist)
        )

    @property
    def local_live_ready(self) -> bool:
        """仅说明本地实时配置充分，不代表来源实际可用。"""

        return (
            self.runtime_mode == "local_live"
            and self.v2_enabled
            and self.state_backend == "memory"
            and bool(self.research_source_allowlist)
            and self.rollout_mode == "tenant_allowlist"
            and bool(self.rollout_tenant_allowlist)
        )

    @classmethod
    def load(cls, path: Path) -> ResearchPipelineSettings:
        with path.open("rb") as stream:
            payload = tomllib.load(stream)
        return cls.model_validate(payload.get("pipeline", payload))


__all__ = [
    "ResearchPipelineSettings",
    "ResearchPolicySettings",
    "ResearchSourceConfig",
    "ResearchSourceSettings",
]
