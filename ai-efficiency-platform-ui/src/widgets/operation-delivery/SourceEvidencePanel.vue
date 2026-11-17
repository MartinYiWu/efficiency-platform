<script setup lang="ts">
import { computed, ref } from 'vue';
import type { CitationV2, DeliveryProvenanceViewModel } from '../../entities/operation-deliverable';
import styles from './OperationDelivery.module.css';
const props = withDefaults(
  defineProps<{
    citations: CitationV2[];
    provenance: DeliveryProvenanceViewModel | null;
    expanded?: boolean;
  }>(),
  { expanded: undefined },
);
const emit = defineEmits<{ expandedChange: [value: boolean] }>();
const internalExpanded = ref(false);
const isExpanded = computed(() => props.expanded ?? internalExpanded.value);
const conflicted = computed(
  () => props.citations.filter((item) => item.verification_status === 'conflicted').length,
);
const statuses = {
  verified: '已核验',
  partially_verified: '部分核验',
  unverified: '待核验',
  conflicted: '存在冲突',
};
const basis = {
  importance: '重要性',
  recency: '新近性',
  heat: '热度',
  mixed: '综合排序',
  evidence_order: '证据顺序',
  model_event_order: '模型事件顺序',
};
function safeHref(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname && !url.username && !url.password
      ? value
      : undefined;
  } catch {
    return undefined;
  }
}
function label(item: CitationV2) {
  if (item.title) return item.title;
  if (item.source) return item.source;
  try {
    return new URL(item.url).hostname;
  } catch {
    return '未命名来源';
  }
}
function date(value: string | null) {
  if (!value) return '时间未提供';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? '时间未提供'
    : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(parsed);
}
const windowLabel = computed(() =>
  !props.provenance?.collection_window_start && !props.provenance?.collection_window_end
    ? '采集时间窗未提供'
    : `${date(props.provenance.collection_window_start)} 至 ${date(props.provenance.collection_window_end)}`,
);
function change(value: string | number | (string | number)[]) {
  const expanded = (Array.isArray(value) ? value : [value]).some(
    (key) => String(key) === 'sources',
  );
  if (props.expanded === undefined) internalExpanded.value = expanded;
  emit('expandedChange', expanded);
}
</script>
<template>
  <section :class="styles.sourcePanel" aria-label="来源与采集依据">
    <a-collapse :active-key="isExpanded ? ['sources'] : []" @change="change"
      ><a-collapse-panel key="sources" :header="`来源与采集依据（${citations.length} 条）`"
        ><div :class="styles.sourcePanelContent">
          <dl :class="styles.provenanceList">
            <div>
              <dt>采集时间窗</dt>
              <dd>{{ windowLabel }}</dd>
            </div>
            <div>
              <dt>排序口径</dt>
              <dd>{{ provenance?.ranking_basis ? basis[provenance.ranking_basis] : '未提供' }}</dd>
            </div>
            <template v-if="provenance"
              ><div>
                <dt>候选</dt>
                <dd>候选 {{ provenance.candidate_count }} 条</dd>
              </div>
              <div>
                <dt>合并</dt>
                <dd>合并 {{ provenance.merged_event_count }} 条</dd>
              </div>
              <div>
                <dt>保留</dt>
                <dd>保留 {{ provenance.retained_count }} 条</dd>
              </div>
              <div>
                <dt>淘汰</dt>
                <dd>淘汰 {{ provenance.eliminated_count }} 条</dd>
              </div></template
            >
            <div>
              <dt>核验</dt>
              <dd>
                {{
                  provenance
                    ? `已核验 ${provenance.verified_source_count} 条，冲突 ${conflicted} 条`
                    : '核验统计未提供'
                }}
              </dd>
            </div>
          </dl>
          <ul :class="styles.sourceList">
            <li
              v-for="citation in citations"
              :key="citation.citation_id"
              :class="styles.sourceItem"
            >
              <div>
                <a
                  v-if="safeHref(citation.url)"
                  :href="safeHref(citation.url)"
                  target="_blank"
                  rel="noopener noreferrer"
                  >{{ label(citation) }}</a
                ><span v-else>{{ label(citation) }}</span
                ><span v-if="citation.source && citation.source !== label(citation)" class="muted">
                  · {{ citation.source }}</span
                >
              </div>
              <div :class="styles.sourceMeta">
                <span class="muted">发布于 {{ date(citation.published_at) }}</span
                ><a-tag>{{ statuses[citation.verification_status] }}</a-tag>
              </div>
            </li>
          </ul>
        </div></a-collapse-panel
      ></a-collapse
    >
  </section>
</template>
<style scoped>
.muted {
  color: #667085;
}
</style>
