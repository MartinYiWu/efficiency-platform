"""每次发送从本机技术权威重读原授权；复用D13P全部包校验。"""

import asyncio
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import uuid4
from weakref import ReferenceType, ref

from efficiency_platform_agent.core.context_dispatch import (
    ResultPublishDenied,
    current_model_stage,
)
from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.execution_control import (
    RunControl,
    current_run_control,
)
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    MemoryContextPacket,
    SourceDependency,
)
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionRecord,
    MemoryExecutionStore,
    MemorySendPermit,
    memory_operation_deadline_matches,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.security.memory_packet import (
    AuthorizedMemoryPacketValidator,
    MemoryExecutionAuthorization,
    MemoryPacketBinding,
)


@dataclass(slots=True)
class _IssuedSend:
    permit: MemorySendPermit
    task: ReferenceType[asyncio.Task[Any]]
    control: ReferenceType[RunControl]
    derive: bool = False
    complete: bool = False
    result_ref: str | None = None


@dataclass(slots=True)
class _GraphFrame:
    runtime_id: str
    task: ReferenceType[asyncio.Task[Any]]
    control: ReferenceType[RunControl]
    captured: tuple[MemorySendPermit, str] | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class _CurrentResultPublisher:
    authority: "MemorySendLeaseAuthority"
    permit: MemorySendPermit
    result_ref: str

    async def check(self, run_id: str) -> None:
        await self.authority.check_current_result(self.permit, self.result_ref, run_id)


class MemorySendLeaseAuthority:
    """只由实际发送lease产生进程内能力，结果scope保持PG→MySQL锁顺序。"""

    def __init__(
        self,
        registry,
        execution_store: MemoryExecutionStore,
        backend_id: str | None = None,
    ):
        self.registry, self.execution_store, self.backend_id = (
            registry,
            execution_store,
            backend_id,
        )
        self._active: dict[object, object] = {}
        self._issued: dict[str, _IssuedSend] = {}
        self._results: dict[object, MemorySendPermit] = {}
        self._graph: ContextVar[_GraphFrame | None] = ContextVar(
            "memory_send_graph_frame", default=None
        )
        self._checkpoint_permit: ContextVar[MemorySendPermit | None] = ContextVar(
            "memory_result_task_permit", default=None
        )
        self._checkpoint_result_ref: ContextVar[str | None] = ContextVar(
            "memory_checkpoint_result_ref", default=None
        )

    @asynccontextmanager
    async def graph_scope(self, runtime_id: str):
        control, task = current_run_control(), asyncio.current_task()
        if control is None or task is None or self._graph.get() is not None:
            raise PermissionError("MEMORY_GRAPH_FRAME_REQUIRED")
        control.check()
        frame = _GraphFrame(runtime_id, ref(task), ref(control))
        token = self._graph.set(frame)
        try:
            yield
        finally:
            frame.active = False
            self._graph.reset(token)

    def _backend(self, conversation) -> str:
        return self.backend_id or (
            "NO_CHECKPOINT" if conversation.domain == "customer-service" else "official"
        )

    @asynccontextmanager
    async def acquire(self):
        binding = current_run_context()
        task = asyncio.current_task()
        control = current_run_control()
        if (
            binding is None
            or binding.memory_context is None
            or task is None
            or control is None
        ):
            raise PermissionError("MEMORY_SEND_LEASE_REQUIRED")
        control.check()
        if task in self._active:
            raise PermissionError("MEMORY_SEND_LEASE_REENTRY")
        async with self.registry.send_lease_execution(
            binding.conversation.tenant_id,
            binding.execution_id,
            self._backend(binding.conversation),
            "provider",
        ) as owner:
            self._active[task] = owner
            try:
                yield owner
            finally:
                self._active.pop(task, None)

    async def issue(self, prepared, operation: ContextOperation) -> MemorySendPermit:
        task, binding, control = (
            asyncio.current_task(),
            current_run_context(),
            current_run_control(),
        )
        if (
            task is None
            or task not in self._active
            or binding is None
            or binding.memory_context is None
            or control is None
        ):
            raise PermissionError("MEMORY_SEND_LEASE_REQUIRED")
        control.check()
        manifest = prepared.manifest
        record = await self.execution_store.get(
            binding.conversation.tenant_id, binding.execution_id
        )
        if (
            record is None
            or record.state != "ACTIVE"
            or record.context != binding.memory_context
            or record.deadline_epoch_seconds != binding.deadline_epoch_seconds
            or (
                manifest.scope.conversation,
                manifest.scope.task_id,
                manifest.scope.execution_id,
            )
            != (binding.conversation, binding.task_id, binding.execution_id)
            or (manifest.operation_id, manifest.attempt)
            != (operation.operation_id, operation.attempt)
            or not memory_operation_deadline_matches(
                manifest.node_id,
                operation.deadline_epoch_seconds,
                binding.deadline_epoch_seconds,
            )
        ):
            raise PermissionError("MEMORY_SEND_PERMIT_BINDING_INVALID")
        stage = current_model_stage()
        derive = manifest.node_id == "memory.derive"
        if derive and (
            stage is None
            or stage.node_id != "memory.derive"
            or stage.stage_id
            != json.loads(binding.memory_context.derive_template_json or "{}").get(
                "operation_id"
            )
            or (manifest.prompt_version, manifest.output_schema_version)
            not in {
                ("derive-prompt/2", "derive-schema/2"),
                ("derive-prompt/3", "derive-schema/3"),
            }
        ):
            raise PermissionError("DERIVE_ORIGINAL_FRAME_REQUIRED")
        packet = record.context.packet
        permit = MemorySendPermit(
            manifest.scope,
            record.runtime_id,
            operation.operation_id,
            operation.attempt,
            manifest.canonical_request_hmac,
            manifest.manifest_id,
            packet.packet_id,
            packet.packet_revision,
            record.context.packet_digest,
            record.execution_revision,
            operation.deadline_epoch_seconds,
            "send-permit-" + uuid4().hex,
        )
        self._issued[permit.permit_ref] = _IssuedSend(
            permit, ref(task), ref(control), derive
        )
        return permit

    def is_derive_permit(self, permit):
        issued = self._issued.get(getattr(permit, "permit_ref", ""))
        return issued is not None and issued.permit is permit and issued.derive is True

    def response_received(self, permit: MemorySendPermit, *, complete: bool) -> None:
        issued = self._issued.get(getattr(permit, "permit_ref", ""))
        if (
            issued is None
            or issued.permit is not permit
            or issued.task() is not asyncio.current_task()
        ):
            raise PermissionError("MEMORY_SEND_PERMIT_INVALID")
        issued.complete = complete is True

    def validate_issued(self, permit: MemorySendPermit) -> bool:
        if not isinstance(permit, MemorySendPermit):
            return False
        issued = self._issued.get(permit.permit_ref)
        if (
            issued is None
            or issued.permit is not permit
            or not issued.complete
            or (
                issued.task() is not asyncio.current_task()
                and self._checkpoint_permit.get() is not permit
            )
        ):
            return False
        control = issued.control()
        if control is None or control is not current_run_control():
            return False
        if issued.task() is not asyncio.current_task() and not self._live_graph(
            issued, permit
        ):
            return False
        try:
            control.check()
        except PaidBudgetError:
            return False
        binding = current_run_context()
        return (
            binding is not None
            and (
                binding.conversation,
                binding.task_id,
                binding.execution_id,
            )
            == (
                permit.scope.conversation,
                permit.scope.task_id,
                permit.scope.execution_id,
            )
            and memory_operation_deadline_matches(
                "memory.derive" if issued.derive else "direct",
                permit.deadline_epoch_seconds,
                binding.deadline_epoch_seconds,
            )
        )

    def result_captured(self, permit: MemorySendPermit, result_ref: str) -> None:
        if (
            not self.validate_issued(permit)
            or type(result_ref) is not str
            or not result_ref
        ):
            raise PermissionError("MEMORY_RESULT_UNAVAILABLE")
        issued = self._issued[permit.permit_ref]
        if issued.result_ref is not None and issued.result_ref != result_ref:
            raise PermissionError("MEMORY_RESULT_UNAVAILABLE")
        issued.result_ref = result_ref
        frame = self._graph.get()
        if (
            frame is not None
            and frame.runtime_id == permit.runtime_id
            and frame.control() is issued.control()
            and permit.scope.subtask_id == "direct"
        ):
            frame.captured = (permit, result_ref)

    def _live_graph(self, issued, permit) -> bool:
        frame = self._graph.get()
        if frame is None or not frame.active:
            return False
        task, control = frame.task(), frame.control()
        return (
            task is not None
            and not task.done()
            and control is not None
            and control is issued.control()
            and control is current_run_control()
            and frame.runtime_id == permit.runtime_id
        )

    def validate_captured(self, permit: MemorySendPermit, result_ref: str) -> bool:
        if self.validate_issued(permit):
            return self._issued[permit.permit_ref].result_ref == result_ref
        if not isinstance(permit, MemorySendPermit):
            return False
        issued, frame = self._issued.get(permit.permit_ref), self._graph.get()
        if (
            issued is None
            or issued.permit is not permit
            or not issued.complete
            or issued.result_ref != result_ref
            or frame is None
            or not frame.active
        ):
            return False
        if not self._live_graph(issued, permit):
            return False
        control = frame.control()
        if control is None:
            return False
        try:
            control.check()
        except PaidBudgetError:
            return False
        return True

    def captured_for_run(self, runtime_id: str):
        frame = self._graph.get()
        if frame is None or frame.runtime_id != runtime_id or frame.captured is None:
            return None
        return frame.captured if self.validate_captured(*frame.captured) else None

    def result_publish_guard(self, permit: MemorySendPermit, result_ref: str):
        if (
            self._checkpoint_permit.get() is not permit
            or self._checkpoint_result_ref.get() != result_ref
            or not self.validate_captured(permit, result_ref)
        ):
            raise ResultPublishDenied("MEMORY_RESULT_PUBLISH_DENIED")
        return _CurrentResultPublisher(self, permit, result_ref)

    async def check_current_result(
        self, permit: MemorySendPermit, result_ref: str, run_id: str
    ) -> None:
        try:
            if (
                run_id != permit.runtime_id
                or self._checkpoint_permit.get() is not permit
                or self._checkpoint_result_ref.get() != result_ref
                or not self.validate_captured(permit, result_ref)
            ):
                raise ResultPublishDenied("MEMORY_RESULT_PUBLISH_DENIED")
            await self.registry.revalidate_result_checkpoint(permit, result_ref)
            control = current_run_control()
            if control is None:
                raise ResultPublishDenied("MEMORY_RESULT_PUBLISH_DENIED")
            control.check()
        except ResultPublishDenied:
            raise
        except Exception:  # noqa: BLE001 -- 当前技术权威不可用统一拒绝正文，不外泄驱动异常。
            raise ResultPublishDenied("MEMORY_RESULT_PUBLISH_DENIED") from None

    @asynccontextmanager
    async def checkpoint_scope(
        self,
        permit: MemorySendPermit,
        result_ref: str,
        backend_id: str,
        namespace: str,
        *,
        pending_writes: bool = False,
    ):
        if not self.validate_captured(permit, result_ref):
            raise PermissionError("MEMORY_RESULT_UNAVAILABLE")
        token = self._checkpoint_permit.set(permit)
        result_token = self._checkpoint_result_ref.set(result_ref)
        try:
            async with (
                self.registry.result_checkpoint_scope(
                    permit.scope.conversation.tenant_id,
                    permit.scope.execution_id,
                    backend_id,
                    namespace,
                    permit,
                    result_ref,
                ),
                self.registry.guard(
                    permit.runtime_id,
                    backend_id,
                    namespace,
                    pending_writes=pending_writes,
                ) as owner,
            ):
                yield owner
        finally:
            self._checkpoint_result_ref.reset(result_token)
            self._checkpoint_permit.reset(token)

    @asynccontextmanager
    async def result_scope(self, permit: MemorySendPermit):
        if not self.validate_issued(permit):
            raise PermissionError("MEMORY_SEND_PERMIT_INVALID")
        task = asyncio.current_task()
        if task in self._active or task in self._results:
            raise PermissionError("MEMORY_RESULT_LEASE_REENTRY")
        async with self.registry.result_lease_execution(
            permit.scope.conversation.tenant_id,
            permit.scope.execution_id,
            self._backend(permit.scope.conversation),
            "provider",
            permit,
        ):
            self._results[task] = permit
            try:
                yield
            finally:
                self._results.pop(task, None)

    async def validate(self, permit: MemorySendPermit) -> bool:
        if not self.validate_issued(permit):
            return False
        if self._results.get(asyncio.current_task()) is permit:
            return True
        try:
            async with self.result_scope(permit):
                return True
        except PermissionError:
            return False


class _StoredAuthority:
    def __init__(
        self, record: MemoryExecutionRecord, authorization: MemoryExecutionAuthorization
    ):
        self.record = record
        self.authorization = authorization

    def current(
        self, authorization: MemoryExecutionAuthorization
    ) -> MemoryPacketBinding | None:
        record, packet = self.record, self.record.context.packet
        if authorization != self.authorization or record.state != "ACTIVE":
            return None
        return MemoryPacketBinding(
            packet.packet_id,
            packet.packet_revision,
            record.execution_revision,
            record.grant_epoch,
            record.source_epoch,
            record.deletion_epoch,
            record.context.packet_digest,
            packet.safety_dependencies,
        )


class StoredMemoryPacketValidator:
    def __init__(self, store: MemoryExecutionStore):
        self.store = store

    async def validator(self, scope: ExecutionScope) -> AuthorizedMemoryPacketValidator:
        binding = current_run_context()
        if binding is None or binding.memory_context is None:
            raise ValueError("MEMORY_RUN_BINDING_REQUIRED")
        record = await self.store.get(scope.conversation.tenant_id, scope.execution_id)
        if (
            record is None
            or record.context != binding.memory_context
            or record.deadline_epoch_seconds != binding.deadline_epoch_seconds
        ):
            raise ValueError("MEMORY_ACCESS_REVOKED")
        stage = current_model_stage()
        node_id = stage.node_id if stage is not None else scope.subtask_id
        if not any(
            (grant.node_id, grant.execution_agent_id, grant.purpose)
            == (node_id, scope.execution_agent_id, scope.purpose)
            for grant in record.context.execution_grants
        ):
            raise ValueError("MEMORY_EXECUTION_GRANT_DENIED")
        context, packet = record.context, record.context.packet
        authorization = MemoryExecutionAuthorization(
            scope,
            context.policy,
            packet.semantic_input_hash,
            packet.parent_authorization_ref,
            record.deadline_epoch_seconds,
            context.semantic_snapshot_digest,
        )
        return AuthorizedMemoryPacketValidator(
            authorization, _StoredAuthority(record, authorization)
        )

    async def validate(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket | None,
        dependencies: tuple[SourceDependency, ...],
        operation: ContextOperation,
    ) -> None:
        validator = await self.validator(scope)
        await validator.validate(scope, packet, dependencies, operation)
