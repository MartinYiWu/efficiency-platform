import {
  citationSchema,
  conversationSchema,
  feedbackSchema,
  messageViewSchema,
  pageSchema,
  runSchema,
  submitSchema,
  timelineSchema,
} from '../../entities/customer-service/schemas';

export class CustomerServiceApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly traceId?: string,
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
    traceId?: string;
    data?: unknown;
  } | null;
  if (!response.ok || body?.code !== 'SUCCESS')
    throw new CustomerServiceApiError(
      body?.message ?? '智能客服请求失败',
      body?.code ?? 'HTTP_ERROR',
      body?.traceId,
    );
  try {
    return schema.parse(body.data);
  } catch {
    throw new CustomerServiceApiError(
      '服务端响应不符合智能客服契约',
      'CLIENT_CONTRACT_MISMATCH',
      body?.traceId,
    );
  }
}
const json = (method: string, body?: object): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body ? JSON.stringify(body) : undefined,
});
export const listConversations = (keyword = '') =>
  call(
    `/api/customer-service/conversations?${new URLSearchParams(keyword ? { keyword } : {})}`,
    pageSchema(conversationSchema),
  );
export const createConversation = (title: string) =>
  call('/api/customer-service/conversations', conversationSchema, json('POST', { title }));
export const listMessages = (id: string) =>
  call(`/api/customer-service/conversations/${id}/messages`, messageViewSchema.array())
    .then((items) => items.sort((left, right) =>
      left.message.createdAt.localeCompare(right.message.createdAt) ||
      (left.message.role === right.message.role ? 0 : left.message.role === 'USER' ? -1 : 1),
    ));
export const submitMessage = (id: string, message: string, clientRequestId: string) =>
  call(
    `/api/customer-service/conversations/${id}/messages`,
    submitSchema,
    json('POST', { contractVersion: 'customer-service-message/1', message, clientRequestId }),
  );
export const getRun = (id: string) => call(`/api/customer-service/runs/${id}`, runSchema);
export const getTimeline = (id: string) =>
  call(`/api/customer-service/runs/${id}/timeline`, timelineSchema);
export const cancelRun = (id: string) =>
  call(`/api/customer-service/runs/${id}/cancel`, runSchema, json('POST'));
export const submitFeedback = (messageId: string, value: object) =>
  call(`/api/customer-service/messages/${messageId}/feedback`, feedbackSchema, json('PUT', value));
export const getCitation = (id: string) =>
  call(`/api/customer-service/citations/${id}`, citationSchema);
