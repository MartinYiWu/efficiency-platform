import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/vue';
import Antd from 'ant-design-vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import { afterEach, it, expect, vi } from 'vitest';
import AgentDetailPage from './AgentDetailPage.vue';
import FeedbackPage from './FeedbackPage.vue';
import RunReplayPage from './RunReplayPage.vue';
import RagPolicyPage from './RagPolicyPage.vue';
import * as api from '../../features/ai-center/api';
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
async function options(path = '/') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div/>' } }],
  });
  await router.push(path);
  await router.isReady();
  return { global: { plugins: [Antd, router] } };
}
it('preserves feedback reason when paging', async () => {
  const list = vi
    .spyOn(api, 'listFeedback')
    .mockResolvedValue({ items: [], total: 25, page: 1, pageSize: 10 });
  render(FeedbackPage, await options());
  await waitFor(() => expect(list).toHaveBeenCalled());
  await fireEvent.update(screen.getByPlaceholderText('原因编码'), 'INCORRECT');
  await fireEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith(expect.stringContaining('reasonCode=INCORRECT')),
  );
  await fireEvent.click(screen.getByTitle('2'));
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.stringContaining('page=2')));
  expect(list.mock.calls.at(-1)?.[0]).toContain('reasonCode=INCORRECT');
});
it('keeps Agent versions pageable and release evidence frozen', async () => {
  vi.spyOn(api, 'getAgent').mockResolvedValue({
    definition: {
      id: 'a',
      name: '客服 Agent',
      agentKey: 'customer-service',
      agentType: 'CUSTOMER_SERVICE',
      status: 'ACTIVE',
    },
    versions: Array.from({ length: 9 }, (_, i) => ({
      id: `v${i}`,
      semanticVersion: `1.0.${i}`,
      graphKey: 'g',
      graphVersion: '1',
      status: i ? 'RELEASED' : 'DRAFT',
    })),
    evidenceBindings: [
      {
        sourceType: 'RELEASE',
        sourceId: 'frozen',
        knowledgeBaseId: 'kb',
        boundIndexReleaseId: 'old',
        currentIndexReleaseId: 'new',
        largeModelName: null,
        maxInputTokens: null,
      },
    ],
  } as never);
  const transition = vi.spyOn(api, 'transitionAgentVersion');
  render(AgentDetailPage, await options());
  expect(await screen.findByText('客服 Agent')).toBeTruthy();
  expect(screen.getByText('绑定索引落后于知识库当前发布索引')).toBeTruthy();
  expect(screen.getByRole('button', { name: '提交审核' })).toBeTruthy();
  await fireEvent.click(screen.getByTitle('2'));
  expect(await screen.findByText('1.0.8')).toBeTruthy();
  expect(screen.queryByText('1.0.0')).toBeNull();
  expect(transition).not.toHaveBeenCalled();
});
it('offers bounded evidence fields in the existing RAG form', async () => {
  vi.spyOn(api, 'listAgents').mockResolvedValue([]);
  vi.spyOn(api, 'listPolicies').mockResolvedValue({ modelPolicies: [], ragPolicies: [] });
  render(RagPolicyPage, await options('/?agentId=a'));
  expect(await screen.findByLabelText('最终父证据 TopK')).toHaveValue('8');
  expect(screen.getByLabelText('相似候选阈值')).toHaveValue('0.96');
  expect(screen.getByText(/仅筛选送入等价判断/)).toBeTruthy();
});
it('replays all four recorded candidate stages without reconstructing ranks', async () => {
  const candidates = ['vector', 'fts', 'rrf', 'rerank'].map((name, index) => ({
    chunk_id: `${name}-child`,
    parent_id: 'p',
    document_version_id: 'v',
    index_release_id: 'i',
    rank: index + 1,
    score: (index + 1) / 10,
    excerpt: `${name} 原文`,
  }));
  vi.spyOn(api, 'getRunReplay').mockResolvedValue({
    run: { id: 'r', status: 'SUCCEEDED' },
    question: { content: '问题' },
    answer: null,
    stages: [
      {
        sequenceNo: 1,
        stage: '检索',
        status: 'SUCCEEDED',
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
    citations: [],
  } as never);
  render(RunReplayPage, await options());
  for (const [index, label] of [
    '向量原始分数',
    '全文原始分数',
    'RRF 分数',
    'Rerank 分数',
  ].entries()) {
    const tab = await screen.findByRole('tab', { name: `${label} (1)` });
    await fireEvent.click(tab);
    await waitFor(() => expect(tab).toHaveAttribute('aria-selected', 'true'));
    const panel = within(screen.getByRole('tabpanel'));
    expect(await panel.findByText(candidates[index]!.chunk_id)).toBeTruthy();
    expect(panel.getByText(candidates[index]!.score.toFixed(3))).toBeTruthy();
  }
});
