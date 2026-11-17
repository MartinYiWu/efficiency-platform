import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue';
import Antd from 'ant-design-vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import { afterEach, it, expect, vi } from 'vitest';
import RagEvaluationDatasetPage from './RagEvaluationDatasetPage.vue';
import * as api from '../../features/ai-center/api';
import * as knowledgeApi from '../../features/knowledge/api';
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it('imports a parsed JSON case array with the current dataset id', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/datasets/:datasetId', component: { template: '<div/>' } }],
  });
  await router.push('/datasets/d');
  await router.isReady();
  vi.spyOn(api, 'getEvaluationDataset').mockResolvedValue({
    dataset: { name: '评测集', status: 'ACTIVE', caseCount: 0 },
    cases: [],
    runs: [],
  } as never);
  const importer = vi
    .spyOn(api, 'importEvaluationCases')
    .mockResolvedValue({ createdCount: 1, updatedCount: 0, totalCount: 1 });
  render(RagEvaluationDatasetPage, { global: { plugins: [Antd, router] } });
  await fireEvent.click(await screen.findByRole('button', { name: '批量导入' }));
  await fireEvent.update(
    screen.getByLabelText('JSON 用例'),
    '[{"caseNo":"001","question":"问题"}]',
  );
  expect(screen.getByText('已解析 1 条')).toBeTruthy();
  await fireEvent.click(screen.getByRole('button', { name: /^导\s*入$/ }));
  await waitFor(() =>
    expect(importer).toHaveBeenCalledWith('d', [{ caseNo: '001', question: '问题' }]),
  );
});
it('starts an evaluation with explicit ACTIVE agent, published RAG and index versions', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/datasets/:datasetId', component: { template: '<div/>' } },
      { path: '/ai-center/rag-evaluations/runs/:runId', component: { template: '<div/>' } },
    ],
  });
  await router.push('/datasets/d');
  await router.isReady();
  vi.spyOn(api, 'getEvaluationDataset').mockResolvedValue({
    dataset: { name: '评测集', status: 'ACTIVE', caseCount: 0, agentKey: 'customer-service' },
    cases: [],
    runs: [],
  } as never);
  vi.spyOn(api, 'listAgents').mockResolvedValue([
    { id: 'a', agentKey: 'customer-service' },
  ] as never);
  vi.spyOn(api, 'listAgentReleases').mockResolvedValue([
    { id: 'active', agentVersionId: 'agent-v', releaseStatus: 'ACTIVE', environment: 'dev' },
    { id: 'inactive', agentVersionId: 'bad-v', releaseStatus: 'RETIRED', environment: 'dev' },
  ] as never);
  vi.spyOn(api, 'listPolicies').mockResolvedValue({
    modelPolicies: [],
    ragPolicies: [
      { id: 'rag-v', policyKey: 'rag', semanticVersion: '1', status: 'PUBLISHED' },
      { id: 'draft-rag', policyKey: 'draft', semanticVersion: '2', status: 'DRAFT' },
    ],
  } as never);
  vi.spyOn(knowledgeApi, 'listKnowledgeBases').mockResolvedValue({
    items: [{ id: 'kb', name: '技术知识库' }],
    total: 1,
    page: 1,
    pageSize: 100,
  } as never);
  const indexes = vi
    .spyOn(knowledgeApi, 'listIndexReleases')
    .mockResolvedValue([{ id: 'index-v', releaseNo: 'idx-1', status: 'PUBLISHED' }] as never);
  const start = vi.spyOn(api, 'startEvaluationRun').mockResolvedValue({ id: 'result' } as never);
  render(RagEvaluationDatasetPage, { global: { plugins: [Antd, router] } });
  await fireEvent.click(await screen.findByRole('button', { name: '发起评测' }));
  for (const [label, option] of [
    ['ACTIVE Agent 版本', 'agent-v · dev'],
    ['PUBLISHED RAG 策略', 'rag · 1'],
    ['知识库 1', '技术知识库'],
    ['索引发布版本', 'idx-1 · PUBLISHED'],
  ]) {
    const input = await screen.findByLabelText(label!);
    await fireEvent.mouseDown(input.closest('.ant-select')!.querySelector('.ant-select-selector')!);
    await fireEvent.click(
      await screen.findByText(option!, { selector: '.ant-select-item-option-content' }),
    );
  }
  expect(indexes).toHaveBeenCalledWith('kb');
  await fireEvent.click(screen.getByRole('button', { name: /开\s*始/ }));
  await waitFor(() =>
    expect(start).toHaveBeenCalledWith({
      datasetId: 'd',
      agentKey: 'customer-service',
      agentVersionId: 'agent-v',
      ragPolicyVersionId: 'rag-v',
      knowledgeBindings: [{ knowledgeBaseId: 'kb', indexReleaseId: 'index-v' }],
    }),
  );
  await waitFor(() =>
    expect(router.currentRoute.value.path).toBe('/ai-center/rag-evaluations/runs/result'),
  );
});
it('drops equivalent wordings only for removed facts when editing a case', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/datasets/:datasetId', component: { template: '<div/>' } }],
  });
  await router.push('/datasets/d');
  await router.isReady();
  vi.spyOn(api, 'getEvaluationDataset').mockResolvedValue({
    dataset: {
      id: 'd',
      name: '验收集',
      agentKey: 'customer-service',
      status: 'ACTIVE',
      caseCount: 1,
    },
    cases: [
      {
        id: 'c',
        caseNo: '001',
        question: '问题',
        expectedAnswerMode: 'COMPANY_KNOWLEDGE',
        expectedFacts: ['保留', '移除'],
        expectedFactAlternatives: { 保留: ['同义'], 移除: ['旧表述'] },
        prohibitedFacts: [],
        expectedDocumentTitles: [],
        expectedDocumentVersionIds: [],
        tags: [],
        minCitationCount: 1,
        enabled: true,
      },
    ],
    runs: [],
  } as never);
  const update = vi.spyOn(api, 'updateEvaluationCase').mockResolvedValue({} as never);
  render(RagEvaluationDatasetPage, { global: { plugins: [Antd, router] } });
  await fireEvent.click(await screen.findByRole('button', { name: /编\s*辑/ }));
  await fireEvent.update(screen.getByLabelText('必须事实（每行一条）'), '保留\n新增');
  await fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      'd',
      'c',
      expect.objectContaining({
        expectedFacts: ['保留', '新增'],
        expectedFactAlternatives: { 保留: ['同义'] },
      }),
    ),
  );
});
