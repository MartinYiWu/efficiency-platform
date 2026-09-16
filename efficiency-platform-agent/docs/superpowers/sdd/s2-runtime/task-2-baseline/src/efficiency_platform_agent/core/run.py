"""Immutable framework-neutral contracts used at Agent architecture boundaries."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, TypeAlias

from .enums import RunStatus, StrategyMode


JsonScalar: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class JsonObject:
    """Immutable JSON object represented by ordered, unique key/value pairs."""

    items: tuple[tuple[str, "JsonValue"], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TypeError("JSON object items must be an immutable tuple")
        seen_keys: set[str] = set()
        for item in self.items:
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError("JSON object entries must be two-item tuples")
            key, value = item
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            if key in seen_keys:
                raise ValueError(f"duplicate JSON object key: {key!r}")
            seen_keys.add(key)
            _validate_json_value(value)


JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | JsonObject


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    """Version-independent hard limits assigned to one execution scope."""

    max_iterations: int
    max_tool_calls: int
    max_input_tokens: int
    max_output_tokens: int
    timeout_ms: int
    max_cost_microunits: int

    def __post_init__(self) -> None:
        _require_positive_int("max_iterations", self.max_iterations)
        _require_non_negative_int("max_tool_calls", self.max_tool_calls)
        _require_non_negative_int("max_input_tokens", self.max_input_tokens)
        _require_non_negative_int("max_output_tokens", self.max_output_tokens)
        _require_positive_int("timeout_ms", self.timeout_ms)
        _require_non_negative_int(
            "max_cost_microunits", self.max_cost_microunits
        )


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    """Versioned governance metadata shared by all extension ports."""

    name: str
    semantic_version: str
    input_schema_version: str
    output_schema_version: str
    permissions: frozenset[str]
    budget: ExecutionBudget
    termination_conditions: frozenset[str]
    checkpoint_version: str

    def __post_init__(self) -> None:
        _require_non_empty("name", self.name)
        if not _SEMANTIC_VERSION.fullmatch(self.semantic_version):
            raise ValueError("semantic_version must use MAJOR.MINOR.PATCH")
        _require_non_empty("input_schema_version", self.input_schema_version)
        _require_non_empty("output_schema_version", self.output_schema_version)
        _require_string_set("permissions", self.permissions, allow_empty=True)
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget must be an ExecutionBudget")
        _require_string_set(
            "termination_conditions",
            self.termination_conditions,
            allow_empty=False,
        )
        _require_non_empty("checkpoint_version", self.checkpoint_version)


@dataclass(frozen=True, slots=True)
class SupervisorTask:
    """Trimmed subtask that a Supervisor may assign to a specialist Agent."""

    task_id: str
    parent_run_id: str
    target_agent: str
    input_data: JsonObject
    context_view: JsonObject
    allowed_tools: frozenset[str]
    budget: ExecutionBudget

    def __post_init__(self) -> None:
        _require_non_empty("task_id", self.task_id)
        _require_non_empty("parent_run_id", self.parent_run_id)
        _require_non_empty("target_agent", self.target_agent)
        _require_json_object("input_data", self.input_data)
        _require_json_object("context_view", self.context_view)
        _require_string_set("allowed_tools", self.allowed_tools, allow_empty=True)
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget must be an ExecutionBudget")


@dataclass(frozen=True, slots=True)
class RunRequest:
    """Normalized request accepted by the Agent harness."""

    request_id: str
    tenant_id: str
    user_id: str
    input_text: str
    metadata: JsonObject = field(default_factory=JsonObject)

    def __post_init__(self) -> None:
        _require_non_empty("request_id", self.request_id)
        _require_non_empty("tenant_id", self.tenant_id)
        _require_non_empty("user_id", self.user_id)
        _require_non_empty("input_text", self.input_text)
        _require_json_object("metadata", self.metadata)


@dataclass(frozen=True, slots=True)
class RunContext:
    """Identity and trace data propagated through one run."""

    run_id: str
    tenant_id: str
    user_id: str
    trace_id: str
    metadata: JsonObject = field(default_factory=JsonObject)

    def __post_init__(self) -> None:
        _require_non_empty("run_id", self.run_id)
        _require_non_empty("tenant_id", self.tenant_id)
        _require_non_empty("user_id", self.user_id)
        _require_non_empty("trace_id", self.trace_id)
        _require_json_object("metadata", self.metadata)


@dataclass(frozen=True, slots=True)
class ToolError:
    """Structured, provider-independent Tool failure."""

    code: str
    category: str
    retryable: bool
    safe_message: str
    side_effect_status: str

    def __post_init__(self) -> None:
        _require_non_empty("code", self.code)
        _require_non_empty("category", self.category)
        _require_bool("retryable", self.retryable)
        _require_non_empty("safe_message", self.safe_message)
        if self.side_effect_status not in {"none", "possible", "confirmed"}:
            raise ValueError(
                "side_effect_status must be none, possible, or confirmed"
            )


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    """Approval proof bound to one subject, Tool, argument digest, and expiry."""

    approval_id: str
    subject_id: str
    tool_name: str
    arguments_digest: str
    expires_at_epoch_ms: int

    def __post_init__(self) -> None:
        _require_non_empty("approval_id", self.approval_id)
        _require_non_empty("subject_id", self.subject_id)
        _require_non_empty("tool_name", self.tool_name)
        _require_non_empty("arguments_digest", self.arguments_digest)
        _require_positive_int("expires_at_epoch_ms", self.expires_at_epoch_ms)


@dataclass(frozen=True, slots=True)
class ToolRequest:
    """Versioned invocation request consumed by the governed Tool Runtime."""

    contract_version: str
    tool_name: str
    arguments: JsonObject
    timeout_ms: int
    approval_binding: ApprovalBinding | None
    idempotency_key: str | None
    has_side_effects: bool
    max_output_bytes: int

    def __post_init__(self) -> None:
        _require_non_empty("contract_version", self.contract_version)
        _require_non_empty("tool_name", self.tool_name)
        _require_json_object("arguments", self.arguments)
        _require_positive_int("timeout_ms", self.timeout_ms)
        if self.approval_binding is not None:
            if not isinstance(self.approval_binding, ApprovalBinding):
                raise TypeError("approval_binding must be ApprovalBinding or None")
            if self.approval_binding.tool_name != self.tool_name:
                raise ValueError("approval_binding must target the requested Tool")
        _require_optional_non_empty("idempotency_key", self.idempotency_key)
        _require_bool("has_side_effects", self.has_side_effects)
        _require_positive_int("max_output_bytes", self.max_output_bytes)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Bounded structured Tool output or normalized Tool error."""

    contract_version: str
    output: JsonValue
    error: ToolError | None
    output_bytes: int
    is_truncated: bool
    metadata: JsonObject = field(default_factory=JsonObject)

    def __post_init__(self) -> None:
        _require_non_empty("contract_version", self.contract_version)
        _validate_json_value(self.output)
        if self.error is not None and not isinstance(self.error, ToolError):
            raise TypeError("error must be a ToolError or None")
        _require_non_negative_int("output_bytes", self.output_bytes)
        _require_bool("is_truncated", self.is_truncated)
        _require_json_object("metadata", self.metadata)


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    """Version-neutral structured model message."""

    role: str
    content: JsonValue

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("role must be system, user, assistant, or tool")
        _validate_json_value(self.content)


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Versioned provider request with normalized messages and options."""

    contract_version: str
    messages: tuple[ProviderMessage, ...]
    options: JsonObject
    timeout_ms: int

    def __post_init__(self) -> None:
        _require_non_empty("contract_version", self.contract_version)
        if not isinstance(self.messages, tuple):
            raise TypeError("messages must be an immutable tuple")
        if not self.messages:
            raise ValueError("messages must not be empty")
        if any(not isinstance(message, ProviderMessage) for message in self.messages):
            raise TypeError("messages must contain only ProviderMessage values")
        _require_json_object("options", self.options)
        _require_positive_int("timeout_ms", self.timeout_ms)


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Normalized non-negative model usage and cost counters."""

    input_tokens: int
    output_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    cost_microunits: int

    def __post_init__(self) -> None:
        for field_name in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "reasoning_tokens",
            "cost_microunits",
        ):
            _require_non_negative_int(field_name, getattr(self, field_name))


@dataclass(frozen=True, slots=True)
class ProviderError:
    """Normalized Provider error that never exposes a vendor exception."""

    code: str
    category: str
    retryable: bool
    safe_message: str
    provider_request_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("code", self.code)
        _require_non_empty("category", self.category)
        _require_bool("retryable", self.retryable)
        _require_non_empty("safe_message", self.safe_message)
        _require_optional_non_empty(
            "provider_request_id", self.provider_request_id
        )


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Normalized Provider completion, usage, or structured error."""

    contract_version: str
    message: ProviderMessage | None
    usage: ProviderUsage
    error: ProviderError | None = None

    def __post_init__(self) -> None:
        _require_non_empty("contract_version", self.contract_version)
        if not isinstance(self.usage, ProviderUsage):
            raise TypeError("usage must be ProviderUsage")
        if self.message is not None and not isinstance(self.message, ProviderMessage):
            raise TypeError("message must be ProviderMessage or None")
        if self.error is not None and not isinstance(self.error, ProviderError):
            raise TypeError("error must be ProviderError or None")
        if (self.message is None) == (self.error is None):
            raise ValueError("exactly one of message or error must be present")


@dataclass(frozen=True, slots=True)
class RunResult:
    """Normalized terminal or suspended result of an Agent run."""

    run_id: str
    status: RunStatus
    strategy: StrategyMode
    output: JsonValue = None
    metadata: JsonObject = field(default_factory=JsonObject)

    def __post_init__(self) -> None:
        _require_non_empty("run_id", self.run_id)
        if not isinstance(self.status, RunStatus):
            raise TypeError("status must be RunStatus")
        if not isinstance(self.strategy, StrategyMode):
            raise TypeError("strategy must be StrategyMode")
        _validate_json_value(self.output)
        _require_json_object("metadata", self.metadata)


RUN_STATUS_TRANSITIONS: Mapping[RunStatus, frozenset[RunStatus]] = MappingProxyType(
    {
        RunStatus.CREATED: frozenset({RunStatus.QUEUED, RunStatus.CANCELLED}),
        RunStatus.QUEUED: frozenset(
            {
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }
        ),
        RunStatus.RUNNING: frozenset(
            {
                RunStatus.WAITING_TOOL,
                RunStatus.WAITING_INPUT,
                RunStatus.WAITING_APPROVAL,
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }
        ),
        RunStatus.WAITING_TOOL: frozenset(
            {
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }
        ),
        RunStatus.WAITING_INPUT: frozenset(
            {
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }
        ),
        RunStatus.WAITING_APPROVAL: frozenset(
            {
                RunStatus.RUNNING,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }
        ),
        RunStatus.SUCCEEDED: frozenset(),
        RunStatus.FAILED: frozenset(),
        RunStatus.CANCELLED: frozenset(),
        RunStatus.TIMED_OUT: frozenset(),
    }
)


def is_valid_run_status_transition(current: RunStatus, target: RunStatus) -> bool:
    """Return whether a transition is legal; same-state events are idempotent."""

    if not isinstance(current, RunStatus) or not isinstance(target, RunStatus):
        raise TypeError("current and target must be RunStatus values")
    return current == target or target in RUN_STATUS_TRANSITIONS[current]


def validate_run_status_transition(current: RunStatus, target: RunStatus) -> None:
    """Raise ``ValueError`` when a Run status transition is not legal."""

    if not is_valid_run_status_transition(current, target):
        raise ValueError(f"illegal Run status transition: {current.value} -> {target.value}")


_SEMANTIC_VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _validate_json_value(value: JsonValue) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, JsonObject):
        return
    if isinstance(value, tuple):
        for item in value:
            _validate_json_value(item)
        return
    raise TypeError(
        "JSON values must use scalar, tuple, or JsonObject immutable forms"
    )


def _require_non_empty(field_name: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_optional_non_empty(field_name: str, value: str | None) -> None:
    if value is not None:
        _require_non_empty(field_name, value)


def _require_non_negative_int(field_name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive_int(field_name: str, value: int) -> None:
    _require_non_negative_int(field_name, value)
    if value == 0:
        raise ValueError(f"{field_name} must be positive")


def _require_bool(field_name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")


def _require_json_object(field_name: str, value: JsonObject) -> None:
    if not isinstance(value, JsonObject):
        raise TypeError(f"{field_name} must be a JsonObject")


def _require_string_set(
    field_name: str,
    value: frozenset[str],
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(value, frozenset):
        raise TypeError(f"{field_name} must be a frozenset")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    for item in value:
        _require_non_empty(field_name, item)
