"""derive 候选与必须由可信组合边界注入的来源/授权端口。"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.contracts.memory import (
    ConversationScopeModel,
    MemoryProposalModel,
)
from efficiency_platform_agent.core.derive_ports import DeriveOperation
from efficiency_platform_agent.core.memory import MemoryContextPacket
from efficiency_platform_agent.memory.summary_contracts import (
    RejectedOption,
    SummaryBasisEvent,
    SummaryEntry,
    SummaryInputSource,
    SummarySegment,
)

type DeriveMode = Literal["SUMMARY", "PROPOSALS", "BOTH"]


class DeriveCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )
    mode: DeriveMode
    summary: SummarySegment | None = Field(repr=False)
    proposals: tuple[MemoryProposalModel, ...] = Field(max_length=16, repr=False)


@dataclass(frozen=True, slots=True)
class HydratedDeriveSources:
    bodies: tuple[str, ...] = field(repr=False)
    events: tuple[SummaryBasisEvent, ...] = field(repr=False)
    source_revision: int
    required_entries: tuple[SummaryEntry | RejectedOption, ...] = field(
        default=(), repr=False
    )


class DeriveSourceHydrator(Protocol):
    async def hydrate(
        self,
        scope: ConversationScopeModel,
        mode: DeriveMode,
        sources: tuple[SummaryInputSource, ...],
        operation: DeriveOperation,
    ) -> HydratedDeriveSources: ...


class DeriveAuthorizer(Protocol):
    async def check(
        self,
        scope: ConversationScopeModel,
        mode: DeriveMode,
        sources: tuple[SummaryInputSource, ...],
        operation: DeriveOperation,
    ) -> MemoryContextPacket | None:
        """重查原授权/用途/来源，不得从业务 HTTP 声明铸造授权。"""
        ...
