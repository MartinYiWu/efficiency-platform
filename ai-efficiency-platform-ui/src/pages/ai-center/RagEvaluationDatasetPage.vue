<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { FormInstance } from 'ant-design-vue';
import type {
  EvaluationDatasetDetail,
  EvaluationCase,
  AgentRelease,
  RagPolicy,
} from '../../entities/ai-center/model';
import type { KnowledgeBase, IndexRelease } from '../../entities/knowledge/model';
import {
  getEvaluationDataset,
  createEvaluationCase,
  updateEvaluationCase,
  importEvaluationCases,
  listAgents,
  listAgentReleases,
  listPolicies,
  startEvaluationRun,
} from '../../features/ai-center/api';
import { listKnowledgeBases, listIndexReleases } from '../../features/knowledge/api';
import { aiStatusLabel } from '../../features/ai-center/presentation';
import { formatAiDate } from './datePresentation';
import AiWorkspaceSection from './AiWorkspaceSection.vue';
import './ai-center.css';
const route = useRoute(),
  router = useRouter(),
  datasetId = computed(() => String(route.params.datasetId ?? '')),
  detail = ref<EvaluationDatasetDetail>(),
  editing = ref<EvaluationCase>(),
  caseOpen = ref(false),
  importOpen = ref(false),
  runOpen = ref(false),
  importText = ref('[]'),
  caseRef = ref<FormInstance>(),
  runRef = ref<FormInstance>();
const agentReleases = ref<AgentRelease[]>([]),
  ragPolicies = ref<RagPolicy[]>([]),
  knowledgeBases = ref<KnowledgeBase[]>([]),
  indexReleasesByBase = ref<Record<string, IndexRelease[]>>({});
const caseForm = reactive({
  caseNo: '',
  question: '',
  expectedAnswerMode: 'COMPANY_KNOWLEDGE',
  expectedFacts: '',
  prohibitedFacts: '',
  expectedDocumentTitles: '',
  expectedDocumentVersionIds: '',
  tags: '',
  minCitationCount: 1,
  enabled: true,
});
const runForm = reactive<{
  agentVersionId?: string;
  ragPolicyVersionId?: string;
  knowledgeBindings: { knowledgeBaseId?: string; indexReleaseId?: string }[];
}>({ knowledgeBindings: [{}] });
const lines = (value: string) =>
  value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
const importCount = computed(() => {
  try {
    const value: unknown = JSON.parse(importText.value);
    return Array.isArray(value) ? value.length : 0;
  } catch {
    return 0;
  }
});
async function load() {
  try {
    detail.value = await getEvaluationDataset(datasetId.value);
  } catch (error) {
    message.error((error as Error).message);
  }
}
watch(datasetId, load, { immediate: true });
function openCase(item?: EvaluationCase) {
  editing.value = item;
  Object.assign(caseForm, {
    caseNo: item?.caseNo ?? '',
    question: item?.question ?? '',
    expectedAnswerMode: item?.expectedAnswerMode ?? 'COMPANY_KNOWLEDGE',
    expectedFacts: item?.expectedFacts.join('\n') ?? '',
    prohibitedFacts: item?.prohibitedFacts.join('\n') ?? '',
    expectedDocumentTitles: item?.expectedDocumentTitles.join('\n') ?? '',
    expectedDocumentVersionIds: item?.expectedDocumentVersionIds.join('\n') ?? '',
    tags: item?.tags.join('\n') ?? '',
    minCitationCount: item?.minCitationCount ?? 1,
    enabled: item?.enabled ?? true,
  });
  caseOpen.value = true;
}
async function saveCase() {
  try {
    await caseRef.value?.validate();
    const expectedFacts = lines(caseForm.expectedFacts),
      request = {
        ...caseForm,
        ...(editing.value?.expectedFactAlternatives
          ? {
              expectedFactAlternatives: Object.fromEntries(
                Object.entries(editing.value.expectedFactAlternatives).filter(([fact]) =>
                  expectedFacts.includes(fact),
                ),
              ),
            }
          : {}),
        expectedFacts,
        prohibitedFacts: lines(caseForm.prohibitedFacts),
        expectedDocumentTitles: lines(caseForm.expectedDocumentTitles),
        expectedDocumentVersionIds: lines(caseForm.expectedDocumentVersionIds),
        tags: lines(caseForm.tags),
      };
    if (editing.value) await updateEvaluationCase(datasetId.value, editing.value.id, request);
    else await createEvaluationCase(datasetId.value, request);
    caseOpen.value = false;
    editing.value = undefined;
    await load();
    message.success('用例已保存');
  } catch (error) {
    if (error instanceof Error) message.error(error.message);
  }
}
async function importCases() {
  try {
    const value: unknown = JSON.parse(importText.value);
    if (!Array.isArray(value)) throw new Error('必须是 JSON 数组');
    const result = await importEvaluationCases(datasetId.value, value);
    importOpen.value = false;
    await load();
    message.success(`已新增 ${result.createdCount} 条，更新 ${result.updatedCount} 条`);
  } catch (error) {
    message.error((error as Error).message);
  }
}
async function prepareRun() {
  if (!detail.value) return;
  try {
    const [agents, releases, bases] = await Promise.all([
      listAgents(),
      listAgentReleases(detail.value.dataset.agentKey),
      listKnowledgeBases('page=1&pageSize=100'),
    ]);
    const agent = agents.find((item) => item.agentKey === detail.value!.dataset.agentKey);
    if (!agent) throw new Error('未找到数据集所属 Agent');
    const policies = await listPolicies(agent.id);
    agentReleases.value = releases.filter((item) => item.releaseStatus === 'ACTIVE');
    ragPolicies.value = policies.ragPolicies.filter((item) => item.status === 'PUBLISHED');
    knowledgeBases.value = bases.items;
    indexReleasesByBase.value = {};
    Object.assign(runForm, {
      agentVersionId: undefined,
      ragPolicyVersionId: undefined,
      knowledgeBindings: [{}],
    });
    runOpen.value = true;
  } catch (error) {
    message.error((error as Error).message);
  }
}
async function selectBase(index: number, id: string) {
  runForm.knowledgeBindings[index]!.indexReleaseId = undefined;
  if (!indexReleasesByBase.value[id])
    try {
      indexReleasesByBase.value[id] = await listIndexReleases(id);
    } catch (error) {
      message.error((error as Error).message);
    }
}
async function startRun() {
  try {
    await runRef.value?.validate();
    if (!runForm.knowledgeBindings.length) throw new Error('至少绑定一个知识库版本');
    const run = await startEvaluationRun({
      datasetId: datasetId.value,
      agentKey: detail.value!.dataset.agentKey,
      agentVersionId: runForm.agentVersionId,
      ragPolicyVersionId: runForm.ragPolicyVersionId,
      knowledgeBindings: runForm.knowledgeBindings,
    });
    runOpen.value = false;
    await router.push(`/ai-center/rag-evaluations/runs/${run.id}`);
  } catch (error) {
    if (error instanceof Error) message.error(error.message);
  }
}
const caseColumns = [
  { title: '编号', dataIndex: 'caseNo' },
  { title: '问题', dataIndex: 'question' },
  { title: '预期模式', dataIndex: 'expectedAnswerMode' },
  { title: '关键事实', key: 'facts' },
  { title: '预期来源', key: 'sources' },
  { title: '状态', key: 'enabled' },
  { title: '操作', key: 'action' },
];
const runColumns = [
  { title: '批次', dataIndex: 'id', ellipsis: true },
  { title: '状态', key: 'status' },
  { title: '通过', key: 'passed' },
  { title: '创建时间', key: 'time' },
  { title: '操作', key: 'action' },
];
const textFields = [
  ['expectedFacts', '必须事实（每行一条）', 4],
  ['prohibitedFacts', '禁止事实（每行一条）', 3],
  ['expectedDocumentTitles', '预期文档标题（每行一条）', 3],
  ['expectedDocumentVersionIds', '预期文档版本 ID（每行一条）', 3],
  ['tags', '标签（每行一条）', 2],
] as const;
</script>
<template>
  <section v-if="detail" class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <a-button type="link" @click="router.push('/ai-center/rag-evaluations')"
          >← 返回数据集</a-button
        >
        <h2>{{ detail.dataset.name }}</h2>
      </div>
      <a-space wrap
        ><a-button @click="importOpen = true">批量导入</a-button
        ><a-button @click="openCase()">新增用例</a-button
        ><a-button type="primary" @click="prepareRun">发起评测</a-button></a-space
      >
    </header>
    <div class="ui-card">
      <a-descriptions size="small" :column="{ xs: 1, sm: 2, lg: 4 }"
        ><a-descriptions-item label="状态"
          ><a-tag>{{ aiStatusLabel(detail.dataset.status) }}</a-tag></a-descriptions-item
        ><a-descriptions-item label="Agent">{{ detail.dataset.agentKey }}</a-descriptions-item
        ><a-descriptions-item label="用例数">{{ detail.dataset.caseCount }}</a-descriptions-item
        ><a-descriptions-item label="说明">{{
          detail.dataset.description ?? '—'
        }}</a-descriptions-item></a-descriptions
      ><AiWorkspaceSection title="评测用例"
        ><a-table
          row-key="id"
          :data-source="detail.cases"
          :columns="caseColumns"
          :scroll="{ x: 1000 }"
          :pagination="{ pageSize: 10 }"
          ><template #bodyCell="{ column, record }"
            ><template v-if="column.key === 'facts'">{{ record.expectedFacts.length }}</template
            ><template v-else-if="column.key === 'sources'">{{
              record.expectedDocumentTitles.join('、') || '不适用'
            }}</template
            ><a-tag
              v-else-if="column.key === 'enabled'"
              :color="record.enabled ? 'green' : 'default'"
              >{{ record.enabled ? '启用' : '停用' }}</a-tag
            ><a-button v-else-if="column.key === 'action'" type="link" @click="openCase(record)"
              >编辑</a-button
            ></template
          ></a-table
        ></AiWorkspaceSection
      ><AiWorkspaceSection title="运行记录"
        ><a-table
          row-key="id"
          :data-source="detail.runs"
          :columns="runColumns"
          :scroll="{ x: 740 }"
          :pagination="{ pageSize: 10, hideOnSinglePage: true }"
          ><template #bodyCell="{ column, record }"
            ><a-tag v-if="column.key === 'status'">{{ aiStatusLabel(record.status) }}</a-tag
            ><template v-else-if="column.key === 'passed'"
              >{{ record.passedCount }}/{{ record.totalCount }}</template
            ><template v-else-if="column.key === 'time'">{{
              formatAiDate(record.createdAt)
            }}</template
            ><a-button
              v-else-if="column.key === 'action'"
              type="link"
              @click="router.push(`/ai-center/rag-evaluations/runs/${record.id}`)"
              >查看结果</a-button
            ></template
          ></a-table
        ></AiWorkspaceSection
      >
    </div>
    <a-drawer
      v-model:open="caseOpen"
      width="min(620px, 100vw)"
      :title="editing ? '编辑用例' : '新增用例'"
      ><template #extra><a-button type="primary" @click="saveCase">保存</a-button></template
      ><a-form ref="caseRef" :model="caseForm" layout="vertical"
        ><h4>问题输入</h4>
        <a-form-item name="caseNo" label="稳定编号" :rules="[{ required: true }]"
          ><a-input v-model:value="caseForm.caseNo" :disabled="!!editing" /></a-form-item
        ><a-form-item name="question" label="真实提问" :rules="[{ required: true }]"
          ><a-textarea v-model:value="caseForm.question" :rows="3" /></a-form-item
        ><a-form-item name="expectedAnswerMode" label="预期回答模式" :rules="[{ required: true }]"
          ><a-select
            v-model:value="caseForm.expectedAnswerMode"
            :options="
              ['COMPANY_KNOWLEDGE', 'MIXED', 'GENERAL_ADVICE', 'INSUFFICIENT_EVIDENCE'].map(
                (value) => ({ value }),
              )
            "
        /></a-form-item>
        <h4>事实与来源判定</h4>
        <a-form-item
          v-for="[key, label, rows] in textFields"
          :key="key"
          :name="key"
          :label="label"
          :extra="
            key === 'expectedFacts' &&
            editing?.expectedFactAlternatives &&
            Object.keys(editing.expectedFactAlternatives).length
              ? '已有事实绑定等价表述。删除或改名事实后，原绑定会在保存时移除，不会转移到新事实。'
              : undefined
          "
          ><a-textarea v-model:value="caseForm[key]" :rows="rows"
        /></a-form-item>
        <h4>评测约束</h4>
        <a-form-item name="minCitationCount" label="最少引用数"
          ><a-input-number v-model:value="caseForm.minCitationCount" :min="0" /></a-form-item
        ><a-form-item name="enabled" label="参与评测"
          ><a-switch v-model:checked="caseForm.enabled" /></a-form-item></a-form></a-drawer
    ><a-modal v-model:open="importOpen" title="批量导入 JSON 用例" ok-text="导入" @ok="importCases"
      ><p>已解析 {{ importCount }} 条</p>
      <a-textarea v-model:value="importText" :rows="14" aria-label="JSON 用例" /></a-modal
    ><a-drawer v-model:open="runOpen" width="min(520px, 100vw)" title="发起真实评测"
      ><template #extra><a-button type="primary" @click="startRun">开始</a-button></template>
      <p class="ai-muted">批次将冻结以下版本，并在后台按用例串行调用真实 Agent。</p>
      <a-form ref="runRef" :model="runForm" layout="vertical"
        ><a-form-item name="agentVersionId" label="ACTIVE Agent 版本" :rules="[{ required: true }]"
          ><a-select
            v-model:value="runForm.agentVersionId"
            :options="
              agentReleases.map((item) => ({
                value: item.agentVersionId,
                label: `${item.agentVersionId.slice(0, 8)} · ${item.environment}`,
              }))
            " /></a-form-item
        ><a-form-item
          name="ragPolicyVersionId"
          label="PUBLISHED RAG 策略"
          :rules="[{ required: true }]"
          ><a-select
            v-model:value="runForm.ragPolicyVersionId"
            :options="
              ragPolicies.map((item) => ({
                value: item.id,
                label: `${item.policyKey} · ${item.semanticVersion}`,
              }))
            "
        /></a-form-item>
        <div v-for="(binding, index) in runForm.knowledgeBindings" :key="index" class="ai-binding">
          <a-form-item
            :name="['knowledgeBindings', index, 'knowledgeBaseId']"
            :label="`知识库 ${index + 1}`"
            :rules="[{ required: true }]"
            ><a-select
              v-model:value="binding.knowledgeBaseId"
              :options="knowledgeBases.map((item) => ({ value: item.id, label: item.name }))"
              @change="(id: unknown) => selectBase(index, String(id))" /></a-form-item
          ><a-form-item
            :name="['knowledgeBindings', index, 'indexReleaseId']"
            label="索引发布版本"
            :rules="[{ required: true }]"
            ><a-select
              v-model:value="binding.indexReleaseId"
              :disabled="!binding.knowledgeBaseId"
              :options="
                (indexReleasesByBase[binding.knowledgeBaseId ?? ''] ?? [])
                  .filter((item) => item.status === 'PUBLISHED')
                  .map((item) => ({
                    value: item.id,
                    label: `${item.releaseNo} · ${aiStatusLabel(item.status)}`,
                  }))
              " /></a-form-item
          ><a-button
            v-if="runForm.knowledgeBindings.length > 1"
            danger
            @click="runForm.knowledgeBindings.splice(index, 1)"
            >移除</a-button
          >
        </div>
        <a-button block @click="runForm.knowledgeBindings.push({})"
          >添加知识库版本</a-button
        ></a-form
      ></a-drawer
    >
  </section>
  <span v-else>正在加载评测数据集…</span>
</template>
