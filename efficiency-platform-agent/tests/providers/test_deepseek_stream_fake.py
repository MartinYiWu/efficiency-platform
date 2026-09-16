"""DeepSeek 流式 Provider 的离线协议测试。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from efficiency_platform_agent.core.diagnostics import DiagnosticRecord
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
    ProviderError,
)


class _FakeResponse:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code
        self.closed = False

    async def aiter_lines(self):
        for line in self._lines:
            await asyncio.sleep(0)
            yield line

    async def aread(self) -> bytes:
        return b""


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> _FakeResponse:
        return self.response

    async def __aexit__(self, *_: object) -> None:
        self.response.closed = True


class _FakeHttp:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def stream(self, method: str, url: str, **kwargs: Any) -> _FakeStream:
        self.calls.append({"method": method, "url": url, **kwargs})
        return _FakeStream(self.response)


class _SequencedFakeHttp:
    """按网络尝试顺序返回不同响应。"""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def stream(self, method: str, url: str, **kwargs: Any) -> _FakeStream:
        self.calls.append({"method": method, "url": url, **kwargs})
        return _FakeStream(self.responses[len(self.calls) - 1])


class _DiagnosticRecorder:
    """收集 Provider 网络尝试的受控诊断记录。"""

    def __init__(self) -> None:
        self.records: list[DiagnosticRecord] = []

    def record(self, record: DiagnosticRecord) -> None:
        self.records.append(record)


def _request() -> ProviderRequest:
    return ProviderRequest(
        "conversation/1",
        (ProviderMessage("user", "你好"),),
        JsonObject((("temperature", 0),)),
        1000,
    )


def _data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}"


@pytest.mark.asyncio
async def test_stream_preserves_deltas_and_merges_final_usage() -> None:
    response = _FakeResponse(
        [
            _data({"choices": [{"delta": {"content": "你好"}}]}),
            _data({"choices": [{"delta": {"content": "，世界"}}]}),
            _data(
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                }
            ),
            "data: [DONE]",
        ]
    )
    http = _FakeHttp(response)
    provider = DeepSeekStreamingProvider(http, "deepseek-chat", api_key="synthetic")

    chunks = [chunk async for chunk in provider.stream(_request())]

    assert [chunk.delta for chunk in chunks] == ["你好", "，世界", ""]
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage.input_tokens == 3
    assert chunks[-1].usage.output_tokens == 2
    assert http.calls[0]["headers"]["Authorization"] == "Bearer synthetic"
    assert "你好" not in str(http.calls[0]["headers"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "PROVIDER_AUTHENTICATION"), (429, "PROVIDER_RATE_LIMIT")],
)
async def test_http_status_is_stable_provider_error(status: int, code: str) -> None:
    provider = DeepSeekStreamingProvider(
        _FakeHttp(_FakeResponse([], status_code=status)),
        "deepseek-chat",
        api_key="synthetic",
    )

    chunks = [chunk async for chunk in provider.stream(_request())]

    assert len(chunks) == 1
    assert isinstance(chunks[0].error, ProviderError)
    assert chunks[0].error.code == code
    assert "synthetic" not in chunks[0].error.safe_message


@pytest.mark.asyncio
async def test_network_retries_have_distinct_call_ids_and_safe_terminal_facts() -> None:
    """每次真实网络尝试须独立关联，且不得记录请求正文或密钥。"""

    recorder = _DiagnosticRecorder()
    http = _SequencedFakeHttp(
        [
            _FakeResponse([], status_code=503),
            _FakeResponse(["data: [DONE]"]),
        ]
    )
    provider = DeepSeekStreamingProvider(
        http,
        "deepseek-chat",
        api_key="synthetic-secret",
        max_retries=1,
        diagnostic_recorder=recorder,
    )

    chunks = [chunk async for chunk in provider.stream(_request())]

    assert chunks == []
    assert len(http.calls) == 2
    assert [record.event_name for record in recorder.records] == [
        "provider_request_started",
        "provider_request_retrying",
        "provider_request_started",
        "provider_request_succeeded",
    ]
    first_started, retrying, second_started, succeeded = recorder.records
    assert first_started.provider_call_id == retrying.provider_call_id
    assert second_started.provider_call_id == succeeded.provider_call_id
    assert first_started.provider_call_id != second_started.provider_call_id
    assert retrying.http_status == 503
    assert retrying.error_code == "PROVIDER_SERVER_ERROR"
    assert retrying.attempt == 1
    assert succeeded.attempt == 2
    diagnostic_text = repr(recorder.records)
    assert "synthetic-secret" not in diagnostic_text
    assert "你好" not in diagnostic_text


@pytest.mark.asyncio
async def test_cancelled_stream_propagates_and_closes_response() -> None:
    response = _FakeResponse([_data({"choices": [{"delta": {"content": "a"}}]})])
    provider = DeepSeekStreamingProvider(
        _FakeHttp(response), "deepseek-chat", api_key="synthetic"
    )

    async def consume() -> None:
        async for _ in provider.stream(_request()):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await consume()


@pytest.mark.asyncio
async def test_consumer_closing_async_iterator_closes_response() -> None:
    response = _FakeResponse([_data({"choices": [{"delta": {"content": "a"}}]})])
    provider = DeepSeekStreamingProvider(
        _FakeHttp(response), "deepseek-chat", api_key="synthetic"
    )
    iterator = provider.stream(_request())

    await anext(iterator)
    await iterator.aclose()

    assert response.closed is True


@pytest.mark.asyncio
async def test_cancellation_signal_stops_before_network_iteration() -> None:
    class _Signal:
        def wait_requested(self) -> bool:
            return True

    http = _FakeHttp(_FakeResponse([]))
    recorder = _DiagnosticRecorder()
    provider = DeepSeekStreamingProvider(
        http,
        "deepseek-chat",
        api_key="synthetic",
        cancellation_signal=_Signal(),
        diagnostic_recorder=recorder,
    )

    with pytest.raises(asyncio.CancelledError):
        _ = [chunk async for chunk in provider.stream(_request())]
    assert http.calls == []
    assert recorder.records == []


@pytest.mark.asyncio
async def test_cancellation_after_network_start_records_safe_terminal_fact() -> None:
    """已开始的网络尝试被取消时必须产生配对终态诊断。"""

    class _Signal:
        requested = False

        def wait_requested(self) -> bool:
            return self.requested

    signal = _Signal()
    recorder = _DiagnosticRecorder()
    response = _FakeResponse(
        [
            _data({"choices": [{"delta": {"content": "a"}}]}),
            _data({"choices": [{"delta": {"content": "b"}}]}),
        ]
    )
    provider = DeepSeekStreamingProvider(
        _FakeHttp(response),
        "deepseek-chat",
        api_key="synthetic",
        cancellation_signal=signal,
        diagnostic_recorder=recorder,
    )
    iterator = provider.stream(_request())
    first = await anext(iterator)
    signal.requested = True

    with pytest.raises(asyncio.CancelledError):
        await anext(iterator)

    assert first.delta == "a"
    assert [record.event_name for record in recorder.records] == [
        "provider_request_started",
        "provider_request_cancelled",
    ]
    assert recorder.records[0].provider_call_id == recorder.records[1].provider_call_id
    assert recorder.records[1].error_code == "CANCELLED"


@pytest.mark.asyncio
async def test_httpx_mock_transport_receives_normalized_json_payload() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        body = _data({"choices": [{"delta": {"content": "ok"}}]}) + "\ndata: [DONE]\n"
        return httpx.Response(200, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekStreamingProvider(
        client,
        "deepseek-chat",
        api_key="synthetic",
        logical_model_map={"internal-name": "deepseek-chat"},
    )
    request = ProviderRequest(
        "conversation/1",
        (ProviderMessage("user", JsonObject((("nested", ("a", "b")),))),),
        JsonObject(
            (
                ("logical_model", "internal-name"),
                ("json_schema", JsonObject((("type", "object"),))),
                (
                    "response_format",
                    JsonObject(
                        (("type", "json_schema"), ("json_schema", JsonObject()))
                    ),
                ),
            )
        ),
        1000,
    )

    chunks = [chunk async for chunk in provider.stream(request)]
    await client.aclose()

    assert chunks[0].delta == "ok"
    assert seen[0]["messages"][0]["content"] == {"nested": ["a", "b"]}
    assert "logical_model" not in seen[0]
    assert "json_schema" not in seen[0]
    assert seen[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_invalid_json_is_stable_protocol_error() -> None:
    response = _FakeResponse(["data: {invalid-json}"])
    provider = DeepSeekStreamingProvider(
        _FakeHttp(response), "deepseek-chat", api_key="synthetic"
    )

    chunks = [chunk async for chunk in provider.stream(_request())]

    assert chunks[-1].error is not None
    assert chunks[-1].error.code == "PROVIDER_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_connection_error_retries_once_then_maps_to_stable_error() -> None:
    class _BrokenHttp:
        def __init__(self) -> None:
            self.calls = 0

        def stream(self, *_: Any, **__: Any) -> Any:
            self.calls += 1
            raise httpx.ConnectError("synthetic")

    http = _BrokenHttp()
    provider = DeepSeekStreamingProvider(
        http, "deepseek-chat", api_key="synthetic", max_retries=1
    )

    chunks = [chunk async for chunk in provider.stream(_request())]

    assert http.calls == 2
    assert chunks[-1].error is not None
    assert chunks[-1].error.code == "PROVIDER_CONNECTION"


@pytest.mark.asyncio
async def test_transport_error_after_first_delta_is_not_retried() -> None:
    class _BrokenResponse(_FakeResponse):
        async def aiter_lines(self):
            yield _data({"choices": [{"delta": {"content": "partial"}}]})
            raise httpx.RemoteProtocolError("synthetic disconnect")

    http = _FakeHttp(_BrokenResponse([]))
    provider = DeepSeekStreamingProvider(
        http, "deepseek-chat", api_key="synthetic", max_retries=2
    )

    chunks = [chunk async for chunk in provider.stream(_request())]

    assert "partial" == "".join(chunk.delta for chunk in chunks)
    assert chunks[-1].error is not None
    assert chunks[-1].error.code == "PROVIDER_CONNECTION"
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_cancellation_during_iteration_closes_response() -> None:
    class _FlippingSignal:
        def __init__(self) -> None:
            self.calls = 0

        def wait_requested(self) -> bool:
            self.calls += 1
            return self.calls > 1

    response = _FakeResponse(
        [
            _data({"choices": [{"delta": {"content": "first"}}]}),
            _data({"choices": [{"delta": {"content": "second"}}]}),
        ]
    )
    provider = DeepSeekStreamingProvider(
        _FakeHttp(response),
        "deepseek-chat",
        api_key="synthetic",
        cancellation_signal=_FlippingSignal(),
    )

    with pytest.raises(asyncio.CancelledError):
        _ = [chunk async for chunk in provider.stream(_request())]

    assert response.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 409, 422, 429, 500])
async def test_status_whitelist_maps_and_retries_only_transient(status: int) -> None:
    class _CountingHttp(_FakeHttp):
        def __init__(self) -> None:
            super().__init__(_FakeResponse([], status_code=status))

    http = _CountingHttp()
    provider = DeepSeekStreamingProvider(
        http, "deepseek-chat", api_key="synthetic", max_retries=1
    )
    chunks = [chunk async for chunk in provider.stream(_request())]

    assert chunks[-1].error is not None
    assert len(http.calls) == (2 if status in {408, 429} or status >= 500 else 1)
