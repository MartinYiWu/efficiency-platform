from dataclasses import replace

import pytest

from efficiency_platform_agent.core.memory import MemoryReference, SourceDependency
from efficiency_platform_agent.memory.packet_reader import PacketMemoryReader
from efficiency_platform_agent.security.memory_packet import (
    AuthorizedMemoryPacketValidator,
    MemoryPacketBinding,
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.unit.memory import test_packet_reader as packet_cases

case = packet_cases.case
FixedLocalAuthority = packet_cases.FixedLocalAuthority


def reader(case, item):
    packet = replace(
        case["packet"], items=(item,), safety_dependencies=item.safety_dependencies
    )
    authorization = replace(
        case["authorization"],
        policy=replace(
            case["authorization"].policy,
            source_types=frozenset(dep.source_type for dep in item.safety_dependencies),
        ),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    binding = MemoryPacketBinding(
        packet.packet_id,
        packet.packet_revision,
        packet.execution_revision,
        packet.grant_epoch,
        packet.source_epoch,
        packet.deletion_epoch,
        memory_packet_digest(packet),
        packet.safety_dependencies,
    )
    authority = FixedLocalAuthority(binding)
    return (
        PacketMemoryReader(
            AuthorizedMemoryPacketValidator(authorization, authority, clock=lambda: 110)
        ),
        packet,
        authority,
    )


@pytest.mark.asyncio
async def test_shared_preference_preserves_grant_and_all_original_dependencies(case):
    deps = (
        SourceDependency("USER_PREFERENCE_DECISION", "decision", "v1"),
        SourceDependency("MEMORY_SHARE_GRANT", "projection", "1"),
    )
    item = MemoryReference("share:projection", "v1", "response.language", "zh-CN", deps)
    port, packet, authority = reader(case, item)
    selected = await port.read(
        case["scope"], packet, frozenset({"response.language"}), case["operation"]
    )
    assert set(selected.safety_dependencies) == set(deps)
    authority.binding = None
    with pytest.raises(ValueError, match="MEMORY_ACCESS_REVOKED"):
        await port.read(
            case["scope"], packet, frozenset({"response.language"}), case["operation"]
        )


@pytest.mark.asyncio
async def test_missing_grant_and_chat_derived_shared_value_are_rejected(case):
    for deps in (
        (SourceDependency("USER_PREFERENCE_DECISION", "decision", "v1"),),
        (
            SourceDependency("USER_PREFERENCE_DECISION", "decision", "v1"),
            SourceDependency("MEMORY_SHARE_GRANT", "projection", "1"),
            SourceDependency("MESSAGE", "other-session", "1"),
        ),
    ):
        item = MemoryReference(
            "share:projection", "v1", "response.language", "zh-CN", deps
        )
        port, packet, _ = reader(case, item)
        with pytest.raises(ValueError, match="MEMORY_SHARE_GRANT_REQUIRED"):
            await port.read(
                case["scope"],
                packet,
                frozenset({"response.language"}),
                case["operation"],
            )
