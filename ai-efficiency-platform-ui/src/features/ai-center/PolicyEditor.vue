<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { message } from 'ant-design-vue';
import type { FormInstance } from 'ant-design-vue';
import type { AgentDefinition, ModelPolicy, RagPolicy } from '../../entities/ai-center/model';
import { listAgents, listPolicies, saveModelPolicy, saveRagPolicy } from './api';
import { aiStatusLabel } from './presentation';
import '../../pages/ai-center/ai-center.css';
const props = defineProps<{ rag?: boolean }>(),
  route = useRoute(),
  agents = ref<AgentDefinition[]>([]),
  agentId = ref(String(route.query.agentId ?? '')),
  items = ref<(ModelPolicy | RagPolicy)[]>([]),
  formRef = ref<FormInstance>();
const modelDefaults = {
  temperature: 0.2,
  topP: 0.9,
  maxInputTokens: 32000,
  maxOutputTokens: 4096,
  connectTimeoutMs: 10000,
  readTimeoutMs: 120000,
  maxRetries: 1,
};
const ragDefaults = {
  rewriteQueryLimit: 3,
  vectorTopK: 20,
  ftsTopK: 20,
  fusionTopK: 20,
  rerankTopK: 8,
  contextTokenLimit: 8000,
  citationLimit: 8,
  finalEvidenceTopK: 8,
  similarityCandidateThreshold: 0.96,
  similarityPairLimit: 20,
  adjacentGroupMaxParents: 3,
};
const form = reactive<Record<string, string | number>>({
  policyKey: '',
  semanticVersion: '',
  ...(props.rag ? ragDefaults : { provider: '', modelName: '', ...modelDefaults }),
});
const numericFields = props.rag
  ? [
      ['rewriteQueryLimit', '查询改写数量'],
      ['vectorTopK', '向量召回 TopK'],
      ['ftsTopK', '全文召回 TopK'],
      ['fusionTopK', '融合结果 TopK'],
      ['rerankTopK', '重排结果 TopK'],
      ['contextTokenLimit', '上下文 Token 上限'],
      ['citationLimit', '引用数量上限'],
    ]
  : [
      ['temperature', '采样温度'],
      ['topP', 'Top P'],
      ['maxInputTokens', '最大输入 Token'],
      ['maxOutputTokens', '最大输出 Token'],
      ['connectTimeoutMs', '连接超时（毫秒）'],
      ['readTimeoutMs', '响应超时（毫秒）'],
      ['maxRetries', '最大重试次数'],
    ];
const evidenceFields = [
  {
    name: 'finalEvidenceTopK',
    label: '最终父证据 TopK',
    min: 1,
    max: 20,
    step: 1,
    help: '冲突核验与预算组装的独立父证据数量，相邻成员分别计数。',
  },
  {
    name: 'similarityCandidateThreshold',
    label: '相似候选阈值',
    min: 0.85,
    max: 1,
    step: 0.01,
    help: '仅筛选送入等价判断的候选，不直接决定合并。',
  },
  {
    name: 'similarityPairLimit',
    label: '相似候选对上限',
    min: 1,
    max: 50,
    step: 1,
    help: '每次运行最多核验的相似候选对数。',
  },
  {
    name: 'adjacentGroupMaxParents',
    label: '相邻组父片段上限',
    min: 1,
    max: 5,
    step: 1,
    help: '同版同路径且连续命中的父片段组大小。',
  },
];
const columns = [
  { title: '策略', dataIndex: 'policyKey' },
  { title: '版本', dataIndex: 'semanticVersion' },
  ...(props.rag
    ? [
        { title: '召回/重排', key: 'recall' },
        { title: '最终父证据 TopK', dataIndex: 'finalEvidenceTopK' },
        { title: '相似候选阈值', dataIndex: 'similarityCandidateThreshold' },
        { title: '候选对 / 相邻组上限', key: 'limits' },
      ]
    : [{ title: '模型', key: 'model' }]),
  { title: '状态', key: 'status' },
];
async function load() {
  if (!agentId.value) return;
  try {
    const value = await listPolicies(agentId.value);
    items.value = props.rag ? value.ragPolicies : value.modelPolicies;
  } catch (error) {
    message.error((error as Error).message);
  }
}
watch(agentId, load);
onMounted(async () => {
  try {
    agents.value = await listAgents();
    if (!agentId.value) agentId.value = agents.value[0]?.id ?? '';
    else await load();
  } catch (error) {
    message.error((error as Error).message);
  }
});
async function save() {
  try {
    await formRef.value?.validate();
    await (props.rag ? saveRagPolicy : saveModelPolicy)({
      id: null,
      ownerAgentId: agentId.value,
      ...form,
      checksum: null,
    });
    message.success(props.rag ? 'RAG 策略草稿已创建' : '模型策略草稿已创建');
    formRef.value?.resetFields();
    await load();
  } catch (error) {
    if (error instanceof Error) message.error(error.message);
  }
}
</script>
<template>
  <section class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <h2>{{ rag ? 'RAG 策略' : '模型策略' }}</h2>
        <p>
          {{
            rag
              ? '配置查询改写、混合召回、重排、上下文与引用上限。'
              : '策略严格归属于所选 Agent，创建后不可改变归属。'
          }}
        </p>
      </div>
    </header>
    <a-select
      v-model:value="agentId"
      placeholder="先选择所属 Agent"
      style="width: min(320px, 100%)"
      :options="
        agents.map((item) => ({ value: item.id, label: `${item.name} (${item.agentKey})` }))
      "
    />
    <div v-if="agentId" class="ai-grid">
      <a-card title="已有策略"
        ><a-table
          row-key="id"
          :data-source="items"
          :columns="columns"
          :pagination="false"
          :scroll="{ x: rag ? 840 : 500 }"
          ><template #bodyCell="{ column, record, text }"
            ><a-tag v-if="column.key === 'status'">{{ aiStatusLabel(record.status) }}</a-tag
            ><template v-else-if="column.key === 'model'"
              >{{ record.provider }}/{{ record.modelName }}</template
            ><template v-else-if="column.key === 'recall'"
              >向量 {{ record.vectorTopK }} / 全文 {{ record.ftsTopK }} / RRF
              {{ record.fusionTopK }} / Rerank {{ record.rerankTopK }}</template
            ><template v-else-if="column.key === 'limits'"
              >{{ record.similarityPairLimit ?? '未记录' }} /
              {{ record.adjacentGroupMaxParents ?? '未记录' }}</template
            ><template v-else>{{ text ?? '该版本未记录' }}</template></template
          ></a-table
        ></a-card
      ><a-card title="新建策略草稿"
        ><a-form ref="formRef" :model="form" layout="vertical"
          ><h4>基本信息</h4>
          <div class="ai-form-grid">
            <a-form-item name="policyKey" label="策略 Key" :rules="[{ required: true }]"
              ><a-input v-model:value="form.policyKey" /></a-form-item
            ><a-form-item name="semanticVersion" label="语义版本" :rules="[{ required: true }]"
              ><a-input v-model:value="form.semanticVersion" /></a-form-item
            ><template v-if="!rag"
              ><a-form-item name="provider" label="模型服务商" :rules="[{ required: true }]"
                ><a-input v-model:value="form.provider" /></a-form-item
              ><a-form-item name="modelName" label="模型名称" :rules="[{ required: true }]"
                ><a-input v-model:value="form.modelName" /></a-form-item
            ></template>
          </div>
          <h4>{{ rag ? '召回、重排与上下文' : '生成参数与超时' }}</h4>
          <div class="ai-form-grid">
            <a-form-item
              v-for="[name, label] in numericFields"
              :key="name"
              :name="name"
              :label="label"
              :rules="[{ required: true }]"
              ><a-input-number v-model:value="form[name!]" :min="rag ? 1 : undefined"
            /></a-form-item>
          </div>
          <template v-if="rag"
            ><h4>证据处理</h4>
            <div class="ai-form-grid">
              <a-form-item
                v-for="field in evidenceFields"
                :key="field.name"
                :name="field.name"
                :label="field.label"
                :extra="field.help"
                :rules="[{ required: true }, { type: 'number', min: field.min, max: field.max }]"
                ><a-input-number
                  v-model:value="form[field.name]"
                  :min="field.min"
                  :max="field.max"
                  :step="field.step"
                  :precision="field.step === 1 ? 0 : 2"
              /></a-form-item></div></template
          ><a-button type="primary" @click="save">保存草稿</a-button></a-form
        ></a-card
      >
    </div>
  </section>
</template>
