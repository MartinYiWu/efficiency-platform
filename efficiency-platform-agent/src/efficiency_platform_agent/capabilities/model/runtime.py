"""模型调用 Runtime：预算、取消、有限降级和 Usage 归一化。"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any
from uuid import uuid4

from ...core.budget import (
    BudgetCharge,
    BudgetExhaustedError,
    BudgetGuard,
    BudgetState,
    RemainingBudget,
)
from ...core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
    safe_exception_location,
)
from ...core.model import (
    CancellationSignal,
    ModelCandidate,
    ModelCandidateSelector,
    ModelDemand,
    ModelExecutionResult,
    ModelSelection,
)
from ...core.ports import StreamingModelProvider
from ...core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderStreamChunk,
    ProviderUsage,
)
from ...core.runtime import UsageSnapshot
from ...providers.llm.registry import ModelProviderRegistry

_RETRYABLE_PROVIDER_ERRORS = frozenset(
    {
        ("PROVIDER_TIMEOUT", "timeout"),
        ("PROVIDER_CONNECTION", "connection"),
        ("PROVIDER_RATE_LIMIT", "rate_limit"),
        ("PROVIDER_SERVER_ERROR", "server_error"),
        # DOWN is retained as the deterministic Fake Provider's existing test code.
        ("DOWN", "server_error"),
    }
)


class ModelRuntime:
    """通过候选选择端口执行最多两次模型尝试。"""

    def __init__(
        self,
        selector: ModelCandidateSelector,
        registry: ModelProviderRegistry,
        *,
        budget_guard: BudgetGuard | None = None,
        budget: ExecutionBudget | None = None,
        budget_state: BudgetState | None = None,
        cancellation_signal: CancellationSignal | None = None,
        clock: Any | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        diagnostic_recorder: DiagnosticRecorderPort | None = None,
    ) -> None:
        self.selector = selector
        self.registry = registry
        self.budget_guard = budget_guard
        self.budget = budget
        self.budget_state = budget_state
        self.cancellation_signal = cancellation_signal
        self.clock = clock
        self.monotonic_clock = monotonic_clock or time.monotonic
        self.diagnostic_recorder = diagnostic_recorder or NoopDiagnosticRecorder()

    async def complete(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
    ) -> ModelExecutionResult:
        """执行模型步骤，保留每次候选选择与失败事实。"""
        if not isinstance(demand, ModelDemand) or not isinstance(
            request, ProviderRequest
        ):
            raise TypeError("demand/request 类型不正确")
        if not isinstance(remaining_budget, RemainingBudget):
            raise TypeError("remaining_budget 类型不正确")
        deadline = self._call_deadline(remaining_budget)
        attempts: list[ModelSelection] = []
        unavailable: set[str] = set()
        total = ProviderUsage(0, 0, 0, 0, 0)
        estimated = False
        last_result: ProviderResult | None = None
        current_remaining = remaining_budget
        fallback_pending = False

        for attempt_number in range(1, 3):
            try:
                current_remaining = self._refresh_for_call(current_remaining, deadline)
            except BudgetExhaustedError:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
                break
            if current_remaining.iterations <= 0:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
                break
            candidates = self.selector.candidates(
                demand,
                remaining_budget=current_remaining,
                unavailable_candidate_ids=frozenset(unavailable),
            )
            if not candidates:
                break
            candidate = candidates[0]
            unavailable.add(candidate.candidate_id)
            degraded_from = (
                demand.requested_tier
                if candidate.tier is not demand.requested_tier
                else None
            )
            reason = (
                "requested_tier"
                if degraded_from is None
                else "degraded_after_retryable_error"
            )
            attempts.append(
                ModelSelection(candidate, attempt_number, degraded_from, reason)
            )

            if fallback_pending:
                self._record(
                    DiagnosticRecord(
                        event_name="model_fallback_selected",
                        component="model",
                        level=DiagnosticLevel.WARNING,
                        model=candidate.logical_model,
                        attempt=attempt_number,
                    )
                )
                fallback_pending = False

            if await self._cancel_requested():
                last_result = self._error_result(
                    request, "CANCELLED", "cancelled", "模型调用已取消"
                )
                break

            try:
                current_remaining = self._check_before(demand, current_remaining)
                current_remaining = self._cap_to_deadline(current_remaining, deadline)
            except BudgetExhaustedError:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
                break

            provider_request = replace(
                self._request_for_candidate(request, candidate),
                timeout_ms=min(request.timeout_ms, current_remaining.timeout_ms),
            )
            timeout_seconds = (
                min(provider_request.timeout_ms, current_remaining.timeout_ms) / 1000
            )
            started_at = self.monotonic_clock()
            provider_call_id = f"model-{uuid4().hex}"
            self._record_model_started(candidate, attempt_number, provider_call_id)
            caught_error: BaseException | None = None
            try:
                provider = self.registry.get(candidate.provider_id)
                result = await asyncio.wait_for(
                    provider.complete(provider_request), timeout=timeout_seconds
                )
            except TimeoutError as error:
                caught_error = error
                result = self._error_result(
                    request, "PROVIDER_TIMEOUT", "timeout", "模型调用超时"
                )
            except asyncio.CancelledError as error:
                caught_error = error
                result = self._error_result(
                    request, "CANCELLED", "cancelled", "模型调用已取消"
                )
            except Exception as error:  # noqa: BLE001 - Provider 异常必须归一化且不得外泄
                caught_error = error
                result = self._error_result(
                    request, "PROVIDER_FAILURE", "provider", "模型 Provider 调用失败"
                )

            if not isinstance(result, ProviderResult):
                result = self._error_result(
                    request,
                    "PROVIDER_FAILURE",
                    "provider",
                    "模型 Provider 返回无效结果",
                )

            duration_ms = self._duration_ms(started_at)
            if result.message is not None:
                self._record_model_succeeded(
                    candidate,
                    attempt_number,
                    result.usage,
                    duration_ms,
                    provider_call_id,
                )
            elif result.error is not None:
                self._record_model_failed(
                    candidate,
                    attempt_number,
                    result.error,
                    duration_ms,
                    caught_error,
                    provider_call_id,
                )

            usage = result.usage
            total = ProviderUsage(
                total.input_tokens + usage.input_tokens,
                total.output_tokens + usage.output_tokens,
                total.cached_tokens + usage.cached_tokens,
                total.reasoning_tokens + usage.reasoning_tokens,
                total.cost_microunits + usage.cost_microunits,
            )
            estimated = estimated or candidate.usage_is_estimated
            try:
                current_remaining = self._record_after(usage, current_remaining)
                current_remaining = self._cap_to_deadline(current_remaining, deadline)
            except BudgetExhaustedError:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
                break
            if await self._cancel_requested():
                last_result = self._error_result(
                    request, "CANCELLED", "cancelled", "模型调用已取消"
                )
                break
            last_result = result
            if result.message is not None:
                break
            provider_error = result.error
            if provider_error is None or not self._may_degrade(provider_error):
                break
            if current_remaining.iterations <= 0:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
                break
            fallback_pending = True

        if last_result is None:
            last_result = self._error_result(
                request, "MODEL_UNAVAILABLE", "routing", "没有可用模型候选"
            )
        return ModelExecutionResult(
            result=last_result,
            attempts=tuple(attempts),
            usage=UsageSnapshot(
                total.input_tokens,
                total.output_tokens,
                total.cost_microunits,
                estimated,
            ),
            degraded=any(item.degraded_from is not None for item in attempts),
        )

    async def stream(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
    ) -> AsyncIterator[ProviderStreamChunk]:
        """按既有候选路由执行流式调用，首个增量前才允许自动降级。"""
        if not isinstance(demand, ModelDemand) or not isinstance(
            request, ProviderRequest
        ):
            raise TypeError("demand/request 类型不正确")
        if not isinstance(remaining_budget, RemainingBudget):
            raise TypeError("remaining_budget 类型不正确")
        deadline = self._call_deadline(remaining_budget)
        unavailable: set[str] = set()
        current_remaining = remaining_budget
        degraded_event_pending = False
        for attempt_number in range(1, 3):
            if await self._cancel_requested():
                yield ProviderStreamChunk(
                    error=ProviderError(
                        "CANCELLED", "cancelled", False, "模型调用已取消"
                    )
                )
                return
            try:
                current_remaining = self._refresh_for_call(current_remaining, deadline)
                current_remaining = self._check_before(demand, current_remaining)
                current_remaining = self._cap_to_deadline(current_remaining, deadline)
            except BudgetExhaustedError:
                yield ProviderStreamChunk(
                    error=ProviderError(
                        "BUDGET_EXHAUSTED", "budget", False, "运行预算已耗尽"
                    )
                )
                return
            candidates = self.selector.candidates(
                demand,
                remaining_budget=current_remaining,
                unavailable_candidate_ids=frozenset(unavailable),
            )
            if not candidates:
                yield ProviderStreamChunk(
                    error=ProviderError(
                        "MODEL_UNAVAILABLE", "routing", False, "没有可用模型候选"
                    )
                )
                return
            candidate = candidates[0]
            unavailable.add(candidate.candidate_id)
            if degraded_event_pending or candidate.tier is not demand.requested_tier:
                yield ProviderStreamChunk(event="model_degraded")
                degraded_event_pending = False
            provider = self.registry.get(candidate.provider_id)
            if not isinstance(provider, StreamingModelProvider):
                yield ProviderStreamChunk(
                    error=ProviderError(
                        "PROVIDER_UNAVAILABLE",
                        "provider",
                        False,
                        "Provider 不支持流式调用",
                    )
                )
                return
            provider_request = replace(
                self._request_for_candidate(request, candidate),
                timeout_ms=min(request.timeout_ms, current_remaining.timeout_ms),
            )
            stream = provider.stream(provider_request)
            emitted = False
            retry = False
            timed_out = False
            usage = ProviderUsage(0, 0, 0, 0, 0)
            try:
                try:
                    async with asyncio.timeout(
                        min(provider_request.timeout_ms, current_remaining.timeout_ms)
                        / 1000
                    ):
                        async for chunk in stream:
                            try:
                                current_remaining = self._cap_to_deadline(
                                    current_remaining, deadline
                                )
                            except BudgetExhaustedError:
                                yield ProviderStreamChunk(
                                    error=ProviderError(
                                        "BUDGET_EXHAUSTED",
                                        "budget",
                                        False,
                                        "运行预算已耗尽",
                                    )
                                )
                                return
                            if await self._cancel_requested():
                                yield ProviderStreamChunk(
                                    error=ProviderError(
                                        "CANCELLED",
                                        "cancelled",
                                        False,
                                        "模型调用已取消",
                                    )
                                )
                                return
                            usage = ProviderUsage(
                                max(usage.input_tokens, chunk.usage.input_tokens),
                                max(usage.output_tokens, chunk.usage.output_tokens),
                                max(usage.cached_tokens, chunk.usage.cached_tokens),
                                max(
                                    usage.reasoning_tokens,
                                    chunk.usage.reasoning_tokens,
                                ),
                                max(
                                    usage.cost_microunits,
                                    chunk.usage.cost_microunits,
                                ),
                            )
                            if chunk.error is not None:
                                retry = not emitted and self._may_degrade(chunk.error)
                                if retry:
                                    break
                                yield chunk
                                break
                            emitted = emitted or bool(chunk.delta)
                            yield chunk
                except TimeoutError:
                    timed_out = True
                try:
                    current_remaining = self._record_after(usage, current_remaining)
                    current_remaining = self._cap_to_deadline(
                        current_remaining, deadline
                    )
                except BudgetExhaustedError:
                    yield ProviderStreamChunk(
                        error=ProviderError(
                            "BUDGET_EXHAUSTED", "budget", False, "运行预算已耗尽"
                        )
                    )
                    return
                if timed_out:
                    if not emitted and attempt_number < 2:
                        degraded_event_pending = True
                        continue
                    yield ProviderStreamChunk(
                        error=ProviderError(
                            "PROVIDER_TIMEOUT",
                            "timeout",
                            True,
                            "模型调用超时",
                        )
                    )
                    return
                if retry and attempt_number < 2:
                    degraded_event_pending = True
                    continue
                return
            finally:
                close = getattr(stream, "aclose", None)
                if close is not None:
                    await close()
        yield ProviderStreamChunk(
            error=ProviderError(
                "MODEL_UNAVAILABLE", "routing", False, "没有可用模型候选"
            )
        )

    async def stream_complete(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
        on_delta: Callable[[str], Any],
    ) -> ModelExecutionResult:
        """实时交付正文增量，并在流结束后返回完整的执行事实。"""
        if not isinstance(demand, ModelDemand) or not isinstance(
            request, ProviderRequest
        ):
            raise TypeError("demand/request 类型不正确")
        if not isinstance(remaining_budget, RemainingBudget):
            raise TypeError("remaining_budget 类型不正确")
        if not callable(on_delta):
            raise TypeError("on_delta 必须可调用")

        deadline = self._call_deadline(remaining_budget)
        attempts: list[ModelSelection] = []
        unavailable: set[str] = set()
        total = ProviderUsage(0, 0, 0, 0, 0)
        estimated = False
        current_remaining = remaining_budget
        last_result: ProviderResult | None = None
        fallback_pending = False

        for attempt_number in range(1, 3):
            if await self._cancel_requested():
                last_result = self._error_result(
                    request, "CANCELLED", "cancelled", "模型调用已取消"
                )
                break
            try:
                current_remaining = self._refresh_for_call(current_remaining, deadline)
                current_remaining = self._check_before(demand, current_remaining)
                current_remaining = self._cap_to_deadline(current_remaining, deadline)
            except BudgetExhaustedError:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
                break
            candidates = self.selector.candidates(
                demand,
                remaining_budget=current_remaining,
                unavailable_candidate_ids=frozenset(unavailable),
            )
            if not candidates:
                break
            candidate = candidates[0]
            unavailable.add(candidate.candidate_id)
            attempts.append(
                ModelSelection(
                    candidate,
                    attempt_number,
                    demand.requested_tier
                    if candidate.tier is not demand.requested_tier
                    else None,
                    "requested_tier"
                    if candidate.tier is demand.requested_tier
                    else "degraded_after_retryable_error",
                )
            )
            if fallback_pending:
                self._record(
                    DiagnosticRecord(
                        event_name="model_fallback_selected",
                        component="model",
                        level=DiagnosticLevel.WARNING,
                        model=candidate.logical_model,
                        attempt=attempt_number,
                    )
                )
                fallback_pending = False
            estimated = estimated or candidate.usage_is_estimated
            usage = ProviderUsage(0, 0, 0, 0, 0)
            started_at = self.monotonic_clock()
            provider_call_id = f"model-{uuid4().hex}"
            self._record_model_started(candidate, attempt_number, provider_call_id)
            caught_error: BaseException | None = None
            try:
                provider = self.registry.get(candidate.provider_id)
            except Exception as error:  # noqa: BLE001 - Provider 解析失败必须归一化
                caught_error = error
                last_result = self._error_result(
                    request, "PROVIDER_FAILURE", "provider", "模型 Provider 调用失败"
                )
                assert last_result.error is not None
                self._record_model_failed(
                    candidate,
                    attempt_number,
                    last_result.error,
                    self._duration_ms(started_at),
                    caught_error,
                    provider_call_id,
                )
                break
            if not isinstance(provider, StreamingModelProvider):
                last_result = self._error_result(
                    request,
                    "PROVIDER_UNAVAILABLE",
                    "provider",
                    "Provider 不支持流式调用",
                )
                assert last_result.error is not None
                self._record_model_failed(
                    candidate,
                    attempt_number,
                    last_result.error,
                    self._duration_ms(started_at),
                    None,
                    provider_call_id,
                )
                break
            provider_request = replace(
                self._request_for_candidate(request, candidate),
                timeout_ms=min(request.timeout_ms, current_remaining.timeout_ms),
            )
            text: list[str] = []
            emitted = False
            retry = False
            stream = None
            try:
                try:
                    stream = provider.stream(provider_request)
                    async with asyncio.timeout(provider_request.timeout_ms / 1000):
                        async for chunk in stream:
                            current_remaining = self._cap_to_deadline(
                                current_remaining, deadline
                            )
                            if await self._cancel_requested():
                                last_result = self._error_result(
                                    request, "CANCELLED", "cancelled", "模型调用已取消"
                                )
                                break
                            usage = ProviderUsage(
                                max(usage.input_tokens, chunk.usage.input_tokens),
                                max(usage.output_tokens, chunk.usage.output_tokens),
                                max(usage.cached_tokens, chunk.usage.cached_tokens),
                                max(
                                    usage.reasoning_tokens,
                                    chunk.usage.reasoning_tokens,
                                ),
                                max(
                                    usage.cost_microunits,
                                    chunk.usage.cost_microunits,
                                ),
                            )
                            if chunk.error is not None:
                                retry = not emitted and self._may_degrade(chunk.error)
                                last_result = ProviderResult(
                                    request.contract_version,
                                    None,
                                    usage,
                                    chunk.error,
                                )
                                break
                            if chunk.delta:
                                emitted = True
                                text.append(chunk.delta)
                                callback_result = on_delta(chunk.delta)
                                if inspect.isawaitable(callback_result):
                                    await callback_result
                                if await self._cancel_requested():
                                    last_result = self._error_result(
                                        request,
                                        "CANCELLED",
                                        "cancelled",
                                        "模型调用已取消",
                                    )
                                    break
                        else:
                            last_result = ProviderResult(
                                request.contract_version,
                                ProviderMessage("assistant", "".join(text)),
                                usage,
                            )
                except TimeoutError as error:
                    caught_error = error
                    retry = not emitted
                    last_result = self._error_result(
                        request, "PROVIDER_TIMEOUT", "timeout", "模型调用超时"
                    )
            except BudgetExhaustedError:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - Provider 流异常必须归一化且不得外泄
                caught_error = error
                retry = False
                last_result = self._error_result(
                    request, "PROVIDER_FAILURE", "provider", "模型 Provider 调用失败"
                )
            finally:
                close = getattr(stream, "aclose", None) if stream is not None else None
                if close is not None:
                    try:
                        await close()
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:  # noqa: BLE001 - 关闭流失败同样属于 Provider 边界
                        if caught_error is None:
                            caught_error = error
                            retry = False
                            last_result = self._error_result(
                                request,
                                "PROVIDER_FAILURE",
                                "provider",
                                "模型 Provider 调用失败",
                            )

            total = ProviderUsage(
                total.input_tokens + usage.input_tokens,
                total.output_tokens + usage.output_tokens,
                total.cached_tokens + usage.cached_tokens,
                total.reasoning_tokens + usage.reasoning_tokens,
                total.cost_microunits + usage.cost_microunits,
            )
            duration_ms = self._duration_ms(started_at)
            if last_result is not None and last_result.message is not None:
                self._record_model_succeeded(
                    candidate,
                    attempt_number,
                    usage,
                    duration_ms,
                    provider_call_id,
                )
            elif last_result is not None and last_result.error is not None:
                self._record_model_failed(
                    candidate,
                    attempt_number,
                    last_result.error,
                    duration_ms,
                    caught_error,
                    provider_call_id,
                )
            try:
                current_remaining = self._record_after(usage, current_remaining)
                current_remaining = self._cap_to_deadline(current_remaining, deadline)
            except BudgetExhaustedError:
                last_result = self._error_result(
                    request, "BUDGET_EXHAUSTED", "budget", "运行预算已耗尽"
                )
                break
            if last_result is not None and last_result.error is not None:
                if retry and attempt_number < 2:
                    fallback_pending = True
                    continue
                break
            break

        if last_result is None:
            last_result = self._error_result(
                request, "MODEL_UNAVAILABLE", "routing", "没有可用模型候选"
            )
        return ModelExecutionResult(
            result=last_result,
            attempts=tuple(attempts),
            usage=UsageSnapshot(
                total.input_tokens,
                total.output_tokens,
                total.cost_microunits,
                estimated,
            ),
            degraded=any(item.degraded_from is not None for item in attempts),
        )

    async def _cancel_requested(self) -> bool:
        """兼容同步或异步取消信号。"""
        if self.cancellation_signal is None:
            return False
        value = self.cancellation_signal.wait_requested()
        if inspect.isawaitable(value):
            return bool(await value)
        return bool(value)

    def _record_model_started(
        self, candidate: ModelCandidate, attempt: int, provider_call_id: str
    ) -> None:
        """记录实际候选调用开始，不读取请求正文或选项。"""

        self._record(
            DiagnosticRecord(
                event_name="model_invocation_started",
                component="model",
                level=DiagnosticLevel.INFO,
                provider=candidate.provider_id,
                model=candidate.logical_model,
                provider_call_id=provider_call_id,
                attempt=attempt,
            )
        )

    def _record_model_succeeded(
        self,
        candidate: ModelCandidate,
        attempt: int,
        usage: ProviderUsage,
        duration_ms: int,
        provider_call_id: str,
    ) -> None:
        """记录 Provider 已明确返回的成功用量。"""

        self._record(
            DiagnosticRecord(
                event_name="model_invocation_succeeded",
                component="model",
                level=DiagnosticLevel.INFO,
                provider=candidate.provider_id,
                model=candidate.logical_model,
                provider_call_id=provider_call_id,
                attempt=attempt,
                duration_ms=duration_ms,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
        )

    def _record_model_failed(
        self,
        candidate: ModelCandidate,
        attempt: int,
        error: ProviderError,
        duration_ms: int,
        caught_error: BaseException | None,
        provider_call_id: str,
    ) -> None:
        """记录归一化失败事实，不读取异常正文。"""

        self._record(
            DiagnosticRecord(
                event_name="model_invocation_failed",
                component="model",
                level=DiagnosticLevel.ERROR,
                provider=candidate.provider_id,
                model=candidate.logical_model,
                provider_call_id=provider_call_id,
                error_code=error.code,
                error_type=(
                    type(caught_error).__name__
                    if caught_error is not None
                    else "ProviderError"
                ),
                error_location=(
                    safe_exception_location(caught_error)
                    if caught_error is not None
                    else None
                ),
                retryable=error.retryable,
                duration_ms=duration_ms,
                attempt=attempt,
            )
        )

    def _record(self, record: DiagnosticRecord) -> None:
        """隔离 Recorder 失败，避免诊断改变模型调用语义。"""

        try:
            self.diagnostic_recorder.record(record)
        except Exception:  # noqa: BLE001 - Recorder 异常不得影响模型调用
            return

    def _duration_ms(self, started_at: float) -> int:
        """以单调时钟产生非负耗时。"""

        return max(0, int((self.monotonic_clock() - started_at) * 1000))

    def _request_for_candidate(
        self, request: ProviderRequest, candidate: ModelCandidate
    ) -> ProviderRequest:
        """复制 options 并由 Runtime 控制 logical_model。"""
        options = tuple(
            (key, value)
            for key, value in request.options.items
            if key != "logical_model"
        )
        options += (("logical_model", candidate.logical_model),)
        return replace(request, options=JsonObject(options))

    def _refresh_remaining(self, fallback: RemainingBudget) -> RemainingBudget:
        """每次候选选择前取得最新的 Run 预算快照。"""
        if (
            self.budget_guard is not None
            and self.budget is not None
            and self.budget_state is not None
        ):
            return self.budget_guard.remaining(
                self.budget, self.budget_state, now_epoch_ms=self._now_ms()
            )
        return fallback

    def _call_deadline(self, remaining: RemainingBudget) -> float:
        """为一次 complete/stream 调用建立不可延长的单调时钟截止点。"""
        return self.monotonic_clock() + max(0, remaining.timeout_ms) / 1000

    def _refresh_for_call(
        self, fallback: RemainingBudget, deadline: float
    ) -> RemainingBudget:
        """合并最新 Run 预算与本次调用的绝对截止时间。"""
        return self._cap_to_deadline(self._refresh_remaining(fallback), deadline)

    def _cap_to_deadline(
        self, remaining: RemainingBudget, deadline: float
    ) -> RemainingBudget:
        """收紧 timeout；截止时间到达后稳定失败关闭。"""
        timeout_ms = min(
            remaining.timeout_ms,
            max(0, int((deadline - self.monotonic_clock()) * 1000)),
        )
        if timeout_ms <= 0:
            raise BudgetExhaustedError("absolute_timeout")
        if timeout_ms == remaining.timeout_ms:
            return remaining
        return RemainingBudget(
            remaining.iterations,
            remaining.tool_calls,
            remaining.input_tokens,
            remaining.output_tokens,
            remaining.cost_microunits,
            timeout_ms,
        )

    def _check_before(
        self, demand: ModelDemand, remaining: RemainingBudget
    ) -> RemainingBudget:
        """在可用 BudgetGuard 上执行统一前置检查。"""
        if (
            self.budget_guard is not None
            and self.budget is not None
            and self.budget_state is not None
        ):
            now = self._now_ms()
            return self.budget_guard.check_before_node(
                self.budget,
                self.budget_state,
                BudgetCharge(
                    iterations=1,
                    input_tokens=demand.estimated_input_tokens,
                    output_tokens=demand.max_output_tokens,
                ),
                now_epoch_ms=now,
            )
        if remaining.iterations < 1:
            raise BudgetExhaustedError("iteration_limit")
        if remaining.input_tokens < demand.estimated_input_tokens:
            raise BudgetExhaustedError("input_token_limit")
        if remaining.output_tokens < demand.max_output_tokens:
            raise BudgetExhaustedError("output_token_limit")
        return remaining

    def _record_after(
        self, usage: ProviderUsage, remaining: RemainingBudget
    ) -> RemainingBudget:
        """记录 Provider 明确返回的用量，超限不泄露模型正文。"""
        if (
            self.budget_guard is not None
            and self.budget is not None
            and self.budget_state is not None
        ):
            now = self._now_ms()
            self.budget_state, next_remaining = self.budget_guard.record_after_node(
                self.budget,
                self.budget_state,
                BudgetCharge(
                    iterations=1,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cost_microunits=usage.cost_microunits,
                ),
                now_epoch_ms=now,
            )
            return next_remaining

        next_remaining = RemainingBudget(
            iterations=remaining.iterations - 1,
            tool_calls=remaining.tool_calls,
            input_tokens=remaining.input_tokens - usage.input_tokens,
            output_tokens=remaining.output_tokens - usage.output_tokens,
            cost_microunits=remaining.cost_microunits - usage.cost_microunits,
            timeout_ms=remaining.timeout_ms,
        )
        for reason, value in (
            ("iteration_limit", next_remaining.iterations),
            ("input_token_limit", next_remaining.input_tokens),
            ("output_token_limit", next_remaining.output_tokens),
            ("cost_limit", next_remaining.cost_microunits),
        ):
            if value < 0:
                raise BudgetExhaustedError(reason)
        return next_remaining

    def _now_ms(self) -> int:
        if self.clock is not None and hasattr(self.clock, "now_epoch_ms"):
            return int(self.clock.now_epoch_ms())
        return int(time.time() * 1000)

    @staticmethod
    def _may_degrade(error: ProviderError) -> bool:
        """仅临时 Provider 错误允许切换候选。"""
        return (
            error.retryable
            and (error.code, error.category) in _RETRYABLE_PROVIDER_ERRORS
        )

    @staticmethod
    def _error_result(
        request: ProviderRequest, code: str, category: str, message: str
    ) -> ProviderResult:
        return ProviderResult(
            contract_version=request.contract_version,
            message=None,
            usage=ProviderUsage(0, 0, 0, 0, 0),
            error=ProviderError(code, category, code == "PROVIDER_TIMEOUT", message),
        )
