"""S2 与运营领域之间的窄 Protocol，仅定义职责不提供实现。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .deliverables import DeliverableBundle
from .evidence import EvidencePack
from .planning import OperationPlan
from .profiles import OperationContext
from .task import OperationRequest, OperationTaskSpec


@runtime_checkable
class S2OperationIntentPort(Protocol):
    def normalize(self, request: OperationRequest) -> OperationTaskSpec: ...


@runtime_checkable
class S2OperationPlanningPort(Protocol):
    def build_plan(
        self, task: OperationTaskSpec, context: OperationContext
    ) -> OperationPlan: ...


@runtime_checkable
class S2OperationAssemblyPort(Protocol):
    def assemble(
        self, task: OperationTaskSpec, plan: OperationPlan, evidence: EvidencePack
    ) -> DeliverableBundle: ...


__all__ = [
    "S2OperationAssemblyPort",
    "S2OperationIntentPort",
    "S2OperationPlanningPort",
]
