"""运营助手面向前端的结构化交付物契约。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from efficiency_platform_agent.contracts.stream_events import JsonValue


class CitationV1(BaseModel):
    """交付物中可追溯的来源引用。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(min_length=1, max_length=4_000, description="来源 URL。")
    title: str | None = Field(default=None, max_length=500, description="来源标题。")
    source: str | None = Field(default=None, max_length=500, description="来源名称。")


class DeliverableV1(BaseModel):
    """一个可直接展示或复制的单平台运营成品。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["deliverable/1"] = Field(
        default="deliverable/1", description="交付物契约版本。"
    )
    platform: str = Field(min_length=1, max_length=128, description="目标平台。")
    title: str = Field(min_length=1, max_length=500, description="交付物标题。")
    body: str = Field(min_length=1, max_length=100_000, description="交付物正文。")
    hashtags: list[str] = Field(default_factory=list, description="平台标签。")
    format_notes: list[str] = Field(default_factory=list, description="平台格式说明。")
    citations: list[CitationV1] = Field(default_factory=list, description="来源引用。")
    warnings: list[str] = Field(default_factory=list, description="降级或质量提醒。")


class DeliverableSetV1(BaseModel):
    """一次运营任务的结构化交付物集合。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["deliverable-set/1"] = Field(
        default="deliverable-set/1", description="交付物集合契约版本。"
    )
    deliverables: list[DeliverableV1] = Field(description="独立的平台交付物列表。")
    summary: str = Field(min_length=1, max_length=10_000, description="任务总结。")
    degraded: bool = Field(default=False, description="是否存在部分失败或降级。")


class _OperationContractV2Model(BaseModel):
    """V2 运营交付契约的统一失败关闭与冻结基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


ConfidenceV2 = Literal["high", "medium", "low"]
VerificationStatusV2 = Literal[
    "verified", "partially_verified", "unverified", "conflicted"
]
RankingBasisV2 = Literal["importance", "recency", "heat", "mixed", "evidence_order"]
NextActionTypeV2 = Literal[
    "rewrite_for_platform",
    "expand_item",
    "generate_script",
    "replace_candidates",
    "show_sources",
    "refine_constraints",
]


class CitationV2(_OperationContractV2Model):
    """可关联到具体候选条目的 V2 来源引用。"""

    citation_id: str
    url: str
    title: str | None = None
    source: str | None = None
    published_at: str | None = None
    source_type: Literal["api", "rss", "public_page", "official", "community"]
    source_tier: Literal["primary", "secondary", "community"]
    verification_status: VerificationStatusV2
    supports_item_ids: list[str] = Field(default_factory=list, max_length=100)
    independent_source_group: str | None = None
    document_id: str | None = Field(default=None, max_length=128)
    excerpt: str | None = Field(default=None, max_length=2_000)
    content_scope: Literal["summary", "full", "platform_text"] | None = None
    content_hash: str | None = Field(default=None, min_length=16, max_length=128)
    acquisition_method: Literal["api", "rss", "atom", "public_page", "cache"] | None = (
        None
    )


class RankedItemV2(_OperationContractV2Model):
    """排名摘要中的一个类型化候选条目。"""

    item_id: str
    rank: int = Field(ge=1, le=100)
    title: str = Field(min_length=1, max_length=500)
    occurred_at: str | None = None
    summary: str = Field(min_length=1, max_length=2_000)
    why_it_matters: str = Field(min_length=1, max_length=1_000)
    content_angles: list[str] = Field(default_factory=list, max_length=10)
    metrics: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    confidence: ConfidenceV2
    verification_status: VerificationStatusV2


class RankedDigestContentV2(_OperationContractV2Model):
    """经过筛选和排序的研究摘要内容。"""

    kind: Literal["ranked_digest"] = "ranked_digest"
    selection_summary: str = Field(min_length=1, max_length=2_000)
    ranking_basis: RankingBasisV2
    items: list[RankedItemV2] = Field(min_length=1, max_length=100)


class PlatformContentV2(_OperationContractV2Model):
    """可直接面向指定平台使用的内容。"""

    kind: Literal["platform_content"] = "platform_content"
    body_markdown: str = Field(min_length=1, max_length=100_000)
    hashtags: list[str] = Field(default_factory=list, max_length=100)
    format_notes: list[str] = Field(default_factory=list, max_length=50)


class ActionPhaseV2(_OperationContractV2Model):
    """行动方案中的一个实施阶段。"""

    phase_id: str
    title: str
    actions: list[str] = Field(min_length=1, max_length=50)
    metrics: list[str] = Field(default_factory=list, max_length=20)


class ActionPlanContentV2(_OperationContractV2Model):
    """面向运营执行的分阶段行动方案。"""

    kind: Literal["action_plan"] = "action_plan"
    goal: str
    audience: str
    phases: list[ActionPhaseV2] = Field(min_length=1, max_length=20)
    metrics: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=50)


class FindingV2(_OperationContractV2Model):
    """诊断内容中的一个问题与建议。"""

    finding_id: str
    title: str
    evidence: list[str] = Field(default_factory=list, max_length=50)
    priority: Literal["high", "medium", "low"]
    recommendation: str


class DiagnosisContentV2(_OperationContractV2Model):
    """运营质量诊断内容。"""

    kind: Literal["diagnosis"] = "diagnosis"
    findings: list[FindingV2] = Field(min_length=1, max_length=50)
    data_gaps: list[str] = Field(default_factory=list, max_length=50)


class RetrospectiveContentV2(_OperationContractV2Model):
    """运营结果复盘内容。"""

    kind: Literal["retrospective"] = "retrospective"
    objectives: list[str] = Field(min_length=1, max_length=50)
    outcomes: list[str] = Field(default_factory=list, max_length=50)
    gaps: list[str] = Field(default_factory=list, max_length=50)
    causes: list[str] = Field(default_factory=list, max_length=50)
    next_steps: list[str] = Field(min_length=1, max_length=50)


OperationContentV2 = Annotated[
    RankedDigestContentV2
    | PlatformContentV2
    | ActionPlanContentV2
    | DiagnosisContentV2
    | RetrospectiveContentV2,
    Field(discriminator="kind"),
]


class WarningV2(_OperationContractV2Model):
    """面向用户的结构化降级或质量提醒。"""

    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1_000)


class OperationDeliverableBaseV2(_OperationContractV2Model):
    """所有 V2 运营交付物共享的展示字段。"""

    contract_version: Literal["deliverable/2"] = "deliverable/2"
    deliverable_id: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    lead: str = Field(min_length=1, max_length=2_000)
    citations: list[CitationV2] = Field(default_factory=list, max_length=100)
    copy_text: str = Field(min_length=1, max_length=100_000)
    warnings: list[WarningV2] = Field(default_factory=list, max_length=100)


class RankedDigestDeliverableV2(OperationDeliverableBaseV2):
    """排名摘要交付物。"""

    deliverable_kind: Literal["ranked_digest"] = "ranked_digest"
    content: RankedDigestContentV2


class PlatformContentDeliverableV2(OperationDeliverableBaseV2):
    """平台内容交付物。"""

    deliverable_kind: Literal["platform_content"] = "platform_content"
    content: PlatformContentV2


class ActionPlanDeliverableV2(OperationDeliverableBaseV2):
    """行动方案交付物。"""

    deliverable_kind: Literal["action_plan"] = "action_plan"
    content: ActionPlanContentV2


class DiagnosisDeliverableV2(OperationDeliverableBaseV2):
    """质量诊断交付物。"""

    deliverable_kind: Literal["diagnosis"] = "diagnosis"
    content: DiagnosisContentV2


class RetrospectiveDeliverableV2(OperationDeliverableBaseV2):
    """运营复盘交付物。"""

    deliverable_kind: Literal["retrospective"] = "retrospective"
    content: RetrospectiveContentV2


OperationDeliverableV2 = Annotated[
    RankedDigestDeliverableV2
    | PlatformContentDeliverableV2
    | ActionPlanDeliverableV2
    | DiagnosisDeliverableV2
    | RetrospectiveDeliverableV2,
    Field(discriminator="deliverable_kind"),
]


class DeliverySummaryV2(_OperationContractV2Model):
    """面向用户的 V2 交付完成摘要。"""

    message: str
    result_count: int = Field(ge=0)
    complete: bool


class DeliveryProvenanceV2(_OperationContractV2Model):
    """研究收集与筛选过程的可审计计数和时间窗。"""

    source_count: int = Field(ge=0)
    verified_source_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    merged_event_count: int = Field(ge=0)
    retained_count: int = Field(ge=0)
    eliminated_count: int = Field(ge=0)
    collection_window_start: datetime | None = None
    collection_window_end: datetime | None = None
    ranking_basis: RankingBasisV2 | None = None

    @model_validator(mode="after")
    def validate_invariants(self) -> DeliveryProvenanceV2:
        """校验来源计数和 UTC 收集时间窗不变量。"""

        if self.verified_source_count > self.source_count:
            raise ValueError("已核验来源数不得超过来源总数")
        start = self.collection_window_start
        end = self.collection_window_end
        if (start is None) != (end is None):
            raise ValueError("收集时间窗起止必须同时为空或同时存在")
        if start is None or end is None:
            return self
        if start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0):
            raise ValueError("收集时间窗必须使用 UTC aware datetime")
        if start >= end:
            raise ValueError("收集时间窗开始时间必须早于结束时间")
        return self


class NextActionV2(_OperationContractV2Model):
    """只生成下一轮输入、不自动执行的建议动作。"""

    action_id: str
    action_type: NextActionTypeV2
    label: str
    target_deliverable_id: str | None = None
    target_item_ids: list[str] = Field(default_factory=list)
    intent_patch: dict[str, JsonValue] = Field(default_factory=dict, max_length=50)
    requires_user_input: bool


class DeliverableSetV2(_OperationContractV2Model):
    """一次运营任务的完整 V2 结构化交付集合。"""

    contract_version: Literal["deliverable-set/2"] = "deliverable-set/2"
    run_id: str
    intent_revision: int = Field(ge=0)
    summary: DeliverySummaryV2
    deliverables: list[OperationDeliverableV2] = Field(max_length=20)
    next_actions: list[NextActionV2] = Field(default_factory=list, max_length=20)
    provenance: DeliveryProvenanceV2 | None = None
    degraded: bool = False
    warnings: list[WarningV2] = Field(default_factory=list, max_length=100)


DeliverableSet = Annotated[
    DeliverableSetV1 | DeliverableSetV2,
    Field(discriminator="contract_version"),
]


__all__ = [
    "ActionPhaseV2",
    "ActionPlanContentV2",
    "ActionPlanDeliverableV2",
    "CitationV1",
    "CitationV2",
    "ConfidenceV2",
    "DeliverableSet",
    "DeliverableSetV1",
    "DeliverableSetV2",
    "DeliverableV1",
    "DeliveryProvenanceV2",
    "DeliverySummaryV2",
    "DiagnosisContentV2",
    "DiagnosisDeliverableV2",
    "FindingV2",
    "NextActionTypeV2",
    "NextActionV2",
    "OperationContentV2",
    "OperationDeliverableBaseV2",
    "OperationDeliverableV2",
    "PlatformContentDeliverableV2",
    "PlatformContentV2",
    "RankedDigestContentV2",
    "RankedDigestDeliverableV2",
    "RankedItemV2",
    "RankingBasisV2",
    "RetrospectiveContentV2",
    "RetrospectiveDeliverableV2",
    "VerificationStatusV2",
    "WarningV2",
]
