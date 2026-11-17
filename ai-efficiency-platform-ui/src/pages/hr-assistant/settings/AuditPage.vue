<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { Alert, Button, Input, Pagination } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest } from '../../../entities/hr';
import { beijing } from '../../../entities/hr/completion';
import styles from './AuditPage.module.css';
const row = z.object({
  id: z.string(),
  action: z.string(),
  actorId: z.string(),
  subjectRef: z.string(),
  departmentId: z.string(),
  occurredAt: z.string(),
});
const items = ref<z.infer<typeof row>[]>([]);
const page = ref(1);
const total = ref(0);
const query = ref('');
const error = ref('');
const busy = ref(false);
const visible = computed(() =>
  items.value.filter((r) =>
    [r.action, r.actorId, r.subjectRef].some((v) => v.includes(query.value)),
  ),
);
async function load() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const data = await hrRequest(
      `/audit-events?page=${page.value}&pageSize=20`,
      z.object({ items: z.array(row), total: z.number(), page: z.number(), pageSize: z.number() }),
    );
    items.value = data.items;
    total.value = data.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header>
      <h1>审计日志</h1>
      <p>只读操作元数据，不显示候选人正文或敏感材料。</p>
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon /><Input
      v-model:value="query"
      aria-label="筛选本页审计"
      placeholder="筛选本页操作者、操作或对象"
    /><Button :loading="busy" @click="load">刷新读取</Button>
    <p v-if="busy" role="status">正在读取审计事件…</p>
    <p v-else-if="!items.length && !error">暂无可访问的审计事件。</p>
    <div style="overflow: auto">
      <table v-if="items.length" style="width: 100%; min-width: 650px">
        <thead>
          <tr>
            <th>北京时间</th>
            <th>操作者</th>
            <th>操作</th>
            <th>对象</th>
            <th>部门</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in visible" :key="item.id">
            <td>{{ beijing(item.occurredAt) }}</td>
            <td>{{ item.actorId }}</td>
            <td>{{ item.action }}</td>
            <td>{{ item.subjectRef }}</td>
            <td>{{ item.departmentId }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <Pagination v-if="total" v-model:current="page" :total="total" :page-size="20" @change="load" />
  </div>
</template>

<style scoped>
header {
  margin-bottom: 20px;
}
header h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #10172b;
}
header p {
  color: #64748b;
  font-size: 13px;
  margin: 0;
  line-height: 1.6;
}
label {
  line-height: 1.6;
}
label:has(> .ant-input),
label:has(> .ant-input-number) {
  display: grid;
  gap: 5px;
  font-size: 13px;
  color: #475569;
}
details {
  background: #ffffffa8;
  border: 1px solid #dde4f2;
  border-radius: 8px;
  padding: 15px 18px;
  margin: 14px 0;
}
summary {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  cursor: pointer;
}
details[open] > summary {
  margin-bottom: 14px;
}
table {
  background: #fff;
  border-collapse: collapse;
  border: 1px solid #dde4f2;
}
th {
  padding: 12px 18px;
  background: #f6f8fc;
  font-weight: 500;
  color: #64748b;
  font-size: 12px;
  text-align: left;
}
td {
  padding: 15px 18px;
  border-bottom: 1px solid #edf0f5;
  vertical-align: middle;
  font-size: 13px;
}
article h2 {
  font-size: 18px;
  margin: 12px 0;
}
article p {
  line-height: 1.7;
  color: #475569;
}
.ant-btn + .ant-btn {
  margin-left: 8px;
}
@media (max-width: 700px) {
  header {
    margin-bottom: 16px;
  }
  header h1 {
    font-size: 22px;
  }
  details {
    padding: 12px;
  }
  th,
  td {
    padding: 12px;
  }
  .ant-btn + .ant-btn {
    margin-left: 4px;
  }
}
</style>
