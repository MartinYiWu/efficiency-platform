<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { FormInstance } from 'ant-design-vue';
import type { EvaluationDataset } from '../../entities/ai-center/model';
import { listEvaluationDatasets, createEvaluationDataset } from '../../features/ai-center/api';
import { aiStatusLabel } from '../../features/ai-center/presentation';
import { formatAiDate } from './datePresentation';
import './ai-center.css';
const router = useRouter(),
  datasets = ref<EvaluationDataset[]>([]),
  status = ref<string>(),
  open = ref(false),
  formRef = ref<FormInstance>(),
  form = reactive({ name: '', description: '' });
const filtered = computed(() =>
  status.value ? datasets.value.filter((item) => item.status === status.value) : datasets.value,
);
async function load() {
  try {
    datasets.value = await listEvaluationDatasets();
  } catch (error) {
    message.error((error as Error).message);
  }
}
async function create() {
  try {
    await formRef.value?.validate();
    await createEvaluationDataset({ ...form, agentKey: 'customer-service', status: 'DRAFT' });
    open.value = false;
    formRef.value?.resetFields();
    await load();
    message.success('数据集已创建');
  } catch (error) {
    if (error instanceof Error) message.error(error.message);
  }
}
onMounted(load);
const columns = [
  { title: '名称', dataIndex: 'name' },
  { title: 'Agent', dataIndex: 'agentKey' },
  { title: '状态', key: 'status' },
  { title: '用例数', dataIndex: 'caseCount' },
  { title: '更新时间', key: 'time' },
  { title: '操作', key: 'action' },
];
</script>
<template>
  <section class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <h2>RAG 评测</h2>
        <p>用真实知识、真实检索和真实模型调用验证智能客服效果。</p>
      </div>
      <a-button type="primary" @click="open = true">新建数据集</a-button>
    </header>
    <div class="ui-card">
      <div class="ai-toolbar">
        <h3>
          评测数据集 <span>{{ filtered.length }}</span>
        </h3>
        <a-select
          v-model:value="status"
          allow-clear
          placeholder="数据集状态"
          style="width: 180px"
          :options="
            ['DRAFT', 'ACTIVE', 'ARCHIVED'].map((value) => ({ value, label: aiStatusLabel(value) }))
          "
        />
      </div>
      <a-table
        row-key="id"
        :data-source="filtered"
        :columns="columns"
        :pagination="{ pageSize: 10, hideOnSinglePage: true }"
        :scroll="{ x: 760 }"
        ><template #bodyCell="{ column, record }"
          ><a-tag v-if="column.key === 'status'">{{ aiStatusLabel(record.status) }}</a-tag
          ><template v-else-if="column.key === 'time'">{{
            formatAiDate(record.updatedAt)
          }}</template
          ><a-button
            v-else-if="column.key === 'action'"
            type="link"
            @click="router.push(`/ai-center/rag-evaluations/${record.id}`)"
            >查看用例</a-button
          ></template
        ></a-table
      >
    </div>
    <a-modal v-model:open="open" title="新建评测数据集" ok-text="创建" @ok="create"
      ><a-form ref="formRef" :model="form" layout="vertical"
        ><a-form-item name="name" label="名称" :rules="[{ required: true }]"
          ><a-input v-model:value="form.name" /></a-form-item
        ><a-form-item name="description" label="说明"
          ><a-textarea v-model:value="form.description" :rows="3" /></a-form-item></a-form
    ></a-modal>
  </section>
</template>
