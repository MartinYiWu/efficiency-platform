import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';

import { RagEvaluationListPage } from './RagEvaluationListPage';

afterEach(() => vi.restoreAllMocks());

it('renders real RAG evaluation datasets with management actions', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    code: 'SUCCESS', message: 'success', traceId: null, data: [{
      id: 'dataset-1', name: '研发规范真实评测', description: '三份 DOCX',
      agentKey: 'customer-service', status: 'ACTIVE', caseCount: 18,
      createdAt: '2026-10-26T00:00:00Z', updatedAt: '2026-10-26T01:00:00Z',
    }],
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

  render(<MemoryRouter><RagEvaluationListPage /></MemoryRouter>);

  expect(screen.getByRole('heading', { name: 'RAG 评测' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '新建数据集' })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('研发规范真实评测')).toBeInTheDocument());
  expect(screen.getByText('18')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '查看用例' })).toBeInTheDocument();
});
