import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/vue';
import { afterEach, expect, it, vi } from 'vitest';
import Antd from 'ant-design-vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import RunListPage from './RunListPage.vue';
import PromptManagementPage from './PromptManagementPage.vue';
import * as api from '../../features/ai-center/api';
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const router = () =>
  createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  });
it('keeps all run filters when requesting a new page', async () => {
  const list = vi
    .spyOn(api, 'listRuns')
    .mockResolvedValue({ items: [], total: 21, page: 1, pageSize: 10 });
  render(RunListPage, { global: { plugins: [Antd, router()] } });
  await waitFor(() => expect(list).toHaveBeenCalled());
  await fireEvent.update(screen.getByPlaceholderText('Agent Key'), 'customer-service');
  await fireEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
  await waitFor(() => expect(list.mock.calls.at(-1)?.[0]).toContain('agentKey=customer-service'));
  await fireEvent.click(screen.getByTitle('2'));
  await waitFor(() => expect(list.mock.calls.at(-1)?.[0]).toContain('page=2'));
  expect(list.mock.calls.at(-1)?.[0]).toContain('agentKey=customer-service');
});
it('opens an independent prompt draft and preserves other roles on save', async () => {
  vi.spyOn(api, 'listPrompts').mockResolvedValue([
    { id: 'p', name: '客服提示', scope: 'AGENT', stageKey: 'answer' },
  ] as never);
  vi.spyOn(api, 'createPromptVersion').mockResolvedValue({ id: 'v' } as never);
  vi.spyOn(api, 'getPromptVersion').mockResolvedValue({
    definition: { name: '客服提示' },
    version: { id: 'v', status: 'DRAFT', semanticVersion: 'draft' },
    messages: [
      {
        id: 's',
        role: 'SYSTEM',
        ordinal: 1,
        messageKey: 'system',
        contentTemplate: '原系统',
        trustedInstruction: true,
      },
      {
        id: 'u',
        role: 'USER',
        ordinal: 2,
        messageKey: 'user',
        contentTemplate: '{{question}}',
        trustedInstruction: false,
      },
    ],
    variables: [],
  } as never);
  const save = vi.spyOn(api, 'replacePromptContent').mockResolvedValue({} as never);
  render(PromptManagementPage, { global: { plugins: [Antd, router()] } });
  await fireEvent.click(await screen.findByRole('button', { name: '创建草稿并编辑' }));
  await fireEvent.update(await screen.findByRole('textbox', { name: '消息正文' }), '新系统');
  await fireEvent.click(screen.getByRole('button', { name: /保存草稿/ }));
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(
      'v',
      expect.objectContaining({
        messages: expect.arrayContaining([
          expect.objectContaining({ role: 'USER', contentTemplate: '{{question}}' }),
          expect.objectContaining({ role: 'SYSTEM', contentTemplate: '新系统' }),
        ]),
      }),
    ),
  );
});
