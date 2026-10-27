import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  answerModeSchema,
  messageViewSchema,
  runSchema,
} from '../../entities/customer-service/schemas';

import { getTimeline, listMessages } from './api';
import { CustomerServiceAnswer } from './CustomerServiceAnswer';
import { parseCustomerServiceSse } from './sseClient';

// Captured from the HTTP 200 acceptance response on 2026-10-27.
const messagesPayload = {
  code: 'SUCCESS',
  message: 'success',
  data: [
    {
      message: {
        id: 'b1f25a59-42f1-4298-9ee6-86cf0d070483',
        conversationId: '88be3f1e-4218-4aec-b74e-cd39ef98b8f4',
        tenantId: 'dev',
        role: 'USER',
        content: '按那个方案执行。',
        status: 'COMPLETED',
        answerMode: null,
        runId: 'ef71495f-d13a-488d-9a36-3c4a903edabe',
        clientRequestId: '920cf3f8-add9-4b0c-865e-9ed46ce719d6',
        createdAt: '2026-10-27T02:28:24.690791Z',
      },
      citations: [],
    },
    {
      message: {
        id: '9ff40468-92c1-4776-95d9-81471ec25500',
        conversationId: '88be3f1e-4218-4aec-b74e-cd39ef98b8f4',
        tenantId: 'dev',
        role: 'ASSISTANT',
        content:
          '请补充所指“那个方案”的具体名称或内容（当前对话历史为空，无法解析指代对象），我再为你准确查询。',
        status: 'COMPLETED',
        answerMode: 'CLARIFY',
        runId: 'ef71495f-d13a-488d-9a36-3c4a903edabe',
        clientRequestId: null,
        createdAt: '2026-10-27T02:28:24.690791Z',
      },
      citations: [],
    },
  ],
  traceId: null,
};
const assistant = messagesPayload.data[1];

afterEach(() => vi.unstubAllGlobals());

describe('CLARIFY answer contract', () => {
  it('accepts the captured persisted messages through the employee API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify(messagesPayload))),
    );

    const messages = await listMessages(assistant.message.conversationId);

    expect(messages.map((item) => item.message.role)).toEqual(['USER', 'ASSISTANT']);
    expect(messages[1]).toEqual(assistant);
  });

  it('restores a CLARIFY assistant through the timeline API', async () => {
    const timeline = {
      runId: assistant.message.runId,
      status: 'SUCCEEDED',
      lastEventSequence: 2,
      assistant,
      steps: [],
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: timeline }))),
    );

    expect(await getTimeline(timeline.runId)).toEqual(timeline);
  });

  it('accepts CLARIFY on run metadata', () => {
    expect(
      runSchema.parse({
        id: assistant.message.runId,
        conversationId: assistant.message.conversationId,
        tenantId: 'dev',
        userMessageId: messagesPayload.data[0].message.id,
        agentRunId: null,
        agentReleaseId: 'release-1',
        status: 'SUCCEEDED',
        answerMode: 'CLARIFY',
        lastEventSequence: 2,
        failureCode: null,
        failureMessage: null,
        startedAt: null,
        finishedAt: null,
        createdAt: assistant.message.createdAt,
        updatedAt: assistant.message.createdAt,
      }).answerMode,
    ).toBe('CLARIFY');
  });

  it('retains the completed CLARIFY event when parsing SSE', () => {
    expect(
      parseCustomerServiceSse('id: 2\nevent: run.completed\ndata: {"answerMode":"CLARIFY"}\n\n'),
    ).toEqual([{ id: 2, event: 'run.completed', payload: { answerMode: 'CLARIFY' } }]);
  });

  it('labels the persisted clarification answer for employees', () => {
    const parsed = messageViewSchema.parse(assistant);
    render(
      <CustomerServiceAnswer
        content={parsed.message.content}
        mode={parsed.message.answerMode}
        citations={parsed.citations}
        streaming={false}
        onCitation={vi.fn()}
      />,
    );

    expect(screen.getByText('需要补充信息')).toBeInTheDocument();
    expect(screen.getByText(assistant.message.content)).toBeInTheDocument();
  });

  it.each(['CLARIFICATION', 'MADE_UP'])('keeps rejecting the unsupported mode %s', (answerMode) => {
    expect(answerModeSchema.safeParse(answerMode).success).toBe(false);
    expect(
      parseCustomerServiceSse(
        `id: 2\nevent: run.completed\ndata: ${JSON.stringify({ answerMode })}\n\n`,
      ),
    ).toEqual([]);
  });
});
