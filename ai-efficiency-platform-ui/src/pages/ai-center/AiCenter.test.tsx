import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AgentListPage } from './AgentListPage';
import { AgentDetailPage } from './AgentDetailPage';
import * as api from '../../features/ai-center/api';

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

it('keeps long Agent versions pageable and Release evidence read only', async () => {
  vi.spyOn(api, 'getAgent').mockResolvedValue({
    definition: {
      id: 'a',
      agentKey: 'customer-service',
      name: '客服 Agent',
      description: '真实定义',
      agentType: 'CUSTOMER_SERVICE',
      status: 'ACTIVE',
      createdBy: '1',
      createdAt: '2026-10-26',
      updatedBy: '1',
      updatedAt: '2026-10-26',
    },
    versions: Array.from({ length: 9 }, (_, index) => ({
      id: `v${index}`,
      agentDefinitionId: 'a',
      semanticVersion: `1.0.${index}`,
      graphKey: 'customer-service',
      graphVersion: '1',
      status: index === 0 ? 'DRAFT' : 'RELEASED',
      changeSummary: null,
      createdBy: '1',
      createdAt: '2026-10-26',
      publishedAt: null,
    })),
    evidenceBindings: [
      {
        sourceType: 'RELEASE',
        sourceId: 'release-frozen',
        largeModelName: null,
        maxInputTokens: null,
        knowledgeBaseId: 'kb-real',
        boundIndexReleaseId: 'index-bound',
        currentIndexReleaseId: 'index-current',
      },
    ],
  });
  const transition = vi.spyOn(api, 'transitionAgentVersion');
  render(
    <MemoryRouter>
      <AgentDetailPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText('客服 Agent')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '新建版本' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '提交审核' })).toBeInTheDocument();
  expect(screen.getByText(/release-frozen/)).toBeInTheDocument();
  expect(screen.getByText('kb-real')).toBeInTheDocument();
  expect(screen.getByText('绑定索引落后于知识库当前发布索引')).toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: /绑定凭证|解除绑定|设为当前/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByTitle('2'));
  expect(await screen.findByText('1.0.8')).toBeInTheDocument();
  expect(screen.queryByText('1.0.0')).not.toBeInTheDocument();
  expect(transition).not.toHaveBeenCalled();
});
