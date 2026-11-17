<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue';
import { message } from 'ant-design-vue';
import type { ProcessingTask } from '../../entities/knowledge/model';
import { getProcessingTask, retryProcessingTask } from './api';
const props = defineProps<{ taskId?: string; open: boolean }>();
const emit = defineEmits<{ close: [] }>();
const task = ref<ProcessingTask>();
const terminal = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED']);
let timer: ReturnType<typeof setInterval> | undefined;
let sequence = 0;
watch(
  () => [props.open, props.taskId] as const,
  ([open, id]) => {
    const current = ++sequence;
    if (timer) clearInterval(timer);
    task.value = undefined;
    if (!open || !id) return;
    const refresh = async () => {
      try {
        const next = await getProcessingTask(id);
        if (current === sequence) task.value = next;
      } catch (error) {
        if (current === sequence)
          message.error(error instanceof Error ? error.message : '加载失败');
      }
    };
    void refresh();
    timer = setInterval(() => {
      if (!task.value || !terminal.has(task.value.status)) void refresh();
    }, 3000);
  },
  { immediate: true },
);
onUnmounted(() => {
  sequence++;
  if (timer) clearInterval(timer);
});
async function retry() {
  if (!task.value) return;
  try {
    task.value = await retryProcessingTask(task.value.id);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '重试失败');
  }
}
</script>
<template>
  <a-drawer title="处理任务" :open="open" width="min(520px, 100vw)" @close="emit('close')">
    <a-space v-if="task" direction="vertical" :size="20" style="width: 100%">
      <a-progress
        :percent="task.progressPercent"
        :status="task.status === 'FAILED' ? 'exception' : undefined"
      />
      <a-descriptions :column="1" bordered>
        <a-descriptions-item label="状态"
          ><a-tag>{{ task.status }}</a-tag></a-descriptions-item
        >
        <a-descriptions-item label="阶段">{{ task.stage }}</a-descriptions-item>
        <a-descriptions-item label="执行次数">{{ task.attemptNo }}</a-descriptions-item>
        <a-descriptions-item label="错误信息">{{ task.errorMessage ?? '-' }}</a-descriptions-item>
      </a-descriptions>
      <a-button v-if="task.status === 'FAILED'" type="primary" @click="retry">重试任务</a-button>
    </a-space>
  </a-drawer>
</template>
