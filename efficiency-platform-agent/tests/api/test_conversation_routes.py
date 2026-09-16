"""会话门面与 HTTP 路由的离线契约测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from efficiency_platform_agent.agents.operation.contracts.profiles import (
    select_profiles_for_task,
)
from efficiency_platform_agent.agents.operation.contracts.scenarios import (
    compile_scenario_plan,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    OperationDomain,
    OperationObjectKind,
)
from efficiency_platform_agent.api.app import create_app
from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)
from efficiency_platform_agent.contracts.responses import RunViewV1, UsageV1
from efficiency_platform_agent.conversation.context import ConversationTurn
from efficiency_platform_agent.conversation.service import (
    ConversationService,
    ConversationSubmissionStore,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import ExecutionBudget
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness.errors import HarnessError
from efficiency_platform_agent.orchestration.intent_fast_path import (
    detect_fast_path_intent,
)
from efficiency_platform_agent.orchestration.scenario_resolver import ScenarioResolver
from efficiency_platform_agent.runtime.event_hub import EventHub


@pytest.mark.asyncio
async def test_identity_question_returns_direct_chat_without_clarification() -> None:
    from efficiency_platform_agent.harness.local_real_factory import (
        build_local_agent_application,
    )
    from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
    from tests.unit.harness.test_local_real_factory import synthetic_settings

    class ForbiddenProvider(FakeModelProvider):
        async def complete(self, request):
            pytest.fail("身份快速响应不得调用任何模型")

    bundle = build_local_agent_application(
        synthetic_settings(),
        provider=ForbiddenProvider("synthetic", []),
        test_mode=True,
    )
    interpreter = StubInterpreter([])
    bundle.conversation.interpreter = interpreter
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=bundle.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/conversations/conversation-identity/messages",
            headers={"X-Tenant-ID": "tenant-1"},
            json={"message": "你是谁", "request_id": "identity", "user_id": "user-1"},
        )
        assert response.status_code == 201
        run_id = response.json()["run_id"]
        await bundle.runtime.wait_for_background_tasks()
        run = await bundle.runtime.get_run(run_id, "tenant-1")
        assert run.status is RunStatus.SUCCEEDED
        assert run.strategy is StrategyMode.DIRECT
        stream = await client.get(
            f"/v1/runs/{run_id}/events", headers={"X-Tenant-ID": "tenant-1"}
        )
        assert "AI 内容运营助手" in stream.text
        assert "assistant_delta" in stream.text
        assert "stream_done" in stream.text
        assert "clarification_required" not in stream.text
        assert "deliverable" not in stream.text
    assert interpreter.context_sizes == []
    turns = bundle.conversation._contexts[
        ("tenant-1", "conversation-identity")
    ].context.turns
    assert turns[0] == ConversationTurn("user", "你是谁")
    assert "AI 内容运营助手" in turns[1].content
    assert bundle.conversation.direct_submissions._entries == {}
    await bundle.close()


@pytest.mark.asyncio
async def test_general_chat_prepares_direct_with_remaining_budget_and_history() -> None:
    class ChatInterpreter:
        async def execute(self, text, context, *, remaining_budget):
            return SimpleNamespace(
                intent=intent().model_copy(update={"task_type": "general_chat"}),
                usage=UsageSnapshot(9, 4, 3, estimated=True),
                degraded=True,
                attempts=(object(), object()),
            )

    runtime = RecordingRuntime()
    facade = service(runtime, ChatInterpreter())
    await facade.submit(
        "chat",
        "tenant-1",
        ConversationMessageV1(
            message="解释品牌定位", request_id="chat-1", user_id="user-1"
        ),
    )
    await runtime.wait()
    prepared = runtime.preparations[0]
    assert prepared.request.requested_strategy is StrategyMode.DIRECT
    assert prepared.request.strategy_payload_schema_version == "strategy.none/1"
    assert prepared.request.strategy_payload == {}
    submission = facade.direct_submissions._entries[("tenant-1", "chat-1")].submission
    assert submission.visible_history == ()
    assert submission.current_message == "解释品牌定位"
    assert submission.remaining_budget.iterations == 8
    assert submission.remaining_budget.input_tokens == 91
    assert submission.remaining_budget.output_tokens == 96
    assert submission.remaining_budget.cost_microunits == 97
    assert 0 < submission.remaining_budget.timeout_ms <= 1_000
    assert prepared.usage == UsageSnapshot(9, 4, 3, estimated=True)
    assert prepared.degraded is True
    assert facade.submissions._entries == {}


@pytest.mark.asyncio
async def test_explicit_research_content_uses_fast_path_and_marks_research_requirement() -> None:
    """明确的研究加多平台请求跳过意图模型，并把研究要求传入任务契约。"""

    class ForbiddenInterpreter:
        async def interpret(self, text, context):
            del text, context
            pytest.fail("明确研究请求不应再次调用意图模型")

    runtime = RecordingRuntime()
    facade = service(
        runtime,
        ForbiddenInterpreter(),
        fast_path_detector=detect_fast_path_intent,
    )

    await facade.submit(
        "fast-research",
        "tenant-1",
        ConversationMessageV1(
            message="收集下周 AI 行业热点，整理成公众号、小红书和头条三种版本",
            request_id="fast-research-1",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    submission = facade.submissions._entries[("tenant-1", "fast-research-1")]
    assert submission.submission.scenario_id == "multi_platform_content"
    assert submission.submission.task_spec.requires_research is True
    assert submission.submission.task_spec.requires_user_input is False
    assert runtime.requests[0].requested_strategy is StrategyMode.MULTI_AGENT


@pytest.mark.asyncio
async def test_non_research_message_keeps_model_interpreter_path() -> None:
    """普通运营请求不命中研究快路径，仍由原意图解释器处理。"""
    runtime = RecordingRuntime()
    interpreter = StubInterpreter([intent()])
    facade = service(
        runtime,
        interpreter,
        fast_path_detector=detect_fast_path_intent,
    )

    await facade.submit(
        "model-path",
        "tenant-1",
        ConversationMessageV1(
            message="帮我规划新品内容方向",
            request_id="model-path-1",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    assert interpreter.context_sizes == [0]


@pytest.mark.asyncio
async def test_general_chat_research_conflict_routes_to_industry_digest() -> None:
    runtime = RecordingRuntime()
    parsed = intent().model_copy(
        update={
            "domain": "公开资料研究",
            "goal": "核实 AI Agent 最新进展",
            "task_type": "general_chat",
            "needs_research": True,
            "needs_multi_agent": False,
            "requirements": IntentRequirementsV1(),
        }
    )
    facade = service(runtime, StubInterpreter([parsed]))

    await facade.submit(
        "research-conflict",
        "tenant-1",
        ConversationMessageV1(
            message="查一下 AI Agent 最新进展",
            request_id="research-conflict-1",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    submission = facade.submissions._entries[("tenant-1", "research-conflict-1")]
    conditions = {
        item.condition_id: item.value for item in submission.submission.task_spec.key_conditions
    }
    assert runtime.preparations[0].request.requested_strategy is StrategyMode.MULTI_AGENT
    assert submission.submission.scenario_id == "industry_digest"
    assert dict(conditions["topic"].items)["topic"] == "AI Agent 最新进展"
    assert "最近7天" in dict(conditions["time-window"].items)["time-window"]
    assert "最近7天（默认最新信息窗口）" in (
        submission.submission.task_spec.goals[0].description
    )
    assert submission.submission.task_spec.requires_user_input is False


@pytest.mark.asyncio
async def test_research_follow_up_inherits_topic_from_visible_history() -> None:
    runtime = RecordingRuntime()
    parsed = intent().model_copy(
        update={
            "domain": "公开资料研究",
            "goal": "获取最新信息",
            "task_type": "general_chat",
            "needs_research": True,
            "needs_multi_agent": False,
            "requirements": IntentRequirementsV1(),
        }
    )
    facade = service(runtime, StubInterpreter([parsed]))
    context_entry = facade._context_entry(
        ("tenant-1", "research-follow-up"), facade.monotonic()
    )
    context_entry.context.append(ConversationTurn("user", "AI Agent 行业动态"))

    await facade.submit(
        "research-follow-up",
        "tenant-1",
        ConversationMessageV1(
            message="那查一下最新的",
            request_id="research-follow-up-1",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    submission = facade.submissions._entries[("tenant-1", "research-follow-up-1")]
    conditions = {
        item.condition_id: item.value for item in submission.submission.task_spec.key_conditions
    }
    assert submission.submission.scenario_id == "industry_digest"
    assert dict(conditions["topic"].items)["topic"] == "AI Agent 行业动态"
    assert submission.submission.task_spec.requires_user_input is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message_text",
    [
        "帮我查一下最新的",
        "请给我来源",
        "帮我搜一下最新的",
        "请帮忙核实一下",
    ],
)
async def test_explicit_research_follow_up_overrides_misclassified_general_chat(
    message_text: str,
) -> None:
    """搜索、最新和来源追问即使被误分普通对话，也必须继承主题进入研究场景。"""
    runtime = RecordingRuntime()
    misclassified = intent().model_copy(
        update={
            "domain": "通用对话",
            "goal": "普通问答",
            "task_type": "general_chat",
            "needs_research": False,
            "needs_multi_agent": False,
            "requirements": IntentRequirementsV1(),
        }
    )
    facade = service(runtime, StubInterpreter([misclassified]))
    context_entry = facade._context_entry(
        ("tenant-1", "misclassified-research"), facade.monotonic()
    )
    context_entry.context.append(ConversationTurn("user", "AI Agent 行业动态"))

    await facade.submit(
        "misclassified-research",
        "tenant-1",
        ConversationMessageV1(
            message=message_text,
            request_id=f"misclassified-{message_text}",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    submission = facade.submissions._entries[
        ("tenant-1", f"misclassified-{message_text}")
    ]
    conditions = {
        item.condition_id: item.value for item in submission.submission.task_spec.key_conditions
    }
    assert runtime.preparations[0].request.requested_strategy is StrategyMode.MULTI_AGENT
    assert submission.submission.scenario_id == "industry_digest"
    assert dict(conditions["topic"].items)["topic"] == "AI Agent 行业动态"
    assert submission.submission.task_spec.requires_user_input is False


@pytest.mark.asyncio
async def test_explicit_research_topic_overrides_misclassified_general_goal() -> None:
    """带主题的显式搜索必须优先当前消息，不能采用误分类的通用目标。"""
    runtime = RecordingRuntime()
    misclassified = intent().model_copy(
        update={
            "domain": "通用对话",
            "goal": "回答用户问题",
            "task_type": "general_chat",
            "needs_research": False,
            "needs_multi_agent": False,
            "requirements": IntentRequirementsV1(),
        }
    )
    facade = service(runtime, StubInterpreter([misclassified]))
    context_entry = facade._context_entry(
        ("tenant-1", "misclassified-topic"), facade.monotonic()
    )
    context_entry.context.append(ConversationTurn("user", "AI Agent 行业动态"))

    await facade.submit(
        "misclassified-topic",
        "tenant-1",
        ConversationMessageV1(
            message="请搜索机器人行业最新动态",
            request_id="misclassified-topic",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    submission = facade.submissions._entries[
        ("tenant-1", "misclassified-topic")
    ]
    conditions = {
        item.condition_id: item.value
        for item in submission.submission.task_spec.key_conditions
    }
    assert submission.submission.scenario_id == "industry_digest"
    assert dict(conditions["topic"].items)["topic"] == "机器人行业最新动态"


@pytest.mark.asyncio
@pytest.mark.parametrize("follow_up_type", ["general_chat", "multi_platform_content"])
async def test_pending_operation_takes_precedence_over_local_and_chat(
    follow_up_type,
) -> None:
    runtime = RecordingRuntime()
    prior = intent().model_copy(
        update={
            "requirements": IntentRequirementsV1(topic="新品", platforms=()),
        }
    )
    follow_up = intent().model_copy(update={"task_type": follow_up_type})
    interpreter = StubInterpreter([prior, follow_up])
    facade = service(runtime, interpreter)
    for index, message in enumerate(("写新品内容", "你好")):
        await facade.submit(
            "pending",
            "tenant-1",
            ConversationMessageV1(
                message=message, request_id=f"pending-{index}", user_id="user-1"
            ),
        )
        await runtime.wait()
    assert interpreter.context_sizes == [0, 2]
    assert runtime.requests[-1].requested_strategy is StrategyMode.MULTI_AGENT
    assert (
        facade.submissions._entries[("tenant-1", "pending-1")].submission.scenario_id
        == "multi_platform_content"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.TIMED_OUT],
)
async def test_direct_terminal_discards_unconsumed_submission_and_writes_success_only(
    status,
) -> None:
    runtime = RecordingRuntime()
    facade = service(runtime, StubInterpreter([]))
    submitted = await facade.submit(
        "terminal",
        "tenant-1",
        ConversationMessageV1(
            message="你好", request_id="terminal-1", user_id="user-1"
        ),
    )
    await runtime.wait()
    assert ("tenant-1", "terminal-1") in facade.direct_submissions._entries
    await facade.on_run_state(
        SimpleNamespace(
            run_id=submitted.run_id,
            status=status,
            output={"content": "回答正文"},
        )
    )
    assert facade.direct_submissions._entries == {}
    assert facade._active_runs == {}
    turns = facade._contexts[("tenant-1", "terminal")].context.turns
    assert len(turns) == (2 if status is RunStatus.SUCCEEDED else 1)


@pytest.mark.asyncio
async def test_general_chat_model_uses_prior_answer_and_counts_both_stages() -> None:
    from efficiency_platform_agent.core.run import (
        ProviderMessage,
        ProviderResult,
        ProviderUsage,
    )
    from efficiency_platform_agent.harness.local_real_factory import (
        build_local_agent_application,
    )
    from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
    from tests.unit.harness.test_local_real_factory import synthetic_settings

    parsed = intent().model_copy(
        update={
            "task_type": "general_chat",
            "requirements": IntentRequirementsV1(),
            "needs_multi_agent": False,
        }
    )

    class RecordingProvider(FakeModelProvider):
        def __init__(self):
            super().__init__(
                "synthetic",
                [
                    ProviderResult(
                        "intent/1",
                        ProviderMessage("assistant", parsed.model_dump_json()),
                        ProviderUsage(3, 2, 0, 0, 1),
                    ),
                    ProviderResult(
                        "general-conversation/1",
                        ProviderMessage("assistant", "品牌定位是明确独特价值。"),
                        ProviderUsage(5, 4, 0, 0, 2),
                    ),
                    ProviderResult(
                        "intent/1",
                        ProviderMessage("assistant", parsed.model_dump_json()),
                        ProviderUsage(3, 2, 0, 0, 1),
                    ),
                    ProviderResult(
                        "general-conversation/1",
                        ProviderMessage("assistant", "例如，面向通勤者提供便携咖啡。"),
                        ProviderUsage(5, 4, 0, 0, 2),
                    ),
                ],
            )
            self.requests = []

        async def complete(self, request):
            self.requests.append(request)
            return await super().complete(request)

    model = RecordingProvider()
    bundle = build_local_agent_application(
        synthetic_settings(), provider=model, test_mode=True
    )
    for index, text in enumerate(("解释品牌定位", "请举个例子")):
        submitted = await bundle.conversation.submit(
            "multi-turn",
            "tenant-1",
            ConversationMessageV1(
                message=text, request_id=f"chat-{index}", user_id="user-1"
            ),
        )
        await bundle.runtime.wait_for_background_tasks()
        run = await bundle.runtime.get_run(submitted.run_id, "tenant-1")
        assert run.status is RunStatus.SUCCEEDED
        assert run.strategy is StrategyMode.DIRECT
        assert set(run.output) == {"content"}
        assert run.usage.input_tokens == 8
        assert run.usage.output_tokens == 6
    assert len(model.requests) == 4
    messages = model.requests[-1].messages
    assert [(item.role, item.content) for item in messages[1:]] == [
        ("user", "解释品牌定位"),
        ("assistant", "品牌定位是明确独特价值。"),
        ("user", "请举个例子"),
    ]
    assert bundle.conversation.direct_submissions._entries == {}
    await bundle.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_direct_model_failure_or_cancellation_does_not_write_answer(
    cancel,
) -> None:
    from efficiency_platform_agent.contracts.requests import CancelRunRequestV1
    from efficiency_platform_agent.core.run import (
        ProviderMessage,
        ProviderResult,
        ProviderUsage,
    )
    from efficiency_platform_agent.harness.local_real_factory import (
        build_local_agent_application,
    )
    from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
    from tests.unit.harness.test_local_real_factory import synthetic_settings

    started = asyncio.Event()
    release = asyncio.Event()

    class ControlledProvider(FakeModelProvider):
        async def complete(self, request):
            started.set()
            await release.wait()
            return ProviderResult(
                "general-conversation/1",
                ProviderMessage("assistant", "迟到正文" if cancel else "  "),
                ProviderUsage(1, 1, 0, 0, 0),
            )

    bundle = build_local_agent_application(
        synthetic_settings(),
        provider=ControlledProvider("synthetic", []),
        test_mode=True,
    )
    bundle.conversation.interpreter = StubInterpreter(
        [
            intent().model_copy(update={"task_type": "general_chat"}),
        ]
    )
    submitted = await bundle.conversation.submit(
        "model-terminal",
        "tenant-1",
        ConversationMessageV1(
            message="解释品牌定位", request_id="model-terminal", user_id="user-1"
        ),
    )
    await asyncio.wait_for(started.wait(), 1)
    if cancel:
        await bundle.runtime.cancel_run(
            submitted.run_id, CancelRunRequestV1(tenant_id="tenant-1")
        )
    release.set()
    await bundle.runtime.wait_for_background_tasks()
    run = await bundle.runtime.get_run(submitted.run_id, "tenant-1")
    assert run.status is (RunStatus.CANCELLED if cancel else RunStatus.FAILED)
    if not cancel:
        assert run.error.code == "GENERAL_CONVERSATION_MODEL_FAILED"
    assert bundle.conversation.direct_submissions._entries == {}
    turns = bundle.conversation._contexts[("tenant-1", "model-terminal")].context.turns
    assert turns == (ConversationTurn("user", "解释品牌定位"),)
    await bundle.close()


class StubInterpreter:
    """按脚本返回意图并保留所见多轮上下文。"""

    def __init__(self, intents: list[IntentEnvelopeV1]) -> None:
        self.intents = intents
        self.context_sizes: list[int] = []

    async def interpret(self, text, context):
        del text
        self.context_sizes.append(len(context.turns))
        return self.intents.pop(0)


@pytest.mark.asyncio
async def test_terminal_before_direct_preparation_cannot_reinsert_submission() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class LateInterpreter:
        async def interpret(self, text, context):
            started.set()
            await release.wait()
            return intent().model_copy(update={"task_type": "general_chat"})

    runtime = RecordingRuntime()
    facade = service(runtime, LateInterpreter())
    submitted = await facade.submit(
        "late",
        "tenant-1",
        ConversationMessageV1(
            message="解释品牌定位", request_id="late", user_id="user-1"
        ),
    )
    await asyncio.wait_for(started.wait(), 1)
    await facade.on_run_state(
        SimpleNamespace(
            run_id=submitted.run_id,
            status=RunStatus.CANCELLED,
            output=None,
        )
    )
    release.set()
    with pytest.raises(HarnessError) as caught:
        await runtime.wait()
    assert caught.value.code == "CANCELLED"
    assert facade.direct_submissions._entries == {}
    assert facade._contexts[("tenant-1", "late")].context.turns == ()


@pytest.mark.asyncio
async def test_chat_intent_exhaustion_preserves_usage_without_model_submission() -> (
    None
):
    from efficiency_platform_agent.core.budget import BudgetExhaustedError

    class ExpensiveInterpreter:
        async def execute(self, text, context, *, remaining_budget):
            return SimpleNamespace(
                intent=intent().model_copy(update={"task_type": "general_chat"}),
                usage=UsageSnapshot(100, 4, 3, estimated=True),
                degraded=True,
                attempts=(object(),),
            )

    runtime = RecordingRuntime()
    facade = service(runtime, ExpensiveInterpreter())
    await facade.submit(
        "budget",
        "tenant-1",
        ConversationMessageV1(
            message="解释品牌定位", request_id="budget", user_id="user-1"
        ),
    )
    with pytest.raises(BudgetExhaustedError) as caught:
        await runtime.wait()
    assert caught.value.reason_code == "input_token_limit"
    assert caught.value.usage == UsageSnapshot(100, 4, 3, estimated=True)
    assert caught.value.degraded is True
    assert facade.direct_submissions._entries == {}


class RecordingRuntime:
    """不执行图，仅记录会话门面构造的真实 Run envelope。"""

    def __init__(self) -> None:
        self.event_hub = EventHub()
        self.requests = []
        self.initial_events = []
        self.pipeline_tasks = []
        self.preparations = []
        self.listeners = []

    async def create_and_schedule(self, request, *, initial_stream_events=()):
        self.requests.append(request)
        self.initial_events.append(initial_stream_events)
        return RunViewV1(
            run_id=f"run-{len(self.requests)}",
            request_id=request.request_id,
            status=RunStatus.QUEUED,
            strategy=None,
            usage=UsageV1(
                input_tokens=0,
                output_tokens=0,
                cost_microunits=0,
                estimated=False,
            ),
        )

    async def create_and_schedule_pipeline(self, request, prepare, *, on_queued=None):
        self.requests.append(request)
        request_index = len(self.requests) - 1
        view = RunViewV1(
            run_id=f"run-{len(self.requests)}",
            request_id=request.request_id,
            status=RunStatus.QUEUED,
            strategy=None,
            usage=UsageV1(
                input_tokens=0,
                output_tokens=0,
                cost_microunits=0,
                estimated=False,
            ),
        )

        if on_queued is not None:
            await on_queued(view)

        async def run_pipeline():
            class PipelineContext:
                run_id = view.run_id
                remaining_budget = RemainingBudget(10, 2, 100, 100, 100, 1_000)

                @staticmethod
                async def is_cancelled():
                    return False

                @staticmethod
                async def wait_cancelled():
                    await asyncio.Event().wait()

            prepared = await prepare(PipelineContext())
            self.preparations.append(prepared)
            self.initial_events.append(prepared.stream_events)
            self.requests[request_index] = prepared.request

        self.pipeline_tasks.append(asyncio.create_task(run_pipeline()))
        return view

    def add_run_state_listener(self, listener):
        self.listeners.append(listener)

    async def wait(self):
        await asyncio.gather(*self.pipeline_tasks)


def intent(*, missing: list[str] | None = None) -> IntentEnvelopeV1:
    return IntentEnvelopeV1(
        domain="content",
        goal="生成多平台内容",
        task_type="multi_platform_content",
        channels=["xiaohongshu"],
        needs_multi_agent=True,
        missing_fields=missing or [],
        needs_clarification=bool(missing),
        confidence=0.9,
        requirements=IntentRequirementsV1(
            topic="生成多平台内容", platforms=("xiaohongshu",)
        ),
    )


def service(runtime, interpreter, **kwargs) -> ConversationService:
    return ConversationService(
        runtime=runtime,
        interpreter=interpreter,
        resolver=ScenarioResolver(),
        submissions=ConversationSubmissionStore(),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_route_returns_201_and_controlled_multi_agent_envelope() -> None:
    runtime = RecordingRuntime()
    app = create_app(
        runtime, conversation_service=service(runtime, StubInterpreter([intent()]))
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/conversations/conversation-1/messages",
            headers={"X-Tenant-ID": "tenant-1"},
            json={
                "contract_version": "conversation/1",
                "message": "请生成多平台内容",
                "request_id": "request-1",
                "user_id": "user-1",
                "attachments": [],
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "queued"
    await runtime.wait()
    request = runtime.requests[0]
    assert request.requested_strategy is StrategyMode.MULTI_AGENT
    assert request.strategy_payload_schema_version == "operation-strategy-payload/1"
    assert set(request.strategy_payload) == {"operation_request"}


@pytest.mark.asyncio
async def test_clarification_is_recoverable_event_and_context_is_reused() -> None:
    runtime = RecordingRuntime()
    interpreter = StubInterpreter([intent(missing=["platforms"]), intent()])
    facade = service(runtime, interpreter)

    first = await facade.submit(
        "conversation-1",
        "tenant-1",
        ConversationMessageV1(
            message="写内容", request_id="request-1", user_id="user-1"
        ),
    )
    second = await facade.submit(
        "conversation-1",
        "tenant-1",
        ConversationMessageV1(
            message="发小红书", request_id="request-2", user_id="user-1"
        ),
    )
    await runtime.wait()

    assert first.run_id != second.run_id
    assert interpreter.context_sizes == [0, 2]
    clarification = runtime.initial_events[0][1]
    assert clarification[0] == "clarification_required"
    assert clarification[1]["fields"] == ["platforms"]


@pytest.mark.asyncio
async def test_clarification_follow_up_preserves_already_confirmed_platform_scope() -> (
    None
):
    runtime = RecordingRuntime()
    first_intent = intent(missing=["topic"]).model_copy(
        update={
            "requirements": IntentRequirementsV1(topic=None, platforms=("xiaohongshu",))
        }
    )
    follow_up = intent().model_copy(
        update={
            "requirements": IntentRequirementsV1(
                topic="秋季桂花拿铁新品上市",
                platforms=(
                    "xiaohongshu",
                    "wechat_official_account",
                    "toutiao",
                ),
            )
        }
    )
    facade = service(runtime, StubInterpreter([first_intent, follow_up]))

    await facade.submit(
        "conversation-scope",
        "tenant-1",
        ConversationMessageV1(
            message="只生成小红书文案",
            request_id="request-scope-1",
            user_id="user-1",
        ),
    )
    await runtime.wait()
    await facade.submit(
        "conversation-scope",
        "tenant-1",
        ConversationMessageV1(
            message="主题是秋季桂花拿铁新品上市",
            request_id="request-scope-2",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    submission = facade.submissions._entries[("tenant-1", "request-scope-2")].submission
    assert tuple(
        item.requirement_id for item in submission.request.requested_deliverables
    ) == ("platform-content-xiaohongshu",)
    platforms = next(
        item.value
        for item in submission.task_spec.key_conditions
        if item.condition_id == "platforms"
    )
    assert platforms is not None
    assert dict(platforms.items)["platforms"] == ("xiaohongshu",)


@pytest.mark.asyncio
async def test_resolver_derived_missing_field_is_preserved_for_follow_up_merge() -> (
    None
):
    runtime = RecordingRuntime()
    first_intent = intent().model_copy(
        update={
            "requirements": IntentRequirementsV1(topic="秋季新品", platforms=()),
            "missing_fields": [],
            "needs_clarification": False,
        }
    )
    follow_up = intent().model_copy(
        update={
            "requirements": IntentRequirementsV1(topic=None, platforms=("xiaohongshu",))
        }
    )
    facade = service(runtime, StubInterpreter([first_intent, follow_up]))

    await facade.submit(
        "conversation-derived-missing",
        "tenant-1",
        ConversationMessageV1(
            message="主题是秋季新品",
            request_id="request-derived-1",
            user_id="user-1",
        ),
    )
    await runtime.wait()
    assert runtime.initial_events[0][1][1]["fields"] == ["platforms"]
    await facade.submit(
        "conversation-derived-missing",
        "tenant-1",
        ConversationMessageV1(
            message="只发小红书",
            request_id="request-derived-2",
            user_id="user-1",
        ),
    )
    await runtime.wait()

    submission = facade.submissions._entries[
        ("tenant-1", "request-derived-2")
    ].submission
    conditions = {
        item.condition_id: item.value for item in submission.task_spec.key_conditions
    }
    assert conditions["topic"] is not None
    assert conditions["platforms"] is not None
    assert dict(conditions["topic"].items)["topic"] == "秋季新品"
    assert dict(conditions["platforms"].items)["platforms"] == ("xiaohongshu",)
    assert submission.task_spec.requires_user_input is False


@pytest.mark.asyncio
async def test_unknown_platform_fails_closed_without_expanding_to_all_platforms() -> (
    None
):
    runtime = RecordingRuntime()
    parsed = intent().model_copy(
        update={
            "requirements": IntentRequirementsV1(topic="新品", platforms=("douyin",))
        }
    )
    facade = service(runtime, StubInterpreter([parsed]))

    await facade.submit(
        "conversation-unknown-platform",
        "tenant-1",
        ConversationMessageV1(
            message="生成抖音文案",
            request_id="request-unknown-platform",
            user_id="user-1",
        ),
    )
    with pytest.raises(HarnessError, match="暂不支持的平台"):
        await runtime.wait()


@pytest.mark.asyncio
async def test_request_id_is_idempotent_and_conflicts_across_conversations() -> None:
    runtime = RecordingRuntime()
    facade = service(runtime, StubInterpreter([intent()]))
    message = ConversationMessageV1(
        message="写内容", request_id="request-1", user_id="user-1"
    )

    first, second = await asyncio.gather(
        facade.submit("conversation-1", "tenant-1", message),
        facade.submit("conversation-1", "tenant-1", message),
    )
    await runtime.wait()

    assert first == second
    assert len(runtime.requests) == 1
    with pytest.raises(ValueError, match="request_id"):
        await facade.submit("conversation-2", "tenant-1", message)


@pytest.mark.asyncio
async def test_same_request_id_is_tenant_isolated() -> None:
    runtime = RecordingRuntime()
    facade = service(runtime, StubInterpreter([intent(), intent()]))
    message = ConversationMessageV1(
        message="写内容", request_id="request-1", user_id="user-1"
    )

    first = await facade.submit("conversation-1", "tenant-1", message)
    second = await facade.submit("conversation-1", "tenant-2", message)
    await runtime.wait()

    assert first.run_id != second.run_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "tenant"),
    [
        ("/v1/conversations/%20/messages", "tenant-1"),
        ("/v1/conversations/conversation-1/messages", " "),
    ],
)
async def test_route_rejects_invalid_path_or_tenant(path: str, tenant: str) -> None:
    runtime = RecordingRuntime()
    app = create_app(
        runtime, conversation_service=service(runtime, StubInterpreter([intent()]))
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            path,
            headers={"X-Tenant-ID": tenant},
            json={
                "message": "写内容",
                "request_id": "request-1",
                "user_id": "user-1",
                "attachments": [],
            },
        )

    assert response.status_code == 400
    assert runtime.requests == []


class MutableClock:
    """测试用单调时钟。"""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.mark.asyncio
async def test_submit_returns_queued_before_intent_model_completes() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingInterpreter:
        async def interpret(self, text, context):
            del text, context
            started.set()
            await release.wait()
            return intent()

    runtime = RecordingRuntime()
    facade = service(runtime, BlockingInterpreter())

    submitted = await asyncio.wait_for(
        facade.submit(
            "conversation-1",
            "tenant-1",
            ConversationMessageV1(
                message="写内容", request_id="request-1", user_id="user-1"
            ),
        ),
        0.2,
    )

    assert submitted.status == "queued"
    await asyncio.wait_for(started.wait(), 0.2)
    release.set()
    await runtime.wait()


@pytest.mark.asyncio
async def test_inflight_intent_task_is_cancelled_without_waiting_for_provider() -> None:
    started = asyncio.Event()
    closed = asyncio.Event()

    class BlockingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.Event().wait()
            yield b""

        async def aclose(self) -> None:
            closed.set()

    from efficiency_platform_agent.contracts.requests import CancelRunRequestV1
    from efficiency_platform_agent.orchestration.cancellation import (
        InMemoryCancellationSignal,
    )
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )
    from tests.api.test_run_sse_integration import BlockingGraph, service_with_graph
    from tests.orchestration.test_intent_interpreter import _wire_runtime

    model_runtime, client = _wire_runtime(
        lambda _request: httpx.Response(200, stream=BlockingBody())
    )
    cancellation = InMemoryCancellationSignal()
    runtime = service_with_graph(BlockingGraph(), signal=cancellation)
    runtime.budget = ExecutionBudget(10, 2, 64_000, 8_000, 10_000, 1_000_000)
    facade = service(runtime, IntentInterpreter(model_runtime))
    try:
        submitted = await facade.submit(
            "conversation-cancel-intent",
            "tenant-1",
            ConversationMessageV1(
                message="写内容",
                request_id="request-cancel-intent",
                user_id="user-1",
            ),
        )
        await asyncio.wait_for(started.wait(), 0.2)
        await runtime.cancel_run(
            submitted.run_id, CancelRunRequestV1(tenant_id="tenant-1")
        )
        await asyncio.wait_for(runtime.wait_for_background_tasks(), 0.2)
    finally:
        await client.aclose()

    assert closed.is_set()
    final = await runtime.get_run(submitted.run_id, "tenant-1")
    assert final.status is RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_intent_attempt_count_becomes_pipeline_iteration_charge() -> None:
    class AttemptInterpreter:
        async def execute(self, text, context, *, remaining_budget):
            del text, context, remaining_budget
            return SimpleNamespace(
                intent=intent(),
                usage=UsageSnapshot(9, 4, 3, estimated=True),
                degraded=True,
                attempts=(object(), object(), object()),
                repair_attempted=True,
            )

    runtime = RecordingRuntime()
    facade = service(runtime, AttemptInterpreter())
    await facade.submit(
        "conversation-attempts",
        "tenant-1",
        ConversationMessageV1(
            message="写内容", request_id="request-attempts", user_id="user-1"
        ),
    )
    await runtime.wait()

    assert runtime.preparations[0].charge.iterations == 3
    assert runtime.preparations[0].charge.input_tokens == 9
    assert runtime.preparations[0].charge.output_tokens == 4


@pytest.mark.asyncio
async def test_context_and_idempotency_cache_are_ttl_and_capacity_bounded() -> None:
    clock = MutableClock()
    runtime = RecordingRuntime()
    facade = service(
        runtime,
        StubInterpreter([intent(), intent(), intent(), intent()]),
        max_contexts=2,
        max_requests=2,
        ttl_seconds=10,
        monotonic=clock,
    )
    for index in range(3):
        await facade.submit(
            f"conversation-{index}",
            "tenant-1",
            ConversationMessageV1(
                message="写内容",
                request_id=f"request-{index}",
                user_id="user-1",
            ),
        )
    await runtime.wait()

    assert len(facade._contexts) == 2
    assert len(facade._requests) == 2
    assert ("tenant-1", "conversation-0") not in facade._contexts
    assert ("tenant-1", "request-0") not in facade._requests

    clock.value = 11
    await facade.submit(
        "conversation-next",
        "tenant-2",
        ConversationMessageV1(
            message="写内容", request_id="request-next", user_id="user-2"
        ),
    )
    await runtime.wait()
    assert set(facade._contexts) == {("tenant-2", "conversation-next")}
    assert set(facade._requests) == {("tenant-2", "request-next")}


@pytest.mark.asyncio
async def test_waiting_input_context_is_retained_until_terminal_cleanup() -> None:
    clock = MutableClock()
    runtime = RecordingRuntime()
    facade = service(
        runtime,
        StubInterpreter([intent(missing=["platforms"]), intent(), intent()]),
        max_contexts=2,
        max_requests=3,
        ttl_seconds=100,
        monotonic=clock,
    )
    waiting = await facade.submit(
        "conversation-waiting",
        "tenant-a",
        ConversationMessageV1(
            message="写内容", request_id="request-waiting", user_id="user-a"
        ),
    )
    await runtime.wait()
    base_view = RunViewV1(
        run_id=waiting.run_id,
        request_id="request-waiting",
        status=RunStatus.QUEUED,
        strategy=None,
        usage=UsageV1(
            input_tokens=0,
            output_tokens=0,
            cost_microunits=0,
            estimated=False,
        ),
    )
    await runtime.listeners[0](
        base_view.model_copy(update={"status": RunStatus.WAITING_INPUT})
    )
    clock.value = 101
    for suffix in ("b", "c"):
        await facade.submit(
            f"conversation-{suffix}",
            "tenant-a",
            ConversationMessageV1(
                message="写内容", request_id=f"request-{suffix}", user_id="user-a"
            ),
        )
    await runtime.wait()

    assert ("tenant-a", "conversation-waiting") in facade._contexts
    await runtime.listeners[0](
        base_view.model_copy(update={"status": RunStatus.CANCELLED})
    )
    assert waiting.run_id not in facade._active_runs


@pytest.mark.asyncio
async def test_new_conversation_is_rejected_when_all_contexts_wait_for_input() -> None:
    runtime = RecordingRuntime()
    facade = service(
        runtime,
        StubInterpreter([intent(missing=["platforms"])]),
        max_contexts=1,
    )
    waiting = await facade.submit(
        "conversation-waiting",
        "tenant-a",
        ConversationMessageV1(
            message="写内容", request_id="request-waiting", user_id="user-a"
        ),
    )
    await runtime.wait()
    await runtime.listeners[0](
        RunViewV1(
            run_id=waiting.run_id,
            request_id="request-waiting",
            status=RunStatus.WAITING_INPUT,
            strategy=StrategyMode.MULTI_AGENT,
            usage=UsageV1(
                input_tokens=0,
                output_tokens=0,
                cost_microunits=0,
                estimated=False,
            ),
        )
    )

    with pytest.raises(HarnessError, match="等待输入的会话已达到容量上限"):
        await facade.submit(
            "conversation-new",
            "tenant-a",
            ConversationMessageV1(
                message="另一个任务", request_id="request-new", user_id="user-a"
            ),
        )

    assert set(facade._contexts) == {("tenant-a", "conversation-waiting")}
    assert len(runtime.requests) == 1


@pytest.mark.asyncio
async def test_terminal_callback_cannot_race_ahead_of_active_run_registration() -> None:
    class ImmediateTerminalRuntime(RecordingRuntime):
        async def create_and_schedule_pipeline(
            self, request, prepare, *, on_queued=None
        ):
            del prepare
            self.requests.append(request)
            queued = RunViewV1(
                run_id="run-immediate",
                request_id=request.request_id,
                status=RunStatus.QUEUED,
                strategy=StrategyMode.MULTI_AGENT,
                usage=UsageV1(
                    input_tokens=0,
                    output_tokens=0,
                    cost_microunits=0,
                    estimated=False,
                ),
            )
            assert on_queued is not None
            await on_queued(queued)
            terminal = queued.model_copy(
                update={"status": RunStatus.SUCCEEDED, "output": {"content": "完成"}}
            )
            for listener in self.listeners:
                await listener(terminal)
            return queued

    runtime = ImmediateTerminalRuntime()
    facade = service(runtime, StubInterpreter([intent()]))

    view = await facade.submit(
        "conversation-fast",
        "tenant-a",
        ConversationMessageV1(
            message="写内容", request_id="request-fast", user_id="user-a"
        ),
    )

    assert view.status == "queued"
    assert facade._active_runs == {}
    context = facade._contexts[("tenant-a", "conversation-fast")].context
    assert context.turns[-1] == ConversationTurn("assistant", "完成")


@pytest.mark.asyncio
async def test_multi_platform_intent_maps_semantic_task_fields() -> None:
    runtime = RecordingRuntime()
    parsed = intent().model_copy(
        update={
            "goal": "为效率工具新品生成内容",
            "channels": ["xiaohongshu", "wechat_official_account"],
            "audience": "职场人",
            "style": "专业",
            "requirements": IntentRequirementsV1(
                topic="效率工具新品",
                platforms=("xiaohongshu", "wechat_official_account"),
                audience="职场人",
            ),
        }
    )
    facade = service(runtime, StubInterpreter([parsed]))

    await facade.submit(
        "conversation-1",
        "tenant-1",
        ConversationMessageV1(
            message="生成内容", request_id="request-semantic", user_id="user-1"
        ),
    )
    await runtime.wait()
    submission = next(iter(facade.submissions._entries.values())).submission
    conditions = {
        item.condition_id: item.value for item in submission.task_spec.key_conditions
    }

    assert submission.request.requested_domains == frozenset(
        {OperationDomain.CONTENT, OperationDomain.CHANNEL}
    )
    assert submission.task_spec.domains == frozenset(
        {OperationDomain.CONTENT, OperationDomain.CHANNEL}
    )
    assert submission.task_spec.goals[0].description == "为效率工具新品生成内容"
    assert submission.task_spec.objects[0].kind is OperationObjectKind.CONTENT
    assert dict(conditions["platforms"].items)["platforms"] == (
        "xiaohongshu",
        "wechat_official_account",
    )
    assert dict(conditions["topic"].items)["topic"] == "效率工具新品"
    assert submission.task_spec.requires_user_input is False


@pytest.mark.asyncio
async def test_low_confidence_without_reported_fields_uses_generic_clarification() -> (
    None
):
    runtime = RecordingRuntime()
    parsed = intent().model_copy(update={"confidence": 0.4})
    facade = service(runtime, StubInterpreter([parsed]))

    await facade.submit(
        "conversation-low-confidence",
        "tenant-1",
        ConversationMessageV1(
            message="帮我运营一下", request_id="request-low", user_id="user-1"
        ),
    )
    await runtime.wait()
    event_name, payload = runtime.initial_events[0][1]
    submission = next(iter(facade.submissions._entries.values())).submission

    assert event_name == "clarification_required"
    assert payload == {
        "question": "请再具体说明本次运营目标、对象和期望交付物。",
        "fields": [],
    }
    assert submission.task_spec.missing_critical_condition_ids == ("goal",)
    assert submission.task_spec.requires_user_input is True


@pytest.mark.asyncio
async def test_unexpressible_brand_requirements_are_not_fabricated() -> None:
    runtime = RecordingRuntime()
    parsed = intent().model_copy(
        update={
            "domain": "brand",
            "task_type": "brand_operation_plan",
            "goal": "制定品牌运营计划",
            "channels": [],
            "confidence": 0.9,
            "requirements": IntentRequirementsV1(goal="制定品牌运营计划"),
        }
    )
    facade = service(runtime, StubInterpreter([parsed]))

    await facade.submit(
        "conversation-brand",
        "tenant-1",
        ConversationMessageV1(
            message="制定品牌运营计划", request_id="request-brand", user_id="user-1"
        ),
    )
    await runtime.wait()
    submission = next(iter(facade.submissions._entries.values())).submission
    conditions = {
        item.condition_id: item.value for item in submission.task_spec.key_conditions
    }

    assert submission.task_spec.requires_user_input is True
    assert submission.task_spec.missing_critical_condition_ids == (
        "brand",
        "planning-window",
        "product",
    )
    assert conditions["brand"] is None
    assert conditions["planning-window"] is None
    assert runtime.initial_events[0][1][1]["question"].startswith("请补充品牌")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_id", "requirements"),
    [
        (
            "industry_digest",
            IntentRequirementsV1(topic="AI 行业", time_window="最近一周"),
        ),
        (
            "multi_platform_content",
            IntentRequirementsV1(topic="新品", platforms=("xiaohongshu",)),
        ),
        (
            "brand_operation_plan",
            IntentRequirementsV1(
                brand="示例品牌",
                product="示例产品",
                goal="提升认知",
                planning_window="下季度",
            ),
        ),
        (
            "ip_operation_plan",
            IntentRequirementsV1(
                ip="专家 IP",
                audience="职场人",
                incubation_window="三个月",
            ),
        ),
        (
            "campaign_plan",
            IntentRequirementsV1(
                campaign_goal="拉新",
                audience="新用户",
                campaign_window="国庆期间",
            ),
        ),
        (
            "content_calendar",
            IntentRequirementsV1(topic_scope="效率工具", calendar_window="九月"),
        ),
        (
            "growth_experiment",
            IntentRequirementsV1(
                growth_goal="提高转化",
                funnel_stage="注册",
                experiment_window="两周",
            ),
        ),
        (
            "operation_review",
            IntentRequirementsV1(review_window="八月", metric_definition="有效注册率"),
        ),
    ],
)
async def test_all_scenarios_build_executable_submission(
    scenario_id: str, requirements: IntentRequirementsV1
) -> None:
    runtime = RecordingRuntime()
    parsed = intent().model_copy(
        update={
            "task_type": scenario_id,
            "goal": "完成运营任务",
            "requirements": requirements,
        }
    )
    facade = service(runtime, StubInterpreter([parsed]))

    await facade.submit(
        f"conversation-{scenario_id}",
        "tenant-1",
        ConversationMessageV1(
            message="完成运营任务",
            request_id=f"request-{scenario_id}",
            user_id="user-1",
        ),
    )
    await runtime.wait()
    submission = next(iter(facade.submissions._entries.values())).submission
    manifest = facade.resolver.registry.get(
        submission.scenario_id, submission.manifest_semantic_version
    )

    assert submission.task_spec.requires_user_input is False
    context = select_profiles_for_task(
        submission.task_spec, submission.profile_candidates
    )
    plan = compile_scenario_plan(
        manifest, submission.task_spec, context, submission.plan_id
    )
    assert plan.task_id == submission.task_spec.task_id
    if scenario_id == "multi_platform_content":
        assert tuple(step.step_id for step in plan.steps) == ("xiaohongshu",)
        assert tuple(
            item.requirement_id for item in submission.request.requested_deliverables
        ) == ("platform-content-xiaohongshu",)
