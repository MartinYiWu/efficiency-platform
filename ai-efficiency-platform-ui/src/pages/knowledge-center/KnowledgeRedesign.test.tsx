import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { KnowledgeBaseDetailPage } from './KnowledgeBaseDetailPage';
import { KnowledgeBaseListPage } from './KnowledgeBaseListPage';
import { KnowledgeDocumentPage } from './KnowledgeDocumentPage';
import { KnowledgeImportPage } from './KnowledgeImportPage';

const base = {
  id: 'kb-1',
  code: 'company-policy',
  name: '公司制度知识库',
  description: '正式制度',
  knowledgeType: 'COMPANY_POLICY',
  visibilityScope: 'COMPANY_WIDE',
  status: 'ACTIVE',
  currentIndexReleaseId: 'release-1',
  createdAt: '2026-10-20T10:00:00',
  updatedAt: '2026-10-20T10:00:00',
};
const document = {
  id: 'doc-1',
  knowledgeBaseId: 'kb-1',
  directoryId: null,
  title: '报销制度',
  documentCode: 'EXPENSE',
  sourceType: 'MANUAL_UPLOAD',
  status: 'ACTIVE',
  currentPublishedVersionId: null,
  versions: [
    {
      id: 'version-1',
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
    },
  ],
};
function response(data: unknown) {
  return new Response(JSON.stringify({ code: 'SUCCESS', data }), { status: 200 });
}
function mockApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost');
    if (url.pathname.endsWith('/directories')) return response([]);
    if (url.pathname.endsWith('/index-releases'))
      return response([
        {
          id: 'release-1',
          knowledgeBaseId: 'kb-1',
          releaseNo: 1,
          status: 'PUBLISHED',
          documentCount: 1,
          chunkCount: 5,
          embeddingModel: 'embedding-model',
          embeddingDimension: 1024,
          checksum: null,
          previousReleaseId: null,
          createdAt: '2026-10-20T10:00:00',
          publishedAt: '2026-10-20T10:00:00',
        },
      ]);
    if (url.pathname.endsWith('/documents'))
      return response({ items: [document], page: 1, pageSize: 10, total: 21 });
    if (url.pathname === '/api/knowledge/documents/doc-1') return response(document);
    if (url.pathname === '/api/knowledge/bases/kb-1' || init?.method === 'POST')
      return response(base);
    return response({
      items: [{ ...base, name: url.searchParams.get('keyword') || base.name }],
      page: Number(url.searchParams.get('page') || 1),
      pageSize: 10,
      total: 21,
    });
  });
}
afterEach(() => vi.restoreAllMocks());

describe('KnowledgeCenter redesign', () => {
  it('submits trimmed searches and real type filters with server pagination', async () => {
    const fetch = mockApi();
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <KnowledgeBaseListPage />
      </MemoryRouter>,
    );
    await screen.findByText('正式制度');
    await user.click(screen.getByTitle('2'));
    await waitFor(() => expect(String(fetch.mock.lastCall?.[0])).toContain('page=2&pageSize=10'));
    const search = screen.getByPlaceholderText('搜索知识库名称或描述');
    await user.type(search, '  报销  {Enter}');
    await waitFor(() => {
      const query = new URL(String(fetch.mock.lastCall?.[0]), 'http://localhost').searchParams;
      expect(query.get('page')).toBe('1');
      expect(query.get('keyword')).toBe('报销');
    });
    expect(await screen.findByText('报销')).toBeInTheDocument();
    const filters = within(screen.getByRole('complementary', { name: '资料分类' }));
    for (const [label, type] of [
      ['公司制度', 'COMPANY_POLICY'],
      ['业务流程', 'BUSINESS_PROCESS'],
      ['产品文档', 'PRODUCT_DOCUMENTATION'],
      ['技术文档', 'TECHNICAL_DOCUMENTATION'],
    ]) {
      await user.click(screen.getByTitle('2'));
      await user.click(filters.getByRole('button', { name: label }));
      await waitFor(() => {
        const query = new URL(String(fetch.mock.lastCall?.[0]), 'http://localhost').searchParams;
        expect(query.get('page')).toBe('1');
        expect(query.get('knowledgeType')).toBe(type);
        expect(query.get('keyword')).toBe('报销');
      });
      expect(filters.getByRole('button', { name: label })).toHaveAttribute('aria-pressed', 'true');
    }
    await user.click(filters.getByRole('button', { name: '全部资料' }));
    await waitFor(() => expect(String(fetch.mock.lastCall?.[0])).not.toContain('knowledgeType'));
    await user.clear(search);
    await user.type(search, '{Enter}');
    await waitFor(() => expect(String(fetch.mock.lastCall?.[0])).not.toContain('keyword'));
  });

  it('keeps creation fields and navigates to the created base', async () => {
    const fetch = mockApi();
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<KnowledgeBaseListPage />} />
          <Route
            path="/knowledge-center/knowledge-bases/:baseId"
            element={<div>创建后的详情路由</div>}
          />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(screen.getByRole('button', { name: '新建知识库' }));
    const drawer = within(screen.getByRole('dialog'));
    await user.type(drawer.getByLabelText('名称'), '制度库');
    await user.type(drawer.getByLabelText('编码'), 'policy');
    await user.type(drawer.getByLabelText('描述'), '正式资料');
    await user.click(drawer.getByRole('button', { name: /^创\s*建$/ }));
    expect(await screen.findByText('创建后的详情路由')).toBeInTheDocument();
    const call = fetch.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(call?.[0]).toBe('/api/knowledge/bases');
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      name: '制度库',
      code: 'policy',
      description: '正式资料',
      knowledgeType: 'COMPANY_POLICY',
    });
  });

  it('navigates from a selected row to its real detail route', async () => {
    mockApi();
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<KnowledgeBaseListPage />} />
          <Route
            path="/knowledge-center/knowledge-bases/kb-1"
            element={<div>知识库详情路由</div>}
          />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(await screen.findByText(base.name));
    expect(await screen.findByText('知识库详情路由')).toBeInTheDocument();
  });

  it('separates base information, directory documents, and index releases with real document pagination', async () => {
    const fetch = mockApi();
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/knowledge-center/knowledge-bases/kb-1']}>
        <Routes>
          <Route
            path="/knowledge-center/knowledge-bases/:baseId"
            element={<KnowledgeBaseDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: '知识库信息' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '目录与文档' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '索引版本' })).toBeInTheDocument();
    expect(screen.getByText('报销制度')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: '版本数' })).not.toBeInTheDocument();
    expect(screen.getByText('当前版本')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '回滚到此版本' })).not.toBeInTheDocument();
    await user.click(screen.getByTitle('2'));
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(([url]) => String(url).includes('/documents?page=2&pageSize=10')),
      ).toBe(true),
    );
    await user.click(screen.getByRole('button', { name: '上传文档' }));
    expect(await screen.findByRole('dialog', { name: '上传文档' })).toBeInTheDocument();
  });

  it('exposes document versions, processing tasks, and actual source metadata', async () => {
    mockApi();
    render(
      <MemoryRouter initialEntries={['/knowledge-center/documents/doc-1']}>
        <Routes>
          <Route
            path="/knowledge-center/documents/:documentId"
            element={<KnowledgeDocumentPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: '版本记录' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '处理任务' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '原文与引用信息' })).toBeInTheDocument();
    expect(screen.getByText('file-1')).toBeInTheDocument();
    expect(screen.getByText('2026-10-20 10:00')).toBeInTheDocument();
    expect(screen.queryByText('2026-10-20T10:00:00')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^发\s*布$/ })).toBeInTheDocument();
  });

  it('opens the existing batch importer from a real base import page', async () => {
    mockApi();
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/knowledge-center/knowledge-bases/kb-1/imports']}>
        <Routes>
          <Route
            path="/knowledge-center/knowledge-bases/:baseId/imports"
            element={<KnowledgeImportPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole('heading', { name: '批量导入' })).toBeInTheDocument();
    expect(screen.getByText(base.name)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '选择文件并导入' }));
    expect(await screen.findByRole('dialog', { name: '批量导入' })).toBeInTheDocument();
    expect(screen.getByText('选择多个文件批量导入')).toBeInTheDocument();
  });

  it.each(['imports', 'detail'])(
    'starts a fresh batch after reopening the importer on %s',
    async (entry) => {
      const fetch = mockApi();
      const defaultFetch = fetch.getMockImplementation()!;
      fetch.mockImplementation((input, init) => {
        const path = new URL(String(input), 'http://localhost').pathname;
        if (path.endsWith('/documents')) {
          return Promise.resolve(response({ items: [], page: 1, pageSize: 10, total: 0 }));
        }
        if (path.endsWith('/index-releases')) return Promise.resolve(response([]));
        if (String(input).endsWith('/imports') && init?.method === 'POST') {
          return Promise.resolve(
            response({
              id: 'batch-1',
              knowledgeBaseId: 'kb-1',
              importMode: 'BATCH',
              totalCount: 2,
              succeededCount: 2,
              failedCount: 0,
              status: 'SUCCEEDED',
              createdAt: '2026-10-20T10:00:00',
              finishedAt: '2026-10-20T10:01:00',
              items: [],
            }),
          );
        }
        return defaultFetch(input, init);
      });
      const user = userEvent.setup();
      const view = render(
        <MemoryRouter initialEntries={['/kb-1']}>
          <Routes>
            <Route
              path="/:baseId"
              element={entry === 'imports' ? <KnowledgeImportPage /> : <KnowledgeBaseDetailPage />}
            />
          </Routes>
        </MemoryRouter>,
      );
      const openButton = entry === 'imports' ? '选择文件并导入' : '批量导入';
      fireEvent.click(await screen.findByRole('button', { name: openButton }));
      const input = view.baseElement.querySelector<HTMLInputElement>('input[type="file"]');
      expect(input).not.toBeNull();
      await user.upload(input!, [
        new File(['first'], 'first.txt', { type: 'text/plain' }),
        new File(['second'], 'second.txt', { type: 'text/plain' }),
      ]);
      fireEvent.click(screen.getByRole('button', { name: '开始导入' }));
      expect(await screen.findByText('成功 2，失败 0，共 2')).toBeInTheDocument();
      fireEvent.click(
        within(screen.getByRole('dialog', { name: '批量导入' })).getByRole('button', {
          name: 'Close',
        }),
      );
      await waitFor(() =>
        expect(screen.queryByRole('dialog', { name: '批量导入' })).not.toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole('button', { name: openButton }));
      expect(await screen.findByText('选择多个文件批量导入')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '开始导入' })).toBeInTheDocument();
      expect(screen.queryByText('成功 2，失败 0，共 2')).not.toBeInTheDocument();
    },
  );

  it('keeps the latest document page when earlier requests finish later', async () => {
    const fetch = mockApi();
    const defaultFetch = fetch.getMockImplementation()!;
    const pending = new Map<string, (value: Response) => void>();
    fetch.mockImplementation((input, init) => {
      const url = new URL(String(input), 'http://localhost');
      const page = url.searchParams.get('page');
      if (url.pathname.endsWith('/documents') && page && page !== '1') {
        return new Promise<Response>((resolve) => pending.set(page, resolve));
      }
      return defaultFetch(input, init);
    });
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/kb-1']}>
        <Routes>
          <Route path="/:baseId" element={<KnowledgeBaseDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText('报销制度');
    await user.click(screen.getByTitle('2'));
    await waitFor(() => expect(pending.has('2')).toBe(true));
    await user.click(screen.getByTitle('3'));
    await waitFor(() => expect(pending.has('3')).toBe(true));
    await act(async () =>
      pending.get('3')!(
        response({
          items: [{ ...document, id: 'doc-3', title: '第三页文档' }],
          page: 3,
          pageSize: 10,
          total: 21,
        }),
      ),
    );
    expect(await screen.findByText('第三页文档')).toBeInTheDocument();
    await act(async () =>
      pending.get('2')!(
        response({
          items: [{ ...document, id: 'doc-2', title: '第二页旧响应' }],
          page: 2,
          pageSize: 10,
          total: 21,
        }),
      ),
    );
    expect(screen.getByText('第三页文档')).toBeInTheDocument();
    expect(screen.queryByText('第二页旧响应')).not.toBeInTheDocument();
  });
});
