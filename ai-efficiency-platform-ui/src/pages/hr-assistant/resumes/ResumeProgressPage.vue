<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Alert, Button, Checkbox, Input, Modal, Progress, Tag } from 'ant-design-vue';
import { batchSchema, batchItemSchema, hrRequest, hrWrite } from '../../../entities/hr';
import { z } from 'zod';
import styles from './ResumeProgressPage.module.css';
const route = useRoute();
const router = useRouter();
const batch = ref<z.infer<typeof batchSchema>>();
const error = ref('');
const loading = ref(false);
const busy = ref(false);
const cancelOpen = ref(false);
const retryItem = ref<z.infer<typeof batchItemSchema>>();
const retryFile = ref<File>();
const retryReason = ref('');
const retryConfirmed = ref(false);
function openRetry(item: z.infer<typeof batchItemSchema>) {
  retryItem.value = item;
  retryFile.value = undefined;
  retryReason.value = '';
  retryConfirmed.value = false;
}
function chooseRetry(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file && file.size > 20 * 1024 * 1024) {
    error.value = '修正材料不能超过20MiB';
    retryFile.value = undefined;
    return;
  }
  retryFile.value = file;
}
async function retry() {
  if (
    !retryItem.value?.contentHash ||
    !retryFile.value ||
    !retryReason.value.trim() ||
    !retryConfirmed.value ||
    busy.value
  )
    return;
  busy.value = true;
  error.value = '';
  try {
    const file = retryFile.value;
    const bytes = new Uint8Array(await file.arrayBuffer());
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    const hash = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('');
    if (hash === retryItem.value.contentHash)
      throw new Error('材料内容未变化，请选择修正后的新文件');
    let binary = '';
    for (let i = 0; i < bytes.length; i += 32768)
      binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    const batchId = await hrWrite(`/batch-items/${retryItem.value.id}/retry`, z.string(), {
      filename: file.name,
      contentBase64: btoa(binary),
      expectedHash: retryItem.value.contentHash,
      reason: retryReason.value.trim(),
    });
    retryItem.value = undefined;
    if (batchId !== route.params.batchId)
      await router.replace(`/ai-assistants/hr/resumes/batches/${encodeURIComponent(batchId)}`);
    else await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '修正重试失败，未重置预算';
  } finally {
    busy.value = false;
  }
}

let controller: AbortController | undefined;
let timer: ReturnType<typeof setTimeout> | undefined;
let failures = 0;
const labels: Record<string, string> = {
  PENDING: '等待处理',
  UPLOADING: '上传中',
  READY: '待开始',
  RUNNING: '正在处理',
  SUCCEEDED: '已完成',
  FAILED: '处理失败',
  CANCELLED: '已取消',
  TIMED_OUT: '已超时',
  BLOCKED: '服务阻塞',
  BLOCKED_BUDGET: '预算阻塞',
  PARSE_REVIEW: '待人工确认',
  REVIEW_REQUIRED: '待核验',
  FILTERED: '被硬条件过滤',
  SCORED: '评分完成',
};
const terminal = new Set([
  'SUCCEEDED',
  'FAILED',
  'CANCELLED',
  'TIMED_OUT',
  'BLOCKED',
  'BLOCKED_BUDGET',
]);
function refresh() {
  clearTimeout(timer);
  load();
}
async function load() {
  const id = route.params.batchId;
  if (!id) return;
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  try {
    batch.value = await hrRequest(
      `/resume-batches/${encodeURIComponent(String(id))}`,
      batchSchema,
      { signal: controller.signal },
    );
    error.value = '';
    failures = 0;
    if (!terminal.has(batch.value.status)) {
      timer = setTimeout(load, 2000);
    }
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError')) {
      error.value = e instanceof Error ? e.message : '进度读取失败';
      failures++;
      if (failures < 3) timer = setTimeout(load, [1000, 2000, 5000][failures - 1]);
    }
  } finally {
    loading.value = false;
  }
}
watch(
  () => route.params.batchId,
  () => {
    clearTimeout(timer);
    load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  clearTimeout(timer);
  controller?.abort();
});
async function cancelBatch() {
  if (!batch.value || busy.value) return;
  busy.value = true;
  try {
    batch.value = await hrWrite(`/resume-batches/${batch.value.id}/cancel`, batchSchema, {
      expectedVersion: batch.value.version,
    });
    cancelOpen.value = false;
    clearTimeout(timer);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '取消失败';
  } finally {
    busy.value = false;
  }
}
async function itemAction(id: string, action: 'cancel') {
  if (!batch.value || busy.value) return;
  busy.value = true;
  try {
    await hrWrite(`/batch-items/${id}/${action}`, batchItemSchema, {
      expectedVersion: batch.value.version,
    });
    clearTimeout(timer);
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败';
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header class="heading">
      <div>
        <h1>解析进度</h1>
        <p>批次状态来自服务端；刷新只读取进度，不重复开始或调用模型。</p>
      </div>
      <div>
        <Button @click="router.push('/ai-assistants/hr/resumes/upload')">返回上传</Button
        ><Button :loading="loading" @click="refresh">刷新进度</Button
        ><Button
          v-if="batch && !terminal.has(batch.status)"
          :disabled="busy"
          @click="cancelOpen = true"
          >取消整批</Button
        >
      </div>
    </header>
    <p v-if="!route.params.batchId">请选择已创建的上传批次，页面不会自动创建或重发任务。</p>
    <Alert v-if="error" type="error" show-icon :message="error" />
    <p v-if="loading && !batch" role="status">正在读取批次…</p>
    <template v-if="batch"
      ><section class="summary">
        <h2>{{ labels[batch.status] ?? '状态待核验' }}</h2>
        <div class="counts">
          <b>文档 {{ batch.totalCount }}</b
          ><span>完成 {{ batch.completedCount }}</span
          ><span>处理失败 {{ batch.failedCount }}</span
          ><span>待确认 {{ batch.reviewCount }}</span>
        </div>
        <Progress
          :percent="
            batch.totalCount ? Math.round((batch.completedCount / batch.totalCount) * 100) : 0
          "
        /><small>失败、预算阻塞与待确认不代表候选人不达标。</small>
      </section>
      <section class="items">
        <article v-for="item in batch.items" :key="item.id" class="item">
          <div class="item-title">
            <b>{{ item.filename }}</b
            ><Tag
              :color="
                ['FAILED', 'TIMED_OUT'].includes(item.status)
                  ? 'error'
                  : ['PARSE_REVIEW', 'BLOCKED_BUDGET', 'REVIEW_REQUIRED'].includes(item.status)
                    ? 'orange'
                    : item.status === 'SUCCEEDED'
                      ? 'green'
                      : 'blue'
              "
              >{{ labels[item.status] ?? '处理中' }}</Tag
            >
          </div>
          <p v-if="item.stage">当前阶段：{{ labels[item.stage] ?? item.stage }}</p>
          <Progress :percent="item.progress" :show-info="true" /><Alert
            v-if="item.errorCode || item.message"
            :type="item.status === 'FAILED' ? 'error' : 'warning'"
            :message="item.message ?? item.errorCode ?? ''"
          />
          <div class="actions">
            <Button
              v-if="item.candidateId && ['PARSE_REVIEW', 'REVIEW_REQUIRED'].includes(item.status)"
              type="primary"
              @click="
                router.push(`/ai-assistants/hr/resumes/candidates/${item.candidateId}/confirm`)
              "
              >核对解析结果</Button
            ><Button
              v-if="
                !terminal.has(item.status) &&
                !['PARSE_REVIEW', 'REVIEW_REQUIRED'].includes(item.status)
              "
              :disabled="busy"
              @click="itemAction(item.id, 'cancel')"
              >取消本条</Button
            ><Button
              v-if="item.status === 'FAILED'"
              :disabled="!item.contentHash || busy"
              @click="openRetry(item)"
              >修正材料后重试</Button
            >
          </div>
          <p v-if="['FAILED', 'TIMED_OUT'].includes(item.status)">
            只允许修正材料后在原批次额度内重试；原消费与截止时间不会清零。
          </p>
        </article>
        <p v-if="!batch.items.length">当前批次尚未上传文档。</p>
      </section></template
    ><Modal
      :open="!!retryItem"
      title="修正材料后重试"
      ok-text="确认原批额度内重试"
      :confirm-loading="busy"
      :ok-button-props="{ disabled: !retryFile || !retryReason.trim() || !retryConfirmed }"
      @ok="retry"
      @cancel="retryItem = undefined"
      ><p>
        仅FAILED条目可提交内容已变化的新文件，最大20MiB。仍沿用原批次预算、范围与截止；最多两次显式修正，不新建批次续额。
      </p>
      <input type="file" aria-label="修正材料文件" @change="chooseRetry" /><Input
        v-model:value="retryReason"
        aria-label="修正重试原因"
        placeholder="说明材料修正原因"
      /><Checkbox v-model:checked="retryConfirmed">确认使用原批次额度提交修正材料</Checkbox></Modal
    ><Modal
      v-model:open="cancelOpen"
      title="确认取消整批？"
      ok-text="确认取消"
      cancel-text="继续处理"
      :confirm-loading="busy"
      @ok="cancelBatch"
      ><p>将停止当前批次后续处理，已发生的调用费用不会退回，取消不会自动续费或重建任务。</p></Modal
    >
  </div>
</template>
<style scoped>
.heading {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
}
.heading h1 {
  font-size: 24px;
  margin: 0 0 6px;
}
.heading > div:last-child {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.summary {
  background: white;
  border: 1px solid #dce3ef;
  border-radius: 8px;
  padding: 20px;
}
.summary h2 {
  font-size: 20px;
}
.counts {
  display: flex;
  gap: 25px;
  flex-wrap: wrap;
}
.items {
  display: grid;
  gap: 12px;
}
.item {
  border: 1px solid #dce3ef;
  background: #fff;
  padding: 16px;
  border-radius: 8px;
}
.item-title {
  display: flex;
  justify-content: space-between;
  gap: 15px;
}
.actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 10px;
}
small {
  color: #65718a;
}
@media (max-width: 700px) {
  .heading {
    display: block;
  }
  .heading > div:last-child {
    margin-top: 15px;
  }
}
</style>
