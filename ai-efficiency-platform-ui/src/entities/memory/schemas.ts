import { z } from 'zod';
export const topAgentSchema = z.enum(['operations', 'customer-service', 'hr']);
export const fieldValues = {
  'response.language': ['zh-CN', 'en-US'],
  'response.detail_level': ['concise', 'standard', 'detailed'],
  'response.format': ['prose', 'bullets', 'table'],
} as const;
export const fieldSchema = z.enum([
  'response.language',
  'response.detail_level',
  'response.format',
]);
const versionSchema = z.object({
  versionId: z.string().min(1),
  value: z.string(),
  status: z.enum(['ACTIVE', 'SUPERSEDED']),
  sourceType: z.literal('USER_PREFERENCE_DECISION'),
  sourceRef: z.string().min(1),
  expiresAt: z.iso.datetime().nullable(),
});
export const preferenceSchema = versionSchema
  .extend({
    id: z.string().min(1),
    topAgent: topAgentSchema,
    fieldKey: fieldSchema,
    revision: z.number().int().positive(),
  })
  .refine(
    (item) => (fieldValues[item.fieldKey] as readonly string[]).includes(item.value),
    'Unsupported preference value',
  );
export const scopeSchema = z
  .object({ topAgent: topAgentSchema, sessionId: z.string().min(1).optional() })
  .strict();
export const commandSchema = z
  .object({
    fieldKey: fieldSchema,
    value: z.string(),
    expectedRevision: z.number().int().nonnegative(),
    idempotencyKey: z.string().min(1),
  })
  .strict()
  .refine(
    (item) => (fieldValues[item.fieldKey] as readonly string[]).includes(item.value),
    'Unsupported preference value',
  );
export const memoryPageSchema = z.object({
  items: z.array(preferenceSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  pageSize: z.number().int().min(1).max(100),
});
export const memoryDetailSchema = z
  .object({ preference: preferenceSchema, history: z.array(versionSchema) })
  .refine(
    (item) =>
      item.history.every((version) =>
        (fieldValues[item.preference.fieldKey] as readonly string[]).includes(version.value),
      ),
    'Unsupported history value',
  );
export const memoryDeletionSchema = z
  .object({
    jobId: z.string().min(1),
    itemId: z.string().min(1),
    status: z
      .string()
      .min(1)
      .transform((value) =>
        ['LIVE', 'REVOKED', 'EXPIRED', 'DELETE_PENDING', 'DELETED'].includes(value)
          ? value
          : 'UNKNOWN',
      ),
    jobStatus: z.string().min(1),
    revision: z.number().int().positive(),
    deletionEpoch: z.number().int().nonnegative(),
    suppressionId: z.string().min(1),
    suppressionRevision: z.number().int().positive(),
    requiredTargets: z.number().int().nonnegative(),
    completedTargets: z.number().int().nonnegative(),
  })
  .refine((job) => job.completedTargets <= job.requiredTargets, 'Invalid completion counts');
export const forgetCommandSchema = z
  .object({
    itemId: z.string().min(1),
    expectedRevision: z.number().int().nonnegative(),
    idempotencyKey: z.string().min(1),
    mode: z.literal('FORGET_AND_SUPPRESS'),
  })
  .strict();
export const reauthorizationSchema = z
  .object({
    itemId: z.string().min(1),
    fieldKey: fieldSchema,
    value: z.string(),
    expectedRevision: z.number().int().nonnegative(),
    expected_suppression_revision: z.number().int().positive(),
    idempotencyKey: z.string().min(1),
    confirmation: z.literal('ALLOW_REMEMBER'),
  })
  .strict()
  .refine(
    (item) => (fieldValues[item.fieldKey] as readonly string[]).includes(item.value),
    'Unsupported preference value',
  );
