"""运营对话协议验收 CLI；仅输出白名单 JSON 摘要，不输出正文、身份或配置。

消息可由 --message 显式传入，省略时从标准输入读取，避免写入命令历史。
本脚本会调用指定 Agent 服务；离线测试必须注入 HTTPX MockTransport。
澄清验收只确认 waiting_input，不将其冒称终态；不自动补写用户回答。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from efficiency_platform_agent.contracts.conversation import (
    ConversationMessageV1,
    ConversationSubmitViewV1,
)
from efficiency_platform_agent.contracts.deliverables import DeliverableSetV1
from efficiency_platform_agent.contracts.requests import CancelRunRequestV1
from efficiency_platform_agent.contracts.responses import RunViewV1
from efficiency_platform_agent.contracts.stream_events import RunStreamEventV1

_RUN_TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}
_STREAM_TERMINAL = _RUN_TERMINAL | {"degraded_succeeded"}
_THREE_PLATFORMS = {"xiaohongshu", "wechat_official_account", "toutiao"}
_PUBLIC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SAFE_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_MAX_FRAME_CHARS = 1_000_000


class AcceptanceFailure(Exception):
    """仅携带脚本生成的稳定错误码，不保存远端异常文本。"""


@dataclass(frozen=True, repr=False)
class AcceptanceOptions:
    """显式验收输入；禁止通过对象 repr 泄露身份、地址或消息。"""

    base_url: str
    tenant: str
    user: str
    conversation: str
    message: str
    expect: Literal["succeeded", "clarification", "cancelled"] = "succeeded"
    expect_three_platforms: bool = False
    timeout_seconds: float = 120.0
    max_reconnects: int = 2
    cancel_after_events: int = 1


@dataclass(repr=False)
class _Observation:
    """只在内存中保存校验所需信息，不直接序列化。"""

    cursor: int = 0
    reconnects: int = 0
    clarification: bool = False
    cancelled: bool = False
    stream_error: bool = False
    stream_error_code: str | None = None
    sets: list[DeliverableSetV1] = field(default_factory=list)
    digests: dict[int, str] = field(default_factory=dict)
    view: RunViewV1 | None = None
    run_id: str | None = None
    event_sequence: list[str] = field(default_factory=list)


def _validate_options(options: AcceptanceOptions) -> None:
    """入口失败关闭，禁止 URL 凭据、查询参数和头注入。"""
    parsed = urlsplit(options.base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(
            not _PUBLIC_ID.fullmatch(value)
            for value in (options.tenant, options.user, options.conversation)
        )
        or not options.message.strip()
        or len(options.message) > 20_000
        or options.expect not in {"succeeded", "clarification", "cancelled"}
        or not math.isfinite(options.timeout_seconds)
        or options.timeout_seconds <= 0
        or not 0 <= options.max_reconnects <= 10
        or not 0 <= options.cancel_after_events <= 10_000
    ):
        raise AcceptanceFailure("INVALID_ARGUMENTS")


def _model[T: BaseModel](model: type[T], content: bytes | str, version: str) -> T:
    """拒绝缺失版本与类型强制转换，不让 Pydantic 默认值掩盖协议缺口。"""
    try:
        raw = json.loads(content)
        if not isinstance(raw, dict) or raw.get("contract_version") != version:
            raise ValueError
        return model.model_validate_json(content, strict=True)
    except (ValueError, ValidationError):
        raise AcceptanceFailure("INVALID_CONTRACT") from None


async def _events(response: httpx.Response) -> AsyncIterator[RunStreamEventV1]:
    """按完整 SSE 帧解析，允许保活注释，不允许尾部半帧伪装完整事件。"""
    data: list[str] = []
    transport_id = ""
    transport_event = ""
    size = 0
    async for line in response.aiter_lines():
        size += len(line)
        if size > _MAX_FRAME_CHARS:
            raise AcceptanceFailure("STREAM_FRAME_TOO_LARGE")
        if line == "":
            if data:
                try:
                    event = _model(
                        RunStreamEventV1, "\n".join(data), "run.stream.event/1"
                    )
                except AcceptanceFailure:
                    raise AcceptanceFailure("INVALID_STREAM_EVENT") from None
                if (
                    transport_id != str(event.sequence)
                    or transport_event != event.event
                ):
                    raise AcceptanceFailure("INVALID_STREAM_EVENT")
                yield event
            data, transport_id, transport_event, size = [], "", "", 0
        elif not line.startswith(":"):
            name, separator, value = line.partition(":")
            if separator:
                value = value.removeprefix(" ")
                if name == "data":
                    data.append(value)
                elif name == "id":
                    transport_id = value
                elif name == "event":
                    transport_event = value
    # 尾部未结束的帧由下一次 Last-Event-ID 重连重放，绝不推进游标。


async def _view(client: httpx.AsyncClient, path: str, run_id: str) -> RunViewV1:
    """查询权威 Run，保留正式契约校验而不暴露 output。"""
    response = await client.get(path)
    response.raise_for_status()
    view = _model(RunViewV1, response.content, "run.view/1")
    if view.run_id != run_id:
        raise AcceptanceFailure("RUN_ID_MISMATCH")
    return view


async def _wait_view(
    client: httpx.AsyncClient, path: str, run_id: str, *, allow_waiting: bool
) -> RunViewV1:
    """在调用方统一超时内等待权威终态，澄清模式另允许 waiting_input。"""
    while True:
        view = await _view(client, path, run_id)
        if view.status.value in _RUN_TERMINAL or (
            allow_waiting and view.status.value == "waiting_input"
        ):
            return view
        await asyncio.sleep(0.05)


async def _cancel(
    client: httpx.AsyncClient, path: str, options: AcceptanceOptions
) -> None:
    """只发送取消请求，不把 HTTP 202 当成已取消。"""
    request = CancelRunRequestV1(tenant_id=options.tenant)
    response = await client.post(path + "/cancel", json=request.model_dump(mode="json"))
    if response.status_code != 409:
        response.raise_for_status()
    # 取消与正常完成可能竞争；最终结果仍由事件和 GET Run 一致性决定。


async def _consume(
    client: httpx.AsyncClient, options: AcceptanceOptions, state: _Observation
) -> None:
    """提交一轮消息并消费同一 Run；不重试 POST，避免重复调用模型。"""
    request = ConversationMessageV1(
        message=options.message, request_id=str(uuid4()), user_id=options.user
    )
    response = await client.post(
        f"/v1/conversations/{quote(options.conversation, safe='')}/messages",
        json=request.model_dump(mode="json"),
    )
    if response.status_code != 201:
        raise AcceptanceFailure("SUBMIT_HTTP_ERROR")
    submitted = _model(ConversationSubmitViewV1, response.content, "conversation/1")
    if submitted.conversation_id != options.conversation:
        raise AcceptanceFailure("CONVERSATION_ID_MISMATCH")
    run_id = submitted.run_id
    state.run_id = run_id
    if not _PUBLIC_ID.fullmatch(run_id):
        raise AcceptanceFailure("INVALID_RUN_ID")
    path = f"/v1/runs/{quote(run_id, safe='')}"
    if options.expect == "cancelled" and options.cancel_after_events == 0:
        await _cancel(client, path, options)
        state.cancelled = True
    for attempt in range(options.max_reconnects + 1):
        state.reconnects = attempt
        headers = {"Accept": "text/event-stream"}
        if state.cursor:
            headers["Last-Event-ID"] = str(state.cursor)
        try:
            async with client.stream(
                "GET", path + "/events", headers=headers
            ) as response:
                response.raise_for_status()
                if (
                    response.headers.get("content-type", "").split(";", 1)[0].strip()
                    != "text/event-stream"
                ):
                    raise AcceptanceFailure("INVALID_STREAM_CONTENT_TYPE")
                async for event in _events(response):
                    if event.run_id != run_id:
                        raise AcceptanceFailure("RUN_ID_MISMATCH")
                    digest = hashlib.sha256(
                        event.model_dump_json().encode()
                    ).hexdigest()
                    if event.sequence <= state.cursor:
                        if state.digests.get(event.sequence) != digest:
                            raise AcceptanceFailure("REPLAY_CONFLICT")
                        continue
                    if event.sequence != state.cursor + 1:
                        raise AcceptanceFailure("SEQUENCE_GAP")
                    if event.sequence > 10_000:
                        raise AcceptanceFailure("EVENT_LIMIT_EXCEEDED")
                    state.cursor = event.sequence
                    state.digests[event.sequence] = digest
                    state.event_sequence.append(event.event)
                    if event.event == "deliverable":
                        payload = json.dumps(event.payload.get("deliverable_set"))
                        state.sets.append(
                            _model(DeliverableSetV1, payload, "deliverable-set/1")
                        )
                    if event.event == "clarification_required":
                        fields = event.payload.get("fields")
                        if (
                            not isinstance(event.payload.get("question"), str)
                            or not event.payload["question"].strip()
                            or not isinstance(fields, list)
                            or not all(isinstance(value, str) for value in fields)
                        ):
                            raise AcceptanceFailure("INVALID_CLARIFICATION")
                        state.clarification = True
                    if event.event == "stream_error":
                        state.stream_error = True
                        code = event.payload.get("code")
                        if isinstance(code, str) and _SAFE_ERROR_CODE.fullmatch(code):
                            state.stream_error_code = code
                    if (
                        options.expect == "cancelled"
                        and not state.cancelled
                        and state.cursor >= options.cancel_after_events
                        and event.event != "stream_done"
                    ):
                        await _cancel(client, path, options)
                        state.cancelled = True
                    if event.event == "stream_done":
                        status = event.payload.get("status")
                        if (
                            status not in _STREAM_TERMINAL
                            or type(event.payload.get("degraded")) is not bool
                        ):
                            raise AcceptanceFailure("INVALID_TERMINAL_EVENT")
                        # 展示态别名仅在 SSE 边界归一化，GET 仍严格使用核心 Run 契约。
                        if status == "degraded_succeeded":
                            if event.payload["degraded"] is not True:
                                raise AcceptanceFailure("INVALID_TERMINAL_EVENT")
                            status = "succeeded"
                        if status == "succeeded" and state.stream_error:
                            raise AcceptanceFailure("ERROR_EVENT_WITH_SUCCESS")
                        state.view = await _wait_view(
                            client, path, run_id, allow_waiting=False
                        )
                        if (
                            state.view.status.value != status
                            or state.view.degraded != event.payload["degraded"]
                        ):
                            raise AcceptanceFailure("TERMINAL_STATE_MISMATCH")
                        return
                    if state.clarification:
                        state.view = await _wait_view(
                            client,
                            path,
                            run_id,
                            allow_waiting=options.expect != "cancelled",
                        )
                        return
        except httpx.TransportError:
            if attempt == options.max_reconnects:
                raise AcceptanceFailure("STREAM_INCOMPLETE") from None
    raise AcceptanceFailure("STREAM_INCOMPLETE")


def _summary(
    state: _Observation,
    error: str | None,
    *,
    include_details: bool = False,
) -> dict[str, Any]:
    """仅序列化固定白名单字段；详情模式只增加 Run 标识和事件名称。"""
    view = state.view
    items = [item for group in state.sets for item in group.deliverables]
    result: dict[str, Any] = {
        "contract_version": "operation.acceptance/1",
        "passed": error is None,
        "error_code": error,
        "status": (
            "degraded_succeeded"
            if view and view.status.value == "succeeded" and view.degraded
            else view.status.value
            if view
            else "unconfirmed"
        ),
        "terminal": view is not None and view.status.value in _RUN_TERMINAL,
        "event_count": state.cursor,
        "reconnect_count": state.reconnects,
        "deliverable_count": len(items),
        "citation_count": sum(len(item.citations) for item in items),
        "clarification_observed": state.clarification,
        "cancel_requested": state.cancelled,
        "degraded": view.degraded if view else None,
        "usage": view.usage.model_dump(mode="json") if view else None,
    }
    if include_details:
        result["run_id"] = state.run_id
        result["event_sequence"] = list(state.event_sequence)
    return result


async def run_acceptance(
    options: AcceptanceOptions,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    include_details: bool = False,
) -> dict[str, Any]:
    """执行有界验收；离线单测通过传输注入保证零真实网络。"""
    state = _Observation()
    error: str | None = None
    try:
        _validate_options(options)
        async with asyncio.timeout(options.timeout_seconds):
            async with httpx.AsyncClient(
                base_url=options.base_url.rstrip("/"),
                headers={"X-Tenant-ID": options.tenant},
                timeout=options.timeout_seconds,
                transport=transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                await _consume(client, options, state)
        expected_status = (
            "waiting_input" if options.expect == "clarification" else options.expect
        )
        if state.view is None or state.view.status.value != expected_status:
            raise AcceptanceFailure(
                state.stream_error_code
                if state.view is not None
                and state.view.status.value == "failed"
                and state.stream_error_code is not None
                else "UNEXPECTED_OUTCOME"
            )
        if options.expect == "clarification" and not state.clarification:
            raise AcceptanceFailure("CLARIFICATION_NOT_OBSERVED")
        if options.expect == "cancelled" and not state.cancelled:
            raise AcceptanceFailure("CANCEL_NOT_REQUESTED")
        if options.expect_three_platforms:
            items = [item for group in state.sets for item in group.deliverables]
            if (
                len(items) != 3
                or {item.platform for item in items} != _THREE_PLATFORMS
                or len({item.body.strip() for item in items}) != 3
            ):
                raise AcceptanceFailure("THREE_PLATFORM_CHECK_FAILED")
    except AcceptanceFailure as failure:
        error = str(failure)
    except (TimeoutError, httpx.TimeoutException):
        error = "ACCEPTANCE_TIMEOUT"
    except httpx.HTTPError:
        error = "HTTP_REQUEST_FAILED"
    except Exception:  # noqa: BLE001 — 安全边界必须隐藏第三方异常中的正文和配置。
        error = "ACCEPTANCE_INTERNAL_ERROR"
    return _summary(state, error, include_details=include_details)


class _SafeArgumentParser(argparse.ArgumentParser):
    """屏蔽 argparse 默认回显不合法参数原值的行为。"""

    def error(self, message: str) -> NoReturn:
        raise AcceptanceFailure("INVALID_ARGUMENTS")


def main(argv: Sequence[str] | None = None) -> int:
    """打印一条脱敏 JSON；返回零表示预期验收通过。"""
    parser = _SafeArgumentParser(description="运营对话协议验收；只输出脱敏 JSON 摘要")
    for name in ("base-url", "tenant", "user", "conversation"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--message", help="省略时从标准输入读取消息，不回显")
    parser.add_argument(
        "--expect",
        choices=("succeeded", "clarification", "cancelled"),
        default="succeeded",
    )
    parser.add_argument("--expect-three-platforms", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-reconnects", type=int, default=2)
    parser.add_argument("--cancel-after-events", type=int, default=1)
    try:
        args = parser.parse_args(argv)
        message = args.message if args.message is not None else sys.stdin.read(20_001)
        result = asyncio.run(
            run_acceptance(AcceptanceOptions(**{**vars(args), "message": message}))
        )
    except AcceptanceFailure:
        result = _summary(_Observation(), "INVALID_ARGUMENTS")
    except KeyboardInterrupt:
        result = _summary(_Observation(), "ACCEPTANCE_INTERRUPTED")
    except Exception:  # noqa: BLE001 — CLI 最外层禁止将异常堆栈写入验收证据。
        result = _summary(_Observation(), "ACCEPTANCE_INTERNAL_ERROR")
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
