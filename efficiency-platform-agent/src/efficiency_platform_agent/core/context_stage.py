"""逻辑阶段与固定HTTP槽的持久关联端口，不授予调用或费用额度。"""

from dataclasses import dataclass
from typing import Protocol

from .memory import ExecutionScope, require_count, require_id


@dataclass(frozen=True, slots=True)
class StageSlot:
    slot: int
    operation_id: str

    def __post_init__(self) -> None:
        require_count(self.slot)
        require_id(self.operation_id)
        if not 1 <= self.slot <= 3:
            raise ValueError("CONTEXT_STAGE_ATTEMPTS_EXHAUSTED")


class ContextStageStore(Protocol):
    async def claim(
        self, scope: ExecutionScope, stage_id: str, semantic_hash: str, deadline: int
    ) -> StageSlot: ...
    async def transition(
        self,
        scope: ExecutionScope,
        stage_id: str,
        slot: int,
        expected: str,
        status: str,
    ) -> bool: ...
