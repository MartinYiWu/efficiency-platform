import {
  conversationSubmitViewSchema,
  type ConversationSubmitInput,
  type ConversationSubmitViewV1,
  type RunDisplayStatus,
} from './types';

export interface OperationApiOptions {
  baseUrl: string;
  tenantId: string;
  fetcher?: typeof fetch;
  signal?: AbortSignal;
}
const url = (baseUrl: string, path: string) => `${baseUrl.replace(/\/$/, '')}${path}`;
function apiError(response: Response): Error {
  return new Error(
    response.status === 401 ? '登录状态已失效，请重新登录。' : '运营助手请求失败，请稍后重试。',
  );
}

export async function submitConversationMessage(
  input: ConversationSubmitInput & { conversationId: string },
  options: OperationApiOptions,
): Promise<ConversationSubmitViewV1> {
  const response = await (options.fetcher ?? fetch)(
    url(options.baseUrl, `/v1/conversations/${encodeURIComponent(input.conversationId)}/messages`),
    {
      method: 'POST',
      signal: options.signal,
      headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': options.tenantId },
      body: JSON.stringify({
        contract_version: 'conversation/1',
        message: input.message,
        request_id: input.requestId,
        user_id: input.userId,
        attachments: input.attachments ?? [],
      }),
    },
  );
  if (!response.ok) throw apiError(response);
  const parsed = conversationSubmitViewSchema.safeParse(await response.json());
  if (!parsed.success || parsed.data.conversation_id !== input.conversationId)
    throw new Error('运营助手返回了无法识别的响应。');
  return parsed.data;
}

export async function cancelRun(
  runId: string,
  options: OperationApiOptions,
): Promise<{ status: RunDisplayStatus }> {
  const response = await (options.fetcher ?? fetch)(
    url(options.baseUrl, `/v1/runs/${encodeURIComponent(runId)}/cancel`),
    {
      method: 'POST',
      signal: options.signal,
      headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': options.tenantId },
      body: JSON.stringify({
        contract_version: 'run.cancel/1',
        tenant_id: options.tenantId,
        reason_code: 'user_requested',
      }),
    },
  );
  if (!response.ok) throw apiError(response);
  const body = (await response.json().catch(() => ({}))) as { status?: RunDisplayStatus };
  return { status: body.status ?? 'running' };
}
