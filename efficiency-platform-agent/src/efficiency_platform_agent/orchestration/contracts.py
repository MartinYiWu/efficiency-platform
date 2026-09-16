"""唯一 S2 图运行时与构建器共享的契约。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from efficiency_platform_agent.core.budget import BudgetState
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import JsonObject, JsonValue
from efficiency_platform_agent.core.runtime import (
    ExecutionFact,
    RunFailure,
    UsageSnapshot,
)
from efficiency_platform_agent.routing.strategy_router import StrategySelection

from .state import AgentGraphState


class GraphProgram(Protocol):
    async def invoke(
        self, initial_state: AgentGraphState, config: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        raise NotImplementedError

    async def resume(
        self, resume_value: JsonObject, config: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        raise NotImplementedError

    async def get_state(
        self, config: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        raise NotImplementedError


class GraphBuilder(Protocol):
    def build(self) -> GraphProgram:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class CheckpointView:
    thread_id: str
    checkpoint_ns: str
    checkpoint_id: str
    resume_binding: JsonObject = field(default_factory=JsonObject)

    def __post_init__(self) -> None:
        for name, value in (
            ("thread_id", self.thread_id),
            ("checkpoint_ns", self.checkpoint_ns),
            ("checkpoint_id", self.checkpoint_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.resume_binding, JsonObject):
            raise TypeError("resume_binding must be JsonObject")


class ResumeValueValidator(Protocol):
    def validate(self, checkpoint: CheckpointView, resume_value: JsonObject) -> None:
        raise NotImplementedError


class StrategyPayloadAdapter(Protocol):
    def adapt(self, schema_version: str, payload: JsonObject) -> object:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class GraphRegistration:
    graph_id: str
    strategy: StrategyMode
    graph_version: str
    checkpoint_ns: str
    strategy_payload_schema_version: str
    allowed_strategy_payload_keys: frozenset[str]
    allowed_next_statuses: frozenset[RunStatus]
    builder: GraphBuilder
    payload_adapter: StrategyPayloadAdapter
    resume_validator: ResumeValueValidator | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.graph_id, str) or not isinstance(
            self.graph_version, str
        ):
            raise TypeError("图标识和版本必须是字符串")
        if not self.graph_id.strip() or not self.graph_version.strip():
            raise ValueError("graph id/version must be non-empty")
        if not isinstance(self.strategy, StrategyMode):
            raise TypeError("strategy must be StrategyMode")
        expected = f"s2:{self.strategy.value}:{self.graph_version.split('.', 1)[0]}"
        if self.checkpoint_ns != expected:
            raise ValueError("checkpoint namespace must be s2:<strategy>:<major>")
        if not self.allowed_next_statuses:
            raise ValueError("allowed_next_statuses must not be empty")
        if not isinstance(self.allowed_strategy_payload_keys, frozenset):
            raise TypeError("allowed_strategy_payload_keys must be frozenset")


@dataclass(frozen=True, slots=True)
class GraphExecutionResult:
    usage: UsageSnapshot
    budget_state: BudgetState
    checkpoint: CheckpointView
    facts: tuple[ExecutionFact, ...]
    next_status: RunStatus = RunStatus.SUCCEEDED
    output: JsonValue = None
    failure: RunFailure | None = None
    degraded: bool = False


class GraphRuntime:
    async def execute(
        self, selection: StrategySelection, initial_state: AgentGraphState
    ) -> GraphExecutionResult:
        raise NotImplementedError

    def validate_resume(
        self,
        selection: StrategySelection,
        checkpoint: CheckpointView,
        resume_value: JsonObject,
    ) -> None:
        raise NotImplementedError

    async def resume(
        self,
        selection: StrategySelection,
        run_id: str,
        checkpoint_id: str,
        resume_value: JsonObject,
        *,
        tenant_id: str = "",
    ) -> GraphExecutionResult:
        raise NotImplementedError

    async def get_checkpoint(
        self, selection: StrategySelection, run_id: str, *, tenant_id: str = ""
    ) -> CheckpointView | None:
        raise NotImplementedError
