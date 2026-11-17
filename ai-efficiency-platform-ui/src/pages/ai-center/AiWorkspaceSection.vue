<script setup lang="ts">
defineProps<{ title?: string; compact?: boolean }>();
</script>
<template>
  <section class="ai-section" :class="{ 'ai-compact': compact }">
    <h3>
      <slot name="title">{{ title }}</slot>
    </h3>
    <slot />
  </section>
</template>
