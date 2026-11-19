"""Direct授权等待必须是真LangGraph CPU interrupt，恢复不重取提交或重发。"""

import pytest

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
)
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.orchestration.builders.conversation_direct import (
    ConversationDirectGraphBuilder,
)
from tests.orchestration.test_conversation_direct_runtime import (
    FakeModelRuntime,
    _state,
    _submission,
)


async def test_direct_cpu_gate_uses_real_interrupt_and_internal_command_once():
    model = FakeModelRuntime()
    resolutions = []
    published = []

    async def resolver(*args):
        resolutions.append(args)
        return _submission()

    class Gate:
        capability = object()
        ready = False
        used = False

        async def before_dispatch(self, state, submission):
            assert not model.calls
            return None if self.ready else "memory-wait"

        async def consume_resume(self, capability, config):
            if capability is not self.capability or self.used or not self.ready:
                return False
            self.used = True
            return True

        async def before_publish(self, state):
            assert model.calls == 1

    gate = Gate()

    async def publish(run_id, delta):
        published.append(delta)

    program = ConversationDirectGraphBuilder(
        GeneralConversationAgent(model),
        resolver,
        output_publisher=publish,
        memory_gate=gate,
    ).build()
    config = {"configurable": {"thread_id": "run-1", "checkpoint_ns": ""}}
    assert set(program._compiled.get_graph().nodes) >= {
        "Prepare",
        "AuthorizationGate",
        "Dispatch",
        "Publish",
    }
    waiting = await program.invoke(_state(), config)
    assert waiting["__interrupt__"] and model.calls == 0
    snapshot = await program._compiled.aget_state(config)
    assert snapshot.next == ("AuthorizationGate",)
    assert len(resolutions) == 1
    with pytest.raises(ValueError, match="RESUME_UNSUPPORTED"):
        await program.resume(JsonObject(), config)
    with pytest.raises(PermissionError, match="MEMORY_CONTEXT_RESUME_REQUIRED"):
        await program.resume_memory_context({}, config)
    gate.ready = True
    result = await program.resume_memory_context(gate.capability, config)
    assert result["output"]["content"]
    assert model.calls == len(resolutions) == len(published) == 1
    with pytest.raises(PermissionError, match="MEMORY_CONTEXT_RESUME_REQUIRED"):
        await program.resume_memory_context(gate.capability, config)
    assert model.calls == 1


def test_encrypted_checkpoint_serializer_roundtrips_official_interrupt():
    from langgraph.types import Interrupt

    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        CheckpointPayloadSerializer,
    )
    from efficiency_platform_agent.persistence.memory_checkpoint_cipher import (
        AesGcmCheckpointBodyCipher,
    )
    from tests.unit.memory.test_send_lease_authority import case

    scope = case()[1]
    location = CheckpointLocation(
        scope, "runtime", "", ("write", "checkpoint", "task", "__interrupt__")
    )
    serializer = CheckpointPayloadSerializer(
        AesGcmCheckpointBodyCipher(b"k" * 32, "synthetic")
    )
    value = (Interrupt({"memory_context_wait": "wait"}, id="synthetic-interrupt"),)
    encoded = serializer.encode(location, value)
    assert serializer.decode(location, encoded) == value


async def test_graph_runtime_internal_resume_rejects_uninstalled_or_forged_capability():
    from efficiency_platform_agent.orchestration.registry import GraphRegistry
    from efficiency_platform_agent.orchestration.runtime import GraphRuntime

    runtime = GraphRuntime(GraphRegistry())
    with pytest.raises(PermissionError, match="MEMORY_CONTEXT_RESUME_REQUIRED"):
        await runtime.resume_memory_context({"dispatch_allowed": True})


async def test_trusted_direct_gate_rejects_changed_cpu_frame_and_dispatch_checkpoint():
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.core.run_context_binding import bind_run_context
    from efficiency_platform_agent.orchestration.context_gate import (
        MemoryDirectContextGate,
    )
    from tests.unit.memory.test_send_lease_authority import case

    binding, _scope, record, _, _ = case()
    from dataclasses import replace

    from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant

    context = replace(
        record.context,
        execution_grants=(
            MemoryExecutionGrant("direct", "operations", "assistant_response"),
        ),
    )
    record = replace(record, context=context)
    binding = replace(binding, memory_context=context)

    class Store:
        async def get(self, *args):
            return record

    class Registry:
        @asynccontextmanager
        async def send_lease_execution(self, *args):
            yield

    class Authority:
        @asynccontextmanager
        async def graph_scope(self, *args):
            yield

    gate = MemoryDirectContextGate(SimpleNamespace(), Store(), Registry(), Authority())
    state = _state()
    state["run_id"] = "runtime"
    state["tenant_id"] = binding.conversation.tenant_id
    state["user_id"] = binding.conversation.user_id
    config = {"configurable": {"thread_id": "runtime", "checkpoint_ns": ""}}
    with bind_run_context(binding), execution_scope(RunControl()):
        async with gate.run_scope(SimpleNamespace(), state, config):
            gate.prepared(state, {"current_message": state["input_text"]})
            values = state | {
                "direct_submission": {"current_message": state["input_text"]},
                "branch:to:AuthorizationGate": None,
            }
            assert gate.validate_cpu_checkpoint(values)
            assert not gate.validate_cpu_checkpoint({})
            assert not gate.validate_cpu_checkpoint(
                {key: value for key, value in values.items() if key != "input_text"}
            )
            assert not gate.validate_cpu_checkpoint(values | {"input_text": "changed"})
            assert not gate.validate_cpu_checkpoint(
                values | {"output": {"content": "forged"}}
            )
            assert not gate.validate_cpu_checkpoint(
                values | {"branch:to:Dispatch": None}
            )


async def test_fenced_saver_requires_frozen_frame_authority_for_wait_capability():
    from contextlib import asynccontextmanager

    from langgraph.checkpoint.base import empty_checkpoint
    from langgraph.checkpoint.memory import InMemorySaver

    from efficiency_platform_agent.core.memory_execution import (
        MemoryWaitCheckpointCapability,
        bind_memory_wait_checkpoint_capability,
    )
    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        FencedCheckpointSaver,
    )
    from tests.unit.memory.test_send_lease_authority import case

    scope = case()[1]
    cap = MemoryWaitCheckpointCapability(
        scope, "runtime", "wait", "operation", 1, None, 1, 1, "c" * 64, 200, "cap"
    )

    class Registry:
        @asynccontextmanager
        async def guard(self, *args, **kwargs):
            yield CheckpointLocation(scope, "runtime", "", ())

    saver = FencedCheckpointSaver(InMemorySaver(), Registry(), "official")
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"input_text": "forged", "branch:to:Dispatch": None}
    with (
        bind_memory_wait_checkpoint_capability(cap),
        pytest.raises(PermissionError, match="MEMORY_WAIT_CHECKPOINT_FORBIDDEN"),
    ):
        await saver.aput(
            {"configurable": {"thread_id": "runtime", "checkpoint_ns": ""}},
            checkpoint,
            {},
            {},
        )


async def test_ready_wait_reads_official_root_namespace_and_saves_owned_namespace():
    from contextlib import asynccontextmanager
    from dataclasses import replace
    from types import SimpleNamespace

    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
    from efficiency_platform_agent.core.run_context_binding import bind_run_context
    from efficiency_platform_agent.orchestration.context_gate import (
        MemoryDirectContextGate,
    )
    from tests.unit.memory.test_send_lease_authority import case

    binding, _, record, _, _ = case()
    context = replace(
        record.context,
        execution_grants=(
            MemoryExecutionGrant("direct", "operations", "assistant_response"),
        ),
    )
    record, binding = (
        replace(record, context=context),
        replace(binding, memory_context=context),
    )
    state = _state() | {"run_id": "runtime"}

    class Store:
        async def get(self, *args):
            return record

    class Registry:
        @asynccontextmanager
        async def send_lease_execution(self, *args):
            yield

    class Authority:
        @asynccontextmanager
        async def graph_scope(self, *args):
            yield

    class Compiled:
        async def aget_state(self, config):
            assert config["configurable"]["checkpoint_ns"] == ""
            return SimpleNamespace(
                config={
                    "configurable": {"checkpoint_ns": "", "checkpoint_id": "actual-id"}
                },
                next=("AuthorizationGate",),
                values=state,
            )

    class Owned:
        async def save(self, runtime, namespace, values, **kwargs):
            assert namespace == "s2:direct:1" and kwargs["checkpoint_id"] == "actual-id"

    class Service:
        async def finish_wait(self, *args, **kwargs):
            assert kwargs == {"checkpoint_ns": "", "checkpoint_id": "actual-id"}

    gate = MemoryDirectContextGate(
        Service(), Store(), Registry(), Authority(), checkpoint_store=Owned()
    )
    program = SimpleNamespace(_compiled=Compiled())
    config = {"configurable": {"thread_id": "runtime", "checkpoint_ns": "s2:direct:1"}}
    with bind_run_context(binding), execution_scope(RunControl()):
        async with gate.run_scope(program, state, config) as frame:
            frame.wait_id, frame.wait_capability = "wait", object()
            await gate.ready_wait(program, config)


async def test_fenced_saver_passes_frozen_channel_values_to_checkpoint_authority():
    from contextlib import asynccontextmanager

    from langgraph.checkpoint.base import empty_checkpoint
    from langgraph.checkpoint.memory import InMemorySaver

    from efficiency_platform_agent.core.memory_thread import CheckpointLocation
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        FencedCheckpointSaver,
    )
    from tests.unit.memory.test_send_lease_authority import case

    scope = case()[1]

    class Authority:
        def has_frame(self):
            return True

        @asynccontextmanager
        async def checkpoint_guard(self, *args, values=None, **kwargs):
            assert values is None or values == {"input_text": "frozen"}
            yield CheckpointLocation(scope, "runtime", "", ())

    saver = FencedCheckpointSaver(InMemorySaver(), object(), "official")
    saver.install_context_checkpoint_authority(Authority())
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"input_text": "frozen"}
    checkpoint["channel_versions"] = {"input_text": "1"}
    config = await saver.aput(
        {"configurable": {"thread_id": "runtime", "checkpoint_ns": ""}},
        checkpoint,
        {},
        {"input_text": "1"},
    )
    saved = await saver.aget_tuple(config)
    assert saved.checkpoint["channel_values"] == {"input_text": "frozen"}


async def test_authorization_gate_in_exact_wait_scope_never_reenters_send_lease():
    import hashlib
    import json
    from contextlib import asynccontextmanager
    from dataclasses import replace
    from types import SimpleNamespace

    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.core.memory_execution import (
        MemoryExecutionGrant,
        MemoryWaitCheckpointCapability,
        bind_memory_wait_checkpoint_capability,
    )
    from efficiency_platform_agent.core.run_context_binding import bind_run_context
    from efficiency_platform_agent.orchestration.context_gate import (
        MemoryDirectContextGate,
    )
    from tests.unit.memory.test_send_lease_authority import case

    binding, _, record, _, _ = case()
    context = replace(
        record.context,
        execution_grants=(
            MemoryExecutionGrant("direct", "operations", "assistant_response"),
        ),
    )
    record, binding = (
        replace(record, context=context),
        replace(binding, memory_context=context),
    )

    class Store:
        async def get(self, *args):
            return record

    class Registry:
        inside_wait = False

        @asynccontextmanager
        async def send_lease_execution(self, *args):
            assert not self.inside_wait, "CPU等待栅栏内不得重入发送lease"
            yield

        @asynccontextmanager
        async def wait_checkpoint_scope(self, cap):
            self.inside_wait = True
            try:
                with bind_memory_wait_checkpoint_capability(cap):
                    yield
            finally:
                self.inside_wait = False

    class Authority:
        @asynccontextmanager
        async def graph_scope(self, *args):
            yield

    registry = Registry()
    gate = MemoryDirectContextGate(SimpleNamespace(), Store(), registry, Authority())
    state = _state() | {
        "run_id": "runtime",
        "tenant_id": binding.conversation.tenant_id,
        "user_id": binding.conversation.user_id,
    }
    config = {"configurable": {"thread_id": "runtime", "checkpoint_ns": ""}}
    with bind_run_context(binding), execution_scope(RunControl()):
        async with gate.run_scope(SimpleNamespace(), state, config) as frame:
            cap = MemoryWaitCheckpointCapability(
                frame.scope,
                "runtime",
                "wait",
                hashlib.sha256(b'["direct"]').hexdigest(),
                1,
                None,
                context.packet.packet_revision,
                context.packet.execution_revision,
                hashlib.sha256(
                    json.dumps(
                        context.metadata(),
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                200,
                "private-cap",
            )
            frame.wait_id, frame.wait_capability = "wait", cap
            async with registry.wait_checkpoint_scope(cap):
                assert await gate.before_dispatch(state, None) == "wait"
                with (
                    bind_memory_wait_checkpoint_capability(replace(cap)),
                    pytest.raises(
                        PermissionError, match="MEMORY_WAIT_CHECKPOINT_FORBIDDEN"
                    ),
                ):
                    await gate.before_dispatch(state, None)


@pytest.mark.parametrize("fail_save", [False, True])
async def test_runtime_applies_result_once_inside_original_result_scope(fail_save):
    from contextlib import asynccontextmanager

    from efficiency_platform_agent.core.enums import StrategyMode
    from efficiency_platform_agent.orchestration.builders.conversation_direct import (
        build_conversation_direct_registration,
    )
    from efficiency_platform_agent.orchestration.registry import GraphRegistry
    from efficiency_platform_agent.orchestration.runtime import GraphRuntime
    from efficiency_platform_agent.routing.strategy_router import StrategySelection

    model, events = FakeModelRuntime(), []

    class Gate:
        defer_publication = True
        active = False

        @asynccontextmanager
        async def run_scope(self, *args):
            self.active = True
            try:
                yield
            finally:
                self.active = False

        @asynccontextmanager
        async def invoke_scope(self):
            yield

        async def before_dispatch(self, *args):
            return None

        async def before_publish(self, *args):
            assert self.active

        @asynccontextmanager
        async def result_save_scope(self, *args):
            events.append("result-lease")
            try:
                yield
            finally:
                events.append("release")

    gate = Gate()

    async def resolver(*args):
        return _submission()

    async def early_publish(*args):
        pytest.fail("原Run持久化前不得发布结果")

    graphs = GraphRegistry()
    graphs.register(
        build_conversation_direct_registration(
            GeneralConversationAgent(model),
            resolver,
            output_publisher=early_publish,
            memory_gate=gate,
        )
    )
    runtime = GraphRuntime(graphs)

    async def save(result):
        assert (
            gate.active
            and events == ["result-lease"]
            and result.checkpoint.checkpoint_id
        )
        events.append("save")
        if fail_save:
            raise ValueError("synthetic-save-failed")
        return "saved"

    if fail_save:
        with pytest.raises(ValueError, match="synthetic-save-failed"):
            await runtime.execute_memory_context(
                StrategySelection(StrategyMode.DIRECT, "rf04/1", "memory"),
                _state(),
                save,
            )
    else:
        assert (
            await runtime.execute_memory_context(
                StrategySelection(StrategyMode.DIRECT, "rf04/1", "memory"),
                _state(),
                save,
            )
            == "saved"
        )
    assert (
        model.calls == 1
        and events == ["result-lease", "save", "release"]
        and not gate.active
    )


async def test_result_checkpoint_accepts_exact_budget_normalization_and_rejects_extension():
    from contextlib import asynccontextmanager
    from dataclasses import replace
    from types import SimpleNamespace

    from efficiency_platform_agent.core.budget import BudgetCharge, BudgetState
    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
    from efficiency_platform_agent.core.run_context_binding import bind_run_context
    from efficiency_platform_agent.orchestration.context_gate import (
        MemoryDirectContextGate,
    )
    from tests.unit.memory.test_send_lease_authority import case

    binding, _, record, _, _ = case()
    context = replace(
        record.context,
        execution_grants=(
            MemoryExecutionGrant("direct", "operations", "assistant_response"),
        ),
    )
    record, binding = (
        replace(record, context=context),
        replace(binding, memory_context=context),
    )

    class Store:
        async def get(self, *args):
            return record

    class Registry:
        @asynccontextmanager
        async def send_lease_execution(self, *args):
            yield

    class Authority:
        def captured_for_run(self, *args):
            return object(), "captured-ref"

        @asynccontextmanager
        async def graph_scope(self, *args):
            yield

        @asynccontextmanager
        async def checkpoint_scope(self, *args, pending_writes=False):
            yield None

    gate = MemoryDirectContextGate(SimpleNamespace(), Store(), Registry(), Authority())
    state = _state() | {"run_id": "runtime"}
    from dataclasses import asdict

    state["budget_state"] = asdict(BudgetState(BudgetCharge(), 100000, 200000))
    delta = {
        "output": {"content": "captured"},
        "usage": {
            "input_tokens": 2,
            "output_tokens": 3,
            "cost_microunits": 0,
            "estimated": False,
        },
        "model_attempts": [{"attempt": 1}],
        "next_status": "succeeded",
    }
    raw = state["budget_state"]
    charge = dict(raw["consumed"])
    charge["iterations"] += 1
    charge["input_tokens"] += 2
    charge["output_tokens"] += 3
    budget = BudgetState(
        BudgetCharge(**charge), raw["started_at_epoch_ms"], raw["deadline_epoch_ms"]
    )
    with bind_run_context(binding), execution_scope(RunControl()):
        async with gate.run_scope(
            SimpleNamespace(), state, {"configurable": {"thread_id": "runtime"}}
        ):
            await gate.dispatch_completed(state, delta)
            async with gate.checkpoint_guard(
                "owned", "s2:direct:1", values=state | delta | {"budget_state": budget}
            ):
                pass
            with pytest.raises(
                PermissionError, match="MEMORY_RESULT_CHECKPOINT_FORBIDDEN"
            ):
                async with gate.checkpoint_guard(
                    "owned",
                    "s2:direct:1",
                    values=state
                    | delta
                    | {
                        "budget_state": replace(
                            budget, deadline_epoch_ms=budget.deadline_epoch_ms + 1
                        )
                    },
                ):
                    pass
            with pytest.raises(
                PermissionError, match="MEMORY_RESULT_CHECKPOINT_FORBIDDEN"
            ):
                async with gate.checkpoint_guard(
                    "official",
                    "",
                    writes=[("__no_writes__", None)],
                    pending_writes=True,
                ):
                    pass
            await gate.before_publish(state | delta)
            async with gate.checkpoint_guard(
                "official", "", writes=[("__no_writes__", None)], pending_writes=True
            ):
                pass
            with pytest.raises(
                PermissionError, match="MEMORY_RESULT_CHECKPOINT_FORBIDDEN"
            ):
                async with gate.checkpoint_guard(
                    "official",
                    "",
                    writes=[("__no_writes__", "changed")],
                    pending_writes=True,
                ):
                    pass


async def test_consumed_graph_capability_exits_wait_checkpoint_mode():
    from contextlib import asynccontextmanager
    from dataclasses import replace
    from types import SimpleNamespace

    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
    from efficiency_platform_agent.core.run_context_binding import bind_run_context
    from efficiency_platform_agent.orchestration.context_gate import (
        MemoryDirectContextGate,
    )
    from tests.unit.memory.test_send_lease_authority import case

    binding, _, record, _, _ = case()
    context = replace(
        record.context,
        execution_grants=(
            MemoryExecutionGrant("direct", "operations", "assistant_response"),
        ),
    )
    record, binding = (
        replace(record, context=context),
        replace(binding, memory_context=context),
    )

    class Store:
        async def get(self, *args):
            return record

    class Registry:
        @asynccontextmanager
        async def send_lease_execution(self, *args):
            yield

    class Authority:
        @asynccontextmanager
        async def graph_scope(self, *args):
            yield

    class Service:
        async def consume_resume(self, *args):
            return True

    gate = MemoryDirectContextGate(Service(), Store(), Registry(), Authority())
    with bind_run_context(binding), execution_scope(RunControl()):
        async with gate.run_scope(
            SimpleNamespace(),
            _state() | {"run_id": "runtime"},
            {"configurable": {"thread_id": "runtime"}},
        ) as frame:
            cap = SimpleNamespace(
                binding=SimpleNamespace(wait_event_id="wait", runtime_id="runtime")
            )
            frame.wait_id, frame.wait_capability = "wait", object()
            assert await gate.consume_resume(cap, {})
            assert frame.wait_capability is None and frame.resume_capability is cap


async def test_real_langgraph_publish_emits_nil_no_writes_protocol_marker():
    from langgraph.checkpoint.memory import InMemorySaver

    records = []

    class Recorder(InMemorySaver):
        async def aput_writes(self, config, writes, task_id, task_path=""):
            records.extend(
                (channel, type(value).__name__, value is None)
                for channel, value in writes
            )
            return await super().aput_writes(config, writes, task_id, task_path)

    class Gate:
        async def before_dispatch(self, *args):
            return None

        async def before_publish(self, *args):
            pass

    async def resolver(*args):
        return _submission()

    program = ConversationDirectGraphBuilder(
        GeneralConversationAgent(FakeModelRuntime()),
        resolver,
        checkpointer=Recorder(),
        memory_gate=Gate(),
    ).build()
    result = await program.invoke(
        _state(), {"configurable": {"thread_id": "runtime", "checkpoint_ns": ""}}
    )
    assert result["output"]["content"]
    assert ("__no_writes__", "NoneType", True) in records


async def test_dispatch_checkpoint_requires_original_live_reserved_transport_frame():
    from contextlib import asynccontextmanager
    from dataclasses import replace
    from types import SimpleNamespace

    from efficiency_platform_agent.core.execution_control import (
        RunControl,
        execution_scope,
    )
    from efficiency_platform_agent.core.memory_execution import (
        MemoryExecutionGrant,
        MemoryWaitCheckpointCapability,
    )
    from efficiency_platform_agent.core.run_context_binding import bind_run_context
    from efficiency_platform_agent.orchestration.context_gate import (
        MemoryDirectContextGate,
    )
    from tests.unit.memory.test_send_lease_authority import case

    binding, _, record, _, _ = case()
    context = replace(
        record.context,
        execution_grants=(
            MemoryExecutionGrant("direct", "operations", "assistant_response"),
        ),
    )
    record, binding = (
        replace(record, context=context),
        replace(binding, memory_context=context),
    )

    class Store:
        async def get(self, *args):
            return record

    class Registry:
        @asynccontextmanager
        async def send_lease_execution(self, *args):
            yield

    class Authority:
        @asynccontextmanager
        async def graph_scope(self, *args):
            yield

    class Dispatch:
        def __init__(self):
            self._waiting_frames = {}

        def install_wait_checkpoint_callback(self, callback):
            self.callback = callback

    dispatch = Dispatch()
    gate = MemoryDirectContextGate(
        SimpleNamespace(), Store(), Registry(), Authority(), dispatch=dispatch
    )
    state = _state() | {"run_id": "runtime"}
    with bind_run_context(binding), execution_scope(RunControl()) as control:
        async with gate.run_scope(
            SimpleNamespace(), state, {"configurable": {"thread_id": "runtime"}}
        ) as frame:
            values = state | {"branch:to:Dispatch": None}
            assert not gate.validate_cpu_checkpoint(values)
            cap = MemoryWaitCheckpointCapability(
                frame.scope,
                "runtime",
                "reserved-wait",
                "original-operation",
                1,
                "b" * 64,
                1,
                1,
                "c" * 64,
                200,
                "opaque-cap",
            )
            import asyncio

            send = SimpleNamespace(
                _task=asyncio.current_task(),
                _waiting=True,
                sent=False,
                _reservation=object(),
                _control=control,
                _wait_event_id="reserved-wait",
                plan=SimpleNamespace(
                    scope=frame.scope,
                    operation=SimpleNamespace(
                        operation_id="original-operation", attempt=1
                    ),
                ),
                prepared=SimpleNamespace(
                    manifest=SimpleNamespace(canonical_request_hmac="b" * 64)
                ),
                _check_reservation=lambda: None,
                check_live=lambda: None,
            )
            frame.wait_id, frame.wait_capability, frame.transport_wait = (
                "reserved-wait",
                cap,
                send,
            )
            dispatch._waiting_frames[id(send)] = send
            assert gate.validate_cpu_checkpoint(values)
            send.sent = True
            assert not gate.validate_cpu_checkpoint(values)
            send.sent = False
            dispatch._waiting_frames.clear()
            assert not gate.validate_cpu_checkpoint(values)


async def test_memory_dispatch_waits_for_real_authorization_checkpoint_commit():
    import asyncio

    from langgraph.checkpoint.memory import InMemorySaver

    entered, release = asyncio.Event(), asyncio.Event()

    class Saver(InMemorySaver):
        async def aput(self, config, checkpoint, metadata, new_versions):
            if "branch:to:Dispatch" in checkpoint["channel_values"]:
                entered.set()
                await release.wait()
            return await super().aput(config, checkpoint, metadata, new_versions)

    class Gate:
        async def before_dispatch(self, *args):
            return None

        async def before_publish(self, *args):
            pass

    async def resolver(*args):
        return _submission()

    model = FakeModelRuntime()
    program = ConversationDirectGraphBuilder(
        GeneralConversationAgent(model),
        resolver,
        checkpointer=Saver(),
        memory_gate=Gate(),
    ).build()
    task = asyncio.create_task(
        program.invoke(
            _state(), {"configurable": {"thread_id": "runtime", "checkpoint_ns": ""}}
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        assert model.calls == 0
    finally:
        release.set()
        await task
