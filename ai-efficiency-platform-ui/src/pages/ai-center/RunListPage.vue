<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { AiRun } from '../../entities/ai-center/model';
import { listRuns } from '../../features/ai-center/api';
import { aiStatusLabel, answerModeLabel } from '../../features/ai-center/presentation';
import { formatAiDate } from './datePresentation';
import './ai-center.css';
const router = useRouter();
const items = ref<AiRun[]>([]),
  agentKey = ref(''),
  status = ref<string>(),
  answerMode = ref<string>();
const page = ref(1),
  total = ref(0),
  loading = ref(false);
const columns = [
  { title: 'Run ID', dataIndex: 'id', ellipsis: true },
  { title: '状态', key: 'status' },
  { title: '回答模式', key: 'mode' },
  { title: 'Release', dataIndex: 'agentReleaseId', ellipsis: true },
  { title: '开始时间', key: 'time' },
  { title: '操作', key: 'action' },
];
async function load(nextPage = 1) {
  const query = new URLSearchParams({ page: String(nextPage), pageSize: '10' });
  if (agentKey.value) query.set('agentKey', agentKey.value);
  if (status.value) query.set('status', status.value);
  if (answerMode.value) query.set('answerMode', answerMode.value);
  loading.value = true;
  try {
    const result = await listRuns(query.toString());
    items.value = result.items;
    total.value = result.total;
    page.value = nextPage;
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}
onMounted(() => load());
</script>
<template>
  <section class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <h2>运行回放</h2>
        <p>默认查看全部 Agent 的结构化运行事实，可按 Agent、状态和回答模式过滤。</p>
      </div>
    </header>
    <div class="ui-card">
      <div class="ai-toolbar">
        <h3>
          运行记录 <span>{{ total }}</span>
        </h3>
        <div class="ui-filters">
          <a-input v-model:value="agentKey" placeholder="Agent Key" /><a-select
            v-model:value="status"
            allow-clear
            placeholder="状态"
            :options="
              ['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'].map((value) => ({
                value,
                label: aiStatusLabel(value),
              }))
            "
          /><a-select
            v-model:value="answerMode"
            allow-clear
            placeholder="回答模式"
            :options="
              ['COMPANY_KNOWLEDGE', 'MIXED', 'GENERAL_ADVICE', 'INSUFFICIENT_EVIDENCE'].map(
                (value) => ({ value, label: answerModeLabel(value) }),
              )
            "
          /><a-button type="primary" @click="load()">查询</a-button>
        </div>
      </div>
      <a-table
        row-key="id"
        :columns="columns"
        :data-source="items"
        :loading="loading"
        :scroll="{ x: 1040 }"
        :pagination="{
          current: page,
          pageSize: 10,
          total,
          hideOnSinglePage: true,
          showSizeChanger: false,
          onChange: load,
        }"
        ><template #bodyCell="{ column, record }"
          ><a-tag
            v-if="column.key === 'status'"
            :color="
              record.status === 'FAILED'
                ? 'error'
                : record.status === 'SUCCEEDED'
                  ? 'success'
                  : 'default'
            "
            >{{ aiStatusLabel(record.status) }}</a-tag
          ><template v-else-if="column.key === 'mode'">{{
            record.answerMode ? answerModeLabel(record.answerMode) : '-'
          }}</template
          ><template v-else-if="column.key === 'time'">{{
            formatAiDate(record.startedAt)
          }}</template
          ><a-button
            v-else-if="column.key === 'action'"
            type="link"
            @click="router.push(`/ai-center/runs/${record.id}`)"
            >回放</a-button
          ></template
        ></a-table
      >
    </div>
  </section>
</template>
