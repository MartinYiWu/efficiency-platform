import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AgentListPage } from './AgentListPage';

afterEach(() => vi.restoreAllMocks());
describe('AI center', () => {
  it('renders independent agents', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: [
            {
              id: 'a-1',
              agentKey: 'customer-service',
              name: 'AI 智能客服',
              description: '内部知识问答',
              agentType: 'CUSTOMER_SERVICE',
              status: 'ACTIVE',
              createdBy: '1',
              createdAt: '2026-10-20T10:00:00',
              updatedBy: '1',
              updatedAt: '2026-10-20T10:00:00',
            },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    render(
      <MemoryRouter>
        <AgentListPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('AI 智能客服')).toBeInTheDocument());
    expect(screen.getByText('customer-service')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Agent 详情加载失败')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument();
  });
  it('rejects an incomplete agent response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ code: 'SUCCESS', data: [{ id: 'a-1', name: '不完整' }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    render(
      <MemoryRouter>
        <AgentListPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.queryByText('不完整')).not.toBeInTheDocument());
  });
});
