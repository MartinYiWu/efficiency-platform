from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .memory import (
    ExecutionScope,
    SourceDependency,
    require_bool,
    require_count,
    require_dependencies,
    require_id,
)
from .run import ProviderMessage, ProviderRequest


@dataclass(frozen=True, slots=True)
class ModelCapacity:
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

    def __post_init__(self) -> None:
        for value in (
            self.provider,
            self.model,
            self.model_version,
            self.tokenizer_ref,
            self.serialization_ref,
            self.reasoning_rule,
            self.evidence_ref,
        ):
            require_id(value)
        for count in (self.context_window_tokens, self.max_output_tokens):
            require_count(count)
        if self.max_input_tokens is not None:
            require_count(self.max_input_tokens)
        require_bool(self.verified)


@dataclass(frozen=True, slots=True)
class WindowLimits:
    context_window_tokens: int
    independent_input_limit: int | None
    output_reserve_tokens: int
    safety_margin_tokens: int
    node_input_limit: int

    def __post_init__(self) -> None:
        for count in (
            self.context_window_tokens,
            self.output_reserve_tokens,
            self.safety_margin_tokens,
            self.node_input_limit,
        ):
            require_count(count)
        if self.independent_input_limit is not None:
            require_count(self.independent_input_limit)
        if (
            self.output_reserve_tokens + self.safety_margin_tokens
            > self.context_window_tokens
        ):
            raise ValueError("WINDOW_RESERVE_INVALID")

    def input_cap(self) -> int:
        cap = min(
            self.context_window_tokens
            - self.output_reserve_tokens
            - self.safety_margin_tokens,
            self.node_input_limit,
        )
        return (
            min(cap, self.independent_input_limit)
            if self.independent_input_limit is not None
            else cap
        )


@dataclass(frozen=True, slots=True)
class TokenMeasurement:
    total_upper_bound: int
    by_component: tuple[tuple[str, int], ...]
    method: str
    verified: bool

    def __post_init__(self) -> None:
        require_count(self.total_upper_bound)
        require_id(self.method)
        require_bool(self.verified)
        if type(self.by_component) is not tuple:
            raise ValueError("TOKEN_COMPONENTS_INVALID")
        names = set()
        for component in self.by_component:
            if type(component) is not tuple or len(component) != 2:
                raise ValueError("TOKEN_COMPONENTS_INVALID")
            name, count = component
            require_id(name)
            require_count(count)
            if name in names:
                raise ValueError("TOKEN_COMPONENTS_DUPLICATE")
            names.add(name)
        if sum(count for _, count in self.by_component) > self.total_upper_bound:
            raise ValueError("TOKEN_TOTAL_INVALID")


@runtime_checkable
class TokenCounter(Protocol):
    """完整Provider请求的离线输入上界，不执行模型或远程计数调用。"""

    def measure(
        self, request: ProviderRequest, capacity: ModelCapacity
    ) -> TokenMeasurement:
        """返回已核实序列化口径的输入上界。"""
        ...


@runtime_checkable
class ContextFragmentCounter(Protocol):
    """可选的片段计数合同；全请求硬校验仍然独立执行。"""

    def measure_messages(
        self, messages: tuple[ProviderMessage, ...], capacity: ModelCapacity
    ) -> TokenMeasurement:
        """只计算消息片段及其封装，不加入全请求固定余量。"""
        ...


@dataclass(frozen=True, slots=True)
class WindowDecision:
    H_ctx: int
    T: int
    F: int
    status: str

    def __post_init__(self) -> None:
        for count in (self.H_ctx, self.T, self.F):
            require_count(count)
        if self.status not in {"ALLOW", "TRIM", "REJECT"}:
            raise ValueError("WINDOW_STATUS_INVALID")


@dataclass(frozen=True, slots=True)
class ContextManifest:
    manifest_id: str
    scope: ExecutionScope
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
    safety_dependencies: tuple[SourceDependency, ...]
    selected_sources: tuple[SourceDependency, ...]
    exclusions: tuple[tuple[str, str], ...]
    measurement: TokenMeasurement
    decision: WindowDecision
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
    summary_projection_aliases: tuple[tuple[str, str], ...] = ()
    derive_binding_json: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, ExecutionScope)
            or not isinstance(self.measurement, TokenMeasurement)
            or not isinstance(self.decision, WindowDecision)
        ):
            raise TypeError("MANIFEST_TYPE_INVALID")
        for value in (
            self.manifest_id,
            self.operation_id,
            self.node_id,
            self.model_version,
            self.prompt_version,
            self.tool_version,
            self.output_schema_version,
            self.tokenizer_ref,
            self.serialization_ref,
            self.policy_version,
            self.canonical_request_hmac,
            self.prediction_basis,
            self.critical_fields_digest,
            self.summary_cas_status,
            self.summary_adoption_status,
        ):
            require_id(value)
        for optional_ref in (self.packet_id, self.reservation_ref, self.usage_ref):
            if optional_ref is not None:
                require_id(optional_ref)
        for count in (
            self.attempt,
            self.ctx_revision,
            self.output_reserve_tokens,
            self.safety_margin_tokens,
            self.predicted_generation_tokens,
            self.cpu_before_tokens,
            self.cpu_after_tokens,
            self.summary_before_tokens,
            self.summary_after_tokens,
        ):
            require_count(count)
        if (self.packet_id is None) != (self.packet_revision is None):
            raise ValueError("MANIFEST_PACKET_INVALID")
        if self.packet_revision is not None:
            require_count(self.packet_revision)
        require_dependencies(self.safety_dependencies)
        require_dependencies(self.selected_sources)
        if not set(self.selected_sources).issubset(self.safety_dependencies):
            raise ValueError("MANIFEST_DEPENDENCIES_INCOMPLETE")
        if type(self.exclusions) is not tuple:
            raise ValueError("MANIFEST_EXCLUSIONS_INVALID")
        for exclusion in self.exclusions:
            if type(exclusion) is not tuple or len(exclusion) != 2:
                raise ValueError("MANIFEST_EXCLUSIONS_INVALID")
            for value in exclusion:
                require_id(value)
        if self.derive_binding_json is not None and (
            self.node_id != "memory.derive"
            or type(self.derive_binding_json) is not str
            or not self.derive_binding_json
            or len(self.derive_binding_json.encode("utf-8")) > 16384
        ):
            raise ValueError("DERIVE_MANIFEST_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class PreparedContext:
    request: ProviderRequest = field(repr=False)
    manifest: ContextManifest
    memory_policy_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, ProviderRequest) or not isinstance(
            self.manifest, ContextManifest
        ):
            raise TypeError("PREPARED_CONTEXT_INVALID")
