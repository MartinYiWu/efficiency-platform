"""经统一 Context、Prompt、Model 与预算边界执行 Intent V2 解释。"""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from efficiency_platform_agent.context.builder import ContextBuilder
from efficiency_platform_agent.context.contracts import BuiltContext
from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    CapabilityCatalogSnapshot,
    IntentContextV2,
    IntentFrameV2,
    IntentPatchV2,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import (
    CancellationSignal,
    ModelDemand,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    JsonValue,
    ProviderMessage,
    ProviderRequest,
    RunContext,
    RunRequest,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.orchestration.intent_interpreter import (
    IntentModelRuntime,
)
from efficiency_platform_agent.prompts.contracts import RenderedPrompt
from efficiency_platform_agent.prompts.runtime import PromptRuntime

type ReviewPolicy = Callable[[IntentPatchV2, IntentFrameV2 | None], bool]

_MAX_MODEL_OUTPUT_CHARS = 20_000
_MAX_OUTPUT_TOKENS = 8_000


@dataclass(frozen=True, slots=True)
class IntentV2ContextBuildScope:
    """由可信 resolver 提供、交给唯一 ContextBuilder 的构建作用域。"""

    context_version: str
    request: RunRequest
    run_context: RunContext
    budget: ExecutionBudget

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context_version, str)
            or not self.context_version.strip()
        ):
            raise ValueError("context_version 必须是非空字符串")
        if not isinstance(self.request, RunRequest):
            raise TypeError("request 必须是 RunRequest")
        if not isinstance(self.run_context, RunContext):
            raise TypeError("run_context 必须是 RunContext")
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget 必须是 ExecutionBudget")


@runtime_checkable
class IntentV2ContextScopeResolver(Protocol):
    async def resolve(
        self,
        text: str,
        context: IntentContextV2,
        lease: BudgetLeaseReferenceV2,
    ) -> IntentV2ContextBuildScope: ...


@runtime_checkable
class IntentV2BudgetResolver(Protocol):
    async def remaining(
        self,
        lease: BudgetLeaseReferenceV2,
    ) -> RemainingBudget: ...


@dataclass(frozen=True, slots=True)
class IntentInterpretationV2Execution:
    """Patch 与可供 Run 审计、记账使用的非敏感执行事实。"""

    patch: IntentPatchV2
    usage: UsageSnapshot
    degraded: bool
    attempts: tuple[ModelSelection, ...]
    provider_calls: int
    repair_attempted: bool
    review_attempted: bool
    review_applied: bool
    prompt_versions: tuple[str, ...]
    catalog_version: str
    context_version: str
    lease_id: str
    lease_version: int


class IntentInterpretationV2Error(RuntimeError):
    """Intent V2 技术失败的稳定、安全错误。"""

    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        usage: UsageSnapshot | None = None,
        degraded: bool = False,
        attempts: tuple[ModelSelection, ...] = (),
        provider_calls: int = 0,
        prompt_versions: tuple[str, ...] = (),
        catalog_version: str | None = None,
        context_version: str | None = None,
        lease_id: str | None = None,
        lease_version: int | None = None,
    ) -> None:
        self.code = code
        self.safe_message = safe_message
        self.usage = usage or UsageSnapshot()
        self.degraded = degraded
        self.attempts = attempts
        self.provider_calls = provider_calls
        self.prompt_versions = prompt_versions
        self.catalog_version = catalog_version
        self.context_version = context_version
        self.lease_id = lease_id
        self.lease_version = lease_version
        super().__init__(f"{code}: {safe_message}")


@dataclass(slots=True)
class _InvocationState:
    executions: list[ModelExecutionResult] = field(default_factory=list)
    prompt_versions: list[str] = field(default_factory=list)
    provider_calls: int = 0
    local_remaining: RemainingBudget | None = None
    deadline: float | None = None
    catalog_version: str | None = None
    context_version: str | None = None
    lease_id: str | None = None
    lease_version: int | None = None


class _PatchInvalid(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ControlledIntentInterpreterV2:
    """让模型提出 Patch；确定性校验、预算和调用上限决定是否接纳。"""

    def __init__(
        self,
        model_runtime: IntentModelRuntime,
        prompt_runtime: PromptRuntime,
        context_builder: ContextBuilder,
        context_scope_resolver: IntentV2ContextScopeResolver,
        budget_resolver: IntentV2BudgetResolver,
        *,
        cancellation_signal: CancellationSignal | None = None,
        review_policy: ReviewPolicy | None = None,
        timeout_ms: int = 30_000,
        clock: Callable[[], float] | None = None,
    ) -> None:
        complete = getattr(model_runtime, "complete", None)
        if complete is None or not callable(complete):
            raise TypeError("model_runtime 必须实现 IntentModelRuntime")
        if not isinstance(prompt_runtime, PromptRuntime):
            raise TypeError("prompt_runtime 必须是 PromptRuntime")
        if not isinstance(context_builder, ContextBuilder):
            raise TypeError("context_builder 必须是唯一 ContextBuilder")
        if not isinstance(context_scope_resolver, IntentV2ContextScopeResolver):
            raise TypeError("context_scope_resolver 接口不完整")
        if not isinstance(budget_resolver, IntentV2BudgetResolver):
            raise TypeError("budget_resolver 接口不完整")
        if cancellation_signal is not None and not isinstance(
            cancellation_signal, CancellationSignal
        ):
            raise TypeError("cancellation_signal 接口不完整")
        if review_policy is not None and not callable(review_policy):
            raise TypeError("review_policy 必须可调用")
        if (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or timeout_ms <= 0
        ):
            raise ValueError("timeout_ms 必须是正整数")
        if clock is not None and not callable(clock):
            raise TypeError("clock 必须可调用")
        self.model_runtime = model_runtime
        self.prompt_runtime = prompt_runtime
        self.context_builder = context_builder
        self.context_scope_resolver = context_scope_resolver
        self.budget_resolver = budget_resolver
        self.cancellation_signal = cancellation_signal
        self.review_policy = review_policy or (lambda patch, previous: False)
        self.timeout_ms = timeout_ms
        self.clock = clock or time.monotonic
        self._field_schema = json.dumps(
            IntentPatchV2.model_json_schema(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    async def interpret(
        self,
        text: str,
        context: IntentContextV2,
        previous: IntentFrameV2 | None,
        catalog: CapabilityCatalogSnapshot,
        lease: BudgetLeaseReferenceV2,
    ) -> IntentPatchV2:
        return (await self.execute(text, context, previous, catalog, lease)).patch

    async def execute(
        self,
        text: str,
        context: IntentContextV2,
        previous: IntentFrameV2 | None,
        catalog: CapabilityCatalogSnapshot,
        lease: BudgetLeaseReferenceV2,
    ) -> IntentInterpretationV2Execution:
        self._validate_inputs(text, context, previous, catalog, lease)
        built = await self._build_context(text, context, lease)
        catalog_json = catalog.model_dump_json()
        context_manifest = self._context_manifest(context, built)
        user_payload = self._user_payload(context, built, previous)
        state = _InvocationState(
            catalog_version=catalog.catalog_version,
            context_version=context.context_version,
            lease_id=lease.lease_id,
            lease_version=lease.version,
        )

        interpret_prompt = self._render_prompt(
            state,
            "intent.v2.interpret",
            {
                "capability_catalog": catalog_json,
                "field_schema": self._field_schema,
                "context_manifest": context_manifest,
            },
        )
        first_content = await self._invoke(
            "intent-v2-interpret/1",
            ModelTier.BALANCED,
            interpret_prompt,
            user_payload,
            lease,
            state,
        )
        repair_attempted = False
        try:
            patch = self._parse_patch(first_content, previous)
        except _PatchInvalid as error:
            repair_attempted = True
            repair_prompt = self._render_prompt(
                state,
                "intent.v2.repair",
                {
                    "field_schema": self._field_schema,
                    "validation_error": _validation_error_payload(error, previous),
                },
            )
            repaired_content = await self._invoke(
                "intent-v2-repair/1",
                ModelTier.BALANCED,
                repair_prompt,
                _safe_model_output(first_content),
                lease,
                state,
            )
            try:
                patch = self._parse_patch(repaired_content, previous)
            except _PatchInvalid as final_error:
                raise self._error(
                    "INTENT_SCHEMA_INVALID",
                    "模型返回的 IntentPatchV2 结构无效",
                    state,
                ) from final_error

        review_attempted = False
        review_applied = False
        try:
            requires_review = self.review_policy(patch, previous)
        except Exception as error:
            raise self._error(
                "INTENT_REVIEW_UNAVAILABLE", "意图语义复核策略不可用", state
            ) from error
        if requires_review:
            review_attempted = True
            review_prompt = self._render_prompt(
                state,
                "intent.v2.review",
                {
                    "capability_catalog": catalog_json,
                    "field_schema": self._field_schema,
                },
            )
            review_payload = json.dumps(
                {
                    "untrusted_context": json.loads(user_payload),
                    "candidate_patch": patch.model_dump(mode="json"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            reviewed_content = await self._invoke(
                "intent-v2-review/1",
                ModelTier.STRONG,
                review_prompt,
                review_payload,
                lease,
                state,
            )
            try:
                reviewed = self._parse_patch(reviewed_content, previous)
            except _PatchInvalid:
                reviewed = None
            if reviewed is not None and len(reviewed.unresolved_references) <= len(
                patch.unresolved_references
            ):
                patch = reviewed
                review_applied = True

        usage, degraded, attempts = _execution_facts(state.executions)
        return IntentInterpretationV2Execution(
            patch=patch,
            usage=usage,
            degraded=degraded,
            attempts=attempts,
            provider_calls=state.provider_calls,
            repair_attempted=repair_attempted,
            review_attempted=review_attempted,
            review_applied=review_applied,
            prompt_versions=tuple(state.prompt_versions),
            catalog_version=catalog.catalog_version,
            context_version=context.context_version,
            lease_id=lease.lease_id,
            lease_version=lease.version,
        )

    @staticmethod
    def _validate_inputs(
        text: str,
        context: IntentContextV2,
        previous: IntentFrameV2 | None,
        catalog: CapabilityCatalogSnapshot,
        lease: BudgetLeaseReferenceV2,
    ) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text 必须是非空字符串")
        if not isinstance(context, IntentContextV2):
            raise TypeError("context 必须是 IntentContextV2")
        if previous is not None and not isinstance(previous, IntentFrameV2):
            raise TypeError("previous 必须是 IntentFrameV2 或 None")
        if not isinstance(catalog, CapabilityCatalogSnapshot):
            raise TypeError("catalog 必须是 CapabilityCatalogSnapshot")
        if not isinstance(lease, BudgetLeaseReferenceV2):
            raise TypeError("lease 必须是 BudgetLeaseReferenceV2")

    async def _build_context(
        self,
        text: str,
        context: IntentContextV2,
        lease: BudgetLeaseReferenceV2,
    ) -> BuiltContext:
        try:
            scope = await self.context_scope_resolver.resolve(text, context, lease)
        except Exception as error:
            raise IntentInterpretationV2Error(
                "INTENT_CONTEXT_INVALID",
                "意图上下文当前不可用",
                context_version=context.context_version,
                lease_id=lease.lease_id,
                lease_version=lease.version,
            ) from error
        if not isinstance(scope, IntentV2ContextBuildScope):
            raise IntentInterpretationV2Error(
                "INTENT_CONTEXT_INVALID",
                "意图上下文类型无效",
                context_version=context.context_version,
                lease_id=lease.lease_id,
                lease_version=lease.version,
            )
        if (
            scope.context_version != context.context_version
            or scope.request.input_text != text
        ):
            raise IntentInterpretationV2Error(
                "INTENT_CONTEXT_INVALID",
                "意图上下文版本或消息不匹配",
                context_version=context.context_version,
                lease_id=lease.lease_id,
                lease_version=lease.version,
            )
        try:
            return self.context_builder.build(
                scope.request,
                scope.run_context,
                scope.budget,
                frozenset(),
            )
        except (TypeError, ValueError) as error:
            raise IntentInterpretationV2Error(
                "INTENT_CONTEXT_INVALID",
                "意图上下文构建失败",
                context_version=context.context_version,
                lease_id=lease.lease_id,
                lease_version=lease.version,
            ) from error

    def _render_prompt(
        self,
        state: _InvocationState,
        prompt_id: str,
        variables: Mapping[str, JsonValue],
    ) -> RenderedPrompt:
        try:
            return self.prompt_runtime.render(prompt_id, variables)
        except (KeyError, TypeError, ValueError) as error:
            raise self._error(
                "INTENT_PROMPT_UNAVAILABLE", "意图 Prompt 当前不可用", state
            ) from error

    async def _invoke(
        self,
        demand_version: str,
        tier: ModelTier,
        rendered: RenderedPrompt,
        untrusted_payload: str,
        lease: BudgetLeaseReferenceV2,
        state: _InvocationState,
    ) -> str:
        if state.provider_calls >= 3:
            raise self._error(
                "INTENT_BUDGET_EXHAUSTED", "意图模型调用次数已达上限", state
            )
        await self._raise_if_cancelled(state)
        try:
            fresh = await self.budget_resolver.remaining(lease)
        except Exception as error:
            raise self._error(
                "INTENT_BUDGET_EXHAUSTED", "意图模型剩余预算不可用", state
            ) from error
        if not isinstance(fresh, RemainingBudget):
            raise self._error(
                "INTENT_BUDGET_EXHAUSTED", "意图模型剩余预算类型无效", state
            )
        available = (
            fresh
            if state.local_remaining is None
            else _minimum_remaining(fresh, state.local_remaining)
        )
        now = self.clock()
        if state.deadline is None:
            state.deadline = now + min(available.timeout_ms, self.timeout_ms) / 1000
        remaining_timeout = max(0, int((state.deadline - now) * 1000))
        available = replace(
            available,
            timeout_ms=min(available.timeout_ms, remaining_timeout, self.timeout_ms),
        )
        request = ProviderRequest(
            contract_version="intent-patch/2",
            messages=(
                *rendered.messages,
                ProviderMessage("user", untrusted_payload),
            ),
            options=_model_options(),
            timeout_ms=max(1, available.timeout_ms),
        )
        demand = ModelDemand(
            demand_version=demand_version,
            requested_tier=tier,
            requires_structured_output=True,
            requires_tools=False,
            estimated_input_tokens=_estimated_tokens(request),
            max_output_tokens=min(_MAX_OUTPUT_TOKENS, available.output_tokens),
        )
        self._ensure_budget(demand, available, state)
        state.provider_calls += 1
        state.prompt_versions.append(
            f"{rendered.prompt_id}@{rendered.semantic_version}"
        )
        try:
            execution = await self.model_runtime.complete(
                demand,
                request,
                remaining_budget=available,
            )
        except Exception as error:
            raise self._error(
                "INTENT_PROVIDER_UNAVAILABLE", "意图模型当前不可用", state
            ) from error
        if not isinstance(execution, ModelExecutionResult):
            raise self._error(
                "INTENT_PROVIDER_UNAVAILABLE", "意图模型返回类型无效", state
            )
        state.executions.append(execution)
        state.local_remaining = _remaining_after(execution, available)
        if self.clock() >= state.deadline:
            raise self._error(
                "INTENT_BUDGET_EXHAUSTED", "意图模型已超过绝对截止时间", state
            )
        provider_error = execution.result.error
        if provider_error is not None:
            code = (
                "INTENT_CANCELLED"
                if provider_error.code == "CANCELLED"
                else "INTENT_PROVIDER_UNAVAILABLE"
            )
            safe_message = (
                "意图解释已取消" if code == "INTENT_CANCELLED" else "意图模型当前不可用"
            )
            raise self._error(code, safe_message, state)
        provider_message = execution.result.message
        if (
            provider_message is None
            or provider_message.role != "assistant"
            or not isinstance(provider_message.content, str)
        ):
            return "null"
        return provider_message.content

    async def _raise_if_cancelled(self, state: _InvocationState) -> None:
        if self.cancellation_signal is None:
            return
        requested = self.cancellation_signal.wait_requested()
        if inspect.isawaitable(requested):
            requested = await requested
        if requested:
            raise self._error("INTENT_CANCELLED", "意图解释已取消", state)

    @staticmethod
    def _ensure_budget(
        demand: ModelDemand,
        budget: RemainingBudget,
        state: _InvocationState,
    ) -> None:
        if (
            budget.iterations <= 0
            or budget.input_tokens < demand.estimated_input_tokens
            or budget.output_tokens <= 0
            or budget.output_tokens < demand.max_output_tokens
            or budget.cost_microunits <= 0
            or budget.timeout_ms <= 0
        ):
            usage, degraded, attempts = _execution_facts(state.executions)
            raise IntentInterpretationV2Error(
                "INTENT_BUDGET_EXHAUSTED",
                "意图模型剩余预算不足",
                usage=usage,
                degraded=degraded,
                attempts=attempts,
                provider_calls=state.provider_calls,
                prompt_versions=tuple(state.prompt_versions),
                catalog_version=state.catalog_version,
                context_version=state.context_version,
                lease_id=state.lease_id,
                lease_version=state.lease_version,
            )

    @staticmethod
    def _parse_patch(
        content: str,
        previous: IntentFrameV2 | None,
    ) -> IntentPatchV2:
        try:
            patch = IntentPatchV2.model_validate_json(content)
        except (TypeError, ValueError, ValidationError) as error:
            raise _PatchInvalid("INTENT_SCHEMA_INVALID") from error
        expected_revision = (
            0
            if patch.dialog_act == "new_task" or previous is None
            else previous.revision
        )
        if patch.base_revision != expected_revision:
            raise _PatchInvalid("INTENT_BASE_REVISION_MISMATCH")
        return patch

    @staticmethod
    def _context_manifest(context: IntentContextV2, built: BuiltContext) -> str:
        return json.dumps(
            {
                "context_version": context.context_version,
                "current_message_id": context.current_message_id,
                "visible_message_ids": list(context.visible_message_ids),
                "sources": [
                    {
                        "source_id": source.source_id,
                        "trust_level": source.trust_level.value,
                    }
                    for source in built.sources
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _user_payload(
        context: IntentContextV2,
        built: BuiltContext,
        previous: IntentFrameV2 | None,
    ) -> str:
        return json.dumps(
            {
                "context_version": context.context_version,
                "current_message_id": context.current_message_id,
                "visible_message_ids": list(context.visible_message_ids),
                "sources": [
                    {
                        "source_id": source.source_id,
                        "trust_level": source.trust_level.value,
                        "content": _plain_json(source.content),
                    }
                    for source in built.sources
                ],
                "previous_intent_state": (
                    None if previous is None else previous.model_dump(mode="json")
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _error(
        code: str,
        safe_message: str,
        state: _InvocationState,
    ) -> IntentInterpretationV2Error:
        usage, degraded, attempts = _execution_facts(state.executions)
        return IntentInterpretationV2Error(
            code,
            safe_message,
            usage=usage,
            degraded=degraded,
            attempts=attempts,
            provider_calls=state.provider_calls,
            prompt_versions=tuple(state.prompt_versions),
            catalog_version=state.catalog_version,
            context_version=state.context_version,
            lease_id=state.lease_id,
            lease_version=state.lease_version,
        )


def _estimated_tokens(request: ProviderRequest) -> int:
    characters = sum(
        len(message.content) if isinstance(message.content, str) else 0
        for message in request.messages
    )
    return max(1, (characters + 3) // 4)


def _model_options() -> JsonObject:
    return JsonObject(
        (
            ("temperature", 0),
            ("response_format", JsonObject((("type", "json_object"),))),
        )
    )


def _remaining_after(
    execution: ModelExecutionResult,
    initial: RemainingBudget,
) -> RemainingBudget:
    return RemainingBudget(
        iterations=max(0, initial.iterations - max(1, len(execution.attempts))),
        tool_calls=initial.tool_calls,
        input_tokens=max(0, initial.input_tokens - execution.usage.input_tokens),
        output_tokens=max(0, initial.output_tokens - execution.usage.output_tokens),
        cost_microunits=max(
            0, initial.cost_microunits - execution.usage.cost_microunits
        ),
        timeout_ms=initial.timeout_ms,
    )


def _minimum_remaining(
    left: RemainingBudget,
    right: RemainingBudget,
) -> RemainingBudget:
    return RemainingBudget(
        iterations=min(left.iterations, right.iterations),
        tool_calls=min(left.tool_calls, right.tool_calls),
        input_tokens=min(left.input_tokens, right.input_tokens),
        output_tokens=min(left.output_tokens, right.output_tokens),
        cost_microunits=min(left.cost_microunits, right.cost_microunits),
        timeout_ms=min(left.timeout_ms, right.timeout_ms),
    )


def _execution_facts(
    executions: list[ModelExecutionResult],
) -> tuple[UsageSnapshot, bool, tuple[ModelSelection, ...]]:
    return (
        UsageSnapshot(
            input_tokens=sum(item.usage.input_tokens for item in executions),
            output_tokens=sum(item.usage.output_tokens for item in executions),
            cost_microunits=sum(item.usage.cost_microunits for item in executions),
            estimated=any(item.usage.estimated for item in executions),
        ),
        any(item.degraded for item in executions),
        tuple(attempt for item in executions for attempt in item.attempts),
    )


def _safe_model_output(content: str) -> str:
    cleaned = "".join(
        character
        for character in content
        if character in {"\n", "\r", "\t"} or ord(character) >= 32
    )
    return cleaned[:_MAX_MODEL_OUTPUT_CHARS]


def _validation_error_payload(
    error: _PatchInvalid,
    previous: IntentFrameV2 | None,
) -> str:
    return json.dumps(
        {
            "code": error.reason,
            "expected_current_revision": 0 if previous is None else previous.revision,
            "new_task_base_revision": 0,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _plain_json(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _plain_json(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


__all__ = [
    "ControlledIntentInterpreterV2",
    "IntentInterpretationV2Error",
    "IntentInterpretationV2Execution",
    "IntentV2BudgetResolver",
    "IntentV2ContextBuildScope",
    "IntentV2ContextScopeResolver",
]
