import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useOperationChat } from './useOperationChat';

const success = (data: unknown, status = 200) =>
  new Response(JSON.stringify({ code: 'SUCCESS', message: 'success', data, traceId: null }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const streamDone = (sequence: number) =>
  new Response(
    `id: ${sequence}\nevent: stream_done\ndata: ${JSON.stringify({
      contract_version: 'run.stream.event/1',
      event: 'stream_done',
      run_id: 'run-1',
      sequence,
      payload: { status: 'succeeded', degraded: false },
    })}\n\n`,
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );

describe('useOperationChat 生命周期', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
    vi.restoreAllMocks();
  });

  it('页面首次进入时创建会话并用 replaceState 写入 URL', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      success({
        conversationId: 'conversation-1',
        title: null,
        status: 'active',
        createdAt: '2026-10-15T08:00:00',
      }),
    );
    const { result } = renderHook(() => useOperationChat({ baseUrl: 'http://java.test', fetcher }));

    await waitFor(() => expect(result.current.isRestoring).toBe(false));
    expect(new URLSearchParams(window.location.search).get('conversationId')).toBe(
      'conversation-1',
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('从 URL 恢复消息和制品，并从 Java 已确认 sequence 续接未终态 Run', async () => {
    window.history.replaceState(null, '', '/?conversationId=conversation-1');
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const target = String(input);
      if (target.endsWith('/conversations/conversation-1'))
        return Promise.resolve(
          success({
            conversationId: 'conversation-1',
            title: 'AI 热点',
            status: 'active',
            createdAt: '2026-10-15T08:00:00',
          }),
        );
      if (target.endsWith('/messages'))
        return Promise.resolve(
          success({
            conversationId: 'conversation-1',
            messages: [
              {
                messageId: 'message-1',
                role: 'user',
                content: '收集 AI 热点',
                runId: 'run-1',
                createdAt: '2026-10-15T08:01:00',
              },
            ],
          }),
        );
      if (target.endsWith('/artifacts'))
        return Promise.resolve(
          success({
            conversationId: 'conversation-1',
            artifacts: [
              {
                artifactId: 'artifact-1',
                artifactType: 'platform_content',
                platform: 'wechat_official_account',
                version: 1,
                title: '公众号周更',
                createdAt: '2026-10-15T08:02:00',
              },
            ],
          }),
        );
      if (target.endsWith('/runs/run-1'))
        return Promise.resolve(
          success({
            conversationId: 'conversation-1',
            runId: 'run-1',
            agentRunId: 'agent-1',
            status: 'running',
            failureCode: null,
            failureMessage: null,
            lastEventSequence: 7,
          }),
        );
      if (target.includes('/events?afterSequence=7')) {
        expect(init?.headers).toMatchObject({ 'Last-Event-ID': '7' });
        return Promise.resolve(streamDone(8));
      }
      throw new Error(`unexpected request: ${target}`);
    });

    const { result } = renderHook(() => useOperationChat({ baseUrl: 'http://java.test', fetcher }));
    await waitFor(() => expect(result.current.isRestoring).toBe(false));

    expect(result.current.state.status).toBe('succeeded');
    expect(result.current.state.messages.map((message) => message.content)).toEqual([
      '收集 AI 热点',
    ]);
    expect(result.current.artifacts.map((artifact) => artifact.artifactId)).toEqual(['artifact-1']);
    expect(fetcher).toHaveBeenCalledTimes(6);
  });

  it('组件卸载时中止同一信号上的 SSE 订阅', async () => {
    let streamSignal: AbortSignal | undefined;
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const target = String(input);
      if (target.endsWith('/conversations'))
        return Promise.resolve(
          success({
            conversationId: 'conversation-1',
            title: null,
            status: 'active',
            createdAt: '2026-10-15T08:00:00',
          }),
        );
      if (target.endsWith('/messages'))
        return Promise.resolve(
          success(
            {
              conversationId: 'conversation-1',
              runId: 'run-1',
              agentRunId: 'agent-1',
              status: 'queued',
              failureCode: null,
              failureMessage: null,
              lastEventSequence: 0,
            },
            202,
          ),
        );
      streamSignal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        streamSignal?.addEventListener('abort', () => {
          reject(new DOMException('订阅已中止', 'AbortError'));
        });
      });
    });
    const { result, unmount } = renderHook(() =>
      useOperationChat({ baseUrl: 'http://java.test', fetcher }),
    );
    await waitFor(() => expect(result.current.isRestoring).toBe(false));

    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.sendMessage('生成行业热点摘要');
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
    expect(streamSignal?.aborted).toBe(false);

    unmount();
    expect(streamSignal?.aborted).toBe(true);
    await request;
  });
});
