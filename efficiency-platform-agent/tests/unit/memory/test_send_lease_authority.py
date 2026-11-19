"""实际lease产生的permit不能由同字段复制、模型输出或跨任务冒充。"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionRecord,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from tests.unit.memory.test_refresh_contracts import fixture


def case():
    raw = fixture()["original_context"]
    context = MemoryExecutionContext.from_metadata(
        raw["authorization"] | {"packet": raw["packet"]}
    )
    packet = context.packet
    binding = RunContextBinding(
        packet.scope, packet.task_id, packet.execution_id, 200, context
    )
    scope = ExecutionScope(
        packet.scope,
        packet.task_id,
        packet.execution_id,
        "direct",
        "assistant_response",
        "operations",
    )
    record = MemoryExecutionRecord(
        context,
        "runtime",
        "OPERATIONS",
        "a" * 64,
        200,
        "ACTIVE",
        1,
        packet.grant_epoch,
        packet.source_epoch,
        packet.deletion_epoch,
    )
    prepared = SimpleNamespace(
        manifest=SimpleNamespace(
            scope=scope,
            node_id="direct",
            operation_id="operation",
            attempt=1,
            canonical_request_hmac="b" * 64,
            manifest_id="manifest",
        )
    )
    return (
        binding,
        scope,
        record,
        prepared,
        ContextOperation("operation", 1, 200, False),
    )


class Registry:
    held = False
    current = True

    @asynccontextmanager
    async def send_lease_execution(self, *args):
        self.held = True
        try:
            yield SimpleNamespace(thread_id="runtime")
        finally:
            self.held = False

    @asynccontextmanager
    async def result_lease_execution(self, *args):
        if not self.current:
            raise PermissionError("SOURCE_REVOKED")
        yield

    @asynccontextmanager
    async def result_checkpoint_scope(self, *args):
        self.checkpoint_permit = args[-2]
        try:
            yield self.checkpoint_permit
        finally:
            self.checkpoint_permit = None

    @asynccontextmanager
    async def guard(self, runtime, backend, namespace, *, pending_writes=False):
        from efficiency_platform_agent.core.memory_thread import CheckpointLocation

        assert self.checkpoint_permit is not None
        yield CheckpointLocation(self.checkpoint_permit.scope, runtime, namespace, ())


async def test_permit_requires_actual_lease_and_complete_original_response():
    from efficiency_platform_agent.memory.execution_authority import (
        MemorySendLeaseAuthority,
    )

    binding, _, record, prepared, operation = case()
    registry = Registry()

    class Store:
        async def get(self, *args):
            return record

    authority = MemorySendLeaseAuthority(registry, Store(), "official")
    with bind_run_context(binding), execution_scope(RunControl()):
        with pytest.raises(PermissionError, match="LEASE_REQUIRED"):
            await authority.issue(prepared, operation)
        async with authority.acquire():
            permit = await authority.issue(prepared, operation)
        assert not await authority.validate(permit)
        authority.response_received(permit, complete=True)
        assert await authority.validate(permit)
        assert not authority.validate_captured(permit, "result")
        authority.result_captured(permit, "result")
        assert authority.validate_captured(permit, "result")
        assert not authority.validate_captured(permit, "other")
        assert not await authority.validate(replace(permit))
        assert not await authority.validate(True)
        assert not await asyncio.create_task(authority.validate(permit))
        registry.current = False
        assert not await authority.validate(permit)


async def test_only_privately_issued_derive_permit_can_keep_shorter_deadline():
    import json

    from efficiency_platform_agent.core.context_dispatch import model_stage
    from efficiency_platform_agent.memory.execution_authority import (
        MemorySendLeaseAuthority,
    )

    binding, _, record, prepared, operation = case()
    context = replace(
        binding.memory_context,
        derive_template_json=json.dumps({"operation_id": "logical"}),
    )
    binding = replace(binding, memory_context=context)
    record = replace(record, context=context)
    prepared.manifest.node_id = "memory.derive"
    prepared.manifest.prompt_version = "derive-prompt/2"
    prepared.manifest.output_schema_version = "derive-schema/2"

    class Store:
        async def get(self, *_):
            return record

    authority = MemorySendLeaseAuthority(Registry(), Store(), "official")
    with (
        bind_run_context(binding),
        execution_scope(RunControl()),
        model_stage("logical", b"", node_id="memory.derive"),
    ):
        async with authority.acquire():
            permit = await authority.issue(
                prepared, replace(operation, deadline_epoch_seconds=199)
            )
        authority.response_received(permit, complete=True)
        assert authority.validate_issued(permit)
        async with authority.result_scope(permit):
            pass
        assert not authority.validate_issued(replace(permit))
        with pytest.raises(PermissionError, match="BINDING"):
            async with authority.acquire():
                await authority.issue(
                    prepared, replace(operation, deadline_epoch_seconds=201)
                )
        prepared.manifest.node_id = "direct"
        with pytest.raises(PermissionError, match="BINDING"):
            async with authority.acquire():
                await authority.issue(
                    prepared, replace(operation, deadline_epoch_seconds=199)
                )


async def test_stop_after_complete_response_still_prevents_result_authorization():
    from efficiency_platform_agent.memory.execution_authority import (
        MemorySendLeaseAuthority,
    )

    binding, _, record, prepared, operation = case()

    class Store:
        async def get(self, *args):
            return record

    authority = MemorySendLeaseAuthority(Registry(), Store(), "official")
    control = RunControl()
    with bind_run_context(binding), execution_scope(control):
        async with authority.acquire():
            permit = await authority.issue(prepared, operation)
        authority.response_received(permit, complete=True)
        control.stop()
        assert not await authority.validate(permit)


async def test_captured_result_can_authorize_only_children_of_original_live_graph_scope():
    from efficiency_platform_agent.memory.execution_authority import (
        MemorySendLeaseAuthority,
    )

    binding, _, record, prepared, operation = case()

    class Store:
        async def get(self, *args):
            return record

    authority = MemorySendLeaseAuthority(Registry(), Store(), "official")
    with bind_run_context(binding), execution_scope(RunControl()):
        async with authority.graph_scope("runtime"):
            release = asyncio.Event()

            async def dispatch():
                async with authority.acquire():
                    permit = await authority.issue(prepared, operation)
                authority.response_received(permit, complete=True)
                authority.result_captured(permit, "result")
                return permit

            import gc
            import weakref

            send_task = asyncio.create_task(dispatch())
            send_task_ref = weakref.ref(send_task)
            permit = await send_task
            del send_task
            await asyncio.sleep(0)
            gc.collect()
            assert send_task_ref() is None
            assert not authority.validate_issued(permit)
            assert authority.validate_captured(permit, "result")
            assert authority.captured_for_run("runtime") == (permit, "result")
            async with authority.checkpoint_scope(
                permit, "result", "official", ""
            ) as location:
                from efficiency_platform_agent.core.memory_thread import (
                    CheckpointLocation,
                )

                assert isinstance(location, CheckpointLocation)
                assert (
                    location.scope == permit.scope
                    and location.thread_id == permit.runtime_id
                )
                assert authority.validate_issued(permit)
            assert not authority.validate_issued(permit)

            async def inherited_scope_after_exit():
                await release.wait()
                return authority.validate_captured(permit, "result")

            late = asyncio.create_task(inherited_scope_after_exit())
        assert not authority.validate_captured(permit, "result")
        release.set()
        assert not await late


async def test_authority_does_not_retain_completed_task_result_or_control_results():
    import gc
    import weakref

    from efficiency_platform_agent.memory.execution_authority import (
        MemorySendLeaseAuthority,
    )

    binding, _, record, prepared, operation = case()

    class Store:
        async def get(self, *args):
            return record

    class PrivateBody:
        pass

    authority = MemorySendLeaseAuthority(Registry(), Store(), "official")
    observed = {}

    async def original_frame():
        control = RunControl()
        control_body, task_body = PrivateBody(), PrivateBody()
        control.results["synthetic-private-result"] = control_body
        observed["control"] = weakref.ref(control)
        observed["control_body"] = weakref.ref(control_body)
        observed["task_body"] = weakref.ref(task_body)
        with bind_run_context(binding), execution_scope(control):
            async with authority.acquire():
                permit = await authority.issue(prepared, operation)
            authority.response_received(permit, complete=True)
            authority.result_captured(permit, "captured-ref")
            return permit, task_body

    task = asyncio.create_task(original_frame())
    observed["task"] = weakref.ref(task)
    permit, task_body = await task
    del task_body, task
    await asyncio.sleep(0)
    gc.collect()
    assert observed["task"]() is None
    assert observed["control"]() is None
    assert observed["task_body"]() is None and observed["control_body"]() is None
    assert not authority.validate_issued(permit)
    assert not authority.validate_captured(permit, "captured-ref")
