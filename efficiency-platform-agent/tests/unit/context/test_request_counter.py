"""完整模型请求计数的离线行为测试，不读取网络或密钥。"""

import json
from dataclasses import replace

import pytest

from efficiency_platform_agent.core.context_control import ModelCapacity
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderToolCall,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
    ContextCapacityError,
)


def capacity():
    return ModelCapacity(
        "deepseek",
        "synthetic-model",
        "fake/1",
        32768,
        28000,
        4096,
        "conservative-utf8/1",
        "openai-chat/1",
        "OUTPUT_INCLUDES_REASONING",
        True,
        "fake-only-capacity-evidence",
    )


def request(text="合成问题", options=None):
    return ProviderRequest(
        "context-counter-test/1",
        (ProviderMessage("system", "合成系统规则"), ProviderMessage("user", text)),
        JsonObject() if options is None else options,
        1000,
    )


@pytest.mark.parametrize(
    "text",
    [
        "中文约束",
        "def f(x): return {'a': x}",
        "https://example.test/a?x=1",
        "🙂🚀",
        '{"a":[1,2,3]}',
    ],
)
def test_complete_serialization_has_verified_conservative_upper_bound(text):
    measured = ConservativeRequestTokenCounter().measure(request(text), capacity())
    assert measured.verified is True
    assert measured.method == "conservative-utf8/1"
    assert measured.total_upper_bound >= len(text.encode("utf-8")) + 4096
    assert (
        sum(value for _, value in measured.by_component) == measured.total_upper_bound
    )


def test_system_developer_tools_and_schema_all_contribute_to_count():
    counter = ConservativeRequestTokenCounter()
    original = request()
    baseline = counter.measure(original, capacity()).total_upper_bound
    schema = JsonObject(
        (
            ("type", "object"),
            (
                "properties",
                JsonObject((("result", JsonObject((("type", "string"),))),)),
            ),
        )
    )
    with_schema = replace(
        original,
        messages=original.messages
        + (
            ProviderMessage(
                "developer",
                json.dumps(
                    {"type": "object", "properties": {"result": {"type": "string"}}}
                ),
            ),
        ),
    )
    with_tools = replace(
        original,
        options=JsonObject(
            (
                (
                    "tools",
                    (
                        JsonObject(
                            (
                                ("type", "function"),
                                (
                                    "function",
                                    JsonObject(
                                        (("name", "lookup"), ("parameters", schema))
                                    ),
                                ),
                            )
                        ),
                    ),
                ),
            )
        ),
    )
    assert counter.measure(with_schema, capacity()).total_upper_bound > baseline
    assert counter.measure(with_tools, capacity()).total_upper_bound > baseline


def test_tool_calls_and_results_are_counted_with_their_protocol_fields():
    call = ProviderToolCall(
        "tool-id", "lookup", JsonObject((("query", "Java合成事实"),))
    )
    messages = request().messages + (
        ProviderMessage("assistant", None, tool_calls=(call,)),
        ProviderMessage("tool", "合成工具返回" * 100, tool_call_id="tool-id"),
    )
    counter = ConservativeRequestTokenCounter()
    assert (
        counter.measure(
            replace(request(), messages=messages), capacity()
        ).total_upper_bound
        > counter.measure(request(), capacity()).total_upper_bound
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified", False),
        ("serialization_ref", "unknown-mode/1"),
        ("tokenizer_ref", "unknown-tokenizer/1"),
        ("provider", "unknown-provider"),
    ],
)
def test_unverified_or_unsupported_capacity_fails_closed_without_input_echo(
    field, value
):
    sensitive = "合成正文不得回显"
    with pytest.raises(ContextCapacityError) as error:
        ConservativeRequestTokenCounter().measure(
            request(sensitive), replace(capacity(), **{field: value})
        )
    assert error.value.code == "CONTEXT_CAPACITY_UNVERIFIED"
    assert sensitive not in str(error.value)


def test_unknown_multimodal_input_is_rejected_before_counting_as_plain_text():
    image = JsonObject(
        (
            ("type", "image_url"),
            ("image_url", JsonObject((("url", "https://example.test/private-image"),))),
        )
    )
    with pytest.raises(ContextCapacityError):
        ConservativeRequestTokenCounter().measure(request((image,)), capacity())


def test_cache_hints_do_not_remove_input_from_window_and_no_model_name_inference():
    counter = ConservativeRequestTokenCounter()
    original = request("同一合成输入" * 100)
    cached = replace(
        original, options=JsonObject((("prompt_cache_hit_tokens", 1000000),))
    )
    assert (
        counter.measure(cached, capacity()).total_upper_bound
        >= counter.measure(original, capacity()).total_upper_bound
    )
    altered_name = replace(capacity(), model="name-does-not-prove-1million-window")
    assert (
        counter.measure(original, altered_name).total_upper_bound
        >= len("同一合成输入".encode()) * 100
    )


def test_counter_implements_core_port_and_registry_has_no_unknown_model_fallback():
    from efficiency_platform_agent.context.model_capacity import (
        ModelCapacityRegistry,
        ModelCapacityUnavailable,
    )
    from efficiency_platform_agent.core.context_control import TokenCounter

    assert isinstance(ConservativeRequestTokenCounter(), TokenCounter)
    registry = ModelCapacityRegistry()
    with pytest.raises(ModelCapacityUnavailable):
        registry.resolve("deepseek", "looks-like-1million-window", "latest")
    registry.register(capacity())
    assert registry.resolve("deepseek", "synthetic-model", "fake/1") == capacity()
    with pytest.raises(ModelCapacityUnavailable):
        registry.register(capacity())
    with pytest.raises(ModelCapacityUnavailable):
        registry.register(replace(capacity(), verified=False, model="not-verified"))


def test_short_memory_fragment_does_not_repeat_request_global_overhead():
    counter = ConservativeRequestTokenCounter()
    messages = (ProviderMessage("user", "默认使用中文回答"),)
    fragment = counter.measure_messages(messages, capacity())
    assert fragment.verified
    assert fragment.method == "conservative-utf8-fragment/1"
    assert len("默认使用中文回答".encode()) <= fragment.total_upper_bound < 512
    assert (
        sum(tokens for _, tokens in fragment.by_component) == fragment.total_upper_bound
    )
    whole = counter.measure(replace(request(), messages=messages), capacity())
    assert whole.total_upper_bound >= fragment.total_upper_bound + 4096


def test_fragment_port_is_explicit_and_rejects_unverified_multimodal():
    from efficiency_platform_agent.core.context_control import ContextFragmentCounter

    counter = ConservativeRequestTokenCounter()
    assert isinstance(counter, ContextFragmentCounter)
    image = JsonObject((("type", "image_url"),))
    with pytest.raises(ContextCapacityError):
        counter.measure_messages((ProviderMessage("user", (image,)),), capacity())
