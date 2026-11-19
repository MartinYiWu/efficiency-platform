import { z } from 'zod';
import { MemoryApiError } from './api';
import { fieldSchema } from './schemas';
import type { MemoryPreference } from './model';

const id = z.string().min(1);
const revision = z.number().int().nonnegative();
const agent = z.enum(['operations', 'customer-service']);
const deadline = z.string().datetime({ offset: true });
export const agentGrantSchema = z.object({
  id,
  itemId: id,
  versionId: id,
  fieldKey: fieldSchema,
  originAgent: agent,
  targetAgent: agent,
  revision,
  status: z.enum(['ACTIVE', 'REVOKED']),
  expiresAt: deadline,
  indexStatus: z.literal('NOT_REQUESTED'),
});
export const sharedScopeSchema = z.object({
  id,
  scopeType: z.enum(['PROJECT', 'DEPARTMENT', 'ORGANIZATION']),
  departmentId: id.nullable(),
  ownerUserId: id,
  approverUserId: id,
  revision,
  status: z.enum(['PENDING', 'ACTIVE']),
  membershipStatus: z.enum(['INVITED', 'ACTIVE', 'LEFT']).nullable(),
  membershipRevision: revision.nullable(),
  expiresAt: deadline,
});
export const sharedMemorySchema = z.object({
  id,
  scopeId: id,
  itemId: id,
  versionId: id,
  fieldKey: fieldSchema,
  originAgent: agent,
  allowedAgents: z.array(agent).min(1).max(2),
  ownerUserId: id,
  revision,
  status: z.enum(['PENDING', 'ACTIVE', 'REVOKED']),
  expiresAt: deadline,
  indexStatus: z.literal('NOT_REQUESTED'),
});
export type AgentMemoryGrant = z.infer<typeof agentGrantSchema>;
export type SharedMemoryScope = z.infer<typeof sharedScopeSchema>;
export type SharedMemory = z.infer<typeof sharedMemorySchema>;
export type SharingAgent = z.infer<typeof agent>;

export function createMemorySharingApi(
  token: () => string | undefined,
  fetcher: typeof fetch = fetch,
) {
  const base =
    (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') + '/api/aihub/memory-sharing';
  async function call<T>(
    path: string,
    schema: z.ZodType<T>,
    signal?: AbortSignal,
    body?: object,
  ): Promise<T> {
    const credential = token();
    if (!credential) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
    const response = await fetcher(`${base}${path}`, {
      method: body ? 'POST' : 'GET',
      signal,
      headers: {
        Authorization: `Bearer ${credential}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const envelope = z
      .object({ code: z.string(), data: z.unknown().optional() })
      .safeParse(await response.json().catch(() => null));
    if (!response.ok || !envelope.success || envelope.data.code !== 'SUCCESS')
      throw new MemoryApiError(
        response.status,
        envelope.success ? envelope.data.code : 'HTTP_ERROR',
      );
    const result = schema.safeParse(envelope.data.data);
    if (!result.success) throw new MemoryApiError(503, 'CLIENT_CONTRACT_MISMATCH');
    return result.data;
  }
  const pathId = (value: string) => encodeURIComponent(id.parse(value));
  const preference = (item: MemoryPreference) => {
    agent.parse(item.topAgent);
    return {
      originAgent: item.topAgent,
      itemId: item.id,
      versionId: item.versionId,
      expectedItemRevision: item.revision,
    };
  };
  return {
    grants: async (originAgent: SharingAgent, signal?: AbortSignal) => {
      const records = await call(
        `/agent-grants?${new URLSearchParams({ originAgent: agent.parse(originAgent) })}`,
        z.array(agentGrantSchema),
        signal,
      );
      if (records.some((record) => record.originAgent !== originAgent))
        throw new MemoryApiError(403, 'MEMORY_SCOPE_DENIED');
      return records;
    },
    grant: (
      item: MemoryPreference,
      targetAgent: SharingAgent,
      expiresAt: string,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call('/agent-grants', agentGrantSchema, signal, {
        ...preference(item),
        targetAgent: agent.parse(targetAgent),
        expiresAt: deadline.parse(expiresAt),
        idempotencyKey,
      }),
    withdrawGrant: (grant: AgentMemoryGrant, idempotencyKey: string, signal?: AbortSignal) =>
      call(`/agent-grants/${pathId(grant.id)}/withdrawals`, agentGrantSchema, signal, {
        expectedRevision: grant.revision,
        idempotencyKey,
      }),
    scopes: (signal?: AbortSignal) => call('/scopes', z.array(sharedScopeSchema), signal),
    createScope: (
      body: {
        scopeType: SharedMemoryScope['scopeType'];
        departmentId: string | null;
        approverUserId: string;
        expiresAt: string;
        idempotencyKey: string;
      },
      signal?: AbortSignal,
    ) => call('/scopes', sharedScopeSchema, signal, body),
    approveScope: (scope: SharedMemoryScope, idempotencyKey: string, signal?: AbortSignal) =>
      call(`/scopes/${pathId(scope.id)}/approvals`, sharedScopeSchema, signal, {
        expectedRevision: scope.revision,
        idempotencyKey,
      }),
    invite: (
      scope: SharedMemoryScope,
      userId: string,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call(`/scopes/${pathId(scope.id)}/members`, sharedScopeSchema, signal, {
        userId: id.parse(userId),
        expectedRevision: scope.revision,
        idempotencyKey,
      }),
    membership: (
      scope: SharedMemoryScope,
      action: 'ACCEPT' | 'LEAVE',
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call(`/scopes/${pathId(scope.id)}/membership`, sharedScopeSchema, signal, {
        expectedRevision: scope.membershipRevision ?? scope.revision,
        action,
        idempotencyKey,
      }),
    shares: async (scopeId: string, signal?: AbortSignal) => {
      const result = await call(
        `/scopes/${pathId(scopeId)}/shares`,
        z.array(sharedMemorySchema),
        signal,
      );
      if (result.some((item) => item.scopeId !== scopeId))
        throw new MemoryApiError(403, 'MEMORY_SCOPE_DENIED');
      return result;
    },
    share: (
      scope: SharedMemoryScope,
      item: MemoryPreference,
      allowedAgents: SharingAgent[],
      expiresAt: string,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call(`/scopes/${pathId(scope.id)}/shares`, sharedMemorySchema, signal, {
        ...preference(item),
        allowedAgents: z.array(agent).min(1).max(2).parse(allowedAgents),
        expiresAt: deadline.parse(expiresAt),
        idempotencyKey,
      }),
    approveShare: (share: SharedMemory, idempotencyKey: string, signal?: AbortSignal) =>
      call(`/shares/${pathId(share.id)}/approvals`, sharedMemorySchema, signal, {
        expectedRevision: share.revision,
        idempotencyKey,
      }),
    withdrawShare: (share: SharedMemory, idempotencyKey: string, signal?: AbortSignal) =>
      call(`/shares/${pathId(share.id)}/withdrawals`, sharedMemorySchema, signal, {
        expectedRevision: share.revision,
        idempotencyKey,
      }),
  };
}
