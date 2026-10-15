import type {
  OperationArtifactSummary,
  OperationConversationView,
  OperationMessageView,
  OperationRunView,
  RunDisplayStatus,
} from './types';

export interface OperationApiOptions {
  baseUrl: string;
  /** 旧版直连 Agent 参数，仅保留类型兼容，Java API 不读取。 */
  tenantId?: string;
  fetcher?: typeof fetch;
  signal?: AbortSignal;
}

interface ApiEnvelope<T> {
  code: string;
  message: string;
  data: T;
}

export class OperationApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
  }
}

const url = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, '')}${path}`;

async function readEnvelope<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (!response.ok || !body || body.code !== 'SUCCESS') {
    throw new OperationApiError(
      body?.message || `运营助手请求失败（${response.status}）`,
      response.status,
      body?.code ?? null,
    );
  }
  return body.data;
}

export async function getConversation(
  conversationId: string,
  options: OperationApiOptions,
): Promise<OperationConversationView> {
  const response = await (options.fetcher ?? fetch)(
    url(options.baseUrl, `/api/operations/conversations/${encodeURIComponent(conversationId)}`),
    { method: 'GET', signal: options.signal },
  );
  return readEnvelope(response);
}

export async function listConversationMessages(
  conversationId: string,
  options: OperationApiOptions,
): Promise<OperationMessageView[]> {
  const response = await (options.fetcher ?? fetch)(
    url(
      options.baseUrl,
      `/api/operations/conversations/${encodeURIComponent(conversationId)}/messages`,
    ),
    { method: 'GET', signal: options.signal },
  );
  const value = await readEnvelope<{
    conversationId: string;
    messages: OperationMessageView[];
  }>(response);
  return value.messages;
}

export async function getRun(
  runId: string,
  options: OperationApiOptions,
): Promise<OperationRunView> {
  const response = await (options.fetcher ?? fetch)(
    url(options.baseUrl, `/api/operations/runs/${encodeURIComponent(runId)}`),
    { method: 'GET', signal: options.signal },
  );
  return readEnvelope(response);
}

export async function createConversation(
  options: OperationApiOptions,
): Promise<OperationConversationView> {
  const response = await (options.fetcher ?? fetch)(
    url(options.baseUrl, '/api/operations/conversations'),
    {
      method: 'POST',
      signal: options.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    },
  );
  return readEnvelope(response);
}

export async function submitConversationMessage(
  input: {
    conversationId: string;
    message: string;
    clientRequestId?: string;
    requestId?: string;
    userId?: string;
  },
  options: OperationApiOptions,
): Promise<OperationRunView> {
  const response = await (options.fetcher ?? fetch)(
    url(
      options.baseUrl,
      `/api/operations/conversations/${encodeURIComponent(input.conversationId)}/messages`,
    ),
    {
      method: 'POST',
      signal: options.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: input.message,
        clientRequestId: input.clientRequestId ?? input.requestId,
      }),
    },
  );
  return readEnvelope(response);
}

export async function cancelRun(
  runId: string,
  options: OperationApiOptions,
): Promise<{ status: RunDisplayStatus }> {
  const response = await (options.fetcher ?? fetch)(
    url(options.baseUrl, `/api/operations/runs/${encodeURIComponent(runId)}/cancel`),
    { method: 'POST', signal: options.signal },
  );
  const run = await readEnvelope<OperationRunView>(response);
  return { status: run.status };
}

export async function listConversationArtifacts(
  conversationId: string,
  options: OperationApiOptions,
): Promise<OperationArtifactSummary[]> {
  const response = await (options.fetcher ?? fetch)(
    url(
      options.baseUrl,
      `/api/operations/conversations/${encodeURIComponent(conversationId)}/artifacts`,
    ),
    { method: 'GET', signal: options.signal },
  );
  const value = await readEnvelope<{
    conversationId: string;
    artifacts: OperationArtifactSummary[];
  }>(response);
  return value.artifacts;
}

export function artifactUrl(
  baseUrl: string,
  artifactId: string,
  action: 'copy' | 'download' | 'wechat-html',
) {
  return url(baseUrl, `/api/operations/artifacts/${encodeURIComponent(artifactId)}/${action}`);
}
