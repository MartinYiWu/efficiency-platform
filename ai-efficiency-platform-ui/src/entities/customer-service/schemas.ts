import { z } from 'zod';

export const answerModeSchema = z.enum([
  'COMPANY_KNOWLEDGE',
  'MIXED',
  'GENERAL_ADVICE',
  'CLARIFICATION',
  'INSUFFICIENT_EVIDENCE',
]);
export const conversationSchema = z
  .object({
    id: z.string(),
    tenantId: z.string(),
    userId: z.string(),
    title: z.string(),
    status: z.enum(['ACTIVE', 'ARCHIVED']),
    lastMessageAt: z.string().nullable(),
    createdAt: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const citationSchema = z
  .object({
    id: z.string(),
    runId: z.string(),
    messageId: z.string(),
    citationNo: z.number().int().positive(),
    knowledgeBaseId: z.string(),
    documentId: z.string(),
    documentVersionId: z.string(),
    indexReleaseId: z.string(),
    chunkId: z.string(),
    documentTitle: z.string().min(1),
    versionNo: z.number().int().positive(),
    sectionPath: z.string().nullable(),
    pageNo: z.number().int().positive().nullable(),
    quotedText: z.string().min(1),
    contentHash: z.string().min(1),
    createdAt: z.string(),
  })
  .strict();
export const messageSchema = z
  .object({
    id: z.string(),
    conversationId: z.string(),
    tenantId: z.string(),
    role: z.enum(['USER', 'ASSISTANT']),
    content: z.string(),
    status: z.string(),
    answerMode: answerModeSchema.nullable(),
    runId: z.string().nullable(),
    clientRequestId: z.string().nullable(),
    createdAt: z.string(),
  })
  .strict();
export const messageViewSchema = z
  .object({ message: messageSchema, citations: z.array(citationSchema) })
  .strict();
export const runSchema = z
  .object({
    id: z.string(),
    conversationId: z.string(),
    tenantId: z.string(),
    userMessageId: z.string(),
    agentRunId: z.string().nullable(),
    agentReleaseId: z.string(),
    status: z.enum(['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'CANCELLED']),
    answerMode: answerModeSchema.nullable(),
    lastEventSequence: z.number().int().nonnegative(),
    failureCode: z.string().nullable(),
    failureMessage: z.string().nullable(),
    startedAt: z.string().nullable(),
    finishedAt: z.string().nullable(),
    createdAt: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const submitSchema = z
  .object({
    conversationId: z.string(),
    runId: z.string(),
    status: z.string(),
    agentReleaseId: z.string(),
  })
  .strict();
export const feedbackSchema = z
  .object({
    id: z.string(),
    conversationId: z.string(),
    messageId: z.string(),
    runId: z.string(),
    tenantId: z.string(),
    userId: z.string(),
    rating: z.enum(['UP', 'DOWN']),
    reasonCode: z.string().nullable(),
    comment: z.string().nullable(),
    createdAt: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const pageSchema = <T extends z.ZodType>(item: T) =>
  z
    .object({ items: z.array(item), page: z.number(), pageSize: z.number(), total: z.number() })
    .strict();
const progressPayload = z.object({ stage: z.string(), summary: z.string() }).strict();
export const customerServiceSseSchema = z.discriminatedUnion('event', [
  z.object({
    id: z.number().int().positive(),
    event: z.literal('run.started'),
    payload: progressPayload,
  }),
  z.object({
    id: z.number().int().positive(),
    event: z.literal('run.progress'),
    payload: progressPayload,
  }),
  z.object({
    id: z.number().int().positive(),
    event: z.literal('message.delta'),
    payload: z.object({ delta: z.string() }).strict(),
  }),
  z.object({
    id: z.number().int().positive(),
    event: z.literal('citation.ready'),
    payload: citationSchema,
  }),
  z.object({
    id: z.number().int().positive(),
    event: z.literal('run.completed'),
    payload: z.object({ answerMode: answerModeSchema }).strict(),
  }),
  z.object({
    id: z.number().int().positive(),
    event: z.literal('run.failed'),
    payload: z.object({ errorCode: z.string(), errorMessage: z.string() }).strict(),
  }),
  z.object({
    id: z.number().int().positive(),
    event: z.literal('run.cancelled'),
    payload: z.object({}).strict(),
  }),
]);
