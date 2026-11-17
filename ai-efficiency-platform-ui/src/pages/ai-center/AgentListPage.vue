<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { AgentDefinition, AgentDetail } from '../../entities/ai-center/model';
import { listAgents, getAgent } from '../../features/ai-center/api';
import { agentTypeLabel, aiStatusLabel } from '../../features/ai-center/presentation';
import { formatAiDate } from './datePresentation';
import './ai-center.css';
const router = useRouter(),
  agents = ref<AgentDefinition[]>([]),
  keyword = ref(''),
  selectedId = ref(''),
  detail = ref<AgentDetail>(),
  detailError = ref('');
const filtered = computed(() =>
  agents.value.filter((item) =>
    `${item.name} ${item.agentKey}`.toLowerCase().includes(keyword.value.toLowerCase()),
  ),
);
let generation = 0;
async function loadDetail() {
  const request = ++generation;
  detail.value = undefined;
  detailError.value = '';
  if (!selectedId.value) return;
  try {
    const value = await getAgent(selectedId.value);
    if (request === generation) detail.value = value;
  } catch (error) {
    if (request === generation) detailError.value = (error as Error).message;
  }
}
watch(selectedId, loadDetail);
onMounted(async () => {
  try {
    agents.value = await listAgents();
    selectedId.value = agents.value[0]?.id ?? '';
  } catch (error) {
    message.error((error as Error).message);
  }
});
const versions = [
  { title: '版本', dataIndex: 'semanticVersion' },
  {
    title: '状态',
    dataIndex: 'status',
    customRender: ({ text }: { text: string }) => aiStatusLabel(text),
  },
  { title: '更新说明', dataIndex: 'changeSummary' },
  {
    title: '创建时间',
    dataIndex: 'createdAt',
    customRender: ({ text }: { text: string }) => formatAiDate(text),
  },
];
const bindings = [
  { title: '来源类型', dataIndex: 'sourceType' },
  { title: '来源标识', dataIndex: 'sourceId' },
  {
    title: '绑定索引',
    dataIndex: 'boundIndexReleaseId',
    customRender: ({ text }: { text: string | null }) => text || '未绑定',
  },
  {
    title: '模型',
    dataIndex: 'largeModelName',
    customRender: ({ text }: { text: string | null }) => text || '未绑定',
  },
];
</script>
<template>
  <section class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <h2>Agent 管理</h2>
        <p>管理独立 Agent 的定义、版本、策略绑定与发布。</p>
      </div>
    </header>
    <div class="ai-agent-layout">
      <aside class="ui-card" aria-label="Agent 列表">
        <h3>
          Agent 列表 <span>{{ agents.length }}</span>
        </h3>
        <a-input-search
          v-model:value="keyword"
          allow-clear
          placeholder="搜索 Agent 名称或标识"
        /><button
          v-for="agent in filtered"
          :key="agent.id"
          class="ai-agent-option"
          type="button"
          :aria-pressed="selectedId === agent.id"
          @click="selectedId = agent.id"
        >
          <span
            ><strong>{{ agent.name }}</strong
            ><small>{{ agent.agentKey }}</small></span
          ><a-tag :color="agent.status === 'ACTIVE' ? 'success' : 'default'">{{
            aiStatusLabel(agent.status)
          }}</a-tag></button
        ><a-empty v-if="agents.length === 0" description="暂无 Agent" />
      </aside>
      <section class="ui-card">
        <template v-if="detail"
          ><div class="ai-toolbar">
            <div>
              <h3>{{ detail.definition.name }}</h3>
              <p>{{ detail.definition.description || '暂无描述' }}</p>
            </div>
            <a-button
              type="primary"
              @click="router.push(`/ai-center/agents/${detail.definition.id}`)"
              >管理版本</a-button
            >
          </div>
          <a-descriptions :column="{ xs: 1, sm: 2 }"
            ><a-descriptions-item label="Agent Key">{{
              detail.definition.agentKey
            }}</a-descriptions-item
            ><a-descriptions-item label="类型">{{
              agentTypeLabel(detail.definition.agentType)
            }}</a-descriptions-item
            ><a-descriptions-item label="状态">{{
              aiStatusLabel(detail.definition.status)
            }}</a-descriptions-item
            ><a-descriptions-item label="创建时间">{{
              formatAiDate(detail.definition.createdAt)
            }}</a-descriptions-item></a-descriptions
          >
          <section class="ai-section">
            <h3>版本管理</h3>
            <a-table
              row-key="id"
              :data-source="detail.versions"
              :columns="versions"
              :scroll="{ x: 620 }"
              :pagination="{ pageSize: 6, hideOnSinglePage: true }"
            />
          </section>
          <section class="ai-section">
            <h3>版本 / Release 证据绑定</h3>
            <a-table
              :row-key="
                (item: any) =>
                  `${item.sourceType}:${item.sourceId}:${item.knowledgeBaseId}:${item.boundIndexReleaseId}`
              "
              :columns="bindings"
              :data-source="detail.evidenceBindings ?? []"
              :scroll="{ x: 620 }"
              :pagination="{ pageSize: 5, hideOnSinglePage: true }"
            /></section></template
        ><a-result
          v-else-if="detailError"
          status="error"
          title="Agent 详情加载失败"
          :sub-title="detailError"
          ><template #extra><a-button @click="loadDetail">重试</a-button></template></a-result
        ><a-empty v-else :description="selectedId ? '正在加载 Agent 详情' : '请选择 Agent'" />
      </section>
    </div>
  </section>
</template>
