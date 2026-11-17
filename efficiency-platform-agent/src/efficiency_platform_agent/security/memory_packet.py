"""独立可信授权绑定与包 CPU 核验，不签发凭据或访问外部服务。"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from efficiency_platform_agent.core.context_ports import ContextOperation
from efficiency_platform_agent.core.memory import (
    ExecutionScope,
    MemoryContextPacket,
    MemoryPolicy,
    SourceDependency,
    require_count,
    require_dependencies,
    require_id,
)


def _require_digest(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("MEMORY_DIGEST_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryExecutionAuthorization:
    scope: ExecutionScope
    policy: MemoryPolicy
    semantic_input_hash: str
    parent_authorization_ref: str
    deadline_epoch_seconds: int
    semantic_snapshot_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope) or not isinstance(
            self.policy, MemoryPolicy
        ):
            raise TypeError("MEMORY_AUTHORIZATION_INVALID")
        require_id(self.semantic_input_hash)
        require_id(self.parent_authorization_ref)
        require_count(self.deadline_epoch_seconds)
        _require_digest(self.semantic_snapshot_digest)


@dataclass(frozen=True, slots=True)
class MemoryPacketBinding:
    packet_id: str
    packet_revision: int
    execution_revision: int
    grant_epoch: int
    source_epoch: int
    deletion_epoch: int
    packet_digest: str
    authorized_dependencies: tuple[SourceDependency, ...]

    def __post_init__(self) -> None:
        require_id(self.packet_id)
        for value in (
            self.packet_revision,
            self.execution_revision,
            self.grant_epoch,
            self.source_epoch,
            self.deletion_epoch,
        ):
            require_count(value)
        _require_digest(self.packet_digest)
        require_dependencies(self.authorized_dependencies)


class MemoryPacketAuthority(Protocol):
    """本机可信投影；必须按传入的完整执行用途和冻结策略给出当前授权。"""

    def current(
        self, authorization: MemoryExecutionAuthorization
    ) -> MemoryPacketBinding | None: ...


def _canonical_dependencies(
    dependencies: tuple[SourceDependency, ...],
) -> list[dict[str, str | int]]:
    return [
        asdict(dep)
        for dep in sorted(
            set(dependencies),
            key=lambda dep: (
                dep.source_type,
                dep.source_id,
                dep.source_version,
                dep.grant_epoch,
                dep.source_epoch,
                dep.deletion_epoch,
            ),
        )
    ]


def _packet_digest(packet: MemoryContextPacket, *, semantic: bool) -> str:
    value = asdict(packet)
    value["safety_dependencies"] = _canonical_dependencies(packet.safety_dependencies)
    for item, item_data in zip(packet.items, value["items"], strict=True):
        item_data["safety_dependencies"] = _canonical_dependencies(
            item.safety_dependencies
        )
    if semantic:
        for key in ("packet_revision", "execution_revision", "issued_at", "expires_at"):
            del value[key]
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def memory_packet_digest(packet: MemoryContextPacket) -> str:
    """比对认证通道预先绑定的 SHA-256；摘要本身不证明签发身份。"""
    return _packet_digest(packet, semantic=False)


def memory_packet_semantic_digest(packet: MemoryContextPacket) -> str:
    """冻结实际字段和来源；只排除有界刷新可变化的授权外壳。"""
    return _packet_digest(packet, semantic=True)


class AuthorizedMemoryPacketValidator:
    def __init__(
        self,
        authorization: MemoryExecutionAuthorization,
        authority: MemoryPacketAuthority,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (
            not isinstance(authorization, MemoryExecutionAuthorization)
            or authority is None
        ):
            raise ValueError("MEMORY_AUTHORITY_REQUIRED")
        self._authorization = authorization
        self._authority = authority
        self._clock = clock

    @property
    def authorization(self) -> MemoryExecutionAuthorization:
        return self._authorization

    def _check_time(
        self, packet: MemoryContextPacket, operation: ContextOperation
    ) -> None:
        now = self._clock()
        if (
            operation.deadline_epoch_seconds
            != self.authorization.deadline_epoch_seconds
            or now >= self.authorization.deadline_epoch_seconds
            or packet.expires_at > self.authorization.deadline_epoch_seconds
        ):
            raise ValueError("MEMORY_DEADLINE_INVALID")
        if not packet.issued_at <= now < packet.expires_at:
            raise ValueError("MEMORY_PACKET_EXPIRED_OR_NOT_YET_VALID")

    async def validate(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket | None,
        dependencies: tuple[SourceDependency, ...],
        operation: ContextOperation,
    ) -> None:
        authorization = self.authorization
        policy = authorization.policy
        if scope != authorization.scope:
            raise ValueError("MEMORY_SCOPE_MISMATCH")
        if packet is None or operation.memory_disabled:
            raise ValueError("MEMORY_PACKET_REQUIRED")
        packet.validate_scope(scope.conversation, scope.task_id, scope.execution_id)
        self._check_time(packet, operation)
        if (
            not policy.enabled
            or policy.domain != scope.conversation.domain
            or scope.conversation.top_level_agent_id not in policy.agent_ids
            or scope.execution_agent_id not in policy.agent_ids
            or not policy.readable_layers
            or "USER_PRIVATE" not in policy.allowed_scopes
            or packet.policy_version != policy.version
        ):
            raise ValueError("MEMORY_POLICY_DENIED")
        if (
            packet.semantic_input_hash != authorization.semantic_input_hash
            or packet.parent_authorization_ref != authorization.parent_authorization_ref
        ):
            raise ValueError("MEMORY_SEMANTIC_AUTHORIZATION_MISMATCH")
        try:
            current = self._authority.current(authorization)
        except (OSError, RuntimeError, ValueError):
            raise ValueError("MEMORY_AUTHORITY_UNAVAILABLE") from None
        if current is None:
            raise ValueError("MEMORY_ACCESS_REVOKED")
        if (
            packet.packet_id,
            packet.packet_revision,
            packet.execution_revision,
            packet.grant_epoch,
            packet.source_epoch,
            packet.deletion_epoch,
        ) != (
            current.packet_id,
            current.packet_revision,
            current.execution_revision,
            current.grant_epoch,
            current.source_epoch,
            current.deletion_epoch,
        ):
            raise ValueError("MEMORY_PACKET_REVISION_OR_EPOCH_MISMATCH")
        if not hmac.compare_digest(memory_packet_digest(packet), current.packet_digest):
            raise ValueError("MEMORY_PACKET_DIGEST_MISMATCH")
        if not hmac.compare_digest(
            memory_packet_semantic_digest(packet),
            authorization.semantic_snapshot_digest,
        ):
            raise ValueError("MEMORY_SOURCE_CHANGED")
        require_dependencies(dependencies)
        if (
            not set(packet.safety_dependencies).issubset(
                current.authorized_dependencies
            )
            or not set(dependencies).issubset(packet.safety_dependencies)
            or any(
                dep.source_type not in policy.source_types
                for dep in packet.safety_dependencies
            )
        ):
            raise ValueError("MEMORY_DEPENDENCIES_UNAUTHORIZED")
        self._check_time(packet, operation)
