import { afterEach, expect, it, vi } from 'vitest';
import { ref, nextTick } from 'vue';
import { flushPromises } from '@vue/test-utils';
import { mountComposable } from '../../test/composable';
import { useMemoryPreferences } from '../../features/memory-preferences/useMemoryPreferences';
import { createMemoryApi, MemoryApiError } from '../../entities/memory/api';
import { preferenceSchema } from '../../entities/memory/schemas';
import type { MemoryApi, MemoryPreference, MemoryScope } from '../../entities/memory/model';
import { memoryAccessTokenKey } from '../../entities/memory/model';
import { cleanup, fireEvent, render, screen } from '@testing-library/vue';
import Antd from 'ant-design-vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import MemoryCenterPage from './MemoryCenterPage.vue';
import MemoryDetailPage from './MemoryDetailPage.vue';

const preference: MemoryPreference = {
  id: 'm1',
  versionId: 'v1',
  topAgent: 'operations',
  fieldKey: 'response.language',
  value: 'zh-CN',
  revision: 1,
  status: 'ACTIVE',
  sourceType: 'USER_PREFERENCE_DECISION',
  sourceRef: 'decision-1',
  expiresAt: '2026-12-01T00:00:00Z',
};
function fakeApi(): MemoryApi {
  return {
    list: vi.fn().mockResolvedValue({ items: [preference], total: 1, page: 1, pageSize: 20 }),
    detail: vi.fn().mockResolvedValue({ preference, history: [] }),
    save: vi.fn().mockResolvedValue(preference),
    correct: vi.fn().mockResolvedValue(preference),
  };
}
it('filters a just-forgotten value from a late list while keeping other rows, and only allows it after explicit restoration', async () => {
  const api = fakeApi(),
    scope = ref<MemoryScope>({ topAgent: 'operations' });
  let finish!: (value: Awaited<ReturnType<MemoryApi['list']>>) => void;
  vi.mocked(api.list).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const view = mountComposable(() => useMemoryPreferences(scope, api));
  view.result.current.revoke('m1');
  const other = {
    ...preference,
    id: 'other-item',
    fieldKey: 'response.format' as const,
    value: 'table',
  };
  finish({ items: [preference, other], total: 2, page: 1, pageSize: 20 });
  await flushPromises();
  expect(view.result.current.items.map((item) => item.id)).toEqual(['other-item']);
  expect(view.result.current.total).toBe(1);
  vi.mocked(api.list).mockResolvedValue({ items: [preference], total: 1, page: 1, pageSize: 20 });
  await view.result.current.load();
  expect(view.result.current.items).toEqual([]);
  view.result.current.restore('m1');
  await view.result.current.load();
  expect(view.result.current.items[0]?.id).toBe('m1');
  view.result.current.revoke('m1');
  scope.value = { topAgent: 'operations', sessionId: 'another-business-session' };
  await flushPromises();
  expect(view.result.current.items[0]?.id).toBe('m1');
  view.unmount();
});
it('aborts a forgotten target correction and ignores its late saved value without stopping other list reads', async () => {
  const api = fakeApi();
  const view = mountComposable(() => useMemoryPreferences(ref({ topAgent: 'operations' }), api));
  await flushPromises();
  view.result.current.edit(preference);
  let finish!: (item: MemoryPreference) => void;
  vi.mocked(api.correct).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const save = view.result.current.save();
  view.result.current.revoke(preference.id);
  expect(vi.mocked(api.correct).mock.calls[0]![3]!.aborted).toBe(true);
  finish({ ...preference, revision: 2, value: 'en-US' });
  await save;
  expect(view.result.current.items).toEqual([]);
  expect(view.result.current.success).toBe('');
  view.unmount();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function renderPage(
  component = MemoryCenterPage,
  path = '/ai-center/memories?topAgent=operations',
  authenticated = true,
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/ai-center/memories/:id?', component }],
  });
  await router.push(path);
  await router.isReady();
  render(component, {
    global: {
      plugins: [Antd, router],
      provide: {
        [memoryAccessTokenKey as symbol]: () => (authenticated ? 'offline-test-token' : undefined),
      },
    },
  });
  return router;
}
it('renders private boundaries with disabled unavailable features and requires login', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  await renderPage(MemoryCenterPage, '/ai-center/memories?topAgent=hr', false);
  expect(await screen.findByText('请先登录后管理记忆')).toBeTruthy();
  expect(screen.getByRole('button', { name: '保存偏好' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '跨 Agent 共享' })).toBeDisabled();
  expect(screen.getByText(/TASK_ONLY/)).toBeTruthy();
  expect(screen.queryByRole('log')).toBeNull();
  expect(fetcher).not.toHaveBeenCalled();
});
it('shows source/version/expiry and preserves correction UI after failed HTTP save', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            code: 'SUCCESS',
            data: { items: [preference], total: 1, page: 1, pageSize: 20 },
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            code: 'MEMORY_REVISION_CONFLICT',
            traceId: 'trace-conflict',
            data: null,
          }),
          { status: 409 },
        ),
      ),
  );
  await renderPage();
  await fireEvent.click(await screen.findByRole('button', { name: /更\s*正/ }));
  await fireEvent.submit(screen.getByRole('button', { name: '保存更正' }).closest('form')!);
  await flushPromises();
  expect(vi.mocked(fetch).mock.calls.length).toBe(2);
  expect(await screen.findByText(/版本冲突/)).toBeTruthy();
  expect(screen.getByText('版本 1')).toBeTruthy();
  expect(screen.getByText('用户明确设置')).toBeTruthy();
  expect(screen.queryByText('偏好已保存')).toBeNull();
});
it('does not display source or history when detail permission is denied', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ code: 'MEMORY_SCOPE_DENIED', data: null, traceId: 'denied' }),
          { status: 403 },
        ),
      ),
  );
  await renderPage(MemoryDetailPage, '/ai-center/memories/m1?topAgent=operations');
  expect(await screen.findByText(/无权查看当前记忆或来源/)).toBeTruthy();
  expect(screen.queryByText('decision-1')).toBeNull();
});

it('clears old Agent values immediately and ignores late responses after scope changes', async () => {
  const api = fakeApi();
  let finish!: (value: Awaited<ReturnType<MemoryApi['list']>>) => void;
  vi.mocked(api.list).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  vi.mocked(api.list).mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 20 });
  const scope = ref<MemoryScope>({ topAgent: 'operations', sessionId: 'session-a' });
  const view = mountComposable(() => useMemoryPreferences(scope, api));
  scope.value = { topAgent: 'customer-service', sessionId: 'session-b' };
  await nextTick();
  await flushPromises();
  finish({ items: [preference], total: 1, page: 1, pageSize: 20 });
  await flushPromises();
  expect(view.result.current.items).toEqual([]);
  expect(vi.mocked(api.list).mock.calls[0]![2]!.aborted).toBe(true);
  view.unmount();
});
it('clears same-scope private values and drafts when account changes or logs out', async () => {
  const api = fakeApi(),
    token = ref<string | undefined>('actor-a');
  const view = mountComposable(() =>
    useMemoryPreferences(ref({ topAgent: 'operations' }), api, () => token.value),
  );
  await flushPromises();
  view.result.current.edit(preference);
  view.result.current.draftValue = 'en-US';
  let late!: (value: Awaited<ReturnType<MemoryApi['list']>>) => void;
  vi.mocked(api.list).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        late = resolve;
      }),
  );
  token.value = 'actor-b';
  expect(view.result.current.items).toEqual([]);
  expect(view.result.current.editing).toBeUndefined();
  token.value = undefined;
  late({ items: [preference], total: 1, page: 1, pageSize: 20 });
  await flushPromises();
  expect(view.result.current.items).toEqual([]);
  expect(view.result.current.error).toContain('请先登录');
  expect(api.list).toHaveBeenCalledTimes(2);
  view.unmount();
});

it('keeps the current value and correction draft on 409 without success', async () => {
  const api = fakeApi();
  vi.mocked(api.correct).mockRejectedValue(
    new MemoryApiError(409, 'MEMORY_REVISION_CONFLICT', 'trace-409'),
  );
  const view = mountComposable(() => useMemoryPreferences(ref({ topAgent: 'operations' }), api));
  await flushPromises();
  view.result.current.edit(preference);
  view.result.current.draftValue = 'en-US';
  await view.result.current.save();
  expect(view.result.current.items[0]?.value).toBe('zh-CN');
  expect(view.result.current.draftValue).toBe('en-US');
  expect(view.result.current.success).toBe('');
  expect(view.result.current.error).toContain('冲突');
  expect(view.result.current.error).toContain('trace-409');
  view.unmount();
});

it('does not report success or write browser storage when saving fails', async () => {
  const api = fakeApi();
  vi.mocked(api.save).mockRejectedValue(new Error('offline'));
  const storage = vi.spyOn(Storage.prototype, 'setItem');
  const view = mountComposable(() => useMemoryPreferences(ref({ topAgent: 'operations' }), api));
  await flushPromises();
  await view.result.current.save();
  expect(view.result.current.success).toBe('');
  expect(view.result.current.error).toBeTruthy();
  expect(storage).not.toHaveBeenCalled();
  view.unmount();
});
it('removes previously displayed private values when refreshed authorization is denied', async () => {
  const api = fakeApi();
  const view = mountComposable(() => useMemoryPreferences(ref({ topAgent: 'operations' }), api));
  await flushPromises();
  view.result.current.edit(preference);
  vi.mocked(api.list).mockRejectedValueOnce(new MemoryApiError(403, 'MEMORY_SCOPE_DENIED'));
  await view.result.current.load();
  expect(view.result.current.items).toEqual([]);
  expect(view.result.current.editing).toBeUndefined();
  view.unmount();
});
it('clears private values if saving discovers the login has expired', async () => {
  const api = fakeApi();
  const view = mountComposable(() => useMemoryPreferences(ref({ topAgent: 'operations' }), api));
  await flushPromises();
  view.result.current.edit(preference);
  vi.mocked(api.correct).mockRejectedValueOnce(new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED'));
  await view.result.current.save();
  expect(view.result.current.items).toEqual([]);
  expect(view.result.current.editing).toBeUndefined();
  expect(view.result.current.success).toBe('');
  view.unmount();
});

it('uses real fetch with Bearer auth and safe typed scope, refusing absent auth before sending', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ code: 'SUCCESS', data: preference, traceId: 't' })),
    );
  const api = createMemoryApi(() => 'offline-test-token', fetcher);
  await api.save(
    { topAgent: 'operations', sessionId: 'business-session' },
    {
      fieldKey: 'response.language',
      value: 'zh-CN',
      expectedRevision: 0,
      idempotencyKey: 'request-1',
    },
  );
  const init = fetcher.mock.calls[0]![1] as RequestInit;
  expect(new Headers(init.headers).get('Authorization')).toBe('Bearer offline-test-token');
  expect(JSON.parse(init.body as string)).toEqual({
    topAgent: 'operations',
    sessionId: 'business-session',
    fieldKey: 'response.language',
    value: 'zh-CN',
    expectedRevision: 0,
    idempotencyKey: 'request-1',
  });
  await expect(
    createMemoryApi(() => undefined, fetcher).list({ topAgent: 'hr' }, 1),
  ).rejects.toMatchObject({ status: 401 });
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it('refuses unauthorized source details and never renders server error body', async () => {
  const api = createMemoryApi(
    () => 'offline-test-token',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'MEMORY_SCOPE_DENIED',
          message: 'sensitive-server-text',
          data: null,
          traceId: 'trace-denied',
        }),
        { status: 403 },
      ),
    ),
  );
  await expect(api.detail('m1', { topAgent: 'customer-service' })).rejects.toMatchObject({
    code: 'MEMORY_SCOPE_DENIED',
    traceId: 'trace-denied',
  });
  try {
    await api.detail('m1', { topAgent: 'customer-service' });
  } catch (error) {
    expect((error as Error).message).not.toContain('sensitive-server-text');
  }
});

it('validates the three field value domains and refuses unsupported Agents', () => {
  expect(preferenceSchema.safeParse(preference).success).toBe(true);
  expect(preferenceSchema.safeParse({ ...preference, value: 'arbitrary' }).success).toBe(false);
  expect(preferenceSchema.safeParse({ ...preference, topAgent: 'invented-agent' }).success).toBe(
    false,
  );
  expect(
    preferenceSchema.safeParse({ ...preference, fieldKey: 'response.format', value: 'table' })
      .success,
  ).toBe(true);
});
