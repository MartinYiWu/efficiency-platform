<script setup lang="ts">
import { computed } from 'vue';
import type { SummaryDetail } from '../../entities/memory/context';
const props = defineProps<{ summary: SummaryDetail }>();
const groups = computed(() => [
  { label: '已确认约束', entries: props.summary.confirmedConstraints },
  { label: '决定', entries: props.summary.decisions },
  { label: '已否决方案', entries: props.summary.rejectedOptions },
  { label: '待确认问题', entries: props.summary.openQuestions },
  { label: '重要引用', entries: props.summary.importantRefs },
  { label: '不确定信息', entries: props.summary.uncertainties },
]);
const states: Record<string, string> = {
  CONFIRMED: '已确认',
  REJECTED: '已否决',
  UNRESOLVED: '未确定',
  PROPOSED: '建议',
};
</script>
<template>
  <article aria-label="会话摘要内容">
    <p><strong>目标：</strong>{{ summary.goal.text }}</p>
    <p class="summary-note">摘要叙述未经核验，请结合原始依据；确认状态沿用原始记录。</p>
    <template v-for="group in groups" :key="group.label">
      <section v-if="group.entries.length">
        <h5>{{ group.label }}</h5>
        <ul>
          <li v-for="(entry, index) in group.entries" :key="index">
            <span>{{ states[entry.decisionStatus] ?? '状态未知' }} · </span>{{ entry.text
            }}<span v-if="entry.reason">（原因：{{ entry.reason }}）</span>
          </li>
        </ul>
      </section>
    </template>
  </article>
</template>
<style scoped>
.summary-note {
  color: var(--ant-color-text-secondary, #6b7280);
  font-size: 12px;
}
h5 {
  margin: 12px 0 4px;
}
ul {
  margin: 0;
  padding-left: 20px;
}
li {
  overflow-wrap: anywhere;
}
</style>
