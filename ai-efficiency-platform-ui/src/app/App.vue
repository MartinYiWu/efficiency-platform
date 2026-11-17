<script setup lang="ts">
import zhCN from 'ant-design-vue/es/locale/zh_CN';
import PlatformShell from '../widgets/platform-shell/PlatformShell.vue';
import AppErrorBoundary from './AppErrorBoundary.vue';
</script>
<template>
  <a-config-provider :locale="zhCN"
    ><AppErrorBoundary
      ><PlatformShell><router-view /></PlatformShell></AppErrorBoundary
  ></a-config-provider>
</template>
