"""生产网关共享操作和底层HTTP重试额度，不使用外部网络。"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel
from test_evidence_pack import bundle

from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.core.execution_control import RunControl, execution_scope
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.paid_http import PaidHttpTransport


def fake_ledger(tmp_path):
    from efficiency_platform_agent.core.paid_budget import (
        PaidBudgetPlan,
        PaidPriceLimit,
    )
    from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger

    result = SqlitePaidBudgetLedger(tmp_path / "fake.db")
    result.authorize(
        PaidBudgetPlan(
            "fake",
            20,
            1000,
            9999999999999,
            20,
            1000,
            10000,
            1,
            10,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
            1000000,
        ),
        (
            PaidPriceLimit(
                "deepseek",
                "fake-model",
                100000,
                1000,
                10,
                "合成价格",
                "fake-v1",
                100000,
                1,
                0,
                1,
            ),
        ),
    )
    return result


class Output(BaseModel):
    answer: str


async def test_gateway_fingerprint_shares_inflight_and_separates_input_policy_schema():
    calls = []

    class Provider:
        async def complete(self, request):
            calls.append(request)
            await asyncio.sleep(0)
            return SimpleNamespace(
                error=None, message=SimpleNamespace(content='{"answer":"结论"}')
            )

    config = bundle(large=9000)
    gateway = ReleaseStructuredModelGateway(Provider(), config)
    outputs = await asyncio.gather(
        *(gateway.complete("sufficiency", {"b": 2, "a": 1}, Output) for _ in range(6))
    )
    assert len(calls) == 1
    outputs[0].answer = "外部修改"
    assert outputs[1].answer == "结论"
    assert (
        await gateway.complete("sufficiency", {"a": 1, "b": 2}, Output)
    ).answer == "结论"
    await gateway.complete("sufficiency", {"a": 2}, Output)
    await gateway.with_model_policy(config.large_context_model_policy).complete(
        "sufficiency", {"a": 2}, Output
    )
    assert len(calls) == 3


async def test_schema_repair_and_network_retries_share_three_http_attempts(
    tmp_path, monkeypatch
):
    from test_paid_budget_failure import bundle as make_bundle

    calls = []

    def upstream(request):
        calls.append(request)
        if len(calls) % 2:
            return httpx.Response(500)
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"{}"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1}}\n\ndata: [DONE]\n\n',
        )

    ledger = fake_ledger(tmp_path)
    async with httpx.AsyncClient(
        transport=PaidHttpTransport(ledger, httpx.MockTransport(upstream), "deepseek")
    ) as client:
        provider = DeepSeekStreamingProvider(
            client, "fake-model", api_key="synthetic", max_retries=3
        )

        async def no_backoff(*args):
            pass

        monkeypatch.setattr(provider, "_backoff", no_backoff)
        config = make_bundle()
        config.model_policy = config.model_policy.model_copy(
            update={
                "max_retries": 5,
                "model_name": "fake-model",
                "read_timeout_ms": 5000,
            }
        )
        gateway = ReleaseStructuredModelGateway(provider, config)
        with execution_scope(RunControl()), pytest.raises(PaidBudgetError) as caught:
            await gateway.complete("sufficiency", {}, Output)
    assert caught.value.code == "AGENT_OPERATION_ATTEMPTS_EXHAUSTED"
    assert len(calls) == 3
    assert ledger.snapshot()["calls"] == 3


async def test_repair_includes_safe_validation_reason_and_stops_after_three_calls():
    calls = []

    class Provider:
        async def complete(self, request):
            calls.append(request)
            return SimpleNamespace(
                error=None,
                message=SimpleNamespace(content='{"UNTRUSTED_SECRET":"BODY_SECRET"}'),
            )

    config = bundle()
    config.model_policy = config.model_policy.model_copy(update={"max_retries": 5})
    gateway = ReleaseStructuredModelGateway(Provider(), config)
    with pytest.raises(RuntimeError):
        await gateway.complete("sufficiency", {}, Output)
    assert len(calls) == 3
    feedback = calls[1].messages[-1].content
    assert "answer" in feedback and "missing" in feedback
    assert "UNTRUSTED_SECRET" not in feedback and "BODY_SECRET" not in feedback


async def test_truncated_operation_can_reenter_without_resetting_http_allowance(
    tmp_path, monkeypatch
):
    book = fake_ledger(tmp_path)
    calls = []

    def upstream(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, text='data: {"choices":[{"delta":{"content":""}}]}\n\n'
            )
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"{\\"answer\\":\\"结论\\"}"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    async with httpx.AsyncClient(
        transport=PaidHttpTransport(book, httpx.MockTransport(upstream), "deepseek")
    ) as client:
        provider = DeepSeekStreamingProvider(
            client, "fake-model", api_key="synthetic", max_retries=0
        )
        config = bundle()
        config.model_policy = config.model_policy.model_copy(
            update={"model_name": "fake-model", "read_timeout_ms": 5000}
        )
        gateway = ReleaseStructuredModelGateway(provider, config)
        from efficiency_platform_agent.agents.customer_service.model_gateway import (
            StructuredModelError,
        )

        with pytest.raises(StructuredModelError) as caught:
            await gateway.complete("sufficiency", {}, Output)
        assert caught.value.code == "PROVIDER_RESPONSE_TRUNCATED"
        assert (await gateway.complete("sufficiency", {}, Output)).answer == "结论"
    assert len(calls) == 2


async def test_optional_input_budget_failure_does_not_stop_other_stage():
    config = bundle()
    calls = []

    class Provider:
        async def complete(self, request):
            calls.append(request)
            return SimpleNamespace(
                error=None, message=SimpleNamespace(content='{"answer":"结论"}')
            )

    gateway = ReleaseStructuredModelGateway(Provider(), config)
    with pytest.raises(RuntimeError, match="完整输入超过模型预算"):
        await gateway.complete("sufficiency", {"large": "证据段落。" * 5000}, Output)
    assert (
        await gateway.complete("sufficiency", {"small": "证据"}, Output)
    ).answer == "结论"
    assert len(calls) == 1
