"""意图与研究闭环冻结的中立端口签名。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from efficiency_platform_agent.contracts.intent_v2 import (
    BudgetLeaseReferenceV2,
    CapabilityCatalogSnapshot,
    CapabilityPlanV2,
    IntentContextV2,
    IntentDecision,
    IntentFrameV2,
    IntentPatchV2,
    PermissionSnapshotV2,
    TrustedMessageV2,
    ValidatedIntentPatchV2,
)
from efficiency_platform_agent.contracts.research_evidence_v2 import EvidenceSnapshotV2
from efficiency_platform_agent.contracts.research_sources_v2 import (
    DiscoveryBatchV2,
    DiscoveryRequestV2,
    ExtractedDocumentV2,
    FetchedContentV2,
    FetchRequestV2,
    SourceDescriptorV2,
    SourceRuntimeContextV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    BudgetSnapshotV2,
    CollectionHistoryV2,
    CollectionPlanV2,
    DeliveryDraftV2,
    OutputDecisionV2,
    QualityReportV2,
    ResearchBriefV2,
    ResearchOutcomeV2,
    ResearchPolicySnapshotV2,
    ResearchRuntimeContextV2,
    TrustedResearchContextV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import (
    ResolvedTimeWindow,
    TemporalExpression,
)


class IntentInterpreterV2(Protocol):
    async def interpret(
        self,
        text: str,
        context: IntentContextV2,
        previous: IntentFrameV2 | None,
        catalog: CapabilityCatalogSnapshot,
        lease: BudgetLeaseReferenceV2,
    ) -> IntentPatchV2: ...


class IntentStateReducer(Protocol):
    def apply(
        self,
        previous: IntentFrameV2 | None,
        patch: ValidatedIntentPatchV2,
        trusted_message: TrustedMessageV2,
    ) -> IntentFrameV2: ...


class TemporalResolver(Protocol):
    def resolve(
        self,
        expression: TemporalExpression,
        anchor: datetime,
        timezone: str,
    ) -> ResolvedTimeWindow: ...


class CapabilityBinder(Protocol):
    def bind(
        self,
        frame: IntentFrameV2,
        catalog: CapabilityCatalogSnapshot,
        permissions: PermissionSnapshotV2,
    ) -> CapabilityPlanV2: ...


class IntentDecisionPolicy(Protocol):
    def decide(
        self, frame: IntentFrameV2, binding: CapabilityPlanV2
    ) -> IntentDecision: ...


class ResearchBriefBuilder(Protocol):
    def build(
        self,
        frame: IntentFrameV2,
        trusted_context: TrustedResearchContextV2,
        policy_snapshot: ResearchPolicySnapshotV2,
    ) -> ResearchBriefV2: ...


class SourceRegistry(Protocol):
    def list_available(
        self, context: SourceRuntimeContextV2, brief: ResearchBriefV2
    ) -> tuple[SourceDescriptorV2, ...]: ...


class SourceProvider(Protocol):
    async def discover(self, request: DiscoveryRequestV2) -> DiscoveryBatchV2: ...


class DocumentProvider(Protocol):
    async def fetch(self, request: FetchRequestV2) -> FetchedContentV2: ...


class DocumentExtractor(Protocol):
    def extract(self, content: FetchedContentV2) -> ExtractedDocumentV2: ...


class QualityEvaluator(Protocol):
    def evaluate(
        self,
        brief: ResearchBriefV2,
        evidence_snapshot: EvidenceSnapshotV2,
        policy: ResearchPolicySnapshotV2,
    ) -> QualityReportV2: ...


class CollectionPlanner(Protocol):
    async def plan_gaps(
        self,
        brief: ResearchBriefV2,
        quality: QualityReportV2,
        history: CollectionHistoryV2,
        budget: BudgetSnapshotV2,
    ) -> CollectionPlanV2: ...


class OutputVerifier(Protocol):
    async def verify(
        self,
        delivery_draft: DeliveryDraftV2,
        evidence_snapshot: EvidenceSnapshotV2,
        policy: ResearchPolicySnapshotV2,
    ) -> OutputDecisionV2: ...


class ResearchServiceV2(Protocol):
    async def research(
        self, brief: ResearchBriefV2, runtime_context: ResearchRuntimeContextV2
    ) -> ResearchOutcomeV2: ...


__all__ = [
    "CapabilityBinder",
    "CollectionPlanner",
    "DocumentExtractor",
    "DocumentProvider",
    "IntentDecisionPolicy",
    "IntentInterpreterV2",
    "IntentStateReducer",
    "OutputVerifier",
    "QualityEvaluator",
    "ResearchBriefBuilder",
    "ResearchServiceV2",
    "SourceProvider",
    "SourceRegistry",
    "TemporalResolver",
]
