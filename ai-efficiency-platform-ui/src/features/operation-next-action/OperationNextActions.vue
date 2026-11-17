<script setup lang="ts">
import { computed } from 'vue';
import type { NextActionV2 } from '../../entities/operation-deliverable';
const props = defineProps<{ actions: NextActionV2[]; onShowSources?: () => void }>();
const emit = defineEmits<{ submit: [message: string]; showSources: [] }>();
const allowed = new Set([
  'rewrite_for_platform',
  'expand_item',
  'generate_script',
  'replace_candidates',
  'show_sources',
  'refine_constraints',
]);
const visible = computed(() => props.actions.filter((action) => allowed.has(action.action_type)));
function run(action: NextActionV2) {
  if (action.action_type === 'show_sources') {
    props.onShowSources?.();
    emit('showSources');
  } else emit('submit', action.label);
}
</script>
<template>
  <section v-if="visible.length" aria-label="后续动作">
    <a-space wrap
      ><a-button
        v-for="action in visible"
        :key="action.action_id"
        :disabled="action.action_type === 'show_sources' && !onShowSources"
        @click="run(action)"
        >{{ action.label }}</a-button
      ></a-space
    >
  </section>
</template>
