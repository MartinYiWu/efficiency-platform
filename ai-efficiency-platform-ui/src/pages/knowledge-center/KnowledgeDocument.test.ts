import { afterEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import Antd from 'ant-design-vue';

afterEach(() => vi.restoreAllMocks());
it('保留版本、原文元数据、发布与处理任务详情入口', async () => {
  const version = {
    id: 'v1',
    documentId: 'doc-1',
    versionNo: 1,
    fileId: 'file-1',
    fileSha256: 'hash',
    contentType: 'text/plain',
    changeSummary: '首版',
    effectiveDate: null,
    status: 'READY',
    errorCode: null,
    errorMessage: null,
    createdAt: '2026-10-20T10:00:00',
    processingTasks: [],
    evidenceMode: 'FULL_ONLY',
  };
  const document = {
    id: 'doc-1',
    knowledgeBaseId: 'kb-1',
    directoryId: null,
    title: '报销制度',
    documentCode: 'EXPENSE',
    sourceType: 'UPLOAD',
    status: 'ACTIVE',
    currentPublishedVersionId: null,
    versions: [version],
  };
  const base = {
    id: 'kb-1',
    code: 'policy',
    name: '制度库',
    description: null,
    knowledgeType: 'COMPANY_POLICY',
    visibilityScope: 'COMPANY_WIDE',
    status: 'ACTIVE',
    currentIndexReleaseId: null,
    createdAt: '',
    updatedAt: '',
  };
  const release = {
    id: 'r1',
    knowledgeBaseId: 'kb-1',
    releaseNo: 1,
    status: 'PUBLISHED',
    documentCount: 1,
    chunkCount: 2,
    embeddingModel: 'mock',
    embeddingDimension: 3,
    checksum: null,
    previousReleaseId: null,
    createdAt: '',
    publishedAt: '',
  };
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(
    async (url) =>
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: String(url).endsWith('/publish')
            ? release
            : String(url).includes('/bases/')
              ? base
              : document,
        }),
        { status: 200 },
      ),
  );
  const { default: Page } = await import('./KnowledgeDocumentPage.vue');
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:documentId', component: Page }],
  });
  await router.push('/doc-1');
  const wrapper = mount(Page, { global: { plugins: [router, Antd] } });
  await flushPromises();
  expect(wrapper.text()).toContain('版本记录');
  expect(wrapper.text()).toContain('原文与引用信息');
  expect(wrapper.text()).toContain('file-1');
  expect(wrapper.text()).toContain('2026-10-20 10:00');
  await wrapper
    .findAll('button')
    .find((b) => b.text().replace(/\s/g, '') === '发布')!
    .trigger('click');
  await flushPromises();
  expect(
    fetch.mock.calls.some(
      ([url, init]) =>
        String(url) === '/api/knowledge/document-versions/v1/publish' && init?.method === 'POST',
    ),
  ).toBe(true);
  wrapper.unmount();
});
