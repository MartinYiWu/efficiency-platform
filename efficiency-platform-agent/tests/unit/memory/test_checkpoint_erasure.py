"""D16 独立适配单测；Fake 仅证明端口顺序，不代表持久化验收。"""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from psycopg.pq import PipelineStatus, TransactionStatus

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
from efficiency_platform_agent.orchestration.checkpoint import InMemoryCheckpointStore
from efficiency_platform_agent.orchestration.postgres_checkpoint import (
    OfficialPostgresThreadStore,
    PostgresCheckpointStore,
    _check_erasure_connection_state,
)


def plan() -> ThreadErasurePlan:
    scope = ExecutionScope(
        ConversationScope(
            "tenant-a", "user-a", "operations", "operations", "CONVERSATION", "session"
        ),
        "task",
        "execution",
        "subtask",
        "answer",
        "operations",
    )
    a, b = (
        SourceDependency("document", "a", "1"),
        SourceDependency("document", "b", "2"),
    )
    return ThreadErasurePlan(
        scope=scope,
        operation_id="original-operation",
        execution_revision=7,
        root_thread_id="root",
        threads=(
            ThreadBinding("root", None, (a, b)),
            ThreadBinding("child", "root", (b,)),
        ),
        gate_state="REVOKED",
        registry_complete=True,
        unique_owner=True,
        write_fenced=True,
        backend_ids=frozenset({"official", "owned"}),
    )


class FakeRegistry:
    """模拟持久门禁；只用于离线行为测试。"""

    def __init__(self, current, events):
        self.current, self.events = current, events
        self.deleted = False
        self.finish = True

    async def block_for_erasure(self, scope, source):
        self.events.append("persist-block")
        return self.current

    async def mark_deleted(self, current, verification):
        self.events.append("deleted-cas")
        assert current is self.current
        assert all(residue.empty for _, _, residue in verification)
        self.deleted = self.finish
        return self.finish


class FakeStore:
    """模拟完整状态表计数，不伪装为真实 PostgreSQL driver。"""

    def __init__(self, backend_id, events):
        self.backend_id, self.events = backend_id, events
        self.residue = CheckpointResidue(0, 0, 0)
        self.fail = False

    async def delete_thread(self, thread_id, tenant_id, *, authorization):
        self.events.append(("delete", self.backend_id, thread_id, tenant_id))
        if self.fail:
            raise RuntimeError("private-driver-error")

    async def remaining(self, thread_id, tenant_id, *, authorization):
        self.events.append(("verify", self.backend_id, thread_id, tenant_id))
        return self.residue


async def test_block_then_delete_whole_registered_group_then_verify_and_cas():
    current, events = plan(), []
    registry = FakeRegistry(current, events)
    stores = (FakeStore("official", events), FakeStore("owned", events))
    result = await CheckpointEraser(registry, stores).erase(
        current.scope, current.threads[0].safety_dependencies[0]
    )
    assert result.status == "DELETED"
    assert events[0] == "persist-block" and events[-1] == "deleted-cas"
    assert {
        (entry[1], entry[2])
        for entry in events
        if isinstance(entry, tuple) and entry[0] == "delete"
    } == {
        (backend, thread)
        for backend in ("official", "owned")
        for thread in ("root", "child")
    }
    assert result.plan is current
    assert len(result.verification) == 4


@pytest.mark.parametrize(
    "changes",
    [
        {"registry_complete": False},
        {"unique_owner": False},
        {"write_fenced": False},
        {"gate_state": "ACTIVE"},
        {"backend_ids": frozenset({"unknown"})},
        {
            "threads": (
                ThreadBinding(
                    "root", None, (SourceDependency("document", "other", "1"),)
                ),
            )
        },
        {"root_thread_id": "missing"},
        {
            "threads": (
                ThreadBinding("root", None, (SourceDependency("document", "a", "1"),)),
                ThreadBinding("orphan", "unknown", ()),
            )
        },
        {
            "threads": (
                ThreadBinding("root", None, (SourceDependency("document", "a", "1"),)),
                ThreadBinding("child", "child", ()),
            )
        },
        {
            "threads": (
                ThreadBinding("root", None, (SourceDependency("document", "a", "1"),)),
                ThreadBinding("root", None, ()),
            )
        },
    ],
)
async def test_incomplete_or_unproven_plan_refuses_without_deleting(changes):
    current, events = plan(), []
    registry = FakeRegistry(replace(current, **changes), events)
    result = await CheckpointEraser(
        registry, (FakeStore("official", events), FakeStore("owned", events))
    ).erase(current.scope, current.threads[0].safety_dependencies[0])
    assert result.status == "DELETE_PENDING"
    assert events == ["persist-block"] and not registry.deleted


async def test_foreign_authorized_scope_or_missing_registry_denied():
    current, events = plan(), []
    foreign = replace(current, scope=replace(current.scope, execution_id="foreign"))
    for returned in (foreign, None):
        registry = FakeRegistry(returned, events)
        with pytest.raises(PermissionError, match="ERASURE_SCOPE_DENIED"):
            await CheckpointEraser(registry, (FakeStore("official", events),)).erase(
                current.scope, current.threads[0].safety_dependencies[0]
            )
    assert all(event == "persist-block" for event in events)


@pytest.mark.parametrize(
    "residue",
    [
        CheckpointResidue(1, 0, 0),
        CheckpointResidue(0, 1, 0),
        CheckpointResidue(0, 0, 1),
    ],
)
async def test_any_table_residue_keeps_gate_blocked(residue):
    current, events = plan(), []
    registry = FakeRegistry(current, events)
    official, owned = FakeStore("official", events), FakeStore("owned", events)
    official.residue = residue
    result = await CheckpointEraser(registry, (official, owned)).erase(
        current.scope, current.threads[0].safety_dependencies[0]
    )
    assert result.status == "DELETE_PENDING" and not registry.deleted
    assert "deleted-cas" not in events


async def test_driver_failure_or_changed_revision_cannot_claim_deleted():
    current, events = plan(), []
    registry = FakeRegistry(current, events)
    official, owned = FakeStore("official", events), FakeStore("owned", events)
    official.fail = True
    eraser = CheckpointEraser(registry, (official, owned))
    result = await eraser.erase(
        current.scope, current.threads[0].safety_dependencies[0]
    )
    assert (
        result.status == "DELETE_PENDING"
        and result.error_code == "CHECKPOINT_ERASURE_FAILED"
    )
    assert "private-driver-error" not in repr(result)
    official.fail, registry.finish = False, False
    result = await eraser.erase(
        current.scope, current.threads[0].safety_dependencies[0]
    )
    assert result.status == "DELETE_PENDING" and not registry.deleted


async def test_owned_memory_store_exact_tenant_thread_and_all_namespaces():
    store = InMemoryCheckpointStore()
    for tenant in ("a", "b"):
        for thread in ("root", "other"):
            for namespace in ("main", "child:x"):
                store.save(thread, namespace, {"mixed": ["a", "b"]}, tenant_id=tenant)
    assert (await store.remaining("root", "a")).checkpoints == 2
    await store.delete_thread("root", "a")
    assert (await store.remaining("root", "a")).empty
    assert store.get("root", "child:x", "b") is not None
    assert store.get("other", "main", "a") is not None


async def test_postgres_erasure_rejects_fake_driver():
    store = PostgresCheckpointStore(object(), "agent_runtime_1234abcd")
    with pytest.raises(TypeError, match="REAL_POSTGRES_DRIVER_REQUIRED"):
        await store.delete_thread("root", "tenant")
    with pytest.raises(TypeError, match="REAL_POSTGRES_DRIVER_REQUIRED"):
        await store.remaining("root", "tenant")
    with pytest.raises(TypeError, match="OFFICIAL_POSTGRES_SAVER_REQUIRED"):
        OfficialPostgresThreadStore(object())


@pytest.mark.parametrize(
    "thread_id,tenant_id,changes",
    [
        ("root", "tenant-a", None),
        ("unregistered", "tenant-a", {}),
        ("root", "foreign-tenant", {}),
        ("root", "tenant-a", {"unique_owner": False}),
        ("root", "tenant-a", {"write_fenced": False}),
    ],
)
async def test_official_adapter_refuses_unproven_thread_before_touching_driver(
    thread_id, tenant_id, changes
):
    # 未初始化实例只用于检查参数拒绝顺序，不模拟真实连接。
    store = object.__new__(OfficialPostgresThreadStore)
    authorization = None if changes is None else replace(plan(), **changes)
    for operation in (store.delete_thread, store.remaining):
        with pytest.raises(PermissionError, match="ERASURE_THREAD_NOT_AUTHORIZED"):
            await operation(thread_id, tenant_id, authorization=authorization)


async def test_duplicate_or_missing_backend_cannot_complete():
    current, events = plan(), []
    for stores in ((), (FakeStore("official", events), FakeStore("official", events))):
        registry = FakeRegistry(current, events)
        result = await CheckpointEraser(registry, stores).erase(
            current.scope, current.threads[0].safety_dependencies[0]
        )
        assert result.status == "DELETE_PENDING" and not registry.deleted
    assert events == ["persist-block", "persist-block"]


@pytest.mark.parametrize(
    "transaction,pipeline,error",
    [
        (
            TransactionStatus.ACTIVE,
            PipelineStatus.OFF,
            "POSTGRES_ERASURE_IDLE_REQUIRED",
        ),
        (
            TransactionStatus.INTRANS,
            PipelineStatus.OFF,
            "POSTGRES_ERASURE_IDLE_REQUIRED",
        ),
        (
            TransactionStatus.INERROR,
            PipelineStatus.OFF,
            "POSTGRES_ERASURE_IDLE_REQUIRED",
        ),
        (
            TransactionStatus.UNKNOWN,
            PipelineStatus.OFF,
            "POSTGRES_ERASURE_IDLE_REQUIRED",
        ),
        (
            TransactionStatus.IDLE,
            PipelineStatus.ON,
            "POSTGRES_ERASURE_PIPELINE_UNSUPPORTED",
        ),
        (
            TransactionStatus.IDLE,
            PipelineStatus.ABORTED,
            "POSTGRES_ERASURE_PIPELINE_UNSUPPORTED",
        ),
    ],
)
def test_connection_state_policy_rejects_external_transaction_or_pipeline(
    transaction, pipeline, error
):
    # 这里只测纯状态策略，Fake 不进入真实 driver 检查或执行任何 SQL。
    connection = SimpleNamespace(
        autocommit=True,
        info=SimpleNamespace(transaction_status=transaction, pipeline_status=pipeline),
    )
    with pytest.raises(ValueError, match=error):
        _check_erasure_connection_state(connection)


def test_connection_state_policy_rechecks_current_state_without_committing():
    # 可控只读状态替身没有 commit/rollback，检查不得接管调用方事务。
    state = SimpleNamespace(
        transaction_status=TransactionStatus.IDLE, pipeline_status=PipelineStatus.OFF
    )
    connection = SimpleNamespace(autocommit=True, info=state)
    _check_erasure_connection_state(connection)
    state.transaction_status = TransactionStatus.INTRANS
    with pytest.raises(ValueError, match="POSTGRES_ERASURE_IDLE_REQUIRED"):
        _check_erasure_connection_state(connection)


def test_connection_state_policy_keeps_autocommit_requirement():
    with pytest.raises(ValueError, match="POSTGRES_ERASURE_AUTOCOMMIT_REQUIRED"):
        _check_erasure_connection_state(SimpleNamespace(autocommit=False))
