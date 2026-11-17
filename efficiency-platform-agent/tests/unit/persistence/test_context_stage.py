import asyncio
import importlib.util
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import cast

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope


def test_persistent_stage_store_is_available():
    assert (
        importlib.util.find_spec("efficiency_platform_agent.persistence.context_stage")
        is not None
    )


class LocalConnection:
    def __init__(self, connection):
        self.connection = connection

    async def execute(self, statement, params):
        return await asyncio.to_thread(self.connection.execute, statement, params)


class LocalEngine:
    def __init__(self, path):
        self.engine = create_engine(
            "sqlite:///" + str(path),
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE agent_context_stage (tenant_id BLOB,task_id BLOB,execution_id BLOB,stage_id BLOB,scope_hash TEXT NOT NULL,semantic_hash TEXT NOT NULL,deadline INTEGER NOT NULL,current_slot INTEGER NOT NULL,status TEXT NOT NULL,operation_id_1 TEXT NOT NULL,operation_id_2 TEXT NOT NULL,operation_id_3 TEXT NOT NULL,PRIMARY KEY(tenant_id,task_id,execution_id,stage_id))"
                )
            )

    @asynccontextmanager
    async def begin(self):
        context = self.engine.begin()
        connection = await asyncio.to_thread(context.__enter__)
        try:
            yield LocalConnection(connection)
        except BaseException:
            await asyncio.to_thread(context.__exit__, *sys.exc_info())
            raise
        else:
            await asyncio.to_thread(context.__exit__, None, None, None)


@pytest.fixture
async def setup(tmp_path):
    from efficiency_platform_agent.persistence.context_stage import (
        MySqlContextStageStore,
    )

    engine = LocalEngine(tmp_path / "stage.db")
    store = MySqlContextStageStore(cast(AsyncEngine, engine), b"k" * 32)
    scope = ExecutionScope(
        ConversationScope("t", "u", "operations", "operations", "TASK_ONLY", None),
        "task",
        "exec",
        "sub",
        "answer",
        "operations",
    )
    return store, scope, engine


async def test_reentry_and_concurrent_claims_share_one_slot(setup):
    store, scope, engine = setup
    slots = await asyncio.gather(
        *(store.claim(scope, "stage", "semantic", 100) for _ in range(8))
    )
    assert len(set(slots)) == 1
    assert slots[0].slot == 1
    with engine.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT operation_id_1,operation_id_2,operation_id_3,current_slot FROM agent_context_stage"
            )
        ).one()
        assert len(set(row[:3])) == 3
        assert slots[0].operation_id == row[0]
        assert row[3] == 1


async def test_only_invalid_advances_fixed_three_slots(setup):
    store, scope, engine = setup
    first = await store.claim(scope, "stage", "semantic", 100)
    with engine.engine.connect() as conn:
        fixed = conn.execute(
            text(
                "SELECT operation_id_1,operation_id_2,operation_id_3 FROM agent_context_stage"
            )
        ).one()
    for index in range(1, 4):
        slot = await store.claim(scope, "stage", "semantic", 100)
        assert slot.slot == index
        assert slot.operation_id == fixed[index - 1]
        assert await store.transition(scope, "stage", index, "CLAIMED", "RETURNED")
        assert await store.transition(scope, "stage", index, "RETURNED", "INVALID")
    with pytest.raises(ValueError, match="EXHAUSTED"):
        await store.claim(scope, "stage", "semantic", 100)
    assert first.operation_id == fixed[0]


async def test_invalid_concurrent_claims_advance_exactly_once(setup):
    store, scope, _ = setup
    await store.claim(scope, "stage", "semantic", 100)
    assert await store.transition(scope, "stage", 1, "CLAIMED", "RETURNED")
    assert await store.transition(scope, "stage", 1, "RETURNED", "INVALID")
    slots = await asyncio.gather(
        *(store.claim(scope, "stage", "semantic", 100) for _ in range(8))
    )
    assert len(set(slots)) == 1
    assert slots[0].slot == 2


@pytest.mark.parametrize("state", ["RETURNED", "SUCCEEDED", "UNKNOWN"])
async def test_returned_and_terminal_states_do_not_create_another_slot(setup, state):
    store, scope, _ = setup
    await store.claim(scope, "stage", "semantic", 100)
    if state == "UNKNOWN":
        assert await store.transition(scope, "stage", 1, "CLAIMED", "UNKNOWN")
    else:
        assert await store.transition(scope, "stage", 1, "CLAIMED", "RETURNED")
        if state == "SUCCEEDED":
            assert await store.transition(scope, "stage", 1, "RETURNED", "SUCCEEDED")
    with pytest.raises(ValueError, match="BLOCKED"):
        await store.claim(scope, "stage", "semantic", 100)


async def test_out_of_order_and_unknown_transitions_cannot_progress(setup):
    store, scope, _ = setup
    original = await store.claim(scope, "stage", "semantic", 100)
    assert not await store.transition(scope, "stage", 2, "CLAIMED", "RETURNED")
    assert not await store.transition(scope, "stage", 1, "RETURNED", "INVALID")
    assert not await store.transition(scope, "stage", 1, "CLAIMED", "INVALID")
    assert not await store.transition(scope, "stage", 1, "CLAIMED", "FAILED")
    assert await store.claim(scope, "stage", "semantic", 100) == original
    assert await store.transition(scope, "stage", 1, "CLAIMED", "UNKNOWN")
    assert not await store.transition(scope, "stage", 1, "UNKNOWN", "INVALID")
    assert not await store.transition(scope, "stage", 1, "UNKNOWN", "SUCCEEDED")


@pytest.mark.parametrize("semantic,deadline", [("changed", 100), ("semantic", 101)])
async def test_original_semantic_and_deadline_cannot_change(setup, semantic, deadline):
    store, scope, _ = setup
    await store.claim(scope, "stage", "semantic", 100)
    with pytest.raises(ValueError, match="CONFLICT_409"):
        await store.claim(scope, "stage", semantic, deadline)


async def test_full_scope_mismatch_cannot_read_or_transition_stage(setup):
    store, scope, _ = setup
    await store.claim(scope, "stage", "semantic", 100)
    other = replace(scope, conversation=replace(scope.conversation, user_id="other"))
    with pytest.raises(ValueError, match="CONFLICT_409"):
        await store.claim(other, "stage", "semantic", 100)
    assert not await store.transition(other, "stage", 1, "CLAIMED", "RETURNED")


@pytest.mark.parametrize("field", ["tenant_id", "task_id", "execution_id", "stage_id"])
async def test_binary_identity_trailing_space_isolation(setup, field):
    store, scope, engine = setup
    initial = await store.claim(scope, "stage", "semantic", 100)
    stage = "stage"
    if field == "tenant_id":
        scope = replace(scope, conversation=replace(scope.conversation, tenant_id="t "))
    elif field == "stage_id":
        stage += " "
    else:
        scope = replace(scope, **{field: getattr(scope, field) + " "})
    other = await store.claim(scope, stage, "semantic", 100)
    assert other.operation_id != initial.operation_id
    with engine.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tenant_id,task_id,execution_id,stage_id FROM agent_context_stage"
            )
        ).all()
        assert len(rows) == 2
        assert all(type(value) is bytes for row in rows for value in row)


async def test_unicode_identity_and_restart_keep_fixed_operations(setup):
    from efficiency_platform_agent.persistence.context_stage import (
        MySqlContextStageStore,
    )

    store, scope, engine = setup
    scope = replace(
        scope, conversation=replace(scope.conversation, tenant_id="😀" * 128)
    )
    first = await store.claim(scope, "阶段 ", "semantic", 100)
    restarted = MySqlContextStageStore(cast(AsyncEngine, engine), b"k" * 32)
    assert await restarted.claim(scope, "阶段 ", "semantic", 100) == first
    with engine.engine.connect() as conn:
        assert (
            conn.execute(text("SELECT tenant_id FROM agent_context_stage")).scalar_one()
            == ("😀" * 128).encode()
        )


def test_schema_uses_exact_binary_identity_and_controlled_states():
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[3] / "sql/bootstrap/context_stage_v1/02-up.sql"
    ).read_text(encoding="utf-8-sig")
    for field in ["tenant_id", "task_id", "execution_id", "stage_id"]:
        assert field + " VARBINARY(512) NOT NULL" in sql
    for state in ["CLAIMED", "RETURNED", "SUCCEEDED", "INVALID", "UNKNOWN"]:
        assert "'" + state + "'" in sql


async def test_concurrent_transitions_are_compare_and_swap(setup):
    store, scope, _ = setup
    await store.claim(scope, "stage", "semantic", 100)
    outcomes = await asyncio.gather(
        *(store.transition(scope, "stage", 1, "CLAIMED", "RETURNED") for _ in range(8))
    )
    assert outcomes.count(True) == 1
    assert not await store.transition(scope, "stage", 1, "CLAIMED", "RETURNED")


@pytest.mark.parametrize("key", [b"", b"x" * 31, "x" * 32, None])
def test_missing_or_weak_production_secret_is_rejected(key):
    from efficiency_platform_agent.persistence.context_stage import (
        MySqlContextStageStore,
    )

    with pytest.raises(ValueError, match="HMAC_KEY_INVALID"):
        MySqlContextStageStore(None, key)


async def test_changed_secret_cannot_rebind_existing_stage(setup):
    from efficiency_platform_agent.persistence.context_stage import (
        MySqlContextStageStore,
    )

    store, scope, engine = setup
    await store.claim(scope, "stage", "semantic", 100)
    other = MySqlContextStageStore(
        cast(AsyncEngine, engine), b"different-stable-key-for-stage" * 2
    )
    with pytest.raises(ValueError, match="CONFLICT_409"):
        await other.claim(scope, "stage", "semantic", 100)


async def test_database_failure_is_not_replaced_by_memory_store(setup):
    from sqlalchemy.exc import OperationalError

    store, scope, engine = setup
    with engine.engine.begin() as conn:
        conn.execute(text("DROP TABLE agent_context_stage"))
    with pytest.raises(OperationalError):
        await store.claim(scope, "stage", "semantic", 100)
