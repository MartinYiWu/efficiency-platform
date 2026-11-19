import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/vue';
import { flushPromises } from '@vue/test-utils';
import { createMemoryProposalApi } from '../../entities/memory/proposals';
import { memoryAccessTokenKey } from '../../entities/memory';
import MemoryProposalPanel from './MemoryProposalPanel.vue';

const scope = { topAgent: 'operations' as const, sessionId: 'session-one' };
const proposal = {
  id: 'proposal-one',
  itemId: 'item-one',
  ...scope,
  fieldKey: 'response.language',
  value: 'zh-CN',
  action: 'CONFLICT_CANDIDATE',
  status: 'PENDING',
  revision: 1,
  expectedItemRevision: 2,
  expiresAt: '2030-01-01T00:00:00Z',
  indexStatus: 'NOT_REQUESTED',
  versionId: null,
};
const response = (data: unknown, status = 200, code = 'SUCCESS') =>
  new Response(JSON.stringify({ code, data }), { status });
const global = {
  provide: { [memoryAccessTokenKey as symbol]: () => 'synthetic-token' },
  stubs: { AButton: { template: '<button><slot /></button>' } },
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('rejects cross-session responses before displaying any candidate', async () => {
  const fetcher = vi.fn().mockResolvedValue(response([{ ...proposal, sessionId: 'other' }]));
  await expect(
    createMemoryProposalApi(() => 'synthetic-token', fetcher).list(scope),
  ).rejects.toMatchObject({ status: 403 });
  await expect(createMemoryProposalApi(() => undefined, fetcher).list(scope)).rejects.toMatchObject(
    { status: 401 },
  );
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it('does not generate on GET or claim success after a confirmation conflict', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(response([proposal]))
    .mockResolvedValueOnce(response(null, 409, 'MEMORY_PROPOSAL_REVISION_CONFLICT'));
  vi.stubGlobal('fetch', fetcher);
  render(MemoryProposalPanel, { props: { scope }, global });
  expect(fetcher).not.toHaveBeenCalled();
  await fireEvent.click(screen.getByRole('button', { name: '查看候选记忆' }));
  await flushPromises();
  expect(fetcher.mock.calls[0][1].method).toBe('GET');
  await fireEvent.click(screen.getByRole('button', { name: '确认保存' }));
  const confirmButtons = screen.getAllByRole('button', { name: '确认保存' });
  await fireEvent.click(confirmButtons[confirmButtons.length - 1]);
  await flushPromises();
  expect(screen.getByRole('alert').textContent).toContain('候选版本已变化');
  expect(screen.queryByText('已保存，可按字段使用；尚未建立语义索引。')).toBeNull();
  expect(fetcher).toHaveBeenCalledTimes(2);
  const command = JSON.parse(fetcher.mock.calls[1][1].body);
  expect(command.expectedProposalRevision).toBe(1);
  expect(command.expectedItemRevision).toBe(2);
  expect(command.action).toBe('CONFIRM');
  expect(command).not.toHaveProperty('budgetId');
});

it('clears old candidate text when scope changes and ignores its late response', async () => {
  let resolve!: (value: Response) => void;
  const fetcher = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    )
    .mockResolvedValue(response([]));
  vi.stubGlobal('fetch', fetcher);
  const view = render(MemoryProposalPanel, { props: { scope }, global });
  await fireEvent.click(screen.getByRole('button', { name: '查看候选记忆' }));
  await view.rerender({ scope: { ...scope, sessionId: 'session-two' } });
  resolve(response([proposal]));
  await flushPromises();
  expect(screen.queryByText('简体中文')).toBeNull();
  expect(screen.queryByRole('button', { name: '确认保存' })).toBeNull();
});
