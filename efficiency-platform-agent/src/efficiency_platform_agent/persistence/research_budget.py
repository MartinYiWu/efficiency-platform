"""BudgetLeasePort 的 PostgreSQL 原子实现。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from typing import Any, Literal, cast
from uuid import uuid4

from psycopg.types.json import Jsonb

from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetLimits,
    BudgetScope,
    LeaseConflictError,
    LedgerSnapshot,
    Reservation,
    ReservationNotFoundError,
    TenantUsageSnapshot,
)

from ._postgres import ensure_writes_enabled, fetchone, validate_runtime_schema


class PostgresBudgetLeaseRepository:
    """使用行锁、版本列和 invocation 唯一键提供多 Worker 安全语义。"""

    def __init__(
        self,
        connection: Any,
        schema: str,
        limits: BudgetLimits,
        *,
        clock_ms: Any | None = None,
    ) -> None:
        self.connection = connection
        self.schema = validate_runtime_schema(schema)
        self.default_limits = limits
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

    async def reserve(
        self,
        scope: BudgetScope,
        invocation_id: str,
        charge: BudgetCharge,
        expected_version: int,
    ) -> Reservation:
        if charge.unknown:
            raise ValueError("预留 charge 不得标记 unknown")
        ledger_key = _ledger_key(scope)
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            existing = await self._reservation_by_invocation(
                ledger_key, scope, invocation_id, for_update=True
            )
            if existing is not None:
                if existing.charge != charge:
                    raise LeaseConflictError("同一 invocation 的 charge 不一致")
                return existing
            row = await self._lock_or_create_ledger(ledger_key, scope)
            version, limits, used, reserved, terminal_reason = _ledger_values(row)
            if terminal_reason is not None:
                raise BudgetExhaustedError("Run 已进入终态")
            _ensure_before_deadline(limits, scope.stage, self._clock_ms())
            if version != expected_version:
                raise LeaseConflictError("预算版本已变化")
            combined = _add(_add(used, reserved), charge)
            _ensure_within(combined, limits, preserve_output=scope.stage != "output")
            next_reserved = _add(reserved, charge)
            next_version = version + 1
            reservation = Reservation(
                reservation_id=f"reservation-{uuid4().hex}",
                invocation_id=invocation_id,
                scope=scope,
                charge=charge,
                version=next_version,
            )
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_ledgers SET reserved=%s,version=%s,"
                "updated_at=clock_timestamp() WHERE ledger_key=%s",
                (Jsonb(asdict(next_reserved)), next_version, ledger_key),
            )
            await self._upsert_usage(scope, BudgetCharge(), charge)
            await self.connection.execute(
                f"INSERT INTO {self.schema}.budget_reservations "
                "(reservation_id,ledger_key,tenant_id,run_id,stage,quota_dimension,"
                "source_account_id,invocation_id,charge,status,version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'reserved',%s)",
                (
                    reservation.reservation_id,
                    ledger_key,
                    scope.tenant_id,
                    scope.run_id,
                    scope.stage,
                    scope.quota_dimension,
                    scope.source_account_id,
                    invocation_id,
                    Jsonb(asdict(charge)),
                    next_version,
                ),
            )
            return reservation

    async def mark_dispatched(self, reservation_id: str) -> Reservation:
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            row = await self._reservation_row(reservation_id, for_update=True)
            if row is None:
                raise ReservationNotFoundError("租约不存在")
            reservation = _reservation(row)
            if reservation.status == "dispatched":
                return reservation
            if reservation.status != "reserved":
                raise LeaseConflictError("租约已结束，不能派发")
            ledger = await self._ledger_row(str(row[1]), for_update=True)
            assert ledger is not None
            version, limits, _, _, terminal = _ledger_values(ledger)
            if terminal is not None:
                raise BudgetExhaustedError("Run 已进入终态")
            _ensure_before_deadline(limits, reservation.scope.stage, self._clock_ms())
            next_version = version + 1
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_ledgers SET version=%s,"
                "updated_at=clock_timestamp() WHERE ledger_key=%s",
                (next_version, row[1]),
            )
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_reservations SET status='dispatched',"
                "version=%s,updated_at=clock_timestamp() WHERE reservation_id=%s",
                (next_version, reservation_id),
            )
            return Reservation(
                reservation.reservation_id,
                reservation.invocation_id,
                reservation.scope,
                reservation.charge,
                next_version,
                "dispatched",
            )

    async def settle(
        self,
        reservation_id: str,
        actual: BudgetCharge,
        outcome: Literal["success", "failed", "cancelled", "unknown"],
    ) -> LedgerSnapshot:
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            row = await self._reservation_row(reservation_id, for_update=True)
            if row is None:
                raise ReservationNotFoundError("租约不存在")
            reservation = _reservation(row)
            if reservation.status == "settled":
                stored_actual = _charge(row[11])
                if stored_actual != actual or row[12] != outcome:
                    raise LeaseConflictError("重复结算参数不一致")
                return await self._snapshot_for_row(row)
            if reservation.status != "dispatched":
                raise ReservationNotFoundError("租约不存在、尚未派发或已结束")
            ledger = await self._ledger_row(str(row[1]), for_update=True)
            assert ledger is not None
            version, limits, used, reserved, terminal = _ledger_values(ledger)
            effective = (
                _conservative_max(actual, reservation.charge)
                if outcome == "unknown" or actual.unknown
                else actual
            )
            remaining = _subtract(reserved, reservation.charge)
            combined = _add(_add(used, remaining), effective)
            over_limit = False
            try:
                _ensure_within(
                    combined,
                    limits,
                    preserve_output=reservation.scope.stage != "output",
                )
            except BudgetExhaustedError:
                over_limit = True
            next_used = _add(used, effective)
            next_version = version + 1
            late = _late(limits, self._clock_ms()) or terminal is not None
            delivery_allowed = outcome == "success" and not late and not over_limit
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_ledgers SET used=%s,reserved=%s,"
                "version=%s,updated_at=clock_timestamp() WHERE ledger_key=%s",
                (
                    Jsonb(asdict(next_used)),
                    Jsonb(asdict(remaining)),
                    next_version,
                    row[1],
                ),
            )
            await self._upsert_usage(
                reservation.scope, effective, _negate(reservation.charge)
            )
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_reservations SET status='settled',"
                "actual=%s,outcome=%s,settlement_late=%s,delivery_allowed=%s,"
                "over_limit=%s,updated_at=clock_timestamp() WHERE reservation_id=%s",
                (
                    Jsonb(asdict(actual)),
                    outcome,
                    late,
                    delivery_allowed,
                    over_limit,
                    reservation_id,
                ),
            )
            return LedgerSnapshot(
                reservation.scope,
                next_version,
                limits,
                next_used,
                remaining,
                late,
                delivery_allowed,
                over_limit,
            )

    async def release(self, reservation_id: str) -> LedgerSnapshot:
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            row = await self._reservation_row(reservation_id, for_update=True)
            if row is None:
                raise ReservationNotFoundError("租约不存在")
            reservation = _reservation(row)
            if reservation.status == "released":
                return await self._snapshot_for_row(row)
            if reservation.status != "reserved":
                raise ReservationNotFoundError("租约不存在或已结束")
            ledger = await self._ledger_row(str(row[1]), for_update=True)
            assert ledger is not None
            version, limits, used, reserved, _ = _ledger_values(ledger)
            remaining = _subtract(reserved, reservation.charge)
            next_version = version + 1
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_ledgers SET reserved=%s,version=%s,"
                "updated_at=clock_timestamp() WHERE ledger_key=%s",
                (Jsonb(asdict(remaining)), next_version, row[1]),
            )
            await self._upsert_usage(
                reservation.scope, BudgetCharge(), _negate(reservation.charge)
            )
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_reservations SET status='released',"
                "updated_at=clock_timestamp() WHERE reservation_id=%s",
                (reservation_id,),
            )
            return LedgerSnapshot(
                reservation.scope, next_version, limits, used, remaining
            )

    async def mark_scope_terminal(
        self, scope: BudgetScope, reason: Literal["cancelled", "terminal"]
    ) -> None:
        async with self.connection.transaction():
            await ensure_writes_enabled(self.connection, self.schema)
            key = _ledger_key(scope)
            await self._lock_or_create_ledger(key, scope)
            await self.connection.execute(
                f"UPDATE {self.schema}.budget_ledgers SET terminal_reason=%s,"
                "version=version+1,updated_at=clock_timestamp() WHERE ledger_key=%s",
                (reason, key),
            )

    async def snapshot(self, scope: BudgetScope) -> LedgerSnapshot:
        key = _ledger_key(scope)
        async with self.connection.transaction():
            row = await self._lock_or_create_ledger(key, scope)
            version, limits, used, reserved, _ = _ledger_values(row)
            return LedgerSnapshot(scope, version, limits, used, reserved)

    async def usage_snapshot(self, scope: BudgetScope) -> TenantUsageSnapshot:
        row = await fetchone(
            self.connection,
            f"SELECT used,reserved FROM {self.schema}.budget_usage "
            "WHERE tenant_id=%s AND run_id=%s AND stage=%s AND quota_dimension=%s "
            "AND source_account_key=%s",
            (*_usage_key(scope),),
        )
        if row is None:
            return TenantUsageSnapshot(scope, BudgetCharge(), BudgetCharge())
        return TenantUsageSnapshot(scope, _charge(row[0]), _charge(row[1]))

    async def _lock_or_create_ledger(
        self, key: str, scope: BudgetScope
    ) -> tuple[Any, ...]:
        await self.connection.execute(
            f"INSERT INTO {self.schema}.budget_ledgers "
            "(ledger_key,scope,limits,used,reserved) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (ledger_key) DO NOTHING",
            (
                key,
                Jsonb(asdict(scope)),
                Jsonb(asdict(self.default_limits)),
                Jsonb(asdict(BudgetCharge())),
                Jsonb(asdict(BudgetCharge())),
            ),
        )
        row = await self._ledger_row(key, for_update=True)
        assert row is not None
        return row

    async def _ledger_row(
        self, key: str, *, for_update: bool
    ) -> tuple[Any, ...] | None:
        return await fetchone(
            self.connection,
            f"SELECT version,limits,used,reserved,terminal_reason "
            f"FROM {self.schema}.budget_ledgers WHERE ledger_key=%s"
            + (" FOR UPDATE" if for_update else ""),
            (key,),
        )

    async def _reservation_row(
        self, reservation_id: str, *, for_update: bool
    ) -> tuple[Any, ...] | None:
        return await fetchone(
            self.connection,
            f"SELECT reservation_id,ledger_key,tenant_id,run_id,stage,quota_dimension,"
            "source_account_id,invocation_id,charge,status,version,actual,outcome,"
            "settlement_late,delivery_allowed,over_limit "
            f"FROM {self.schema}.budget_reservations WHERE reservation_id=%s"
            + (" FOR UPDATE" if for_update else ""),
            (reservation_id,),
        )

    async def _reservation_by_invocation(
        self,
        key: str,
        scope: BudgetScope,
        invocation_id: str,
        *,
        for_update: bool,
    ) -> Reservation | None:
        row = await fetchone(
            self.connection,
            f"SELECT reservation_id,ledger_key,tenant_id,run_id,stage,quota_dimension,"
            "source_account_id,invocation_id,charge,status,version,actual,outcome,"
            "settlement_late,delivery_allowed,over_limit "
            f"FROM {self.schema}.budget_reservations "
            "WHERE ledger_key=%s AND tenant_id=%s AND run_id=%s AND stage=%s "
            "AND quota_dimension=%s AND source_account_key=%s AND invocation_id=%s"
            + (" FOR UPDATE" if for_update else ""),
            (key, *_usage_key(scope), invocation_id),
        )
        return None if row is None else _reservation(row)

    async def _snapshot_for_row(
        self, reservation_row: tuple[Any, ...]
    ) -> LedgerSnapshot:
        ledger = await self._ledger_row(str(reservation_row[1]), for_update=False)
        assert ledger is not None
        version, limits, used, reserved, _ = _ledger_values(ledger)
        return LedgerSnapshot(
            _reservation(reservation_row).scope,
            version,
            limits,
            used,
            reserved,
            bool(reservation_row[13]),
            bool(reservation_row[14]),
            bool(reservation_row[15]),
        )

    async def _upsert_usage(
        self,
        scope: BudgetScope,
        used_delta: BudgetCharge | dict[str, object],
        reserved_delta: BudgetCharge | dict[str, object],
    ) -> None:
        row = await fetchone(
            self.connection,
            f"SELECT used,reserved FROM {self.schema}.budget_usage "
            "WHERE tenant_id=%s AND run_id=%s AND stage=%s AND quota_dimension=%s "
            "AND source_account_key=%s FOR UPDATE",
            (*_usage_key(scope),),
        )
        old_used = BudgetCharge() if row is None else _charge(row[0])
        old_reserved = BudgetCharge() if row is None else _charge(row[1])
        new_used = _apply_delta(old_used, used_delta)
        new_reserved = _apply_delta(old_reserved, reserved_delta)
        await self.connection.execute(
            f"INSERT INTO {self.schema}.budget_usage "
            "(tenant_id,run_id,stage,quota_dimension,source_account_key,used,reserved) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT "
            "(tenant_id,run_id,stage,quota_dimension,source_account_key) "
            "DO UPDATE SET used=EXCLUDED.used,reserved=EXCLUDED.reserved,"
            "updated_at=clock_timestamp()",
            (*_usage_key(scope), Jsonb(asdict(new_used)), Jsonb(asdict(new_reserved))),
        )


def _ledger_key(scope: BudgetScope) -> str:
    raw = json.dumps(scope.ledger_key, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _usage_key(scope: BudgetScope) -> tuple[str, str, str, str, str]:
    return (
        scope.tenant_id,
        scope.run_id,
        scope.stage,
        scope.quota_dimension,
        scope.source_account_id or "",
    )


def _reservation(row: tuple[Any, ...]) -> Reservation:
    scope = BudgetScope(str(row[2]), str(row[3]), str(row[4]), str(row[5]), row[6])
    return Reservation(
        str(row[0]), str(row[7]), scope, _charge(row[8]), int(row[10]), row[9]
    )


def _ledger_values(
    row: tuple[Any, ...],
) -> tuple[int, BudgetLimits, BudgetCharge, BudgetCharge, str | None]:
    return int(row[0]), BudgetLimits(**row[1]), _charge(row[2]), _charge(row[3]), row[4]


def _charge(value: dict[str, object] | None) -> BudgetCharge:
    if value is None:
        return BudgetCharge()
    return BudgetCharge(
        calls=int(cast(Any, value.get("calls", 0))),
        input_tokens=int(cast(Any, value.get("input_tokens", 0))),
        output_tokens=int(cast(Any, value.get("output_tokens", 0))),
        bytes=int(cast(Any, value.get("bytes", 0))),
        cost_microunits=int(cast(Any, value.get("cost_microunits", 0))),
        unknown=bool(value.get("unknown", False)),
    )


def _add(left: BudgetCharge, right: BudgetCharge) -> BudgetCharge:
    return left + right


def _subtract(left: BudgetCharge, right: BudgetCharge) -> BudgetCharge:
    return left - right


def _conservative_max(left: BudgetCharge, right: BudgetCharge) -> BudgetCharge:
    return left.conservative_max(right)


def _negate(value: BudgetCharge) -> dict[str, object]:
    return {
        "calls": -value.calls,
        "input_tokens": -value.input_tokens,
        "output_tokens": -value.output_tokens,
        "bytes": -value.bytes,
        "cost_microunits": -value.cost_microunits,
        "unknown": False,
    }


def _apply_delta(
    base: BudgetCharge, delta: BudgetCharge | dict[str, object]
) -> BudgetCharge:
    values = asdict(base)
    raw = asdict(delta) if isinstance(delta, BudgetCharge) else delta
    for key in ("calls", "input_tokens", "output_tokens", "bytes", "cost_microunits"):
        values[key] += int(cast(Any, raw[key]))
        if values[key] < 0:
            raise LeaseConflictError("预算用量不能为负")
    values["unknown"] = bool(values["unknown"]) or bool(raw.get("unknown", False))
    return _charge(values)


def _ensure_before_deadline(limits: BudgetLimits, stage: str, now_ms: int) -> None:
    reserve = 0 if stage == "output" else limits.output_time_reserve_ms
    if (
        limits.deadline_epoch_ms is not None
        and now_ms >= limits.deadline_epoch_ms - reserve
    ):
        raise BudgetExhaustedError("预算截止时间已到")


def _late(limits: BudgetLimits, now_ms: int) -> bool:
    return limits.deadline_epoch_ms is not None and now_ms >= limits.deadline_epoch_ms


def _ensure_within(
    charge: BudgetCharge, limits: BudgetLimits, *, preserve_output: bool
) -> None:
    if (
        charge.calls > limits.max_calls
        or charge.bytes > limits.max_bytes
        or charge.cost_microunits > limits.max_cost_microunits
        or charge.input_tokens > limits.max_input_tokens
        or charge.output_tokens > limits.max_output_tokens
    ):
        raise BudgetExhaustedError("预算上限不足")
    if (
        preserve_output
        and charge.output_tokens
        > limits.max_output_tokens - limits.output_token_reserve
    ):
        raise BudgetExhaustedError("必须保留最终输出预算")


__all__ = ["PostgresBudgetLeaseRepository"]
