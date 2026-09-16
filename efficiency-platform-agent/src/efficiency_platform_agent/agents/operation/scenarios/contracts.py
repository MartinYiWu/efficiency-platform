"""S6 场景包提交、Supervisor 窄端口与结果契约。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    OperationQualityReport,
)
from efficiency_platform_agent.agents.operation.contracts.evidence import EvidencePack
from efficiency_platform_agent.agents.operation.contracts.planning import OperationPlan
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
)
from efficiency_platform_agent.agents.operation.contracts.scenarios import (
    ScenarioPackManifest,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    OperationRequest,
    OperationTaskSpec,
)
from efficiency_platform_agent.core.multi_agent import CompletionStatus

_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")


def _id(name: str, value: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{name}必须是稳定小写标识")


def _version(name: str, value: str) -> None:
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise ValueError(f"{name}必须是语义版本")


@dataclass(frozen=True, slots=True)
class ScenarioSubmission:
    """唯一生产入站，不接受样本、预编译计划或执行参数。"""

    contract_version: str
    submission_id: str
    scenario_id: str
    manifest_semantic_version: str
    plan_id: str
    request: OperationRequest
    task_spec: OperationTaskSpec
    profile_candidates: tuple[object, ...]
    evidence_pack: EvidencePack | None

    def __post_init__(self) -> None:
        if self.contract_version != "scenario-submission/1":
            raise ValueError("场景提交版本无效")
        for name, value in (
            ("submission_id", self.submission_id),
            ("scenario_id", self.scenario_id),
            ("plan_id", self.plan_id),
        ):
            _id(name, value)
        _version("manifest_semantic_version", self.manifest_semantic_version)
        if not isinstance(self.request, OperationRequest) or not isinstance(
            self.task_spec, OperationTaskSpec
        ):
            raise TypeError("request和task_spec必须是S3领域对象")
        if not isinstance(self.profile_candidates, tuple):
            raise TypeError("profile_candidates必须是不可变tuple")
        for candidate in self.profile_candidates:
            if not hasattr(candidate, "profile_id"):
                raise TypeError("profile_candidates只能包含ProfileCandidate")


@dataclass(frozen=True, slots=True)
class ScenarioSupervisorRequest:
    """经 S3 上下文和计划校验后的 Supervisor 请求。"""

    contract_version: str
    submission_id: str
    request: OperationRequest
    task_spec: OperationTaskSpec
    operation_context: OperationContext
    operation_plan: OperationPlan
    evidence_pack: EvidencePack | None

    def __post_init__(self) -> None:
        if self.contract_version != "scenario-supervisor-request/1":
            raise ValueError("场景 Supervisor 请求版本无效")
        _id("submission_id", self.submission_id)
        if self.request.operation_id != self.task_spec.operation_id:
            raise ValueError("请求与任务身份不一致")
        if self.operation_context.task_id != self.task_spec.task_id:
            raise ValueError("上下文与任务身份不一致")
        if self.operation_plan.task_id != self.task_spec.task_id:
            raise ValueError("计划与任务身份不一致")


@dataclass(frozen=True, slots=True)
class ScenarioExecutionResult:
    """复用 S4 CompletionStatus 的场景结果。"""

    scenario_id: str
    semantic_version: str
    completion_status: CompletionStatus
    deliverable_bundle: DeliverableBundle | None
    quality_report: OperationQualityReport | None
    missing_condition_ids: tuple[str, ...]
    completed_scope: tuple[str, ...]
    missing_scope: tuple[str, ...]
    warning_codes: frozenset[str]
    error_code: str | None

    def __post_init__(self) -> None:
        _id("scenario_id", self.scenario_id)
        _version("semantic_version", self.semantic_version)
        if not isinstance(self.completion_status, CompletionStatus):
            raise TypeError("completion_status必须使用S4 CompletionStatus")
        for name, value in (
            ("missing_condition_ids", self.missing_condition_ids),
            ("completed_scope", self.completed_scope),
            ("missing_scope", self.missing_scope),
        ):
            if not isinstance(value, tuple):
                raise TypeError(f"{name}必须是不可变tuple")
        if not isinstance(self.warning_codes, frozenset):
            raise TypeError("warning_codes必须是不可变集合")
        if set(self.completed_scope).intersection(self.missing_scope):
            raise ValueError("完成范围与缺失范围不得重叠")


@runtime_checkable
class ScenarioSupervisorPort(Protocol):
    async def execute_scenario(
        self, request: ScenarioSupervisorRequest
    ) -> ScenarioExecutionResult:
        raise NotImplementedError


@runtime_checkable
class ScenarioQualityGate(Protocol):
    def validate(
        self, manifest: ScenarioPackManifest, result: ScenarioExecutionResult
    ) -> OperationQualityReport:
        raise NotImplementedError


@runtime_checkable
class ScenarioPackRegistry(Protocol):
    def register(self, manifest: ScenarioPackManifest) -> None: ...
    def get(self, scenario_id: str, semantic_version: str) -> ScenarioPackManifest: ...
    def list(self) -> tuple[ScenarioPackManifest, ...]: ...


__all__ = [
    "ScenarioExecutionResult",
    "ScenarioPackRegistry",
    "ScenarioQualityGate",
    "ScenarioSubmission",
    "ScenarioSupervisorPort",
    "ScenarioSupervisorRequest",
]
