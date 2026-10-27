import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { RagPolicyPage } from './RagPolicyPage';
import { RunReplayPage } from './RunReplayPage';
import { CustomerServiceAnswer } from '../../features/customer-service-chat/CustomerServiceAnswer';
import { citationSchema } from '../../entities/customer-service/schemas';
import * as api from '../../features/ai-center/api';

afterEach(() => vi.restoreAllMocks());

it('offers bounded evidence controls in the existing policy form', async () => {
  vi.spyOn(api, 'listAgents').mockResolvedValue([]);
  vi.spyOn(api, 'listPolicies').mockResolvedValue({ modelPolicies: [], ragPolicies: [] });
  render(
    <MemoryRouter initialEntries={['/?agentId=a']}>
      <RagPolicyPage />
    </MemoryRouter>,
  );
  expect(await screen.findByLabelText('最终父证据 TopK')).toHaveValue('8');
  expect(screen.getByLabelText('相似候选阈值')).toHaveValue('0.96');
  expect(screen.getByText(/仅筛选送入等价判断/)).toBeInTheDocument();
});

it('shows a necessary excerpt marker on a keyboard accessible citation button', () => {
  const citation = citationSchema.parse({
    id: 'c',
    runId: 'r',
    messageId: 'm',
    citationNo: 1,
    knowledgeBaseId: 'k',
    documentId: 'd',
    documentVersionId: 'v',
    indexReleaseId: 'i',
    chunkId: 'ch',
    documentTitle: '技术指南',
    versionNo: 1,
    sectionPath: null,
    pageNo: null,
    quotedText: '准确原文',
    contentHash: 'hash',
    createdAt: 'now',
    citationType: 'EXTRACTED_SPANS',
    parentId: 'p',
    originalSpans: [{ start_offset: 0, end_offset: 4, content_hash: 'hash' }],
  });
  const onCitation = vi.fn();
  render(
    <CustomerServiceAnswer
      content="回答"
      mode="COMPANY_KNOWLEDGE"
      citations={[citation]}
      streaming={false}
      onCitation={onCitation}
    />,
  );
  const button = screen.getByRole('button', { name: /技术指南.*原文节选/ });
  button.focus();
  expect(button).toHaveFocus();
  fireEvent.click(button);
  expect(onCitation).toHaveBeenCalledWith(citation);
  expect(screen.queryByText(/score|Prompt|CONFLICT/)).not.toBeInTheDocument();
});

const historicalReplay = {
  run: {
    id: 'r',
    status: 'SUCCEEDED',
    agentReleaseId: 'old',
    answerMode: null,
    conversationId: 'c',
    tenantId: 't',
    userMessageId: 'm',
    agentRunId: 'ar',
    lastEventSequence: 1,
    failureCode: null,
    failureMessage: null,
    startedAt: null,
    finishedAt: null,
    createdAt: 'now',
    updatedAt: 'now',
  },
  question: {
    id: 'm',
    conversationId: 'c',
    tenantId: 't',
    role: 'USER',
    content: '问题',
    status: 'COMPLETED',
    answerMode: null,
    runId: 'r',
    clientRequestId: null,
    createdAt: 'now',
  },
  answer: null,
  stages: [
    {
      id: 's2',
      runId: 'r',
      sequenceNo: 2,
      stage: '形成回答',
      status: 'SUCCEEDED',
      publicSummary: '答案已完成',
      internalPayload: null,
      startedAt: null,
      finishedAt: null,
    },
    {
      id: 's1',
      runId: 'r',
      sequenceNo: 1,
      stage: '检索知识',
      status: 'SUCCEEDED',
      publicSummary: '检索已完成',
      internalPayload: null,
      startedAt: null,
      finishedAt: null,
    },
  ],
  citations: [
    citationSchema.parse({
      id: 'legacy',
      runId: 'r',
      messageId: 'm',
      citationNo: 1,
      knowledgeBaseId: 'k',
      documentId: 'd',
      documentVersionId: 'v',
      indexReleaseId: 'i',
      chunkId: 'ch',
      documentTitle: '历史引用',
      versionNo: 1,
      sectionPath: null,
      pageNo: null,
      quotedText: '旧原文',
      contentHash: 'hash',
      createdAt: 'now',
      citationType: null,
    }),
  ],
  feedback: null,
};

it('marks unrecorded historical processing facts instead of reconstructing them', async () => {
  vi.spyOn(api, 'getRunReplay').mockResolvedValue(historicalReplay);
  render(
    <MemoryRouter>
      <RunReplayPage />
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByText('历史引用')).toBeInTheDocument());
  const retrieval = screen.getByText('检索知识');
  const answer = screen.getByText('形成回答');
  expect(retrieval.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByText('完整原文')).not.toBeInTheDocument();
  expect(screen.getAllByText('该版本未记录').length).toBeGreaterThan(1);
});

it('renders the recorded candidates when switching all four replay evidence tabs', async () => {
  const candidates = ['vector', 'fts', 'rrf', 'rerank'].map((name, index) => ({
    chunk_id: `${name}-child`,
    parent_id: 'parent-1',
    document_version_id: 'version-1',
    index_release_id: 'index-1',
    rank: index + 1,
    score: (index + 1) / 10,
    excerpt: `${name} 原文`,
  }));
  vi.spyOn(api, 'getRunReplay').mockResolvedValue({
    ...historicalReplay,
    stages: [
      {
        ...historicalReplay.stages[0],
        internalPayload: JSON.stringify({
          retrieval_facts: {
            vector_candidates: [candidates[0]],
            fts_candidates: [candidates[1]],
            fused_candidates: [candidates[2]],
            child_hits: [candidates[3]],
          },
        }),
      },
    ],
  });
  render(
    <MemoryRouter>
      <RunReplayPage />
    </MemoryRouter>,
  );
  const user = userEvent.setup();
  const labels = ['向量原始分数', '全文原始分数', 'RRF 分数', 'Rerank 分数'];
  for (const [index, label] of labels.entries()) {
    const tab = await screen.findByRole('tab', { name: `${label} (1)` });
    await user.click(tab);
    await waitFor(() => expect(tab).toHaveAttribute('aria-selected', 'true'), { timeout: 5000 });
    const panel = within(await screen.findByRole('tabpanel'));
    expect(await panel.findByText(candidates[index].chunk_id)).toBeInTheDocument();
    expect(panel.getByText(String(candidates[index].rank))).toBeInTheDocument();
    expect(panel.getByText(candidates[index].score.toFixed(3))).toBeInTheDocument();
    expect(panel.getByText(candidates[index].excerpt)).toBeInTheDocument();
  }
});
