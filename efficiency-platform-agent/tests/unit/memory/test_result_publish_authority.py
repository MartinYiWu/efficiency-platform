"""已有结果scope内复核当前事实，不以新PG事务重入或离开scope后沿用许可。"""

import asyncio

import pytest

from efficiency_platform_agent.core.context_dispatch import ResultPublishDenied
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.run_context_binding import bind_run_context
from efficiency_platform_agent.memory.execution_authority import (
    MemorySendLeaseAuthority,
)
from tests.unit.memory.test_send_lease_authority import Registry, case


async def test_current_result_guard_rechecks_after_io_and_rejects_escaped_scope():
    binding, _, record, prepared, operation = case()

    class Store:
        async def get(self, *args):
            return record

    class FreshRegistry(Registry):
        reads = 0
        stop_after_read = False

        async def revalidate_result_checkpoint(self, permit, result_ref):
            assert self.checkpoint_permit is permit and result_ref == "captured-ref"
            self.reads += 1
            await asyncio.sleep(0)
            if self.stop_after_read:
                control.stop()

    registry = FreshRegistry()
    authority = MemorySendLeaseAuthority(registry, Store(), "official")
    control = RunControl()
    with (
        bind_run_context(binding),
        execution_scope(control),
        pytest.raises(ResultPublishDenied),
    ):
        authority.result_publish_guard(object(), "forged-ref")
    with bind_run_context(binding), execution_scope(control):
        async with authority.graph_scope("runtime"):
            async with authority.acquire():
                permit = await authority.issue(prepared, operation)
            authority.response_received(permit, complete=True)
            authority.result_captured(permit, "captured-ref")
            async with authority.checkpoint_scope(
                permit, "captured-ref", "official", ""
            ):
                guard = authority.result_publish_guard(permit, "captured-ref")
                await guard.check("runtime")
                assert registry.reads == 1
                with pytest.raises(ResultPublishDenied):
                    await guard.check("foreign-runtime")
                assert registry.reads == 1
                registry.stop_after_read = True
                with pytest.raises(ResultPublishDenied):
                    await guard.check("runtime")
                assert registry.reads == 2
            with pytest.raises(ResultPublishDenied):
                await guard.check("runtime")
            assert registry.reads == 2
