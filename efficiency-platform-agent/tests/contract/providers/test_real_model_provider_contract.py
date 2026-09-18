"""DeepSeek Provider 的离线 SDK Transport Stub 契约测试。"""

from __future__ import annotations

import asyncio
import inspect
import unittest
from types import SimpleNamespace
from typing import get_type_hints

from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
)
from efficiency_platform_agent.providers.llm.deepseek import DeepSeekModelProvider


def _request(options: JsonObject | None = None) -> ProviderRequest:
    options = options or JsonObject()
    return ProviderRequest("s2/1", (ProviderMessage("user", "你好"),), options, 10_000)


class _Completions:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _Client:
    def __init__(self, response=None, error=None):
        self.chat = SimpleNamespace(completions=_Completions(response, error))
        self.closed = False

    async def close(self):
        self.closed = True


class _ResponsesClient(_Client):
    """Responses API 形状的离线 Transport Stub。"""

    def __init__(self, response):
        super().__init__(response)
        self.responses = _Completions(response)


class _HTTPError(Exception):
    """带状态码的 Transport Stub 异常。"""

    def __init__(self, status_code: int) -> None:
        super().__init__("stub")
        self.status_code = status_code


class DeepSeekModelProviderContractTests(unittest.IsolatedAsyncioTestCase):
    def test_signature_reuses_s2_provider_contract(self):
        signature = inspect.signature(DeepSeekModelProvider.complete)
        self.assertEqual(tuple(signature.parameters), ("self", "request"))
        annotations = get_type_hints(DeepSeekModelProvider.complete)
        self.assertIs(annotations["return"], ProviderResult)
        self.assertIs(annotations["request"], ProviderRequest)

    async def test_normal_response_and_json_schema_options(self):
        response = SimpleNamespace(
            choices=(SimpleNamespace(message=SimpleNamespace(content="完成")),),
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5),
        )
        client = _Client(response)
        provider = DeepSeekModelProvider(
            client,
            "deepseek-chat",
        )
        result = await provider.complete(
            _request(
                JsonObject(
                    (("response_format", JsonObject((("type", "json_object"),))),)
                )
            )
        )
        self.assertIsInstance(result, ProviderResult)
        self.assertEqual(result.message.content, "完成")
        self.assertEqual(result.usage.input_tokens, 3)
        self.assertEqual(
            client.chat.completions.calls[0]["response_format"], {"type": "json_object"}
        )

    async def test_runtime_logical_model_option_is_not_forwarded_to_sdk(self):
        response = SimpleNamespace(
            choices=(SimpleNamespace(message=SimpleNamespace(content="完成")),),
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5),
        )
        client = _Client(response)

        result = await DeepSeekModelProvider(client, "deepseek-chat").complete(
            _request(JsonObject((("logical_model", "deepseek-chat"),)))
        )

        self.assertIsNone(result.error)
        self.assertNotIn("logical_model", client.chat.completions.calls[0])

    async def test_responses_api_shape_is_supported(self):
        client = _ResponsesClient(SimpleNamespace(output_text="响应结果", usage=None))
        result = await DeepSeekModelProvider(client, "deepseek-chat").complete(
            _request()
        )
        self.assertEqual(result.message.content, "响应结果")
        self.assertIn("input", client.responses.calls[0])

    async def test_error_statuses_are_safe_and_normalized(self):
        for status, code, retryable in (
            (400, "PROVIDER_BAD_REQUEST", False),
            (401, "PROVIDER_AUTHENTICATION", False),
            (403, "PROVIDER_FORBIDDEN", False),
            (404, "PROVIDER_NOT_FOUND", False),
            (422, "PROVIDER_BAD_REQUEST", False),
            (429, "PROVIDER_RATE_LIMITED", True),
            (503, "PROVIDER_UPSTREAM", True),
        ):
            error = _HTTPError(status)
            result = await DeepSeekModelProvider(
                _Client(error=error), "deepseek-chat"
            ).complete(_request())
            self.assertEqual(result.error.code, code)
            self.assertEqual(result.error.retryable, retryable)
            self.assertNotIn(str(status), result.error.safe_message)

    async def test_timeout_malformed_and_missing_usage_fail_closed(self):
        timeout = await DeepSeekModelProvider(
            _Client(error=TimeoutError()), "deepseek-chat"
        ).complete(_request())
        self.assertEqual(timeout.error.code, "PROVIDER_TIMEOUT")
        malformed = await DeepSeekModelProvider(
            _Client(SimpleNamespace(choices=())), "deepseek-chat"
        ).complete(_request())
        self.assertEqual(malformed.error.code, "PROVIDER_RESPONSE_INVALID")
        missing_usage = await DeepSeekModelProvider(
            _Client(
                SimpleNamespace(
                    choices=(SimpleNamespace(message=SimpleNamespace(content="ok")),)
                )
            ),
            "deepseek-chat",
        ).complete(_request())
        self.assertEqual(missing_usage.usage.input_tokens, 0)

    async def test_cancellation_closes_client_and_propagates(self):
        class CancelCompletions(_Completions):
            async def create(self, **kwargs):
                raise asyncio.CancelledError

        client = _Client()
        client.chat.completions = CancelCompletions()
        with self.assertRaises(asyncio.CancelledError):
            await DeepSeekModelProvider(client, "deepseek-chat").complete(_request())
        self.assertTrue(client.closed)


__all__ = ["DeepSeekModelProviderContractTests"]
