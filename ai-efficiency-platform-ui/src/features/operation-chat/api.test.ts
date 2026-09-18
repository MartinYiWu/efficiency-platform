import { describe, expect, it, vi } from 'vitest';
import { cancelRun, submitConversationMessage } from './api';

describe('运营助手 API', () => {
  it('使用会话路径、租户头和版本化请求体', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          contract_version: 'conversation/1',
          conversation_id: 'conversation/1',
          turn_id: 'turn-1',
          run_id: 'run-1',
          status: 'queued',
        }),
        { status: 201 },
      ),
    );
    const signal = new AbortController().signal;
    await submitConversationMessage(
      {
        conversationId: 'conversation/1',
        message: '新品选题',
        requestId: 'req-1',
        userId: 'user-1',
      },
      { baseUrl: 'http://agent.test/', tenantId: 'tenant-demo', fetcher, signal },
    );
    expect(fetcher).toHaveBeenCalledWith(
      'http://agent.test/v1/conversations/conversation%2F1/messages',
      expect.objectContaining({
        signal,
        headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': 'tenant-demo' },
      }),
    );
    expect(JSON.parse(fetcher.mock.calls[0]?.[1].body as string)).toEqual({
      contract_version: 'conversation/1',
      message: '新品选题',
      request_id: 'req-1',
      user_id: 'user-1',
      attachments: [],
    });
  });
  it('取消 API 使用稳定契约', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    await cancelRun('run/1', { baseUrl: 'http://agent.test', tenantId: 'tenant-demo', fetcher });
    expect(fetcher).toHaveBeenCalledWith(
      'http://agent.test/v1/runs/run%2F1/cancel',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(JSON.parse(fetcher.mock.calls[0]?.[1].body as string)).toMatchObject({
      contract_version: 'run.cancel/1',
      tenant_id: 'tenant-demo',
      reason_code: 'user_requested',
    });
  });
});
