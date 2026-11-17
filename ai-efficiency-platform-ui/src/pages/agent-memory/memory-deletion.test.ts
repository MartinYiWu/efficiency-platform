import { afterEach, expect, it, vi } from 'vitest';
import { nextTick, ref } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { cleanup, fireEvent, render, screen } from '@testing-library/vue';
import Antd from 'ant-design-vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import MemoryCenterPage from './MemoryCenterPage.vue';
import MemoryDetailPage from './MemoryDetailPage.vue';
import { mountComposable } from '../../test/composable';
import { useMemoryDeletion } from '../../features/memory-preferences/useMemoryDeletion';
import MemoryDeletionPanel from '../../features/memory-preferences/MemoryDeletionPanel.vue';
import { createMemoryApi, MemoryApiError } from '../../entities/memory/api';
import {
  memoryAccessTokenKey,
  type MemoryDeletionApi,
  type MemoryDeletionTask,
  type MemoryPreference,
  type MemoryScope,
} from '../../entities/memory/model';

const item: MemoryPreference = {
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
const pending: MemoryDeletionTask = {
  jobId: 'job1',
  itemId: 'm1',
  status: 'DELETE_PENDING',
  jobStatus: 'BLOCKED',
  revision: 2,
  deletionEpoch: 1,
  suppressionId: 'sup1',
  suppressionRevision: 1,
  requiredTargets: 6,
  completedTargets: 0,
};
const deleted: MemoryDeletionTask = {
  ...pending,
  status: 'DELETED',
  jobStatus: 'SUCCEEDED',
  completedTargets: 6,
};
function api(): MemoryDeletionApi {
  return {
    forget: vi.fn().mockResolvedValue(pending),
    deletion: vi.fn().mockResolvedValue(pending),
    reauthorize: vi.fn().mockResolvedValue({ ...item, versionId: 'new-v', revision: 3 }),
  };
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it('keeps unrelated delayed list rows when a historical pending deletion job arrives first', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/memory', component: MemoryCenterPage }],
  });
  await router.push('/memory?topAgent=operations&jobId=job1');
  await router.isReady();
  let completeList!: (response: Response) => void, listSignal: AbortSignal | undefined;
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('memory-deletions'))
        return Promise.resolve(new Response(JSON.stringify({ code: 'SUCCESS', data: pending })));
      listSignal = init?.signal as AbortSignal;
      return new Promise<Response>((resolve) => {
        completeList = resolve;
      });
    }),
  );
  const wrapper = mount(MemoryCenterPage, {
    global: {
      plugins: [Antd, router],
      provide: { [memoryAccessTokenKey as symbol]: () => 'same-actor' },
    },
  });
  await flushPromises();
  expect(wrapper.text()).toContain('清理中，尚未全部确认');
  expect(listSignal?.aborted).toBe(false);
  const remaining = [
    { ...item, id: 'detail-item', fieldKey: 'response.detail_level', value: 'detailed' },
    { ...item, id: 'format-item', fieldKey: 'response.format', value: 'table' },
  ];
  completeList(
    new Response(
      JSON.stringify({
        code: 'SUCCESS',
        data: { items: remaining, total: 2, page: 1, pageSize: 20 },
      }),
    ),
  );
  await flushPromises();
  expect(wrapper.findAll('tbody tr')).toHaveLength(2);
  expect(wrapper.text()).toContain('详细程度');
  expect(wrapper.text()).toContain('回复格式');
  wrapper.unmount();
});

it.each(
  [MemoryCenterPage, MemoryDetailPage].flatMap((component) =>
    [401, 403, 404].map((status) => ({ component, status })),
  ),
)(
  'clears child task memory and aborts late jobs when parent GET is denied with unchanged token ($status)',
  async ({ component, status }) => {
    const token = ref('same-actor-token');
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/memory/:id?', component }],
    });
    await router.push('/memory/m1?topAgent=operations&jobId=job1');
    await router.isReady();
    let denyParent = false,
      finishJob!: (response: Response) => void,
      jobSignal: AbortSignal | undefined;
    let deferJob = false;
    const fetcher = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('memory-deletions')) {
        if (deferJob) {
          jobSignal = init?.signal as AbortSignal;
          return new Promise<Response>((resolve) => {
            finishJob = resolve;
          });
        }
        return Promise.resolve(new Response(JSON.stringify({ code: 'SUCCESS', data: deleted })));
      }
      if (url.includes('memory-suppressions'))
        return Promise.reject(new TypeError('unknown network result'));
      return Promise.resolve(
        new Response(
          JSON.stringify(
            denyParent
              ? {
                  code:
                    status === 401
                      ? 'MEMORY_IDENTITY_REQUIRED'
                      : status === 403
                        ? 'MEMORY_SCOPE_DENIED'
                        : 'MEMORY_NOT_FOUND',
                  data: null,
                }
              : {
                  code: 'SUCCESS',
                  data:
                    component === MemoryCenterPage
                      ? { items: [], total: 0, page: 1, pageSize: 20 }
                      : { preference: item, history: [item] },
                },
          ),
          { status: denyParent ? status : 200 },
        ),
      );
    });
    vi.stubGlobal('fetch', fetcher);
    const wrapper = mount(component, {
      global: {
        plugins: [Antd, router],
        provide: { [memoryAccessTokenKey as symbol]: () => token.value },
      },
    });
    await flushPromises();
    const panel = wrapper.findComponent(MemoryDeletionPanel);
    const state = panel.vm as unknown as {
      task?: MemoryDeletionTask;
      target?: unknown;
      relearnField?: string;
      relearnValue: string;
      refresh: (jobId?: string) => Promise<void>;
      reauthorize: () => Promise<void>;
    };
    expect(state.task?.status).toBe('DELETED');
    state.relearnField = 'response.language';
    state.relearnValue = 'en-US';
    await state.reauthorize();
    expect(state.relearnValue).toBe('en-US');
    deferJob = true;
    const late = state.refresh('job1');
    await flushPromises();
    denyParent = true;
    await (wrapper.vm as unknown as { load: () => Promise<void> }).load();
    await flushPromises();
    expect(token.value).toBe('same-actor-token');
    expect(state.task).toBeUndefined();
    expect(state.target).toBeUndefined();
    expect(state.relearnField).toBeUndefined();
    expect(state.relearnValue).toBe('');
    expect(jobSignal?.aborted).toBe(true);
    expect(wrapper.find('[aria-label="偏好遗忘任务"]').exists()).toBe(false);
    const requests = fetcher.mock.calls.length;
    finishJob(new Response(JSON.stringify({ code: 'SUCCESS', data: deleted })));
    await late;
    await flushPromises();
    expect(state.task).toBeUndefined();
    expect(fetcher).toHaveBeenCalledTimes(requests);
    await state.reauthorize();
    expect(fetcher).toHaveBeenCalledTimes(requests);
    wrapper.unmount();
  },
);

it('keeps a stable forget key after unknown network failure and only revokes on accepted HTTP', async () => {
  const service = api(),
    revoked = vi.fn();
  vi.mocked(service.forget)
    .mockRejectedValueOnce(new TypeError('network'))
    .mockResolvedValueOnce(pending);
  const view = mountComposable(() =>
    useMemoryDeletion(ref({ topAgent: 'operations' }), service, () => 'actor', revoked),
  );
  view.result.current.choose(item);
  await view.result.current.forget();
  expect(revoked).not.toHaveBeenCalled();
  expect(view.result.current.task).toBeUndefined();
  await view.result.current.forget();
  expect(vi.mocked(service.forget).mock.calls[0]![1].idempotencyKey).toBe(
    vi.mocked(service.forget).mock.calls[1]![1].idempotencyKey,
  );
  expect(view.result.current.task?.status).toBe('DELETE_PENDING');
  expect(view.result.current.complete).toBe(false);
  expect(revoked).toHaveBeenCalledWith('m1', 'job1');
  view.unmount();
});
it('refreshes jobs with GET only and cannot reauthorize pending or inconsistent completion', async () => {
  const service = api();
  const view = mountComposable(() =>
    useMemoryDeletion(ref({ topAgent: 'operations' }), service, () => 'actor'),
  );
  await view.result.current.refresh('job1');
  view.result.current.relearnField = 'response.language';
  view.result.current.relearnValue = 'en-US';
  await view.result.current.reauthorize();
  expect(service.reauthorize).not.toHaveBeenCalled();
  expect(service.forget).not.toHaveBeenCalled();
  vi.mocked(service.deletion).mockResolvedValueOnce({ ...deleted, jobStatus: 'BLOCKED' });
  await view.result.current.refresh('job1');
  expect(view.result.current.complete).toBe(false);
  vi.mocked(service.deletion).mockResolvedValueOnce(deleted);
  await view.result.current.refresh('job1');
  expect(view.result.current.complete).toBe(true);
  expect(service.reauthorize).not.toHaveBeenCalled();
  await view.result.current.reauthorize();
  expect(service.reauthorize).toHaveBeenCalledWith(
    'sup1',
    { topAgent: 'operations' },
    expect.objectContaining({
      itemId: 'm1',
      expectedRevision: 2,
      expected_suppression_revision: 1,
      confirmation: 'ALLOW_REMEMBER',
      fieldKey: 'response.language',
      value: 'en-US',
    }),
    expect.any(AbortSignal),
  );
  view.unmount();
});
it('preserves current target and draft on 409 and clears all private task state on identity changes', async () => {
  const service = api(),
    token = ref<string | undefined>('actor-a'),
    revoked = vi.fn();
  vi.mocked(service.forget).mockRejectedValueOnce(
    new MemoryApiError(409, 'MEMORY_REVISION_CONFLICT'),
  );
  const scope = ref<MemoryScope>({ topAgent: 'operations', sessionId: 's1' });
  const view = mountComposable(() => useMemoryDeletion(scope, service, () => token.value, revoked));
  view.result.current.choose(item);
  await view.result.current.forget();
  expect(view.result.current.target?.itemId).toBe('m1');
  expect(revoked).not.toHaveBeenCalled();
  let late!: (value: MemoryDeletionTask) => void;
  vi.mocked(service.deletion).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        late = resolve;
      }),
  );
  const old = view.result.current.refresh('job1');
  token.value = 'actor-b';
  await nextTick();
  late(deleted);
  await old;
  expect(view.result.current.task).toBeUndefined();
  expect(view.result.current.target).toBeUndefined();
  expect(view.result.current.relearnField).toBeUndefined();
  expect(revoked).not.toHaveBeenCalled();
  token.value = undefined;
  await view.result.current.refresh('job1');
  expect(service.deletion).toHaveBeenCalledTimes(1);
  view.unmount();
});
it('refuses a task response for another requested job and does not revoke unrelated data', async () => {
  const service = api(),
    revoked = vi.fn();
  vi.mocked(service.deletion).mockResolvedValue({ ...pending, jobId: 'other-job' });
  const view = mountComposable(() =>
    useMemoryDeletion(ref({ topAgent: 'operations' }), service, () => 'actor', revoked),
  );
  await view.result.current.refresh('job1');
  expect(view.result.current.task).toBeUndefined();
  expect(revoked).not.toHaveBeenCalled();
  view.unmount();
});
it('preserves explicit reauthorization draft and key on unknown failure, then clears it on account change', async () => {
  const service = api(),
    token = ref('actor-a');
  vi.mocked(service.reauthorize)
    .mockRejectedValueOnce(new TypeError('network'))
    .mockRejectedValueOnce(new MemoryApiError(409, 'MEMORY_REVISION_CONFLICT'));
  vi.mocked(service.deletion).mockResolvedValue(deleted);
  const view = mountComposable(() =>
    useMemoryDeletion(ref({ topAgent: 'operations' }), service, () => token.value),
  );
  await view.result.current.refresh('job1');
  view.result.current.relearnField = 'response.language';
  view.result.current.relearnValue = 'en-US';
  await view.result.current.reauthorize();
  await view.result.current.reauthorize();
  expect(vi.mocked(service.reauthorize).mock.calls[0]![2].idempotencyKey).toBe(
    vi.mocked(service.reauthorize).mock.calls[1]![2].idempotencyKey,
  );
  expect(view.result.current.relearnValue).toBe('en-US');
  expect(view.result.current.success).toBe('');
  token.value = 'actor-b';
  expect(view.result.current.task).toBeUndefined();
  expect(view.result.current.relearnField).toBeUndefined();
  expect(view.result.current.relearnValue).toBe('');
  view.unmount();
});
it('uses D15 exact paths and camel/snake fields with Bearer and no private identity body', async () => {
  const fetcher = vi
    .fn()
    .mockImplementation((_url, init) =>
      Promise.resolve(
        new Response(
          JSON.stringify({ code: 'SUCCESS', data: init?.method === 'GET' ? deleted : pending }),
        ),
      ),
    );
  const service = createMemoryApi(() => 'offline-fixture', fetcher);
  await service.forget(
    { topAgent: 'operations' },
    {
      itemId: 'm1',
      expectedRevision: 1,
      idempotencyKey: 'stable-key',
      mode: 'FORGET_AND_SUPPRESS',
    },
  );
  await service.deletion('job1', { topAgent: 'operations' });
  expect(fetcher.mock.calls[0]![0]).toContain('/api/aihub/memory-deletions');
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toEqual({
    topAgent: 'operations',
    itemId: 'm1',
    expectedRevision: 1,
    idempotencyKey: 'stable-key',
    mode: 'FORGET_AND_SUPPRESS',
  });
  expect(fetcher.mock.calls[1]![1].method).toBe('GET');
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'SUCCESS', data: item })));
  await service.reauthorize(
    'sup1',
    { topAgent: 'operations' },
    {
      itemId: 'm1',
      fieldKey: 'response.language',
      value: 'en-US',
      expectedRevision: 2,
      expected_suppression_revision: 1,
      idempotencyKey: 'explicit',
      confirmation: 'ALLOW_REMEMBER',
    },
  );
  expect(fetcher.mock.calls[2]![0]).toContain(
    '/api/aihub/memory-suppressions/sup1/reauthorizations',
  );
  expect(JSON.parse(fetcher.mock.calls[2]![1].body)).toMatchObject({
    expected_suppression_revision: 1,
    confirmation: 'ALLOW_REMEMBER',
  });
});
it('asks for explicit forget confirmation and never labels pending as fully deleted', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: pending }))),
  );
  render(MemoryDeletionPanel, {
    props: { scope: { topAgent: 'operations' }, target: item },
    global: {
      plugins: [Antd],
      provide: { [memoryAccessTokenKey as symbol]: () => 'offline-fixture' },
    },
  });
  expect(screen.getByText('忘记并停止自动记住此偏好')).toBeTruthy();
  expect(fetch).not.toHaveBeenCalled();
  await fireEvent.click(screen.getByRole('button', { name: '确认忘记' }));
  await flushPromises();
  expect(screen.getByText(/清理中/)).toBeTruthy();
  expect(screen.queryByText('已清理')).toBeNull();
  expect(screen.queryByRole('button', { name: '重新允许记住' })).toBeNull();
});
it('does not claim deletion or revocation for an unknown task state', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: { ...pending, status: 'UNKNOWN', jobStatus: 'FAILED' },
        }),
      ),
    ),
  );
  render(MemoryDeletionPanel, {
    props: { scope: { topAgent: 'operations' }, jobId: 'job1' },
    global: {
      plugins: [Antd],
      provide: { [memoryAccessTokenKey as symbol]: () => 'offline-fixture' },
    },
  });
  await flushPromises();
  expect(screen.getByRole('heading', { name: '状态暂无法确认' })).toBeTruthy();
  expect(screen.queryByText(/相关偏好已停止使用/)).toBeNull();
  expect(screen.queryByRole('button', { name: '重新允许记住' })).toBeNull();
});
it('shows an old succeeded job with a LIVE item as reconfigured and never offers its reauthorization', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ code: 'SUCCESS', data: { ...deleted, status: 'LIVE', revision: 3 } }),
        ),
      ),
  );
  render(MemoryDeletionPanel, {
    props: { scope: { topAgent: 'operations' }, jobId: 'job1' },
    global: {
      plugins: [Antd],
      provide: { [memoryAccessTokenKey as symbol]: () => 'offline-fixture' },
    },
  });
  await flushPromises();
  expect(screen.getByText('该次清理已完成，偏好已重新设置')).toBeTruthy();
  expect(screen.queryByRole('button', { name: '重新允许记住' })).toBeNull();
  expect(screen.queryByText('已清理', { exact: true })).toBeNull();
  expect(vi.mocked(fetch).mock.calls.every((call) => call[1]?.method === 'GET')).toBe(true);
});
it.each([MemoryCenterPage, MemoryDetailPage])(
  'removes old value/source/history only after forget is accepted in the page',
  async (component) => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/memory/:id?', component }],
    });
    await router.push(
      component === MemoryCenterPage
        ? '/memory?topAgent=operations'
        : '/memory/m1?topAgent=operations',
    );
    await router.isReady();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('memory-deletions'))
          return Promise.resolve(new Response(JSON.stringify({ code: 'SUCCESS', data: pending })));
        return Promise.resolve(
          new Response(
            JSON.stringify({
              code: 'SUCCESS',
              data:
                component === MemoryCenterPage
                  ? { items: [item], total: 1, page: 1, pageSize: 20 }
                  : { preference: item, history: [item] },
            }),
          ),
        );
      }),
    );
    render(component, {
      global: {
        plugins: [Antd, router],
        provide: { [memoryAccessTokenKey as symbol]: () => 'offline-fixture' },
      },
    });
    await fireEvent.click(await screen.findByRole('button', { name: /^忘\s*记$/ }));
    await fireEvent.click(screen.getByRole('button', { name: '确认忘记' }));
    await flushPromises();
    expect(screen.getByText(/清理中/)).toBeTruthy();
    expect(screen.queryByText('decision-1')).toBeNull();
    expect(screen.queryByText('简体中文', { selector: 'strong' })).toBeNull();
    expect(router.currentRoute.value.query.jobId).toBe('job1');
  },
);
