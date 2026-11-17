import { z } from 'zod';
export const blockSchema = z.object({
  id: z.string(),
  page: z.number().nullable(),
  text: z.string(),
  section: z.string().nullish(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullish(),
  paragraph: z.number().nullish(),
  ocrQuality: z.number().nullish(),
});
export const structuredFactSchema = z.object({
  background_claim: z.enum(['ENTREPRENEURSHIP', 'CAREER_TRANSITION']).nullish(),
  fact_id: z.string(),
  kind: z.string(),
  value: z.string(),
  evidence: z.array(
    z.object({ block_id: z.string(), start: z.number(), end: z.number(), quote: z.string() }),
  ),
  organization: z.string().nullable(),
  title: z.string().nullable(),
  degree: z.string().nullable(),
  major: z.string().nullable(),
  start_date: z
    .object({ value: z.string(), precision: z.string(), source_text: z.string() })
    .nullable(),
  end_date: z
    .object({ value: z.string(), precision: z.string(), source_text: z.string() })
    .nullable(),
  ongoing: z.boolean().nullable(),
  is_internship: z.boolean().nullable(),
  measurement: z
    .object({
      metric: z.string().nullable(),
      unit: z.string().nullable(),
      value: z.number().nullable(),
      project_id: z.string().nullable(),
      role_level: z.number().nullable(),
      managed_team_size: z.number().nullable(),
    })
    .nullish(),
});
export const factsSchema = z.object({
  structuredFacts: z.array(structuredFactSchema).default([]),
  notApplicableGroups: z.array(z.string()).default([]),
  dictionaryVersion: z.number().nullable().optional(),
  normalizations: z
    .array(
      z.object({
        factId: z.string(),
        category: z.string(),
        original: z.string(),
        standardId: z.string().nullable(),
        canonical: z.string().nullable(),
        status: z.string(),
        dictionaryVersion: z.number(),
        quality: z.number(),
      }),
    )
    .default([]),
  candidateId: z.string(),
  resumeVersionId: z.string(),
  filename: z.string(),
  pageCount: z.number(),
  qualityScore: z.number().nullable(),
  status: z.string(),
  profile: z.object({
    name: z.string().nullable(),
    education: z.string().nullable(),
    experienceMonths: z.number().nullable(),
    targetPosition: z.string().nullable(),
  }),
  blocks: z.array(blockSchema),
  fields: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      value: z.string(),
      status: z.enum(['CONFIRMED', 'NEEDS_REVIEW', 'UNKNOWN']),
      reason: z.string().nullable(),
      evidenceIds: z.array(z.string()),
    }),
  ),
  skills: z.array(
    z.object({
      name: z.string(),
      strength: z.enum(['STRONG', 'MEDIUM', 'WEAK', 'UNKNOWN']),
      evidenceCount: z.number(),
      evidenceIds: z.array(z.string()),
    }),
  ),
  confirmedCount: z.number(),
  totalCount: z.number(),
  version: z.number(),
});
const requirementSchema = z.object({
  id: z.string(),
  label: z.string(),
  judgment: z.string(),
  quote: z.string().nullable(),
  evidenceIds: z.array(z.string()),
});
export const matchingSchema = z.object({
  specialMarks: z
    .array(
      z.object({
        key: z.string(),
        active: z.boolean(),
        visible: z.boolean(),
        reason: z.string().nullable(),
      }),
    )
    .default([]),
  resultId: z.string(),
  candidateId: z.string(),
  candidateName: z.string().nullable(),
  positionId: z.string(),
  positionName: z.string(),
  factSnapshotId: z.string(),
  configVersion: z.string(),
  contextVersion: z.string(),
  semanticSnapshotId: z.string().nullable(),
  asOfDate: z.string(),
  businessStatus: z.string(),
  scoreStatus: z.string(),
  totalScore: z.number().nullable(),
  referenceScore: z.number().nullable(),
  evidenceCoverage: z.number(),
  band: z.string().nullable(),
  reasonCodes: z.array(z.string()),
  dimensions: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      score: z.number().nullable(),
      weight: z.number(),
      evidenceCoverage: z.number(),
      requirements: z.array(requirementSchema),
    }),
  ),
  hardConditions: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      status: z.enum(['PASS', 'FAIL', 'UNKNOWN', 'NEEDS_REVIEW', 'BORDERLINE', 'OVERRIDDEN']),
      expected: z.string().nullable(),
      actual: z.string().nullable(),
      overridable: z.boolean(),
    }),
  ),
  overrides: z.array(
    z.object({
      id: z.string(),
      conditionId: z.string(),
      reason: z.string(),
      actorId: z.string(),
      createdAt: z.string(),
      action: z.string(),
      revokedOverrideId: z.string().nullable(),
    }),
  ),
  snapshotHash: z.string(),
  createdAt: z.string(),
  supersededBy: z.string().nullable(),
  highlights: z.array(z.string()),
  reviewPoints: z.array(z.string()),
  thresholds: z.array(z.number()),
  pageCount: z.number(),
  blocks: z.array(blockSchema),
});
export type HrFacts = z.infer<typeof factsSchema>;
export type HrMatching = z.infer<typeof matchingSchema>;
export const batchItemSchema = z.object({
  contentHash: z.string().nullish(),
  id: z.string(),
  filename: z.string(),
  status: z.string(),
  stage: z.string().nullable(),
  candidateId: z.string().nullable(),
  errorCode: z.string().nullable(),
  message: z.string().nullable(),
  progress: z.number(),
});
export const batchSchema = z.object({
  id: z.string(),
  positionId: z.string().nullable(),
  mode: z.enum(['MATCH', 'STORE_ONLY']),
  status: z.string(),
  version: z.number(),
  items: z.array(batchItemSchema),
  createdAt: z.string(),
  completedCount: z.number(),
  failedCount: z.number(),
  reviewCount: z.number(),
  totalCount: z.number(),
});
export const uploadPolicySchema = z.object({
  policyVersionId: z.string(),
  authorizationText: z.string(),
  formats: z.array(
    z.object({ extension: z.string(), available: z.boolean(), reason: z.string().nullable() }),
  ),
});
export async function hrRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/hr${path}`, { credentials: 'same-origin', ...init });
  const body = await response.json();
  if (!response.ok || body.code !== 'SUCCESS')
    throw new Error(`${body.message || '请求失败'}${body.traceId ? ` · ${body.traceId}` : ''}`);
  const result = schema.safeParse(body.data);
  if (!result.success) throw new Error('服务响应格式不符合约定');
  return result.data;
}
export function hrWrite<T>(path: string, schema: z.ZodType<T>, data: unknown) {
  return hrRequest(path, schema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(data),
  });
}
