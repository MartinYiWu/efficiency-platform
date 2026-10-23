import { z } from 'zod';

export const processingTaskSchema = z
  .object({
    id: z.string(),
    documentVersionId: z.string(),
    agentTaskId: z.string().nullable(),
    stage: z.string(),
    status: z.string(),
    attemptNo: z.number(),
    progressPercent: z.number(),
    errorCode: z.string().nullable(),
    errorMessage: z.string().nullable(),
    startedAt: z.string().nullable(),
    finishedAt: z.string().nullable(),
  })
  .strict();
export const documentVersionSchema = z
  .object({
    evidenceMode: z.enum(['FULL_ONLY', 'EXTRACTIVE_NARRATIVE']).nullish(),
    id: z.string(),
    documentId: z.string(),
    versionNo: z.number(),
    fileId: z.string(),
    fileSha256: z.string(),
    contentType: z.string(),
    changeSummary: z.string().nullable(),
    effectiveDate: z.string().nullable(),
    status: z.string(),
    errorCode: z.string().nullable(),
    errorMessage: z.string().nullable(),
    createdAt: z.string(),
    processingTasks: z.array(processingTaskSchema),
  })
  .strict();
export const documentSchema = z
  .object({
    id: z.string(),
    knowledgeBaseId: z.string(),
    directoryId: z.string().nullable(),
    title: z.string(),
    documentCode: z.string(),
    sourceType: z.string(),
    status: z.string(),
    currentPublishedVersionId: z.string().nullable(),
    versions: z.array(documentVersionSchema),
  })
  .strict();
export const knowledgeBaseSchema = z
  .object({
    id: z.string(),
    code: z.string(),
    name: z.string(),
    description: z.string().nullable(),
    knowledgeType: z.string(),
    visibilityScope: z.string(),
    status: z.string(),
    currentIndexReleaseId: z.string().nullable(),
    createdAt: z.string(),
    updatedAt: z.string(),
  })
  .strict();
export const directorySchema = z
  .object({
    id: z.string(),
    knowledgeBaseId: z.string(),
    parentId: z.string().nullable(),
    name: z.string(),
    path: z.string(),
    sortNo: z.number(),
    status: z.string(),
  })
  .strict();
export const indexReleaseSchema = z
  .object({
    id: z.string(),
    knowledgeBaseId: z.string(),
    releaseNo: z.number(),
    status: z.string(),
    documentCount: z.number(),
    chunkCount: z.number(),
    embeddingModel: z.string(),
    embeddingDimension: z.number(),
    checksum: z.string().nullable(),
    previousReleaseId: z.string().nullable(),
    createdAt: z.string(),
    publishedAt: z.string().nullable(),
  })
  .strict();
export const ingestItemSchema = z
  .object({
    id: z.string(),
    batchId: z.string(),
    fileId: z.string().nullable(),
    documentId: z.string().nullable(),
    documentVersionId: z.string().nullable(),
    status: z.string(),
    errorCode: z.string().nullable(),
    errorMessage: z.string().nullable(),
    retryOfItemId: z.string().nullable(),
  })
  .strict();
export const ingestBatchSchema = z
  .object({
    id: z.string(),
    knowledgeBaseId: z.string(),
    importMode: z.string(),
    totalCount: z.number(),
    succeededCount: z.number(),
    failedCount: z.number(),
    status: z.string(),
    createdAt: z.string(),
    finishedAt: z.string().nullable(),
    items: z.array(ingestItemSchema),
  })
  .strict();
export const pageSchema = <T extends z.ZodType>(item: T) =>
  z
    .object({ items: z.array(item), page: z.number(), pageSize: z.number(), total: z.number() })
    .strict();
