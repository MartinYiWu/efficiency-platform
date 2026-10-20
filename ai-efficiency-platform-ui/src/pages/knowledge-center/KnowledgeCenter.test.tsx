import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { KnowledgeBaseListPage } from './KnowledgeBaseListPage';

afterEach(() => vi.restoreAllMocks());

describe('KnowledgeCenter', () => {
  it('renders knowledge bases returned by the strict contract', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          message: 'ok',
          data: {
            items: [
              {
                id: 'kb-1',
                code: 'company-policy',
                name: '公司制度',
                description: '正式制度',
                knowledgeType: 'POLICY',
                visibilityScope: 'ALL_EMPLOYEES',
                status: 'ACTIVE',
                currentIndexReleaseId: null,
                createdAt: '2026-10-20T10:00:00',
                updatedAt: '2026-10-20T10:00:00',
              },
            ],
            page: 1,
            pageSize: 20,
            total: 1,
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(
      <MemoryRouter>
        <KnowledgeBaseListPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('公司制度')).toBeInTheDocument());
    expect(screen.getByText('正式制度')).toBeInTheDocument();
  });

  it('shows a contract error instead of inventing missing fields', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: { items: [{ id: 'kb-1', name: '不完整知识库' }], page: 1, pageSize: 20, total: 1 },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(
      <MemoryRouter>
        <KnowledgeBaseListPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.queryByText('不完整知识库')).not.toBeInTheDocument());
  });
});
