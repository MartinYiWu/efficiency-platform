"""运营 Specialist 输入输出公共契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    OperationDeliverable,
    OperationQualityReport,
)
from efficiency_platform_agent.agents.operation.contracts.evidence import EvidencePack
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
)
from efficiency_platform_agent.agents.operation.contracts.task import OperationTaskSpec
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.multi_agent import BudgetUsage


@dataclass(frozen=True, slots=True)
class SpecialistExecutionInput:
    contract_version: Literal["operation-specialist-input/1"]
    task_id: str
    tenant_id: str
    operation_task: OperationTaskSpec
    operation_context: OperationContext
    input_deliverables: tuple[OperationDeliverable, ...] = ()
    evidence_pack: EvidencePack | None = None
    platform_profile: object | None = None
    analytics_dataset_reference: object | None = None
    analytics_summary: object | None = None

    def __post_init__(self) -> None:
        if self.contract_version != "operation-specialist-input/1":
            raise ValueError("INPUT_SCHEMA_INVALID:contract_version")
        if not self.task_id or not self.tenant_id:
            raise ValueError("INPUT_SCHEMA_INVALID:identity")
        task_tenant = getattr(self.operation_task, "tenant_id", self.tenant_id)
        if task_tenant != self.tenant_id:
            raise ValueError("INPUT_SCHEMA_INVALID:tenant")
        if not isinstance(self.input_deliverables, tuple):
            raise TypeError("input_deliverables必须是tuple")
        if (self.analytics_dataset_reference is None) != (
            self.analytics_summary is None
        ):
            raise ValueError("analytics引用必须同时存在或为空")


@dataclass(frozen=True, slots=True)
class SpecialistExecutionResult:
    contract_version: Literal["operation-specialist-result/1"]
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
    revision_request: object | None
    usage: BudgetUsage

    def __post_init__(self) -> None:
        if self.contract_version != "operation-specialist-result/1":
            raise ValueError("OUTPUT_SCHEMA_INVALID:contract_version")
        if not self.task_id:
            raise ValueError("OUTPUT_SCHEMA_INVALID:task_id")
        if not isinstance(self.completed_scope, tuple) or not isinstance(
            self.missing_scope, tuple
        ):
            raise TypeError("scope必须是tuple")
        if set(self.completed_scope).intersection(self.missing_scope):
            raise ValueError("完成范围和缺失范围不得重叠")
        if (
            self.error_code is None
            and not self.completed_scope
            and self.deliverable_bundle is None
            and self.evidence_pack is None
            and self.quality_report is None
        ):
            raise ValueError("成功结果必须包含完成范围或结构化产物")
        if self.error_code is not None and not self.missing_scope:
            raise ValueError("失败结果必须包含缺失范围")


__all__ = ["SpecialistExecutionInput", "SpecialistExecutionResult"]
