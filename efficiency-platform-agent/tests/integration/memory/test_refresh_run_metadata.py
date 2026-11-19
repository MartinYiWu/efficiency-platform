"""真实 OPS Run 密文授权和 execution 快照的同库安装。"""

import asyncio
import os
from contextlib import AsyncExitStack
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
)
from efficiency_platform_agent.contracts.direct_conversation import (
    DirectConversationSubmission,
)
from efficiency_platform_agent.core.budget import (
    BudgetCharge,
    BudgetState,
    RemainingBudget,
)
from efficiency_platform_agent.core.diagnostics import safe_exception_location
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
from efficiency_platform_agent.core.memory_refresh import (
    MemoryContextResume,
    ResumeMode,
)
from efficiency_platform_agent.core.run import ExecutionBudget, JsonObject, RunRequest
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.core.runtime import RunRecord, UsageSnapshot
from efficiency_platform_agent.memory.context_refresh import MemoryContextRefreshService
from efficiency_platform_agent.memory.execution_authority import (
    MemorySendLeaseAuthority,
)
from efficiency_platform_agent.orchestration.builders.conversation_direct import (
    build_conversation_direct_registration,
)
from efficiency_platform_agent.orchestration.context_gate import MemoryDirectContextGate
from efficiency_platform_agent.orchestration.fenced_checkpoint import (
    FencedCheckpointSaver,
    FencedCheckpointStore,
    OfficialPostgresInventory,
    OwnedPostgresInventory,
)
from efficiency_platform_agent.orchestration.postgres_checkpoint import (
    PostgresCheckpointStore,
)
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime
from efficiency_platform_agent.persistence.memory_context_refresh import (
    MySqlMemoryContextRefreshStore,
)
from efficiency_platform_agent.persistence.memory_execution_registry import (
    PostgresMemoryExecutionRegistry,
)
from efficiency_platform_agent.persistence.mysql_codec import _immutable_object, _plain
from efficiency_platform_agent.persistence.mysql_runtime import MySqlRunRepository
from efficiency_platform_agent.routing.strategy_router import StrategySelection
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.memory.test_context_refresh_resume import checkpoint_serializer
from tests.integration.memory.test_refresh_persistence import refresh_case  # noqa: F401


@pytest.fixture
async def ops_case(refresh_case):  # noqa: F811
    _, csr_record, store, registry, clock = refresh_case
    conversation = replace(
        csr_record.context.packet.scope,
        domain="operations",
        top_level_agent_id="operations",
    )
    packet = replace(
        csr_record.context.packet, scope=conversation, execution_id=uuid4().hex
    )
    context = replace(
        csr_record.context,
        packet=packet,
        policy=replace(
            csr_record.context.policy,
            domain="operations",
            agent_ids=frozenset({"operations"}),
        ),
        execution_grants=(
            MemoryExecutionGrant("direct", "operations", "assistant_response"),
        ),
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    scope = ExecutionScope(
        conversation,
        packet.task_id,
        packet.execution_id,
        "direct",
        "assistant_response",
        "operations",
    )
    runtime = uuid4().hex
    record, _ = await store.claim(context, runtime, "OPERATIONS", "c" * 64, 200)
    clock[0] = 150
    run = RunRecord(
        runtime,
        RunRequest(
            uuid4().hex,
            conversation.tenant_id,
            conversation.user_id,
            "synthetic input",
            _immutable_object(
                {
                    "context_scope": asdict(conversation),
                    "memory_execution": context.metadata(),
                    "context_request_fingerprint": record.request_fingerprint,
                }
            ),
        ),
        RunStatus.RUNNING,
        StrategyMode.DIRECT,
        ExecutionBudget(3, 0, 100, 100, 100000, 100),
        BudgetState(BudgetCharge(), 100000, 200000),
        UsageSnapshot(3, 5, 7, True),
        1,
    )
    repository = MySqlRunRepository(store.engine, store.cipher)
    await repository.create(run)
    official_schema, owned_schema = (
        "agent_runtime_" + uuid4().hex[:8],
        "agent_runtime_" + uuid4().hex[:8],
    )
    from efficiency_platform_agent.providers.database.postgres import (
        validate_agent_owned_schema,
    )

    validate_agent_owned_schema(owned_schema)
    assert len({registry.schema, official_schema, owned_schema}) == 3
    for schema in (official_schema, owned_schema):
        await registry.connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
        )
    try:
        async with AsyncExitStack() as stack:
            official_connection = await stack.enter_async_context(
                await AsyncConnection.connect(
                    os.environ["MEMORY_IT_POSTGRES_DSN"],
                    options="-csearch_path=" + official_schema,
                    autocommit=True,
                    row_factory=dict_row,
                )
            )
            owned_connection = await stack.enter_async_context(
                await AsyncConnection.connect(
                    os.environ["MEMORY_IT_POSTGRES_DSN"],
                    options="-csearch_path=" + owned_schema,
                    autocommit=True,
                    row_factory=dict_row,
                )
            )
            raw = AsyncPostgresSaver(official_connection)
            await raw.setup()
            await owned_connection.execute(
                sql.SQL(
                    "CREATE TABLE {}.checkpoints(thread_id TEXT NOT NULL,tenant_id TEXT NOT NULL,checkpoint_ns TEXT NOT NULL,checkpoint_id TEXT NOT NULL,state JSONB NOT NULL,saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(thread_id,tenant_id,checkpoint_ns))"
                ).format(sql.Identifier(owned_schema))
            )
            owned = PostgresCheckpointStore(owned_connection, owned_schema)
            graph_registry = PostgresMemoryExecutionRegistry(
                registry.connection,
                registry.schema,
                store,
                registry.source_authority,
                (OfficialPostgresInventory(raw), OwnedPostgresInventory(owned)),
                clock=lambda: clock[0],
            )
            await graph_registry.enroll(scope, runtime)
            serializer = checkpoint_serializer()
            saver = FencedCheckpointSaver(
                raw, graph_registry, "official", serializer=serializer
            )
            index = FencedCheckpointStore(owned, graph_registry, serializer=serializer)
            clock[0] = 161
            yield (
                scope,
                record,
                store,
                graph_registry,
                clock,
                repository,
                run,
                saver,
                index,
                stack,
            )
    finally:
        for schema in (official_schema, owned_schema):
            await registry.connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


async def _begin(ops_case, fault_hook=None):
    scope, record, store, registry, _, _, run, saver, index, stack = ops_case
    service = MemoryContextRefreshService(
        registry, MySqlMemoryContextRefreshStore(store), fault_hook=fault_hook
    )
    authority = MemorySendLeaseAuthority(registry, store, "official")
    registry.install_result_authority(authority)
    registry.install_wait_authority(service)
    ready = asyncio.Event()
    hold = asyncio.Event()

    async def on_wait(wait_id, execution_id, runtime_id):
        assert execution_id == scope.execution_id and runtime_id == record.runtime_id
        ready.set()
        await hold.wait()

    gate = MemoryDirectContextGate(
        service,
        store,
        registry,
        authority,
        saver=saver,
        checkpoint_store=index,
        on_wait=on_wait,
    )
    service.frame_verifier = gate.verify_wait_frame
    service.checkpoint_verifier = gate.verify_wait_checkpoint
    saver.install_context_checkpoint_authority(gate)
    index.install_context_checkpoint_authority(gate)

    class NoModel:
        async def complete(self, demand, request, *, remaining_budget):
            pytest.fail("CPU等待期间不得触发Provider")

    async def resolver(request, state):
        return DirectConversationSubmission(
            "direct-conversation/1",
            run.request,
            (),
            run.request.input_text,
            None,
            RemainingBudget(3, 0, 20000, 2000, 100000, 10000),
        )

    graphs = GraphRegistry()
    graphs.register(
        build_conversation_direct_registration(
            GeneralConversationAgent(NoModel()),
            resolver,
            checkpointer=saver,
            memory_gate=gate,
        )
    )

    class SafeDiagnostics:
        def record(self, event):
            if event.error_code is not None:
                print(
                    "RF04_GRAPH_SAFE_FAILURE",
                    event.error_code,
                    event.error_type,
                    event.error_location,
                    flush=True,
                )

    runtime = GraphRuntime(
        graphs, checkpoint_store=index, diagnostic_recorder=SafeDiagnostics()
    )
    runtime.memory_registry = registry
    state = {
        "run_id": record.runtime_id,
        "tenant_id": scope.conversation.tenant_id,
        "user_id": scope.conversation.user_id,
        "request_id": run.request.request_id,
        "input_text": run.request.input_text,
        "strategy_payload_schema_version": "strategy.none/1",
        "strategy_payload": JsonObject(),
        "budget_state": asdict(run.budget_state),
        "output": None,
        "usage": {},
        "model_attempts": [],
        "error_code": None,
        "next_status": None,
    }
    control = RunControl()
    binding = RunContextBinding(
        scope.conversation,
        scope.task_id,
        scope.execution_id,
        record.deadline_epoch_seconds,
        record.context,
    )

    async def invoke():
        with bind_run_context(binding), execution_scope(control):
            return await runtime.execute(
                StrategySelection(StrategyMode.DIRECT, "rf04/1", "cpu-memory-wait"),
                state,
            )

    task = asyncio.create_task(invoke())

    async def cancel_frame():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert control.calls == 0

    stack.push_async_callback(cancel_frame)
    ready_task = asyncio.create_task(ready.wait())
    done, _ = await asyncio.wait(
        (task, ready_task), timeout=5, return_when=asyncio.FIRST_COMPLETED
    )
    if ready_task not in done:
        ready_task.cancel()
        print(
            "RF04_GRAPH_WAIT_STATUS",
            registry.connection.info.transaction_status.name,
            "lock_held",
            registry._lock.locked(),
            "waiters",
            len(registry._lock._waiters or ()),
            flush=True,
        )
        count = 0
        for active in asyncio.all_tasks():
            frames = []
            coroutine = active.get_coro()
            for _ in range(40):
                frame = getattr(coroutine, "cr_frame", None) or getattr(
                    coroutine, "ag_frame", None
                )
                if frame is not None and (
                    "/efficiency_platform_agent/"
                    in frame.f_code.co_filename.replace("\\", "/")
                    or "/tests/integration/memory/"
                    in frame.f_code.co_filename.replace("\\", "/")
                ):
                    frames.append(
                        (
                            Path(frame.f_code.co_filename).name,
                            frame.f_lineno,
                            frame.f_code.co_name,
                        )
                    )
                coroutine = getattr(coroutine, "cr_await", None) or getattr(
                    coroutine, "ag_await", None
                )
                if coroutine is None:
                    break
            if frames:
                print(
                    "RF04_GRAPH_TASK",
                    count,
                    "original_worker",
                    active is task,
                    frames[-8:],
                    flush=True,
                )
                count += 1
                if count == 8:
                    break
        if task.done():
            try:
                result = task.result()
            except Exception as error:  # noqa: BLE001 -- 仅提取异常类型与安全位置，不打印数据库参数。
                raise AssertionError(
                    {
                        "code": "RF04_GRAPH_WAIT_FAILED",
                        "type": type(error).__name__,
                        "location": safe_exception_location(error),
                    }
                ) from None
            raise AssertionError(
                {
                    "code": result.failure.code
                    if result.failure
                    else "RF04_GRAPH_EARLY_END"
                }
            )
        raise AssertionError("RF04_GRAPH_WAIT_TIMEOUT")
    wait = await service.get_wait(scope.conversation, scope.execution_id)
    assert (
        wait is not None
        and wait.checkpoint_id
        and wait.checkpoint_mode.value == "GRAPH"
    )
    wait_id = wait.wait_event_id
    packet = replace(
        record.context.packet, packet_revision=2, issued_at=161, expires_at=190
    )
    context = replace(
        record.context, packet=packet, packet_digest=memory_packet_digest(packet)
    )
    command = MemoryContextResume(
        wait_id,
        1,
        1,
        uuid4().hex,
        record.request_fingerprint,
        ResumeMode.REFRESH,
        False,
        "memory-context-resume/2",
        wait.logical_operation_id,
        None,
        1,
        wait.expected_current_context_fingerprint,
        context,
    )
    return service, command


@pytest.mark.asyncio
async def test_real_ops_snapshot_and_encrypted_run_metadata_commit_together(ops_case):
    scope, record, store, _, _, repository, original, *_ = ops_case

    async def fail(point):
        if point == "after_b":
            raise RuntimeError("RF03_AFTER_B")

    service, command = await _begin(ops_case, fail)
    with pytest.raises(RuntimeError, match="RF03_AFTER_B"):
        await service.resume(scope.conversation, scope.execution_id, command)
    installed = await store.get(scope.conversation.tenant_id, scope.execution_id)
    current = await repository.get(record.runtime_id, scope.conversation.tenant_id)
    assert installed.context == command.refreshed_context
    assert dict(current.request.metadata.items)[
        "memory_execution"
    ] == _immutable_object(command.refreshed_context.metadata())
    assert current.request.input_text == original.request.input_text
    assert (
        current.budget_state == original.budget_state
        and current.usage == original.usage
    )
    assert (
        dict(current.request.metadata.items)["context_request_fingerprint"]
        == record.request_fingerprint
    )
    service.fault_hook = None
    receipt = await service.resume(scope.conversation, scope.execution_id, command)
    assert receipt.code == "CONTEXT_REFRESHED" and receipt.dispatch_allowed is False


@pytest.mark.asyncio
async def test_real_wrong_run_request_anchor_rolls_back_snapshot_install(ops_case):
    scope, record, store, _, _, repository, original, *_ = ops_case
    metadata = _plain(original.request.metadata)
    metadata["context_request_fingerprint"] = "0" * 64
    bad = replace(
        original,
        request=replace(
            original.request,
            metadata=_immutable_object(
                {
                    key: value
                    for key, value in metadata.items()
                    if key != "memory_execution"
                }
                | {"memory_execution": record.context.metadata()}
            ),
        ),
        version=2,
    )
    await repository.save(bad, 1)
    service, command = await _begin(ops_case)
    with pytest.raises((ValueError, PermissionError), match="MEMORY_"):
        await service.resume(scope.conversation, scope.execution_id, command)
    current = await store.get(scope.conversation.tenant_id, scope.execution_id)
    assert current.context == record.context
