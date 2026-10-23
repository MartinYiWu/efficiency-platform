import { expect, test } from '@playwright/test';

const now = '2026-10-23T00:00:00Z';
const agent = {
  id: 'a',
  agentKey: 'customer-service',
  name: '证据客服',
  description: null,
  agentType: 'CUSTOMER_SERVICE',
  status: 'ACTIVE',
  createdBy: '1',
  createdAt: now,
  updatedBy: '1',
  updatedAt: now,
};
const citation = {
  id: 'ci',
  runId: 'r',
  messageId: 'answer',
  citationNo: 1,
  knowledgeBaseId: 'kb',
  documentId: 'd',
  documentVersionId: 'v',
  indexReleaseId: 'index',
  chunkId: 'ch',
  documentTitle: '技术指南',
  versionNo: 1,
  sectionPath: null,
  pageNo: null,
  quotedText: '准确原文',
  contentHash: 'hash',
  createdAt: now,
  parentId: 'p',
  citationType: 'EXTRACTED_SPANS',
  originalSpans: [{ start_offset: 0, end_offset: 4, content_hash: 'hash' }],
};
const message = {
  id: 'answer',
  conversationId: 'c',
  tenantId: 't',
  role: 'ASSISTANT',
  content: '依据资料回答',
  status: 'COMPLETED',
  answerMode: 'COMPANY_KNOWLEDGE',
  runId: 'r',
  clientRequestId: null,
  createdAt: now,
};
const run = {
  id: 'r',
  conversationId: 'c',
  tenantId: 't',
  userMessageId: 'q',
  agentRunId: 'ar',
  agentReleaseId: 'rel',
  status: 'SUCCEEDED',
  answerMode: 'COMPANY_KNOWLEDGE',
  lastEventSequence: 1,
  failureCode: null,
  failureMessage: null,
  startedAt: now,
  finishedAt: now,
  createdAt: now,
  updatedAt: now,
};
const facts = {
  equivalence_decisions: [],
  equivalence_errors: [],
  version_exclusions: [],
  final_parent_candidates: ['p'],
  evidence_groups: [],
  grouping_decisions: [],
  conflict_screen: { pairs: [], errors: [], blocked: false },
  child_hits: [
    {
      chunk_id: 'ch',
      parent_id: 'p',
      document_version_id: 'v',
      index_release_id: 'index',
      rank: 1,
      score: 0,
      excerpt: '准确原文',
    },
  ],
};
const base = {
  id: 'kb',
  code: 'tech',
  name: '技术资料',
  description: null,
  knowledgeType: 'TECHNICAL_DOCUMENTATION',
  visibilityScope: 'ALL_EMPLOYEES',
  status: 'ACTIVE',
  currentIndexReleaseId: 'new-index',
  createdAt: now,
  updatedAt: now,
};
const document = {
  id: 'd',
  knowledgeBaseId: 'kb',
  directoryId: null,
  title: '技术指南',
  documentCode: 'TECH-1',
  sourceType: 'UPLOAD',
  status: 'ACTIVE',
  currentPublishedVersionId: 'v',
  versions: [],
};

for (const width of [1440, 1024, 390]) {
  test(`evidence pages and public excerpt stay usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      const responses: Record<string, unknown> = {
        '/api/aihub/agents': [agent],
        '/api/aihub/agents/a': {
          definition: agent,
          versions: [],
          evidenceBindings: [
            {
              sourceType: 'RELEASE',
              sourceId: 'rel',
              largeModelName: 'large-model',
              maxInputTokens: 64000,
              knowledgeBaseId: 'kb',
              boundIndexReleaseId: 'old-index',
              currentIndexReleaseId: 'new-index',
            },
          ],
        },
        '/api/aihub/policies': { modelPolicies: [], ragPolicies: [] },
        '/api/aihub/runs/r/replay': {
          run,
          question: { ...message, id: 'q', role: 'USER', content: '问题' },
          answer: message,
          stages: [
            {
              id: 's',
              runId: 'r',
              sequenceNo: 1,
              stage: 'retrieval',
              status: 'SUCCEEDED',
              publicSummary: '完成',
              internalPayload: JSON.stringify({ retrieval_facts: facts }),
              startedAt: now,
              finishedAt: now,
            },
          ],
          citations: [citation],
          feedback: null,
        },
        '/api/knowledge/documents/d': document,
        '/api/knowledge/bases/kb': base,
        '/api/customer-service/conversations': {
          items: [
            {
              id: 'c',
              tenantId: 't',
              userId: '1',
              title: '历史会话',
              status: 'ACTIVE',
              lastMessageAt: now,
              createdAt: now,
              updatedAt: now,
            },
          ],
          page: 1,
          pageSize: 20,
          total: 1,
        },
        '/api/customer-service/conversations/c/messages': [{ message, citations: [citation] }],
      };
      await route.fulfill({ json: { code: 'SUCCESS', data: responses[path] ?? [] } });
    });
    for (const [url, title] of [
      ['/ai-center/rag-policies?agentId=a', 'RAG 策略'],
      ['/ai-center/agents/a', '证据客服'],
      ['/knowledge-center/documents/d', '技术指南'],
      ['/ai-center/rag-debug', 'RAG 调试'],
      ['/ai-center/runs/r', 'Run 回放'],
    ]) {
      await page.goto(url);
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
      if (url.includes('agents/a'))
        await expect(page.getByText('绑定索引落后于知识库当前发布索引')).toBeVisible();
      if (url.includes('runs/r')) await expect(page.getByText('旧版过滤计数：0')).toBeVisible();
      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
        .toBe(true);
    }
    await page.goto('/ai-assistants/customer-service/chat');
    await page.getByRole('button', { name: '历史会话', exact: true }).click();
    const button = page.getByRole('button', { name: /技术指南.*原文节选/ });
    await expect(button).toBeVisible();
    await button.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toContainText('准确原文');
    await expect(page.getByRole('log')).not.toContainText(/Rerank|Prompt|BUDGET_EXCLUDED/);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
  });
}
