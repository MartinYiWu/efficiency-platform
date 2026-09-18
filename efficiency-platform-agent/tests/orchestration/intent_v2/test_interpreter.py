"""I04 受控 Intent V2 解释器行为测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.context.builder import ContextBuilder
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    CapabilityCatalogSnapshot,
    CapabilityDescriptorV2,
    IntentContextV2,
    IntentFrameV2,
    IntentPatchV2,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelDemand,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
    RunContext,
    RunRequest,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.orchestration.intent_v2.interpreter import (
    ControlledIntentInterpreterV2,
    IntentInterpretationV2Error,
    IntentV2ContextBuildScope,
)
from efficiency_platform_agent.prompts.registry import (
    PromptRegistry,
    register_intent_v2_prompts,
)
from efficiency_platform_agent.prompts.runtime import PromptRuntime

VALID_PATCH = '{"base_revision":0,"dialog_act":"chat"}'
UNRESOLVED_PATCH = (
    '{"base_revision":0,"dialog_act":"chat","unresolved_references":["它指哪个任务"]}'
)


class SpyContextBuilder(ContextBuilder):
    def __init__(self) -> None:
        self.calls = 0

    def build(self, request, run_context, budget, allowed_tools):
        self.calls += 1
        return super().build(request, run_context, budget, allowed_tools)


class FakeScopeResolver:
    def __init__(self, *, mismatch_text: bool = False) -> None:
        self.calls = 0
        self.mismatch_text = mismatch_text

    async def resolve(self, text, context, lease):
        self.calls += 1
        del lease
        request_text = "被篡改" if self.mismatch_text else text
        return IntentV2ContextBuildScope(
            context_version=context.context_version,
            request=RunRequest("req-1", "tenant-1", "user-1", request_text),
            run_context=RunContext("run-1", "tenant-1", "user-1", "trace-1"),
            budget=ExecutionBudget(10, 0, 100_000, 20_000, 30_000, 1_000_000),
        )


class FakeBudgetResolver:
    def __init__(self, budgets: tuple[RemainingBudget, ...]) -> None:
        self.budgets = list(budgets)
        self.calls = 0

    async def remaining(self, lease):
        assert lease.lease_id == "lease-1"
        self.calls += 1
        if len(self.budgets) > 1:
            return self.budgets.pop(0)
        return self.budgets[0]


class FakeCancellation:
    def __init__(self, requested: bool) -> None:
        self.requested = requested

    def wait_requested(self) -> bool:
        return self.requested


class FakeModelRuntime:
    def __init__(self, outputs: tuple[str | ProviderError, ...]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[ModelDemand, ProviderRequest, RemainingBudget]] = []

    async def complete(self, demand, request, *, remaining_budget):
        self.calls.append((demand, request, remaining_budget))
        output = self.outputs.pop(0)
        usage = ProviderUsage(10, 5, 0, 0, 3)
        result = ProviderResult(
            "provider/1",
            None
            if isinstance(output, ProviderError)
            else ProviderMessage("assistant", output),
            usage,
            output if isinstance(output, ProviderError) else None,
        )
        candidate = ModelCandidate(
            "candidate-1",
            "fake",
            "fake-model",
            demand.requested_tier,
            True,
            False,
            100_000,
            True,
            False,
        )
        return ModelExecutionResult(
            result,
            (ModelSelection(candidate, 1, None, "selected"),),
            UsageSnapshot(10, 5, 3, False),
            False,
        )


def _budget(**changes: int) -> RemainingBudget:
    values = {
        "iterations": 6,
        "tool_calls": 0,
        "input_tokens": 100_000,
        "output_tokens": 20_000,
        "cost_microunits": 1_000_000,
        "timeout_ms": 30_000,
    }
    values.update(changes)
    return RemainingBudget(**values)


def _catalog() -> CapabilityCatalogSnapshot:
    return CapabilityCatalogSnapshot(
        catalog_version="catalog-1",
        capabilities=(
            CapabilityDescriptorV2(
                capability_id="general_chat",
                version="1",
                description="普通对话",
                parameter_schema_ref="schema://general-chat/1",
            ),
        ),
    )


def _interpreter(
    outputs: tuple[str | ProviderError, ...],
    *,
    budgets: tuple[RemainingBudget, ...] | None = None,
    cancellation: FakeCancellation | None = None,
    review_policy=None,
    scope_resolver: FakeScopeResolver | None = None,
):
    registry = PromptRegistry()
    register_intent_v2_prompts(registry)
    builder = SpyContextBuilder()
    runtime = FakeModelRuntime(outputs)
    budget_resolver = FakeBudgetResolver(budgets or (_budget(),))
    interpreter = ControlledIntentInterpreterV2(
        runtime,
        PromptRuntime(registry),
        builder,
        scope_resolver or FakeScopeResolver(),
        budget_resolver,
        cancellation_signal=cancellation,
        review_policy=review_policy,
    )
    return interpreter, runtime, builder, budget_resolver


async def _execute(interpreter: ControlledIntentInterpreterV2):
    return await interpreter.execute(
        "你叫什么名字？",
        IntentContextV2(
            current_message_id="m-1",
            visible_message_ids=("m-1",),
            context_version="ctx-1",
        ),
        None,
        _catalog(),
        BudgetLeaseReferenceV2(lease_id="lease-1", version=3),
    )


@pytest.mark.asyncio
async def test_first_valid_patch_uses_context_builder_and_one_model_call() -> None:
    interpreter, runtime, builder, budget_resolver = _interpreter((VALID_PATCH,))

    execution = await _execute(interpreter)

    assert execution.patch == IntentPatchV2(base_revision=0, dialog_act="chat")
    assert execution.provider_calls == 1
    assert execution.repair_attempted is False
    assert execution.review_attempted is False
    assert execution.catalog_version == "catalog-1"
    assert execution.context_version == "ctx-1"
    assert execution.lease_id == "lease-1"
    assert execution.lease_version == 3
    assert execution.usage == UsageSnapshot(10, 5, 3, False)
    assert builder.calls == 1
    assert budget_resolver.calls == 1
    demand, request, remaining = runtime.calls[0]
    assert demand.requires_tools is False
    assert remaining.tool_calls == 0
    assert "general_chat" in cast(str, request.messages[0].content)
    assert "你叫什么名字" not in cast(str, request.messages[0].content)
    assert "你叫什么名字" in cast(str, request.messages[1].content)
    assert '"current_message_id":"m-1"' in cast(
        str, request.messages[1].content
    )


def test_current_message_id_must_belong_to_unique_visible_scope() -> None:
    with pytest.raises(ValidationError):
        IntentContextV2(
            current_message_id="m-current",
            visible_message_ids=("m-old",),
            context_version="ctx-1",
        )
    with pytest.raises(ValidationError):
        IntentContextV2(
            current_message_id="m-1",
            visible_message_ids=("m-1", "m-1"),
            context_version="ctx-1",
        )


@pytest.mark.asyncio
async def test_invalid_schema_is_repaired_once_and_each_call_refreshes_budget() -> None:
    interpreter, runtime, _, budget_resolver = _interpreter(
        ("{}", VALID_PATCH),
        budgets=(_budget(), _budget(iterations=5, input_tokens=90_000)),
    )

    execution = await _execute(interpreter)

    assert execution.provider_calls == 2
    assert execution.repair_attempted is True
    assert len(runtime.calls) == 2
    assert budget_resolver.calls == 2
    assert runtime.calls[1][0].demand_version == "intent-v2-repair/1"
    assert "{}" in cast(str, runtime.calls[1][1].messages[1].content)
    assert runtime.calls[1][2].iterations < runtime.calls[0][2].iterations


@pytest.mark.asyncio
async def test_second_invalid_schema_fails_without_looping() -> None:
    interpreter, runtime, _, _ = _interpreter(("{}", "[]"))

    with pytest.raises(IntentInterpretationV2Error) as caught:
        await _execute(interpreter)

    assert caught.value.code == "INTENT_SCHEMA_INVALID"
    assert caught.value.provider_calls == 2
    assert len(runtime.calls) == 2


@pytest.mark.asyncio
async def test_provider_timeout_is_technical_failure_not_clarification() -> None:
    error = ProviderError("PROVIDER_TIMEOUT", "timeout", True, "模型调用超时")
    interpreter, runtime, _, _ = _interpreter((error,))

    with pytest.raises(IntentInterpretationV2Error) as caught:
        await _execute(interpreter)

    assert caught.value.code == "INTENT_PROVIDER_UNAVAILABLE"
    assert caught.value.provider_calls == 1
    assert caught.value.catalog_version == "catalog-1"
    assert caught.value.context_version == "ctx-1"
    assert caught.value.lease_id == "lease-1"
    assert caught.value.lease_version == 3
    assert len(runtime.calls) == 1


@pytest.mark.asyncio
async def test_budget_exhaustion_and_cancellation_do_not_call_model() -> None:
    low_budget, runtime, _, _ = _interpreter(
        (VALID_PATCH,), budgets=(_budget(input_tokens=1),)
    )
    with pytest.raises(IntentInterpretationV2Error) as budget_error:
        await _execute(low_budget)
    assert budget_error.value.code == "INTENT_BUDGET_EXHAUSTED"
    assert runtime.calls == []

    cancelled, runtime, _, _ = _interpreter(
        (VALID_PATCH,), cancellation=FakeCancellation(True)
    )
    with pytest.raises(IntentInterpretationV2Error) as cancel_error:
        await _execute(cancelled)
    assert cancel_error.value.code == "INTENT_CANCELLED"
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_positive_small_output_budget_is_used_as_request_cap() -> None:
    interpreter, runtime, _, _ = _interpreter(
        (VALID_PATCH,), budgets=(_budget(output_tokens=1_000),)
    )

    execution = await _execute(interpreter)

    assert execution.provider_calls == 1
    assert runtime.calls[0][0].max_output_tokens == 1_000


@pytest.mark.asyncio
async def test_deterministic_review_is_bounded_and_does_not_use_confidence() -> None:
    interpreter, runtime, _, _ = _interpreter(
        (UNRESOLVED_PATCH, VALID_PATCH),
        review_policy=lambda patch, previous: bool(patch.unresolved_references),
    )

    execution = await _execute(interpreter)

    assert execution.provider_calls == 2
    assert execution.review_attempted is True
    assert execution.patch.unresolved_references == ()
    assert runtime.calls[1][0].requested_tier is ModelTier.STRONG


@pytest.mark.asyncio
async def test_repair_plus_review_never_exceeds_three_model_calls() -> None:
    interpreter, runtime, _, _ = _interpreter(
        ("{}", UNRESOLVED_PATCH, VALID_PATCH),
        review_policy=lambda patch, previous: bool(patch.unresolved_references),
    )

    execution = await _execute(interpreter)

    assert execution.provider_calls == 3
    assert execution.repair_attempted is True
    assert execution.review_attempted is True
    assert len(runtime.calls) == 3


@pytest.mark.asyncio
async def test_revision_mismatch_repair_receives_trusted_expected_revision() -> None:
    interpreter, runtime, _, _ = _interpreter(
        (
            '{"base_revision":0,"dialog_act":"refine"}',
            '{"base_revision":2,"dialog_act":"refine"}',
        )
    )
    previous = IntentFrameV2(
        task_id="task-1",
        revision=2,
        message_id="m-0",
        anchor_time=datetime(2026, 9, 16, tzinfo=UTC),
        timezone="Asia/Shanghai",
        dialog_act="new_task",
    )

    execution = await interpreter.execute(
        "继续细化",
        IntentContextV2(
            current_message_id="m-1",
            visible_message_ids=("m-1",),
            context_version="ctx-1",
        ),
        previous,
        _catalog(),
        BudgetLeaseReferenceV2(lease_id="lease-1", version=3),
    )

    assert execution.patch.base_revision == 2
    assert execution.repair_attempted is True
    repair_system = cast(str, runtime.calls[1][1].messages[0].content)
    assert '"expected_current_revision":2' in repair_system


@pytest.mark.asyncio
async def test_invalid_review_keeps_last_valid_patch_and_records_non_application() -> None:
    interpreter, runtime, _, _ = _interpreter(
        (VALID_PATCH, "{}"),
        review_policy=lambda patch, previous: True,
    )

    execution = await _execute(interpreter)

    assert execution.patch == IntentPatchV2(base_revision=0, dialog_act="chat")
    assert execution.review_attempted is True
    assert execution.review_applied is False
    assert len(runtime.calls) == 2


@pytest.mark.asyncio
async def test_review_cannot_increase_unresolved_references() -> None:
    interpreter, _, _, _ = _interpreter(
        (VALID_PATCH, UNRESOLVED_PATCH),
        review_policy=lambda patch, previous: True,
    )

    execution = await _execute(interpreter)

    assert execution.patch.unresolved_references == ()
    assert execution.review_applied is False


@pytest.mark.asyncio
async def test_repair_payload_is_safely_cropped_to_twenty_thousand_characters() -> None:
    interpreter, runtime, _, _ = _interpreter(("x" * 25_000, VALID_PATCH))

    execution = await _execute(interpreter)

    assert execution.repair_attempted is True
    repair_payload = cast(str, runtime.calls[1][1].messages[1].content)
    assert len(repair_payload) == 20_000


@pytest.mark.asyncio
async def test_missing_prompt_registration_fails_before_model_call() -> None:
    builder = SpyContextBuilder()
    runtime = FakeModelRuntime((VALID_PATCH,))
    interpreter = ControlledIntentInterpreterV2(
        runtime,
        PromptRuntime(PromptRegistry()),
        builder,
        FakeScopeResolver(),
        FakeBudgetResolver((_budget(),)),
    )

    with pytest.raises(IntentInterpretationV2Error) as caught:
        await _execute(interpreter)

    assert caught.value.code == "INTENT_PROMPT_UNAVAILABLE"
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_context_scope_cannot_replace_current_user_text() -> None:
    resolver = FakeScopeResolver(mismatch_text=True)
    interpreter, runtime, builder, _ = _interpreter(
        (VALID_PATCH,), scope_resolver=resolver
    )

    with pytest.raises(IntentInterpretationV2Error) as caught:
        await _execute(interpreter)

    assert caught.value.code == "INTENT_CONTEXT_INVALID"
    assert runtime.calls == []
    assert builder.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "你叫什么名字？",
        "这篇文章介绍了‘收集昨天新闻’按钮怎么实现",
        "不要帮我研究新闻",
    ],
)
async def test_identity_button_description_and_negation_never_call_tools(
    text: str,
) -> None:
    interpreter, runtime, _, _ = _interpreter((VALID_PATCH,))

    result = await interpreter.interpret(
        text,
        IntentContextV2(
            current_message_id="m-1",
            visible_message_ids=("m-1",),
            context_version="ctx-1",
        ),
        None,
        _catalog(),
        BudgetLeaseReferenceV2(lease_id="lease-1", version=3),
    )

    assert result.dialog_act == "chat"
    assert len(runtime.calls) == 1
    assert runtime.calls[0][0].requires_tools is False
