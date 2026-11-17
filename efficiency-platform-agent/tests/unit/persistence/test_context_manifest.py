from contextlib import asynccontextmanager
from dataclasses import replace
from typing import cast

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.context_ports import (
    ContextMetadata,
    ContextOperation,
)
from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)


class LocalConnection:
    def __init__(self, conn):
        self.conn = conn

    async def execute(self, statement, params):
        return self.conn.execute(statement, params)


class LocalEngine:
    def __init__(self, path):
        self.engine = create_engine("sqlite:///" + str(path))
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE agent_context_operation (tenant_id BLOB, task_id BLOB, execution_id BLOB, operation_id BLOB, input_hash TEXT, status TEXT, deadline INTEGER,latest_attempt INTEGER NOT NULL,receipt_ref TEXT, PRIMARY KEY(tenant_id,task_id,execution_id,operation_id))"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE agent_context_manifest (tenant_id BLOB,task_id BLOB,execution_id BLOB,operation_id BLOB,attempt INTEGER,input_hash TEXT,metadata_json TEXT,PRIMARY KEY(tenant_id,task_id,execution_id,operation_id,attempt))"
                )
            )

    @asynccontextmanager
    async def begin(self):
        with self.engine.begin() as conn:
            yield LocalConnection(conn)

    @asynccontextmanager
    async def connect(self):
        with self.engine.connect() as conn:
            yield LocalConnection(conn)


class Counter:
    def __init__(self):
        self.extra = 0

    def measure(self, request, capacity):
        n = (
            len(str(request.options))
            + sum(len(str(m.content)) for m in request.messages)
            + self.extra
        )
        return TokenMeasurement(n, (("full", n),), "fake", True)


@pytest.fixture
async def setup(tmp_path):
    engine = LocalEngine(tmp_path / "context.db")
    store = MySqlContextManifestStore(cast(AsyncEngine, engine))
    counter = Counter()
    controller = ContextController(counter, store, b"k" * 32, clock=lambda: 10)
    scope = ExecutionScope(
        ConversationScope("t", "u", "operations", "operations", "TASK_ONLY", None),
        "task",
        "exec",
        "sub",
        "answer",
        "operations",
    )
    capacity = ModelCapacity(
        "fake",
        "fake",
        "1",
        1000,
        None,
        100,
        "fake/1",
        "fake/1",
        "none",
        True,
        "offline",
    )
    limits = WindowLimits(1000, None, 100, 0, 900)
    options = JsonObject()
    metadata = ContextMetadata("node", "1", "1", "1", "1", 0, capacity, limits, options)
    operation = ContextOperation("op", 1, 100, True)
    request = ProviderRequest(
        "1", (ProviderMessage("user", "private question"),), options, 1000
    )
    pieces = (
        ContextPiece("question", scope, request.messages, kind="current_request"),
    )
    policy = ContextPolicy("node", "1", scope)

    async def prepare(**changes):
        args = {
            "request_template": request,
            "scope": scope,
            "policy": policy,
            "pieces": pieces,
            "capacity": capacity,
            "limits": limits,
            "metadata": metadata,
            "operation": operation,
        }
        args.update(changes)
        return await controller.prepare(**args)

    prepared = await prepare()
    return locals()


async def test_persists_replays_and_does_not_store_prompt(setup):
    s = setup
    assert await s["prepare"]() == s["prepared"]
    with s["engine"].engine.connect() as conn:
        payload = conn.execute(
            text("SELECT metadata_json FROM agent_context_manifest")
        ).scalar_one()
        assert "private question" not in payload
    reopened = MySqlContextManifestStore(cast(AsyncEngine, s["engine"]))
    receipt = await reopened.get_operation_receipt(s["scope"], "op")
    assert receipt.status == "NOT_SENT"
    assert receipt.deadline_epoch_seconds == 100


async def test_changed_hash_and_new_attempt_cannot_reset_operation(setup):
    s = setup
    changed = replace(s["request"], messages=(ProviderMessage("user", "changed"),))
    with pytest.raises(ValueError, match="CONFLICT_409"):
        await s["prepare"](
            request_template=changed,
            pieces=(replace(s["pieces"][0], messages=changed.messages),),
        )
    next_prepared = await s["prepare"](operation=replace(s["operation"], attempt=2))
    assert (
        next_prepared.manifest.canonical_request_hmac
        == s["prepared"].manifest.canonical_request_hmac
    )
    assert not await s["store"].mark_sending(s["prepared"].manifest, s["operation"])
    with pytest.raises(ValueError, match="ATTEMPT"):
        await s["prepare"](operation=replace(s["operation"], attempt=4))


async def test_sending_cas_unknown_and_late_receipt(setup):
    s = setup
    m = s["prepared"].manifest
    assert await s["store"].mark_sending(m, s["operation"])
    assert not await s["store"].mark_sending(m, s["operation"])
    assert await s["store"].record_receipt(m, "UNKNOWN")
    assert not await s["store"].mark_sending(m, s["operation"])
    assert await s["store"].record_receipt(m, "SUCCEEDED", "late")
    assert not await s["store"].record_receipt(m, "UNKNOWN")
    assert (
        await s["store"].get_operation_receipt(s["scope"], "op")
    ).status == "SUCCEEDED"


async def test_tenant_receipt_isolation(setup):
    s = setup
    other = replace(
        s["scope"], conversation=replace(s["scope"].conversation, tenant_id="other")
    )
    assert await s["store"].get_operation_receipt(other, "op") is None


async def test_first_attempt_must_be_one_and_sent_cannot_advance(setup):
    s = setup
    with pytest.raises(ValueError, match="ATTEMPT"):
        await s["prepare"](
            operation=replace(s["operation"], operation_id="new", attempt=2)
        )
    assert await s["store"].mark_sending(s["prepared"].manifest, s["operation"])
    with pytest.raises(ValueError, match="ATTEMPT|BLOCKED"):
        await s["prepare"](operation=replace(s["operation"], attempt=2))


@pytest.mark.parametrize(
    "field", ["tenant_id", "task_id", "execution_id", "operation_id"]
)
async def test_binary_identity_storage_and_trailing_space_isolation(setup, field):
    s = setup
    scope = s["scope"]
    operation = s["operation"]
    if field == "tenant_id":
        scope = replace(
            scope,
            conversation=replace(
                scope.conversation, tenant_id=scope.conversation.tenant_id + " "
            ),
        )
    elif field == "operation_id":
        operation = replace(operation, operation_id=operation.operation_id + " ")
    else:
        scope = replace(scope, **{field: getattr(scope, field) + " "})
    assert await s["store"].get_operation_receipt(scope, operation.operation_id) is None
    manifest = replace(
        s["prepared"].manifest,
        scope=scope,
        operation_id=operation.operation_id,
        canonical_request_hmac="b" * 64,
    )
    assert await s["store"].save_manifest_once(manifest, operation) == manifest
    assert (await s["store"].get_operation_receipt(s["scope"], "op")).input_hash != (
        await s["store"].get_operation_receipt(scope, operation.operation_id)
    ).input_hash
    with s["engine"].engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tenant_id,task_id,execution_id,operation_id FROM agent_context_operation"
            )
        ).all()
        assert len(rows) == 2
        assert all(type(value) is bytes for row in rows for value in row)
        assert any(
            row[
                ["tenant_id", "task_id", "execution_id", "operation_id"].index(field)
            ].endswith(b" ")
            for row in rows
        )


async def test_binary_identity_preserves_maximum_unicode_length(setup):
    s = setup
    tenant = "😀" * 128
    scope = replace(
        s["scope"], conversation=replace(s["scope"].conversation, tenant_id=tenant)
    )
    manifest = replace(
        s["prepared"].manifest, scope=scope, canonical_request_hmac="c" * 64
    )
    assert await s["store"].save_manifest_once(manifest, s["operation"]) == manifest
    assert (await s["store"].get_operation_receipt(scope, "op")).input_hash == "c" * 64
    with s["engine"].engine.connect() as conn:
        values = (
            conn.execute(text("SELECT tenant_id FROM agent_context_operation"))
            .scalars()
            .all()
        )
        assert tenant.encode("utf-8") in values
        assert len(tenant.encode("utf-8")) == 512


def test_mysql_schema_uses_matching_binary_identity_keys():
    from pathlib import Path

    schema = (
        Path(__file__).resolve().parents[3]
        / "sql/bootstrap/context_control_v1/02-up.sql"
    ).read_text(encoding="utf-8-sig")
    for name in ["tenant_id", "task_id", "execution_id", "operation_id"]:
        assert schema.count(name + " VARBINARY(512) NOT NULL") == 2
    assert "VARCHAR(128) COLLATE utf8mb4_bin" not in schema
