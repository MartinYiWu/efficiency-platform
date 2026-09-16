"""意图解释器、统一模型运行时和有界上下文的离线测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.contracts.intent import IntentEnvelopeV1
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelDemand,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from efficiency_platform_agent.routing.model_router import ModelPolicyRouter


def _result(
    payload: dict[str, Any] | str,
    *,
    input_tokens: int = 7,
    output_tokens: int = 3,
) -> ProviderResult:
    content = (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    )
    return ProviderResult(
        "intent/1",
        ProviderMessage("assistant", content),
        ProviderUsage(input_tokens, output_tokens, 0, 0, 0),
    )


def _candidate(tier: ModelTier = ModelTier.BALANCED) -> ModelCandidate:
    return ModelCandidate(
        f"fake-{tier.value}",
        "fake-provider",
        tier.value,
        tier,
        True,
        False,
        64_000,
        True,
        False,
    )


def _execution(
    result: ProviderResult,
    *,
    tier: ModelTier = ModelTier.BALANCED,
    degraded: bool = False,
) -> ModelExecutionResult:
    candidate = _candidate(tier)
    return ModelExecutionResult(
        result,
        (
            ModelSelection(
                candidate,
                1,
                ModelTier.BALANCED if degraded else None,
                "degraded_after_retryable_error" if degraded else "requested_tier",
            ),
        ),
        UsageSnapshot(
            result.usage.input_tokens,
            result.usage.output_tokens,
            result.usage.cost_microunits,
            False,
        ),
        degraded,
    )


def _budget(
    *,
    iterations: int = 4,
    input_tokens: int = 64_000,
    output_tokens: int = 8_000,
    cost_microunits: int = 1_000_000,
    timeout_ms: int = 15_000,
) -> RemainingBudget:
    return RemainingBudget(
        iterations,
        0,
        input_tokens,
        output_tokens,
        cost_microunits,
        timeout_ms,
    )


class _FakeRuntime:
    """按脚本返回统一模型执行结果，不进行网络调用。"""

    def __init__(self, script: list[ModelExecutionResult]) -> None:
        self.script = list(script)
        self.calls: list[tuple[ModelDemand, ProviderRequest, RemainingBudget]] = []

    async def complete(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
    ) -> ModelExecutionResult:
        self.calls.append((demand, request, remaining_budget))
        return self.script.pop(0)


class _DirectProvider:
    """用于证明意图解释器拒绝绕过统一运行时的旧接口。"""

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        return _result(_complete_intent())


def _complete_intent(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": "intent/1",
        "domain": "运营",
        "goal": "生成新品多平台文案",
        "task_type": "multi_platform_content",
        "channels": ["xiaohongshu", "wechat_official_account", "toutiao"],
        "audience": "关注效率工具的职场人",
        "style": "专业且亲切",
        "time_range": None,
        "needs_research": False,
        "needs_multi_agent": True,
        "missing_fields": [],
        "needs_clarification": False,
        "confidence": 0.96,
        "model_hint": "balanced",
        "requirements": {
            "contract_version": "intent.requirements/1",
            "topic": "新品效率工具",
            "platforms": ["xiaohongshu", "wechat_official_account", "toutiao"],
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_interpreter_uses_unified_runtime_and_structured_demand() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    runtime = _FakeRuntime([_execution(_result(_complete_intent()))])
    interpreter = IntentInterpreter(runtime)

    intent = await interpreter.interpret("为新品生成三平台文案", ConversationContext())

    assert intent.task_type == "multi_platform_content"
    assert len(runtime.calls) == 1
    demand, request, remaining = runtime.calls[0]
    assert demand.requires_structured_output is True
    assert demand.requires_tools is False
    assert demand.requested_tier is ModelTier.BALANCED
    assert remaining.iterations >= 1
    options = dict(request.options.items)
    assert options["response_format"] == JsonObject((("type", "json_object"),))


@pytest.mark.asyncio
async def test_interpreter_prompt_defines_general_chat_without_operation_fields() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    runtime = _FakeRuntime(
        [
            _execution(
                _result(
                    _complete_intent(
                        task_type="general_chat",
                        needs_research=False,
                        needs_multi_agent=False,
                        missing_fields=[],
                        needs_clarification=False,
                        requirements={"contract_version": "intent.requirements/1"},
                    )
                )
            )
        ]
    )

    intent = await IntentInterpreter(runtime).interpret("你是谁", ConversationContext())

    prompt = str(runtime.calls[0][1].messages[0].content)
    assert intent.task_type == "general_chat"
    assert "general_chat" in prompt
    assert "requirements 必须为空对象" in prompt
    assert "missing_fields 必须为空数组" in prompt
    assert "needs_clarification、needs_research、needs_multi_agent 均为 false" in prompt


@pytest.mark.asyncio
async def test_interpreter_prompt_routes_explicit_online_research_to_industry_digest() -> (
    None
):
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    runtime = _FakeRuntime(
        [_execution(_result(_complete_intent()))]
    )

    await IntentInterpreter(runtime).interpret("请搜索并核实最新动态", ConversationContext())

    prompt = str(runtime.calls[0][1].messages[0].content)
    assert "稳定知识" in prompt
    assert "general_chat + needs_research=false" in prompt
    assert "搜索、最新、核实、来源" in prompt
    assert "industry_digest" in prompt
    assert "最近7天（默认最新信息窗口）" in prompt
    assert "可见历史" in prompt


def test_interpreter_rejects_direct_model_provider() -> None:
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    with pytest.raises(TypeError, match="IntentModelRuntime"):
        IntentInterpreter(_DirectProvider())


def test_orchestration_package_exports_intent_runtime_contracts() -> None:
    from efficiency_platform_agent.orchestration import (
        IntentExecution,
        IntentInterpreter,
        IntentModelRuntime,
    )

    assert IntentExecution.__name__ == "IntentExecution"
    assert IntentInterpreter.__name__ == "IntentInterpreter"
    assert IntentModelRuntime.__name__ == "IntentModelRuntime"


@pytest.mark.asyncio
async def test_execute_aggregates_repair_usage_and_degraded_facts() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    runtime = _FakeRuntime(
        [
            _execution(_result("不是JSON", input_tokens=4, output_tokens=2)),
            _execution(
                _result(_complete_intent(), input_tokens=5, output_tokens=3),
                tier=ModelTier.FAST,
                degraded=True,
            ),
        ]
    )

    execution = await IntentInterpreter(runtime).execute(
        "生成新品文案", ConversationContext(), remaining_budget=_budget()
    )

    assert execution.intent.goal == "生成新品多平台文案"
    assert execution.repair_attempted is True
    assert execution.usage == UsageSnapshot(9, 5, 0, False)
    assert execution.degraded is True
    assert len(execution.attempts) == 2
    assert len(runtime.calls) == 2
    assert runtime.calls[1][0] is not runtime.calls[0][0]
    assert runtime.calls[1][0].estimated_input_tokens == sum(
        len(str(message.content)) for message in runtime.calls[1][1].messages
    )
    assert runtime.calls[1][2].iterations < runtime.calls[0][2].iterations
    assert "修复" in str(runtime.calls[1][1].messages[0].content)


@pytest.mark.asyncio
async def test_repair_demand_matches_the_exact_truncated_repair_request() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    runtime = _FakeRuntime(
        [
            _execution(_result("x" * 25_000)),
            _execution(_result(_complete_intent())),
        ]
    )

    await IntentInterpreter(runtime).execute(
        "生成新品文案", ConversationContext(), remaining_budget=_budget()
    )

    repair_demand, repair_request, _ = runtime.calls[1]
    assert len(str(repair_request.messages[1].content)) == 20_000
    assert repair_demand.demand_version == "intent-repair-model/1"
    assert repair_demand.estimated_input_tokens == sum(
        len(str(message.content)) for message in repair_request.messages
    )


@pytest.mark.asyncio
async def test_interpreter_rejects_after_one_failed_repair() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpretationError,
        IntentInterpreter,
    )

    runtime = _FakeRuntime(
        [_execution(_result("第一次无效")), _execution(_result("第二次仍无效"))]
    )

    with pytest.raises(IntentInterpretationError, match="INTENT_RESPONSE_INVALID"):
        await IntentInterpreter(runtime).interpret("生成文案", ConversationContext())
    assert len(runtime.calls) == 2


@pytest.mark.asyncio
async def test_context_is_bounded_and_only_exposes_visible_turns() -> None:
    from efficiency_platform_agent.conversation.context import (
        ConversationContext,
        ConversationTurn,
    )
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    context = ConversationContext(max_turns=2, max_characters=80)
    context.append(ConversationTurn("user", "应被淘汰的旧需求"))
    context.append(ConversationTurn("assistant", "可见的澄清问题"))
    context.append(ConversationTurn("user", "补充产品是智能日历"))
    with pytest.raises(TypeError):
        context.append(  # type: ignore[arg-type]
            {"role": "assistant", "content": "可见", "reasoning": "隐藏思维链"}
        )

    runtime = _FakeRuntime([_execution(_result(_complete_intent()))])
    await IntentInterpreter(runtime).interpret("继续", context)

    request_text = "\n".join(str(item.content) for item in runtime.calls[0][1].messages)
    assert "应被淘汰的旧需求" not in request_text
    assert "可见的澄清问题" in request_text
    assert "补充产品是智能日历" in request_text
    assert "隐藏思维链" not in request_text
    assert len(context.turns) == 2


def _sse_response(
    content: str, input_tokens: int, output_tokens: int
) -> httpx.Response:
    content_event = json.dumps(
        {"choices": [{"delta": {"content": content}}]}, ensure_ascii=False
    )
    finish_event = json.dumps(
        {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
            },
        },
        ensure_ascii=False,
    )
    return httpx.Response(
        200,
        text=f"data: {content_event}\ndata: {finish_event}\ndata: [DONE]\n",
    )


def _wire_runtime(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[ModelRuntime, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = DeepSeekStreamingProvider(
        client,
        "unused-fixed-model",
        api_key="synthetic",
        max_retries=0,
        logical_model_map={
            "balanced": "deepseek-balanced",
            "fast": "deepseek-fast",
        },
    )
    registry = ModelProviderRegistry()
    registry.register("deepseek", provider)
    candidates = tuple(
        ModelCandidate(
            tier.value,
            "deepseek",
            tier.value,
            tier,
            True,
            False,
            64_000,
            True,
            False,
        )
        for tier in (ModelTier.BALANCED, ModelTier.FAST)
    )
    return ModelRuntime(ModelPolicyRouter(candidates), registry), client


@pytest.mark.asyncio
async def test_deepseek_wire_parses_general_chat_without_operation_fields() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    payload = _complete_intent(
        domain="通用对话",
        goal="了解助手身份",
        task_type="general_chat",
        channels=[],
        audience=None,
        style=None,
        time_range=None,
        needs_research=False,
        needs_multi_agent=False,
        missing_fields=[],
        needs_clarification=False,
        model_hint=None,
        requirements={},
    )
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _sse_response(json.dumps(payload, ensure_ascii=False), 4, 2)

    runtime, client = _wire_runtime(handler)
    try:
        execution = await IntentInterpreter(runtime).execute(
            "你是谁", ConversationContext(), remaining_budget=_budget()
        )
    finally:
        await client.aclose()

    assert len(bodies) == 1
    prompt = bodies[0]["messages"][0]["content"]
    assert bodies[0]["messages"][0]["role"] == "system"
    assert "general_chat" in prompt
    assert execution.intent.task_type == "general_chat"
    assert execution.intent.requirements.model_dump(exclude_defaults=True) == {}
    assert execution.intent.missing_fields == []
    assert execution.intent.needs_clarification is False
    assert execution.intent.needs_research is False
    assert execution.intent.needs_multi_agent is False


@pytest.mark.asyncio
async def test_deepseek_wire_repairs_once_with_trusted_field_specification() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            return _sse_response("不是JSON", 2, 1)
        return _sse_response(json.dumps(_complete_intent(), ensure_ascii=False), 3, 2)

    runtime, client = _wire_runtime(handler)
    try:
        execution = await IntentInterpreter(runtime).execute(
            "生成新品文案", ConversationContext(), remaining_budget=_budget()
        )
    finally:
        await client.aclose()

    assert execution.repair_attempted is True
    assert execution.usage == UsageSnapshot(5, 3, 0, False)
    assert len(bodies) == 2
    assert all(body["response_format"] == {"type": "json_object"} for body in bodies)
    first_system = bodies[0]["messages"][0]["content"]
    repair_system = bodies[1]["messages"][0]["content"]
    for prompt in (first_system, repair_system):
        assert "contract_version" in prompt
        assert "intent/1" in prompt
        assert "confidence" in prompt
        assert "multi_platform_content" in prompt
        assert "intent.requirements/1" in prompt
        assert "brand" in prompt
        assert "product" in prompt
        assert "ip" in prompt
        assert "funnel_stage" in prompt
        assert "metric_definition" in prompt


@pytest.mark.asyncio
async def test_non_retryable_provider_error_does_not_trigger_format_repair() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpretationError,
        IntentInterpreter,
    )

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    runtime, client = _wire_runtime(handler)
    try:
        with pytest.raises(
            IntentInterpretationError, match="INTENT_PROVIDER_ERROR"
        ) as captured:
            await IntentInterpreter(runtime).execute(
                "生成文案", ConversationContext(), remaining_budget=_budget()
            )
    finally:
        await client.aclose()

    assert calls == 1
    assert captured.value.usage == UsageSnapshot()
    assert captured.value.degraded is False
    assert len(captured.value.attempts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["rate_limit", "timeout"])
async def test_model_runtime_degrades_and_returns_usage(failure: str) -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        models.append(body["model"])
        if len(models) == 1:
            if failure == "rate_limit":
                return httpx.Response(429)
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return _sse_response(json.dumps(_complete_intent(), ensure_ascii=False), 5, 2)

    runtime, client = _wire_runtime(handler)
    try:
        execution = await IntentInterpreter(runtime).execute(
            "生成文案", ConversationContext(), remaining_budget=_budget()
        )
    finally:
        await client.aclose()

    assert models == ["deepseek-balanced", "deepseek-fast"]
    assert execution.degraded is True
    assert execution.usage == UsageSnapshot(5, 2, 0, False)
    assert len(execution.attempts) == 2


_WIRE_SCENARIO_MATRIX = (
    ("industry_digest", {"topic": "AI Agent", "time_window": "最近30天"}),
    (
        "multi_platform_content",
        {"topic": "效率工具", "platforms": ["xiaohongshu", "wechat"]},
    ),
    (
        "brand_operation_plan",
        {
            "brand": "效率品牌",
            "product": "效率工作台",
            "goal": "提升认知",
            "planning_window": "Q4",
        },
    ),
    (
        "ip_operation_plan",
        {"ip": "效率教练", "audience": "职场新人", "incubation_window": "90天"},
    ),
    (
        "campaign_plan",
        {
            "campaign_goal": "获得1000条线索",
            "audience": "中小企业主",
            "campaign_window": "双十一",
        },
    ),
    (
        "content_calendar",
        {"topic_scope": "AI效率", "calendar_window": "2026年10月"},
    ),
    (
        "growth_experiment",
        {
            "growth_goal": "注册转化提升10%",
            "funnel_stage": "激活",
            "experiment_window": "4周",
        },
    ),
    (
        "operation_review",
        {"review_window": "2026年Q3", "metric_definition": "有效线索率"},
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("scenario_id", "requirements"), _WIRE_SCENARIO_MATRIX)
async def test_deepseek_wire_parses_controlled_fields_for_all_scenarios(
    scenario_id: str, requirements: dict[str, object]
) -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    payload = _complete_intent(
        task_type=scenario_id,
        requirements={
            "contract_version": "intent.requirements/1",
            **requirements,
        },
    )
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _sse_response(json.dumps(payload, ensure_ascii=False), 4, 2)

    runtime, client = _wire_runtime(handler)
    try:
        execution = await IntentInterpreter(runtime).execute(
            "解析完整需求", ConversationContext(), remaining_budget=_budget()
        )
    finally:
        await client.aclose()

    assert execution.intent.task_type == scenario_id
    parsed = execution.intent.requirements.model_dump(exclude={"contract_version"})
    for field_name, value in requirements.items():
        expected = tuple(value) if isinstance(value, list) else value
        assert parsed[field_name] == expected
    assert len(bodies) == 1


class _ConcurrentRuntime:
    """让两个调用同时进入 Runtime，以验证解释器不持有共享预算。"""

    def __init__(self) -> None:
        self.entered = 0
        self.ready = asyncio.Event()
        self.budgets: list[RemainingBudget] = []

    async def complete(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
    ) -> ModelExecutionResult:
        del demand, request
        self.budgets.append(remaining_budget)
        self.entered += 1
        if self.entered == 2:
            self.ready.set()
        await self.ready.wait()
        return _execution(_result(_complete_intent()))


@pytest.mark.asyncio
async def test_concurrent_interpretations_keep_run_scoped_budgets_isolated() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpreter,
    )

    runtime = _ConcurrentRuntime()
    interpreter = IntentInterpreter(runtime)
    budget_a = _budget(input_tokens=20_000)
    budget_b = _budget(input_tokens=30_000)

    await asyncio.gather(
        interpreter.execute("请求A", ConversationContext(), remaining_budget=budget_a),
        interpreter.execute("请求B", ConversationContext(), remaining_budget=budget_b),
    )

    assert {id(item) for item in runtime.budgets} == {id(budget_a), id(budget_b)}
    assert {item.input_tokens for item in runtime.budgets} == {20_000, 30_000}


@pytest.mark.asyncio
async def test_insufficient_run_budget_does_not_call_provider() -> None:
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpretationError,
        IntentInterpreter,
    )

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _sse_response(json.dumps(_complete_intent(), ensure_ascii=False), 1, 1)

    runtime, client = _wire_runtime(handler)
    try:
        with pytest.raises(IntentInterpretationError) as captured:
            await IntentInterpreter(runtime).execute(
                "生成文案",
                ConversationContext(),
                remaining_budget=_budget(iterations=0),
            )
    finally:
        await client.aclose()

    assert captured.value.code == "INTENT_BUDGET_EXHAUSTED"
    assert calls == 0


@pytest.mark.asyncio
async def test_repair_demand_uses_truncated_output_and_fails_before_second_provider() -> (
    None
):
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpretationError,
        IntentInterpreter,
    )

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _sse_response("x" * 25_000, 100, 10)

    runtime, client = _wire_runtime(handler)
    try:
        with pytest.raises(IntentInterpretationError) as captured:
            await IntentInterpreter(runtime).execute(
                "生成文案",
                ConversationContext(),
                remaining_budget=_budget(input_tokens=10_000),
            )
    finally:
        await client.aclose()

    assert captured.value.code == "INTENT_BUDGET_EXHAUSTED"
    assert captured.value.usage.input_tokens == 100
    assert calls == 1


class _FakeClock:
    """可控单调时钟，用于验证同一次解释共享绝对截止时间。"""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _TimeoutAfterFirstRuntime(_FakeRuntime):
    def __init__(self, clock: _FakeClock) -> None:
        super().__init__([_execution(_result("无效JSON"))])
        self.clock = clock

    async def complete(
        self,
        demand: ModelDemand,
        request: ProviderRequest,
        *,
        remaining_budget: RemainingBudget,
    ) -> ModelExecutionResult:
        result = await super().complete(
            demand, request, remaining_budget=remaining_budget
        )
        self.clock.now += 0.051
        return result


@pytest.mark.asyncio
async def test_repair_respects_original_absolute_timeout_and_skips_second_call() -> (
    None
):
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpretationError,
        IntentInterpreter,
    )

    clock = _FakeClock()
    runtime = _TimeoutAfterFirstRuntime(clock)

    with pytest.raises(IntentInterpretationError) as captured:
        await IntentInterpreter(runtime, timeout_ms=50, clock=clock).execute(
            "生成文案",
            ConversationContext(),
            remaining_budget=_budget(timeout_ms=1_000),
        )

    assert captured.value.code == "INTENT_BUDGET_EXHAUSTED"
    assert len(runtime.calls) == 1
    assert runtime.calls[0][2].timeout_ms == 50


@pytest.mark.asyncio
async def test_interpreter_rejects_late_valid_result_and_preserves_execution_facts() -> (
    None
):
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpretationError,
        IntentInterpreter,
    )

    clock = _FakeClock()

    class LateSuccessRuntime(_TimeoutAfterFirstRuntime):
        def __init__(self) -> None:
            _FakeRuntime.__init__(
                self,
                [
                    _execution(
                        _result(_complete_intent(), input_tokens=11, output_tokens=7)
                    )
                ],
            )
            self.clock = clock

    runtime = LateSuccessRuntime()

    with pytest.raises(IntentInterpretationError) as captured:
        await IntentInterpreter(runtime, timeout_ms=50, clock=clock).execute(
            "生成文案",
            ConversationContext(),
            remaining_budget=_budget(timeout_ms=1_000),
        )

    assert captured.value.code == "INTENT_BUDGET_EXHAUSTED"
    assert captured.value.usage == UsageSnapshot(11, 7, 0, False)
    assert len(captured.value.attempts) == 1


@pytest.mark.asyncio
async def test_real_model_runtime_repair_fallback_cannot_cross_absolute_deadline() -> (
    None
):
    from efficiency_platform_agent.conversation.context import ConversationContext
    from efficiency_platform_agent.orchestration.intent_interpreter import (
        IntentInterpretationError,
        IntentInterpreter,
    )

    models: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        models.append(body["model"])
        if len(models) == 1:
            return _sse_response("不是JSON", 2, 1)
        if len(models) == 2:
            await asyncio.sleep(1)
        return _sse_response(json.dumps(_complete_intent(), ensure_ascii=False), 3, 2)

    runtime, client = _wire_runtime(handler)  # type: ignore[arg-type]
    try:
        with pytest.raises(IntentInterpretationError) as captured:
            await IntentInterpreter(runtime, timeout_ms=120).execute(
                "生成文案",
                ConversationContext(),
                remaining_budget=_budget(timeout_ms=120),
            )
    finally:
        await client.aclose()

    assert captured.value.code == "INTENT_BUDGET_EXHAUSTED"
    assert captured.value.usage == UsageSnapshot(2, 1, 0, False)
    assert len(captured.value.attempts) == 2
    assert models == ["deepseek-balanced", "deepseek-balanced"]


def test_clarification_manager_asks_for_missing_product_information() -> None:
    from efficiency_platform_agent.conversation.clarification import (
        ClarificationManager,
    )

    intent = IntentEnvelopeV1(
        domain="运营",
        goal="生成新品文案",
        task_type="multi_platform_content",
        missing_fields=["product"],
        needs_clarification=True,
        confidence=0.88,
    )

    question = ClarificationManager().next_question(intent)

    assert question is not None
    assert "产品" in question


@pytest.mark.parametrize(
    "field_name",
    (
        "topic",
        "time-window",
        "platforms",
        "brand",
        "goal",
        "planning-window",
        "ip",
        "audience",
        "incubation-window",
        "campaign-goal",
        "campaign-window",
        "topic-scope",
        "calendar-window",
        "growth-goal",
        "funnel-stage",
        "experiment-window",
        "review-window",
        "metric-definition",
    ),
)
def test_clarification_manager_has_specific_question_for_each_manifest_field(
    field_name: str,
) -> None:
    from efficiency_platform_agent.conversation.clarification import (
        ClarificationManager,
    )

    intent = IntentEnvelopeV1(
        domain="运营",
        goal="完成运营任务",
        task_type="industry_digest",
        missing_fields=[field_name],
        needs_clarification=True,
        confidence=0.9,
    )

    question = ClarificationManager().next_question(intent)

    assert question != "请补充任务中缺少的关键信息，以便继续处理。"
