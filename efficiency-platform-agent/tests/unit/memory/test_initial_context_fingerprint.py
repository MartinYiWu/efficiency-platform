"""纯SQL捕获单元，不mock数据库声称跨库成功；完整metadata指纹必须初次登记。"""

import json
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import MemoryExecutionContext
from efficiency_platform_agent.persistence.memory_execution import _fingerprint
from efficiency_platform_agent.persistence.memory_execution_registry import (
    PostgresMemoryExecutionRegistry,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("graph,refresh", [(True, True), (False, True), (True, False)])
async def test_initial_enrollment_freezes_exact_full_context_fingerprint(
    graph, refresh
):
    data = json.loads(
        (
            Path(__file__).parents[2] / "fixtures/memory_refresh_transport.json"
        ).read_text(encoding="utf-8")
    )
    raw = json.dumps(data["original_context"])
    if not graph:
        raw = raw.replace('"operations"', '"customer-service"')
    context = MemoryContextEnvelope.model_validate_json(raw).to_core()
    context = replace(
        context,
        summary_context_json='{"scope":"原授权😀","summaries":[]}',
        derive_template_json='{"plan_id":"原计划😀"}',
    )
    decoded = MemoryExecutionContext.from_metadata(
        json.loads(json.dumps(context.metadata(), ensure_ascii=False))
    )
    expected = _fingerprint(context.metadata())
    assert decoded == context and _fingerprint(decoded.metadata()) == expected
    packet = context.packet
    scope = ExecutionScope(
        packet.scope,
        packet.task_id,
        packet.execution_id,
        "direct",
        "assistant_response",
        "operations",
    )
    record = SimpleNamespace(
        context=context,
        runtime_id="runtime",
        request_fingerprint="a" * 64,
        execution_revision=1,
        deadline_epoch_seconds=200,
        runtime_kind="CUSTOMER_SERVICE" if not graph else "OPERATIONS",
    )
    registry = object.__new__(PostgresMemoryExecutionRegistry)
    registry.checkpoint_capability = "GRAPH"
    registry._wait_authority = object() if refresh else None
    registry.inventories = ()
    registry.backend_ids = frozenset({"official"})
    captured = []

    async def owner(*args):
        return record

    registry._owner_record = owner

    @asynccontextmanager
    async def transaction():
        yield

    registry._transaction = transaction
    registry._sql = lambda statement: statement

    async def execute(statement, params):
        captured.append((statement, params))

    registry.connection = SimpleNamespace(execute=execute)

    async def one(*args):
        inserted = captured[0]
        has_fp = "current_context_fingerprint" in inserted[0]
        return {
            "runtime_id": "runtime",
            "scope": asdict(scope),
            "operation_hash": record.request_fingerprint,
            "state": "ACTIVE",
            "execution_revision": 1,
            "checkpoint_mode": "GRAPH" if graph else "NONE",
            "root_thread_id": "runtime" if graph else None,
            "backend_ids": [] if not graph else ["official"],
            "current_context_fingerprint": inserted[1][-1] if has_fp else None,
        }

    registry._one = one

    async def members(*args):
        return ()

    async def complete(*args):
        return True

    registry._members = members
    registry._inventory_complete = complete
    await (
        registry.enroll(scope, "runtime")
        if graph
        else registry.enroll_no_checkpoint(scope, "runtime")
    )
    statement, params = captured[0]
    assert ("current_context_fingerprint" in statement) == refresh
    if refresh:
        assert params[-1] == expected
    assert "DO NOTHING" in statement and "DO UPDATE" not in statement
