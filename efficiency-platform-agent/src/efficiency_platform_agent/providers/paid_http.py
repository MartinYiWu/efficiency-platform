"""真实付费HTTP发送前预扣共享预算；失败和取消均不退费用。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import suppress

import httpx

from ..core.context_dispatch import current_context_send_guard
from ..core.execution_control import (
    RunControl,
    consume_http_attempt,
    current_run_control,
)
from ..core.paid_budget import (
    PaidBudgetError,
    PaidBudgetLedger,
    PaidReservation,
    current_paid_scope,
)
from .paid_usage import PaidUsageCollector, input_token_upper_bound

logger = logging.getLogger("efficiency_platform_agent.execution")


class PaidBudgetTransportError(httpx.RequestError):
    def __init__(self, code: str, request: httpx.Request) -> None:
        self.code = code
        super().__init__("付费调用已被预算保护阻止", request=request)


def paid_error_code(error: BaseException) -> str | None:
    """SDK可能包装传输异常，只读取受控类型，不打印厂商异常正文。"""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (PaidBudgetTransportError, PaidBudgetError)):
            return current.code
        current = current.__cause__ or current.__context__
    return None


class _BudgetStream(httpx.AsyncByteStream):
    def __init__(
        self,
        stream: httpx.AsyncByteStream,
        ledger: PaidBudgetLedger,
        reservation: PaidReservation,
        request: httpx.Request,
        collector: PaidUsageCollector,
        request_slots: asyncio.Semaphore | None = None,
        control: RunControl | None = None,
        http_token: object | None = None,
    ) -> None:
        self.stream = stream
        self.ledger = ledger
        self.reservation = reservation
        self.request = request
        self.closed = False
        self.collector = collector
        self.complete = False
        self.request_slots = request_slots
        self.control = control
        self.http_token = http_token
        self.consumer_token = object()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        task = asyncio.current_task()
        if self.control is not None and task is not None:
            self.control.http_tasks[self.consumer_token] = task
        try:
            iterator = self.stream.__aiter__()
            while True:
                if self.control is not None:
                    self.control.check()
                self.ledger.check_live(self.reservation.reservation_id)
                remaining = (
                    self.reservation.deadline_epoch_ms - time.time() * 1000
                ) / 1000
                if remaining <= 0:
                    raise TimeoutError
                try:
                    async with asyncio.timeout(remaining):
                        chunk = await anext(iterator)
                except StopAsyncIteration:
                    self.collector.end()
                    self.complete = True
                    break
                self.ledger.check_live(self.reservation.reservation_id)
                if self.control is not None:
                    self.control.check()
                self.collector.feed(chunk)
                yield chunk
        except PaidBudgetError as error:
            raise PaidBudgetTransportError(error.code, self.request) from None
        except TimeoutError:
            raise PaidBudgetTransportError(
                "PAID_BUDGET_DEADLINE", self.request
            ) from None
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        closed_normally = False
        settled = False
        try:
            await self.stream.aclose()
            closed_normally = True
        finally:
            try:
                try:
                    if (
                        closed_normally
                        and self.complete
                        and self.collector.usage is not None
                    ):
                        self.ledger.settle(
                            self.reservation.reservation_id, self.collector.usage
                        )
                        settled = True
                finally:
                    try:
                        self.ledger.finish(self.reservation.reservation_id)
                    finally:
                        with suppress(Exception):
                            logger.info(
                                "event=paid_http_usage reservation_id=%s provider=%s "
                                "outcome=%s complete=%s close_ok=%s diagnostic=%s",
                                self.reservation.reservation_id,
                                self.collector.provider,
                                "settled" if settled else "unknown",
                                self.complete,
                                closed_normally,
                                json.dumps(
                                    self.collector.diagnostics(), sort_keys=True
                                ),
                            )
            except PaidBudgetError as error:
                raise PaidBudgetTransportError(error.code, self.request) from None
            finally:
                if self.control is not None:
                    self.control.http_tasks.pop(self.http_token, None)
                    self.control.http_tasks.pop(self.consumer_token, None)
                    self.control.streams.pop(self.http_token, None)
                if self.request_slots is not None:
                    self.request_slots.release()
                    self.request_slots = None


class PaidHttpTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        ledger: PaidBudgetLedger,
        inner: httpx.AsyncBaseTransport,
        provider: str,
        *,
        allowed_url: str | None = None,
        request_slots: asyncio.Semaphore | None = None,
        require_context_guard: bool = False,
    ) -> None:
        self.ledger = ledger
        self.inner = inner
        self.provider = provider
        self.allowed_url = allowed_url
        self.budget_id = ledger.active_budget_id()
        self.request_slots = request_slots
        self.require_context_guard = require_context_guard

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        reservation: PaidReservation | None = None
        response: httpx.Response | None = None
        transferred = False
        slot_acquired = False
        control = current_run_control()
        http_token = object()
        task = asyncio.current_task()
        if control is not None:
            control.check()
            if task is not None:
                control.http_tasks[http_token] = task
        try:
            if self.require_context_guard and current_context_send_guard() is None:
                raise PaidBudgetTransportError(
                    "CONTEXT_TRANSPORT_GATE_REQUIRED", request
                )
            if request.method != "POST" or (
                self.allowed_url is not None and str(request.url) != self.allowed_url
            ):
                raise PaidBudgetTransportError("PAID_ENDPOINT_NOT_ALLOWED", request)
            body = await request.aread()
            if len(body) > 1_000_000:
                raise PaidBudgetTransportError("PAID_REQUEST_TOO_LARGE", request)
            try:
                payload = json.loads(body)
                model = payload["model"]
                output_tokens = (
                    payload.get("max_tokens", payload.get("max_completion_tokens"))
                    if self.provider == "deepseek"
                    else 0
                )
                if self.provider == "deepseek" and (
                    ("max_tokens" in payload and "max_completion_tokens" in payload)
                    or payload.get("n", 1) != 1
                    or any(
                        tool.get("type") not in {"function"}
                        for tool in payload.get("tools", [])
                    )
                ):
                    raise ValueError
                if (
                    not isinstance(model, str)
                    or not model.strip()
                    or isinstance(output_tokens, bool)
                    or not isinstance(output_tokens, int)
                    or output_tokens < 0
                ):
                    raise ValueError
                if self.provider == "deepseek" and output_tokens == 0:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise PaidBudgetTransportError(
                    "PAID_REQUEST_BOUND_REQUIRED", request
                ) from None
            if self.request_slots is not None:
                await self.request_slots.acquire()
                slot_acquired = True
            consume_http_attempt()
            reservation = self.ledger.reserve(
                self.budget_id,
                current_paid_scope(),
                self.provider,
                model,
                len(body),
                output_tokens,
                input_tokens=input_token_upper_bound(self.provider, body, payload),
                reasoning_tokens=output_tokens
                if self.provider == "deepseek"
                and payload.get("thinking", {}).get("type") != "disabled"
                else 0,
            )
            remaining = (reservation.deadline_epoch_ms - time.time() * 1000) / 1000
            if remaining <= 0:
                raise PaidBudgetTransportError("PAID_BUDGET_DEADLINE", request)
            context_guard = current_context_send_guard()
            if self.provider == "deepseek" and context_guard is not None:
                await context_guard.before_send(payload)
            if control is not None:
                control.check()
            self.ledger.check_live(reservation.reservation_id)
            if self.provider == "deepseek" and context_guard is not None:
                context_guard.check_live()
            if control is not None:
                control.check()
            remaining = (reservation.deadline_epoch_ms - time.time() * 1000) / 1000
            if remaining <= 0:
                raise PaidBudgetTransportError("PAID_BUDGET_DEADLINE", request)
            # 只协商采集器能够有界解析的编码，避免HTTPX默认接受zstd。
            request.headers["Accept-Encoding"] = "gzip, deflate"
            async with asyncio.timeout(remaining):
                response = await self.inner.handle_async_request(request)
            self.ledger.record_status(reservation.reservation_id, response.status_code)
            if response.status_code >= 400:
                await response.aclose()
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=b"",
                    request=request,
                )
            self.ledger.check_live(reservation.reservation_id)
            if not isinstance(response.stream, httpx.AsyncByteStream):
                raise PaidBudgetTransportError("PAID_RESPONSE_STREAM_INVALID", request)
            stream = _BudgetStream(
                response.stream,
                self.ledger,
                reservation,
                request,
                PaidUsageCollector(
                    self.provider,
                    response.headers.get("content-type", ""),
                    thinking=self.provider == "deepseek"
                    and payload.get("thinking", {}).get("type") != "disabled",
                    content_encoding=response.headers.get("content-encoding", ""),
                ),
                self.request_slots if slot_acquired else None,
                control,
                http_token,
            )
            if control is not None:
                control.streams[http_token] = stream.aclose
            transferred = True
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                stream=stream,
                extensions=response.extensions,
                request=request,
            )
        except PaidBudgetError as error:
            logger.warning(
                "event=paid_http_blocked provider=%s code=%s", self.provider, error.code
            )
            raise PaidBudgetTransportError(error.code, request) from None
        except TimeoutError:
            raise PaidBudgetTransportError("PAID_BUDGET_DEADLINE", request) from None
        finally:
            # 已返回响应由流关闭释放槽位；其他失败保留已扣次数和金额。
            if not transferred:
                if control is not None:
                    control.http_tasks.pop(http_token, None)
                try:
                    try:
                        if response is not None:
                            await response.aclose()
                    finally:
                        if reservation is not None:
                            try:
                                self.ledger.finish(reservation.reservation_id)
                            except PaidBudgetError as error:
                                raise PaidBudgetTransportError(
                                    error.code, request
                                ) from None
                finally:
                    if slot_acquired and self.request_slots is not None:
                        self.request_slots.release()

    async def aclose(self) -> None:
        await self.inner.aclose()
