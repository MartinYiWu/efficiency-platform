<script setup lang="ts">
import type { AnswerMode, Citation } from '../../entities/customer-service/model';
import MarkdownContent from '../../shared/ui/MarkdownContent.vue';
import styles from '../../pages/customer-service/CustomerServiceChatPage.module.css';
defineProps<{
  content: string;
  mode: AnswerMode | null;
  citations: Citation[];
  streaming: boolean;
}>();
const emit = defineEmits<{ citation: [value: Citation] }>();
const labels: Record<AnswerMode, { title: string; color: string }> = {
  COMPANY_KNOWLEDGE: { title: '依据公司知识', color: 'blue' },
  MIXED: { title: '公司知识 + 通用建议', color: 'purple' },
  GENERAL_ADVICE: { title: '通用建议（非公司制度）', color: 'orange' },
  CLARIFY: { title: '需要补充信息', color: 'gold' },
  INSUFFICIENT_EVIDENCE: { title: '现有资料不足', color: 'default' },
};
</script>
<template>
  <div :class="styles.answer">
    <a-tag v-if="mode" :color="labels[mode].color" :class="styles.answerMode">{{
      labels[mode].title
    }}</a-tag>
    <div :class="styles.answerBody">
      <MarkdownContent :content="content || (streaming ? '正在生成回答…' : '')" />
    </div>
    <div v-if="citations.length" :class="styles.sources">
      <div :class="styles.sourcesLabel">参考来源 · {{ citations.length }}</div>
      <div :class="styles.sourceItems">
        <a-button
          v-for="citation in citations"
          :key="citation.id"
          size="small"
          :class="styles.sourceButton"
          @click="emit('citation', citation)"
          >[{{ citation.citationNo }}] {{ citation.documentTitle
          }}{{ citation.citationType === 'EXTRACTED_SPANS' ? ' · 原文节选' : '' }}</a-button
        >
      </div>
    </div>
  </div>
</template>
