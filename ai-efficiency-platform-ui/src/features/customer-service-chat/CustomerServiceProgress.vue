<script setup lang="ts">
import { computed } from 'vue';
import type { PublicProgress } from '../../entities/customer-service/model';
import styles from '../../pages/customer-service/CustomerServiceChatPage.module.css';
const props = defineProps<{ steps: PublicProgress[]; status: string; pending?: boolean }>();
const current = computed(() => [
  ...new Map(props.steps.map((step) => [step.stage, step])).values(),
]);
const finished = computed(() =>
  ['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(props.status),
);
const outcome = computed(() =>
  ['FAILED', 'TIMED_OUT'].includes(props.status)
    ? '本次回答未完成，请重试'
    : props.status === 'CANCELLED'
      ? '已停止生成'
      : null,
);
</script>
<template>
  <div v-if="pending && !steps.length" :class="styles.progressPending">请求提交中…</div>
  <details v-if="steps.length" :class="styles.progress" :open="!finished">
    <summary>处理过程</summary>
    <ol>
      <li v-for="step in current" :key="step.stage">{{ step.summary }}</li>
    </ol>
  </details>
  <div v-if="outcome" :class="styles.progressOutcome">{{ outcome }}</div>
</template>
