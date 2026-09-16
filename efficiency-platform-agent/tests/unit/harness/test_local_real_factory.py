"""本地真实组合根的离线装配测试。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchResult,
    ResearchStatus,
)
from efficiency_platform_agent.configuration.integration import S7IntegrationSettings
from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.core.diagnostics import NoopDiagnosticRecorder
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.harness import local_real_factory
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome", ["success", "failure", "degraded", "degraded_failure"]
)
async def test_direct_body_records_actual_attempts_in_original_run_budget(
    outcome,
) -> None:
    from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
    from efficiency_platform_agent.core.budget import BudgetCharge
    from efficiency_platform_agent.core.enums import RunStatus
    from efficiency_platform_agent.core.run import ProviderError
    from tests.api.test_conversation_routes import intent

    parsed = intent().model_copy(update={"task_type": "general_chat"})
    script = [
        ProviderResult(
            "intent/1",
            ProviderMessage("assistant", parsed.model_dump_json()),
            ProviderUsage(3, 2, 0, 0, 1),
        )
    ]
    if outcome.startswith("degraded"):
        script.append(
            ProviderResult(
                "general-conversation/1",
                None,
                ProviderUsage(2, 1, 0, 0, 1),
                ProviderError("DOWN", "server_error", True, "暂时不可用"),
            )
        )
    script.append(
        ProviderResult(
            "general-conversation/1",
            None
            if outcome.endswith("failure")
            else ProviderMessage("assistant", "正文"),
            ProviderUsage(5, 4, 0, 0, 2),
            ProviderError("MODEL_FAILED", "provider", False, "模型不可用")
            if outcome.endswith("failure")
            else None,
        )
    )
    bundle = build_local_agent_application(
        synthetic_settings(),
        provider=FakeModelProvider("synthetic", script),
        test_mode=True,
    )
    submitted = await bundle.conversation.submit(
        "budget-body",
        "tenant-1",
        ConversationMessageV1(
            message="解释品牌定位",
            request_id="budget-body",
            user_id="user-1",
        ),
    )
    initial = await bundle.runtime.repository.get(submitted.run_id, "tenant-1")
    await bundle.runtime.wait_for_background_tasks()
    final = await bundle.runtime.repository.get(submitted.run_id, "tenant-1")
    expected = BudgetCharge(
        iterations=3 if outcome.startswith("degraded") else 2,
        input_tokens=10 if outcome.startswith("degraded") else 8,
        output_tokens=7 if outcome.startswith("degraded") else 6,
        cost_microunits=4 if outcome.startswith("degraded") else 3,
    )
    assert final.budget_state.consumed == expected
    assert (
        final.budget_state.started_at_epoch_ms
        == initial.budget_state.started_at_epoch_ms
    )
    assert (
        final.budget_state.deadline_epoch_ms == initial.budget_state.deadline_epoch_ms
    )
    assert final.usage.input_tokens == expected.input_tokens
    assert final.usage.output_tokens == expected.output_tokens
    assert final.usage.cost_microunits == expected.cost_microunits
    assert final.status is (
        RunStatus.FAILED if outcome.endswith("failure") else RunStatus.SUCCEEDED
    )
    assert final.degraded is outcome.startswith("degraded")
    await bundle.close()


@pytest.mark.asyncio
async def test_cancelled_direct_first_failure_cannot_start_fallback() -> None:
    from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
    from efficiency_platform_agent.contracts.requests import CancelRunRequestV1
    from efficiency_platform_agent.core.enums import RunStatus
    from efficiency_platform_agent.core.run import ProviderError
    from tests.api.test_conversation_routes import StubInterpreter, intent

    started = asyncio.Event()
    release = asyncio.Event()

    class RetryableProvider(FakeModelProvider):
        calls = 0

        async def complete(self, request):
            self.calls += 1
            started.set()
            await release.wait()
            return ProviderResult(
                request.contract_version,
                None,
                ProviderUsage(5, 2, 0, 0, 1),
                ProviderError("DOWN", "server_error", True, "暂时不可用"),
            )

    provider = RetryableProvider("synthetic", [])
    bundle = build_local_agent_application(
        synthetic_settings(), provider=provider, test_mode=True
    )
    bundle.conversation.interpreter = StubInterpreter(
        [
            intent().model_copy(update={"task_type": "general_chat"}),
        ]
    )
    submitted = await bundle.conversation.submit(
        "cancel-body",
        "tenant-1",
        ConversationMessageV1(
            message="解释品牌定位",
            request_id="cancel-body",
            user_id="user-1",
        ),
    )
    await asyncio.wait_for(started.wait(), 1)
    await bundle.runtime.cancel_run(
        submitted.run_id, CancelRunRequestV1(tenant_id="tenant-1")
    )
    release.set()
    await bundle.runtime.wait_for_background_tasks()
    final = await bundle.runtime.get_run(submitted.run_id, "tenant-1")
    assert provider.calls == 1
    assert final.status is RunStatus.CANCELLED
    assert bundle.conversation.direct_submissions._entries == {}
    await bundle.close()


@pytest.mark.asyncio
async def test_direct_model_cancellation_scope_does_not_cancel_other_run() -> None:
    from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
    from efficiency_platform_agent.contracts.requests import CancelRunRequestV1
    from efficiency_platform_agent.core.enums import RunStatus
    from efficiency_platform_agent.core.run import ProviderError
    from tests.api.test_conversation_routes import StubInterpreter, intent

    started = {"请求A": asyncio.Event(), "请求B": asyncio.Event()}
    release = asyncio.Event()
    calls = {"请求A": 0, "请求B": 0}

    class ConcurrentProvider(FakeModelProvider):
        async def complete(self, request):
            text = request.messages[-1].content
            calls[text] += 1
            if calls[text] == 1:
                started[text].set()
                await release.wait()
                return ProviderResult(
                    request.contract_version,
                    None,
                    ProviderUsage(1, 1, 0, 0, 1),
                    ProviderError("DOWN", "server_error", True, "暂时不可用"),
                )
            return ProviderResult(
                request.contract_version,
                ProviderMessage("assistant", "未取消任务的回答"),
                ProviderUsage(2, 1, 0, 0, 1),
            )

    bundle = build_local_agent_application(
        synthetic_settings(),
        provider=ConcurrentProvider("synthetic", []),
        test_mode=True,
    )
    parsed = intent().model_copy(update={"task_type": "general_chat"})
    bundle.conversation.interpreter = StubInterpreter([parsed, parsed])
    submitted = []
    for index, text in enumerate(started):
        submitted.append(
            await bundle.conversation.submit(
                f"scope-{index}",
                "tenant-1",
                ConversationMessageV1(
                    message=text,
                    request_id=f"scope-{index}",
                    user_id="user-1",
                ),
            )
        )
    await asyncio.wait_for(
        asyncio.gather(*(event.wait() for event in started.values())), 1
    )
    await bundle.runtime.cancel_run(
        submitted[0].run_id, CancelRunRequestV1(tenant_id="tenant-1")
    )
    release.set()
    await bundle.runtime.wait_for_background_tasks()
    assert calls == {"请求A": 1, "请求B": 2}
    cancelled = await bundle.runtime.get_run(submitted[0].run_id, "tenant-1")
    completed = await bundle.runtime.get_run(submitted[1].run_id, "tenant-1")
    assert cancelled.status is RunStatus.CANCELLED
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.degraded is True
    await bundle.close()


def synthetic_settings() -> S7IntegrationSettings:
    """使用合成值构造配置，测试不读取真实 env 或网络。"""
    return S7IntegrationSettings(
        deepseek_base_url=SecretStr("https://synthetic.invalid"),
        deepseek_api_key=SecretStr("synthetic-key"),
        deepseek_fast_model=SecretStr("synthetic-fast"),
        deepseek_balanced_model=SecretStr("synthetic-balanced"),
        deepseek_strong_model=SecretStr("synthetic-strong"),
    )


@pytest.mark.parametrize(
    ("research_enabled", "event_name", "reason_code"),
    (
        (False, "capability_disabled", "RESEARCH_GATE_DISABLED"),
        (True, "capability_ready", None),
    ),
)
def test_factory_creates_one_logger_and_reports_research_capability_state(
    monkeypatch, research_enabled, event_name, reason_code
) -> None:
    """真实组合根只输出能力状态，不向日志器传递配置值。"""

    instances = []

    class CapturingExecutionLogger:
        def __init__(self) -> None:
            self.capabilities = []
            instances.append(self)

        def record(self, record) -> None:
            del record

        def log_capability(self, capability, *, enabled, reason_code=None) -> None:
            self.capabilities.append(
                (
                    "capability_ready" if enabled else "capability_disabled",
                    capability,
                    enabled,
                    reason_code,
                )
            )

        async def on_run_event(self, event) -> None:
            del event

        async def on_run_state(self, view) -> None:
            del view

    monkeypatch.setattr(
        local_real_factory, "LocalExecutionLogger", CapturingExecutionLogger
    )
    settings = synthetic_settings().model_copy(
        update={"gates": {"deepseek_web_search": research_enabled}}
    )
    bundle = local_real_factory.build_local_agent_application(settings)
    try:
        assert len(instances) == 1
        assert instances[0].capabilities == [
            ("capability_ready", "deepseek_chat", True, None),
            (event_name, "deepseek_web_search", research_enabled, reason_code)
        ]
        assert "synthetic-key" not in repr(instances[0].capabilities)
        assert "synthetic.invalid" not in repr(instances[0].capabilities)
    finally:
        asyncio.run(bundle.close())


def test_factory_disables_openai_sdk_hidden_retries(monkeypatch) -> None:
    """研究调用次数必须由 Agent 显式治理，SDK 不得暗中自动重试。"""

    captured_options = []

    class _Responses:
        async def create(self, **kwargs):
            del kwargs
            raise AssertionError("本测试只验证装配参数")

    class _ResearchClient:
        def __init__(self) -> None:
            self.responses = _Responses()

        async def close(self) -> None:
            return None

    def capture_async_openai(**kwargs):
        captured_options.append(kwargs)
        return _ResearchClient()

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", capture_async_openai)
    settings = synthetic_settings().model_copy(
        update={"gates": {"deepseek_web_search": True}}
    )
    provider = FakeModelProvider("synthetic", [])
    bundle = build_local_agent_application(
        settings,
        provider=provider,
        test_mode=True,
    )
    try:
        assert len(captured_options) == 1
        assert captured_options[0]["max_retries"] == 0
    finally:
        asyncio.run(bundle.close())


def test_factory_injects_one_logger_into_all_diagnostic_boundaries(monkeypatch) -> None:
    """真实组合根的模型、图、Harness 与研究 Provider 必须共享同一日志器。"""

    logger_instances = []
    research_provider_instances = []

    class CapturingExecutionLogger:
        def __init__(self) -> None:
            logger_instances.append(self)

        def record(self, record) -> None:
            del record

        def log_capability(self, capability, *, enabled, reason_code=None) -> None:
            del capability, enabled, reason_code

        async def on_run_event(self, event) -> None:
            del event

        async def on_run_state(self, view) -> None:
            del view

    class CapturingResearchProvider:
        def __init__(self, client, *, model, recorder) -> None:
            self.client = client
            self.model = model
            self.recorder = recorder
            research_provider_instances.append(self)

    monkeypatch.setattr(
        local_real_factory, "LocalExecutionLogger", CapturingExecutionLogger
    )
    monkeypatch.setattr(
        local_real_factory, "DeepSeekWebSearchProvider", CapturingResearchProvider
    )
    settings = synthetic_settings().model_copy(
        update={"gates": {"deepseek_web_search": True}}
    )
    bundle = local_real_factory.build_local_agent_application(settings)
    try:
        assert len(logger_instances) == 1
        assert len(research_provider_instances) == 1
        recorder = logger_instances[0]
        assert bundle.conversation.interpreter.model_runtime.diagnostic_recorder is recorder
        assert bundle.runtime.graph_runtime.diagnostic_recorder is recorder
        assert bundle.runtime.diagnostic_recorder is recorder
        assert research_provider_instances[0].recorder is recorder
    finally:
        asyncio.run(bundle.close())


def test_factory_test_mode_uses_one_noop_recorder_without_terminal_logger(monkeypatch) -> None:
    """测试模式复用 Noop Recorder，且不得构造本地终端日志器。"""

    def reject_logger_creation():
        raise AssertionError("测试模式不得创建本地终端日志器")

    monkeypatch.setattr(
        local_real_factory, "LocalExecutionLogger", reject_logger_creation
    )
    bundle = build_local_agent_application(
        synthetic_settings(),
        provider=FakeModelProvider("synthetic", []),
        test_mode=True,
    )
    try:
        recorder = bundle.conversation.interpreter.model_runtime.diagnostic_recorder
        assert isinstance(recorder, NoopDiagnosticRecorder)
        assert bundle.runtime.graph_runtime.diagnostic_recorder is recorder
        assert bundle.runtime.diagnostic_recorder is recorder
    finally:
        asyncio.run(bundle.close())


@pytest.mark.asyncio
@pytest.mark.parametrize("test_mode", [True, False])
async def test_factory_registers_both_paths_with_shared_governance(test_mode) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: pytest.fail("组合根装配不得访问模型")
        )
    ) as client:
        bundle = build_local_agent_application(
            synthetic_settings(),
            test_mode=test_mode,
            http_client=client,
            provider=FakeModelProvider("synthetic", []) if test_mode else None,
        )
        graph = bundle.runtime.graph_runtime
        assert graph.registry.available_modes() == frozenset(
            {
                StrategyMode.DIRECT,
                StrategyMode.MULTI_AGENT,
            }
        )
        direct = graph.registry.get(StrategyMode.DIRECT).builder
        assert (
            direct.agent.model_runtime is bundle.conversation.interpreter.model_runtime
        )
        assert direct.resolver.__self__ is bundle.conversation.direct_submissions
        assert graph.cancellation is bundle.runtime.cancellation_signal
        await bundle.close()


def test_factory_accepts_mock_provider_only_in_explicit_test_mode() -> None:
    provider = FakeModelProvider("synthetic", [])

    with pytest.raises(ValueError, match="测试模式"):
        build_local_agent_application(synthetic_settings(), provider=provider)

    bundle = build_local_agent_application(
        synthetic_settings(), provider=provider, test_mode=True
    )

    paths = set(bundle.app.openapi()["paths"])
    assert "/v1/conversations/{conversation_id}/messages" in paths
    assert bundle.runtime.event_hub is bundle.event_hub
    assert bundle.app.state.local_test_mode is True
    assert bundle.http_client is None
    assert bundle.conversation.interpreter.timeout_ms == 60_000


def test_factory_real_streaming_providers_allow_operation_step_budget() -> None:
    """真实组合根的模型 HTTP 上限不得短于运营单节点预算。"""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: pytest.fail("模型请求不应在装配阶段发生")
        )
    )
    bundle = build_local_agent_application(
        synthetic_settings(),
        test_mode=False,
        http_client=client,
    )
    providers = bundle.conversation.interpreter.model_runtime.registry.providers
    assert providers
    assert {provider.timeout_ms for provider in providers.values()} == {120_000}




@pytest.mark.asyncio
async def test_factory_fake_http_research_flow_keeps_provider_citation() -> None:
    intent = {
        "contract_version": "intent/1",
        "domain": "内容",
        "goal": "研究行业热点",
        "task_type": "industry_digest",
        "channels": [],
        "audience": None,
        "style": None,
        "time_range": "本周",
        "needs_research": True,
        "needs_multi_agent": True,
        "missing_fields": [],
        "needs_clarification": False,
        "confidence": 0.99,
        "model_hint": "balanced",
        "requirements": {
            "contract_version": "intent.requirements/1",
            "topic": "行业热点",
            "time_window": "本周",
            "platforms": [],
            "brand": None,
            "product": None,
            "goal": None,
            "planning_window": None,
            "ip": None,
            "audience": None,
            "incubation_window": None,
            "campaign_goal": None,
            "campaign_window": None,
            "topic_scope": None,
            "calendar_window": None,
            "growth_goal": None,
            "funnel_stage": None,
            "experiment_window": None,
            "review_window": None,
            "metric_definition": None,
        },
    }
    deliverable = {
        "contract_version": "deliverable/1",
        "platform": "research",
        "title": "热点",
        "body": "研究正文",
        "hashtags": [],
        "format_notes": [],
        "citations": [
            {
                "url": "https://example.com/hot",
                "title": "可信来源",
                "source": "公开机构",
            }
        ],
        "warnings": [],
    }
    model = FakeModelProvider(
        "synthetic",
        [
            ProviderResult(
                "intent-model/1",
                ProviderMessage("assistant", json.dumps(intent, ensure_ascii=False)),
                ProviderUsage(1, 1, 0, 0, 0),
            ),
            ProviderResult(
                "operation-model/1",
                ProviderMessage(
                    "assistant", json.dumps(deliverable, ensure_ascii=False)
                ),
                ProviderUsage(1, 1, 0, 0, 0),
            ),
        ],
    )

    class ResearchFake:
        async def research(self, request):
            return ResearchResult(
                "research-result/1",
                request.request_id,
                request.task_id,
                request.tenant_id,
                ResearchStatus.SUCCEEDED,
                (
                    ResearchObservation(
                        "observation-hot",
                        "可信来源",
                        "公开机构",
                        "https://example.com/hot",
                        1,
                        2,
                        SourceScope.EXTERNAL_REFERENCE,
                        frozenset({"goal"}),
                        True,
                        EvidenceDuplicateStatus.UNIQUE,
                        EvidenceQualityStatus.VALID,
                    ),
                ),
                (),
                None,
            )

    settings = synthetic_settings().model_copy(
        update={"gates": {"deepseek_web_search": True}}
    )
    bundle = build_local_agent_application(
        settings,
        provider=model,
        test_mode=True,
        research_provider=ResearchFake(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=bundle.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/conversations/conversation-hot/messages",
            headers={"X-Tenant-ID": "tenant-1"},
            json={
                "message": "研究行业热点",
                "request_id": "request-hot",
                "user_id": "user-1",
            },
        )
        assert response.status_code == 201
        await bundle.runtime.wait_for_background_tasks()
        run = await bundle.runtime.get_run(response.json()["run_id"], "tenant-1")
        assert run.status.value == "succeeded"
        assert run.output is not None
        stream = await client.get(
            f"/v1/runs/{response.json()['run_id']}/events",
            headers={"X-Tenant-ID": "tenant-1"},
        )
        assert stream.status_code == 200
        assert "https://example.com/hot" in stream.text
        assert "stream_done" in stream.text
    await bundle.close()


@pytest.mark.asyncio
async def test_factory_research_gate_off_fails_without_model_fallback() -> None:
    """研究 Gate 关闭时不得以普通模型专家伪造联网研究结果。"""
    intent = {
        "contract_version": "intent/1",
        "domain": "内容",
        "goal": "研究行业热点",
        "task_type": "industry_digest",
        "channels": [],
        "audience": None,
        "style": None,
        "time_range": "本周",
        "needs_research": True,
        "needs_multi_agent": True,
        "missing_fields": [],
        "needs_clarification": False,
        "confidence": 0.99,
        "model_hint": "balanced",
        "requirements": {
            "contract_version": "intent.requirements/1",
            "topic": "行业热点",
            "time_window": "本周",
            "platforms": [],
            "brand": None,
            "product": None,
            "goal": None,
            "planning_window": None,
            "ip": None,
            "audience": None,
            "incubation_window": None,
            "campaign_goal": None,
            "campaign_window": None,
            "topic_scope": None,
            "calendar_window": None,
            "growth_goal": None,
            "funnel_stage": None,
            "experiment_window": None,
            "review_window": None,
            "metric_definition": None,
        },
    }
    deliverable = {
        "contract_version": "deliverable/1",
        "platform": "research",
        "title": "伪造研究",
        "body": "已联网检索并完成研究。",
        "hashtags": [],
        "format_notes": [],
        "citations": [
            {
                "url": "https://example.com/unverified",
                "title": "未核验证据",
                "source": "未知来源",
            }
        ],
        "warnings": [],
    }
    model = FakeModelProvider(
        "synthetic",
        [
            ProviderResult(
                "intent-model/1",
                ProviderMessage("assistant", json.dumps(intent, ensure_ascii=False)),
                ProviderUsage(1, 1, 0, 0, 0),
            ),
            ProviderResult(
                "operation-model/1",
                ProviderMessage(
                    "assistant", json.dumps(deliverable, ensure_ascii=False)
                ),
                ProviderUsage(1, 1, 0, 0, 0),
            ),
        ],
    )
    settings = synthetic_settings().model_copy(
        update={"gates": {"deepseek_web_search": False}}
    )
    bundle = build_local_agent_application(settings, provider=model, test_mode=True)
    submitted = await bundle.conversation.submit(
        "research-disabled",
        "tenant-1",
        ConversationMessageV1(
            message="研究行业热点",
            request_id="research-disabled",
            user_id="user-1",
        ),
    )
    await bundle.runtime.wait_for_background_tasks()
    run = await bundle.runtime.get_run(submitted.run_id, "tenant-1")

    assert run.status is RunStatus.FAILED
    assert run.output is None
    assert run.failure is not None
    assert run.failure.code == "RESEARCH_UNAVAILABLE"
    assert run.failure.safe_message == "本次未能完成在线核验，请稍后重试"
    assert model._index == 1
    await bundle.close()
