import type { MemoryApi, MemoryDeletionApi, MemoryScope } from './model';
import {
  commandSchema,
  memoryDetailSchema,
  memoryPageSchema,
  preferenceSchema,
  scopeSchema,
  memoryDeletionSchema,
  forgetCommandSchema,
  reauthorizationSchema,
} from './schemas';
const errorMessages: Record<string, string> = {
  MEMORY_IDENTITY_REQUIRED: '请先登录后管理记忆',
  MEMORY_SCOPE_DENIED: '无权查看当前记忆或来源',
  MEMORY_NOT_FOUND: '记忆不存在或已不可用',
  MEMORY_REVISION_CONFLICT: '版本冲突，当前值与草稿已保留，请重新加载后核对',
  MEMORY_IDEMPOTENCY_CONFLICT: '请求冲突，请重新加载后核对',
  MEMORY_SESSION_BINDING_CONFLICT: '会话归属冲突，请返回当前 Agent 会话',
  FEATURE_DISABLED: '功能暂未开放',
  MEMORY_VALUE_INVALID: '当前策略不支持此偏好值',
  MEMORY_KEY_UNAVAILABLE: '记忆暂不可用，请稍后重试',
  MEMORY_STORAGE_UNAVAILABLE: '记忆服务暂不可用，请稍后重试',
};
export class MemoryApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly traceId?: string,
  ) {
    super(errorMessages[code] ?? '记忆请求失败，请稍后重试');
  }
}
export function memoryErrorMessage(error: unknown) {
  if (!(error instanceof MemoryApiError)) return '记忆请求失败，请稍后重试';
  return error.message + (error.traceId ? `（追踪号：${error.traceId}）` : '');
}
export function createMemoryApi(
  token: () => string | undefined,
  fetcher: typeof fetch = fetch,
): MemoryApi & MemoryDeletionApi {
  const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') + '/api/aihub';
  function query(scope: MemoryScope, page?: number) {
    const checked = scopeSchema.parse(scope);
    const params = new URLSearchParams({ topAgent: checked.topAgent });
    if (checked.sessionId && checked.topAgent !== 'hr') params.set('sessionId', checked.sessionId);
    if (page !== undefined) {
      params.set('page', String(page));
      params.set('pageSize', '20');
    }
    return params;
  }
  async function call<T>(
    path: string,
    schema: { parse(value: unknown): T },
    signal?: AbortSignal,
    body?: object,
    service = 'memories',
  ): Promise<T> {
    const accessToken = token();
    if (!accessToken) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
    const headers = new Headers({ Authorization: `Bearer ${accessToken}` });
    if (body) headers.set('Content-Type', 'application/json');
    const response = await fetcher(`${base}/${service}${path}`, {
      method: body ? 'POST' : 'GET',
      headers,
      signal,
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const value = (await response.json().catch(() => null)) as {
      code?: unknown;
      data?: unknown;
      traceId?: unknown;
    } | null;
    const traceId =
      typeof value?.traceId === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value.traceId)
        ? value.traceId
        : undefined;
    if (!response.ok || value?.code !== 'SUCCESS')
      throw new MemoryApiError(
        response.status,
        typeof value?.code === 'string' && Object.hasOwn(errorMessages, value.code)
          ? value.code
          : 'HTTP_ERROR',
        traceId,
      );
    try {
      return schema.parse(value.data);
    } catch {
      throw new MemoryApiError(response.status, 'CLIENT_CONTRACT_MISMATCH', traceId);
    }
  }
  function body(scope: MemoryScope, command: Parameters<MemoryApi['save']>[1]) {
    const checked = scopeSchema.parse(scope);
    return {
      ...checked,
      ...(checked.topAgent === 'hr' ? { sessionId: undefined } : {}),
      ...commandSchema.parse(command),
    };
  }
  return {
    list: (scope, page = 1, signal) => call(`?${query(scope, page)}`, memoryPageSchema, signal),
    detail: (id, scope, signal) =>
      call(`/${encodeURIComponent(id)}?${query(scope)}`, memoryDetailSchema, signal),
    save: (scope, command, signal) => call('', preferenceSchema, signal, body(scope, command)),
    correct: (id, scope, command, signal) =>
      call(
        `/${encodeURIComponent(id)}/corrections`,
        preferenceSchema,
        signal,
        body(scope, command),
      ),
    forget: (scope, command, signal) =>
      call(
        '',
        memoryDeletionSchema,
        signal,
        { ...scopeSchema.parse(scope), ...forgetCommandSchema.parse(command) },
        'memory-deletions',
      ),
    deletion: (jobId, scope, signal) =>
      call(
        `/${encodeURIComponent(jobId)}?${query(scope)}`,
        memoryDeletionSchema,
        signal,
        undefined,
        'memory-deletions',
      ),
    reauthorize: (suppressionId, scope, command, signal) =>
      call(
        `/${encodeURIComponent(suppressionId)}/reauthorizations`,
        preferenceSchema,
        signal,
        { ...scopeSchema.parse(scope), ...reauthorizationSchema.parse(command) },
        'memory-suppressions',
      ),
  };
}
