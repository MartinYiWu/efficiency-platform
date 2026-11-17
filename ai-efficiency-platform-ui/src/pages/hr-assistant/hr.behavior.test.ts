import type { Component } from 'vue';
import { render, screen, fireEvent, cleanup } from '@testing-library/vue';
import { afterEach, expect, it, vi } from 'vitest';
import { createRouter, createMemoryHistory } from 'vue-router';

import PositionBasicPage from './positions/PositionBasicPage.vue';

import HrChatPage from './chat/HrChatPage.vue';

import CandidateProfilePage from './talent/CandidateProfilePage.vue';
const mountPage = (page: Component) =>
  render(page, {
    global: {
      plugins: [
        createRouter({
          history: createMemoryHistory(),
          routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
        }),
      ],
    },
  });
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
it('没有真实候选人时不展示联系方式查看入口', () => {
  mountPage(CandidateProfilePage);
  expect(screen.queryByRole('button', { name: '查看联系方式（需授权）' })).not.toBeInTheDocument();
});
it('基础信息缺失时禁止下一步', () => {
  mountPage(PositionBasicPage);
  expect(screen.getByRole('button', { name: /下一步/ })).toBeDisabled();
});
it('HR对话发送后保留内容并清空输入', async () => {
  mountPage(HrChatPage);
  await fireEvent.update(screen.getByLabelText('输入消息'), '请整理招聘进展');
  await fireEvent.click(screen.getByRole('button', { name: '发送消息' }));
  expect(screen.getByText('请整理招聘进展')).toBeInTheDocument();
  expect(screen.getByLabelText('输入消息')).toHaveValue('');
});
