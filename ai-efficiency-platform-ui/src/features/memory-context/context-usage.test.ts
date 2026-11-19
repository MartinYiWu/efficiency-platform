import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/vue';
import { flushPromises } from '@vue/test-utils';
import { createContextUsageApi } from '../../entities/memory/context';
import { memoryAccessTokenKey } from '../../entities/memory';
import ContextUsagePanel from './ContextUsagePanel.vue';

const usage = {
  topAgent: 'operations',
  sessionId: 'session-one',
  runId: 'run-one',
  status: 'AVAILABLE',
  summaries: [],
  operations: [
    {
      nodeId: 'direct',
      inputTokens: 700,
      inputLimit: 2000,
      freeTokens: 1300,
      cpuBeforeTokens: 900,
      cpuAfterTokens: 700,
      summaryBeforeTokens: 0,
      summaryAfterTokens: 0,
      outputReserveTokens: 300,
      windowStatus: 'ALLOW',
      summaryCasStatus: 'not-applied',
      summaryAdoptionStatus: 'not-applied',
      feeStatus: 'NOT_REPORTED',
      costMicrounits: null,
      omissions: [{ reason: 'HISTORY_LIMIT', count: 2 }],
    },
  ],
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('only reads stored usage on expansion and refresh, without estimating missing cost', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: usage })));
  vi.stubGlobal('fetch', fetcher);
  render(ContextUsagePanel, {
    props: { topAgent: 'operations', sessionId: 'session-one', runId: 'run-one' },
    global: { provide: { [memoryAccessTokenKey as symbol]: () => 'synthetic-token' } },
  });
  expect(fetcher).not.toHaveBeenCalled();
  await fireEvent.click(screen.getByRole('button', { name: '查看上下文与摘要' }));
  await flushPromises();
  expect(screen.getByText('尚未同步实际费用')).toBeTruthy();
  expect(screen.getByText('历史条数上限：2 项')).toBeTruthy();
  fetcher.mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: usage })));
  await fireEvent.click(screen.getByRole('button', { name: '刷新记录' }));
  await flushPromises();
  expect(fetcher).toHaveBeenCalledTimes(2);
  for (const [, options] of fetcher.mock.calls) expect(options.method).toBe('GET');
});

it('rejects cross-session data and never requests without a credential', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: usage })));
  await expect(
    createContextUsageApi(() => undefined, fetcher).read({
      topAgent: 'operations',
      sessionId: 'session-one',
    }),
  ).rejects.toMatchObject({ status: 401 });
  expect(fetcher).not.toHaveBeenCalled();
  await expect(
    createContextUsageApi(() => 'synthetic-token', fetcher).read({
      topAgent: 'operations',
      sessionId: 'other-session',
      runId: 'run-one',
    }),
  ).rejects.toMatchObject({ status: 403 });
});

it('clears private usage on a scope switch and ignores a late old response', async () => {
  let release!: (response: Response) => void;
  const fetcher = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    )
    .mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: { ...usage, sessionId: 'session-two', operations: [] },
        }),
      ),
    );
  vi.stubGlobal('fetch', fetcher);
  const view = render(ContextUsagePanel, {
    props: { topAgent: 'operations', sessionId: 'session-one', runId: 'run-one' },
    global: { provide: { [memoryAccessTokenKey as symbol]: () => 'synthetic-token' } },
  });
  await fireEvent.click(screen.getByRole('button', { name: '查看上下文与摘要' }));
  await view.rerender({ topAgent: 'operations', sessionId: 'session-two', runId: 'run-one' });
  release(new Response(JSON.stringify({ code: 'SUCCESS', data: usage })));
  await flushPromises();
  expect(screen.queryByText('direct')).toBeNull();
  expect(screen.getByText('当前会话暂无已保存的上下文使用记录。')).toBeTruthy();
});
