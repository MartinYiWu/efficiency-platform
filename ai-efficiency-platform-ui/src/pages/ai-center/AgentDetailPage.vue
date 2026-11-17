<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { FormInstance } from 'ant-design-vue';
import type { AgentDetail } from '../../entities/ai-center/model';
import { getAgent, createAgentVersion, transitionAgentVersion } from '../../features/ai-center/api';
import { agentTypeLabel, aiStatusLabel } from '../../features/ai-center/presentation';
import AiWorkspaceSection from './AiWorkspaceSection.vue';
import './ai-center.css';
const route = useRoute(),
  router = useRouter(),
  detail = ref<AgentDetail>(),
  open = ref(false),
  formRef = ref<FormInstance>();
const form = reactive({ semanticVersion: '', graphKey: '', graphVersion: '', changeSummary: '' });
async function load() {
  try {
    detail.value = await getAgent(String(route.params.agentId ?? ''));
  } catch (error) {
    message.error((error as Error).message);
  }
}
async function create() {
  try {
    await formRef.value?.validate();
    await createAgentVersion(String(route.params.agentId ?? ''), { ...form });
    message.success('草稿版本已创建');
    open.value = false;
    formRef.value?.resetFields();
    await load();
  } catch (error) {
    if (error instanceof Error) message.error(error.message);
  }
}
async function transition(id: string) {
  try {
    await transitionAgentVersion(id, 'READY');
    await load();
  } catch (error) {
    message.error((error as Error).message);
  }
}
watch(() => route.params.agentId, load, { immediate: true });
const columns = [
  { title: '语义版本', dataIndex: 'semanticVersion' },
  { title: 'Graph', key: 'graph' },
  { title: '状态', key: 'status' },
  { title: '变更', dataIndex: 'changeSummary' },
  { title: '操作', key: 'action' },
];
const evidenceColumns = [
  { title: '来源', key: 'source' },
  { title: '可选大上下文模型', dataIndex: 'largeModelName' },
  { title: '输入上限 Token', dataIndex: 'maxInputTokens' },
  { title: '知识库', dataIndex: 'knowledgeBaseId' },
  { title: '绑定索引', dataIndex: 'boundIndexReleaseId' },
  { title: '知识库当前索引', dataIndex: 'currentIndexReleaseId' },
  { title: '提示', key: 'warning' },
];
</script>
<template>
  <section v-if="detail" class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <a-button type="link" @click="router.push('/ai-center/agents')">返回 Agent 列表</a-button>
        <h2>{{ detail.definition.name }}</h2>
      </div>
      <a-button type="primary" @click="open = true">新建版本</a-button>
    </header>
    <div class="ui-card">
      <p class="ai-muted">{{ detail.definition.description || '暂无描述' }}</p>
      <a-descriptions :column="{ xs: 1, sm: 2, lg: 3 }"
        ><a-descriptions-item label="Agent Key">{{
          detail.definition.agentKey
        }}</a-descriptions-item
        ><a-descriptions-item label="类型">{{
          agentTypeLabel(detail.definition.agentType)
        }}</a-descriptions-item
        ><a-descriptions-item label="状态">{{
          aiStatusLabel(detail.definition.status)
        }}</a-descriptions-item></a-descriptions
      ><AiWorkspaceSection title="版本管理"
        ><a-table
          row-key="id"
          :columns="columns"
          :data-source="detail.versions"
          :pagination="{ pageSize: 8, hideOnSinglePage: true }"
          :scroll="{ x: 780 }"
          ><template #bodyCell="{ column, record }"
            ><template v-if="column.key === 'graph'"
              >{{ record.graphKey }}@{{ record.graphVersion }}</template
            ><a-tag v-else-if="column.key === 'status'">{{ aiStatusLabel(record.status) }}</a-tag
            ><a-space v-else-if="column.key === 'action'" wrap
              ><a-button
                v-if="record.status === 'DRAFT'"
                size="small"
                @click="transition(record.id)"
                >提交审核</a-button
              ><a-button
                size="small"
                @click="router.push(`/ai-center/prompts?agentId=${detail.definition.id}`)"
                >Prompt</a-button
              ><a-button
                size="small"
                @click="router.push(`/ai-center/model-policies?agentId=${detail.definition.id}`)"
                >策略</a-button
              ></a-space
            ></template
          ></a-table
        ></AiWorkspaceSection
      ><AiWorkspaceSection title="版本 / Release 证据绑定"
        ><template v-if="detail.evidenceBindings == null">该版本未记录</template
        ><a-table
          v-else
          :row-key="
            (item: any) =>
              `${item.sourceType}:${item.sourceId}:${item.knowledgeBaseId}:${item.boundIndexReleaseId}`
          "
          :columns="evidenceColumns"
          :data-source="detail.evidenceBindings"
          :pagination="{ pageSize: 10, hideOnSinglePage: true }"
          :scroll="{ x: 720 }"
          ><template #bodyCell="{ column, record, text }"
            ><template v-if="column.key === 'source'"
              >{{ record.sourceType }} · {{ record.sourceId }}</template
            ><template v-else-if="column.key === 'warning'"
              ><a-tag
                v-if="
                  record.currentIndexReleaseId &&
                  record.boundIndexReleaseId &&
                  record.currentIndexReleaseId !== record.boundIndexReleaseId
                "
                color="warning"
                >绑定索引落后于知识库当前发布索引</a-tag
              ><template v-else>—</template></template
            ><template v-else>{{
              text ?? (column.dataIndex === 'currentIndexReleaseId' ? '未记录' : '未绑定')
            }}</template></template
          ></a-table
        >
        <p class="ai-muted">
          Release 展示冻结绑定；发布知识库新索引不会自动切换运行索引。
        </p></AiWorkspaceSection
      >
    </div>
    <a-modal
      v-model:open="open"
      title="新建 Agent 版本"
      ok-text="确定"
      cancel-text="取消"
      @ok="create"
      ><a-form ref="formRef" :model="form" layout="vertical"
        ><a-form-item name="semanticVersion" label="版本号" :rules="[{ required: true }]"
          ><a-input v-model:value="form.semanticVersion" placeholder="1.0.1" /></a-form-item
        ><a-form-item name="graphKey" label="Graph Key" :rules="[{ required: true }]"
          ><a-input v-model:value="form.graphKey" /></a-form-item
        ><a-form-item name="graphVersion" label="Graph 版本" :rules="[{ required: true }]"
          ><a-input v-model:value="form.graphVersion" /></a-form-item
        ><a-form-item name="changeSummary" label="变更说明"
          ><a-textarea v-model:value="form.changeSummary" /></a-form-item></a-form
    ></a-modal>
  </section>
  <a-empty v-else description="正在加载 Agent 详情" />
</template>
