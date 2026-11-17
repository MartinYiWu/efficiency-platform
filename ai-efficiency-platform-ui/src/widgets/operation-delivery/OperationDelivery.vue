<script setup lang="ts">
import { computed, ref } from 'vue';
import { mapDeliverableSet, type DeliverableSetDto } from '../../entities/operation-deliverable';
import { OperationNextActions } from '../../features/operation-next-action';
import { OperationArtifactActions } from '../../features/operation-artifact';
import type { OperationArtifactSummary } from '../../features/operation-chat/types';
import MarkdownContent from '../../shared/ui/MarkdownContent.vue';
import PlatformContentView from './PlatformContentView.vue';
import RankedDigestView from './RankedDigestView.vue';
import StructuredOperationView from './StructuredOperationView.vue';
import styles from './OperationDelivery.module.css';
const props = withDefaults(
  defineProps<{
    value: DeliverableSetDto;
    artifacts?: OperationArtifactSummary[];
    baseUrl?: string;
  }>(),
  { artifacts: () => [], baseUrl: '' },
);
const emit = defineEmits<{ submitNextAction: [message: string] }>();
const delivery = computed(() => mapDeliverableSet(props.value));
const sourcesExpanded = ref(false);
const copyFeedback = ref<'success' | 'error' | null>(null);
async function copy(text: string) {
  copyFeedback.value = null;
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
    await navigator.clipboard.writeText(text);
    copyFeedback.value = 'success';
  } catch {
    copyFeedback.value = 'error';
  }
}
function artifact(kind: string, platform: string) {
  return [...props.artifacts]
    .filter((item) => item.artifactType === kind && item.platform === platform)
    .sort((a, b) => b.version - a.version)[0];
}
</script>
<template>
  <section aria-label="运营交付" :class="styles.deliverySet">
    <p :class="styles.deliverySummary">
      {{ delivery.kind === 'legacy' ? delivery.summary : delivery.summary.message }}
    </p>
    <a-alert
      v-if="delivery.degraded"
      message="部分内容已降级，请确认后使用。"
      show-icon
      type="warning"
    />
    <template v-if="delivery.kind === 'legacy'"
      ><article
        v-for="item in delivery.deliverables"
        :key="`${item.platform}-${item.title}`"
        :aria-labelledby="`legacy-delivery-${item.platform}-${item.title}`"
        :class="styles.legacyDelivery"
      >
        <h2 :id="`legacy-delivery-${item.platform}-${item.title}`">{{ item.title }}</h2>
        <span>平台：{{ item.platform }}</span>
        <section aria-label="正文" :class="styles.legacyBody">
          <MarkdownContent :content="item.body" />
        </section>
        <p v-if="item.hashtags.length">标签：{{ item.hashtags.join(' ') }}</p>
        <p v-for="note in item.format_notes" :key="note">格式说明：{{ note }}</p>
        <a-collapse v-if="item.citations.length" :class="styles.legacySources"
          ><a-collapse-panel key="sources" :header="`来源（${item.citations.length} 条）`"
            ><ul :class="styles.sourceList">
              <li v-for="citation in item.citations" :key="citation.url" :class="styles.sourceItem">
                <a
                  v-if="citation.href"
                  :href="citation.href"
                  rel="noopener noreferrer"
                  target="_blank"
                  >来源：{{ citation.title ?? citation.source ?? citation.url }}</a
                ><span v-else>来源：{{ citation.title ?? citation.source ?? citation.url }}</span>
              </li>
            </ul></a-collapse-panel
          ></a-collapse
        ><a-alert
          v-for="warning in item.warnings"
          :key="warning"
          :message="warning"
          show-icon
          type="warning"
        /></article
    ></template>
    <template v-else
      ><a-alert
        v-for="warning in delivery.warnings"
        :key="warning.code"
        :message="warning.message"
        show-icon
        type="warning" />
      <template v-if="delivery.kind === 'v3'"
        ><section
          v-for="item in delivery.deliverables"
          :key="item.deliverable_id"
          :class="styles.deliveryItem"
        >
          <article
            :aria-labelledby="`operation-v3-${item.deliverable_id}`"
            :class="styles.deliveryDocument"
          >
            <h2 :id="`operation-v3-${item.deliverable_id}`">{{ item.title }}</h2>
            <p>场景：{{ item.scenario }}{{ item.platform ? ` · 平台：${item.platform}` : '' }}</p>
            <a-button @click="copy(item.copy_text)">复制结果</a-button>
            <section aria-label="交付正文" :class="styles.legacyBody">
              <MarkdownContent :content="item.copy_text" />
            </section>
          </article>
          <a-alert
            v-for="warning in item.warnings"
            :key="warning.code"
            :message="warning.message"
            show-icon
            type="warning"
          /><OperationArtifactActions
            v-if="artifact(item.content.kind, item.platform ?? 'generic')"
            :artifact="artifact(item.content.kind, item.platform ?? 'generic')!"
            :base-url="baseUrl"
          /></section
      ></template>
      <template v-else
        ><section v-for="item in delivery.deliverables" :key="item.id" :class="styles.deliveryItem">
          <RankedDigestView
            v-if="item.kind === 'ranked_digest'"
            :deliverable="item"
            :provenance="delivery.provenance"
            :sources-expanded="sourcesExpanded"
            @copy-item="copy"
            @sources-expanded-change="sourcesExpanded = $event"
          /><PlatformContentView
            v-else-if="item.kind === 'platform_content'"
            :deliverable="item"
            :provenance="delivery.provenance"
            :sources-expanded="sourcesExpanded"
            @copy-item="copy"
            @sources-expanded-change="sourcesExpanded = $event"
          /><StructuredOperationView v-else :deliverable="item" /><a-alert
            v-for="warning in item.warnings"
            :key="warning.code"
            :message="warning.message"
            show-icon
            type="warning"
          /><OperationArtifactActions
            v-if="artifact(item.kind, item.platform)"
            :artifact="artifact(item.kind, item.platform)!"
            :base-url="baseUrl"
          /></section
      ></template>
      <span v-if="copyFeedback === 'success'" role="status">已复制</span
      ><a-alert
        v-if="copyFeedback === 'error'"
        message="复制失败，请手动复制"
        role="alert"
        show-icon
        type="error" /><OperationNextActions
        v-if="delivery.kind === 'v2'"
        :actions="delivery.nextActions"
        :on-show-sources="() => (sourcesExpanded = true)"
        @submit="emit('submitNextAction', $event)"
    /></template>
  </section>
</template>
