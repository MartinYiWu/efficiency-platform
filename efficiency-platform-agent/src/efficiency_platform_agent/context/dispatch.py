"""在最终 Provider 请求和付费预留之后执行持久上下文门禁。"""

import hmac
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import asdict, dataclass, replace
from typing import Protocol

from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.core.context_control import PreparedContext
from efficiency_platform_agent.core.context_dispatch import (
    bind_context_send_guard,
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
from efficiency_platform_agent.core.ports import ModelProvider, StreamingModelProvider
from efficiency_platform_agent.core.run import (
    ProviderRequest,
    ProviderResult,
    ProviderStreamChunk,
)
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

    async def finalize(self) -> None:
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

    async def finish(self, succeeded: bool) -> None:
        if self.sent and not await self.dispatch.store.record_receipt(
            self.prepared.manifest, "SUCCEEDED" if succeeded else "UNKNOWN"
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
        if stage_store is not None and (
            not isinstance(hmac_key, bytes) or len(hmac_key) < 32
        ):
            raise ValueError("CONTEXT_STAGE_HMAC_KEY_REQUIRED")
        self._key = hmac_key

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
        send = _Send(
            self, plan, prepared, stage_id=stage.stage_id if stage else None, slot=slot
        )
        if stage is not None and slot is not None:
            stage.allow_repair = send.allow_repair
            stage.complete = send.complete
        return send


class ControlledModelProvider:
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
        send = await self.dispatch.prepare(request, self.provider_id, self.model)
        succeeded = False
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
            await send.finish(succeeded)


class ControlledStreamingModelProvider(ControlledModelProvider):
    async def stream(
        self, request: ProviderRequest
    ) -> AsyncIterator[ProviderStreamChunk]:
        if not isinstance(self.inner, StreamingModelProvider):
            raise TypeError("CONTEXT_STREAM_PROVIDER_REQUIRED")
        send = await self.dispatch.prepare(request, self.provider_id, self.model)
        finished = False
        failed = False
        exhausted = False
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
                        yield chunk
                    exhausted = True
                finally:
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        await close()
            if not send.sent:
                raise ValueError("CONTEXT_TRANSPORT_GATE_REQUIRED")
        finally:
            await send.finish(exhausted and finished and not failed)
