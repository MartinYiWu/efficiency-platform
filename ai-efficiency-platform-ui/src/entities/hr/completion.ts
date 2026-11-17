import { z } from 'zod';
import { factsSchema } from './index';
import { ruleSchema, criterionSchema } from '../../features/hr-position-draft/model';
export const talentSummarySchema = z.object({
  candidateId: z.string(),
  name: z.string().nullable(),
  education: z.string().nullable(),
  experienceMonths: z.number().nullable(),
  skills: z.array(z.string()),
  updatedAt: z.string(),
  expiresAt: z.string(),
  olderThan30Days: z.boolean(),
  expiringWithin30Days: z.boolean(),
  snippet: z.string().nullable().optional(),
  retrievalRelevance: z.number().nullable().optional(),
});
export const questionSchema = z.object({
  id: z.string(),
  layer: z.number(),
  title: z.string(),
  purpose: z.string(),
  answerPoints: z.array(z.string()),
  followUps: z.array(z.string()),
  references: z.object({
    excellent: z.string(),
    qualified: z.string(),
    needsVerification: z.string(),
  }),
  sourceType: z.string(),
  sourceIds: z.array(z.string()),
  minutes: z.number(),
  dimension: z.string().nullable(),
});
export const interviewSchema = z.object({
  id: z.string(),
  candidateId: z.string(),
  positionId: z.string(),
  version: z.number(),
  status: z.string(),
  targetMinutes: z.number(),
  estimatedMinutes: z.number(),
  questions: z.array(questionSchema),
  resumeSections: z.array(z.object({ kind: z.string(), text: z.string() })).default([]),
  insufficientLayers: z.array(z.number()),
  createdAt: z.string(),
});
export const profileSchema = z.object({
  candidateId: z.string(),
  sources: z.array(
    z.object({
      candidateId: z.string(),
      departmentId: z.string(),
      facts: factsSchema,
      expiresAt: z.string(),
      consentPolicyId: z.string(),
      candidateVersion: z.number(),
    }),
  ),
  interviewSets: z.array(interviewSchema),
  mergeId: z.string().nullable(),
  mergeVersion: z.number().nullable(),
  revocableUntil: z.string().nullable(),
});
export const guideSchema = z.object({
  setId: z.string(),
  version: z.number(),
  positionName: z.string(),
  questions: z.array(questionSchema),
  resumeSections: z.array(z.object({ kind: z.string(), text: z.string() })).default([]),
  disclaimer: z.string(),
});
export const exportSchema = z.object({
  id: z.string(),
  status: z.string(),
  format: z.string(),
  grantId: z.string().nullable(),
  expiresAt: z.string().nullable(),
  failureCode: z.string().nullable(),
});
export const entrySchema = z.object({
  id: z.string(),
  category: z.string(),
  canonical: z.string(),
  aliases: z.array(z.string()),
  contextPattern: z.string(),
});
export const dictionarySchema = z.object({
  departmentId: z.string(),
  status: z.string(),
  entries: z.array(entrySchema),
  version: z.number(),
});
export const settingsSchema = z.object({
  departmentId: z.string(),
  status: z.string(),
  retentionMonths: z.number(),
  confirmationWaitDays: z.number(),
  maxModelAttempts: z.number(),
  failedItemRetentionDays: z.number(),
  highThreshold: z.number(),
  middleThreshold: z.number(),
  lowThreshold: z.number(),
  noticeVersion: z.string(),
  authorizationText: z.string().default(''),
  maxFileBytes: z.number(),
  maxArchiveBytes: z.number(),
  maxBatchItems: z.number(),
  version: z.number(),
  prohibitedAttributes: z.array(z.string()),
});
export const templateSchema = z.object({
  dictionaryVersion: z.number().nullable().optional(),
  id: z.string(),
  departmentId: z.string().nullable(),
  name: z.string(),
  family: z.string(),
  system: z.boolean(),
  status: z.string(),
  weights: z.record(z.string(), z.number()),
  hardConditions: z.array(ruleSchema),
  criteria: z.array(criterionSchema),
  version: z.number(),
  requirements: z
    .array(
      z.object({
        id: z.string(),
        dimension: z.string(),
        weight: z.number(),
        critical: z.boolean(),
        applicable: z.boolean(),
      }),
    )
    .default([]),
  verification: z
    .object({
      trialId: z.string(),
      sampleSize: z.number(),
      agreement: z.number(),
      verifiedAt: z.string(),
      ruleHash: z.string(),
    })
    .nullish(),
  sourceTemplateId: z.string().nullable(),
  sourceVersion: z.number().nullable(),
});
export const trialSchema = z.object({
  dictionaryVersion: z.number().nullable().optional(),
  bindings: z
    .record(
      z.string(),
      z.object({
        promptVersion: z.string(),
        promptHash: z.string(),
        modelRouteVersion: z.string(),
        modelRoute: z.string(),
        outputSchemaHash: z.string(),
      }),
    )
    .default({}),
  id: z.string(),
  positionId: z.string(),
  departmentId: z.string(),
  sampleSize: z.number(),
  actualSize: z.number(),
  seed: z.number(),
  snapshotHash: z.string(),
  version: z.number(),
  status: z.string(),
  results: z.array(
    z.object({
      candidateId: z.string(),
      status: z.string(),
      label: z.string().nullable(),
      score: z.number().nullable(),
      coverage: z.number().nullable(),
    }),
  ),
  labels: z.array(
    z.object({ candidateId: z.string(), label: z.string(), reason: z.string(), note: z.string() }),
  ),
  diagnosis: z.string().nullable(),
  hardConditionFailureRates: z.record(z.string(), z.number()).default({}),
  agreement: z.number().nullable(),
  verified: z.boolean(),
});
export function beijing(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}
