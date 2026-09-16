"""通过统一 PromptRuntime 和 ModelRuntime 执行运营专家。"""

from __future__ import annotations

import json
from typing import Any

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
from efficiency_platform_agent.contracts.deliverables import CitationV1, DeliverableV1
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
    ) -> None:
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
            "research",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("SPECIALIST_INPUT_INVALID")
        rendered = self.prompts.render(
            "operation.deliverable.generation/1", {"capability": self.spec.agent_id}
        )
        content = json.dumps(raw, ensure_ascii=False)
        budget = task.budget
        schema = freeze(DeliverableV1.model_json_schema())
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
                                            ("name", "operation_deliverable"),
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
        execution = await self.model.complete(
            ModelDemand(
                "model-demand/1",
                ModelTier.BALANCED,
                True,
                False,
                len(content) + rendered.rendered_chars,
                budget.max_output_tokens,
            ),
            request,
            remaining_budget=remaining,
        )
        if self.usage is not None:
            self.usage.record(execution)
        if execution.result.error or execution.result.message is None:
            raise ValueError("OPERATION_MODEL_FAILED")
        output = execution.result.message.content
        item = (
            DeliverableV1.model_validate_json(output)
            if isinstance(output, str)
            else DeliverableV1.model_validate(plain(output))
        )
        if item.platform != raw["platform"]:
            raise ValueError("DELIVERABLE_PLATFORM_MISMATCH")
        sources = {citation["url"]: citation for citation in raw["citations"]}
        if any(citation.url not in sources for citation in item.citations):
            raise ValueError("UNSUPPORTED_CITATION")
        citations = [
            CitationV1.model_validate(sources[citation.url])
            for citation in item.citations
        ]
        if raw["research"] and not citations:
            # 研究证据已由 Supervisor 通过 EvidencePack 校验；模型未主动回填
            # 引用时仍把已验证来源带入成品，避免用户收到无来源的“最新”内容。
            citations = [
                CitationV1.model_validate(value) for value in raw["citations"]
            ]
        warnings = [*item.warnings, *self.extra_warnings]
        if raw["research"] and not citations:
            warnings.append("RESEARCH_SOURCES_UNAVAILABLE")
        if execution.degraded:
            warnings.append("MODEL_DEGRADED")
        item = item.model_copy(update={"citations": citations, "warnings": warnings})
        report = DeliverableAssembler().assess(
            [item],
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
            (),
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
            iterations=len(execution.attempts)
            + (1 if self.capability_usage != UsageSnapshot() else 0),
            input_tokens=execution.usage.input_tokens
            + self.capability_usage.input_tokens,
            output_tokens=execution.usage.output_tokens
            + self.capability_usage.output_tokens,
            cost_microunits=execution.usage.cost_microunits
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


def evidence_citations(pack: EvidencePack | None) -> list[dict[str, object]]:
    """只投影有效且处于时间窗内的来源元数据，不声称在线核验。"""
    if pack is None:
        return []
    return [
        {"url": item.source_url, "title": item.title, "source": item.publisher}
        for item in pack.records
        if item.quality_status
        in {
            EvidenceQualityStatus.VALID,
            EvidenceQualityStatus.UNVERIFIED,
        }
        and item.within_time_window
    ]
