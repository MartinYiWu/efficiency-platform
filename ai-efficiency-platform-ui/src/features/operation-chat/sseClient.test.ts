import { describe, expect, it, vi } from 'vitest';
import { connectRunStream, parseSseChunk } from './sseClient';
const envelope = (sequence: number, event: string, payload: Record<string, unknown>) =>
  `id: ${sequence}\nevent: ${event}\ndata: ${JSON.stringify({ contract_version: 'run.stream.event/1', event, run_id: 'run-1', sequence, payload })}\n\n`;
describe('SSE 客户端', () => {
  it('以 data envelope 为准，忽略传输层 event 名', () => {
    expect(
      parseSseChunk(
        envelope(7, 'assistant_delta', { delta: '第一段' }).replace(
          'event: assistant_delta',
          'event: wrong',
        ),
      )[0],
    ).toMatchObject({
      id: '7',
      event: 'assistant_delta',
      sequence: 7,
      payload: { delta: '第一段' },
    });
  });
  it.each([
    'research_started',
    'research_completed',
    'content_generation_started',
    'content_generation_completed',
    'quality_checked',
  ])('接收 Agent 真实阶段事件 %s', (event) => {
    expect(parseSseChunk(envelope(1, event, { phase: 'collecting_sources' }))[0]?.event).toBe(
      event,
    );
  });
  it('携带租户和 sequence Last-Event-ID，网络异常后有限重连并严格去重', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('断开'))
      .mockResolvedValueOnce(
        new Response(envelope(2, 'stream_done', { status: 'succeeded', degraded: false }), {
          status: 200,
        }),
      );
    const events = [];
    for await (const item of connectRunStream('run-1', {
      baseUrl: 'http://agent.test',
      tenantId: 'tenant-demo',
      lastEventId: '1',
      fetcher: fetchMock,
      maxReconnects: 1,
    }))
      events.push(item);
    expect(events.map((item) => item.sequence)).toEqual([2]);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      headers: { 'X-Tenant-ID': 'tenant-demo', 'Last-Event-ID': '1' },
    });
  });
  it('Abort 后不重连', async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockImplementation(async () => {
      controller.abort();
      throw new Error('aborted');
    });
    const events = [];
    for await (const item of connectRunStream('run-1', {
      baseUrl: 'http://agent.test',
      tenantId: 'tenant-demo',
      signal: controller.signal,
      fetcher: fetchMock,
      maxReconnects: 3,
    }))
      events.push(item);
    expect(events).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('干净 EOF 耗尽重连次数后抛出稳定错误', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('', { status: 200 }));
    const consume = async () => {
      for await (const event of connectRunStream('run-1', {
        baseUrl: 'http://agent.test',
        tenantId: 'tenant-demo',
        fetcher: fetchMock,
        maxReconnects: 1,
      }))
        void event;
    };
    await expect(consume()).rejects.toThrow('SSE_RECONNECT_EXHAUSTED');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it('同一响应块出现 stream_done 后不再交付后续事件', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          envelope(1, 'assistant_delta', { delta: '正文' }) +
            envelope(2, 'stream_done', { status: 'succeeded', degraded: false }) +
            envelope(3, 'assistant_delta', { delta: '迟到正文' }),
          { status: 200 },
        ),
      );
    const events = [];
    for await (const item of connectRunStream('run-1', {
      baseUrl: 'http://agent.test',
      tenantId: 'tenant-demo',
      fetcher: fetchMock,
    }))
      events.push(item);

    expect(events.map((item) => item.sequence)).toEqual([1, 2]);
  });
});
