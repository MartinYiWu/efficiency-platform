<script setup lang="ts">
import { useRouter } from 'vue-router';
const router = useRouter();
</script>
<template>
  <a-result status="404" sub-title="请检查访问地址后重试。"
    ><template #title><h1>页面不存在</h1></template
    ><template #extra
      ><a-button type="primary" @click="router.push('/ai-assistants/hr/workbench')"
        >返回工作台</a-button
      ></template
    ></a-result
  >
</template>
