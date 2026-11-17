<script setup lang="ts">
import { computed } from 'vue';
import type { parseRetrievalFacts } from '../../entities/ai-center/schemas';
import EvidenceFactsPanel from './EvidenceFactsPanel.vue';
type Facts = NonNullable<ReturnType<typeof parseRetrievalFacts>>;
const props = defineProps<{ facts: Facts }>();
const tabs = computed(
  () =>
    [
      ['向量原始分数', props.facts.vector_candidates],
      ['全文原始分数', props.facts.fts_candidates],
      ['RRF 分数', props.facts.fused_candidates],
      ['Rerank 分数', props.facts.child_hits],
    ] as const,
);
const candidates = [
  { title: '子片段', dataIndex: 'chunk_id' },
  {
    title: '阶段名次',
    dataIndex: 'rank',
    customRender: ({ text }: { text: number | null | undefined }) => text ?? '该版本未记录',
  },
  {
    title: '分数',
    dataIndex: 'score',
    customRender: ({ text }: { text: number }) => text.toFixed(3),
  },
  { title: '命中原文', dataIndex: 'excerpt' },
];
const hits = [
  { title: '子片段', dataIndex: 'chunk_id' },
  {
    title: '父片段',
    dataIndex: 'parent_id',
    customRender: ({ text }: { text: string | null }) => text ?? '旧索引',
  },
  { title: '文档版本', dataIndex: 'document_version_id' },
  { title: '索引版本', dataIndex: 'index_release_id' },
  {
    title: '重排分数',
    dataIndex: 'score',
    customRender: ({ text }: { text: number }) => text.toFixed(3),
  },
  { title: '命中原文', dataIndex: 'excerpt' },
];
</script>
<template>
  <EvidenceFactsPanel :facts="facts" /><a-descriptions v-if="facts.budget_usage" size="small"
    ><a-descriptions-item label="已使用 Token">{{
      facts.budget_usage.used_tokens
    }}</a-descriptions-item
    ><a-descriptions-item label="上下文上限">{{
      facts.budget_usage.context_token_limit
    }}</a-descriptions-item></a-descriptions
  ><a-tabs
    ><a-tab-pane v-for="[label, rows] in tabs" :key="label" :tab="`${label} (${rows.length})`"
      ><a-table
        size="small"
        :row-key="(item: any, index: number) => `${item.chunk_id}-${index}`"
        :data-source="rows"
        :columns="candidates"
        :pagination="{ pageSize: 10, hideOnSinglePage: true }"
        :scroll="{ x: 680 }" /></a-tab-pane></a-tabs
  ><a-table
    size="small"
    row-key="chunk_id"
    :data-source="facts.child_hits"
    :columns="hits"
    :pagination="{ pageSize: 10, hideOnSinglePage: true }"
    :scroll="{ x: 680 }"
  />
  <p v-for="decision in facts.assembly_decisions" :key="decision.parent_id">
    {{ decision.parent_id }}：<a-tag :color="decision.selected ? 'green' : 'orange'">{{
      decision.selected ? '已入选' : decision.reason
    }}</a-tag>
  </p>
  <section v-for="item in facts.parent_evidence" :key="item.parent_id" class="ai-section">
    <h3>
      {{ item.document_title }} · v{{ item.version_no }} · {{ item.section_path ?? '正文'
      }}<template v-if="item.page_start">
        · 第 {{ item.page_start
        }}{{
          item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ''
        }}
        页</template
      >
    </h3>
    <p class="ai-muted">命中子片段：{{ item.hit_chunk_ids.join('、') }}</p>
    <div class="ai-pre">{{ item.content }}</div>
  </section>
  <a-descriptions v-if="facts.sufficiency" size="small"
    ><a-descriptions-item label="证据判断">{{
      facts.sufficiency.sufficient ? '充分' : '不足'
    }}</a-descriptions-item
    ><a-descriptions-item label="建议模式">{{
      facts.sufficiency.recommended_mode
    }}</a-descriptions-item
    ><a-descriptions-item label="依据状态">{{
      facts.sufficiency.evidence_status ?? '旧版本未记录'
    }}</a-descriptions-item
    ><a-descriptions-item label="通用补充">{{
      facts.sufficiency.general_advice_allowed ? '允许' : '未允许'
    }}</a-descriptions-item
    ><a-descriptions-item label="允许补充范围">{{
      facts.sufficiency.general_advice_scope?.join('；') || '无'
    }}</a-descriptions-item
    ><a-descriptions-item label="公司专属未知项">{{
      facts.sufficiency.company_specific_unknowns?.join('；') || '无'
    }}</a-descriptions-item
    ><a-descriptions-item label="冲突">{{
      facts.sufficiency.conflicts.join('；') || '无'
    }}</a-descriptions-item
    ><a-descriptions-item label="未支持事实">{{
      facts.sufficiency.unsupported_claims.join('；') || '无'
    }}</a-descriptions-item></a-descriptions
  >
</template>
