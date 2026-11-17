import { expect, type Page } from './fixtures';
import type {
  Conversation,
  MessageView,
  CustomerServiceRun,
  Citation,
} from '../src/entities/customer-service/model';

const now = '2026-11-03T00:00:00Z';
export const answer = Array.from(
  { length: 18 },
  (_, i) => `### 服务步骤 ${i + 1}\n\n${'离线验收回答保留完整上下文。'.repeat(12)}`,
).join('\n\n');
export const source: Citation = {
  id: 'citation-1',
  runId: 'run-1',
  messageId: 'answer-1',
  citationNo: 1,
  knowledgeBaseId: 'kb-1',
  documentId: 'doc-1',
  documentVersionId: 'version-1',
  indexReleaseId: 'index-1',
  chunkId: 'chunk-1',
  documentTitle: '售后服务规范与复杂场景操作指南'.repeat(8),
  versionNo: 3,
  sectionPath: '售后/受理流程',
  pageNo: 5,
  quotedText: '售后申请应先核实订单，再登记问题并通知处理结果。',
  contentHash: 'fixture-hash',
  createdAt: now,
  citationType: 'FULL_PARENT',
};

export async function installCustomerJourney(
  page: Page,
  mode: 'success' | 'budget' | 'stop' | 'missing-citation' = 'success',
) {
  const conversations: Conversation[] = [];
  const messages: MessageView[] = [];
  const requests: { method: string; path: string; status: number; body: unknown }[] = [];
  const unknown: string[] = [];
  let feedback: unknown;
  let releaseEvents: (() => void) | undefined;
  const eventGate = new Promise<void>((resolve) => {
    releaseEvents = resolve;
  });
  const run: CustomerServiceRun = {
    id: 'run-1',
    conversationId: 'conversation-1',
    tenantId: 'offline',
    userMessageId: 'question-1',
    agentRunId: 'agent-run-1',
    agentReleaseId: 'release-1',
    status: 'RUNNING',
    answerMode: null,
    lastEventSequence: 0,
    failureCode: null,
    failureMessage: null,
    startedAt: now,
    finishedAt: null,
    createdAt: now,
    updatedAt: now,
  };
  const steps = [
    { sequence: 1, stage: 'retrieval', phase: 'COMPLETED' as const, summary: '已检索到售后规范' },
  ];
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== 'http://127.0.0.1:5197' && url.origin !== 'http://127.0.0.1:5190') {
      unknown.push(`${request.method()} external ${url.origin}`);
      await route.abort('blockedbyclient');
      return;
    }
    if (!url.pathname.startsWith('/api/')) {
      await route.fallback();
      return;
    }
    const method = request.method();
    const path = url.pathname;
    const body: unknown = request.postData() ? request.postDataJSON() : null;
    const respond = async (data: unknown, status = 200, code = 'SUCCESS', message?: string) => {
      requests.push({ method, path, status, body });
      await route.fulfill({ status, json: { code, data, ...(message ? { message } : {}) } });
    };
    const root = '/api/customer-service';
    if (path === `${root}/conversations` && method === 'GET') {
      await respond({ items: conversations, page: 1, pageSize: 20, total: conversations.length });
      return;
    }
    if (path === `${root}/conversations` && method === 'POST') {
      expect(body).toEqual({ title: '' });
      expect(conversations).toHaveLength(0);
      const conversation: Conversation = {
        id: 'conversation-1',
        tenantId: 'offline',
        userId: 'user-1',
        title: '新对话',
        status: 'ACTIVE',
        lastMessageAt: null,
        createdAt: now,
        updatedAt: now,
      };
      conversations.push(conversation);
      await respond(conversation);
      return;
    }
    if (path === `${root}/conversations/conversation-1` && method === 'PATCH') {
      const title = (body as { title: string }).title;
      expect(Object.keys(body as object)).toEqual(['title']);
      expect(title).toBe(title.trim());
      if (title === '重复名称') {
        await respond(
          null,
          409,
          'CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE',
          '会话名称已存在，请使用其他标题',
        );
        return;
      }
      expect(title).toBe('售后验收记录');
      conversations[0].title = title;
      await respond(conversations[0]);
      return;
    }
    if (path === `${root}/conversations/conversation-1/messages` && method === 'GET') {
      await respond(messages);
      return;
    }
    if (path === `${root}/conversations/conversation-1/messages` && method === 'POST') {
      expect(body).toEqual({
        contractVersion: 'customer-service-message/1',
        message: '如何申请售后？',
        clientRequestId: expect.stringMatching(/^[\da-f-]{36}$/),
      });
      if (mode === 'budget') {
        await respond(null, 402, 'PAID_BUDGET_REQUIRED', '未授权真实预算，已拒绝提交');
        return;
      }
      expect(messages).toHaveLength(0);
      messages.push({
        message: {
          id: 'question-1',
          conversationId: 'conversation-1',
          tenantId: 'offline',
          role: 'USER',
          content: '如何申请售后？',
          status: 'COMPLETED',
          answerMode: null,
          runId: null,
          clientRequestId: (body as { clientRequestId: string }).clientRequestId,
          createdAt: now,
        },
        citations: [],
      });
      messages.push({
        message: {
          id: 'answer-1',
          conversationId: 'conversation-1',
          tenantId: 'offline',
          role: 'ASSISTANT',
          content: '',
          status: 'STREAMING',
          answerMode: null,
          runId: run.id,
          clientRequestId: null,
          createdAt: now,
        },
        citations: [],
      });
      await respond({
        conversationId: 'conversation-1',
        runId: run.id,
        status: 'RUNNING',
        agentReleaseId: 'release-1',
      });
      return;
    }
    if (path === `${root}/runs/run-1/events` && method === 'GET') {
      expect(request.headers().accept).toBe('text/event-stream');
      expect(url.searchParams.get('afterSequence')).toBe('0');
      if (mode === 'stop') await eventGate;
      const event = (id: number, name: string, payload: unknown) =>
        `id: ${id}\nevent: ${name}\ndata: ${JSON.stringify(payload)}\n\n`;
      let content = event(1, 'run.progress', {
        stage: 'retrieval',
        phase: 'COMPLETED',
        summary: steps[0].summary,
      });
      if (mode === 'stop') content += event(2, 'run.cancelled', {});
      else {
        messages[1].message.content = answer;
        messages[1].message.status = 'COMPLETED';
        messages[1].message.answerMode = 'COMPANY_KNOWLEDGE';
        messages[1].citations = mode === 'missing-citation' ? [] : [source];
        run.status = 'SUCCEEDED';
        run.answerMode = 'COMPANY_KNOWLEDGE';
        run.finishedAt = now;
        run.lastEventSequence = 4;
        content += event(2, 'message.delta', { delta: answer });
        if (mode !== 'missing-citation') content += event(3, 'citation.ready', source);
        content += event(4, 'run.completed', { answerMode: 'COMPANY_KNOWLEDGE' });
      }
      requests.push({ method, path, status: 200, body });
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: content });
      return;
    }
    if (path === `${root}/runs/run-1/cancel` && method === 'POST') {
      expect(body).toBeNull();
      run.status = 'CANCELLED';
      run.finishedAt = now;
      messages[1].message.status = 'CANCELLED';
      await respond(run);
      releaseEvents?.();
      return;
    }
    if (path === `${root}/runs/run-1` && method === 'GET') {
      await respond(run);
      return;
    }
    if (path === `${root}/runs/run-1/timeline` && method === 'GET') {
      await respond({
        runId: run.id,
        status: run.status,
        lastEventSequence: run.lastEventSequence,
        assistant: messages[1],
        steps,
      });
      return;
    }
    if (path === `${root}/messages/answer-1/feedback` && method === 'PUT') {
      expect(body).toEqual({ rating: 'UP', reasonCode: null, comment: null });
      feedback = body;
      await respond({
        id: 'feedback-1',
        conversationId: 'conversation-1',
        messageId: 'answer-1',
        runId: run.id,
        tenantId: 'offline',
        userId: 'user-1',
        ...(body as object),
        createdAt: now,
        updatedAt: now,
      });
      return;
    }
    unknown.push(`${method} ${path}`);
    await route.abort('blockedbyclient');
  });
  return {
    conversations,
    messages,
    requests,
    unknown,
    run,
    feedback: () => feedback,
    writes: () => requests.filter((r) => ['POST', 'PATCH', 'PUT', 'DELETE'].includes(r.method)),
  };
}
