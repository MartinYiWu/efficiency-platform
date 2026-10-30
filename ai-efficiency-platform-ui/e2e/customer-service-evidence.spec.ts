import { expect, test } from './fixtures';

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
  originalSpans: [
    { start_offset: 0, end_offset: 4, content_hash: 'hash' },
    { start_offset: 20, end_offset: 24, content_hash: 'hash2' },
  ],
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
const longOriginal =
  '这是需要完整保留上下文的技术说明。'.repeat(80) + 'UNBROKEN_IDENTIFIER_'.repeat(30);
const evidence = {
  rank: 1,
  query_index: 1,
  chunk_id: 'ch',
  parent_id: 'p',
  knowledge_base_id: 'kb',
  document_id: 'd',
  document_version_id: 'v',
  index_release_id: 'index',
  document_title: '技术指南',
  version_no: 1,
  section_path: null,
  page_no: null,
  content: longOriginal,
  content_hash: 'hash',
  score: 0,
};
const parent = {
  parent_id: 'p',
  knowledge_base_id: 'kb',
  document_id: 'd',
  document_version_id: 'v',
  index_release_id: 'index',
  document_title: '技术指南',
  version_no: 1,
  section_path: null,
  page_no: null,
  content: longOriginal,
  content_hash: 'hash',
  token_count: 1000,
  block_kind: 'PARAGRAPH',
  evidence_mode: 'EXTRACTIVE_NARRATIVE',
};
const conflict = {
  pairs: [
    {
      left_parent_id: 'p',
      right_parent_id: 'p2',
      same_scope: true,
      verdict: 'CONFLICT',
      left_quote: '允许离线使用',
      right_quote: '禁止离线使用',
      reason: '适用条件存在冲突',
    },
  ],
  errors: [],
  blocked: true,
};
const facts = {
  equivalence_decisions: [
    {
      left: evidence,
      right: { ...evidence, chunk_id: 'ch2', parent_id: 'p2' },
      left_parent: parent,
      right_parent: { ...parent, parent_id: 'p2' },
      similarity: 0.98,
      reason: 'DIFFERENT_CONDITIONS',
      result: {
        left_chunk_id: 'ch',
        right_chunk_id: 'ch2',
        verdict: 'DIFFERENT',
        left_quote: '仅内部使用',
        right_quote: '允许外部使用',
        differing_conditions: ['受众范围不同'],
      },
      retained_parent_id: null,
      merged_chunk_ids: [],
    },
  ],
  equivalence_errors: [],
  version_exclusions: [],
  final_parent_candidates: ['p'],
  evidence_groups: [{ parent_ids: ['p', 'p2'] }],
  grouping_decisions: [{ parent_id: 'p', reason: 'ADJACENT_SECTION' }],
  conflict_screen: conflict,
  evidence_pack: {
    entries: [
      {
        ...evidence,
        original_parent: parent,
        citation_type: 'EXTRACTED_SPANS',
        original_spans: citation.originalSpans,
        hit_chunk_ids: ['ch'],
      },
    ],
    groups: [{ parent_ids: ['p', 'p2'] }],
    exclusions: [{ parent_id: 'p3', reason: 'BUDGET_EXCLUDED' }],
    model_policy: {
      policy_key: 'large',
      semantic_version: '1',
      provider: 'fake',
      model_name: 'frozen-large-model',
      temperature: 0,
      top_p: 1,
      max_input_tokens: 64000,
      max_output_tokens: 1000,
      connect_timeout_ms: 10,
      read_timeout_ms: 10,
      max_retries: 0,
      checksum: 'hash',
    },
    budget: {
      context_token_limit: 60000,
      reserved_tokens: 1000,
      used_tokens: 2000,
      output_tokens: 1000,
      safety_tokens: 100,
      fixed_input_tokens: 800,
      intermediate_output_tokens: 100,
      evidence_tokens: 1000,
    },
    blocked: true,
    block_reasons: ['CONFLICT'],
    extraction_decisions: [
      { parent_id: 'p', selected_sentence_ids: [0, 2], reason: 'EXACT_SENTENCE_SELECTION' },
    ],
    conflict_screen: conflict,
  },
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
          versions: [
            {
              id: 'av',
              agentDefinitionId: 'a',
              semanticVersion: '1',
              graphKey: 'customer-service',
              graphVersion: '1',
              status: 'PUBLISHED',
              changeSummary: null,
              createdBy: '1',
              createdAt: now,
              publishedAt: now,
            },
          ],
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
        '/api/aihub/policies': {
          modelPolicies: [],
          ragPolicies: [
            {
              id: 'rp',
              ownerAgentDefinitionId: 'a',
              policyKey: 'evidence-policy',
              semanticVersion: '1',
              rewriteQueryLimit: 3,
              vectorTopK: 10,
              ftsTopK: 10,
              fusionTopK: 10,
              rerankTopK: 5,
              contextTokenLimit: 60000,
              citationLimit: 5,
              status: 'PUBLISHED',
              checksum: null,
              createdBy: '1',
              createdAt: now,
              publishedAt: now,
            },
          ],
        },
        '/api/aihub/agents/customer-service/releases': [
          {
            id: 'rel',
            agentDefinitionId: 'a',
            agentVersionId: 'av',
            environment: 'TEST',
            releaseStatus: 'ACTIVE',
            releaseSnapshotId: 'snap',
            releasedBy: '1',
            releasedAt: now,
            rolledBackFromReleaseId: null,
            createdAt: now,
          },
        ],
        '/api/aihub/rag-debug-runs': {
          ...facts,
          contract_version: 'customer-service-rag-debug-view/1',
          debug_run_id: 'dr',
          status: 'SUCCEEDED',
          stages: [],
          answer_mode: null,
          answer_markdown: null,
          error_code: null,
          error_message: null,
        },
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
      if (url.includes('rag-debug')) {
        await page.getByRole('combobox').nth(0).click();
        await page.getByText('证据客服', { exact: true }).last().click();
        await page.getByRole('combobox').nth(1).click();
        await page.getByText('TEST · rel', { exact: true }).click();
        await page.getByRole('combobox').nth(3).click();
        await page.getByText('evidence-policy@1', { exact: true }).click();
        await page.getByPlaceholder('知识库 ID').fill('kb');
        await page.getByPlaceholder('索引 Release ID').fill('index');
        await page.getByPlaceholder('输入真实问题').fill('离线技术支持范围是什么？');
        const debugResponse = page.waitForResponse(
          (response) =>
            response.url().includes('/api/aihub/rag-debug-runs') &&
            response.request().method() === 'POST',
        );
        await page.getByRole('button', { name: '执行调试' }).click();
        expect((await debugResponse).status()).toBe(200);
      }
      if (url.includes('runs/r') || url.includes('rag-debug')) {
        for (const text of [
          '旧版过滤计数：0',
          'frozen-large-model',
          '允许离线使用',
          '禁止离线使用',
          'BUDGET_EXCLUDED',
        ]) {
          await page.getByText(text, { exact: true }).first().scrollIntoViewIfNeeded();
          await expect(page.getByText(text, { exact: true }).first()).toBeVisible();
        }
        await expect(page.getByText(/受众范围不同/)).toBeVisible();
        await expect(page.getByText(/ADJACENT_SECTION/)).toBeVisible();
        await expect(page.getByText(/实际使用 Token/)).toBeVisible();
        await expect(page.getByText(longOriginal, { exact: true })).toBeVisible();
        await expect(page.getByText(/原文偏移.*\[起,止\)/)).toContainText('[20, 24)');
      }
      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
        .toBe(true);
    }
    await page.goto('/ai-assistants/customer-service/chat');
    if (width < 768) {
      await page.getByRole('button', { name: /^history 历史会话$/ }).click();
      await page
        .getByRole('dialog', { name: '历史会话' })
        .getByRole('button', { name: '历史会话', exact: true })
        .click();
      await expect(page.getByRole('dialog', { name: '历史会话' })).toBeHidden();
    } else {
      await page.getByRole('button', { name: '历史会话', exact: true }).click();
    }
    const button = page.getByRole('button', { name: /技术指南.*原文节选/ });
    await expect(button).toBeVisible();
    await button.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('dialog')).toContainText('准确原文');
    await expect(page.getByRole('dialog')).toContainText('原文节选');
    await expect(page.getByRole('dialog')).not.toContainText('[0, 4)');
    await expect(page.getByRole('dialog')).not.toContainText('[20, 24)');
    await expect(page.getByRole('dialog')).not.toContainText(/Rerank|Prompt|BUDGET_EXCLUDED/);
    await expect(page.getByRole('log')).not.toContainText(/Rerank|Prompt|BUDGET_EXCLUDED/);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
  });
}
