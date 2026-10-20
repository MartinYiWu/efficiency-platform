import {
  agentDefinitionSchema,
  agentDetailSchema,
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
