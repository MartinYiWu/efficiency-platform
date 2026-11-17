<script setup lang="ts">
import type {
  DeliveryProvenanceViewModel,
  RankedDigestViewModel,
} from '../../entities/operation-deliverable';
import SourceEvidencePanel from './SourceEvidencePanel.vue';
import styles from './OperationDelivery.module.css';
withDefaults(
  defineProps<{
    deliverable: RankedDigestViewModel;
    provenance: DeliveryProvenanceViewModel | null;
    sourcesExpanded?: boolean;
  }>(),
  { sourcesExpanded: undefined },
);
const emit = defineEmits<{ copyItem: [text: string]; sourcesExpandedChange: [value: boolean] }>();
const confidence = { high: '高可信度', medium: '中可信度', low: '低可信度' };
const statuses = {
  verified: '已核验',
  partially_verified: '部分核验',
  unverified: '待核验',
  conflicted: '存在冲突',
};
function date(value: string | null) {
  if (!value) return '时间未提供';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? '时间未提供'
    : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(parsed);
}
</script>
<template>
  <article :class="styles.deliveryDocument" :aria-labelledby="`ranked-digest-${deliverable.id}`">
    <header :class="styles.documentHeader">
      <div>
        <h2 :id="`ranked-digest-${deliverable.id}`">{{ deliverable.title }}</h2>
        <p :class="styles.documentLead">{{ deliverable.lead }}</p>
        <span>{{ deliverable.content.selection_summary }}</span>
      </div>
      <a-button @click="emit('copyItem', deliverable.copyText)">复制热点榜</a-button>
    </header>
    <ol aria-label="热点榜" :class="styles.rankedList">
      <li
        v-for="(item, index) in deliverable.content.items"
        :key="item.item_id"
        :class="styles.rankedItem"
      >
        <div :class="styles.itemHeader">
          <h3>{{ index + 1 }}. {{ item.title }}</h3>
          <div :class="styles.itemMeta">
            <span>{{ date(item.occurred_at) }}</span
            ><span>关联来源 {{ item.source_refs.length }} 条</span
            ><a-tag>{{ confidence[item.confidence] }}</a-tag
            ><a-tag>{{ statuses[item.verification_status] }}</a-tag>
          </div>
        </div>
        <p :class="styles.itemSummary">{{ item.summary }}</p>
        <section :class="styles.itemRationale" :aria-label="`${item.title}的运营价值`">
          <strong>为什么值得关注</strong>
          <p>{{ item.why_it_matters }}</p>
        </section>
        <section
          v-if="item.content_angles.length"
          :class="styles.itemAngles"
          :aria-label="`${item.title}的内容角度`"
        >
          <strong>内容角度</strong>
          <ul>
            <li v-for="angle in item.content_angles" :key="angle">{{ angle }}</li>
          </ul>
        </section>
        <div
          v-if="item.metrics.length"
          :class="styles.itemMetrics"
          :aria-label="`${item.title}的关键指标`"
        >
          <a-tag v-for="metric in item.metrics" :key="metric">{{ metric }}</a-tag>
        </div>
      </li>
    </ol>
    <SourceEvidencePanel
      :citations="deliverable.citations"
      :expanded="sourcesExpanded"
      :provenance="provenance"
      @expanded-change="emit('sourcesExpandedChange', $event)"
    />
  </article>
</template>
