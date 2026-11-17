<script setup lang="ts">
import { computed } from 'vue';
export type EvidenceMode = 'FULL_ONLY' | 'EXTRACTIVE_NARRATIVE';
const props = defineProps<{ knowledgeType?: string; value: EvidenceMode }>();
const emit = defineEmits<{ 'update:value': [value: EvidenceMode] }>();
const allowed = computed(() =>
  ['PRODUCT_DOCUMENTATION', 'TECHNICAL_DOCUMENTATION'].includes(props.knowledgeType ?? ''),
);
const options = computed(() => [
  { label: '全文优先', value: 'FULL_ONLY' },
  ...(allowed.value ? [{ label: '允许叙述性原文节选', value: 'EXTRACTIVE_NARRATIVE' }] : []),
]);
</script>
<template>
  <div class="evidence-mode">
    <p>证据处理</p>
    <a-select
      aria-label="证据处理"
      :disabled="!allowed"
      :value="allowed ? value : 'FULL_ONLY'"
      :options="options"
      @change="emit('update:value', $event as EvidenceMode)"
    />
    <p class="hint">
      仅选择原文句段，不生成替代公司事实的摘要；制度、流程及受保护条款始终保留全文。模式随新版本冻结。
    </p>
  </div>
</template>
<style scoped>
.evidence-mode {
  min-width: 0;
  max-width: 440px;
}
.evidence-mode :deep(.ant-select) {
  width: 100%;
  min-width: 190px;
}
.hint {
  color: #6b7280;
  font-size: 13px;
  margin: 8px 0 0;
}
</style>
