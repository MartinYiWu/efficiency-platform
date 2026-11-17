"""仅消费已授权记忆包的中立只读端口。"""

from dataclasses import dataclass
from typing import Protocol

from .context_ports import ContextOperation
from .memory import (
    ExecutionScope,
    MemoryContextPacket,
    MemoryReference,
    SourceDependency,
    require_dependencies,
)


@dataclass(frozen=True, slots=True)
class MemorySelection:
    items: tuple[MemoryReference, ...]
    safety_dependencies: tuple[SourceDependency, ...]

    def __post_init__(self) -> None:
        if type(self.items) is not tuple or any(
            not isinstance(item, MemoryReference) for item in self.items
        ):
            raise ValueError("MEMORY_SELECTION_INVALID")
        require_dependencies(self.safety_dependencies)
        if any(
            not set(item.safety_dependencies).issubset(self.safety_dependencies)
            for item in self.items
        ):
            raise ValueError("MEMORY_DEPENDENCIES_INCOMPLETE")


class MemoryPort(Protocol):
    async def read(
        self,
        scope: ExecutionScope,
        packet: MemoryContextPacket,
        fields: frozenset[str],
        operation: ContextOperation,
    ) -> MemorySelection: ...
