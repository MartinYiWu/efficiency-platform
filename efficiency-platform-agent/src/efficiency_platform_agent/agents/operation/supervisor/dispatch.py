"""构造受控 Specialist 派发任务并失败关闭地解码结果。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from efficiency_platform_agent.agents.factory import AgentFactory
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.multi_agent import (
    BudgetUsage,
    TaskDispatch,
    TaskNode,
)
from efficiency_platform_agent.core.run import JsonObject, RunResult, SupervisorTask

from ..contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
    OperationQualityCheck,
    OperationQualityReport,
    QualityDimension,
    QualityStatus,
)
from ..contracts.evidence import (
    ConclusionSupport,
    EvidenceDuplicateStatus,
    EvidencePack,
    EvidenceQualityStatus,
    EvidenceRecord,
    TimeWindow,
)
from ..contracts.task import SourceScope
from .budget import BudgetLedger
from .selection import SelectedSpecialist


def _values(value: JsonObject) -> dict[str, object]:
    """读取不可变 JSON 对象并保留调用方的严格字段校验。"""
    return dict(value.items)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """解析仅允许字符串的不可变序列。"""
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"OUTPUT_SCHEMA_INVALID:{field_name}")
    return value


def _optional_json_object(value: object, field_name: str) -> JsonObject | None:
    """解析可空 JSON 对象。"""
    if value is None:
        return None
    if not isinstance(value, JsonObject):
        raise ValueError(  # noqa: TRY004  # 结构化输出类型错误统一映射为契约错误
            f"OUTPUT_SCHEMA_INVALID:{field_name}"
        )
    return value


@dataclass(frozen=True, slots=True)
class SpecialistResultEnvelope:
    """S4 对 S3 交付物权威类型的版本化结果封装。"""

    contract_version: str
    task_id: str
    completed_scope: tuple[str, ...]
    missing_scope: tuple[str, ...]
    deliverable_bundle: DeliverableBundle | None
    evidence_pack: EvidencePack | None
    quality_report: OperationQualityReport | None
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    error_code: str | None
    requested_capability: CapabilityRequirement | None
    revision_request: JsonObject | None
    usage: BudgetUsage | None

    def __post_init__(self) -> None:
        if self.contract_version != "operation-specialist-result/1":
            raise ValueError("OUTPUT_SCHEMA_INVALID:contract_version")
        if not isinstance(self.task_id, str) or not self.task_id:
            raise ValueError("OUTPUT_SCHEMA_INVALID:task_id")
        if set(self.completed_scope).intersection(self.missing_scope):
            raise ValueError("OUTPUT_SCHEMA_INVALID:scope")


class DispatchBuilder:
    """从已选择候选和预算账本构造 S1 SupervisorTask。"""

    def __init__(self, factory: AgentFactory, ledger: BudgetLedger) -> None:
        if not isinstance(factory, AgentFactory):
            raise TypeError("factory 必须是 AgentFactory")
        if not isinstance(ledger, BudgetLedger):
            raise TypeError("ledger 必须是 BudgetLedger")
        self._factory = factory
        self._ledger = ledger

    def build(
        self,
        node: TaskNode,
        selected: SelectedSpecialist,
        *,
        parent_run_id: str,
        parent_deadline_epoch_ms: int,
        input_data: JsonObject,
        context_view: JsonObject | None = None,
        attempt: int = 1,
        revision: int = 0,
        fence_token: int = 0,
    ) -> TaskDispatch:
        """复核候选白名单后生成不含父态和注册表的调度包装。"""
        if not isinstance(node, TaskNode):
            raise TypeError("node 必须是 TaskNode")
        if not isinstance(selected, SelectedSpecialist):
            raise TypeError("selected 必须是 SelectedSpecialist")
        if not isinstance(input_data, JsonObject):
            raise TypeError("input_data 必须是 JsonObject")
        if context_view is not None and not isinstance(context_view, JsonObject):
            raise TypeError("context_view 必须是 JsonObject 或 None")
        if (
            not isinstance(parent_deadline_epoch_ms, int)
            or parent_deadline_epoch_ms <= 0
        ):
            raise ValueError("parent_deadline_epoch_ms 必须是正整数")
        spec = selected.spec
        if selected.agent_id != spec.agent_id:
            raise ValueError("候选 Agent 标识与定义不一致")
        if node.task_type not in spec.supported_task_types:
            raise ValueError("SPECIALIST_UNAVAILABLE:task_type")
        if node.input_schema_version != spec.input_schema_version:
            raise ValueError("SPECIALIST_UNAVAILABLE:input_schema")
        if node.output_schema_version != spec.output_schema_version:
            raise ValueError("SPECIALIST_UNAVAILABLE:output_schema")
        if not node.required_permissions.issubset(spec.permissions):
            raise ValueError("SPECIALIST_UNAVAILABLE:permissions")
        if not node.allowed_tools.issubset(spec.allowed_tools):
            raise ValueError("SPECIALIST_UNAVAILABLE:tools")
        budget = self._ledger.budget_for(node.task_id, spec.budget)
        task = SupervisorTask(
            task_id=node.task_id,
            parent_run_id=parent_run_id,
            target_agent=selected.agent_id,
            input_data=input_data,
            context_view=context_view or node.context_view,
            allowed_tools=node.allowed_tools,
            budget=budget,
        )
        return TaskDispatch(
            task=task,
            capability_ids=spec.capability_ids,
            attempt=attempt,
            revision=revision,
            fence_token=fence_token,
            parent_deadline_epoch_ms=parent_deadline_epoch_ms,
        )


class SpecialistResultDecoder:
    """只接受版本化 JSON 信封；S3 嵌入对象由后续专用适配器解析。"""

    _REQUIRED_KEYS = frozenset(
        {
            "contract_version",
            "task_id",
            "completed_scope",
            "missing_scope",
            "deliverable_bundle",
            "evidence_pack",
            "quality_report",
            "assumptions",
            "warnings",
            "error_code",
            "requested_capability",
            "revision_request",
            "usage",
        }
    )

    def decode(self, result: RunResult) -> SpecialistResultEnvelope:
        """把 Specialist 的结构化输出转换为封装；任何缺失或未知字段均拒绝。"""
        if not isinstance(result, RunResult) or not isinstance(
            result.output, JsonObject
        ):
            raise ValueError(  # noqa: TRY004  # 解码失败必须对外隐藏内部类型细节
                "OUTPUT_SCHEMA_INVALID:result"
            )
        raw = _values(result.output)
        if set(raw) != self._REQUIRED_KEYS:
            raise ValueError("OUTPUT_SCHEMA_INVALID:fields")
        if raw["contract_version"] != "operation-specialist-result/1":
            raise ValueError("OUTPUT_SCHEMA_INVALID:contract_version")
        task_id = raw["task_id"]
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("OUTPUT_SCHEMA_INVALID:task_id")
        completed_scope = _string_tuple(raw["completed_scope"], "completed_scope")
        missing_scope = _string_tuple(raw["missing_scope"], "missing_scope")
        assumptions = _string_tuple(raw["assumptions"], "assumptions")
        warnings = _string_tuple(raw["warnings"], "warnings")
        error_code = raw["error_code"]
        if error_code is not None and not isinstance(error_code, str):
            raise ValueError("OUTPUT_SCHEMA_INVALID:error_code")
        requested_capability = self._capability(raw["requested_capability"])
        revision_request = _optional_json_object(
            raw["revision_request"], "revision_request"
        )
        usage = self._usage(raw["usage"])
        if usage is not None and "SPECIALIST_USAGE_IGNORED" not in warnings:
            warnings = (*warnings, "SPECIALIST_USAGE_IGNORED")
        evidence_pack = self._evidence_pack(raw["evidence_pack"])
        deliverable_bundle = self._deliverable_bundle(raw["deliverable_bundle"])
        quality_report = self._quality_report(raw["quality_report"])
        return SpecialistResultEnvelope(
            contract_version="operation-specialist-result/1",
            task_id=task_id,
            completed_scope=completed_scope,
            missing_scope=missing_scope,
            deliverable_bundle=deliverable_bundle,
            evidence_pack=evidence_pack,
            quality_report=quality_report,
            assumptions=assumptions,
            warnings=warnings,
            error_code=error_code,
            requested_capability=requested_capability,
            revision_request=revision_request,
            usage=usage,
        )

    @staticmethod
    def _capability(value: object) -> CapabilityRequirement | None:
        if value is None:
            return None
        if not isinstance(value, JsonObject):
            raise ValueError(  # noqa: TRY004  # 统一返回稳定的输出契约错误码
                "OUTPUT_SCHEMA_INVALID:requested_capability"
            )
        raw = _values(value)
        if set(raw) != {"all_of", "any_of"}:
            raise ValueError("OUTPUT_SCHEMA_INVALID:requested_capability")
        return CapabilityRequirement(
            all_of=frozenset(_string_tuple(raw["all_of"], "requested_capability")),
            any_of=frozenset(_string_tuple(raw["any_of"], "requested_capability")),
        )

    @staticmethod
    def _usage(value: object) -> BudgetUsage | None:
        if value is None:
            return None
        if not isinstance(value, JsonObject):
            raise ValueError(  # noqa: TRY004  # 统一返回稳定的输出契约错误码
                "OUTPUT_SCHEMA_INVALID:usage"
            )
        raw = _values(value)
        fields = (
            "iterations",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "elapsed_ms",
            "cost_microunits",
        )
        if set(raw) != set(fields) or any(
            not isinstance(raw[field], int) or isinstance(raw[field], bool)
            for field in fields
        ):
            raise ValueError("OUTPUT_SCHEMA_INVALID:usage")
        try:
            return BudgetUsage(*(cast(int, raw[field]) for field in fields))
        except (TypeError, ValueError) as error:
            raise ValueError("OUTPUT_SCHEMA_INVALID:usage") from error

    @staticmethod
    def _object(
        value: object, field_name: str, keys: frozenset[str]
    ) -> dict[str, object]:
        """读取并严格校验一个嵌套 JSON 对象的字段集合。"""
        if not isinstance(value, JsonObject):
            raise ValueError(  # noqa: TRY004  # 对外统一映射为结构化输出契约错误
                f"OUTPUT_SCHEMA_INVALID:{field_name}"
            )
        raw = _values(value)
        if set(raw) != keys:
            raise ValueError(f"OUTPUT_SCHEMA_INVALID:{field_name}")
        return raw

    @classmethod
    def _evidence_pack(cls, value: object) -> EvidencePack | None:
        """按 S3 EvidencePack Schema 解码并保留 records/supports。"""
        if value is None:
            return None
        try:
            raw = cls._object(
                value,
                "evidence_pack",
                frozenset(
                    {"contract_version", "pack_id", "task_id", "records", "supports"}
                ),
            )
            records_value = raw["records"]
            supports_value = raw["supports"]
            if not isinstance(records_value, tuple) or not isinstance(
                supports_value, tuple
            ):
                raise ValueError(  # noqa: TRY004  # 数组类型错误统一映射为契约错误
                    "OUTPUT_SCHEMA_INVALID:evidence_pack"
                )
            records = tuple(cls._evidence_record(item) for item in records_value)
            supports = tuple(cls._conclusion_support(item) for item in supports_value)
            return EvidencePack(
                cast(str, raw["contract_version"]),
                cast(str, raw["pack_id"]),
                cast(str, raw["task_id"]),
                records,
                supports,
            )
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError("OUTPUT_SCHEMA_INVALID:evidence_pack") from error

    @classmethod
    def _evidence_record(cls, value: object) -> EvidenceRecord:
        raw = cls._object(
            value,
            "evidence_record",
            frozenset(
                {
                    "evidence_id",
                    "title",
                    "publisher",
                    "source_url",
                    "published_at_epoch_ms",
                    "retrieved_at_epoch_ms",
                    "source_scope",
                    "supported_conclusion_ids",
                    "within_time_window",
                    "duplicate_status",
                    "quality_status",
                }
            ),
        )
        return EvidenceRecord(
            cast(str, raw["evidence_id"]),
            cast(str, raw["title"]),
            cast(str, raw["publisher"]),
            cast(str, raw["source_url"]),
            cast(int | None, raw["published_at_epoch_ms"]),
            cast(int, raw["retrieved_at_epoch_ms"]),
            SourceScope(cast(str, raw["source_scope"])),
            frozenset(
                _string_tuple(
                    raw["supported_conclusion_ids"], "supported_conclusion_ids"
                )
            ),
            cast(bool, raw["within_time_window"]),
            EvidenceDuplicateStatus(cast(str, raw["duplicate_status"])),
            EvidenceQualityStatus(cast(str, raw["quality_status"])),
        )

    @classmethod
    def _conclusion_support(cls, value: object) -> ConclusionSupport:
        raw = cls._object(
            value,
            "conclusion_support",
            frozenset({"conclusion_id", "evidence_ids"}),
        )
        return ConclusionSupport(
            cast(str, raw["conclusion_id"]),
            frozenset(_string_tuple(raw["evidence_ids"], "evidence_ids")),
        )

    @classmethod
    def _deliverable_bundle(cls, value: object) -> DeliverableBundle | None:
        """按 S3 交付物包 Schema 解码，不保存文件正文。"""
        if value is None:
            return None
        try:
            raw = cls._object(
                value,
                "deliverable_bundle",
                frozenset(
                    {
                        "contract_version",
                        "bundle_id",
                        "task_id",
                        "plan_id",
                        "deliverables",
                        "evidence_pack_id",
                        "quality_report_ids",
                        "warning_codes",
                    }
                ),
            )
            deliverables_value = raw["deliverables"]
            if not isinstance(deliverables_value, tuple):
                raise TypeError("交付物列表必须是不可变元组")
            return DeliverableBundle(
                cast(str, raw["contract_version"]),
                cast(str, raw["bundle_id"]),
                cast(str, raw["task_id"]),
                cast(str, raw["plan_id"]),
                tuple(cls._deliverable(item) for item in deliverables_value),
                cls._optional_string(raw["evidence_pack_id"], "evidence_pack_id"),
                _string_tuple(raw["quality_report_ids"], "quality_report_ids"),
                frozenset(_string_tuple(raw["warning_codes"], "warning_codes")),
            )
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError("OUTPUT_SCHEMA_INVALID:deliverable_bundle") from error

    @classmethod
    def _quality_report(cls, value: object) -> OperationQualityReport | None:
        """按 S3 质量报告 Schema 解码结构化检查项。"""
        if value is None:
            return None
        try:
            raw = cls._object(
                value,
                "quality_report",
                frozenset(
                    {
                        "contract_version",
                        "report_id",
                        "task_id",
                        "deliverable_ids",
                        "checks",
                        "final_status",
                        "revision_count",
                    }
                ),
            )
            checks_value = raw["checks"]
            if not isinstance(checks_value, tuple):
                raise TypeError("质量检查列表必须是不可变元组")
            revision_count = raw["revision_count"]
            if not isinstance(revision_count, int) or isinstance(revision_count, bool):
                raise TypeError("revision_count 必须是整数")
            return OperationQualityReport(
                cast(str, raw["contract_version"]),
                cast(str, raw["report_id"]),
                cast(str, raw["task_id"]),
                _string_tuple(raw["deliverable_ids"], "deliverable_ids"),
                tuple(cls._quality_check(item) for item in checks_value),
                QualityStatus(cast(str, raw["final_status"])),
                revision_count,
            )
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError("OUTPUT_SCHEMA_INVALID:quality_report") from error

    @classmethod
    def _deliverable(cls, value: object) -> OperationDeliverable:
        raw = cls._object(
            value,
            "deliverable",
            frozenset(
                {
                    "contract_version",
                    "deliverable_id",
                    "kind",
                    "semantic_version",
                    "title",
                    "subject_reference_ids",
                    "channel_ids",
                    "time_window",
                    "payload",
                    "evidence_ids",
                    "assumption_ids",
                    "warning_codes",
                    "profile_reference_ids",
                    "generation_process",
                    "prompt_bundle_id",
                    "prompt_bundle_version",
                    "plan_id",
                    "quality_report_id",
                    "artifact_reference",
                }
            ),
        )
        return OperationDeliverable(
            cast(str, raw["contract_version"]),
            cast(str, raw["deliverable_id"]),
            DeliverableKind(cast(str, raw["kind"])),
            cast(str, raw["semantic_version"]),
            cast(str, raw["title"]),
            _string_tuple(raw["subject_reference_ids"], "subject_reference_ids"),
            _string_tuple(raw["channel_ids"], "channel_ids"),
            cls._time_window(raw["time_window"]),
            cast(JsonObject, cls._json_object(raw["payload"], "payload")),
            frozenset(_string_tuple(raw["evidence_ids"], "evidence_ids")),
            frozenset(_string_tuple(raw["assumption_ids"], "assumption_ids")),
            frozenset(_string_tuple(raw["warning_codes"], "warning_codes")),
            _string_tuple(raw["profile_reference_ids"], "profile_reference_ids"),
            cls._generation_process(raw["generation_process"]),
            cls._optional_string(raw["prompt_bundle_id"], "prompt_bundle_id"),
            cls._optional_string(raw["prompt_bundle_version"], "prompt_bundle_version"),
            cast(str, raw["plan_id"]),
            cls._optional_string(raw["quality_report_id"], "quality_report_id"),
            cls._optional_string(raw["artifact_reference"], "artifact_reference"),
        )

    @classmethod
    def _quality_check(cls, value: object) -> OperationQualityCheck:
        raw = cls._object(
            value,
            "quality_check",
            frozenset({"dimension", "status", "issue_reference_ids", "safe_message"}),
        )
        return OperationQualityCheck(
            QualityDimension(cast(str, raw["dimension"])),
            QualityStatus(cast(str, raw["status"])),
            _string_tuple(raw["issue_reference_ids"], "issue_reference_ids"),
            cast(str, raw["safe_message"]),
        )

    @staticmethod
    def _json_object(value: object, field_name: str) -> JsonObject:
        if not isinstance(value, JsonObject):
            raise TypeError(f"OUTPUT_SCHEMA_INVALID:{field_name}")
        return value

    @staticmethod
    def _optional_string(value: object, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError(f"OUTPUT_SCHEMA_INVALID:{field_name}")
        return value

    @classmethod
    def _time_window(cls, value: object) -> TimeWindow | None:
        if value is None:
            return None
        raw = cls._object(
            value,
            "time_window",
            frozenset({"starts_at_epoch_ms", "ends_at_epoch_ms"}),
        )
        return TimeWindow(
            cls._optional_int(raw["starts_at_epoch_ms"], "starts_at_epoch_ms"),
            cls._optional_int(raw["ends_at_epoch_ms"], "ends_at_epoch_ms"),
        )

    @staticmethod
    def _optional_int(value: object, field_name: str) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"OUTPUT_SCHEMA_INVALID:{field_name}")
        return value

    @classmethod
    def _generation_process(cls, value: object) -> GenerationProcessReference:
        raw = cls._object(
            value,
            "generation_process",
            frozenset(
                {
                    "process_id",
                    "process_version",
                    "plan_step_ids",
                    "input_reference_ids",
                }
            ),
        )
        return GenerationProcessReference(
            cast(str, raw["process_id"]),
            cast(str, raw["process_version"]),
            _string_tuple(raw["plan_step_ids"], "plan_step_ids"),
            _string_tuple(raw["input_reference_ids"], "input_reference_ids"),
        )


__all__ = [
    "DispatchBuilder",
    "SpecialistResultDecoder",
    "SpecialistResultEnvelope",
]
