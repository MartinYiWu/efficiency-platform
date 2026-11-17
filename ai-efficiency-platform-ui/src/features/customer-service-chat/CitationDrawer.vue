<script setup lang="ts">
import type { Citation } from '../../entities/customer-service/model';
import MarkdownContent from '../../shared/ui/MarkdownContent.vue';
import styles from './CitationDrawer.module.css';
defineProps<{ citation?: Citation }>();
const emit = defineEmits<{ close: [] }>();
</script>
<template>
  <a-drawer title="引用来源" :open="!!citation" :width="640" @close="emit('close')"
    ><div
      v-if="citation"
      role="dialog"
      aria-label="引用来源"
      aria-modal="true"
      :class="styles.content"
    >
      <div :class="styles.documentLabel">来源文档</div>
      <h2>{{ citation.documentTitle }}</h2>
      <div :class="styles.meta">
        <span>版本 V{{ citation.versionNo }}</span
        ><span v-if="citation.pageNo">第 {{ citation.pageNo }} 页</span
        ><span v-if="citation.citationType === 'FULL_PARENT'">完整原文</span
        ><span v-if="citation.citationType === 'EXTRACTED_SPANS'">原文节选</span>
      </div>
      <div v-if="citation.sectionPath" :class="styles.section">{{ citation.sectionPath }}</div>
      <div :class="styles.divider" />
      <h3>引用原文</h3>
      <div :class="styles.excerpt"><MarkdownContent :content="citation.quotedText" /></div></div
  ></a-drawer>
</template>
