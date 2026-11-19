"""记忆索引与有限召回的中立合同；不含权威正文或授权签发。"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Protocol

from .memory import SCOPE_CATALOG, ExecutionScope, require_count, require_id


@dataclass(frozen=True, slots=True)
class MemoryIndexScope:
    tenant_id: str
    user_id: str
    domain: str
    top_level_agent_id: str
    scope_kind: str = "USER_PRIVATE"
    scope_ref: str = ""

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.user_id):
            require_id(value)
        if self.domain not in SCOPE_CATALOG or self.top_level_agent_id != self.domain:
            raise ValueError("MEMORY_INDEX_SCOPE_DENIED")
        if self.scope_kind not in {
            "USER_PRIVATE",
            "PROJECT",
            "DEPARTMENT",
            "ORGANIZATION",
        }:
            raise ValueError("MEMORY_INDEX_SCOPE_DENIED")
        if self.scope_kind == "USER_PRIVATE":
            if self.scope_ref not in {"", self.user_id}:
                raise ValueError("MEMORY_INDEX_SCOPE_DENIED")
        else:
            require_id(self.scope_ref)

    @property
    def key(self) -> str:
        return hashlib.sha256(
            json.dumps(
                [
                    self.tenant_id,
                    self.user_id,
                    self.domain,
                    self.top_level_agent_id,
                    self.scope_kind,
                    self.scope_ref or self.user_id,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class MemoryIndexSpace:
    embedding_model: str
    dimension: int
    policy_version: str

    def __post_init__(self) -> None:
        require_id(self.embedding_model)
        require_id(self.policy_version)
        if type(self.dimension) is not int or not 1 <= self.dimension <= 4096:
            raise ValueError("MEMORY_INDEX_DIMENSION_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryIndexIdentity:
    item_id: str
    version_id: str
    generation: int
    deletion_epoch: int
    source_fingerprint: str

    def __post_init__(self) -> None:
        require_id(self.item_id)
        require_id(self.version_id)
        require_count(self.generation)
        require_count(self.deletion_epoch)
        if (
            self.generation < 1
            or len(self.source_fingerprint) != 64
            or any(value not in "0123456789abcdef" for value in self.source_fingerprint)
        ):
            raise ValueError("MEMORY_INDEX_IDENTITY_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryRecallCandidate:
    identity: MemoryIndexIdentity
    score: float

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not MemoryIndexIdentity
            or type(self.score) not in {float, int}
            or not math.isfinite(self.score)
        ):
            raise ValueError("MEMORY_RECALL_CANDIDATE_INVALID")


@dataclass(frozen=True, slots=True)
class AuthorizedMemoryRecall:
    scope: MemoryIndexScope
    space: MemoryIndexSpace
    execution: ExecutionScope
    allowed: tuple[MemoryIndexIdentity, ...]
    expires_at: int
    query_embedding_allowed: bool = False
    top_k: int = 8

    def __post_init__(self) -> None:
        conversation = self.execution.conversation
        if (
            (
                self.scope.tenant_id,
                self.scope.user_id,
                self.scope.domain,
                self.scope.top_level_agent_id,
            )
            != (
                conversation.tenant_id,
                conversation.user_id,
                conversation.domain,
                conversation.top_level_agent_id,
            )
            or type(self.allowed) is not tuple
            or any(type(item) is not MemoryIndexIdentity for item in self.allowed)
            or len(set(self.allowed)) != len(self.allowed)
            or len({item.item_id for item in self.allowed}) != len(self.allowed)
            or len(self.allowed) > 10000
            or type(self.top_k) is not int
            or not 1 <= self.top_k <= 8
            or type(self.expires_at) is not int
            or self.expires_at < 1
            or type(self.query_embedding_allowed) is not bool
            or conversation.domain == "hr"
        ):
            raise ValueError("MEMORY_RECALL_AUTHORIZATION_INVALID")


class MemoryIndexReader(Protocol):
    async def search(
        self,
        scope: MemoryIndexScope,
        space: MemoryIndexSpace,
        allowed: tuple[MemoryIndexIdentity, ...],
        *,
        vector: tuple[float, ...] | None,
        terms: tuple[str, ...],
        limit: int,
    ) -> tuple[tuple[MemoryRecallCandidate, ...], tuple[MemoryRecallCandidate, ...]]:
        """先按完整合法ID/版本/代次/源指纹过滤，向量和词法各至多limit条。"""
        ...


@dataclass(frozen=True, slots=True)
class IndexUpsert:
    event_id: str
    scope: MemoryIndexScope
    space: MemoryIndexSpace
    identity: MemoryIndexIdentity
    execution: ExecutionScope
    expires_at: int
    projection: str
    terms: tuple[str, ...] = ()
    retention_expires_at: int = 0

    def __post_init__(self) -> None:
        require_id(self.event_id)
        require_count(self.expires_at)
        require_count(self.retention_expires_at)
        if self.retention_expires_at == 0:
            object.__setattr__(self, "retention_expires_at", self.expires_at)
        if self.retention_expires_at < self.expires_at:
            raise ValueError("MEMORY_INDEX_RETENTION_INVALID")
        conversation = self.execution.conversation
        if (
            self.scope.tenant_id,
            self.scope.user_id,
            self.scope.domain,
            self.scope.top_level_agent_id,
        ) != (
            conversation.tenant_id,
            conversation.user_id,
            conversation.domain,
            conversation.top_level_agent_id,
        ) or conversation.domain == "hr":
            raise ValueError("MEMORY_INDEX_EXECUTION_SCOPE_INVALID")
        if (
            type(self.projection) is not str
            or not self.projection.strip()
            or len(self.projection) > 8192
            or type(self.terms) is not tuple
            or len(self.terms) > 32
            or any(
                type(term) is not str or not term.strip() or len(term) > 128
                for term in self.terms
            )
        ):
            raise ValueError("MEMORY_INDEX_PROJECTION_INVALID")


@dataclass(frozen=True, slots=True)
class IndexDelete:
    event_id: str
    scope: MemoryIndexScope
    item_id: str
    generation: int
    deletion_epoch: int

    def __post_init__(self) -> None:
        require_id(self.event_id)
        require_id(self.item_id)
        require_count(self.generation)
        require_count(self.deletion_epoch)


@dataclass(frozen=True, slots=True)
class IndexLease:
    request: IndexUpsert
    token: str
    operation_id: str
    fingerprint: str
    ready: bool = False


@dataclass(frozen=True, slots=True)
class QueryEmbeddingLease:
    token: str
    operation_id: str
    fingerprint: str
    vector: tuple[float, ...] | None = None


class MemoryIndexWriter(Protocol):
    async def claim(self, request: IndexUpsert) -> IndexLease: ...
    async def complete(self, lease: IndexLease, vector: tuple[float, ...]) -> None: ...
    async def fail_unknown(self, lease: IndexLease) -> None: ...
    async def delete(self, request: IndexDelete) -> None: ...


def validate_memory_vector(vector: tuple[float, ...], space: MemoryIndexSpace) -> None:
    if (
        type(vector) is not tuple
        or len(vector) != space.dimension
        or any(
            type(value) not in {int, float} or not math.isfinite(value)
            for value in vector
        )
        or not any(value != 0 for value in vector)
    ):
        raise ValueError("MEMORY_INDEX_VECTOR_INVALID")
