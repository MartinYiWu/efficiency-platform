"""DeepSeek web_search Provider 的离线契约测试。"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
from openai import APITimeoutError

from efficiency_platform_agent.agents.operation.contracts.evidence import TimeWindow
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchRequest,
    ResearchStatus,
)
from efficiency_platform_agent.capabilities.research.deepseek_web_search import (
    DeepSeekWebSearchProvider,
)


class _DiagnosticRecorder:
    """捕获白名单诊断记录，供离线断言使用。"""

    def __init__(self) -> None:
        self.records = []

    def record(self, record) -> None:
        self.records.append(record)


class _StatusError(Exception):
    """携带稳定 HTTP 状态的合成上游异常。"""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class _Responses:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class _Client:
    def __init__(self, response=None, error=None):
        self.responses = _Responses(response, error)
        self.closed = False

    async def close(self):
        self.closed = True


def _request() -> ResearchRequest:
    return ResearchRequest(
        "research-request/1",
        "research.test",
        "task.test",
        "tenant.test",
        "AI 行业动态",
        TimeWindow(None, None),
        3,
        ("conclusion.test",),
        "research-result/1",
    )


class ResearchProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_timeout_covers_server_side_search_chain(self):
        provider = DeepSeekWebSearchProvider(_Client(), model="deepseek-search")

        self.assertEqual(provider.timeout_ms, 240_000)

    async def test_invocation_failures_are_classified_without_sensitive_values(self):
        synthetic_prompt = "不要记录这个合成 Prompt"
        synthetic_secret = "synthetic-secret"
        cases = (
            (_StatusError(401, synthetic_secret), "PROVIDER_AUTHENTICATION", 401, False),
            (_StatusError(403, synthetic_secret), "PROVIDER_AUTHENTICATION", 403, False),
            (_StatusError(404, synthetic_secret), "PROVIDER_NOT_FOUND", 404, False),
            (_StatusError(408, synthetic_secret), "PROVIDER_TIMEOUT", 408, True),
            (_StatusError(429, synthetic_secret), "PROVIDER_RATE_LIMITED", 429, True),
            (_StatusError(503, synthetic_secret), "PROVIDER_UPSTREAM", 503, True),
            (TimeoutError(synthetic_secret), "PROVIDER_TIMEOUT", None, True),
            (
                APITimeoutError(
                    request=httpx.Request("POST", "https://synthetic.invalid")
                ),
                "PROVIDER_TIMEOUT",
                None,
                True,
            ),
            (RuntimeError(synthetic_secret), "PROVIDER_UNAVAILABLE", None, True),
        )
        request = replace(_request(), goal=synthetic_prompt)
        for error, error_code, http_status, retryable in cases:
            with self.subTest(error_code=error_code):
                recorder = _DiagnosticRecorder()
                client = _Client(error=error)
                result = await DeepSeekWebSearchProvider(
                    client,
                    model="deepseek-search",
                    recorder=recorder,
                ).research(request)

                self.assertEqual(result.error_code, "RESEARCH_UNAVAILABLE")
                self.assertEqual(len(client.responses.calls), 1)
                failure = recorder.records[-1]
                self.assertEqual(failure.event_name, "research_invocation_failed")
                self.assertEqual(failure.error_code, error_code)
                self.assertEqual(failure.error_type, type(error).__name__)
                self.assertEqual(failure.http_status, http_status)
                self.assertEqual(failure.retryable, retryable)
                self.assertIsNotNone(failure.provider_call_id)
                recorded = repr(recorder.records)
                self.assertNotIn(synthetic_prompt, recorded)
                self.assertNotIn(synthetic_secret, recorded)

    async def test_unsupported_responses_records_stable_failure_without_call_id(self):
        recorder = _DiagnosticRecorder()
        client = _Client()
        client.responses = None

        result = await DeepSeekWebSearchProvider(
            client,
            model="deepseek-search",
            recorder=recorder,
        ).research(_request())

        self.assertEqual(result.error_code, "RESEARCH_UNAVAILABLE")
        failure = recorder.records[-1]
        self.assertEqual(failure.error_code, "RESEARCH_RESPONSES_UNSUPPORTED")
        self.assertEqual(failure.retryable, False)
        self.assertIsNone(failure.provider_call_id)

    async def test_success_and_evidence_failure_record_only_counts(self):
        recorder = _DiagnosticRecorder()
        response = SimpleNamespace(
            sources=(
                SimpleNamespace(
                    url="https://example.com/secret-url",
                    title="敏感标题",
                    publisher="敏感发布者",
                    retrieved_at_epoch_ms=1,
                ),
            )
        )
        result = await DeepSeekWebSearchProvider(
            _Client(response), model="deepseek-search", recorder=recorder
        ).research(_request())

        self.assertEqual(result.status, ResearchStatus.SUCCEEDED)
        completed = recorder.records[-1]
        self.assertEqual(completed.event_name, "research_invocation_succeeded")
        self.assertEqual(completed.evidence_valid_count, 1)
        self.assertEqual(completed.evidence_rejected_count, 0)
        self.assertNotIn("secret-url", repr(recorder.records))
        self.assertNotIn("敏感标题", repr(recorder.records))
        self.assertNotIn("敏感发布者", repr(recorder.records))

    async def test_server_search_maps_sources_without_opening_urls(self):
        response = SimpleNamespace(
            sources=(
                SimpleNamespace(
                    url="https://example.com/a/",
                    title="标题",
                    publisher="来源",
                    retrieved_at_epoch_ms=1,
                ),
            )
        )
        client = _Client(response)
        result = await DeepSeekWebSearchProvider(
            client, model="deepseek-search"
        ).research(_request())
        self.assertEqual(result.status, ResearchStatus.SUCCEEDED)
        self.assertEqual(result.observations[0].source_url, "https://example.com/a")
        self.assertEqual(
            client.responses.calls[0]["tools"],
            [{"type": "web_search_2025_08_26"}],
        )
        self.assertEqual(
            client.responses.calls[0]["tool_choice"],
            {"type": "web_search_2025_08_26"},
        )
        self.assertEqual(client.responses.calls[0]["model"], "deepseek-search")
        self.assertIn("完整 URL", client.responses.calls[0]["input"])

    async def test_search_prompt_contains_current_date_and_news_source_constraints(self):
        response = SimpleNamespace(
            sources=(
                SimpleNamespace(
                    url="https://example.com/news",
                    title="今日新闻",
                    publisher="公开媒体",
                    retrieved_at_epoch_ms=1,
                ),
            )
        )
        client = _Client(response)
        await DeepSeekWebSearchProvider(client, model="deepseek-search").research(
            _request()
        )
        prompt = client.responses.calls[0]["input"]
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        self.assertIn(f"今天日期：{today}", prompt)
        self.assertIn("优先选择官方公告、主流新闻媒体或厂商原始发布", prompt)

    async def test_response_text_sources_are_extracted_when_sdk_sources_are_missing(self):
        response = SimpleNamespace(
            sources=None,
            output_text=(
                "## 新闻标题：模型发布\n"
                "- 财联社：*模型发布并完成升级*\n"
                "  https://example.com/news/1\n"
            ),
        )
        result = await DeepSeekWebSearchProvider(
            _Client(response), model="deepseek-search"
        ).research(_request())

        self.assertEqual(result.status, ResearchStatus.SUCCEEDED)
        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.observations[0].source_url, "https://example.com/news/1")
        self.assertEqual(result.observations[0].publisher, "财联社")
        self.assertIn("模型发布", result.observations[0].title)

    async def test_web_search_actions_recover_open_page_urls_as_sources(self):
        """DeepSeek Responses API 的 open_page 动作也必须形成可引用来源。"""
        response = SimpleNamespace(
            sources=None,
            output=(
                SimpleNamespace(
                    type="web_search_call",
                    action=SimpleNamespace(
                        type="open_page", url="https://example.com/ai-news"
                    ),
                ),
            ),
        )

        result = await DeepSeekWebSearchProvider(
            _Client(response), model="deepseek-search"
        ).research(_request())

        self.assertEqual(result.status, ResearchStatus.SUCCEEDED)
        self.assertEqual(result.observations[0].source_url, "https://example.com/ai-news")
        self.assertEqual(result.observations[0].publisher, "example.com")

    async def test_malformed_response_is_closed_with_response_invalid_diagnostic(self):
        recorder = _DiagnosticRecorder()
        response = SimpleNamespace(
            usage=SimpleNamespace(input_tokens="invalid", output_tokens=1),
            sources=(),
        )
        result = await DeepSeekWebSearchProvider(
            _Client(response), model="deepseek-search", recorder=recorder
        ).research(_request())

        self.assertEqual(result.error_code, "RESEARCH_UNAVAILABLE")
        self.assertEqual(recorder.records[-1].event_name, "research_invocation_failed")
        self.assertEqual(recorder.records[-1].error_code, "RESPONSE_INVALID")

    async def test_duplicate_or_invalid_sources_fail_closed(self):
        response = SimpleNamespace(
            sources=(
                {
                    "url": "https://example.com/a",
                    "title": "A",
                    "publisher": "P",
                    "retrieved_at_epoch_ms": 1,
                },
                {
                    "url": "https://example.com/a/",
                    "title": "A2",
                    "publisher": "P",
                    "retrieved_at_epoch_ms": 1,
                },
                {
                    "url": "http://bad.example",
                    "title": "B",
                    "publisher": "P",
                    "retrieved_at_epoch_ms": 1,
                },
            )
        )
        result = await DeepSeekWebSearchProvider(
            _Client(response), model="deepseek-search"
        ).research(_request())
        self.assertEqual(len(result.observations), 1)
        insufficient_recorder = _DiagnosticRecorder()
        invalid = await DeepSeekWebSearchProvider(
            _Client(SimpleNamespace(sources=())),
            model="deepseek-search",
            recorder=insufficient_recorder,
        ).research(_request())
        self.assertEqual(invalid.error_code, "RESEARCH_INSUFFICIENT")
        insufficient_record = insufficient_recorder.records[-1]
        self.assertEqual(insufficient_record.event_name, "research_evidence_insufficient")
        self.assertEqual(insufficient_record.evidence_valid_count, 0)
        self.assertEqual(insufficient_record.evidence_rejected_count, 0)
        malformed_recorder = _DiagnosticRecorder()
        malformed = await DeepSeekWebSearchProvider(
            _Client(SimpleNamespace(sources=({"url": "http://bad.example"},))),
            model="deepseek-search",
            recorder=malformed_recorder,
        ).research(_request())
        self.assertEqual(malformed.error_code, "EVIDENCE_INVALID")
        malformed_record = malformed_recorder.records[-1]
        self.assertEqual(malformed_record.event_name, "research_evidence_insufficient")
        self.assertEqual(malformed_record.evidence_valid_count, 0)
        self.assertEqual(malformed_record.evidence_rejected_count, 1)
        self.assertNotIn("bad.example", repr(malformed_recorder.records))

    async def test_timeout_and_cancellation(self):
        failed = await DeepSeekWebSearchProvider(
            _Client(error=TimeoutError()), model="deepseek-search"
        ).research(_request())
        self.assertEqual(failed.error_code, "RESEARCH_UNAVAILABLE")
        client = _Client()
        client.responses = _Responses(error=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await DeepSeekWebSearchProvider(client, model="deepseek-search").research(
                _request()
            )
        self.assertFalse(client.closed)


__all__ = ["ResearchProviderTests"]
