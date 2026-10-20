import { z } from 'zod';

const date = z.string().nullable();
export const agentDefinitionSchema = z
  .object({
    id: z.string(),
    agentKey: z.string(),
    name: z.string(),
    description: z.string().nullable(),
    agentType: z.string(),
    status: z.string(),
    createdBy: z.string(),
    createdAt: z.string(),
    updatedBy: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const agentVersionSchema = z
  .object({
    id: z.string(),
    agentDefinitionId: z.string(),
    semanticVersion: z.string(),
    graphKey: z.string(),
    graphVersion: z.string(),
    status: z.string(),
    changeSummary: z.string().nullable(),
    createdBy: z.string(),
    createdAt: z.string(),
    publishedAt: date,
  })
  .strict();
export const agentDetailSchema = z
  .object({ definition: agentDefinitionSchema, versions: z.array(agentVersionSchema) })
  .strict();
export const promptDefinitionSchema = z
  .object({
    id: z.string(),
    promptKey: z.string(),
    scope: z.string(),
    ownerAgentDefinitionId: z.string().nullable(),
    name: z.string(),
    description: z.string().nullable(),
    stageKey: z.string(),
    status: z.string(),
    createdBy: z.string(),
    createdAt: z.string(),
    updatedBy: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const promptVersionSchema = z
  .object({
    id: z.string(),
    promptDefinitionId: z.string(),
    semanticVersion: z.string(),
    status: z.string(),
    checksum: z.string().nullable(),
    changeSummary: z.string().nullable(),
    createdBy: z.string(),
    createdAt: z.string(),
    publishedAt: date,
  })
  .strict();
export const promptMessageSchema = z
  .object({
    id: z.string(),
    promptVersionId: z.string(),
    ordinal: z.number(),
    role: z.enum(['SYSTEM', 'USER', 'ASSISTANT']),
    messageKey: z.string(),
    contentTemplate: z.string(),
    contentFormat: z.string(),
    trustedInstruction: z.boolean(),
    checksum: z.string(),
  })
  .strict();
export const promptVariableSchema = z
  .object({
    id: z.string(),
    promptMessageTemplateId: z.string(),
    variableName: z.string(),
    valueType: z.string(),
    valueSource: z.string(),
    required: z.boolean(),
    sensitive: z.boolean(),
    maxLength: z.number().nullable(),
    allowUntrustedContent: z.boolean(),
  })
  .strict();
export const promptDetailSchema = z
  .object({
    definition: promptDefinitionSchema,
    version: promptVersionSchema,
    messages: z.array(promptMessageSchema),
    variables: z.array(promptVariableSchema),
  })
  .strict();
export const modelPolicySchema = z
  .object({
    id: z.string(),
    ownerAgentDefinitionId: z.string(),
    policyKey: z.string(),
    semanticVersion: z.string(),
    provider: z.string(),
    modelName: z.string(),
    temperature: z.number(),
    topP: z.number(),
    maxInputTokens: z.number(),
    maxOutputTokens: z.number(),
    connectTimeoutMs: z.number(),
    readTimeoutMs: z.number(),
    maxRetries: z.number(),
    status: z.string(),
    checksum: z.string().nullable(),
    createdBy: z.string(),
    createdAt: z.string(),
    publishedAt: date,
  })
  .strict();
export const ragPolicySchema = z
  .object({
    id: z.string(),
    ownerAgentDefinitionId: z.string(),
    policyKey: z.string(),
    semanticVersion: z.string(),
    rewriteQueryLimit: z.number(),
    vectorTopK: z.number(),
    ftsTopK: z.number(),
    fusionTopK: z.number(),
    rerankTopK: z.number(),
    contextTokenLimit: z.number(),
    citationLimit: z.number(),
    status: z.string(),
    checksum: z.string().nullable(),
    createdBy: z.string(),
    createdAt: z.string(),
    publishedAt: date,
  })
  .strict();
export const policyListSchema = z
  .object({ modelPolicies: z.array(modelPolicySchema), ragPolicies: z.array(ragPolicySchema) })
  .strict();
export const debugEvidenceSchema = z
  .object({
    chunk_id: z.string(),
    document_version_id: z.string(),
    section_path: z.string(),
    score: z.number(),
    excerpt: z.string(),
  })
  .strict();
export const debugViewSchema = z
  .object({
    contract_version: z.string(),
    debug_run_id: z.string(),
    status: z.string(),
    stages: z.array(
      z
        .object({
          stage_key: z.string(),
          status: z.string(),
          public_summary: z.string(),
          evidence: z.array(debugEvidenceSchema),
        })
        .strict(),
    ),
    answer_mode: z.string().nullable(),
    answer_markdown: z.string().nullable(),
    error_code: z.string().nullable(),
    error_message: z.string().nullable(),
  })
  .strict();
export const runSchema = z
  .object({
    id: z.string(),
    conversationId: z.string(),
    tenantId: z.string(),
    userMessageId: z.string(),
    agentRunId: z.string().nullable(),
    agentReleaseId: z.string(),
    status: z.string(),
    answerMode: z.string().nullable(),
    lastEventSequence: z.number(),
    failureCode: z.string().nullable(),
    failureMessage: z.string().nullable(),
    startedAt: date,
    finishedAt: date,
    createdAt: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const messageSchema = z
  .object({
    id: z.string(),
    conversationId: z.string(),
    tenantId: z.string(),
    role: z.string(),
    content: z.string(),
    status: z.string(),
    answerMode: z.string().nullable(),
    runId: z.string().nullable(),
    clientRequestId: z.string().nullable(),
    createdAt: z.string(),
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
    rating: z.string(),
    reasonCode: z.string().nullable(),
    comment: z.string().nullable(),
    createdAt: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const runStepSchema = z
  .object({
    id: z.string(),
    runId: z.string(),
    sequenceNo: z.number(),
    stage: z.string(),
    status: z.string(),
    publicSummary: z.string(),
    internalPayload: z.string().nullable(),
    startedAt: date,
    finishedAt: date,
  })
  .strict();
export const citationSchema = z
  .object({
    id: z.string(),
    runId: z.string(),
    messageId: z.string(),
    citationNo: z.number(),
    knowledgeBaseId: z.string(),
    documentId: z.string(),
    documentVersionId: z.string(),
    indexReleaseId: z.string(),
    chunkId: z.string(),
    documentTitle: z.string(),
    versionNo: z.number(),
    sectionPath: z.string().nullable(),
    pageNo: z.number().nullable(),
    quotedText: z.string(),
    contentHash: z.string(),
    createdAt: z.string(),
  })
  .strict();
export const replaySchema = z
  .object({
    run: runSchema,
    question: messageSchema,
    answer: messageSchema.nullable(),
    stages: z.array(runStepSchema),
    citations: z.array(citationSchema),
    feedback: feedbackSchema.nullable(),
  })
  .strict();
export const pageSchema = <T extends z.ZodType>(item: T) =>
  z
    .object({ items: z.array(item), page: z.number(), pageSize: z.number(), total: z.number() })
    .strict();
