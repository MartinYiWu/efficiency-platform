"""把 HTTP/模型实际用量统一提交给父级预算租约。"""

from __future__ import annotations

from typing import Literal

from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge,
    BudgetLeasePort,
    BudgetScope,
    LedgerSnapshot,
    Reservation,
)


class ResearchBudgetAdapter:
    """研究来源和模型共用一个父账本，避免 Runtime/Provider 双扣。"""

    def __init__(self, lease_port: BudgetLeasePort) -> None:
        self._lease_port = lease_port

    async def reserve_http(
        self,
        scope: BudgetScope,
        invocation_id: str,
        *,
        expected_version: int,
        bytes: int = 0,
    ) -> Reservation:
        return await self._lease_port.reserve(
            scope,
            invocation_id,
            BudgetCharge(calls=1, bytes=bytes),
            expected_version,
        )

    async def settle_http(
        self,
        reservation_id: str,
        *,
        bytes: int,
        status: Literal["success", "failed", "cancelled", "unknown"],
    ) -> LedgerSnapshot:
        return await self._lease_port.settle(
            reservation_id,
            BudgetCharge(calls=1, bytes=bytes, unknown=status == "unknown"),
            status,
        )

    async def mark_dispatched(self, reservation_id: str) -> Reservation:
        """在真正调用 Provider 前原子标记派发。"""

        return await self._lease_port.mark_dispatched(reservation_id)

    async def reserve_model(
        self,
        scope: BudgetScope,
        invocation_id: str,
        *,
        expected_version: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_microunits: int = 0,
    ) -> Reservation:
        return await self._lease_port.reserve(
            scope,
            invocation_id,
            BudgetCharge(
                calls=1,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_microunits=cost_microunits,
            ),
            expected_version,
        )

    async def settle_model(
        self,
        reservation_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cost_microunits: int,
        outcome: Literal["success", "failed", "cancelled", "unknown"],
    ) -> LedgerSnapshot:
        return await self._lease_port.settle(
            reservation_id,
            BudgetCharge(
                calls=1,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_microunits=cost_microunits,
                unknown=outcome == "unknown",
            ),
            outcome,
        )

    async def release(self, reservation_id: str) -> LedgerSnapshot:
        """仅释放尚未 dispatch 的预留；unknown 必须走 settle。"""

        return await self._lease_port.release(reservation_id)

    async def mark_scope_terminal(
        self,
        scope: BudgetScope,
        reason: Literal["cancelled", "terminal"],
    ) -> None:
        """把取消/终态传给父账本，禁止迟到成功交付。"""

        await self._lease_port.mark_scope_terminal(scope, reason)


__all__ = ["ResearchBudgetAdapter"]
