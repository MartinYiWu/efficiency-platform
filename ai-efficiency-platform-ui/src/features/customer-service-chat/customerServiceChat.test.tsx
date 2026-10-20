import { describe, expect, it } from 'vitest';

import { parseCustomerServiceSse } from './sseClient';

describe('customer service chat', () => {
  it('parses and validates public SSE events', () => {
    const events = parseCustomerServiceSse(
      'id: 1\nevent: run.progress\ndata: {"stage":"retrieval","summary":"正在检索公司资料"}\n\nid: 2\nevent: run.completed\ndata: {"answerMode":"COMPANY_KNOWLEDGE"}\n\n',
    );
    expect(events).toHaveLength(2);
    expect(events[1].event).toBe('run.completed');
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
