"""I1生产恢复/清理方法反例；仅SQL传输和本机权威为离线替身。"""

from contextlib import asynccontextmanager
from dataclasses import asdict

import pytest

from efficiency_platform_agent.core.memory_thread import ResumeRequest
from efficiency_platform_agent.persistence.memory_execution_registry import (
    PostgresMemoryExecutionRegistry,
)
from tests.integration.memory.test_context_refresh_resume import synthetic_record


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def fetchall(self):
        return self.rows


class Epochs:
    def __init__(self):
        self.calls = []

    async def revoked(self, scope, source, event):
        self.calls.append(event)
        return event == "real-event"


class EmptyBackend:
    backend_id = "official"

    async def entries(self, root):
        return frozenset()


class RegistryTransportProbe(PostgresMemoryExecutionRegistry):
    def __init__(self):
        self.scope, self.record = synthetic_record()
        self.row = {
            "tenant_id": self.scope.conversation.tenant_id,
            "execution_id": self.scope.execution_id,
            "runtime_id": self.record.runtime_id,
            "root_thread_id": self.record.runtime_id,
            "scope": asdict(self.scope),
            "state": "ACTIVE",
            "wait_event_id": "wait",
            "packet_revision": 1,
            "execution_revision": 1,
            "fence_revision": 0,
            "operation_hash": "c" * 64,
            "original_deadline": 1600,
            "registry_complete": True,
            "backend_ids": ["official"],
            "dependencies": [
                asdict(dep) for dep in self.record.context.packet.safety_dependencies
            ],
        }
        self.receipts = {}
        self.clock = lambda: 1001
        self.connection = self
        self.backend_ids = frozenset({"official"})
        self.inventories = (EmptyBackend(),)
        self.source_authority = Epochs()

    @asynccontextmanager
    async def _transaction(self):
        yield

    async def _active(self, row):
        return None

    def _sql(self, query):
        return query

    async def _one(self, query, params):
        if "{execution}" in query:
            return dict(self.row)
        if "{resume}" in query:
            if "starts_with" in query:
                values = sorted(
                    key for key in self.receipts if key.startswith("erase:")
                )
                return self.receipts[values[0]] if values else None
            return self.receipts.get(params[-1])
        raise AssertionError("非预期SQL")

    async def execute(self, query, params):
        if query.startswith("INSERT INTO {resume}"):
            pending = "'DELETE_PENDING'" in query
            self.receipts[params[2]] = {
                "resume_request_id": params[2],
                "request_hash": params[3],
                "result_code": "DELETE_PENDING" if pending else params[4],
                "receipt_ref": params[4] if pending else params[5],
            }
        elif query.startswith("UPDATE {execution}"):
            self.row["state"] = "REVOKED"
            self.row["fence_revision"] += 1
        elif "FROM {member}" in query:
            return Cursor(
                [
                    {
                        "thread_id": self.record.runtime_id,
                        "parent_thread_id": None,
                        "tenant_id": self.row["tenant_id"],
                        "execution_id": self.row["execution_id"],
                        "dependencies": self.row["dependencies"],
                    }
                ]
            )
        elif "FROM {namespace}" in query:
            return Cursor([])
        elif "FROM {resume}" in query:
            return Cursor(list(self.receipts.values()))
        else:
            raise AssertionError("非预期SQL")
        return Cursor([])


@pytest.mark.parametrize(
    "request_id",
    [
        "erase:real-event",
        "erase:000-fake-event",
        '["memory-thread-receipt/2","ERASURE","000-fake-event"]',
    ],
)
async def test_resume_cannot_occupy_or_pollute_actual_erasure_record(request_id):
    registry = RegistryTransportProbe()
    request = ResumeRequest("wait", 1, 1, request_id, "c" * 64, "cpu")
    first = await registry.resume(
        registry.record.runtime_id, registry.scope.conversation.tenant_id, request
    )
    assert (
        await registry.resume(
            registry.record.runtime_id, registry.scope.conversation.tenant_id, request
        )
        == first
    )
    args = (
        registry.scope.conversation.tenant_id,
        registry.scope.execution_id,
        "real-event",
        1,
        (registry.record.context.packet.safety_dependencies[0],),
    )
    assert await registry.prepare_cleanup(*args) is not None
    assert registry.row["state"] == "REVOKED"
    plan = await registry.block_for_erasure(registry.scope, args[-1][0])
    assert plan.registry_complete
    assert "000-fake-event" not in registry.source_authority.calls
    assert len(registry.receipts) == 2


async def test_legacy_receipt_never_becomes_new_authorization_or_unfences_execution():
    registry = RegistryTransportProbe()
    registry.receipts["erase:real-event"] = {
        "resume_request_id": "erase:real-event",
        "request_hash": "a" * 64,
        "result_code": "DELETED",
        "receipt_ref": "legacy-ref",
    }
    source = registry.record.context.packet.safety_dependencies[0]
    with pytest.raises(ValueError, match="MEMORY_RECEIPT_PROTOCOL_UPGRADE_REQUIRED"):
        await registry.prepare_cleanup(
            registry.scope.conversation.tenant_id,
            registry.scope.execution_id,
            "real-event",
            1,
            (source,),
        )
    assert registry.row["state"] == "REVOKED"
    plan = await registry.block_for_erasure(registry.scope, source)
    assert not plan.registry_complete
    assert registry.receipts["erase:real-event"]["receipt_ref"] == "legacy-ref"
