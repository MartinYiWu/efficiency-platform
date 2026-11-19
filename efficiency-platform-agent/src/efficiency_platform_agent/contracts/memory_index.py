"""仅Java内部认证使用的严格索引/召回边界。"""

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_index import (
    AuthorizedMemoryRecall,
    IndexDelete,
    IndexUpsert,
    MemoryIndexIdentity,
    MemoryIndexScope,
    MemoryIndexSpace,
)


class _Boundary(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )


class MemoryIndexUpsertBody(_Boundary):
    event_id: str
    scope: MemoryIndexScope
    space: MemoryIndexSpace
    identity: MemoryIndexIdentity
    execution: ExecutionScope
    expires_at: int
    retention_expires_at: int = Field(gt=0)
    projection: str
    terms: tuple[str, ...] = ()

    def to_core(self) -> IndexUpsert:
        return IndexUpsert(
            **{key: getattr(self, key) for key in type(self).model_fields}
        )


class MemoryIndexDeleteBody(_Boundary):
    event_id: str
    scope: MemoryIndexScope
    item_id: str
    generation: int
    deletion_epoch: int

    def to_core(self) -> IndexDelete:
        return IndexDelete(
            **{key: getattr(self, key) for key in type(self).model_fields}
        )


class MemoryRecallBody(_Boundary):
    authorization: AuthorizedMemoryRecall
    terms: tuple[str, ...] = ()
    query: str | None = None


class MemoryIndexExpiryBody(_Boundary):
    scope: MemoryIndexScope
    limit: int = Field(default=100, ge=1, le=100)
