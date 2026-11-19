"""正式组件必须在打开连接前遵守既有owned-schema命名边界。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from efficiency_platform_agent.harness import memory_runtime
from efficiency_platform_agent.harness.memory_runtime import build_memory_runtime
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.providers.database.postgres import InvalidPostgresSchema


@pytest.mark.asyncio
async def test_invalid_owned_schema_is_rejected_before_any_connection():
    engine = Mock()
    engine.connect.side_effect = AssertionError(
        "schema validation must precede connections"
    )
    with pytest.raises(InvalidPostgresSchema):
        await build_memory_runtime(
            engine=engine,
            memory_cipher=MemorySnapshotCipher("synthetic", {"synthetic": bytes(32)}),
            checkpoint_key=bytes(32),
            checkpoint_key_version="synthetic",
            postgres_dsn="host=127.0.0.1",
            registry_schema="memory_it_registry_12345678",
            official_schema="memory_it_official_12345678",
            owned_schema="agent_runtime_d17_1234567890",
        )
    engine.connect.assert_not_called()


@pytest.mark.parametrize("kind", ["OPERATIONS", "CUSTOMER_SERVICE", "HR"])
async def test_refresh_binding_selects_the_original_runtime_owner(kind):
    direct = SimpleNamespace(update_wait_frame_binding=AsyncMock(return_value=True))
    customer = SimpleNamespace(refresh_memory_binding=AsyncMock(return_value=True))
    updater = memory_runtime.build_memory_binding_updater(direct, customer)
    record, context = SimpleNamespace(runtime_kind=kind), object()
    assert await updater(record, context) is (kind != "HR")
    if kind == "OPERATIONS":
        direct.update_wait_frame_binding.assert_awaited_once_with(record, context)
        customer.refresh_memory_binding.assert_not_awaited()
    elif kind == "CUSTOMER_SERVICE":
        customer.refresh_memory_binding.assert_awaited_once_with(record, context)
        direct.update_wait_frame_binding.assert_not_awaited()
    else:
        customer.refresh_memory_binding.assert_not_awaited()
        direct.update_wait_frame_binding.assert_not_awaited()


async def test_refresh_binding_never_falls_through_to_another_agent():
    customer = SimpleNamespace(refresh_memory_binding=AsyncMock(return_value=True))
    updater = memory_runtime.build_memory_binding_updater(None, customer)
    assert await updater(SimpleNamespace(runtime_kind="OPERATIONS"), object()) is False
    customer.refresh_memory_binding.assert_not_awaited()
