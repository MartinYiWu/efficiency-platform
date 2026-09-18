export type DeliverableKindV2 =
  'ranked_digest' | 'platform_content' | 'action_plan' | 'diagnosis' | 'retrospective';

export type ConfidenceV2 = 'high' | 'medium' | 'low';
export type VerificationStatusV2 = 'verified' | 'partially_verified' | 'unverified' | 'conflicted';
export type RankingBasisV2 = 'importance' | 'recency' | 'heat' | 'mixed';
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

export type DeliverableSetDto = DeliverableSetV1 | DeliverableSetV2;

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

export type OperationDeliveryViewModel = LegacyDeliveryViewModel | DeliverySetV2ViewModel;
