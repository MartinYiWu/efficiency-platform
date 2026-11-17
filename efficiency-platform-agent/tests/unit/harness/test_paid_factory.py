"""真实组合根在没有授权时必须拒绝模型派发。"""

import httpx
import pytest
from test_local_real_factory import synthetic_settings

from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.harness import local_real_factory


def test_test_mode_cannot_construct_an_unprotected_real_client():
    with pytest.raises(ValueError, match="PAID_TEST_CLIENT_REQUIRED"):
        local_real_factory.build_local_agent_application(
            synthetic_settings(), test_mode=True
        )


async def test_real_factory_installs_guard_and_disables_sdk_retries(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        local_real_factory, "default_paid_budget_path", lambda: tmp_path / "empty.db"
    )
    dispatched = []

    def inner(*args, **kwargs):
        def sent(request):
            dispatched.append(request)
            pytest.fail("没有预算不得进入实际HTTP传输")

        return httpx.MockTransport(sent)

    monkeypatch.setattr(local_real_factory.httpx, "AsyncHTTPTransport", inner)
    app = local_real_factory.build_local_agent_application(synthetic_settings())
    try:
        provider = next(
            iter(app.conversation.interpreter.model_runtime.registry.providers.values())
        )
        result = await provider.complete(
            ProviderRequest(
                "test",
                (ProviderMessage("user", "synthetic"),),
                JsonObject((("max_tokens", 10),)),
                1000,
            )
        )
        assert result.error is not None and result.error.category == "budget"
        assert not dispatched
        assert app.customer_service_resources[0].max_retries == 0
        assert app.app.state.paid_budget_ledger.active_budget_id() is None
        model_client = provider.client
        shared_slots = model_client._transport.request_slots
        assert shared_slots is not None
        assert shared_slots._value == 1
        embedding_client = app.customer_service_resources[0]._client
        assert embedding_client._transport.request_slots is shared_slots
        rerank_client = app.customer_service_resources[-1]
        assert rerank_client._transport.request_slots is shared_slots
        from efficiency_platform_agent.core.paid_budget import PaidBudgetError

        ingest = app.app.state.customer_service_ingest_service
        with pytest.raises(PaidBudgetError):
            await ingest.embedder.embed(("synthetic test",))
        service = app.app.state.customer_service_run_service
        with pytest.raises(PaidBudgetError):
            await service.graph.retrieval.reranker.rerank(
                "synthetic", ("synthetic",), top_n=1
            )
        assert not dispatched
    finally:
        await app.close()
