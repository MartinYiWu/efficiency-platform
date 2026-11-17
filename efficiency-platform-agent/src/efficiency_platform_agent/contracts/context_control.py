from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from efficiency_platform_agent.core import context_control as core

from .memory import ExecutionScopeModel, SourceDependencyModel


class _Boundary(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class ModelCapacityModel(_Boundary):
    provider: str
    model: str
    model_version: str
    context_window_tokens: int
    max_input_tokens: int | None
    max_output_tokens: int
    tokenizer_ref: str
    serialization_ref: str
    reasoning_rule: str
    verified: bool
    evidence_ref: str

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.ModelCapacity:
        return core.ModelCapacity(
            provider=self.provider,
            model=self.model,
            model_version=self.model_version,
            context_window_tokens=self.context_window_tokens,
            max_input_tokens=self.max_input_tokens,
            max_output_tokens=self.max_output_tokens,
            tokenizer_ref=self.tokenizer_ref,
            serialization_ref=self.serialization_ref,
            reasoning_rule=self.reasoning_rule,
            verified=self.verified,
            evidence_ref=self.evidence_ref,
        )

    @classmethod
    def from_core(cls, value: core.ModelCapacity) -> Self:
        return cls(
            provider=value.provider,
            model=value.model,
            model_version=value.model_version,
            context_window_tokens=value.context_window_tokens,
            max_input_tokens=value.max_input_tokens,
            max_output_tokens=value.max_output_tokens,
            tokenizer_ref=value.tokenizer_ref,
            serialization_ref=value.serialization_ref,
            reasoning_rule=value.reasoning_rule,
            verified=value.verified,
            evidence_ref=value.evidence_ref,
        )


class WindowLimitsModel(_Boundary):
    context_window_tokens: int
    independent_input_limit: int | None
    output_reserve_tokens: int
    safety_margin_tokens: int
    node_input_limit: int

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.WindowLimits:
        return core.WindowLimits(
            context_window_tokens=self.context_window_tokens,
            independent_input_limit=self.independent_input_limit,
            output_reserve_tokens=self.output_reserve_tokens,
            safety_margin_tokens=self.safety_margin_tokens,
            node_input_limit=self.node_input_limit,
        )

    @classmethod
    def from_core(cls, value: core.WindowLimits) -> Self:
        return cls(
            context_window_tokens=value.context_window_tokens,
            independent_input_limit=value.independent_input_limit,
            output_reserve_tokens=value.output_reserve_tokens,
            safety_margin_tokens=value.safety_margin_tokens,
            node_input_limit=value.node_input_limit,
        )


class TokenMeasurementModel(_Boundary):
    total_upper_bound: int
    by_component: tuple[tuple[str, int], ...]
    method: str
    verified: bool

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.TokenMeasurement:
        return core.TokenMeasurement(
            total_upper_bound=self.total_upper_bound,
            by_component=self.by_component,
            method=self.method,
            verified=self.verified,
        )

    @classmethod
    def from_core(cls, value: core.TokenMeasurement) -> Self:
        return cls(
            total_upper_bound=value.total_upper_bound,
            by_component=value.by_component,
            method=value.method,
            verified=value.verified,
        )


class WindowDecisionModel(_Boundary):
    H_ctx: int
    T: int
    F: int
    status: str

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.WindowDecision:
        return core.WindowDecision(
            H_ctx=self.H_ctx,
            T=self.T,
            F=self.F,
            status=self.status,
        )

    @classmethod
    def from_core(cls, value: core.WindowDecision) -> Self:
        return cls(
            H_ctx=value.H_ctx,
            T=value.T,
            F=value.F,
            status=value.status,
        )


class ContextManifestModel(_Boundary):
    manifest_id: str
    scope: ExecutionScopeModel
    operation_id: str
    node_id: str
    attempt: int
    model_version: str
    prompt_version: str
    tool_version: str
    output_schema_version: str
    tokenizer_ref: str
    serialization_ref: str
    policy_version: str
    packet_id: str | None
    packet_revision: int | None
    ctx_revision: int
    safety_dependencies: tuple[SourceDependencyModel, ...]
    selected_sources: tuple[SourceDependencyModel, ...]
    exclusions: tuple[tuple[str, str], ...]
    measurement: TokenMeasurementModel
    decision: WindowDecisionModel
    output_reserve_tokens: int
    safety_margin_tokens: int
    canonical_request_hmac: str
    predicted_generation_tokens: int = 0
    prediction_basis: str = "output-reserve"
    cpu_before_tokens: int = 0
    cpu_after_tokens: int = 0
    summary_before_tokens: int = 0
    summary_after_tokens: int = 0
    critical_fields_digest: str = "not-applied"
    summary_cas_status: str = "not-applied"
    summary_adoption_status: str = "not-applied"
    reservation_ref: str | None = None
    usage_ref: str | None = None

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        self.to_core()
        return self

    def to_core(self) -> core.ContextManifest:
        return core.ContextManifest(
            manifest_id=self.manifest_id,
            scope=self.scope.to_core(),
            operation_id=self.operation_id,
            node_id=self.node_id,
            attempt=self.attempt,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            tool_version=self.tool_version,
            output_schema_version=self.output_schema_version,
            tokenizer_ref=self.tokenizer_ref,
            serialization_ref=self.serialization_ref,
            policy_version=self.policy_version,
            packet_id=self.packet_id,
            packet_revision=self.packet_revision,
            ctx_revision=self.ctx_revision,
            safety_dependencies=tuple(
                item.to_core() for item in self.safety_dependencies
            ),
            selected_sources=tuple(item.to_core() for item in self.selected_sources),
            exclusions=self.exclusions,
            measurement=self.measurement.to_core(),
            decision=self.decision.to_core(),
            output_reserve_tokens=self.output_reserve_tokens,
            safety_margin_tokens=self.safety_margin_tokens,
            canonical_request_hmac=self.canonical_request_hmac,
            predicted_generation_tokens=self.predicted_generation_tokens,
            prediction_basis=self.prediction_basis,
            cpu_before_tokens=self.cpu_before_tokens,
            cpu_after_tokens=self.cpu_after_tokens,
            summary_before_tokens=self.summary_before_tokens,
            summary_after_tokens=self.summary_after_tokens,
            critical_fields_digest=self.critical_fields_digest,
            summary_cas_status=self.summary_cas_status,
            summary_adoption_status=self.summary_adoption_status,
            reservation_ref=self.reservation_ref,
            usage_ref=self.usage_ref,
        )

    @classmethod
    def from_core(cls, value: core.ContextManifest) -> Self:
        return cls(
            manifest_id=value.manifest_id,
            scope=ExecutionScopeModel.from_core(value.scope),
            operation_id=value.operation_id,
            node_id=value.node_id,
            attempt=value.attempt,
            model_version=value.model_version,
            prompt_version=value.prompt_version,
            tool_version=value.tool_version,
            output_schema_version=value.output_schema_version,
            tokenizer_ref=value.tokenizer_ref,
            serialization_ref=value.serialization_ref,
            policy_version=value.policy_version,
            packet_id=value.packet_id,
            packet_revision=value.packet_revision,
            ctx_revision=value.ctx_revision,
            safety_dependencies=tuple(
                SourceDependencyModel.from_core(item)
                for item in value.safety_dependencies
            ),
            selected_sources=tuple(
                SourceDependencyModel.from_core(item) for item in value.selected_sources
            ),
            exclusions=value.exclusions,
            measurement=TokenMeasurementModel.from_core(value.measurement),
            decision=WindowDecisionModel.from_core(value.decision),
            output_reserve_tokens=value.output_reserve_tokens,
            safety_margin_tokens=value.safety_margin_tokens,
            canonical_request_hmac=value.canonical_request_hmac,
            predicted_generation_tokens=value.predicted_generation_tokens,
            prediction_basis=value.prediction_basis,
            cpu_before_tokens=value.cpu_before_tokens,
            cpu_after_tokens=value.cpu_after_tokens,
            summary_before_tokens=value.summary_before_tokens,
            summary_after_tokens=value.summary_after_tokens,
            critical_fields_digest=value.critical_fields_digest,
            summary_cas_status=value.summary_cas_status,
            summary_adoption_status=value.summary_adoption_status,
            reservation_ref=value.reservation_ref,
            usage_ref=value.usage_ref,
        )
