"""持久恢复门禁及最后Provider边界；不创建第二执行框架。"""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

from efficiency_platform_agent.core.budget import BudgetCharge, BudgetState
from efficiency_platform_agent.core.context_dispatch import (
    bind_context_send_lease,
    bind_result_publish_guard,
    require_result_publish_guard,
)
from efficiency_platform_agent.core.execution_control import current_run_control
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import (
    current_memory_result_checkpoint_permit,
    current_memory_wait_checkpoint_capability,
)
from efficiency_platform_agent.core.memory_refresh import WaitPhase
from efficiency_platform_agent.core.memory_thread import (
    MemoryThreadRegistry,
    ResumeRequest,
)
from efficiency_platform_agent.core.ports import StreamingModelProvider
from efficiency_platform_agent.core.run_context_binding import (
    bind_run_context,
    current_run_context,
)
from efficiency_platform_agent.memory.context_refresh import validate_refresh_context


class MemoryContextGate:
    def __init__(self, registry: MemoryThreadRegistry):
        self.registry = registry

    async def before_load(self, runtime_id: str, tenant_id: str):
        await self.registry.check_runtime(runtime_id, tenant_id)

    async def resume(self, runtime_id: str, tenant_id: str, request: ResumeRequest):
        return await self.registry.resume(runtime_id, tenant_id, request)


@dataclass(slots=True)
class _DirectMemoryFrame:
    program: Any
    initial: dict
    config: dict
    binding: Any
    scope: ExecutionScope
    runtime_id: str
    task: Any
    control: Any
    submission: dict | None = None
    result: dict | None = None
    wait_id: str | None = None
    wait_capability: Any = None
    resume_capability: Any = None
    checkpoint_id: str | None = None
    active: bool = True
    authorized_context: Any = None
    publish_checked: bool = False
    transport_wait: Any = None


class MemoryDirectContextGate:
    """只接原活Direct帧；等待和结果检查点不能成为再次Dispatch的入口。"""

    defer_publication = True

    def __init__(
        self,
        service,
        execution_store,
        registry,
        send_authority,
        *,
        saver=None,
        checkpoint_store=None,
        dispatch=None,
        on_wait=None,
    ):
        self.service, self.execution_store, self.registry, self.send_authority = (
            service,
            execution_store,
            registry,
            send_authority,
        )
        self.saver, self.checkpoint_store, self.dispatch, self.on_wait = (
            saver,
            checkpoint_store,
            dispatch,
            on_wait,
        )
        self._current: ContextVar[_DirectMemoryFrame | None] = ContextVar(
            "direct_memory_frame", default=None
        )
        self._frames: dict[str, _DirectMemoryFrame] = {}
        if dispatch is not None:
            dispatch.install_wait_checkpoint_callback(self.ready_reserved_wait)

    def _frame(self):
        frame = self._current.get()
        if (
            frame is None
            or not frame.active
            or frame.task.done()
            or frame.control is not current_run_control()
        ):
            raise PermissionError("MEMORY_GRAPH_FRAME_REQUIRED")
        frame.control.check()
        return frame

    def has_frame(self) -> bool:
        frame = self._current.get()
        return (
            frame is not None
            and frame.active
            and not frame.task.done()
            and frame.control is current_run_control()
        )

    @asynccontextmanager
    async def run_scope(self, program, initial_state, config):
        binding, control, task = (
            current_run_context(),
            current_run_control(),
            asyncio.current_task(),
        )
        if (
            binding is None
            or binding.memory_context is None
            or control is None
            or task is None
        ):
            raise PermissionError("MEMORY_GRAPH_FRAME_REQUIRED")
        record = await self.execution_store.get(
            binding.conversation.tenant_id, binding.execution_id
        )
        runtime_id = str(initial_state.get("run_id", ""))
        if (
            record is None
            or record.context != binding.memory_context
            or record.runtime_id != runtime_id
            or record.state != "ACTIVE"
            or runtime_id in self._frames
        ):
            raise PermissionError("MEMORY_GRAPH_FRAME_REQUIRED")
        grant = next(
            (
                item
                for item in record.context.execution_grants
                if item.node_id == "direct"
            ),
            None,
        )
        if grant is None:
            raise PermissionError("MEMORY_EXECUTION_GRANT_DENIED")
        scope = ExecutionScope(
            binding.conversation,
            binding.task_id,
            binding.execution_id,
            grant.node_id,
            grant.purpose,
            grant.execution_agent_id,
        )
        frame = _DirectMemoryFrame(
            program,
            deepcopy(dict(initial_state)),
            deepcopy(dict(config)),
            binding,
            scope,
            runtime_id,
            task,
            control,
        )
        self._frames[runtime_id] = frame
        token = self._current.set(frame)
        try:
            with require_result_publish_guard():
                async with self.send_authority.graph_scope(runtime_id):
                    await self._check(frame)
                    yield frame
        finally:
            frame.active = False
            self._current.reset(token)
            self._frames.pop(runtime_id, None)

    async def _check(self, frame):
        try:
            async with self.registry.send_lease_execution(
                frame.scope.conversation.tenant_id,
                frame.scope.execution_id,
                "official",
                "provider",
            ):
                pass
        except PermissionError as error:
            if str(error) != "MEMORY_PACKET_EXPIRED":
                raise
            await self._begin_wait(frame)

    @asynccontextmanager
    async def invoke_scope(self):
        frame = self._frame()
        if frame.wait_capability is None:
            yield
        else:
            async with self.registry.wait_checkpoint_scope(frame.wait_capability):
                yield

    async def _begin_wait(self, frame):
        if frame.wait_id is not None:
            return
        frame.wait_id = await self.service.begin_wait_intent(
            frame.scope,
            frame.runtime_id,
            hashlib.sha256(b'["direct"]').hexdigest(),
            1,
            WaitPhase.BEFORE_PREPARE,
        )
        frame.wait_capability = await self.service.issue_wait_checkpoint_capability(
            frame.scope.conversation, frame.scope.execution_id, frame.wait_id
        )

    def prepared(self, state, submission):
        frame = self._frame()
        if frame.submission is not None and frame.submission != submission:
            raise PermissionError("MEMORY_FROZEN_FRAME_CHANGED")
        frame.submission = deepcopy(submission)

    def _valid_state(
        self, values, *, result=False, allow_dispatch=False, frame=None, partial=False
    ):
        frame = frame if frame is not None else self._frame()
        if type(values) is not dict:
            return False
        if "__start__" in values:
            return (
                not result
                and values["__start__"] == frame.initial
                and set(values) <= {"__start__"}
            )
        if not partial and not set(frame.initial).issubset(values):
            return False
        expected = dict(frame.initial)
        if frame.submission is not None:
            expected["direct_submission"] = frame.submission
        if result:
            if frame.result is None:
                return False
            expected.update(frame.result)
            if isinstance(values.get("budget_state"), BudgetState):
                raw = frame.initial["budget_state"]
                consumed = dict(raw["consumed"])
                consumed["iterations"] += len(frame.result.get("model_attempts", []))
                for key in ("input_tokens", "output_tokens", "cost_microunits"):
                    consumed[key] += frame.result.get("usage", {}).get(key, 0)
                expected["budget_state"] = BudgetState(
                    BudgetCharge(**consumed),
                    raw["started_at_epoch_ms"],
                    raw["deadline_epoch_ms"],
                )
        allowed_branches = (
            {"branch:to:Publish"}
            if result
            else {"branch:to:Prepare", "branch:to:AuthorizationGate"}
        )
        if allow_dispatch and not result:
            allowed_branches.add("branch:to:Dispatch")
        return all(
            (key in allowed_branches) or (key in expected and value == expected[key])
            for key, value in values.items()
        ) and (result or not values.get("output"))

    def validate_cpu_checkpoint(self, values):
        frame = self._frame()
        return self._valid_state(
            values, allow_dispatch=self._transport_frame_live(frame)
        )

    def _transport_frame_live(self, frame):
        send = frame.transport_wait
        if (
            send is None
            or not frame.active
            or send._task is None
            or send._task.done()
            or not send._waiting
            or send.sent
            or send._reservation is None
            or send._control is not frame.control
            or send._wait_event_id != frame.wait_id
            or self.dispatch is None
            or self.dispatch._waiting_frames.get(id(send)) is not send
        ):
            return False
        send._control.check()
        send._check_reservation()
        send.check_live()
        return (
            send.plan.scope,
            send.plan.operation.operation_id,
            send.plan.operation.attempt,
            send.prepared.manifest.canonical_request_hmac,
        ) == (
            frame.scope,
            frame.wait_capability.operation_id,
            frame.wait_capability.attempt,
            frame.wait_capability.canonical_request_hmac,
        )

    async def ready_reserved_wait(self, send, wait_id):
        frame = self._current.get()
        if frame is None:
            return False
        frame = self._frame()
        if (
            send.plan.scope != frame.scope
            or self.dispatch is None
            or self.dispatch._waiting_frames.get(id(send)) is not send
            or send._reservation is None
            or send.sent
            or not send._waiting
        ):
            raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN")
        frame.wait_id, frame.transport_wait = wait_id, send
        frame.wait_capability = await self.service.issue_wait_checkpoint_capability(
            frame.scope.conversation, frame.scope.execution_id, wait_id
        )
        if not self._transport_frame_live(frame):
            raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN")
        root_config = {
            "configurable": {"thread_id": frame.runtime_id, "checkpoint_ns": ""}
        }
        snapshot = await frame.program._compiled.aget_state(root_config)
        coordinates = snapshot.config["configurable"]
        checkpoint_id = coordinates.get("checkpoint_id")
        if (
            snapshot.next != ("Dispatch",)
            or not checkpoint_id
            or coordinates.get("checkpoint_ns", "") != ""
            or not self.validate_cpu_checkpoint(dict(snapshot.values))
        ):
            raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN")
        await self.checkpoint_store.save(
            frame.runtime_id,
            "s2:direct:1",
            dict(snapshot.values),
            tenant_id=frame.scope.conversation.tenant_id,
            checkpoint_id=checkpoint_id,
        )
        frame.checkpoint_id = checkpoint_id
        await self.service.finish_wait(
            frame.scope.conversation,
            frame.scope.execution_id,
            wait_id,
            checkpoint_ns="",
            checkpoint_id=checkpoint_id,
        )
        return True

    def _valid_writes(self, writes):
        frame = self._frame()
        for channel, value in writes:
            if channel == "__no_writes__":
                # LangGraph终点的空写标记只承认已认证Publish之后的空值。
                if (
                    frame.result is None
                    or not frame.publish_checked
                    or value is not None
                ):
                    return False
            elif channel == "__interrupt__":
                if (
                    frame.wait_id is None
                    or not value
                    or any(
                        getattr(item, "value", None)
                        != {"memory_context_wait": frame.wait_id}
                        for item in value
                    )
                ):
                    return False
            elif not self._valid_state(
                {channel: value}, result=frame.result is not None, partial=True
            ):
                return False
        return True

    @asynccontextmanager
    async def checkpoint_guard(
        self, backend, namespace, *, values=None, writes=None, pending_writes=False
    ):
        frame = self._frame()
        if frame.result is not None:
            if (values is not None and not self._valid_state(values, result=True)) or (
                writes is not None and not self._valid_writes(writes)
            ):
                raise PermissionError("MEMORY_RESULT_CHECKPOINT_FORBIDDEN")
            captured = self.send_authority.captured_for_run(frame.runtime_id)
            if captured is None:
                raise PermissionError("MEMORY_RESULT_UNAVAILABLE")
            async with self.send_authority.checkpoint_scope(
                *captured, backend, namespace, pending_writes=pending_writes
            ) as owner:
                yield owner
            return
        if frame.wait_capability is None:
            try:
                async with self.registry.guard_for_refresh_checkpoint(
                    frame.runtime_id, backend, namespace, pending_writes=pending_writes
                ) as owner:
                    if values is not None and not self._valid_state(
                        values, allow_dispatch=True
                    ):
                        raise PermissionError("MEMORY_FROZEN_FRAME_CHANGED")
                    yield owner
                return
            except PermissionError as error:
                if str(error) != "MEMORY_PACKET_EXPIRED":
                    raise
                if (
                    values is not None and not self.validate_cpu_checkpoint(values)
                ) or (writes is not None and not self._valid_writes(writes)):
                    raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN") from None
                await self._begin_wait(frame)
        if (values is not None and not self.validate_cpu_checkpoint(values)) or (
            writes is not None and not self._valid_writes(writes)
        ):
            raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN")
        if current_memory_wait_checkpoint_capability() is frame.wait_capability:
            async with self.registry.guard(
                frame.runtime_id, backend, namespace, pending_writes=pending_writes
            ) as owner:
                yield owner
        else:
            async with (
                self.registry.wait_checkpoint_scope(frame.wait_capability),
                self.registry.guard(
                    frame.runtime_id, backend, namespace, pending_writes=pending_writes
                ) as owner,
            ):
                yield owner

    async def before_dispatch(self, state, submission):
        frame = self._frame()
        if frame.resume_capability is None:
            current = current_memory_wait_checkpoint_capability()
            if current is not None:
                packet = frame.binding.memory_context.packet
                fingerprint = hashlib.sha256(
                    json.dumps(
                        frame.binding.memory_context.metadata(),
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                if (
                    current is not frame.wait_capability
                    or current.wait_event_id != frame.wait_id
                    or current.scope != frame.scope
                    or current.runtime_id != frame.runtime_id
                    or current.operation_id != hashlib.sha256(b'["direct"]').hexdigest()
                    or current.attempt != 1
                    or current.canonical_request_hmac is not None
                    or current.packet_revision != packet.packet_revision
                    or current.execution_revision != packet.execution_revision
                    or current.current_context_fingerprint != fingerprint
                    or current.original_deadline != frame.binding.deadline_epoch_seconds
                    or not self.validate_cpu_checkpoint(dict(state))
                ):
                    raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN")
                return frame.wait_id
            await self._check(frame)
            return frame.wait_id
        return None

    async def dispatch_completed(self, state, result):
        frame = self._frame()
        if (
            result.get("output") is not None
            and self.send_authority.captured_for_run(frame.runtime_id) is None
        ):
            raise PermissionError("MEMORY_RESULT_UNAVAILABLE")
        frame.result = deepcopy(result)

    async def before_publish(self, state):
        frame = self._frame()
        captured = self.send_authority.captured_for_run(frame.runtime_id)
        if captured is None or frame.result is None:
            raise PermissionError("MEMORY_RESULT_UNAVAILABLE")
        async with self.send_authority.checkpoint_scope(*captured, "official", ""):
            pass
        frame.publish_checked = True

    @asynccontextmanager
    async def result_save_scope(self, state):
        frame = self._frame()
        captured = self.send_authority.captured_for_run(frame.runtime_id)
        if (
            captured is None
            or frame.result is None
            or not self._valid_state(dict(state), result=True)
        ):
            raise PermissionError("MEMORY_RESULT_UNAVAILABLE")
        async with self.send_authority.checkpoint_scope(*captured, "official", ""):
            with bind_result_publish_guard(
                self.send_authority.result_publish_guard(*captured)
            ):
                yield

    async def ready_wait(self, program, config):
        frame = self._frame()
        if (
            frame.wait_capability is None
            or frame.wait_id is None
            or self.checkpoint_store is None
        ):
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        root_config = dict(config) | {
            "configurable": dict(config["configurable"]) | {"checkpoint_ns": ""}
        }
        snapshot = await program._compiled.aget_state(root_config)
        coordinates = snapshot.config["configurable"]
        checkpoint_id = coordinates.get("checkpoint_id")
        if (
            not checkpoint_id
            or coordinates.get("checkpoint_ns", "") != ""
            or snapshot.next != ("AuthorizationGate",)
        ):
            raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN")
        values = dict(snapshot.values)
        if not self.validate_cpu_checkpoint(values):
            raise PermissionError("MEMORY_WAIT_CHECKPOINT_FORBIDDEN")
        await self.checkpoint_store.save(
            frame.runtime_id,
            "s2:direct:1",
            values,
            tenant_id=frame.scope.conversation.tenant_id,
            checkpoint_id=checkpoint_id,
        )
        frame.checkpoint_id = checkpoint_id
        await self.service.finish_wait(
            frame.scope.conversation,
            frame.scope.execution_id,
            frame.wait_id,
            checkpoint_ns="",
            checkpoint_id=checkpoint_id,
        )
        if self.on_wait is not None:
            await self.on_wait(
                frame.wait_id, frame.scope.execution_id, frame.runtime_id
            )

    async def wait_for_resume(self):
        frame = self._frame()
        if frame.wait_id is None:
            raise PermissionError("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED")
        while True:
            frame.control.check()
            await self.service.get_wait(
                frame.scope.conversation,
                frame.scope.execution_id,
                wait_event_id=frame.wait_id,
            )
            record = await self.execution_store.get(
                frame.scope.conversation.tenant_id, frame.scope.execution_id
            )
            if (
                record is not None
                and record.context.packet.packet_revision
                > frame.wait_capability.packet_revision
            ):
                try:
                    return await self.service.claim_resume_start(
                        frame.scope.conversation,
                        frame.scope.execution_id,
                        frame.wait_id,
                    )
                except PermissionError as error:
                    if str(error) != "MEMORY_REFRESH_PENDING":
                        raise
            await asyncio.sleep(0.025)

    async def consume_resume(self, capability, config):
        frame = self._frame()
        if (
            capability.binding.wait_event_id != frame.wait_id
            or capability.binding.runtime_id != frame.runtime_id
        ):
            return False
        accepted = await self.service.consume_resume(capability, config)
        if accepted:
            frame.resume_capability = capability
            frame.wait_capability = None
        return accepted

    @asynccontextmanager
    async def resume_scope(self, capability):
        frame = self._frame()
        record = await self.execution_store.get(
            frame.scope.conversation.tenant_id, frame.scope.execution_id
        )
        if record is None or record.state != "ACTIVE":
            raise PermissionError("MEMORY_ACCESS_REVOKED")
        validate_refresh_context(
            frame.binding.memory_context,
            record.context,
            frame.binding.deadline_epoch_seconds,
            self.registry.clock(),
        )
        frame.binding = replace(frame.binding, memory_context=record.context)
        with bind_run_context(frame.binding):
            yield

    async def finish_resume(self, capability):
        await self.service.finish_resume_start(capability)

    async def verify_wait_frame(self, wait, runtime_id):
        if self.dispatch is not None and await self.dispatch.verify_wait_frame(
            wait, runtime_id
        ):
            return True
        frame = self._frames.get(runtime_id)
        if (
            frame is None
            or frame.task.done()
            or not frame.active
            or frame.wait_id != wait.wait_event_id
            or wait.wait_phase != WaitPhase.BEFORE_PREPARE
        ):
            return False
        frame.control.check()
        return (
            wait.scope,
            wait.task_id,
            wait.execution_id,
            wait.logical_operation_id,
            wait.attempt,
            wait.original_deadline,
        ) == (
            frame.scope.conversation,
            frame.scope.task_id,
            frame.scope.execution_id,
            hashlib.sha256(b'["direct"]').hexdigest(),
            1,
            frame.binding.deadline_epoch_seconds,
        )

    def wait_frame_task(self, wait, runtime_id):
        frame = self._current.get()
        if (
            frame is None
            or not frame.active
            or self._frames.get(runtime_id) is not frame
            or frame.task.done()
            or frame.control is not current_run_control()
        ):
            return None
        if (
            frame.runtime_id,
            frame.wait_id,
            frame.scope.conversation,
            frame.scope.task_id,
            frame.scope.execution_id,
        ) != (
            runtime_id,
            wait.wait_event_id,
            wait.scope,
            wait.task_id,
            wait.execution_id,
        ):
            return None
        try:
            frame.control.check()
        except Exception:  # noqa: BLE001 -- 仅拒绝已停止的原内部帧，不输出异常正文。
            return None
        return frame.task

    async def update_wait_frame_binding(self, original_record, refreshed_context):
        if self.dispatch is not None and await self.dispatch.update_wait_frame_binding(
            original_record, refreshed_context
        ):
            return True
        frame = self._frames.get(original_record.runtime_id)
        if (
            frame is None
            or not frame.active
            or frame.task.done()
            or frame.binding.memory_context != original_record.context
            or frame.wait_id is None
        ):
            return False
        frame.control.check()
        validate_refresh_context(
            original_record.context,
            refreshed_context,
            frame.binding.deadline_epoch_seconds,
            self.registry.clock(),
        )
        frame.authorized_context = refreshed_context
        return True

    async def verify_wait_checkpoint(self, wait, namespace, checkpoint_id):
        frame = self._frames.get(wait.runtime_id)
        if (
            frame is None
            or frame.task.done()
            or not frame.active
            or frame.wait_id != wait.wait_event_id
            or frame.checkpoint_id != checkpoint_id
            or namespace != ""
            or self.saver is None
            or self.checkpoint_store is None
        ):
            return False
        frame.control.check()
        from efficiency_platform_agent.core.memory_thread import CheckpointLocation

        config = {
            "configurable": {
                "thread_id": frame.runtime_id,
                "checkpoint_ns": "",
                "checkpoint_id": checkpoint_id,
            }
        }
        raw = await self.saver._saver.aget_tuple(config)
        if (
            raw is None
            or raw.config["configurable"].get("checkpoint_id") != checkpoint_id
        ):
            return False
        decoded = self.saver._decode_tuple(
            CheckpointLocation(frame.scope, frame.runtime_id, "", ()), raw
        )
        reserved = wait.wait_phase == WaitPhase.RESERVED
        if reserved and not self._transport_frame_live(frame):
            return False
        if not self._valid_state(
            dict(decoded.checkpoint["channel_values"]),
            frame=frame,
            allow_dispatch=reserved,
        ):
            return False
        interrupts = [
            value
            for _, channel, value in decoded.pending_writes or ()
            if channel == "__interrupt__"
        ]
        if reserved:
            if (
                "branch:to:Dispatch" not in decoded.checkpoint["channel_values"]
                or self.dispatch is None
                or not await self.dispatch.verify_wait_frame(wait, wait.runtime_id)
            ):
                return False
        elif not interrupts or not any(
            any(
                getattr(item, "value", None) == {"memory_context_wait": frame.wait_id}
                for item in value
            )
            for value in interrupts
        ):
            return False
        owned = self.checkpoint_store._store.get(
            frame.runtime_id, "s2:direct:1", frame.scope.conversation.tenant_id
        )
        import inspect

        owned = await owned if inspect.isawaitable(owned) else owned
        if owned is None or owned.view.checkpoint_id != checkpoint_id:
            return False
        values = self.checkpoint_store.serializer.decode(
            CheckpointLocation(
                frame.scope, frame.runtime_id, "s2:direct:1", ("owned", checkpoint_id)
            ),
            owned.state,
        )
        return values == {
            key: value
            for key, value in decoded.checkpoint["channel_values"].items()
            if not key.startswith("branch:")
        }


class FencedModelProvider:
    """仅显式登记Graph装配；Direct/HR若未登记，启用时安全拒绝。"""

    def __new__(
        cls,
        provider,
        registry: MemoryThreadRegistry,
        backend_id: str,
        *,
        send_authority=None,
    ):
        if cls is FencedModelProvider and isinstance(provider, StreamingModelProvider):
            return object.__new__(FencedStreamingModelProvider)
        return object.__new__(cls)

    def __init__(
        self,
        provider,
        registry: MemoryThreadRegistry,
        backend_id: str,
        *,
        send_authority=None,
    ):
        self._provider, self._registry, self._backend_id = (
            provider,
            registry,
            backend_id,
        )
        self.descriptor = provider.descriptor
        self._send_authority = send_authority

    def _guard(self):
        binding = current_run_context()
        if binding is None or binding.memory_context is None:
            raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
        return self._registry.guard_execution(
            binding.conversation.tenant_id,
            binding.execution_id,
            self._backend_id,
            "provider",
        )

    def acquire(self):
        binding = current_run_context()
        if binding is None or binding.memory_context is None:
            raise PermissionError("MEMORY_EXECUTION_OWNER_REQUIRED")
        acquire = getattr(self._send_authority, "acquire", None)
        if not callable(acquire):
            raise PermissionError("MEMORY_SEND_LEASE_REQUIRED")
        return acquire()

    @asynccontextmanager
    async def _provider_scope(self):
        if (
            current_memory_wait_checkpoint_capability() is not None
            or current_memory_result_checkpoint_permit() is not None
        ):
            raise PermissionError("MEMORY_CPU_CHECKPOINT_SEND_FORBIDDEN")
        if self._send_authority is not None and getattr(
            self._provider, "context_send_lease_boundary", False
        ):
            with bind_context_send_lease(self._send_authority):
                yield
        else:
            async with self._guard():
                yield

    async def complete(self, request):
        async with self._provider_scope():
            return await self._provider.complete(request)


class FencedStreamingModelProvider(FencedModelProvider):
    """仅底层真实支持stream时声明流式能力，关闭迭代器后才释放门禁。"""

    async def stream(self, request):
        async with self._provider_scope():
            iterator = self._provider.stream(request)
            try:
                async for event in iterator:
                    yield event
            finally:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
