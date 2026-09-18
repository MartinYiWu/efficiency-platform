"""跨调用共享预算租约的框架中立事实与离线 CAS 实现。

生产环境应把同样的比较并交换语义放入权威存储；本文件的内存实现只用于
离线契约测试和 Fake 装配，不把进程内锁当作多 Worker 的生产正确性保证。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import uuid4


def _text(name: str, value: str, limit: int = 128) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} 必须是非空且有界字符串")


def _non_negative(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


@dataclass(frozen=True, slots=True)
class BudgetScope:
    """一笔预算事实的租户、Run、阶段和配额维度。"""

    tenant_id: str
    run_id: str
    stage: str
    quota_dimension: str
    source_account_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("tenant_id", "run_id", "stage", "quota_dimension"):
            _text(name, getattr(self, name))
        if self.source_account_id is not None:
            _text("source_account_id", self.source_account_id)

    @property
    def ledger_key(self) -> tuple[Hashable, ...]:
        """免费来源按 source/account 共享；普通额度按租户 Run 隔离。"""

        if self.source_account_id is not None:
            return ("source-account", self.source_account_id, self.quota_dimension)
        return (
            "tenant-run",
            self.tenant_id,
            self.run_id,
            self.quota_dimension,
        )

    @property
    def usage_key(self) -> tuple[Hashable, ...]:
        """租户用量事实始终按 tenant/run/stage 隔离。"""

        return (
            self.tenant_id,
            self.run_id,
            self.stage,
            self.quota_dimension,
            self.source_account_id,
        )


@dataclass(frozen=True, slots=True)
class BudgetCharge:
    """一次调用预留或实际结算的不可变用量。"""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    bytes: int = 0
    cost_microunits: int = 0
    unknown: bool = False

    def __post_init__(self) -> None:
        for name in (
            "calls",
            "input_tokens",
            "output_tokens",
            "bytes",
            "cost_microunits",
        ):
            _non_negative(name, getattr(self, name))
        if not isinstance(self.unknown, bool):
            raise TypeError("unknown 必须是布尔值")

    def __add__(self, other: BudgetCharge) -> BudgetCharge:
        if not isinstance(other, BudgetCharge):
            return NotImplemented
        return BudgetCharge(
            calls=self.calls + other.calls,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            bytes=self.bytes + other.bytes,
            cost_microunits=self.cost_microunits + other.cost_microunits,
            unknown=self.unknown or other.unknown,
        )

    def __sub__(self, other: BudgetCharge) -> BudgetCharge:
        if not isinstance(other, BudgetCharge):
            return NotImplemented
        values = (
            self.calls - other.calls,
            self.input_tokens - other.input_tokens,
            self.output_tokens - other.output_tokens,
            self.bytes - other.bytes,
            self.cost_microunits - other.cost_microunits,
        )
        if any(value < 0 for value in values):
            raise ValueError("预算结算不能产生负用量")
        return BudgetCharge(*values, unknown=self.unknown)

    def conservative_max(self, other: BudgetCharge) -> BudgetCharge:
        """逐维取最大值，保证未知结果不释放已占用额度。"""

        if not isinstance(other, BudgetCharge):
            raise TypeError("other 必须是 BudgetCharge")
        return BudgetCharge(
            calls=max(self.calls, other.calls),
            input_tokens=max(self.input_tokens, other.input_tokens),
            output_tokens=max(self.output_tokens, other.output_tokens),
            bytes=max(self.bytes, other.bytes),
            cost_microunits=max(self.cost_microunits, other.cost_microunits),
            unknown=self.unknown or other.unknown,
        )


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """一个租户或共享来源桶的硬上限。"""

    max_calls: int
    max_bytes: int
    max_cost_microunits: int
    max_input_tokens: int = 1_000_000
    max_output_tokens: int = 1_000_000
    deadline_epoch_ms: int | None = None
    output_token_reserve: int = 0
    output_time_reserve_ms: int = 0

    def __post_init__(self) -> None:
        for name in (
            "max_calls",
            "max_bytes",
            "max_cost_microunits",
            "max_input_tokens",
            "max_output_tokens",
            "output_token_reserve",
            "output_time_reserve_ms",
        ):
            _non_negative(name, getattr(self, name))
        if self.deadline_epoch_ms is not None:
            _non_negative("deadline_epoch_ms", self.deadline_epoch_ms)
        if self.output_token_reserve > self.max_output_tokens:
            raise ValueError("输出预留不得超过输出上限")


@dataclass(frozen=True, slots=True)
class Reservation:
    """一次尚未完成的原子预算预留。"""

    reservation_id: str
    invocation_id: str
    scope: BudgetScope
    charge: BudgetCharge
    version: int
    status: Literal["reserved", "dispatched", "settled", "released"] = "reserved"

    def __post_init__(self) -> None:
        _text("reservation_id", self.reservation_id)
        _text("invocation_id", self.invocation_id)
        _non_negative("version", self.version)


@dataclass(frozen=True, slots=True)
class LedgerSnapshot:
    """CAS 版本对应的累计已用与已预留事实。"""

    scope: BudgetScope
    version: int
    limits: BudgetLimits
    used: BudgetCharge
    reserved: BudgetCharge
    settlement_late: bool = False
    delivery_allowed: bool = True
    over_limit: bool = False

    def __post_init__(self) -> None:
        _non_negative("version", self.version)
        if self.settlement_late and self.delivery_allowed:
            raise ValueError("迟到结算不得允许交付")
        if self.over_limit and self.delivery_allowed:
            raise ValueError("超限结算不得允许交付")


@dataclass(frozen=True, slots=True)
class SettlementAuditRecord:
    """结算审计事实；迟到结果只计费，不允许自动交付。"""

    reservation_id: str
    invocation_id: str
    outcome: Literal["success", "failed", "cancelled", "unknown"]
    actual: BudgetCharge
    late: bool
    delivery_allowed: bool
    over_limit: bool = False

    def __post_init__(self) -> None:
        _text("reservation_id", self.reservation_id)
        _text("invocation_id", self.invocation_id)
        if self.late and self.delivery_allowed:
            raise ValueError("迟到结果不得允许交付")
        if self.over_limit and self.delivery_allowed:
            raise ValueError("超限结果不得允许交付")


@dataclass(frozen=True, slots=True)
class TenantUsageSnapshot:
    """共享来源桶之外按租户 Run 隔离保存的使用事实。"""

    scope: BudgetScope
    used: BudgetCharge
    reserved: BudgetCharge


class BudgetLeaseError(RuntimeError):
    """预算租约领域错误基类。"""


class BudgetExhaustedError(BudgetLeaseError):
    """预留会超过某一硬上限。"""


class LeaseConflictError(BudgetLeaseError):
    """CAS 版本或幂等参数冲突。"""


class ReservationNotFoundError(BudgetLeaseError):
    """找不到可结算或可释放的租约。"""


class BudgetLeasePort(Protocol):
    """供 Tool/Model/Research Runtime 注入的共享预算端口。"""

    async def reserve(
        self,
        scope: BudgetScope,
        invocation_id: str,
        charge: BudgetCharge,
        expected_version: int,
    ) -> Reservation: ...

    async def settle(
        self,
        reservation_id: str,
        actual: BudgetCharge,
        outcome: Literal["success", "failed", "cancelled", "unknown"],
    ) -> LedgerSnapshot: ...

    async def release(self, reservation_id: str) -> LedgerSnapshot: ...

    async def mark_dispatched(self, reservation_id: str) -> Reservation: ...

    async def mark_scope_terminal(
        self, scope: BudgetScope, reason: Literal["cancelled", "terminal"]
    ) -> None: ...

    async def snapshot(self, scope: BudgetScope) -> LedgerSnapshot: ...


@dataclass(slots=True)
class _MutableLedger:
    scope: BudgetScope
    limits: BudgetLimits
    version: int = 0
    used: BudgetCharge = BudgetCharge()
    reserved: BudgetCharge = BudgetCharge()


@dataclass(slots=True)
class _MutableTenantUsage:
    scope: BudgetScope
    used: BudgetCharge = BudgetCharge()
    reserved: BudgetCharge = BudgetCharge()


class InMemoryBudgetLeaseRepository:
    """离线 Fake CAS 仓储；生产实现必须使用持久化原子更新。"""

    def __init__(
        self,
        limits: BudgetLimits,
        *,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(limits, BudgetLimits):
            raise TypeError("limits 必须是 BudgetLimits")
        self._default_limits = limits
        self._ledgers: dict[tuple[Hashable, ...], _MutableLedger] = {}
        self._tenant_usage: dict[tuple[Hashable, ...], _MutableTenantUsage] = {}
        self._reservations: dict[str, Reservation] = {}
        self._invocations: dict[tuple[tuple[Hashable, ...], str], str] = {}
        self._settled: dict[str, LedgerSnapshot] = {}
        self._settlement_inputs: dict[
            str,
            tuple[BudgetCharge, Literal["success", "failed", "cancelled", "unknown"]],
        ] = {}
        self._released: dict[str, LedgerSnapshot] = {}
        self._audit_records: list[SettlementAuditRecord] = []
        self._terminal_scopes: set[tuple[Hashable, ...]] = set()
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._lock = asyncio.Lock()

    @property
    def dispatched_invocation_count(self) -> int:
        """已经原子标记派发的 invocation 数量。"""

        return sum(
            reservation.status in {"dispatched", "settled"}
            for reservation in self._reservations.values()
        )

    @property
    def audit_records(self) -> tuple[SettlementAuditRecord, ...]:
        """返回不可变的结算审计快照。"""

        return tuple(self._audit_records)

    async def reserve(
        self,
        scope: BudgetScope,
        invocation_id: str,
        charge: BudgetCharge,
        expected_version: int,
    ) -> Reservation:
        if not isinstance(scope, BudgetScope) or not isinstance(charge, BudgetCharge):
            raise TypeError("scope/charge 类型不正确")
        _text("invocation_id", invocation_id)
        _non_negative("expected_version", expected_version)
        if charge.unknown:
            raise ValueError("预留 charge 不得标记 unknown")
        async with self._lock:
            invocation_key = (scope.usage_key, invocation_id)
            existing_id = self._invocations.get(invocation_key)
            if existing_id is not None:
                existing = self._reservations[existing_id]
                if existing.charge != charge:
                    raise LeaseConflictError("同一 invocation 的 charge 不一致")
                return existing
            ledger = self._ledger(scope)
            if scope.usage_key in self._terminal_scopes:
                raise BudgetExhaustedError("Run 已进入终态")
            self._ensure_before_deadline(ledger.limits, scope.stage)
            if ledger.version != expected_version:
                raise LeaseConflictError("预算版本已变化")
            combined = ledger.used + ledger.reserved + charge
            _ensure_within(
                combined,
                ledger.limits,
                preserve_output=scope.stage != "output",
            )
            ledger.reserved = ledger.reserved + charge
            ledger.version += 1
            usage = self._usage(scope)
            usage.reserved = usage.reserved + charge
            reservation = Reservation(
                reservation_id=f"reservation-{uuid4().hex}",
                invocation_id=invocation_id,
                scope=scope,
                charge=charge,
                version=ledger.version,
            )
            self._reservations[reservation.reservation_id] = reservation
            self._invocations[invocation_key] = reservation.reservation_id
            return reservation

    async def mark_dispatched(self, reservation_id: str) -> Reservation:
        """原子记录外部调用即将派发；此后禁止 release。"""

        _text("reservation_id", reservation_id)
        async with self._lock:
            reservation = self._reservations.get(reservation_id)
            if reservation is None:
                raise ReservationNotFoundError("租约不存在")
            if reservation.status == "dispatched":
                return reservation
            if reservation.status != "reserved":
                raise LeaseConflictError("租约已结束，不能派发")
            ledger = self._ledger(reservation.scope)
            try:
                if reservation.scope.usage_key in self._terminal_scopes:
                    raise BudgetExhaustedError("Run 已进入终态")
                self._ensure_before_deadline(ledger.limits, reservation.scope.stage)
            except BudgetExhaustedError:
                ledger.reserved = ledger.reserved - reservation.charge
                ledger.version += 1
                usage = self._usage(reservation.scope)
                usage.reserved = usage.reserved - reservation.charge
                released = self._snapshot(ledger, reservation.scope)
                self._reservations[reservation_id] = Reservation(
                    reservation_id=reservation.reservation_id,
                    invocation_id=reservation.invocation_id,
                    scope=reservation.scope,
                    charge=reservation.charge,
                    version=reservation.version,
                    status="released",
                )
                self._released[reservation_id] = released
                raise
            ledger.version += 1
            dispatched = Reservation(
                reservation_id=reservation.reservation_id,
                invocation_id=reservation.invocation_id,
                scope=reservation.scope,
                charge=reservation.charge,
                version=ledger.version,
                status="dispatched",
            )
            self._reservations[reservation_id] = dispatched
            return dispatched

    async def settle(
        self,
        reservation_id: str,
        actual: BudgetCharge,
        outcome: Literal["success", "failed", "cancelled", "unknown"],
    ) -> LedgerSnapshot:
        _text("reservation_id", reservation_id)
        if not isinstance(actual, BudgetCharge):
            raise TypeError("actual 必须是 BudgetCharge")
        if outcome not in {"success", "failed", "cancelled", "unknown"}:
            raise ValueError("未知结算结果")
        async with self._lock:
            replay = self._settled.get(reservation_id)
            if replay is not None:
                if self._settlement_inputs[reservation_id] != (actual, outcome):
                    raise LeaseConflictError("重复结算参数不一致")
                return replay
            reservation = self._reservations.get(reservation_id)
            if reservation is None or reservation.status != "dispatched":
                raise ReservationNotFoundError("租约不存在、尚未派发或已结束")
            ledger = self._ledger(reservation.scope)
            effective = (
                actual.conservative_max(reservation.charge)
                if outcome == "unknown" or actual.unknown
                else actual
            )
            remaining_reserved = ledger.reserved - reservation.charge
            combined = ledger.used + remaining_reserved + effective
            over_limit = False
            try:
                _ensure_within(
                    combined,
                    ledger.limits,
                    preserve_output=reservation.scope.stage != "output",
                )
            except BudgetExhaustedError:
                # 外部调用已经发生，真实用量不能因超限而丢失；记录超额并禁止交付。
                over_limit = True
            ledger.reserved = remaining_reserved
            ledger.used = ledger.used + effective
            ledger.version += 1
            usage = self._usage(reservation.scope)
            usage.reserved = usage.reserved - reservation.charge
            usage.used = usage.used + effective
            late = self._is_late(ledger.limits) or (
                reservation.scope.usage_key in self._terminal_scopes
            )
            delivery_allowed = outcome == "success" and not late and not over_limit
            snapshot = self._snapshot(
                ledger,
                reservation.scope,
                settlement_late=late,
                delivery_allowed=delivery_allowed,
                over_limit=over_limit,
            )
            self._reservations[reservation_id] = Reservation(
                reservation_id=reservation.reservation_id,
                invocation_id=reservation.invocation_id,
                scope=reservation.scope,
                charge=reservation.charge,
                version=reservation.version,
                status="settled",
            )
            self._settled[reservation_id] = snapshot
            self._settlement_inputs[reservation_id] = (actual, outcome)
            self._audit_records.append(
                SettlementAuditRecord(
                    reservation_id=reservation_id,
                    invocation_id=reservation.invocation_id,
                    outcome=outcome,
                    actual=effective,
                    late=late,
                    delivery_allowed=delivery_allowed,
                    over_limit=over_limit,
                )
            )
            return snapshot

    async def release(self, reservation_id: str) -> LedgerSnapshot:
        _text("reservation_id", reservation_id)
        async with self._lock:
            replay = self._released.get(reservation_id)
            if replay is not None:
                return replay
            reservation = self._reservations.get(reservation_id)
            if reservation is None or reservation.status != "reserved":
                raise ReservationNotFoundError("租约不存在或已结束")
            ledger = self._ledger(reservation.scope)
            ledger.reserved = ledger.reserved - reservation.charge
            ledger.version += 1
            usage = self._usage(reservation.scope)
            usage.reserved = usage.reserved - reservation.charge
            snapshot = self._snapshot(ledger, reservation.scope)
            self._reservations[reservation_id] = Reservation(
                reservation_id=reservation.reservation_id,
                invocation_id=reservation.invocation_id,
                scope=reservation.scope,
                charge=reservation.charge,
                version=reservation.version,
                status="released",
            )
            self._released[reservation_id] = snapshot
            return snapshot

    async def snapshot(self, scope: BudgetScope) -> LedgerSnapshot:
        if not isinstance(scope, BudgetScope):
            raise TypeError("scope 类型不正确")
        async with self._lock:
            return self._snapshot(self._ledger(scope), scope)

    async def usage_snapshot(self, scope: BudgetScope) -> TenantUsageSnapshot:
        """读取当前租户 Run 的隔离用量事实。"""

        if not isinstance(scope, BudgetScope):
            raise TypeError("scope 类型不正确")
        async with self._lock:
            usage = self._usage(scope)
            return TenantUsageSnapshot(
                scope=scope,
                used=usage.used,
                reserved=usage.reserved,
            )

    async def mark_scope_terminal(
        self, scope: BudgetScope, reason: Literal["cancelled", "terminal"]
    ) -> None:
        """记录取消或终态，后续迟到成功只保留审计。"""

        if not isinstance(scope, BudgetScope):
            raise TypeError("scope 类型不正确")
        if reason not in {"cancelled", "terminal"}:
            raise ValueError("未知终态原因")
        async with self._lock:
            self._terminal_scopes.add(scope.usage_key)

    def _ledger(self, scope: BudgetScope) -> _MutableLedger:
        key = scope.ledger_key
        ledger = self._ledgers.get(key)
        if ledger is None:
            ledger = _MutableLedger(scope=scope, limits=self._default_limits)
            self._ledgers[key] = ledger
        return ledger

    def _usage(self, scope: BudgetScope) -> _MutableTenantUsage:
        usage = self._tenant_usage.get(scope.usage_key)
        if usage is None:
            usage = _MutableTenantUsage(scope=scope)
            self._tenant_usage[scope.usage_key] = usage
        return usage

    def _ensure_before_deadline(self, limits: BudgetLimits, stage: str) -> None:
        if (
            limits.deadline_epoch_ms is not None
            and self._clock_ms()
            >= limits.deadline_epoch_ms
            - (0 if stage == "output" else limits.output_time_reserve_ms)
        ):
            raise BudgetExhaustedError("预算截止时间已到")

    def _is_late(self, limits: BudgetLimits) -> bool:
        return (
            limits.deadline_epoch_ms is not None
            and self._clock_ms() >= limits.deadline_epoch_ms
        )

    @staticmethod
    def _snapshot(
        ledger: _MutableLedger,
        requested_scope: BudgetScope,
        *,
        settlement_late: bool = False,
        delivery_allowed: bool = True,
        over_limit: bool = False,
    ) -> LedgerSnapshot:
        return LedgerSnapshot(
            scope=requested_scope,
            version=ledger.version,
            limits=ledger.limits,
            used=ledger.used,
            reserved=ledger.reserved,
            settlement_late=settlement_late,
            delivery_allowed=delivery_allowed,
            over_limit=over_limit,
        )


def _ensure_within(
    charge: BudgetCharge,
    limits: BudgetLimits,
    *,
    preserve_output: bool,
) -> None:
    checks = (
        (charge.calls, limits.max_calls),
        (charge.input_tokens, limits.max_input_tokens),
        (charge.output_tokens, limits.max_output_tokens),
        (charge.bytes, limits.max_bytes),
        (charge.cost_microunits, limits.max_cost_microunits),
    )
    if any(value > limit for value, limit in checks):
        raise BudgetExhaustedError("预算上限不足")
    if preserve_output and charge.output_tokens > (
        limits.max_output_tokens - limits.output_token_reserve
    ):
        raise BudgetExhaustedError("必须保留最终输出预算")


__all__ = [
    "BudgetCharge",
    "BudgetExhaustedError",
    "BudgetLeaseError",
    "BudgetLeasePort",
    "BudgetLimits",
    "BudgetScope",
    "InMemoryBudgetLeaseRepository",
    "LeaseConflictError",
    "LedgerSnapshot",
    "Reservation",
    "ReservationNotFoundError",
    "SettlementAuditRecord",
    "TenantUsageSnapshot",
]
