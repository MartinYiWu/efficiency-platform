import { describe, expect, it, vi, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import Antd from 'ant-design-vue';

const base = {
  id: 'kb-1',
  code: 'policy',
  name: '公司制度知识库',
  description: '正式制度',
  knowledgeType: 'COMPANY_POLICY',
  visibilityScope: 'COMPANY_WIDE',
  status: 'DRAFT',
  currentIndexReleaseId: null,
  createdAt: '2026-10-20T10:00:00',
  updatedAt: '2026-10-20T10:00:00',
};
const response = (data: unknown) =>
  new Response(JSON.stringify({ code: 'SUCCESS', data }), { status: 200 });
afterEach(() => vi.restoreAllMocks());

describe('知识中心 Vue 迁移', () => {
  it('保留资料分类、严格接口与搜索分页', async () => {
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () =>
        response({ items: [base], page: 1, pageSize: 10, total: 21 }),
      );
    const { default: Page } = await import('./KnowledgeBaseListPage.vue');
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: Page }],
    });
    await router.push('/');
    const wrapper = mount(Page, { global: { plugins: [router, Antd] } });
    await flushPromises();
    expect(wrapper.text()).toContain('正式制度');
    expect(wrapper.text()).toContain('全员可见');
    await wrapper.get('input[placeholder="搜索知识库名称或描述"]').setValue('  报销  ');
    await wrapper
      .get('input[placeholder="搜索知识库名称或描述"]')
      .trigger('keydown', { key: 'Enter', keyCode: 13 });
    await flushPromises();
    expect(String(fetch.mock.lastCall?.[0])).toContain('keyword=%E6%8A%A5%E9%94%80');
    await wrapper
      .findAll('aside button')
      .find((b) => b.text() === '技术文档')!
      .trigger('click');
    await flushPromises();
    expect(String(fetch.mock.lastCall?.[0])).toContain('knowledgeType=TECHNICAL_DOCUMENTATION');
    wrapper.unmount();
  });
  it('草稿知识库先激活并刷新后才允许上传', async () => {
    let status = 'DRAFT';
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.includes('/directories') || path.includes('/index-releases')) return response([]);
      if (path.includes('/documents?'))
        return response({ items: [], page: 1, pageSize: 10, total: 0 });
      if (init?.method === 'PUT') status = 'ACTIVE';
      return response({ ...base, status });
    });
    const { default: Page } = await import('./KnowledgeBaseDetailPage.vue');
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:baseId', component: Page }],
    });
    await router.push('/kb-1');
    const wrapper = mount(Page, { global: { plugins: [router, Antd] } });
    await flushPromises();
    const button = (name: string) => wrapper.findAll('button').find((b) => b.text() === name)!;
    expect(button('上传文档').attributes('disabled')).toBeDefined();
    await button('启用知识库').trigger('click');
    await flushPromises();
    expect(button('上传文档').attributes('disabled')).toBeUndefined();
    const update = fetch.mock.calls.find(([, init]) => init?.method === 'PUT');
    expect(JSON.parse(String(update?.[1]?.body))).toEqual({
      name: base.name,
      description: base.description,
      knowledgeType: base.knowledgeType,
      status: 'ACTIVE',
    });
    wrapper.unmount();
  });
  it('制度仅允许全文，技术文档允许原文节选', async () => {
    const { default: Evidence } = await import('../../features/knowledge/EvidenceModeSelect.vue');
    const wrapper = mount(Evidence, {
      props: { knowledgeType: 'COMPANY_POLICY', value: 'EXTRACTIVE_NARRATIVE' },
      global: { plugins: [Antd] },
    });
    expect(wrapper.findComponent({ name: 'ASelect' }).props('disabled')).toBe(true);
    await wrapper.setProps({ knowledgeType: 'TECHNICAL_DOCUMENTATION' });
    expect(wrapper.findComponent({ name: 'ASelect' }).props('disabled')).toBe(false);
    expect(wrapper.text()).toContain('仅选择原文句段');
    wrapper.unmount();
  });
});
