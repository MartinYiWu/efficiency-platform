from typing import Protocol

from .memory import ExecutionScope, MemoryContextPacket, MemoryPolicy


class MemoryPacketValidator(Protocol):
    def validate(
        self, packet: MemoryContextPacket, scope: ExecutionScope, policy: MemoryPolicy
    ) -> None: ...
