import { afterEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { fireEvent, screen } from '@testing-library/vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import Antd, { message } from 'ant-design-vue';
import Detail from './KnowledgeBaseDetailPage.vue';
import List from './KnowledgeBaseListPage.vue';
import Import from './KnowledgeImportPage.vue';

const base = {
  id: 'kb-1',
  code: 'policy',
  name: '制度库',
  description: '正式制度',
  knowledgeType: 'COMPANY_POLICY',
  visibilityScope: 'COMPANY_WIDE',
  status: 'ACTIVE',
  currentIndexReleaseId: 'r1',
  createdAt: '',
  updatedAt: '',
};
const doc = {
  id: 'd1',
  knowledgeBaseId: 'kb-1',
  directoryId: null,
  title: '报销制度',
  documentCode: 'EXPENSE',
  sourceType: 'UPLOAD',
  status: 'ACTIVE',
  currentPublishedVersionId: null,
  versions: [],
};
const directory = {
  id: 'dir1',
  knowledgeBaseId: 'kb-1',
  parentId: null,
  name: '财务目录',
  path: '/财务目录',
  sortNo: 1,
  status: 'ACTIVE',
};
const release = {
  id: 'r1',
  knowledgeBaseId: 'kb-1',
  releaseNo: 1,
  status: 'PUBLISHED',
  documentCount: 1,
  chunkCount: 3,
  embeddingModel: 'mock',
  embeddingDimension: 3,
  checksum: null,
  previousReleaseId: null,
  createdAt: '',
  publishedAt: null,
};
const response = (data: unknown) =>
  new Response(JSON.stringify({ code: 'SUCCESS', data }), { status: 200 });
afterEach(() => {
  vi.restoreAllMocks();
  message.destroy();
});
async function mountPage(Page: typeof Detail | typeof Import | typeof List) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/:baseId', component: Page },
      { path: '/knowledge-center/knowledge-bases/:baseId', component: Detail },
    ],
  });
  await router.push('/kb-1');
  const wrapper = mount(Page, { attachTo: document.body, global: { plugins: [router, Antd] } });
  await flushPromises();
  return { wrapper, router };
}
function mockApi(status = 'ACTIVE') {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    const path = String(url);
    if (path.endsWith('/directories'))
      return response(init?.method === 'POST' ? directory : [directory]);
    if (path.endsWith('/index-releases'))
      return response([release, { ...release, id: 'r0', releaseNo: 0 }]);
    if (path.includes('/documents?'))
      return response({ items: [doc], page: 1, pageSize: 10, total: 21 });
    if (path.endsWith('/rollback')) return response(release);
    if (path.startsWith('/api/knowledge/bases?'))
      return response({ items: [base], page: 1, pageSize: 10, total: 21 });
    return response({ ...base, status });
  });
}
it('保留文档表格、分页、目录新增与索引回滚', async () => {
  const fetch = mockApi();
  const { wrapper } = await mountPage(Detail);
  expect(wrapper.text()).toContain('报销制度');
  expect(wrapper.text()).toContain('EXPENSE');
  expect(wrapper.text()).toContain('mock');
  expect(wrapper.text()).toContain('当前版本');
  await wrapper.get('[title="2"] a').trigger('click');
  await flushPromises();
  expect(
    fetch.mock.calls.some(([url]) => String(url).includes('documents?page=2&pageSize=10')),
  ).toBe(true);
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '新建目录')!
    .trigger('click');
  await flushPromises();
  await fireEvent.update(screen.getByPlaceholderText('目录名称'), '新目录');
  await fireEvent.click(screen.getByRole('button', { name: /O\s*K|确\s*定/ }));
  await flushPromises();
  const created = fetch.mock.calls.find(
    ([url, init]) => String(url).endsWith('/directories') && init?.method === 'POST',
  );
  expect(JSON.parse(String(created?.[1]?.body))).toEqual({
    name: '新目录',
    parentId: null,
    sortNo: 2,
  });
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '回滚到此版本')!
    .trigger('click');
  await flushPromises();
  expect(
    fetch.mock.calls.some(
      ([url, init]) =>
        String(url) === '/api/knowledge/index-releases/r0/rollback' && init?.method === 'POST',
    ),
  ).toBe(true);
  wrapper.unmount();
});
it('创建知识库保留所有字段并导航', async () => {
  const fetch = mockApi();
  const { wrapper, router } = await mountPage(List);
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '新建知识库')!
    .trigger('click');
  await flushPromises();
  await fireEvent.update(screen.getByLabelText('名称'), '制度库');
  await fireEvent.update(screen.getByLabelText('编码'), 'policy');
  await fireEvent.update(screen.getByLabelText('描述'), '正式资料');
  await fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }));
  await flushPromises();
  const created = fetch.mock.calls.find(([, init]) => init?.method === 'POST');
  expect(JSON.parse(String(created?.[1]?.body))).toEqual({
    name: '制度库',
    code: 'policy',
    description: '正式资料',
    knowledgeType: 'COMPANY_POLICY',
  });
  expect(router.currentRoute.value.path).toBe('/knowledge-center/knowledge-bases/kb-1');
  wrapper.unmount();
});
it.each(['DRAFT', 'DISABLED'])('独立导入页在%s时禁用', async (status) => {
  mockApi(status);
  const { wrapper } = await mountPage(Import);
  const button = wrapper.findAll('button').find((b) => b.text() === '选择文件并导入')!;
  expect(button.attributes('disabled')).toBeDefined();
  expect(wrapper.text()).toContain('知识库未启用，请返回知识库启用后再批量导入。');
  wrapper.unmount();
});
it('激活后的刷新失败保持上传禁用且不报成功', async () => {
  const fetch = mockApi('DRAFT');
  const original = fetch.getMockImplementation()!;
  let activated = false;
  fetch.mockImplementation(async (url, init) => {
    if (init?.method === 'PUT') {
      activated = true;
      return response(base);
    }
    if (activated && String(url) === '/api/knowledge/bases/kb-1')
      return new Response(JSON.stringify({ code: 'ERROR', message: '刷新失败' }), { status: 500 });
    return original(url, init);
  });
  const { wrapper } = await mountPage(Detail);
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '启用知识库')!
    .trigger('click');
  await flushPromises();
  expect(
    wrapper
      .findAll('button')
      .find((b) => b.text() === '上传文档')!
      .attributes('disabled'),
  ).toBeDefined();
  expect(screen.queryByText('知识库已启用')).toBeNull();
  expect(wrapper.text()).toContain('刷新失败');
  wrapper.unmount();
});
it('早发分页晚返回不能覆盖当前页', async () => {
  const fetch = mockApi();
  const original = fetch.getMockImplementation()!;
  const pending = new Map<string, (value: Response) => void>();
  fetch.mockImplementation((url, init) => {
    const parsed = new URL(String(url), 'http://localhost');
    const page = parsed.searchParams.get('page');
    if (parsed.pathname.endsWith('/documents') && page && page !== '1')
      return new Promise<Response>((resolve) => pending.set(page, resolve));
    return original(url, init);
  });
  const { wrapper } = await mountPage(Detail);
  await wrapper.get('[title="2"] a').trigger('click');
  await flushPromises();
  await wrapper.get('[title="3"] a').trigger('click');
  await flushPromises();
  pending.get('3')!(
    response({ items: [{ ...doc, title: '第三页' }], page: 3, pageSize: 10, total: 21 }),
  );
  await flushPromises();
  pending.get('2')!(
    response({ items: [{ ...doc, title: '第二页旧数据' }], page: 2, pageSize: 10, total: 21 }),
  );
  await flushPromises();
  expect(wrapper.text()).toContain('第三页');
  expect(wrapper.text()).not.toContain('第二页旧数据');
  wrapper.unmount();
});
