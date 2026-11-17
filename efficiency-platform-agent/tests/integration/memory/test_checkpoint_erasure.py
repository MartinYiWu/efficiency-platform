"""真实 PG 隔离 schema 验收；缺显式配置时跳过，不计为真实通过。"""

import os
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import asdict, replace

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, Error, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.pq import PipelineStatus, TransactionStatus
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from efficiency_platform_agent.core.checkpoint_erasure import (
    CheckpointResidue,
    ThreadBinding,
    ThreadErasurePlan,
)
from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    SourceDependency,
)
from efficiency_platform_agent.memory.checkpoint_erasure import CheckpointEraser
from efficiency_platform_agent.orchestration.postgres_checkpoint import (
    OfficialPostgresThreadStore,
    PostgresCheckpointStore,
)


@pytest.fixture
async def pg_erasure():
    dsn = os.environ.get("MEMORY_IT_POSTGRES_DSN")
    if not dsn or os.environ.get("MEMORY_IT_ALLOW_SCHEMA_DDL") != "1":
        pytest.skip(
            "需要显式本机 MEMORY_IT_POSTGRES_DSN 与 MEMORY_IT_ALLOW_SCHEMA_DDL=1"
        )
    try:
        settings = conninfo_to_dict(dsn)
    except Error:
        pytest.fail("MEMORY_IT_POSTGRES_DSN_FORMAT_INVALID", pytrace=False)
    if settings.get("host", "") not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("MEMORY_IT_REQUIRES_EXPLICIT_LOOPBACK_HOST", pytrace=False)
    try:
        connection = await AsyncConnection.connect(
            dsn,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
            connect_timeout=5,
        )
    except Error:
        pytest.fail("MEMORY_IT_POSTGRES_CONNECTION_FAILED", pytrace=False)
    suffix = uuid.uuid4().hex[:8]
    official_schema, owned_schema = (
        "memory_it_checkpoint_" + suffix,
        "agent_runtime_" + suffix,
    )
    created = []
    try:
        for schema in (official_schema, owned_schema):
            await connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
            )
            created.append(schema)
        await connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(official_schema))
        )
        saver = AsyncPostgresSaver(connection)
        await saver.setup()
        await connection.execute(
            sql.SQL(
                "CREATE TABLE {}.checkpoints (thread_id text NOT NULL, tenant_id text NOT NULL, "
                "checkpoint_ns text NOT NULL, checkpoint_id text NOT NULL, state jsonb NOT NULL, "
                "PRIMARY KEY (tenant_id, thread_id, checkpoint_ns))"
            ).format(sql.Identifier(owned_schema))
        )
        await connection.execute(
            "CREATE TABLE erasure_gate (execution_id text PRIMARY KEY, tenant_id text NOT NULL, "
            "state text NOT NULL, revision bigint NOT NULL, thread_ids jsonb NOT NULL)"
        )
        await connection.execute(
            "CREATE TABLE thread_registry (thread_id text PRIMARY KEY, tenant_id text NOT NULL, "
            "execution_id text NOT NULL, parent_thread_id text, dependencies jsonb NOT NULL)"
        )
        yield connection, saver, PostgresCheckpointStore(connection, owned_schema)
    finally:
        await connection.execute("SET search_path TO public")
        for schema in reversed(created):
            await connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )
        await connection.close()


def erasure_plan():
    a, b = (
        SourceDependency("document", "a", "1"),
        SourceDependency("document", "b", "2"),
    )
    return ThreadErasurePlan(
        scope=ExecutionScope(
            ConversationScope(
                "tenant-a",
                "user-a",
                "operations",
                "operations",
                "CONVERSATION",
                "session-a",
            ),
            "task-a",
            "execution-a",
            "subtask-a",
            "answer",
            "operations",
        ),
        operation_id="original-operation",
        execution_revision=1,
        root_thread_id="server-random-root",
        threads=(
            ThreadBinding("server-random-root", None, (a, b)),
            ThreadBinding("server-random-child", "server-random-root", (b,)),
        ),
        gate_state="REVOKED",
        registry_complete=True,
        unique_owner=True,
        write_fenced=True,
        backend_ids=frozenset({"official", "owned"}),
    )


class FixturePostgresRegistry:
    """测试专用登记簿；真实 gate 写入 PG，不代表业务登记簿已实现。"""

    def __init__(self, connection, current):
        self.connection, self.current = connection, current

    async def block_for_erasure(self, scope, source):
        if (
            scope != self.current.scope
            or source not in self.current.threads[0].safety_dependencies
        ):
            return None
        cursor = await self.connection.execute(
            "UPDATE erasure_gate SET state = 'REVOKED' WHERE execution_id = %s AND tenant_id = %s "
            "AND revision = %s RETURNING thread_ids",
            (
                scope.execution_id,
                scope.conversation.tenant_id,
                self.current.execution_revision,
            ),
        )
        row = await cursor.fetchone()
        if row is None or row["thread_ids"] != [
            thread.thread_id for thread in self.current.threads
        ]:
            return None
        cursor = await self.connection.execute(
            "SELECT thread_id, parent_thread_id, dependencies FROM thread_registry "
            "WHERE tenant_id = %s AND execution_id = %s",
            (scope.conversation.tenant_id, scope.execution_id),
        )
        rows = await cursor.fetchall()
        actual = {
            row["thread_id"]: (row["parent_thread_id"], row["dependencies"])
            for row in rows
        }
        expected = {
            thread.thread_id: (
                thread.parent_thread_id,
                [asdict(source) for source in thread.safety_dependencies],
            )
            for thread in self.current.threads
        }
        if actual != expected:
            return None
        return self.current

    async def mark_deleted(self, current, verification):
        assert all(residue.empty for _, _, residue in verification)
        cursor = await self.connection.execute(
            "UPDATE erasure_gate SET state = 'DELETED' WHERE execution_id = %s AND tenant_id = %s "
            "AND revision = %s AND state = 'REVOKED'",
            (
                current.scope.execution_id,
                current.scope.conversation.tenant_id,
                current.execution_revision,
            ),
        )
        return cursor.rowcount == 1


async def seed(connection, saver, owned, current):
    await connection.execute(
        "INSERT INTO erasure_gate VALUES (%s, %s, 'ACTIVE', %s, %s)",
        (
            current.scope.execution_id,
            current.scope.conversation.tenant_id,
            current.execution_revision,
            Jsonb([thread.thread_id for thread in current.threads]),
        ),
    )
    for thread in current.threads:
        await connection.execute(
            "INSERT INTO thread_registry VALUES (%s, %s, %s, %s, %s)",
            (
                thread.thread_id,
                current.scope.conversation.tenant_id,
                current.scope.execution_id,
                thread.parent_thread_id,
                Jsonb([asdict(source) for source in thread.safety_dependencies]),
            ),
        )
    for thread in (
        *[item.thread_id for item in current.threads],
        "other-tenant-thread",
    ):
        for namespace in ("", "subgraph:x"):
            checkpoint = empty_checkpoint()
            checkpoint["channel_values"] = {"mixed": {"source_a": "a", "source_b": "b"}}
            checkpoint["channel_versions"] = {"mixed": "1"}
            config = await saver.aput(
                {"configurable": {"thread_id": thread, "checkpoint_ns": namespace}},
                checkpoint,
                {"source": "input", "step": 0, "parents": {}},
                {"mixed": "1"},
            )
            await saver.aput_writes(
                config, [("pending", {"source_a": "a"})], "pending-task"
            )
        for tenant in ("tenant-a", "tenant-b"):
            for namespace in ("main", "subgraph:x"):
                await owned.save(
                    thread, namespace, {"mixed": ["a", "b"]}, tenant_id=tenant
                )


async def test_real_saver_deletes_all_tables_namespaces_children_after_durable_gate(
    pg_erasure, monkeypatch
):
    connection, saver, owned = pg_erasure
    current = erasure_plan()
    await seed(connection, saver, owned, current)
    official = OfficialPostgresThreadStore(saver)
    registry = FixturePostgresRegistry(connection, current)
    real_delete = saver.adelete_thread
    called = []

    async def delete_after_gate(thread_id):
        cursor = await connection.execute("SELECT state FROM erasure_gate")
        assert (await cursor.fetchone())["state"] == "REVOKED"
        called.append(thread_id)
        await real_delete(thread_id)

    monkeypatch.setattr(saver, "adelete_thread", delete_after_gate)
    for thread in current.threads:
        assert await official.remaining(
            thread.thread_id, "tenant-a", authorization=current
        ) == CheckpointResidue(2, 2, 2)
    result = await CheckpointEraser(registry, (official, owned)).erase(
        current.scope, current.threads[0].safety_dependencies[0]
    )
    assert result.status == "DELETED" and len(result.verification) == 4
    assert set(called) == {thread.thread_id for thread in current.threads}
    assert all(residue.empty for _, _, residue in result.verification)
    cursor = await connection.execute("SELECT state FROM erasure_gate")
    assert (await cursor.fetchone())["state"] == "DELETED"
    for thread in current.threads:
        assert (await owned.remaining(thread.thread_id, "tenant-b")).checkpoints == 2
    cursor = await connection.execute(
        "SELECT count(*) AS count FROM checkpoints WHERE thread_id = %s",
        ("other-tenant-thread",),
    )
    assert (await cursor.fetchone())["count"] == 2


@pytest.mark.parametrize("failure", ["unknown-child", "residual-write", "driver"])
async def test_real_cleanup_failure_keeps_revoked_gate(
    pg_erasure, monkeypatch, failure
):
    connection, saver, owned = pg_erasure
    current = erasure_plan()
    await seed(connection, saver, owned, current)
    if failure == "unknown-child":
        current = replace(current, registry_complete=False)
    registry = FixturePostgresRegistry(connection, current)
    real_delete = saver.adelete_thread

    async def failing_delete(thread_id):
        if failure == "driver":
            raise RuntimeError("injected-driver-failure")
        await real_delete(thread_id)
        if failure == "residual-write":
            await connection.execute(
                "INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob) "
                "VALUES (%s, 'orphan-ns', 'orphan-checkpoint', 'late', 0, 'pending', 'json', %s)",
                (thread_id, b"{}"),
            )

    monkeypatch.setattr(saver, "adelete_thread", failing_delete)
    result = await CheckpointEraser(
        registry, (OfficialPostgresThreadStore(saver), owned)
    ).erase(current.scope, current.threads[0].safety_dependencies[0])
    assert result.status == "DELETE_PENDING"
    cursor = await connection.execute("SELECT state FROM erasure_gate")
    assert (await cursor.fetchone())["state"] == "REVOKED"


@pytest.mark.parametrize("backend", ["official", "owned"])
@pytest.mark.parametrize("external_mode", ["transaction", "begin", "pipeline"])
async def test_real_external_transaction_or_pipeline_refused_without_commit(
    pg_erasure, monkeypatch, backend, external_mode
):
    connection, saver, owned = pg_erasure
    current = erasure_plan()
    await seed(connection, saver, owned, current)
    official = OfficialPostgresThreadStore(saver)
    registry = FixturePostgresRegistry(connection, current)
    blocked = await registry.block_for_erasure(
        current.scope, current.threads[0].safety_dependencies[0]
    )
    assert blocked is current
    marked = False

    async def already_persisted_block(scope, source):
        assert scope == current.scope
        return blocked

    async def record_terminal_attempt(*args):
        nonlocal marked
        marked = True
        return True

    monkeypatch.setattr(registry, "block_for_erasure", already_persisted_block)
    monkeypatch.setattr(registry, "mark_deleted", record_terminal_attempt)
    selected = official if backend == "official" else owned
    stores = (official, owned) if backend == "official" else (owned, official)
    expected = (
        "POSTGRES_ERASURE_PIPELINE_UNSUPPORTED"
        if external_mode == "pipeline"
        else "POSTGRES_ERASURE_IDLE_REQUIRED"
    )
    async with AsyncExitStack() as stack:
        if external_mode == "begin":
            await connection.execute("BEGIN")
            stack.push_async_callback(connection.rollback)
        elif external_mode == "transaction":
            await stack.enter_async_context(connection.transaction())
        else:
            await stack.enter_async_context(connection.pipeline())
        assert connection.autocommit
        if backend == "official":
            with pytest.raises(ValueError, match=expected):
                OfficialPostgresThreadStore(saver)
        for operation in (selected.delete_thread, selected.remaining):
            with pytest.raises(ValueError, match=expected):
                await operation(
                    current.root_thread_id, "tenant-a", authorization=current
                )
        result = await CheckpointEraser(registry, stores).erase(
            current.scope, current.threads[0].safety_dependencies[0]
        )
        assert result.status == "DELETE_PENDING" and not marked
        if external_mode != "pipeline":
            assert connection.info.transaction_status == TransactionStatus.INTRANS
        else:
            assert connection.info.pipeline_status == PipelineStatus.ON
    assert connection.info.transaction_status == TransactionStatus.IDLE
    assert connection.info.pipeline_status == PipelineStatus.OFF
    for thread in current.threads:
        assert await official.remaining(
            thread.thread_id, "tenant-a", authorization=current
        ) == CheckpointResidue(2, 2, 2)
        assert (await owned.remaining(thread.thread_id, "tenant-a")).checkpoints == 2
    cursor = await connection.execute("SELECT state FROM erasure_gate")
    assert (await cursor.fetchone())["state"] == "REVOKED"


@pytest.mark.parametrize("leak_stage", ["delete", "verify"])
async def test_real_saver_nonidle_on_return_never_marks_deleted(
    pg_erasure, monkeypatch, leak_stage
):
    connection, saver, owned = pg_erasure
    current = erasure_plan()
    await seed(connection, saver, owned, current)
    official = OfficialPostgresThreadStore(saver)
    registry = FixturePostgresRegistry(connection, current)
    marked = False

    async def record_terminal_attempt(*args):
        nonlocal marked
        marked = True
        return True

    monkeypatch.setattr(registry, "mark_deleted", record_terminal_attempt)
    if leak_stage == "delete":
        real_delete = saver.adelete_thread

        async def delete_then_begin(thread_id):
            await real_delete(thread_id)
            await connection.execute("BEGIN")

        monkeypatch.setattr(saver, "adelete_thread", delete_then_begin)
    else:
        real_cursor = saver._cursor

        @asynccontextmanager
        async def cursor_then_begin(*, pipeline=False):
            async with real_cursor(pipeline=pipeline) as cursor:
                yield cursor
            if not pipeline:
                await connection.execute("BEGIN")

        monkeypatch.setattr(saver, "_cursor", cursor_then_begin)
    try:
        result = await CheckpointEraser(registry, (official, owned)).erase(
            current.scope, current.threads[0].safety_dependencies[0]
        )
        assert result.status == "DELETE_PENDING" and not marked
        assert connection.info.transaction_status == TransactionStatus.INTRANS
    finally:
        await connection.rollback()
    cursor = await connection.execute("SELECT state FROM erasure_gate")
    assert (await cursor.fetchone())["state"] == "REVOKED"
