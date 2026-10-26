import {
  agentDefinitionSchema,
  agentDetailSchema,
  agentReleaseSchema,
  debugViewSchema,
  feedbackSchema,
  modelPolicySchema,
  pageSchema,
  policyListSchema,
  promptDefinitionSchema,
  promptDetailSchema,
  ragPolicySchema,
  replaySchema,
  runSchema,
} from '../../entities/ai-center/schemas';
import {
  evaluationCaseSchema,
  evaluationDatasetDetailSchema,
  evaluationDatasetSchema,
  evaluationImportResultSchema,
  evaluationRunComparisonSchema,
  evaluationRunDetailSchema,
  evaluationRunSchema,
} from '../../entities/ai-center/evaluationSchemas';

export class AiCenterApiError extends Error {
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
  const response = await fetch(path, init);
  const body = (await response.json().catch(() => null)) as {
    code?: string;
    message?: string;
    data?: unknown;
  } | null;
  if (!response.ok || body?.code !== 'SUCCESS')
    throw new AiCenterApiError(body?.message ?? 'AI 中心请求失败', body?.code ?? 'HTTP_ERROR');
  try {
    return schema.parse(body.data);
  } catch {
    throw new AiCenterApiError('服务端响应不符合 AI 中心契约', 'CLIENT_CONTRACT_MISMATCH');
  }
}
const json = (method: string, value?: object): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: value ? JSON.stringify(value) : undefined,
});
export const listAgents = () => call('/api/aihub/agents', agentDefinitionSchema.array());
export const getAgent = (id: string) => call(`/api/aihub/agents/${id}`, agentDetailSchema);
export const listAgentReleases = (agentKey: string) =>
  call(
    `/api/aihub/agents/${encodeURIComponent(agentKey)}/releases?environment=dev`,
    agentReleaseSchema.array(),
  );
export const createAgentVersion = (id: string, value: object) =>
  call(
    `/api/aihub/agents/${id}/versions`,
    agentDetailSchema.shape.versions.element,
    json('POST', value),
  );
export const transitionAgentVersion = (id: string, status: string) =>
  call(
    `/api/aihub/agents/versions/${id}/transition`,
    agentDetailSchema.shape.versions.element,
    json('POST', { status }),
  );
export const listPrompts = (query = '') =>
  call(`/api/aihub/prompts?${query}`, promptDefinitionSchema.array());
export const createPrompt = (value: object) =>
  call('/api/aihub/prompts', promptDefinitionSchema, json('POST', value));
export const createPromptVersion = (id: string, value: object) =>
  call(`/api/aihub/prompts/${id}/versions`, promptDetailSchema.shape.version, json('POST', value));
export const getPromptVersion = (id: string) =>
  call(`/api/aihub/prompts/versions/${id}`, promptDetailSchema);
export const replacePromptContent = (id: string, value: object) =>
  call(
    `/api/aihub/prompts/versions/${id}/content`,
    promptDetailSchema.shape.version,
    json('PUT', value),
  );
export const listPolicies = (agentId: string) =>
  call(`/api/aihub/policies?agentId=${encodeURIComponent(agentId)}`, policyListSchema);
export const saveModelPolicy = (value: object) =>
  call('/api/aihub/model-policies', modelPolicySchema, json('POST', value));
export const saveRagPolicy = (value: object) =>
  call('/api/aihub/rag-policies', ragPolicySchema, json('POST', value));
export const executeRagDebug = (value: object) =>
  call('/api/aihub/rag-debug-runs', debugViewSchema, json('POST', value));
export const listRuns = (query = '') => call(`/api/aihub/runs?${query}`, pageSchema(runSchema));
export const getRunReplay = (id: string) => call(`/api/aihub/runs/${id}/replay`, replaySchema);
export const listFeedback = (query = '') =>
  call(`/api/aihub/feedback?${query}`, pageSchema(feedbackSchema));

const evaluationBase = '/api/aihub/rag-evaluations';
export const listEvaluationDatasets = () =>
  call(`${evaluationBase}/datasets`, evaluationDatasetSchema.array());
export const createEvaluationDataset = (value: object) =>
  call(`${evaluationBase}/datasets`, evaluationDatasetSchema, json('POST', value));
export const getEvaluationDataset = (id: string) =>
  call(`${evaluationBase}/datasets/${encodeURIComponent(id)}`, evaluationDatasetDetailSchema);
export const createEvaluationCase = (datasetId: string, value: object) =>
  call(`${evaluationBase}/datasets/${encodeURIComponent(datasetId)}/cases`, evaluationCaseSchema, json('POST', value));
export const updateEvaluationCase = (datasetId: string, caseId: string, value: object) =>
  call(`${evaluationBase}/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}`,
    evaluationCaseSchema, json('PUT', value));
export const importEvaluationCases = (datasetId: string, value: object[]) =>
  call(`${evaluationBase}/datasets/${encodeURIComponent(datasetId)}/cases/import`,
    evaluationImportResultSchema, json('POST', value));
export const startEvaluationRun = (value: object) =>
  call(`${evaluationBase}/runs`, evaluationRunSchema, json('POST', value));
export const listEvaluationRuns = (datasetId: string) =>
  call(`${evaluationBase}/runs?datasetId=${encodeURIComponent(datasetId)}`, evaluationRunSchema.array());
export const getEvaluationRun = (id: string) =>
  call(`${evaluationBase}/runs/${encodeURIComponent(id)}`, evaluationRunDetailSchema);
export const compareEvaluationRuns = (baselineRunId: string, candidateRunId: string) =>
  call(`${evaluationBase}/runs/compare?baselineRunId=${encodeURIComponent(baselineRunId)}&candidateRunId=${encodeURIComponent(candidateRunId)}`,
    evaluationRunComparisonSchema);
