"""内部认证完成后保存的原执行授权；不从模型或公开请求解析权限。"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .memory import (
    ConversationScope,
    MemoryContextPacket,
    MemoryPolicy,
    MemoryReference,
    SourceDependency,
    require_id,
)
from .run import JsonObject


@dataclass(frozen=True, slots=True)
class MemoryExecutionGrant:
    node_id: str
    execution_agent_id: str
    purpose: str

    def __post_init__(self) -> None:
        for value in (self.node_id, self.execution_agent_id, self.purpose):
            require_id(value)


@dataclass(frozen=True, slots=True)
class MemoryExecutionContext:
    packet: MemoryContextPacket = field(repr=False)
    policy: MemoryPolicy
    execution_grants: tuple[MemoryExecutionGrant, ...]
    deadline_epoch_seconds: int
    packet_digest: str
    semantic_snapshot_digest: str
    request_digest: str
    input_dependencies: tuple[SourceDependency, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.packet, MemoryContextPacket) or not isinstance(
            self.policy, MemoryPolicy
        ):
            raise TypeError("MEMORY_EXECUTION_INVALID")
        if (
            not self.policy.enabled
            or self.policy.domain != self.packet.scope.domain
            or self.policy.version != self.packet.policy_version
            or self.packet.scope.top_level_agent_id not in self.policy.agent_ids
            or type(self.deadline_epoch_seconds) is not int
            or self.deadline_epoch_seconds < self.packet.expires_at
        ):
            raise ValueError("MEMORY_EXECUTION_INVALID")
        if (
            not self.execution_grants
            or len({grant.node_id for grant in self.execution_grants})
            != len(self.execution_grants)
            or any(
                grant.execution_agent_id not in self.policy.agent_ids
                for grant in self.execution_grants
            )
        ):
            raise ValueError("MEMORY_EXECUTION_GRANT_INVALID")
        if type(self.input_dependencies) is not tuple or not set(
            self.input_dependencies
        ).issubset(self.packet.safety_dependencies):
            raise ValueError("MEMORY_INPUT_DEPENDENCIES_INVALID")
        for digest in (
            self.packet_digest,
            self.semantic_snapshot_digest,
            self.request_digest,
        ):
            if (
                type(digest) is not str
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("MEMORY_DIGEST_INVALID")

    def metadata(self) -> dict[str, Any]:
        def plain(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: plain(child) for key, child in value.items()}
            if isinstance(value, frozenset):
                return sorted(value)
            if isinstance(value, (tuple, list)):
                return [plain(child) for child in value]
            return value

        return plain(asdict(self))

    @classmethod
    def from_metadata(cls, value: object) -> "MemoryExecutionContext":
        def plain(item: Any) -> Any:
            if isinstance(item, JsonObject):
                return {key: plain(child) for key, child in item.items}
            if isinstance(item, Mapping):
                return {key: plain(child) for key, child in item.items()}
            if isinstance(item, (tuple, list)):
                return [plain(child) for child in item]
            return item

        data = plain(value)
        if not isinstance(data, dict):
            raise TypeError("MEMORY_EXECUTION_METADATA_INVALID")
        packet = dict(data.pop("packet"))
        packet["scope"] = ConversationScope(**packet["scope"])
        packet["safety_dependencies"] = tuple(
            SourceDependency(**dep) for dep in packet["safety_dependencies"]
        )
        packet["items"] = tuple(
            MemoryReference(
                **(
                    item
                    | {
                        "safety_dependencies": tuple(
                            SourceDependency(**dep)
                            for dep in item["safety_dependencies"]
                        )
                    }
                )
            )
            for item in packet["items"]
        )
        policy = dict(data.pop("policy"))
        for key in (
            "agent_ids",
            "readable_layers",
            "writable_kinds",
            "allowed_scopes",
            "field_allowlist",
            "sensitivity_levels",
            "source_types",
        ):
            policy[key] = frozenset(policy[key])
        grants = tuple(
            MemoryExecutionGrant(**grant) for grant in data.pop("execution_grants")
        )
        data["input_dependencies"] = tuple(
            SourceDependency(**dep) for dep in data.get("input_dependencies", ())
        )
        return cls(
            packet=MemoryContextPacket(**packet),
            policy=MemoryPolicy(**policy),
            execution_grants=grants,
            **data,
        )


@dataclass(frozen=True, slots=True)
class MemoryExecutionRecord:
    context: MemoryExecutionContext = field(repr=False)
    runtime_id: str
    runtime_kind: str
    request_fingerprint: str
    deadline_epoch_seconds: int
    state: str
    execution_revision: int
    grant_epoch: int
    source_epoch: int
    deletion_epoch: int


@dataclass(frozen=True, slots=True)
class MemoryInvalidation:
    tenant_id: str
    execution_id: str
    event_id: str
    expected_execution_revision: int
    grant_epoch: int
    source_epoch: int
    deletion_epoch: int

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.execution_id, self.event_id):
            require_id(value)
        for count in (
            self.expected_execution_revision,
            self.grant_epoch,
            self.source_epoch,
            self.deletion_epoch,
        ):
            if type(count) is not int or count < 0:
                raise ValueError("MEMORY_INVALIDATION_INVALID")


class MemoryExecutionStore(Protocol):
    async def claim(
        self,
        context: MemoryExecutionContext,
        runtime_id: str,
        runtime_kind: str,
        request_fingerprint: str,
        budget_deadline: int,
    ) -> tuple[MemoryExecutionRecord, bool]: ...

    async def get(
        self, tenant_id: str, execution_id: str
    ) -> MemoryExecutionRecord | None: ...

    async def invalidate(self, event: MemoryInvalidation) -> str: ...
