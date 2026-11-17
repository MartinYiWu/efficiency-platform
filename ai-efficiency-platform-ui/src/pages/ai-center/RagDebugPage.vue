<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { message } from 'ant-design-vue';
import type {
  AgentDefinition,
  AgentDetail,
  AgentRelease,
  RagPolicy,
  DebugView,
} from '../../entities/ai-center/model';
import {
  listAgents,
  getAgent,
  listPolicies,
  listAgentReleases,
  executeRagDebug,
} from '../../features/ai-center/api';
import { aiStatusLabel, answerModeLabel } from '../../features/ai-center/presentation';
import RetrievalEvidence from '../../features/ai-center/RetrievalEvidence.vue';
import AiWorkspaceSection from './AiWorkspaceSection.vue';
import './ai-center.css';
const agents = ref<AgentDefinition[]>([]),
  agentId = ref(''),
  detail = ref<AgentDetail>(),
  policies = ref<RagPolicy[]>([]),
  releases = ref<AgentRelease[]>([]),
  agentReleaseId = ref(''),
  versionId = ref(''),
  policyId = ref(''),
  baseId = ref(''),
  releaseId = ref(''),
  question = ref(''),
  result = ref<DebugView>(),
  loading = ref(false);
onMounted(async () => {
  try {
    agents.value = await listAgents();
  } catch (error) {
    message.error((error as Error).message);
  }
});
let generation = 0;
async function selectAgent(id: string) {
  agentId.value = id;
  versionId.value = '';
  policyId.value = '';
  agentReleaseId.value = '';
  result.value = undefined;
  detail.value = undefined;
  policies.value = [];
  releases.value = [];
  const request = ++generation;
  const agent = agents.value.find((item) => item.id === id);
  if (!agent) return;
  try {
    const [nextDetail, nextPolicies, nextReleases] = await Promise.all([
      getAgent(id),
      listPolicies(id),
      listAgentReleases(agent.agentKey),
    ]);
    if (request !== generation) return;
    detail.value = nextDetail;
    policies.value = nextPolicies.ragPolicies;
    releases.value = nextReleases;
  } catch (error) {
    message.error((error as Error).message);
  }
}
function selectRelease(id: string) {
  agentReleaseId.value = id;
  const release = releases.value.find((item) => item.id === id);
  if (release) versionId.value = release.agentVersionId;
}
async function run() {
  if (
    !agentId.value ||
    !agentReleaseId.value ||
    !versionId.value ||
    !policyId.value ||
    !baseId.value ||
    !releaseId.value ||
    !question.value.trim()
  ) {
    message.warning('请完整填写调试输入');
    return;
  }
  const agent = agents.value.find((item) => item.id === agentId.value);
  if (!agent) return;
  loading.value = true;
  try {
    result.value = await executeRagDebug({
      agentKey: agent.agentKey,
      question: question.value,
      agentReleaseId: agentReleaseId.value,
      agentVersionId: versionId.value,
      ragPolicyVersionId: policyId.value,
      knowledgeBindings: [{ knowledgeBaseId: baseId.value, indexReleaseId: releaseId.value }],
    });
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}
</script>
<template>
  <section class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <h2>RAG 调试</h2>
        <p>只展示结构化执行阶段和证据摘要，不展示隐藏思维链或完整 Prompt。</p>
      </div>
    </header>
    <div class="ai-columns">
      <a-card title="调试输入"
        ><a-form layout="vertical"
          ><a-form-item label="Agent"
            ><a-select
              :value="agentId || undefined"
              placeholder="Agent"
              :options="agents.map((item) => ({ label: item.name, value: item.id }))"
              @change="selectAgent" /></a-form-item
          ><a-form-item label="ACTIVE Release"
            ><a-select
              :value="agentReleaseId || undefined"
              placeholder="ACTIVE Release"
              :options="
                releases
                  .filter((item) => item.releaseStatus === 'ACTIVE')
                  .map((item) => ({ label: `${item.environment} · ${item.id}`, value: item.id }))
              "
              @change="selectRelease" /></a-form-item
          ><a-form-item label="Agent 版本"
            ><a-select
              v-model:value="versionId"
              placeholder="Agent 版本"
              :options="
                detail?.versions.map((item) => ({
                  label: `${item.semanticVersion} · ${item.status}`,
                  value: item.id,
                }))
              " /></a-form-item
          ><a-form-item label="RAG 策略"
            ><a-select
              v-model:value="policyId"
              placeholder="RAG 策略"
              :options="
                policies.map((item) => ({
                  label: `${item.policyKey}@${item.semanticVersion}`,
                  value: item.id,
                }))
              " /></a-form-item
          ><a-form-item label="知识库 ID"
            ><a-input v-model:value="baseId" placeholder="知识库 ID" /></a-form-item
          ><a-form-item label="索引 Release ID"
            ><a-input v-model:value="releaseId" placeholder="索引 Release ID" /></a-form-item
          ><a-form-item label="问题"
            ><a-textarea
              v-model:value="question"
              :rows="8"
              placeholder="输入真实问题" /></a-form-item
          ><a-button type="primary" :loading="loading" @click="run">执行调试</a-button></a-form
        ></a-card
      ><a-card
        ><template #title
          >执行阶段
          <a-tag
            :color="
              loading
                ? 'processing'
                : result?.status === 'FAILED'
                  ? 'error'
                  : result
                    ? 'success'
                    : 'default'
            "
            >{{ loading ? '执行中' : result ? aiStatusLabel(result.status) : '待执行' }}</a-tag
          ></template
        ><a-steps
          v-if="result"
          direction="vertical"
          :status="result.status === 'FAILED' ? 'error' : 'finish'"
          :items="
            result.stages.map((stage) => ({
              title: stage.stage_key,
              description: stage.public_summary,
              status:
                stage.status === 'FAILED'
                  ? 'error'
                  : stage.status === 'SUCCEEDED'
                    ? 'finish'
                    : 'process',
            }))
          " /><a-empty v-else description="执行后显示真实阶段" /></a-card
      ><a-card title="召回 Chunk"
        ><a-table
          v-if="result"
          row-key="chunk_id"
          size="small"
          :data-source="result.stages.flatMap((stage) => stage.evidence)"
          :pagination="{ pageSize: 8, hideOnSinglePage: true }"
          :scroll="{ x: 540 }"
          :columns="[
            { title: '章节', dataIndex: 'section_path' },
            {
              title: '分数',
              dataIndex: 'score',
              customRender: ({ text }: { text: number }) => text.toFixed(3),
            },
            { title: '摘要', dataIndex: 'excerpt' },
          ]" /><a-empty v-else description="暂无证据"
      /></a-card>
    </div>
    <div v-if="result" class="ui-card">
      <AiWorkspaceSection title="父子证据组装"
        ><RetrievalEvidence :facts="result" /></AiWorkspaceSection
      ><AiWorkspaceSection v-if="result.error_message" :title="result.error_code ?? '调试失败'">{{
        result.error_message
      }}</AiWorkspaceSection
      ><AiWorkspaceSection
        v-if="result.answer_markdown"
        :title="`回答模式：${result.answer_mode ? answerModeLabel(result.answer_mode) : '未记录'}`"
        ><div class="ai-pre">{{ result.answer_markdown }}</div></AiWorkspaceSection
      >
    </div>
  </section>
</template>
