<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import MarkdownContent from '../../shared/ui/MarkdownContent.vue';
const props = defineProps<{ content: string; mode: 'typing' | 'complete' | 'frozen' }>();
const media = window.matchMedia('(prefers-reduced-motion: reduce)');
const reduced = ref(media.matches);
const graphemes = computed(() =>
  [...new Intl.Segmenter('zh-CN', { granularity: 'grapheme' }).segment(props.content)].map(
    (item) => item.segment,
  ),
);
const count = ref(reduced.value || props.mode === 'frozen' ? graphemes.value.length : 0);
const visible = computed(() =>
  reduced.value ? props.content : graphemes.value.slice(0, count.value).join(''),
);
const updatePreference = (event: MediaQueryListEvent) => {
  reduced.value = event.matches;
};
media.addEventListener('change', updatePreference);
watch(
  [() => props.content, () => props.mode, reduced, count],
  (_, __, onCleanup) => {
    if (reduced.value || props.mode === 'frozen' || count.value >= graphemes.value.length) return;
    const timer = window.setInterval(() => {
      count.value = Math.min(count.value + 1, graphemes.value.length);
    }, 24);
    onCleanup(() => window.clearInterval(timer));
  },
  { immediate: true },
);
onBeforeUnmount(() => media.removeEventListener('change', updatePreference));
</script>
<template>
  <div aria-label="助手回复"><MarkdownContent :content="visible" /></div>
</template>
