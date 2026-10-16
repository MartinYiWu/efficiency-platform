export type DeliverableKindV2 =
  'ranked_digest' | 'platform_content' | 'action_plan' | 'diagnosis' | 'retrospective';

export type ConfidenceV2 = 'high' | 'medium' | 'low';
export type VerificationStatusV2 = 'verified' | 'partially_verified' | 'unverified' | 'conflicted';
export type RankingBasisV2 =
  | 'importance'
  | 'recency'
  | 'heat'
  | 'mixed'
  | 'evidence_order'
  | 'model_event_order';
export type NextActionTypeV2 =
  | 'rewrite_for_platform'
  | 'expand_item'
  | 'generate_script'
  | 'replace_candidates'
  | 'show_sources'
  | 'refine_constraints';

export interface CitationV1 {
  url: string;
  title: string | null;
  source: string | null;
}

/**
 * V1 URL 原文保留用于兼容和可读展示；只有 href 非空时才允许将其渲染为外链。
 */
export interface CitationV1ViewModel extends CitationV1 {
  href: string | null;
}

export interface DeliverableV1 {
  contract_version: 'deliverable/1';
  platform: string;
  title: string;
  body: string;
  hashtags: string[];
  format_notes: string[];
  citations: CitationV1[];
  warnings: string[];
}

export interface DeliverableSetV1 {
  contract_version: 'deliverable-set/1';
  deliverables: DeliverableV1[];
  summary: string;
  degraded: boolean;
}

export interface LegacyDeliverableViewModel extends Omit<DeliverableV1, 'citations'> {
  citations: CitationV1ViewModel[];
}

export interface CitationV2 {
  citation_id: string;
  url: string;
  title: string | null;
  source: string | null;
  published_at: string | null;
  source_type: 'api' | 'rss' | 'public_page' | 'official' | 'community';
  source_tier: 'primary' | 'secondary' | 'community';
  verification_status: VerificationStatusV2;
  supports_item_ids: string[];
  independent_source_group: string | null;
  document_id?: string | null;
  excerpt?: string | null;
  content_scope?: 'summary' | 'full' | 'platform_text' | null;
  content_hash?: string | null;
  acquisition_method?: 'api' | 'rss' | 'atom' | 'public_page' | 'cache' | null;
}

export interface RankedItemV2 {
  item_id: string;
  rank: number;
  title: string;
  occurred_at: string | null;
  summary: string;
  why_it_matters: string;
  content_angles: string[];
  metrics: string[];
  source_refs: string[];
  confidence: ConfidenceV2;
  verification_status: VerificationStatusV2;
}

export interface RankedDigestContentV2 {
  kind: 'ranked_digest';
  selection_summary: string;
  ranking_basis: RankingBasisV2;
  items: RankedItemV2[];
}

export interface PlatformContentV2 {
  kind: 'platform_content';
  body_markdown: string;
  hashtags: string[];
  format_notes: string[];
}

export interface ActionPhaseV2 {
  phase_id: string;
  title: string;
  actions: string[];
  metrics: string[];
}

export interface ActionPlanContentV2 {
  kind: 'action_plan';
  goal: string;
  audience: string;
  phases: ActionPhaseV2[];
  metrics: string[];
  assumptions: string[];
}

export interface FindingV2 {
  finding_id: string;
  title: string;
  evidence: string[];
  priority: 'high' | 'medium' | 'low';
  recommendation: string;
}

export interface DiagnosisContentV2 {
  kind: 'diagnosis';
  findings: FindingV2[];
  data_gaps: string[];
}

export interface RetrospectiveContentV2 {
  kind: 'retrospective';
  objectives: string[];
  outcomes: string[];
  gaps: string[];
  causes: string[];
  next_steps: string[];
}

export type OperationContentV2 =
  | RankedDigestContentV2
  | PlatformContentV2
  | ActionPlanContentV2
  | DiagnosisContentV2
  | RetrospectiveContentV2;

export interface WarningV2 {
  code: string;
  message: string;
}

interface OperationDeliverableBaseV2 {
  contract_version: 'deliverable/2';
  deliverable_id: string;
  platform: string;
  title: string;
  lead: string;
  citations: CitationV2[];
  copy_text: string;
  warnings: WarningV2[];
}

export interface RankedDigestDeliverableV2 extends OperationDeliverableBaseV2 {
  deliverable_kind: 'ranked_digest';
  content: RankedDigestContentV2;
}

export interface PlatformContentDeliverableV2 extends OperationDeliverableBaseV2 {
  deliverable_kind: 'platform_content';
  content: PlatformContentV2;
}

export interface ActionPlanDeliverableV2 extends OperationDeliverableBaseV2 {
  deliverable_kind: 'action_plan';
  content: ActionPlanContentV2;
}

export interface DiagnosisDeliverableV2 extends OperationDeliverableBaseV2 {
  deliverable_kind: 'diagnosis';
  content: DiagnosisContentV2;
}

export interface RetrospectiveDeliverableV2 extends OperationDeliverableBaseV2 {
  deliverable_kind: 'retrospective';
  content: RetrospectiveContentV2;
}

export type OperationDeliverableV2 =
  | RankedDigestDeliverableV2
  | PlatformContentDeliverableV2
  | ActionPlanDeliverableV2
  | DiagnosisDeliverableV2
  | RetrospectiveDeliverableV2;

export interface DeliverySummaryV2 {
  message: string;
  result_count: number;
  complete: boolean;
}

export interface DeliveryProvenanceV2 {
  source_count: number;
  verified_source_count: number;
  candidate_count: number;
  merged_event_count: number;
  retained_count: number;
  eliminated_count: number;
  collection_window_start: string | null;
  collection_window_end: string | null;
  ranking_basis: RankingBasisV2 | null;
}

export interface NextActionV2 {
  action_id: string;
  action_type: NextActionTypeV2;
  label: string;
  target_deliverable_id: string | null;
  target_item_ids: string[];
  intent_patch: Record<string, unknown>;
  requires_user_input: boolean;
}

export interface DeliverableSetV2 {
  contract_version: 'deliverable-set/2';
  run_id: string;
  intent_revision: number;
  summary: DeliverySummaryV2;
  deliverables: OperationDeliverableV2[];
  next_actions: NextActionV2[];
  provenance: DeliveryProvenanceV2 | null;
  degraded: boolean;
  warnings: WarningV2[];
}

export type OperationScenarioV3 =
  | 'industry_digest'
  | 'multi_platform_content'
  | 'brand_operation_plan'
  | 'ip_operation_plan'
  | 'campaign_plan'
  | 'content_calendar'
  | 'growth_experiment'
  | 'operation_review';

export interface MetricDefinitionV3 {
  name: string;
  definition: string;
  observation_period: string;
  purpose: string;
}

export interface RankedDigestContentV3 {
  kind: 'ranked_digest';
  topic: string;
  time_window: string;
  actual_count: number;
  items: Array<{
    rank: number;
    title: string;
    event_summary: string;
    why_it_matters: string;
    operator_insight: string;
    occurred_at: string | null;
  }>;
}

export interface PlatformContentV3 {
  kind: 'platform_content';
  platform: 'wechat_official_account' | 'xiaohongshu' | 'toutiao';
  title: string;
  introduction: string;
  sections: Array<{
    heading: string;
    facts: string[];
    analysis: string[];
    operator_takeaway: string;
  }>;
  closing: string;
  hashtags: string[];
}

export interface BrandPlanV3 {
  kind: 'brand_plan';
  current_context: string[];
  objectives: string[];
  positioning: string;
  audience_segments: Record<string, unknown>[];
  value_proposition: string[];
  content_pillars: Record<string, unknown>[];
  channel_strategy: Record<string, unknown>[];
  roadmap: Record<string, unknown>[];
  metric_framework: MetricDefinitionV3[];
  risks: string[];
  next_actions: string[];
}

export interface IpPlanV3 {
  kind: 'ip_plan';
  ip_profile: string[];
  positioning: string;
  audience: Record<string, unknown>[];
  differentiators: string[];
  persona_rules: string[];
  content_columns: Record<string, unknown>[];
  voice_style: string[];
  interaction_mechanism: string[];
  growth_phases: Record<string, unknown>[];
  metrics: MetricDefinitionV3[];
  risks: string[];
}

export interface CampaignPlanV3 {
  kind: 'campaign_plan';
  objective: string;
  theme: string;
  value_proposition: string;
  audience: Record<string, unknown>[];
  mechanics: string[];
  participant_journey: Record<string, unknown>[];
  timeline: Record<string, unknown>[];
  channel_plan: Record<string, unknown>[];
  asset_checklist: Record<string, unknown>[];
  metric_framework: MetricDefinitionV3[];
  risks: string[];
  contingencies: string[];
}

export interface ContentCalendarV3 {
  kind: 'content_calendar';
  period: { start_date: string; end_date: string; timezone: string };
  cadence: Record<string, unknown>[];
  entries: Array<{
    publish_at: string;
    platform: string;
    topic: string;
    format: string;
    objective: string;
    angle: string;
    cta: string;
    dependencies: string[];
  }>;
}

export interface GrowthExperimentV3 {
  kind: 'growth_experiment';
  business_goal: string;
  funnel_stage: string;
  current_problem: string;
  experiments: Array<{
    hypothesis: string;
    target_segment: string;
    design: string[];
    variants: string[];
    primary_metric: MetricDefinitionV3;
    guardrail_metrics: MetricDefinitionV3[];
    data_requirements: string[];
    duration: string;
    stopping_rule: string;
    decision_rule: string;
    cost_and_risk: string[];
  }>;
}

export interface OperationReviewV3 {
  kind: 'operation_review';
  review_period: string;
  comparison_period: string;
  metric_table: Array<{
    name: string;
    definition: string;
    current_value: string;
    comparison_value: string | null;
    change: string | null;
    data_source: string;
  }>;
  verified_changes: string[];
  confirmed_causes: Array<{ cause: string; evidence_refs: string[] }>;
  hypotheses: Array<{ explanation: string; validation_method: string; required_data: string[] }>;
  wins: string[];
  issues: string[];
  data_gaps: string[];
  next_actions: Record<string, unknown>[];
}

export type OperationContentV3 =
  | RankedDigestContentV3
  | PlatformContentV3
  | BrandPlanV3
  | IpPlanV3
  | CampaignPlanV3
  | ContentCalendarV3
  | GrowthExperimentV3
  | OperationReviewV3;

export interface OperationDeliverableV3 {
  contract_version: 'deliverable/3';
  deliverable_id: string;
  scenario: OperationScenarioV3;
  platform: string | null;
  title: string;
  copy_text: string;
  content: OperationContentV3;
  warnings: WarningV2[];
}

export interface DeliverableSetV3 {
  contract_version: 'deliverable-set/3';
  run_id: string;
  intent_revision: number;
  summary: DeliverySummaryV2;
  deliverables: OperationDeliverableV3[];
  degraded: boolean;
  warnings: WarningV2[];
}

export type DeliverableSetDto = DeliverableSetV1 | DeliverableSetV2 | DeliverableSetV3;

export interface LegacyDeliveryViewModel {
  kind: 'legacy';
  summary: string;
  degraded: boolean;
  deliverables: LegacyDeliverableViewModel[];
}

export type OperationDeliverableViewModel =
  | {
      kind: 'ranked_digest';
      id: string;
      platform: string;
      title: string;
      lead: string;
      citations: CitationV2[];
      copyText: string;
      warnings: WarningV2[];
      content: RankedDigestContentV2;
    }
  | {
      kind: 'platform_content';
      id: string;
      platform: string;
      title: string;
      lead: string;
      citations: CitationV2[];
      copyText: string;
      warnings: WarningV2[];
      content: PlatformContentV2;
    }
  | {
      kind: 'action_plan';
      id: string;
      platform: string;
      title: string;
      lead: string;
      citations: CitationV2[];
      copyText: string;
      warnings: WarningV2[];
      content: ActionPlanContentV2;
    }
  | {
      kind: 'diagnosis';
      id: string;
      platform: string;
      title: string;
      lead: string;
      citations: CitationV2[];
      copyText: string;
      warnings: WarningV2[];
      content: DiagnosisContentV2;
    }
  | {
      kind: 'retrospective';
      id: string;
      platform: string;
      title: string;
      lead: string;
      citations: CitationV2[];
      copyText: string;
      warnings: WarningV2[];
      content: RetrospectiveContentV2;
    };

export type RankedDigestViewModel = Extract<
  OperationDeliverableViewModel,
  { kind: 'ranked_digest' }
>;
export type PlatformContentViewModel = Extract<
  OperationDeliverableViewModel,
  { kind: 'platform_content' }
>;
export type ActionPlanViewModel = Extract<OperationDeliverableViewModel, { kind: 'action_plan' }>;
export type DiagnosisViewModel = Extract<OperationDeliverableViewModel, { kind: 'diagnosis' }>;
export type RetrospectiveViewModel = Extract<
  OperationDeliverableViewModel,
  { kind: 'retrospective' }
>;

export type DeliveryProvenanceViewModel = DeliveryProvenanceV2;

export interface DeliverySetV2ViewModel {
  kind: 'v2';
  runId: string;
  intentRevision: number;
  summary: DeliverySummaryV2;
  deliverables: OperationDeliverableViewModel[];
  nextActions: NextActionV2[];
  provenance: DeliveryProvenanceViewModel | null;
  degraded: boolean;
  warnings: WarningV2[];
  citationsById: Record<string, CitationV2>;
}

export interface DeliverySetV3ViewModel {
  kind: 'v3';
  runId: string;
  intentRevision: number;
  summary: DeliverySummaryV2;
  deliverables: OperationDeliverableV3[];
  degraded: boolean;
  warnings: WarningV2[];
}

export type OperationDeliveryViewModel =
  | LegacyDeliveryViewModel
  | DeliverySetV2ViewModel
  | DeliverySetV3ViewModel;
