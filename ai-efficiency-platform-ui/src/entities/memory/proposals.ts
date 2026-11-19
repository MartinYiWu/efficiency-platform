import { z } from 'zod';
import { MemoryApiError } from './api';
import type { MemoryScope } from './model';

export const memoryProposalSchema = z.object({
  id: z.string().min(1),
  itemId: z.string().min(1),
  topAgent: z.enum(['operations', 'customer-service']),
  sessionId: z.string().min(1),
  fieldKey: z.enum(['response.language', 'response.detail_level', 'response.format']),
  value: z.string().nullable(),
  action: z.enum(['ADD', 'REPLACE_CANDIDATE', 'CONFLICT_CANDIDATE', 'NOOP']),
  status: z.enum(['PENDING', 'ACCEPTED', 'REJECTED', 'STALE', 'SUPPRESSED', 'EXPIRED']),
  revision: z.number().int().nonnegative(),
  expectedItemRevision: z.number().int().nonnegative(),
  expiresAt: z.string().datetime({ offset: true }),
  indexStatus: z.literal('NOT_REQUESTED'),
  versionId: z.string().nullable(),
});
export type MemoryProposal = z.infer<typeof memoryProposalSchema>;
export type ProposalDecision = 'CONFIRM' | 'REJECT';

export function createMemoryProposalApi(
  token: () => string | undefined,
  fetcher: typeof fetch = fetch,
) {
  const base =
    (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') + '/api/aihub/memories/proposals';
  function scopeOf(scope: MemoryScope) {
    if (scope.topAgent === 'hr' || !scope.sessionId)
      throw new MemoryApiError(403, 'MEMORY_SCOPE_DENIED');
    return { topAgent: scope.topAgent, sessionId: scope.sessionId };
  }
  async function call<T>(
    path: string,
    scope: MemoryScope,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
    body?: object,
  ): Promise<T> {
    const credential = token();
    if (!credential) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
    const checked = scopeOf(scope);
    const response = await fetcher(`${base}${path}`, {
      method: body ? 'POST' : 'GET',
      headers: {
        Authorization: `Bearer ${credential}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal,
    });
    const raw: unknown = await response.json().catch(() => null);
    const envelope = z.object({ code: z.string(), data: z.unknown().optional() }).safeParse(raw);
    if (!response.ok || !envelope.success || envelope.data.code !== 'SUCCESS')
      throw new MemoryApiError(
        response.status,
        envelope.success ? envelope.data.code : 'HTTP_ERROR',
      );
    const value = schema.safeParse(envelope.data.data);
    if (!value.success) throw new MemoryApiError(503, 'CLIENT_CONTRACT_MISMATCH');
    const records = Array.isArray(value.data) ? value.data : [value.data];
    for (const record of records) {
      const proposal = memoryProposalSchema.parse(record);
      if (proposal.topAgent !== checked.topAgent || proposal.sessionId !== checked.sessionId)
        throw new MemoryApiError(403, 'MEMORY_SCOPE_DENIED');
    }
    return value.data;
  }
  return {
    list(scope: MemoryScope, signal?: AbortSignal) {
      const query = new URLSearchParams({ ...scopeOf(scope), limit: '20' });
      return call(`?${query}`, scope, z.array(memoryProposalSchema).max(100), signal);
    },
    async decide(
      proposal: MemoryProposal,
      scope: MemoryScope,
      action: ProposalDecision,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) {
      const currentScope = scopeOf(scope);
      if (
        proposal.topAgent !== currentScope.topAgent ||
        proposal.sessionId !== currentScope.sessionId
      )
        throw new MemoryApiError(403, 'MEMORY_SCOPE_DENIED');
      const result = await call(
        `/${encodeURIComponent(proposal.id)}/decisions`,
        scope,
        memoryProposalSchema,
        signal,
        {
          ...currentScope,
          expectedProposalRevision: proposal.revision,
          expectedItemRevision: proposal.expectedItemRevision,
          action,
          idempotencyKey,
        },
      );
      if (result.id !== proposal.id) throw new MemoryApiError(503, 'CLIENT_CONTRACT_MISMATCH');
      return result;
    },
  };
}
