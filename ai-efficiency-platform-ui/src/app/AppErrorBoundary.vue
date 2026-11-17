<script setup lang="ts">
import { onErrorCaptured, ref } from 'vue';
const hasError = ref(false);
onErrorCaptured(() => {
  hasError.value = true;
  return false;
});
</script>
<template>
  <p v-if="hasError" role="alert">页面发生异常，请刷新后重试。</p>
  <slot v-else />
</template>
