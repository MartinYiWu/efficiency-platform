"""Tool Runtime 的唯一调用治理入口。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from efficiency_platform_agent.core.budget import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetGuard,
    BudgetState,
    RemainingBudget,
)
from efficiency_platform_agent.core.budget_execution import (
    current_budget_execution_binding,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge as LeaseBudgetCharge,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLeaseError,
    BudgetLeasePort,
    BudgetScope,
    LeaseConflictError,
    Reservation,
)
from efficiency_platform_agent.core.ports import Tool
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    JsonValue,
    RunContext,
    ToolError,
    ToolRequest,
    ToolResult,
)
from efficiency_platform_agent.tools.runtime.contracts import ToolInvocationRecord
from efficiency_platform_agent.tools.runtime.registry import ToolRegistry


class CancellationPort(Protocol):
    """最小取消端口，避免 Runtime 依赖编排层。"""

    async def wait_requested(self) -> None: ...

    def is_requested(self) -> bool: ...


@dataclass(slots=True)
class ToolBudgetContext:
    """单次 Tool 调用独占的旧预算守卫上下文。"""

    guard: BudgetGuard
    budget: ExecutionBudget
    state: BudgetState


@dataclass(slots=True)
class ToolLeaseContext:
    """单次 Run 在共享父账本中的 Tool 调用上下文。"""

    port: BudgetLeasePort
    scope: BudgetScope
    invocation_prefix: str
    version: int
    reserve_cost_microunits: int | None = None


class ToolRuntime:
    """按固定顺序执行 Tool，并将异常归一化为安全结果。"""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        cancellation_signal: CancellationPort | None = None,
        budget_guard: BudgetGuard | None = None,
        budget: ExecutionBudget | None = None,
        budget_state: BudgetState | None = None,
        clock: Callable[[], int] | Any | None = None,
    ) -> None:
        self.registry = registry
        self.cancellation_signal = cancellation_signal
        if (budget_guard is None) != (budget is None) or (budget_guard is None) != (
            budget_state is None
        ):
            raise ValueError("budget_guard、budget 和 budget_state 必须同时提供")
        self.budget_guard = budget_guard
        self.budget = budget
        self.budget_state = budget_state
        self.clock = clock
        self._legacy_budget_lock = asyncio.Lock()

    async def invoke(
        self,
        request: ToolRequest,
        context: RunContext,
        *,
        allowed_tools: frozenset[str],
        granted_permissions: frozenset[str],
        remaining_budget: RemainingBudget,
        budget_guard: BudgetGuard | None = None,
        budget: ExecutionBudget | None = None,
        budget_state: BudgetState | None = None,
        budget_context: ToolBudgetContext | None = None,
        lease_context: ToolLeaseContext | None = None,
    ) -> tuple[ToolResult, tuple[ToolInvocationRecord, ...]]:
        """隔离显式上下文；旧构造器预算以锁保护并写回累计状态。"""

        binding = current_budget_execution_binding()
        if binding is not None:
            if (
                budget_context is not None
                or self.budget_guard is not None
                or any(
                    value is not None
                    for value in (budget_guard, budget, budget_state)
                )
            ):
                raise ValueError("BOUND_BUDGET_MUST_BE_ONLY_ACCOUNTING_PATH")
            if lease_context is not None and (
                lease_context.port is not binding.port
                or lease_context.scope != binding.scope
            ):
                raise ValueError("BOUND_BUDGET_LEASE_MISMATCH")
            if lease_context is None:
                prefix, version = await binding.next_invocation("tool")
                bound_context = ToolLeaseContext(
                    binding.port,
                    binding.scope,
                    prefix,
                    version,
                )
                try:
                    return await self.invoke(
                        request,
                        context,
                        allowed_tools=allowed_tools,
                        granted_permissions=granted_permissions,
                        remaining_budget=remaining_budget,
                        lease_context=bound_context,
                    )
                finally:
                    binding.update_version(bound_context.version)

        constructor_budget = (
            self.budget_guard is not None
            and budget_context is None
            and lease_context is None
            and all(value is None for value in (budget_guard, budget, budget_state))
        )
        if not constructor_budget:
            return await self._invoke_once(
                request,
                context,
                allowed_tools=allowed_tools,
                granted_permissions=granted_permissions,
                remaining_budget=remaining_budget,
                budget_guard=budget_guard,
                budget=budget,
                budget_state=budget_state,
                budget_context=budget_context,
                lease_context=lease_context,
            )
        async with self._legacy_budget_lock:
            assert self.budget_guard is not None
            assert self.budget is not None and self.budget_state is not None
            legacy_context = ToolBudgetContext(
                self.budget_guard,
                self.budget,
                self.budget_state,
            )
            try:
                return await self._invoke_once(
                    request,
                    context,
                    allowed_tools=allowed_tools,
                    granted_permissions=granted_permissions,
                    remaining_budget=remaining_budget,
                    budget_context=legacy_context,
                )
            finally:
                self.budget_state = legacy_context.state

    async def _invoke_once(
        self,
        request: ToolRequest,
        context: RunContext,
        *,
        allowed_tools: frozenset[str],
        granted_permissions: frozenset[str],
        remaining_budget: RemainingBudget,
        budget_guard: BudgetGuard | None = None,
        budget: ExecutionBudget | None = None,
        budget_state: BudgetState | None = None,
        budget_context: ToolBudgetContext | None = None,
        lease_context: ToolLeaseContext | None = None,
    ) -> tuple[ToolResult, tuple[ToolInvocationRecord, ...]]:
        """完成注册、身份、预算、执行、结果和审计治理。"""
        if lease_context is not None and (
            budget_context is not None
            or any(value is not None for value in (budget_guard, budget, budget_state))
            or self.budget_guard is not None
        ):
            raise ValueError("lease_context 必须是唯一预算计账路径")
        if budget_context is not None and any(
            value is not None for value in (budget_guard, budget, budget_state)
        ):
            raise ValueError("budget_context 与旧预算参数不能同时提供")
        if any(value is not None for value in (budget_guard, budget, budget_state)):
            if budget_guard is None or budget is None or budget_state is None:
                raise ValueError("budget_guard、budget 和 budget_state 必须同时提供")
            budget_context = ToolBudgetContext(budget_guard, budget, budget_state)
        elif budget_context is None and self.budget_guard is not None:
            assert self.budget is not None and self.budget_state is not None
            budget_context = ToolBudgetContext(
                self.budget_guard,
                self.budget,
                self.budget_state,
            )

        def record_budget(actual: BudgetCharge) -> bool:
            if lease_context is not None:
                return True
            if budget_context is None:
                return True
            try:
                budget_context.state, _ = budget_context.guard.record_after_node(
                    budget_context.budget,
                    budget_context.state,
                    actual,
                    now_epoch_ms=self._now_epoch_ms(),
                )
            except BudgetExhaustedError:
                return False
            return True

        active_reservation: Reservation | None = None
        lease_delivery_allowed = True

        async def reserve_lease(
            attempt: int, *, max_bytes: int, max_cost_microunits: int
        ) -> bool:
            nonlocal active_reservation
            if lease_context is None:
                return True
            charge = LeaseBudgetCharge(
                calls=1,
                bytes=max_bytes,
                cost_microunits=(
                    lease_context.reserve_cost_microunits
                    if lease_context.reserve_cost_microunits is not None
                    else max_cost_microunits
                ),
            )
            invocation_id = f"{lease_context.invocation_prefix}:{attempt}"
            for _ in range(8):
                try:
                    reserved = await lease_context.port.reserve(
                        lease_context.scope,
                        invocation_id,
                        charge,
                        lease_context.version,
                    )
                    active_reservation = await lease_context.port.mark_dispatched(
                        reserved.reservation_id
                    )
                    lease_context.version = active_reservation.version
                    return True
                except LeaseConflictError:
                    snapshot = await lease_context.port.snapshot(lease_context.scope)
                    lease_context.version = snapshot.version
                except BudgetLeaseError:
                    snapshot = await lease_context.port.snapshot(lease_context.scope)
                    lease_context.version = snapshot.version
                    active_reservation = None
                    return False
            active_reservation = None
            return False

        async def settle_lease(
            outcome: Literal["success", "failed", "cancelled", "unknown"],
            *,
            bytes: int = 0,
            output_tokens: int = 0,
            cost_microunits: int = 0,
        ) -> bool:
            nonlocal active_reservation, lease_delivery_allowed
            if lease_context is None:
                return True
            if active_reservation is None:
                return False
            reservation = active_reservation
            try:
                snapshot = await lease_context.port.settle(
                    reservation.reservation_id,
                    LeaseBudgetCharge(
                        calls=1,
                        bytes=bytes,
                        output_tokens=output_tokens,
                        cost_microunits=cost_microunits,
                        unknown=outcome == "unknown",
                    ),
                    outcome,
                )
                lease_context.version = snapshot.version
                lease_delivery_allowed = snapshot.delivery_allowed
                active_reservation = None
                if snapshot.over_limit:
                    return False
            except BudgetLeaseError:
                return False
            return True

        async def mark_lease_cancelled() -> None:
            if lease_context is not None:
                await lease_context.port.mark_scope_terminal(
                    lease_context.scope, "cancelled"
                )

        records: list[ToolInvocationRecord] = []
        if not isinstance(request, ToolRequest) or not isinstance(context, RunContext):
            return self._failure(request, "TOOL_ARGUMENT_INVALID", records)
        try:
            spec, tool = self.registry.get(request.tool_name)
        except KeyError:
            return self._failure(request, "TOOL_NOT_REGISTERED", records)
        if request.tool_name not in allowed_tools:
            return self._failure(request, "TOOL_NOT_ALLOWED", records)
        if not spec.required_permissions.issubset(granted_permissions):
            return self._failure(request, "TOOL_PERMISSION_DENIED", records)
        if request.has_side_effects or spec.has_side_effects:
            return self._failure(request, "TOOL_SIDE_EFFECT_FORBIDDEN", records)
        arguments = _json_object_to_mapping(request.arguments)
        fields = set(spec.argument_model.model_fields)
        if set(arguments) != fields:
            return self._failure(request, "TOOL_ARGUMENT_INVALID", records)
        try:
            argument_model = spec.argument_model.model_validate(arguments)
        except ValidationError:
            return self._failure(request, "TOOL_ARGUMENT_INVALID", records)
        del argument_model
        if lease_context is not None:
            available = remaining_budget
        elif budget_context is None:
            if not _budget_available(remaining_budget):
                return self._failure(request, "BUDGET_EXHAUSTED", records)
            available = remaining_budget
        else:
            try:
                available = budget_context.guard.check_before_node(
                    budget_context.budget,
                    budget_context.state,
                    BudgetCharge(tool_calls=1),
                    now_epoch_ms=self._now_epoch_ms(),
                )
            except BudgetExhaustedError:
                return self._failure(request, "BUDGET_EXHAUSTED", records)
        max_attempts = (
            spec.max_attempts
            if lease_context is not None
            else min(spec.max_attempts, available.tool_calls)
        )
        effective_timeout = min(
            request.timeout_ms, spec.timeout_ms, available.timeout_ms
        )
        if effective_timeout <= 0:
            return self._failure(request, "BUDGET_EXHAUSTED", records)
        # 所有尝试共享首次确定的本地绝对 deadline；BudgetGuard 同时提供 Run 级 deadline。
        absolute_deadline = asyncio.get_running_loop().time() + effective_timeout / 1000
        checked_before = budget_context is not None
        for attempt in range(1, max_attempts + 1):
            if budget_context is not None and not checked_before:
                try:
                    available = budget_context.guard.check_before_node(
                        budget_context.budget,
                        budget_context.state,
                        BudgetCharge(tool_calls=1),
                        now_epoch_ms=self._now_epoch_ms(),
                    )
                except BudgetExhaustedError:
                    return self._failure(request, "BUDGET_EXHAUSTED", records)
            elif lease_context is None and not _budget_available(available):
                return self._failure(request, "BUDGET_EXHAUSTED", records)
            checked_before = False
            remaining_absolute_ms = int(
                (absolute_deadline - asyncio.get_running_loop().time()) * 1000
            )
            effective_timeout = min(
                request.timeout_ms,
                spec.timeout_ms,
                available.timeout_ms,
                remaining_absolute_ms,
            )
            if effective_timeout <= 0:
                return self._failure(request, "TOOL_TIMEOUT", records)
            if not await reserve_lease(
                attempt,
                max_bytes=min(request.max_output_bytes, spec.max_output_bytes),
                max_cost_microunits=remaining_budget.cost_microunits,
            ):
                return self._failure(request, "BUDGET_EXHAUSTED", records)
            try:
                result = await self._invoke_bounded(
                    tool, request, context, effective_timeout
                )
            except (TimeoutError, _ToolTimeout):
                records.append(
                    self._record(
                        request.tool_name, attempt, "timeout", "TOOL_TIMEOUT", 0
                    )
                )
                if not await settle_lease("unknown") or not record_budget(
                    BudgetCharge(tool_calls=1)
                ):
                    return self._failure(request, "BUDGET_EXHAUSTED", records)
                return self._failure(request, "TOOL_TIMEOUT", records)
            except _ToolCancelled:
                records.append(
                    self._record(
                        request.tool_name, attempt, "cancelled", "TOOL_CANCELLED", 0
                    )
                )
                await mark_lease_cancelled()
                if not await settle_lease("unknown") or not record_budget(
                    BudgetCharge(tool_calls=1)
                ):
                    return self._failure(request, "BUDGET_EXHAUSTED", records)
                return self._failure(request, "TOOL_CANCELLED", records)
            except asyncio.CancelledError:
                records.append(
                    self._record(
                        request.tool_name, attempt, "cancelled", "TOOL_CANCELLED", 0
                    )
                )
                await mark_lease_cancelled()
                if not await settle_lease("unknown") or not record_budget(
                    BudgetCharge(tool_calls=1)
                ):
                    return self._failure(request, "BUDGET_EXHAUSTED", records)
                return self._failure(request, "TOOL_CANCELLED", records)
            except Exception:  # noqa: BLE001 - Tool 异常必须统一归一化且不得泄露原文
                records.append(
                    self._record(
                        request.tool_name, attempt, "failed", "TOOL_EXECUTION_FAILED", 0
                    )
                )
                if not await settle_lease("unknown") or not record_budget(
                    BudgetCharge(tool_calls=1)
                ):
                    return self._failure(request, "BUDGET_EXHAUSTED", records)
                return self._failure(request, "TOOL_EXECUTION_FAILED", records)
            if not isinstance(result, ToolResult):
                records.append(
                    self._record(
                        request.tool_name, attempt, "failed", "TOOL_EXECUTION_FAILED", 0
                    )
                )
                if not await settle_lease("failed") or not record_budget(
                    BudgetCharge(tool_calls=1)
                ):
                    return self._failure(request, "BUDGET_EXHAUSTED", records)
                return self._failure(request, "TOOL_EXECUTION_FAILED", records)
            output_tokens, cost = _usage(result.metadata)
            if output_tokens < 0 or cost < 0:
                records.append(
                    self._record(
                        request.tool_name, attempt, "failed", "BUDGET_EXHAUSTED", 0
                    )
                )
                await settle_lease("unknown")
                return self._failure(request, "BUDGET_EXHAUSTED", records)
            if budget_context is None and lease_context is None and (
                output_tokens > available.output_tokens
                or cost > available.cost_microunits
            ):
                records.append(
                    self._record(
                        request.tool_name, attempt, "failed", "BUDGET_EXHAUSTED", 0
                    )
                )
                return self._failure(request, "BUDGET_EXHAUSTED", records)
            if result.error is None:
                success_error = self._success_error_code(spec, request, result)
                if success_error is not None:
                    records.append(
                        self._record(
                            request.tool_name,
                            attempt,
                            "failed",
                            success_error,
                            0,
                        )
                    )
                    if not await settle_lease(
                        "failed",
                        bytes=result.output_bytes,
                        output_tokens=output_tokens,
                        cost_microunits=cost,
                    ) or not record_budget(
                        BudgetCharge(
                            tool_calls=1,
                            output_tokens=output_tokens,
                            cost_microunits=cost,
                        )
                    ):
                        return self._failure(request, "BUDGET_EXHAUSTED", records)
                    return self._failure(request, success_error, records)
            lease_outcome: Literal["success", "failed"] = (
                "failed" if result.error is not None else "success"
            )
            if not await settle_lease(
                lease_outcome,
                bytes=result.output_bytes,
                output_tokens=output_tokens,
                cost_microunits=cost,
            ) or not record_budget(
                BudgetCharge(
                    tool_calls=1, output_tokens=output_tokens, cost_microunits=cost
                )
            ):
                records.append(
                    self._record(
                        request.tool_name, attempt, "failed", "BUDGET_EXHAUSTED", 0
                    )
                )
                return self._failure(request, "BUDGET_EXHAUSTED", records)
            if result.error is None and not lease_delivery_allowed:
                records.append(
                    self._record(
                        request.tool_name,
                        attempt,
                        "cancelled",
                        "TOOL_CANCELLED",
                        0,
                    )
                )
                return self._failure(request, "TOOL_CANCELLED", records)
            if budget_context is None and lease_context is None:
                available = _consume_tool_call(_consume(available, output_tokens, cost))
                if not _budget_available(available):
                    records.append(
                        self._record(
                            request.tool_name, attempt, "failed", "BUDGET_EXHAUSTED", 0
                        )
                    )
                    return self._failure(request, "BUDGET_EXHAUSTED", records)
            if result.error is not None:
                governed_error = self._govern_error_result(spec, request, result)
                if governed_error is not None:
                    records.append(
                        self._record(
                            request.tool_name,
                            attempt,
                            "failed",
                            governed_error.error.code
                            if governed_error.error
                            else "TOOL_EXECUTION_FAILED",
                            governed_error.output_bytes,
                        )
                    )
                    return governed_error, tuple(records)
                records.append(
                    self._record(
                        request.tool_name,
                        attempt,
                        "failed",
                        _normalized_error(result.error).code,
                        0,
                    )
                )
                if (
                    result.error.retryable
                    and attempt < max_attempts
                    and result.error.side_effect_status == "none"
                ):
                    continue
                return _normalized_error_result(result), tuple(records)
            records.append(
                self._record(
                    request.tool_name, attempt, "succeeded", None, result.output_bytes
                )
            )
            return result, tuple(records)
        return self._failure(request, "BUDGET_EXHAUSTED", records)

    def _now_epoch_ms(self) -> int:
        clock = self.clock
        if clock is None:
            return int(time.time() * 1000)
        value = clock() if callable(clock) else clock.now_epoch_ms()
        return int(value)

    def _govern_error_result(
        self, spec: Any, request: ToolRequest, result: ToolResult
    ) -> ToolResult | None:
        if result.contract_version != spec.result_schema_version:
            return self._failure(request, "TOOL_EXECUTION_FAILED", [])[0]
        if result.output is not None:
            try:
                _validate_result(spec.result_model, result.output)
            except (ValidationError, TypeError, ValueError):
                return self._failure(request, "TOOL_EXECUTION_FAILED", [])[0]
        max_bytes = min(request.max_output_bytes, spec.max_output_bytes)
        if result.output_bytes > max_bytes:
            return self._failure(request, "TOOL_OUTPUT_TOO_LARGE", [])[0]
        return None

    @staticmethod
    def _success_error_code(spec: Any, request: ToolRequest, result: ToolResult) -> str | None:
        """在成功租约结算前完成 Schema 与输出大小治理。"""

        if result.contract_version != spec.result_schema_version:
            return "TOOL_EXECUTION_FAILED"
        try:
            _validate_result(spec.result_model, result.output)
        except (ValidationError, TypeError, ValueError):
            return "TOOL_EXECUTION_FAILED"
        max_bytes = min(request.max_output_bytes, spec.max_output_bytes)
        if result.output_bytes > max_bytes:
            return "TOOL_OUTPUT_TOO_LARGE"
        return None

    async def _invoke_bounded(
        self, tool: Tool, request: ToolRequest, context: RunContext, timeout_ms: int
    ) -> ToolResult:
        """将 Tool 调用与取消唤醒置于同一有界竞争中。"""
        signal = self.cancellation_signal
        if signal is not None and signal.is_requested():
            raise _ToolCancelled
        async with asyncio.timeout(timeout_ms / 1000):
            tool_task = asyncio.create_task(tool.invoke(request, context))
            cancel_task = (
                asyncio.create_task(signal.wait_requested())
                if signal is not None
                else None
            )
            try:
                if cancel_task is None:
                    return await tool_task
                done, _ = await asyncio.wait(
                    {tool_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancel_task in done:
                    tool_task.cancel()
                    await asyncio.gather(tool_task, return_exceptions=True)
                    raise _ToolCancelled
                cancel_task.cancel()
                await asyncio.gather(cancel_task, return_exceptions=True)
                return await tool_task
            finally:
                if cancel_task is not None and not cancel_task.done():
                    cancel_task.cancel()

    def _failure(
        self, request: ToolRequest, code: str, records: list[ToolInvocationRecord]
    ) -> tuple[ToolResult, tuple[ToolInvocationRecord, ...]]:
        contract_version = (
            request.contract_version if isinstance(request, ToolRequest) else "1"
        )
        result = ToolResult(
            contract_version,
            None,
            ToolError(code, "tool_runtime", False, _SAFE_MESSAGES[code], "none"),
            0,
            False,
        )
        return result, tuple(records)

    @staticmethod
    def _record(
        tool_name: str,
        attempt: int,
        status: str,
        error_code: str | None,
        output_bytes: int,
    ) -> ToolInvocationRecord:
        return ToolInvocationRecord(
            str(uuid4()), tool_name, attempt, status, error_code, output_bytes
        )


class _ToolTimeout(Exception):
    pass


class _ToolCancelled(Exception):
    pass


_SAFE_MESSAGES = {
    "TOOL_NOT_REGISTERED": "Tool 未注册",
    "TOOL_NOT_ALLOWED": "Tool 不在允许清单",
    "TOOL_PERMISSION_DENIED": "Tool 权限不足",
    "TOOL_SIDE_EFFECT_FORBIDDEN": "S2 禁止有副作用 Tool",
    "BUDGET_EXHAUSTED": "运行预算已耗尽",
    "TOOL_ARGUMENT_INVALID": "Tool 参数契约无效",
    "TOOL_TIMEOUT": "Tool 执行超时",
    "TOOL_CANCELLED": "Tool 调用已取消",
    "TOOL_OUTPUT_TOO_LARGE": "Tool 输出超过大小限制",
    "TOOL_EXECUTION_FAILED": "Tool 执行失败",
    "CONTENT_REJECTED": "研究内容被安全策略拒绝",
    "CONTENT_UNAVAILABLE": "研究内容暂不可用",
    "SOURCE_AUTH_REQUIRED": "研究来源需要授权",
    "SOURCE_FORBIDDEN": "研究来源拒绝访问",
    "SOURCE_NOT_RUNTIME_ALLOWED": "研究来源不在运行时允许范围",
    "SOURCE_RATE_LIMITED": "研究来源请求受限",
    "SOURCE_SCHEMA_INVALID": "研究来源响应契约无效",
    "SOURCE_TEMPORARY_FAILURE": "研究来源暂时不可用",
}


def _json_object_to_mapping(value: JsonObject) -> dict[str, JsonValue]:
    return {key: _json_to_python(item) for key, item in value.items}


def _json_to_python(value: JsonValue) -> Any:
    if isinstance(value, JsonObject):
        return {key: _json_to_python(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_json_to_python(item) for item in value]
    return value


def _validate_result(model: type[BaseModel], output: JsonValue) -> BaseModel:
    if not isinstance(output, JsonObject):
        raise TypeError("结果必须为 JsonObject")
    return model.model_validate(_json_object_to_mapping(output))


def _usage(metadata: JsonObject) -> tuple[int, int]:
    values: Mapping[str, JsonValue] = _json_object_to_mapping(metadata)
    output_tokens = values.get("output_tokens", 0)
    cost = values.get("cost_microunits", 0)
    return (
        output_tokens if isinstance(output_tokens, int) else 0,
        cost if isinstance(cost, int) else 0,
    )


def _budget_available(remaining: RemainingBudget) -> bool:
    return all(
        isinstance(getattr(remaining, field), int) and getattr(remaining, field) > 0
        for field in (
            "iterations",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "cost_microunits",
            "timeout_ms",
        )
    )


def _consume(
    remaining: RemainingBudget, output_tokens: int, cost: int
) -> RemainingBudget:
    """扣除一次尝试的可信输出 Usage；输入和耗时由父级边界负责。"""
    return RemainingBudget(
        iterations=remaining.iterations,
        tool_calls=remaining.tool_calls,
        input_tokens=remaining.input_tokens,
        output_tokens=remaining.output_tokens - output_tokens,
        cost_microunits=remaining.cost_microunits - cost,
        timeout_ms=remaining.timeout_ms,
    )


def _consume_tool_call(remaining: RemainingBudget) -> RemainingBudget:
    """为已完成的失败尝试扣除一个 Tool 调用额度。"""
    return RemainingBudget(
        iterations=remaining.iterations,
        tool_calls=remaining.tool_calls - 1,
        input_tokens=remaining.input_tokens,
        output_tokens=remaining.output_tokens,
        cost_microunits=remaining.cost_microunits,
        timeout_ms=remaining.timeout_ms,
    )


def _normalized_error(error: ToolError) -> ToolError:
    """将 Tool 自报错误转换为固定安全错误，不回显原文。"""
    code = error.code if error.code in _SAFE_MESSAGES else "TOOL_EXECUTION_FAILED"
    return ToolError(
        code,
        "tool_runtime",
        error.retryable,
        _SAFE_MESSAGES[code],
        error.side_effect_status,
    )


def _normalized_error_result(result: ToolResult) -> ToolResult:
    error = result.error
    if error is None:
        raise ValueError("仅错误结果可归一化")
    return ToolResult(
        result.contract_version,
        None,
        _normalized_error(error),
        0,
        False,
    )
