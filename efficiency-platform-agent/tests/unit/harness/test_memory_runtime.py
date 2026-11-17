"""正式组件必须在打开连接前遵守既有owned-schema命名边界。"""

from unittest.mock import Mock

import pytest

from efficiency_platform_agent.harness.memory_runtime import build_memory_runtime
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.providers.database.postgres import InvalidPostgresSchema


@pytest.mark.asyncio
async def test_invalid_owned_schema_is_rejected_before_any_connection():
    engine = Mock()
    engine.connect.side_effect = AssertionError("schema validation must precede connections")
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
