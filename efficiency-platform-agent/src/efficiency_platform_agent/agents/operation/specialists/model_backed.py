"""通过统一 PromptRuntime 和 ModelRuntime 执行运营专家。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError, create_model

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
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
from efficiency_platform_agent.prompts.runtime import PromptRuntime

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
    ) -> None:
        if deliverable_contract_version not in {"deliverable/1", "deliverable/2"}:
            raise ValueError("DELIVERABLE_VERSION_UNSUPPORTED")
        self.deliverable_contract_version = deliverable_contract_version
        self.spec = spec
        self.prompts = prompts
        self.model = model
        self.usage = usage
        self.evidence_pack = evidence_pack
        self.extra_warnings = extra_warnings
        self.capability_usage = capability_usage
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
        schema_model = _V2_DRAFTS[kind] if is_v2 else DeliverableV1
        schema = freeze(schema_model.model_json_schema())
        request = ProviderRequest(
            "operation-model/1",
            (*rendered.messages, ProviderMessage("user", content)),
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
                    ("max_tokens", budget.max_output_tokens),
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
            len(content) + rendered.rendered_chars,
            budget.max_output_tokens,
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
        output = execution.result.message.content
        try:
            item = self._validate_deliverable(
                output, schema_model, raw, kind, citations_v2
            )
        except ValidationError:
            retry_budget = replace(
                self._retry_budget(remaining, execution),
                timeout_ms=max(
                    0, remaining.timeout_ms - int((time.monotonic() - started) * 1000)
                ),
            )
            if (
                retry_budget.iterations < 1
                or retry_budget.output_tokens < 1
                or retry_budget.input_tokens < 1
                or (remaining.cost_microunits > 0 and retry_budget.cost_microunits < 1)
                or retry_budget.timeout_ms < 1
            ):
                raise
            retry_max_tokens = min(budget.max_output_tokens, retry_budget.output_tokens)
            retry_options = JsonObject(
                tuple(
                    (key, retry_max_tokens if key == "max_tokens" else value)
                    for key, value in request.options.items
                )
            )
            retry_request = ProviderRequest(
                request.contract_version,
                (
                    *rendered.messages,
                    ProviderMessage(
                        "system",
                        "上一版输出未通过严格 Schema 校验。请重新生成；只能输出约定 JSON 对象，禁止额外字段、Markdown 围栏和解释。",
                    ),
                    ProviderMessage("user", content),
                ),
                retry_options,
                retry_budget.timeout_ms,
            )
            execution = await self.model.complete(
                replace(demand, max_output_tokens=retry_max_tokens),
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
                    budget.max_output_tokens, final_budget.output_tokens
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
                    replace(demand, max_output_tokens=final_max_tokens),
                    final_request,
                    remaining_budget=final_budget,
                )
                executions.append(execution)
                if self.usage is not None:
                    self.usage.record(execution)
                if execution.result.error or execution.result.message is None:
                    raise ValueError("OPERATION_MODEL_FAILED")
            item = self._validate_deliverable(
                execution.result.message.content, schema_model, raw, kind, citations_v2
            )
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
            return schema.model_validate_json(output, strict=True)
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
