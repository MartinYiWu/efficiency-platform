import { z } from 'zod';
import type {
  ActionPhaseV2,
  ActionPlanContentV2,
  ActionPlanDeliverableV2,
  CitationV1,
  CitationV2,
  DeliveryProvenanceV2,
  DeliverySummaryV2,
  DeliverableSetDto,
  DeliverableSetV1,
  DeliverableSetV2,
  DeliverableV1,
  DiagnosisContentV2,
  DiagnosisDeliverableV2,
  FindingV2,
  NextActionV2,
  OperationDeliverableV2,
  PlatformContentDeliverableV2,
  PlatformContentV2,
  RankedDigestContentV2,
  RankedDigestDeliverableV2,
  RankedItemV2,
  RetrospectiveContentV2,
  RetrospectiveDeliverableV2,
  WarningV2,
} from './model';

function isCredentialFreeHttpsUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (
      url.protocol === 'https:' &&
      url.hostname.length > 0 &&
      url.username.length === 0 &&
      url.password.length === 0
    );
  } catch {
    return false;
  }
}

const httpsUrlSchema = z
  .url()
  .refine(isCredentialFreeHttpsUrl, '来源必须是无凭据且带主机名的 HTTPS URL');
const utcDateTimeSchema = z
  .string()
  .datetime({ offset: true })
  .refine((value) => value.endsWith('Z') || value.endsWith('+00:00'), '时间必须使用 UTC');
const verificationStatusSchema = z.enum([
  'verified',
  'partially_verified',
  'unverified',
  'conflicted',
]);
const rankingBasisSchema = z.enum(['importance', 'recency', 'heat', 'mixed']);
const warningV2Schema: z.ZodType<WarningV2> = z
  .object({
    code: z.string().min(1).max(100),
    message: z.string().min(1).max(1_000),
  })
  .strict();
const citationV1Schema: z.ZodType<CitationV1> = z
  .object({
    url: z.string().min(1).max(4_000),
    title: z.string().max(500).nullable(),
    source: z.string().max(500).nullable(),
  })
  .strict();
const deliverableV1Schema: z.ZodType<DeliverableV1> = z
  .object({
    contract_version: z.literal('deliverable/1'),
    platform: z.string().min(1).max(128),
    title: z.string().min(1).max(500),
    body: z.string().min(1).max(100_000),
    hashtags: z.array(z.string()),
    format_notes: z.array(z.string()),
    citations: z.array(citationV1Schema),
    warnings: z.array(z.string()),
  })
  .strict();
export const deliverableSetV1Schema: z.ZodType<DeliverableSetV1> = z
  .object({
    contract_version: z.literal('deliverable-set/1'),
    deliverables: z.array(deliverableV1Schema),
    summary: z.string().min(1).max(10_000),
    degraded: z.boolean(),
  })
  .strict();

export const citationV2Schema: z.ZodType<CitationV2> = z
  .object({
    citation_id: z.string(),
    url: httpsUrlSchema,
    title: z.string().nullable(),
    source: z.string().nullable(),
    published_at: z.string().nullable(),
    source_type: z.enum(['api', 'rss', 'public_page', 'official', 'community']),
    source_tier: z.enum(['primary', 'secondary', 'community']),
    verification_status: verificationStatusSchema,
    supports_item_ids: z.array(z.string()).max(100),
    independent_source_group: z.string().nullable(),
  })
  .strict();
const rankedItemV2Schema: z.ZodType<RankedItemV2> = z
  .object({
    item_id: z.string(),
    rank: z.number().int().min(1).max(100),
    title: z.string().min(1).max(500),
    occurred_at: z.string().nullable(),
    summary: z.string().min(1).max(2_000),
    why_it_matters: z.string().min(1).max(1_000),
    content_angles: z.array(z.string()).max(10),
    metrics: z.array(z.string()).max(20),
    source_refs: z.array(z.string()).max(20),
    confidence: z.enum(['high', 'medium', 'low']),
    verification_status: verificationStatusSchema,
  })
  .strict();
const rankedDigestContentV2Schema = z
  .object({
    kind: z.literal('ranked_digest'),
    selection_summary: z.string().min(1).max(2_000),
    ranking_basis: rankingBasisSchema,
    items: z.array(rankedItemV2Schema).min(1).max(100),
  })
  .strict() satisfies z.ZodType<RankedDigestContentV2>;
const platformContentV2Schema = z
  .object({
    kind: z.literal('platform_content'),
    body_markdown: z.string().min(1).max(100_000),
    hashtags: z.array(z.string()).max(100),
    format_notes: z.array(z.string()).max(50),
  })
  .strict() satisfies z.ZodType<PlatformContentV2>;
const actionPhaseV2Schema: z.ZodType<ActionPhaseV2> = z
  .object({
    phase_id: z.string(),
    title: z.string(),
    actions: z.array(z.string()).min(1).max(50),
    metrics: z.array(z.string()).max(20),
  })
  .strict();
const actionPlanContentV2Schema = z
  .object({
    kind: z.literal('action_plan'),
    goal: z.string(),
    audience: z.string(),
    phases: z.array(actionPhaseV2Schema).min(1).max(20),
    metrics: z.array(z.string()).max(50),
    assumptions: z.array(z.string()).max(50),
  })
  .strict() satisfies z.ZodType<ActionPlanContentV2>;
const findingV2Schema: z.ZodType<FindingV2> = z
  .object({
    finding_id: z.string(),
    title: z.string(),
    evidence: z.array(z.string()).max(50),
    priority: z.enum(['high', 'medium', 'low']),
    recommendation: z.string(),
  })
  .strict();
const diagnosisContentV2Schema = z
  .object({
    kind: z.literal('diagnosis'),
    findings: z.array(findingV2Schema).min(1).max(50),
    data_gaps: z.array(z.string()).max(50),
  })
  .strict() satisfies z.ZodType<DiagnosisContentV2>;
const retrospectiveContentV2Schema = z
  .object({
    kind: z.literal('retrospective'),
    objectives: z.array(z.string()).min(1).max(50),
    outcomes: z.array(z.string()).max(50),
    gaps: z.array(z.string()).max(50),
    causes: z.array(z.string()).max(50),
    next_steps: z.array(z.string()).min(1).max(50),
  })
  .strict() satisfies z.ZodType<RetrospectiveContentV2>;
export const operationContentV2Schema = z.discriminatedUnion('kind', [
  rankedDigestContentV2Schema,
  platformContentV2Schema,
  actionPlanContentV2Schema,
  diagnosisContentV2Schema,
  retrospectiveContentV2Schema,
]);

const operationDeliverableBaseV2Schema = z.object({
  contract_version: z.literal('deliverable/2'),
  deliverable_id: z.string().min(1).max(100),
  platform: z.string().min(1).max(100),
  title: z.string().min(1).max(500),
  lead: z.string().min(1).max(2_000),
  citations: z.array(citationV2Schema).max(100),
  copy_text: z.string().min(1).max(100_000),
  warnings: z.array(warningV2Schema).max(100),
});
const rankedDigestDeliverableV2Schema = operationDeliverableBaseV2Schema
  .extend({
    deliverable_kind: z.literal('ranked_digest'),
    content: rankedDigestContentV2Schema,
  })
  .strict() satisfies z.ZodType<RankedDigestDeliverableV2>;
const platformContentDeliverableV2Schema = operationDeliverableBaseV2Schema
  .extend({
    deliverable_kind: z.literal('platform_content'),
    content: platformContentV2Schema,
  })
  .strict() satisfies z.ZodType<PlatformContentDeliverableV2>;
const actionPlanDeliverableV2Schema = operationDeliverableBaseV2Schema
  .extend({
    deliverable_kind: z.literal('action_plan'),
    content: actionPlanContentV2Schema,
  })
  .strict() satisfies z.ZodType<ActionPlanDeliverableV2>;
const diagnosisDeliverableV2Schema = operationDeliverableBaseV2Schema
  .extend({
    deliverable_kind: z.literal('diagnosis'),
    content: diagnosisContentV2Schema,
  })
  .strict() satisfies z.ZodType<DiagnosisDeliverableV2>;
const retrospectiveDeliverableV2Schema = operationDeliverableBaseV2Schema
  .extend({
    deliverable_kind: z.literal('retrospective'),
    content: retrospectiveContentV2Schema,
  })
  .strict() satisfies z.ZodType<RetrospectiveDeliverableV2>;
export const operationDeliverableV2Schema = z.discriminatedUnion('deliverable_kind', [
  rankedDigestDeliverableV2Schema,
  platformContentDeliverableV2Schema,
  actionPlanDeliverableV2Schema,
  diagnosisDeliverableV2Schema,
  retrospectiveDeliverableV2Schema,
]) satisfies z.ZodType<OperationDeliverableV2>;
const deliverySummaryV2Schema: z.ZodType<DeliverySummaryV2> = z
  .object({
    message: z.string(),
    result_count: z.number().int().min(0),
    complete: z.boolean(),
  })
  .strict();
const deliveryProvenanceV2Schema: z.ZodType<DeliveryProvenanceV2> = z
  .object({
    source_count: z.number().int().min(0),
    verified_source_count: z.number().int().min(0),
    candidate_count: z.number().int().min(0),
    merged_event_count: z.number().int().min(0),
    retained_count: z.number().int().min(0),
    eliminated_count: z.number().int().min(0),
    collection_window_start: utcDateTimeSchema.nullable(),
    collection_window_end: utcDateTimeSchema.nullable(),
    ranking_basis: rankingBasisSchema.nullable(),
  })
  .strict()
  .superRefine((value, context) => {
    if (value.verified_source_count > value.source_count) {
      context.addIssue({ code: 'custom', message: '已核验来源数不得超过来源总数' });
    }
    const { collection_window_start: start, collection_window_end: end } = value;
    if ((start === null) !== (end === null)) {
      context.addIssue({ code: 'custom', message: '收集时间窗起止必须同时为空或同时存在' });
    }
    if (start !== null && end !== null && start >= end) {
      context.addIssue({ code: 'custom', message: '收集时间窗开始时间必须早于结束时间' });
    }
  });
const jsonValueSchema: z.ZodType<unknown> = z.lazy(() =>
  z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.null(),
    z.array(jsonValueSchema),
    z.record(z.string(), jsonValueSchema),
  ]),
);
const jsonRecordSchema = z
  .record(z.string(), jsonValueSchema)
  .refine((value) => Object.keys(value).length <= 50, 'intent_patch 最多包含 50 个顶层键');
const nextActionV2Schema: z.ZodType<NextActionV2> = z
  .object({
    action_id: z.string(),
    action_type: z.enum([
      'rewrite_for_platform',
      'expand_item',
      'generate_script',
      'replace_candidates',
      'show_sources',
      'refine_constraints',
    ]),
    label: z.string(),
    target_deliverable_id: z.string().nullable(),
    target_item_ids: z.array(z.string()),
    intent_patch: jsonRecordSchema,
    requires_user_input: z.boolean(),
  })
  .strict();
export const deliverableSetV2Schema: z.ZodType<DeliverableSetV2> = z
  .object({
    contract_version: z.literal('deliverable-set/2'),
    run_id: z.string(),
    intent_revision: z.number().int().min(0),
    summary: deliverySummaryV2Schema,
    deliverables: z.array(operationDeliverableV2Schema).max(20),
    next_actions: z.array(nextActionV2Schema).max(20),
    provenance: deliveryProvenanceV2Schema.nullable(),
    degraded: z.boolean(),
    warnings: z.array(warningV2Schema).max(100),
  })
  .strict();

export function parseDeliverableSet(value: unknown): DeliverableSetDto | null {
  if (!value || typeof value !== 'object' || !('contract_version' in value)) return null;
  const version = (value as { contract_version?: unknown }).contract_version;
  const result =
    version === 'deliverable-set/1'
      ? deliverableSetV1Schema.safeParse(value)
      : version === 'deliverable-set/2'
        ? deliverableSetV2Schema.safeParse(value)
        : null;
  return result?.success ? result.data : null;
}
