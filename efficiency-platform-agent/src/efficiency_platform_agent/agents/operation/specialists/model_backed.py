"""通过统一 PromptRuntime 和 ModelRuntime 执行运营专家。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidencePack,
    EvidenceQualityStatus,
)
from efficiency_platform_agent.agents.operation.delivery_kind import (
    deliverable_kind_for,
)
from efficiency_platform_agent.agents.operation.execution import OperationUsage
from efficiency_platform_agent.agents.operation.specialists.contracts import (
    SpecialistExecutionResult,
)
from efficiency_platform_agent.agents.operation.specialists.runtime import (
    encode_specialist_result,
)
from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.capabilities.quality.deliverable_assembler import (
    DeliverableAssembler,
)
from efficiency_platform_agent.capabilities.quality.deliverable_v2 import (
    DeliveryPresentationValidator,
    project_set_v2_to_v1,
    render_copy_text,
)
from efficiency_platform_agent.contracts.deliverables import (
    ActionPlanDeliverableV2,
    CitationV1,
    CitationV2,
    DeliverableSetV2,
    DeliverableV1,
    DeliverySummaryV2,
    DiagnosisDeliverableV2,
    PlatformContentDeliverableV2,
    RankedDigestDeliverableV2,
    RetrospectiveDeliverableV2,
    WarningV2,
    has_complete_wechat_hotspot_fields,
)
from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.model import ModelDemand, ModelTier
from efficiency_platform_agent.core.multi_agent import BudgetUsage
from efficiency_platform_agent.core.run import (
    ExtensionDescriptor,
    JsonObject,
    JsonValue,
    ProviderMessage,
    ProviderRequest,
    RunResult,
    SupervisorTask,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot

_EMPTY_USAGE = UsageSnapshot()
_REFERENCED_CONTENT_OUTPUT_TOKEN_CAP = 7_500
logger = logging.getLogger(__name__)
stage_logger = logging.getLogger("efficiency_platform_agent.execution")
from efficiency_platform_agent.prompts.runtime import PromptRuntime

_V3_ROUTE_BY_AGENT = {
    "operation.research.insight": ("industry_digest", "compose"),
    "operation.channel.content": ("multi_platform_content", "draft"),
    "operation.brand.strategy": ("brand_operation_plan", "plan"),
    "operation.ip.strategy": ("ip_operation_plan", "plan"),
    "operation.campaign.plan": ("campaign_plan", "plan"),
    "operation.content.create": ("content_calendar", "plan"),
    "operation.user_growth.plan": ("growth_experiment", "plan"),
    "operation.analytics.review": ("operation_review", "analyze"),
}

_V2_MODELS: dict[
    str,
    type[
        RankedDigestDeliverableV2
        | PlatformContentDeliverableV2
        | ActionPlanDeliverableV2
        | DiagnosisDeliverableV2
        | RetrospectiveDeliverableV2
    ],
] = {
    "ranked_digest": RankedDigestDeliverableV2,
    "platform_content": PlatformContentDeliverableV2,
    "action_plan": ActionPlanDeliverableV2,
    "diagnosis": DiagnosisDeliverableV2,
    "retrospective": RetrospectiveDeliverableV2,
}
_V2_DRAFTS: dict[str, type[BaseModel]] = {
    kind: create_model(
        f"_ModelDraft{model.__name__}",
        __base__=model,
        copy_text=(Literal[""], Field(...)),
        citations=(list[CitationV2], Field(..., max_length=0)),
        warnings=(list[WarningV2], Field(..., max_length=0)),
    )
    for kind, model in _V2_MODELS.items()
}


class _WechatSupplement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    background_and_impact: list[str] = Field(min_length=1, max_length=5)
    content_strategy: list[str] = Field(min_length=1, max_length=5)
    action_guidance: list[str] = Field(min_length=1, max_length=5)


class _WechatHotspotRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact: str = Field(min_length=1, max_length=1_200)
    impact: str = Field(min_length=1, max_length=1_200)
    operation_observation: str = Field(min_length=1, max_length=1_200)


class _WechatStructuredRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    introduction: str = Field(min_length=1, max_length=600)
    hotspots: list[_WechatHotspotRewrite] = Field(min_length=1, max_length=10)
    closing: str = Field(min_length=1, max_length=600)


def freeze(value: Any) -> JsonValue:
    """将受校验对象转换为不可变 JSON，不允许任意运行时实例。"""
    if isinstance(value, dict):
        return JsonObject(
            tuple((str(key), freeze(item)) for key, item in value.items())
        )
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("值必须是 JSON 基础值")


def plain(value: JsonValue) -> Any:
    """还原不可变 JSON 以执行严格 Schema 校验。"""
    if isinstance(value, JsonObject):
        return {key: plain(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


def _message_text(message: ProviderMessage) -> str:
    if not isinstance(message.content, str):
        raise TypeError("OPERATION_MODEL_RESPONSE_NOT_TEXT")
    return message.content


def _validation_summary(error: ValidationError) -> str:
    """只向修复调用传递字段位置和稳定错误，不回显模型正文。"""
    summaries: list[str] = []
    for item in error.errors(include_input=False, include_url=False)[:8]:
        location = ".".join(str(value) for value in item.get("loc", ())) or "root"
        message = str(item.get("msg", "validation failed"))
        summaries.append(f"{location}: {message[:160]}")
    return "; ".join(summaries) or "validation failed"


def _wechat_body_metrics(output: str) -> tuple[int | None, bool]:
    """记录重写质量信号，不把模型正文写入日志。"""
    try:
        payload = json.loads(output)
        content = payload.get("content") if isinstance(payload, dict) else None
        body = content.get("body_markdown") if isinstance(content, dict) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, False
    if not isinstance(body, str):
        return None, False
    return (
        len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", body)),
        has_complete_wechat_hotspot_fields(body),
    )


def _wechat_hotspot_titles(raw: dict[str, Any], count: int) -> list[str]:
    titles: list[str] = []
    for index, source in enumerate(raw.get("input_deliverables", ())):
        item = source.get("item", source) if isinstance(source, dict) else source
        title = item.get("title") if isinstance(item, dict) else None
        normalized = " ".join(str(title or "").split()).strip("# ")
        titles.append(normalized or f"热点 {index + 1}")
        if len(titles) == count:
            return titles
    return [*titles, *(f"热点 {index + 1}" for index in range(len(titles), count))]


def _merge_wechat_structured_rewrite(
    raw: dict[str, Any],
    initial_candidate: dict[str, Any],
    rewrite: _WechatStructuredRewrite,
    hotspot_count: int,
) -> tuple[str, int]:
    if len(rewrite.hotspots) != hotspot_count:
        raise ValueError("WECHAT_STRUCTURED_HOTSPOT_COUNT_INVALID")
    candidate_content = initial_candidate["content"]
    assert isinstance(candidate_content, dict)
    title = str(initial_candidate.get("title", "公众号行业周更")).strip()
    headings = _wechat_hotspot_titles(raw, hotspot_count)
    hotspots = "\n\n".join(
        "\n\n".join(
            (
                f"## {heading}",
                "**事实**\n" + section.fact.strip(),
                "**影响**\n" + section.impact.strip(),
                "**运营观察**\n" + section.operation_observation.strip(),
            )
        )
        for heading, section in zip(headings, rewrite.hotspots, strict=True)
    )
    candidate_content["body_markdown"] = "\n\n".join(
        (
            f"# {title}",
            rewrite.introduction.strip(),
            hotspots,
            "## 收束",
            rewrite.closing.strip(),
        )
    )
    merged_body = candidate_content["body_markdown"]
    assert isinstance(merged_body, str)
    chinese_count = len(
        re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", merged_body)
    )
    return json.dumps(initial_candidate, ensure_ascii=False), chinese_count


class ModelBackedOperationSpecialist:
    """保留 S1 注册定义，通过模型端口返回 S3/S4 权威结果。"""

    def __init__(
        self,
        spec: AgentSpec,
        prompts: PromptRuntime,
        model: ModelRuntime,
        usage: OperationUsage | None = None,
        evidence_pack: EvidencePack | None = None,
        extra_warnings: tuple[str, ...] = (),
        capability_usage: UsageSnapshot = _EMPTY_USAGE,
        deliverable_contract_version: str = "deliverable/1",
        scenario_executor: Any | None = None,
    ) -> None:
        if deliverable_contract_version not in {
            "deliverable/1",
            "deliverable/2",
            "deliverable/3",
        }:
            raise ValueError("DELIVERABLE_VERSION_UNSUPPORTED")
        if deliverable_contract_version == "deliverable/3" and scenario_executor is None:
            raise ValueError("SCENARIO_EXECUTOR_REQUIRED")
        self.deliverable_contract_version = deliverable_contract_version
        self.spec = spec
        self.prompts = prompts
        self.model = model
        self.usage = usage
        self.evidence_pack = evidence_pack
        self.extra_warnings = extra_warnings
        self.capability_usage = capability_usage
        self.scenario_executor = scenario_executor
        self.descriptor = ExtensionDescriptor(
            spec.agent_id,
            spec.semantic_version,
            spec.input_schema_version,
            spec.output_schema_version,
            spec.permissions,
            spec.budget,
            spec.termination_conditions,
            spec.checkpoint_version,
        )

    async def run(self, task: SupervisorTask) -> RunResult:
        """按当前平台独立生成，严格拒绝未知字段和伪造引用。"""
        raw = plain(task.input_data)
        expected = {
            "platform",
            "tenant_id",
            "goal",
            "task_id",
            "plan_id",
            "deliverable_id",
            "citations",
            "input_deliverables",
            "profile_reference_ids",
            "research",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("SPECIALIST_INPUT_INVALID")
        if task.target_agent != self.spec.agent_id:
            raise ValueError("SPECIALIST_PERMISSION_DENIED")
        if self.deliverable_contract_version == "deliverable/3":
            return await self._run_v3(task, raw)
        kind = deliverable_kind_for(
            self.spec.agent_id, raw["platform"], bool(raw["research"])
        )
        is_v2 = self.deliverable_contract_version == "deliverable/2"
        citations_v2 = self._citations_v2(raw["citations"]) if is_v2 else []
        if is_v2:
            raw["citations"] = [
                citation.model_dump(mode="json") for citation in citations_v2
            ]
        variables = {"capability": self.spec.agent_id}
        if is_v2:
            variables["deliverable_kind"] = kind
        rendered = self.prompts.render(
            f"operation.deliverable.generation/{2 if is_v2 else 1}", variables
        )
        content = json.dumps(raw, ensure_ascii=False)
        budget = task.budget
        requested_output_tokens = (
            min(budget.max_output_tokens, _REFERENCED_CONTENT_OUTPUT_TOKEN_CAP)
            if raw["input_deliverables"]
            else budget.max_output_tokens
        )
        schema_model = _V2_DRAFTS[kind] if is_v2 else DeliverableV1
        schema = freeze(schema_model.model_json_schema())
        schema_instruction = json.dumps(
            {
                "authority_fields": {
                    "contract_version": self.deliverable_contract_version,
                    "deliverable_id": raw["deliverable_id"],
                    "platform": raw["platform"],
                    "deliverable_kind": kind,
                },
                "output_schema": plain(schema),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request = ProviderRequest(
            "operation-model/1",
            (
                *rendered.messages,
                ProviderMessage(
                    "system",
                    "以下 authority_fields 必须逐字输出，output_schema 是唯一允许的输出结构："
                    + schema_instruction,
                ),
                ProviderMessage("user", content),
            ),
            JsonObject(
                (
                    (
                        "response_format",
                        JsonObject(
                            (
                                ("type", "json_schema"),
                                (
                                    "json_schema",
                                    JsonObject(
                                        (
                                            (
                                                "name",
                                                f"operation_{kind}"
                                                if is_v2
                                                else "operation_deliverable",
                                            ),
                                            ("strict", True),
                                            ("schema", schema),
                                        )
                                    ),
                                ),
                            )
                        ),
                    ),
                    ("max_tokens", requested_output_tokens),
                )
            ),
            budget.timeout_ms,
        )
        remaining = RemainingBudget(
            budget.max_iterations,
            budget.max_tool_calls,
            budget.max_input_tokens,
            budget.max_output_tokens,
            budget.max_cost_microunits,
            budget.timeout_ms,
        )
        demand = ModelDemand(
            "model-demand/1",
            ModelTier.BALANCED,
            True,
            False,
            max(
                1,
                (
                    len(content)
                    + rendered.rendered_chars
                    + len(schema_instruction)
                    + 3
                )
                // 4,
            ),
            requested_output_tokens,
        )
        started = time.monotonic()
        execution = await self.model.complete(
            demand,
            request,
            remaining_budget=remaining,
        )
        executions = [execution]
        if self.usage is not None:
            self.usage.record(execution)
        if execution.result.error or execution.result.message is None:
            raise ValueError("OPERATION_MODEL_FAILED")
        output = _message_text(execution.result.message)
        try:
            item = self._validate_deliverable(
                output, schema_model, raw, kind, citations_v2
            )
        except ValidationError as validation_error:
            logger.warning(
                "event=operation_deliverable_validation_failed platform=%s attempt=1 errors=%s",
                raw["platform"],
                _validation_summary(validation_error),
            )
            retry_budget = replace(
                self._retry_budget(remaining, execution),
                timeout_ms=max(
                    0, remaining.timeout_ms - int((time.monotonic() - started) * 1000)
                ),
            )
            stage_logger.info(
                "event=operation_schema_repair_budget platform=%s "
                "iterations=%s input_tokens=%s output_tokens=%s "
                "cost_microunits=%s timeout_ms=%s",
                raw["platform"],
                retry_budget.iterations,
                retry_budget.input_tokens,
                retry_budget.output_tokens,
                retry_budget.cost_microunits,
                retry_budget.timeout_ms,
            )
            if (
                retry_budget.iterations < 1
                or retry_budget.output_tokens < 1
                or retry_budget.input_tokens < 1
                or (remaining.cost_microunits > 0 and retry_budget.cost_microunits < 1)
                or retry_budget.timeout_ms < 1
            ):
                raise
            retry_max_tokens = min(requested_output_tokens, retry_budget.output_tokens)
            validation_summary = _validation_summary(validation_error)
            retry_schema = schema
            initial_candidate: dict[str, Any] | None = None
            initial_body = ""
            hotspot_count = max(1, len(raw.get("input_deliverables", [])))
            wechat_presentation_failure = (
                raw["platform"] == "wechat_official_account"
                and validation_summary
                in {
                    "root: Value error, WECHAT_BODY_CHINESE_LENGTH_INVALID",
                    "root: Value error, WECHAT_HOTSPOT_STRUCTURE_INVALID",
                }
            )
            if (
                wechat_presentation_failure
            ):
                try:
                    candidate = json.loads(str(output))
                    content_candidate = candidate.get("content")
                    if isinstance(candidate, dict) and isinstance(
                        content_candidate, dict
                    ) and isinstance(content_candidate.get("body_markdown"), str):
                        initial_candidate = candidate
                        initial_body = content_candidate["body_markdown"]
                except (TypeError, ValueError, json.JSONDecodeError):
                    initial_candidate = None
                    initial_body = ""
            structured_wechat_repair = (
                initial_candidate is not None
                and not has_complete_wechat_hotspot_fields(initial_body)
            )
            length_only_repair = (
                initial_candidate is not None
                and validation_summary
                == "root: Value error, WECHAT_BODY_CHINESE_LENGTH_INVALID"
                and has_complete_wechat_hotspot_fields(initial_body)
            )
            if structured_wechat_repair:
                retry_schema_value = _WechatStructuredRewrite.model_json_schema()
                introduction_schema = retry_schema_value["properties"]["introduction"]
                closing_schema = retry_schema_value["properties"]["closing"]
                introduction_schema["minLength"] = 240
                introduction_schema["maxLength"] = 360
                closing_schema["minLength"] = 240
                closing_schema["maxLength"] = 360
                hotspot_schema = retry_schema_value["$defs"]["_WechatHotspotRewrite"]
                hotspot_fields = hotspot_schema["properties"]
                per_field_min = max(
                    180,
                    (3_150 - 240 - 240 + hotspot_count * 40)
                    // (hotspot_count * 3),
                )
                per_field_max = max(per_field_min, min(1_000, per_field_min + 120))
                for field_name in ("fact", "impact", "operation_observation"):
                    hotspot_fields[field_name]["minLength"] = per_field_min
                    hotspot_fields[field_name]["maxLength"] = per_field_max
                hotspots_schema = retry_schema_value["properties"]["hotspots"]
                hotspots_schema["minItems"] = hotspot_count
                hotspots_schema["maxItems"] = hotspot_count
                retry_schema = freeze(retry_schema_value)
                stage_logger.info(
                    "event=operation_wechat_structured_rewrite_requested "
                    "hotspot_count=%s field_min=%s field_max=%s",
                    hotspot_count,
                    per_field_min,
                    per_field_max,
                )
            elif length_only_repair:
                chinese_count = len(
                    re.findall(
                        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
                        initial_body,
                    )
                )
                supplement_min = max(150, 3_100 - chinese_count)
                supplement_max = max(supplement_min + 150, 3_950 - chinese_count)
                paragraphs_per_field = min(
                    5, max(1, (supplement_min + 3 * 120 - 1) // (3 * 120))
                )
                retry_schema_value = _WechatSupplement.model_json_schema()
                paragraph_count = 3 * paragraphs_per_field
                paragraph_min = max(
                    70, (supplement_min + paragraph_count - 1) // paragraph_count
                )
                paragraph_max = max(
                    paragraph_min, min(240, supplement_max // paragraph_count)
                )
                for field_name in (
                    "background_and_impact",
                    "content_strategy",
                    "action_guidance",
                ):
                    field_schema = retry_schema_value["properties"][field_name]
                    field_schema["minItems"] = paragraphs_per_field
                    field_schema["maxItems"] = paragraphs_per_field
                    field_schema["items"]["minLength"] = paragraph_min
                    field_schema["items"]["maxLength"] = paragraph_max
                retry_schema = freeze(retry_schema_value)
                stage_logger.info(
                    "event=operation_wechat_supplement_requested "
                    "initial_chinese_count=%s supplement_target_min=%s "
                    "supplement_target_max=%s paragraphs_per_field=%s "
                    "paragraph_min=%s paragraph_max=%s",
                    chinese_count,
                    supplement_min,
                    supplement_max,
                    paragraphs_per_field,
                    paragraph_min,
                    paragraph_max,
                )
            retry_options = JsonObject(
                (
                    (
                        "response_format",
                        JsonObject(
                            (
                                ("type", "json_schema"),
                                (
                                    "json_schema",
                                    JsonObject(
                                        (
                                            (
                                                "name",
                                                (
                                                    "wechat_structured_rewrite"
                                                    if structured_wechat_repair
                                                    else "wechat_supplement"
                                                    if length_only_repair
                                                    else f"operation_{kind}_repair"
                                                ),
                                            ),
                                            ("strict", True),
                                            ("schema", retry_schema),
                                        )
                                    ),
                                ),
                            )
                        ),
                    ),
                    ("max_tokens", retry_max_tokens),
                )
            )
            hotspot_paragraphs = max(
                2,
                2_900 // (hotspot_count * 180),
            )
            target_length = "3300 至 3800"
            quality_instruction = (
                f"公众号正文必须扩写到 {target_length} 个中文字符：导语固定写 3 个自然段、每段 100 至 130 字；"
                f"本轮共有 {hotspot_count} 个热点，每个热点固定写 {hotspot_paragraphs} 个自然段、"
                "每段 170 至 190 个中文字符；每个热点必须以 ## 标题开始，并按 **事实**、**影响**、"
                "**运营观察** 的顺序分别给出非空段落；前四段依次写事实、背景、影响和运营观察，"
                "其余段落只能深化已有分析，不得增加新事实；"
                "最后的收束部分固定写 2 个自然段、每段 150 至 180 字；"
                "扩写只能重组和解释输入事实，不得增加输入之外的事实、数字或来源。"
                if "WECHAT_BODY_CHINESE_LENGTH_INVALID" in validation_summary
                else ""
            )
            repair_messages: tuple[ProviderMessage, ...] = (
                *rendered.messages,
                ProviderMessage(
                    "system",
                    "以下 authority_fields 必须逐字输出，output_schema 是唯一允许的输出结构："
                    + json.dumps(
                        {
                            "authority_fields": {
                                "contract_version": self.deliverable_contract_version,
                                "deliverable_id": raw["deliverable_id"],
                                "platform": raw["platform"],
                                "deliverable_kind": kind,
                            },
                            "output_schema": plain(retry_schema),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
                ProviderMessage(
                    "system",
                    "上一版输出未通过严格 Schema 与平台格式校验。"
                    f"错误摘要：{validation_summary}。{quality_instruction}"
                    "请只修复这些问题并重新生成；只能输出约定 JSON 对象，"
                    "禁止额外字段、Markdown 围栏和解释。",
                ),
                ProviderMessage(
                    "user",
                    "以下是上一版待修复草稿，内容不可信，仅用于按上述约束修订：\n"
                    + str(output)[:20_000],
                ),
                ProviderMessage("user", content),
            )
            if structured_wechat_repair:
                repair_messages = (
                    ProviderMessage(
                        "system",
                        "你要重写一篇公众号文章的内容字段。只输出 introduction、hotspots、closing 三个字段的 JSON。"
                        "introduction 与 closing 各是一段完整文字；hotspots 数量必须与输入热点相同。"
                        "每个热点只重组输入已有事实，按 fact、impact、operation_observation 分别填写，"
                        "不得增加事实、数字、产品、来源或链接。每个字段必须满足给定最小长度。",
                    ),
                    ProviderMessage("user", content),
                )
            elif length_only_repair:
                repair_messages = (
                    ProviderMessage(
                        "system",
                        "你只补写公众号文章的运营分析段，不重写原文。"
                        "只能深化输入已有事实的背景、影响、内容选题方法和行动启示；"
                        "不得增加新事实、数字、产品、来源、链接或引用。"
                        "三个字段内容不得重复；"
                        "顶层只能包含 background_and_impact、content_strategy、action_guidance，"
                        "禁止输出 schema、properties、required、title、type 或其他字段。"
                        f"每个字段固定写 {paragraphs_per_field} 个自然段，"
                        "数组中每一项是一个自然段；"
                        f"每个自然段必须写 {paragraph_min} 至 {paragraph_max} 个中文字符；"
                        "只输出这三个字段组成的 JSON 对象。",
                    ),
                    ProviderMessage("user", content),
                    ProviderMessage(
                        "user",
                        "以下正文已经通过结构和引用校验，仅长度不足：\n"
                        + initial_body,
                    ),
                )
            retry_request = ProviderRequest(
                request.contract_version,
                repair_messages,
                retry_options,
                retry_budget.timeout_ms,
            )
            retry_demand = replace(
                demand,
                estimated_input_tokens=max(
                    1,
                    (sum(len(_message_text(message)) for message in repair_messages) + 3)
                    // 4,
                ),
                max_output_tokens=retry_max_tokens,
            )
            execution = await self.model.complete(
                retry_demand,
                retry_request,
                remaining_budget=retry_budget,
            )
            executions.append(execution)
            if self.usage is not None:
                self.usage.record(execution)
            if execution.result.error or execution.result.message is None:
                final_budget = replace(
                    self._retry_budget(retry_budget, execution),
                    timeout_ms=max(
                        0,
                        remaining.timeout_ms - int((time.monotonic() - started) * 1000),
                    ),
                )
                if (
                    execution.result.error is None
                    or execution.result.error.code != "PROVIDER_RESPONSE_TRUNCATED"
                    or final_budget.iterations < 1
                    or final_budget.output_tokens < 1
                    or final_budget.input_tokens < 1
                    or (
                        remaining.cost_microunits > 0
                        and final_budget.cost_microunits < 1
                    )
                    or final_budget.timeout_ms < 1
                ):
                    raise ValueError("OPERATION_MODEL_FAILED")
                # 唯一修复的响应被截断时，只重传相同修复消息，不再生成修复 Prompt。
                final_max_tokens = min(
                    requested_output_tokens, final_budget.output_tokens
                )
                final_request = replace(
                    retry_request,
                    timeout_ms=final_budget.timeout_ms,
                    options=JsonObject(
                        tuple(
                            (key, final_max_tokens if key == "max_tokens" else value)
                            for key, value in retry_request.options.items
                        )
                    ),
                )
                execution = await self.model.complete(
                    replace(retry_demand, max_output_tokens=final_max_tokens),
                    final_request,
                    remaining_budget=final_budget,
                )
                executions.append(execution)
                if self.usage is not None:
                    self.usage.record(execution)
                if execution.result.error or execution.result.message is None:
                    raise ValueError("OPERATION_MODEL_FAILED")
            try:
                repaired_output = _message_text(execution.result.message)
                if structured_wechat_repair:
                    rewrite = _WechatStructuredRewrite.model_validate_json(
                        repaired_output, strict=True
                    )
                    assert initial_candidate is not None
                    repaired_output, rewritten_chinese_count = (
                        _merge_wechat_structured_rewrite(
                            raw,
                            initial_candidate,
                            rewrite,
                            hotspot_count,
                        )
                    )
                    stage_logger.info(
                        "event=operation_wechat_structured_rewrite_merged "
                        "hotspot_count=%s chinese_count=%s",
                        hotspot_count,
                        rewritten_chinese_count,
                    )
                elif length_only_repair:
                    supplement_payload = json.loads(repaired_output)
                    if isinstance(supplement_payload, dict):
                        allowed_supplement_fields = (
                            "background_and_impact",
                            "content_strategy",
                            "action_guidance",
                        )
                        unexpected_fields = sorted(
                            str(key)
                            for key in supplement_payload
                            if key not in allowed_supplement_fields
                        )
                        if unexpected_fields:
                            stage_logger.warning(
                                "event=operation_wechat_supplement_fields_dropped fields=%s",
                                ",".join(unexpected_fields),
                            )
                        supplement_payload = {
                            field_name: (
                                supplement_payload[field_name][
                                    :paragraphs_per_field
                                ]
                                if isinstance(supplement_payload[field_name], list)
                                else supplement_payload[field_name]
                            )
                            for field_name in allowed_supplement_fields
                            if field_name in supplement_payload
                        }
                    supplement = _WechatSupplement.model_validate(
                        supplement_payload, strict=True
                    )
                    if any(
                        len(value) != paragraphs_per_field
                        for value in (
                            supplement.background_and_impact,
                            supplement.content_strategy,
                            supplement.action_guidance,
                        )
                    ):
                        raise ValueError("WECHAT_SUPPLEMENT_PARAGRAPH_COUNT_INVALID")
                    assert initial_candidate is not None
                    candidate_content = initial_candidate["content"]
                    assert isinstance(candidate_content, dict)
                    candidate_content["body_markdown"] = (
                        initial_body.rstrip()
                        + "\n\n## 运营背景与影响\n\n"
                        + "\n\n".join(
                            value.strip() for value in supplement.background_and_impact
                        )
                        + "\n\n## 内容选题方法\n\n"
                        + "\n\n".join(
                            value.strip() for value in supplement.content_strategy
                        )
                        + "\n\n## 行动启示\n\n"
                        + "\n\n".join(
                            value.strip() for value in supplement.action_guidance
                        )
                    )
                    merged_chinese_count = len(
                        re.findall(
                            r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
                            candidate_content["body_markdown"],
                        )
                    )
                    stage_logger.info(
                        "event=operation_wechat_supplement_merged "
                        "initial_chinese_count=%s merged_chinese_count=%s",
                        chinese_count,
                        merged_chinese_count,
                    )
                    repaired_output = json.dumps(initial_candidate, ensure_ascii=False)
                item = self._validate_deliverable(
                    repaired_output,
                    schema_model,
                    raw,
                    kind,
                    citations_v2,
                )
            except ValidationError as final_validation_error:
                final_validation_summary = _validation_summary(final_validation_error)
                chinese_count_after_rewrite, structure_complete = _wechat_body_metrics(
                    repaired_output
                )
                stage_logger.warning(
                    "event=operation_wechat_rewrite_validation_failed "
                    "attempt=2 chinese_count=%s hotspot_structure_complete=%s errors=%s",
                    chinese_count_after_rewrite,
                    structure_complete,
                    final_validation_summary,
                )
                retryable_wechat_presentation = (
                    not length_only_repair
                    and raw["platform"] == "wechat_official_account"
                    and final_validation_summary
                    in {
                        "root: Value error, WECHAT_BODY_CHINESE_LENGTH_INVALID",
                        "root: Value error, WECHAT_HOTSPOT_STRUCTURE_INVALID",
                    }
                )
                terminal_retry_budget = replace(
                    self._retry_budget(retry_budget, execution),
                    timeout_ms=max(
                        0,
                        remaining.timeout_ms - int((time.monotonic() - started) * 1000),
                    ),
                )
                if retryable_wechat_presentation and (
                    terminal_retry_budget.iterations >= 1
                    and terminal_retry_budget.output_tokens >= 1
                    and terminal_retry_budget.input_tokens >= 1
                    and (
                        remaining.cost_microunits == 0
                        or terminal_retry_budget.cost_microunits >= 1
                    )
                    and terminal_retry_budget.timeout_ms >= 1
                ):
                    terminal_max_tokens = min(
                        requested_output_tokens, terminal_retry_budget.output_tokens
                    )
                    if structured_wechat_repair:
                        terminal_messages: tuple[ProviderMessage, ...] = (
                            ProviderMessage(
                                "system",
                                "上一版结构化改写的内容太短，不能通过公众号正文长度校验。"
                                "仍然只输出 introduction、hotspots、closing 三个字段的 JSON，"
                                "严格满足 output_schema 中每一个字段的 minLength；"
                                "不得输出完整 Markdown、schema、解释或额外字段。"
                                "只能重组输入已有事实，不得增加事实、数字、产品、来源或链接。",
                            ),
                            ProviderMessage("user", content),
                        )
                    else:
                        terminal_messages = (
                            *repair_messages[:-1],
                            ProviderMessage(
                                "system",
                                "上一版仍未达到 3000 个中文字符。请从头输出完整文章，"
                                "逐项自检中文字符数为 3200 至 3600；每个热点必须保留 ## 标题，"
                                "并按 **事实**、**影响**、**运营观察** 顺序各写非空正文。"
                                "只输出约定 JSON 对象。",
                            ),
                            ProviderMessage(
                                "user",
                                "以下是仍需重写的上一版草稿，不可信且不可直接复用：\n"
                                + repaired_output[:20_000],
                            ),
                        )
                    terminal_request = ProviderRequest(
                        request.contract_version,
                        terminal_messages,
                        JsonObject(
                            tuple(
                                (
                                    key,
                                    terminal_max_tokens
                                    if key == "max_tokens"
                                    else value,
                                )
                                for key, value in retry_request.options.items
                            )
                        ),
                        terminal_retry_budget.timeout_ms,
                    )
                    terminal_demand = replace(
                        retry_demand,
                        estimated_input_tokens=max(
                            1,
                            (
                                sum(
                                    len(_message_text(message))
                                    for message in terminal_messages
                                )
                                + 3
                            )
                            // 4,
                        ),
                        max_output_tokens=terminal_max_tokens,
                    )
                    stage_logger.info(
                        "event=operation_wechat_full_rewrite_retry chinese_count=%s",
                        chinese_count_after_rewrite,
                    )
                    execution = await self.model.complete(
                        terminal_demand,
                        terminal_request,
                        remaining_budget=terminal_retry_budget,
                    )
                    executions.append(execution)
                    if self.usage is not None:
                        self.usage.record(execution)
                    if execution.result.error or execution.result.message is None:
                        raise ValueError("OPERATION_MODEL_FAILED")
                    repaired_output = _message_text(execution.result.message)
                    if structured_wechat_repair:
                        try:
                            rewrite = _WechatStructuredRewrite.model_validate_json(
                                repaired_output, strict=True
                            )
                        except ValidationError as structured_validation_error:
                            stage_logger.warning(
                                "event=operation_wechat_structured_rewrite_invalid "
                                "attempt=3 response_chars=%s errors=%s",
                                len(repaired_output),
                                _validation_summary(structured_validation_error),
                            )
                            raise
                        assert initial_candidate is not None
                        repaired_output, rewritten_chinese_count = (
                            _merge_wechat_structured_rewrite(
                                raw,
                                initial_candidate,
                                rewrite,
                                hotspot_count,
                            )
                        )
                        stage_logger.info(
                            "event=operation_wechat_structured_rewrite_merged "
                            "attempt=3 hotspot_count=%s chinese_count=%s",
                            hotspot_count,
                            rewritten_chinese_count,
                        )
                    item = self._validate_deliverable(
                        repaired_output,
                        schema_model,
                        raw,
                        kind,
                        citations_v2,
                    )
                else:
                    logger.warning(
                        "event=operation_deliverable_validation_failed platform=%s attempt=2 errors=%s",
                        raw["platform"],
                        final_validation_summary,
                    )
                    raise
        if item.platform != raw["platform"]:
            raise ValueError("DELIVERABLE_PLATFORM_MISMATCH")
        sources = {citation["url"]: citation for citation in raw["citations"]}
        if any(citation.url not in sources for citation in item.citations):
            raise ValueError("UNSUPPORTED_CITATION")
        citations = (
            [
                CitationV1.model_validate(sources[citation.url])
                for citation in item.citations
            ]
            if not is_v2
            else citations_v2
        )
        if not is_v2 and raw["research"] and not citations:
            # 研究证据已由 Supervisor 通过 EvidencePack 校验；模型未主动回填
            # 引用时仍把已验证来源带入成品，避免用户收到无来源的“最新”内容。
            citations = [CitationV1.model_validate(value) for value in raw["citations"]]
        # 模型生成的自由文本不是权威运行状态，不能自行把正常任务标成降级。
        # 用户需要看到的事实限制应写在正文；系统 warnings 只接收能力层和
        # 确定性检查产生的稳定代码。
        warnings = [*self.extra_warnings]
        if raw["research"] and not citations:
            warnings.append("RESEARCH_SOURCES_UNAVAILABLE")
        if any(attempt.degraded for attempt in executions):
            warnings.append("MODEL_DEGRADED")
        assembler = DeliverableAssembler()
        # 结构化归一化必须先于质量报告和最终 payload；否则正文标签虽被
        # 识别，后续质量节点仍会看到模型原始的空 hashtags 并产生误报。
        if is_v2:
            data = item.model_dump(mode="json")
            data.update(
                citations=citations,
                copy_text=render_copy_text(item),
                warnings=[WarningV2(code=code, message=code) for code in warnings],
            )
            item = DeliveryPresentationValidator().validate_deliverable(
                _V2_MODELS[kind].model_validate(data)
            )
            if isinstance(item, RankedDigestDeliverableV2):
                ranked_items = item.content.items
                item = item.model_copy(
                    update={
                        "citations": [
                            citation.model_copy(
                                update={
                                    "supports_item_ids": [
                                        entry.item_id
                                        for entry in ranked_items
                                        if citation.citation_id in entry.source_refs
                                    ]
                                }
                            )
                            for citation in item.citations
                        ]
                    }
                )
            quality_item = project_set_v2_to_v1(
                DeliverableSetV2(
                    run_id=task.parent_run_id,
                    intent_revision=0,
                    summary=DeliverySummaryV2(
                        message="质量检查投影", result_count=1, complete=True
                    ),
                    deliverables=[item],
                )
            ).deliverables[0]
        else:
            item = item.model_copy(
                update={"citations": citations, "warnings": warnings}
            )
            item = assembler.assemble((item,)).deliverables[0]
            quality_item = item
        report = assembler.assess(
            [quality_item],
            task_id=raw["task_id"],
            report_id=f"quality-{task.task_id}",
            deliverable_ids=(raw["deliverable_id"],),
        )
        payload = freeze(item.model_dump(mode="json"))
        assert isinstance(payload, JsonObject)
        deliverable = OperationDeliverable(
            "operation-deliverable/1",
            raw["deliverable_id"],
            DeliverableKind.REPORT
            if raw["research"] and raw["platform"] == "research"
            else DeliverableKind.COPY,
            "1.0.0",
            item.title,
            (),
            (item.platform,),
            None,
            payload,
            frozenset(),
            frozenset(),
            frozenset(),
            tuple(raw["profile_reference_ids"]),
            GenerationProcessReference(
                f"process-{task.task_id}", "operation-process/1", (task.task_id,), ()
            ),
            "operation.deliverable.generation",
            "1.0.0",
            raw["plan_id"],
            report.report_id,
            None,
        )
        bundle = DeliverableBundle(
            "deliverable-bundle/1",
            f"bundle-{task.task_id}",
            raw["task_id"],
            raw["plan_id"],
            (deliverable,),
            None,
            (report.report_id,),
            frozenset(),
        )
        usage = BudgetUsage(
            iterations=sum(len(attempt.attempts) for attempt in executions)
            + (1 if self.capability_usage != UsageSnapshot() else 0),
            input_tokens=sum(attempt.usage.input_tokens for attempt in executions)
            + self.capability_usage.input_tokens,
            output_tokens=sum(attempt.usage.output_tokens for attempt in executions)
            + self.capability_usage.output_tokens,
            cost_microunits=sum(attempt.usage.cost_microunits for attempt in executions)
            + self.capability_usage.cost_microunits,
        )
        result = SpecialistExecutionResult(
            "operation-specialist-result/1",
            task.task_id,
            (task.task_id,),
            (),
            bundle,
            self.evidence_pack,
            report,
            (),
            tuple(warnings),
            None,
            None,
            None,
            usage,
        )
        return encode_specialist_result(result, task.parent_run_id)

    async def _run_v3(self, task: SupervisorTask, raw: dict[str, Any]) -> RunResult:
        scenario, stage = _V3_ROUTE_BY_AGENT[self.spec.agent_id]
        executor = self.scenario_executor
        assert executor is not None
        arguments = {
            "run_id": task.parent_run_id,
            "scenario": scenario,
            "stage": stage,
            "platform": None if raw["platform"] == "general" else raw["platform"],
            "user_request": raw["goal"],
            "input_artifact_ids": tuple(
                str(item.get("source_deliverable_id"))
                for item in raw["input_deliverables"]
                if isinstance(item, dict) and item.get("source_deliverable_id")
            ),
            "evidence": {
                "evidence_pack": (
                    asdict(self.evidence_pack) if self.evidence_pack is not None else None
                ),
                "citations": raw["citations"],
                "input_deliverables": raw["input_deliverables"],
            },
        }
        if hasattr(executor, "generate_with_usage"):
            generation = await executor.generate_with_usage(**arguments)
            generated_deliverable = generation.deliverable
            generation_executions = generation.executions
        else:
            generated_deliverable = await executor.generate(**arguments)
            generation_executions = ()
        generated = generated_deliverable.model_copy(
            update={
                "deliverable_id": raw["deliverable_id"],
                "platform": None
                if raw["platform"] == "general"
                else raw["platform"],
            }
        )
        report = OperationQualityReport(
            "operation-quality-report/1",
            f"quality-{task.task_id}",
            raw["task_id"],
            (raw["deliverable_id"],),
            (
                OperationQualityCheck(
                    QualityDimension.FORMAT,
                    QualityStatus.PASSED,
                    (),
                    "deliverable/3 强类型契约校验通过",
                ),
            ),
            QualityStatus.PASSED,
            0,
        )
        payload = freeze(generated.model_dump(mode="json"))
        assert isinstance(payload, JsonObject)
        kind = {
            "multi_platform_content": DeliverableKind.COPY,
            "operation_review": DeliverableKind.ANALYSIS,
            "industry_digest": DeliverableKind.REPORT,
        }.get(scenario, DeliverableKind.PLAN)
        artifact = OperationDeliverable(
            "operation-deliverable/1",
            raw["deliverable_id"],
            kind,
            "3.0.0",
            generated.title,
            (),
            (raw["platform"],) if raw["platform"] != "general" else (),
            None,
            payload,
            frozenset(),
            frozenset(),
            frozenset(warning.code for warning in generated.warnings),
            tuple(raw["profile_reference_ids"]),
            GenerationProcessReference(
                f"process-{task.task_id}", "operation-process/1", (task.task_id,), ()
            ),
            None,
            None,
            raw["plan_id"],
            report.report_id,
            None,
        )
        bundle = DeliverableBundle(
            "deliverable-bundle/1",
            f"bundle-{task.task_id}",
            raw["task_id"],
            raw["plan_id"],
            (artifact,),
            None,
            (report.report_id,),
            frozenset(),
        )
        for execution in generation_executions:
            if self.usage is not None:
                self.usage.record(execution)
        return encode_specialist_result(
            SpecialistExecutionResult(
                "operation-specialist-result/1",
                task.task_id,
                (task.task_id,),
                (),
                bundle,
                self.evidence_pack,
                report,
                (),
                tuple(warning.code for warning in generated.warnings),
                None,
                None,
                None,
                BudgetUsage(
                    iterations=sum(
                        max(1, len(execution.attempts))
                        for execution in generation_executions
                    ),
                    input_tokens=sum(
                        execution.usage.input_tokens
                        for execution in generation_executions
                    )
                    + self.capability_usage.input_tokens,
                    output_tokens=sum(
                        execution.usage.output_tokens
                        for execution in generation_executions
                    )
                    + self.capability_usage.output_tokens,
                    cost_microunits=sum(
                        execution.usage.cost_microunits
                        for execution in generation_executions
                    )
                    + self.capability_usage.cost_microunits,
                ),
            ),
            task.parent_run_id,
        )

    def _validate_deliverable(
        self,
        output: JsonValue,
        schema: type[BaseModel],
        raw: dict[str, Any],
        kind: str,
        citations: list[CitationV2],
    ) -> Any:
        """先拒绝越权字段与引用，再执行可修复的结构校验。"""
        try:
            value = json.loads(output) if isinstance(output, str) else plain(output)
        except json.JSONDecodeError:
            assert isinstance(output, str)
            candidate = output.lstrip()
            try:
                value, end = json.JSONDecoder().raw_decode(candidate)
            except json.JSONDecodeError:
                return schema.model_validate_json(output, strict=True)
            trailing = candidate[end:].strip()
            if not trailing or not isinstance(value, dict):
                return schema.model_validate_json(output, strict=True)
            logger.warning(
                "event=operation_deliverable_trailing_text_removed platform=%s trailing_chars=%s",
                raw["platform"],
                len(trailing),
            )
        if isinstance(value, dict):
            fixed = {
                "contract_version": self.deliverable_contract_version,
                "platform": raw["platform"],
            }
            if self.deliverable_contract_version == "deliverable/2":
                fixed.update(
                    deliverable_id=raw["deliverable_id"], deliverable_kind=kind
                )
                if value.get("citations", []) != []:
                    raise ValueError("UNSUPPORTED_CITATION")
                source_ids = {citation.citation_id for citation in citations}
                content = value.get("content", {})
                if isinstance(content, dict):
                    for entry in (
                        content.get("items", [])
                        if isinstance(content.get("items", []), list)
                        else []
                    ):
                        if (
                            isinstance(entry, dict)
                            and entry.get("verification_status", "unverified")
                            != "unverified"
                        ):
                            raise ValueError("DELIVERABLE_VERIFICATION_FORBIDDEN")
                        if (
                            isinstance(entry, dict)
                            and isinstance(entry.get("source_refs"), list)
                            and any(
                                not isinstance(ref, str) or ref not in source_ids
                                for ref in entry["source_refs"]
                            )
                        ):
                            raise ValueError("DELIVERY_CITATION_CLOSURE_INVALID")
            elif isinstance(value.get("citations"), list):
                allowed_urls = {source["url"] for source in raw["citations"]}
                if any(
                    isinstance(citation, dict)
                    and "url" in citation
                    and citation["url"] not in allowed_urls
                    for citation in value["citations"]
                ):
                    raise ValueError("UNSUPPORTED_CITATION")
            for key, expected in fixed.items():
                if key in value and value[key] != expected:
                    raise ValueError("DELIVERABLE_AUTHORITY_MISMATCH")
            if set(value) & {
                "permissions",
                "allowed_tools",
                "budget",
                "tenant_id",
                "degraded",
            }:
                raise ValueError("SPECIALIST_PERMISSION_DENIED")
        return schema.model_validate(value, strict=True)

    def _citations_v2(self, sources: list[dict[str, Any]]) -> list[CitationV2]:
        """旧来源保守升级，绝不把离线字段质量冒充事实核验。"""
        records = (
            {
                self._source_url(record.source_url): record
                for record in self.evidence_pack.records
            }
            if self.evidence_pack
            else {}
        )
        result: list[CitationV2] = []
        seen: set[str] = set()
        for source in sources:
            if "citation_id" in source:
                citation = CitationV2.model_validate(source, strict=True)
                url = self._source_url(citation.url)
                # V2 来源按 citation_id 闭合，不能按 URL 合并不同的引用标识。
                seen.add(url)
                result.append(citation.model_copy(update={"url": url}))
                continue
            legacy = CitationV1.model_validate(source)
            url = self._source_url(legacy.url)
            if url in seen:
                continue
            seen.add(url)
            record = records.get(url)
            result.append(
                CitationV2(
                    citation_id=record.evidence_id
                    if record
                    else "citation-" + hashlib.sha256(url.encode()).hexdigest()[:20],
                    url=url,
                    title=record.title if record else legacy.title,
                    source=record.publisher if record else legacy.source,
                    published_at=datetime.fromtimestamp(
                        record.published_at_epoch_ms / 1000, tz=UTC
                    ).isoformat()
                    if record and record.published_at_epoch_ms is not None
                    else None,
                    source_type="public_page",
                    source_tier="secondary",
                    verification_status="unverified",
                    independent_source_group=urlsplit(url).hostname,
                )
            )
        return result

    @staticmethod
    def _source_url(value: str) -> str:
        """只做 HTTPS 来源规范化，不联网或推断来源级别。"""
        parts = urlsplit(value)
        if (
            parts.scheme.lower() != "https"
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise ValueError("DELIVERABLE_CITATION_INVALID")
        return urlunsplit(
            (
                "https",
                parts.netloc.lower(),
                parts.path,
                parts.query,
                "",
            )
        )

    @staticmethod
    def _retry_budget(remaining: RemainingBudget, execution: Any) -> RemainingBudget:
        attempts = len(execution.attempts)
        usage = execution.usage
        return RemainingBudget(
            max(0, remaining.iterations - attempts),
            remaining.tool_calls,
            max(0, remaining.input_tokens - usage.input_tokens),
            max(0, remaining.output_tokens - usage.output_tokens),
            max(0, remaining.cost_microunits - usage.cost_microunits),
            remaining.timeout_ms,
        )


def evidence_citations(pack: EvidencePack | None) -> list[dict[str, object]]:
    """只投影有效且处于时间窗内的来源元数据，不声称在线核验。"""
    if pack is None:
        return []
    return [
        {
            "url": item.source_url,
            "title": _citation_title(item.title, item.published_at_epoch_ms),
            "source": item.publisher,
        }
        for item in pack.records
        if item.quality_status
        in {
            EvidenceQualityStatus.VALID,
            EvidenceQualityStatus.UNVERIFIED,
        }
        and item.within_time_window
    ]


def _citation_title(title: str, published_at_epoch_ms: int | None) -> str:
    if published_at_epoch_ms is None:
        return title
    published = datetime.fromtimestamp(
        published_at_epoch_ms / 1_000, tz=UTC
    ).astimezone(ZoneInfo("Asia/Shanghai"))
    return f"{title}（发布日期：{published.date().isoformat()}）"
