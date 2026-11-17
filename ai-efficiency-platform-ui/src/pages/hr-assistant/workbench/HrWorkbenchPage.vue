<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';
import { Alert, Button, Card } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest } from '../../../entities/hr';
import styles from './HrWorkbenchPage.module.css';
const schema = z.object({
  metrics: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      value: z.union([z.string(), z.number()]),
      comparisonText: z.string().nullable(),
    }),
  ),
  todos: z.array(
    z.object({ key: z.string(), label: z.string(), count: z.number(), path: z.string() }),
  ),
  positions: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      matched: z.number(),
      filtered: z.number(),
      reviewRequired: z.number(),
    }),
  ),
  activities: z.array(z.object({ id: z.string(), occurredAt: z.string(), label: z.string() })),
});
const data = ref<z.infer<typeof schema>>();
const loading = ref(false);
const error = ref('');
const router = useRouter();
let controller: AbortController | undefined;
async function load() {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  try {
    data.value = await hrRequest('/workbench', schema, { signal: controller.signal });
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '工作台读取失败';
  } finally {
    loading.value = false;
  }
}
onMounted(load);
onBeforeUnmount(() => controller?.abort());
function time(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header :class="styles.welcome">
      <div>
        <h1 :class="styles.pageTitle">招聘工作台</h1>
        <p :class="styles.dateText">优先处理待办，跟踪岗位进展</p>
      </div>
      <div :class="styles.welcomeActions">
        <Button type="primary" @click="router.push('/ai-assistants/hr/resumes/upload')"
          >上传简历</Button
        ><Button @click="router.push('/ai-assistants/hr/positions/new')">新建岗位</Button
        ><Button :loading="loading" @click="load">刷新</Button>
      </div>
    </header>
    <Alert v-if="error" show-icon type="error" :message="error" />
    <p v-if="loading" role="status">正在读取授权范围内的招聘进展…</p>
    <template v-if="data && !loading"
      ><section v-if="data.metrics.length" :class="styles.metricGrid" aria-label="招聘概览">
        <article
          v-for="(metric, index) in data.metrics"
          :key="metric.key"
          class="v1-metric-card"
          :class="`is-${['blue', 'green', 'purple', 'orange'][index % 4]}`"
        >
          <div>
            <span class="v1-metric-label">{{ metric.label }}</span
            ><strong class="v1-metric-value">{{ metric.value }}</strong
            ><small>{{ metric.comparisonText ?? '暂无对比数据' }}</small>
          </div>
        </article>
      </section>
      <div :class="styles.contentGrid" data-layout="balanced" data-testid="workbench-main-grid">
        <Card title="需要你处理" :class="styles.todosCard"
          ><div :class="styles.todoList">
            <article v-for="todo in data.todos" :key="todo.key" :class="styles.todoItem">
              <span :class="styles.warningDot" />
              <div :class="styles.todoCopy">
                <b>{{ todo.label }}</b
                ><span>{{ todo.count }}项待处理</span>
              </div>
              <Button
                type="link"
                :disabled="!todo.path.startsWith('/ai-assistants/hr/')"
                @click="router.push(todo.path)"
                >去处理 →</Button
              >
            </article>
            <p v-if="!data.todos.length">当前没有待办事项。</p>
          </div></Card
        ><Card title="岗位匹配进展" :class="styles.positionsCard"
          ><div :class="styles.tableScroll">
            <table :class="styles.positionTable">
              <thead>
                <tr>
                  <th>岗位</th>
                  <th>已匹配</th>
                  <th>被硬过滤</th>
                  <th>待核验</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="position in data.positions" :key="position.id">
                  <td>{{ position.name }}</td>
                  <td>{{ position.matched }}</td>
                  <td>{{ position.filtered }}</td>
                  <td>{{ position.reviewRequired }}</td>
                  <td>
                    <Button
                      type="link"
                      @click="router.push(`/ai-assistants/hr/matching?positionId=${position.id}`)"
                      >查看</Button
                    >
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="!data.positions.length">还没有岗位进展，请先配置并发布岗位。</p>
          </div></Card
        ><Card title="最近活动" :class="styles.activitiesCard"
          ><ol :class="styles.activityList">
            <li v-for="activity in data.activities" :key="activity.id">
              <time>{{ time(activity.occurredAt) }}（北京时间）</time>
              <p>{{ activity.label }}</p>
            </li>
          </ol>
          <p v-if="!data.activities.length">暂无已记录的活动。</p></Card
        >
      </div></template
    >
  </div>
</template>
