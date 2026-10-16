"""由 LLM 选择工具、由程序治理边界的有界 Research Agent 循环。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import ValidationError

from efficiency_platform_agent.contracts.research_tooling import (
    EvidencePackV1,
    ResearchReflectionV1,
    ResearchRequestV2,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import (
    ModelDemand,
    ModelExecutionResult,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    JsonValue,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderToolCall,
    RunContext,
    ToolRequest,
    ToolResult,
)
from efficiency_platform_agent.orchestration.intent_interpreter import (
    IntentModelRuntime,
)
from efficiency_platform_agent.orchestration.prompt_keys import PromptKeyResolver
from efficiency_platform_agent.prompts.contracts import PromptValue
from efficiency_platform_agent.prompts.runtime import PromptAssembler
from efficiency_platform_agent.tools.runtime.service import ToolRuntime


class ResearchToolLoopError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(f"{code}: {safe_message}")


class ResearchToolExecutor(Protocol):
    async def invoke(
        self,
        call: ProviderToolCall,
        request: ResearchRequestV2,
        allowed_tools: frozenset[str],
        budget: RemainingBudget,
    ) -> ToolResult: ...


class GovernedResearchToolExecutor:
    """把模型 Tool Call 接入现有唯一 ToolRuntime 和真实来源 Provider。"""

    def __init__(self, runtime: ToolRuntime) -> None:
        self._runtime = runtime

    async def invoke(
        self,
        call: ProviderToolCall,
        request: ResearchRequestV2,
        allowed_tools: frozenset[str],
        budget: RemainingBudget,
    ) -> ToolResult:
        result, _ = await self._runtime.invoke(
            ToolRequest(
                contract_version="2",
                tool_name=call.name,
                arguments=call.arguments,
                timeout_ms=max(1, budget.timeout_ms),
                approval_binding=None,
                idempotency_key=None,
                has_side_effects=False,
                max_output_bytes=2 * 1024 * 1024,
            ),
            RunContext(
                request.run_id,
                request.tenant_id,
                request.user_id,
                f"research-{request.request_id}",
            ),
            allowed_tools=allowed_tools,
            granted_permissions=frozenset({"research:read"}),
            remaining_budget=budget,
        )
        return result


@dataclass(frozen=True, slots=True)
class _Observation:
    call: ProviderToolCall
    result: ToolResult


@dataclass(frozen=True, slots=True)
class _ObservedSource:
    tool_call_id: str
    url: str
    title: str
    published_at: str | None


class ResearchToolLoop:
    """最多一轮补查；无真实来源时失败，不允许模型补造材料。"""

    def __init__(
        self,
        model_runtime: IntentModelRuntime,
        prompt_assembler: PromptAssembler,
        tool_executor: ResearchToolExecutor,
    ) -> None:
        if not callable(getattr(model_runtime, "complete", None)):
            raise TypeError("model_runtime 必须实现 complete")
        if not callable(getattr(prompt_assembler, "assemble", None)):
            raise TypeError("prompt_assembler 必须实现 assemble")
        if not callable(getattr(tool_executor, "invoke", None)):
            raise TypeError("tool_executor 必须实现 invoke")
        self._model_runtime = model_runtime
        self._prompt_assembler = prompt_assembler
        self._tool_executor = tool_executor

    async def execute(
        self,
        request: ResearchRequestV2,
        allowed_tools: frozenset[str],
        budget: ExecutionBudget,
    ) -> EvidencePackV1:
        if not isinstance(request, ResearchRequestV2):
            raise TypeError("request 必须为 ResearchRequestV2")
        if not allowed_tools:
            raise ResearchToolLoopError(
                "RESEARCH_TOOL_NOT_ALLOWED", "没有可用研究工具"
            )
        remaining = RemainingBudget(
            budget.max_iterations,
            budget.max_tool_calls,
            budget.max_input_tokens,
            budget.max_output_tokens,
            budget.max_cost_microunits,
            budget.timeout_ms,
        )
        if remaining.tool_calls <= 0:
            raise ResearchToolLoopError(
                "RESEARCH_BUDGET_EXHAUSTED", "研究工具预算不足"
            )

        planned, remaining = await self._model_call(
            request,
            "plan",
            {"allowed_tools": sorted(allowed_tools)},
            remaining,
            tools=allowed_tools,
        )
        calls = self._require_tool_calls(planned)
        observations, remaining = await self._invoke_calls(
            calls, request, allowed_tools, remaining, known_digests=set()
        )
        self._require_any_source(observations)

        pack, remaining = await self._synthesize(
            request, observations, remaining
        )
        reflected, remaining = await self._model_call(
            request,
            "reflect",
            {"evidence_pack": pack.model_dump(mode="json")},
            remaining,
            tools=allowed_tools,
        )
        if reflected.result.error is not None:
            raise ResearchToolLoopError(
                "RESEARCH_MODEL_UNAVAILABLE", "研究反思模型不可用"
            )
        message = reflected.result.message
        if message is None:
            raise ResearchToolLoopError(
                "RESEARCH_REFLECTION_INVALID", "研究反思结果为空"
            )
        if message.tool_calls:
            known = {_call_digest(item.call) for item in observations}
            supplement, remaining = await self._invoke_calls(
                message.tool_calls,
                request,
                allowed_tools,
                remaining,
                known_digests=known,
            )
            observations = (*observations, *supplement)
            self._require_any_source(observations)
            pack, _ = await self._synthesize(request, observations, remaining)
            return pack
        if not isinstance(message.content, str):
            raise ResearchToolLoopError(
                "RESEARCH_REFLECTION_INVALID", "研究反思结构无效"
            )
        try:
            reflection = ResearchReflectionV1.model_validate_json(message.content)
        except (TypeError, ValueError, ValidationError) as exc:
            raise ResearchToolLoopError(
                "RESEARCH_REFLECTION_INVALID", "研究反思结构无效"
            ) from exc
        if not reflection.complete:
            return pack.model_copy(
                update={
                    "partial": True,
                    "gaps": tuple(
                        dict.fromkeys((*pack.gaps, *reflection.problems))
                    ),
                }
            )
        return pack

    async def _synthesize(
        self,
        request: ResearchRequestV2,
        observations: tuple[_Observation, ...],
        remaining: RemainingBudget,
    ) -> tuple[EvidencePackV1, RemainingBudget]:
        execution, remaining = await self._model_call(
            request,
            "synthesize",
            {"tool_observations": [_observation_payload(item) for item in observations]},
            remaining,
        )
        pack = self._parse_pack(execution.result)
        observed = _observed_sources(observations)
        known = {(item.tool_call_id, item.url, item.title) for item in observed}
        for source in pack.sources:
            if (source.tool_call_id, source.url, source.title) not in known:
                raise ResearchToolLoopError(
                    "RESEARCH_SOURCE_CLOSURE_INVALID",
                    "证据包包含工具未返回的来源",
                )
        had_failures = any(item.result.error is not None for item in observations)
        if had_failures and not pack.partial:
            raise ResearchToolLoopError(
                "RESEARCH_PARTIAL_STATE_INVALID", "来源失败未在证据包中披露"
            )
        return pack, remaining

    async def _model_call(
        self,
        request: ResearchRequestV2,
        stage: str,
        context_payload: object,
        remaining: RemainingBudget,
        *,
        tools: frozenset[str] = frozenset(),
    ) -> tuple[ModelExecutionResult, RemainingBudget]:
        if remaining.iterations <= 0 or remaining.output_tokens <= 0:
            raise ResearchToolLoopError(
                "RESEARCH_BUDGET_EXHAUSTED", "研究模型预算不足"
            )
        assembled = await self._prompt_assembler.assemble(
            run_id=request.run_id,
            stage=f"research.{stage}",
            prompt_key=PromptKeyResolver.research(stage),
            variables={
                "user_request": PromptValue(request.topic, "user_input"),
                "context_payload": PromptValue(context_payload, "research_data"),
            },
        )
        messages = tuple(
            ProviderMessage(item.role, item.content) for item in assembled.messages
        )
        option_items: list[tuple[str, JsonValue]] = [
            ("temperature", assembled.model_policy.temperature),
            (
                "max_tokens",
                min(assembled.model_policy.max_output_tokens, remaining.output_tokens),
            ),
        ]
        if tools:
            option_items.append(("tools", _tool_definitions(tools)))
        else:
            option_items.extend(
                (
                    ("response_format", JsonObject((("type", "json_object"),))),
                    (
                        "json_schema",
                        _freeze(assembled.output_contract.json_schema),
                    ),
                )
            )
        provider_request = ProviderRequest(
            "research-agent/1",
            messages,
            JsonObject(tuple(option_items)),
            min(assembled.model_policy.read_timeout_ms, remaining.timeout_ms),
        )
        demand = ModelDemand(
            f"research-{stage}/1",
            ModelTier.STRONG,
            not tools,
            bool(tools),
            max(1, sum(len(item.content) for item in assembled.messages) // 4),
            min(assembled.model_policy.max_output_tokens, remaining.output_tokens),
        )
        if remaining.input_tokens < demand.estimated_input_tokens:
            raise ResearchToolLoopError(
                "RESEARCH_BUDGET_EXHAUSTED", "研究模型输入预算不足"
            )
        execution = await self._model_runtime.complete(
            demand,
            provider_request,
            remaining_budget=remaining,
        )
        if not isinstance(execution, ModelExecutionResult):
            raise ResearchToolLoopError(
                "RESEARCH_MODEL_UNAVAILABLE", "研究模型返回类型无效"
            )
        remaining = RemainingBudget(
            max(0, remaining.iterations - max(1, len(execution.attempts))),
            remaining.tool_calls,
            max(0, remaining.input_tokens - execution.usage.input_tokens),
            max(0, remaining.output_tokens - execution.usage.output_tokens),
            max(0, remaining.cost_microunits - execution.usage.cost_microunits),
            remaining.timeout_ms,
        )
        return execution, remaining

    async def _invoke_calls(
        self,
        calls: tuple[ProviderToolCall, ...],
        request: ResearchRequestV2,
        allowed_tools: frozenset[str],
        remaining: RemainingBudget,
        *,
        known_digests: set[str],
    ) -> tuple[tuple[_Observation, ...], RemainingBudget]:
        identifiers: set[str] = set()
        digests = set(known_digests)
        for call in calls:
            if call.name not in allowed_tools:
                raise ResearchToolLoopError(
                    "RESEARCH_TOOL_NOT_ALLOWED", "模型选择了未授权研究工具"
                )
            if call.tool_call_id in identifiers:
                raise ResearchToolLoopError(
                    "RESEARCH_TOOL_CALL_DUPLICATE", "研究 Tool Call 标识重复"
                )
            identifiers.add(call.tool_call_id)
            digest = _call_digest(call)
            if digest in digests:
                raise ResearchToolLoopError(
                    "RESEARCH_TOOL_CALL_DUPLICATE", "研究 Tool Call 内容重复"
                )
            digests.add(digest)
            _validate_urls(call.arguments)
        if len(calls) > remaining.tool_calls:
            raise ResearchToolLoopError(
                "RESEARCH_BUDGET_EXHAUSTED", "研究 Tool Call 超出预算"
            )

        observations: list[_Observation] = []
        for call in calls:
            result = await self._tool_executor.invoke(
                call, request, allowed_tools, remaining
            )
            if not isinstance(result, ToolResult):
                raise ResearchToolLoopError(
                    "RESEARCH_TOOL_RESULT_INVALID", "研究工具返回类型无效"
                )
            observations.append(_Observation(call, result))
            remaining = RemainingBudget(
                remaining.iterations,
                max(0, remaining.tool_calls - 1),
                remaining.input_tokens,
                remaining.output_tokens,
                remaining.cost_microunits,
                remaining.timeout_ms,
            )
        return tuple(observations), remaining

    @staticmethod
    def _require_tool_calls(execution: ModelExecutionResult) -> tuple[ProviderToolCall, ...]:
        if execution.result.error is not None:
            raise ResearchToolLoopError(
                "RESEARCH_MODEL_UNAVAILABLE", "研究规划模型不可用"
            )
        message = execution.result.message
        if message is None or not message.tool_calls:
            raise ResearchToolLoopError(
                "RESEARCH_TOOL_PLAN_INVALID", "研究规划未选择任何工具"
            )
        return message.tool_calls

    @staticmethod
    def _require_any_source(observations: tuple[_Observation, ...]) -> None:
        if not _observed_sources(observations):
            raise ResearchToolLoopError(
                "RESEARCH_NO_SOURCES", "真实来源没有返回可用材料"
            )

    @staticmethod
    def _parse_pack(result: ProviderResult) -> EvidencePackV1:
        if result.error is not None:
            raise ResearchToolLoopError(
                "RESEARCH_MODEL_UNAVAILABLE", "研究综合模型不可用"
            )
        if result.message is None or not isinstance(result.message.content, str):
            raise ResearchToolLoopError(
                "RESEARCH_EVIDENCE_PACK_INVALID", "证据包结构无效"
            )
        try:
            return EvidencePackV1.model_validate_json(result.message.content)
        except (TypeError, ValueError, ValidationError) as exc:
            raise ResearchToolLoopError(
                "RESEARCH_EVIDENCE_PACK_INVALID", "证据包结构无效"
            ) from exc


def _call_digest(call: ProviderToolCall) -> str:
    value = json.dumps(
        {"name": call.name, "arguments": _thaw(call.arguments)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_urls(arguments: JsonObject) -> None:
    def visit(value: object, key: str | None = None) -> None:
        if key == "url" and isinstance(value, str):
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ResearchToolLoopError(
                    "RESEARCH_TOOL_URL_INVALID", "研究工具 URL 非法"
                )
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(_thaw(arguments))


def _observed_sources(
    observations: tuple[_Observation, ...],
) -> tuple[_ObservedSource, ...]:
    sources: list[_ObservedSource] = []

    def visit(value: object, call_id: str) -> None:
        if isinstance(value, Mapping):
            url = value.get("url") or value.get("final_url")
            title = value.get("title")
            if isinstance(url, str) and isinstance(title, str):
                published = value.get("published_at")
                sources.append(
                    _ObservedSource(
                        call_id,
                        url,
                        title,
                        published if isinstance(published, str) else None,
                    )
                )
            for child in value.values():
                visit(child, call_id)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, call_id)

    for observation in observations:
        if observation.result.error is None and observation.result.output is not None:
            visit(_thaw(observation.result.output), observation.call.tool_call_id)
    return tuple(sources)


def _observation_payload(observation: _Observation) -> dict[str, object]:
    return {
        "tool_call_id": observation.call.tool_call_id,
        "tool_name": observation.call.name,
        "output": _thaw(observation.result.output),
        "error_code": (
            None
            if observation.result.error is None
            else observation.result.error.code
        ),
    }


def _tool_definitions(tools: frozenset[str]) -> JsonValue:
    return tuple(
        JsonObject(
            (
                ("type", "function"),
                (
                    "function",
                    JsonObject(
                        (
                            ("name", name),
                            ("description", "读取真实公开研究来源"),
                            (
                                "parameters",
                                JsonObject(
                                    (
                                        ("type", "object"),
                                        ("additionalProperties", True),
                                    )
                                ),
                            ),
                        )
                    ),
                ),
            )
        )
        for name in sorted(tools)
    )


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return JsonObject(
            tuple((str(key), _freeze(item)) for key, item in value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError("RESEARCH_JSON_INVALID")


def _thaw(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _thaw(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


__all__ = [
    "GovernedResearchToolExecutor",
    "ResearchToolExecutor",
    "ResearchToolLoop",
    "ResearchToolLoopError",
]
