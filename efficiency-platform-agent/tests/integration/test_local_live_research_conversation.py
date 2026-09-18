"""正式 ASGI、Supervisor 与研究图，仅在 HTTP/模型边界提供离线内容。"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.harness import local_real_factory, research_local_tools
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from tests.conversation.test_intent_v2_flow import _new_task_patch
from tests.integration.test_operation_deliverable_v2 import ContentProviderV2
from tests.orchestration.research_v2.test_live_stage_runner import (
    body_response,
    rss_response,
    semantic_model,
)
from tests.unit.harness.test_local_live_research_factory import module, settings
from tests.unit.harness.test_local_real_factory import synthetic_settings
from tests.unit.harness.test_research_local_tools import Connector, Resolver, source


class BoundaryModel(FakeModelProvider):
    """只替换外部模型响应，不替换意图/研究/交付代码。"""

    def __init__(self):
        super().__init__("boundary", [])
        self.calls = []
        self.content = ContentProviderV2()

    async def complete(self, request):
        self.calls.append(request)
        if request.contract_version == "intent-patch/2":
            data = json.loads(request.messages[-1].content)
            text = data["sources"][0]["content"]
            if isinstance(text, dict):
                text = text.get("text", text.get("input_text"))
            patch = _new_task_patch(data["current_message_id"], text)
            if "解释" in text:
                from efficiency_platform_agent.contracts.intent_v2 import IntentPatchV2

                patch = IntentPatchV2(base_revision=0, dialog_act="chat")
            from efficiency_platform_agent.contracts.temporal_v2 import (
                RollingDurationExpression,
            )

            operations = tuple(
                x.model_copy(
                    update={
                        "value": x.value.model_copy(
                            update={
                                "value": RollingDurationExpression(
                                    text="最近7天", amount=7, unit="day"
                                )
                            }
                        )
                    }
                )
                if x.field_name == "temporal"
                else x
                for x in patch.field_operations
            )
            if "缺少时间" in text:
                operations = tuple(x for x in operations if x.field_name != "temporal")
            if text == "补充最近7天":
                previous = data.get("previous_intent_state")
                if previous:
                    patch = patch.model_copy(
                        update={
                            "dialog_act": "follow_up",
                            "base_revision": previous["revision"],
                            "goal_updates": (),
                        }
                    )
                    operations = tuple(
                        x for x in operations if x.field_name == "temporal"
                    )
            value = patch.model_copy(
                update={"field_operations": operations}
            ).model_dump(mode="json")
        elif request.contract_version == "2":
            raw = json.loads(request.messages[-1].content)
            stage = (
                "relevance"
                if "document" in raw
                else "claims"
                if "evidence_context" in raw
                else "replan"
                if "allowed_actions" in raw
                else "cluster"
            )
            value = semantic_model(
                SimpleNamespace(demand_version=f"research.v2.{stage}"), request
            )
        else:
            if request.contract_version == "general-conversation/1":
                return ProviderResult(
                    request.contract_version,
                    ProviderMessage("assistant", "普通解释正文"),
                    ProviderUsage(2, 3, 0, 0, 1),
                )
            return await self.content.complete(request)
        return ProviderResult(
            request.contract_version,
            ProviderMessage("assistant", json.dumps(value)),
            ProviderUsage(10, 20, 0, 0, 1),
        )


async def build_case(monkeypatch, *, admitted=True):
    factory = module()
    model = BoundaryModel()
    monkeypatch.setattr(
        local_real_factory, "DeepSeekStreamingProvider", lambda *a, **k: model
    )
    connector = Connector([rss_response(), body_response(), rss_response()])
    monkeypatch.setattr(
        research_local_tools, "AsyncioPinnedHttpConnector", lambda: connector
    )
    monkeypatch.setattr(research_local_tools, "AsyncioTargetResolver", Resolver)
    if admitted:
        now = datetime.now(UTC)
        descriptor = source(body=True)
        descriptor = descriptor.model_copy(
            update={
                "history_mode": "latest_only",
                "freshness_sla": timedelta(days=30),
                "max_lookback": timedelta(days=30),
                "admission": descriptor.admission.model_copy(
                    update={
                        "history_verified": True,
                        "expires_at": now + timedelta(days=1),
                    }
                ),
            }
        )
        monkeypatch.setattr(
            factory, "load_local_source_descriptors", lambda path: (descriptor,)
        )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("真实网络被禁止"))
    )
    bundle = local_real_factory.build_local_agent_application(
        synthetic_settings(), http_client=client, research_v2_settings=settings()
    )
    return bundle, connector, model, client


async def post(
    bundle,
    text,
    request,
    *,
    tenant="tenant-1",
    user="user-1",
    conversation="conversation",
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=bundle.app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/v1/conversations/{conversation}/messages",
            headers={"X-Tenant-ID": tenant},
            json={"message": text, "request_id": request, "user_id": user},
        )
    assert response.status_code == 201, response.text
    await bundle.runtime.wait_for_background_tasks()
    return await bundle.runtime.get_run(response.json()["run_id"], tenant)


async def test_formal_two_rounds_research_then_only_selected_reference(monkeypatch):
    bundle, connector, model, client = await build_case(monkeypatch)
    try:
        first = await post(bundle, "研究最近7天AI动态，给出排名摘要", "first")
        bound = list(
            bundle.app.state.local_live_research_components.research_service._runs.values()
        )
        assert first.status.value == "succeeded", (
            first.failure,
            [
                (x.key, (x.task.exception() or x.task.result()) if x.task else None)
                for x in bound
            ],
            connector.calls,
        )
        pack = first.output["deliverable_set"]
        assert pack["contract_version"] == "deliverable-set/2"
        item = pack["deliverables"][0]["content"]["items"][0]
        before = len(connector.calls)
        second = await post(bundle, "把上一轮第1条改写成小红书文案", "second")
        assert second.status.value == "succeeded", second
        assert len(connector.calls) == before
        raw = model.content.calls[-1]
        assert raw["input_deliverables"][0]["item"]["item_id"] == item["item_id"]
        assert len(raw["input_deliverables"]) == 1
        assert {x["citation_id"] for x in raw["citations"]} == set(item["source_refs"])
        third = await post(bundle, "把上一轮第1条改写成公众号", "third")
        assert third.status.value == "failed"
        assert third.failure.code == "CONVERSATION_REFERENCE_UNAVAILABLE"
    finally:
        await bundle.close()
        await client.aclose()


@pytest.mark.parametrize(
    "message,status",
    [("解释品牌定位", "succeeded"), ("研究AI动态，缺少时间", "waiting_input")],
)
async def test_chat_and_clarification_keep_existing_conversation_paths(
    monkeypatch, message, status
):
    bundle, connector, _model, client = await build_case(monkeypatch)
    try:
        run = await post(bundle, message, "non-research")
        assert run.status.value == status, run.failure
        assert not connector.calls
        assert not await bundle.app.state.local_live_research_components.state_store.retained_keys()
    finally:
        await bundle.close()
        await client.aclose()


async def test_unadmitted_source_cannot_produce_fabricated_research(monkeypatch):
    bundle, connector, _model, client = await build_case(monkeypatch, admitted=False)
    try:
        run = await post(bundle, "研究最近7天AI动态", "denied")
        assert run.status.value == "failed"
        assert run.output is None
        assert not connector.calls
    finally:
        await bundle.close()
        await client.aclose()


@pytest.mark.parametrize(
    "invalid", ["expired", "user", "tenant", "conversation", "rank"]
)
async def test_local_reference_requires_live_same_identity_facts(monkeypatch, invalid):
    bundle, connector, model, client = await build_case(monkeypatch)
    try:
        first = await post(bundle, "研究最近7天AI动态", "source")
        assert first.status.value == "succeeded", first.failure
        components = bundle.app.state.local_live_research_components
        if invalid == "expired":
            await components.state_store.expire(datetime.now(UTC) + timedelta(hours=1))
        before = (len(connector.calls), len(model.calls))
        run = await post(
            bundle,
            f"把上一轮第{9 if invalid == 'rank' else 1}条改写成小红书",
            "invalid",
            user="other" if invalid == "user" else "user-1",
            tenant="other" if invalid == "tenant" else "tenant-1",
            conversation="other" if invalid == "conversation" else "conversation",
        )
        assert run.status.value == "failed", run.output
        assert run.failure.code == "CONVERSATION_REFERENCE_UNAVAILABLE"
        assert (len(connector.calls), len(model.calls)) == before
    finally:
        await bundle.close()
        await client.aclose()


async def test_clarification_continues_in_v2_with_new_run_bound_budget(monkeypatch):
    bundle, _connector, _model, client = await build_case(monkeypatch)
    try:
        first = await post(bundle, "研究AI动态，缺少时间", "clarify")
        assert first.status.value == "waiting_input"
        second = await post(bundle, "补充最近7天", "answer")
        assert second.status.value == "succeeded", second.failure
        assert second.run_id != first.run_id
        assert (
            second.output["deliverable_set"]["contract_version"] == "deliverable-set/2"
        )
        facts = bundle.app.state.local_live_research_components.state_store
        keys = await facts.retained_keys()
        assert len(keys) == 1
        assert next(iter(keys)).run_id == second.run_id
        assert next(iter(keys)).revision == 2
    finally:
        await bundle.close()
        await client.aclose()


async def test_new_research_runs_share_only_application_network_limits(monkeypatch):
    factory = module()
    stages, tool_calls = [], []
    real_stages, real_tools = (
        factory.LocalLiveResearchStageRunner,
        factory.build_local_research_tools,
    )

    def capture_stage(**kwargs):
        stages.append(kwargs)
        return real_stages(**kwargs)

    def capture_tools(**kwargs):
        tool_calls.append(kwargs)
        return real_tools(**kwargs)

    monkeypatch.setattr(factory, "LocalLiveResearchStageRunner", capture_stage)
    monkeypatch.setattr(factory, "build_local_research_tools", capture_tools)
    bundle, connector, _model, client = await build_case(monkeypatch)
    connector.responses = [
        rss_response(),
        body_response(),
        rss_response(),
        body_response(),
    ]
    try:
        first = await post(bundle, "研究最近7天AI动态", "one")
        from dataclasses import replace

        coordinator = bundle.conversation.intent_v2_coordinator
        await coordinator.update_rollout_settings(
            replace(
                coordinator.settings,
                research_policy_version="local-live-research/2",
                research_replan_enabled=False,
            )
        )
        second = await post(bundle, "研究最近7天AI动态", "two")
        assert first.status.value == second.status.value == "succeeded", (
            first.failure,
            second.failure,
        )
        assert len(stages) == len(tool_calls) == 2
        components = bundle.app.state.local_live_research_components
        assert stages[0]["key"] != stages[1]["key"]
        assert stages[0]["binding"] is not stages[1]["binding"]
        assert stages[0]["policy"].policy_version == "local-live-research/1"
        assert stages[1]["policy"].policy_version == "local-live-research/2"
        assert stages[1]["policy"].max_collection_rounds == 1
        for stage, tool in zip(stages, tool_calls, strict=True):
            assert stage["store"] is components.state_store
            assert tool["network_limits"] is components.network_limits
            assert (
                tool["binding"] is tool["body_http_quota"].binding is stage["binding"]
            )
            assert stage["output_stages"].binding is stage["binding"]
            assert stage["output_stages"].key == stage["key"]
            assert stage["output_stages"].store is stage["store"]
            assert (
                stage["content_acquirer"].runtime
                is stage["acquisition_executor"].runtime
            )
            assert (
                stage["output_stages"].cancellation_signal
                is tool["cancellation_signal"]
            )
            assert (
                stage["output_stages"].deadline_monotonic
                == stage["acquisition_context"].deadline_monotonic
            )
            assert tool["body_http_quota"].dispatched == 1
            ledger = await stage["binding"].port.snapshot(stage["binding"].scope)
            assert ledger.limits.max_calls == 60
            assert ledger.limits.output_time_reserve_ms == 35_000
            assert ledger.limits.output_token_reserve == 8_000
            assert 0 < ledger.used.calls < 60
        assert len(connector.calls) == 4
    finally:
        await bundle.close()
        await client.aclose()


async def test_whitelist_rejection_precedes_all_model_and_http_calls(monkeypatch):
    bundle, connector, model, client = await build_case(monkeypatch)
    try:
        run = await post(bundle, "研究最近7天AI动态", "foreign", tenant="foreign")
        assert run.status.value == "failed"
        assert run.failure.code == "RESEARCH_LOCAL_LIVE_TENANT_NOT_ALLOWED"
        assert not connector.calls
        assert not model.calls
    finally:
        await bundle.close()
        await client.aclose()


async def test_formal_two_item_digest_rewrite_excludes_unselected_document(monkeypatch):
    from efficiency_platform_agent.providers.research.transport import PinnedResponse

    bundle, connector, model, client = await build_case(monkeypatch)
    feed = rss_response()
    xml = b"".join(feed.body_chunks)
    second = (
        xml.split(b"<item>")[1]
        .split(b"</item>")[0]
        .replace(b"/article", b"/second")
        .replace(b"<guid>1", b"<guid>2")
    )
    feed = PinnedResponse(
        200,
        feed.headers,
        (xml.replace(b"</channel>", b"<item>" + second + b"</item></channel>"),),
    )
    connector.responses = [
        feed,
        body_response(),
        PinnedResponse(
            200,
            {"content-type": "text/plain"},
            (b"Acme announced an AI release. Beta story.",),
        ),
    ]
    try:
        first = await post(bundle, "研究最近7天AI动态", "multi-source")
        bounds = list(
            bundle.app.state.local_live_research_components.research_service._runs.values()
        )
        assert first.status.value == "succeeded", (
            first.failure,
            [
                (x.task.exception() or x.task.result()) if x.task else None
                for x in bounds
            ],
        )
        digest = first.output["deliverable_set"]["deliverables"][0]
        assert len(digest["content"]["items"]) == 2
        selected, excluded = digest["content"]["items"]
        before = len(connector.calls)
        second_run = await post(bundle, "把上一轮第1条改写成小红书", "rewrite")
        assert second_run.status.value == "succeeded", second_run.failure
        payload = model.content.calls[-1]
        assert (
            payload["input_deliverables"][0]["item"]["item_id"] == selected["item_id"]
        )
        assert {c["citation_id"] for c in payload["citations"]} == set(
            selected["source_refs"]
        )
        assert not set(excluded["source_refs"]) & {
            c["citation_id"] for c in payload["citations"]
        }
        assert excluded["item_id"] not in json.dumps(payload)
        assert len(connector.calls) == before
    finally:
        await bundle.close()
        await client.aclose()


@pytest.mark.parametrize("change", ["item", "citation", "why", "source_run"])
async def test_reference_validator_rejects_external_or_tampered_fields(
    monkeypatch, change
):
    from efficiency_platform_agent.harness.errors import HarnessError
    from efficiency_platform_agent.harness.local_live_references import (
        LocalLiveRankedReferenceValidator,
    )
    from efficiency_platform_agent.harness.referenced_inputs import (
        select_ranked_reference,
    )

    bundle, connector, model, client = await build_case(monkeypatch)
    try:
        first = await post(bundle, "研究最近7天AI动态", "source")
        value = select_ranked_reference(
            first,
            1,
            tenant_id="tenant-1",
            user_id="user-1",
            conversation_id="conversation",
        )
        if change == "source_run":
            value = value.model_copy(update={"source_run_id": "nonexistent"})
        elif change == "citation":
            value = value.model_copy(
                update={
                    "citations": (
                        value.citations[0].model_copy(
                            update={"url": "https://foreign.example/"}
                        ),
                    )
                }
            )
        else:
            field = "summary" if change == "item" else "why_it_matters"
            value = value.model_copy(
                update={
                    "item": value.item.model_copy(update={field: "模型生成的外部事实"})
                }
            )
        before = len(connector.calls), len(model.calls)
        with pytest.raises(HarnessError) as error:
            await LocalLiveRankedReferenceValidator(
                bundle.app.state.local_live_research_components.state_store
            )(value)
        assert error.value.code == "CONVERSATION_REFERENCE_UNAVAILABLE"
        assert (len(connector.calls), len(model.calls)) == before
    finally:
        await bundle.close()
        await client.aclose()
