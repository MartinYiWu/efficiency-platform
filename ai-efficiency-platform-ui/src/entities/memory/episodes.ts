import { z } from 'zod';
import { MemoryApiError } from './api';
import type { MemoryScope } from './model';

const id = z.string().min(1);
const instant = z.string().datetime({ offset: true });
export const episodeContentSchema = z.object({
  category: z.enum(['USER_PREFERENCE', 'MEASURED_RESULT', 'TECHNICAL_EXPERIENCE']),
  scenario: z.string().min(1).max(2048),
  preconditions: z.array(z.string().min(1)).max(16),
  actions: z.array(z.string().min(1)).min(1).max(16),
  observedResults: z.string().min(1).max(4096),
  denominator: z.number().int().positive().nullable(),
  observedFrom: instant.nullable(),
  observedUntil: instant.nullable(),
  evidenceRefs: z.array(id).min(1).max(128),
  applicableVersion: id,
  disallowedConditions: z.array(z.string().min(1)).max(16),
});
export const memoryEpisodeSchema = z.object({
  id,
  topAgent: z.enum(['operations', 'customer-service', 'hr']),
  sessionId: id.nullable(),
  content: episodeContentSchema.nullable(),
  status: z.enum(['CANDIDATE', 'CONFIRMED', 'REJECTED', 'SHARE_PENDING', 'SHARED', 'REVOKED']),
  revision: z.number().int().nonnegative(),
  expiresAt: instant,
  feedbackLikes: z.number().int().nonnegative(),
});
export const memoryPromotionSchema = z.object({
  id,
  episodeId: id,
  targetType: z.enum(['PROMPT', 'WORKFLOW', 'SKILL']),
  targetDefinitionId: id,
  targetVersionId: id,
  candidateDigest: z.string().regex(/^[0-9a-f]{64}$/),
  status: z.enum(['DRAFT', 'REGRESSION_PASSED', 'PUBLISHED', 'REVOKED']),
  revision: z.number().int().nonnegative(),
  regressionReportSha256: z
    .string()
    .regex(/^[0-9a-f]{64}$/)
    .nullable(),
});
export type EpisodeContent = z.infer<typeof episodeContentSchema>;
export type MemoryEpisode = z.infer<typeof memoryEpisodeSchema>;
export type MemoryPromotion = z.infer<typeof memoryPromotionSchema>;
export type PromotionInput = {
  targetType: MemoryPromotion['targetType'];
  targetDefinitionId: string;
  semanticVersion: string;
  changeSummary: string;
  graphKey: string | null;
  graphVersion: string | null;
};

export function createMemoryEpisodeApi(
  token: () => string | undefined,
  fetcher: typeof fetch = fetch,
) {
  const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '') + '/api/aihub';
  const checkedScope = (scope: MemoryScope) => ({
    topAgent: scope.topAgent,
    sessionId: scope.topAgent === 'hr' ? null : (scope.sessionId ?? null),
  });
  async function call<T>(path: string, schema: z.ZodType<T>, signal?: AbortSignal, body?: object) {
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
    const value = schema.safeParse(envelope.data.data);
    if (!value.success) throw new MemoryApiError(503, 'CLIENT_CONTRACT_MISMATCH');
    return value.data;
  }
  return {
    async list(scope: MemoryScope, signal?: AbortSignal) {
      const params = new URLSearchParams({ topAgent: scope.topAgent });
      if (scope.sessionId && scope.topAgent !== 'hr') params.set('sessionId', scope.sessionId);
      const result = await call(`/memory-episodes?${params}`, z.array(memoryEpisodeSchema), signal);
      if (
        result.some(
          (item) =>
            item.topAgent !== scope.topAgent || item.sessionId !== checkedScope(scope).sessionId,
        )
      )
        throw new MemoryApiError(403, 'MEMORY_SCOPE_DENIED');
      return result;
    },
    create: (
      scope: MemoryScope,
      executionId: string,
      content: EpisodeContent,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call('/memory-episodes', memoryEpisodeSchema, signal, {
        ...checkedScope(scope),
        executionId,
        content: episodeContentSchema.parse(content),
        idempotencyKey,
      }),
    shared: (shareScopeId: string, signal?: AbortSignal) =>
      call(
        `/memory-episodes/shared?${new URLSearchParams({ shareScopeId: id.parse(shareScopeId) })}`,
        z.array(memoryEpisodeSchema),
        signal,
      ),
    decide: (
      episode: MemoryEpisode,
      scope: MemoryScope,
      action: 'CONFIRM' | 'REJECT',
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call(
        `/memory-episodes/${encodeURIComponent(episode.id)}/decisions`,
        memoryEpisodeSchema,
        signal,
        { ...checkedScope(scope), expectedRevision: episode.revision, action, idempotencyKey },
      ),
    proposePromotion: (
      episode: MemoryEpisode,
      scope: MemoryScope,
      input: PromotionInput,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call('/memory-promotions', memoryPromotionSchema, signal, {
        episodeId: episode.id,
        ...checkedScope(scope),
        expectedEpisodeRevision: episode.revision,
        ...input,
        idempotencyKey,
      }),
    sharing: (
      episode: MemoryEpisode,
      scope: MemoryScope,
      shareScopeId: string,
      deidentifiedContent: EpisodeContent,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call(
        `/memory-episodes/${encodeURIComponent(episode.id)}/sharing`,
        memoryEpisodeSchema,
        signal,
        {
          ...checkedScope(scope),
          expectedRevision: episode.revision,
          shareScopeId,
          deidentifiedContent: episodeContentSchema.parse(deidentifiedContent),
          idempotencyKey,
        },
      ),
    approveSharing: (episode: MemoryEpisode, idempotencyKey: string, signal?: AbortSignal) =>
      call(
        `/memory-episodes/${encodeURIComponent(episode.id)}/sharing-approvals`,
        memoryEpisodeSchema,
        signal,
        { expectedRevision: episode.revision, idempotencyKey },
      ),
    like: (episode: MemoryEpisode, scope: MemoryScope, signal?: AbortSignal) =>
      call(
        `/memory-episodes/${encodeURIComponent(episode.id)}/likes`,
        memoryEpisodeSchema,
        signal,
        checkedScope(scope),
      ),
    withdraw: (
      episode: MemoryEpisode,
      scope: MemoryScope,
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call(
        `/memory-episodes/${encodeURIComponent(episode.id)}/withdrawals`,
        memoryEpisodeSchema,
        signal,
        { ...checkedScope(scope), expectedRevision: episode.revision, idempotencyKey },
      ),
    promotions: (signal?: AbortSignal) =>
      call('/memory-promotions', z.array(memoryPromotionSchema), signal),
    regression: (
      promotion: MemoryPromotion,
      proof: {
        suiteId: string;
        suiteVersion: string;
        reportSha256: string;
        totalCases: number;
        passedCases: number;
      },
      idempotencyKey: string,
      signal?: AbortSignal,
    ) =>
      call(
        `/memory-promotions/${encodeURIComponent(promotion.id)}/regressions`,
        memoryPromotionSchema,
        signal,
        {
          expectedRevision: promotion.revision,
          candidateDigest: promotion.candidateDigest,
          ...proof,
          idempotencyKey,
        },
      ),
    publish: (promotion: MemoryPromotion, idempotencyKey: string, signal?: AbortSignal) =>
      call(
        `/memory-promotions/${encodeURIComponent(promotion.id)}/publications`,
        memoryPromotionSchema,
        signal,
        { expectedRevision: promotion.revision, action: 'APPROVE_PUBLISH', idempotencyKey },
      ),
  };
}
