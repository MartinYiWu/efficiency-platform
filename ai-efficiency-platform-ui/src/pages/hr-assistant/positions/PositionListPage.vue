<script setup lang="ts">
import { onBeforeUnmount, ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { Alert, Button, Input, Select, Table, Tag } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest } from '../../../entities/hr';
import styles from './PositionListPage.module.css';
const router = useRouter();
const positionSchema = z.object({
  id: z.string(),
  name: z.string(),
  family: z.string(),
  departmentId: z.string(),
  level: z.string().nullable(),
  code: z.string(),
  status: z.enum(['DRAFT', 'ACTIVE', 'DISABLED']),
  configVersion: z.string().nullable(),
  contextVersion: z.string(),
  createdAt: z.string(),
  version: z.number(),
});
const schema = z.object({
  items: z.array(positionSchema),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
});
const rows = ref<z.infer<typeof positionSchema>[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(false);
const error = ref('');
const keyword = ref('');
const family = ref<string>();
const status = ref<string>();
const families: Record<string, string> = {
  TECHNOLOGY: '技术研发',
  PRODUCT: '产品',
  DESIGN: '设计',
  OPERATIONS: '运营',
  MARKETING: '市场',
  SALES: '销售',
  SUPPORT: '职能支持',
  MANAGEMENT: '管理',
  GRADUATE: '应届培养',
};
const statuses: Record<string, string> = {
  DRAFT: '配置待完善',
  ACTIVE: '启用中',
  DISABLED: '已停用',
};
let controller: AbortController | undefined;
async function load(next = 1) {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  page.value = next;
  const query = new URLSearchParams({ page: String(next), pageSize: '20' });
  if (keyword.value) query.set('keyword', keyword.value);
  if (family.value) query.set('family', family.value);
  if (status.value) query.set('status', status.value);
  try {
    const data = await hrRequest(`/positions?${query}`, schema, { signal: controller.signal });
    rows.value = data.items;
    total.value = data.total;
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '读取岗位失败';
  } finally {
    loading.value = false;
  }
}
onMounted(() => load());
onBeforeUnmount(() => controller?.abort());
const columns = [
  { title: '岗位名称 / 编码', key: 'name', dataIndex: 'name' },
  { title: '岗位族', key: 'family', dataIndex: 'family' },
  { title: '部门', key: 'departmentId', dataIndex: 'departmentId' },
  { title: '职级', key: 'level', dataIndex: 'level' },
  { title: '配置版本', key: 'configVersion', dataIndex: 'configVersion' },
  { title: '状态', key: 'status', dataIndex: 'status' },
  { title: '操作', key: 'actions' },
];
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header :class="styles.heading">
      <div>
        <h1>岗位管理</h1>
        <p>配置岗位要求、评分规则与不可变版本，管理实际发布状态。</p>
      </div>
      <div :class="styles.headingActions">
        <Button @click="router.push('/ai-assistants/hr/positions/templates')">岗位模板库</Button
        ><Button type="primary" @click="router.push('/ai-assistants/hr/positions/new')"
          >＋ 新建岗位</Button
        >
      </div>
    </header>
    <Alert v-if="error" show-icon type="error" :message="error" /><Button
      v-if="error"
      @click="load(page)"
      >重试读取</Button
    >
    <form :class="styles.filterPanel" @submit.prevent="load()">
      <Input
        v-model:value="keyword"
        placeholder="搜索岗位名称或编码"
        aria-label="岗位名称或编码"
      /><Select
        v-model:value="family"
        placeholder="全部岗位族"
        allow-clear
        :options="Object.entries(families).map(([value, label]) => ({ value, label }))"
        style="min-width: 140px"
      /><Select
        v-model:value="status"
        placeholder="全部状态"
        allow-clear
        :options="Object.entries(statuses).map(([value, label]) => ({ value, label }))"
        style="min-width: 140px"
      /><Button html-type="submit" type="primary" :loading="loading">查询</Button
      ><Button
        @click="
          keyword = '';
          family = undefined;
          status = undefined;
          load();
        "
        >重置</Button
      >
    </form>
    <div style="min-width: 0; overflow-x: auto">
      <Table
        :columns="columns"
        :data-source="rows"
        row-key="id"
        :loading="loading"
        :scroll="{ x: 850 }"
        :pagination="{
          current: page,
          pageSize: 20,
          total,
          showTotal: (n: number) => `共 ${n} 条`,
          onChange: (next: number) => load(next),
        }"
        ><template #emptyText
          ><span>{{
            error ? '读取未完成，请重试。' : '暂无岗位，请新建岗位并完成规则配置。'
          }}</span></template
        ><template #bodyCell="{ column, record }"
          ><template v-if="column.key === 'name'"
            ><Button type="link" @click="router.push(`/ai-assistants/hr/positions/${record.id}`)">{{
              record.name
            }}</Button
            ><small style="display: block">{{ record.code }}</small></template
          ><template v-else-if="column.key === 'family'">{{
            families[record.family] ?? '未记录'
          }}</template
          ><template v-else-if="column.key === 'status'"
            ><Tag
              :color="
                record.status === 'ACTIVE'
                  ? 'green'
                  : record.status === 'DRAFT'
                    ? 'orange'
                    : 'default'
              "
              >{{ statuses[record.status] }}</Tag
            ></template
          ><template v-else-if="column.key === 'configVersion'">{{
            record.configVersion ?? '尚未发布'
          }}</template
          ><template v-else-if="column.key === 'level'">{{ record.level ?? '未记录' }}</template
          ><template v-else-if="column.key === 'actions'"
            ><Button type="link" @click="router.push(`/ai-assistants/hr/positions/${record.id}`)"
              >查看岗位</Button
            ><Button
              v-if="record.status === 'DRAFT'"
              type="link"
              @click="router.push(`/ai-assistants/hr/positions/new?positionId=${record.id}`)"
              >继续配置</Button
            ></template
          ></template
        ></Table
      >
    </div>
  </div>
</template>
