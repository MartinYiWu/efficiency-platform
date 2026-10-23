import {
  directorySchema,
  documentSchema,
  documentVersionSchema,
  indexReleaseSchema,
  ingestBatchSchema,
  ingestItemSchema,
  knowledgeBaseSchema,
  pageSchema,
  processingTaskSchema,
} from '../../entities/knowledge/schemas';

const url = (path: string) => path;
export class KnowledgeApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
  }
}
async function call<T>(
  path: string,
  schema: { parse(value: unknown): T },
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url(path), init);
  const body = (await response.json().catch(() => null)) as {
    code?: string;
    message?: string;
    data?: unknown;
  } | null;
  if (!response.ok || body?.code !== 'SUCCESS')
    throw new KnowledgeApiError(body?.message ?? '知识中心请求失败', body?.code ?? 'HTTP_ERROR');
  try {
    return schema.parse(body.data);
  } catch {
    throw new KnowledgeApiError('服务端响应不符合知识中心契约', 'CLIENT_CONTRACT_MISMATCH');
  }
}
export const listKnowledgeBases = (query = '') =>
  call(`/api/knowledge/bases?${query}`, pageSchema(knowledgeBaseSchema));
export const getKnowledgeBase = (id: string) =>
  call(`/api/knowledge/bases/${id}`, knowledgeBaseSchema);
export const createKnowledgeBase = (value: object) =>
  call('/api/knowledge/bases', knowledgeBaseSchema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  });
export const listDirectories = (id: string) =>
  call(`/api/knowledge/bases/${id}/directories`, {
    parse: (value: unknown) => directorySchema.array().parse(value),
  });
export const createDirectory = (id: string, value: object) =>
  call(`/api/knowledge/bases/${id}/directories`, directorySchema, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  });
export const listDocuments = (id: string, query = '') =>
  call(`/api/knowledge/bases/${id}/documents?${query}`, pageSchema(documentSchema));
export const getDocument = (id: string) => call(`/api/knowledge/documents/${id}`, documentSchema);
export const getDocumentVersion = (id: string) =>
  call(`/api/knowledge/document-versions/${id}`, documentVersionSchema);
export async function uploadDocumentVersion(
  documentId: string,
  file: File,
  changeSummary: string,
  effectiveDate?: string,
  evidenceMode: 'FULL_ONLY' | 'EXTRACTIVE_NARRATIVE' = 'FULL_ONLY',
) {
  const form = new FormData();
  form.append('file', file);
  form.append('changeSummary', changeSummary);
  form.append('evidenceMode', evidenceMode);
  if (effectiveDate) form.append('effectiveDate', effectiveDate);
  return call(`/api/knowledge/documents/${documentId}/versions`, documentVersionSchema, {
    method: 'POST',
    body: form,
  });
}
export const publishDocumentVersion = (id: string) =>
  call(`/api/knowledge/document-versions/${id}/publish`, indexReleaseSchema, { method: 'POST' });
export const listIndexReleases = (id: string) =>
  call(`/api/knowledge/bases/${id}/index-releases`, {
    parse: (value: unknown) => indexReleaseSchema.array().parse(value),
  });
export const rollbackIndexRelease = (id: string) =>
  call(`/api/knowledge/index-releases/${id}/rollback`, indexReleaseSchema, { method: 'POST' });
export async function uploadDocuments(
  baseId: string,
  files: File[],
  directoryId?: string,
  evidenceMode: 'FULL_ONLY' | 'EXTRACTIVE_NARRATIVE' = 'FULL_ONLY',
) {
  const form = new FormData();
  files.forEach((file) => form.append(files.length === 1 ? 'file' : 'files', file));
  if (directoryId) form.append('directoryId', directoryId);
  if (files.length === 1) form.append('evidenceMode', evidenceMode);
  return call(
    `/api/knowledge/bases/${baseId}/${files.length === 1 ? 'documents/upload' : 'imports'}`,
    ingestBatchSchema,
    { method: 'POST', body: form },
  );
}
export const getImportBatch = (id: string) =>
  call(`/api/knowledge/imports/${id}`, ingestBatchSchema);
export const retryImportItem = (id: string) =>
  call(`/api/knowledge/import-items/${id}/retry`, ingestItemSchema, { method: 'POST' });
export const getProcessingTask = (id: string) =>
  call(`/api/knowledge/processing-tasks/${id}`, processingTaskSchema);
export const retryProcessingTask = (id: string) =>
  call(`/api/knowledge/processing-tasks/${id}/retry`, processingTaskSchema, { method: 'POST' });
