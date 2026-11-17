import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue';
import Antd from 'ant-design-vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import { afterEach, it, expect, vi } from 'vitest';
import ModelPolicyPage from './ModelPolicyPage.vue';
import RagPolicyPage from './RagPolicyPage.vue';
import * as api from '../../features/ai-center/api';
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
async function options() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div/>' } }],
  });
  await router.push('/?agentId=a');
  await router.isReady();
  vi.spyOn(api, 'listAgents').mockResolvedValue([
    { id: 'a', name: '客服', agentKey: 'customer-service' },
  ] as never);
  vi.spyOn(api, 'listPolicies').mockResolvedValue({ modelPolicies: [], ragPolicies: [] });
  return { global: { plugins: [Antd, router] } };
}
it('saves all model generation and timeout fields bound to selected Agent', async () => {
  const save = vi.spyOn(api, 'saveModelPolicy').mockResolvedValue({} as never);
  render(ModelPolicyPage, await options());
  for (const [label, value] of [
    ['策略 Key', 'model'],
    ['语义版本', '1.0'],
    ['模型服务商', 'fake'],
    ['模型名称', 'test-model'],
  ])
    await fireEvent.update(await screen.findByLabelText(label!), value!);
  await fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      id: null,
      ownerAgentId: 'a',
      checksum: null,
      policyKey: 'model',
      semanticVersion: '1.0',
      provider: 'fake',
      modelName: 'test-model',
      temperature: 0.2,
      topP: 0.9,
      maxInputTokens: 32000,
      maxOutputTokens: 4096,
      connectTimeoutMs: 10000,
      readTimeoutMs: 120000,
      maxRetries: 1,
    }),
  );
});
it('saves all RAG recall and bounded evidence controls', async () => {
  const save = vi.spyOn(api, 'saveRagPolicy').mockResolvedValue({} as never);
  render(RagPolicyPage, await options());
  await fireEvent.update(await screen.findByLabelText('策略 Key'), 'rag');
  await fireEvent.update(screen.getByLabelText('语义版本'), '1.0');
  await fireEvent.update(screen.getByLabelText('最终父证据 TopK'), '12');
  await fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith({
      id: null,
      ownerAgentId: 'a',
      checksum: null,
      policyKey: 'rag',
      semanticVersion: '1.0',
      rewriteQueryLimit: 3,
      vectorTopK: 20,
      ftsTopK: 20,
      fusionTopK: 20,
      rerankTopK: 8,
      contextTokenLimit: 8000,
      citationLimit: 8,
      finalEvidenceTopK: 12,
      similarityCandidateThreshold: 0.96,
      similarityPairLimit: 20,
      adjacentGroupMaxParents: 3,
    }),
  );
});
