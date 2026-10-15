import { describe, expect, it, vi } from 'vitest';
import {
  cancelRun,
  getConversation,
  getRun,
  listConversationMessages,
  submitConversationMessage,
} from './api';

const success = (data: unknown, status = 200) =>
  new Response(JSON.stringify({ code: 'SUCCESS', message: 'success', data, traceId: null }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

describe('运营助手 Java API', () => {
  it('提交消息仅发送 Java 公开契约，不发送可伪造身份', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      success(
        {
          conversationId: 'conversation/1',
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
    const signal = new AbortController().signal;
    await submitConversationMessage(
      {
        conversationId: 'conversation/1',
        message: '新品选题',
        requestId: 'req-1',
        userId: '不得发送',
      },
      { baseUrl: 'http://java.test/', tenantId: '不得发送', fetcher, signal },
    );
    expect(fetcher).toHaveBeenCalledWith(
      'http://java.test/api/operations/conversations/conversation%2F1/messages',
      expect.objectContaining({
        signal,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    expect(JSON.parse(fetcher.mock.calls[0]?.[1].body as string)).toEqual({
      message: '新品选题',
      clientRequestId: 'req-1',
    });
  });

  it('历史和 Run 查询使用固定开发身份下的 Java 路径', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        success({
          conversationId: 'conversation-1',
          title: null,
          status: 'active',
          createdAt: 'x',
        }),
      )
      .mockResolvedValueOnce(
        success({
          conversationId: 'conversation-1',
          messages: [
            {
              messageId: 'message-1',
              role: 'user',
              content: '热点',
              runId: 'run-1',
              createdAt: '2026-10-15T08:00:00',
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
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
    const options = { baseUrl: 'http://java.test', fetcher };
    await getConversation('conversation-1', options);
    await listConversationMessages('conversation-1', options);
    await getRun('run-1', options);
    expect(fetcher.mock.calls.map(([target]) => String(target))).toEqual([
      'http://java.test/api/operations/conversations/conversation-1',
      'http://java.test/api/operations/conversations/conversation-1/messages',
      'http://java.test/api/operations/runs/run-1',
    ]);
  });

  it('取消 API 使用 Java 公开契约', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      success({
        conversationId: 'conversation-1',
        runId: 'run/1',
        agentRunId: 'agent-1',
        status: 'cancelled',
        failureCode: null,
        failureMessage: null,
        lastEventSequence: 1,
      }),
    );
    await cancelRun('run/1', { baseUrl: 'http://java.test', fetcher });
    expect(fetcher).toHaveBeenCalledWith(
      'http://java.test/api/operations/runs/run%2F1/cancel',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetcher.mock.calls[0]?.[1]?.body).toBeUndefined();
  });
});
