"""D16离线门禁；Fake端口不作为真实数据库证明。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver


def test_resume_request_rejects_changed_content():
    from efficiency_platform_agent.core.memory_thread import ResumeRequest

    with pytest.raises(ValueError, match="RESUME_NEW_CONTENT_DISABLED"):
        ResumeRequest("wait", 1, 1, "resume", "a" * 64, "cpu", new_content=True)


@pytest.mark.asyncio
async def test_fenced_memory_saver_blocks_late_writes_reads_and_unknown_threads():
    from efficiency_platform_agent.orchestration.fenced_checkpoint import (
        FencedCheckpointSaver,
    )

    class Gate:
        blocked = False

        @asynccontextmanager
        async def guard(self, thread_id, backend_id, namespace, **kwargs):
            if self.blocked or thread_id != "root":
                raise PermissionError("MEMORY_THREAD_FENCED")
            yield

    gate = Gate()
    saver = FencedCheckpointSaver(InMemorySaver(), gate, "official-memory")
    config = {"configurable": {"thread_id": "root", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    config = await saver.aput(config, checkpoint, {}, {})
    assert await saver.aget_tuple(config) is not None
    gate.blocked = True
    for operation in (
        lambda: saver.aput(config, empty_checkpoint(), {}, {}),
        lambda: saver.aput_writes(config, [("pending", "x")], "task"),
        lambda: saver.aget_tuple(config),
    ):
        with pytest.raises(PermissionError, match="FENCED"):
            await operation()
    with pytest.raises(PermissionError):
        await saver.aget_tuple({"configurable": {"thread_id": "unknown"}})
    with pytest.raises(PermissionError):
        await saver.adelete_thread("root")
    with pytest.raises(PermissionError):
        [item async for item in saver.alist(None)]


@pytest.mark.asyncio
async def test_provider_uses_java_execution_mapping_and_never_sends_after_fence():
    from efficiency_platform_agent.core.run_context_binding import bind_run_context
    from efficiency_platform_agent.orchestration.context_gate import FencedModelProvider

    class Gate:
        blocked = False

        @asynccontextmanager
        async def guard_execution(self, tenant, execution, backend, namespace):
            assert (tenant, execution) == ("tenant", "java-execution")
            if self.blocked:
                raise PermissionError("MEMORY_THREAD_FENCED")
            yield

    class Provider:
        descriptor = SimpleNamespace(name="fake")
        calls = 0

        async def complete(self, request):
            self.calls += 1
            return "ok"

    gate, provider = Gate(), Provider()
    controlled = FencedModelProvider(provider, gate, "official")
    binding = SimpleNamespace(
        memory_context=SimpleNamespace(
            packet=SimpleNamespace(execution_id="java-execution")
        ),
        conversation=SimpleNamespace(tenant_id="tenant"),
        execution_id="java-execution",
    )
    with bind_run_context(binding):
        assert await controlled.complete(None) == "ok"
        gate.blocked = True
        with pytest.raises(PermissionError):
            await controlled.complete(None)
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_runtime_denies_memory_resume_before_loading_checkpoint_body():
    from efficiency_platform_agent.core.run import JsonObject
    from efficiency_platform_agent.orchestration.runtime import GraphRuntime

    class Gate:
        async def check_runtime(self, runtime, tenant):
            raise PermissionError("MEMORY_THREAD_FENCED")

    class Checkpoints:
        backend_id = "owned-memory"
        reads = 0

        def get(self, *args, **kwargs):
            self.reads += 1
            raise AssertionError("正文不应被读取")

    registration = SimpleNamespace(checkpoint_ns="ns", graph_id="graph")
    graphs = SimpleNamespace(get=lambda mode: registration)
    selection = SimpleNamespace(mode="direct")
    checkpoints = Checkpoints()
    runtime = GraphRuntime(graphs, checkpoint_store=checkpoints, memory_registry=Gate())
    with pytest.raises(PermissionError, match="FENCED"):
        await runtime.get_checkpoint(selection, "run", tenant_id="tenant")
    with pytest.raises(PermissionError, match="CONTINUATION_AUTH_UNSUPPORTED"):
        await runtime.resume(
            selection, "run", "checkpoint", JsonObject(), tenant_id="tenant"
        )
    assert checkpoints.reads == 0
