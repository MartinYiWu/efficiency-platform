import { afterEach, describe, expect, it, vi } from 'vitest';

import { listMessages } from './api';
import { parseCustomerServiceSse } from './sseClient';

afterEach(() => vi.unstubAllGlobals());

describe('customer service chat', () => {
  it('shows persisted user and assistant messages in conversation order', async () => {
    const message = (id: string, role: 'USER' | 'ASSISTANT') => ({
      message: {
        id, conversationId: 'c', tenantId: 'dev', role, content: id,
        status: 'COMPLETED', answerMode: null, runId: 'r', clientRequestId: null,
        createdAt: '2026-10-26T16:00:00Z',
      },
      citations: [],
    });
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 'SUCCESS', data: [message('answer', 'ASSISTANT'), message('question', 'USER')],
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 'SUCCESS', data: [message('question', 'USER'), message('answer', 'ASSISTANT')],
      }))));

    expect((await listMessages('c')).map((item) => item.message.role)).toEqual(['USER', 'ASSISTANT']);
    expect((await listMessages('c')).map((item) => item.message.role)).toEqual(['USER', 'ASSISTANT']);
  });
  it('parses and validates public SSE events', () => {
    const events = parseCustomerServiceSse(
      'id: 1\nevent: run.progress\ndata: {"stage":"retrieval","summary":"正在检索公司资料"}\n\nid: 2\nevent: run.completed\ndata: {"answerMode":"COMPANY_KNOWLEDGE"}\n\n',
    );
    expect(events).toHaveLength(2);
    expect(events[1].event).toBe('run.completed');
  });
  it('parses a live stage with an explicit phase', () => {
    const events = parseCustomerServiceSse(
      'id: 3\nevent: run.progress\ndata: {"stage":"retrieval","phase":"STARTED","summary":"正在查找公司资料"}\n\n',
    );
    expect(events).toHaveLength(1);
    expect(events[0].payload).toMatchObject({ stage: 'retrieval', phase: 'STARTED' });
  });
  it('rejects an unknown answer mode', () => {
    const events = parseCustomerServiceSse(
      'id: 1\nevent: run.completed\ndata: {"answerMode":"MADE_UP"}\n\n',
    );
    expect(events).toEqual([]);
  });
  it('rejects invalid citations', () => {
    const events = parseCustomerServiceSse('id: 1\nevent: citation.ready\ndata: {"id":"c1"}\n\n');
    expect(events).toEqual([]);
  });
});
