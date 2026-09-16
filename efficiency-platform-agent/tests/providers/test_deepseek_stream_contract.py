"""流式 Provider 和模型选择的稳定契约测试。"""

import asyncio
import json

import httpx
import pytest

from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import ModelCandidate, ModelDemand, ModelTier
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from efficiency_platform_agent.routing.model_router import ModelPolicyRouter


def test_existing_policy_router_orders_lower_tier_candidates() -> None:
    selector = ModelPolicyRouter()
    demand = ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 10, 20)

    selected = selector.candidates(
        demand,
        remaining_budget=RemainingBudget(2, 0, 100, 100, 0, 1000),
        unavailable_candidate_ids=frozenset({"fake_strong"}),
    )

    assert selected[0].tier is ModelTier.BALANCED


@pytest.mark.asyncio
async def test_registered_deepseek_adapter_runs_through_model_runtime_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":1,"completion_tokens":1}}\n'
            "data: [DONE]\n"
        )
        return httpx.Response(200, text=body)

    adapter = DeepSeekStreamingProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        "deepseek-chat",
        api_key="synthetic",
    )
    registry = ModelProviderRegistry()
    registry.register("deepseek_direct", adapter)
    runtime = ModelRuntime(
        ModelPolicyRouter(
            [
                ModelCandidate(
                    "deepseek",
                    "deepseek_direct",
                    "deepseek-chat",
                    ModelTier.STRONG,
                    True,
                    True,
                    128_000,
                    True,
                    False,
                )
            ]
        ),
        registry,
    )
    request = ProviderRequest(
        "conversation/1", (ProviderMessage("user", "hi"),), JsonObject(), 1000
    )

    chunks = [
        chunk
        async for chunk in runtime.stream(
            ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 1, 10),
            request,
            remaining_budget=RemainingBudget(2, 0, 100, 100, 0, 1000),
        )
    ]
    await adapter.client.aclose()

    assert "ok" == "".join(chunk.delta for chunk in chunks)
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_runtime_suppresses_pre_delta_error_and_emits_degraded_then_delta() -> (
    None
):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"fallback"}}]}\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
            "data: [DONE]\n",
        )

    adapter = DeepSeekStreamingProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        "deepseek-chat",
        api_key="synthetic",
        max_retries=0,
        logical_model_map={
            "strong": "deepseek-strong",
            "balanced": "deepseek-balanced",
        },
    )
    registry = ModelProviderRegistry()
    registry.register("deepseek_direct", adapter)
    router = ModelPolicyRouter(
        [
            ModelCandidate(
                "strong",
                "deepseek_direct",
                "strong",
                ModelTier.STRONG,
                True,
                True,
                128000,
                True,
                False,
            ),
            ModelCandidate(
                "balanced",
                "deepseek_direct",
                "balanced",
                ModelTier.BALANCED,
                True,
                True,
                128000,
                True,
                False,
            ),
        ]
    )
    runtime = ModelRuntime(router, registry)
    request = ProviderRequest(
        "conversation/1", (ProviderMessage("user", "hi"),), JsonObject(), 1000
    )

    chunks = [
        chunk
        async for chunk in runtime.stream(
            ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 1, 10),
            request,
            remaining_budget=RemainingBudget(3, 0, 100, 100, 0, 1000),
        )
    ]
    await adapter.client.aclose()

    assert [chunk.event for chunk in chunks if chunk.event] == ["model_degraded"]
    assert "fallback" == "".join(chunk.delta for chunk in chunks)
    assert all(chunk.error is None for chunk in chunks)


@pytest.mark.asyncio
async def test_stream_absolute_deadline_prevents_fallback_without_budget_guard() -> (
    None
):
    models: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        models.append(str(json.loads(request.content)["model"]))
        if len(models) == 1:
            await asyncio.sleep(1)
            return httpx.Response(429)
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"late"}}]}\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
            "data: [DONE]\n",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekStreamingProvider(
        client,
        "unused-fixed-model",
        api_key="synthetic",
        max_retries=0,
        logical_model_map={
            "strong": "deepseek-strong",
            "balanced": "deepseek-balanced",
        },
    )
    registry = ModelProviderRegistry()
    registry.register("deepseek_direct", adapter)
    runtime = ModelRuntime(
        ModelPolicyRouter(
            [
                ModelCandidate(
                    tier.value,
                    "deepseek_direct",
                    tier.value,
                    tier,
                    True,
                    True,
                    128_000,
                    True,
                    False,
                )
                for tier in (ModelTier.STRONG, ModelTier.BALANCED)
            ]
        ),
        registry,
    )

    try:
        chunks = [
            chunk
            async for chunk in runtime.stream(
                ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 1, 10),
                ProviderRequest(
                    "conversation/1",
                    (ProviderMessage("user", "hi"),),
                    JsonObject(),
                    1_000,
                ),
                remaining_budget=RemainingBudget(3, 0, 100, 100, 0, 50),
            )
        ]
    finally:
        await client.aclose()

    assert chunks[-1].error is not None
    assert chunks[-1].error.code == "BUDGET_EXHAUSTED"
    assert models == ["deepseek-strong"]


@pytest.mark.asyncio
async def test_runtime_reports_budget_before_second_retry_when_only_one_iteration_remains() -> (
    None
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    adapter = DeepSeekStreamingProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        "deepseek-chat",
        api_key="synthetic",
        max_retries=0,
        logical_model_map={"strong": "deepseek-strong"},
    )
    registry = ModelProviderRegistry()
    registry.register("deepseek_direct", adapter)
    runtime = ModelRuntime(
        ModelPolicyRouter(
            [
                ModelCandidate(
                    "strong",
                    "deepseek_direct",
                    "strong",
                    ModelTier.STRONG,
                    True,
                    True,
                    128000,
                    True,
                    False,
                )
            ]
        ),
        registry,
    )
    chunks = [
        chunk
        async for chunk in runtime.stream(
            ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 1, 10),
            ProviderRequest(
                "conversation/1", (ProviderMessage("user", "hi"),), JsonObject(), 1000
            ),
            remaining_budget=RemainingBudget(1, 0, 100, 100, 0, 1000),
        )
    ]
    await adapter.client.aclose()

    assert chunks[-1].error is not None
    assert chunks[-1].error.code == "BUDGET_EXHAUSTED"


@pytest.mark.asyncio
async def test_degraded_candidate_uses_distinct_allowlisted_vendor_model() -> None:
    models: list[str] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        models.append(str(json.loads(request.content)["model"]))
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"ok"}}]}\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
            "data: [DONE]\n",
        )

    adapter = DeepSeekStreamingProvider(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        "unused-fixed-model",
        api_key="synthetic",
        max_retries=0,
        logical_model_map={
            "strong": "deepseek-strong",
            "balanced": "deepseek-balanced",
        },
    )
    registry = ModelProviderRegistry()
    registry.register("deepseek_direct", adapter)
    runtime = ModelRuntime(
        ModelPolicyRouter(
            [
                ModelCandidate(
                    "strong",
                    "deepseek_direct",
                    "strong",
                    ModelTier.STRONG,
                    True,
                    True,
                    128000,
                    True,
                    False,
                ),
                ModelCandidate(
                    "balanced",
                    "deepseek_direct",
                    "balanced",
                    ModelTier.BALANCED,
                    True,
                    True,
                    128000,
                    True,
                    False,
                ),
            ]
        ),
        registry,
    )
    request = ProviderRequest(
        "conversation/1",
        (ProviderMessage("user", "hi"),),
        JsonObject(
            (
                ("logical_model", "evil-model"),
                ("model", "evil-model"),
                ("messages", ("evil",)),
                ("stream", False),
                ("base_url", "https://evil.invalid"),
            )
        ),
        1000,
    )

    chunks = [
        chunk
        async for chunk in runtime.stream(
            ModelDemand("s2.model/1", ModelTier.STRONG, False, False, 1, 10),
            request,
            remaining_budget=RemainingBudget(3, 0, 100, 100, 0, 1000),
        )
    ]
    await adapter.client.aclose()

    assert models == ["deepseek-strong", "deepseek-balanced"]
    assert "ok" == "".join(chunk.delta for chunk in chunks)
