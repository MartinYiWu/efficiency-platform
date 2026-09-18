"""仅用 HTTPX 内存传输验证运营对话验收脚本，不访问外网。"""

from __future__ import annotations

import asyncio
import io
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from efficiency_platform_agent.contracts.deliverables import DeliverableSetV2
from scripts.operation_chat_acceptance import AcceptanceOptions, main, run_acceptance

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROGRESS_LEDGER = (
    _PROJECT_ROOT
    / "docs/superpowers/progress/2026-09-17-运营Agent专业化交付与质量闭环-进度.md"
)


def options(**changes: Any) -> AcceptanceOptions:
    """构造不包含真实身份或配置的离线验收参数。"""
    return replace(
        AcceptanceOptions(
            base_url="http://agent.test",
            tenant="private-tenant",
            user="private-user",
            conversation="private-conversation",
            message="private-request-body",
        ),
        **changes,
    )


def frame(number: int, event: str, payload: dict[str, Any], **changes: Any) -> str:
    """使用与正式 API 相同的完整事件信封。"""
    value = {
        "contract_version": "run.stream.event/1",
        "run_id": "private-run",
        "sequence": number,
        "event": event,
        "payload": payload,
    }
    value.update(changes)
    return f"id: {number}\nevent: {event}\ndata: {json.dumps(value)}\n\n"


def deliverables() -> dict[str, Any]:
    """提供三平台独立正文和引用，检测摘要是否泄露原文。"""
    return {
        "contract_version": "deliverable-set/1",
        "summary": "private-summary",
        "degraded": False,
        "deliverables": [
            {
                "contract_version": "deliverable/1",
                "platform": platform,
                "title": "private-title",
                "body": f"private-model-body-{index}",
                "hashtags": [],
                "format_notes": [],
                "citations": [
                    {
                        "url": "https://private-source.test",
                        "title": None,
                        "source": None,
                    }
                ],
                "warnings": [],
            }
            for index, platform in enumerate(
                ("xiaohongshu", "wechat_official_account", "toutiao")
            )
        ],
    }


def test_progress_ledger_frozen_v2_sample_matches_delivery_contract() -> None:
    """前端消费的冻结样例必须持续通过正式 V2 契约。"""

    content = _PROGRESS_LEDGER.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- frozen-deliverable-set-v2-sample -->\s*```json\s*(\{.*?\})\s*```",
        content,
        re.DOTALL,
    )

    assert match is not None, "正式进度账本缺少冻结 DeliverableSetV2 样例"
    value = DeliverableSetV2.model_validate(json.loads(match.group(1)))

    assert len(value.deliverables) == 1
    assert value.deliverables[0].content.kind == "ranked_digest"
    assert len(value.deliverables[0].content.items) == 9
    assert len(value.deliverables[0].citations) == 2
    assert {
        citation.url.split("/")[2] for citation in value.deliverables[0].citations
    } == {"example.test"}
    assert [action.action_type for action in value.next_actions] == [
        "rewrite_for_platform"
    ]
    assert value.provenance is not None
    assert value.warnings == []


def run_view(status: str, *, degraded: bool = False) -> dict[str, Any]:
    """构造正式 RunView 所要求的完整响应。"""
    return {
        "contract_version": "run.view/1",
        "run_id": "private-run",
        "request_id": "private-request",
        "status": status,
        "degraded": degraded,
        "strategy": "multi_agent",
        "output": None,
        "usage": {
            "input_tokens": 11,
            "output_tokens": 7,
            "cost_microunits": 3,
            "estimated": False,
        },
    }


class Endpoint:
    """只模拟 HTTP 边界，脚本自身的解析、状态机与校验均真实运行。"""

    def __init__(
        self,
        streams: list[str],
        *,
        status: str = "succeeded",
        degraded: bool = False,
        strategy: str = "multi_agent",
    ) -> None:
        self.streams = streams
        self.status = status
        self.degraded = degraded
        self.strategy = strategy
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                201,
                json={
                    "contract_version": "conversation/1",
                    "conversation_id": "private-conversation",
                    "turn_id": "private-turn",
                    "run_id": "private-run",
                    "status": "queued",
                },
            )
        if request.url.path.endswith("/cancel"):
            return httpx.Response(202, json=run_view("running"))
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                text=self.streams.pop(0),
                headers={"Content-Type": "text/event-stream"},
            )
        result = run_view(self.status, degraded=self.degraded)
        result["strategy"] = self.strategy
        return httpx.Response(200, json=result)


async def test_direct_chat_without_deliverables_passes_and_keeps_summary_safe() -> None:
    """正式 DIRECT 普通正文流不需要交付物，验收摘要也不泄露正文。"""
    endpoint = Endpoint(
        [
            frame(1, "run_started", {"status": "running"})
            + frame(2, "assistant_started", {})
            + frame(3, "assistant_delta", {"delta": "private-chat-body"})
            + frame(4, "stream_done", {"status": "succeeded", "degraded": False})
        ],
        strategy="direct",
    )

    result = await run_acceptance(options(), transport=httpx.MockTransport(endpoint))

    assert result["passed"] is True
    assert result["terminal"] is True
    assert result["status"] == "succeeded"
    assert result["event_count"] == 4
    assert result["deliverable_count"] == 0
    assert result["citation_count"] == 0
    assert result["clarification_observed"] is False
    assert "private" not in json.dumps(result)


async def test_three_platforms_and_safe_summary() -> None:
    endpoint = Endpoint(
        [
            ": keep-alive\n\n"
            + frame(1, "run_started", {"status": "running"})
            + frame(2, "deliverable", {"deliverable_set": deliverables()})
            + frame(3, "stream_done", {"status": "succeeded", "degraded": False})
        ]
    )
    result = await run_acceptance(
        options(expect_three_platforms=True), transport=httpx.MockTransport(endpoint)
    )
    assert result["passed"] is True
    assert result["terminal"] is True
    assert result["deliverable_count"] == 3
    assert result["citation_count"] == 3
    assert result["usage"]["input_tokens"] == 11
    assert "private" not in json.dumps(result)
    assert all(
        request.headers["X-Tenant-ID"] == "private-tenant"
        for request in endpoint.requests
    )
    body = json.loads(endpoint.requests[0].content)
    assert body["contract_version"] == "conversation/1"
    assert body["attachments"] == []
    assert body["message"] == "private-request-body"


@pytest.mark.parametrize("stream_status", ["succeeded", "degraded_succeeded"])
async def test_formal_degraded_success_is_a_confirmed_terminal(
    stream_status: str,
) -> None:
    endpoint = Endpoint(
        [frame(1, "stream_done", {"status": stream_status, "degraded": True})],
        degraded=True,
    )
    result = await run_acceptance(options(), transport=httpx.MockTransport(endpoint))
    assert result["passed"] is True
    assert result["terminal"] is True
    assert result["status"] == "degraded_succeeded"
    assert result["degraded"] is True


async def test_degraded_stream_alias_must_agree_with_formal_get() -> None:
    endpoint = Endpoint(
        [frame(1, "stream_done", {"status": "degraded_succeeded", "degraded": True})],
        degraded=False,
    )
    result = await run_acceptance(options(), transport=httpx.MockTransport(endpoint))
    assert result["error_code"] == "TERMINAL_STATE_MISMATCH"


@pytest.mark.parametrize(
    "change",
    [
        {"contract_version": "wrong"},
        {"run_id": "other"},
        {"sequence": "1"},
        {"sequence": True},
        {"extra": "private-secret"},
    ],
)
async def test_invalid_envelope_fails_closed(change: dict[str, Any]) -> None:
    endpoint = Endpoint([frame(1, "run_started", {}, **change)])
    result = await run_acceptance(options(), transport=httpx.MockTransport(endpoint))
    assert result["passed"] is False
    assert result["error_code"] in {"INVALID_STREAM_EVENT", "RUN_ID_MISMATCH"}
    assert "private" not in json.dumps(result)


async def test_sequence_gap_is_rejected() -> None:
    endpoint = Endpoint(
        [frame(2, "stream_done", {"status": "succeeded", "degraded": False})]
    )
    result = await run_acceptance(options(), transport=httpx.MockTransport(endpoint))
    assert result["error_code"] == "SEQUENCE_GAP"


async def test_clean_eof_reconnect_uses_cursor_and_deduplicates() -> None:
    first = frame(1, "run_started", {"status": "running"})
    endpoint = Endpoint(
        [
            first,
            first + frame(2, "stream_done", {"status": "succeeded", "degraded": False}),
        ]
    )
    result = await run_acceptance(
        options(max_reconnects=1), transport=httpx.MockTransport(endpoint)
    )
    assert result["passed"] is True
    assert result["event_count"] == 2
    streams = [item for item in endpoint.requests if item.url.path.endswith("/events")]
    assert streams[1].headers["Last-Event-ID"] == "1"


async def test_clean_eof_exhaustion_is_failure() -> None:
    endpoint = Endpoint(["", ""])
    result = await run_acceptance(
        options(max_reconnects=1), transport=httpx.MockTransport(endpoint)
    )
    assert result["error_code"] == "STREAM_INCOMPLETE"


async def test_clarification_requires_authoritative_waiting_state() -> None:
    endpoint = Endpoint(
        [
            frame(
                1,
                "clarification_required",
                {"question": "private-question", "fields": ["product"]},
            )
        ],
        status="waiting_input",
    )
    result = await run_acceptance(
        options(expect="clarification"), transport=httpx.MockTransport(endpoint)
    )
    assert result["passed"] is True
    assert result["status"] == "waiting_input"
    assert result["terminal"] is False
    assert result["clarification_observed"] is True
    assert "private" not in json.dumps(result)


async def test_cancel_202_waits_for_server_terminal() -> None:
    endpoint = Endpoint(
        [
            frame(1, "run_started", {"status": "running"})
            + frame(2, "stream_done", {"status": "cancelled", "degraded": False})
        ],
        status="cancelled",
    )
    result = await run_acceptance(
        options(expect="cancelled"), transport=httpx.MockTransport(endpoint)
    )
    assert result["passed"] is True
    assert result["status"] == "cancelled"
    cancel = next(
        item for item in endpoint.requests if item.url.path.endswith("/cancel")
    )
    assert json.loads(cancel.content) == {
        "contract_version": "run.cancel/1",
        "tenant_id": "private-tenant",
        "reason_code": "user_requested",
    }


async def test_done_must_match_run_view() -> None:
    endpoint = Endpoint(
        [frame(1, "stream_done", {"status": "succeeded", "degraded": False})],
        status="failed",
    )
    result = await run_acceptance(options(), transport=httpx.MockTransport(endpoint))
    assert result["error_code"] == "TERMINAL_STATE_MISMATCH"


async def test_three_platform_gate_rejects_reused_body() -> None:
    value = deliverables()
    value["deliverables"][1]["body"] = value["deliverables"][0]["body"]
    endpoint = Endpoint(
        [
            frame(1, "deliverable", {"deliverable_set": value})
            + frame(2, "stream_done", {"status": "succeeded", "degraded": False})
        ]
    )
    result = await run_acceptance(
        options(expect_three_platforms=True), transport=httpx.MockTransport(endpoint)
    )
    assert result["error_code"] == "THREE_PLATFORM_CHECK_FAILED"


async def test_timeout_is_bounded_and_safe() -> None:
    async def slow(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        raise AssertionError("不应到达真实请求")

    result = await run_acceptance(
        options(timeout_seconds=0.01), transport=httpx.MockTransport(slow)
    )
    assert result["error_code"] == "ACCEPTANCE_TIMEOUT"


def test_cli_invalid_arguments_never_echo_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--unknown-private-secret"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["error_code"] == "INVALID_ARGUMENTS"
    assert "private" not in captured.out


async def test_remote_exception_never_leaks_details() -> None:
    def broken(_: httpx.Request) -> httpx.Response:
        raise RuntimeError("private-key-and-model-body")

    result = await run_acceptance(options(), transport=httpx.MockTransport(broken))
    assert result["error_code"] == "ACCEPTANCE_INTERNAL_ERROR"
    assert "private" not in json.dumps(result)


async def test_cancel_202_without_terminal_does_not_pass() -> None:
    endpoint = Endpoint([frame(1, "run_started", {"status": "running"}), ""])
    result = await run_acceptance(
        options(expect="cancelled", max_reconnects=1),
        transport=httpx.MockTransport(endpoint),
    )
    assert result["passed"] is False
    assert result["terminal"] is False
    assert result["error_code"] == "STREAM_INCOMPLETE"


async def test_conflicting_replay_fails_closed() -> None:
    endpoint = Endpoint(
        [
            frame(1, "assistant_delta", {"delta": "private-a"}),
            frame(1, "assistant_delta", {"delta": "private-b"}),
        ]
    )
    result = await run_acceptance(
        options(max_reconnects=1), transport=httpx.MockTransport(endpoint)
    )
    assert result["error_code"] == "REPLAY_CONFLICT"


async def test_invalid_clarification_fields_are_rejected() -> None:
    endpoint = Endpoint(
        [
            frame(
                1,
                "clarification_required",
                {"question": "private-question", "fields": "not-a-list"},
            )
        ],
        status="waiting_input",
    )
    result = await run_acceptance(
        options(expect="clarification"), transport=httpx.MockTransport(endpoint)
    )
    assert result["error_code"] == "INVALID_CLARIFICATION"


async def test_error_event_cannot_be_followed_by_accepted_success() -> None:
    endpoint = Endpoint(
        [
            frame(1, "stream_error", {"safe_message": "private-error"})
            + frame(2, "stream_done", {"status": "succeeded", "degraded": False})
        ]
    )
    result = await run_acceptance(options(), transport=httpx.MockTransport(endpoint))
    assert result["error_code"] == "ERROR_EVENT_WITH_SUCCESS"


def test_cli_stdin_and_json_output_are_safe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    endpoint = Endpoint(
        [frame(1, "stream_done", {"status": "succeeded", "degraded": False})]
    )

    async def offline(value: AcceptanceOptions) -> dict[str, Any]:
        assert value.message == "private-stdin"
        return await run_acceptance(value, transport=httpx.MockTransport(endpoint))

    monkeypatch.setattr("scripts.operation_chat_acceptance.run_acceptance", offline)
    monkeypatch.setattr("sys.stdin", io.StringIO("private-stdin"))
    assert (
        main(
            [
                "--base-url",
                "http://agent.test",
                "--tenant",
                "private-tenant",
                "--user",
                "private-user",
                "--conversation",
                "private-conversation",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["passed"] is True
    assert "private" not in captured.out
