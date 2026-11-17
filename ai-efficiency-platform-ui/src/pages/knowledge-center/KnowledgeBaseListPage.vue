<script setup lang="ts">
import { ref, reactive, watch, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { FormInstance } from 'ant-design-vue';
import { DatabaseOutlined, PlusOutlined } from '@ant-design/icons-vue';
import type { KnowledgeBase } from '../../entities/knowledge/model';
import { createKnowledgeBase, listKnowledgeBases } from '../../features/knowledge/api';
import {
  knowledgeStatusLabel,
  knowledgeTypeLabel,
  visibilityScopeLabel,
} from '../../features/knowledge/presentation';
import styles from './KnowledgeCenter.module.css';
const router = useRouter();
const items = ref<KnowledgeBase[]>([]);
const loading = ref(true);
const open = ref(false);
const keyword = ref('');
const submittedKeyword = ref('');
const typeFilter = ref('ALL');
const page = ref(1);
const total = ref(0);
const error = ref('');
const creating = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({ name: '', code: '', knowledgeType: 'COMPANY_POLICY', description: '' });
const types = [
  'COMPANY_POLICY',
  'BUSINESS_PROCESS',
  'PRODUCT_DOCUMENTATION',
  'TECHNICAL_DOCUMENTATION',
];
const filters = [
  { value: 'ALL', label: '全部资料' },
  ...types.map((value) => ({ value, label: knowledgeTypeLabel(value) })),
];
let sequence = 0;
async function load() {
  const current = ++sequence;
  loading.value = true;
  error.value = '';
  const query = new URLSearchParams({ page: String(page.value), pageSize: '10' });
  if (submittedKeyword.value) query.set('keyword', submittedKeyword.value);
  if (typeFilter.value !== 'ALL') query.set('knowledgeType', typeFilter.value);
  try {
    const result = await listKnowledgeBases(query.toString());
    if (current !== sequence) return;
    items.value = result.items;
    total.value = result.total;
  } catch (e) {
    if (current === sequence) {
      error.value = e instanceof Error ? e.message : '加载失败';
      message.error(error.value);
    }
  } finally {
    if (current === sequence) loading.value = false;
  }
}
watch([page, submittedKeyword, typeFilter], load, { immediate: true });
onUnmounted(() => {
  sequence++;
});
function search(value: string) {
  submittedKeyword.value = value.trim();
  page.value = 1;
}
function filter(value: string) {
  typeFilter.value = value;
  page.value = 1;
}
function view(id: string) {
  void router.push(`/knowledge-center/knowledge-bases/${id}`);
}
async function create() {
  try {
    await formRef.value?.validateFields();
  } catch {
    return;
  }
  creating.value = true;
  try {
    const base = await createKnowledgeBase({ ...form });
    message.success('知识库已创建');
    open.value = false;
    formRef.value?.resetFields();
    view(base.id);
  } catch (e) {
    message.error(e instanceof Error ? e.message : '创建失败');
  } finally {
    creating.value = false;
  }
}
const columns = [
  { title: '知识库名称', dataIndex: 'name', width: 235 },
  { title: '描述', dataIndex: 'description', width: 225, ellipsis: true },
  { title: '类型', dataIndex: 'knowledgeType', width: 105 },
  { title: '可见范围', dataIndex: 'visibilityScope', width: 105 },
  { title: '更新时间', dataIndex: 'updatedAt', width: 160 },
  { title: '状态', dataIndex: 'status', width: 90 },
  { title: '操作', key: 'action', width: 75 },
];
</script>
<template>
  <section :class="[styles.page, 'ui-page']">
    <header :class="[styles.header, 'ui-header']">
      <div>
        <h2>知识中心</h2>
        <p class="v1-muted">集中管理公司制度、业务流程、产品与技术文档。</p>
      </div>
      <a-button type="primary" @click="open = true"
        ><template #icon><PlusOutlined /></template>新建知识库</a-button
      >
    </header>
    <div :class="styles.catalogLayout">
      <aside :class="styles.catalogFilters" aria-label="资料分类">
        <strong>资料分类</strong
        ><button
          v-for="item in filters"
          :key="item.value"
          type="button"
          :aria-pressed="typeFilter === item.value"
          :class="[styles.filterItem, typeFilter === item.value && styles.filterActive]"
          @click="filter(item.value)"
        >
          {{ item.label }}
        </button>
      </aside>
      <div :class="styles.catalogResults">
        <div :class="styles.filters">
          <a-input-search
            v-model:value="keyword"
            :class="styles.search"
            placeholder="搜索知识库名称或描述"
            allow-clear
            @search="search"
          /><span :class="styles.resultCount">共 {{ total }} 个知识库</span>
        </div>
        <a-alert v-if="error" type="error" :message="error" show-icon
          ><template #action
            ><a-button size="small" @click="load">重试</a-button></template
          ></a-alert
        >
        <a-table
          row-key="id"
          :data-source="items"
          :columns="columns"
          :loading="loading"
          :scroll="{ x: 850 }"
          :custom-row="
            (record: KnowledgeBase) => ({
              onClick: () => view(record.id),
              class: styles.clickableRow,
            })
          "
          :pagination="{
            current: page,
            pageSize: 10,
            total,
            showSizeChanger: false,
            onChange: (value: number) => (page = value),
          }"
        >
          <template #bodyCell="{ column, record, text }">
            <span v-if="column.dataIndex === 'name'" :class="styles.baseName"
              ><span :class="styles.baseIcon"><DatabaseOutlined /></span
              ><span :title="record.name"
                ><strong>{{ text }}</strong
                ><small>{{ record.code }}</small></span
              ></span
            >
            <template v-else-if="column.dataIndex === 'knowledgeType'">{{
              knowledgeTypeLabel(text)
            }}</template>
            <template v-else-if="column.dataIndex === 'visibilityScope'">{{
              visibilityScopeLabel(text)
            }}</template>
            <template v-else-if="column.dataIndex === 'updatedAt'">{{
              text ? text.replace('T', ' ').slice(0, 16) : '—'
            }}</template>
            <a-tag
              v-else-if="column.dataIndex === 'status'"
              :color="text === 'ACTIVE' ? 'success' : 'default'"
              >{{ knowledgeStatusLabel(text) }}</a-tag
            >
            <a-button v-else-if="column.key === 'action'" type="link" @click.stop="view(record.id)"
              >查看</a-button
            >
            <template v-else>{{ text || '—' }}</template>
          </template>
        </a-table>
      </div>
    </div>
    <a-drawer title="新建知识库" :open="open" width="min(480px, 100vw)" @close="open = false">
      <template #extra
        ><a-button type="primary" :loading="creating" @click="create">创建</a-button></template
      >
      <a-form ref="formRef" :model="form" layout="vertical">
        <a-form-item name="name" label="名称" :rules="[{ required: true, message: '请输入名称' }]"
          ><a-input v-model:value="form.name"
        /></a-form-item>
        <a-form-item
          name="code"
          label="编码"
          :rules="[
            {
              required: true,
              pattern: /^[a-z0-9_-]+$/,
              message: '编码仅支持小写字母、数字、下划线和短横线',
            },
          ]"
          ><a-input v-model:value="form.code"
        /></a-form-item>
        <a-form-item name="knowledgeType" label="知识类型" :rules="[{ required: true }]"
          ><a-select
            v-model:value="form.knowledgeType"
            :options="types.map((value) => ({ value, label: knowledgeTypeLabel(value) }))"
        /></a-form-item>
        <a-form-item name="description" label="描述"
          ><a-textarea v-model:value="form.description" :rows="4"
        /></a-form-item>
      </a-form>
    </a-drawer>
  </section>
</template>
<style scoped>
h2 {
  margin: 0;
  color: var(--v1-text);
  font-size: 22px;
  font-weight: 600;
}
p {
  margin: 0;
  color: var(--v1-text-muted);
}
</style>
