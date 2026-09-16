"""PostgreSQL 适配器离线契约测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.capabilities.retrieval.postgres import (
    PostgresRetrievalProvider,
)
from efficiency_platform_agent.persistence.postgres import PostgresRuntimeRepository
from efficiency_platform_agent.providers.database.postgres import (
    InvalidPostgresSchema,
    PostgresConcurrencyError,
    PostgresProvider,
)


class FakeConnection:
    def __init__(self, result: list[dict] | None = None) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.result = result or []

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> list[dict]:
        self.calls.append((sql, params))
        return self.result


def test_schema_is_strictly_validated_and_dsn_is_not_in_error() -> None:
    with pytest.raises(InvalidPostgresSchema):
        PostgresProvider(FakeConnection(), "public")


def test_runtime_repository_uses_tenant_parameter_and_placeholders() -> None:
    conn = FakeConnection()
    repo = PostgresRuntimeRepository(conn, "s7_acceptance_abcdef12")
    asyncio.run(repo.append_event("run-1", "tenant-1", {"kind": "run_started"}))
    sql, params = conn.calls[-1]
    assert "tenant_id = %s" in sql
    assert "%" in sql
    assert "tenant-1" not in sql
    assert "tenant-1" in params


def test_runtime_repository_save_carries_expected_version_for_cas() -> None:
    conn = FakeConnection()
    repo = PostgresRuntimeRepository(conn, "s7_acceptance_abcdef12")
    record = type(
        "Record",
        (),
        {
            "run_id": "run-1",
            "request": type("Request", (), {"tenant_id": "tenant-1"})(),
            "status": type("Status", (), {"value": "running"})(),
            "output": None,
        },
    )()

    asyncio.run(repo.save(record, expected_version=3))

    sql, params = conn.calls[-1]
    assert "AND version = %s" in sql
    assert params[-1] == 3


def test_runtime_repository_rejects_zero_row_cas_update() -> None:
    conn = FakeConnection()
    conn.result = SimpleNamespace(rowcount=0)
    repo = PostgresRuntimeRepository(conn, "s7_acceptance_abcdef12")
    record = type(
        "Record",
        (),
        {
            "run_id": "run-1",
            "request": type("Request", (), {"tenant_id": "tenant-1"})(),
            "status": type("Status", (), {"value": "running"})(),
            "output": None,
        },
    )()

    with pytest.raises(PostgresConcurrencyError):
        asyncio.run(repo.save(record, expected_version=3))


def test_runtime_repository_rejects_duplicate_create_without_row_change() -> None:
    conn = FakeConnection()
    conn.result = SimpleNamespace(rowcount=0)
    repo = PostgresRuntimeRepository(conn, "s7_acceptance_abcdef12")
    record = type(
        "Record",
        (),
        {
            "run_id": "run-1",
            "version": 1,
            "request": type(
                "Request",
                (),
                {"tenant_id": "tenant-1", "request_id": "request-1"},
            )(),
            "status": type("Status", (), {"value": "created"})(),
        },
    )()

    with pytest.raises(PostgresConcurrencyError):
        asyncio.run(repo.create(record))


def test_vector_contract_is_fixed_and_fts_is_native() -> None:
    conn = FakeConnection()
    provider = PostgresRetrievalProvider(conn, "s7_acceptance_abcdef12")
    asyncio.run(
        provider.search(
            tenant_id="tenant-1",
            query_vector=[0.0] * 1024,
            query_text="标题",
            top_k=3,
        )
    )
    sql, _ = conn.calls[-1]
    assert "to_tsvector" in sql
    assert "<=>" in sql
    assert "tenant_id = %s" in sql


def test_unknown_schema_and_dimension_are_rejected() -> None:
    conn = FakeConnection()
    with pytest.raises(InvalidPostgresSchema):
        PostgresProvider(conn, "s7_acceptance_abcdef1z")
    with pytest.raises(ValueError):
        PostgresRetrievalProvider(conn, "s7_acceptance_abcdef12", dimension=768)


def test_checkpoint_store_returns_runtime_record_and_resume_binding() -> None:
    from efficiency_platform_agent.orchestration.checkpoint import CheckpointRecord
    from efficiency_platform_agent.orchestration.postgres_checkpoint import (
        PostgresCheckpointStore,
    )

    conn = FakeConnection(
        [
            {
                "checkpoint_id": "checkpoint-1",
                "state": {
                    "next_status": "waiting_input",
                    "resume_binding": {
                        "contract_version": "operation-resume/1",
                        "request_id": "request-1",
                        "plan_revision": 1,
                        "supplemental": {"answer": "合成"},
                        "fence_token": "fence-1",
                    },
                },
            }
        ]
    )
    store = PostgresCheckpointStore(conn, "s7_acceptance_abcdef12")

    record = asyncio.run(store.get("run-1", "s2:direct:1", "tenant-1"))

    assert isinstance(record, CheckpointRecord)
    assert record.view.thread_id == "run-1"
    assert record.view.checkpoint_id == "checkpoint-1"
    assert dict(record.view.resume_binding.items)["request_id"] == "request-1"
    assert conn.calls[-1][1] == ("run-1", "s2:direct:1", "tenant-1")
