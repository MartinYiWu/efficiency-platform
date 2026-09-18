"""研究发现动作的幂等执行、唯一重试与尝试记账。"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal, Protocol

from efficiency_platform_agent.contracts.research_sources_v2 import (
    DiscoveryBatchV2,
    SourceAttemptV2,
    SourceUsageV2,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.run import (
    JsonObject,
    JsonValue,
    RunContext,
    ToolRequest,
)
from efficiency_platform_agent.tools.external.research import (
    ResearchDiscoverArgumentsV2,
)
from efficiency_platform_agent.tools.runtime.contracts import ToolInvocationRecord
from efficiency_platform_agent.tools.runtime.service import (
    ToolLeaseContext,
    ToolRuntime,
)

from .attempts import InMemorySourceAttemptLedger

_RETRYABLE_SOURCE_ERRORS = frozenset(
    {"SOURCE_RATE_LIMITED", "SOURCE_TEMPORARY_FAILURE"}
)


class RetryBackoff(Protocol):
    async def wait(self, seconds: float) -> None: ...


class AsyncioRetryBackoff:
    async def wait(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)


@dataclass(frozen=True, slots=True)
class DiscoveryActionV2:
    action_id: str
    arguments: ResearchDiscoverArgumentsV2

    def __post_init__(self) -> None:
        if not self.action_id.strip():
            raise ValueError("DISCOVERY_ACTION_ID_INVALID")


@dataclass(slots=True)
class AcquisitionRuntimeContextV2:
    run_context: RunContext
    allowed_source_ids: frozenset[str]
    granted_permissions: frozenset[str]
    remaining_budget: RemainingBudget
    deadline_monotonic: float
    lease_context: ToolLeaseContext | None = None
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("ACQUISITION_MAX_ATTEMPTS_INVALID")
        if self.deadline_monotonic <= 0:
            raise ValueError("ACQUISITION_DEADLINE_INVALID")


@dataclass(frozen=True, slots=True)
class AcquisitionResultV2:
    action_id: str
    batch: DiscoveryBatchV2 | None
    error_code: str | None
    stop_reason: str
    tool_records: tuple[ToolInvocationRecord, ...]
    replayed: bool = False

    def __post_init__(self) -> None:
        if (self.batch is None) == (self.error_code is None):
            raise ValueError("ACQUISITION_RESULT_INVALID")


class AcquisitionExecutor:
    def __init__(
        self,
        runtime: ToolRuntime,
        attempt_ledger: InMemorySourceAttemptLedger,
        *,
        backoff: RetryBackoff | None = None,
        monotonic_clock=None,
    ) -> None:
        self.runtime = runtime
        self.attempt_ledger = attempt_ledger
        self.backoff = backoff or AsyncioRetryBackoff()
        self.monotonic_clock = monotonic_clock or time.monotonic
        self._results: dict[tuple[str, str, str], AcquisitionResultV2] = {}
        self._actions: dict[tuple[str, str, str], DiscoveryActionV2] = {}
        self._locks: dict[tuple[str, str, str], asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def execute_discovery(
        self,
        action: DiscoveryActionV2,
        context: AcquisitionRuntimeContextV2,
    ) -> AcquisitionResultV2:
        scope_key = (
            context.run_context.tenant_id,
            context.run_context.run_id,
            action.action_id,
        )
        lock = await self._lock_for(scope_key)
        async with lock:
            existing = self._results.get(scope_key)
            if existing is not None:
                if self._actions[scope_key] != action:
                    return AcquisitionResultV2(
                        action.action_id,
                        None,
                        "ACQUISITION_ACTION_CONFLICT",
                        "ACTION_CONFLICT",
                        (),
                    )
                return replace(existing, replayed=True)
            result = await self._execute_once(action, context)
            self._actions[scope_key] = action
            self._results[scope_key] = result
            return result

    async def _execute_once(
        self,
        action: DiscoveryActionV2,
        context: AcquisitionRuntimeContextV2,
    ) -> AcquisitionResultV2:
        records: list[ToolInvocationRecord] = []
        signal = self.runtime.cancellation_signal
        if signal is not None and signal.is_requested():
            return await self._cancelled_result(action, context, records)
        if action.arguments.source_id not in context.allowed_source_ids:
            return AcquisitionResultV2(
                action.action_id,
                None,
                "SOURCE_NOT_RUNTIME_ALLOWED",
                "SOURCE_NOT_ALLOWED",
                (),
            )
        remaining = context.remaining_budget
        last_batch: DiscoveryBatchV2 | None = None
        for attempt_number in range(1, context.max_attempts + 1):
            if signal is not None and signal.is_requested():
                return await self._cancelled_result(action, context, records)
            remaining_ms = int(
                (context.deadline_monotonic - self.monotonic_clock()) * 1000
            )
            if remaining_ms <= 0:
                return _terminal(
                    action.action_id,
                    last_batch,
                    "TOOL_TIMEOUT",
                    "DEADLINE_EXHAUSTED",
                    records,
                )
            if context.lease_context is None and remaining.tool_calls <= 0:
                return _terminal(
                    action.action_id,
                    last_batch,
                    "BUDGET_EXHAUSTED",
                    "BUDGET_EXHAUSTED",
                    records,
                )
            arguments = action.arguments.model_copy(
                update={
                    "request_id": _attempt_request_id(
                        action.arguments.request_id, attempt_number
                    )
                }
            )
            request = ToolRequest(
                "2",
                "research.discover.v2",
                _freeze_object(arguments.model_dump(mode="json")),
                min(10_000, remaining_ms),
                None,
                f"{action.action_id}:{attempt_number}",
                False,
                2 * 1024 * 1024,
            )
            lease_context = _lease_context_for_attempt(
                context.lease_context,
                action.action_id,
                attempt_number,
            )
            result, invocation_records = await self.runtime.invoke(
                request,
                context.run_context,
                allowed_tools=frozenset({"research.discover.v2"}),
                granted_permissions=context.granted_permissions,
                remaining_budget=remaining,
                lease_context=lease_context,
            )
            if context.lease_context is not None and lease_context is not None:
                context.lease_context.version = max(
                    context.lease_context.version,
                    lease_context.version,
                )
            records.extend(invocation_records)
            remaining = replace(
                remaining,
                tool_calls=max(0, remaining.tool_calls - len(invocation_records)),
            )
            context.remaining_budget = remaining
            if result.error is not None:
                code = result.error.code
                if code == "TOOL_CANCELLED":
                    return await self._cancelled_result(action, context, records)
                if invocation_records:
                    await self._append_failed_boundary_attempt(
                        action,
                        context,
                        attempt_number,
                        code,
                    )
                if (
                    code in _RETRYABLE_SOURCE_ERRORS
                    and attempt_number < context.max_attempts
                ):
                    retry_decision = await self._wait_before_retry(
                        code,
                        None,
                        attempt_number,
                        context.deadline_monotonic,
                    )
                    if retry_decision != "ready":
                        if retry_decision == "cancelled":
                            return await self._cancelled_result(
                                action, context, records
                            )
                        return AcquisitionResultV2(
                            action.action_id,
                            None,
                            code,
                            "RETRY_DEADLINE_EXCEEDED",
                            tuple(records),
                        )
                    continue
                return AcquisitionResultV2(
                    action.action_id,
                    None,
                    code,
                    "TOOL_ERROR",
                    tuple(records),
                )
            try:
                batch = DiscoveryBatchV2.model_validate(_thaw(result.output))
            except Exception:  # noqa: BLE001 - Tool 输出二次校验失败统一收敛
                return AcquisitionResultV2(
                    action.action_id,
                    None,
                    "SOURCE_SCHEMA_INVALID",
                    "RESULT_INVALID",
                    tuple(records),
                )
            batch = batch.model_copy(
                update={
                    "attempts": tuple(
                        item.model_copy(update={"action_id": action.action_id})
                        for item in batch.attempts
                    )
                }
            )
            await self.attempt_ledger.append_many(
                context.run_context.tenant_id,
                context.run_context.run_id,
                batch.attempts,
            )
            last_batch = batch
            if self.monotonic_clock() >= context.deadline_monotonic:
                return AcquisitionResultV2(
                    action.action_id,
                    None,
                    "TOOL_TIMEOUT",
                    "LATE_RESULT",
                    tuple(records),
                )
            error_code = _batch_error(batch)
            if error_code not in _RETRYABLE_SOURCE_ERRORS:
                return AcquisitionResultV2(
                    action.action_id,
                    batch,
                    None,
                    "COMPLETED",
                    tuple(records),
                )
            if attempt_number >= context.max_attempts:
                return AcquisitionResultV2(
                    action.action_id,
                    batch,
                    None,
                    "RETRY_LIMIT",
                    tuple(records),
                )
            retry_after = max(
                (
                    item.retry_after_seconds or 0
                    for item in batch.attempts
                    if item.error_code == error_code
                ),
                default=0,
            )
            retry_decision = await self._wait_before_retry(
                error_code,
                retry_after,
                attempt_number,
                context.deadline_monotonic,
            )
            if retry_decision == "cancelled":
                return await self._cancelled_result(action, context, records)
            if retry_decision == "deadline":
                return AcquisitionResultV2(
                    action.action_id,
                    batch,
                    None,
                    "RETRY_DEADLINE_EXCEEDED",
                    tuple(records),
                )
        raise AssertionError("unreachable")

    async def _append_failed_boundary_attempt(
        self,
        action: DiscoveryActionV2,
        context: AcquisitionRuntimeContextV2,
        attempt_number: int,
        error_code: str,
    ) -> None:
        now = datetime.now(UTC)
        digest = hashlib.sha256(
            (
                f"{context.run_context.tenant_id}:"
                f"{context.run_context.run_id}:"
                f"{action.action_id}:boundary:{attempt_number}:{error_code}"
            ).encode()
        ).hexdigest()[:32]
        await self.attempt_ledger.append(
            context.run_context.tenant_id,
            context.run_context.run_id,
            SourceAttemptV2(
                attempt_id=f"attempt-{digest}",
                action_id=action.action_id,
                source_id=action.arguments.source_id,
                status="failed",
                started_at=now,
                finished_at=now,
                returned_count=0,
                filtered_count=0,
                error_code=error_code,
                coverage="unknown",
                cursor=action.arguments.cursor,
                lease_id=None,
                usage=SourceUsageV2(
                    requests=0,
                    returned_items=0,
                    downloaded_bytes=0,
                ),
            ),
        )

    async def _cancelled_result(
        self,
        action: DiscoveryActionV2,
        context: AcquisitionRuntimeContextV2,
        records: list[ToolInvocationRecord],
    ) -> AcquisitionResultV2:
        if any(record.status == "cancelled" for record in records):
            now = datetime.now(UTC)
            digest = hashlib.sha256(
                (
                    f"{context.run_context.tenant_id}:"
                    f"{context.run_context.run_id}:"
                    f"{action.action_id}:cancelled:{len(records)}"
                ).encode()
            ).hexdigest()[:32]
            await self.attempt_ledger.append(
                context.run_context.tenant_id,
                context.run_context.run_id,
                SourceAttemptV2(
                    attempt_id=f"attempt-{digest}",
                    action_id=action.action_id,
                    source_id=action.arguments.source_id,
                    status="cancelled",
                    started_at=now,
                    finished_at=now,
                    returned_count=0,
                    filtered_count=0,
                    error_code="TOOL_CANCELLED",
                    coverage="unknown",
                    cursor=action.arguments.cursor,
                    lease_id=None,
                    usage=SourceUsageV2(
                        requests=0,
                        returned_items=0,
                        downloaded_bytes=0,
                    ),
                ),
            )
        if context.lease_context is not None:
            await context.lease_context.port.mark_scope_terminal(
                context.lease_context.scope,
                "cancelled",
            )
        return AcquisitionResultV2(
            action.action_id,
            None,
            "TOOL_CANCELLED",
            "USER_CANCELLED",
            tuple(records),
        )

    async def _wait_before_retry(
        self,
        error_code: str,
        retry_after: int | None,
        attempt_number: int,
        deadline: float,
    ) -> Literal["ready", "deadline", "cancelled"]:
        if retry_after is not None and retry_after > 0:
            delay = float(retry_after)
        elif error_code == "SOURCE_RATE_LIMITED":
            delay = float(min(4, 2 ** (attempt_number - 1)))
        else:
            delay = min(2.0, 0.25 * (2 ** (attempt_number - 1)))
        if self.monotonic_clock() + delay >= deadline:
            return "deadline"
        signal = self.runtime.cancellation_signal
        if signal is not None and signal.is_requested():
            return "cancelled"
        if signal is None:
            await self.backoff.wait(delay)
        else:
            wait_task = asyncio.create_task(self.backoff.wait(delay))
            cancel_task = asyncio.create_task(signal.wait_requested())
            try:
                done, _ = await asyncio.wait(
                    {wait_task, cancel_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel_task in done or signal.is_requested():
                    return "cancelled"
                await wait_task
            finally:
                for task in (wait_task, cancel_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(
                    wait_task,
                    cancel_task,
                    return_exceptions=True,
                )
        if signal is not None and signal.is_requested():
            return "cancelled"
        if self.monotonic_clock() >= deadline:
            return "deadline"
        return "ready"

    async def _lock_for(self, key: tuple[str, str, str]) -> asyncio.Lock:
        async with self._locks_guard:
            return self._locks.setdefault(key, asyncio.Lock())


def _batch_error(batch: DiscoveryBatchV2) -> str | None:
    return next(
        (
            item.error_code
            for item in reversed(batch.attempts)
            if item.status == "failed" and item.error_code is not None
        ),
        None,
    )


def _terminal(
    action_id: str,
    batch: DiscoveryBatchV2 | None,
    error_code: str,
    stop_reason: str,
    records: list[ToolInvocationRecord],
) -> AcquisitionResultV2:
    if batch is not None:
        return AcquisitionResultV2(
            action_id, batch, None, stop_reason, tuple(records)
        )
    return AcquisitionResultV2(
        action_id, None, error_code, stop_reason, tuple(records)
    )


def _attempt_request_id(request_id: str, attempt: int) -> str:
    value = f"{request_id}:attempt:{attempt}"
    if len(value) <= 128:
        return value
    digest = hashlib.sha256(value.encode()).hexdigest()
    return f"request-{digest}"


def _lease_context_for_attempt(
    context: ToolLeaseContext | None,
    action_id: str,
    attempt: int,
) -> ToolLeaseContext | None:
    if context is None:
        return None
    digest = hashlib.sha256(
        f"{context.invocation_prefix}:{action_id}:{attempt}".encode()
    ).hexdigest()[:32]
    return ToolLeaseContext(
        context.port,
        context.scope,
        f"research-{digest}",
        context.version,
        context.reserve_cost_microunits,
    )


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return JsonObject(tuple((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError("ACQUISITION_JSON_INVALID")


def _freeze_object(value: dict[str, object]) -> JsonObject:
    return JsonObject(tuple((key, _freeze(item)) for key, item in value.items()))


def _thaw(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _thaw(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


__all__ = [
    "AcquisitionExecutor",
    "AcquisitionResultV2",
    "AcquisitionRuntimeContextV2",
    "AsyncioRetryBackoff",
    "DiscoveryActionV2",
    "RetryBackoff",
]
