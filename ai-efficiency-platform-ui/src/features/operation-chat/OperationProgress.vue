<script setup lang="ts">
import type { VisibleOperationPhase } from './types';
defineProps<{ value: VisibleOperationPhase }>();
</script>
<template>
  <div role="status" aria-live="polite">
    <span>{{ value.label }}</span
    ><span v-if="typeof value.completed === 'number' && typeof value.target === 'number'"
      >（{{ value.completed }}/{{ value.target }}）</span
    >
  </div>
</template>
