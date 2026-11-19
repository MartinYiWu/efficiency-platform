"""选择已认证绑定包的白名单偏好，继承所有实际输入的安全依赖。"""

from types import MappingProxyType

from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    MemoryContextPacket,
    SourceDependency,
    require_dependencies,
)
from efficiency_platform_agent.core.memory_read import MemorySelection
from efficiency_platform_agent.security.memory_packet import (
    AuthorizedMemoryPacketValidator,
)

PREFERENCE_VALUES = MappingProxyType(
    {
        "response.language": frozenset({"zh-CN", "en-US"}),
        "response.detail_level": frozenset({"concise", "standard", "detailed"}),
        "response.format": frozenset({"prose", "bullets", "table"}),
    }
)


class PacketMemoryReader:
    def __init__(self, validator: AuthorizedMemoryPacketValidator) -> None:
        self._validator = validator

    async def read(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket,
        fields: frozenset[str],
        operation: ContextOperation,
    ) -> MemorySelection:
        if type(fields) is not frozenset or not fields.issubset(PREFERENCE_VALUES):
            raise ValueError("MEMORY_FIELD_DENIED")
        await self._validator.validate(scope, packet, (), operation)
        policy = self._validator.authorization.policy
        if not fields.issubset(policy.field_allowlist):
            raise ValueError("MEMORY_FIELD_DENIED")
        seen: set[str] = set()
        for item in packet.items:
            if (
                item.field_key not in PREFERENCE_VALUES
                or item.field_key not in policy.field_allowlist
                or item.field_key in seen
            ):
                raise ValueError("MEMORY_FIELD_DENIED_OR_DUPLICATE")
            if item.value not in PREFERENCE_VALUES[item.field_key]:
                raise ValueError("MEMORY_VALUE_DENIED")
            if not item.safety_dependencies:
                raise ValueError("MEMORY_ITEM_DEPENDENCIES_REQUIRED")
            grants = tuple(
                dep
                for dep in item.safety_dependencies
                if dep.source_type == "MEMORY_SHARE_GRANT"
            )
            if item.item_id.startswith("share:"):
                if (
                    len(grants) != 1
                    or grants[0].source_id != item.item_id.removeprefix("share:")
                    or scope.conversation.domain == "hr"
                    or not any(
                        dep.source_type == "USER_PREFERENCE_DECISION"
                        for dep in item.safety_dependencies
                    )
                    or any(
                        dep.source_type
                        not in {"MEMORY_SHARE_GRANT", "USER_PREFERENCE_DECISION"}
                        for dep in item.safety_dependencies
                    )
                ):
                    raise ValueError("MEMORY_SHARE_GRANT_REQUIRED")
            elif grants:
                raise ValueError("MEMORY_SHARE_GRANT_BINDING_INVALID")
            seen.add(item.field_key)
        items = tuple(item for item in packet.items if item.field_key in fields)
        dependencies = inherit_safety_dependencies(
            tuple(item.safety_dependencies for item in items),
            authorized_dependencies=packet.safety_dependencies,
        )
        return MemorySelection(items, dependencies)


def inherit_safety_dependencies(
    actual_inputs: tuple[tuple[SourceDependency, ...], ...],
    *,
    authorized_dependencies: tuple[SourceDependency, ...],
    display_citations: tuple[SourceDependency, ...] = (),
) -> tuple[SourceDependency, ...]:
    require_dependencies(authorized_dependencies)
    require_dependencies(display_citations)
    if type(actual_inputs) is not tuple:
        raise ValueError("MEMORY_DEPENDENCIES_INVALID")
    dependencies: set[SourceDependency] = set()
    for actual_input in actual_inputs:
        require_dependencies(actual_input)
        dependencies.update(actual_input)
    if not dependencies.issubset(authorized_dependencies):
        raise ValueError("MEMORY_DEPENDENCIES_UNAUTHORIZED")
    return tuple(
        sorted(
            dependencies,
            key=lambda dep: (
                dep.source_type,
                dep.source_id,
                dep.source_version,
                dep.grant_epoch,
                dep.source_epoch,
                dep.deletion_epoch,
            ),
        )
    )
