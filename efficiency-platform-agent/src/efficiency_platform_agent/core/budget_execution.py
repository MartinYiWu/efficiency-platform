"""在单个异步执行链中传播服务器已批准的父 BudgetLease。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from .budget_lease import BudgetLeasePort, BudgetScope


class BudgetExecutionBindingError(RuntimeError):
    pass


@dataclass(slots=True)
class BudgetExecutionBinding:
    """服务端创建、随 asyncio Task 复制且不可由请求体构造的预算绑定。"""

    port: BudgetLeasePort
    scope: BudgetScope
    lease_id: str
    authorization_scope_digest: str
    version: int = 0
    _invocation_counter: int = field(default=0, init=False, repr=False)
    _counter_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if (
            not self.lease_id.strip()
            or len(self.lease_id) > 128
            or len(self.authorization_scope_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.authorization_scope_digest
            )
            or isinstance(self.version, bool)
            or self.version < 0
        ):
            raise ValueError("BUDGET_EXECUTION_BINDING_INVALID")

    async def next_invocation(self, kind: str) -> tuple[str, int]:
        if not kind.strip() or len(kind) > 32:
            raise ValueError("BUDGET_INVOCATION_KIND_INVALID")
        async with self._counter_lock:
            self._invocation_counter += 1
            counter = self._invocation_counter
            version = self.version
        digest = hashlib.sha256(
            f"{self.lease_id}:{kind}:{counter}".encode()
        ).hexdigest()[:32]
        return f"bound-{kind}-{digest}", version

    def update_version(self, version: int) -> None:
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError("BUDGET_BINDING_VERSION_INVALID")
        self.version = max(self.version, version)


_CURRENT_BINDING: ContextVar[BudgetExecutionBinding | None] = ContextVar(
    "budget_execution_binding", default=None
)


def current_budget_execution_binding() -> BudgetExecutionBinding | None:
    return _CURRENT_BINDING.get()


@contextmanager
def bind_budget_execution(
    binding: BudgetExecutionBinding,
) -> Iterator[None]:
    if not isinstance(binding, BudgetExecutionBinding):
        raise TypeError("BUDGET_EXECUTION_BINDING_INVALID")
    current = _CURRENT_BINDING.get()
    if current is not None and current is not binding:
        raise BudgetExecutionBindingError("BUDGET_EXECUTION_BINDING_CONFLICT")
    token = _CURRENT_BINDING.set(binding)
    try:
        yield
    finally:
        _CURRENT_BINDING.reset(token)


__all__ = [
    "BudgetExecutionBinding",
    "BudgetExecutionBindingError",
    "bind_budget_execution",
    "current_budget_execution_binding",
]
