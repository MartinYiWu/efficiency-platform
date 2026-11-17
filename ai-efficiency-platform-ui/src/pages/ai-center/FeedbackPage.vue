<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { AiFeedback } from '../../entities/ai-center/model';
import { listFeedback } from '../../features/ai-center/api';
import { formatAiDate } from './datePresentation';
import './ai-center.css';
const router = useRouter(),
  items = ref<AiFeedback[]>([]),
  rating = ref<string>(),
  reasonCode = ref(''),
  page = ref(1),
  total = ref(0),
  loading = ref(false);
const columns = [
  { title: '评价', key: 'rating' },
  { title: '原因', dataIndex: 'reasonCode' },
  { title: '补充说明', dataIndex: 'comment' },
  { title: '用户', dataIndex: 'userId' },
  { title: '时间', key: 'time' },
  { title: '操作', key: 'action' },
];
async function load(nextPage = 1) {
  const query = new URLSearchParams({ page: String(nextPage), pageSize: '10' });
  if (rating.value) query.set('rating', rating.value);
  if (reasonCode.value) query.set('reasonCode', reasonCode.value);
  loading.value = true;
  try {
    const result = await listFeedback(query.toString());
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
        <h2>用户反馈</h2>
        <p>查看内部用户对回答的当前反馈，并跳转到对应运行事实。</p>
      </div>
    </header>
    <div class="ui-card">
      <div class="ai-toolbar">
        <h3>
          反馈记录 <span>{{ total }}</span>
        </h3>
        <div class="ui-filters">
          <a-select
            v-model:value="rating"
            allow-clear
            placeholder="评价"
            :options="[
              { value: 'UP', label: '点赞' },
              { value: 'DOWN', label: '点踩' },
            ]"
          /><a-input v-model:value="reasonCode" placeholder="原因编码" /><a-button
            type="primary"
            @click="load()"
            >查询</a-button
          >
        </div>
      </div>
      <a-table
        row-key="id"
        :columns="columns"
        :data-source="items"
        :loading="loading"
        :scroll="{ x: 960 }"
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
            v-if="column.key === 'rating'"
            :color="record.rating === 'UP' ? 'success' : 'warning'"
            >{{
              record.rating === 'UP' ? '点赞' : record.rating === 'DOWN' ? '点踩' : record.rating
            }}</a-tag
          ><template v-else-if="column.key === 'time'">{{
            formatAiDate(record.updatedAt)
          }}</template
          ><a-button
            v-else-if="column.key === 'action'"
            type="link"
            @click="router.push(`/ai-center/runs/${record.runId}`)"
            >查看原 Run</a-button
          ></template
        ></a-table
      >
    </div>
  </section>
</template>
