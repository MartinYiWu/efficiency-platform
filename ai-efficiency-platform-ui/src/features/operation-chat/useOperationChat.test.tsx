import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useOperationChat } from './useOperationChat';

describe('useOperationChat 生命周期', () => {
  it('组件卸载时中止尚未完成的会话提交', async () => {
    let observedSignal: AbortSignal | undefined;
    const fetcher = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      observedSignal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        observedSignal?.addEventListener('abort', () => {
          reject(new DOMException('请求已中止', 'AbortError'));
        });
      });
    });
    const { result, unmount } = renderHook(() =>
      useOperationChat({ baseUrl: 'http://agent.test', fetcher }),
    );

    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.sendMessage('生成一份运营方案');
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

    expect(observedSignal).toBeDefined();
    expect(observedSignal?.aborted).toBe(false);
    unmount();
    expect(observedSignal?.aborted).toBe(true);
    await request;
  });

  it('组件卸载时把同一中止信号传播到 SSE 订阅', async () => {
    let streamSignal: AbortSignal | undefined;
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/messages')) {
        const conversationId = String(input).split('/').at(-2) ?? '';
        return Promise.resolve(
          new Response(
            JSON.stringify({
              contract_version: 'conversation/1',
              conversation_id: conversationId,
              turn_id: 'turn-1',
              run_id: 'run-1',
              status: 'queued',
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      streamSignal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        streamSignal?.addEventListener('abort', () => {
          reject(new DOMException('订阅已中止', 'AbortError'));
        });
      });
    });
    const { result, unmount } = renderHook(() =>
      useOperationChat({ baseUrl: 'http://agent.test', fetcher }),
    );

    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.sendMessage('生成行业热点摘要');
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));

    expect(streamSignal).toBeDefined();
    expect(streamSignal?.aborted).toBe(false);
    unmount();
    expect(streamSignal?.aborted).toBe(true);
    await request;
  });

  it('提交阶段请求停止且取消失败时保留错误并继续订阅权威 Run', async () => {
    let resolveSubmission: ((response: Response) => void) | undefined;
    const submission = new Promise<Response>((resolve) => {
      resolveSubmission = resolve;
    });
    let streamSignal: AbortSignal | undefined;
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const target = String(input);
      if (target.endsWith('/messages')) return submission;
      if (target.endsWith('/cancel')) {
        return Promise.resolve(new Response(null, { status: 503 }));
      }
      streamSignal = init?.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        streamSignal?.addEventListener('abort', () => {
          reject(new DOMException('订阅已中止', 'AbortError'));
        });
      });
    });
    const { result, unmount } = renderHook(() =>
      useOperationChat({ baseUrl: 'http://agent.test', fetcher }),
    );

    let request: Promise<void> | undefined;
    act(() => {
      request = result.current.sendMessage('生成一份运营方案');
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.cancel();
    });
    expect(result.current.state.status).toBe('cancelling');

    const conversationId = String(fetcher.mock.calls[0]?.[0]).split('/').at(-2) ?? '';
    act(() => {
      resolveSubmission?.(
        new Response(
          JSON.stringify({
            contract_version: 'conversation/1',
            conversation_id: conversationId,
            turn_id: 'turn-1',
            run_id: 'run-1',
            status: 'queued',
          }),
          { status: 201, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    });

    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
    expect(result.current.state.status).toBe('streaming');
    expect(result.current.state.runId).toBe('run-1');
    expect(result.current.state.error).toBe('运营助手请求失败，请稍后重试。');
    unmount();
    expect(streamSignal?.aborted).toBe(true);
    await request;
  });
});
