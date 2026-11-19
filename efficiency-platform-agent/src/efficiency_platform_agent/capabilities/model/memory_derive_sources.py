"""单次鉴权请求内的冻结来源适配；不缓存原文、不反调 Java。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

from efficiency_platform_agent.contracts.memory import ConversationScopeModel
from efficiency_platform_agent.contracts.memory_derive import MemoryDeriveRequest
from efficiency_platform_agent.core.derive_ports import DeriveOperation
from efficiency_platform_agent.core.memory import MemoryContextPacket
from efficiency_platform_agent.memory.derive import DeriveMode, HydratedDeriveSources
from efficiency_platform_agent.memory.summary_contracts import SummaryInputSource
from efficiency_platform_agent.memory.summary_validation import SummaryTaskState

if TYPE_CHECKING:
    from .memory_derive_handler import OriginalDeriveFrame


class TrustedDeriveSourceChecker(Protocol):
    async def check(
        self, request: MemoryDeriveRequest, frame: OriginalDeriveFrame
    ) -> SummaryTaskState:
        """核原执行 packet、全部依赖及本机可信来源镜像；不得默认接受 HTTP 声明。"""
        ...


class RequestDeriveSources:
    def __init__(self, request: MemoryDeriveRequest, frame: OriginalDeriveFrame):
        self.request, self.frame = request, frame
        self.sources = tuple(source.metadata for source in request.sources)

    async def current(self) -> SummaryTaskState:
        request, frame = self.request, self.frame
        if time.time() >= request.deadline_epoch_seconds:
            raise ValueError("DERIVE_DEADLINE_EXCEEDED")
        state = await frame.source_checker.check(request, frame)
        if (
            type(state) is not SummaryTaskState
            or state.scope != request.execution_scope.conversation
            or state.original_mode != request.mode
            or state.memory_policy_version != request.assets.memory_policy_version
            or state.authority_ref != request.authority_ref
            or state.session_revision < request.session_revision
            or state.source_revision < request.source_revision
            or abs(state.now - int(time.time())) > 5
        ):
            raise ValueError("DERIVE_SOURCE_AUTHORITY_MISMATCH")
        first, last = self.sources[0].sequence, self.sources[-1].sequence
        if (
            tuple(s for s in state.current_sources if first <= s.sequence <= last)
            != self.sources
        ):
            raise ValueError("SUMMARY_STALE")
        return state

    async def check(
        self,
        scope: ConversationScopeModel,
        mode: DeriveMode,
        sources: tuple[SummaryInputSource, ...],
        operation: DeriveOperation,
    ) -> MemoryContextPacket:
        if (
            scope != self.request.execution_scope.conversation
            or mode != self.request.mode
            or sources != self.sources
            or operation != self.frame.operation
        ):
            raise ValueError("DERIVE_BINDING_CONFLICT")
        await self.current()
        memory = self.frame.binding.memory_context
        if memory is None:
            raise ValueError("DERIVE_ORIGINAL_EXECUTION_REQUIRED")
        return memory.packet

    async def hydrate(
        self,
        scope: ConversationScopeModel,
        mode: DeriveMode,
        sources: tuple[SummaryInputSource, ...],
        operation: DeriveOperation,
    ) -> HydratedDeriveSources:
        await self.check(scope, mode, sources, operation)
        return HydratedDeriveSources(
            tuple(source.body for source in self.request.sources),
            self.request.events,
            self.request.source_revision,
            self.request.required_entries,
        )
