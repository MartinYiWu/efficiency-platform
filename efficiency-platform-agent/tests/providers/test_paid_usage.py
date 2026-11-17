"""用合成响应验证usage，不访问外部模型。"""

import json

import pytest

from efficiency_platform_agent.core.paid_budget import PaidUsage
from efficiency_platform_agent.providers.paid_usage import (
    PaidUsageCollector,
    input_token_upper_bound,
)


def stream(chunks, thinking=False):
    result = PaidUsageCollector("deepseek", "text/event-stream", thinking=thinking)
    for chunk in chunks:
        result.feed(chunk)
    result.end()
    return result.usage


def test_sse_split_utf8_and_usage_cache_reasoning_subsets():
    text = (
        "data: "
        + json.dumps(
            {
                "choices": [{"delta": {"content": "中文"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 30,
                    "prompt_cache_hit_tokens": 40,
                    "completion_tokens_details": {"reasoning_tokens": 20},
                },
            },
            ensure_ascii=False,
        )
        + "\r\n\r\ndata: [DONE]\n\n"
    )
    raw = text.encode()
    assert stream(
        [raw[i : i + 1] for i in range(len(raw))], thinking=True
    ) == PaidUsage(100, 30, 40, 20)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "negative",
        "bool",
        "cache_exceeds",
        "reasoning_exceeds",
        "no_reasoning",
    ],
)
def test_invalid_or_unproved_usage_is_unknown(mutation):
    usage = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "completion_tokens_details": {"reasoning_tokens": 1},
    }
    if mutation == "missing":
        usage.pop("prompt_tokens")
    if mutation == "negative":
        usage["prompt_tokens"] = -1
    if mutation == "bool":
        usage["completion_tokens"] = True
    if mutation == "cache_exceeds":
        usage["prompt_cache_hit_tokens"] = 11
    if mutation == "reasoning_exceeds":
        usage["completion_tokens_details"]["reasoning_tokens"] = 6
    if mutation == "no_reasoning":
        usage.pop("completion_tokens_details")
    raw = (
        "data: "
        + json.dumps({"choices": [{"finish_reason": "stop"}], "usage": usage})
        + "\n\ndata: [DONE]\n\n"
    ).encode()
    assert stream([raw], thinking=True) is None


def test_missing_done_truncation_and_conflicting_duplicate_usage_are_unknown():
    usage = {"prompt_tokens": 10, "completion_tokens": 5}
    first = (
        "data: "
        + json.dumps({"choices": [{"finish_reason": "stop"}], "usage": usage})
        + "\n\n"
    ).encode()
    assert stream([first]) is None
    other = (
        "data: "
        + json.dumps({"usage": usage | {"prompt_tokens": 11}})
        + "\n\ndata: [DONE]\n\n"
    ).encode()
    assert stream([first, other]) is None
    assert stream([first, first, b"data: [DONE]\n\n"]) == PaidUsage(10, 5)


@pytest.mark.parametrize(
    "provider,payload,expected",
    [
        (
            "embedding",
            {"data": [], "usage": {"prompt_tokens": 12, "total_tokens": 12}},
            PaidUsage(12, 0),
        ),
        (
            "rerank",
            {"output": {"results": []}, "usage": {"total_tokens": 23}},
            PaidUsage(23, 0),
        ),
        (
            "deepseek",
            {
                "choices": [{"finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
            PaidUsage(12, 4),
        ),
    ],
)
def test_complete_json_usage(provider, payload, expected):
    collector = PaidUsageCollector(provider, "application/json")
    body = json.dumps(payload).encode()
    collector.feed(body[:7])
    collector.feed(body[7:])
    assert collector.usage is None
    collector.end()
    assert collector.usage == expected


def test_error_json_or_incomplete_json_cannot_refund():
    for raw in [
        b'{"error":"failed","usage":{"total_tokens":1}}',
        b'{"usage":{"total_tokens":1}',
    ]:
        c = PaidUsageCollector("rerank", "application/json")
        c.feed(raw)
        c.end()
        assert c.usage is None


@pytest.mark.parametrize(
    "provider,usage",
    [
        (
            "deepseek",
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "reasoning_tokens": 4,
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
        ),
        ("embedding", {"input_tokens": 1, "prompt_tokens": 100}),
        ("rerank", {"input_tokens": 1, "prompt_tokens": False}),
        (
            "deepseek",
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "prompt_cache_hit_tokens": 1,
                "prompt_tokens_details": {"cached_tokens": True},
                "reasoning_tokens": 0,
            },
        ),
        (
            "deepseek",
            {
                "prompt_tokens": 100,
                "completion_tokens": 5,
                "prompt_cache_hit_tokens": 90,
                "prompt_cache_miss_tokens": 20,
                "reasoning_tokens": 0,
            },
        ),
    ],
)
def test_conflicting_aliases_are_unknown(provider, usage):
    payload = {
        "usage": usage,
        **(
            {"choices": [{"finish_reason": "stop"}]}
            if provider == "deepseek"
            else {"data": []}
            if provider == "embedding"
            else {"output": {"results": []}}
        ),
    }
    c = PaidUsageCollector(
        provider, "application/json", thinking=provider == "deepseek"
    )
    c.feed(json.dumps(payload).encode())
    c.end()
    assert c.usage is None


def test_input_upper_bound_covers_per_document_repeated_query():
    payload = {
        "model": "m",
        "input": {"query": "query" * 20, "documents": ["one", "two", "three"]},
    }
    raw = json.dumps(payload).encode()
    assert input_token_upper_bound("rerank", raw, payload) >= 3 * len(
        payload["input"]["query"].encode()
    ) + len(raw)
    assert (
        input_token_upper_bound(
            "deepseek", b"{}", {"messages": [{"role": "user", "content": "x"}]}
        )
        > 2
    )


def test_collector_bounds_memory_and_never_exposes_response_text():
    collector = PaidUsageCollector("deepseek", "text/event-stream")
    collector.feed(b"x" * 300000)
    collector.end()
    assert collector.usage is None
    assert len(collector.buffer) <= 262144
