import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { message } from 'antd';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { KnowledgeBaseDetailPage } from './KnowledgeBaseDetailPage';
import { KnowledgeImportPage } from './KnowledgeImportPage';

const base = {
  id: 'kb-1',
  code: 'POLICY',
  name: '公司制度知识库',
  description: null,
  knowledgeType: 'COMPANY_POLICY',
  visibilityScope: 'COMPANY_WIDE',
  status: 'DRAFT',
  currentIndexReleaseId: null,
  createdAt: '2026-10-20T10:00:00',
  updatedAt: '2026-10-20T10:00:00',
};

function response(data: unknown) {
  return new Response(JSON.stringify({ code: 'SUCCESS', data }), { status: 200 });
}

function mockApi(status: string, activationFails = false, refreshFails = false) {
  let currentStatus = status;
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input), 'http://localhost').pathname;
    if (path.endsWith('/directories') || path.endsWith('/index-releases')) return response([]);
    if (path.endsWith('/documents'))
      return response({ items: [], page: 1, pageSize: 10, total: 0 });
    if (path === '/api/knowledge/bases/kb-1') {
      if (refreshFails && currentStatus === 'ACTIVE' && init?.method !== 'PUT')
        return new Response(JSON.stringify({ code: 'HTTP_ERROR', message: '刷新知识库失败' }), {
          status: 500,
        });
      if (init?.method === 'PUT') {
        if (activationFails)
          return new Response(JSON.stringify({ code: 'KB_STATUS_INVALID', message: '启用失败' }), {
            status: 400,
          });
        currentStatus = 'ACTIVE';
      }
      return response({ ...base, status: currentStatus });
    }
    throw new Error(`Unexpected request: ${path}`);
  });
}

function renderPage(entry: 'detail' | 'imports') {
  return render(
    <MemoryRouter
      initialEntries={[
        `/knowledge-center/knowledge-bases/kb-1${entry === 'imports' ? '/imports' : ''}`,
      ]}
    >
      <Routes>
        <Route
          path="/knowledge-center/knowledge-bases/:baseId"
          element={<KnowledgeBaseDetailPage />}
        />
        <Route
          path="/knowledge-center/knowledge-bases/:baseId/imports"
          element={<KnowledgeImportPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  act(() => message.destroy());
  vi.restoreAllMocks();
});

describe('knowledge base activation', () => {
  it.each(['DRAFT', 'DISABLED'])(
    'blocks uploads until the %s base is explicitly activated',
    async (status) => {
      const fetch = mockApi(status);
      renderPage('detail');
      expect(await screen.findByRole('button', { name: '上传文档' })).toBeDisabled();
      expect(screen.getByRole('button', { name: '批量导入' })).toBeDisabled();
      expect(
        screen.getByText('知识库未启用，请先启用知识库后再上传文档或批量导入。'),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: '启用知识库' }));
      await waitFor(() => expect(screen.getByRole('button', { name: '上传文档' })).toBeEnabled());
      expect(screen.getByRole('button', { name: '批量导入' })).toBeEnabled();
      expect(screen.getByText('已启用')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: '启用知识库' })).not.toBeInTheDocument();
      const update = fetch.mock.calls.find(([, init]) => init?.method === 'PUT');
      expect(update?.[0]).toBe('/api/knowledge/bases/kb-1');
      expect(update?.[1]?.headers).toEqual({ 'Content-Type': 'application/json' });
      expect(JSON.parse(String(update?.[1]?.body))).toEqual({
        name: base.name,
        description: null,
        knowledgeType: base.knowledgeType,
        status: 'ACTIVE',
      });
      expect(
        fetch.mock.calls.filter(([url, init]) => url === '/api/knowledge/bases/kb-1' && !init)
          .length,
      ).toBe(2);
      fireEvent.click(screen.getByRole('button', { name: '上传文档' }));
      expect(await screen.findByRole('dialog', { name: '上传文档' })).toBeInTheDocument();
    },
  );

  it('preserves the inactive state and shows an activation failure', async () => {
    mockApi('DRAFT', true);
    renderPage('detail');
    fireEvent.click(await screen.findByRole('button', { name: '启用知识库' }));
    expect(await screen.findByText('启用失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上传文档' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '批量导入' })).toBeDisabled();
    expect(screen.getByText('草稿')).toBeInTheDocument();
    expect(screen.queryByText('知识库已启用')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '启用知识库' })).toBeEnabled());
  });

  it('does not show success when refreshing the activated base fails', async () => {
    mockApi('DRAFT', false, true);
    renderPage('detail');
    fireEvent.click(await screen.findByRole('button', { name: '启用知识库' }));
    expect(await screen.findByText('刷新知识库失败')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '启用知识库' })).toBeEnabled());
    expect(screen.queryByText('知识库已启用')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上传文档' })).toBeDisabled();
  });

  it.each(['DRAFT', 'DISABLED'])(
    'blocks the standalone importer for %s and returns to the activation entry',
    async (status) => {
      mockApi(status);
      renderPage('imports');
      expect(await screen.findByRole('button', { name: '选择文件并导入' })).toBeDisabled();
      expect(screen.getByText('知识库未启用，请返回知识库启用后再批量导入。')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: '返回知识库启用' }));
      expect(await screen.findByRole('button', { name: '启用知识库' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '上传文档' })).toBeDisabled();
    },
  );

  it.each(['detail', 'imports'] as const)(
    'keeps uploads available for an active base on %s',
    async (entry) => {
      mockApi('ACTIVE');
      renderPage(entry);
      const label = entry === 'imports' ? '选择文件并导入' : '批量导入';
      expect(await screen.findByRole('button', { name: label })).toBeEnabled();
      expect(screen.queryByRole('button', { name: '启用知识库' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: label }));
      expect(await screen.findByRole('dialog', { name: '批量导入' })).toBeInTheDocument();
    },
  );
});
