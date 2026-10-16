"""数据库 Prompt 驱动的八场景模型执行器。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.contracts.deliverables import (
    ArticleDraftV1,
    BrandPlanV1,
    CampaignPlanV1,
    ContentCalendarV1,
    GrowthExperimentBacklogV1,
    IndustryDigestV1,
    IpPlanV1,
    OperationDeliverableV3,
    OperationReviewV1,
)
from efficiency_platform_agent.contracts.operation_intent import OperationScenario
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import ModelDemand, ModelTier
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    JsonValue,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.orchestration.prompt_keys import PromptKeyResolver
from efficiency_platform_agent.prompts.contracts import AssembledPrompt, PromptValue
from efficiency_platform_agent.prompts.runtime import PromptAssembler


class ScenarioModelExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class _Route:
    first_stage: str
    model: type[BaseModel]


_ROUTES: dict[OperationScenario, _Route] = {
    "industry_digest": _Route("compose", IndustryDigestV1),
    "multi_platform_content": _Route("draft", ArticleDraftV1),
    "brand_operation_plan": _Route("plan", BrandPlanV1),
    "ip_operation_plan": _Route("plan", IpPlanV1),
    "campaign_plan": _Route("plan", CampaignPlanV1),
    "content_calendar": _Route("plan", ContentCalendarV1),
    "growth_experiment": _Route("plan", GrowthExperimentBacklogV1),
    "operation_review": _Route("analyze", OperationReviewV1),
}


class ScenarioModelExecutor:
    """一次首稿、至多一次定向修复；不在 Python 中扩写正文。"""

    def __init__(
        self,
        model_runtime: ModelRuntime,
        prompt_assembler: PromptAssembler,
        *,
        budget: ExecutionBudget | None = None,
    ) -> None:
        self._model = model_runtime
        self._prompts = prompt_assembler
        self._budget = budget or ExecutionBudget(
            2, 0, 48_000, 24_000, 180_000, 1_000_000
        )

    async def generate(
        self,
        *,
        run_id: str,
        scenario: OperationScenario,
        stage: str,
        platform: str | None,
        user_request: str,
        input_artifact_ids: tuple[str, ...],
        evidence: object | None,
    ) -> OperationDeliverableV3:
        route = _ROUTES[scenario]
        if stage != route.first_stage:
            raise ScenarioModelExecutionError(
                "SCENARIO_STAGE_UNSUPPORTED", "场景执行阶段不受支持"
            )
        context = {
            "input_artifact_ids": list(input_artifact_ids),
            "evidence": _plain(evidence),
        }
        first = await self._assemble(
            run_id=run_id,
            scenario=scenario,
            stage=stage,
            platform=platform,
            user_request=user_request,
            context=context,
        )
        first_output = await self._complete(first, self._remaining())
        try:
            content = route.model.model_validate_json(first_output)
        except (ValidationError, ValueError) as error:
            previous = _json_or_text(first_output)
            repair = await self._assemble(
                run_id=run_id,
                scenario=scenario,
                stage="repair",
                platform=platform,
                user_request=user_request,
                context=context,
                previous_output=previous,
                validation_errors=_validation_errors(error),
            )
            repaired_output = await self._complete(repair, self._remaining(iterations=1))
            try:
                content = route.model.model_validate_json(repaired_output)
            except (ValidationError, ValueError) as final_error:
                raise ScenarioModelExecutionError(
                    "SCENARIO_OUTPUT_INVALID", "场景模型输出修复后仍不符合契约"
                ) from final_error
        title = _title(content)
        return OperationDeliverableV3(
            deliverable_id=f"{run_id}-{scenario}",
            title=title,
            content=content,  # type: ignore[arg-type]
        )

    async def _assemble(
        self,
        *,
        run_id: str,
        scenario: OperationScenario,
        stage: str,
        platform: str | None,
        user_request: str,
        context: object,
        previous_output: object | None = None,
        validation_errors: object | None = None,
    ) -> AssembledPrompt:
        values = {
            "user_request": PromptValue(user_request, "user_input"),
            "context_payload": PromptValue(context, "research_data"),
        }
        if stage == "repair":
            values.update(
                {
                    "previous_output": PromptValue(previous_output, "artifact"),
                    "validation_errors": PromptValue(
                        validation_errors, "system_context"
                    ),
                }
            )
        prompt_key = PromptKeyResolver.scenario(
            scenario, stage, platform=_prompt_platform(platform)
        )
        return await self._prompts.assemble(
            run_id=run_id,
            stage=f"scenario.{scenario}.{stage}.{platform or 'default'}",
            prompt_key=prompt_key,
            variables=values,
        )

    async def _complete(
        self, prompt: AssembledPrompt, remaining: RemainingBudget
    ) -> str:
        schema = _freeze(prompt.output_contract.json_schema)
        max_tokens = min(prompt.model_policy.max_output_tokens, remaining.output_tokens)
        request = ProviderRequest(
            "scenario-model/3",
            tuple(ProviderMessage(item.role, item.content) for item in prompt.messages),
            JsonObject(
                (
                    ("temperature", prompt.model_policy.temperature),
                    ("max_tokens", max_tokens),
                    (
                        "response_format",
                        JsonObject(
                            (
                                ("type", "json_schema"),
                                (
                                    "json_schema",
                                    JsonObject(
                                        (
                                            ("name", prompt.output_contract.contract_key),
                                            ("strict", True),
                                            ("schema", schema),
                                        )
                                    ),
                                ),
                            )
                        ),
                    ),
                )
            ),
            timeout_ms=min(prompt.model_policy.read_timeout_ms, remaining.timeout_ms),
        )
        demand = ModelDemand(
            "scenario-model/3",
            ModelTier.BALANCED,
            True,
            False,
            max(1, sum(len(item.content) for item in prompt.messages) // 4),
            max_tokens,
        )
        execution = await self._model.complete(
            demand, request, remaining_budget=remaining
        )
        result = execution.result
        if result.error is not None:
            raise ScenarioModelExecutionError(result.error.code, "场景模型调用失败")
        if result.message is None or not isinstance(result.message.content, str):
            raise ScenarioModelExecutionError(
                "SCENARIO_OUTPUT_EMPTY", "场景模型没有返回结构化内容"
            )
        return result.message.content

    def _remaining(self, *, iterations: int | None = None) -> RemainingBudget:
        return RemainingBudget(
            self._budget.max_iterations if iterations is None else iterations,
            self._budget.max_tool_calls,
            self._budget.max_input_tokens,
            self._budget.max_output_tokens,
            self._budget.max_cost_microunits,
            self._budget.timeout_ms,
        )


def _validation_errors(error: Exception) -> list[dict[str, object]]:
    if isinstance(error, ValidationError):
        return [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "type": item["type"],
                "message": item["msg"],
            }
            for item in error.errors(include_input=False, include_url=False)[:20]
        ]
    return [{"location": "root", "type": "json_invalid", "message": str(error)}]


def _json_or_text(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"invalid_output": value[:20_000]}


def _prompt_platform(platform: str | None) -> str | None:
    if platform is None:
        return None
    aliases: dict[str, str] = {
        "wechat_official_account": "wechat",
        "wechat": "wechat",
        "xiaohongshu": "xiaohongshu",
        "toutiao": "toutiao",
    }
    return aliases.get(platform, platform)


def _title(content: BaseModel) -> str:
    for name in ("title", "topic", "positioning", "objective", "business_goal"):
        value = getattr(content, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return "运营助手交付结果"


def _plain(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    raise TypeError("SCENARIO_CONTEXT_INVALID")


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return JsonObject(tuple((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError("SCENARIO_SCHEMA_INVALID")


__all__ = ["ScenarioModelExecutionError", "ScenarioModelExecutor"]
