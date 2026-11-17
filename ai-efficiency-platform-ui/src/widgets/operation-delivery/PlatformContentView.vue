<script setup lang="ts">
import type {
  DeliveryProvenanceViewModel,
  PlatformContentViewModel,
} from '../../entities/operation-deliverable';
import MarkdownContent from '../../shared/ui/MarkdownContent.vue';
import SourceEvidencePanel from './SourceEvidencePanel.vue';
import styles from './OperationDelivery.module.css';
withDefaults(
  defineProps<{
    deliverable: PlatformContentViewModel;
    provenance: DeliveryProvenanceViewModel | null;
    sourcesExpanded?: boolean;
  }>(),
  { sourcesExpanded: undefined },
);
const emit = defineEmits<{ copyItem: [text: string]; sourcesExpandedChange: [value: boolean] }>();
</script>
<template>
  <article :aria-labelledby="`platform-content-${deliverable.id}`" :class="styles.deliveryDocument">
    <header :class="styles.documentHeader">
      <div>
        <h2 :id="`platform-content-${deliverable.id}`">{{ deliverable.title }}</h2>
        <p :class="styles.documentLead">{{ deliverable.lead }}</p>
      </div>
      <a-button @click="emit('copyItem', deliverable.copyText)">复制全文</a-button>
    </header>
    <section aria-label="正文" :class="styles.platformBody">
      <MarkdownContent :content="deliverable.content.body_markdown" />
    </section>
    <section
      v-if="deliverable.content.hashtags.length"
      aria-label="标签"
      :class="styles.platformTags"
    >
      <strong>标签</strong>
      <div>
        <a-tag v-for="tag in deliverable.content.hashtags" :key="tag">{{ tag }}</a-tag>
      </div>
    </section>
    <section
      v-if="deliverable.content.format_notes.length"
      :aria-labelledby="`format-notes-${deliverable.id}`"
      :class="styles.formatNotes"
    >
      <h3 :id="`format-notes-${deliverable.id}`">格式说明</h3>
      <ul>
        <li v-for="note in deliverable.content.format_notes" :key="note">{{ note }}</li>
      </ul>
    </section>
    <SourceEvidencePanel
      :citations="deliverable.citations"
      :expanded="sourcesExpanded"
      :provenance="provenance"
      @expanded-change="emit('sourcesExpandedChange', $event)"
    />
  </article>
</template>
