"""刷新journal密文隔离与来源摘要验证。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from efficiency_platform_agent.core.memory_execution import MemoryExecutionContext
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.security.memory_packet import memory_packet_digest


@pytest.mark.parametrize("kind", ["WAIT", "REFRESH", "RESULT"])
def test_journal_cipher_binds_scope_wait_and_record_kind(kind):
    cipher = MemorySnapshotCipher("test", {"test": bytes(range(32))})
    scope = (
        "tenant",
        "user",
        "customer-service",
        "customer-service",
        "CONVERSATION",
        "session",
    )
    sealed = cipher.seal_journal(
        scope, "execution", "runtime", "wait", kind, b"private"
    )
    assert (
        cipher.open_journal(scope, "execution", "runtime", "wait", kind, sealed)
        == b"private"
    )
    for changed in (
        (
            scope,
            "execution",
            "runtime",
            "wait",
            "RESULT" if kind != "RESULT" else "WAIT",
        ),
        (scope, "execution", "runtime", "other", "WAIT"),
        (scope, "execution", "other", "wait", "WAIT"),
        (("other", *scope[1:]), "execution", "runtime", "wait", "WAIT"),
    ):
        with pytest.raises(ValueError, match="MEMORY_SNAPSHOT_UNAVAILABLE"):
            cipher.open_journal(*changed, sealed)


def test_journal_cipher_authenticates_immutable_operation_binding():
    cipher = MemorySnapshotCipher("test", {"test": bytes(range(32))})
    scope = (
        "tenant",
        "user",
        "customer-service",
        "customer-service",
        "TASK_ONLY",
        None,
    )
    sealed = cipher.seal_journal(
        scope, "execution", "runtime", "record", "RESULT", b"private", binding="a" * 64
    )
    assert (
        cipher.open_journal(
            scope, "execution", "runtime", "record", "RESULT", sealed, binding="a" * 64
        )
        == b"private"
    )
    with pytest.raises(ValueError, match="MEMORY_SNAPSHOT_UNAVAILABLE"):
        cipher.open_journal(
            scope, "execution", "runtime", "record", "RESULT", sealed, binding="b" * 64
        )


def test_refresh_recomputes_packet_and_semantic_digests():
    from efficiency_platform_agent.memory.context_refresh import (
        validate_refresh_context,
    )

    raw = json.loads(
        (
            Path(__file__).parents[2] / "fixtures/memory_refresh_transport.json"
        ).read_text(encoding="utf-8")
    )["original_context"]
    old = MemoryExecutionContext.from_metadata(
        raw["authorization"] | {"packet": raw["packet"]}
    )
    packet = replace(old.packet, packet_revision=2, issued_at=161, expires_at=190)
    valid = replace(old, packet=packet, packet_digest=memory_packet_digest(packet))
    validate_refresh_context(old, valid, 200, 161)
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        validate_refresh_context(old, replace(valid, packet_digest="0" * 64), 200, 161)
    changed = replace(
        packet, items=(replace(packet.items[0], value="changed"), *packet.items[1:])
    )
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        validate_refresh_context(
            old,
            replace(valid, packet=changed, packet_digest=memory_packet_digest(changed)),
            200,
            161,
        )


def test_send_permit_rejects_missing_packet_or_operation_binding():
    from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
    from efficiency_platform_agent.core.memory_execution import MemorySendPermit

    scope = ExecutionScope(
        ConversationScope(
            "tenant", "user", "customer-service", "customer-service", "TASK_ONLY", None
        ),
        "task",
        "execution",
        "answer",
        "assistant_response",
        "customer-service",
    )
    valid = MemorySendPermit(
        scope,
        "runtime",
        "operation",
        1,
        "a" * 64,
        "manifest",
        "packet",
        1,
        "b" * 64,
        1,
        200,
        "opaque",
    )
    assert valid.scope == scope
    for changes in (
        {"packet_digest": "invalid"},
        {"attempt": 0},
        {"packet_revision": 0},
        {"permit_ref": ""},
    ):
        with pytest.raises(ValueError):
            replace(valid, **changes)


def test_wait_checkpoint_capability_requires_original_scope_and_fingerprint():
    from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
    from efficiency_platform_agent.core.memory_execution import (
        MemoryWaitCheckpointCapability,
    )

    scope = ExecutionScope(
        ConversationScope(
            "tenant", "user", "operations", "operations", "TASK_ONLY", None
        ),
        "task",
        "execution",
        "answer",
        "assistant_response",
        "operations",
    )
    valid = MemoryWaitCheckpointCapability(
        scope, "runtime", "wait", "operation", 1, None, 1, 1, "a" * 64, 200, "opaque"
    )
    for changes in (
        {"current_context_fingerprint": "invalid"},
        {"original_deadline": 0},
        {"wait_event_id": ""},
    ):
        with pytest.raises(ValueError):
            replace(valid, **changes)


def test_refresh_cipher_keeps_execution_key_version_after_default_key_changes():
    cipher = MemorySnapshotCipher(
        "new", {"old": bytes(range(32)), "new": bytes(reversed(range(32)))}
    )
    sealed = cipher.seal(
        "tenant", "execution", "runtime", b"synthetic", key_version="old"
    )
    assert (
        sealed.key_version == "old"
        and cipher.open("tenant", "execution", "runtime", sealed) == b"synthetic"
    )
    without_old = MemorySnapshotCipher("new", {"new": bytes(reversed(range(32)))})
    with pytest.raises(ValueError, match="MEMORY_SNAPSHOT_UNAVAILABLE"):
        without_old.seal(
            "tenant", "execution", "runtime", b"synthetic", key_version="old"
        )


@pytest.mark.asyncio
async def test_checkpoint_capabilities_reject_completed_or_collected_owner_tasks():
    import asyncio
    import gc
    import weakref

    from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
    from efficiency_platform_agent.core.memory_execution import (
        MemoryGraphResumeCapability,
        MemoryWaitCheckpointCapability,
    )
    from efficiency_platform_agent.memory.context_refresh import (
        MemoryContextRefreshService,
    )

    class Payload:
        pass

    release = asyncio.Event()

    async def owner():
        await release.wait()
        return Payload()

    task = asyncio.create_task(owner())
    await asyncio.sleep(0)
    scope = ExecutionScope(
        ConversationScope(
            "tenant", "user", "operations", "operations", "TASK_ONLY", None
        ),
        "task",
        "execution",
        "direct",
        "assistant_response",
        "operations",
    )
    wait = MemoryWaitCheckpointCapability(
        scope, "runtime", "wait", "operation", 1, None, 1, 1, "a" * 64, 200, "opaque"
    )
    resume = MemoryGraphResumeCapability(
        wait, "receipt", "", "actual-checkpoint", 2, "b" * 64, "resume"
    )
    service = MemoryContextRefreshService(None, None)
    service._wait_capabilities[wait.capability_ref] = wait, weakref.ref(task), None
    service._resume_capabilities[resume.capability_ref] = (
        resume,
        weakref.ref(task),
        False,
    )
    assert service.validate_wait_capability(wait) is True
    assert service.validate_wait_capability(replace(wait)) is False
    assert service.validate_wait_scope_task(wait) is False
    release.set()
    await task
    result_ref = weakref.ref(task.result())
    task_ref = weakref.ref(task)
    assert service.validate_wait_capability(wait) is False
    assert await service.consume_resume(resume, {}) is False
    del task
    await asyncio.sleep(0)
    gc.collect()
    assert task_ref() is None and result_ref() is None
    assert service.wait_capability_task(wait) is None
    assert service.validate_wait_capability(wait) is False
    assert await service.consume_resume(resume, {}) is False
