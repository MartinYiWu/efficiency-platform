"""原活跃节点的进程内派生绑定；不创建预算、控制器或持久机会账本。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from weakref import ReferenceType, ref

from efficiency_platform_agent.capabilities.model.memory_derive_handler import (
    MemoryDeriveHandler,
    OriginalDeriveFrame,
)
from efficiency_platform_agent.context.compaction import CompactionBaseline
from efficiency_platform_agent.contracts.memory_derive import MemoryDeriveRequest
from efficiency_platform_agent.core.context_dispatch import (
    current_model_stage,
    model_stage,
)
from efficiency_platform_agent.core.context_ports import (
    ContextOperation,
    MemoryPacketValidator,
)
from efficiency_platform_agent.core.execution_control import (
    RunControl,
    current_run_control,
    execution_scope,
)
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    MemoryContextPacket,
    SourceDependency,
)
from efficiency_platform_agent.core.memory_execution import MemoryExecutionStore
from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    current_paid_scope,
    paid_scope,
)
from efficiency_platform_agent.core.run_context_binding import (
    bind_run_context,
    current_run_context,
)
from efficiency_platform_agent.memory.execution_authority import (
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.memory.summary_policy import SummaryPolicy
from efficiency_platform_agent.memory.summary_validation import SummaryTaskState

type FrameFactory = Callable[
    [CompactionBaseline, ContextOperation],
    tuple[OriginalDeriveFrame, MemoryDeriveRequest] | None,
]


class OriginalDeriveStageAuthority(Protocol):
    async def is_claimed_operation(
        self, scope: ExecutionScope, stage_id: str, operation_id: str, deadline: int
    ) -> bool: ...


class FrozenOriginalDeriveSourceChecker:
    """冻结已认证计划的指纹；每次重读本机可信来源权威，不保留原文。"""

    def __init__(
        self,
        frozen_request: MemoryDeriveRequest,
        current: Callable[[], Awaitable[SummaryTaskState]],
    ):
        if frozen_request.fingerprint() != frozen_request.plan_fingerprint:
            raise ValueError("DERIVE_BINDING_CONFLICT")
        self._fingerprint = frozen_request.plan_fingerprint
        self._current = current

    async def check(
        self, request: MemoryDeriveRequest, frame: OriginalDeriveFrame
    ) -> SummaryTaskState:
        if (
            request.fingerprint() != self._fingerprint
            or request.plan_fingerprint != self._fingerprint
            or frame.operation != request.operation()
            or any(
                hashlib.sha256(source.body.encode("utf-8")).hexdigest()
                != source.body_sha256
                for source in request.sources
            )
        ):
            raise ValueError("DERIVE_SOURCE_AUTHORITY_MISMATCH")
        return await self._current()


@dataclass(slots=True)
class _Registration:
    frame: OriginalDeriveFrame | None = field(repr=False)
    fingerprint: str
    control: ReferenceType[RunControl]
    task: ReferenceType[asyncio.Task[Any]]
    request: MemoryDeriveRequest | None = field(default=None, repr=False)
    paid_scope_id: str = "unscoped"


@dataclass(slots=True)
class _FactoryScope:
    factory: FrameFactory | None
    control: ReferenceType[RunControl]
    task: ReferenceType[asyncio.Task[Any]]
    active: bool = True
    handles: list[OriginalDeriveScopeHandle] = field(default_factory=list)


class _LiveSourceChecker:
    def __init__(
        self, registry: LiveOriginalDeriveFrames, entry: _Registration, original
    ):
        self._registry, self._entry, self._original = registry, entry, original

    async def check(
        self, request: MemoryDeriveRequest, frame: OriginalDeriveFrame
    ) -> SummaryTaskState:
        await self._registry._validate(self._entry, request)
        state = await self._original.check(request, frame)
        await self._registry._check_live(self._entry)
        return state


class OriginalDeriveScopeHandle:
    def __init__(self, registry: LiveOriginalDeriveFrames, key: object):
        self._registry, self._key = registry, key

    def close(self) -> None:
        registration = self._registry._frames.pop(self._key, None)
        if registration is not None:
            registration.frame = None
            registration.request = None


class LiveOriginalDeriveFrames:
    def __init__(
        self,
        execution_store: MemoryExecutionStore,
        *,
        validator: MemoryPacketValidator | None = None,
        stage_authority: OriginalDeriveStageAuthority | None = None,
    ):
        self._store = execution_store
        self._validator = validator or StoredMemoryPacketValidator(execution_store)
        self._stage_authority = stage_authority
        self._frames: dict[object, _Registration] = {}
        self._factory: ContextVar[_FactoryScope | None] = ContextVar(
            "original_derive_factory", default=None
        )
        self._bound: ContextVar[_Registration | None] = ContextVar(
            "bound_original_derive_frame", default=None
        )

    @contextmanager
    def authorized_scope(self, frame_factory: FrameFactory) -> Iterator[None]:
        control, task = current_run_control(), asyncio.current_task()
        if control is None or task is None or self._factory.get() is not None:
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        control.check()
        scope = _FactoryScope(frame_factory, ref(control), ref(task))
        token = self._factory.set(scope)
        try:
            yield
        finally:
            scope.active = False
            scope.factory = None
            for handle in reversed(scope.handles):
                handle.close()
            scope.handles.clear()
            self._factory.reset(token)

    def observe_baseline(
        self, baseline: CompactionBaseline, operation: ContextOperation
    ) -> OriginalDeriveScopeHandle | None:
        authorized = self._factory.get()
        if authorized is None:
            return None
        control, task = authorized.control(), authorized.task()
        if (
            not authorized.active
            or authorized.factory is None
            or control is not current_run_control()
            or task is None
            or task.done()
            or task.cancelling()
        ):
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        created = authorized.factory(baseline, operation)
        if created is None:
            return None
        frame, frozen_request = created
        if frame.baseline is not baseline:
            raise ValueError("SUMMARY_BASELINE_MISMATCH")
        node_task = asyncio.current_task()
        assert control is not None and node_task is not None
        handle = self.register_scope(
            frame, control, node_task, frozen_request=frozen_request
        )
        authorized.handles.append(handle)
        return handle

    def register_scope(
        self,
        frame: OriginalDeriveFrame,
        original_control: RunControl,
        original_task: asyncio.Task[Any],
        *,
        frozen_request: MemoryDeriveRequest,
    ) -> OriginalDeriveScopeHandle:
        if (
            original_control is not current_run_control()
            or original_task is not asyncio.current_task()
            or original_task.done()
            or frozen_request.mode not in {"SUMMARY", "PROPOSALS", "BOTH"}
            or current_run_context() is not frame.binding
            or frozen_request.fingerprint() != frozen_request.plan_fingerprint
        ):
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        MemoryDeriveHandler._check_frame(frozen_request, frame)
        SummaryPolicy().admit(
            frozen_request.mode,
            tuple(source.metadata for source in frozen_request.sources),
            frozen_request.execution_scope.conversation,
            now=int(time.time()),
        )
        if any(
            entry.fingerprint == frozen_request.plan_fingerprint
            for entry in self._frames.values()
        ):
            raise ValueError("DERIVE_ORIGINAL_FRAME_CONFLICT")
        key = object()
        entry = _Registration(
            frame,
            frozen_request.plan_fingerprint,
            ref(original_control),
            ref(original_task),
            frozen_request,
            current_paid_scope(),
        )
        entry.frame = replace(
            frame, source_checker=_LiveSourceChecker(self, entry, frame.source_checker)
        )
        self._frames[key] = entry
        handle = OriginalDeriveScopeHandle(self, key)
        original_task.add_done_callback(lambda _: handle.close())
        return handle

    async def lookup_request(
        self, tenant_id: str, execution_id: str
    ) -> MemoryDeriveRequest | None:
        """仅暴露仍登记的原节点请求；节点退出同步清正文引用。"""
        for entry in tuple(self._frames.values()):
            frame = entry.frame
            if frame is None or (
                frame.binding.conversation.tenant_id,
                frame.binding.execution_id,
            ) != (tenant_id, execution_id):
                continue
            try:
                await self._check_live(entry)
            except (ValueError, PaidBudgetError):
                return None
            return entry.request
        return None

    async def _check_live(self, entry: _Registration) -> OriginalDeriveFrame:
        frame, control, task = entry.frame, entry.control(), entry.task()
        if (
            frame is None
            or control is None
            or task is None
            or task.done()
            or task.cancelling()
        ):
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        control.check()
        binding = frame.binding
        memory = binding.memory_context
        record = await self._store.get(
            binding.conversation.tenant_id, binding.execution_id
        )
        if (
            entry.frame is not frame
            or memory is None
            or record is None
            or record.state != "ACTIVE"
            or record.context != memory
            or (record.runtime_id, record.runtime_kind)
            != (frame.runtime_id, frame.runtime_kind)
            or record.deadline_epoch_seconds != binding.deadline_epoch_seconds
            or time.time() >= frame.operation.deadline_epoch_seconds
            or (
                record.execution_revision,
                record.grant_epoch,
                record.source_epoch,
                record.deletion_epoch,
            )
            != (
                memory.packet.execution_revision,
                memory.packet.grant_epoch,
                memory.packet.source_epoch,
                memory.packet.deletion_epoch,
            )
        ):
            raise ValueError("DERIVE_ORIGINAL_EXECUTION_REQUIRED")
        return frame

    async def _validate(
        self, entry: _Registration, request: MemoryDeriveRequest
    ) -> OriginalDeriveFrame:
        frame = await self._check_live(entry)
        if (
            request.plan_fingerprint != entry.fingerprint
            or request.fingerprint() != entry.fingerprint
        ):
            raise ValueError("DERIVE_BINDING_CONFLICT")
        MemoryDeriveHandler._check_frame(request, frame)
        dependencies = tuple(
            dict.fromkeys(
                dependency.to_core()
                for source in request.sources
                for dependency in source.metadata.source_dependencies
            )
        )
        memory = frame.binding.memory_context
        assert memory is not None
        await self._validate_packet(frame, dependencies)
        return frame

    async def _validate_packet(
        self, frame: OriginalDeriveFrame, dependencies: tuple[SourceDependency, ...]
    ) -> None:
        memory = frame.binding.memory_context
        assert memory is not None
        # 派生阶段复核的是已登记原节点grant；检查结束恢复当前派生stage。
        with model_stage(
            frame.operation.operation_id,
            b"",
            node_id=frame.operation.scope.subtask_id,
            subtask_id=frame.operation.scope.subtask_id,
        ):
            await self._validator.validate(
                frame.operation.scope,
                memory.packet,
                dependencies,
                ContextOperation(
                    frame.operation.operation_id,
                    1,
                    frame.binding.deadline_epoch_seconds,
                    False,
                ),
            )

    async def validate(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket | None,
        dependencies: tuple[SourceDependency, ...],
        operation: ContextOperation,
    ) -> None:
        """派生专用Controller的包门禁；私有bind缺失时不能借此获得原grant。"""
        entry = self._bound.get()
        if entry is None:
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        frame = await self._check_live(entry)
        memory = frame.binding.memory_context
        operation_matches = operation.operation_id == frame.operation.operation_id
        if not operation_matches and self._stage_authority is not None:
            stage = current_model_stage()
            if (
                stage is not None
                and stage.node_id == "memory.derive"
                and stage.stage_id == frame.operation.operation_id
                and operation.attempt == 1
            ):
                operation_matches = await self._stage_authority.is_claimed_operation(
                    frame.operation.scope,
                    stage.stage_id,
                    operation.operation_id,
                    operation.deadline_epoch_seconds,
                )
        if (
            memory is None
            or current_run_context() is not frame.binding
            or scope != frame.operation.scope
            or packet != memory.packet
            or not operation_matches
            or operation.deadline_epoch_seconds
            != frame.operation.deadline_epoch_seconds
            or operation.memory_disabled
            or not set(dependencies).issubset(
                frame.baseline.window_policy.authorized_dependencies
            )
        ):
            raise ValueError("DERIVE_BINDING_CONFLICT")
        await self._validate_packet(frame, dependencies)
        await self._check_live(entry)

    async def derive_manifest_binding(
        self, scope: ExecutionScope, operation: ContextOperation
    ) -> str:
        entry = self._bound.get()
        if entry is None or entry.request is None:
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        frame = await self._check_live(entry)
        memory = frame.binding.memory_context
        assert memory is not None
        stage = current_model_stage()
        if (
            self._stage_authority is None
            or stage is None
            or stage.node_id != "memory.derive"
            or stage.stage_id != frame.operation.operation_id
            or not await self._stage_authority.is_claimed_operation(
                scope,
                stage.stage_id,
                operation.operation_id,
                operation.deadline_epoch_seconds,
            )
        ):
            raise ValueError("DERIVE_MANIFEST_BINDING_INVALID")
        await self.validate(
            scope,
            memory.packet,
            frame.baseline.window_policy.authorized_dependencies,
            operation,
        )
        header = entry.request.model_dump(
            mode="json", exclude={"sources", "events", "required_entries"}
        )
        header["logical_stage_id"] = frame.operation.operation_id
        header["physical_operation_id"] = operation.operation_id
        return json.dumps(
            header,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @asynccontextmanager
    async def bind(self, request: MemoryDeriveRequest):
        if request.fingerprint() != request.plan_fingerprint or any(
            hashlib.sha256(source.body.encode("utf-8")).hexdigest()
            != source.body_sha256
            for source in request.sources
        ):
            raise ValueError("DERIVE_BINDING_CONFLICT")
        entry = next(
            (
                item
                for item in self._frames.values()
                if item.fingerprint == request.plan_fingerprint
            ),
            None,
        )
        if entry is None:
            raise ValueError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        frame = await self._check_live(entry)
        control = entry.control()
        assert control is not None
        with (
            execution_scope(control),
            bind_run_context(frame.binding),
            paid_scope(entry.paid_scope_id),
        ):
            token = self._bound.set(entry)
            try:
                await frame.source_checker.check(request, frame)
                await self._check_live(entry)
                yield frame
                await self._check_live(entry)
            finally:
                self._bound.reset(token)
