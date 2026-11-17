"""已擦执行不尝试解密；保留显式拒恢复语义。"""

import pytest

from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.persistence.memory_execution import (
    MySqlMemoryExecutionStore,
)
from efficiency_platform_agent.persistence.mysql_runtime import MySqlRunRepository


def test_scrubbed_execution_is_rejected_before_cipher_decode():
    store = MySqlMemoryExecutionStore(
        None, MemorySnapshotCipher("test", {"test": bytes(32)})
    )
    with pytest.raises(ValueError, match="MEMORY_ACCESS_REVOKED"):
        store._decode(
            {"state": "SCRUBBED", "snapshot_ciphertext": None, "snapshot_nonce": None}
        )


def test_scrubbed_run_cannot_decode_as_a_new_unprotected_run():
    repository = MySqlRunRepository(None)
    with pytest.raises(ValueError, match="MEMORY_ACCESS_REVOKED"):
        repository._decode({"memory_scrubbed": True, "request": {"metadata": {}}})
