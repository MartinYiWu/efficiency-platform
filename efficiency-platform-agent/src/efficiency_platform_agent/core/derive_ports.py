"""唯一 derive 的中立操作与技术租约；不授予业务或费用权限。"""

from dataclasses import dataclass, field
from typing import Protocol

from .memory import ExecutionScope, require_count, require_id


@dataclass(frozen=True, slots=True)
class DeriveOperation:
    scope: ExecutionScope
    run_id: str
    operation_id: str
    authorization_ref: str
    budget_id: str
    deadline_epoch_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("DERIVE_SCOPE_INVALID")
        for value in (
            self.run_id,
            self.operation_id,
            self.authorization_ref,
            self.budget_id,
        ):
            require_id(value)
        require_count(self.deadline_epoch_seconds)


@dataclass(frozen=True, slots=True)
class DeriveLease:
    operation: DeriveOperation
    fingerprint: str
    token: str = field(repr=False)
    result: bytes | None = field(default=None, repr=False)


class DeriveOperationStore(Protocol):
    def claim(self, operation: DeriveOperation, fingerprint: str) -> DeriveLease: ...
    def check_live(self, lease: DeriveLease) -> None: ...
    def consume_attempt(self, lease: DeriveLease) -> None: ...
    def succeed(self, lease: DeriveLease, sealed_result: bytes) -> None: ...
    def fail(self, lease: DeriveLease) -> None: ...
