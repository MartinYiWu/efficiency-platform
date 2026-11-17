import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue';
import Antd from 'ant-design-vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import { afterEach, it, expect, vi } from 'vitest';
import AgentDetailPage from './AgentDetailPage.vue';
import AgentListPage from './AgentListPage.vue';
import RagDebugPage from './RagDebugPage.vue';
import RagEvaluationListPage from './RagEvaluationListPage.vue';
import RagEvaluationRunPage from './RagEvaluationRunPage.vue';
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
it('creates and reviews an Agent draft with its entered graph binding', async () => {
  vi.spyOn(api, 'getAgent').mockResolvedValue({
    definition: {
      id: 'a',
      name: '客服 Agent',
      agentKey: 'customer-service',
      agentType: 'CUSTOMER_SERVICE',
      status: 'ACTIVE',
    },
    versions: [
      { id: 'draft', semanticVersion: '1.0.0', graphKey: 'g', graphVersion: '1', status: 'DRAFT' },
    ],
  } as never);
  const create = vi.spyOn(api, 'createAgentVersion').mockResolvedValue({} as never),
    transition = vi.spyOn(api, 'transitionAgentVersion').mockResolvedValue({} as never);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/agents/:agentId', component: { template: '<div/>' } }],
  });
  await router.push('/agents/a');
  await router.isReady();
  render(AgentDetailPage, { global: { plugins: [Antd, router] } });
  await fireEvent.click(await screen.findByRole('button', { name: '提交审核' }));
  await waitFor(() => expect(transition).toHaveBeenCalledWith('draft', 'READY'));
  await fireEvent.click(screen.getByRole('button', { name: '新建版本' }));
  for (const [label, value] of [
    ['版本号', '1.0.1'],
    ['Graph Key', 'customer-service'],
    ['Graph 版本', '2'],
    ['变更说明', '新图'],
  ])
    await fireEvent.update(screen.getByLabelText(label!), value!);
  await fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }));
  await waitFor(() =>
    expect(create).toHaveBeenCalledWith('a', {
      semanticVersion: '1.0.1',
      graphKey: 'customer-service',
      graphVersion: '2',
      changeSummary: '新图',
    }),
  );
});
it('retries selected Agent details without losing the list', async () => {
  vi.spyOn(api, 'listAgents').mockResolvedValue([
    { id: 'a', name: '独立 Agent', agentKey: 'customer-service', status: 'ACTIVE' },
  ] as never);
  const get = vi
    .spyOn(api, 'getAgent')
    .mockRejectedValueOnce(new Error('加载失败'))
    .mockResolvedValue({
      definition: {
        id: 'a',
        name: '详情名称',
        description: '已恢复',
        agentKey: 'customer-service',
        agentType: 'CUSTOMER_SERVICE',
        status: 'ACTIVE',
        createdAt: '2026-10-20',
      },
      versions: [],
    } as never);
  render(AgentListPage, await options());
  expect(await screen.findByText('Agent 详情加载失败')).toBeTruthy();
  await fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  expect(await screen.findByText('已恢复')).toBeTruthy();
  expect(get).toHaveBeenCalledTimes(2);
  expect(screen.getByText('独立 Agent')).toBeTruthy();
});
it('does not send a debug request with incomplete explicit frozen versions', async () => {
  vi.spyOn(api, 'listAgents').mockResolvedValue([]);
  const execute = vi.spyOn(api, 'executeRagDebug');
  render(RagDebugPage, await options());
  await fireEvent.click(screen.getByRole('button', { name: '执行调试' }));
  expect(execute).not.toHaveBeenCalled();
  expect(await screen.findByText('请完整填写调试输入')).toBeTruthy();
});
it('creates an evaluation dataset using the current customer-service contract', async () => {
  vi.spyOn(api, 'listEvaluationDatasets').mockResolvedValue([]);
  const create = vi.spyOn(api, 'createEvaluationDataset').mockResolvedValue({} as never);
  render(RagEvaluationListPage, await options());
  await fireEvent.click(screen.getByRole('button', { name: '新建数据集' }));
  await fireEvent.update(screen.getByLabelText('名称'), '真实评测');
  await fireEvent.update(screen.getByLabelText('说明'), '测试描述');
  await fireEvent.click(screen.getByRole('button', { name: /创\s*建/ }));
  await waitFor(() =>
    expect(create).toHaveBeenCalledWith({
      name: '真实评测',
      description: '测试描述',
      agentKey: 'customer-service',
      status: 'DRAFT',
    }),
  );
});
it('shows frozen evaluation answer, citations and metric failures', async () => {
  vi.spyOn(api, 'getEvaluationRun').mockResolvedValue({
    run: {
      datasetId: 'd',
      status: 'SUCCEEDED',
      agentVersionId: 'frozen-agent',
      ragPolicyVersionId: 'frozen-rag',
      knowledgeBindings: [{ knowledgeBaseId: 'kb', indexReleaseId: 'frozen-index' }],
      metrics: null,
    },
    cases: [{ id: 'c', caseNo: '001', question: '真实问题' }],
    results: [
      {
        id: 'result',
        caseId: 'c',
        passed: false,
        executionStatus: 'SUCCEEDED',
        answerMode: 'COMPANY_KNOWLEDGE',
        latencyMs: 12,
        debugRunId: 'debug',
        metrics: { failures: ['EXPECTED_FACT_MISSING'] },
        answerMarkdown: '**真实回答**',
        citations: [
          {
            citation_no: 1,
            document_title: '冻结文档',
            version_no: 2,
            quoted_text: '准确引文',
            document_version_id: 'v2',
            index_release_id: 'frozen-index',
          },
        ],
      },
    ],
  } as never);
  render(RagEvaluationRunPage, await options());
  await fireEvent.click(await screen.findByRole('button', { name: '查看事实' }));
  expect(screen.getByText('EXPECTED_FACT_MISSING')).toBeTruthy();
  expect(screen.getByText('准确引文')).toBeTruthy();
  expect(screen.getByText('真实回答', { selector: 'strong' })).toBeTruthy();
  expect(screen.getByText('frozen-agent')).toBeTruthy();
});
