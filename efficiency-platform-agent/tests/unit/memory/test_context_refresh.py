"""刷新journal密文隔离与来源摘要验证。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from efficiency_platform_agent.core.memory_execution import MemoryExecutionContext
from efficiency_platform_agent.persistence.memory_cipher import MemorySnapshotCipher
from efficiency_platform_agent.security.memory_packet import memory_packet_digest


def test_journal_cipher_binds_scope_wait_and_record_kind():
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
        scope, "execution", "runtime", "wait", "WAIT", b"private"
    )
    assert (
        cipher.open_journal(scope, "execution", "runtime", "wait", "WAIT", sealed)
        == b"private"
    )
    for changed in (
        (scope, "execution", "runtime", "wait", "RESULT"),
        (scope, "execution", "runtime", "other", "WAIT"),
        (scope, "execution", "other", "wait", "WAIT"),
        (("other", *scope[1:]), "execution", "runtime", "wait", "WAIT"),
    ):
        with pytest.raises(ValueError, match="MEMORY_SNAPSHOT_UNAVAILABLE"):
            cipher.open_journal(*changed, sealed)


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
