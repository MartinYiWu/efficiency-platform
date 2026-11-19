import { z } from 'zod';
import { MemoryApiError } from './api';

const count = z.number().int().nonnegative();
const metric = count.nullable();
const entry = z.object({
  text: z.string(),
  contentOrigin: z.string(),
  decisionStatus: z.string(),
  reason: z.string().nullable().optional(),
});
export const summaryDetailSchema = z.object({
  segmentId: z.string().min(1),
  freeTextQuality: z.literal('UNVERIFIED'),
  goal: entry,
  confirmedConstraints: z.array(entry),
  decisions: z.array(entry),
  rejectedOptions: z.array(entry),
  openQuestions: z.array(entry),
  importantRefs: z.array(entry),
  uncertainties: z.array(entry),
});
export const contextUsageSchema = z.object({
  topAgent: z.enum(['operations', 'customer-service']),
  sessionId: z.string().min(1),
  runId: z.string().nullable(),
  status: z.enum(['AVAILABLE', 'EMPTY', 'DISABLED']),
  operations: z.array(
    z.object({
      nodeId: z.string(),
      inputTokens: metric,
      inputLimit: metric,
      freeTokens: metric,
      cpuBeforeTokens: metric,
      cpuAfterTokens: metric,
      summaryBeforeTokens: metric,
      summaryAfterTokens: metric,
      outputReserveTokens: metric,
      windowStatus: z.string(),
      summaryCasStatus: z.string(),
      summaryAdoptionStatus: z.string(),
      feeStatus: z.string(),
      costMicrounits: metric,
      omissions: z.array(z.object({ reason: z.string(), count })),
    }),
  ),
  summaries: z.array(
    z.object({
      segmentId: z.string().min(1),
      firstSequence: count,
      lastSequence: count,
      expiresAt: count,
      sourceCount: count,
      freeTextQuality: z.literal('UNVERIFIED'),
    }),
  ),
});
export type ContextUsage = z.infer<typeof contextUsageSchema>;
export type SummaryDetail = z.infer<typeof summaryDetailSchema>;
export type ContextScope = {
  topAgent: 'operations' | 'customer-service';
  sessionId: string;
  runId?: string;
};

export function createContextUsageApi(
  token: () => string | undefined,
  fetcher: typeof fetch = fetch,
) {
  const base =
    (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') + '/api/aihub/memory-context';
  async function get<T>(
    path: string,
    scope: ContextScope,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
  ) {
    const credential = token();
    if (!credential) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
    const query = new URLSearchParams({ topAgent: scope.topAgent, sessionId: scope.sessionId });
    if (scope.runId && !path) query.set('runId', scope.runId);
    const response = await fetcher(`${base}${path}?${query}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${credential}` },
      signal,
    });
    const value: unknown = await response.json();
    const envelope = z.object({ code: z.string(), data: z.unknown().optional() }).safeParse(value);
    if (!response.ok || !envelope.success || envelope.data.code !== 'SUCCESS')
      throw new MemoryApiError(
        response.status,
        envelope.success ? envelope.data.code : 'HTTP_ERROR',
      );
    const result = schema.safeParse(envelope.data.data);
    if (!result.success) throw new MemoryApiError(503, 'CLIENT_CONTRACT_MISMATCH');
    return result.data;
  }
  return {
    read: async (scope: ContextScope, signal?: AbortSignal) => {
      const result = await get('', scope, contextUsageSchema, signal);
      if (
        result.topAgent !== scope.topAgent ||
        result.sessionId !== scope.sessionId ||
        result.runId !== (scope.runId ?? null)
      )
        throw new MemoryApiError(403, 'MEMORY_SCOPE_DENIED');
      return result;
    },
    summary: (id: string, scope: ContextScope, signal?: AbortSignal) =>
      get(`/summaries/${encodeURIComponent(id)}`, scope, summaryDetailSchema, signal),
  };
}
