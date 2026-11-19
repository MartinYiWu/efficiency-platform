"""在最终 Provider 请求和付费预留之后执行持久上下文门禁。"""

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol

from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.core.context_control import PreparedContext
from efficiency_platform_agent.core.context_dispatch import (
    bind_context_send_guard,
    current_context_send_lease,
    current_model_stage,
)
from efficiency_platform_agent.core.context_ports import (
    ContextManifestStore,
    ContextMetadata,
    ContextOperation,
)
from efficiency_platform_agent.core.context_stage import ContextStageStore, StageSlot
from efficiency_platform_agent.core.execution_control import current_run_control
from efficiency_platform_agent.core.memory import ExecutionScope, MemoryContextPacket
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionStore,
    current_memory_result_checkpoint_permit,
    current_memory_wait_checkpoint_capability,
)
from efficiency_platform_agent.core.memory_lineage import record_specialist_manifest
from efficiency_platform_agent.core.memory_refresh import WaitPhase
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.core.ports import ModelProvider, StreamingModelProvider
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderStreamChunk,
    ProviderToolCall,
    ProviderUsage,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
    current_run_context,
)
from efficiency_platform_agent.core.task_authorization import TaskPaidBinding
from efficiency_platform_agent.memory.context_refresh import validate_refresh_context
from efficiency_platform_agent.providers.llm.deepseek import (
    _json_value,
    _serialize_message,
)


@dataclass(frozen=True, slots=True)
class DispatchPlan:
    scope: ExecutionScope
    policy: ContextPolicy
    pieces: tuple[ContextPiece, ...]
    metadata: ContextMetadata
    operation: ContextOperation
    packet: MemoryContextPacket | None = None
    request: ProviderRequest | None = None


class DispatchAuthority(Protocol):
    async def resolve(
        self, request: ProviderRequest, provider_id: str, model: str
    ) -> DispatchPlan: ...


class _Send:
    def __init__(
        self,
        dispatch: "ContextDispatch",
        plan: DispatchPlan,
        prepared: PreparedContext,
        *,
        stage_id: str | None = None,
        slot: StageSlot | None = None,
    ):
        self.dispatch = dispatch
        self.plan = plan
        self.prepared = prepared
        self.sent = False
        self.stage_id = stage_id
        self.slot = slot
        self.returned = False
        self._lease = AsyncExitStack()
        self._lease_acquired = False
        self._lease_authority: Any = None
        self.send_permit = None
        self.result_ref = None
        self._transport_complete: bool | None = None
        self._reservation = None
        self._ledger = None
        self._waiting = False
        self._task = asyncio.current_task()
        self._control = current_run_control()
        self._binding = current_run_context()
        self._wait_event_id = None
        self._wait_binding: RunContextBinding | None = None

    async def finalize(self) -> None:
        if (
            current_memory_wait_checkpoint_capability() is not None
            or current_memory_result_checkpoint_permit() is not None
        ):
            raise PermissionError("MEMORY_CPU_CHECKPOINT_SEND_FORBIDDEN")
        while True:
            try:
                with bind_run_context(self._binding):
                    await self._finalize_once()
                return
            except (ValueError, PermissionError) as error:
                if (
                    str(error)
                    not in {
                        "MEMORY_PACKET_EXPIRED",
                        "CONTEXT_PACKET_EXPIRED",
                        "MEMORY_REFRESH_PENDING",
                    }
                    or self.sent
                ):
                    raise
                await self.after_transport_close()
                await self._wait_for_refresh(
                    create_wait=str(error) != "MEMORY_REFRESH_PENDING"
                )

    async def _finalize_once(self) -> None:
        if not self._lease_acquired:
            lease = current_context_send_lease()
            if lease is not None:
                await self._lease.enter_async_context(lease.acquire())
                self._lease_acquired = True
                self._lease_authority = lease
                if self.plan.packet is not None and not callable(
                    getattr(lease, "issue", None)
                ):
                    raise PermissionError("MEMORY_SEND_AUTHORITY_REQUIRED")
        plan = self.plan
        self.prepared = await self.dispatch.controller.finalize(
            self.prepared,
            plan.scope,
            plan.metadata.capacity,
            plan.metadata.limits,
            plan.metadata,
            operation=plan.operation,
            packet=plan.packet,
        )
        self.sent = True
        self.check_live()
        issue = getattr(self._lease_authority, "issue", None)
        if issue is not None:
            self.send_permit = await issue(self.prepared, plan.operation)

    async def after_transport_close(self, *, complete: bool | None = None) -> None:
        if complete is not None:
            self._transport_complete = complete
        await self._lease.aclose()
        self._lease_acquired = False

    def bind_reservation(self, reservation, ledger) -> None:
        if self._reservation is not None:
            raise PermissionError("MEMORY_RESERVATION_FRAME_CHANGED")
        self._reservation, self._ledger = reservation, ledger

    def before_reservation(self) -> None:
        if self.sent or (
            self.dispatch.refresh_service is not None and self._reservation is not None
        ):
            if self._control is not None:
                self._control.stop("CONTEXT_OPERATION_BLOCKED")
            raise ValueError("CONTEXT_OPERATION_BLOCKED")

    def task_authorization_binding(self) -> TaskPaidBinding:
        request = asdict(self.prepared.request)
        request.pop("timeout_ms")
        metadata = asdict(self.plan.metadata)
        metadata.pop("ctx_revision")
        # 授权包、run和截止属于外壳；逻辑操作内容及版本跨执行保持一致。
        digest = self.dispatch.controller._digest(
            self.plan.scope,
            {
                "request": request,
                "metadata": metadata,
                "purpose": self.plan.scope.purpose,
                "execution_agent_id": self.plan.scope.execution_agent_id,
                "packet_input": self.plan.packet.semantic_input_hash
                if self.plan.packet is not None
                else None,
                "dependencies": [
                    (d.source_type, d.source_id, d.source_version)
                    for d in self.prepared.manifest.safety_dependencies
                ],
            },
        )
        return TaskPaidBinding(
            self.plan.scope,
            self.plan.operation.operation_id,
            digest,
        )

    def _check_reservation(self) -> None:
        if self._reservation is not None:
            self._ledger.check_live(self._reservation.reservation_id)
            if time.time() * 1000 >= self._reservation.deadline_epoch_ms:
                raise ValueError("PAID_BUDGET_DEADLINE")

    async def _wait_for_refresh(self, *, create_wait: bool) -> None:
        service, store = (
            self.dispatch.refresh_service,
            self.dispatch.memory_execution_store,
        )
        if (
            service is None
            or store is None
            or self._binding is None
            or self.plan.packet is None
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        self.check_live()
        self._check_reservation()
        phase = (
            WaitPhase.RESERVED if self._reservation is not None else WaitPhase.PREPARED
        )
        record = await store.get(
            self.plan.scope.conversation.tenant_id, self.plan.scope.execution_id
        )
        if record is None or record.context != self._binding.memory_context:
            raise PermissionError("MEMORY_RUN_BINDING_REQUIRED")
        self._waiting = True
        self._wait_binding = self._binding
        self.dispatch._waiting_frames[id(self)] = self
        try:
            if create_wait:
                self._wait_event_id = await service.begin_wait_intent(
                    self.plan.scope,
                    record.runtime_id,
                    self.plan.operation.operation_id,
                    self.plan.operation.attempt,
                    phase,
                    canonical_request_hmac=self.prepared.manifest.canonical_request_hmac,
                    stage_id=self.stage_id,
                    stage_slot=self.slot.slot if self.slot else None,
                )
                ready = self.dispatch._wait_checkpoint_callback
                if ready is None or await ready(self, self._wait_event_id) is not True:
                    await service.finish_wait(
                        self.plan.scope.conversation,
                        self.plan.scope.execution_id,
                        self._wait_event_id,
                    )
                if self.dispatch._on_wait is not None:
                    await self.dispatch._on_wait(
                        self._wait_event_id,
                        self.plan.scope.execution_id,
                        record.runtime_id,
                    )
            elif self._wait_event_id is None:
                raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
            while True:
                self.check_live()
                self._check_reservation()
                await service.get_wait(
                    self.plan.scope.conversation,
                    self.plan.scope.execution_id,
                    wait_event_id=self._wait_event_id,
                )
                current = await store.get(
                    self.plan.scope.conversation.tenant_id, self.plan.scope.execution_id
                )
                if (
                    current is None
                    or current.state != "ACTIVE"
                    or current.runtime_id != record.runtime_id
                ):
                    raise PermissionError("MEMORY_ACCESS_REVOKED")
                if current.context != record.context:
                    outcome = getattr(
                        service, "get_wait_outcome", service.get_wait_receipt
                    )
                    receipt = await outcome(
                        self.plan.scope.conversation,
                        self.plan.scope.execution_id,
                        self._wait_event_id,
                    )
                    if receipt is None:
                        await asyncio.sleep(0.025)
                        continue
                    if receipt.candidate_phase == "APPLIED_EXPIRED":
                        await self._align_successor(record, current, receipt, phase)
                        record = current
                        continue
                    if receipt.dispatch_allowed is not True:
                        if self._control is not None:
                            self._control.stop("CONTINUATION_AUTH_UNSUPPORTED")
                        raise PermissionError("CONTINUATION_AUTH_UNSUPPORTED")
                    fingerprint = hashlib.sha256(
                        json.dumps(
                            current.context.metadata(),
                            sort_keys=True,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    if (
                        receipt.code != "CONTEXT_REFRESHED"
                        or receipt.candidate_phase != "ACKED"
                        or receipt.state != "ACTIVE"
                        or receipt.wait_event_id != self._wait_event_id
                        or receipt.packet_revision
                        != current.context.packet.packet_revision
                        or receipt.current_packet_revision
                        != current.context.packet.packet_revision
                        or receipt.execution_revision != record.execution_revision
                        or receipt.current_context_fingerprint != fingerprint
                    ):
                        raise PermissionError("MEMORY_RESUME_CONFLICT")
                    validate_refresh_context(
                        record.context,
                        current.context,
                        self.plan.operation.deadline_epoch_seconds,
                        self.dispatch.controller._clock(),
                    )
                    self.plan = replace(self.plan, packet=current.context.packet)
                    self._binding = replace(
                        self._binding, memory_context=current.context
                    )
                    return
                await asyncio.sleep(0.025)
        finally:
            self._waiting = False
            self.dispatch._waiting_frames.pop(id(self), None)

    async def _align_successor(self, previous, current, receipt, phase) -> None:
        if self._binding is None:
            raise PermissionError("MEMORY_RUN_BINDING_REQUIRED")
        fingerprint = hashlib.sha256(
            json.dumps(
                current.context.metadata(),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if (
            receipt.code != "MEMORY_REFRESH_PACKET_EXPIRED"
            or receipt.state != "WAITING_CONTEXT"
            or receipt.dispatch_allowed
            or receipt.wait_event_id != self._wait_event_id
            or not receipt.next_wait_event_id
            or receipt.next_wait_event_id == self._wait_event_id
            or receipt.current_packet_revision != current.context.packet.packet_revision
            or receipt.packet_revision != current.context.packet.packet_revision
            or receipt.execution_revision != previous.execution_revision
            or receipt.current_context_fingerprint != fingerprint
            or receipt.refresh_count >= 3
        ):
            raise PermissionError("MEMORY_RESUME_CONFLICT")
        validate_refresh_context(
            previous.context,
            current.context,
            self.plan.operation.deadline_epoch_seconds,
            self.dispatch.controller._clock(),
        )
        wait = await self.dispatch.refresh_service.get_wait(
            self.plan.scope.conversation,
            self.plan.scope.execution_id,
            wait_event_id=receipt.next_wait_event_id,
        )
        if wait is None or (
            wait.wait_event_id,
            wait.scope,
            wait.task_id,
            wait.execution_id,
            wait.runtime_id,
            wait.expected_packet_revision,
            wait.expected_execution_revision,
            wait.expected_current_context_fingerprint,
            wait.logical_operation_id,
            wait.canonical_request_hmac,
            wait.attempt,
            wait.stage_id,
            wait.stage_slot,
            wait.wait_phase,
            wait.original_deadline,
        ) != (
            receipt.next_wait_event_id,
            self.plan.scope.conversation,
            self.plan.scope.task_id,
            self.plan.scope.execution_id,
            previous.runtime_id,
            current.context.packet.packet_revision,
            current.execution_revision,
            fingerprint,
            self.plan.operation.operation_id,
            self.prepared.manifest.canonical_request_hmac,
            self.plan.operation.attempt,
            self.stage_id,
            self.slot.slot if self.slot else None,
            phase,
            self.plan.operation.deadline_epoch_seconds,
        ):
            raise PermissionError("MEMORY_RESUME_CONFLICT")
        self._binding = replace(self._binding, memory_context=current.context)
        self._wait_binding = self._binding
        self.plan = replace(self.plan, packet=current.context.packet)
        self._wait_event_id = wait.wait_event_id
        if self.dispatch._on_wait is not None:
            await self.dispatch._on_wait(
                wait.wait_event_id, self.plan.scope.execution_id, previous.runtime_id
            )

    def check_live(self) -> None:
        self.dispatch.controller.check_deadline(self.plan.operation)
        control = current_run_control()
        if control is not None:
            control.check()

    async def before_send(self, payload: Mapping[str, object]) -> None:
        request = self.prepared.request
        options = _json_value(request.options)
        for key in ("logical_model", "json_schema", "model", "timeout"):
            options.pop(key, None)
        actual = dict(payload)
        if actual.get("stream") is True:
            actual.pop("stream")
            if actual.pop("stream_options", None) != {"include_usage": True}:
                raise ValueError("CONTEXT_WIRE_REQUEST_CHANGED")
        matches = any(
            actual
            == {
                **options,
                "model": self.plan.metadata.capacity.model,
                "messages": [
                    _serialize_message(message, supports_developer_role=role)
                    for message in request.messages
                ],
            }
            for role in (True, False)
        )
        if not matches:
            raise ValueError("CONTEXT_WIRE_REQUEST_CHANGED")
        await self.finalize()

    async def finish(
        self, succeeded: bool, result: ProviderResult | None = None
    ) -> None:
        captured = False
        if self.sent and self.send_permit is not None and succeeded:
            await self.after_transport_close()
            self._lease_authority.response_received(
                self.send_permit,
                complete=result is not None and self._transport_complete is not False,
            )
            try:
                async with self._lease_authority.result_scope(self.send_permit):
                    self.result_ref = await self.dispatch.store.capture_result_once(
                        self.prepared.manifest,
                        self.plan.operation,
                        self.send_permit,
                        result,
                    )
                    capture = getattr(self._lease_authority, "result_captured", None)
                    if capture is not None:
                        capture(self.send_permit, self.result_ref)
                captured = True
            except BaseException:
                await self.dispatch.store.record_receipt(
                    self.prepared.manifest, "UNKNOWN"
                )
                control = current_run_control()
                if control is not None:
                    control.stop("MEMORY_RESULT_UNAVAILABLE")
                raise
        if (
            self.sent
            and not captured
            and not await self.dispatch.store.record_receipt(
                self.prepared.manifest, "SUCCEEDED" if succeeded else "UNKNOWN"
            )
        ):
            raise ValueError("CONTEXT_RECEIPT_WRITE_FAILED")
        if (
            self.sent
            and self.dispatch.stage_store is not None
            and self.slot is not None
        ):
            assert self.stage_id is not None
            if not await self.dispatch.stage_store.transition(
                self.plan.scope,
                self.stage_id,
                self.slot.slot,
                "CLAIMED",
                "RETURNED" if succeeded else "UNKNOWN",
            ):
                raise ValueError("CONTEXT_STAGE_WRITE_FAILED")
            self.returned = succeeded
        if self.sent:
            record_specialist_manifest(self.prepared.manifest)

    async def allow_repair(self) -> None:
        if not self.returned or self.slot is None or self.dispatch.stage_store is None:
            raise ValueError("CONTEXT_STAGE_REPAIR_FORBIDDEN")
        assert self.stage_id is not None
        if not await self.dispatch.stage_store.transition(
            self.plan.scope, self.stage_id, self.slot.slot, "RETURNED", "INVALID"
        ):
            raise ValueError("CONTEXT_STAGE_REPAIR_FORBIDDEN")

    async def complete(self) -> None:
        if not self.returned or self.slot is None or self.dispatch.stage_store is None:
            raise ValueError("CONTEXT_STAGE_COMPLETION_FORBIDDEN")
        assert self.stage_id is not None
        if not await self.dispatch.stage_store.transition(
            self.plan.scope, self.stage_id, self.slot.slot, "RETURNED", "SUCCEEDED"
        ):
            raise ValueError("CONTEXT_STAGE_COMPLETION_FORBIDDEN")


class ContextDispatch:
    def __init__(
        self,
        controller: ContextController,
        store: ContextManifestStore,
        authority: DispatchAuthority,
        *,
        stage_store: ContextStageStore | None = None,
        hmac_key: bytes | None = None,
    ):
        self.controller = controller
        self.store = store
        self.authority = authority
        self.stage_store = stage_store
        self.refresh_service: Any = None
        self.memory_execution_store: MemoryExecutionStore | None = None
        self._waiting_frames: dict[int, _Send] = {}
        self._on_wait = None
        self.derive_coordinator: Any | None = None
        self._wait_checkpoint_callback = None
        if stage_store is not None and (
            not isinstance(hmac_key, bytes) or len(hmac_key) < 32
        ):
            raise ValueError("CONTEXT_STAGE_HMAC_KEY_REQUIRED")
        self._key = hmac_key

    def install_refresh(self, service, memory_execution_store, *, on_wait=None) -> None:
        if self.refresh_service is not None:
            raise ValueError("MEMORY_REFRESH_ALREADY_BOUND")
        self.refresh_service, self.memory_execution_store = (
            service,
            memory_execution_store,
        )
        self._on_wait = on_wait
        self.controller.install_manifest_authorization_validator(
            service.validate_manifest_authorization
        )

    def install_wait_checkpoint_callback(self, callback) -> None:
        if self._wait_checkpoint_callback is not None or not callable(callback):
            raise ValueError("MEMORY_WAIT_CHECKPOINT_ALREADY_BOUND")
        self._wait_checkpoint_callback = callback

    async def verify_wait_frame(self, wait, runtime_id: str) -> bool:
        if self.memory_execution_store is None:
            return False
        for frame in tuple(self._waiting_frames.values()):
            binding = frame._wait_binding
            if (
                not frame._waiting
                or frame.sent
                or frame._task is None
                or frame._task.done()
                or frame._control is None
                or binding is None
            ):
                continue
            try:
                frame._control.check()
                frame._check_reservation()
                frame.check_live()
            except (ValueError, PaidBudgetError):
                continue
            manifest = frame.prepared.manifest
            record = await self.memory_execution_store.get(
                wait.scope.tenant_id, wait.execution_id
            )
            packet = (
                binding.memory_context.packet
                if binding.memory_context is not None
                else None
            )
            if (
                record is not None
                and packet is not None
                and (
                    record.runtime_id,
                    binding.conversation,
                    binding.task_id,
                    binding.execution_id,
                    manifest.operation_id,
                    manifest.attempt,
                    manifest.canonical_request_hmac,
                    frame.plan.operation.deadline_epoch_seconds,
                    WaitPhase.RESERVED
                    if frame._reservation is not None
                    else WaitPhase.PREPARED,
                    packet.packet_revision,
                    packet.execution_revision,
                    packet.semantic_input_hash,
                    record.request_fingerprint,
                    frame.stage_id,
                    frame.slot.slot if frame.slot else None,
                )
                == (
                    runtime_id,
                    wait.scope,
                    wait.task_id,
                    wait.execution_id,
                    wait.logical_operation_id,
                    wait.attempt,
                    wait.canonical_request_hmac,
                    wait.original_deadline,
                    wait.wait_phase,
                    wait.expected_packet_revision,
                    wait.expected_execution_revision,
                    wait.semantic_input_hash,
                    wait.operation_hash,
                    wait.stage_id,
                    wait.stage_slot,
                )
            ):
                return True
        return False

    async def update_wait_frame_binding(
        self, original_record, refreshed_context
    ) -> bool:
        for frame in tuple(self._waiting_frames.values()):
            binding = frame._wait_binding
            if (
                not frame._waiting
                or frame.sent
                or frame._task is None
                or frame._task.done()
                or binding is None
                or frame._control is None
            ):
                continue
            if (binding.conversation, binding.execution_id, binding.memory_context) != (
                original_record.context.packet.scope,
                original_record.context.packet.execution_id,
                original_record.context,
            ):
                continue
            frame._control.check()
            frame._check_reservation()
            validate_refresh_context(
                original_record.context,
                refreshed_context,
                binding.deadline_epoch_seconds,
                self.controller._clock(),
            )
            frame._binding = replace(binding, memory_context=refreshed_context)
            return True
        return False

    def validate_key(self, key: bytes) -> None:
        if self._key is None or not hmac.compare_digest(self._key, key):
            raise ValueError("CONTEXT_HMAC_KEY_MISMATCH")

    async def prepare(
        self, request: ProviderRequest, provider_id: str, model: str
    ) -> _Send:
        plan = await self.authority.resolve(request, provider_id, model)
        if (plan.metadata.capacity.provider, plan.metadata.capacity.model) != (
            provider_id,
            model,
        ):
            raise ValueError("CONTEXT_PROVIDER_BINDING_MISMATCH")
        stage = current_model_stage()
        slot = None
        if self.stage_store is not None:
            if stage is None or stage.stage_id != plan.operation.operation_id:
                raise ValueError("CONTEXT_STAGE_BINDING_REQUIRED")
            assert self._key is not None
            semantic = hmac.digest(
                self._key,
                json.dumps(
                    {
                        "scope": asdict(plan.scope),
                        "policy_version": plan.metadata.policy_version,
                        "capacity": asdict(plan.metadata.capacity),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                + b"\0"
                + stage.semantic_input,
                "sha256",
            ).hex()
            slot = await self.stage_store.claim(
                plan.scope,
                stage.stage_id,
                semantic,
                plan.operation.deadline_epoch_seconds,
            )
            plan = replace(
                plan,
                operation=replace(
                    plan.operation, operation_id=slot.operation_id, attempt=1
                ),
            )
        prepared = await self.controller.prepare(
            plan.request or request,
            plan.scope,
            plan.policy,
            plan.pieces,
            plan.metadata.capacity,
            plan.metadata.limits,
            plan.metadata,
            plan.packet,
            operation=plan.operation,
        )
        if self.derive_coordinator is not None:
            await self.derive_coordinator.wait_for_derivation(
                plan.scope, plan.operation
            )
        if self.refresh_service is not None:
            receipt = await self.store.get_operation_receipt(
                plan.scope, plan.operation.operation_id
            )
            if receipt is None or receipt.status != "NOT_SENT":
                raise ValueError(
                    "MEMORY_RESULT_UNAVAILABLE"
                    if receipt is not None and receipt.status == "SUCCEEDED"
                    else "CONTEXT_OPERATION_BLOCKED"
                )
        send = _Send(
            self,
            plan,
            prepared,
            stage_id=stage.stage_id if stage and slot else None,
            slot=slot,
        )
        if stage is not None and slot is not None:
            stage.allow_repair = send.allow_repair
            stage.complete = send.complete
        return send


class ControlledModelProvider:
    context_send_lease_boundary = True

    def __init__(
        self,
        inner: ModelProvider,
        dispatch: ContextDispatch,
        provider_id: str,
        model: str,
        *,
        paid_transport: bool,
    ):
        self.inner = inner
        self.dispatch = dispatch
        self.provider_id = provider_id
        self.model = model
        self.paid_transport = paid_transport
        self.descriptor = inner.descriptor

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        with self.dispatch.controller.baseline_scope():
            return await self._complete(request)

    async def _complete(self, request: ProviderRequest) -> ProviderResult:
        send = await self.dispatch.prepare(request, self.provider_id, self.model)
        succeeded = False
        result = None
        try:
            if not self.paid_transport:
                await send.finalize()
            with bind_context_send_guard(send):
                result = await self.inner.complete(send.prepared.request)
            if not send.sent:
                raise ValueError("CONTEXT_TRANSPORT_GATE_REQUIRED")
            succeeded = (
                result.error is None or result.error.code == "PROVIDER_SCHEMA_INVALID"
            )
            return result
        finally:
            try:
                await send.finish(succeeded, result)
            finally:
                await send.after_transport_close()


class ControlledStreamingModelProvider(ControlledModelProvider):
    async def stream(
        self, request: ProviderRequest
    ) -> AsyncIterator[ProviderStreamChunk]:
        with self.dispatch.controller.baseline_scope():
            iterator = self._stream(request)
            try:
                async for chunk in iterator:
                    yield chunk
            finally:
                await iterator.aclose()

    async def _stream(
        self, request: ProviderRequest
    ) -> AsyncGenerator[ProviderStreamChunk]:
        if not isinstance(self.inner, StreamingModelProvider):
            raise TypeError("CONTEXT_STREAM_PROVIDER_REQUIRED")
        send = await self.dispatch.prepare(request, self.provider_id, self.model)
        finished = False
        failed = False
        exhausted = False
        parts = []
        total = ProviderUsage(0, 0, 0, 0, 0)
        tool_calls: tuple[ProviderToolCall, ...] = ()
        try:
            if not self.paid_transport:
                await send.finalize()
            with bind_context_send_guard(send):
                iterator = self.inner.stream(send.prepared.request)
                try:
                    async for chunk in iterator:
                        if not send.sent:
                            raise ValueError("CONTEXT_TRANSPORT_GATE_REQUIRED")
                        failed = failed or chunk.error is not None
                        finished = finished or chunk.finish_reason is not None
                        parts.append(chunk.delta)
                        total = ProviderUsage(
                            max(total.input_tokens, chunk.usage.input_tokens),
                            max(total.output_tokens, chunk.usage.output_tokens),
                            max(total.cached_tokens, chunk.usage.cached_tokens),
                            max(total.reasoning_tokens, chunk.usage.reasoning_tokens),
                            max(total.cost_microunits, chunk.usage.cost_microunits),
                        )
                        if chunk.tool_calls:
                            tool_calls = chunk.tool_calls
                        yield chunk
                    exhausted = True
                finally:
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        await close()
            if not send.sent:
                raise ValueError("CONTEXT_TRANSPORT_GATE_REQUIRED")
        finally:
            try:
                result = (
                    ProviderResult(
                        send.prepared.request.contract_version,
                        ProviderMessage(
                            "assistant", "".join(parts), tool_calls=tool_calls
                        ),
                        total,
                    )
                    if exhausted and finished and not failed
                    else None
                )
                await send.finish(result is not None, result)
            finally:
                await send.after_transport_close()
