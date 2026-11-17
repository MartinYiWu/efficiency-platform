import { render, screen, fireEvent } from '@testing-library/vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import { createPinia } from 'pinia';
import Antd from 'ant-design-vue';
import { describe, expect, it } from 'vitest';
import PlatformShell from './PlatformShell.vue';

describe('Vue 平台导航', () => {
  it('可折叠侧栏，并保留知识与助手入口', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
    });
    await router.push('/knowledge-center/knowledge-bases');
    await router.isReady();
    const { container } = render(PlatformShell, {
      global: { plugins: [router, createPinia(), Antd] },
    });
    expect(screen.getByRole('button', { name: '折叠侧栏' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /知识中心/ })).toBeInTheDocument();
    expect(
      screen.getByRole('menuitem', { name: /知识中心/ }).querySelector('[aria-current="page"]'),
    ).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: '折叠侧栏' }));
    expect(container.querySelector('[data-collapsed="true"]')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '展开侧栏' })).toBeInTheDocument();
  });
});
