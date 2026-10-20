"""运营助手面向前端的结构化交付物契约。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
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
RankingBasisV2 = Literal[
    "importance", "recency", "heat", "mixed", "evidence_order", "model_event_order"
]
_WECHAT_HOTSPOT_LABEL_PATTERNS = (
    r"\*\*[^*\n]{0,8}事实[^*\n]{0,8}\*\*",
    r"\*\*[^*\n]{0,8}影响[^*\n]{0,8}\*\*",
    r"\*\*[^*\n]{0,8}运营观察[^*\n]{0,8}\*\*",
)
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

    @model_validator(mode="after")
    def validate_platform_presentation(self) -> PlatformContentDeliverableV2:
        body = self.content.body_markdown.strip()
        if self.platform == "wechat_official_account":
            chinese_count = len(
                re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", body)
            )
            if not 3_000 <= chinese_count <= 4_000:
                raise ValueError("WECHAT_BODY_CHINESE_LENGTH_INVALID")
            lines = body.splitlines()
            if sum(line.startswith("# ") for line in lines) != 1 or sum(
                line.startswith("## ") for line in lines
            ) < 2:
                raise ValueError("WECHAT_MARKDOWN_STRUCTURE_INVALID")
            if not has_complete_wechat_hotspot_fields(body):
                raise ValueError("WECHAT_HOTSPOT_STRUCTURE_INVALID")
        elif self.platform == "xiaohongshu" and self.copy_text == "":
            paragraphs = [
                value.strip()
                for value in re.split(r"\n\s*\n", body)
                if value.strip()
            ]
            hashtags = self.content.hashtags
            if len(paragraphs) < 3:
                raise ValueError("XIAOHONGSHU_PARAGRAPHS_INVALID")
            if not 5 <= len(hashtags) <= 10 or any(
                not value.startswith("#") or len(value) < 2 for value in hashtags
            ):
                raise ValueError("XIAOHONGSHU_HASHTAGS_INVALID")
        return self


def _wechat_hotspot_fields_complete(section: str) -> bool:
    """每个热点按事实、影响、运营观察顺序给出非空正文。"""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for pattern in _WECHAT_HOTSPOT_LABEL_PATTERNS:
        match = re.search(pattern, section[cursor:])
        if match is None:
            return False
        start = cursor + match.start()
        end = cursor + match.end()
        spans.append((start, end))
        cursor = end
    for index, (_, end) in enumerate(spans):
        next_start = spans[index + 1][0] if index + 1 < len(spans) else len(section)
        meaningful = re.findall(
            r"[0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]",
            section[end:next_start],
        )
        if len(meaningful) < 8:
            return False
    return True


def has_complete_wechat_hotspot_fields(body: str) -> bool:
    """只校验公众号热点结构，供长度补写前判断是否可安全追加正文。"""
    sections = re.split(r"(?m)^##\s+", body)[1:]
    non_hotspot_titles = (
        "收束",
        "结语",
        "总结",
        "运营背景与影响",
        "内容选题方法",
        "行动启示",
    )
    hotspot_sections = [
        section
        for section in sections
        if section.splitlines()
        and not section.splitlines()[0].strip().startswith(non_hotspot_titles)
    ]
    return bool(hotspot_sections) and all(
        _wechat_hotspot_fields_complete(section) for section in hotspot_sections
    )


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


class _OperationContractV3Model(BaseModel):
    """八场景对外内容契约；内部来源闭包不进入这些模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class IndustryDigestItemV1(_OperationContractV3Model):
    rank: int = Field(ge=1)
    title: str = Field(min_length=1)
    event_summary: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    operator_insight: str = Field(min_length=1)
    occurred_at: datetime | None = None


class IndustryDigestV1(_OperationContractV3Model):
    kind: Literal["ranked_digest"] = "ranked_digest"
    topic: str = Field(min_length=1)
    time_window: str = Field(min_length=1)
    items: list[IndustryDigestItemV1] = Field(min_length=1, max_length=100)
    actual_count: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_ranks(self) -> IndustryDigestV1:
        if self.actual_count != len(self.items):
            raise ValueError("INDUSTRY_ACTUAL_COUNT_INVALID")
        if [item.rank for item in self.items] != list(range(1, len(self.items) + 1)):
            raise ValueError("INDUSTRY_RANKS_INVALID")
        return self


class ArticleSectionV1(_OperationContractV3Model):
    heading: str = Field(min_length=1)
    facts: list[str] = Field(default_factory=list)
    analysis: list[str] = Field(default_factory=list)
    operator_takeaway: str = Field(min_length=1)


class ArticleDraftV1(_OperationContractV3Model):
    kind: Literal["platform_content"] = "platform_content"
    platform: Literal["wechat_official_account", "xiaohongshu", "toutiao"]
    title: str = Field(min_length=1)
    introduction: str = Field(min_length=1)
    sections: list[ArticleSectionV1] = Field(min_length=1)
    closing: str = Field(min_length=1)
    hashtags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rendered_content(self) -> ArticleDraftV1:
        if self.platform == "wechat_official_account":
            visible = "\n".join(
                [
                    self.title,
                    self.introduction,
                    *(
                        text
                        for section in self.sections
                        for text in (
                            section.heading,
                            *section.facts,
                            *section.analysis,
                            section.operator_takeaway,
                        )
                    ),
                    self.closing,
                ]
            )
            count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", visible))
            if not 3_000 <= count <= 4_000:
                raise ValueError(f"WECHAT_BODY_CHINESE_LENGTH_INVALID:{count}")
            if self.hashtags:
                raise ValueError("WECHAT_HASHTAGS_FORBIDDEN")
        return self


class MetricDefinitionV1(_OperationContractV3Model):
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    observation_period: str = Field(min_length=1)
    purpose: str = Field(min_length=1)


class BrandPlanV1(_OperationContractV3Model):
    kind: Literal["brand_plan"] = "brand_plan"
    current_context: list[str] = Field(min_length=1)
    objectives: list[str] = Field(min_length=1)
    positioning: str = Field(min_length=1)
    audience_segments: list[dict[str, JsonValue]] = Field(min_length=1)
    value_proposition: list[str] = Field(min_length=1)
    content_pillars: list[dict[str, JsonValue]] = Field(min_length=1)
    channel_strategy: list[dict[str, JsonValue]] = Field(min_length=1)
    roadmap: list[dict[str, JsonValue]] = Field(min_length=1)
    metric_framework: list[MetricDefinitionV1] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(min_length=1)


class IpPlanV1(_OperationContractV3Model):
    kind: Literal["ip_plan"] = "ip_plan"
    ip_profile: list[str] = Field(min_length=1)
    positioning: str = Field(min_length=1)
    audience: list[dict[str, JsonValue]] = Field(min_length=1)
    differentiators: list[str] = Field(min_length=1)
    persona_rules: list[str] = Field(min_length=1)
    content_columns: list[dict[str, JsonValue]] = Field(min_length=1)
    voice_style: list[str] = Field(min_length=1)
    interaction_mechanism: list[str] = Field(min_length=1)
    growth_phases: list[dict[str, JsonValue]] = Field(min_length=1)
    metrics: list[MetricDefinitionV1] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)


class CampaignPlanV1(_OperationContractV3Model):
    kind: Literal["campaign_plan"] = "campaign_plan"
    objective: str = Field(min_length=1)
    theme: str = Field(min_length=1)
    value_proposition: str = Field(min_length=1)
    audience: list[dict[str, JsonValue]] = Field(min_length=1)
    mechanics: list[str] = Field(min_length=1)
    participant_journey: list[dict[str, JsonValue]] = Field(min_length=1)
    timeline: list[dict[str, JsonValue]] = Field(min_length=1)
    channel_plan: list[dict[str, JsonValue]] = Field(min_length=1)
    asset_checklist: list[dict[str, JsonValue]] = Field(min_length=1)
    metric_framework: list[MetricDefinitionV1] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)
    contingencies: list[str] = Field(default_factory=list)


class CalendarPeriodV1(_OperationContractV3Model):
    start_date: date
    end_date: date
    timezone: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> CalendarPeriodV1:
        if self.start_date > self.end_date:
            raise ValueError("CALENDAR_PERIOD_INVALID")
        return self


class ContentCalendarEntryV1(_OperationContractV3Model):
    publish_at: datetime
    platform: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    format: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    angle: str = Field(min_length=1)
    cta: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)


class ContentCalendarV1(_OperationContractV3Model):
    kind: Literal["content_calendar"] = "content_calendar"
    period: CalendarPeriodV1
    cadence: list[dict[str, JsonValue]] = Field(min_length=1)
    entries: list[ContentCalendarEntryV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dates(self) -> ContentCalendarV1:
        if any(
            not self.period.start_date <= item.publish_at.date() <= self.period.end_date
            for item in self.entries
        ):
            raise ValueError("CALENDAR_ENTRY_OUT_OF_RANGE")
        return self


class GrowthExperimentV1(_OperationContractV3Model):
    hypothesis: str = Field(min_length=1)
    target_segment: str = Field(min_length=1)
    design: list[str] = Field(min_length=1)
    variants: list[str] = Field(min_length=2)
    primary_metric: MetricDefinitionV1
    guardrail_metrics: list[MetricDefinitionV1] = Field(min_length=1)
    data_requirements: list[str] = Field(min_length=1)
    duration: str = Field(min_length=1)
    stopping_rule: str = Field(min_length=1)
    decision_rule: str = Field(min_length=1)
    cost_and_risk: list[str] = Field(min_length=1)


class GrowthExperimentBacklogV1(_OperationContractV3Model):
    kind: Literal["growth_experiment"] = "growth_experiment"
    business_goal: str = Field(min_length=1)
    funnel_stage: str = Field(min_length=1)
    current_problem: str = Field(min_length=1)
    experiments: list[GrowthExperimentV1] = Field(min_length=1)


class ReviewMetricV1(_OperationContractV3Model):
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    current_value: str = Field(min_length=1)
    comparison_value: str | None = None
    change: str | None = None
    data_source: str = Field(min_length=1)


class ConfirmedCauseV1(_OperationContractV3Model):
    cause: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)


class ReviewHypothesisV1(_OperationContractV3Model):
    explanation: str = Field(min_length=1)
    validation_method: str = Field(min_length=1)
    required_data: list[str] = Field(min_length=1)


class OperationReviewV1(_OperationContractV3Model):
    kind: Literal["operation_review"] = "operation_review"
    review_period: str = Field(min_length=1)
    comparison_period: str = Field(min_length=1)
    metric_table: list[ReviewMetricV1] = Field(min_length=1)
    verified_changes: list[str] = Field(default_factory=list)
    confirmed_causes: list[ConfirmedCauseV1] = Field(default_factory=list)
    hypotheses: list[ReviewHypothesisV1] = Field(default_factory=list)
    wins: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    next_actions: list[dict[str, JsonValue]] = Field(min_length=1)


OperationContentV3 = Annotated[
    IndustryDigestV1
    | ArticleDraftV1
    | BrandPlanV1
    | IpPlanV1
    | CampaignPlanV1
    | ContentCalendarV1
    | GrowthExperimentBacklogV1
    | OperationReviewV1,
    Field(discriminator="kind"),
]


class OperationDeliverableV3(_OperationContractV3Model):
    contract_version: Literal["deliverable/3"] = "deliverable/3"
    deliverable_id: str = Field(min_length=1)
    scenario: Literal[
        "industry_digest",
        "multi_platform_content",
        "brand_operation_plan",
        "ip_operation_plan",
        "campaign_plan",
        "content_calendar",
        "growth_experiment",
        "operation_review",
    ]
    platform: str | None = None
    title: str = Field(min_length=1)
    copy_text: str = Field(min_length=1)
    content: OperationContentV3
    warnings: list[WarningV2] = Field(default_factory=list)


class DeliverableSetV3(_OperationContractV3Model):
    contract_version: Literal["deliverable-set/3"] = "deliverable-set/3"
    run_id: str = Field(min_length=1)
    intent_revision: int = Field(ge=0)
    summary: DeliverySummaryV2
    deliverables: list[OperationDeliverableV3] = Field(max_length=20)
    degraded: bool = False
    warnings: list[WarningV2] = Field(default_factory=list, max_length=100)


def render_operation_content_v3(content: OperationContentV3) -> str:
    """把强类型内容确定性渲染为可复制文本，不让模型控制外层排版。"""

    if isinstance(content, ArticleDraftV1):
        sections = []
        for section in content.sections:
            parts = [f"## {section.heading}"]
            if section.facts:
                parts.extend(("### 事实", _markdown_list(section.facts)))
            if section.analysis:
                parts.extend(("### 分析", _markdown_list(section.analysis)))
            parts.extend(("### 运营建议", section.operator_takeaway))
            sections.append("\n\n".join(parts))
        parts = [f"# {content.title}", content.introduction, *sections, content.closing]
        if content.hashtags:
            parts.append(" ".join(f"#{item.lstrip('#')}" for item in content.hashtags))
        return "\n\n".join(parts)
    if isinstance(content, IndustryDigestV1):
        window_label = content.time_window
        authoritative_window = re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T.+[（(][^）)]*[，,]\s*([^）)]+)[）)]",
            window_label,
        )
        if authoritative_window:
            window_label = authoritative_window.group(1).strip()
        items = [
            " ".join(
                (
                    f"{item.rank}. **{item.title}：**",
                    item.event_summary,
                    item.why_it_matters,
                    item.operator_insight,
                )
            )
            for item in content.items
        ]
        lead = (
            f"{window_label}，{content.topic}已整理完成，"
            f"共 {content.actual_count} 条，按重要性排序："
        )
        return "\n\n".join((lead, *items))
    title = {
        "brand_plan": "品牌运营方案",
        "ip_plan": "IP 运营方案",
        "campaign_plan": "活动运营方案",
        "content_calendar": "内容日历",
        "growth_experiment": "增长实验方案",
        "operation_review": "运营复盘",
    }[content.kind]
    return f"# {title}\n\n" + _render_mapping(content.model_dump(mode="json", exclude={"kind"}))


def _markdown_list(values: list[str]) -> str:
    return "\n".join(f"- {item}" for item in values)


def _render_mapping(value: object, *, depth: int = 2) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            heading = "#" * min(depth, 6)
            parts.append(f"{heading} {key}\n\n{_render_mapping(item, depth=depth + 1)}")
        return "\n\n".join(parts)
    if isinstance(value, list):
        return "\n".join(f"- {_render_mapping(item, depth=depth + 1)}" for item in value)
    return str(value)


DeliverableSet = Annotated[
    DeliverableSetV1 | DeliverableSetV2 | DeliverableSetV3,
    Field(discriminator="contract_version"),
]


__all__ = [
    "ActionPhaseV2",
    "ActionPlanContentV2",
    "ActionPlanDeliverableV2",
    "ArticleDraftV1",
    "BrandPlanV1",
    "CampaignPlanV1",
    "CitationV1",
    "CitationV2",
    "ConfidenceV2",
    "ContentCalendarV1",
    "DeliverableSet",
    "DeliverableSetV1",
    "DeliverableSetV2",
    "DeliverableSetV3",
    "DeliverableV1",
    "DeliveryProvenanceV2",
    "DeliverySummaryV2",
    "DiagnosisContentV2",
    "DiagnosisDeliverableV2",
    "FindingV2",
    "GrowthExperimentBacklogV1",
    "IndustryDigestV1",
    "IpPlanV1",
    "MetricDefinitionV1",
    "NextActionTypeV2",
    "NextActionV2",
    "OperationContentV2",
    "OperationContentV3",
    "OperationDeliverableBaseV2",
    "OperationDeliverableV2",
    "OperationDeliverableV3",
    "OperationReviewV1",
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
    "render_operation_content_v3",
]
