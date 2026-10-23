import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

it('marks unrecorded historical processing facts instead of reconstructing them', async () => {
  vi.spyOn(api, 'getRunReplay').mockResolvedValue({
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
    stages: [],
    citations: [],
    feedback: null,
  });
  render(
    <MemoryRouter>
      <RunReplayPage />
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByText('该版本未记录')).toBeInTheDocument());
});
